//! The lane-local `sim-native` boundary.
//!
//! The numerical implementation is the pinned PyBERT `native/pybert-core`
//! Rust crate copied from Git objects.  This file owns only the public CLI
//! boundary: strict JSON admission, the upstream metadata/diagnostic shape,
//! and a small dependency-free NPZ writer for the same `arrays.npz` artifact.

use std::{
    collections::BTreeMap,
    fs, io,
    path::{Path, PathBuf},
};

use flate2::{Compression, write::DeflateEncoder};
use serde::{Serialize, Serializer, ser::SerializeMap};
use serde_json::{Map, Value, json};
use thiserror::Error;

use crate::{
    NativeSimulationError, RunEventV1, RunStageV1, SimulationInputV1, SimulationOutputV1,
    simulate_native_v1,
};

pub const UPSTREAM_COMMIT: &str = "5bf6d7ea0ace261891aaeb611ffc1c267e160afe";
pub const UPSTREAM_TREE: &str = "5faef6bdb341d444ad65d82a11c0018b15805e24";
pub const NATIVE_CORE_SOURCE: &str = "native/pybert-core";
pub const PYTHON_BOUNDARY_SOURCE: &str = "native/pybert-python/src/lib.rs";
pub const NATIVE_CLI_SCHEMA: &str = "pybert.native-cli-result.v1";
pub const ERROR_SCHEMA: &str = "pybert.native-cli-error.v1";
// The nested SimulationOutputV1 envelope carries the same bounded numeric
// arrays as the NPZ artifact.  Keep the metadata budget aligned with the
// existing 16 MiB reference-input boundary instead of publishing an empty
// placeholder for larger, but still bounded, DuoBinary jitter results.
const MAX_ARTIFACT_METADATA_BYTES: usize = 16 * 1024 * 1024;

const ROOT_METADATA_KEYS: &[&str] = &[
    "schema",
    "input_file",
    "effective_input",
    "output",
    "backend_metadata",
    "effective_randomness",
    "diagnostics",
    "arrays_file",
    "workflow_metadata",
    "workflow_diagnostics",
];
const DIAGNOSTIC_KEYS: &[&str] = &[
    "pipeline",
    "capabilities",
    "events",
    "cancellation",
    "source",
    "workflow_diagnostics",
];

/// Row-major numeric data accepted by the content-addressed NPZ writer.
/// JSON control payloads remain one-dimensional for the v1 wire contract;
/// this type preserves two-dimensional eye/diagnostic arrays in artifacts.
#[derive(Clone, Debug, PartialEq)]
pub struct NumericArrayV1 {
    pub shape: Vec<usize>,
    pub values: Vec<f64>,
}

/// Dtype retained by the result adapter when an upstream BackendRunResult
/// carries discrete arrays.  The native simulation envelope remains f64, but
/// compare artifacts must not erase the source bool/int/float contract.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ArrayDTypeV1 {
    Bool,
    Int64,
    Float64,
}

impl ArrayDTypeV1 {
    pub fn label(self) -> &'static str {
        match self {
            Self::Bool => "bool",
            Self::Int64 => "int64",
            Self::Float64 => "float64",
        }
    }

    fn npy_descr(self) -> &'static str {
        match self {
            Self::Bool => "|b1",
            Self::Int64 => "<i8",
            Self::Float64 => "<f8",
        }
    }
}

/// Row-major typed array used by the PB-05 result adapter and NPZ writer.
/// Values use f64 storage at this boundary so the validated simulation output
/// and legacy JSON envelope can stay unchanged; `dtype` controls validation,
/// comparison strictness, and the actual NPY byte encoding.
#[derive(Clone, Debug, PartialEq)]
pub struct TypedArrayV1 {
    pub shape: Vec<usize>,
    pub values: Vec<f64>,
    pub dtype: ArrayDTypeV1,
}

#[derive(Debug, Error)]
pub enum DirectRunError {
    #[error("input JSON is invalid: {0}")]
    Json(String),
    #[error("input JSON root must be an object")]
    RootNotObject,
    #[error("input JSON contains unknown field {field} at {path}")]
    UnknownField { path: String, field: String },
    #[error("input JSON field {path} must be an object")]
    ObjectExpected { path: String },
    #[error("input JSON field {path} has an unsupported variant {variant}")]
    UnsupportedVariant { path: String, variant: String },
    #[error("native simulation rejected the request: {0}")]
    Native(#[from] NativeSimulationError),
    #[error("native simulation output is invalid: {0}")]
    Output(String),
    #[error("could not read or write sim-native artifact: {0}")]
    Io(#[from] io::Error),
    #[error("sim-native usage: sipi-pybert-direct INPUT_FILE --output-dir OUTPUT_DIR")]
    Usage,
}

impl DirectRunError {
    pub fn code(&self) -> &'static str {
        match self {
            Self::Json(_)
            | Self::RootNotObject
            | Self::UnknownField { .. }
            | Self::ObjectExpected { .. }
            | Self::UnsupportedVariant { .. } => "invalid_input",
            Self::Native(error) => match error {
                NativeSimulationError::UnsupportedPattern
                | NativeSimulationError::UnsupportedChannel
                | NativeSimulationError::UnsupportedExternalModel
                | NativeSimulationError::UnsupportedStatisticalEyeModulation
                | NativeSimulationError::UnsupportedFecModulation
                | NativeSimulationError::UnsupportedLegacyOptions => "unsupported_native_input",
                NativeSimulationError::ResourceLimitExceeded => "resource_limit_exceeded",
                NativeSimulationError::Cancelled => "cancelled",
                NativeSimulationError::Contract(_)
                | NativeSimulationError::InconsistentTimebase
                | NativeSimulationError::MissingDfeConfiguration
                | NativeSimulationError::MissingCtleConfiguration
                | NativeSimulationError::MissingViterbiConfiguration
                | NativeSimulationError::MissingViterbiDfe
                | NativeSimulationError::ViterbiPulseTooShort
                | NativeSimulationError::IncompleteFecObservations
                | NativeSimulationError::AdditiveNoiseLengthMismatch
                | NativeSimulationError::LegacyStageFrequencyOutOfRange => "invalid_native_input",
                NativeSimulationError::Pattern(_)
                | NativeSimulationError::Link(_)
                | NativeSimulationError::Signal(_)
                | NativeSimulationError::StatisticalEye(_)
                | NativeSimulationError::Dfe(_)
                | NativeSimulationError::Channel(_)
                | NativeSimulationError::Equalization(_)
                | NativeSimulationError::Isi(_)
                | NativeSimulationError::Fec(_)
                | NativeSimulationError::Ber(_)
                | NativeSimulationError::Crossing(_)
                | NativeSimulationError::Bathtub(_) => "native_execution_error",
            },
            Self::Output(_) => "invalid_native_output",
            Self::Io(_) => "artifact_io_error",
            Self::Usage => "usage",
        }
    }

    pub fn error_json(&self) -> String {
        serde_json::to_string(&json!({
            "schema": ERROR_SCHEMA,
            "code": self.code(),
            "message": self.to_string(),
            "source": {
                "repository": "pybert",
                "commit": UPSTREAM_COMMIT,
                "tree": UPSTREAM_TREE,
                "native_core": NATIVE_CORE_SOURCE,
                "python_extension_boundary": PYTHON_BOUNDARY_SOURCE,
            },
        }))
        .unwrap_or_else(|_| {
            format!(
                "{{\"schema\":\"{ERROR_SCHEMA}\",\"code\":\"{}\"}}",
                self.code()
            )
        })
    }
}

#[derive(Clone, Debug)]
pub struct DirectRunReport {
    pub input: SimulationInputV1,
    pub output: SimulationOutputV1,
    pub metadata: Value,
    pub diagnostics: Value,
    pub meta_path: PathBuf,
    pub arrays_path: PathBuf,
}

#[derive(Default)]
struct BoundedCountingWriter {
    bytes: usize,
    limit: usize,
    limit_hit: bool,
}

impl BoundedCountingWriter {
    fn new(limit: usize) -> Self {
        Self {
            limit,
            ..Self::default()
        }
    }
}

impl io::Write for BoundedCountingWriter {
    fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
        let Some(next) = self.bytes.checked_add(bytes.len()) else {
            self.limit_hit = true;
            return Err(io::Error::other("native artifact metadata size overflow"));
        };
        if next > self.limit {
            self.limit_hit = true;
            return Err(io::Error::other(
                "native artifact metadata preflight limit exceeded",
            ));
        }
        self.bytes = next;
        Ok(bytes.len())
    }

