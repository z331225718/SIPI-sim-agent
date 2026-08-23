//! Bounded direct leaves for Agent-COM run and public artifact workflows.
//!
//! The scoped portable source branches are exposed through one bounded
//! canonical JSON surface: source-schema config materialization is reused,
//! channels resolve to impulses, and the numeric COM chain is delegated to
//! `sipi-com`. FEXT/NEXT impulses are consumed by the portable residual/noise-
//! PDF chain. Calibration, MMSE, and RxFFE publish their numeric payloads,
//! rather than reducing those source branches to status-only diagnostics.

use crate::{
    ConfigValidateErrorV1, ConfigValidateReportV1, ConfigValidateRequestV1, config_validate_v1,
};
use serde_json::{Map, Value, json};
use sha2::{Digest, Sha256};
use sipi_com::{
    CalibrationErrorV1, CandidateEvalOptionsV1, CandidateEvalParamsV1, ComRunResultEnvelopeV1,
    CtleParamsV1, FdToTdOptionsV1, MmseCandidateSpecV1, ReceiverNoiseOptionsV1,
    ReceiverNoiseParamsV1, ResolvedDefaultV1, RxFfeSearchCandidateV1, RxFfeSearchEvaluationV1,
    SearchFullOptionsV1, SearchFullParamsV1, SearchLoopResultV1, apply_r480_equalization_v1,
    apply_r480_pn_skew_v1, butterworth_filter_v1, calculate_r480_calibration_noise_v1,
    calibrate_receiver_noise_v1, com_mixed_mode_spectrum_v1, execute_com_run_v1,
    execute_com_run_with_crosstalk_v1, merge_com_parameters_v1, r480_tdiln_v1,
    raised_cosine_filter_v1, rectangular_pulse_response_v1, s21_to_impulse_dc_v1,
    sampled_signal_pdf_v1, search_fvlms_rxffe_candidates_v1, search_mmse_candidates_v1,
    search_r480_nonmmse_no_xtalk_with_sigma_v1,
};
use sipi_touchstone::selected_four_port_v1::parse_selected_four_port_hz_s_ri_50_v2;
use sipi_touchstone::{TouchstoneParseLimitsV1, parse_touchstone_hz_s_ri_50_two_port_v1};
use sipi_types::Complex64;
use std::collections::BTreeMap;
use std::fmt::{Display, Formatter};
use std::fs;
use std::num::NonZeroUsize;
use std::path::{Path, PathBuf};

pub const COM_02_DIRECT_PORT_SCHEMA_V1: &str = "sipi.com-02.direct-port.v1";
pub const COM_04_DIRECT_PORT_SCHEMA_V1: &str = "sipi.com-04.direct-port.v1";
pub const COM_DIRECT_RESULT_SCHEMA_V1: &str = "sipi.com.direct-run-result.v1";
pub const MAX_IMPULSE_FILE_BYTES_V1: u64 = 8 * 1024 * 1024;
pub const MAX_CONFIG_JSON_BYTES_V1: u64 = 16 * 1024 * 1024;
pub const MAX_RESULT_BYTES_V1: usize = 16 * 1024 * 1024;
pub const MAX_REPORT_BYTES_V1: usize = 64 * 1024;
pub const MAX_DIAGNOSTICS_BYTES_V1: usize = 256 * 1024;
pub const MAX_CROSSTALK_CHANNELS_V1: usize = 64;
pub const MAX_SEARCH_FREQUENCY_POINTS_V1: usize = 262_144;
pub const MAX_SEARCH_TX_FFE_CANDIDATES_V1: u64 = 1_000_000;
const MAX_TOUCHSTONE_RECORDS_V1: usize = 65_536;

/// Inputs shared by the executable COM run and the public API workflow.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct DirectRunRequestV1 {
    pub config: PathBuf,
    pub pulse: PathBuf,
    pub fext: Vec<PathBuf>,
    pub next: Vec<PathBuf>,
    pub output_dir: PathBuf,
    pub artifact_id: String,
    pub profile: String,
    pub reader: Option<String>,
    pub fix_ids: Vec<String>,
    pub overrides: Vec<String>,
    pub overwrite: bool,
    /// Optional JSON calibration payload supplied by the CLI/API boundary.
    pub calibration_noise: Option<PathBuf>,
    /// Emit the bounded semantic legacy CSV projection beside the JSON
    /// artifacts.  This is not the rejected upstream MATLAB output schema.
    pub legacy_csv: bool,
}

impl DirectRunRequestV1 {
    pub fn new(
        config: impl Into<PathBuf>,
        pulse: impl Into<PathBuf>,
        output_dir: impl Into<PathBuf>,
    ) -> Self {
        Self {
            config: config.into(),
            pulse: pulse.into(),
            fext: Vec::new(),
            next: Vec::new(),
            output_dir: output_dir.into(),
            artifact_id: "com-run".to_owned(),
            profile: "r480".to_owned(),
            reader: Some("r480".to_owned()),
            fix_ids: Vec::new(),
            overrides: Vec::new(),
            overwrite: false,
            calibration_noise: None,
            legacy_csv: false,
        }
    }

    pub fn with_artifact_id(mut self, artifact_id: impl Into<String>) -> Self {
        self.artifact_id = artifact_id.into();
        self
    }

    pub fn with_overwrite(mut self, overwrite: bool) -> Self {
        self.overwrite = overwrite;
        self
    }
}

/// The files emitted by the direct `write_artifacts` boundary.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct RunArtifactSetV1 {
    pub result_json: PathBuf,
    pub report_html: PathBuf,
    pub diagnostics_json: PathBuf,
    pub legacy_csv: Option<PathBuf>,
}

/// A semantically useful run report.  The result JSON contains the COM
/// metrics and a digest/count of the exact impulse used by the chain.
#[derive(Clone, Debug, PartialEq)]
pub struct DirectRunReportV1 {
    pub schema: &'static str,
    pub workflow: Vec<&'static str>,
    pub result: Value,
    pub artifacts: RunArtifactSetV1,
    pub impulse_sample_count: usize,
    pub impulse_sha256: String,
    pub config_sha256: String,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum DirectRunErrorV1 {
    InvalidRequest(String),
    Unsupported(String),
    Config(ConfigValidateErrorV1),
    Json(String),
    Input { path: String, message: String },
    InputLimit { path: String, limit: u64 },
    NonFiniteImpulse { index: usize },
    Touchstone(String),
    Channel(String),
    Parameters(String),
    Execution(String),
    Artifact(String),
}

impl Display for DirectRunErrorV1 {
    fn fmt(&self, f: &mut Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::InvalidRequest(message) => write!(f, "invalid COM run request: {message}"),
            Self::Unsupported(message) => write!(f, "unsupported COM run scope: {message}"),
            Self::Config(error) => Display::fmt(error, f),
            Self::Json(message) => write!(f, "invalid COM run JSON: {message}"),
            Self::Input { path, message } => write!(f, "cannot read {path}: {message}"),
            Self::InputLimit { path, limit } => {
                write!(f, "input {path} exceeds the {limit}-byte limit")
            }
            Self::NonFiniteImpulse { index } => {
                write!(f, "impulse sample {index} is not finite")
            }
            Self::Touchstone(message) => write!(f, "invalid Touchstone impulse input: {message}"),
            Self::Channel(message) => write!(f, "channel impulse resolution failed: {message}"),
            Self::Parameters(message) => write!(f, "invalid COM parameter surface: {message}"),
            Self::Execution(message) => write!(f, "COM execution failed: {message}"),
            Self::Artifact(message) => write!(f, "artifact write failed: {message}"),
        }
    }
}

impl std::error::Error for DirectRunErrorV1 {}

#[derive(Clone, Debug)]
struct LoadedConfigV1 {
    values: BTreeMap<String, ResolvedDefaultV1>,
    source_sha256: String,
    profile: String,
    document: Value,
}

#[derive(Clone, Debug)]
struct ImpulseInputV1 {
    values: Vec<f64>,
    erl_values: Option<Vec<f64>>,
    erl_time_s: Option<Vec<f64>>,
    source_sha256: String,
    sample_interval_s: Option<f64>,
    source_kind: &'static str,
    /// JSON may explicitly provide the already-integrated pulse response.
    /// Raw, Touchstone, and FD inputs remain impulse responses and are
    /// integrated at the COM boundary exactly once.
    already_pulse: bool,
    causality_correction_db: Option<f64>,
    truncation_db: Option<f64>,
    causality_iterations: Option<usize>,
}

#[derive(Clone, Debug)]
struct ErlTdrInputV1 {
    impulse: Vec<f64>,
    time_s: Vec<f64>,
}

#[derive(Clone, Debug)]
struct PortableBranchResultV1 {
    diagnostics: Value,
    effective_values: Option<Vec<f64>>,
    effective_pulse: Option<Vec<f64>>,
    effective_source_kind: Option<&'static str>,
    selected_fom_db: Option<f64>,
    calibration_sigma_bn_v: Option<f64>,
    calibration_sigma_ne_v: Option<f64>,
    calibration_sigma_hp_v: Option<f64>,
    erl_only_metrics: Option<sipi_com::ErlOnlyMetricsV1>,
    // Apply_EQ can produce a full THRU/FEXT/NEXT set.  Keep the generated
    // crosstalk waveforms separate from caller-provided files so the run
    // boundary can compose both inputs without reducing Apply_EQ to a
    // diagnostics-only branch.
    effective_fext: Vec<Vec<f64>>,
    effective_next: Vec<Vec<f64>>,
    effective_fext_pulses: Vec<Vec<f64>>,
    effective_next_pulses: Vec<Vec<f64>>,
}

/// Execute the bounded COM-02 run route and publish deterministic artifacts.
pub fn run_com_v1(request: &DirectRunRequestV1) -> Result<DirectRunReportV1, DirectRunErrorV1> {
    run_with_workflow(request, COM_02_DIRECT_PORT_SCHEMA_V1)
}

/// Execute COM-04's public sequence: load config, run COM, write artifacts.
pub fn load_config_run_com_write_artifacts_v1(
    request: &DirectRunRequestV1,
) -> Result<DirectRunReportV1, DirectRunErrorV1> {
    run_with_workflow(request, COM_04_DIRECT_PORT_SCHEMA_V1)
}

#[derive(Clone, Debug)]
struct PackageChannelV1 {
    values: Vec<f64>,
    source: Option<PathBuf>,
    source_bytes: Option<Vec<u8>>,
    already_pulse: bool,
    source_sha256: String,
    source_kind: &'static str,
}

#[derive(Clone, Debug)]
struct PackageCaseV1 {
    identity: String,
    calibration_identity: String,
    document: Value,
    pulse: PackageChannelV1,
    fext: Vec<PackageChannelV1>,
    next: Vec<PackageChannelV1>,
}

fn package_cases_from_config_v1(
    request: &DirectRunRequestV1,
) -> Result<Option<Vec<PackageCaseV1>>, DirectRunErrorV1> {
    let is_json = request
        .config
        .extension()
        .and_then(|value| value.to_str())
        .is_some_and(|value| value.eq_ignore_ascii_case("json"));
    if !is_json {
        return Ok(None);
    }
    let bytes = bounded_read_v1(&request.config, MAX_CONFIG_JSON_BYTES_V1)?;
    let document: Value = serde_json::from_slice(&bytes)
        .map_err(|error| DirectRunErrorV1::Json(error.to_string()))?;
    validate_output_input_custody_v1(request, Some(&document))?;
    let Some(cases) = document
        .get("package_cases")
        .or_else(|| document.get("cases"))
        .and_then(Value::as_array)
        .cloned()
    else {
        return Ok(None);
    };
    if cases.is_empty() || cases.len() > MAX_CROSSTALK_CHANNELS_V1 {
        return Err(DirectRunErrorV1::InputLimit {
            path: "package_cases".to_owned(),
            limit: MAX_CROSSTALK_CHANNELS_V1 as u64,
        });
    }
    let mut document_base = document;
    if let Some(object) = document_base.as_object_mut() {
        object.remove("package_cases");
        object.remove("cases");
    }
    let mut result = Vec::with_capacity(cases.len());
    for (index, value) in cases.iter().enumerate() {
        let case = value.as_object().ok_or_else(|| {
            DirectRunErrorV1::Parameters(format!("package_cases[{index}] must be an object"))
        })?;
        if request.calibration_noise.is_some()
            && ["fext", "next"].iter().any(|key| {
                case.get(*key)
                    .and_then(Value::as_array)
                    .is_some_and(|values| !values.is_empty())
            })
        {
            return Err(DirectRunErrorV1::InvalidRequest(
                "calibration_noise is mutually exclusive with FEXT/NEXT in the pinned ChannelSet"
                    .to_owned(),
            ));
        }
        let identity = case
            .get("case_id")
            .or_else(|| case.get("package_id"))
            .and_then(Value::as_str)
            .map(str::to_owned)
            .unwrap_or_else(|| format!("case-{index}"));
        if identity.is_empty() {
            return Err(DirectRunErrorV1::Parameters(format!(
                "package_cases[{index}].case_id must be non-empty"
            )));
        }
        let calibration_identity = case
            .get("calibration_id")
            .and_then(Value::as_str)
            .or_else(|| case.get("calibration_channel").and_then(Value::as_str))
            .map(str::to_owned)
            .unwrap_or_else(|| format!("{identity}:calibration"));
        if calibration_identity.is_empty() {
            return Err(DirectRunErrorV1::Parameters(format!(
                "package_cases[{index}].calibration_channel must be non-empty"
            )));
        }
        let base = request.config.parent().unwrap_or_else(|| Path::new("."));
        let pulse = parse_package_channel_v1(
            case.get("pulse").ok_or_else(|| {
                DirectRunErrorV1::Parameters(format!("package_cases[{index}].pulse is required"))
            })?,
            base,
            &format!("package_cases[{index}].pulse"),
        )?;
        let fext = parse_case_channels_v1(case.get("fext"), base, index, "fext")?;
        let next = parse_case_channels_v1(case.get("next"), base, index, "next")?;
        if case.contains_key("calibration_path")
            || case.contains_key("calibration_file")
            || case.contains_key("calibration")
            || case.contains_key("calibration_noise")
            || case
                .get("calibration_channel")
                .is_some_and(Value::is_object)
        {
            return Err(DirectRunErrorV1::Unsupported(
                "per-case calibration channels are not part of the pinned ChannelSet; use --calibration-noise once"
                    .to_owned(),
            ));
        }
        let mut case_document = document_base.clone();
        if let Some(object) = case_document.as_object_mut() {
            object.insert(
                "package_case".to_owned(),
                json!({
                    "case_id": identity,
                    "pulse": pulse.values,
                    "pulse_already_pulse": pulse.already_pulse,
                    "fext": fext.iter().map(|value| value.values.clone()).collect::<Vec<_>>(),
                    "fext_already_pulse": fext.iter().map(|value| value.already_pulse).collect::<Vec<_>>(),
                    "next": next.iter().map(|value| value.values.clone()).collect::<Vec<_>>(),
                    "next_already_pulse": next.iter().map(|value| value.already_pulse).collect::<Vec<_>>()
                }),
            );
            for key in [
                "parameters",
                "portable",
                "workbook",
                "legacy_csv",
                "calibration",
                "calibration_noise",
                "equalization",
                "mmse",
                "rx_ffe_search",
                "fvlms_rxffe",
                "tdiln",
                "search",
                "erl_only",
            ] {
                if let Some(value) = case.get(key) {
                    object.insert(key.to_owned(), value.clone());
                }
            }
        }
        result.push(PackageCaseV1 {
            identity,
            calibration_identity,
            document: case_document,
            pulse,
            fext,
            next,
        });
    }
    Ok(Some(result))
}

fn parse_case_channels_v1(
    value: Option<&Value>,
    base: &Path,
    index: usize,
    role: &str,
) -> Result<Vec<PackageChannelV1>, DirectRunErrorV1> {
    let Some(value) = value else {
        return Ok(Vec::new());
    };
    let rows = value.as_array().ok_or_else(|| {
        DirectRunErrorV1::Parameters(format!("package_cases[{index}].{role} must be arrays"))
    })?;
    rows.iter()
        .enumerate()
        .map(|(row, value)| {
            parse_package_channel_v1(
                value,
                base,
                &format!("package_cases[{index}].{role}[{row}]"),
            )
        })
        .collect()
}

fn parse_package_channel_v1(
    value: &Value,
    base: &Path,
    field: &str,
) -> Result<PackageChannelV1, DirectRunErrorV1> {
    let source_value = value.as_str().or_else(|| {
        value
            .as_object()
            .and_then(|object| object.get("path"))
            .and_then(Value::as_str)
    });
    if let Some(source_value) = source_value {
        let source = if Path::new(source_value).is_absolute() {
            PathBuf::from(source_value)
        } else {
            base.join(source_value)
        };
        let (loaded, source_bytes) = load_channel_input_snapshot_v1(&source)?;
        return Ok(PackageChannelV1 {
            values: loaded.values,
            source: Some(source),
            source_bytes: Some(source_bytes),
            already_pulse: loaded.already_pulse,
            source_sha256: loaded.source_sha256,
            source_kind: loaded.source_kind,
        });
    }
    let values = parse_f64_array_v1(value, field)?;
    validate_impulse_v1(&values)?;
    Ok(PackageChannelV1 {
        source_sha256: sha256_f64_v1(&values),
        values,
        source: None,
        source_bytes: None,
        already_pulse: false,
        source_kind: "package-case-inline-impulse",
    })
}

fn load_channel_input_snapshot_v1(
    path: &Path,
) -> Result<(ImpulseInputV1, Vec<u8>), DirectRunErrorV1> {
    let bytes = bounded_read_v1(path, MAX_IMPULSE_FILE_BYTES_V1)?;
    let extension = path.extension().and_then(|value| value.to_str());
    let mut staged = std::env::temp_dir().join(format!(
        "sipi-com-channel-snapshot-{}",
        sha256_bytes_v1(&bytes)
    ));
    if let Some(extension) = extension {
        staged.set_extension(extension);
    }
    fs::write(&staged, &bytes).map_err(|error| DirectRunErrorV1::Input {
        path: path.display().to_string(),
        message: format!("cannot stage exact channel bytes: {error}"),
    })?;
    let loaded = load_channel_input_v1(&staged);
    let _ = fs::remove_file(&staged);
    Ok((loaded?, bytes))
}

fn stage_exact_input_v1(
    root: &Path,
    role: &str,
    source: &Path,
    limit: u64,
) -> Result<(PathBuf, String, &'static str), DirectRunErrorV1> {
    let bytes = bounded_read_v1(source, limit)?;
    let mut staged = root.join(format!("{role}-source"));
    if let Some(extension) = source.extension() {
        staged.set_extension(extension);
    }
    fs::write(&staged, &bytes).map_err(|error| DirectRunErrorV1::Artifact(error.to_string()))?;
    let source_kind = if source
        .extension()
        .and_then(|value| value.to_str())
        .is_some_and(|value| value.eq_ignore_ascii_case("s4p"))
    {
        "s4p-calibration-channel"
    } else {
        "json-calibration-channel"
    };
    Ok((staged, sha256_bytes_v1(&bytes), source_kind))
}

fn stage_package_channel_v1(
    root: &Path,
    role: &str,
    index: usize,
    channel: &PackageChannelV1,
) -> Result<PathBuf, DirectRunErrorV1> {
    let mut path = root.join(format!("{role}-{index}"));
    if let Some(source) = channel.source.as_ref() {
        if let Some(extension) = source.extension() {
            path.set_extension(extension);
        }
        let bytes = channel.source_bytes.as_ref().ok_or_else(|| {
            DirectRunErrorV1::Execution("package source snapshot is missing".to_owned())
        })?;
        fs::write(&path, bytes).map_err(|error| DirectRunErrorV1::Artifact(error.to_string()))?;
    } else {
        path.set_extension("json");
        fs::write(
            &path,
            serde_json::to_vec(&json!({"impulse": channel.values}))
                .map_err(|error| DirectRunErrorV1::Artifact(error.to_string()))?,
        )
        .map_err(|error| DirectRunErrorV1::Artifact(error.to_string()))?;
    }
    Ok(path)
}

