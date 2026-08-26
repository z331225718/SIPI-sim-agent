//! Native leaves for the pinned PyBERT `sim-rust`, `sim-auto`, and
//! Native leaves for the pinned PyBERT workflow commands.
//!
//! These leaves deliberately stay narrow. Legacy configuration is admitted
//! only by the bounded projection, auto selection records the pinned gate and
//! runs the portable Rust reference for admitted inputs, and compare gates
//! actual result payloads rather than process status.

use std::{
    collections::{BTreeMap, BTreeSet},
    fs, io,
    path::{Path, PathBuf},
};

use serde_json::{Value, json};
use thiserror::Error;

use crate::runner::{ArrayDTypeV1, TypedArrayV1, UPSTREAM_COMMIT, UPSTREAM_TREE};
use crate::{
    ArtifactRefV1, DirectRunError, DirectRunReport, LegacyRuntimeError, SimulationInputV1,
    SimulationOutputV1, StatisticalEyeConfigV1, Volts, project_legacy_config_v1,
    simulate_native_v1, write_simulation_artifacts,
    write_simulation_artifacts_with_schema_and_backend_and_shapes_and_typed_arrays,
};

const MAX_REFERENCE_JSON_BYTES: u64 = 16 * 1024 * 1024;
const MIN_STATISTICAL_TIME_POINTS: u32 = 32;
const MAX_STATISTICAL_TIME_POINTS: u32 = 10_000;
const COMPARE_RTOL: f64 = 1.0e-8;
const COMPARE_ATOL: f64 = 1.0e-10;
const AUTO_PARITY_GATE_VERSION: &str = "pybert.native-auto-parity.v1";
const COMPARE_RESULT_SCHEMA: &str = "pybert.cli-compare-result.v1";