    fn flush(&mut self) -> io::Result<()> {
        Ok(())
    }
}

type ExtraObjectParts = (Map<String, Value>, Map<String, Value>);

fn split_extra_object(
    value: Value,
    reserved: &[&str],
    label: &str,
) -> Result<ExtraObjectParts, DirectRunError> {
    let Value::Object(extra) = value else {
        return Err(DirectRunError::Output(format!(
            "workflow {label} must be a JSON object"
        )));
    };
    let mut safe = Map::new();
    let mut namespaced = Map::new();
    for (key, value) in extra {
        if reserved.contains(&key.as_str()) {
            namespaced.insert(key, value);
        } else {
            safe.insert(key, value);
        }
    }
    Ok((safe, namespaced))
}

#[derive(Serialize)]
struct MetadataSourceV1 {
    repository: &'static str,
    commit: &'static str,
    tree: &'static str,
    native_core: &'static str,
    python_extension_boundary: &'static str,
}

#[derive(Serialize)]
struct MetadataEngineDetailsV1<'a> {
    backend: &'a str,
    native_simulation_v1: bool,
    source: &'a str,
    python_extension_boundary: &'static str,
}

#[derive(Serialize)]
struct MetadataBackendV1<'a> {
    schema: &'a str,
    run_id: &'a str,
    engine: MetadataEngineDetailsV1<'a>,
    metrics: &'a BTreeMap<String, f64>,
    aborted: bool,
    effective_seed: Option<u64>,
}

#[derive(Serialize)]
struct MetadataRandomnessV1<'a> {
    prbs_seed: Option<u64>,
    noise_seed: Option<u64>,
    noise: &'a Option<Value>,
}

struct MetadataDiagnosticsV1<'a> {
    safe: &'a Map<String, Value>,
    stages: &'a [RunStageV1],
    events: &'a [RunEventV1],
}

impl Serialize for MetadataDiagnosticsV1<'_> {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        let mut map = serializer.serialize_map(None)?;
        for (key, value) in self.safe {
            map.serialize_entry(key, value)?;
        }
        map.serialize_entry("pipeline", "typed_simulation_input_v1")?;
        map.serialize_entry("capabilities", self.stages)?;
        map.serialize_entry("events", self.events)?;
        map.serialize_entry(
            "cancellation",
            "checked_before_and_after_the_bounded_native_call",
        )?;
        map.serialize_entry(
            "source",
            &MetadataSourceV1 {
                repository: "pybert",
                commit: UPSTREAM_COMMIT,
                tree: UPSTREAM_TREE,
                native_core: NATIVE_CORE_SOURCE,
                python_extension_boundary: PYTHON_BOUNDARY_SOURCE,
            },
        )?;
        map.end()
    }
}

struct MetadataEnvelopeV1<'a> {
    safe_metadata: &'a Map<String, Value>,
    reserved_metadata: &'a Map<String, Value>,
    reserved_diagnostics: &'a Map<String, Value>,
    artifact_schema: &'a str,
    source_file: &'a Path,
    input: &'a SimulationInputV1,
    output: &'a SimulationOutputV1,
    backend_label: &'a str,
    native_core_backend: bool,
    backend_source: &'a str,
    effective_seed: Option<u64>,
    noise_effective_seed: Option<u64>,
    noise_metadata: &'a Option<Value>,
    safe_diagnostics: &'a Map<String, Value>,
}

impl Serialize for MetadataEnvelopeV1<'_> {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        let mut map = serializer.serialize_map(None)?;
        for (key, value) in self.safe_metadata {
            map.serialize_entry(key, value)?;
        }
        if !self.reserved_metadata.is_empty() {
            map.serialize_entry("workflow_metadata", self.reserved_metadata)?;
        }
        if !self.reserved_diagnostics.is_empty() {
            map.serialize_entry("workflow_diagnostics", self.reserved_diagnostics)?;
        }
        // Keep this order and field set in lockstep with the materialized
        // metadata map below.  Every canonical duplicate is counted here,
        // including nested arrays/metrics/events and provenance labels.
        map.serialize_entry("schema", self.artifact_schema)?;
        map.serialize_entry("input_file", self.source_file)?;
        map.serialize_entry("effective_input", self.input)?;
        map.serialize_entry("output", self.output)?;
        map.serialize_entry(
            "backend_metadata",
            &MetadataBackendV1 {
                schema: &self.output.schema,
                run_id: &self.output.run_id,
                engine: MetadataEngineDetailsV1 {
                    backend: self.backend_label,
                    native_simulation_v1: self.native_core_backend,
                    source: self.backend_source,
                    python_extension_boundary: "same_simulation_input_v1_contract",
                },
                metrics: &self.output.metrics,
                aborted: false,
                effective_seed: self.effective_seed,
            },
        )?;
        map.serialize_entry(
            "effective_randomness",
            &MetadataRandomnessV1 {
                prbs_seed: self.effective_seed,
                noise_seed: self.noise_effective_seed,
                noise: self.noise_metadata,
            },
        )?;
        map.serialize_entry(
            "diagnostics",
            &MetadataDiagnosticsV1 {
                safe: self.safe_diagnostics,
                stages: &self.output.capabilities.stages,
                events: &self.output.events,
            },
        )?;
        map.serialize_entry("arrays_file", "arrays.npz")?;
        map.end()
    }
}

fn preflight_metadata_size(envelope: &MetadataEnvelopeV1<'_>) -> Result<(), DirectRunError> {
    // This is the exact final metadata envelope, serialized through the same
    // pretty JSON writer as `meta.json`.  It borrows all large values and
    // stops before the budget boundary, so no `to_value` or large clone can
    // happen before this gate.
    let mut writer = BoundedCountingWriter::new(MAX_ARTIFACT_METADATA_BYTES);
    serde_json::to_writer_pretty(&mut writer, envelope).map_err(|error| {
        if writer.limit_hit {
            DirectRunError::Output("native artifact metadata preflight exceeds 16 MiB".into())
        } else {
            DirectRunError::Output(format!(
                "native artifact metadata preflight failed: {error}"
            ))
        }
    })?;
    Ok(())
}

/// Parse the exact native JSON contract before deserializing it.
///
/// The upstream core's Rust structs intentionally preserve compatibility with
/// older callers and therefore do not use `deny_unknown_fields`.  The pinned
/// `sim-native` CLI is strict at its command boundary; this preflight keeps
/// that boundary without changing the upstream core source.
pub fn strict_simulation_input_json(input: &[u8]) -> Result<SimulationInputV1, DirectRunError> {
    let value: Value =
        serde_json::from_slice(input).map_err(|error| DirectRunError::Json(error.to_string()))?;
    strict_shape(&value)?;
    serde_json::from_value(value).map_err(|error| DirectRunError::Json(error.to_string()))
}