fn package_calibration_manifest_v1(
    identity: &str,
    source: Option<&PathBuf>,
    snapshot: Option<&(PathBuf, String, &'static str)>,
) -> Value {
    json!({
        "identity": identity,
        "source": source,
        "sha256": snapshot.map(|value| &value.1),
        "source_kind": snapshot.map(|value| value.2),
        "materialization": snapshot.map(|_| "staged_exact_bytes")
    })
}

fn run_package_cases_v1(
    request: &DirectRunRequestV1,
    schema: &'static str,
    cases: Vec<PackageCaseV1>,
) -> Result<DirectRunReportV1, DirectRunErrorV1> {
    let root = std::env::temp_dir().join(format!(
        "sipi-com-package-cases-{}-{}",
        std::process::id(),
        sha256_bytes_v1(request.config.to_string_lossy().as_bytes())
    ));
    if root.exists() {
        fs::remove_dir_all(&root).map_err(|error| DirectRunErrorV1::Artifact(error.to_string()))?;
    }
    fs::create_dir_all(&root).map_err(|error| DirectRunErrorV1::Artifact(error.to_string()))?;
    let calibration_snapshot = request
        .calibration_noise
        .as_ref()
        .map(|path| stage_exact_input_v1(&root, "calibration", path, MAX_CONFIG_JSON_BYTES_V1))
        .transpose()?;
    let mut published_cases = Vec::with_capacity(cases.len());
    let mut case_manifests = Vec::with_capacity(cases.len());
    let mut first_report = None;
    let outcome = (|| {
        for (index, case) in cases.iter().enumerate() {
            let case_root = root.join(format!("case-{index}"));
            fs::create_dir_all(&case_root)
                .map_err(|error| DirectRunErrorV1::Artifact(error.to_string()))?;
            let config_path = case_root.join("config.json");
            let pulse_path = stage_package_channel_v1(&case_root, "thru", 0, &case.pulse)?;
            fs::write(
                &config_path,
                serde_json::to_vec(&case.document)
                    .map_err(|error| DirectRunErrorV1::Artifact(error.to_string()))?,
            )
            .map_err(|error| DirectRunErrorV1::Artifact(error.to_string()))?;
            let mut child =
                DirectRunRequestV1::new(&config_path, &pulse_path, case_root.join("artifacts"));
            child.calibration_noise = calibration_snapshot.as_ref().map(|value| value.0.clone());
            child.fext = Vec::with_capacity(case.fext.len());
            for (channel, source) in case.fext.iter().enumerate() {
                let path = stage_package_channel_v1(&case_root, "fext", channel, source)?;
                child.fext.push(path);
            }
            child.next = Vec::with_capacity(case.next.len());
            for (channel, source) in case.next.iter().enumerate() {
                let path = stage_package_channel_v1(&case_root, "next", channel, source)?;
                child.next.push(path);
            }
            let report = run_with_workflow(&child, schema)?;
            if first_report.is_none() {
                first_report = Some(report.clone());
            }
            let mut published = report.result["cases"]
                .as_array()
                .and_then(|values| values.first())
                .cloned()
                .ok_or_else(|| {
                    DirectRunErrorV1::Execution("package case emitted no result".to_owned())
                })?;
            published["case_index"] = json!(index);
            published["case_id"] = json!(case.identity);
            published["package_case_index"] = json!(index);
            if let Some(path) = case.pulse.source.as_ref() {
                published["channels"]["thru"] = json!(path);
            }
            if !case.fext.is_empty() {
                let existing = published["channels"]["fext"]
                    .as_array()
                    .cloned()
                    .unwrap_or_default();
                published["channels"]["fext"] = json!(
                    case.fext
                        .iter()
                        .enumerate()
                        .map(|(index, channel)| {
                            channel
                                .source
                                .as_ref()
                                .map(|path| json!(path))
                                .unwrap_or_else(|| {
                                    existing.get(index).cloned().unwrap_or(Value::Null)
                                })
                        })
                        .collect::<Vec<_>>()
                );
            }
            if !case.next.is_empty() {
                let existing = published["channels"]["next"]
                    .as_array()
                    .cloned()
                    .unwrap_or_default();
                published["channels"]["next"] = json!(
                    case.next
                        .iter()
                        .enumerate()
                        .map(|(index, channel)| {
                            channel
                                .source
                                .as_ref()
                                .map(|path| json!(path))
                                .unwrap_or_else(|| {
                                    existing.get(index).cloned().unwrap_or(Value::Null)
                                })
                        })
                        .collect::<Vec<_>>()
                );
            }
            if let Some(path) = request.calibration_noise.as_ref() {
                published["channels"]["calibration_noise"] = json!(path);
            }
            published["channel_identity"] = json!({
                "thru": format!("{}:thru", case.identity),
                "fext": case.fext.iter().enumerate().map(|(channel, _)| {
                    format!("{}:fext:{channel}", case.identity)
                }).collect::<Vec<_>>(),
                "next": case.next.iter().enumerate().map(|(channel, _)| {
                    format!("{}:next:{channel}", case.identity)
                }).collect::<Vec<_>>(),
                "calibration": case.calibration_identity,
            });
            case_manifests.push(json!({
                "case_id": case.identity,
                "thru": {
                    "identity": format!("{}:thru", case.identity),
                    "sha256": case.pulse.source_sha256,
                    "sample_count": case.pulse.values.len(),
                    "source": case.pulse.source,
                    "source_kind": case.pulse.source_kind,
                    "already_pulse": case.pulse.already_pulse
                },
                "fext": case.fext.iter().enumerate().map(|(channel, values)| json!({
                    "identity": format!("{}:fext:{channel}", case.identity),
                    "sha256": values.source_sha256,
                    "sample_count": values.values.len(),
                    "source": values.source,
                    "source_kind": values.source_kind,
                    "already_pulse": values.already_pulse
                })).collect::<Vec<_>>(),
                "next": case.next.iter().enumerate().map(|(channel, values)| json!({
                    "identity": format!("{}:next:{channel}", case.identity),
                    "sha256": values.source_sha256,
                    "sample_count": values.values.len(),
                    "source": values.source,
                    "source_kind": values.source_kind,
                    "already_pulse": values.already_pulse
                })).collect::<Vec<_>>(),
                "calibration": package_calibration_manifest_v1(
                    &case.calibration_identity,
                    request.calibration_noise.as_ref(),
                    calibration_snapshot.as_ref(),
                )
            }));
            published_cases.push(published);
        }
        let first = first_report
            .ok_or_else(|| DirectRunErrorV1::Execution("empty package cases".to_owned()))?;
        let mut result = first.result;
        result["cases"] = Value::Array(published_cases);
        result["provenance"]["package_cases"] = json!({
            "count": cases.len(),
            "identity_field": "case_id",
            "channel_identity": "cases[].channel_identity",
            "calibration_identity": "cases[].channel_identity.calibration",
            "manifests": case_manifests
        });
        result["input_manifest"]["package_cases"] =
            result["provenance"]["package_cases"]["manifests"].clone();
        let artifacts = write_run_artifacts_internal_v1(
            &request.output_dir,
            &result,
            request.overwrite,
            request.legacy_csv,
        )?;
        Ok(DirectRunReportV1 {
            schema,
            workflow: vec!["load_config", "run_com", "write_artifacts"],
            result,
            artifacts,
            impulse_sample_count: first.impulse_sample_count,
            impulse_sha256: first.impulse_sha256,
            config_sha256: first.config_sha256,
        })
    })();
    let _ = fs::remove_dir_all(&root);
    outcome
}

fn run_with_workflow(
    request: &DirectRunRequestV1,
    schema: &'static str,
) -> Result<DirectRunReportV1, DirectRunErrorV1> {
    validate_request(request)?;
    if let Some(package_cases) = package_cases_from_config_v1(request)? {
        return run_package_cases_v1(request, schema, package_cases);
    }
    let loaded = load_config_v1(request)?;
    validate_output_input_custody_v1(request, Some(&loaded.document))?;
    let erl_s2p_exact = exact_erl_s2p_profile_v1(&loaded.document, &request.pulse)?;
    let input_impulse = if request
        .pulse
        .extension()
        .and_then(|value| value.to_str())
        .is_some_and(|value| value.eq_ignore_ascii_case("s4p"))
    {
        load_s4p_impulse_v1(&request.pulse)?
    } else if erl_s2p_exact {
        load_erl_s2p_impulse_v1(&request.pulse)?
    } else {
        load_impulse_v1(&request.pulse)?
    };
    let mut fext_inputs = request
        .fext
        .iter()
        .map(|path| load_channel_input_v1(path))
        .collect::<Result<Vec<_>, _>>()?;
    let mut next_inputs = request
        .next
        .iter()
        .map(|path| load_channel_input_v1(path))
        .collect::<Result<Vec<_>, _>>()?;
    // A parsed package_case is itself an admitted channel source.  When the
    // public request did not provide separate FEXT/NEXT files, retain those
    // package channels in the final COM chain instead of using them only for
    // calibration diagnostics.  Package fan-out supplies explicit child
    // files, so this guard avoids duplicating those channels.
    if let Some(package_case) = loaded
        .document
        .get("package_case")
        .and_then(Value::as_object)
    {
        if request.fext.is_empty() {
            for (index, value) in package_case
                .get("fext")
                .and_then(Value::as_array)
                .unwrap_or(&Vec::new())
                .iter()
                .enumerate()
            {
                let values = parse_f64_array_v1(value, &format!("package_case.fext[{index}]"))?;
                validate_impulse_v1(&values)?;
                fext_inputs.push(ImpulseInputV1 {
                    source_sha256: sha256_f64_v1(&values),
                    values,
                    erl_values: None,
                    erl_time_s: None,
                    sample_interval_s: None,
                    source_kind: "package-case-fext",
                    already_pulse: false,
                    causality_correction_db: None,
                    truncation_db: None,
                    causality_iterations: None,
                });
            }
        }
        if request.next.is_empty() {
            for (index, value) in package_case
                .get("next")
                .and_then(Value::as_array)
                .unwrap_or(&Vec::new())
                .iter()
                .enumerate()
            {
                let values = parse_f64_array_v1(value, &format!("package_case.next[{index}]"))?;
                validate_impulse_v1(&values)?;
                next_inputs.push(ImpulseInputV1 {
                    source_sha256: sha256_f64_v1(&values),
                    values,
                    erl_values: None,
                    erl_time_s: None,
                    sample_interval_s: None,
                    source_kind: "package-case-next",
                    already_pulse: false,
                    causality_correction_db: None,
                    truncation_db: None,
                    causality_iterations: None,
                });
            }
        }
    }
    let controls = canonical_controls_v1(&loaded.values)?;
    let branches = portable_branch_result_v1(
        &loaded.document,
        &input_impulse,
        Some(request),
        Some(&controls),
    )?;
    if fext_inputs
        .len()
        .saturating_add(next_inputs.len())
        .saturating_add(branches.effective_fext.len())
        .saturating_add(branches.effective_next.len())
        > MAX_CROSSTALK_CHANNELS_V1
    {
        return Err(DirectRunErrorV1::InputLimit {
            path: "fext/next channel count including portable.equalization".to_owned(),
            limit: MAX_CROSSTALK_CHANNELS_V1 as u64,
        });
    }
    let impulse = if let Some(values) = branches.effective_values.clone() {
        ImpulseInputV1 {
            values,
            erl_values: input_impulse.erl_values.clone(),
            erl_time_s: input_impulse.erl_time_s.clone(),
            source_sha256: input_impulse.source_sha256.clone(),
            sample_interval_s: input_impulse.sample_interval_s,
            source_kind: branches
                .effective_source_kind
                .unwrap_or(input_impulse.source_kind),
            already_pulse: false,
            causality_correction_db: input_impulse.causality_correction_db,
            truncation_db: input_impulse.truncation_db,
            causality_iterations: input_impulse.causality_iterations,
        }
    } else {
        input_impulse
    };
    let samples_per_ui = required_usize_from_controls_v1(&controls, "samples_per_ui")?;
    // Channel files are impulse responses; the COM PDF chain consumes the
    // source's zero-state rectangular pulse response. Search/Apply_EQ may
    // already provide the selected pulse, otherwise form it here exactly once.
    let source_pulse = if impulse.already_pulse {
        impulse.values.clone()
    } else {
        rectangular_pulse_response_v1(&impulse.values, samples_per_ui)
            .map_err(|error| DirectRunErrorV1::Parameters(format!("channel pulse: {error:?}")))?
    };
    let chain_values = branches
        .effective_pulse
        .clone()
        .map_or_else(
            || {
                if impulse.already_pulse {
                    Ok(impulse.values.clone())
                } else {
                    rectangular_pulse_response_v1(&impulse.values, samples_per_ui)
                }
            },
            |selected| Ok(materialize_selected_pulse_v1(&source_pulse, &selected)),
        )
        .map_err(|error| DirectRunErrorV1::Parameters(format!("channel pulse: {error:?}")))?;
    let mut effective_controls = controls.clone();
    if let Some(sigma_ne_v) = branches.calibration_sigma_ne_v {
        effective_controls.insert("sigma_ne".to_owned(), ResolvedDefaultV1::Scalar(sigma_ne_v));
    }
    let dto = merge_com_parameters_v1(
        &effective_controls.keys().cloned().collect::<Vec<_>>(),
        &effective_controls,
        &BTreeMap::new(),
        &[],
    )
    .map_err(|error| DirectRunErrorV1::Parameters(format!("{error:?}")))?;
    let request_bytes = admission_request_bytes_v1(request, &controls)?;
    let mut fext_pulse_values = fext_inputs
        .iter()
        .map(|input| {
            if input.already_pulse {
                Ok(input.values.clone())
            } else {
                rectangular_pulse_response_v1(&input.values, samples_per_ui)
                    .map_err(|error| DirectRunErrorV1::Parameters(format!("FEXT pulse: {error:?}")))
            }
        })
        .collect::<Result<Vec<_>, _>>()?;
    fext_pulse_values.extend(branches.effective_fext_pulses.clone());
    let fext_values = fext_pulse_values
        .iter()
        .map(Vec::as_slice)
        .collect::<Vec<_>>();
    let mut next_pulse_values = next_inputs
        .iter()
        .map(|input| {
            if input.already_pulse {
                Ok(input.values.clone())
            } else {
                rectangular_pulse_response_v1(&input.values, samples_per_ui)
                    .map_err(|error| DirectRunErrorV1::Parameters(format!("NEXT pulse: {error:?}")))
            }
        })
        .collect::<Result<Vec<_>, _>>()?;
    next_pulse_values.extend(branches.effective_next_pulses.clone());
    let next_values = next_pulse_values
        .iter()
        .map(Vec::as_slice)
        .collect::<Vec<_>>();
    let envelope = if let Some(metrics) = branches.erl_only_metrics.as_ref() {
        sipi_com::erl_only_envelope_v1(metrics)
            .map_err(|error| DirectRunErrorV1::Parameters(error.to_owned()))
    } else if fext_values.is_empty() && next_values.is_empty() {
        execute_com_run_v1(&request_bytes, &chain_values, &dto)
            .map_err(|error| DirectRunErrorV1::Execution(format!("{error:?}")))
    } else {
        execute_com_run_with_crosstalk_v1(
            &request_bytes,
            &chain_values,
            &fext_values,
            &next_values,
            &dto,
        )
        .map_err(|error| DirectRunErrorV1::Execution(format!("{error:?}")))
    }?;
    if !envelope.admitted() {
        return Err(DirectRunErrorV1::Execution(
            envelope
                .invalid_reason()
                .unwrap_or("request was not admitted")
                .to_owned(),
        ));
    }
    let result = result_value_v1(
        request,
        &loaded,
        &impulse,
        &fext_inputs,
        &next_inputs,
        &branches.effective_fext,
        &branches.effective_next,
        &envelope,
        &branches.diagnostics,
        &chain_values,
        &fext_pulse_values,
        &next_pulse_values,
        branches.selected_fom_db,
        branches.calibration_sigma_bn_v,
        branches.calibration_sigma_ne_v,
        branches.calibration_sigma_hp_v,
    );
    let artifacts = write_run_artifacts_internal_v1(
        &request.output_dir,
        &result,
        request.overwrite,
        request.legacy_csv,
    )?;
    Ok(DirectRunReportV1 {
        schema,
        workflow: vec!["load_config", "run_com", "write_artifacts"],
        result,
        artifacts,
        impulse_sample_count: impulse.values.len(),
        impulse_sha256: sha256_f64_v1(&impulse.values),
        config_sha256: loaded.source_sha256,
    })
}

/// Publish a validated result payload.  This function deliberately does not
/// execute code or accept arbitrary file names, keeping the write boundary
/// reusable by COM-03 evidence tools and the COM-04 API leaf.
pub fn write_run_artifacts_v1(
    output_dir: &Path,
    result: &Value,
    overwrite: bool,
) -> Result<RunArtifactSetV1, DirectRunErrorV1> {
    write_run_artifacts_internal_v1(output_dir, result, overwrite, false)
}

fn write_run_artifacts_internal_v1(
    output_dir: &Path,
    result: &Value,
    overwrite: bool,
    legacy_csv: bool,
) -> Result<RunArtifactSetV1, DirectRunErrorV1> {
    crate::validate_result_json_v1(result)
        .map_err(|error| DirectRunErrorV1::Artifact(error.to_string()))?;
    let result_bytes = serde_json::to_vec_pretty(result)
        .map_err(|error| DirectRunErrorV1::Artifact(error.to_string()))?;
    if result_bytes.len() > MAX_RESULT_BYTES_V1 {
        return Err(DirectRunErrorV1::Artifact(
            "result JSON exceeds the output budget".to_owned(),
        ));
    }
    reject_symlink_chain_v1(output_dir).map_err(DirectRunErrorV1::Artifact)?;
    let output_exists = output_dir.exists();
    if output_exists {
        let metadata = fs::symlink_metadata(output_dir)
            .map_err(|error| DirectRunErrorV1::Artifact(error.to_string()))?;
        if !metadata.is_dir() || metadata.file_type().is_symlink() {
            return Err(DirectRunErrorV1::Artifact(
                "output directory must be a regular directory".to_owned(),
            ));
        }
    } else if let Some(parent) = output_dir.parent() {
        fs::create_dir_all(parent)
            .map_err(|error| DirectRunErrorV1::Artifact(error.to_string()))?;
    }
    let result_path = output_dir.join("result.json");
    let report_path = output_dir.join("report.html");
    let diagnostics_path = output_dir.join("diagnostics.json");
    let report = report_html_v1(result)?;
    let diagnostics = diagnostics_json_v1(result)?;
    if report.len() > MAX_REPORT_BYTES_V1 || diagnostics.len() > MAX_DIAGNOSTICS_BYTES_V1 {
        return Err(DirectRunErrorV1::Artifact(
            "artifact output exceeds the output budget".to_owned(),
        ));
    }
    for path in [&result_path, &report_path, &diagnostics_path] {
        if path.exists() && !overwrite {
            return Err(DirectRunErrorV1::Artifact(format!(
                "output already exists: {}",
                path.display()
            )));
        }
    }
    if output_exists && !overwrite {
        let has_stale = fs::read_dir(output_dir)
            .map_err(|error| DirectRunErrorV1::Artifact(error.to_string()))?
            .next()
            .is_some();
        if has_stale {
            return Err(DirectRunErrorV1::Artifact(format!(
                "output directory already contains artifacts: {}",
                output_dir.display()
            )));
        }
    }
    let parent = output_dir.parent().unwrap_or_else(|| Path::new("."));
    let name = output_dir
        .file_name()
        .and_then(|value| value.to_str())
        .unwrap_or("artifacts");
    let staging = parent.join(format!(".{name}.staging-{}", std::process::id()));
    if staging.exists() {
        return Err(DirectRunErrorV1::Artifact(format!(
            "staging directory already exists: {}",
            staging.display()
        )));
    }
    fs::create_dir(&staging).map_err(|error| DirectRunErrorV1::Artifact(error.to_string()))?;
    let staged_result = staging.join("result.json");
    let staged_report = staging.join("report.html");
    let staged_diagnostics = staging.join("diagnostics.json");
    let staged_legacy = staging.join("legacy.csv");
    let staged = (|| {
        atomic_write_v1(&staged_result, &result_bytes, false)?;
        atomic_write_v1(&staged_report, report.as_bytes(), false)?;
        atomic_write_v1(&staged_diagnostics, diagnostics.as_bytes(), false)?;
        if legacy_csv {
            write_legacy_csv_v1(&staged_legacy, result, false)?;
        }
        Ok::<(), DirectRunErrorV1>(())
    })();
    if let Err(error) = staged {
        let _ = fs::remove_dir_all(&staging);
        return Err(error);
    }
    let backup = parent.join(format!(".{name}.backup-{}", std::process::id()));
    if output_exists {
        if backup.exists() {
            let _ = fs::remove_dir_all(&staging);
            return Err(DirectRunErrorV1::Artifact(format!(
                "backup directory already exists: {}",
                backup.display()
            )));
        }
        fs::rename(output_dir, &backup).map_err(|error| {
            let _ = fs::remove_dir_all(&staging);
            DirectRunErrorV1::Artifact(error.to_string())
        })?;
    }
    if let Err(error) = fs::rename(&staging, output_dir) {
        if output_exists {
            let _ = fs::rename(&backup, output_dir);
        }
        let _ = fs::remove_dir_all(&staging);
        return Err(DirectRunErrorV1::Artifact(error.to_string()));
    }
    if output_exists {
        fs::remove_dir_all(&backup)
            .map_err(|error| DirectRunErrorV1::Artifact(error.to_string()))?;
    }
    Ok(RunArtifactSetV1 {
        result_json: result_path,
        report_html: report_path,
        diagnostics_json: diagnostics_path,
        legacy_csv: legacy_csv.then_some(output_dir.join("legacy.csv")),
    })
}

/// Upstream-shaped name for callers that only need the artifact publication
/// boundary after producing a validated result payload.
pub fn write_artifacts_v1(
    output_dir: &Path,
    result: &Value,
    overwrite: bool,
) -> Result<RunArtifactSetV1, DirectRunErrorV1> {
    write_run_artifacts_v1(output_dir, result, overwrite)
}

fn validate_request(request: &DirectRunRequestV1) -> Result<(), DirectRunErrorV1> {
    if request.config.as_os_str().is_empty() {
        return Err(DirectRunErrorV1::InvalidRequest(
            "configuration path is required".to_owned(),
        ));
    }
    if request.pulse.as_os_str().is_empty() {
        return Err(DirectRunErrorV1::InvalidRequest(
            "channel impulse path is required".to_owned(),
        ));
    }
    if request.output_dir.as_os_str().is_empty() {
        return Err(DirectRunErrorV1::InvalidRequest(
            "output directory is required".to_owned(),
        ));
    }
    if request.fext.len().saturating_add(request.next.len()) > MAX_CROSSTALK_CHANNELS_V1 {
        return Err(DirectRunErrorV1::InputLimit {
            path: "fext/next channel count".to_owned(),
            limit: MAX_CROSSTALK_CHANNELS_V1 as u64,
        });
    }
    if request.calibration_noise.is_some() && (!request.fext.is_empty() || !request.next.is_empty())
    {
        return Err(DirectRunErrorV1::InvalidRequest(
            "calibration_noise is mutually exclusive with FEXT/NEXT in the pinned ChannelSet"
                .to_owned(),
        ));
    }
    if request.artifact_id.is_empty()
        || request.artifact_id == "."
        || request.artifact_id == ".."
        || request
            .artifact_id
            .chars()
            .any(|value| value == '/' || value == '\\' || value.is_control())
    {
        return Err(DirectRunErrorV1::InvalidRequest(
            "artifact_id must be a single safe path component".to_owned(),
        ));
    }
    if request.profile != "r480" {
        return Err(DirectRunErrorV1::Unsupported(format!(
            "only profile r480 is admitted, got {}",
            request.profile
        )));
    }
    validate_output_input_custody_v1(request, None)?;
    if let Some(reader) = request.reader.as_deref()
        && reader != "r480"
    {
        return Err(DirectRunErrorV1::Unsupported(format!(
            "only r480 reader semantics are admitted, got {reader}"
        )));
    }
    Ok(())
}

fn validate_output_input_custody_v1(
    request: &DirectRunRequestV1,
    document: Option<&Value>,
) -> Result<(), DirectRunErrorV1> {
    reject_symlink_chain_v1(&request.output_dir).map_err(DirectRunErrorV1::InvalidRequest)?;
    let mut inputs = vec![request.config.clone(), request.pulse.clone()];
    inputs.extend(request.fext.iter().cloned());
    inputs.extend(request.next.iter().cloned());
    if let Some(path) = request.calibration_noise.as_ref() {
        inputs.push(path.clone());
    }
    if let Some(document) = document {
        let base = request.config.parent().unwrap_or_else(|| Path::new("."));
        collect_document_input_paths_v1(document, base, false, &mut inputs);
    }
    let output_key = relation_path_v1(&request.output_dir).map_err(|message| {
        DirectRunErrorV1::InvalidRequest(format!("output directory custody: {message}"))
    })?;
    for input in inputs {
        let input_key = relation_path_v1(&input).map_err(|message| {
            DirectRunErrorV1::InvalidRequest(format!(
                "input custody {}: {message}",
                input.display()
            ))
        })?;
        if paths_overlap_v1(&output_key, &input_key)
            || (request.output_dir.exists()
                && input.exists()
                && same_file::is_same_file(&request.output_dir, &input).unwrap_or(false))
        {
            return Err(DirectRunErrorV1::InvalidRequest(format!(
                "output directory overlaps input path: {}",
                input.display()
            )));
        }
    }
    Ok(())
}

fn collect_document_input_paths_v1(
    value: &Value,
    base: &Path,
    input_context: bool,
    paths: &mut Vec<PathBuf>,
) {
    if let Some(array) = value.as_array() {
        for item in array {
            if input_context && let Some(path) = item.as_str() {
                let candidate = Path::new(path);
                paths.push(if candidate.is_absolute() {
                    candidate.to_path_buf()
                } else {
                    base.join(candidate)
                });
            }
            collect_document_input_paths_v1(item, base, input_context, paths);
        }
        return;
    }
    let Some(object) = value.as_object() else {
        return;
    };
    for (key, value) in object {
        let normalized = key.to_ascii_lowercase();
        let key_context = input_context
            || normalized.contains("workbook")
            || normalized.contains("legacy_csv")
            || normalized.contains("reuse")
            || normalized.contains("calibration")
            || normalized.contains("channel")
            || normalized == "fext"
            || normalized == "next"
            || normalized == "thru"
            || normalized == "pulse"
            || normalized == "input"
            || normalized == "source";
        if key_context {
            if let Some(path) = value.as_str() {
                let candidate = Path::new(path);
                paths.push(if candidate.is_absolute() {
                    candidate.to_path_buf()
                } else {
                    base.join(candidate)
                });
            }
            collect_document_input_paths_v1(value, base, true, paths);
        } else {
            collect_document_input_paths_v1(value, base, false, paths);
        }
    }
}

fn relation_path_v1(path: &Path) -> Result<PathBuf, String> {
    let absolute = if path.is_absolute() {
        path.to_path_buf()
    } else {
        std::env::current_dir()
            .map_err(|error| error.to_string())?
            .join(path)
    };
    let mut missing = Vec::new();
    let mut cursor = absolute.clone();
    while !cursor.exists() {
        let Some(name) = cursor.file_name() else {
            break;
        };
        missing.push(name.to_os_string());
        cursor.pop();
    }
    let mut canonical = fs::canonicalize(&cursor).map_err(|error| error.to_string())?;
    for name in missing.iter().rev() {
        canonical.push(name);
    }
    Ok(canonical)
}

fn paths_overlap_v1(left: &Path, right: &Path) -> bool {
    #[cfg(windows)]
    {
        let left = PathBuf::from(left.to_string_lossy().to_ascii_lowercase());
        let right = PathBuf::from(right.to_string_lossy().to_ascii_lowercase());
        left == right || left.starts_with(&right) || right.starts_with(&left)
    }
    #[cfg(not(windows))]
    {
        left == right || left.starts_with(right) || right.starts_with(left)
    }
}

fn load_config_v1(request: &DirectRunRequestV1) -> Result<LoadedConfigV1, DirectRunErrorV1> {
    let bytes = bounded_read_v1(&request.config, MAX_CONFIG_JSON_BYTES_V1)?;
    let source_sha256 = sha256_bytes_v1(&bytes);
    if request
        .config
        .extension()
        .and_then(|extension| extension.to_str())
        .is_some_and(|extension| extension.eq_ignore_ascii_case("json"))
    {
        let mut document: Value = serde_json::from_slice(&bytes)
            .map_err(|error| DirectRunErrorV1::Json(error.to_string()))?;
        merge_cli_calibration_v1(&mut document, request)?;
        let values = parameter_map_from_json_v1(&document)?;
        if values.is_empty() {
            return Err(DirectRunErrorV1::Unsupported(
                "JSON config contains no canonical COM parameters".to_owned(),
            ));
        }
        return Ok(LoadedConfigV1 {
            values,
            source_sha256,
            profile: request.profile.clone(),
            document,
        });
    }

    let config_request = ConfigValidateRequestV1 {
        config: request.config.clone(),
        profile: request.profile.clone(),
        reader: request.reader.clone(),
        fix_ids: request.fix_ids.clone(),
        overrides: request.overrides.clone(),
        json: false,
        materialized_json: true,
    };
    let report = config_validate_v1(&config_request).map_err(DirectRunErrorV1::Config)?;
    let mut document = report.value().clone();
    merge_cli_calibration_v1(&mut document, request)?;
    let values = parameter_map_from_materialized_v1(&report)?;
    Ok(LoadedConfigV1 {
        values,
        source_sha256,
        profile: request.profile.clone(),
        document,
    })
}

fn parameter_map_from_materialized_v1(
    report: &ConfigValidateReportV1,
) -> Result<BTreeMap<String, ResolvedDefaultV1>, DirectRunErrorV1> {
    let object = report
        .value()
        .get("materialized")
        .and_then(Value::as_object)
        .ok_or_else(|| {
            DirectRunErrorV1::Json("config report has no materialized object".to_owned())
        })?;
    let mut values = BTreeMap::new();
    for key in ["parameters", "options"] {
        let Some(map) = object.get(key).and_then(Value::as_object) else {
            continue;
        };
        values.extend(parse_parameter_object_v1(map)?);
    }
    Ok(values)
}

fn merge_cli_calibration_v1(
    document: &mut Value,
    request: &DirectRunRequestV1,
) -> Result<(), DirectRunErrorV1> {
    let Some(path) = request.calibration_noise.as_ref() else {
        return Ok(());
    };
    let is_s4p = path
        .extension()
        .and_then(|value| value.to_str())
        .is_some_and(|value| value.eq_ignore_ascii_case("s4p"));
    let calibration = if is_s4p {
        load_s4p_calibration_document_v1(path)?
    } else {
        let bytes = bounded_read_v1(path, MAX_CONFIG_JSON_BYTES_V1)?;
        let payload: Value = serde_json::from_slice(&bytes)
            .map_err(|error| DirectRunErrorV1::Json(format!("calibration payload: {error}")))?;
        payload
            .get("portable")
            .and_then(Value::as_object)
            .and_then(|portable| portable.get("calibration"))
            .or_else(|| payload.get("calibration"))
            .unwrap_or(&payload)
            .clone()
    };
    if !calibration.is_object() {
        return Err(DirectRunErrorV1::Parameters(
            "--calibration-noise JSON must contain a calibration object".to_owned(),
        ));
    }
    let root = document.as_object_mut().ok_or_else(|| {
        DirectRunErrorV1::Json("canonical config must be a JSON object".to_owned())
    })?;
    let portable = root
        .entry("portable".to_owned())
        .or_insert_with(|| Value::Object(Map::new()))
        .as_object_mut()
        .ok_or_else(|| DirectRunErrorV1::Parameters("portable must be an object".to_owned()))?;
    if is_s4p {
        let mut merged = portable
            .get("calibration")
            .and_then(Value::as_object)
            .cloned()
            .unwrap_or_default();
        let calibration_object = calibration.as_object().ok_or_else(|| {
            DirectRunErrorV1::Parameters(
                "--calibration-noise JSON must contain a calibration object".to_owned(),
            )
        })?;
        merged.extend(calibration_object.clone());
        portable.insert("calibration".to_owned(), Value::Object(merged));
    } else {
        portable.insert("calibration".to_owned(), calibration);
    }
    Ok(())
}

fn parameter_map_from_json_v1(
    document: &Value,
) -> Result<BTreeMap<String, ResolvedDefaultV1>, DirectRunErrorV1> {
    let object = document.as_object().ok_or_else(|| {
        DirectRunErrorV1::Json("canonical config must be a JSON object".to_owned())
    })?;
    let mut values = BTreeMap::new();
    if let Some(materialized) = object.get("materialized").and_then(Value::as_object) {
        for key in ["parameters", "options"] {
            if let Some(map) = materialized.get(key).and_then(Value::as_object) {
                values.extend(parse_parameter_object_v1(map)?);
            }
        }
    }
    for key in ["parameters", "params", "options"] {
        if let Some(map) = object.get(key).and_then(Value::as_object) {
            values.extend(parse_parameter_object_v1(map)?);
        }
    }
    if values.is_empty() {
        values.extend(parse_parameter_object_v1(object)?);
    }
    Ok(values)
}

fn parse_parameter_object_v1(
    object: &Map<String, Value>,
) -> Result<BTreeMap<String, ResolvedDefaultV1>, DirectRunErrorV1> {
    object
        .iter()
        .map(|(key, value)| {
            Ok((
                key.clone(),
                resolved_from_json_v1(value)
                    .map_err(|message| DirectRunErrorV1::Parameters(format!("{key}: {message}")))?,
            ))
        })
        .collect()
}

fn resolved_from_json_v1(value: &Value) -> Result<ResolvedDefaultV1, String> {
    if let Some(object) = value.as_object() {
        if let Some(special) = object.get("$special_float").and_then(Value::as_str) {
            return Err(format!("special float {special} is not admitted"));
        }
        if let Some(scalar) = object.get("scalar") {
            return resolved_from_json_v1(scalar);
        }
        if let Some(vector) = object.get("vector") {
            return resolved_from_json_v1(vector);
        }
        return Err("object values are not canonical scalar/vector values".to_owned());
    }
    if let Some(number) = value.as_f64() {
        return number
            .is_finite()
            .then_some(ResolvedDefaultV1::Scalar(number))
            .ok_or_else(|| "number must be finite".to_owned());
    }
    if let Some(boolean) = value.as_bool() {
        return Ok(ResolvedDefaultV1::Boolean(boolean));
    }
    if let Some(string) = value.as_str() {
        return Ok(ResolvedDefaultV1::String(string.to_owned()));
    }
    if let Some(array) = value.as_array() {
        if array.is_empty() {
            return Ok(ResolvedDefaultV1::Empty);
        }
        if array.iter().all(Value::is_number) {
            return array
                .iter()
                .map(|value| {
                    value
                        .as_f64()
                        .filter(|value| value.is_finite())
                        .ok_or_else(|| "array contains a non-finite number".to_owned())
                })
                .collect::<Result<Vec<_>, _>>()
                .map(ResolvedDefaultV1::Vector);
        }
        if array.iter().all(Value::is_array) {
            let rows = array
                .iter()
                .map(|row| {
                    row.as_array()
                        .ok_or_else(|| "matrix row must be an array".to_owned())?
                        .iter()
                        .map(|value| {
                            value
                                .as_f64()
                                .filter(|value| value.is_finite())
                                .ok_or_else(|| "matrix contains a non-finite number".to_owned())
                        })
                        .collect::<Result<Vec<_>, _>>()
                })
                .collect::<Result<Vec<_>, _>>()?;
            let width = rows.first().map_or(0, Vec::len);
            if rows.iter().any(|row| row.len() != width) {
                return Err("matrix must be rectangular".to_owned());
            }
            return Ok(ResolvedDefaultV1::Matrix(rows));
        }
    }
    Err("value must be a finite number, bool, string, or numeric array".to_owned())
}

fn canonical_controls_v1(
    source: &BTreeMap<String, ResolvedDefaultV1>,
) -> Result<BTreeMap<String, ResolvedDefaultV1>, DirectRunErrorV1> {
    let aliases: &[(&str, &[&str])] = &[
        (
            "samples_per_ui",
            &["samples_per_ui", "SAMP_PER_UI", "N_v", "M"],
        ),
        ("LEVELS", &["LEVELS", "PAM_LEVELS", "levels", "L"]),
        ("bin_size", &["bin_size", "BIN_SIZE", "force_pdf_bin_size"]),
        ("A_v", &["A_v", "AVAILABLE_SIGNAL", "a_thru"]),
        ("R_LM", &["R_LM", "R_LM_OHM"]),
        ("SNR_TX", &["SNR_TX", "TX_SNR_DB", "SNDR"]),
        ("sigma_X", &["sigma_X", "SIGMA_X", "sigma_r"]),
        ("sigma_RJ", &["sigma_RJ", "SIGMA_RJ"]),
        ("h_J", &["h_J", "JITTER_RESPONSE"]),
        ("sigma_N", &["sigma_N", "SIGMA_N"]),
        ("A_DD", &["A_DD", "AMPLITUDE_DD"]),
        ("spec_ber", &["spec_ber", "SPEC_BER", "specBER", "DER_0"]),
    ];
    let mut result = BTreeMap::new();
    for (canonical, names) in aliases {
        let Some(value) = names.iter().find_map(|name| source.get(*name).cloned()) else {
            return Err(DirectRunErrorV1::Unsupported(format!(
                "config does not expose direct COM control {canonical}; supply a canonical JSON parameter document"
            )));
        };
        result.insert((*canonical).to_owned(), value);
    }

    // Preserve the optional controls already understood by the Rust COM
    // resolver.  The required surface above keeps the direct leaf honest,
    // while carrying these values through lets callers exercise the fixed
    // DFE/C2M/noise branches instead of silently replacing them with the
    // resolver defaults.
    let optional_aliases: &[(&str, &[&str])] = &[
        (
            "dfe_first_max",
            &["dfe_first_max", "DFE_FIRST_MAX", "dfe_first_maximum"],
        ),
        ("cdr", &["cdr", "CDR"]),
        ("peak_start", &["peak_start", "PEAK_START"]),
        ("peak_stop", &["peak_stop", "PEAK_STOP"]),
        ("dfe_max", &["dfe_max", "DFE_MAX"]),
        ("dfe_min", &["dfe_min", "DFE_MIN"]),
        ("dfe_tap_count", &["dfe_tap_count", "DFE_TAP_COUNT"]),
        ("dfe_step", &["dfe_step", "DFE_STEP"]),
        ("floating_dfe", &["floating_dfe", "FLOATING_DFE"]),
        (
            "noise_crest_factor",
            &[
                "noise_crest_factor",
                "NOISE_CREST_FACTOR",
                "Noise_Crest_Factor",
            ],
        ),
        ("sigma_ne", &["sigma_ne", "SIGMA_NE"]),
        (
            "pass_threshold_db",
            &["pass_threshold_db", "PASS_THRESHOLD", "pass_threshold"],
        ),
        ("t_o_s", &["t_o_s", "T_O_S"]),
    ];
    for (canonical, names) in optional_aliases {
        if let Some(value) = names.iter().find_map(|name| source.get(*name).cloned()) {
            result.insert((*canonical).to_owned(), value);
        }
    }
    Ok(result)
}

fn required_usize_from_controls_v1(
    controls: &BTreeMap<String, ResolvedDefaultV1>,
    key: &str,
) -> Result<usize, DirectRunErrorV1> {
    let value = controls.get(key).ok_or_else(|| {
        DirectRunErrorV1::Parameters(format!("control {key} is required for pulse formation"))
    })?;
    let scalar = match value {
        ResolvedDefaultV1::Scalar(value) => *value,
        ResolvedDefaultV1::Vector(values) if values.len() == 1 => values[0],
        _ => {
            return Err(DirectRunErrorV1::Parameters(format!(
                "control {key} must be a scalar"
            )));
        }
    };
    if !scalar.is_finite() || scalar < 1.0 || scalar.fract() != 0.0 {
        return Err(DirectRunErrorV1::Parameters(format!(
            "control {key} must be a positive integer"
        )));
    }
    usize::try_from(scalar as u64)
        .map_err(|_| DirectRunErrorV1::Parameters(format!("control {key} is too large")))
}

/// Search leaves expose sampled SBR/FFE waveforms, which can be shorter than
/// the full COM time-domain channel.  Keep the selected values as the actual
/// channel response while placing them in a bounded full-length buffer so the
/// shared cursor/PDF chain can still evaluate the required precursor/tail.
fn materialize_selected_pulse_v1(source: &[f64], selected: &[f64]) -> Vec<f64> {
    if selected.len() >= source.len() {
        return selected.to_vec();
    }
    let mut result = vec![0.0; source.len()];
    let offset = source.len().saturating_sub(selected.len()) / 2;
    let end = offset.saturating_add(selected.len()).min(result.len());
    result[offset..end].copy_from_slice(&selected[..end - offset]);
    result
}

fn portable_branch_result_v1(
    document: &Value,
    impulse: &ImpulseInputV1,
    request: Option<&DirectRunRequestV1>,
    controls: Option<&BTreeMap<String, ResolvedDefaultV1>>,
) -> Result<PortableBranchResultV1, DirectRunErrorV1> {
    portable_branch_result_with_sigma_v1(document, impulse, request, controls, None)
}

fn portable_branch_result_with_sigma_v1(
    document: &Value,
    impulse: &ImpulseInputV1,
    request: Option<&DirectRunRequestV1>,
    controls: Option<&BTreeMap<String, ResolvedDefaultV1>>,
    calibration_sigma_ne_override: Option<f64>,
) -> Result<PortableBranchResultV1, DirectRunErrorV1> {
    let document_object = document.as_object().ok_or_else(|| {
        DirectRunErrorV1::Json("canonical config object must be an object".to_owned())
    })?;
    let root = document
        .get("portable")
        .and_then(Value::as_object)
        .unwrap_or(document_object);
    if document
        .get("portable")
        .and_then(Value::as_object)
        .is_some()
        && (document_object.contains_key("erl_only") || document_object.contains_key("erl"))
    {
        return Err(DirectRunErrorV1::Unsupported(
            "ERL-only controls cannot be split between portable and root config".to_owned(),
        ));
    }
    if root.contains_key("erl_only") && root.contains_key("erl") {
        return Err(DirectRunErrorV1::Unsupported(
            "erl_only and erl aliases cannot both be present".to_owned(),
        ));
    }
    for unsupported in ["matlab_only_reporting", "wiener_hopf"] {
        if root.contains_key(unsupported) {
            return Err(DirectRunErrorV1::Unsupported(format!(
                "portable.{unsupported} is not admitted: the pinned r4.80 source has no portable implementation"
            )));
        }
    }
    let mut diagnostics = Map::new();
    let mut effective_values = None;
    let mut effective_pulse = None;
    let mut effective_source_kind = None;
    let mut selected_fom_db = None;
    let mut calibration_sigma_bn_v = None;
    let mut calibration_sigma_ne_v = None;
    let mut calibration_sigma_hp_v = None;
    let mut erl_only_metrics = None;
    let mut effective_fext = Vec::new();
    let mut effective_next = Vec::new();
    let mut effective_fext_pulses = Vec::new();
    let mut effective_next_pulses = Vec::new();
    if root.contains_key("workbook") {
        diagnostics.insert(
            "workbook".to_owned(),
            json!({
                "status": "portable_reused",
                "policy": sipi_com::WORKBOOK_IMPORT_POLICY_V1,
                "source": "COM-01 config materializer"
            }),
        );
    }
    if root.contains_key("legacy_csv") {
        diagnostics.insert(
            "legacy_csv".to_owned(),
            json!({
                "status": "portable_reused",
                "policy": sipi_com::CSV_READER_POLICY_V1,
                "source": "COM-01 config CSV ingestion"
            }),
        );
    }
    if root.contains_key("plotting") {
        diagnostics.insert(
            "plotting".to_owned(),
            json!({
                "status": "external_blocked",
                "reason": "non-core report rendering format"
            }),
        );
    }
    if let Some(equalization) = root.get("equalization").and_then(Value::as_object) {
        let channel_types = equalization
            .get("channel_types")
            .and_then(Value::as_array)
            .map(|values| {
                values
                    .iter()
                    .map(|value| {
                        value.as_str().map(str::to_owned).ok_or_else(|| {
                            DirectRunErrorV1::Parameters(
                                "equalization.channel_types must contain strings".to_owned(),
                            )
                        })
                    })
                    .collect::<Result<Vec<_>, _>>()
            })
            .transpose()?
            .unwrap_or_else(|| vec!["THRU".to_owned()]);
        let unequalized = if let Some(values) = equalization.get("impulses") {
            let rows = values.as_array().ok_or_else(|| {
                DirectRunErrorV1::Parameters(
                    "equalization.impulses must be an array of numeric arrays".to_owned(),
                )
            })?;
            rows.iter()
                .enumerate()
                .map(|(row, value)| {
                    parse_f64_array_v1(value, &format!("equalization.impulses[{row}]"))
                })
                .collect::<Result<Vec<_>, _>>()?
        } else {
            vec![impulse.values.clone()]
        };
        if unequalized.len() != channel_types.len() {
            return Err(DirectRunErrorV1::Parameters(
                "equalization impulses and channel_types must be aligned".to_owned(),
            ));
        }
        let rx_ffe_taps = equalization
            .get("rx_ffe_taps")
            .map(|value| parse_f64_array_v1(value, "equalization.rx_ffe_taps"))
            .transpose()?;
        let rx_ffe_precursor_count = equalization
            .get("rx_ffe_precursor_count")
            .map(|_| required_usize_v1(equalization, "rx_ffe_precursor_count", "equalization"))
            .transpose()?;
        let equalized = apply_r480_equalization_v1(
            &unequalized,
            &channel_types,
            required_f64_v1(equalization, "baud_hz", "equalization")?,
            required_usize_v1(equalization, "samples_per_ui", "equalization")?,
            required_str_v1(equalization, "ctle_type", "equalization")?,
            required_f64_v1(equalization, "ctle_fz_hz", "equalization")?,
            required_f64_v1(equalization, "ctle_fp1_hz", "equalization")?,
            required_f64_v1(equalization, "ctle_fp2_hz", "equalization")?,
            required_f64_v1(equalization, "ctle_gain_db", "equalization")?,
            &parse_f64_array_key_v1(equalization, "tx_ffe_taps", "equalization")?,
            required_usize_v1(equalization, "tx_precursor_count", "equalization")?,
            optional_f64_v1(equalization, "high_pass_hz")?,
            optional_f64_v1(equalization, "high_pass_gain_db")?,
            optional_f64_v1(equalization, "high_pass_zero_hz")?,
            optional_f64_v1(equalization, "high_pass_pole_hz")?,
            rx_ffe_taps.as_deref(),
            rx_ffe_precursor_count,
        )
        .map_err(|error| DirectRunErrorV1::Unsupported(format!("equalization: {error:?}")))?;
        for ((channel_type, impulse_response), pulse_response) in channel_types
            .iter()
            .zip(equalized.impulse_responses())
            .zip(equalized.pulse_responses())
        {
            match channel_type.to_ascii_uppercase().as_str() {
                "THRU" if effective_values.is_none() => {
                    effective_values = Some(impulse_response.clone());
                    effective_pulse = Some(pulse_response.clone());
                    effective_source_kind = Some("equalized-channel-impulse");
                }
                "FEXT" => {
                    effective_fext.push(impulse_response.clone());
                    effective_fext_pulses.push(pulse_response.clone());
                }
                "NEXT" => {
                    effective_next.push(impulse_response.clone());
                    effective_next_pulses.push(pulse_response.clone());
                }
                _ => {}
            }
        }
        if effective_values.is_none() {
            return Err(DirectRunErrorV1::Unsupported(
                "equalization must provide one THRU channel".to_owned(),
            ));
        }
        diagnostics.insert(
            "equalization".to_owned(),
            json!({
                "schema": "sipi.com.equalization.apply-r480.v1",
                "policy": sipi_com::EQUALIZATION_APPLY_POLICY_V1,
                "ctle_type": required_str_v1(equalization, "ctle_type", "equalization")?,
                "tx_ffe_tap_count": parse_f64_array_key_v1(equalization, "tx_ffe_taps", "equalization")?.len(),
                "rx_ffe": rx_ffe_taps.as_ref().map(|taps| json!({
                    "enabled": true,
                    "tap_count": taps.len(),
                    "precursor_count": rx_ffe_precursor_count,
                    "taps_sha256": sha256_f64_v1(taps),
                })).unwrap_or_else(|| json!({"enabled": false})),
                "channel_types": channel_types,
                "impulse_count": equalized.impulse_responses().len(),
                "pulse_count": equalized.pulse_responses().len(),
                "impulse_sha256": equalized.impulse_responses().iter().map(|values| sha256_f64_v1(values)).collect::<Vec<_>>(),
                "pulse_sha256": equalized.pulse_responses().iter().map(|values| sha256_f64_v1(values)).collect::<Vec<_>>(),
            }),
        );
    }
    if let Some(mixed_mode) = root.get("mixed_mode").and_then(Value::as_object) {
        let frequency_hz = parse_f64_array_key_v1(mixed_mode, "frequency_hz", "mixed_mode")?;
        let samples = parse_four_port_array_v1(mixed_mode, "s", "mixed_mode")?;
        let port_order = mixed_mode
            .get("port_order")
            .map(|value| parse_port_order_v1(value, "mixed_mode.port_order"))
            .transpose()?
            .unwrap_or([0, 1, 2, 3]);
        let samples = reorder_four_port_samples_v1(&samples, port_order);
        if frequency_hz.len() != samples.len() {
            return Err(DirectRunErrorV1::Parameters(
                "mixed_mode frequency_hz and s must have equal lengths".to_owned(),
            ));
        }
        let skewed = apply_r480_pn_skew_v1(
            &frequency_hz,
            &samples,
            mixed_mode
                .get("txp_ps")
                .and_then(Value::as_f64)
                .unwrap_or(0.0),
            mixed_mode
                .get("txn_ps")
                .and_then(Value::as_f64)
                .unwrap_or(0.0),
            mixed_mode
                .get("rxp_ps")
                .and_then(Value::as_f64)
                .unwrap_or(0.0),
            mixed_mode
                .get("rxn_ps")
                .and_then(Value::as_f64)
                .unwrap_or(0.0),
        )
        .map_err(|error| DirectRunErrorV1::Unsupported(format!("mixed_mode skew: {error:?}")))?;
        let mixed = com_mixed_mode_spectrum_v1(&skewed);
        let sdd21 = mixed.iter().map(|sample| sample[3][1]).collect::<Vec<_>>();
        let mut channelized_impulse = None;
        if mixed_mode
            .get("channelize")
            .and_then(Value::as_bool)
            .unwrap_or(false)
        {
            let mut options = FdToTdOptionsV1::default();
            let controls = mixed_mode.get("fd_to_td").unwrap_or(&Value::Null);
            if let Some(value) = controls.get("sample_dt_s").and_then(Value::as_f64) {
                options.sample_dt_s = value;
            }
            if let Some(value) = controls.get("magnitude_policy").and_then(Value::as_str) {
                options.magnitude_policy = value.to_owned();
            }
            if let Some(value) = controls.get("phase_policy").and_then(Value::as_str) {
                options.phase_policy = value.to_owned();
            }
            if let Some(value) = controls.get("enforce_causality").and_then(Value::as_bool) {
                options.enforce_causality = value;
            }
            if let Some(value) = controls.get("ec_pulse_tolerance").and_then(Value::as_f64) {
                options.ec_pulse_tolerance = value;
            }
            if let Some(value) = controls
                .get("ec_relative_tolerance")
                .and_then(Value::as_f64)
            {
                options.ec_relative_tolerance = value;
            }
            if let Some(value) = controls
                .get("ec_difference_tolerance")
                .and_then(Value::as_f64)
            {
                options.ec_difference_tolerance = value;
            }
            if let Some(value) = controls.get("truncation_threshold").and_then(Value::as_f64) {
                options.truncation_threshold = value;
            }
            if let Some(value) = controls.get("debug").and_then(Value::as_bool) {
                options.debug = value;
            }
            if let Some(value) = controls.get("max_iterations").and_then(Value::as_u64) {
                options.max_iterations = usize::try_from(value).map_err(|_| {
                    DirectRunErrorV1::Json(
                        "mixed_mode max_iterations does not fit the platform usize".to_owned(),
                    )
                })?;
            }
            let result =
                s21_to_impulse_dc_v1(&sdd21, &frequency_hz, &options).map_err(|error| {
                    DirectRunErrorV1::Unsupported(format!("mixed_mode fd-to-td: {error:?}"))
                })?;
            validate_impulse_v1(&result.voltage)?;
            channelized_impulse = Some(result.voltage);
            effective_source_kind = Some("mixed-mode-channel-impulse");
            effective_values = channelized_impulse.clone();
        }
        diagnostics.insert(
            "mixed_mode".to_owned(),
            json!({
                "schema": "sipi.com.network.mixed-mode.v1",
                "policy": sipi_com::NETWORK_INGEST_POLICY_V1,
                "port_order": port_order.iter().map(|port| port + 1).collect::<Vec<_>>(),
                "sample_count": sdd21.len(),
                "sdd21_sha256": sha256_complex_v1(&sdd21),
                "sdd21_first": sdd21.first().map(|value| [value.real(), value.imaginary()]),
                "sdd21_last": sdd21.last().map(|value| [value.real(), value.imaginary()]),
                "channelized": channelized_impulse.is_some(),
                "channel_impulse_sha256": channelized_impulse.as_ref().map(|values| sha256_f64_v1(values)),
            }),
        );
    }
    if let Some(calibration) = root
        .get("calibration")
        .or_else(|| root.get("calibration_noise"))
        .and_then(Value::as_object)
    {
        let frequency_hz = parse_f64_array_key_v1(calibration, "frequency_hz", "calibration")?;
        let calibration_sdd21 = if calibration.get("calibration_sdd21").is_some() {
            parse_complex_array_key_v1(calibration, "calibration_sdd21", "calibration")?
        } else if calibration.get("s4p").is_some() {
            // A calibration S4P supplied as already-parsed four-port samples
            // follows the same mixed-mode transform as the public network
            // route.  No fit or port-order guess is introduced here.
            let samples = parse_four_port_array_v1(calibration, "s4p", "calibration")?;
            let order = calibration
                .get("port_order")
                .map(|value| parse_port_order_v1(value, "calibration.port_order"))
                .transpose()?
                .unwrap_or([0, 1, 2, 3]);
            let samples = reorder_four_port_samples_v1(&samples, order);
            com_mixed_mode_spectrum_v1(&samples)
                .into_iter()
                .map(|sample| sample[3][1])
                .collect()
        } else {
            return Err(DirectRunErrorV1::Parameters(
                "calibration requires calibration_sdd21 or parsed four-port s4p samples".to_owned(),
            ));
        };
        let ctle_transfer =
            parse_complex_array_key_v1(calibration, "ctle_transfer", "calibration")?;
        let fb_hz = required_f64_v1(calibration, "fb_hz", "calibration")?;
        let f_r = required_f64_v1(calibration, "f_r", "calibration")?;
        let f_hp_hz = calibration
            .get("f_hp_hz")
            .and_then(Value::as_f64)
            .unwrap_or(0.0);
        let initial_sigma_bn_v = calibration
            .get("sigma_bn_v")
            .and_then(Value::as_f64)
            .unwrap_or(0.0);
        let initial_noise = calculate_r480_calibration_noise_v1(
            &frequency_hz,
            &calibration_sdd21,
            &ctle_transfer,
            fb_hz,
            f_r,
            f_hp_hz,
            initial_sigma_bn_v,
        )
        .map_err(|error| DirectRunErrorV1::Parameters(format!("calibration: {error:?}")))?;
        if calibration.get("evaluations").is_some() || calibration.get("case_com_db").is_some() {
            return Err(DirectRunErrorV1::Unsupported(
                "calibration precomputed evaluations/case_com_db are not admitted; provide parsed package_case channel state for dynamic COM evaluation"
                    .to_owned(),
            ));
        }
        // The source calibration loop evaluates the same package-case
        // orchestration as the final run.  Its pulse/FEXT/NEXT state must come
        // from the parsed package case, rather than a detached pulse table.
        let (case_identities, case_channels_source) = if let Some(package_case) =
            document.get("package_case").and_then(Value::as_object)
        {
            let identity = package_case
                .get("case_id")
                .and_then(Value::as_str)
                .unwrap_or("package-case")
                .to_owned();
            let pulse = parse_f64_array_v1(
                package_case.get("pulse").ok_or_else(|| {
                    DirectRunErrorV1::Parameters(
                        "package_case.pulse is required for calibration orchestration".to_owned(),
                    )
                })?,
                "package_case.pulse",
            )?;
            validate_impulse_v1(&pulse)?;
            let base = request
                .and_then(|request| request.config.parent())
                .unwrap_or_else(|| Path::new("."));
            let fext = parse_case_channels_v1(package_case.get("fext"), base, 0, "fext")?;
            let next = parse_case_channels_v1(package_case.get("next"), base, 0, "next")?;
            let pulse_already_pulse = package_case
                .get("pulse_already_pulse")
                .and_then(Value::as_bool)
                .unwrap_or(false);
            let fext_already_pulse = fext
                .iter()
                .map(|channel| channel.already_pulse)
                .collect::<Vec<_>>();
            let next_already_pulse = next
                .iter()
                .map(|channel| channel.already_pulse)
                .collect::<Vec<_>>();
            (
                vec![identity],
                vec![(
                    pulse,
                    fext.into_iter()
                        .map(|channel| channel.values)
                        .collect::<Vec<_>>(),
                    next.into_iter()
                        .map(|channel| channel.values)
                        .collect::<Vec<_>>(),
                    pulse_already_pulse,
                    fext_already_pulse,
                    next_already_pulse,
                )],
            )
        } else {
            return Err(DirectRunErrorV1::Parameters(
                "calibration requires parsed package_case channel state (pulse/fext/next)"
                    .to_owned(),
            ));
        };
        if case_channels_source.is_empty() {
            return Err(DirectRunErrorV1::Parameters(
                "calibration package-case channel state must not be empty".to_owned(),
            ));
        }
        let request = request.ok_or_else(|| {
            DirectRunErrorV1::Unsupported(
                "dynamic calibration requires the admitted COM request context".to_owned(),
            )
        })?;
        let controls = controls.ok_or_else(|| {
            DirectRunErrorV1::Unsupported(
                "dynamic calibration requires resolved COM controls".to_owned(),
            )
        })?;
        let calibration_samples_per_ui =
            required_usize_from_controls_v1(controls, "samples_per_ui")?;
        let request_bytes = admission_request_bytes_v1(request, controls)
            .map_err(|error| DirectRunErrorV1::Parameters(error.to_string()))?;
        let mut selected_case_orchestration = Vec::new();
        let mut per_sigma_search_orchestration = Vec::new();
        let evaluate = |sigma: f64| {
            let noise = calculate_r480_calibration_noise_v1(
                &frequency_hz,
                &calibration_sdd21,
                &ctle_transfer,
                fb_hz,
                f_r,
                f_hp_hz,
                sigma,
            )
            .map_err(|_| CalibrationErrorV1::Evaluator)?;
            let mut effective_controls = controls.clone();
            effective_controls.insert(
                "sigma_ne".to_owned(),
                ResolvedDefaultV1::Scalar(noise.sigma_ne_v),
            );
            let dto = merge_com_parameters_v1(
                &effective_controls.keys().cloned().collect::<Vec<_>>(),
                &effective_controls,
                &BTreeMap::new(),
                &[],
            )
            .map_err(|_| CalibrationErrorV1::Evaluator)?;
            selected_case_orchestration.clear();
            let mut case_com_db = Vec::with_capacity(case_channels_source.len());
            for (
                case_index,
                (
                    identity,
                    (
                        case_impulse,
                        case_fext,
                        case_next,
                        case_already_pulse,
                        fext_already_pulse,
                        next_already_pulse,
                    ),
                ),
            ) in case_identities
                .iter()
                .zip(case_channels_source.iter())
                .enumerate()
            {
                let mut orchestration_document = document.clone();
                if let Some(object) = orchestration_document.as_object_mut() {
                    object.remove("calibration");
                    object.remove("calibration_noise");
                }
                if let Some(portable) = orchestration_document
                    .get_mut("portable")
                    .and_then(Value::as_object_mut)
                {
                    portable.remove("calibration");
                    portable.remove("calibration_noise");
                }
                let case_input = ImpulseInputV1 {
                    values: case_impulse.clone(),
                    erl_values: None,
                    erl_time_s: None,
                    source_sha256: sha256_f64_v1(case_impulse),
                    sample_interval_s: None,
                    source_kind: "package-case-channel-state",
                    already_pulse: *case_already_pulse,
                    causality_correction_db: None,
                    truncation_db: None,
                    causality_iterations: None,
                };
                let orchestration = portable_branch_result_with_sigma_v1(
                    &orchestration_document,
                    &case_input,
                    None,
                    Some(controls),
                    Some(noise.sigma_ne_v),
                )
                .map_err(|_| CalibrationErrorV1::Evaluator)?;
                let source_values = orchestration
                    .effective_values
                    .clone()
                    .unwrap_or_else(|| case_input.values.clone());
                let source_pulse =
                    if case_input.already_pulse && orchestration.effective_values.is_none() {
                        source_values
                    } else {
                        rectangular_pulse_response_v1(&source_values, calibration_samples_per_ui)
                            .map_err(|_| CalibrationErrorV1::Evaluator)?
                    };
                let chain_pulse = orchestration
                    .effective_pulse
                    .clone()
                    .map_or_else(
                        || Ok::<Vec<f64>, CalibrationErrorV1>(source_pulse.clone()),
                        |selected| {
                            Ok::<Vec<f64>, CalibrationErrorV1>(materialize_selected_pulse_v1(
                                &source_pulse,
                                &selected,
                            ))
                        },
                    )
                    .map_err(|_| CalibrationErrorV1::Evaluator)?;
                let mut fext_pulses = case_fext
                    .iter()
                    .enumerate()
                    .map(|(index, values)| {
                        if fext_already_pulse.get(index).copied().unwrap_or(false) {
                            Ok(values.clone())
                        } else {
                            rectangular_pulse_response_v1(values, calibration_samples_per_ui)
                        }
                    })
                    .collect::<Result<Vec<_>, _>>()
                    .map_err(|_| CalibrationErrorV1::Evaluator)?;
                fext_pulses.extend(orchestration.effective_fext_pulses.clone());
                let mut next_pulses = case_next
                    .iter()
                    .enumerate()
                    .map(|(index, values)| {
                        if next_already_pulse.get(index).copied().unwrap_or(false) {
                            Ok(values.clone())
                        } else {
                            rectangular_pulse_response_v1(values, calibration_samples_per_ui)
                        }
                    })
                    .collect::<Result<Vec<_>, _>>()
                    .map_err(|_| CalibrationErrorV1::Evaluator)?;
                next_pulses.extend(orchestration.effective_next_pulses.clone());
                let fext_values = fext_pulses.iter().map(Vec::as_slice).collect::<Vec<_>>();
                let next_values = next_pulses.iter().map(Vec::as_slice).collect::<Vec<_>>();
                let envelope = if fext_values.is_empty() && next_values.is_empty() {
                    execute_com_run_v1(&request_bytes, &chain_pulse, &dto)
                } else {
                    execute_com_run_with_crosstalk_v1(
                        &request_bytes,
                        &chain_pulse,
                        &fext_values,
                        &next_values,
                        &dto,
                    )
                }
                .map_err(|_| CalibrationErrorV1::Evaluator)?;
                let com_db = envelope.com_db().ok_or(CalibrationErrorV1::Evaluator)?;
                case_com_db.push(com_db);
                selected_case_orchestration.push(json!({
                    "case_index": case_index,
                    "case_id": identity,
                    "channel_impulse_sha256": sha256_f64_v1(case_impulse),
                    "search_input_sha256": orchestration.diagnostics
                        .get("search")
                        .and_then(|value| value.get("search_input_sha256")),
                    "search_fom_db": orchestration
                        .diagnostics
                        .get("search")
                        .and_then(|value| value.get("fom_db")),
                    "selected_pulse_sha256": sha256_f64_v1(&chain_pulse),
                    "fext_pulse_sha256": fext_pulses.iter().map(|values| sha256_f64_v1(values)).collect::<Vec<_>>(),
                    "next_pulse_sha256": next_pulses.iter().map(|values| sha256_f64_v1(values)).collect::<Vec<_>>(),
                    "com_db": com_db,
                }));
            }
            per_sigma_search_orchestration.push(json!({
                "sigma_bn_v": sigma,
                "sigma_ne_v": noise.sigma_ne_v,
                "cases": selected_case_orchestration.clone(),
            }));
            Ok(case_com_db)
        };
        let calibration_result = calibrate_receiver_noise_v1(
            evaluate,
            required_f64_v1(calibration, "pass_threshold_db", "calibration")?,
            required_f64_v1(calibration, "initial_step_v", "calibration")?,
        )
        .map_err(|error| DirectRunErrorV1::Parameters(format!("calibration: {error:?}")))?;
        let selected_noise = calculate_r480_calibration_noise_v1(
            &frequency_hz,
            &calibration_sdd21,
            &ctle_transfer,
            fb_hz,
            f_r,
            f_hp_hz,
            calibration_result.sigma_bn_v,
        )
        .map_err(|error| DirectRunErrorV1::Parameters(format!("calibration: {error:?}")))?;
        calibration_sigma_bn_v = Some(calibration_result.sigma_bn_v);
        calibration_sigma_ne_v = Some(selected_noise.sigma_ne_v);
        calibration_sigma_hp_v = Some(selected_noise.sigma_hp_v);
        diagnostics.insert(
            "calibration".to_owned(),
            json!({
                "schema": "sipi.com.calibration.r480.v1",
                "policy": sipi_com::CALIBRATION_POLICY_V1,
                "frequency_sample_count": frequency_hz.len(),
                "calibration_s4p": calibration.get("s4p").is_some(),
                "evaluator": "evaluate_cases(sigma_bn_v)-fresh-reference-COM",
                "evaluate_cases": "reruns every package case through COM for each sigma",
                "case_channel_source": "parsed-package-case-channel-state",
                "selected_case_orchestration": selected_case_orchestration,
                "per_sigma_search_orchestration": per_sigma_search_orchestration,
                "channel_source": if calibration.get("s4p").is_some() { "calibration.s4p" } else { "calibration_sdd21" },
                "initial_noise": {
                    "sigma_bn_v": initial_sigma_bn_v,
                    "sigma_ne_v": initial_noise.sigma_ne_v,
                    "sigma_hp_v": initial_noise.sigma_hp_v
                },
                "selected_noise": {
                    "sigma_bn_v": calibration_result.sigma_bn_v,
                    "sigma_ne_v": selected_noise.sigma_ne_v,
                    "sigma_hp_v": selected_noise.sigma_hp_v
                },
                "final_step_v": calibration_result.final_step_v,
                "minimum_com_db": calibration_result.iterations.last().map(|item| item.minimum_com_db),
                "iterations": calibration_result.iterations.iter().map(|item| json!({
                    "sigma_bn_v": item.sigma_bn_v,
                    "step_v": item.step_v,
                    "case_com_db": item.case_com_db,
                    "minimum_com_db": item.minimum_com_db
                })).collect::<Vec<_>>()
            }),
        );
    }
    if let Some(mmse) = root
        .get("mmse")
        .or_else(|| root.get("mmse_search"))
        .and_then(Value::as_object)
    {
        let candidate_values = mmse
            .get("candidates")
            .and_then(Value::as_array)
            .ok_or_else(|| {
                DirectRunErrorV1::Parameters("mmse.candidates must be an array".to_owned())
            })?;
        let mut candidates = Vec::with_capacity(candidate_values.len());
        for (index, value) in candidate_values.iter().enumerate() {
            let candidate = value.as_object().ok_or_else(|| {
                DirectRunErrorV1::Parameters(format!("mmse.candidates[{index}] must be an object"))
            })?;
            candidates.push(MmseCandidateSpecV1 {
                h_matrix: parse_f64_matrix_key_v1(candidate, "h_matrix", "mmse.candidate")?,
                noise_correlation: parse_f64_matrix_key_v1(
                    candidate,
                    "noise_correlation",
                    "mmse.candidate",
                )?,
                decision_index: required_usize_v1(candidate, "decision_index", "mmse.candidate")?,
                dfe_tap_count: required_usize_v1(candidate, "dfe_tap_count", "mmse.candidate")?,
                sigma_x2: required_f64_v1(candidate, "sigma_x2", "mmse.candidate")?,
                levels: u32::try_from(required_usize_v1(candidate, "levels", "mmse.candidate")?)
                    .map_err(|_| {
                        DirectRunErrorV1::Parameters(
                            "mmse.candidate.levels is too large for the portable solver".to_owned(),
                        )
                    })?,
                r_lm: required_f64_v1(candidate, "r_lm", "mmse.candidate")?,
                rx_min: parse_f64_array_key_v1(candidate, "rx_min", "mmse.candidate")?,
                rx_max: parse_f64_array_key_v1(candidate, "rx_max", "mmse.candidate")?,
                dfe_min: parse_f64_array_key_v1(candidate, "dfe_min", "mmse.candidate")?,
                dfe_max: parse_f64_array_key_v1(candidate, "dfe_max", "mmse.candidate")?,
                rx_cursor_offset: candidate
                    .get("rx_cursor_offset")
                    .map(|_| required_usize_v1(candidate, "rx_cursor_offset", "mmse.candidate"))
                    .transpose()?
                    .unwrap_or(0),
                ctle_index: candidate
                    .get("ctle_index")
                    .and_then(Value::as_i64)
                    .unwrap_or(0),
                high_pass_index: candidate
                    .get("high_pass_index")
                    .and_then(Value::as_i64)
                    .unwrap_or(0),
                pre_rx_sbr: candidate
                    .get("pre_rx_sbr")
                    .map(|value| parse_f64_array_v1(value, "mmse.candidate.pre_rx_sbr"))
                    .transpose()?
                    .unwrap_or_default(),
                equalized_sbr: candidate
                    .get("equalized_sbr")
                    .map(|value| parse_f64_array_v1(value, "mmse.candidate.equalized_sbr"))
                    .transpose()?
                    .unwrap_or_default(),
            });
        }
        let result = search_mmse_candidates_v1(&candidates)
            .map_err(|error| DirectRunErrorV1::Unsupported(format!("mmse: {error:?}")))?;
        let selected_candidate = &candidates[result.candidate_index];
        let kkt_normalization = selected_candidate
            .h_matrix
            .get(selected_candidate.decision_index)
            .map(|row| {
                row.iter()
                    .zip(result.result.rx_ffe.iter())
                    .map(|(left, right)| left * right)
                    .sum::<f64>()
            })
            .unwrap_or(f64::NAN);
        selected_fom_db = Some(result.result.fom_db);
        if !result.result.equalized_sbr.is_empty() {
            effective_pulse = Some(result.result.equalized_sbr.clone());
        }
        diagnostics.insert(
            "mmse".to_owned(),
            json!({
                "schema": "sipi.com.equalization.mmse-r480.v1",
                "policy": sipi_com::MMSE_POLICY_V1,
                "candidate_index": result.candidate_index,
                "ctle_index": result.ctle_index,
                "high_pass_index": result.high_pass_index,
                "fom_db": result.result.fom_db,
                "sigma_e": result.result.sigma_e,
                "condition_number": result.result.condition_number,
                "kkt_normalization": kkt_normalization,
                "sbr_kkt_consistent": kkt_normalization.is_finite()
                    && (kkt_normalization - 1.0).abs() <= 1.0e-6,
                "rx_ffe": result.result.rx_ffe,
                "dfe": result.result.dfe,
                "dfe_limited": result.result.dfe_limited,
                "pre_rx_sbr": result.result.pre_rx_sbr,
                "equalized_sbr": result.result.equalized_sbr
            }),
        );
    }
    if let Some(rxffe) = root
        .get("rx_ffe_search")
        .or_else(|| root.get("fvlms_rxffe"))
        .and_then(Value::as_object)
    {
        let candidate_values = rxffe
            .get("candidates")
            .and_then(Value::as_array)
            .ok_or_else(|| {
                DirectRunErrorV1::Parameters("rx_ffe_search.candidates must be an array".to_owned())
            })?;
        let mut candidates = Vec::with_capacity(candidate_values.len());
        for (index, value) in candidate_values.iter().enumerate() {
            let candidate = value.as_object().ok_or_else(|| {
                DirectRunErrorV1::Parameters(format!(
                    "rx_ffe_search.candidates[{index}] must be an object"
                ))
            })?;
            let waveform =
                parse_f64_array_key_v1(candidate, "waveform", "rx_ffe_search.candidate")?;
            if waveform.len() > sipi_com::MAX_RXFFE_SEARCH_WAVEFORM_SAMPLES_V1 {
                return Err(DirectRunErrorV1::InputLimit {
                    path: format!("rx_ffe_search.candidates[{index}].waveform"),
                    limit: sipi_com::MAX_RXFFE_SEARCH_WAVEFORM_SAMPLES_V1 as u64,
                });
            }
            let evaluation = candidate
                .get("evaluation")
                .map(|value| parse_rxffe_evaluation_v1(value, index))
                .transpose()?;
            if evaluation
                .as_ref()
                .is_some_and(|value| value.parameters.floating_dfe)
            {
                return Err(DirectRunErrorV1::Unsupported(
                    "Floating_DFE with RxFFE is not an admitted portable combination".to_owned(),
                ));
            }
            candidates.push(RxFfeSearchCandidateV1 {
                waveform,
                cursor_index: required_usize_v1(
                    candidate,
                    "cursor_index",
                    "rx_ffe_search.candidate",
                )?,
                precursor_count: required_usize_v1(
                    candidate,
                    "precursor_count",
                    "rx_ffe_search.candidate",
                )?,
                postcursor_count: required_usize_v1(
                    candidate,
                    "postcursor_count",
                    "rx_ffe_search.candidate",
                )?,
                samples_per_ui: required_usize_v1(
                    candidate,
                    "samples_per_ui",
                    "rx_ffe_search.candidate",
                )?,
                dfe_first_max: candidate
                    .get("dfe_first_max")
                    .and_then(Value::as_f64)
                    .unwrap_or(0.0),
                unity_cursor: candidate
                    .get("unity_cursor")
                    .and_then(Value::as_bool)
                    .unwrap_or(false),
                tap_step: candidate
                    .get("tap_step")
                    .and_then(Value::as_f64)
                    .unwrap_or(0.0),
                floating: candidate
                    .get("floating")
                    .and_then(Value::as_bool)
                    .unwrap_or(false),
                maximum_postcursor_count: candidate
                    .get("maximum_postcursor_count")
                    .map(|_| {
                        required_usize_v1(
                            candidate,
                            "maximum_postcursor_count",
                            "rx_ffe_search.candidate",
                        )
                    })
                    .transpose()?
                    .unwrap_or(0),
                floating_start: candidate
                    .get("floating_start")
                    .map(|_| {
                        required_usize_v1(candidate, "floating_start", "rx_ffe_search.candidate")
                    })
                    .transpose()?
                    .unwrap_or(1),
                taps_per_bank: candidate
                    .get("taps_per_bank")
                    .map(|_| {
                        required_usize_v1(candidate, "taps_per_bank", "rx_ffe_search.candidate")
                    })
                    .transpose()?
                    .unwrap_or(1),
                bank_count: candidate
                    .get("bank_count")
                    .map(|_| required_usize_v1(candidate, "bank_count", "rx_ffe_search.candidate"))
                    .transpose()?
                    .unwrap_or(1),
                coefficient_limit: candidate
                    .get("coefficient_limit")
                    .and_then(Value::as_f64)
                    .unwrap_or(0.0),
                selection: candidate
                    .get("selection")
                    .and_then(Value::as_str)
                    .unwrap_or("taps")
                    .to_owned(),
                rx_ffe_gain_db: candidate
                    .get("rx_ffe_gain_db")
                    .and_then(Value::as_f64)
                    .unwrap_or(0.0),
                ctle_index: candidate
                    .get("ctle_index")
                    .and_then(Value::as_i64)
                    .unwrap_or(0),
                ctle_gain_db: candidate
                    .get("ctle_gain_db")
                    .and_then(Value::as_f64)
                    .unwrap_or(0.0),
                high_pass_index: candidate
                    .get("high_pass_index")
                    .and_then(Value::as_i64)
                    .unwrap_or(0),
                high_pass_gain_db: candidate
                    .get("high_pass_gain_db")
                    .and_then(Value::as_f64)
                    .unwrap_or(0.0),
                evaluation,
            });
        }
        let result = search_fvlms_rxffe_candidates_v1(&candidates)
            .map_err(|error| DirectRunErrorV1::Unsupported(format!("rx_ffe_search: {error:?}")))?;
        selected_fom_db = Some(result.fom_db);
        if !result.filtered.is_empty() {
            effective_pulse = Some(result.filtered.clone());
        }
        diagnostics.insert(
            "rx_ffe_search".to_owned(),
            json!({
                "schema": "sipi.com.equalization.fvlms-rxffe-r480.v1",
                "policy": sipi_com::RXFFE_SEARCH_POLICY_V1,
                "candidate_index": result.candidate_index,
                "ctle_index": result.ctle_index,
                "ctle_gain_db": result.ctle_gain_db,
                "high_pass_index": result.high_pass_index,
                "high_pass_gain_db": result.high_pass_gain_db,
                "rx_ffe_gain_db": result.rx_ffe_gain_db,
                "fom_db": result.fom_db,
                "cursor_v": result.cursor_v,
                "residual_rms_v": result.residual_rms_v,
                "full_fom_evaluation": result.full_fom_evaluation,
                "available_signal_v": result.available_signal_v,
                "sigma_n_v": result.sigma_n_v,
                "sigma_ne_v": result.sigma_ne_v,
                "sigma_xt_v": result.sigma_xt_v,
                "sigma_isi_v": result.sigma_isi_v,
                "sigma_j_v": result.sigma_j_v,
                "sigma_tx_v": result.sigma_tx_v,
                "sigma_total_v": result.sigma_total_v,
                "dfe_taps": result.dfe_taps,
                "dfe_max": result.dfe_max,
                "dfe_min": result.dfe_min,
                "h_j": result.h_j,
                "tx_taps": result.tx_taps,
                "tx_precursor_count": result.tx_precursor_count,
                "tx_grid_index": result.tx_grid_index,
                "tx_source_indices": result.tx_source_indices,
                "itick": result.itick,
                "taps": result.taps,
                "floating_locations": result.floating_locations,
                "filtered_waveform": result.filtered,
                "filtered_waveform_sha256": sha256_f64_v1(&result.filtered)
            }),
        );
    }
    if let Some(tdiln) = root.get("tdiln").and_then(Value::as_object) {
        let frequency_hz = parse_f64_array_key_v1(tdiln, "frequency_hz", "tdiln")?;
        let sdd21 = parse_complex_array_key_v1(tdiln, "sdd21", "tdiln")?;
        if frequency_hz.len() != sdd21.len() {
            return Err(DirectRunErrorV1::Parameters(
                "tdiln frequency_hz and sdd21 must have equal lengths".to_owned(),
            ));
        }
        let result = r480_tdiln_v1(
            &sdd21,
            &frequency_hz,
            required_f64_v1(tdiln, "f1_hz", "tdiln")?,
            required_f64_v1(tdiln, "f2_hz", "tdiln")?,
            required_f64_v1(tdiln, "baud_hz", "tdiln")?,
            required_usize_v1(tdiln, "samples_per_ui", "tdiln")?,
            required_f64_v1(tdiln, "sample_dt_s", "tdiln")?,
            u32::try_from(required_usize_v1(tdiln, "levels", "tdiln")?).map_err(|_| {
                DirectRunErrorV1::Parameters(
                    "tdiln.levels is too large for the portable solver".to_owned(),
                )
            })?,
            required_f64_v1(tdiln, "spec_ber", "tdiln")?,
            required_f64_v1(tdiln, "bin_size", "tdiln")?,
            required_usize_v1(tdiln, "bessel_order", "tdiln")?,
            required_f64_v1(tdiln, "bessel_cutoff_multiplier", "tdiln")?,
            required_f64_v1(tdiln, "transmitter_transition_time_ns", "tdiln")?,
            tdiln
                .get("enforce_causality")
                .and_then(Value::as_bool)
                .unwrap_or(false),
            tdiln
                .get("ec_pulse_tolerance")
                .and_then(Value::as_f64)
                .unwrap_or(0.05),
            tdiln
                .get("ec_relative_tolerance")
                .and_then(Value::as_f64)
                .unwrap_or(0.006),
            tdiln
                .get("ec_difference_tolerance")
                .and_then(Value::as_f64)
                .unwrap_or(1.0e-4),
        )
        .map_err(|error| DirectRunErrorV1::Unsupported(format!("tdiln: {error:?}")))?;
        diagnostics.insert(
            "tdiln".to_owned(),
            json!({
                "schema": "sipi.com.metrics.tdiln.v1",
                "policy": sipi_com::TDILN_POLICY_V1,
                "fit_sha256": sha256_complex_v1(&result.fit),
                "iln_db_sha256": sha256_f64_v1(&result.iln_db),
                "reference_pulse_sha256": sha256_f64_v1(&result.reference_pulse),
                "fitted_pulse_sha256": sha256_f64_v1(&result.fitted_pulse),
                "iln_pulse_sha256": sha256_f64_v1(&result.iln_pulse),
                "selected_phase": result.selected_phase,
                "fom_v": result.fom_v,
                "fom_pdf_v": result.fom_pdf_v,
                "snr_isi_fom_db": result.snr_isi_fom_db,
                "snr_isi_fom_pdf_db": result.snr_isi_fom_pdf_db,
                "pdf": {
                    "bin_size": result.pdf.bin_size(),
                    "min_bin": result.pdf.min_bin(),
                    "sample_count": result.pdf.probability().len(),
                },
            }),
        );
    }
    if let Some(search) = root.get("search").and_then(Value::as_object) {
        let search_input = effective_values.as_ref().map_or_else(
            || impulse.clone(),
            |values| ImpulseInputV1 {
                values: values.clone(),
                erl_values: None,
                erl_time_s: None,
                source_sha256: impulse.source_sha256.clone(),
                sample_interval_s: impulse.sample_interval_s,
                source_kind: "portable-channel-producing-search-input",
                already_pulse: false,
                causality_correction_db: impulse.causality_correction_db,
                truncation_db: impulse.truncation_db,
                causality_iterations: impulse.causality_iterations,
            },
        );
        let result = portable_search_v1(search, &search_input, calibration_sigma_ne_override)?;
        selected_fom_db = Some(result.fom_db);
        if effective_pulse.is_none() {
            effective_pulse = Some(result.selected_pulse.clone());
        }
        diagnostics.insert(
            "search".to_owned(),
            json!({
                "schema": "sipi.com.equalization.search-r480.v1",
                "policy": sipi_com::SEARCH_LOOP_POLICY_V1,
                "fom_db": result.fom_db,
                "ctle_index": result.ctle_index,
                "high_pass_index": result.high_pass_index,
                "cursor_index": result.cursor_index,
                "tx_grid_index": result.tx_grid_index,
                "sigma_tx_v": result.sigma_tx_v,
                "search_input_sha256": sha256_f64_v1(&search_input.values),
                "search_input_sample_count": search_input.values.len(),
                "search_input_source_kind": search_input.source_kind,
                "calibration_sigma_ne_v": calibration_sigma_ne_override,
                "selected_pulse_sha256": sha256_f64_v1(&result.selected_pulse),
                "selected_pulse_sample_count": result.selected_pulse.len(),
                "selected_tx_taps": result.selected_tx_taps,
            }),
        );
    }
    let erl_value = root.get("erl_only").or_else(|| root.get("erl"));
    if erl_value.is_some_and(|value| !value.is_object()) {
        return Err(DirectRunErrorV1::Unsupported(
            "erl_only must be an object with r480 ERL controls".to_owned(),
        ));
    }
    if let Some(erl) = erl_value.and_then(Value::as_object) {
        if effective_values.is_some() || effective_pulse.is_some() {
            return Err(DirectRunErrorV1::Unsupported(
                "erl_only cannot be combined with another channel-producing branch".to_owned(),
            ));
        }
        let samples_per_ui = required_usize_v1(erl, "samples_per_ui", "erl_only")?;
        let levels = u32::try_from(required_usize_v1(erl, "levels", "erl_only")?)
            .map_err(|_| DirectRunErrorV1::Parameters("erl_only.levels is too large".to_owned()))?;
        let bin_size = required_f64_v1(erl, "bin_size", "erl_only")?;
        let spec_ber = required_f64_v1(erl, "spec_ber", "erl_only")?;
        let erl_source = match impulse.erl_values.as_deref() {
            Some(values) => values,
            None if impulse.source_kind.starts_with("touchstone-") => {
                return Err(DirectRunErrorV1::Unsupported(
                    "erl_only Touchstone reflection channel could not be resolved without fitting"
                        .to_owned(),
                ));
            }
            None => &impulse.values,
        };
        let pulse = rectangular_pulse_response_v1(erl_source, samples_per_ui)
            .map_err(|error| DirectRunErrorV1::Parameters(format!("erl_only pulse: {error:?}")))?;
        let gated = if let Some(time_s) = impulse.erl_time_s.as_deref() {
            if time_s.len() != pulse.len() {
                return Err(DirectRunErrorV1::Unsupported(
                    "erl_only TDR time and PTDR waveform lengths differ".to_owned(),
                ));
            }
            erl_gate_v1(&pulse, time_s, 0.0, 1.0 / 53.125e9, 0, 0.01, 0.618, 1, 0.0)?
        } else if impulse.source_kind.starts_with("touchstone-") {
            return Err(DirectRunErrorV1::Unsupported(
                "erl_only Touchstone input has no validated TDR time axis".to_owned(),
            ));
        } else {
            pulse.clone()
        };
        let mut best_phase = 0usize;
        let mut best_selector = f64::NEG_INFINITY;
        let mut best_quantile = 0.0;
        let mut last_quantile = 0.0;
        let mut best_samples = Vec::new();
        for phase in 0..samples_per_ui {
            let samples = gated
                .iter()
                .skip(phase)
                .step_by(samples_per_ui)
                .copied()
                .collect::<Vec<_>>();
            if samples.is_empty() {
                continue;
            }
            let pdf = sampled_signal_pdf_v1(&samples, levels, bin_size * 10.0, false).map_err(
                |error| DirectRunErrorV1::Parameters(format!("erl_only PDF: {error:?}")),
            )?;
            let quantile = -pdf.first_quantile(spec_ber).map_err(|error| {
                DirectRunErrorV1::Parameters(format!("erl_only quantile: {error:?}"))
            })?;
            if !quantile.is_finite() {
                return Err(DirectRunErrorV1::Parameters(
                    "erl_only PDF quantile is non-finite".to_owned(),
                ));
            }
            last_quantile = quantile;
            let selector = if erl
                .get("rl_norm_test")
                .and_then(Value::as_bool)
                .unwrap_or(true)
            {
                let sum = samples.iter().try_fold(0.0_f64, |sum, value| {
                    let next = sum + value * value;
                    next.is_finite().then_some(next).ok_or_else(|| {
                        DirectRunErrorV1::Parameters(
                            "erl_only phase selector overflowed".to_owned(),
                        )
                    })
                })?;
                let selector = sum.sqrt();
                if !selector.is_finite() {
                    return Err(DirectRunErrorV1::Parameters(
                        "erl_only phase selector is non-finite".to_owned(),
                    ));
                }
                selector
            } else {
                quantile
            };
            if selector > best_selector {
                best_selector = selector;
                best_phase = phase;
                best_quantile = quantile;
                best_samples = samples;
            }
        }
        if best_samples.is_empty() {
            return Err(DirectRunErrorV1::Parameters(
                "erl_only has no phase samples".to_owned(),
            ));
        }
        let erl_quantile = if erl
            .get("rl_norm_test")
            .and_then(Value::as_bool)
            .unwrap_or(true)
        {
            best_quantile
        } else {
            last_quantile
        };
        let erl_db = if erl_quantile == 0.0 {
            f64::INFINITY
        } else {
            -20.0 * erl_quantile.abs().log10()
        };
        let rms_sum = gated.iter().try_fold(0.0_f64, |sum, value| {
            let next = sum + value * value;
            next.is_finite()
                .then_some(next)
                .ok_or_else(|| DirectRunErrorV1::Parameters("erl_only RMS overflowed".to_owned()))
        })?;
        let rms = (rms_sum / (gated.len() as f64)).sqrt();
        if !rms.is_finite() {
            return Err(DirectRunErrorV1::Parameters(
                "erl_only RMS is non-finite".to_owned(),
            ));
        }
        let erl_rms_db = if rms == 0.0 {
            f64::INFINITY
        } else {
            -20.0 * rms.abs().log10()
        };
        let erl_db_value = metric_db_value_v1(erl_db)?;
        let erl11_db_value = metric_db_value_v1(erl_db)?;
        let erl_rms_db_value = metric_db_value_v1(erl_rms_db)?;
        erl_only_metrics = Some(sipi_com::ErlOnlyMetricsV1 {
            erl_db,
            erl11_db: erl_db,
            erl_rms_db,
            phase_index: best_phase,
        });
        diagnostics.insert(
            "erl_only".to_owned(),
            json!({
                "schema": "sipi.com.erl-only.r480.v1",
                "dispatch": "r480.erl_only",
                "erl_db": erl_db_value,
                "erl11_db": erl11_db_value,
                "erl_rms_db": erl_rms_db_value,
                "phase_index": best_phase,
                "worst_samples": best_samples,
                "impulse_sha256": sha256_f64_v1(erl_source),
                "impulse_sample_count": erl_source.len(),
                "ptdr_sha256": sha256_f64_v1(&pulse),
                "ptdr_sample_count": pulse.len(),
                "gated_sha256": sha256_f64_v1(&gated),
                "gated_sample_count": gated.len()
            }),
        );
    }
    Ok(PortableBranchResultV1 {
        diagnostics: Value::Object(diagnostics),
        effective_values,
        effective_pulse,
        effective_source_kind,
        selected_fom_db,
        calibration_sigma_bn_v,
        calibration_sigma_ne_v,
        calibration_sigma_hp_v,
        erl_only_metrics,
        effective_fext,
        effective_next,
        effective_fext_pulses,
        effective_next_pulses,
    })
}

/// Execute the already-portable R480 non-MMSE/no-RxFFE search loop from a
/// bounded canonical JSON branch.  The upstream loop is deliberately given
/// explicit frequency and receiver/equalizer controls here; we do not infer
/// an S-parameter model from the impulse or silently fall back to a fixed
/// status.  Crosstalk and calibration are separate direct-run inputs and are
/// therefore not fabricated for this no-Xtalk search leaf.
fn portable_search_v1(
    search: &Map<String, Value>,
    impulse: &ImpulseInputV1,
    calibration_sigma_ne_override: Option<f64>,
) -> Result<SearchLoopResultV1, DirectRunErrorV1> {
    let branch = "portable.search";
    let frequency_hz = parse_f64_array_key_v1(search, "frequency_hz", branch)?;
    if frequency_hz.len() < 2 {
        return Err(DirectRunErrorV1::Parameters(
            "portable.search.frequency_hz needs at least two samples".to_owned(),
        ));
    }
    if frequency_hz.len() > MAX_SEARCH_FREQUENCY_POINTS_V1 {
        return Err(DirectRunErrorV1::Unsupported(format!(
            "portable.search.frequency_hz exceeds the {}-point budget",
            MAX_SEARCH_FREQUENCY_POINTS_V1
        )));
    }
    let noise_frequency_hz = search
        .get("noise_frequency_hz")
        .map(|value| parse_f64_array_v1(value, "portable.search.noise_frequency_hz"))
        .transpose()?
        .unwrap_or_else(|| frequency_hz.clone());
    let crosstalk_frequency_hz = search
        .get("crosstalk_frequency_hz")
        .map(|value| parse_f64_array_v1(value, "portable.search.crosstalk_frequency_hz"))
        .transpose()?
        .unwrap_or_else(|| frequency_hz.clone());
    let ctle_object = required_object_v1(search, "ctle", branch)?;
    let ctle = CtleParamsV1 {
        ctle_gdc_values: parse_f64_array_key_v1(
            ctle_object,
            "ctle_gdc_values",
            "portable.search.ctle",
        )?,
        ctle_fz: parse_f64_array_key_v1(ctle_object, "ctle_fz", "portable.search.ctle")?,
        ctle_fp1: parse_f64_array_key_v1(ctle_object, "ctle_fp1", "portable.search.ctle")?,
        ctle_fp2: parse_f64_array_key_v1(ctle_object, "ctle_fp2", "portable.search.ctle")?,
        ctle_type: required_str_v1(ctle_object, "ctle_type", "portable.search.ctle")?.to_owned(),
        f_hp: parse_f64_array_key_v1(ctle_object, "f_hp", "portable.search.ctle")?,
        f_hp_z: parse_f64_array_key_v1(ctle_object, "f_hp_z", "portable.search.ctle")?,
        f_hp_p: parse_f64_array_key_v1(ctle_object, "f_hp_p", "portable.search.ctle")?,
    };
    let receiver_object = required_object_v1(search, "receiver", branch)?;
    let receiver = ReceiverNoiseParamsV1 {
        fb: required_f64_v1(receiver_object, "fb_hz", "portable.search.receiver")?,
        btorder: required_usize_v1(receiver_object, "btorder", "portable.search.receiver")?,
        fb_bt_cutoff: required_f64_v1(receiver_object, "fb_bt_cutoff", "portable.search.receiver")?,
        fb_bw_cutoff: required_f64_v1(receiver_object, "fb_bw_cutoff", "portable.search.receiver")?,
        rc_start: required_f64_v1(receiver_object, "rc_start_hz", "portable.search.receiver")?,
        rc_end: required_f64_v1(receiver_object, "rc_end_hz", "portable.search.receiver")?,
        eta_0: required_f64_v1(receiver_object, "eta_0", "portable.search.receiver")?,
        accm_max_freq: required_f64_v1(
            receiver_object,
            "accm_max_freq_hz",
            "portable.search.receiver",
        )?,
        ac_cm_rms: parse_f64_array_key_v1(
            receiver_object,
            "ac_cm_rms",
            "portable.search.receiver",
        )?,
        ctle_gdc_values: ctle.ctle_gdc_values.clone(),
        ctle_fz: ctle.ctle_fz.clone(),
        ctle_fp1: ctle.ctle_fp1.clone(),
        ctle_fp2: ctle.ctle_fp2.clone(),
        ctle_type: ctle.ctle_type.clone(),
        f_hp: ctle.f_hp.clone(),
        f_hp_z: ctle.f_hp_z.clone(),
        f_hp_p: ctle.f_hp_p.clone(),
    };
    let candidate_object = required_object_v1(search, "candidate", branch)?;
    let candidate = CandidateEvalParamsV1 {
        samples_per_ui: required_usize_v1(
            candidate_object,
            "samples_per_ui",
            "portable.search.candidate",
        )?,
        r_lm: required_f64_v1(candidate_object, "r_lm", "portable.search.candidate")?,
        levels: required_usize_v1(candidate_object, "levels", "portable.search.candidate")?,
        sigma_x: required_f64_v1(candidate_object, "sigma_x", "portable.search.candidate")?,
        dfe_delta: required_f64_v1(candidate_object, "dfe_delta", "portable.search.candidate")?,
        n_tail_start: required_i64_v1(
            candidate_object,
            "n_tail_start",
            "portable.search.candidate",
        )?,
        b_float_rss_max: required_f64_v1(
            candidate_object,
            "b_float_rss_max",
            "portable.search.candidate",
        )?,
        a_dd: required_f64_v1(candidate_object, "a_dd", "portable.search.candidate")?,
        sigma_rj: required_f64_v1(candidate_object, "sigma_rj", "portable.search.candidate")?,
        t_o: required_f64_v1(candidate_object, "t_o", "portable.search.candidate")?,
        min_veo_test: required_f64_v1(
            candidate_object,
            "min_veo_test",
            "portable.search.candidate",
        )?,
        noise_crest_factor: required_f64_v1(
            candidate_object,
            "noise_crest_factor",
            "portable.search.candidate",
        )?,
        spec_ber: required_f64_v1(candidate_object, "spec_ber", "portable.search.candidate")?,
        samples_for_c2m: required_usize_v1(
            candidate_object,
            "samples_for_c2m",
            "portable.search.candidate",
        )?,
        ql: required_f64_v1(candidate_object, "ql", "portable.search.candidate")?,
        floating_dfe: required_bool_v1(
            candidate_object,
            "floating_dfe",
            "portable.search.candidate",
        )?,
        ndfe: required_i64_v1(candidate_object, "ndfe", "portable.search.candidate")?,
        n_bmax: required_i64_v1(candidate_object, "n_bmax", "portable.search.candidate")?,
        n_bf: required_i64_v1(candidate_object, "n_bf", "portable.search.candidate")?,
        n_bg: required_i64_v1(candidate_object, "n_bg", "portable.search.candidate")?,
        bmaxg: required_f64_v1(candidate_object, "bmaxg", "portable.search.candidate")?,
        bmax: parse_f64_array_key_v1(candidate_object, "bmax", "portable.search.candidate")?,
        bmin: parse_f64_array_key_v1(candidate_object, "bmin", "portable.search.candidate")?,
    };
    let tx_values_object = required_object_v1(search, "tx_ffe_values", branch)?;
    let mut candidate_budget = 1_u64;
    let tx_ffe_values = tx_values_object
        .iter()
        .map(|(key, value)| {
            let values =
                parse_f64_array_v1(value, &format!("portable.search.tx_ffe_values.{key}"))?;
            if values.is_empty() {
                return Err(DirectRunErrorV1::Parameters(format!(
                    "portable.search.tx_ffe_values.{key} must not be empty"
                )));
            }
            candidate_budget = candidate_budget
                .checked_mul(values.len() as u64)
                .ok_or_else(|| {
                    DirectRunErrorV1::Unsupported(
                        "portable.search TX-FFE candidate budget overflow".to_owned(),
                    )
                })?;
            if candidate_budget > MAX_SEARCH_TX_FFE_CANDIDATES_V1 {
                return Err(DirectRunErrorV1::Unsupported(format!(
                    "portable.search TX-FFE grid exceeds the {}-candidate budget",
                    MAX_SEARCH_TX_FFE_CANDIDATES_V1
                )));
            }
            Ok((key.clone(), values))
        })
        .collect::<Result<BTreeMap<_, _>, DirectRunErrorV1>>()?;
    let full = SearchFullParamsV1 {
        samples_per_ui: required_usize_v1(search, "samples_per_ui", branch)?,
        fb: required_f64_v1(search, "fb_hz", branch)?,
        tx_ffe_values,
        tx_ffe_c0_min: required_f64_v1(search, "tx_ffe_c0_min", branch)?,
        ts_anchor: required_i64_v1(search, "ts_anchor", branch)?,
        local_search: required_f64_v1(search, "local_search", branch)?,
        ts_sample_adj_range: parse_i64_array_key_v1(search, "ts_sample_adj_range", branch)?,
        include_ctle: required_bool_v1(search, "include_ctle", branch)?,
        gdc_min: required_f64_v1(search, "gdc_min", branch)?,
        gqual: parse_f64_matrix_key_v1(search, "gqual", branch)?,
        g2qual: parse_f64_array_key_v1(search, "g2qual", branch)?,
        dfe_first_max: required_f64_v1(search, "dfe_first_max", branch)?,
        receiver_noise: receiver,
        ctle,
        candidate,
    };
    let options_object = required_object_v1(search, "options", branch)?;
    let receiver_options_object =
        required_object_v1(options_object, "receiver", "portable.search.options")?;
    let candidate_options_object =
        required_object_v1(options_object, "candidate", "portable.search.options")?;
    let options = SearchFullOptionsV1 {
        ffe_opt_method: required_str_v1(
            options_object,
            "ffe_opt_method",
            "portable.search.options",
        )?
        .to_owned(),
        rx_ffe_enabled: required_bool_v1(
            options_object,
            "rx_ffe_enabled",
            "portable.search.options",
        )?,
        ts_srch_mode: required_str_v1(options_object, "ts_srch_mode", "portable.search.options")?
            .to_owned(),
        cdr: required_str_v1(options_object, "cdr", "portable.search.options")?.to_owned(),
        receiver: ReceiverNoiseOptionsV1 {
            bessel_thomson: required_bool_v1(
                receiver_options_object,
                "bessel_thomson",
                "portable.search.options.receiver",
            )?,
            butterworth: required_bool_v1(
                receiver_options_object,
                "butterworth",
                "portable.search.options.receiver",
            )?,
            raised_cosine: required_bool_v1(
                receiver_options_object,
                "raised_cosine",
                "portable.search.options.receiver",
            )?,
            use_eta0_psd: required_bool_v1(
                receiver_options_object,
                "use_eta0_psd",
                "portable.search.options.receiver",
            )?,
            wc_portz: required_bool_v1(
                receiver_options_object,
                "wc_portz",
                "portable.search.options.receiver",
            )?,
            pkg_len_select: parse_i64_array_key_v1(
                receiver_options_object,
                "pkg_len_select",
                "portable.search.options.receiver",
            )?,
        },
        candidate: CandidateEvalOptionsV1 {
            snr_txw_c0: required_bool_v1(
                candidate_options_object,
                "snr_txw_c0",
                "portable.search.options.candidate",
            )?,
            wc_portz: required_bool_v1(
                candidate_options_object,
                "wc_portz",
                "portable.search.options.candidate",
            )?,
            tx_rd_sel: required_i64_v1(
                candidate_options_object,
                "tx_rd_sel",
                "portable.search.options.candidate",
            )?,
            pkg_len_select: parse_i64_array_key_v1(
                candidate_options_object,
                "pkg_len_select",
                "portable.search.options.candidate",
            )?,
            sndr: parse_f64_array_key_v1(
                candidate_options_object,
                "sndr",
                "portable.search.options.candidate",
            )?,
            limit_jitter_contrib_to_dfe_span: required_bool_v1(
                candidate_options_object,
                "limit_jitter_contrib_to_dfe_span",
                "portable.search.options.candidate",
            )?,
            force_pdf_bin_size: required_bool_v1(
                candidate_options_object,
                "force_pdf_bin_size",
                "portable.search.options.candidate",
            )?,
            bin_size: required_f64_v1(
                candidate_options_object,
                "bin_size",
                "portable.search.options.candidate",
            )?,
            force_bbn_q_factor: required_bool_v1(
                candidate_options_object,
                "force_bbn_q_factor",
                "portable.search.options.candidate",
            )?,
            bbn_q_factor: required_f64_v1(
                candidate_options_object,
                "bbn_q_factor",
                "portable.search.options.candidate",
            )?,
            histogram_window_weight: required_str_v1(
                candidate_options_object,
                "histogram_window_weight",
                "portable.search.options.candidate",
            )?
            .to_owned(),
        },
    };
    search_r480_nonmmse_no_xtalk_with_sigma_v1(
        &impulse.values,
        &frequency_hz,
        &noise_frequency_hz,
        &crosstalk_frequency_hz,
        &[],
        zero_calibration_noise_v1,
        calibration_sigma_ne_override,
        None,
        false,
        &[],
        search
            .get("package_case_index")
            .and_then(Value::as_u64)
            .map(|value| value as usize)
            .unwrap_or(0),
        &full,
        &options,
    )
    .map_err(|error| DirectRunErrorV1::Unsupported(format!("portable.search: {error:?}")))
}

fn zero_calibration_noise_v1(
    _ctle_index: usize,
    _high_pass_index: usize,
    _high_pass_gain_db: f64,
) -> f64 {
    0.0
}

fn parse_rxffe_evaluation_v1(
    value: &Value,
    candidate_index: usize,
) -> Result<RxFfeSearchEvaluationV1, DirectRunErrorV1> {
    let branch = format!("rx_ffe_search.candidates[{candidate_index}].evaluation");
    let object = value
        .as_object()
        .ok_or_else(|| DirectRunErrorV1::Parameters(format!("{branch} must be an object")))?;
    let parameters = required_object_v1(object, "parameters", &branch)?;
    let options = required_object_v1(object, "options", &branch)?;
    let parameters_branch = format!("{branch}.parameters");
    let options_branch = format!("{branch}.options");
    let levels = required_usize_v1(parameters, "levels", &parameters_branch)?;
    let levels = u32::try_from(levels).map_err(|_| {
        DirectRunErrorV1::Parameters(format!("{parameters_branch}.levels is too large"))
    })?;
    let evaluation_parameters = CandidateEvalParamsV1 {
        samples_per_ui: required_usize_v1(parameters, "samples_per_ui", &parameters_branch)?,
        r_lm: required_f64_v1(parameters, "r_lm", &parameters_branch)?,
        levels: usize::try_from(levels).map_err(|_| {
            DirectRunErrorV1::Parameters(format!("{parameters_branch}.levels is too large"))
        })?,
        sigma_x: required_f64_v1(parameters, "sigma_x", &parameters_branch)?,
        dfe_delta: required_f64_v1(parameters, "dfe_delta", &parameters_branch)?,
        n_tail_start: required_i64_v1(parameters, "n_tail_start", &parameters_branch)?,
        b_float_rss_max: required_f64_v1(parameters, "b_float_rss_max", &parameters_branch)?,
        a_dd: required_f64_v1(parameters, "a_dd", &parameters_branch)?,
        sigma_rj: required_f64_v1(parameters, "sigma_rj", &parameters_branch)?,
        t_o: required_f64_v1(parameters, "t_o", &parameters_branch)?,
        min_veo_test: required_f64_v1(parameters, "min_veo_test", &parameters_branch)?,
        noise_crest_factor: required_f64_v1(parameters, "noise_crest_factor", &parameters_branch)?,
        spec_ber: required_f64_v1(parameters, "spec_ber", &parameters_branch)?,
        samples_for_c2m: required_usize_v1(parameters, "samples_for_c2m", &parameters_branch)?,
        ql: required_f64_v1(parameters, "ql", &parameters_branch)?,
        floating_dfe: required_bool_v1(parameters, "floating_dfe", &parameters_branch)?,
        ndfe: required_i64_v1(parameters, "ndfe", &parameters_branch)?,
        n_bmax: required_i64_v1(parameters, "n_bmax", &parameters_branch)?,
        n_bf: required_i64_v1(parameters, "n_bf", &parameters_branch)?,
        n_bg: required_i64_v1(parameters, "n_bg", &parameters_branch)?,
        bmaxg: required_f64_v1(parameters, "bmaxg", &parameters_branch)?,
        bmax: parse_f64_array_key_v1(parameters, "bmax", &parameters_branch)?,
        bmin: parse_f64_array_key_v1(parameters, "bmin", &parameters_branch)?,
    };
    let evaluation_options = CandidateEvalOptionsV1 {
        snr_txw_c0: required_bool_v1(options, "snr_txw_c0", &options_branch)?,
        wc_portz: required_bool_v1(options, "wc_portz", &options_branch)?,
        tx_rd_sel: required_i64_v1(options, "tx_rd_sel", &options_branch)?,
        pkg_len_select: parse_i64_array_key_v1(options, "pkg_len_select", &options_branch)?,
        sndr: parse_f64_array_key_v1(options, "sndr", &options_branch)?,
        limit_jitter_contrib_to_dfe_span: required_bool_v1(
            options,
            "limit_jitter_contrib_to_dfe_span",
            &options_branch,
        )?,
        force_pdf_bin_size: required_bool_v1(options, "force_pdf_bin_size", &options_branch)?,
        bin_size: required_f64_v1(options, "bin_size", &options_branch)?,
        force_bbn_q_factor: required_bool_v1(options, "force_bbn_q_factor", &options_branch)?,
        bbn_q_factor: required_f64_v1(options, "bbn_q_factor", &options_branch)?,
        histogram_window_weight: required_str_v1(
            options,
            "histogram_window_weight",
            &options_branch,
        )?
        .to_owned(),
    };
    Ok(RxFfeSearchEvaluationV1 {
        parameters: evaluation_parameters,
        options: evaluation_options,
        sigma_n_v: required_f64_v1(object, "sigma_n_v", &branch)?,
        sigma_ne_v: required_f64_v1(object, "sigma_ne_v", &branch)?,
        sigma_xt_v: required_f64_v1(object, "sigma_xt_v", &branch)?,
        package_case_index: required_usize_v1(object, "package_case_index", &branch)?,
        tx_taps: parse_f64_array_key_v1(object, "tx_taps", &branch)?,
        tx_precursor_count: required_usize_v1(object, "tx_precursor_count", &branch)?,
        tx_grid_index: required_i64_v1(object, "tx_grid_index", &branch)?,
        tx_source_indices: parse_i64_array_key_v1(object, "tx_source_indices", &branch)?,
        itick: required_i64_v1(object, "itick", &branch)?,
        ffe_main_cursor_min: required_f64_v1(object, "ffe_main_cursor_min", &branch)?,
        ffe_pre_tap1_max: object
            .get("ffe_pre_tap1_max")
            .and_then(Value::as_f64)
            .unwrap_or(f64::INFINITY),
        ffe_pre_tapn_max: object
            .get("ffe_pre_tapn_max")
            .and_then(Value::as_f64)
            .unwrap_or(f64::INFINITY),
        ffe_post_tap1_max: required_f64_v1(object, "ffe_post_tap1_max", &branch)?,
        ffe_tapn_max: required_f64_v1(object, "ffe_tapn_max", &branch)?,
    })
}

fn required_f64_v1(
    object: &Map<String, Value>,
    key: &str,
    branch: &str,
) -> Result<f64, DirectRunErrorV1> {
    object
        .get(key)
        .and_then(Value::as_f64)
        .filter(|value| value.is_finite())
        .ok_or_else(|| {
            DirectRunErrorV1::Parameters(format!("{branch}.{key} must be a finite number"))
        })
}

fn required_object_v1<'a>(
    object: &'a Map<String, Value>,
    key: &str,
    branch: &str,
) -> Result<&'a Map<String, Value>, DirectRunErrorV1> {
    object
        .get(key)
        .and_then(Value::as_object)
        .ok_or_else(|| DirectRunErrorV1::Parameters(format!("{branch}.{key} must be an object")))
}

