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

use serde_json::{Map, Value, json};
use thiserror::Error;

use crate::{NativeSimulationError, SimulationInputV1, SimulationOutputV1, simulate_native_v1};

pub const UPSTREAM_COMMIT: &str = "5bf6d7ea0ace261891aaeb611ffc1c267e160afe";
pub const UPSTREAM_TREE: &str = "5faef6bdb341d444ad65d82a11c0018b15805e24";
pub const NATIVE_CORE_SOURCE: &str = "native/pybert-core";
pub const PYTHON_BOUNDARY_SOURCE: &str = "native/pybert-python/src/lib.rs";
pub const NATIVE_CLI_SCHEMA: &str = "pybert.native-cli-result.v1";
pub const ERROR_SCHEMA: &str = "pybert.native-cli-error.v1";

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
    let output = simulate_native_v1(&input)?;
    output
        .validate()
        .map_err(|error| DirectRunError::Output(error.to_string()))?;

    let source_file = input_file
        .canonicalize()
        .unwrap_or_else(|_| input_file.to_path_buf());
    prepare_output_directory(output_dir)?;
    let metadata = json!({
        "schema": NATIVE_CLI_SCHEMA,
        "input_file": source_file,
        "effective_input": serde_json::to_value(&input).map_err(|error| DirectRunError::Output(error.to_string()))?,
        "backend_metadata": {
            "schema": output.schema,
            "run_id": output.run_id,
            "engine": {
                "backend": "rust",
                "native_simulation_v1": true,
                "source": "pinned_pybert_native_core",
                "python_extension_boundary": "same_simulation_input_v1_contract",
            },
            "metrics": output.metrics,
            "aborted": false,
        },
        "diagnostics": {
            "pipeline": "typed_simulation_input_v1",
            "capabilities": output.capabilities.stages,
            "events": output.events,
            "cancellation": "checked_before_and_after_the_bounded_native_call",
            "source": {
                "repository": "pybert",
                "commit": UPSTREAM_COMMIT,
                "tree": UPSTREAM_TREE,
                "native_core": NATIVE_CORE_SOURCE,
                "python_extension_boundary": PYTHON_BOUNDARY_SOURCE,
            },
        },
        "arrays_file": "arrays.npz",
    });
    let diagnostics = metadata.get("diagnostics").cloned().unwrap_or(Value::Null);
    let meta_path = output_dir.join("meta.json");
    let arrays_path = output_dir.join("arrays.npz");
    fs::write(
        &meta_path,
        serde_json::to_vec_pretty(&metadata)
            .map_err(|error| DirectRunError::Output(error.to_string()))?,
    )?;
    fs::write(&arrays_path, npz_bytes(&output.arrays)?)?;
    Ok(DirectRunReport {
        input,
        output,
        metadata,
        diagnostics,
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
        object_keys(value, "$.tx.additiveNoise", &["samplesV"])?;
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

fn npz_bytes(arrays: &BTreeMap<String, Vec<f64>>) -> Result<Vec<u8>, DirectRunError> {
    let mut result = Vec::new();
    let mut central = Vec::new();
    for (name, values) in arrays {
        let filename = format!("{name}.npy");
        let data = npy_f64(values)?;
        let crc = crc32(&data);
        let offset = u32::try_from(result.len())
            .map_err(|_| DirectRunError::Output("NPZ offset overflow".into()))?;
        write_local_header(&mut result, filename.as_bytes(), crc, data.len())?;
        result.extend_from_slice(&data);
        write_central_header(&mut central, filename.as_bytes(), crc, data.len(), offset)?;
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

fn npy_f64(values: &[f64]) -> Result<Vec<u8>, DirectRunError> {
    let mut header = format!(
        "{{'descr': '<f8', 'fortran_order': False, 'shape': ({},), }}",
        values.len()
    );
    let preamble = 10_usize;
    let padding = (16 - (preamble + header.len() + 1) % 16) % 16;
    header.extend(std::iter::repeat_n(' ', padding));
    header.push('\n');
    let header_len = u16::try_from(header.len())
        .map_err(|_| DirectRunError::Output("NPY header is too long".into()))?;
    let mut result = Vec::with_capacity(preamble + header.len() + values.len() * 8);
    result.extend_from_slice(b"\x93NUMPY");
    result.extend_from_slice(&[1, 0]);
    result.extend_from_slice(&header_len.to_le_bytes());
    result.extend_from_slice(header.as_bytes());
    for value in values {
        result.extend_from_slice(&value.to_le_bytes());
    }
    Ok(result)
}

fn write_local_header(
    result: &mut Vec<u8>,
    filename: &[u8],
    crc: u32,
    length: usize,
) -> Result<(), DirectRunError> {
    let length =
        u32::try_from(length).map_err(|_| DirectRunError::Output("NPZ member too large".into()))?;
    let filename_len = u16::try_from(filename.len())
        .map_err(|_| DirectRunError::Output("NPZ filename too long".into()))?;
    result.extend_from_slice(&0x0403_4b50_u32.to_le_bytes());
    result.extend_from_slice(&20_u16.to_le_bytes());
    result.extend_from_slice(&0_u16.to_le_bytes());
    result.extend_from_slice(&0_u16.to_le_bytes());
    result.extend_from_slice(&0_u16.to_le_bytes());
    result.extend_from_slice(&0_u16.to_le_bytes());
    result.extend_from_slice(&crc.to_le_bytes());
    result.extend_from_slice(&length.to_le_bytes());
    result.extend_from_slice(&length.to_le_bytes());
    result.extend_from_slice(&filename_len.to_le_bytes());
    result.extend_from_slice(&0_u16.to_le_bytes());
    result.extend_from_slice(filename);
    Ok(())
}

fn write_central_header(
    result: &mut Vec<u8>,
    filename: &[u8],
    crc: u32,
    length: usize,
    offset: u32,
) -> Result<(), DirectRunError> {
    let length =
        u32::try_from(length).map_err(|_| DirectRunError::Output("NPZ member too large".into()))?;
    let filename_len = u16::try_from(filename.len())
        .map_err(|_| DirectRunError::Output("NPZ filename too long".into()))?;
    result.extend_from_slice(&0x0201_4b50_u32.to_le_bytes());
    result.extend_from_slice(&20_u16.to_le_bytes());
    result.extend_from_slice(&20_u16.to_le_bytes());
    result.extend_from_slice(&0_u16.to_le_bytes());
    result.extend_from_slice(&0_u16.to_le_bytes());
    result.extend_from_slice(&0_u16.to_le_bytes());
    result.extend_from_slice(&0_u16.to_le_bytes());
    result.extend_from_slice(&crc.to_le_bytes());
    result.extend_from_slice(&length.to_le_bytes());
    result.extend_from_slice(&length.to_le_bytes());
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