pub fn run_sim_native_file(
    input_file: &Path,
    output_dir: &Path,
) -> Result<DirectRunReport, DirectRunError> {
    let input = fs::read(input_file)?;
    run_sim_native_json(&input, input_file, output_dir)
}

pub fn run_sim_native_json(
    input_json: &[u8],
    input_file: &Path,
    output_dir: &Path,
) -> Result<DirectRunReport, DirectRunError> {
    let input = strict_simulation_input_json(input_json)?;
    let output = native_cli_output(simulate_native_v1(&upstream_native_input(input.clone()))?);
    write_upstream_native_cli_artifacts(
        input,
        input_file,
        output_dir,
        output,
        raw_analysis_has_jitter_rel_thresh(input_json)?,
    )
}

/// Keep implementation-only arrays available to projected/legacy callers,
/// while matching the pinned `sim-native` artifact member and metric contract.
///
/// The native core retains the requested PRBS seed in its typed metrics for
/// engine-level callers.  The pinned CLI publishes that seed through its
/// effective-randomness metadata instead; projecting it into the CLI output
/// metrics creates a false extra key during complete-output comparison.
fn native_cli_output(mut output: SimulationOutputV1) -> SimulationOutputV1 {
    output.arrays.remove("tx_impulse_v_per_v");
    output.metrics.remove("effective_prbs_seed");
    output
}

fn upstream_native_input(mut input: SimulationInputV1) -> SimulationInputV1 {
    if let Some(ctle) = input.rx.ctle.as_mut() {
        // The pinned `NativeSimulationRequest` model does not declare this
        // direct-port extension. Its Pydantic boundary drops the extra key
        // before native execution, so `sim-native` must not let it change a
        // source-compatible artifact. The typed in-process API retains the
        // field for its separately documented direct-port boundary.
        ctle.impulse_response_v_per_v = None;
    }
    input
}

/// Write the exact artifact envelope published by the pinned `sim-native`
/// command.  SIPI-only nested output and provenance fields deliberately stay
/// out of this compatibility artifact: the upstream Python CLI does not
/// publish them, and adding them makes otherwise equal native payloads
/// incompatible.
fn write_upstream_native_cli_artifacts(
    input: SimulationInputV1,
    input_file: &Path,
    output_dir: &Path,
    output: SimulationOutputV1,
    include_jitter_rel_thresh: bool,
) -> Result<DirectRunReport, DirectRunError> {
    let effective_input = upstream_effective_input(&input, include_jitter_rel_thresh)?;
    let diagnostics = json!({
        "pipeline": "typed_simulation_input_v1",
        "capabilities": output.capabilities.stages,
        "events": output.events,
        "cancellation": "checked_before_and_after_the_bounded_native_call",
    });
    let backend_metadata = json!({
            "schema": output.schema,
            "run_id": output.run_id,
            "engine": upstream_native_engine_metadata(),
            "metrics": output.metrics,
            "aborted": false,
    });
    write_native_cli_artifacts_with_effective_input(
        input,
        input_file,
        output_dir,
        output,
        effective_input,
        backend_metadata,
        diagnostics,
        None,
    )
}

/// Publish the six-key artifact envelope owned by the upstream CLI while a
/// legacy adapter supplies its already-validated effective request and
/// result-adapter metadata.  This keeps large NPZ payloads out of meta.json;
/// the richer SIPI workflow writer remains separate by design.
pub(crate) fn write_native_cli_artifacts_with_effective_input(
    input: SimulationInputV1,
    input_file: &Path,
    output_dir: &Path,
    output: SimulationOutputV1,
    effective_input: Value,
    backend_metadata: Value,
    diagnostics: Value,
    array_shapes: Option<&BTreeMap<String, Vec<usize>>>,
) -> Result<DirectRunReport, DirectRunError> {
    output
        .validate()
        .map_err(|error| DirectRunError::Output(error.to_string()))?;
    let source_file = upstream_cli_input_path(input_file);
    let metadata = json!({
        "schema": NATIVE_CLI_SCHEMA,
        "input_file": source_file,
        "effective_input": effective_input,
        "backend_metadata": backend_metadata,
        "diagnostics": diagnostics,
        "arrays_file": "arrays.npz",
    });
    let metadata_bytes = serde_json::to_vec_pretty(&metadata)
        .map_err(|error| DirectRunError::Output(error.to_string()))?;
    if metadata_bytes.len() > MAX_ARTIFACT_METADATA_BYTES {
        return Err(DirectRunError::Output(
            "native artifact metadata exceeds 16 MiB".into(),
        ));
    }
    prepare_output_directory(output_dir)?;
    let meta_path = output_dir.join("meta.json");
    let arrays_path = output_dir.join("arrays.npz");
    fs::write(&meta_path, metadata_bytes)?;
    fs::write(
        &arrays_path,
        npz_bytes_with_shapes(&output.arrays, array_shapes)?,
    )?;
    Ok(DirectRunReport {
        input,
        output,
        metadata,
        diagnostics,
        meta_path,
        arrays_path,
    })
}

fn raw_analysis_has_jitter_rel_thresh(input_json: &[u8]) -> Result<bool, DirectRunError> {
    let value: Value = serde_json::from_slice(input_json)
        .map_err(|error| DirectRunError::Json(error.to_string()))?;
    Ok(value
        .get("analysis")
        .and_then(Value::as_object)
        .is_some_and(|analysis| analysis.contains_key("jitterRelThresh")))
}

fn upstream_effective_input(
    input: &SimulationInputV1,
    include_jitter_rel_thresh: bool,
) -> Result<Value, DirectRunError> {
    let mut value =
        serde_json::to_value(input).map_err(|error| DirectRunError::Output(error.to_string()))?;
    // `jitterRelThresh` is a SIPI direct-port control absent from the pinned
    // Python request model. Pydantic drops it before `_write_native_artifacts`;
    // retaining it in the emitted contract would be a wire drift.
    if !include_jitter_rel_thresh
        && let Some(analysis) = value.get_mut("analysis").and_then(Value::as_object_mut)
    {
        analysis.remove("jitterRelThresh");
    }
    Ok(value)
}

fn upstream_native_engine_metadata() -> Value {
    json!({
        "backend": "rust",
        "native_simulation_v1": true,
        "name": "pybert-python",
        "version": env!("CARGO_PKG_VERSION"),
        "build": {
            "profile": if cfg!(debug_assertions) { "debug" } else { "release" },
            "target": format!("{}-{}", std::env::consts::ARCH, std::env::consts::OS),
            "id": option_env!("PYBERT_NATIVE_BUILD_ID").unwrap_or("unknown"),
        },
    })
}