fn required_bool_v1(
    object: &Map<String, Value>,
    key: &str,
    branch: &str,
) -> Result<bool, DirectRunErrorV1> {
    object
        .get(key)
        .and_then(Value::as_bool)
        .ok_or_else(|| DirectRunErrorV1::Parameters(format!("{branch}.{key} must be boolean")))
}

fn required_i64_v1(
    object: &Map<String, Value>,
    key: &str,
    branch: &str,
) -> Result<i64, DirectRunErrorV1> {
    let value = object.get(key).and_then(Value::as_i64).ok_or_else(|| {
        DirectRunErrorV1::Parameters(format!("{branch}.{key} must be a signed integer"))
    })?;
    Ok(value)
}

fn required_usize_v1(
    object: &Map<String, Value>,
    key: &str,
    branch: &str,
) -> Result<usize, DirectRunErrorV1> {
    let value = required_f64_v1(object, key, branch)?;
    if value < 0.0 || value.fract() != 0.0 {
        return Err(DirectRunErrorV1::Parameters(format!(
            "{branch}.{key} must be a non-negative integer"
        )));
    }
    usize::try_from(value as u64)
        .map_err(|_| DirectRunErrorV1::Parameters(format!("{branch}.{key} is too large")))
}

fn required_str_v1<'a>(
    object: &'a Map<String, Value>,
    key: &str,
    branch: &str,
) -> Result<&'a str, DirectRunErrorV1> {
    object
        .get(key)
        .and_then(Value::as_str)
        .filter(|value| !value.is_empty())
        .ok_or_else(|| DirectRunErrorV1::Parameters(format!("{branch}.{key} must be a string")))
}