fn auto_parity_blocked(selection: Value) -> WorkflowError {
    WorkflowError::AutoParityBlocked {
        selection: serde_json::to_string(&selection).unwrap_or_else(|_| {
            "{\"engine_selection\":{\"requested\":\"auto\",\"selected\":\"python\"}}".into()
        }),
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum CompareReference {
    /// Use the independent Rust PB-01 portable reference pipeline and a native
    /// candidate. This is a complete payload contract, not an upstream Python
    /// parity claim.
    Shadow,
    /// Load a serialized result payload supplied by an external oracle. The
    /// payload may wrap `SimulationOutputV1` with metadata, diagnostics, and
    /// performance maps from the upstream result adapter.
    Json(PathBuf),
}

#[derive(Clone, Debug)]
struct ComparePayload {
    output: SimulationOutputV1,
    arrays: BTreeMap<String, ArrayPayload>,
    /// A reference payload may expose the typed output plus a legacy flat
    /// projection.  The projection is validated at ingestion and retained as
    /// an explicit gate instead of allowing the flat fields to shadow the
    /// nested `SimulationOutputV1` values.
    projection: Value,
    metadata: Value,
    diagnostics: Value,
    performance: Value,
}

#[derive(Clone, Debug)]
struct ArrayPayload {
    shape: Vec<usize>,
    values: Vec<f64>,
    dtype: ArrayDTypeV1,
}

impl ComparePayload {
    fn from_output(output: SimulationOutputV1) -> Self {
        // Keep the candidate side in the same BackendRunResult shape emitted by
        // the pinned Python result adapter.  Comparing only `output` would let
        // metadata/diagnostics drift while arrays and scalar metrics happened
        // to agree.
        let schema = output.schema.clone();
        let run_id = output.run_id.clone();
        let stages = output.capabilities.stages.clone();
        let metrics = output.metrics.clone();
        let events = output.events.clone();
        Self {
            arrays: output
                .arrays
                .iter()
                .map(|(name, values)| {
                    (
                        name.clone(),
                        ArrayPayload {
                            shape: vec![values.len()],
                            values: values.clone(),
                            dtype: ArrayDTypeV1::Float64,
                        },
                    )
                })
                .collect(),
            output,
            projection: json!({
                "present": false,
                "passed": true,
                "source": "typed_simulation_output",
            }),
            metadata: json!({
                "schema": schema,
                "run_id": run_id,
                "engine": {
                    "backend": "rust",
                    "native_simulation_v1": true,
                },
                "metrics": metrics,
                "aborted": false,
            }),
            diagnostics: json!({
                "pipeline": "typed_simulation_input_v1",
                "capabilities": stages,
                "events": events,
                "cancellation": "checked_before_and_after_the_bounded_native_call",
            }),
            performance: json!({}),
        }
    }
}

#[derive(Debug, Error)]
pub enum WorkflowError {
    #[error("workflow input is invalid: {0}")]
    InvalidInput(String),
    #[error("workflow projection is unsupported: {0}")]
    Unsupported(String),
    #[error("workflow reference is unavailable: {0}")]
    ReferenceUnavailable(String),
    #[error("workflow comparison failed: {0}")]
    Comparison(String),
    #[error("sim-auto parity gate is blocked: {selection}")]
    AutoParityBlocked { selection: String },
    #[error("workflow artifact failed: {0}")]
    Artifact(String),
    #[error("workflow I/O failed: {0}")]
    Io(#[from] io::Error),
}

impl WorkflowError {
    pub fn code(&self) -> &'static str {
        match self {
            Self::InvalidInput(_) => "invalid_input",
            Self::Unsupported(_) => "unsupported_workflow",
            Self::ReferenceUnavailable(_) => "reference_unavailable",
            Self::Comparison(_) => "comparison_error",
            Self::AutoParityBlocked { .. } => "auto_parity_blocked",
            Self::Artifact(_) => "artifact_error",
            Self::Io(_) => "artifact_io_error",
        }
    }

    pub fn error_json(&self) -> String {
        let mut payload = json!({
            "schema": "pybert.workflow-error.v1",
            "code": self.code(),
            "message": self.to_string(),
            "source": {
                "repository": "pybert",
                "commit": UPSTREAM_COMMIT,
                "tree": UPSTREAM_TREE,
            },
        });
        if let Some(object) = payload.as_object_mut() {
            match self {
                Self::AutoParityBlocked { selection } => {
                    object.insert(
                        "diagnostics".into(),
                        serde_json::from_str(selection).unwrap_or_else(|_| {
                            json!({
                                "engine_selection": {
                                    "requested": "auto",
                                    "selected": "python",
                                    "fallback_reason": selection,
                                }
                            })
                        }),
                    );
                }
                Self::ReferenceUnavailable(message) => {
                    object.insert(
                        "diagnostics".into(),
                        json!({
                            "comparison": {
                                "schema": COMPARE_RESULT_SCHEMA.replace("cli-compare-result", "engine-compare"),
                                "passed": false,
                                "reason": "not_evaluated",
                                "status_only_comparison": false,
                                "reference_required": "external_python_reference_required",
                            },
                            "compare_reference": {
                                "source": "external_python_reference_required",
                                "reference_kind": "independent_external_oracle",
                                "reference_retained_on_candidate_failure": false,
                            },
                            "reason": message,
                        }),
                    );
                }
                _ => {}
            }
        }
        serde_json::to_string(&payload).unwrap_or_else(|_| {
            format!(
                "{{\"schema\":\"pybert.workflow-error.v1\",\"code\":\"{}\"}}",
                self.code()
            )
        })
    }
}

impl From<LegacyRuntimeError> for WorkflowError {
    fn from(error: LegacyRuntimeError) -> Self {
        match error {
            LegacyRuntimeError::Unsupported(message) => Self::Unsupported(message),
            LegacyRuntimeError::ResourceLimit(message) => Self::InvalidInput(message),
            other => Self::InvalidInput(other.to_string()),
        }
    }
}

impl From<DirectRunError> for WorkflowError {
    fn from(error: DirectRunError) -> Self {
        Self::Artifact(error.to_string())
    }
}

/// Execute the strict native projection used by `sim-rust`.
pub fn run_sim_rust_file(
    config_file: &Path,
    output_dir: &Path,
    statistical_time_points: Option<u32>,
) -> Result<DirectRunReport, WorkflowError> {
    let (_, mut input) = projected_input(config_file)?;
    apply_statistical_override(&mut input, statistical_time_points)?;
    run_projected_input(input, config_file, output_dir)
}

/// Execute `sim-auto` with the pinned selection semantics.
///
/// The pinned upstream gate selects Python while its Web result contract is
/// blocked. This Rust-only lane cannot claim to have executed that Python
/// backend, so it fails closed instead of silently substituting an independent
/// Rust reference implementation.
pub fn run_sim_auto_file(
    config_file: &Path,
    output_dir: &Path,
    statistical_time_points: Option<u32>,
) -> Result<DirectRunReport, WorkflowError> {
    let projection_error = match projected_input(config_file) {
        Ok((_, mut input)) => apply_statistical_override(&mut input, statistical_time_points)
            .err()
            .map(|error| error.to_string()),
        Err(error) => Some(error.to_string()),
    };
    let selection = json!({
        "requested": "auto",
        "selected": "python",
        "fallback_reason": projection_error.as_deref().unwrap_or(
            "native Web result contract parity is incomplete",
        ),
        "fallback_status": "external_python_reference_required",
        "implementation": "external_python_reference_required",
        "rust_only": false,
        "parity_gate": {
            "version": AUTO_PARITY_GATE_VERSION,
            "status": if projection_error.is_some() { "not_reached" } else { "blocked" },
            "reason": projection_error.as_deref().unwrap_or(
                "native Web result contract parity is incomplete",
            ),
        }
    });
    let _ = output_dir;
    Err(auto_parity_blocked(json!({
        "engine_selection": selection,
        "parity_gate": {
            "version": AUTO_PARITY_GATE_VERSION,
            "status": if projection_error.is_some() { "not_reached" } else { "blocked" },
            "reason": projection_error.as_deref().unwrap_or(
                "native Web result contract parity is incomplete",
            ),
        }
    })))
}

/// Execute `sim-compare` and retain the externally supplied reference payload
/// in the output artifact. The upstream Python result adapter is the reference
/// owner; a missing reference is rejected rather than self-comparing a Rust
/// candidate against a same-crate shadow.
pub fn run_sim_compare_file(
    config_file: &Path,
    output_dir: &Path,
    statistical_time_points: Option<u32>,
    reference_json: Option<&Path>,
) -> Result<DirectRunReport, WorkflowError> {
    let reference_path = reference_json.ok_or_else(|| {
        WorkflowError::ReferenceUnavailable(
            "external_python_reference_required: sim-compare requires --reference-json; comparison is not_evaluated without an independent reference payload".into(),
        )
    })?;
    let (_, mut input) = projected_input(config_file)?;
    apply_statistical_override(&mut input, statistical_time_points)?;

    let reference = read_reference_payload(reference_path)?;
    let reference_source = "external_json";
    let candidate = match simulate_native_v1(&input) {
        Ok(output) => Some(ComparePayload::from_output(output)),
        Err(error) => {
            let comparison = json!({
                "schema": "pybert.engine-compare.v1",
                "passed": false,
                "reason": "candidate_error",
                "candidate_backend": "rust",
                "error": error.to_string(),
                "status_only_comparison": false,
            });
            let diagnostics = json!({
                "pipeline": "upstream_backend_run_result_adapter",
                "comparison": comparison,
                "compare_reference": {
                    "source": reference_source,
                    "reference_kind": reference_kind(reference_source),
                    "payload": "arrays_metrics_diagnostics",
                    "reference_retained_on_candidate_failure": true,
                    "rtol": COMPARE_RTOL,
                    "atol": COMPARE_ATOL
                },
                "reference_diagnostics": reference.diagnostics,
            });
            return write_compare_artifacts(
                input,
                config_file,
                output_dir,
                reference.output,
                diagnostics,
                &reference.metadata,
                &reference.arrays,
            )
            .map_err(WorkflowError::from);
        }
    };
    let candidate = candidate.expect("candidate success is represented above");
    let comparison = compare_payloads(&reference, &candidate);
    let diagnostics = json!({
        "pipeline": "upstream_backend_run_result_adapter",
        "comparison": comparison,
        "compare_reference": {
            "source": reference_source,
            "reference_kind": reference_kind(reference_source),
            "payload": "arrays_metrics_diagnostics",
            "reference_retained_on_candidate_failure": true,
            "rtol": COMPARE_RTOL,
            "atol": COMPARE_ATOL
        },
        "reference_diagnostics": reference.diagnostics,
        "reference_metadata": reference.metadata,
    });
    write_compare_artifacts(
        input,
        config_file,
        output_dir,
        reference.output,
        diagnostics,
        &reference.metadata,
        &reference.arrays,
    )
    .map_err(WorkflowError::from)
}

fn write_compare_artifacts(
    input: SimulationInputV1,
    input_file: &Path,
    output_dir: &Path,
    output: SimulationOutputV1,
    diagnostics: Value,
    reference_metadata: &Value,
    reference_arrays: &BTreeMap<String, ArrayPayload>,
) -> Result<DirectRunReport, DirectRunError> {
    let mut metadata = serde_json::Map::new();
    metadata.insert("engine_diagnostics".into(), diagnostics.clone());
    if let Value::Object(reference_metadata) = reference_metadata
        && !reference_metadata.is_empty()
    {
        metadata.insert(
            "backend_metadata".into(),
            Value::Object(reference_metadata.clone()),
        );
    }
    let array_shapes = reference_arrays
        .iter()
        .map(|(name, array)| (name.clone(), array.shape.clone()))
        .collect::<BTreeMap<_, _>>();
    let typed_arrays = reference_arrays
        .iter()
        .map(|(name, array)| {
            (
                name.clone(),
                TypedArrayV1 {
                    shape: array.shape.clone(),
                    values: array.values.clone(),
                    dtype: array.dtype,
                },
            )
        })
        .collect::<BTreeMap<_, _>>();
    let array_dtypes = reference_arrays
        .iter()
        .map(|(name, array)| (name.clone(), Value::String(array.dtype.label().into())))
        .collect::<serde_json::Map<_, _>>();
    metadata.insert("array_dtypes".into(), Value::Object(array_dtypes));
    write_simulation_artifacts_with_schema_and_backend_and_shapes_and_typed_arrays(
        input,
        input_file,
        output_dir,
        output,
        Some(diagnostics.clone()),
        COMPARE_RESULT_SCHEMA,
        "external_reference",
        Some(Value::Object(metadata)),
        Some(&array_shapes),
        Some(&typed_arrays),
    )
}

fn reference_kind(source: &str) -> &'static str {
    match source {
        "external_json" => "independent_external_oracle",
        _ => "unknown",
    }
}

/// Compare the actual numeric output payloads of two native runs.
pub fn compare_native_outputs(
    reference: &SimulationOutputV1,
    candidate: &SimulationOutputV1,
) -> Value {
    compare_payloads(
        &ComparePayload::from_output(reference.clone()),
        &ComparePayload::from_output(candidate.clone()),
    )
}

fn projected_input(
    path: &Path,
) -> Result<(crate::LegacyConfigProjectionV1, SimulationInputV1), WorkflowError> {
    let run_id = path
        .file_stem()
        .and_then(|value| value.to_str())
        .filter(|value| !value.is_empty())
        .unwrap_or("pybert-workflow")
        .to_owned();
    project_legacy_config_v1(path, run_id).map_err(WorkflowError::from)
}

fn run_projected_input(
    input: SimulationInputV1,
    input_file: &Path,
    output_dir: &Path,
) -> Result<DirectRunReport, WorkflowError> {
    let mut output = simulate_native_v1(&input)
        .map_err(|error| WorkflowError::Artifact(format!("native simulation failed: {error}")))?;
    crate::legacy_runtime::augment_sim_rust_result_arrays_v1(&input, &mut output)?;
    write_simulation_artifacts(input, input_file, output_dir, output, None)
        .map_err(WorkflowError::from)
}

fn apply_statistical_override(
    input: &mut SimulationInputV1,
    time_points: Option<u32>,
) -> Result<(), WorkflowError> {
    let Some(time_points) = time_points else {
        return Ok(());
    };
    if !(MIN_STATISTICAL_TIME_POINTS..=MAX_STATISTICAL_TIME_POINTS).contains(&time_points) {
        return Err(WorkflowError::InvalidInput(format!(
            "statistical-time-points must be in {MIN_STATISTICAL_TIME_POINTS}..={MAX_STATISTICAL_TIME_POINTS}"
        )));
    }
    let config = input
        .analysis
        .statistical_eye
        .take()
        .unwrap_or(StatisticalEyeConfigV1 {
            target_ber: 1.0e-5,
            contour_ber_levels: vec![1.0e-4, 1.0e-3],
            rx_rj_ui: None,
            rx_dj_ui: None,
            tx_rj_ui: None,
            tx_dj_ui: None,
            tx_dcd_ui: None,
            voltage_resolution: Some(Volts(1.0e-3)),
            time_points,
            max_distribution_states: input.limits.max_distribution_states,
            post_receiver_output: false,
        });
    input.analysis.statistical_eye = Some(StatisticalEyeConfigV1 {
        time_points,
        ..config
    });
    Ok(())
}

fn read_reference_payload(path: &Path) -> Result<ComparePayload, WorkflowError> {
    let metadata = fs::symlink_metadata(path).map_err(|error| {
        WorkflowError::ReferenceUnavailable(format!("could not stat reference JSON: {error}"))
    })?;
    if !metadata.is_file()
        || metadata.file_type().is_symlink()
        || metadata.len() > MAX_REFERENCE_JSON_BYTES
    {
        return Err(WorkflowError::ReferenceUnavailable(
            "reference JSON is not a regular file within the 16 MiB budget".into(),
        ));
    }
    let bytes = fs::read(path).map_err(|error| {
        WorkflowError::ReferenceUnavailable(format!("could not read reference JSON: {error}"))
    })?;
    let value: Value = serde_json::from_slice(&bytes).map_err(|error| {
        WorkflowError::ReferenceUnavailable(format!("reference JSON is invalid: {error}"))
    })?;
    let output = parse_reference_output(&value)?;
    output.validate().map_err(|error| {
        WorkflowError::ReferenceUnavailable(format!("reference output is invalid: {error}"))
    })?;
    let dtype_hints = array_dtype_hints(&value)?;
    let projection = nested_output_projection(&value, &output, &dtype_hints)?;
    let arrays = if nested_output_value(&value).is_some() {
        // The typed nested envelope is canonical.  A valid flat projection is
        // used only to preserve its declared NumPy dtype; values and shape
        // have already been checked against `output.arrays` above.
        let mut arrays = typed_output_array_payloads(&output)?;
        if let Some(projected) = projection.arrays.as_ref() {
            for (name, array) in projected {
                if let Some(canonical) = arrays.get_mut(name) {
                    canonical.dtype = array.dtype;
                }
            }
        }
        arrays
    } else {
        let empty_arrays = json!({});
        let arrays_value = value.get("arrays").unwrap_or(&empty_arrays);
        parse_array_payloads(arrays_value, &dtype_hints)?
    };
    Ok(ComparePayload {
        arrays,
        output,
        projection: projection.report,
        metadata: value.get("metadata").cloned().unwrap_or_else(|| json!({})),
        diagnostics: value
            .get("diagnostics")
            .cloned()
            .unwrap_or_else(|| json!({})),
        performance: value
            .get("performance")
            .cloned()
            .unwrap_or_else(|| json!({})),
    })
}

struct NestedProjection {
    report: Value,
    arrays: Option<BTreeMap<String, ArrayPayload>>,
}

fn nested_output_value(value: &Value) -> Option<&Value> {
    value
        .get("output")
        .or_else(|| value.get("simulation_output"))
}

/// Validate legacy flat projections without allowing them to replace the
/// nested typed output.  The nested envelope is parsed first and remains the
/// source of metrics/array values; a flat projection is only accepted when it
/// is an exact shape/value match.
fn nested_output_projection(
    root: &Value,
    output: &SimulationOutputV1,
    dtype_hints: &BTreeMap<String, ArrayDTypeV1>,
) -> Result<NestedProjection, WorkflowError> {
    if nested_output_value(root).is_none() {
        return Ok(NestedProjection {
            report: json!({
                "present": false,
                "passed": true,
                "source": "flat_backend_run_result",
            }),
            arrays: None,
        });
    }

    let mut metric_reports = Vec::new();
    for (source, metrics) in [
        ("top_level", root.get("metrics")),
        (
            "metadata",
            root.get("metadata")
                .and_then(|metadata| metadata.get("metrics")),
        ),
    ] {
        let Some(metrics) = metrics else {
            continue;
        };
        let projected = parse_metric_projection(metrics, &format!("{source}.metrics"))?;
        let report = compare_nested_metrics(&output.metrics, &projected, source);
        if !report
            .get("passed")
            .and_then(Value::as_bool)
            .unwrap_or(false)
        {
            return Err(WorkflowError::ReferenceUnavailable(format!(
                "nested output metrics drift from {source} projection"
            )));
        }
        metric_reports.push(report);
    }

    let projected_arrays = root
        .get("arrays")
        .map(|arrays| parse_array_payloads(arrays, dtype_hints))
        .transpose()?;
    let array_report = if let Some(projected) = &projected_arrays {
        let canonical = typed_output_array_payloads(output)?;
        let report = compare_nested_arrays(&canonical, projected);
        if !report
            .get("passed")
            .and_then(Value::as_bool)
            .unwrap_or(false)
        {
            return Err(WorkflowError::ReferenceUnavailable(
                "nested output arrays drift from top-level projection".into(),
            ));
        }
        json!({
            "present": true,
            "passed": true,
            "projection_names": projected.keys().collect::<Vec<_>>(),
            "comparison": report,
        })
    } else {
        json!({
            "present": false,
            "passed": true,
            "reason": "no_top_level_arrays_projection",
        })
    };

    Ok(NestedProjection {
        report: json!({
            "present": true,
            "passed": true,
            "source": "nested_simulation_output",
            "metrics": metric_reports,
            "arrays": array_report,
        }),
        arrays: projected_arrays,
    })
}

fn typed_output_array_payloads(
    output: &SimulationOutputV1,
) -> Result<BTreeMap<String, ArrayPayload>, WorkflowError> {
    let arrays = serde_json::to_value(&output.arrays).map_err(|error| {
        WorkflowError::ReferenceUnavailable(format!(
            "nested output arrays cannot be serialized: {error}"
        ))
    })?;
    parse_array_payloads(&arrays, &BTreeMap::new())
}

fn parse_metric_projection(
    value: &Value,
    path: &str,
) -> Result<BTreeMap<String, f64>, WorkflowError> {
    let object = value
        .as_object()
        .ok_or_else(|| WorkflowError::ReferenceUnavailable(format!("{path} must be an object")))?;
    object
        .iter()
        .map(|(name, value)| {
            let number = value
                .as_f64()
                .filter(|value| value.is_finite())
                .ok_or_else(|| {
                    WorkflowError::ReferenceUnavailable(format!(
                        "{path}.{name} must be a finite number"
                    ))
                })?;
            Ok((name.clone(), number))
        })
        .collect()
}

fn compare_nested_metrics(
    canonical: &BTreeMap<String, f64>,
    projected: &BTreeMap<String, f64>,
    source: &str,
) -> Value {
    let names = canonical
        .keys()
        .chain(projected.keys())
        .cloned()
        .collect::<BTreeSet<_>>();
    let mut differences = Vec::new();
    for name in names {
        match (canonical.get(&name), projected.get(&name)) {
            (Some(left), Some(right)) if left == right => {}
            (Some(left), Some(right)) => differences.push(json!({
                "path": format!("{source}.metrics.{name}"),
                "reason": "exact_value",
                "nested": left,
                "projection": right,
            })),
            (Some(_), None) => differences.push(json!({
                "path": format!("{source}.metrics.{name}"),
                "reason": "missing_from_projection",
            })),
            (None, Some(_)) => differences.push(json!({
                "path": format!("{source}.metrics.{name}"),
                "reason": "extra_in_projection",
            })),
            (None, None) => unreachable!("metric union contains a missing key"),
        }
    }
    json!({
        "source": source,
        "passed": differences.is_empty(),
        "differences": differences,
    })
}

fn compare_nested_arrays(
    canonical: &BTreeMap<String, ArrayPayload>,
    projected: &BTreeMap<String, ArrayPayload>,
) -> Value {
    let names = canonical
        .keys()
        .chain(projected.keys())
        .cloned()
        .collect::<BTreeSet<_>>();
    let mut differences = Vec::new();
    for name in names {
        match (canonical.get(&name), projected.get(&name)) {
            (Some(left), Some(right)) => {
                if left.shape != right.shape {
                    differences.push(json!({
                        "path": format!("output.arrays.{name}"),
                        "reason": "shape",
                        "nested": left.shape,
                        "projection": right.shape,
                    }));
                }
                if left.values.len() != right.values.len() {
                    differences.push(json!({
                        "path": format!("output.arrays.{name}"),
                        "reason": "length",
                        "nested": left.values.len(),
                        "projection": right.values.len(),
                    }));
                } else {
                    for (index, (nested, projection)) in
                        left.values.iter().zip(&right.values).enumerate()
                    {
                        if nested != projection {
                            differences.push(json!({
                                "path": format!("output.arrays.{name}[{index}]"),
                                "reason": "exact_value",
                                "nested": nested,
                                "projection": projection,
                            }));
                            if differences.len() >= 128 {
                                break;
                            }
                        }
                    }
                }
            }
            (Some(_), None) => differences.push(json!({
                "path": format!("output.arrays.{name}"),
                "reason": "missing_from_projection",
            })),
            (None, Some(_)) => differences.push(json!({
                "path": format!("output.arrays.{name}"),
                "reason": "extra_in_projection",
            })),
            (None, None) => unreachable!("array union contains a missing key"),
        }
        if differences.len() >= 128 {
            break;
        }
    }
    json!({
        "passed": differences.is_empty(),
        "differences": differences,
    })
}

fn parse_reference_output(value: &Value) -> Result<SimulationOutputV1, WorkflowError> {
    if let Some(payload) = value
        .get("output")
        .or_else(|| value.get("simulation_output"))
    {
        let payload = normalize_output_arrays(payload)?;
        return serde_json::from_value(payload).map_err(|error| {
            WorkflowError::ReferenceUnavailable(format!("reference output is invalid: {error}"))
        });
    }
    if let Ok(output) =
        serde_json::from_value::<SimulationOutputV1>(normalize_output_arrays(value)?)
    {
        return Ok(output);
    }

    // Accept the serialized BackendRunResult shape emitted by the upstream
    // result adapter. Its arrays/metrics live beside metadata and diagnostics,
    // so synthesize only the typed native envelope needed by this comparator.
    let metadata = value.get("metadata").cloned().unwrap_or_else(|| json!({}));
    let diagnostics = value
        .get("diagnostics")
        .cloned()
        .unwrap_or_else(|| json!({}));
    let schema = metadata
        .get("schema")
        .or_else(|| value.get("schema"))
        .and_then(Value::as_str)
        .unwrap_or(crate::SIMULATION_SCHEMA_V1);
    let run_id = metadata
        .get("run_id")
        .or_else(|| metadata.get("runId"))
        .or_else(|| value.get("run_id"))
        .or_else(|| value.get("runId"))
        .and_then(Value::as_str)
        .unwrap_or("reference")
        .to_owned();
    let capabilities = metadata
        .get("capabilities")
        .or_else(|| value.get("capabilities"))
        .cloned()
        .unwrap_or_else(|| json!({"stages": [], "externalModels": []}));
    let metrics = value
        .get("metrics")
        .or_else(|| metadata.get("metrics"))
        .cloned()
        .unwrap_or_else(|| json!({}));
    let dtype_hints = array_dtype_hints(value)?;
    let arrays = value
        .get("arrays")
        .map(|arrays| normalize_arrays_value(arrays, &dtype_hints))
        .transpose()?
        .unwrap_or_else(|| json!({}));
    let events = value
        .get("events")
        .or_else(|| diagnostics.get("events"))
        .cloned()
        .unwrap_or_else(|| json!([]));
    let artifacts = value.get("artifacts").cloned().unwrap_or_else(|| json!([]));
    let output = serde_json::from_value(json!({
        "schema": schema,
        "runId": run_id,
        "capabilities": capabilities,
        "metrics": metrics,
        "events": events,
        "arrays": arrays,
        "artifacts": artifacts,
    }))
    .map_err(|error| {
        WorkflowError::ReferenceUnavailable(format!(
            "reference BackendRunResult payload is invalid: {error}"
        ))
    })?;
    Ok(output)
}

fn normalize_output_arrays(value: &Value) -> Result<Value, WorkflowError> {
    let mut output = value.clone();
    let dtype_hints = array_dtype_hints(&output)?;
    if let Value::Object(object) = &mut output
        && let Some(arrays) = object.get("arrays").cloned()
    {
        object.insert(
            "arrays".into(),
            normalize_arrays_value(&arrays, &dtype_hints)?,
        );
    }
    Ok(output)
}

fn normalize_arrays_value(
    value: &Value,
    dtype_hints: &BTreeMap<String, ArrayDTypeV1>,
) -> Result<Value, WorkflowError> {
    let Value::Object(object) = value else {
        return Err(WorkflowError::ReferenceUnavailable(
            "BackendRunResult arrays must be an object".into(),
        ));
    };
    let mut normalized = serde_json::Map::new();
    for (name, value) in object {
        let (_, values, _) =
            flatten_numeric_array_with_dtype(value, name, dtype_hints.get(name).copied())?;
        normalized.insert(
            name.clone(),
            Value::Array(
                values
                    .into_iter()
                    .filter_map(serde_json::Number::from_f64)
                    .map(Value::Number)
                    .collect(),
            ),
        );
    }
    Ok(Value::Object(normalized))
}

fn parse_array_payloads(
    value: &Value,
    dtype_hints: &BTreeMap<String, ArrayDTypeV1>,
) -> Result<BTreeMap<String, ArrayPayload>, WorkflowError> {
    let Value::Object(object) = value else {
        return Err(WorkflowError::ReferenceUnavailable(
            "BackendRunResult arrays must be an object".into(),
        ));
    };
    object
        .iter()
        .map(|(name, value)| {
            let (shape, values, dtype) =
                flatten_numeric_array_with_dtype(value, name, dtype_hints.get(name).copied())?;
            Ok((
                name.clone(),
                ArrayPayload {
                    shape,
                    values,
                    dtype,
                },
            ))
        })
        .collect()
}

fn array_dtype_hints(value: &Value) -> Result<BTreeMap<String, ArrayDTypeV1>, WorkflowError> {
    let candidate = value
        .get("array_dtypes")
        .or_else(|| value.get("dtypes"))
        .or_else(|| {
            value
                .get("metadata")
                .and_then(|metadata| metadata.get("array_dtypes"))
        })
        .or_else(|| {
            value
                .get("output")
                .and_then(|output| output.get("array_dtypes"))
        });
    let Some(candidate) = candidate else {
        return Ok(BTreeMap::new());
    };
    let object = candidate.as_object().ok_or_else(|| {
        WorkflowError::ReferenceUnavailable(
            "BackendRunResult array_dtypes must be an object".into(),
        )
    })?;
    object
        .iter()
        .map(|(name, value)| Ok((name.clone(), parse_array_dtype(value, name)?)))
        .collect()
}

fn flatten_numeric_array(
    value: &Value,
    path: &str,
) -> Result<(Vec<usize>, Vec<f64>, ArrayDTypeV1), WorkflowError> {
    flatten_numeric_array_with_dtype(value, path, None)
}

fn flatten_numeric_array_with_dtype(
    value: &Value,
    path: &str,
    expected_dtype: Option<ArrayDTypeV1>,
) -> Result<(Vec<usize>, Vec<f64>, ArrayDTypeV1), WorkflowError> {
    if let Value::Object(object) = value {
        let shape = object
            .get("shape")
            .and_then(Value::as_array)
            .ok_or_else(|| {
                WorkflowError::ReferenceUnavailable(format!("{path} array shape is missing"))
            })?
            .iter()
            .map(|value| {
                value
                    .as_u64()
                    .and_then(|value| usize::try_from(value).ok())
                    .ok_or_else(|| {
                        WorkflowError::ReferenceUnavailable(format!(
                            "{path} array shape is invalid"
                        ))
                    })
            })
            .collect::<Result<Vec<_>, _>>()?;
        let data = object
            .get("data")
            .or_else(|| object.get("values"))
            .ok_or_else(|| {
                WorkflowError::ReferenceUnavailable(format!("{path} array data is missing"))
            })?;
        let declared_dtype = object
            .get("dtype")
            .map(|value| parse_array_dtype(value, path))
            .transpose()?;
        let dtype = match merge_array_dtype(expected_dtype, declared_dtype, path)? {
            Some(dtype) => dtype,
            None => {
                let (_, _, dtype) = flatten_numeric_array(data, path)?;
                dtype
            }
        };
        let (_, values, inferred_dtype) =
            flatten_numeric_array_with_dtype(data, path, Some(dtype))?;
        if inferred_dtype != dtype {
            return Err(WorkflowError::ReferenceUnavailable(format!(
                "{path} array dtype does not match its declaration"
            )));
        }
        let expected = shape
            .iter()
            .try_fold(1usize, |product, dimension| product.checked_mul(*dimension))
            .ok_or_else(|| {
                WorkflowError::ReferenceUnavailable(format!("{path} array shape overflows"))
            })?;
        if expected != values.len() {
            return Err(WorkflowError::ReferenceUnavailable(format!(
                "{path} array data length does not match shape"
            )));
        }
        return Ok((shape, values, dtype));
    }
    let Value::Array(values) = value else {
        return Err(WorkflowError::ReferenceUnavailable(format!(
            "{path} array must contain bool or numeric values"
        )));
    };
    let dtype = if values.is_empty() {
        expected_dtype.unwrap_or(ArrayDTypeV1::Float64)
    } else {
        expected_dtype.unwrap_or_else(|| infer_array_dtype(values))
    };
    if values.is_empty() {
        return Ok((vec![0], Vec::new(), dtype));
    }
    if values.iter().all(Value::is_boolean) || values.iter().all(Value::is_number) {
        let flattened = values
            .iter()
            .map(|value| array_scalar_to_f64(value, dtype, path))
            .collect::<Result<Vec<_>, _>>()?;
        return Ok((vec![values.len()], flattened, dtype));
    }
    let children = values
        .iter()
        .map(|value| flatten_numeric_array_with_dtype(value, path, Some(dtype)))
        .collect::<Result<Vec<_>, _>>()?;
    let first_shape = children
        .first()
        .map(|child| child.0.clone())
        .unwrap_or_default();
    if children
        .iter()
        .any(|child| child.0 != first_shape || child.2 != dtype)
    {
        return Err(WorkflowError::ReferenceUnavailable(format!(
            "{path} is a ragged array"
        )));
    }
    let mut flattened = Vec::new();
    for (_, values, _) in children {
        flattened.extend(values);
    }
    let mut shape = vec![values.len()];
    shape.extend(first_shape);
    Ok((shape, flattened, dtype))
}

fn infer_array_dtype(values: &[Value]) -> ArrayDTypeV1 {
    if !values.is_empty() && values.iter().all(value_is_boolean_recursive) {
        ArrayDTypeV1::Bool
    } else {
        // A bare JSON number has no reliable NumPy dtype marker.  The typed
        // SimulationOutput envelope serializes f64 values as numbers that may
        // look integral, so defaulting those values to float64 avoids inventing
        // an integer dtype.  BackendRunResult producers that carry int64 use
        // the explicit `{dtype: "int64", ...}` form handled above.
        ArrayDTypeV1::Float64
    }
}

fn value_is_boolean_recursive(value: &Value) -> bool {
    match value {
        Value::Bool(_) => true,
        Value::Array(values) => !values.is_empty() && values.iter().all(value_is_boolean_recursive),
        _ => false,
    }
}

fn parse_array_dtype(value: &Value, path: &str) -> Result<ArrayDTypeV1, WorkflowError> {
    let Some(dtype) = value.as_str() else {
        return Err(WorkflowError::ReferenceUnavailable(format!(
            "{path} array dtype must be a string"
        )));
    };
    match dtype.to_ascii_lowercase().as_str() {
        "bool" | "boolean" | "b1" | "|b1" => Ok(ArrayDTypeV1::Bool),
        "int" | "int64" | "i8" | "<i8" => Ok(ArrayDTypeV1::Int64),
        "float" | "float64" | "f8" | "<f8" | "double" => Ok(ArrayDTypeV1::Float64),
        _ => Err(WorkflowError::ReferenceUnavailable(format!(
            "{path} array dtype is unsupported: {dtype}"
        ))),
    }
}

fn merge_array_dtype(
    expected: Option<ArrayDTypeV1>,
    declared: Option<ArrayDTypeV1>,
    path: &str,
) -> Result<Option<ArrayDTypeV1>, WorkflowError> {
    match (expected, declared) {
        (Some(expected), Some(declared)) if expected != declared => {
            Err(WorkflowError::ReferenceUnavailable(format!(
                "{path} array dtype declaration conflicts with its parent"
            )))
        }
        (Some(expected), _) | (_, Some(expected)) => Ok(Some(expected)),
        (None, None) => Ok(None),
    }
}

fn array_scalar_to_f64(
    value: &Value,
    dtype: ArrayDTypeV1,
    path: &str,
) -> Result<f64, WorkflowError> {
    match dtype {
        ArrayDTypeV1::Bool => value
            .as_bool()
            .map(|value| if value { 1.0 } else { 0.0 })
            .or_else(|| {
                value.as_f64().and_then(|value| {
                    (value.is_finite() && (value == 0.0 || value == 1.0)).then_some(value)
                })
            })
            .ok_or_else(|| {
                WorkflowError::ReferenceUnavailable(format!(
                    "{path} bool array contains a non-boolean/non-binary value"
                ))
            }),
        ArrayDTypeV1::Int64 => value
            .as_i64()
            .map(|value| value as f64)
            .or_else(|| {
                value
                    .as_f64()
                    .and_then(|value| (value.is_finite() && value.fract() == 0.0).then_some(value))
            })
            .ok_or_else(|| {
                WorkflowError::ReferenceUnavailable(format!(
                    "{path} int64 array contains a non-integral value"
                ))
            }),
        ArrayDTypeV1::Float64 => {
            value
                .as_f64()
                .filter(|value| value.is_finite())
                .ok_or_else(|| {
                    WorkflowError::ReferenceUnavailable(format!(
                        "{path} float64 array contains a non-finite value"
                    ))
                })
        }
    }
}

fn compare_payloads(reference: &ComparePayload, candidate: &ComparePayload) -> Value {
    let array_report = compare_maps(&reference.arrays, &candidate.arrays);
    let metric_report = compare_scalars(&reference.output.metrics, &candidate.output.metrics);
    let output_report = compare_output_contract(&reference.output, &candidate.output);
    let projection_report = reference.projection.clone();
    let metadata_report = compare_values(&reference.metadata, &candidate.metadata, "metadata");
    let diagnostics_report = compare_values(
        &reference.diagnostics,
        &candidate.diagnostics,
        "diagnostics",
    );
    let performance = compare_performance(reference, candidate);
    let passed = [
        &array_report,
        &metric_report,
        &output_report,
        &projection_report,
        &metadata_report,
        &diagnostics_report,
    ]
    .into_iter()
    .all(|report| {
        report
            .get("passed")
            .and_then(Value::as_bool)
            .unwrap_or(false)
    });
    json!({
        "schema": "pybert.engine-compare.v1",
        "passed": passed,
        "reference_run_id": reference.output.run_id,
        "candidate_run_id": candidate.output.run_id,
        "tolerance": {"rtol": COMPARE_RTOL, "atol": COMPARE_ATOL},
        "arrays": array_report,
        "metrics": metric_report,
        "output": output_report,
        "nested_output_projection": projection_report,
        "metadata": metadata_report,
        "diagnostics": diagnostics_report,
        "performance": performance,
        "status_only_comparison": false
    })
}

/// Compare the complete typed `SimulationOutputV1` envelope in addition to
/// its numeric payload.  The existing result-adapter comparison intentionally
/// keeps host run IDs out of the gate; stage capabilities, ordered events, and
/// artifact references are semantic output and must not disappear merely
/// because all waveform arrays still match.
fn compare_output_contract(
    reference: &SimulationOutputV1,
    candidate: &SimulationOutputV1,
) -> Value {
    let schema = compare_values(
        &Value::String(reference.schema.clone()),
        &Value::String(candidate.schema.clone()),
        "output.schema",
    );
    let capabilities = compare_values(
        &serde_json::to_value(&reference.capabilities).expect("capabilities serialize"),
        &serde_json::to_value(&candidate.capabilities).expect("capabilities serialize"),
        "output.capabilities",
    );
    let metrics = compare_values(
        &serde_json::to_value(&reference.metrics).expect("metrics serialize"),
        &serde_json::to_value(&candidate.metrics).expect("metrics serialize"),
        "output.metrics",
    );
    let arrays = compare_values(
        &serde_json::to_value(&reference.arrays).expect("arrays serialize"),
        &serde_json::to_value(&candidate.arrays).expect("arrays serialize"),
        "output.arrays",
    );
    let events = compare_values(
        &event_payload_without_run_ids(&reference.events),
        &event_payload_without_run_ids(&candidate.events),
        "output.events",
    );
    let artifacts = compare_artifacts_strict(&reference.artifacts, &candidate.artifacts);
    let passed = [
        &schema,
        &capabilities,
        &metrics,
        &arrays,
        &events,
        &artifacts,
    ]
    .into_iter()
    .all(|report| {
        report
            .get("passed")
            .and_then(Value::as_bool)
            .unwrap_or(false)
    });
    json!({
        "passed": passed,
        "reference_run_id": reference.run_id,
        "candidate_run_id": candidate.run_id,
        "run_id_is_provenance_only": true,
        "schema": schema,
        "capabilities": capabilities,
        "metrics": metrics,
        "arrays": arrays,
        "events": events,
        "artifacts": artifacts,
    })
}

fn event_payload_without_run_ids(events: &[crate::RunEventV1]) -> Value {
    Value::Array(
        events
            .iter()
            .map(|event| {
                json!({
                    "sequence": event.sequence,
                    "stage": event.stage,
                    "stageProgress": event.stage_progress,
                    "totalProgress": event.total_progress,
                    "message": event.message,
                })
            })
            .collect(),
    )
}

fn compare_artifacts_strict(reference: &[ArtifactRefV1], candidate: &[ArtifactRefV1]) -> Value {
    let mut differences = Vec::new();
    if reference.len() != candidate.len() {
        differences.push(json!({
            "path": "output.artifacts",
            "reason": "length",
            "reference": reference.len(),
            "candidate": candidate.len(),
        }));
    }
    for (index, (left, right)) in reference.iter().zip(candidate).enumerate() {
        let fields = [
            ("name", left.name.as_str(), right.name.as_str()),
            ("schema", left.schema.as_str(), right.schema.as_str()),
            (
                "relativePath",
                left.relative_path.as_str(),
                right.relative_path.as_str(),
            ),
            (
                "mimeType",
                left.mime_type.as_str(),
                right.mime_type.as_str(),
            ),
            ("sha256", left.sha256.as_str(), right.sha256.as_str()),
        ];
        for (field, reference, candidate) in fields {
            if reference != candidate {
                differences.push(json!({
                    "path": format!("output.artifacts[{index}].{field}"),
                    "reason": "exact_value",
                    "reference": reference,
                    "candidate": candidate,
                }));
            }
        }
        if left.byte_length != right.byte_length {
            differences.push(json!({
                "path": format!("output.artifacts[{index}].byteLength"),
                "reason": "exact_value",
                "reference": left.byte_length,
                "candidate": right.byte_length,
            }));
        }
    }
    json!({
        "passed": differences.is_empty(),
        "comparison": "exact",
        "differences": differences,
    })
}

fn compare_values(reference: &Value, candidate: &Value, path: &str) -> Value {
    let mut differences = Vec::new();
    let mut ignored_paths = Vec::new();
    let mut observational_paths = Vec::new();
    compare_value_inner(
        reference,
        candidate,
        path,
        &mut differences,
        &mut ignored_paths,
        &mut observational_paths,
    );
    json!({
        "passed": differences.is_empty(),
        "differences": differences,
        "ignored_provenance_paths": ignored_paths,
        "observational_only_paths": observational_paths,
    })
}

fn compare_value_inner(
    reference: &Value,
    candidate: &Value,
    path: &str,
    differences: &mut Vec<Value>,
    ignored_paths: &mut Vec<String>,
    observational_paths: &mut Vec<String>,
) {
    if differences.len() >= 128 {
        return;
    }
    if is_nonsemantic_provenance_path(path) {
        if !ignored_paths.iter().any(|known| known == path) {
            ignored_paths.push(path.to_owned());
        }
        return;
    }
    if is_observational_metric_path(path) {
        if !observational_paths.iter().any(|known| known == path) {
            observational_paths.push(path.to_owned());
        }
        return;
    }
    match (reference, candidate) {
        (Value::Object(left), Value::Object(right)) => {
            let keys = left
                .keys()
                .chain(right.keys())
                .cloned()
                .collect::<BTreeSet<_>>();
            for key in keys {
                let next_path = format!("{path}.{key}");
                match (left.get(&key), right.get(&key)) {
                    (Some(left), Some(right)) => compare_value_inner(
                        left,
                        right,
                        &next_path,
                        differences,
                        ignored_paths,
                        observational_paths,
                    ),
                    _ if is_nonsemantic_provenance_path(&next_path) => {
                        if !ignored_paths.iter().any(|known| known == &next_path) {
                            ignored_paths.push(next_path);
                        }
                    }
                    _ => differences.push(json!({"path": next_path, "reason": "missing_key"})),
                }
            }
        }
        (Value::Array(left), Value::Array(right)) => {
            if left.len() != right.len() {
                differences.push(json!({
                    "path": path,
                    "reason": "length",
                    "reference": left.len(),
                    "candidate": right.len()
                }));
            } else {
                for (index, (left, right)) in left.iter().zip(right).enumerate() {
                    compare_value_inner(
                        left,
                        right,
                        &format!("{path}[{index}]"),
                        differences,
                        ignored_paths,
                        observational_paths,
                    );
                }
            }
        }
        (Value::Number(left), Value::Number(right)) => {
            let left = left.as_f64();
            let right = right.as_f64();
            if !matches!((left, right), (Some(left), Some(right)) if left.is_finite()
                && right.is_finite()
                && (left - right).abs() <= COMPARE_ATOL + COMPARE_RTOL * left.abs())
            {
                differences.push(json!({
                    "path": path,
                    "reason": "number",
                    "reference": left,
                    "candidate": right
                }));
            }
        }
        (left, right) if left != right => {
            differences.push(json!({
                "path": path,
                "reason": "value",
                "reference": left,
                "candidate": right
            }));
        }
        _ => {}
    }
}

fn is_nonsemantic_provenance_path(path: &str) -> bool {
    matches!(
        path,
        "metadata.engine.backend"
            | "metadata.engine.implementation"
            | "metadata.engine.candidate_core_reused"
            | "metadata.engine.native_simulation_v1"
            | "metadata.engine.source"
            | "diagnostics.pipeline"
    )
}

fn is_observational_metric_path(path: &str) -> bool {
    // The Python result adapter does not require the Rust statistical-eye
    // state count.  Quantization can differ by a few states even when the
    // full pulse, contour, and required scalar payloads are within budget.
    // Keep the value visible in the payload but do not promote it to a parity
    // gate or pretend it is an upstream required metric.
    path == "metadata.metrics.eye_distribution_state_count"
}

fn compare_performance(reference: &ComparePayload, candidate: &ComparePayload) -> Value {
    let mut reference_timings = BTreeMap::new();
    let mut candidate_timings = BTreeMap::new();
    collect_timing_values(
        &reference.metadata,
        "metadata",
        false,
        &mut reference_timings,
    );
    collect_timing_values(
        &reference.diagnostics,
        "diagnostics",
        false,
        &mut reference_timings,
    );
    collect_timing_values(
        &reference.performance,
        "performance",
        true,
        &mut reference_timings,
    );
    collect_timing_values(
        &candidate.metadata,
        "metadata",
        false,
        &mut candidate_timings,
    );
    collect_timing_values(
        &candidate.diagnostics,
        "diagnostics",
        false,
        &mut candidate_timings,
    );
    collect_timing_values(
        &candidate.performance,
        "performance",
        true,
        &mut candidate_timings,
    );
    let common = reference_timings
        .keys()
        .filter(|key| candidate_timings.contains_key(*key))
        .cloned()
        .collect::<Vec<_>>();
    let entries = common
        .iter()
        .map(|path| {
            let reference_seconds = reference_timings[path];
            let candidate_seconds = candidate_timings[path];
            (
                path.clone(),
                json!({
                    "reference_seconds": reference_seconds,
                    "candidate_seconds": candidate_seconds,
                    "candidate_over_reference": if reference_seconds > 0.0 {
                        Some(candidate_seconds / reference_seconds)
                    } else {
                        None::<f64>
                    }
                }),
            )
        })
        .collect::<serde_json::Map<_, _>>();
    json!({
        "available": !entries.is_empty(),
        "entries": entries,
        "missing_from_candidate": reference_timings.keys().filter(|key| !candidate_timings.contains_key(*key)).cloned().collect::<Vec<_>>(),
        "missing_from_reference": candidate_timings.keys().filter(|key| !reference_timings.contains_key(*key)).cloned().collect::<Vec<_>>(),
    })
}

fn collect_timing_values(
    value: &Value,
    path: &str,
    within_timing: bool,
    output: &mut BTreeMap<String, f64>,
) {
    let Value::Object(object) = value else {
        return;
    };
    for (key, value) in object {
        let next_path = format!("{path}.{key}");
        let nested = within_timing
            || matches!(
                key.to_ascii_lowercase().as_str(),
                "timing" | "timings" | "performance" | "stage_timings"
            );
        if value.is_object() {
            collect_timing_values(value, &next_path, nested, output);
        } else if nested
            && ["_s", "_seconds", "_duration"]
                .iter()
                .any(|suffix| key.to_ascii_lowercase().ends_with(suffix))
            && let Some(number) = value
                .as_f64()
                .filter(|number| number.is_finite() && *number >= 0.0)
        {
            output.insert(next_path, number);
        }
    }
}

fn compare_maps(
    reference: &BTreeMap<String, ArrayPayload>,
    candidate: &BTreeMap<String, ArrayPayload>,
) -> Value {
    if reference.is_empty() || candidate.is_empty() {
        return json!({"passed": false, "reason": "empty_payload"});
    }
    let names = reference
        .keys()
        .chain(candidate.keys())
        .cloned()
        .collect::<BTreeSet<_>>();
    let mut entries = serde_json::Map::new();
    let mut passed = true;
    for name in names {
        let entry = match (reference.get(&name), candidate.get(&name)) {
            (None, Some(_)) => json!({"passed": false, "reason": "missing_from_reference"}),
            (Some(_), None) => json!({"passed": false, "reason": "missing_from_candidate"}),
            (Some(left), Some(right)) => compare_arrays(name.as_str(), left, right),
            (None, None) => unreachable!("union contains a key from one map"),
        };
        passed = passed
            && entry
                .get("passed")
                .and_then(Value::as_bool)
                .unwrap_or(false);
        entries.insert(name, entry);
    }
    json!({
        "passed": passed,
        "missing_from_candidate": reference.keys().filter(|name| !candidate.contains_key(*name)).cloned().collect::<Vec<_>>(),
        "missing_from_reference": candidate.keys().filter(|name| !reference.contains_key(*name)).cloned().collect::<Vec<_>>(),
        "entries": entries
    })
}

fn compare_scalars(reference: &BTreeMap<String, f64>, candidate: &BTreeMap<String, f64>) -> Value {
    if reference.is_empty() {
        return json!({
            "passed": true,
            "available": false,
            "reason": "reference_metrics_not_required",
            "entries": {}
        });
    }
    if candidate.is_empty() {
        return json!({"passed": false, "reason": "empty_candidate_metrics"});
    }
    let names = reference
        .keys()
        .chain(candidate.keys())
        .cloned()
        .collect::<BTreeSet<_>>();
    let mut entries = serde_json::Map::new();
    let mut passed = true;
    for name in names {
        let entry = match (reference.get(&name), candidate.get(&name)) {
            (None, Some(_)) => json!({"passed": false, "reason": "missing_from_reference"}),
            (Some(_), None) => json!({"passed": false, "reason": "missing_from_candidate"}),
            (Some(left), Some(right)) if name == "eye_distribution_state_count" => json!({
                "passed": true,
                "required": false,
                "reason": "derived_distribution_state_count_observational_only",
                "reference": left,
                "candidate": right
            }),
            (Some(left), Some(right)) => compare_vectors(name.as_str(), &[*left], &[*right]),
            (None, None) => unreachable!("union contains a key from one map"),
        };
        passed = passed
            && entry
                .get("passed")
                .and_then(Value::as_bool)
                .unwrap_or(false);
        entries.insert(name, entry);
    }
    json!({
        "passed": passed,
        "missing_from_candidate": reference.keys().filter(|name| !candidate.contains_key(*name)).cloned().collect::<Vec<_>>(),
        "missing_from_reference": candidate.keys().filter(|name| !reference.contains_key(*name)).cloned().collect::<Vec<_>>(),
        "entries": entries
    })
}

fn compare_arrays(name: &str, reference: &ArrayPayload, candidate: &ArrayPayload) -> Value {
    if reference.shape != candidate.shape {
        return json!({
            "passed": false,
            "reason": "shape",
            "reference_shape": reference.shape,
            "candidate_shape": candidate.shape,
            "reference_dtype": reference.dtype.label(),
            "candidate_dtype": candidate.dtype.label()
        });
    }
    if reference.dtype != candidate.dtype {
        return json!({
            "passed": false,
            "reason": "dtype",
            "reference_shape": reference.shape,
            "candidate_shape": candidate.shape,
            "reference_dtype": reference.dtype.label(),
            "candidate_dtype": candidate.dtype.label(),
            "discrete": true,
        });
    }
    compare_vectors_with_shape(
        name,
        &reference.values,
        &candidate.values,
        &reference.shape,
        reference.dtype,
        candidate.dtype,
    )
}

fn compare_vectors(name: &str, reference: &[f64], candidate: &[f64]) -> Value {
    compare_vectors_with_shape(
        name,
        reference,
        candidate,
        &[reference.len()],
        ArrayDTypeV1::Float64,
        ArrayDTypeV1::Float64,
    )
}

fn compare_vectors_with_shape(
    name: &str,
    reference: &[f64],
    candidate: &[f64],
    shape: &[usize],
    reference_dtype: ArrayDTypeV1,
    candidate_dtype: ArrayDTypeV1,
) -> Value {
    if reference.len() != candidate.len() {
        return json!({
            "passed": false,
            "reason": "shape",
            "reference_shape": shape,
            "candidate_shape": [candidate.len()],
            "reference_dtype": reference_dtype.label(),
            "candidate_dtype": candidate_dtype.label()
        });
    }
    let lower_name = name.to_ascii_lowercase();
    // Decision names are discrete by contract even when a producer encoded
    // them as float64.  Dtype is also part of the gate, so an integer-looking
    // waveform never becomes discrete merely because its values round.
    let discrete = reference_dtype != ArrayDTypeV1::Float64 || is_discrete_array_name(&lower_name);
    let mut max_abs = 0.0_f64;
    let mut max_rel = 0.0_f64;
    let mut finite = true;
    let mut mismatch_count = 0_u64;
    let mut first_mismatch_flat_indices = Vec::new();
    for (index, (&left, &right)) in reference.iter().zip(candidate).enumerate() {
        if !(left.is_finite() && right.is_finite()) {
            finite = false;
            mismatch_count += 1;
            continue;
        }
        let delta = (left - right).abs();
        let relative = delta / left.abs().max(f64::MIN_POSITIVE);
        max_abs = max_abs.max(delta);
        max_rel = max_rel.max(relative);
        if (discrete && left != right)
            || (!discrete && delta > COMPARE_ATOL + COMPARE_RTOL * left.abs())
        {
            mismatch_count += 1;
            if first_mismatch_flat_indices.len() < 16 {
                first_mismatch_flat_indices.push(index);
            }
        }
    }
    json!({
        "passed": finite && mismatch_count == 0,
        "reference_shape": shape,
        "candidate_shape": shape,
        "reference_dtype": reference_dtype.label(),
        "candidate_dtype": candidate_dtype.label(),
        "finite": finite,
        "discrete": discrete,
        "mismatch_count": mismatch_count,
        "first_mismatch_flat_indices": first_mismatch_flat_indices,
        "missing_error_indices": if name.to_ascii_lowercase().contains("error_index") {
            discrete_indices(reference)
                .difference(&discrete_indices(candidate))
                .copied()
                .collect::<Vec<_>>()
        } else {
            Vec::new()
        },
        "unexpected_error_indices": if name.to_ascii_lowercase().contains("error_index") {
            discrete_indices(candidate)
                .difference(&discrete_indices(reference))
                .copied()
                .collect::<Vec<_>>()
        } else {
            Vec::new()
        },
        "max_abs_error": max_abs,
        "max_rel_error": max_rel
    })
}

fn is_discrete_array_name(lower_name: &str) -> bool {
    // Match the upstream result adapter: every array whose semantic name says
    // decision is exact, including float64 decision-scalers.  Never infer this
    // contract from whether the current values happen to be integral.
    lower_name.contains("decision")
        || lower_name.contains("bit")
        || lower_name.contains("error_index")
        || lower_name.contains("error_indices")
        || lower_name.contains("indices")
        || lower_name.contains("locked")
        || lower_name.contains("state_path")
}

fn discrete_indices(values: &[f64]) -> std::collections::BTreeSet<i64> {
    values
        .iter()
        .filter(|value| value.is_finite() && value.fract() == 0.0)
        .map(|value| *value as i64)
        .collect()
}