fn upstream_cli_input_path(input_file: &Path) -> String {
    let path = input_file
        .canonicalize()
        .unwrap_or_else(|_| input_file.to_path_buf());
    let display = path.to_string_lossy();
    display
        .strip_prefix(r"\\?\")
        .unwrap_or(display.as_ref())
        .to_owned()
}

/// Run an already projected, typed request through the same artifact boundary
/// as `sim-native`. Legacy YAML workflows use this entry point so projection
/// does not create a second numerical implementation or a second NPZ writer.
pub fn run_sim_native_input(
    input: SimulationInputV1,
    input_file: &Path,
    output_dir: &Path,
) -> Result<DirectRunReport, DirectRunError> {
    let output = native_cli_output(simulate_native_v1(&input)?);
    write_simulation_artifacts(input, input_file, output_dir, output, None)
}

/// Write a validated native result and optional workflow diagnostics.
///
/// The `extra_diagnostics` value is additive metadata owned by a workflow
/// wrapper (selection or comparison). It is never used to turn a failed core
/// execution into a successful artifact.
pub fn write_simulation_artifacts(
    input: SimulationInputV1,
    input_file: &Path,
    output_dir: &Path,
    output: SimulationOutputV1,
    extra_diagnostics: Option<Value>,
) -> Result<DirectRunReport, DirectRunError> {
    write_simulation_artifacts_with_schema(
        input,
        input_file,
        output_dir,
        output,
        extra_diagnostics,
        NATIVE_CLI_SCHEMA,
    )
}

/// Write a validated result with the schema owned by a workflow wrapper.
///
/// The numerical payload and diagnostics remain the same native v1 contract;
/// only the outer CLI result schema changes for `sim-auto` compatibility.
pub fn write_simulation_artifacts_with_schema(
    input: SimulationInputV1,
    input_file: &Path,
    output_dir: &Path,
    output: SimulationOutputV1,
    extra_diagnostics: Option<Value>,
    artifact_schema: &str,
) -> Result<DirectRunReport, DirectRunError> {
    write_simulation_artifacts_with_schema_and_backend(
        input,
        input_file,
        output_dir,
        output,
        extra_diagnostics,
        artifact_schema,
        "rust",
        None,
    )
}

/// Write a workflow result while preserving the result-adapter engine label.
///
/// The native payload remains the same validated v1 output.  `backend_label`
/// is provenance only; it must not be used to bypass native validation.
pub fn write_simulation_artifacts_with_schema_and_backend(
    input: SimulationInputV1,
    input_file: &Path,
    output_dir: &Path,
    output: SimulationOutputV1,
    extra_diagnostics: Option<Value>,
    artifact_schema: &str,
    backend_label: &str,
    extra_metadata: Option<Value>,
) -> Result<DirectRunReport, DirectRunError> {
    write_simulation_artifacts_with_schema_and_backend_and_shapes_and_typed_arrays(
        input,
        input_file,
        output_dir,
        output,
        extra_diagnostics,
        artifact_schema,
        backend_label,
        extra_metadata,
        None,
        None,
    )
}

/// Write a workflow result while retaining source array shapes for the NPZ
/// artifact.  External BackendRunResult payloads may contain two-dimensional
/// eye arrays even though the small typed JSON envelope stores flattened data.
pub fn write_simulation_artifacts_with_schema_and_backend_and_shapes(
    input: SimulationInputV1,
    input_file: &Path,
    output_dir: &Path,
    output: SimulationOutputV1,
    extra_diagnostics: Option<Value>,
    artifact_schema: &str,
    backend_label: &str,
    extra_metadata: Option<Value>,
    array_shapes: Option<&BTreeMap<String, Vec<usize>>>,
) -> Result<DirectRunReport, DirectRunError> {
    write_simulation_artifacts_with_schema_and_backend_and_shapes_and_typed_arrays(
        input,
        input_file,
        output_dir,
        output,
        extra_diagnostics,
        artifact_schema,
        backend_label,
        extra_metadata,
        array_shapes,
        None,
    )
}

/// Write a workflow result with source shapes and source dtypes retained in
/// the compressed NPZ artifact.  This is deliberately an additive API so the
/// native f64 artifact path keeps its existing callers and contract.
pub fn write_simulation_artifacts_with_schema_and_backend_and_shapes_and_typed_arrays(
    input: SimulationInputV1,
    input_file: &Path,
    output_dir: &Path,
    output: SimulationOutputV1,
    extra_diagnostics: Option<Value>,
    artifact_schema: &str,
    backend_label: &str,
    extra_metadata: Option<Value>,
    array_shapes: Option<&BTreeMap<String, Vec<usize>>>,
    typed_arrays: Option<&BTreeMap<String, TypedArrayV1>>,
) -> Result<DirectRunReport, DirectRunError> {
    if artifact_schema.trim().is_empty() {
        return Err(DirectRunError::Output(
            "native artifact schema must not be empty".into(),
        ));
    }
    if backend_label.trim().is_empty() {
        return Err(DirectRunError::Output(
            "native artifact backend label must not be empty".into(),
        ));
    }
    output
        .validate()
        .map_err(|error| DirectRunError::Output(error.to_string()))?;
    let (safe_diagnostics, reserved_diagnostics) = match extra_diagnostics {
        Some(value) => split_extra_object(value, DIAGNOSTIC_KEYS, "diagnostics")?,
        None => (Map::new(), Map::new()),
    };
    let (safe_metadata, reserved_metadata) = match extra_metadata {
        Some(value) => split_extra_object(value, ROOT_METADATA_KEYS, "metadata")?,
        None => (Map::new(), Map::new()),
    };
    let source_file = input_file
        .canonicalize()
        .unwrap_or_else(|_| input_file.to_path_buf());
    let effective_seed = match &input.pattern {
        crate::PatternV1::Prbs { seed, .. } => Some(*seed),
        crate::PatternV1::ExplicitBits { .. } => None,
    };
    // Keep the materialized-noise provenance separate from the PRBS seed:
    // callers may inject an explicit waveform while still using a seeded
    // pattern.  The legacy projection sets `effective_seed` on generated
    // noise, so only that path is labelled PCG64 below.
    let materialized_noise_seed = input
        .tx
        .additive_noise
        .as_ref()
        .and_then(|noise| noise.effective_seed);
    let noise_effective_seed = materialized_noise_seed;
    let noise_metadata = input.tx.additive_noise.as_ref().map(|noise| {
        let source = if noise.samples_v.iter().all(|sample| *sample == 0.0) {
            "zero_sigma"
        } else if materialized_noise_seed.is_some() {
            // The admitted legacy projection materializes NumPy-compatible
            // PCG64/normal samples before entering this typed boundary.
            // Preserve that generator provenance instead of mislabelling the
            // replay waveform as an arbitrary injected array.
            "pcg64"
        } else {
            "explicit_samples"
        };
        json!({
            "source": source,
            "generator": if source == "pcg64" {
                Some("numpy_pcg64_xsl_rr_128_64_ziggurat_double")
            } else {
                None
            },
            "effective_seed": noise_effective_seed,
            "sample_count": noise.samples_v.len(),
            "dtype": "float64",
            "sha256": sha256_f64_le(&noise.samples_v),
        })
    });
    let native_core_backend = matches!(backend_label, "rust" | "rust_native");
    let backend_source = if native_core_backend {
        "pinned_pybert_native_core"
    } else if backend_label == "rust_portable_reference" {
        "pb01_independent_rust_reference_pipeline_v1"
    } else {
        "backend_run_result_reference_payload"
    };
    preflight_metadata_size(&MetadataEnvelopeV1 {
        safe_metadata: &safe_metadata,
        reserved_metadata: &reserved_metadata,
        reserved_diagnostics: &reserved_diagnostics,
        artifact_schema,
        source_file: source_file.as_path(),
        input: &input,
        output: &output,
        backend_label,
        native_core_backend,
        backend_source,
        effective_seed,
        noise_effective_seed,
        noise_metadata: &noise_metadata,
        safe_diagnostics: &safe_diagnostics,
    })?;
    prepare_output_directory(output_dir)?;
    let mut diagnostics = Map::new();
    diagnostics.extend(safe_diagnostics);
    // Canonical diagnostic fields are inserted after caller extras.  A
    // hostile workflow payload can only be retained in the namespaced map.
    diagnostics.insert("pipeline".into(), json!("typed_simulation_input_v1"));
    diagnostics.insert(
        "capabilities".into(),
        json!(output.capabilities.stages.clone()),
    );
    diagnostics.insert("events".into(), json!(output.events.clone()));
    diagnostics.insert(
        "cancellation".into(),
        json!("checked_before_and_after_the_bounded_native_call"),
    );
    diagnostics.insert(
        "source".into(),
        json!({
            "repository": "pybert",
            "commit": UPSTREAM_COMMIT,
            "tree": UPSTREAM_TREE,
            "native_core": NATIVE_CORE_SOURCE,
            "python_extension_boundary": PYTHON_BOUNDARY_SOURCE,
        }),
    );
    let nested_output = serde_json::to_value(&output).map_err(|error| {
        DirectRunError::Output(format!("nested output serialization failed: {error}"))
    })?;
    let mut metadata = safe_metadata;
    if !reserved_metadata.is_empty() {
        metadata.insert("workflow_metadata".into(), Value::Object(reserved_metadata));
    }
    if !reserved_diagnostics.is_empty() {
        metadata.insert(
            "workflow_diagnostics".into(),
            Value::Object(reserved_diagnostics),
        );
    }
    // The typed nested envelope and all flat projections are canonical.  They
    // are deliberately written last so workflow payloads cannot shadow them.
    metadata.insert("schema".into(), json!(artifact_schema));
    metadata.insert("input_file".into(), json!(source_file));
    metadata.insert(
        "effective_input".into(),
        serde_json::to_value(&input).map_err(|error| DirectRunError::Output(error.to_string()))?,
    );
    metadata.insert("output".into(), nested_output);
    metadata.insert(
        "backend_metadata".into(),
        json!({
            "schema": output.schema,
            "run_id": output.run_id,
            "engine": {
                "backend": backend_label,
                "native_simulation_v1": native_core_backend,
                "source": backend_source,
                "python_extension_boundary": "same_simulation_input_v1_contract",
            },
            "metrics": output.metrics,
            "aborted": false,
            "effective_seed": effective_seed,
        }),
    );
    metadata.insert(
        "effective_randomness".into(),
        json!({
            "prbs_seed": effective_seed,
            "noise_seed": noise_effective_seed,
            "noise": noise_metadata,
        }),
    );
    let diagnostics_value = Value::Object(diagnostics);
    metadata.insert("diagnostics".into(), diagnostics_value.clone());
    metadata.insert("arrays_file".into(), json!("arrays.npz"));
    let meta_path = output_dir.join("meta.json");
    let arrays_path = output_dir.join("arrays.npz");
    let metadata_bytes = serde_json::to_vec_pretty(&metadata)
        .map_err(|error| DirectRunError::Output(error.to_string()))?;
    if metadata_bytes.len() > MAX_ARTIFACT_METADATA_BYTES {
        return Err(DirectRunError::Output(
            "native artifact metadata exceeds 16 MiB".into(),
        ));
    }
    fs::write(&meta_path, metadata_bytes)?;
    let arrays_bytes = match typed_arrays {
        Some(arrays) => npz_bytes_typed_nd(arrays)?,
        None => npz_bytes_with_shapes(&output.arrays, array_shapes)?,
    };
    fs::write(&arrays_path, arrays_bytes)?;
    Ok(DirectRunReport {
        input,
        output,
        metadata: Value::Object(metadata),
        diagnostics: diagnostics_value,
        meta_path,
        arrays_path,
    })
}

fn prepare_output_directory(path: &Path) -> Result<(), DirectRunError> {
    match fs::symlink_metadata(path) {
        Ok(metadata) if metadata.file_type().is_symlink() => {
            Err(io::Error::new(io::ErrorKind::InvalidInput, "output directory is a link").into())
        }
        Ok(metadata) if !metadata.is_dir() => Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "output path is not a directory",
        )
        .into()),
        Ok(_) => Ok(()),
        Err(error) if error.kind() == io::ErrorKind::NotFound => {
            fs::create_dir_all(path).map_err(DirectRunError::Io)
        }
        Err(error) => Err(error.into()),
    }
}