fn optional_f64_v1(
    object: &Map<String, Value>,
    key: &str,
) -> Result<Option<f64>, DirectRunErrorV1> {
    object
        .get(key)
        .map(|value| {
            value
                .as_f64()
                .filter(|value| value.is_finite())
                .ok_or_else(|| {
                    DirectRunErrorV1::Parameters(format!("{key} must be a finite number"))
                })
        })
        .transpose()
}

fn parse_f64_array_key_v1(
    object: &Map<String, Value>,
    key: &str,
    branch: &str,
) -> Result<Vec<f64>, DirectRunErrorV1> {
    let value = object
        .get(key)
        .ok_or_else(|| DirectRunErrorV1::Parameters(format!("{branch}.{key} is required")))?;
    parse_f64_array_v1(value, &format!("{branch}.{key}"))
}

fn parse_f64_array_v1(value: &Value, label: &str) -> Result<Vec<f64>, DirectRunErrorV1> {
    value
        .as_array()
        .ok_or_else(|| DirectRunErrorV1::Parameters(format!("{label} must be a numeric array")))?
        .iter()
        .enumerate()
        .map(|(index, value)| {
            value
                .as_f64()
                .filter(|value| value.is_finite())
                .ok_or_else(|| {
                    DirectRunErrorV1::Parameters(format!("{label}[{index}] is not finite"))
                })
        })
        .collect()
}