fn strict_shape(value: &Value) -> Result<(), DirectRunError> {
    let root = object(value, "$")?;
    keys(
        root,
        "$",
        &[
            "schema",
            "runId",
            "modulation",
            "pattern",
            "timebase",
            "channel",
            "tx",
            "rx",
            "analysis",
            "limits",
            "externalModels",
            "legacyOptions",
        ],
    )?;
    strict_pattern(
        root.get("pattern")
            .ok_or_else(|| DirectRunError::ObjectExpected {
                path: "$.pattern".into(),
            })?,
    )?;
    object_at(
        root,
        "timebase",
        "$.timebase",
        &["sampleInterval", "samplesPerUi", "dataRate", "nbits"],
    )?;
    strict_channel(
        root.get("channel")
            .ok_or_else(|| DirectRunError::ObjectExpected {
                path: "$.channel".into(),
            })?,
    )?;
    strict_tx(
        root.get("tx")
            .ok_or_else(|| DirectRunError::ObjectExpected {
                path: "$.tx".into(),
            })?,
    )?;
    strict_rx(
        root.get("rx")
            .ok_or_else(|| DirectRunError::ObjectExpected {
                path: "$.rx".into(),
            })?,
    )?;
    strict_analysis(
        root.get("analysis")
            .ok_or_else(|| DirectRunError::ObjectExpected {
                path: "$.analysis".into(),
            })?,
    )?;
    object_at(
        root,
        "limits",
        "$.limits",
        &["maxTotalSamples", "maxMemoryBytes", "maxDistributionStates"],
    )?;
    if let Some(models) = root.get("externalModels").and_then(Value::as_array) {
        for (index, model) in models.iter().enumerate() {
            object_keys(
                model,
                &format!("$.externalModels[{index}]"),
                &["kind", "capability"],
            )?;
        }
    }
    Ok(())
}

fn strict_channel(value: &Value) -> Result<(), DirectRunError> {
    let object = object(value, "$.channel")?;
    keys(object, "$.channel", &["kind", "value"])?;
    let kind = string_field(object, "kind", "$.channel")?;
    let allowed = match kind {
        "impulse_response" => &[
            "sampleInterval",
            "impulseResponseVoltsPerSecond",
            "sourceImpedance",
            "loadImpedance",
        ][..],
        "metallic_line" => &[
            "sampleInterval",
            "lengthM",
            "skinEffectResistanceOhmPerM",
            "crossoverAngularFrequencyRadPerS",
            "dcResistanceOhmPerM",
            "characteristicImpedance",
            "propagationVelocityMPerS",
            "lossTangent",
            "sourceImpedance",
            "sourceCapacitanceF",
            "loadImpedance",
            "loadCapacitanceF",
            "applyRaisedCosineWindow",
            "frequencyStepHz",
            "frequencyMaxHz",
            "impulseLength",
        ][..],
        "external_model" => &["kind", "capability"][..],
        variant => {
            return Err(DirectRunError::UnsupportedVariant {
                path: "$.channel.kind".into(),
                variant: variant.into(),
            });
        }
    };
    let value = object
        .get("value")
        .ok_or_else(|| DirectRunError::ObjectExpected {
            path: "$.channel.value".into(),
        })?;
    object_keys(value, "$.channel.value", allowed)
}

fn strict_pattern(value: &Value) -> Result<(), DirectRunError> {
    let object = object(value, "$.pattern")?;
    let kind = string_field(object, "kind", "$.pattern")?;
    match kind {
        "prbs" => keys(object, "$.pattern", &["kind", "order", "seed"]),
        "explicit_bits" => keys(object, "$.pattern", &["kind", "bitCount", "bits"]),
        variant => Err(DirectRunError::UnsupportedVariant {
            path: "$.pattern.kind".into(),
            variant: variant.into(),
        }),
    }
}

fn strict_tx(value: &Value) -> Result<(), DirectRunError> {
    let object = object(value, "$.tx")?;
    keys(
        object,
        "$.tx",
        &["amplitude", "ffe", "additiveNoise", "periodicNoise"],
    )?;
    strict_ffe(
        object
            .get("ffe")
            .ok_or_else(|| DirectRunError::ObjectExpected {
                path: "$.tx.ffe".into(),
            })?,
        "$.tx.ffe",
    )?;
    if let Some(value) = object.get("additiveNoise").filter(|value| !value.is_null()) {
        object_keys(value, "$.tx.additiveNoise", &["samplesV", "effectiveSeed"])?;
    }
    if let Some(value) = object.get("periodicNoise").filter(|value| !value.is_null()) {
        object_keys(value, "$.tx.periodicNoise", &["magnitude", "frequency"])?;
    }
    Ok(())
}

fn strict_rx(value: &Value) -> Result<(), DirectRunError> {
    let object = object(value, "$.rx")?;
    keys(
        object,
        "$.rx",
        &[
            "nativeCtleEnabled",
            "ctle",
            "ffe",
            "dfeTaps",
            "dfe",
            "viterbiEnabled",
            "viterbi",
        ],
    )?;
    if let Some(value) = object.get("ctle").filter(|value| !value.is_null()) {
        object_keys(
            value,
            "$.rx.ctle",
            &[
                "bandwidth",
                "peakFrequency",
                "peakMagnitudeDb",
                "frequencyStepHz",
                "frequencyMaxHz",
                "impulseResponseVPerV",
            ],
        )?;
    }
    strict_ffe(
        object
            .get("ffe")
            .ok_or_else(|| DirectRunError::ObjectExpected {
                path: "$.rx.ffe".into(),
            })?,
        "$.rx.ffe",
    )?;
    if let Some(value) = object.get("dfe").filter(|value| !value.is_null()) {
        object_keys(
            value,
            "$.rx.dfe",
            &[
                "gain",
                "decisionScaler",
                "nAve",
                "deltaT",
                "alpha",
                "nLockAve",
                "relLockTol",
                "lockSustain",
                "ideal",
                "bandwidth",
                "useAgc",
                "agcNAve",
                "tapLimits",
            ],
        )?;
    }
    if let Some(value) = object.get("viterbi").filter(|value| !value.is_null()) {
        object_keys(
            value,
            "$.rx.viterbi",
            &["stateSymbols", "fec", "noiseSigmaV", "maxStates"],
        )?;
    }
    Ok(())
}

fn strict_ffe(value: &Value, path: &str) -> Result<(), DirectRunError> {
    object_keys(value, path, &["enabled", "weights", "cursorPosition"])
}

fn strict_analysis(value: &Value) -> Result<(), DirectRunError> {
    let object = object(value, "$.analysis")?;
    keys(
        object,
        "$.analysis",
        &[
            "statisticalEye",
            "includeJitter",
            "includeBathtub",
            "berEyeBits",
            "jitterEyeUis",
            "jitterRelThresh",
        ],
    )?;
    if let Some(value) = object
        .get("statisticalEye")
        .filter(|value| !value.is_null())
    {
        object_keys(
            value,
            "$.analysis.statisticalEye",
            &[
                "targetBer",
                "contourBerLevels",
                "rxRjUi",
                "rxDjUi",
                "txRjUi",
                "txDjUi",
                "txDcdUi",
                "voltageResolution",
                "timePoints",
                "maxDistributionStates",
                "postReceiverOutput",
            ],
        )?;
    }
    Ok(())
}

fn object_at(
    parent: &Map<String, Value>,
    field: &str,
    path: &str,
    allowed: &[&str],
) -> Result<(), DirectRunError> {
    let value = parent
        .get(field)
        .ok_or_else(|| DirectRunError::ObjectExpected { path: path.into() })?;
    object_keys(value, path, allowed)
}

fn object<'a>(value: &'a Value, path: &str) -> Result<&'a Map<String, Value>, DirectRunError> {
    value
        .as_object()
        .ok_or_else(|| DirectRunError::ObjectExpected { path: path.into() })
}

fn object_keys(value: &Value, path: &str, allowed: &[&str]) -> Result<(), DirectRunError> {
    let object = object(value, path)?;
    keys(object, path, allowed)
}

fn keys(object: &Map<String, Value>, path: &str, allowed: &[&str]) -> Result<(), DirectRunError> {
    for key in object.keys() {
        if !allowed.contains(&key.as_str()) {
            return Err(DirectRunError::UnknownField {
                path: path.into(),
                field: key.clone(),
            });
        }
    }
    Ok(())
}

fn string_field<'a>(
    object: &'a Map<String, Value>,
    field: &str,
    path: &str,
) -> Result<&'a str, DirectRunError> {
    object
        .get(field)
        .and_then(Value::as_str)
        .ok_or_else(|| DirectRunError::Json(format!("{path}.{field} must be a string")))
}

fn npz_bytes_with_shapes(
    arrays: &BTreeMap<String, Vec<f64>>,
    array_shapes: Option<&BTreeMap<String, Vec<usize>>>,
) -> Result<Vec<u8>, DirectRunError> {
    let arrays = arrays
        .iter()
        .map(|(name, values)| {
            (
                name.clone(),
                NumericArrayV1 {
                    shape: array_shapes
                        .and_then(|shapes| shapes.get(name))
                        .cloned()
                        .unwrap_or_else(|| vec![values.len()]),
                    values: values.clone(),
                },
            )
        })
        .collect::<BTreeMap<_, _>>();
    npz_bytes_nd(&arrays)
}

/// Encode validated row-major f64 arrays as a deterministic Deflate NPZ.
pub fn npz_bytes_nd(arrays: &BTreeMap<String, NumericArrayV1>) -> Result<Vec<u8>, DirectRunError> {
    let typed = arrays
        .iter()
        .map(|(name, array)| {
            (
                name.clone(),
                TypedArrayV1 {
                    shape: array.shape.clone(),
                    values: array.values.clone(),
                    dtype: ArrayDTypeV1::Float64,
                },
            )
        })
        .collect::<BTreeMap<_, _>>();
    npz_bytes_typed_nd(&typed)
}

/// Encode bool, int64, and f64 arrays while retaining row-major shape and
/// Deflate compression.  The NPY member dtype is chosen from `array.dtype`,
/// rather than from whether the f64 staging values happen to look integral.
pub fn npz_bytes_typed_nd(
    arrays: &BTreeMap<String, TypedArrayV1>,
) -> Result<Vec<u8>, DirectRunError> {
    let mut npy_arrays = BTreeMap::new();
    for (name, array) in arrays {
        let expected = array
            .shape
            .iter()
            .try_fold(1usize, |product, dimension| product.checked_mul(*dimension))
            .ok_or_else(|| DirectRunError::Output("NPZ shape overflow".into()))?;
        if array.shape.is_empty() || expected != array.values.len() {
            return Err(DirectRunError::Output(format!(
                "NPZ array {name:?} has an invalid shape or value"
            )));
        }
        let data = npy_typed_nd(array)?;
        npy_arrays.insert(name.clone(), data);
    }
    npz_bytes_from_npy(&npy_arrays)
}