fn parse_i64_array_key_v1(
    object: &Map<String, Value>,
    key: &str,
    branch: &str,
) -> Result<Vec<i64>, DirectRunErrorV1> {
    let value = object
        .get(key)
        .ok_or_else(|| DirectRunErrorV1::Parameters(format!("{branch}.{key} is required")))?;
    value
        .as_array()
        .ok_or_else(|| {
            DirectRunErrorV1::Parameters(format!("{branch}.{key} must be an integer array"))
        })?
        .iter()
        .enumerate()
        .map(|(index, value)| {
            value.as_i64().ok_or_else(|| {
                DirectRunErrorV1::Parameters(format!(
                    "{branch}.{key}[{index}] must be a signed integer"
                ))
            })
        })
        .collect()
}

fn parse_f64_matrix_key_v1(
    object: &Map<String, Value>,
    key: &str,
    branch: &str,
) -> Result<Vec<Vec<f64>>, DirectRunErrorV1> {
    let value = object
        .get(key)
        .ok_or_else(|| DirectRunErrorV1::Parameters(format!("{branch}.{key} is required")))?;
    let rows = value
        .as_array()
        .ok_or_else(|| DirectRunErrorV1::Parameters(format!("{branch}.{key} must be a matrix")))?;
    rows.iter()
        .enumerate()
        .map(|(row, value)| parse_f64_array_v1(value, &format!("{branch}.{key}[{row}]")))
        .collect()
}

fn parse_complex_array_key_v1(
    object: &Map<String, Value>,
    key: &str,
    branch: &str,
) -> Result<Vec<Complex64>, DirectRunErrorV1> {
    let values = object
        .get(key)
        .ok_or_else(|| DirectRunErrorV1::Parameters(format!("{branch}.{key} is required")))?
        .as_array()
        .ok_or_else(|| {
            DirectRunErrorV1::Parameters(format!("{branch}.{key} must be complex pairs"))
        })?;
    values
        .iter()
        .enumerate()
        .map(|(index, value)| {
            let pair = value.as_array().ok_or_else(|| {
                DirectRunErrorV1::Parameters(format!(
                    "{branch}.{key}[{index}] must be [real, imaginary]"
                ))
            })?;
            if pair.len() != 2 {
                return Err(DirectRunErrorV1::Parameters(format!(
                    "{branch}.{key}[{index}] must have two values"
                )));
            }
            let real = pair[0]
                .as_f64()
                .filter(|value| value.is_finite())
                .ok_or_else(|| {
                    DirectRunErrorV1::Parameters(format!(
                        "{branch}.{key}[{index}][0] is not finite"
                    ))
                })?;
            let imaginary = pair[1]
                .as_f64()
                .filter(|value| value.is_finite())
                .ok_or_else(|| {
                    DirectRunErrorV1::Parameters(format!(
                        "{branch}.{key}[{index}][1] is not finite"
                    ))
                })?;
            Complex64::try_new(real, imaginary).map_err(|_| {
                DirectRunErrorV1::Parameters(format!("{branch}.{key}[{index}] is not finite"))
            })
        })
        .collect()
}

fn parse_four_port_array_v1(
    object: &Map<String, Value>,
    key: &str,
    branch: &str,
) -> Result<Vec<sipi_com::FourPortSMatrixV1>, DirectRunErrorV1> {
    let samples = object
        .get(key)
        .ok_or_else(|| DirectRunErrorV1::Parameters(format!("{branch}.{key} is required")))?
        .as_array()
        .ok_or_else(|| {
            DirectRunErrorV1::Parameters(format!("{branch}.{key} must be a 4x4 matrix array"))
        })?;
    samples
        .iter()
        .enumerate()
        .map(|(sample_index, sample)| {
            let rows = sample.as_array().ok_or_else(|| {
                DirectRunErrorV1::Parameters(format!("{branch}.{key}[{sample_index}] must be 4x4"))
            })?;
            if rows.len() != 4 {
                return Err(DirectRunErrorV1::Parameters(format!(
                    "{branch}.{key}[{sample_index}] must have four rows"
                )));
            }
            let zero = Complex64::try_new(0.0, 0.0).map_err(|_| {
                DirectRunErrorV1::Parameters(format!("{branch}.{key}[{sample_index}] has invalid zero"))
            })?;
            let mut result = [[zero; 4]; 4];
            for (row_index, row) in rows.iter().enumerate() {
                let entries = row.as_array().ok_or_else(|| {
                    DirectRunErrorV1::Parameters(format!(
                        "{branch}.{key}[{sample_index}][{row_index}] must be a row"
                    ))
                })?;
                if entries.len() != 4 {
                    return Err(DirectRunErrorV1::Parameters(format!(
                        "{branch}.{key}[{sample_index}][{row_index}] must have four entries"
                    )));
                }
                for (column_index, value) in entries.iter().enumerate() {
                    let pair = value.as_array().ok_or_else(|| {
                        DirectRunErrorV1::Parameters(format!(
                            "{branch}.{key}[{sample_index}][{row_index}][{column_index}] must be [real, imaginary]"
                        ))
                    })?;
                    if pair.len() != 2 {
                        return Err(DirectRunErrorV1::Parameters(format!(
                            "{branch}.{key}[{sample_index}][{row_index}][{column_index}] must have two values"
                        )));
                    }
                    let real = pair[0].as_f64().filter(|value| value.is_finite()).ok_or_else(|| {
                        DirectRunErrorV1::Parameters(format!(
                            "{branch}.{key}[{sample_index}][{row_index}][{column_index}][0] is not finite"
                        ))
                    })?;
                    let imaginary = pair[1].as_f64().filter(|value| value.is_finite()).ok_or_else(|| {
                        DirectRunErrorV1::Parameters(format!(
                            "{branch}.{key}[{sample_index}][{row_index}][{column_index}][1] is not finite"
                        ))
                    })?;
                    result[row_index][column_index] = Complex64::try_new(real, imaginary).map_err(|_| {
                        DirectRunErrorV1::Parameters(format!(
                            "{branch}.{key}[{sample_index}][{row_index}][{column_index}] is not finite"
                        ))
                    })?;
                }
            }
            Ok(result)
        })
        .collect()
}

fn parse_port_order_v1(value: &Value, branch: &str) -> Result<[usize; 4], DirectRunErrorV1> {
    let values = value
        .as_array()
        .ok_or_else(|| DirectRunErrorV1::Parameters(format!("{branch} must be [1,2,3,4]")))?;
    if values.len() != 4 {
        return Err(DirectRunErrorV1::Parameters(format!(
            "{branch} must contain four one-based ports"
        )));
    }
    let mut order = [0usize; 4];
    for (index, value) in values.iter().enumerate() {
        let port = value.as_u64().and_then(|port| usize::try_from(port).ok());
        let Some(port) = port.filter(|port| (1..=4).contains(port)) else {
            return Err(DirectRunErrorV1::Parameters(format!(
                "{branch}[{index}] must be one of 1..4"
            )));
        };
        order[index] = port - 1;
    }
    let mut sorted = order;
    sorted.sort_unstable();
    if sorted != [0, 1, 2, 3] {
        return Err(DirectRunErrorV1::Parameters(format!(
            "{branch} must be a permutation without duplicate ports"
        )));
    }
    Ok(order)
}

fn reorder_four_port_samples_v1(
    samples: &[sipi_com::FourPortSMatrixV1],
    order: [usize; 4],
) -> Vec<sipi_com::FourPortSMatrixV1> {
    samples
        .iter()
        .map(|sample| {
            let mut reordered = *sample;
            for row in 0..4 {
                for column in 0..4 {
                    reordered[row][column] = sample[order[row]][order[column]];
                }
            }
            reordered
        })
        .collect()
}

fn load_channel_input_v1(path: &Path) -> Result<ImpulseInputV1, DirectRunErrorV1> {
    if path
        .extension()
        .and_then(|value| value.to_str())
        .is_some_and(|value| value.eq_ignore_ascii_case("s4p"))
    {
        load_s4p_impulse_v1(path)
    } else {
        load_impulse_v1(path)
    }
}

fn complex_mul_v1(left: Complex64, right: Complex64) -> Result<Complex64, DirectRunErrorV1> {
    Complex64::try_new(
        left.real() * right.real() - left.imaginary() * right.imaginary(),
        left.real() * right.imaginary() + left.imaginary() * right.real(),
    )
    .map_err(|_| DirectRunErrorV1::Channel("non-finite complex product".to_owned()))
}

fn complex_add_v1(left: Complex64, right: Complex64) -> Result<Complex64, DirectRunErrorV1> {
    Complex64::try_new(
        left.real() + right.real(),
        left.imaginary() + right.imaginary(),
    )
    .map_err(|_| DirectRunErrorV1::Channel("non-finite complex sum".to_owned()))
}

fn complex_sub_v1(left: Complex64, right: Complex64) -> Result<Complex64, DirectRunErrorV1> {
    Complex64::try_new(
        left.real() - right.real(),
        left.imaginary() - right.imaginary(),
    )
    .map_err(|_| DirectRunErrorV1::Channel("non-finite complex difference".to_owned()))
}

fn exact_erl_s2p_profile_v1(document: &Value, path: &Path) -> Result<bool, DirectRunErrorV1> {
    let is_s2p = path
        .extension()
        .and_then(|value| value.to_str())
        .is_some_and(|value| value.eq_ignore_ascii_case("s2p"));
    if !is_s2p {
        return Ok(false);
    }
    let document_object = document.as_object().ok_or_else(|| {
        DirectRunErrorV1::Json("canonical config object must be an object".to_owned())
    })?;
    if document_object.contains_key("erl_only") || document_object.contains_key("erl") {
        return Err(DirectRunErrorV1::Unsupported(
            "S2P ERL-only aliases must be under typed portable.erl_only".to_owned(),
        ));
    }
    let Some(portable) = document.get("portable").and_then(Value::as_object) else {
        return Ok(false);
    };
    if portable.contains_key("erl") {
        return Err(DirectRunErrorV1::Unsupported(
            "S2P ERL-only portable.erl alias is not admitted".to_owned(),
        ));
    }
    let Some(erl) = portable.get("erl_only") else {
        return Ok(false);
    };
    let Some(erl) = erl.as_object() else {
        return Err(DirectRunErrorV1::Unsupported(
            "S2P ERL-only requires a typed portable.erl_only object".to_owned(),
        ));
    };
    if erl.contains_key("erl") {
        return Err(DirectRunErrorV1::Unsupported(
            "S2P ERL-only portable.erl alias is not admitted".to_owned(),
        ));
    }
    let Some(profile) = erl.get("tdr_profile").and_then(Value::as_object) else {
        return Err(DirectRunErrorV1::Unsupported(
            "S2P ERL-only requires the exact r480_s2p_erl_v1 tdr_profile".to_owned(),
        ));
    };
    let required = [
        ("name", "r480_s2p_erl_v1"),
        ("samples_per_ui", "32"),
        ("levels", "4"),
        ("bin_size", "0.00001"),
        ("spec_ber", "0.00001"),
        ("rl_norm_test", "true"),
        ("baud_hz", "53125000000"),
        ("sample_dt_s", "0.0000000000005882352941176471"),
        ("s_reference_ohm", "100"),
        ("zt_ohm", "50"),
        ("transition_time_ns", "0.01"),
        ("transition_filter_type", "1"),
        ("transition_measurement_point", "0"),
        ("receiver_cutoff_multiplier", "0.75"),
        ("receiver_filter_enabled", "true"),
        ("tukey_enabled", "true"),
        ("fixture_delay_s", "0"),
        ("tdr_delay_s", "0.0000000005"),
        ("observation_duration_ui", "800"),
        ("gate_n_bx", "0"),
        ("gate_rho_x", "0.618"),
        ("gate_grr", "1"),
        ("gate_beta_x_db_per_s", "0"),
    ];
    let exact = required.iter().all(|(key, expected)| match *expected {
        "r480_s2p_erl_v1" => profile.get(*key).and_then(Value::as_str) == Some(expected),
        "true" => profile.get(*key).and_then(Value::as_bool) == Some(true),
        _ => profile
            .get(*key)
            .and_then(Value::as_f64)
            .and_then(|value| {
                expected
                    .parse::<f64>()
                    .ok()
                    .filter(|target| value.is_finite() && value.to_bits() == target.to_bits())
            })
            .is_some(),
    });
    if !exact || profile.len() != required.len() {
        return Err(DirectRunErrorV1::Unsupported(
            "S2P ERL-only tdr_profile does not exactly match pinned r480 controls".to_owned(),
        ));
    }
    let outer_controls = [
        ("samples_per_ui", "32"),
        ("levels", "4"),
        ("bin_size", "0.00001"),
        ("spec_ber", "0.00001"),
        ("rl_norm_test", "true"),
    ];
    let outer_keys = [
        "samples_per_ui",
        "levels",
        "bin_size",
        "spec_ber",
        "rl_norm_test",
        "tdr_profile",
    ];
    let outer_exact = erl.len() == outer_keys.len()
        && erl.keys().all(|key| outer_keys.contains(&key.as_str()))
        && outer_controls
            .iter()
            .all(|(key, expected)| match *expected {
                "true" => erl.get(*key).and_then(Value::as_bool) == Some(true),
                _ => erl
                    .get(*key)
                    .and_then(Value::as_f64)
                    .and_then(|value| {
                        expected.parse::<f64>().ok().filter(|target| {
                            value.is_finite() && value.to_bits() == target.to_bits()
                        })
                    })
                    .is_some(),
            });
    if !outer_exact {
        return Err(DirectRunErrorV1::Unsupported(
            "S2P ERL-only outer controls do not match pinned r480 profile".to_owned(),
        ));
    }
    Ok(true)
}

fn load_erl_s2p_impulse_v1(path: &Path) -> Result<ImpulseInputV1, DirectRunErrorV1> {
    load_impulse_mode_v1(path, true)
}

/// Port the pinned r4.80 S2P ERL-only TDR preparation.  This is intentionally
/// an impulse-producing path: no rational model or S-parameter fit is used.
fn s2p_erl_impulse_v1(
    reflection: &[Complex64],
    frequency_hz: &[f64],
) -> Result<ErlTdrInputV1, DirectRunErrorV1> {
    if reflection.len() != frequency_hz.len() || reflection.len() < 3 {
        return Err(DirectRunErrorV1::Channel(
            "S2P ERL reflection axis mismatch".to_owned(),
        ));
    }
    let receiver = butterworth_filter_v1(frequency_hz, 0.75, 53.125e9, true)
        .map_err(|error| DirectRunErrorV1::Channel(format!("S2P ERL receiver: {error:?}")))?;
    let tukey = raised_cosine_filter_v1(frequency_hz, 0.75 * 53.125e9, 53.125e9, true)
        .map_err(|error| DirectRunErrorV1::Channel(format!("S2P ERL Tukey: {error:?}")))?;
    let mut filtered = Vec::with_capacity(reflection.len());
    for ((value, frequency), (receiver, tukey)) in reflection
        .iter()
        .zip(frequency_hz)
        .zip(receiver.iter().zip(tukey.iter()))
    {
        let frequency_ghz = *frequency / 1.0e9;
        let gaussian =
            (-2.0 * (std::f64::consts::PI * frequency_ghz * 0.01 / 1.6832).powi(2)).exp();
        let angle = -2.0 * std::f64::consts::PI * frequency_ghz * 0.01 * 3.0
            - 2.0 * std::f64::consts::PI * *frequency * 500.0e-12;
        let transition = Complex64::try_new(gaussian * angle.cos(), gaussian * angle.sin())
            .map_err(|_| DirectRunErrorV1::Channel("non-finite transition filter".to_owned()))?;
        let receiver = Complex64::try_new(receiver.real() * *tukey, receiver.imaginary() * *tukey)
            .map_err(|_| DirectRunErrorV1::Channel("non-finite receiver filter".to_owned()))?;
        filtered.push(complex_mul_v1(
            complex_mul_v1(*value, transition)?,
            receiver,
        )?);
    }
    let impulse = s21_to_impulse_dc_v1(
        &filtered,
        frequency_hz,
        &FdToTdOptionsV1 {
            sample_dt_s: 1.0 / (53.125e9 * 32.0),
            magnitude_policy: "linear_trend_to_DC".to_owned(),
            phase_policy: "extrap_cubic_to_dc_linear_to_inf".to_owned(),
            debug: false,
            truncation_threshold: 1.0e-5,
            ..FdToTdOptionsV1::default()
        },
    )
    .map_err(|error| DirectRunErrorV1::Channel(format!("S2P ERL FD-to-TD: {error:?}")))?;
    let delay_s = 500.0e-12;
    let ui_s = 1.0 / 53.125e9;
    let shifted_time = impulse
        .time_s
        .iter()
        .map(|time| {
            let shifted = *time - delay_s;
            if shifted.is_finite() {
                Ok(shifted)
            } else {
                Err(DirectRunErrorV1::Channel(
                    "non-finite S2P ERL observation time".to_owned(),
                ))
            }
        })
        .collect::<Result<Vec<_>, _>>()?;
    let end = impulse
        .time_s
        .iter()
        .position(|time| *time >= delay_s + 800.0 * ui_s)
        .map_or(impulse.time_s.len(), |index| index + 1);
    let start = impulse
        .time_s
        .iter()
        .position(|time| *time - delay_s >= 0.01e-9)
        .unwrap_or(0);
    let observation_start = start.min(end);
    let selected = impulse.voltage[observation_start..end].to_vec();
    let selected_time = shifted_time[observation_start..end].to_vec();
    if selected.is_empty() || selected_time.len() != selected.len() {
        return Err(DirectRunErrorV1::Channel(
            "S2P ERL TDR window is empty".to_owned(),
        ));
    }
    validate_impulse_v1(&selected)?;
    Ok(ErlTdrInputV1 {
        impulse: selected,
        time_s: selected_time,
    })
}

/// Exact r4.80 `erl_gate` semantics for the admitted S2P profile.  The
/// The gate is applied after the trimmed TDR observation, preserving the
/// source's leading zero/factor window and its unchanged tail.
#[allow(clippy::too_many_arguments)]
fn erl_gate_v1(
    ptdr: &[f64],
    time_s: &[f64],
    tfx_s: f64,
    ui_s: f64,
    n_bx: i64,
    transition_ns: f64,
    rho_x: f64,
    grr: i64,
    beta_x_db_per_s: f64,
) -> Result<Vec<f64>, DirectRunErrorV1> {
    if ptdr.len() != time_s.len()
        || ptdr.is_empty()
        || !ptdr.iter().chain(time_s).all(|value| value.is_finite())
        || !tfx_s.is_finite()
        || !ui_s.is_finite()
        || ui_s <= 0.0
        || n_bx < 0
        || !transition_ns.is_finite()
        || transition_ns < 0.0
        || !rho_x.is_finite()
        || !beta_x_db_per_s.is_finite()
        || !matches!(grr, 0..=2)
    {
        return Err(DirectRunErrorV1::Channel(
            "invalid ERL gate inputs".to_owned(),
        ));
    }
    let transition_delay = 3.0 * transition_ns * 1.0e-9;
    let gate_start = tfx_s + transition_delay;
    let Some(start) = time_s.iter().position(|time| *time >= gate_start) else {
        return Ok(ptdr.to_vec());
    };
    let gate_end = (n_bx as f64 + 1.0) * ui_s + tfx_s + transition_delay;
    let end = time_s
        .iter()
        .position(|time| *time > gate_end)
        .unwrap_or(ptdr.len().saturating_sub(1));
    let tk = gate_end;
    let mut gated = ptdr.to_vec();
    gated[..start].fill(0.0);
    for index in start..=end.min(ptdr.len().saturating_sub(1)) {
        let x = (time_s[index] - tfx_s - transition_delay) / ui_s;
        let reflection = if grr == 2 {
            rho_x
        } else {
            (1.0 + rho_x)
                * rho_x
                * (-(x - n_bx as f64 - 1.0).powi(2) / (1.0 + n_bx as f64).powi(2)).exp()
        };
        let loss = if n_bx > 0 && beta_x_db_per_s != 0.0 {
            10.0_f64.powf(beta_x_db_per_s * (time_s[index] - tk) / 20.0)
        } else {
            1.0
        };
        let value = ptdr[index] * loss * reflection;
        if !value.is_finite() {
            return Err(DirectRunErrorV1::Channel(
                "non-finite ERL gate output".to_owned(),
            ));
        }
        gated[index] = value;
    }
    Ok(gated)
}

fn load_impulse_v1(path: &Path) -> Result<ImpulseInputV1, DirectRunErrorV1> {
    load_impulse_mode_v1(path, false)
}

fn touchstone_limits_v1() -> Result<TouchstoneParseLimitsV1, DirectRunErrorV1> {
    let max_file_bytes =
        NonZeroUsize::new(MAX_IMPULSE_FILE_BYTES_V1 as usize).ok_or_else(|| {
            DirectRunErrorV1::Touchstone("invalid zero Touchstone file limit".to_owned())
        })?;
    let max_line_bytes = NonZeroUsize::new(16 * 1024).ok_or_else(|| {
        DirectRunErrorV1::Touchstone("invalid zero Touchstone line limit".to_owned())
    })?;
    let max_records = NonZeroUsize::new(MAX_TOUCHSTONE_RECORDS_V1).ok_or_else(|| {
        DirectRunErrorV1::Touchstone("invalid zero Touchstone record limit".to_owned())
    })?;
    Ok(TouchstoneParseLimitsV1::new(
        max_file_bytes,
        max_line_bytes,
        max_records,
    ))
}

fn load_impulse_mode_v1(
    path: &Path,
    erl_s2p_mode: bool,
) -> Result<ImpulseInputV1, DirectRunErrorV1> {
    let bytes = bounded_read_v1(path, MAX_IMPULSE_FILE_BYTES_V1)?;
    let source_sha256 = sha256_bytes_v1(&bytes);
    let extension = path
        .extension()
        .and_then(|extension| extension.to_str())
        .unwrap_or_default();
    if extension.eq_ignore_ascii_case("s2p") || extension.eq_ignore_ascii_case("ts") {
        let limits = touchstone_limits_v1()?;
        let parsed = parse_touchstone_hz_s_ri_50_two_port_v1(&bytes, limits)
            .map_err(|error| DirectRunErrorV1::Touchstone(format!("{error:?}")))?;
        let frequency_hz = parsed
            .rows()
            .iter()
            .map(|row| row.frequency_hz())
            .collect::<Vec<_>>();
        let s21 = parsed
            .rows()
            .iter()
            .map(|row| row.s21())
            .collect::<Vec<_>>();
        let result = s21_to_impulse_dc_v1(&s21, &frequency_hz, &FdToTdOptionsV1::default())
            .map_err(|error| {
                DirectRunErrorV1::Channel(format!("Touchstone S2P FD-to-TD: {error:?}"))
            })?;
        validate_impulse_v1(&result.voltage)?;
        let reflection = parsed
            .rows()
            .iter()
            .map(|row| row.s11())
            .collect::<Vec<_>>();
        let differential_reflection = parsed
            .rows()
            .iter()
            .map(|row| {
                let differential = complex_add_v1(
                    complex_sub_v1(row.s11(), row.s12())?,
                    complex_sub_v1(row.s22(), row.s21())?,
                )?;
                Complex64::try_new(0.5 * differential.real(), 0.5 * differential.imaginary())
                    .map_err(|_| {
                        DirectRunErrorV1::Channel("non-finite differential reflection".to_owned())
                    })
            })
            .collect::<Result<Vec<_>, _>>()?;
        let (erl_values, erl_time_s) = if erl_s2p_mode {
            let tdr = s2p_erl_impulse_v1(&differential_reflection, &frequency_hz)?;
            (Some(tdr.impulse), Some(tdr.time_s))
        } else {
            (
                s21_to_impulse_dc_v1(&reflection, &frequency_hz, &FdToTdOptionsV1::default())
                    .ok()
                    .and_then(|value| {
                        validate_impulse_v1(&value.voltage)
                            .ok()
                            .map(|_| value.voltage)
                    }),
                None,
            )
        };
        return Ok(ImpulseInputV1 {
            values: result.voltage,
            erl_values,
            erl_time_s,
            source_sha256,
            sample_interval_s: result
                .time_s
                .windows(2)
                .next()
                .map(|pair| pair[1] - pair[0]),
            source_kind: "touchstone-two-port-s21-fd-to-td-impulse",
            already_pulse: false,
            causality_correction_db: Some(result.causality_correction_db),
            truncation_db: Some(result.truncation_db),
            causality_iterations: Some(result.causality_iterations),
        });
    }
    if extension.eq_ignore_ascii_case("json") {
        let document: Value = serde_json::from_slice(&bytes)
            .map_err(|error| DirectRunErrorV1::Json(error.to_string()))?;
        if document.get("frequency_hz").is_some() && document.get("s21").is_some() {
            return load_frequency_domain_json_v1(&document, source_sha256);
        }
        let explicit_pulse = document.get("pulse").is_some() && document.get("impulse").is_none();
        let value = document
            .get("impulse")
            .or_else(|| document.get("pulse"))
            .unwrap_or(&document);
        let values = value
            .as_array()
            .ok_or_else(|| DirectRunErrorV1::Json("impulse JSON must be an array".to_owned()))?
            .iter()
            .enumerate()
            .map(|(index, value)| {
                value
                    .as_f64()
                    .filter(|value| value.is_finite())
                    .ok_or(DirectRunErrorV1::NonFiniteImpulse { index })
            })
            .collect::<Result<Vec<_>, _>>()?;
        validate_impulse_v1(&values)?;
        return Ok(ImpulseInputV1 {
            values,
            erl_values: None,
            erl_time_s: None,
            source_sha256,
            sample_interval_s: None,
            source_kind: if explicit_pulse {
                "json-pulse"
            } else {
                "json-impulse"
            },
            already_pulse: explicit_pulse,
            causality_correction_db: None,
            truncation_db: None,
            causality_iterations: None,
        });
    }
    if extension.eq_ignore_ascii_case("csv") || extension.eq_ignore_ascii_case("td") {
        let values = parse_td_csv_values_v1(&bytes, path)?;
        validate_impulse_v1(&values)?;
        return Ok(ImpulseInputV1 {
            values,
            erl_values: None,
            erl_time_s: None,
            source_sha256,
            sample_interval_s: None,
            source_kind: "td-csv-impulse",
            already_pulse: false,
            causality_correction_db: None,
            truncation_db: None,
            causality_iterations: None,
        });
    }
    if bytes.len() % std::mem::size_of::<f64>() != 0 {
        return Err(DirectRunErrorV1::Input {
            path: path.display().to_string(),
            message: "raw impulse input must contain little-endian f64 samples".to_owned(),
        });
    }
    let values = bytes
        .chunks_exact(8)
        .map(|chunk| {
            let mut bytes = [0_u8; 8];
            bytes.copy_from_slice(chunk);
            f64::from_le_bytes(bytes)
        })
        .collect::<Vec<_>>();
    validate_impulse_v1(&values)?;
    Ok(ImpulseInputV1 {
        values,
        erl_values: None,
        erl_time_s: None,
        source_sha256,
        sample_interval_s: None,
        source_kind: "f64le-impulse",
        already_pulse: false,
        causality_correction_db: None,
        truncation_db: None,
        causality_iterations: None,
    })
}

fn load_s4p_impulse_v1(path: &Path) -> Result<ImpulseInputV1, DirectRunErrorV1> {
    let bytes = bounded_read_v1(path, MAX_IMPULSE_FILE_BYTES_V1)?;
    let source_sha256 = sha256_bytes_v1(&bytes);
    let limits = touchstone_limits_v1()?;
    let parsed = parse_selected_four_port_hz_s_ri_50_v2(&bytes, limits)
        .map_err(|error| DirectRunErrorV1::Touchstone(format!("{error:?}")))?;
    let frequency_hz = parsed
        .rows()
        .iter()
        .map(|row| row.frequency_hz())
        .collect::<Vec<_>>();
    let samples = parsed
        .rows()
        .iter()
        .map(|row| {
            let source = row.matrix();
            let zero = Complex64::try_new(0.0, 0.0).map_err(|_| {
                DirectRunErrorV1::Touchstone("invalid zero S4P matrix sample".to_owned())
            })?;
            let mut matrix = [[zero; 4]; 4];
            for (output, row) in matrix.iter_mut().enumerate() {
                for (incident, value) in row.iter_mut().enumerate() {
                    *value = source.at(output, incident).ok_or_else(|| {
                        DirectRunErrorV1::Touchstone("S4P matrix index".to_owned())
                    })?;
                }
            }
            Ok(matrix)
        })
        .collect::<Result<Vec<_>, DirectRunErrorV1>>()?;
    let mixed = com_mixed_mode_spectrum_v1(&samples);
    let sdd21 = mixed.iter().map(|sample| sample[3][1]).collect::<Vec<_>>();
    let sdd11 = mixed.iter().map(|sample| sample[1][1]).collect::<Vec<_>>();
    let result = s21_to_impulse_dc_v1(&sdd21, &frequency_hz, &FdToTdOptionsV1::default())
        .map_err(|error| DirectRunErrorV1::Channel(format!("S4P FD-to-TD: {error:?}")))?;
    let reflection = s21_to_impulse_dc_v1(&sdd11, &frequency_hz, &FdToTdOptionsV1::default())
        .ok()
        .and_then(|value| {
            validate_impulse_v1(&value.voltage)
                .ok()
                .map(|_| value.voltage)
        });
    validate_impulse_v1(&result.voltage)?;
    Ok(ImpulseInputV1 {
        values: result.voltage,
        erl_values: reflection,
        erl_time_s: Some(result.time_s.clone()),
        source_sha256,
        sample_interval_s: result
            .time_s
            .windows(2)
            .next()
            .map(|pair| pair[1] - pair[0]),
        source_kind: "touchstone-four-port-sdd21-fd-to-td-impulse",
        already_pulse: false,
        causality_correction_db: Some(result.causality_correction_db),
        truncation_db: Some(result.truncation_db),
        causality_iterations: Some(result.causality_iterations),
    })
}

fn load_s4p_calibration_document_v1(path: &Path) -> Result<Value, DirectRunErrorV1> {
    let bytes = bounded_read_v1(path, MAX_IMPULSE_FILE_BYTES_V1)?;
    let limits = touchstone_limits_v1()?;
    let parsed = parse_selected_four_port_hz_s_ri_50_v2(&bytes, limits)
        .map_err(|error| DirectRunErrorV1::Touchstone(format!("{error:?}")))?;
    let mut frequency_hz = Vec::with_capacity(parsed.rows().len());
    let mut samples = Vec::with_capacity(parsed.rows().len());
    for row in parsed.rows() {
        frequency_hz.push(row.frequency_hz());
        let matrix = row.matrix();
        let mut sample = Vec::with_capacity(4);
        for output in 0..4 {
            let mut values = Vec::with_capacity(4);
            for incident in 0..4 {
                let value = matrix
                    .at(output, incident)
                    .ok_or_else(|| DirectRunErrorV1::Touchstone("S4P matrix index".to_owned()))?;
                values.push(json!([value.real(), value.imaginary()]));
            }
            sample.push(Value::Array(values));
        }
        samples.push(Value::Array(sample));
    }
    Ok(json!({"frequency_hz": frequency_hz, "s4p": samples}))
}

fn parse_td_csv_values_v1(bytes: &[u8], path: &Path) -> Result<Vec<f64>, DirectRunErrorV1> {
    let text = std::str::from_utf8(bytes).map_err(|error| DirectRunErrorV1::Input {
        path: path.display().to_string(),
        message: format!("TD CSV must be UTF-8: {error}"),
    })?;
    let mut values = Vec::new();
    for (line_index, line) in text.lines().enumerate() {
        let line = line.trim_start_matches('\u{feff}').trim();
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        let fields = line.split(',').map(str::trim).collect::<Vec<_>>();
        let numeric = fields
            .iter()
            .filter_map(|field| match sipi_com::csv_value_v1(field) {
                sipi_com::CellValueV1::Number(value) if value.is_finite() => Some(value),
                _ => None,
            })
            .collect::<Vec<_>>();
        if let Some(value) = numeric.last().copied() {
            values.push(value);
        } else if values.is_empty() {
            // Permit one textual header row; all subsequent rows must carry
            // a finite waveform value instead of silently dropping data.
            continue;
        } else {
            return Err(DirectRunErrorV1::Json(format!(
                "TD CSV row {} has no finite numeric waveform value",
                line_index + 1
            )));
        }
    }
    if values.is_empty() {
        return Err(DirectRunErrorV1::Json(
            "TD CSV contains no numeric waveform samples".to_owned(),
        ));
    }
    Ok(values)
}

fn load_frequency_domain_json_v1(
    document: &Value,
    source_sha256: String,
) -> Result<ImpulseInputV1, DirectRunErrorV1> {
    let frequency_hz = document
        .get("frequency_hz")
        .and_then(Value::as_array)
        .ok_or_else(|| DirectRunErrorV1::Json("frequency_hz must be an array".to_owned()))?
        .iter()
        .enumerate()
        .map(|(index, value)| {
            value
                .as_f64()
                .filter(|value| value.is_finite())
                .ok_or_else(|| {
                    DirectRunErrorV1::Json(format!("frequency_hz[{index}] is not finite"))
                })
        })
        .collect::<Result<Vec<_>, _>>()?;
    let s21_values = document
        .get("s21")
        .and_then(Value::as_array)
        .ok_or_else(|| {
            DirectRunErrorV1::Json("s21 must be an array of [real, imaginary] pairs".to_owned())
        })?
        .iter()
        .enumerate()
        .map(|(index, value)| {
            let pair = value.as_array().ok_or_else(|| {
                DirectRunErrorV1::Json(format!("s21[{index}] must be a [real, imaginary] pair"))
            })?;
            if pair.len() != 2 {
                return Err(DirectRunErrorV1::Json(format!(
                    "s21[{index}] must contain exactly two numbers"
                )));
            }
            let real = pair[0]
                .as_f64()
                .filter(|value| value.is_finite())
                .ok_or_else(|| DirectRunErrorV1::Json(format!("s21[{index}][0] is not finite")))?;
            let imaginary = pair[1]
                .as_f64()
                .filter(|value| value.is_finite())
                .ok_or_else(|| DirectRunErrorV1::Json(format!("s21[{index}][1] is not finite")))?;
            Complex64::try_new(real, imaginary)
                .map_err(|_| DirectRunErrorV1::Json(format!("s21[{index}] is not finite")))
        })
        .collect::<Result<Vec<_>, _>>()?;
    let mut options = FdToTdOptionsV1::default();
    let controls = document.get("fd_to_td").unwrap_or(document);
    if let Some(value) = controls.get("sample_dt_s").and_then(Value::as_f64) {
        options.sample_dt_s = value;
    }
    if let Some(value) = controls.get("magnitude_policy").and_then(Value::as_str) {
        options.magnitude_policy = value.to_owned();
    }
    if let Some(value) = controls.get("phase_policy").and_then(Value::as_str) {
        options.phase_policy = value.to_owned();
    }
    if let Some(value) = controls.get("enforce_causality").and_then(Value::as_bool) {
        options.enforce_causality = value;
    }
    if let Some(value) = controls.get("ec_pulse_tolerance").and_then(Value::as_f64) {
        options.ec_pulse_tolerance = value;
    }
    if let Some(value) = controls
        .get("ec_relative_tolerance")
        .and_then(Value::as_f64)
    {
        options.ec_relative_tolerance = value;
    }
    if let Some(value) = controls
        .get("ec_difference_tolerance")
        .and_then(Value::as_f64)
    {
        options.ec_difference_tolerance = value;
    }
    if let Some(value) = controls.get("truncation_threshold").and_then(Value::as_f64) {
        options.truncation_threshold = value;
    }
    if let Some(value) = controls.get("debug").and_then(Value::as_bool) {
        options.debug = value;
    }
    if let Some(value) = controls.get("max_iterations").and_then(Value::as_u64) {
        options.max_iterations = usize::try_from(value).map_err(|_| {
            DirectRunErrorV1::Json("max_iterations does not fit the platform usize".to_owned())
        })?;
    }
    let result = s21_to_impulse_dc_v1(&s21_values, &frequency_hz, &options)
        .map_err(|error| DirectRunErrorV1::Channel(format!("fd-to-td: {error:?}")))?;
    validate_impulse_v1(&result.voltage)?;
    let sample_interval_s = result
        .time_s
        .windows(2)
        .next()
        .map(|pair| pair[1] - pair[0]);
    Ok(ImpulseInputV1 {
        values: result.voltage,
        erl_values: None,
        erl_time_s: None,
        source_sha256,
        sample_interval_s,
        source_kind: "json-s21-fd-to-td-impulse",
        already_pulse: false,
        causality_correction_db: Some(result.causality_correction_db),
        truncation_db: Some(result.truncation_db),
        causality_iterations: Some(result.causality_iterations),
    })
}

fn validate_impulse_v1(values: &[f64]) -> Result<(), DirectRunErrorV1> {
    if values.is_empty() {
        return Err(DirectRunErrorV1::Unsupported(
            "channel impulse must contain at least one sample".to_owned(),
        ));
    }
    for (index, value) in values.iter().enumerate() {
        if !value.is_finite() {
            return Err(DirectRunErrorV1::NonFiniteImpulse { index });
        }
    }
    Ok(())
}

fn admission_request_bytes_v1(
    request: &DirectRunRequestV1,
    controls: &BTreeMap<String, ResolvedDefaultV1>,
) -> Result<Vec<u8>, DirectRunErrorV1> {
    let root = request
        .output_dir
        .to_str()
        .ok_or_else(|| DirectRunErrorV1::InvalidRequest("output path is not UTF-8".to_owned()))?;
    let signal = controls
        .get("A_v")
        .and_then(|value| match value {
            ResolvedDefaultV1::Scalar(value) => Some(*value),
            ResolvedDefaultV1::Vector(values) if values.len() == 1 => Some(values[0]),
            _ => None,
        })
        .ok_or_else(|| DirectRunErrorV1::Parameters("A_v must be a scalar".to_owned()))?;
    serde_json::to_vec(&json!({
        "schema": "sipi.com.run-request.v1",
        "artifact_root": root,
        "artifact_id": request.artifact_id,
        "params": {"A_v": signal}
    }))
    .map_err(|error| DirectRunErrorV1::Json(error.to_string()))
}

fn metric_db_value_v1(value: f64) -> Result<Value, DirectRunErrorV1> {
    if value.is_nan() {
        return Err(DirectRunErrorV1::Parameters(
            "ERL dB metric cannot be NaN".to_owned(),
        ));
    }
    Ok(if value.is_finite() {
        json!(value)
    } else if value.is_sign_negative() {
        json!("-inf")
    } else {
        json!("inf")
    })
}

#[allow(clippy::too_many_arguments)]
fn result_value_v1(
    request: &DirectRunRequestV1,
    config: &LoadedConfigV1,
    impulse: &ImpulseInputV1,
    fext_inputs: &[ImpulseInputV1],
    next_inputs: &[ImpulseInputV1],
    generated_fext: &[Vec<f64>],
    generated_next: &[Vec<f64>],
    envelope: &ComRunResultEnvelopeV1,
    portable_diagnostics: &Value,
    chain_pulse: &[f64],
    fext_pulses: &[Vec<f64>],
    next_pulses: &[Vec<f64>],
    selected_fom_db: Option<f64>,
    calibration_sigma_bn_v: Option<f64>,
    calibration_sigma_ne_v: Option<f64>,
    calibration_sigma_hp_v: Option<f64>,
) -> Value {
    let mut fext_manifest = fext_inputs
        .iter()
        .map(channel_input_value_v1)
        .collect::<Vec<_>>();
    fext_manifest.extend(
        generated_fext
            .iter()
            .map(|values| channel_input_value_from_values_v1(values, "equalized-channel-impulse")),
    );
    let mut next_manifest = next_inputs
        .iter()
        .map(channel_input_value_v1)
        .collect::<Vec<_>>();
    next_manifest.extend(
        generated_next
            .iter()
            .map(|values| channel_input_value_from_values_v1(values, "equalized-channel-impulse")),
    );
    json!({
        "schema_version": 1,
        "source_revision": "r480",
        "profile": {
            "source_revision": "r480",
            "reader_semantics": request.reader.as_deref().unwrap_or("r480"),
            "fix_ids": request.fix_ids,
            "name": config.profile,
        },
        "cases": [{
            "case_index": 0,
            "channels": {
                "thru": request.pulse,
                "fext": request.fext,
                "next": request.next,
                // Keep the source channel identity in the public payload.  The
                // upstream CaseResult carries this path; dropping it here made
                // calibration runs look like ordinary COM cases to consumers.
                "calibration_noise": request.calibration_noise,
            },
            "metrics": {
                "FOM": selected_fom_db,
                "ERL": portable_diagnostics.get("erl_only").and_then(|value| value.get("erl_db")),
                "ERL11": portable_diagnostics.get("erl_only").and_then(|value| value.get("erl11_db")),
                "ERL_RMS": portable_diagnostics.get("erl_only").and_then(|value| value.get("erl_rms_db")),
                "ERL_phase_index": portable_diagnostics.get("erl_only").and_then(|value| value.get("phase_index")),
                "COM_dB": envelope.com_db(),
                "VEC_dB": envelope.vec_db(),
                "VEO_mV": envelope.veo_mv(),
                "sigma_N_V": envelope.sigma_n_v(),
                "available_signal_v": envelope.available_signal_v(),
                "interference_noise_v": envelope.interference_noise_v(),
                "threshold_der": envelope.threshold_der(),
                "eye_opening_v": envelope.eye_opening_v(),
                "calibration_sigma_bn_v": calibration_sigma_bn_v,
                "calibration_sigma_ne_v": calibration_sigma_ne_v,
                "calibration_sigma_hp_v": calibration_sigma_hp_v,
                "impulse_sample_count": impulse.values.len(),
                "impulse_first_sample": impulse.values.first().copied(),
                "impulse_last_sample": impulse.values.last().copied(),
            },
            "diagnostics": {
                "channel_impulse": {
                    "sample_count": impulse.values.len(),
                    "sample_interval_s": impulse.sample_interval_s,
                    "sha256": sha256_f64_v1(&impulse.values),
                    "source_kind": impulse.source_kind,
                    "causality_correction_db": impulse.causality_correction_db,
                    "truncation_db": impulse.truncation_db,
                    "causality_iterations": impulse.causality_iterations
                },
                "channel_pulse": {
                    "sample_count": chain_pulse.len(),
                    "sha256": sha256_f64_v1(chain_pulse),
                    "source_kind": "rectangular-pulse-response"
                },
                "com_execution": {
                    "schema": envelope.schema(),
                    "policy": envelope.policy(),
                    "thru_selected_phase": envelope.thru_selected_phase(),
                    "fext_selected_phases": envelope.fext_selected_phases(),
                    "next_selected_phases": envelope.next_selected_phases()
                },
                "crosstalk_inputs": {
                    "policy": "sipi.p5-06f.com-chain-v1.fext-next-residual-noise-pdf",
                    "integrated_into_metrics": !fext_manifest.is_empty() || !next_manifest.is_empty(),
                    "fext": fext_manifest,
                    "next": next_manifest,
                    "fext_pulses": fext_pulses.iter().map(|values| json!({
                        "sample_count": values.len(),
                        "sha256": sha256_f64_v1(values),
                        "source_kind": "rectangular-pulse-response"
                    })).collect::<Vec<_>>(),
                    "next_pulses": next_pulses.iter().map(|values| json!({
                        "sample_count": values.len(),
                        "sha256": sha256_f64_v1(values),
                        "source_kind": "rectangular-pulse-response"
                    })).collect::<Vec<_>>(),
                },
                "portable_branches": portable_diagnostics
            },
            "warnings": []
        }],
        "provenance": {
            "platform": std::env::consts::OS,
            "python_version": "not_applicable",
            "direct_port_schema": COM_DIRECT_RESULT_SCHEMA_V1,
            "config_sha256": config.source_sha256,
            "channel_source_sha256": impulse.source_sha256,
            "channel_source_kind": impulse.source_kind,
            "impulse_sha256": sha256_f64_v1(&impulse.values),
            "sample_interval_s": impulse.sample_interval_s,
        },
        "input_manifest": {
            "config": request.config.to_string_lossy(),
            "pulse": request.pulse.to_string_lossy(),
            "fext": request.fext,
            "next": request.next,
            "calibration_noise": request.calibration_noise,
            "artifact_id": request.artifact_id,
            "legacy_csv_requested": request.legacy_csv,
        },
        "report_manifest": {
            "kind": "diagnostic_fallback",
            "expected_figure_count": 0,
            "actual_figure_count": 0,
            "figures": [],
            "plotting": {
                "status": "external_blocked",
                "reason": "reporting plot format is non-core and no external renderer is bundled"
            }
        },
        "warnings": [],
        "timings_s": {"load_config": 0.0, "run_com": 0.0, "write_artifacts": 0.0}
    })
}

fn channel_input_value_v1(input: &ImpulseInputV1) -> Value {
    json!({
        "sample_count": input.values.len(),
        "sample_interval_s": input.sample_interval_s,
        "source_kind": input.source_kind,
        "source_sha256": input.source_sha256,
        "impulse_sha256": sha256_f64_v1(&input.values),
        "causality_correction_db": input.causality_correction_db,
        "truncation_db": input.truncation_db,
        "causality_iterations": input.causality_iterations,
    })
}

fn channel_input_value_from_values_v1(values: &[f64], source_kind: &str) -> Value {
    json!({
        "sample_count": values.len(),
        "sample_interval_s": null,
        "source_kind": source_kind,
        "source_sha256": null,
        "impulse_sha256": sha256_f64_v1(values),
        "causality_correction_db": null,
        "truncation_db": null,
        "causality_iterations": null,
    })
}

fn report_html_v1(result: &Value) -> Result<String, DirectRunErrorV1> {
    let pretty = serde_json::to_string_pretty(result)
        .map_err(|error| DirectRunErrorV1::Artifact(error.to_string()))?;
    Ok(format!(
        "<!doctype html><meta charset=\"utf-8\"><title>COM run</title><h1>COM run</h1><pre>{}</pre>\n",
        html_escape_v1(&pretty)
    ))
}

fn diagnostics_json_v1(result: &Value) -> Result<String, DirectRunErrorV1> {
    let diagnostics = json!({
        "schema": "sipi.com.direct-run-diagnostics.v1",
        "semantic_payload": result.get("cases"),
        "waveform": result.get("provenance").and_then(|value| value.get("impulse_sha256")),
    });
    serde_json::to_string_pretty(&diagnostics)
        .map_err(|error| DirectRunErrorV1::Artifact(error.to_string()))
}

fn html_escape_v1(value: &str) -> String {
    value
        .replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
}

fn atomic_write_v1(path: &Path, bytes: &[u8], overwrite: bool) -> Result<(), DirectRunErrorV1> {
    let temporary = path.with_extension(format!(
        "{}.tmp-{}",
        path.extension()
            .and_then(|value| value.to_str())
            .unwrap_or("file"),
        std::process::id()
    ));
    fs::write(&temporary, bytes).map_err(|error| DirectRunErrorV1::Artifact(error.to_string()))?;
    if overwrite && path.exists() {
        fs::remove_file(path).map_err(|error| DirectRunErrorV1::Artifact(error.to_string()))?;
    }
    fs::rename(&temporary, path).map_err(|error| {
        let _ = fs::remove_file(&temporary);
        DirectRunErrorV1::Artifact(error.to_string())
    })
}

/// Publish the source-frozen legacy output schema with typed MATLAB-compatible
/// scalar/array serialization.  Values absent from the portable result remain
/// empty cells, matching the upstream exporter rather than inventing metrics.
const LEGACY_OUTPUT_COLUMNS_V1: &[&str] = &[
    "code_revision",
    "config_file",
    "Z11est",
    "Z22est",
    "tfx_estimate",
    "ERL11",
    "ERL22",
    "ERL",
    "ICN_mV",
    "MDNEXT_ICN_92_46_mV",
    "MDFEXT_ICN_92_47_mV",
    "fitted_IL_dB_at_Fnq",
    "cable__assembley_loss",
    "loss_with_PCB",
    "VIP_to_VMP_IL_dB_at_Fnq",
    "IL_dB_channel_only_at_Fnq",
    "VTF_loss_dB_at_Fnq",
    "IL_db_die_to_die_at_Fnq",
    "FOM_TDILN",
    "TD_ILN",
    "FOM_RILN",
    "FOM_ILD",
    "VMC_HF_mV",
    "SCMR_dB",
    "VMA",
    "file_names",
    "R_diepad",
    "C_diepad",
    "L_comp",
    "C_bump",
    "levels",
    "Pkg_len_TX",
    "Pkg_len_NEXT",
    "Pkg_len_FEXT",
    "Pkg_len_RX",
    "pkg_Z_c",
    "C_v",
    "baud_rate_GHz",
    "f_Nyquist_GHz",
    "BER",
    "FOM",
    "sigma_N",
    "DFE4_RSS",
    "DFE2_RSS",
    "tail_RSS",
    "channel_operating_margin_dB",
    "available_signal_after_eq_mV",
    "peak_uneq_pulse_mV",
    "uneq_FIR_peak_time",
    "steady_state_voltage_mV",
    "steady_state_voltage_weq_mV",
    "sigma_bn",
    "Peak_ISI_XTK_and_Noise_interference_at_BER_mV",
    "peak_ISI_XTK_interference_at_BER_mV",
    "peak_ISI_interference_at_BER_mV",
    "equivalent_ICI_sigma_assuming_PDF_is_Gaussian_mV",
    "peak_MDXTK_interference_at_BER_mV",
    "peak_MDNEXT_interference_at_BER_mV",
    "peak_MDFEXT_interference_at_BER_mV",
    "equivalent_ICN_assuming_Gaussian_PDF_mV",
    "SNR_ISI_XTK_normalized_1_sigma",
    "SNR_ISI_est",
    "Pmax_by_Vf_est",
    "Tr_measured_from_step_ps",
    "CTLE_zero_poles",
    "CTLE_DC_gain_dB",
    "g_DC_HP",
    "HP_poles_zero",
    "TXLE_taps",
    "Pre2Pmax",
    "DFE_taps",
    "floating_tap_locations",
    "RxFFE",
    "RxFFEgain",
    "itick",
    "error_propagation_probability",
    "burst_probabilities",
    "sgm_Ani__isi_xt_noise",
    "sgm_isi_xt",
    "sgm_noise__gaussian_noise_p_DD",
    "sgm_p_DD",
    "sgm_gaussian_noise",
    "sgm_G",
    "sgm_rjit",
    "sgm_N",
    "sgm_TX",
    "sgm_isi",
    "sgm_xt",
    "VEC_dB",
    "VEO_mV",
    "EW_UI_est",
    "eye_contour",
    "VEO_window_mUI",
    "sigma_ACCM_at_tp0_mV",
    "sigma_AC_CCM_at_rxpkg_output_mV",
    "COM_dB",
    "DER_thresh",
    "rtmin",
];

fn matlab_number_v1(value: f64) -> String {
    if !value.is_finite() {
        return if value.is_nan() {
            "NaN".to_owned()
        } else if value.is_sign_positive() {
            "Inf".to_owned()
        } else {
            "-Inf".to_owned()
        };
    }
    if value == 0.0 {
        return "0".to_owned();
    }
    // MATLAB's `%g` emits fifteen significant digits, unlike Rust's fixed
    // precision formatter which emits fifteen digits after the decimal.
    // Select fixed/scientific notation at the same practical thresholds and
    // trim insignificant zeroes without changing the numeric payload.
    let magnitude = value.abs();
    let mut text = if (1.0e-4..1.0e15).contains(&magnitude) {
        let exponent = magnitude.log10().floor() as i32;
        let decimals = (14 - exponent).max(0) as usize;
        format!("{value:.*}", decimals)
    } else {
        format!("{value:.14e}")
    };
    if let Some((mantissa, exponent)) = text.split_once('e') {
        let mantissa = mantissa
            .trim_end_matches('0')
            .trim_end_matches('.')
            .to_owned();
        let exponent_value = exponent.parse::<i32>().unwrap_or(0);
        text = format!("{mantissa}e{exponent_value:+}");
    }
    while text.ends_with('0') {
        text.pop();
    }
    if text.ends_with('.') {
        text.pop();
    }
    text
}

fn matlab_csv_value_v1(value: Option<&Value>) -> Result<String, DirectRunErrorV1> {
    let Some(value) = value else {
        return Ok(String::new());
    };
    match value {
        Value::Null => Ok(String::new()),
        Value::Bool(value) => Ok(if *value { "1" } else { "0" }.to_owned()),
        Value::Number(value) => value.as_f64().map(matlab_number_v1).ok_or_else(|| {
            DirectRunErrorV1::Artifact("legacy CSV number is not finite".to_owned())
        }),
        Value::String(value) => Ok(value.clone()),
        Value::Object(_) => Ok("struct".to_owned()),
        Value::Array(values) => {
            if values.iter().all(|item| !item.is_array()) {
                let entries = values
                    .iter()
                    .map(|item| matlab_csv_value_v1(Some(item)))
                    .collect::<Result<Vec<_>, _>>()?;
                return Ok(format!("[{}]", entries.join(" ")));
            }
            if values.iter().all(|item| item.as_array().is_some()) {
                let rows = values
                    .iter()
                    .map(|item| {
                        let row = item.as_array().ok_or_else(|| {
                            DirectRunErrorV1::Artifact(
                                "legacy CSV array rank changed during serialization".to_owned(),
                            )
                        })?;
                        row.iter()
                            .map(|cell| matlab_csv_value_v1(Some(cell)))
                            .collect::<Result<Vec<_>, _>>()
                            .map(|values| values.join(" "))
                    })
                    .collect::<Result<Vec<_>, _>>()?;
                return Ok(format!("[{}]", rows.join(";")));
            }
            Err(DirectRunErrorV1::Artifact(
                "legacy CSV does not support mixed-rank arrays".to_owned(),
            ))
        }
    }
}

fn legacy_csv_field_v1(value: &str) -> String {
    if value
        .chars()
        .any(|character| matches!(character, ',' | '"' | '\n' | '\r'))
    {
        format!("\"{}\"", value.replace('"', "\"\""))
    } else {
        value.to_owned()
    }
}

fn write_legacy_csv_v1(
    path: &Path,
    result: &Value,
    overwrite: bool,
) -> Result<(), DirectRunErrorV1> {
    let case = result
        .get("cases")
        .and_then(Value::as_array)
        .and_then(|cases| cases.first())
        .ok_or_else(|| {
            DirectRunErrorV1::Artifact("result has no case for legacy CSV".to_owned())
        })?;
    let metrics = case
        .get("metrics")
        .and_then(Value::as_object)
        .ok_or_else(|| DirectRunErrorV1::Artifact("result case has no metrics".to_owned()))?;
    let mut values = BTreeMap::<String, Value>::new();
    values.insert("code_revision".to_owned(), json!(result["source_revision"]));
    if let Some(config) = result
        .get("input_manifest")
        .and_then(|manifest| manifest.get("config"))
    {
        values.insert("config_file".to_owned(), config.clone());
    }
    for key in [
        "FOM",
        "VEC_dB",
        "VEO_mV",
        "sigma_N",
        "COM_dB",
        "DER_thresh",
        "BER",
    ] {
        if let Some(value) = metrics.get(key) {
            values.insert(key.to_owned(), value.clone());
        }
    }
    if let Some(value) = metrics
        .get("sigma_N_V")
        .and_then(Value::as_f64)
        .filter(|value| value.is_finite())
    {
        values.insert("sigma_N".to_owned(), json!(value * 1000.0));
    }
    if let Some(value) = metrics.get("threshold_der") {
        values.insert("DER_thresh".to_owned(), value.clone());
    }
    if let Some(value) = metrics
        .get("available_signal_v")
        .and_then(Value::as_f64)
        .filter(|value| value.is_finite())
    {
        values.insert(
            "available_signal_after_eq_mV".to_owned(),
            json!(value * 1000.0),
        );
    }
    if let Some(value) = metrics
        .get("calibration_sigma_bn_v")
        .and_then(Value::as_f64)
        .filter(|value| value.is_finite())
    {
        values.insert("sigma_bn".to_owned(), json!(value * 1000.0));
    }
    if let Some(branches) = case
        .get("diagnostics")
        .and_then(|value| value.get("portable_branches"))
        .and_then(Value::as_object)
    {
        if let Some(tdiln) = branches.get("tdiln").and_then(Value::as_object)
            && let Some(value) = tdiln.get("snr_isi_fom_pdf_db")
        {
            values.insert("FOM_TDILN".to_owned(), value.clone());
        }
        if let Some(search) = branches
            .get("rx_ffe_search")
            .or_else(|| branches.get("mmse"))
            .and_then(Value::as_object)
        {
            for (target, source) in [("RxFFEgain", "rx_ffe_gain_db"), ("itick", "itick")] {
                if let Some(value) = search.get(source) {
                    values.insert(target.to_owned(), value.clone());
                }
            }
            for (target, source) in [("RxFFE", "taps"), ("DFE_taps", "dfe_taps")] {
                if let Some(value) = search.get(source) {
                    values.insert(target.to_owned(), value.clone());
                }
            }
        }
    }
    let header = LEGACY_OUTPUT_COLUMNS_V1.join(",");
    let row = LEGACY_OUTPUT_COLUMNS_V1
        .iter()
        .map(|column| {
            matlab_csv_value_v1(values.get(*column)).map(|value| legacy_csv_field_v1(&value))
        })
        .collect::<Result<Vec<_>, _>>()?
        .join(",");
    reject_symlink_chain_v1(path).map_err(DirectRunErrorV1::Artifact)?;
    if path.exists() && !overwrite {
        return Err(DirectRunErrorV1::Artifact(format!(
            "output already exists: {}",
            path.display()
        )));
    }
    atomic_write_v1(path, format!("{header}\n{row}\n").as_bytes(), overwrite)
}