fn npz_bytes_from_npy(arrays: &BTreeMap<String, Vec<u8>>) -> Result<Vec<u8>, DirectRunError> {
    let mut result = Vec::new();
    let mut central = Vec::new();
    for (name, data) in arrays {
        let filename = format!("{name}.npy");
        let crc = crc32(data);
        let mut encoder = DeflateEncoder::new(Vec::new(), Compression::fast());
        std::io::Write::write_all(&mut encoder, data)
            .map_err(|error| DirectRunError::Output(format!("NPZ compression failed: {error}")))?;
        let compressed = encoder
            .finish()
            .map_err(|error| DirectRunError::Output(format!("NPZ compression failed: {error}")))?;
        let offset = u32::try_from(result.len())
            .map_err(|_| DirectRunError::Output("NPZ offset overflow".into()))?;
        write_local_header(
            &mut result,
            filename.as_bytes(),
            crc,
            compressed.len(),
            data.len(),
        )?;
        result.extend_from_slice(&compressed);
        write_central_header(
            &mut central,
            filename.as_bytes(),
            crc,
            compressed.len(),
            data.len(),
            offset,
        )?;
    }
    let central_offset = u32::try_from(result.len())
        .map_err(|_| DirectRunError::Output("NPZ central offset overflow".into()))?;
    result.extend_from_slice(&central);
    let count = u16::try_from(arrays.len())
        .map_err(|_| DirectRunError::Output("too many NPZ arrays".into()))?;
    let central_size = u32::try_from(central.len())
        .map_err(|_| DirectRunError::Output("NPZ central size overflow".into()))?;
    result.extend_from_slice(&0x0605_4b50_u32.to_le_bytes());
    result.extend_from_slice(&0_u16.to_le_bytes());
    result.extend_from_slice(&0_u16.to_le_bytes());
    result.extend_from_slice(&count.to_le_bytes());
    result.extend_from_slice(&count.to_le_bytes());
    result.extend_from_slice(&central_size.to_le_bytes());
    result.extend_from_slice(&central_offset.to_le_bytes());
    result.extend_from_slice(&0_u16.to_le_bytes());
    Ok(result)
}

fn npy_typed_nd(array: &TypedArrayV1) -> Result<Vec<u8>, DirectRunError> {
    let mut bytes = Vec::new();
    match array.dtype {
        ArrayDTypeV1::Bool => {
            for value in &array.values {
                if !value.is_finite() || (*value != 0.0 && *value != 1.0) {
                    return Err(DirectRunError::Output(
                        "NPZ bool arrays must contain only finite 0/1 values".into(),
                    ));
                }
                bytes.push(u8::from(*value != 0.0));
            }
        }
        ArrayDTypeV1::Int64 => {
            for value in &array.values {
                if !value.is_finite() || value.fract() != 0.0 {
                    return Err(DirectRunError::Output(
                        "NPZ int64 arrays must contain finite integral values".into(),
                    ));
                }
                let converted = *value as i64;
                if (converted as f64) != *value {
                    return Err(DirectRunError::Output(
                        "NPZ int64 array value is outside the exact i64 range".into(),
                    ));
                }
                bytes.extend_from_slice(&converted.to_le_bytes());
            }
        }
        ArrayDTypeV1::Float64 => {
            if array.values.iter().any(|value| !value.is_finite()) {
                return Err(DirectRunError::Output(
                    "NPZ float64 arrays must contain finite values".into(),
                ));
            }
            for value in &array.values {
                bytes.extend_from_slice(&value.to_le_bytes());
            }
        }
    }
    npy_bytes_with_body(array.dtype.npy_descr(), &array.shape, &bytes)
}

fn npy_bytes_with_body(
    descr: &str,
    shape: &[usize],
    values: &[u8],
) -> Result<Vec<u8>, DirectRunError> {
    let shape_text = if shape.len() == 1 {
        format!("({},)", shape[0])
    } else {
        format!(
            "({})",
            shape
                .iter()
                .map(usize::to_string)
                .collect::<Vec<_>>()
                .join(", ")
        )
    };
    let mut header =
        format!("{{'descr': '{descr}', 'fortran_order': False, 'shape': {shape_text}, }}");
    let preamble = 10_usize;
    let padding = (16 - (preamble + header.len() + 1) % 16) % 16;
    header.extend(std::iter::repeat_n(' ', padding));
    header.push('\n');
    let header_len = u16::try_from(header.len())
        .map_err(|_| DirectRunError::Output("NPY header is too long".into()))?;
    let mut result = Vec::with_capacity(preamble + header.len() + values.len());
    result.extend_from_slice(b"\x93NUMPY");
    result.extend_from_slice(&[1, 0]);
    result.extend_from_slice(&header_len.to_le_bytes());
    result.extend_from_slice(header.as_bytes());
    result.extend_from_slice(values);
    Ok(result)
}

fn write_local_header(
    result: &mut Vec<u8>,
    filename: &[u8],
    crc: u32,
    compressed_length: usize,
    uncompressed_length: usize,
) -> Result<(), DirectRunError> {
    let compressed_length = u32::try_from(compressed_length)
        .map_err(|_| DirectRunError::Output("NPZ member too large".into()))?;
    let uncompressed_length = u32::try_from(uncompressed_length)
        .map_err(|_| DirectRunError::Output("NPZ member too large".into()))?;
    let filename_len = u16::try_from(filename.len())
        .map_err(|_| DirectRunError::Output("NPZ filename too long".into()))?;
    result.extend_from_slice(&0x0403_4b50_u32.to_le_bytes());
    result.extend_from_slice(&20_u16.to_le_bytes());
    result.extend_from_slice(&0_u16.to_le_bytes());
    result.extend_from_slice(&8_u16.to_le_bytes());
    result.extend_from_slice(&0_u16.to_le_bytes());
    result.extend_from_slice(&0_u16.to_le_bytes());
    result.extend_from_slice(&crc.to_le_bytes());
    result.extend_from_slice(&compressed_length.to_le_bytes());
    result.extend_from_slice(&uncompressed_length.to_le_bytes());
    result.extend_from_slice(&filename_len.to_le_bytes());
    result.extend_from_slice(&0_u16.to_le_bytes());
    result.extend_from_slice(filename);
    Ok(())
}

fn write_central_header(
    result: &mut Vec<u8>,
    filename: &[u8],
    crc: u32,
    compressed_length: usize,
    uncompressed_length: usize,
    offset: u32,
) -> Result<(), DirectRunError> {
    let compressed_length = u32::try_from(compressed_length)
        .map_err(|_| DirectRunError::Output("NPZ member too large".into()))?;
    let uncompressed_length = u32::try_from(uncompressed_length)
        .map_err(|_| DirectRunError::Output("NPZ member too large".into()))?;
    let filename_len = u16::try_from(filename.len())
        .map_err(|_| DirectRunError::Output("NPZ filename too long".into()))?;
    result.extend_from_slice(&0x0201_4b50_u32.to_le_bytes());
    result.extend_from_slice(&20_u16.to_le_bytes());
    result.extend_from_slice(&20_u16.to_le_bytes());
    result.extend_from_slice(&0_u16.to_le_bytes());
    result.extend_from_slice(&8_u16.to_le_bytes());
    result.extend_from_slice(&0_u16.to_le_bytes());
    result.extend_from_slice(&0_u16.to_le_bytes());
    result.extend_from_slice(&crc.to_le_bytes());
    result.extend_from_slice(&compressed_length.to_le_bytes());
    result.extend_from_slice(&uncompressed_length.to_le_bytes());
    result.extend_from_slice(&filename_len.to_le_bytes());
    result.extend_from_slice(&0_u16.to_le_bytes());
    result.extend_from_slice(&0_u16.to_le_bytes());
    result.extend_from_slice(&0_u16.to_le_bytes());
    result.extend_from_slice(&0_u16.to_le_bytes());
    result.extend_from_slice(&0_u32.to_le_bytes());
    result.extend_from_slice(&offset.to_le_bytes());
    result.extend_from_slice(filename);
    Ok(())
}