fn bounded_read_v1(path: &Path, limit: u64) -> Result<Vec<u8>, DirectRunErrorV1> {
    reject_symlink_chain_v1(path).map_err(|message| DirectRunErrorV1::Input {
        path: path.display().to_string(),
        message,
    })?;
    let metadata = fs::symlink_metadata(path).map_err(|error| DirectRunErrorV1::Input {
        path: path.display().to_string(),
        message: error.to_string(),
    })?;
    if metadata.file_type().is_symlink() || !metadata.is_file() {
        return Err(DirectRunErrorV1::Input {
            path: path.display().to_string(),
            message: "input must be a non-symlink regular file".to_owned(),
        });
    }
    if metadata.len() > limit {
        return Err(DirectRunErrorV1::InputLimit {
            path: path.display().to_string(),
            limit,
        });
    }
    fs::read(path).map_err(|error| DirectRunErrorV1::Input {
        path: path.display().to_string(),
        message: error.to_string(),
    })
}

fn reject_symlink_chain_v1(path: &Path) -> Result<(), String> {
    let mut current = path.to_path_buf();
    loop {
        match fs::symlink_metadata(&current) {
            Ok(metadata) if metadata.file_type().is_symlink() => {
                return Err(format!(
                    "symlink path component is not admitted: {}",
                    current.display()
                ));
            }
            Ok(_) => {}
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            Err(error) => return Err(error.to_string()),
        }
        let Some(parent) = current.parent() else {
            break;
        };
        if parent == current {
            break;
        }
        current = parent.to_path_buf();
    }
    Ok(())
}

fn sha256_bytes_v1(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

fn sha256_f64_v1(values: &[f64]) -> String {
    let mut digest = Sha256::new();
    for value in values {
        digest.update(value.to_le_bytes());
    }
    format!("{:x}", digest.finalize())
}

fn sha256_complex_v1(values: &[Complex64]) -> String {
    let mut digest = Sha256::new();
    for value in values {
        digest.update(value.real().to_le_bytes());
        digest.update(value.imaginary().to_le_bytes());
    }
    format!("{:x}", digest.finalize())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn temp_root(name: &str) -> PathBuf {
        let root =
            std::env::temp_dir().join(format!("sipi-com-direct-{name}-{}", std::process::id()));
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(&root).expect("temporary test root");
        root
    }

    fn canonical_parameters() -> Value {
        json!({
            "parameters": {
                "samples_per_ui": 8.0,
                "LEVELS": 4.0,
                "bin_size": 0.001,
                "A_v": 0.5,
                "R_LM": 50.0,
                "SNR_TX": 30.0,
                "sigma_X": 0.03,
                "sigma_RJ": 1.0e-4,
                "h_J": [0.3, 0.5, 0.2],
                "sigma_N": 0.01,
                "A_DD": 0.4,
                "spec_ber": 1.0e-4
            }
        })
    }

    fn pulse_bytes() -> Vec<u8> {
        // The direct-run contract admits impulse files.  Keep the historical
        // sinusoid as the expected rectangular pulse by writing its discrete
        // derivative, so the COM boundary integration reconstructs it.
        (0..64)
            .scan(0.0, |previous, index| {
                let pulse = 0.02 * (index as f64 * 0.21).sin();
                let impulse = pulse - *previous;
                *previous = pulse;
                Some(impulse)
            })
            .flat_map(f64::to_le_bytes)
            .collect()
    }

    #[test]
    fn public_workflow_emits_semantic_result_and_waveform_digest() {
        let root = temp_root("workflow");
        let config = root.join("params.json");
        let pulse = root.join("pulse.f64le");
        let output = root.join("artifacts");
        fs::write(
            &config,
            serde_json::to_vec(&canonical_parameters()).unwrap(),
        )
        .unwrap();
        fs::write(&pulse, pulse_bytes()).unwrap();
        let request = DirectRunRequestV1::new(&config, &pulse, &output);
        let report = load_config_run_com_write_artifacts_v1(&request).expect("run succeeds");
        assert_eq!(
            report.workflow,
            vec!["load_config", "run_com", "write_artifacts"]
        );
        assert_eq!(report.impulse_sample_count, 64);
        assert!(report.result["cases"][0]["metrics"]["COM_dB"].is_number());
        assert!(report.result["cases"][0]["metrics"]["interference_noise_v"].is_number());
        assert!(report.result["cases"][0]["metrics"]["threshold_der"].is_number());
        assert_eq!(
            report.result["provenance"]["impulse_sha256"],
            report.impulse_sha256
        );
        assert!(report.artifacts.result_json.is_file());
        assert!(report.artifacts.report_html.is_file());
        assert!(report.artifacts.diagnostics_json.is_file());
        let published_result: Value = serde_json::from_slice(
            &fs::read(&report.artifacts.result_json).expect("published result"),
        )
        .expect("result JSON");
        assert_eq!(
            published_result["cases"][0]["metrics"]["COM_dB"],
            report.result["cases"][0]["metrics"]["COM_dB"]
        );
        let published_diagnostics =
            fs::read_to_string(&report.artifacts.diagnostics_json).expect("diagnostics");
        assert!(published_diagnostics.contains("semantic_payload"));
        assert!(
            fs::read_to_string(&report.artifacts.report_html)
                .expect("report")
                .contains("COM_dB")
        );
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn package_case_fanout_preserves_case_and_channel_identity() {
        let root = temp_root("package-cases");
        let config = root.join("params.json");
        let pulse = root.join("unused.f64le");
        let output = root.join("artifacts");
        let mut document = canonical_parameters();
        let base_impulse = pulse_bytes()
            .chunks_exact(8)
            .map(|chunk| f64::from_le_bytes(chunk.try_into().unwrap()))
            .collect::<Vec<_>>();
        let fext_impulse = base_impulse
            .iter()
            .map(|value| value * 0.1)
            .collect::<Vec<_>>();
        let next_impulse = base_impulse
            .iter()
            .map(|value| value * 0.2)
            .collect::<Vec<_>>();
        document["package_cases"] = json!([
            {"case_id": "pkg-a", "calibration_channel": "cal-a", "pulse": base_impulse, "fext": [fext_impulse]},
            {"case_id": "pkg-b", "pulse": base_impulse, "next": [next_impulse]}
        ]);
        fs::write(&config, serde_json::to_vec(&document).unwrap()).unwrap();
        fs::write(&pulse, pulse_bytes()).unwrap();
        let report = run_com_v1(&DirectRunRequestV1::new(&config, &pulse, &output))
            .expect("package fan-out");
        let cases = report.result["cases"].as_array().expect("cases");
        assert_eq!(cases.len(), 2);
        assert_eq!(cases[0]["case_id"], "pkg-a");
        assert_eq!(cases[1]["case_id"], "pkg-b");
        assert_eq!(cases[0]["channels"]["fext"].as_array().unwrap().len(), 1);
        assert_eq!(cases[1]["channels"]["next"].as_array().unwrap().len(), 1);
        assert_eq!(cases[0]["channel_identity"]["thru"], "pkg-a:thru");
        assert_eq!(cases[0]["channel_identity"]["fext"][0], "pkg-a:fext:0");
        assert_eq!(cases[0]["channel_identity"]["calibration"], "cal-a");
        assert_eq!(
            cases[1]["channel_identity"]["calibration"],
            "pkg-b:calibration"
        );
        assert!(report.result["provenance"]["package_cases"]["count"].is_number());
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn package_case_file_channels_preserve_source_and_calibration_identity() {
        let root = temp_root("package-case-files");
        let config = root.join("params.json");
        let pulse = root.join("fallback.json");
        let thru = root.join("thru.json");
        let fext = root.join("fext.json");
        let next = root.join("next.json");
        let calibration = root.join("calibration.json");
        let output = root.join("artifacts");
        let base_impulse = pulse_bytes()
            .chunks_exact(8)
            .map(|chunk| f64::from_le_bytes(chunk.try_into().unwrap()))
            .collect::<Vec<_>>();
        let fext_impulse = base_impulse
            .iter()
            .map(|value| value * 0.1)
            .collect::<Vec<_>>();
        let next_impulse = base_impulse
            .iter()
            .map(|value| value * 0.2)
            .collect::<Vec<_>>();
        let calibration_values = json!({
            "frequency_hz": [0.0, 1.0, 2.0, 3.0],
            "calibration_sdd21": [[1.0, 0.0], [1.0, 0.0], [1.0, 0.0], [1.0, 0.0]],
            "ctle_transfer": [[1.0, 0.0], [1.0, 0.0], [1.0, 0.0], [1.0, 0.0]],
            "fb_hz": 4.0,
            "f_r": 1.0,
            "f_hp_hz": 0.0,
            "sigma_bn_v": 1.0,
            "pass_threshold_db": 0.0,
            "initial_step_v": 2.0
        });
        let mut document = canonical_parameters();
        document["package_cases"] = json!([{
            "case_id": "file-case",
            "calibration_id": "cal-file",
            "pulse": "thru.json"
        }]);
        fs::write(&config, serde_json::to_vec(&document).unwrap()).unwrap();
        fs::write(
            &pulse,
            serde_json::to_vec(&json!({"impulse": base_impulse})).unwrap(),
        )
        .unwrap();
        fs::write(
            &thru,
            serde_json::to_vec(&json!({"impulse": base_impulse})).unwrap(),
        )
        .unwrap();
        fs::write(
            &fext,
            serde_json::to_vec(&json!({"impulse": fext_impulse})).unwrap(),
        )
        .unwrap();
        fs::write(
            &next,
            serde_json::to_vec(&json!({"impulse": next_impulse})).unwrap(),
        )
        .unwrap();
        fs::write(
            &calibration,
            serde_json::to_vec(&json!({"portable": {"calibration": calibration_values}})).unwrap(),
        )
        .unwrap();
        let mut request = DirectRunRequestV1::new(&config, &pulse, &output);
        request.calibration_noise = Some(calibration.clone());
        let report = run_com_v1(&request).expect("file-backed package case");
        let case = &report.result["cases"][0];
        assert_eq!(case["case_id"], "file-case");
        assert_eq!(case["channels"]["thru"], json!(thru));
        assert_eq!(case["channels"]["calibration_noise"], json!(calibration));
        let manifest = &report.result["provenance"]["package_cases"]["manifests"][0];
        assert_eq!(manifest["calibration"]["identity"], "cal-file");
        assert_eq!(manifest["calibration"]["source"], json!(calibration));
        assert_eq!(
            manifest["calibration"]["source_kind"],
            "json-calibration-channel"
        );
        assert_eq!(
            manifest["calibration"]["sha256"],
            sha256_bytes_v1(&fs::read(&calibration).unwrap())
        );
        assert_eq!(manifest["thru"]["source"], json!(thru));
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn package_calibration_and_crosstalk_are_mutually_exclusive() {
        let root = temp_root("package-calibration-crosstalk-exclusive");
        let config = root.join("params.json");
        let calibration = root.join("calibration.json");
        let pulse = root.join("pulse.f64le");
        let mut document = canonical_parameters();
        document["package_cases"] = json!([{
            "case_id": "exclusive",
            "pulse": pulse_bytes().iter().map(|_| 0.0).collect::<Vec<_>>(),
            "fext": [pulse_bytes().iter().map(|_| 0.0).collect::<Vec<_>>()]
        }]);
        fs::write(&config, serde_json::to_vec(&document).unwrap()).unwrap();
        fs::write(&pulse, pulse_bytes()).unwrap();
        fs::write(&calibration, b"{}").unwrap();
        let mut request = DirectRunRequestV1::new(&config, &pulse, root.join("out"));
        request.calibration_noise = Some(calibration);
        let error = run_com_v1(&request).expect_err("ChannelSet must reject mixed roles");
        assert!(
            matches!(error, DirectRunErrorV1::InvalidRequest(message) if message.contains("mutually exclusive"))
        );
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn package_channel_snapshot_preserves_already_pulse_after_source_mutation() {
        let root = temp_root("package-channel-snapshot");
        let source = root.join("thru.json");
        let stage = root.join("stage");
        let original = json!({"pulse": [0.0, 1.0, 0.0, 0.0]});
        fs::write(&source, serde_json::to_vec(&original).unwrap()).unwrap();
        let channel = parse_package_channel_v1(&json!("thru.json"), &root, "package.pulse")
            .expect("source snapshot");
        let original_sha = sha256_bytes_v1(&serde_json::to_vec(&original).unwrap());
        fs::write(&source, br#"{"pulse":[9.0,9.0,9.0,9.0]}"#).unwrap();
        fs::create_dir_all(&stage).unwrap();
        let staged = stage_package_channel_v1(&stage, "thru", 0, &channel).unwrap();
        let loaded = load_channel_input_v1(&staged).unwrap();
        assert!(channel.already_pulse);
        assert_eq!(channel.source_sha256, original_sha);
        assert_eq!(loaded.source_sha256, original_sha);
        assert_eq!(loaded.values, vec![0.0, 1.0, 0.0, 0.0]);
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn package_case_rejects_json_calibration_channel_alias() {
        let root = temp_root("package-calibration-alias");
        let config = root.join("params.json");
        let pulse = root.join("pulse.f64le");
        let mut document = canonical_parameters();
        document["package_cases"] = json!([{
            "case_id": "alias",
            "pulse": [0.0, 1.0, 0.0, 0.0],
            "calibration_channel": {"path": "controls.json"}
        }]);
        fs::write(&config, serde_json::to_vec(&document).unwrap()).unwrap();
        fs::write(&pulse, pulse_bytes()).unwrap();
        let error = run_com_v1(&DirectRunRequestV1::new(&config, &pulse, root.join("out")))
            .expect_err("JSON calibration controls must not become a channel");
        assert!(
            matches!(error, DirectRunErrorV1::Unsupported(message) if message.contains("per-case calibration"))
        );
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn erl_only_dispatch_publishes_return_loss_payload() {
        let root = temp_root("erl-only");
        let config = root.join("params.json");
        let pulse = root.join("pulse.f64le");
        let mut document = canonical_parameters();
        document["portable"] = json!({
            "erl_only": {
                "samples_per_ui": 8,
                "levels": 4,
                "bin_size": 1.0e-5,
                "spec_ber": 1.0e-4,
                "rl_norm_test": true
            }
        });
        fs::write(&config, serde_json::to_vec(&document).unwrap()).unwrap();
        fs::write(&pulse, pulse_bytes()).unwrap();
        let report = run_com_v1(&DirectRunRequestV1::new(
            &config,
            &pulse,
            root.join("artifacts"),
        ))
        .expect("ERL-only run");
        let case = &report.result["cases"][0];
        assert_eq!(
            case["diagnostics"]["portable_branches"]["erl_only"]["dispatch"],
            "r480.erl_only"
        );
        assert!(case["metrics"]["ERL"].is_number());
        assert!(case["metrics"]["ERL_phase_index"].is_number());
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn erl_only_does_not_enter_com_chain_when_cursor_is_absent() {
        let root = temp_root("erl-only-no-chain");
        let config = root.join("params.json");
        let pulse = root.join("flat.f64le");
        let mut document = canonical_parameters();
        document["portable"] = json!({
            "erl_only": {
                "samples_per_ui": 8,
                "levels": 4,
                "bin_size": 1.0e-5,
                "spec_ber": 1.0e-4,
                "rl_norm_test": true
            }
        });
        fs::write(&config, serde_json::to_vec(&document).unwrap()).unwrap();
        let flat = vec![0.01_f64; 64];
        let bytes = flat
            .iter()
            .flat_map(|value| value.to_le_bytes())
            .collect::<Vec<_>>();
        fs::write(&pulse, bytes).unwrap();
        let report = run_com_v1(&DirectRunRequestV1::new(
            &config,
            &pulse,
            root.join("artifacts"),
        ))
        .expect("ERL-only must bypass COM chain");
        let case = &report.result["cases"][0];
        assert!(case["metrics"]["ERL"].is_number());
        assert_eq!(case["metrics"]["ERL11"], case["metrics"]["ERL"]);
        assert!(case["metrics"]["COM_dB"].is_null());
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn missing_required_runtime_control_is_fail_closed() {
        let root = temp_root("missing-control");
        let config = root.join("params.json");
        let pulse = root.join("pulse.f64le");
        let output = root.join("artifacts");
        let mut values = canonical_parameters();
        values["parameters"].as_object_mut().unwrap().remove("h_J");
        fs::write(&config, serde_json::to_vec(&values).unwrap()).unwrap();
        fs::write(&pulse, pulse_bytes()).unwrap();
        let error = run_com_v1(&DirectRunRequestV1::new(&config, &pulse, &output)).unwrap_err();
        assert!(matches!(error, DirectRunErrorV1::Unsupported(message) if message.contains("h_J")));
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn crosstalk_channel_budget_fails_closed_before_file_reads() {
        let root = temp_root("crosstalk-budget");
        let mut request = DirectRunRequestV1::new(
            root.join("missing-config.json"),
            root.join("missing-thru.f64le"),
            root.join("artifacts"),
        );
        request.fext = (0..=MAX_CROSSTALK_CHANNELS_V1)
            .map(|index| root.join(format!("fext-{index}.f64le")))
            .collect();
        let error = run_com_v1(&request).expect_err("channel budget");
        assert!(matches!(error, DirectRunErrorV1::InputLimit { .. }));
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn touchstone_route_resolves_s21_to_impulse_without_fitting() {
        let root = temp_root("touchstone");
        let path = root.join("thru.s2p");
        let mut data = String::from("# Hz S RI R 50.0\n");
        for index in 0..64 {
            data.push_str(&format!("{} 0 0 1 0 1 0 0 0\n", index as f64 * 1.0e9));
        }
        fs::write(&path, data).unwrap();
        let input = load_impulse_v1(&path).expect("strict touchstone input");
        assert_eq!(
            input.source_kind,
            "touchstone-two-port-s21-fd-to-td-impulse"
        );
        assert!(!input.values.is_empty());
        assert_eq!(input.erl_values.as_ref().map(Vec::len), Some(1));
        assert!(input.causality_correction_db.is_some());
        assert!(input.truncation_db.is_some());
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn unadmitted_s2p_erl_profile_fails_closed_without_guessing_controls() {
        let root = temp_root("touchstone-erl-tdr");
        let path = root.join("erl.s2p");
        let mut data = String::from("# Hz S RI R 50.0\n");
        for index in 0..65 {
            let frequency = index as f64 * 26.56e9 / 64.0;
            let phase = -2.0 * std::f64::consts::PI * frequency * 1.0e-9;
            let pole = 26.56e9 / (10.0_f64 - 1.0).sqrt();
            let scale = 1.0 / (1.0 + (frequency / pole).powi(2));
            let real = scale * (phase.cos() + (frequency / pole) * phase.sin());
            let imaginary = scale * (phase.sin() - (frequency / pole) * phase.cos());
            data.push_str(&format!(
                "{frequency:.17e} 0.1 0 {real:.17e} {imaginary:.17e} {real:.17e} {imaginary:.17e} 0.1 0\n"
            ));
        }
        fs::write(&path, data).unwrap();
        let error =
            load_erl_s2p_impulse_v1(&path).expect_err("unadmitted profile must fail closed");
        assert!(
            matches!(error, DirectRunErrorV1::Channel(message) if message.contains("anti-causal"))
        );
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn frequency_domain_json_route_uses_portable_fd_to_td_impulse() {
        let root = temp_root("fd-to-td-json");
        let path = root.join("thru.json");
        let frequency_hz = (0..64)
            .map(|index| index as f64 * 1.0e9)
            .collect::<Vec<_>>();
        let s21 = frequency_hz
            .iter()
            .map(|frequency| {
                let magnitude =
                    (-(frequency / 8.0e10)).exp() * (1.0 + 0.1 * (frequency / 5.0e9).sin());
                let phase = -frequency / 2.0e10;
                json!([magnitude * phase.cos(), magnitude * phase.sin()])
            })
            .collect::<Vec<_>>();
        fs::write(
            &path,
            serde_json::to_vec(&json!({
                "frequency_hz": frequency_hz,
                "s21": s21,
                "fd_to_td": {
                    "sample_dt_s": 1.0e-12,
                    "magnitude_policy": "trend_to_DC",
                    "phase_policy": "interp_to_DC"
                }
            }))
            .unwrap(),
        )
        .unwrap();
        let input = load_impulse_v1(&path).expect("FD-to-TD JSON input");
        assert_eq!(input.source_kind, "json-s21-fd-to-td-impulse");
        assert!(input.values.len() > 1);
        assert!(input.sample_interval_s.is_some());
        assert!(input.causality_correction_db.is_some());
        assert!(input.truncation_db.is_some());
        assert_eq!(input.causality_iterations, Some(0));
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn td_csv_route_reads_time_and_waveform_columns_without_fitting() {
        let root = temp_root("td-csv");
        let path = root.join("channel.td.csv");
        fs::write(&path, "time_s,voltage_v\n0,0.1\n1e-12,0.2\n").unwrap();
        let input = load_impulse_v1(&path).expect("TD CSV input");
        assert_eq!(input.source_kind, "td-csv-impulse");
        assert_eq!(input.values, vec![0.1, 0.2]);
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn artifact_writer_requires_overwrite_and_preserves_result_semantics() {
        let root = temp_root("writer");
        let result = json!({
            "schema_version": 1,
            "source_revision": "r480",
            "profile": {"source_revision": "r480", "fix_ids": []},
            "cases": [{"case_index": 0, "metrics": {"COM_dB": 1.0}}],
            "provenance": {"stable": "same"},
            "warnings": [],
            "timings_s": {"write": 0.0}
        });
        write_run_artifacts_v1(&root, &result, false).expect("first write");
        let error = write_run_artifacts_v1(&root, &result, false).unwrap_err();
        assert!(
            matches!(error, DirectRunErrorV1::Artifact(message) if message.contains("already exists"))
        );
        fs::write(root.join("stale-previous-run.bin"), b"stale").expect("stale artifact");
        write_run_artifacts_v1(&root, &result, true).expect("overwrite");
        assert!(!root.join("stale-previous-run.bin").exists());
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn output_custody_rejects_input_ancestor_before_any_artifact_change() {
        let root = temp_root("output-custody-ancestor");
        let config = root.join("params.json");
        let pulse = root.join("pulse.f64le");
        fs::write(
            &config,
            serde_json::to_vec(&canonical_parameters()).unwrap(),
        )
        .unwrap();
        fs::write(&pulse, pulse_bytes()).unwrap();
        let config_hash = sha256_bytes_v1(&fs::read(&config).unwrap());
        let pulse_hash = sha256_bytes_v1(&fs::read(&pulse).unwrap());
        let request = DirectRunRequestV1::new(&config, &pulse, &root);
        let error = run_com_v1(&request).expect_err("output ancestor must be rejected");
        assert!(
            matches!(error, DirectRunErrorV1::InvalidRequest(message) if message.contains("overlaps input"))
        );
        assert_eq!(sha256_bytes_v1(&fs::read(&config).unwrap()), config_hash);
        assert_eq!(sha256_bytes_v1(&fs::read(&pulse).unwrap()), pulse_hash);
        assert!(!root.join("result.json").exists());
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn output_custody_rejects_hardlink_alias_before_rename() {
        let root = temp_root("output-custody-hardlink");
        let config = root.join("params.json");
        let pulse = root.join("pulse.f64le");
        let alias = root.join("output-alias");
        fs::write(
            &config,
            serde_json::to_vec(&canonical_parameters()).unwrap(),
        )
        .unwrap();
        fs::write(&pulse, pulse_bytes()).unwrap();
        fs::hard_link(&config, &alias).expect("hardlink alias");
        let config_hash = sha256_bytes_v1(&fs::read(&config).unwrap());
        let alias_hash = sha256_bytes_v1(&fs::read(&alias).unwrap());
        let request = DirectRunRequestV1::new(&config, &pulse, &alias);
        let error = run_com_v1(&request).expect_err("hardlink output alias must be rejected");
        assert!(
            matches!(error, DirectRunErrorV1::InvalidRequest(message) if message.contains("overlaps input"))
        );
        assert_eq!(sha256_bytes_v1(&fs::read(&config).unwrap()), config_hash);
        assert_eq!(sha256_bytes_v1(&fs::read(&alias).unwrap()), alias_hash);
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn output_custody_rejects_reuse_workbook_path_after_config_load() {
        let root = temp_root("output-custody-workbook");
        let config = root.join("params.json");
        let pulse = root.join("pulse.f64le");
        let workbook = root.join("reuse.xlsx");
        let mut document = canonical_parameters();
        document["workbook"] = json!({"path": workbook.to_string_lossy()});
        fs::write(&config, serde_json::to_vec(&document).unwrap()).unwrap();
        fs::write(&pulse, pulse_bytes()).unwrap();
        fs::write(&workbook, b"reuse-input").unwrap();
        let workbook_hash = sha256_bytes_v1(&fs::read(&workbook).unwrap());
        let request = DirectRunRequestV1::new(&config, &pulse, &workbook);
        let error = run_com_v1(&request).expect_err("reuse input overlap");
        assert!(
            matches!(error, DirectRunErrorV1::InvalidRequest(message) if message.contains("overlaps input"))
        );
        assert_eq!(
            sha256_bytes_v1(&fs::read(&workbook).unwrap()),
            workbook_hash
        );
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn output_custody_rejects_nested_channel_array_path_before_write() {
        let root = temp_root("output-custody-channel-array");
        let config = root.join("params.json");
        let pulse = root.join("pulse.f64le");
        let output = root.join("artifacts");
        let channel = output.join("fext.json");
        fs::create_dir_all(&output).unwrap();
        let mut document = canonical_parameters();
        document["portable"] = json!({"fext": [channel.to_string_lossy()]});
        fs::write(&config, serde_json::to_vec(&document).unwrap()).unwrap();
        fs::write(&pulse, pulse_bytes()).unwrap();
        fs::write(&channel, b"channel-input").unwrap();
        let channel_hash = sha256_bytes_v1(&fs::read(&channel).unwrap());
        let request = DirectRunRequestV1::new(&config, &pulse, &output);
        let error = run_com_v1(&request).expect_err("nested channel path must be rejected");
        assert!(
            matches!(error, DirectRunErrorV1::InvalidRequest(message) if message.contains("overlaps input"))
        );
        assert_eq!(sha256_bytes_v1(&fs::read(&channel).unwrap()), channel_hash);
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn portable_equalization_branch_is_reachable_from_com_run_and_changes_payload() {
        let root = temp_root("portable-eq");
        let config = root.join("params.json");
        let pulse = root.join("pulse.f64le");
        let output = root.join("artifacts");
        let mut values = canonical_parameters();
        values["portable"] = json!({
            "equalization": {
                "channel_types": ["THRU"],
                "baud_hz": 25.0e9,
                "samples_per_ui": 4,
                "ctle_type": "CL93",
                "ctle_fz_hz": 0.5e9,
                "ctle_fp1_hz": 1.0e9,
                "ctle_fp2_hz": 2.0e9,
                "ctle_gain_db": 0.0,
                "tx_ffe_taps": [1.0, 0.5],
                "tx_precursor_count": 0
            },
            "tdiln": {
                "frequency_hz": (0..64).map(|index| index as f64 * 1.0e9).collect::<Vec<_>>(),
                "sdd21": (0..64).map(|index| {
                    let frequency = index as f64 * 1.0e9;
                    let magnitude = (-(frequency / 8.0e10)).exp()
                        * (1.0 + 0.2 * (frequency / 5.0e9).sin());
                    let phase = -frequency / 2.0e10;
                    json!([magnitude * phase.cos(), magnitude * phase.sin()])
                }).collect::<Vec<_>>(),
                "f1_hz": 0.0,
                "f2_hz": 50.0e9,
                "baud_hz": 25.0e9,
                "samples_per_ui": 4,
                "sample_dt_s": 1.0e-12,
                "levels": 4,
                "spec_ber": 1.0e-4,
                "bin_size": 0.01,
                "bessel_order": 4,
                "bessel_cutoff_multiplier": 1.0,
                "transmitter_transition_time_ns": 0.0
            }
        });
        fs::write(&config, serde_json::to_vec(&values).unwrap()).unwrap();
        fs::write(&pulse, pulse_bytes()).unwrap();
        let report =
            run_com_v1(&DirectRunRequestV1::new(&config, &pulse, &output)).expect("equalized run");
        assert_eq!(
            report.result["cases"][0]["diagnostics"]["portable_branches"]["equalization"]["impulse_count"],
            1
        );
        assert_eq!(
            report.result["cases"][0]["diagnostics"]["channel_impulse"]["source_kind"],
            "equalized-channel-impulse"
        );
        assert!(
            report.result["cases"][0]["diagnostics"]["portable_branches"]["tdiln"]["fom_v"]
                .is_number()
        );
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn portable_equalization_crosstalk_channels_reach_com_metrics() {
        let root = temp_root("portable-eq-crosstalk");
        let config = root.join("params.json");
        let pulse = root.join("pulse.f64le");
        fs::write(&pulse, pulse_bytes()).unwrap();
        let mut values = canonical_parameters();
        let thru = pulse_bytes()
            .chunks_exact(8)
            .map(|chunk| f64::from_le_bytes(chunk.try_into().unwrap()))
            .collect::<Vec<_>>();
        let fext = thru.iter().map(|value| value * 0.2).collect::<Vec<_>>();
        let next = thru.iter().map(|value| value * 0.1).collect::<Vec<_>>();
        values["portable"] = json!({
            "equalization": {
                "channel_types": ["THRU", "FEXT", "NEXT"],
                "impulses": [thru, fext, next],
                "baud_hz": 25.0e9,
                "samples_per_ui": 4,
                "ctle_type": "CL93",
                "ctle_fz_hz": 0.5e9,
                "ctle_fp1_hz": 1.0e9,
                "ctle_fp2_hz": 2.0e9,
                "ctle_gain_db": 0.0,
                "tx_ffe_taps": [1.0, 0.5],
                "tx_precursor_count": 0
            }
        });
        fs::write(&config, serde_json::to_vec(&values).unwrap()).unwrap();
        let report = run_com_v1(&DirectRunRequestV1::new(
            &config,
            &pulse,
            root.join("equalized"),
        ));
        let report = report.expect("multi-channel equalization run");
        assert_eq!(
            report.result["cases"][0]["diagnostics"]["crosstalk_inputs"]["integrated_into_metrics"],
            true
        );
        assert!(
            report.result["cases"][0]["diagnostics"]["com_execution"]["fext_selected_phases"]
                .as_array()
                .is_some_and(|values| !values.is_empty())
        );
        assert!(
            report.result["cases"][0]["diagnostics"]["com_execution"]["next_selected_phases"]
                .as_array()
                .is_some_and(|values| !values.is_empty())
        );
        assert_eq!(
            report.result["cases"][0]["diagnostics"]["crosstalk_inputs"]["fext"][0]["source_kind"],
            "equalized-channel-impulse"
        );
        assert_eq!(
            report.result["cases"][0]["diagnostics"]["crosstalk_inputs"]["next"][0]["source_kind"],
            "equalized-channel-impulse"
        );
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn fext_and_next_inputs_are_loaded_and_published_as_waveform_semantics() {
        let root = temp_root("crosstalk-inputs");
        let config = root.join("params.json");
        let pulse = root.join("thru.f64le");
        let fext = root.join("fext.f64le");
        let next = root.join("next.f64le");
        let output = root.join("artifacts");
        fs::write(
            &config,
            serde_json::to_vec(&canonical_parameters()).unwrap(),
        )
        .unwrap();
        fs::write(&pulse, pulse_bytes()).unwrap();
        fs::write(&fext, pulse_bytes()).unwrap();
        fs::write(&next, pulse_bytes()).unwrap();
        let baseline = run_com_v1(&DirectRunRequestV1::new(
            &config,
            &pulse,
            root.join("baseline-artifacts"),
        ))
        .expect("baseline run");
        let mut request = DirectRunRequestV1::new(&config, &pulse, &output);
        request.fext.push(fext);
        request.next.push(next);
        let report = run_com_v1(&request).expect("FEXT/NEXT run");
        assert_eq!(
            report.result["cases"][0]["diagnostics"]["crosstalk_inputs"]["fext"][0]["sample_count"],
            64
        );
        assert_eq!(
            report.result["cases"][0]["diagnostics"]["crosstalk_inputs"]["next"][0]["sample_count"],
            64
        );
        assert_eq!(
            report.result["cases"][0]["diagnostics"]["crosstalk_inputs"]["integrated_into_metrics"],
            true
        );
        assert_ne!(
            report.result["cases"][0]["metrics"]["COM_dB"],
            baseline.result["cases"][0]["metrics"]["COM_dB"],
            "FEXT/NEXT must affect the COM payload, not only its manifest"
        );
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn mixed_mode_branch_publishes_sdd21_after_pn_skew() {
        let root = temp_root("mixed-mode");
        let config = root.join("params.json");
        let pulse = root.join("pulse.f64le");
        fs::write(&pulse, pulse_bytes()).unwrap();
        let zero = [0.0, 0.0];
        let mut matrix = vec![vec![zero; 4]; 4];
        matrix[2][0] = [1.0, 0.0];
        matrix[3][1] = [1.0, 0.0];
        let document = json!({
            "parameters": canonical_parameters()["parameters"].clone(),
            "portable": {
                "mixed_mode": {
                    "frequency_hz": [1.0e9],
                    "s": [matrix]
                }
            }
        });
        fs::write(&config, serde_json::to_vec(&document).unwrap()).unwrap();
        let loaded = load_config_v1(&DirectRunRequestV1::new(&config, &pulse, root.join("out")))
            .expect("config");
        let input = load_impulse_v1(&pulse).expect("pulse");
        let branches =
            portable_branch_result_v1(&loaded.document, &input, None, None).expect("mixed mode");
        assert_eq!(branches.diagnostics["mixed_mode"]["sample_count"], 1);
        assert!(branches.diagnostics["mixed_mode"]["sdd21_sha256"].is_string());
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn mixed_mode_channelize_reuses_fd_to_td_without_fitting() {
        let root = temp_root("mixed-mode-channelize");
        let config = root.join("params.json");
        let pulse = root.join("pulse.f64le");
        fs::write(&pulse, pulse_bytes()).unwrap();
        let zero = [0.0, 0.0];
        let mut matrix = vec![vec![zero; 4]; 4];
        matrix[2][0] = [1.0, 0.0];
        matrix[3][1] = [1.0, 0.0];
        let samples = (0..64)
            .map(|index| {
                let frequency = index as f64 * 1.0e9;
                let magnitude = (-(frequency / 8.0e10)).exp();
                let phase = -frequency / 2.0e10;
                let mut sample = matrix.clone();
                let value = [magnitude * phase.cos(), magnitude * phase.sin()];
                sample[2][0] = value;
                sample[3][1] = value;
                sample
            })
            .collect::<Vec<_>>();
        let document = json!({
            "parameters": canonical_parameters()["parameters"].clone(),
            "portable": {
                "mixed_mode": {
                    "frequency_hz": (0..64).map(|index| index as f64 * 1.0e9).collect::<Vec<_>>(),
                    "s": samples,
                    "channelize": true,
                    "fd_to_td": {"sample_dt_s": 1.0e-12}
                }
            }
        });
        fs::write(&config, serde_json::to_vec(&document).unwrap()).unwrap();
        let request = DirectRunRequestV1::new(&config, &pulse, root.join("out"));
        let loaded = load_config_v1(&request).expect("config");
        let input = load_impulse_v1(&pulse).expect("impulse");
        let branches = portable_branch_result_v1(&loaded.document, &input, None, None)
            .expect("channelized mixed mode branch");
        assert_eq!(branches.diagnostics["mixed_mode"]["channelized"], true);
        assert!(branches.effective_values.expect("effective impulse").len() > 1);
        assert_eq!(
            branches.effective_source_kind,
            Some("mixed-mode-channel-impulse")
        );
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn portable_search_branch_reaches_the_r480_loop_and_metric_payload() {
        let root = temp_root("portable-search");
        let config = root.join("params.json");
        let pulse = root.join("pulse.f64le");
        let mut values = canonical_parameters();
        let mut impulse = vec![0.0_f64; 300];
        for index in 0..(300 - 5 * 10) {
            impulse[5 * 10 + index] = (-(index as f64) / 16.0).exp();
        }
        impulse[5 * 10] = 1.0;
        let frequencies = (0..200)
            .map(|index| index as f64 * 1.0e7)
            .collect::<Vec<_>>();
        values["portable"] = json!({
            "search": {
                "frequency_hz": frequencies,
                "samples_per_ui": 10,
                "fb_hz": 26.5625e9,
                "tx_ffe_values": {
                    "tx_ffe_cm1_values": [0.3],
                    "tx_ffe_c0_values": [0.6, 0.8],
                    "tx_ffe_cp1_values": [-0.1]
                },
                "tx_ffe_c0_min": 0.2,
                "ts_anchor": 0,
                "local_search": 0.0,
                "ts_sample_adj_range": [-1, 1],
                "include_ctle": true,
                "gdc_min": 0.0,
                "gqual": [[0.0]],
                "g2qual": [0.0],
                "dfe_first_max": 0.5,
                "ctle": {
                    "ctle_gdc_values": [6.0],
                    "ctle_fz": [10.0e9],
                    "ctle_fp1": [30.0e9],
                    "ctle_fp2": [40.0e9],
                    "ctle_type": "CTLE",
                    "f_hp": [0.0],
                    "f_hp_z": [5.0e9],
                    "f_hp_p": [1.0e9]
                },
                "receiver": {
                    "fb_hz": 26.5625e9,
                    "btorder": 3,
                    "fb_bt_cutoff": 0.75,
                    "fb_bw_cutoff": 0.75,
                    "rc_start_hz": 8.0e9,
                    "rc_end_hz": 12.0e9,
                    "eta_0": 1.0e-3,
                    "accm_max_freq_hz": 30.0e9,
                    "ac_cm_rms": [0.0]
                },
                "candidate": {
                    "samples_per_ui": 10,
                    "r_lm": 50.0,
                    "levels": 4,
                    "sigma_x": 0.03,
                    "dfe_delta": 1.0e-3,
                    "n_tail_start": 0,
                    "b_float_rss_max": 0.0,
                    "a_dd": 0.1,
                    "sigma_rj": 1.0e-4,
                    "t_o": 0.0,
                    "min_veo_test": 0.0,
                    "noise_crest_factor": 0.0,
                    "spec_ber": 1.0e-4,
                    "samples_for_c2m": 8,
                    "ql": 1.0,
                    "floating_dfe": false,
                    "ndfe": 2,
                    "n_bmax": 2,
                    "n_bf": 1,
                    "n_bg": 1,
                    "bmaxg": 0.3,
                    "bmax": [0.5, 0.5],
                    "bmin": [-0.5, -0.5]
                },
                "options": {
                    "ffe_opt_method": "MMSE",
                    "rx_ffe_enabled": false,
                    "ts_srch_mode": "full-sweep",
                    "cdr": "MM",
                    "receiver": {
                        "bessel_thomson": false,
                        "butterworth": false,
                        "raised_cosine": false,
                        "use_eta0_psd": false,
                        "wc_portz": false,
                        "pkg_len_select": [1]
                    },
                    "candidate": {
                        "snr_txw_c0": false,
                        "wc_portz": false,
                        "tx_rd_sel": 1,
                        "pkg_len_select": [1],
                        "sndr": [30.0],
                        "limit_jitter_contrib_to_dfe_span": false,
                        "force_pdf_bin_size": false,
                        "bin_size": 1.0e-3,
                        "force_bbn_q_factor": false,
                        "bbn_q_factor": 0.0,
                        "histogram_window_weight": "rectangle"
                    }
                }
            }
        });
        fs::write(&config, serde_json::to_vec(&values).unwrap()).unwrap();
        fs::write(
            &pulse,
            impulse
                .iter()
                .flat_map(|value| value.to_le_bytes())
                .collect::<Vec<_>>(),
        )
        .unwrap();
        let report = run_com_v1(&DirectRunRequestV1::new(&config, &pulse, root.join("out")))
            .expect("portable search");
        let search = &report.result["cases"][0]["diagnostics"]["portable_branches"]["search"];
        assert!(search["fom_db"].as_f64().is_some_and(|value| value > 0.0));
        assert_eq!(
            report.result["cases"][0]["metrics"]["FOM"],
            search["fom_db"]
        );
        let probe_request = DirectRunRequestV1::new(&config, &pulse, root.join("probe-out"));
        let probe_loaded = load_config_v1(&probe_request).expect("probe config");
        let probe_input = load_impulse_v1(&pulse).expect("probe impulse");
        let probe_controls = canonical_controls_v1(&probe_loaded.values).expect("probe controls");
        let sigma_zero = portable_branch_result_with_sigma_v1(
            &probe_loaded.document,
            &probe_input,
            None,
            Some(&probe_controls),
            Some(0.0),
        )
        .expect("zero sigma search");
        let sigma_high = portable_branch_result_with_sigma_v1(
            &probe_loaded.document,
            &probe_input,
            None,
            Some(&probe_controls),
            Some(0.5),
        )
        .expect("nonzero sigma search");
        let sigma_zero_search = &sigma_zero.diagnostics["search"];
        let sigma_high_search = &sigma_high.diagnostics["search"];
        assert_eq!(sigma_zero_search["calibration_sigma_ne_v"], 0.0);
        assert_eq!(sigma_high_search["calibration_sigma_ne_v"], 0.5);
        assert_ne!(
            sigma_zero_search["fom_db"], sigma_high_search["fom_db"],
            "search FOM evaluator must consume the per-sigma noise"
        );
        let raw_search_digest = search["search_input_sha256"]
            .as_str()
            .expect("raw search digest");
        values["portable"]["equalization"] = json!({
            "channel_types": ["THRU"],
            "impulses": [impulse.iter().map(|value| value * 0.45).collect::<Vec<_>>()],
            "baud_hz": 25.0e9,
            "samples_per_ui": 10,
            "ctle_type": "CL93",
            "ctle_fz_hz": 0.5e9,
            "ctle_fp1_hz": 1.0e9,
            "ctle_fp2_hz": 2.0e9,
            "ctle_gain_db": 0.0,
            "tx_ffe_taps": [1.0],
            "tx_precursor_count": 0
        });
        fs::write(&config, serde_json::to_vec(&values).unwrap()).unwrap();
        let generated_report = run_com_v1(&DirectRunRequestV1::new(
            &config,
            &pulse,
            root.join("generated-out"),
        ))
        .expect("generated channel search");
        let generated_search =
            &generated_report.result["cases"][0]["diagnostics"]["portable_branches"]["search"];
        assert_eq!(
            generated_search["search_input_source_kind"],
            "portable-channel-producing-search-input"
        );
        assert_ne!(
            generated_search["search_input_sha256"]
                .as_str()
                .expect("generated search digest"),
            raw_search_digest,
            "portable.search must consume the generated equalized channel"
        );
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn portable_mmse_search_publishes_kkt_payload() {
        let root = temp_root("portable-mmse");
        let config = root.join("config.json");
        let pulse = root.join("pulse.f64le");
        let mut document = canonical_parameters();
        document["portable"] = json!({
            "mmse": {
                "candidates": [{
                    "h_matrix": [[1.0, 0.1], [0.2, 1.0], [0.1, 0.3]],
                    "noise_correlation": [[0.01, 0.0], [0.0, 0.01]],
                    "decision_index": 0,
                    "dfe_tap_count": 1,
                    "sigma_x2": 1.0,
                    "levels": 4,
                    "r_lm": 50.0,
                    "rx_min": [-2.0, -2.0],
                    "rx_max": [2.0, 2.0],
                    "dfe_min": [-0.5],
                    "dfe_max": [0.5],
                    "rx_cursor_offset": 0,
                    "ctle_index": 2,
                    "high_pass_index": 1,
                    "pre_rx_sbr": [0.1, 1.0, 0.2],
                    "equalized_sbr": [0.0, 1.0, 0.1]
                }]
            }
        });
        fs::write(&config, serde_json::to_vec(&document).unwrap()).unwrap();
        fs::write(root.join("pulse.f64le"), pulse_bytes()).unwrap();
        let report = run_com_v1(&DirectRunRequestV1::new(&config, &pulse, root.join("out")))
            .expect("MMSE branch");
        let branch = &report.result["cases"][0]["diagnostics"]["portable_branches"]["mmse"];
        assert_eq!(branch["candidate_index"], 0);
        assert!(
            branch["rx_ffe"]
                .as_array()
                .is_some_and(|values| !values.is_empty())
        );
        assert_eq!(branch["equalized_sbr"].as_array().map(Vec::len), Some(3));
        assert_eq!(
            report.result["cases"][0]["metrics"]["FOM"],
            branch["fom_db"]
        );
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn portable_rxffe_search_requires_full_source_evaluator() {
        let root = temp_root("portable-rxffe-search");
        let config = root.join("config.json");
        let pulse = root.join("pulse.f64le");
        let mut waveform = vec![0.0_f64; 32];
        waveform[8] = 0.01;
        waveform[12] = 0.1;
        waveform[16] = 1.0;
        waveform[20] = 0.05;
        waveform[24] = 0.02;
        waveform[28] = 0.01;
        let mut document = canonical_parameters();
        document["portable"] = json!({
            "rx_ffe_search": {"candidates": [{
                "waveform": waveform,
                "cursor_index": 16,
                "precursor_count": 1,
                "postcursor_count": 2,
                "samples_per_ui": 4,
                "unity_cursor": true,
                "rx_ffe_gain_db": 0.0
            }]}
        });
        fs::write(&config, serde_json::to_vec(&document).unwrap()).unwrap();
        fs::write(&pulse, pulse_bytes()).unwrap();
        let error = run_com_v1(&DirectRunRequestV1::new(&config, &pulse, root.join("out")))
            .expect_err("missing evaluator must fail closed");
        assert!(
            matches!(error, DirectRunErrorV1::Unsupported(message) if message.contains("CandidateEval") || message.contains("InvalidInput"))
        );
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn portable_rxffe_search_runs_source_fom_evaluator_payload() {
        let root = temp_root("portable-rxffe-full-eval");
        let config = root.join("config.json");
        let pulse = root.join("pulse.f64le");
        let mut waveform = vec![0.0_f64; 32];
        waveform[8] = 0.01;
        waveform[12] = 0.1;
        waveform[16] = 1.0;
        waveform[20] = 0.05;
        waveform[24] = 0.02;
        waveform[28] = 0.01;
        let mut document = canonical_parameters();
        document["portable"] = json!({
            "rx_ffe_search": {"candidates": [{
                "waveform": waveform,
                "cursor_index": 16,
                "precursor_count": 1,
                "postcursor_count": 2,
                "samples_per_ui": 4,
                "unity_cursor": true,
                "rx_ffe_gain_db": 0.0,
                "evaluation": {
                    "sigma_n_v": 0.001,
                    "sigma_ne_v": 0.0,
                    "sigma_xt_v": 0.0,
                    "package_case_index": 0,
                    "tx_taps": [1.0],
                    "tx_precursor_count": 0,
                    "tx_grid_index": 0,
                    "tx_source_indices": [0],
                    "itick": 0,
                    "ffe_main_cursor_min": 0.0,
                    "ffe_post_tap1_max": 1.0,
                    "ffe_tapn_max": 1.0,
                    "parameters": {
                        "samples_per_ui": 4,
                        "r_lm": 50.0,
                        "levels": 4,
                        "sigma_x": 0.03,
                        "dfe_delta": 0.0,
                        "n_tail_start": 0,
                        "b_float_rss_max": 0.0,
                        "a_dd": 0.4,
                        "sigma_rj": 0.0001,
                        "t_o": 0.0,
                        "min_veo_test": 0.0,
                        "noise_crest_factor": 0.0,
                        "spec_ber": 0.0001,
                        "samples_for_c2m": 8,
                        "ql": 1.0,
                        "floating_dfe": false,
                        "ndfe": 1,
                        "n_bmax": 1,
                        "n_bf": 1,
                        "n_bg": 0,
                        "bmaxg": 0.3,
                        "bmax": [0.5],
                        "bmin": [-0.5]
                    },
                    "options": {
                        "snr_txw_c0": false,
                        "wc_portz": false,
                        "tx_rd_sel": 0,
                        "pkg_len_select": [1],
                        "sndr": [30.0],
                        "limit_jitter_contrib_to_dfe_span": false,
                        "force_pdf_bin_size": false,
                        "bin_size": 0.01,
                        "force_bbn_q_factor": false,
                        "bbn_q_factor": 0.0,
                        "histogram_window_weight": "rectangle"
                    }
                }
            }]}
        });
        fs::write(&config, serde_json::to_vec(&document).unwrap()).unwrap();
        fs::write(&pulse, pulse_bytes()).unwrap();
        let report = run_com_v1(&DirectRunRequestV1::new(&config, &pulse, root.join("out")))
            .expect("full RxFFE branch");
        let branch =
            &report.result["cases"][0]["diagnostics"]["portable_branches"]["rx_ffe_search"];
        assert_eq!(branch["full_fom_evaluation"], true);
        assert!(
            branch["available_signal_v"]
                .as_f64()
                .is_some_and(|value| value > 0.0)
        );
        assert_eq!(branch["dfe_taps"].as_array().map(Vec::len), Some(1));
        assert_eq!(
            report.result["cases"][0]["metrics"]["FOM"],
            branch["fom_db"]
        );
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn portable_calibration_runs_outer_loop_and_overrides_noise_payload() {
        let root = temp_root("portable-calibration");
        let config = root.join("config.json");
        let calibration_path = root.join("calibration.json");
        let pulse = root.join("pulse.f64le");
        let complex = vec![[1.0, 0.0]; 4];
        let mut document = canonical_parameters();
        let case_pulse = pulse_bytes()
            .chunks_exact(8)
            .map(|chunk| f64::from_le_bytes(chunk.try_into().unwrap()))
            .collect::<Vec<_>>();
        document["package_case"] = json!({
            "case_id": "calibration-case",
            "pulse": case_pulse
        });
        document["portable"] = json!({
            "calibration": {
                "frequency_hz": [0.0, 1.0, 2.0, 3.0],
                "calibration_sdd21": complex,
                "ctle_transfer": [[1.0, 0.0], [1.0, 0.0], [1.0, 0.0], [1.0, 0.0]],
                "fb_hz": 4.0,
                "f_r": 1.0,
                "f_hp_hz": 0.0,
                "sigma_bn_v": 1.0,
                "pass_threshold_db": 0.0,
                "initial_step_v": 2.0
            }
        });
        fs::write(
            &calibration_path,
            serde_json::to_vec(&json!({
                "portable": {"calibration": document["portable"]["calibration"].clone()}
            }))
            .unwrap(),
        )
        .unwrap();
        fs::write(&config, serde_json::to_vec(&document).unwrap()).unwrap();
        fs::write(&pulse, pulse_bytes()).unwrap();
        let mut request = DirectRunRequestV1::new(&config, &pulse, root.join("out"));
        request.calibration_noise = Some(calibration_path.clone());
        let report = run_com_v1(&request).expect("calibration branch");
        assert_eq!(
            report.result["cases"][0]["channels"]["calibration_noise"],
            json!(calibration_path)
        );
        let branch = &report.result["cases"][0]["diagnostics"]["portable_branches"]["calibration"];
        assert!(branch["selected_noise"]["sigma_bn_v"].as_f64().is_some());
        assert!(
            branch["iterations"]
                .as_array()
                .is_some_and(|values| !values.is_empty())
        );
        assert_eq!(
            branch["case_channel_source"],
            "parsed-package-case-channel-state"
        );
        let selected = branch["selected_case_orchestration"]
            .as_array()
            .expect("selected case");
        assert_eq!(selected.len(), 1);
        assert!(selected[0]["selected_pulse_sha256"].is_string());
        assert!(
            selected[0]["fext_pulse_sha256"]
                .as_array()
                .is_some_and(Vec::is_empty)
        );
        assert!(
            selected[0]["next_pulse_sha256"]
                .as_array()
                .is_some_and(Vec::is_empty)
        );
        let per_sigma = branch["per_sigma_search_orchestration"]
            .as_array()
            .expect("per-sigma orchestration");
        assert!(per_sigma.len() >= 2);
        assert_ne!(per_sigma[0]["sigma_ne_v"], per_sigma[1]["sigma_ne_v"]);
        assert_eq!(
            report.result["cases"][0]["diagnostics"]["crosstalk_inputs"]["integrated_into_metrics"],
            false
        );
        assert!(
            report.result["cases"][0]["metrics"]["calibration_sigma_bn_v"]
                .as_f64()
                .is_some()
        );
        assert!(
            report.result["cases"][0]["metrics"]["sigma_N_V"]
                .as_f64()
                .is_some()
        );
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn legacy_csv_flag_publishes_source_schema_projection() {
        let root = temp_root("legacy-csv-artifact");
        let config = root.join("config.json");
        let pulse = root.join("pulse.f64le");
        fs::write(
            &config,
            serde_json::to_vec(&canonical_parameters()).unwrap(),
        )
        .unwrap();
        fs::write(&pulse, pulse_bytes()).unwrap();
        let mut request = DirectRunRequestV1::new(&config, &pulse, root.join("out"));
        request.legacy_csv = true;
        let report = run_com_v1(&request).expect("legacy CSV projection");
        let path = report.artifacts.legacy_csv.expect("CSV path");
        let csv = fs::read_to_string(path).expect("CSV contents");
        assert!(csv.starts_with("code_revision,config_file,Z11est"));
        assert!(
            csv.lines()
                .next()
                .is_some_and(|line| line.split(',').count() == LEGACY_OUTPUT_COLUMNS_V1.len())
        );
        assert!(
            csv.lines()
                .nth(1)
                .is_some_and(|line| line.split(',').count() == LEGACY_OUTPUT_COLUMNS_V1.len())
        );
        assert!(
            csv.lines()
                .next()
                .is_some_and(|line| line.split(',').any(|field| field == "COM_dB"))
        );
        assert!(csv.lines().count() == 2);
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn unsupported_portable_reporting_branches_fail_closed() {
        let root = temp_root("unsupported-portable-reporting");
        let config = root.join("config.json");
        let pulse = root.join("pulse.f64le");
        let mut document = canonical_parameters();
        document["portable"] = json!({"matlab_only_reporting": {"path": "report.mat"}});
        fs::write(&config, serde_json::to_vec(&document).unwrap()).unwrap();
        fs::write(&pulse, pulse_bytes()).unwrap();
        let error = run_com_v1(&DirectRunRequestV1::new(&config, &pulse, root.join("out")))
            .expect_err("unsupported portable reporting branch must fail closed");
        assert!(
            matches!(error, DirectRunErrorV1::Unsupported(message) if message.contains("matlab_only_reporting"))
        );
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn malformed_erl_only_mapping_fails_closed() {
        for (label, value) in [
            ("false", json!(false)),
            ("null", Value::Null),
            ("scalar", json!(1)),
        ] {
            let root = temp_root(&format!("erl-only-{label}"));
            let config = root.join("config.json");
            let pulse = root.join("pulse.f64le");
            let mut document = canonical_parameters();
            document["portable"] = json!({"erl_only": value});
            fs::write(&config, serde_json::to_vec(&document).unwrap()).unwrap();
            fs::write(&pulse, pulse_bytes()).unwrap();
            let error = run_com_v1(&DirectRunRequestV1::new(&config, &pulse, root.join("out")))
                .expect_err("malformed ERL-only mapping must fail closed");
            assert!(
                matches!(error, DirectRunErrorV1::Unsupported(ref message) if message.contains("erl_only must be an object")),
                "{label}: {error:?}"
            );
            let _ = fs::remove_dir_all(root);
        }
    }

    #[test]
    fn s2p_erl_dispatch_requires_the_exact_pinned_profile() {
        let path = Path::new("fixture.s2p");
        let ordinary = canonical_parameters();
        assert!(!exact_erl_s2p_profile_v1(&ordinary, path).expect("ordinary S2P route"));
        let mut root_alias = ordinary.clone();
        root_alias["erl_only"] = json!({});
        assert!(matches!(
            exact_erl_s2p_profile_v1(&root_alias, path),
            Err(DirectRunErrorV1::Unsupported(message)) if message.contains("aliases")
        ));
        let mut portable_alias = ordinary.clone();
        portable_alias["portable"] = json!({"erl": {}});
        assert!(matches!(
            exact_erl_s2p_profile_v1(&portable_alias, path),
            Err(DirectRunErrorV1::Unsupported(message)) if message.contains("alias")
        ));

        let mut typed = ordinary.clone();
        typed["portable"] = json!({"erl_only": {"tdr_profile": {"name": "r480_s2p_erl_v1"}}});
        assert!(matches!(
            exact_erl_s2p_profile_v1(&typed, path),
            Err(DirectRunErrorV1::Unsupported(message)) if message.contains("does not exactly match")
        ));

        typed["portable"]["erl_only"] = json!({
            "samples_per_ui": 32,
            "levels": 4,
            "bin_size": 0.00001,
            "spec_ber": 0.00001,
            "rl_norm_test": true,
            "tdr_profile": {
            "name": "r480_s2p_erl_v1",
            "samples_per_ui": 32,
            "levels": 4,
            "bin_size": 0.00001,
            "spec_ber": 0.00001,
            "rl_norm_test": true,
            "baud_hz": 53125000000_u64,
            "sample_dt_s": 0.0000000000005882352941176471_f64,
            "s_reference_ohm": 100,
            "zt_ohm": 50,
            "transition_time_ns": 0.01,
            "transition_filter_type": 1,
            "transition_measurement_point": 0,
            "receiver_cutoff_multiplier": 0.75,
            "receiver_filter_enabled": true,
            "tukey_enabled": true,
            "fixture_delay_s": 0,
            "tdr_delay_s": 0.0000000005,
            "observation_duration_ui": 800,
            "gate_n_bx": 0,
            "gate_rho_x": 0.618,
            "gate_grr": 1,
            "gate_beta_x_db_per_s": 0
            }
        });
        assert!(exact_erl_s2p_profile_v1(&typed, path).expect("exact ERL profile"));
        let mut extra = typed.clone();
        extra["portable"]["erl_only"]["unexpected_control"] = json!(1);
        assert!(matches!(
            exact_erl_s2p_profile_v1(&extra, path),
            Err(DirectRunErrorV1::Unsupported(message)) if message.contains("outer controls")
        ));
        typed["portable"]["erl_only"]["tdr_profile"]["zt_ohm"] = json!(50.000000000001_f64);
        assert!(matches!(
            exact_erl_s2p_profile_v1(&typed, path),
            Err(DirectRunErrorV1::Unsupported(message)) if message.contains("does not exactly match")
        ));
    }

    #[test]
    fn erl_gate_exact_profile_is_a_checked_noop_before_gate_start() {
        let pulse = [0.25, -0.5, 0.75];
        let time = [0.0, 1.0e-12, 2.0e-12];
        let gated = erl_gate_v1(&pulse, &time, 0.0, 1.0 / 53.125e9, 0, 0.01, 0.618, 1, 0.0)
            .expect("profile gate");
        assert_eq!(gated, pulse);
        assert!(
            erl_gate_v1(
                &pulse,
                &[0.0],
                500.0e-12,
                1.0 / 53.125e9,
                0,
                0.01,
                0.618,
                1,
                0.0
            )
            .is_err()
        );
    }

    #[test]
    fn pinned_8001_point_s2p_fixture_checkpoint_uses_exact_bytes() {
        let fixture = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("tests/fixtures/erl_s2p_10db_at_26p56ghz.s2p");
        let bytes = fs::read(&fixture).expect("pinned fixture bytes");
        assert_eq!(
            sha256_bytes_v1(&bytes),
            "7a59b41a385a95752d2d1159aab7772a10f7bd2c07e5122d770493151853c7a3"
        );
        let limits = touchstone_limits_v1().expect("Touchstone limits");
        let parsed =
            parse_touchstone_hz_s_ri_50_two_port_v1(&bytes, limits).expect("8001-point fixture");
        assert_eq!(parsed.rows().len(), 8001);
        let first = parsed.rows().first().expect("first fixture row");
        let last = parsed.rows().last().expect("last fixture row");
        assert_eq!(first.frequency_hz(), 0.0);
        assert_eq!(last.frequency_hz(), 80.0e9);
        assert_eq!(
            first.s11(),
            Complex64::try_new(0.0, 0.0).expect("finite SDD11")
        );
        assert_eq!(
            last.s11(),
            Complex64::try_new(0.0, 0.0).expect("finite SDD11")
        );
    }

    #[test]
    fn pinned_8001_point_s2p_erl_metric_checkpoint() {
        let fixture = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("tests/fixtures/erl_s2p_10db_at_26p56ghz.s2p");
        let input = load_erl_s2p_impulse_v1(&fixture).expect("pinned S2P ERL input");
        let source = input.erl_values.expect("pinned SDD11 impulse");
        let pulse = rectangular_pulse_response_v1(&source, 32).expect("pinned PTDR pulse");
        let mut best = (f64::NEG_INFINITY, 0usize, 0.0);
        for phase in 0..32 {
            let samples = pulse
                .iter()
                .skip(phase)
                .step_by(32)
                .copied()
                .collect::<Vec<_>>();
            let pdf = sampled_signal_pdf_v1(&samples, 4, 1.0e-4, false).expect("pinned PDF");
            let quantile = -pdf.first_quantile(1.0e-5).expect("pinned quantile");
            let selector = samples
                .iter()
                .map(|value| value * value)
                .sum::<f64>()
                .sqrt();
            if selector > best.0 {
                best = (selector, phase, quantile);
            }
        }
        assert_eq!(best.1, 21);
        assert!((-20.0 * best.2.abs().log10() - 0.014778577737990855).abs() < 1.0e-12);
    }

    #[test]
    fn split_erl_only_entrypoints_fail_closed() {
        let root = temp_root("erl-only-split");
        let config = root.join("config.json");
        let pulse = root.join("pulse.f64le");
        let mut document = canonical_parameters();
        let controls = json!({
            "samples_per_ui": 8,
            "levels": 4,
            "bin_size": 1.0e-5,
            "spec_ber": 1.0e-4,
            "rl_norm_test": true
        });
        document["portable"] = json!({"erl_only": controls.clone()});
        document["erl_only"] = controls;
        fs::write(&config, serde_json::to_vec(&document).unwrap()).unwrap();
        fs::write(&pulse, pulse_bytes()).unwrap();
        let error = run_com_v1(&DirectRunRequestV1::new(&config, &pulse, root.join("out")))
            .expect_err("split ERL-only entrypoints must fail closed");
        assert!(
            matches!(error, DirectRunErrorV1::Unsupported(message) if message.contains("split between"))
        );
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn erl_db_metric_rejects_nan_and_preserves_infinity_tokens() {
        assert!(matches!(
            metric_db_value_v1(f64::NAN),
            Err(DirectRunErrorV1::Parameters(message)) if message.contains("cannot be NaN")
        ));
        assert_eq!(metric_db_value_v1(f64::INFINITY).unwrap(), json!("inf"));
        assert_eq!(
            metric_db_value_v1(f64::NEG_INFINITY).unwrap(),
            json!("-inf")
        );
    }

    #[test]
    fn source_unimplemented_wiener_hopf_branch_fails_closed() {
        let root = temp_root("unsupported-wiener-hopf");
        let config = root.join("config.json");
        let pulse = root.join("pulse.f64le");
        let mut document = canonical_parameters();
        document["portable"] = json!({"wiener_hopf": {"requested": true}});
        fs::write(&config, serde_json::to_vec(&document).unwrap()).unwrap();
        fs::write(&pulse, pulse_bytes()).unwrap();
        let error = run_com_v1(&DirectRunRequestV1::new(&config, &pulse, root.join("out")))
            .expect_err("source-unimplemented Wiener-Hopf branch must fail closed");
        assert!(
            matches!(error, DirectRunErrorV1::Unsupported(message) if message.contains("wiener_hopf"))
        );
        let _ = fs::remove_dir_all(root);
    }
}