fn crc32(bytes: &[u8]) -> u32 {
    let mut crc = 0xffff_ffff_u32;
    for byte in bytes {
        crc ^= u32::from(*byte);
        for _ in 0..8 {
            let mask = 0_u32.wrapping_sub(crc & 1);
            crc = (crc >> 1) ^ (0xedb8_8320_u32 & mask);
        }
    }
    !crc
}

fn sha256_f64_le(values: &[f64]) -> String {
    // Keep this dependency-free and content-addressed.  The artifact contract
    // uses the same byte order as NumPy's contiguous float64 arrays.
    let mut state = Sha256State::new();
    for value in values {
        state.update(&value.to_le_bytes());
    }
    state.finish_hex()
}

struct Sha256State {
    h: [u32; 8],
    buffer: Vec<u8>,
    length_bits: u64,
}

impl Sha256State {
    fn new() -> Self {
        Self {
            h: [
                0x6a09_e667,
                0xbb67_ae85,
                0x3c6e_f372,
                0xa54f_f53a,
                0x510e_527f,
                0x9b05_688c,
                0x1f83_d9ab,
                0x5be0_cd19,
            ],
            buffer: Vec::new(),
            length_bits: 0,
        }
    }

    fn update(&mut self, bytes: &[u8]) {
        self.length_bits = self.length_bits.wrapping_add((bytes.len() as u64) * 8);
        self.buffer.extend_from_slice(bytes);
        while self.buffer.len() >= 64 {
            let block = self.buffer[..64].to_vec();
            self.buffer.drain(..64);
            self.compress(&block);
        }
    }

    fn finish_hex(mut self) -> String {
        self.buffer.push(0x80);
        while self.buffer.len() % 64 != 56 {
            self.buffer.push(0);
        }
        self.buffer
            .extend_from_slice(&self.length_bits.to_be_bytes());
        while let Some(block) = (self.buffer.len() >= 64).then(|| self.buffer[..64].to_vec()) {
            self.buffer.drain(..64);
            self.compress(&block);
        }
        let mut output = String::with_capacity(64);
        for word in self.h {
            use std::fmt::Write as _;
            let _ = write!(output, "{word:08x}");
        }
        output
    }

    fn compress(&mut self, block: &[u8]) {
        const K: [u32; 64] = [
            0x428a_2f98,
            0x7137_4491,
            0xb5c0_fbcf,
            0xe9b5_dba5,
            0x3956_c25b,
            0x59f1_11f1,
            0x923f_82a4,
            0xab1c_5ed5,
            0xd807_aa98,
            0x1283_5b01,
            0x2431_85be,
            0x550c_7dc3,
            0x72be_5d74,
            0x80de_b1fe,
            0x9bdc_06a7,
            0xc19b_f174,
            0xe49b_69c1,
            0xefbe_4786,
            0x0fc1_9dc6,
            0x240c_a1cc,
            0x2de9_2c6f,
            0x4a74_84aa,
            0x5cb0_a9dc,
            0x76f9_88da,
            0x983e_5152,
            0xa831_c66d,
            0xb003_27c8,
            0xbf59_7fc7,
            0xc6e0_0bf3,
            0xd5a7_9147,
            0x06ca_6351,
            0x1429_2967,
            0x27b7_0a85,
            0x2e1b_2138,
            0x4d2c_6dfc,
            0x5338_0d13,
            0x650a_7354,
            0x766a_0abb,
            0x81c2_c92e,
            0x9272_2c85,
            0xa2bf_e8a1,
            0xa81a_664b,
            0xc24b_8b70,
            0xc76c_51a3,
            0xd192_e819,
            0xd699_0624,
            0xf40e_3585,
            0x106a_a070,
            0x19a4_c116,
            0x1e37_6c08,
            0x2748_774c,
            0x34b0_bcb5,
            0x391c_0cb3,
            0x4ed8_aa4a,
            0x5b9c_ca4f,
            0x682e_6ff3,
            0x748f_82ee,
            0x78a5_636f,
            0x84c8_7814,
            0x8cc7_0208,
            0x90be_fffa,
            0xa450_6ceb,
            0xbef9_a3f7,
            0xc671_78f2,
        ];
        let mut w = [0_u32; 64];
        for (index, chunk) in block.chunks_exact(4).take(16).enumerate() {
            w[index] = u32::from_be_bytes([chunk[0], chunk[1], chunk[2], chunk[3]]);
        }
        for index in 16..64 {
            let s0 = w[index - 15].rotate_right(7)
                ^ w[index - 15].rotate_right(18)
                ^ (w[index - 15] >> 3);
            let s1 = w[index - 2].rotate_right(17)
                ^ w[index - 2].rotate_right(19)
                ^ (w[index - 2] >> 10);
            w[index] = w[index - 16]
                .wrapping_add(s0)
                .wrapping_add(w[index - 7])
                .wrapping_add(s1);
        }
        let mut state = self.h;
        for index in 0..64 {
            let s1 =
                state[4].rotate_right(6) ^ state[4].rotate_right(11) ^ state[4].rotate_right(25);
            let choose = (state[4] & state[5]) ^ ((!state[4]) & state[6]);
            let temp1 = state[7]
                .wrapping_add(s1)
                .wrapping_add(choose)
                .wrapping_add(K[index])
                .wrapping_add(w[index]);
            let s0 =
                state[0].rotate_right(2) ^ state[0].rotate_right(13) ^ state[0].rotate_right(22);
            let majority = (state[0] & state[1]) ^ (state[0] & state[2]) ^ (state[1] & state[2]);
            let temp2 = s0.wrapping_add(majority);
            state[7] = state[6];
            state[6] = state[5];
            state[5] = state[4];
            state[4] = state[3].wrapping_add(temp1);
            state[3] = state[2];
            state[2] = state[1];
            state[1] = state[0];
            state[0] = temp1.wrapping_add(temp2);
        }
        for (word, value) in self.h.iter_mut().zip(state) {
            *word = word.wrapping_add(value);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn native_cli_hides_internal_arrays_and_engine_only_metrics() {
        let arrays = BTreeMap::from([
            ("tx_impulse_v_per_v".to_owned(), vec![1.0]),
            ("tx_waveform_v".to_owned(), vec![2.0]),
        ]);
        let output = SimulationOutputV1 {
            schema: crate::SIMULATION_SCHEMA_V1.to_owned(),
            run_id: "test-run".to_owned(),
            capabilities: crate::EngineCapabilitiesV1 {
                stages: Vec::new(),
                external_models: Vec::new(),
            },
            metrics: BTreeMap::from([("effective_prbs_seed".to_owned(), 17.0)]),
            events: Vec::new(),
            arrays,
            artifacts: Vec::new(),
        };

        let output = native_cli_output(output);

        assert!(!output.arrays.contains_key("tx_impulse_v_per_v"));
        assert_eq!(output.arrays.get("tx_waveform_v"), Some(&vec![2.0]));
        assert!(!output.metrics.contains_key("effective_prbs_seed"));
    }

    #[test]
    fn metadata_preflight_counter_is_bounded_and_checked() {
        let mut writer = BoundedCountingWriter::new(3);
        assert!(io::Write::write_all(&mut writer, b"1234").is_err());
        assert!(writer.limit_hit);

        let writer = BoundedCountingWriter {
            bytes: usize::MAX,
            limit: usize::MAX,
            limit_hit: false,
        };
        let mut writer = writer;
        assert!(io::Write::write_all(&mut writer, b"1").is_err());
        assert!(writer.limit_hit);
    }
}
