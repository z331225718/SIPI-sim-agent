//! PyBERT-specific adapter over the existing one-job AMI worker.
//!
//! The worker owns the DLL ABI, closure checks, deadline and lifecycle. This
//! module only maps PyBERT's IBS/AMI/DLL bundle and validates the typed
//! handoff. It never loads or emulates a vendor model. The adapter has no
//! caller-supplied TX/RX role metadata, so `clocks_s` is a generic model-clock
//! stream and may be empty; it is not presented as an RX clock guarantee.

use std::{
    fs,
    io::Write,
    path::{Component, Path},
    time::Duration,
};

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use sipi_ami_text::{AmiTextListV1, AmiTextNodeV1, ParseLimitsV1, parse_ami_text_v1};
use sipi_ami_worker::{
    AmiWorkerJobV2, FileIdentityV1, SupervisorReceiptV1, WorkerBundleManifestV2, WorkerErrorV1,
    supervise_worker_v2, validate_job_v2_contract,
};
use sipi_artifacts::{ArtifactRoot, VerifiedConsumptionPolicyV1};
use thiserror::Error;

use crate::Seconds;

pub const PYBERT_AMI_ADAPTER_SCHEMA_V2: &str = "pybert.ami-worker-adapter.v2";
const JOB_FILE: &str = "job.json";
const LAUNCH_FILE: &str = "pybert-ami-launch.json";
const MAX_ASSET_BYTES: u64 = 64 * 1024 * 1024;
const MAX_ROWS: usize = 1_000_000;
const MAX_AGGRESSORS: usize = 1_024;
const MAX_PARAMETERS_BLOCK_BYTES: usize = 65_536;
const MAX_PARAMETERS_TOTAL_BYTES: usize = 4 * 1024 * 1024;

#[derive(Debug, Clone, Deserialize, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum PybertAmiModeV1 {
    Init,
    InitGetWave,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct PybertAmiRequestV1 {
    pub mode: PybertAmiModeV1,
    pub ibis_path: String,
    pub ami_path: String,
    pub runtime_parameters: String,
    pub dll_path: String,
    pub init_matrix_path: String,
    pub waveform_path: String,
    pub rows: usize,
    pub aggressors: usize,
    pub sample_interval: Seconds,
    pub bit_time: Seconds,
    pub samples_per_bit: usize,
    pub block_size_bits: usize,
    pub max_waveform_samples: usize,
    pub clock_capacity: usize,
    pub max_parameters_bytes: usize,
    pub deadline_ms: u64,
    pub artifact_id: String,
    pub expected_worker_sha256: String,
    pub expected_worker_bytes: u64,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct PybertAmiAssetBundleV1 {
    pub ibis: FileIdentityV1,
    pub ami: FileIdentityV1,
    pub dll: FileIdentityV1,
    pub closure_sha256: String,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct PybertAmiLaunchV2 {
    pub schema: String,
    pub nonce: String,
    pub root_sha256: String,
    pub mode: PybertAmiModeV1,
    pub request_sha256: String,
    pub block_size_bits: usize,
    pub max_waveform_samples: usize,
    pub max_parameters_bytes: usize,
    pub expected_worker_sha256: String,
    pub expected_worker_bytes: u64,
    pub asset_bundle: PybertAmiAssetBundleV1,
    pub job: AmiWorkerJobV2,
}

#[derive(Debug, Clone, Deserialize, PartialEq, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct PybertAmiHostResultV2 {
    pub schema: String,
    pub nonce: String,
    pub request_sha256: String,
    pub mode: PybertAmiModeV1,
    pub status: String,
    pub waveform: Vec<f64>,
    pub clocks_s: Vec<f64>,
    pub parameters_out: Vec<String>,
    pub close_status: i32,
}

#[derive(Debug, Error, PartialEq)]
pub enum PybertAmiWorkerErrorV1 {
    #[error("PyBERT AMI adapter input is invalid")]
    InvalidInput,
    #[error("PyBERT AMI adapter requires a safe relative asset path")]
    UnsafePath,
    #[error("PyBERT AMI asset is unavailable or escaped the sealed root")]
    AssetUnavailable,
    #[error("PyBERT AMI asset identity is invalid")]
    AssetIdentity,
    #[error("PyBERT AMI mode is not expressible by the one-job worker")]
    UnsupportedMode,
    #[error("PyBERT AMI launch root is not fresh")]
    NonFreshRoot,
    #[error("PyBERT AMI launch serialization failed")]
    Serialization,
    #[error("PyBERT AMI worker failed")]
    Worker,
    #[error("PyBERT AMI worker result is invalid or incomplete")]
    InvalidResult,
}

struct RuntimeFileGuard {
    path: std::path::PathBuf,
    keep: bool,
}

impl Drop for RuntimeFileGuard {
    fn drop(&mut self) {
        if !self.keep {
            let _ = fs::remove_file(&self.path);
        }
    }
}

impl From<WorkerErrorV1> for PybertAmiWorkerErrorV1 {
    fn from(_: WorkerErrorV1) -> Self {
        Self::Worker
    }
}

#[must_use]
pub fn sha256_bytes(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

fn safe_relative(value: &str) -> bool {
    let path = Path::new(value);
    !value.is_empty()
        && !path.is_absolute()
        && value.bytes().all(|byte| !byte.is_ascii_control())
        && path
            .components()
            .all(|component| matches!(component, Component::Normal(_)))
}

fn worker_token(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 128
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || byte == b'-' || byte == b'_')
}

fn valid_sha256(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn identity(
    root: &Path,
    value: &str,
    extension: &str,
    maximum_bytes: u64,
) -> Result<FileIdentityV1, PybertAmiWorkerErrorV1> {
    if !safe_relative(value) || !value.to_ascii_lowercase().ends_with(extension) {
        return Err(PybertAmiWorkerErrorV1::UnsafePath);
    }
    let path = checked_asset_path(root, value)?;
    let metadata =
        fs::symlink_metadata(&path).map_err(|_| PybertAmiWorkerErrorV1::AssetUnavailable)?;
    if metadata.file_type().is_symlink() || !metadata.is_file() {
        return Err(PybertAmiWorkerErrorV1::AssetUnavailable);
    }
    if metadata.len() == 0 || metadata.len() > maximum_bytes {
        return Err(PybertAmiWorkerErrorV1::AssetUnavailable);
    }
    let bytes = fs::read(&path).map_err(|_| PybertAmiWorkerErrorV1::AssetUnavailable)?;
    if bytes.len() as u64 != metadata.len() || bytes.len() as u64 > maximum_bytes {
        return Err(PybertAmiWorkerErrorV1::AssetUnavailable);
    }
    Ok(FileIdentityV1 {
        path: value.into(),
        sha256: sha256_bytes(&bytes),
        bytes: bytes.len() as u64,
    })
}

fn checked_root(root: &Path) -> Result<std::path::PathBuf, PybertAmiWorkerErrorV1> {
    let metadata =
        fs::symlink_metadata(root).map_err(|_| PybertAmiWorkerErrorV1::AssetUnavailable)?;
    if !root.is_absolute() || !metadata.is_dir() || metadata.file_type().is_symlink() {
        return Err(PybertAmiWorkerErrorV1::UnsafePath);
    }
    no_symlink_components(root)?;
    fs::canonicalize(root).map_err(|_| PybertAmiWorkerErrorV1::AssetUnavailable)
}

fn no_symlink_components(root: &Path) -> Result<(), PybertAmiWorkerErrorV1> {
    let mut current = std::path::PathBuf::new();
    for component in root.components() {
        match component {
            Component::Prefix(prefix) => current.push(prefix.as_os_str()),
            Component::RootDir => current.push(std::path::MAIN_SEPARATOR.to_string()),
            Component::Normal(part) => {
                current.push(part);
                if fs::symlink_metadata(&current)
                    .map_err(|_| PybertAmiWorkerErrorV1::AssetUnavailable)?
                    .file_type()
                    .is_symlink()
                {
                    return Err(PybertAmiWorkerErrorV1::UnsafePath);
                }
            }
            Component::CurDir | Component::ParentDir => {
                return Err(PybertAmiWorkerErrorV1::UnsafePath);
            }
        }
    }
    Ok(())
}

fn checked_asset_path(
    root: &Path,
    value: &str,
) -> Result<std::path::PathBuf, PybertAmiWorkerErrorV1> {
    let mut current = root.to_path_buf();
    for component in Path::new(value).components() {
        let Component::Normal(part) = component else {
            return Err(PybertAmiWorkerErrorV1::UnsafePath);
        };
        current.push(part);
        let metadata =
            fs::symlink_metadata(&current).map_err(|_| PybertAmiWorkerErrorV1::AssetUnavailable)?;
        if metadata.file_type().is_symlink() {
            return Err(PybertAmiWorkerErrorV1::UnsafePath);
        }
    }
    Ok(current)
}

fn nonce() -> Result<String, PybertAmiWorkerErrorV1> {
    let mut bytes = [0_u8; 32];
    getrandom::getrandom(&mut bytes).map_err(|_| PybertAmiWorkerErrorV1::Serialization)?;
    Ok(format!("pb-ami-{}", hex(&bytes)))
}

fn hex(bytes: &[u8]) -> String {
    let mut result = String::with_capacity(bytes.len() * 2);
    for byte in bytes {
        use std::fmt::Write as _;
        let _ = write!(result, "{byte:02x}");
    }
    result
}

fn closure_digest(values: &[FileIdentityV1]) -> Result<String, PybertAmiWorkerErrorV1> {
    serde_json::to_vec(values)
        .map(|bytes| sha256_bytes(&bytes))
        .map_err(|_| PybertAmiWorkerErrorV1::Serialization)
}

fn digest_root(root: &Path) -> String {
    sha256_bytes(root.to_string_lossy().as_bytes())
}

fn same_identity(left: &FileIdentityV1, right: &FileIdentityV1) -> bool {
    left.path == right.path && left.sha256 == right.sha256 && left.bytes == right.bytes
}

fn validate_launch_binding(launch: &PybertAmiLaunchV2) -> Result<(), PybertAmiWorkerErrorV1> {
    if launch.schema != PYBERT_AMI_ADAPTER_SCHEMA_V2
        || launch.nonce != launch.job.job_id
        || launch.root_sha256 != launch.job.root_sha256
        || launch.job.request_sha256 != launch.request_sha256
        || launch.block_size_bits != launch.job.getwave_bits_per_call
        || launch.max_parameters_bytes != launch.job.max_parameters_bytes
        || launch.job.closure.len() != 2
        || !same_identity(&launch.asset_bundle.dll, &launch.job.dll)
        || same_identity(&launch.asset_bundle.ami, &launch.job.parameters)
        || !same_identity(&launch.asset_bundle.ibis, &launch.job.closure[0])
        || !same_identity(&launch.asset_bundle.ami, &launch.job.closure[1])
    {
        return Err(PybertAmiWorkerErrorV1::AssetIdentity);
    }
    if closure_digest(&launch.job.closure)? != launch.asset_bundle.closure_sha256 {
        return Err(PybertAmiWorkerErrorV1::AssetIdentity);
    }
    let mut digest_job = launch.job.clone();
    digest_job.request_sha256.clear();
    let payload = serde_json::json!({
        "schema": &launch.schema,
        "nonce": &launch.nonce,
        "mode": &launch.mode,
        "block_size_bits": launch.block_size_bits,
        "max_waveform_samples": launch.max_waveform_samples,
        "max_parameters_bytes": launch.max_parameters_bytes,
        "expected_worker_sha256": &launch.expected_worker_sha256,
        "expected_worker_bytes": launch.expected_worker_bytes,
        "asset_bundle": &launch.asset_bundle,
        "job": &digest_job,
    });
    let digest = sha256_bytes(
        &serde_json::to_vec(&payload).map_err(|_| PybertAmiWorkerErrorV1::Serialization)?,
    );
    if digest != launch.request_sha256 {
        return Err(PybertAmiWorkerErrorV1::AssetIdentity);
    }
    Ok(())
}

fn validate_launch_contract(
    launch: &PybertAmiLaunchV2,
    root: &Path,
    bundle: &WorkerBundleManifestV2,
) -> Result<(), PybertAmiWorkerErrorV1> {
    validate_job_v2_contract(&launch.job).map_err(|_| PybertAmiWorkerErrorV1::InvalidInput)?;
    validate_launch_binding(launch)?;
    if launch.root_sha256 != digest_root(root)
        || !worker_token(&launch.nonce)
        || !worker_token(&launch.job.job_id)
        || launch.max_waveform_samples > 8_000_000
        || !launch.job.waveform.bytes.is_multiple_of(8)
        || (launch.max_waveform_samples as u64) < launch.job.waveform.bytes / 8
        || launch.max_parameters_bytes > 65_536
        || launch.max_parameters_bytes != launch.job.max_parameters_bytes
        || launch.job.deadline_ms == 0
        || launch.job.deadline_ms > 300_000
        || launch.expected_worker_sha256 != bundle.worker_sha256
        || launch.expected_worker_bytes != bundle.worker_bytes
        || bundle.schema != "sipi.ami-worker.bundle.v2"
        || bundle.abi_contract_revision != launch.job.abi_contract_revision
        || !valid_sha256(&bundle.worker_sha256)
        || bundle.worker_bytes == 0
        || bundle.worker_bytes > 256 * 1024 * 1024
    {
        return Err(PybertAmiWorkerErrorV1::AssetIdentity);
    }
    for item in [
        &launch.job.dll,
        &launch.job.init_matrix,
        &launch.job.parameters,
        &launch.job.waveform,
    ]
    .into_iter()
    .chain(launch.job.closure.iter())
    {
        if !valid_file_identity(item) {
            return Err(PybertAmiWorkerErrorV1::AssetIdentity);
        }
    }
    let block_samples = launch
        .job
        .getwave_bits_per_call
        .checked_mul(launch.job.samples_per_bit)
        .ok_or(PybertAmiWorkerErrorV1::InvalidInput)?;
    if block_samples == 0 {
        return Err(PybertAmiWorkerErrorV1::InvalidInput);
    }
    let block_count = launch.max_waveform_samples.div_ceil(block_samples);
    let structure_bytes = block_count
        .checked_mul(std::mem::size_of::<String>() + 8)
        .ok_or(PybertAmiWorkerErrorV1::InvalidInput)?;
    if block_count > 100_000 || structure_bytes > MAX_PARAMETERS_TOTAL_BYTES {
        return Err(PybertAmiWorkerErrorV1::InvalidInput);
    }
    let matrix_values = launch
        .job
        .rows
        .checked_mul(
            launch
                .job
                .aggressors
                .checked_add(1)
                .ok_or(PybertAmiWorkerErrorV1::InvalidInput)?,
        )
        .ok_or(PybertAmiWorkerErrorV1::InvalidInput)?;
    if matrix_values > 4_000_000
        || launch.job.init_matrix.bytes
            != matrix_values
                .checked_mul(8)
                .ok_or(PybertAmiWorkerErrorV1::InvalidInput)? as u64
    {
        return Err(PybertAmiWorkerErrorV1::AssetIdentity);
    }
    if launch.job.parameters.bytes > launch.max_parameters_bytes as u64
        || launch.job.waveform.bytes
            > (launch.max_waveform_samples as u64)
                .checked_mul(8)
                .ok_or(PybertAmiWorkerErrorV1::InvalidInput)?
    {
        return Err(PybertAmiWorkerErrorV1::AssetIdentity);
    }
    Ok(())
}

fn valid_file_identity(item: &FileIdentityV1) -> bool {
    safe_relative(&item.path)
        && valid_sha256(&item.sha256)
        && item.bytes > 0
        && item.bytes <= MAX_ASSET_BYTES
}

fn materializer_parse_limits() -> ParseLimitsV1 {
    ParseLimitsV1::try_new(65_536, 64, 4_096, 4_096).expect("non-zero materializer limits")
}

fn text_atom(node: &AmiTextNodeV1) -> Option<&str> {
    match node {
        AmiTextNodeV1::Atom(token) => Some(token.spelling()),
        AmiTextNodeV1::Quoted(_) => None,
        AmiTextNodeV1::List(_) => None,
    }
}

fn list_name(list: &AmiTextListV1) -> Option<&str> {
    list.items().first().and_then(text_atom)
}

fn single_root(
    document: &sipi_ami_text::AmiTextDocumentV1,
) -> Result<&AmiTextListV1, PybertAmiWorkerErrorV1> {
    if document.forms().len() != 1 {
        return Err(PybertAmiWorkerErrorV1::InvalidInput);
    }
    document
        .forms()
        .first()
        .ok_or(PybertAmiWorkerErrorV1::InvalidInput)
}

#[derive(Debug, Clone)]
struct TypedParameter {
    usage: String,
    declared_type: String,
    format: String,
    encoded: String,
    choices: Vec<String>,
    range: Option<(f64, f64)>,
    integer_range: Option<(i64, i64)>,
}

#[derive(Debug, Clone)]
struct ParameterDescriptor {
    path: Vec<String>,
    parameter: TypedParameter,
}

#[derive(Debug, Default)]
struct DeclarationAnalysis {
    info: Vec<ParameterDescriptor>,
    model: Vec<ParameterDescriptor>,
    paths: Vec<Vec<String>>,
    getwave_exists: Option<bool>,
    init_returns_impulse: Option<bool>,
}

fn quoted_value(token: &AmiTextNodeV1) -> Result<String, PybertAmiWorkerErrorV1> {
    let AmiTextNodeV1::Quoted(value) = token else {
        return Err(PybertAmiWorkerErrorV1::InvalidInput);
    };
    let spelling = value.spelling();
    if spelling.len() < 2 || !spelling.starts_with('"') || !spelling.ends_with('"') {
        return Err(PybertAmiWorkerErrorV1::InvalidInput);
    }
    let inner = &spelling[1..spelling.len() - 1];
    if inner.is_empty() || inner.as_bytes().contains(&0) {
        return Err(PybertAmiWorkerErrorV1::InvalidInput);
    }
    Ok(inner.to_owned())
}

fn scalar_atom(token: &AmiTextNodeV1) -> Result<&str, PybertAmiWorkerErrorV1> {
    text_atom(token)
        .filter(|value| !value.is_empty())
        .ok_or(PybertAmiWorkerErrorV1::InvalidInput)
}

fn metadata_values(list: &AmiTextListV1) -> Result<Vec<&AmiTextNodeV1>, PybertAmiWorkerErrorV1> {
    if list.items().len() < 2 || list_name(list).is_none() {
        return Err(PybertAmiWorkerErrorV1::InvalidInput);
    }
    Ok(list.items().iter().skip(1).collect())
}

fn parse_numeric(token: &AmiTextNodeV1) -> Result<f64, PybertAmiWorkerErrorV1> {
    let value = scalar_atom(token)?
        .parse::<f64>()
        .map_err(|_| PybertAmiWorkerErrorV1::InvalidInput)?;
    if value.is_finite() {
        Ok(value)
    } else {
        Err(PybertAmiWorkerErrorV1::InvalidInput)
    }
}

fn python_float_string(value: f64) -> String {
    let mut text = format!("{value:?}");
    if let Some(index) = text.find('e') {
        let (mantissa, exponent) = text.split_at(index + 1);
        let mut exponent = exponent.to_owned();
        if !exponent.starts_with(['+', '-']) {
            exponent.insert(0, '+');
        }
        if exponent.len() == 2 {
            exponent.insert(1, '0');
        }
        text = format!("{mantissa}{exponent}");
    } else if !text.contains('.') {
        text.push_str(".0");
    }
    text
}

fn strict_integer(token: &AmiTextNodeV1) -> Result<String, PybertAmiWorkerErrorV1> {
    let value = scalar_atom(token)?
        .parse::<i64>()
        .map_err(|_| PybertAmiWorkerErrorV1::InvalidInput)?;
    Ok(value.to_string())
}

fn python_string_repr(value: &str) -> String {
    let escaped = value.replace('\\', "\\\\").replace('\'', "\\'");
    format!("'{escaped}'")
}

fn python_list_string(values: &[String]) -> String {
    format!("[{}]", values.join(", "))
}

fn list_item_value(
    declared_type: &str,
    value: &AmiTextNodeV1,
) -> Result<String, PybertAmiWorkerErrorV1> {
    if matches!(declared_type, "Integer" | "Tap") {
        strict_integer(value)
    } else {
        typed_value(declared_type, "Value", &[value])
    }
}

fn list_default_value(
    declared_type: &str,
    value: &AmiTextNodeV1,
) -> Result<String, PybertAmiWorkerErrorV1> {
    if matches!(declared_type, "Integer" | "Tap") {
        strict_integer(value)
    } else {
        typed_value(declared_type, "Default", &[value])
    }
}

fn typed_value(
    declared_type: &str,
    format: &str,
    values: &[&AmiTextNodeV1],
) -> Result<String, PybertAmiWorkerErrorV1> {
    if values.is_empty() {
        return Err(PybertAmiWorkerErrorV1::InvalidInput);
    }
    let value = values[0];
    match format {
        "Value" | "Default" => {
            if values.len() != 1 {
                return Err(PybertAmiWorkerErrorV1::InvalidInput);
            }
            match declared_type {
                "String" | "Tap" => Ok(format!("\"{}\"", quoted_value(value)?)),
                "Boolean" => match scalar_atom(value)? {
                    "True" => Ok("True".into()),
                    "False" => Ok("False".into()),
                    _ => Err(PybertAmiWorkerErrorV1::InvalidInput),
                },
                "Float" | "UI" => {
                    let number = parse_numeric(value)?;
                    Ok(python_float_string(number))
                }
                "Integer" => {
                    // PyAMI's integer boundary is lexical here: accepting a
                    // float first would silently round values above 2^53.
                    strict_integer(value)
                }
                _ => Err(PybertAmiWorkerErrorV1::InvalidInput),
            }
        }
        "Range" => {
            if values.len() != 3 || !matches!(declared_type, "Float" | "UI" | "Integer" | "Tap") {
                return Err(PybertAmiWorkerErrorV1::InvalidInput);
            }
            if declared_type == "Integer" {
                let current = strict_integer(values[0])?.parse::<i64>().unwrap();
                let minimum = strict_integer(values[1])?.parse::<i64>().unwrap();
                let maximum = strict_integer(values[2])?.parse::<i64>().unwrap();
                if minimum > maximum || current < minimum || current > maximum {
                    return Err(PybertAmiWorkerErrorV1::InvalidInput);
                }
                return Ok(current.to_string());
            }
            let (current, minimum, maximum) = {
                (
                    parse_numeric(values[0])?,
                    parse_numeric(values[1])?,
                    parse_numeric(values[2])?,
                )
            };
            if minimum > maximum || current < minimum || current > maximum {
                return Err(PybertAmiWorkerErrorV1::InvalidInput);
            }
            Ok(python_float_string(current))
        }
        "List" | "Corner" => {
            let selected = match declared_type {
                "String" => format!("\"{}\"", quoted_value(value)?),
                "Boolean" => match scalar_atom(value)? {
                    "True" => "True".into(),
                    "False" => "False".into(),
                    _ => return Err(PybertAmiWorkerErrorV1::InvalidInput),
                },
                "Float" | "UI" => python_float_string(parse_numeric(value)?),
                "Integer" | "Tap" => strict_integer(value)?,
                _ => return Err(PybertAmiWorkerErrorV1::InvalidInput),
            };
            Ok(selected)
        }
        _ => Err(PybertAmiWorkerErrorV1::InvalidInput),
    }
}

fn typed_parameter(
    parameter: &AmiTextListV1,
) -> Result<Option<TypedParameter>, PybertAmiWorkerErrorV1> {
    let name = list_name(parameter).ok_or(PybertAmiWorkerErrorV1::InvalidInput)?;
    if name.is_empty() {
        return Err(PybertAmiWorkerErrorV1::InvalidInput);
    }
    let mut tags: Vec<(&str, Vec<&AmiTextNodeV1>)> = Vec::new();
    for child in parameter.items().iter().skip(1) {
        let AmiTextNodeV1::List(tag) = child else {
            return Err(PybertAmiWorkerErrorV1::InvalidInput);
        };
        let tag_name = list_name(tag).ok_or(PybertAmiWorkerErrorV1::InvalidInput)?;
        if tags.iter().any(|(existing, _)| *existing == tag_name) {
            return Err(PybertAmiWorkerErrorV1::InvalidInput);
        }
        let values = metadata_values(tag)?;
        tags.push((tag_name, values));
    }
    let semantic = tags.iter().any(|(name, _)| {
        matches!(
            *name,
            "Usage" | "Type" | "Value" | "Default" | "Range" | "List" | "Corner"
        )
    });
    if !semantic {
        return Ok(None);
    }
    if tags.iter().any(|(name, _)| {
        !matches!(
            *name,
            "Usage"
                | "Type"
                | "Value"
                | "Default"
                | "Range"
                | "List"
                | "Corner"
                | "Description"
                | "List_Tip"
                | "Label"
                | "Labels"
        )
    }) {
        return Err(PybertAmiWorkerErrorV1::InvalidInput);
    }
    let lookup = |name: &str| {
        tags.iter()
            .rev()
            .find(|(tag, _)| *tag == name)
            .map(|(_, values)| values.as_slice())
    };
    let usage = lookup("Usage").ok_or(PybertAmiWorkerErrorV1::InvalidInput)?;
    if usage.len() != 1 || !matches!(scalar_atom(usage[0])?, "In" | "Out" | "InOut" | "Info") {
        return Err(PybertAmiWorkerErrorV1::InvalidInput);
    }
    let declared_type = lookup("Type").ok_or(PybertAmiWorkerErrorV1::InvalidInput)?;
    if declared_type.len() != 1 {
        return Err(PybertAmiWorkerErrorV1::InvalidInput);
    }
    let declared_type = scalar_atom(declared_type[0])?;
    if !matches!(
        declared_type,
        "String" | "Boolean" | "Integer" | "Float" | "UI" | "Tap"
    ) {
        return Err(PybertAmiWorkerErrorV1::InvalidInput);
    }
    let format = tags
        .iter()
        .rev()
        .find(|(tag, _)| matches!(*tag, "Value" | "Range" | "List" | "Corner"))
        .map(|(tag, _)| *tag)
        .or_else(|| lookup("Default").map(|_| "Default"));
    let format = format.ok_or(PybertAmiWorkerErrorV1::InvalidInput)?;
    if scalar_atom(usage[0])? == "Out" && lookup("Default").is_some() {
        return Err(PybertAmiWorkerErrorV1::InvalidInput);
    }
    if let Some(default) = lookup("Default") {
        if default.len() != 1 {
            return Err(PybertAmiWorkerErrorV1::InvalidInput);
        }
        if matches!(format, "List" | "Corner") {
            let _ = list_default_value(declared_type, default[0])?;
        } else {
            let _ = typed_value(declared_type, "Default", default)?;
        }
    }
    let mut choices = Vec::new();
    if matches!(format, "List" | "Corner") {
        for item in lookup(format).unwrap() {
            choices.push(list_item_value(declared_type, item)?);
        }
    }
    let encoded = if matches!(format, "List" | "Corner") && declared_type == "Boolean" {
        if let Some(default) = lookup("Default") {
            typed_value(declared_type, "Default", default)?
        } else {
            "False".into()
        }
    } else if matches!(format, "List" | "Corner") {
        if let Some(default) = lookup("Default") {
            list_default_value(declared_type, default[0])?
        } else {
            typed_value(declared_type, format, lookup(format).unwrap_or(&[]))?
        }
    } else {
        typed_value(declared_type, format, lookup(format).unwrap_or(&[]))?
    };
    let encoded = if matches!(format, "List" | "Corner")
        && declared_type != "Boolean"
        && scalar_atom(usage[0])? == "Info"
        && lookup("Default").is_none()
    {
        let list_values = lookup(format)
            .unwrap()
            .iter()
            .map(|value| {
                if declared_type == "String" {
                    quoted_value(value).map(|value| python_string_repr(&value))
                } else {
                    list_item_value(declared_type, value)
                }
            })
            .collect::<Result<Vec<_>, _>>()?;
        python_list_string(&list_values)
    } else {
        encoded
    };
    Ok(Some(TypedParameter {
        usage: scalar_atom(usage[0])?.into(),
        declared_type: declared_type.into(),
        format: format.into(),
        encoded,
        choices,
        range: if format == "Range" && declared_type != "Integer" {
            let values = lookup(format).ok_or(PybertAmiWorkerErrorV1::InvalidInput)?;
            Some((parse_numeric(values[1])?, parse_numeric(values[2])?))
        } else {
            None
        },
        integer_range: if format == "Range" && declared_type == "Integer" {
            let values = lookup(format).ok_or(PybertAmiWorkerErrorV1::InvalidInput)?;
            Some((
                strict_integer(values[1])?.parse().unwrap(),
                strict_integer(values[2])?.parse().unwrap(),
            ))
        } else {
            None
        },
    }))
}

fn validate_metadata_node(node: &AmiTextListV1) -> Result<bool, PybertAmiWorkerErrorV1> {
    let name = list_name(node).ok_or(PybertAmiWorkerErrorV1::InvalidInput)?;
    match name {
        "Description" | "Label" => {
            let values = metadata_values(node)?;
            if values.len() != 1 {
                return Err(PybertAmiWorkerErrorV1::InvalidInput);
            }
            let _ = quoted_value(values[0])?;
            Ok(true)
        }
        "List_Tip" | "Labels" => {
            let values = metadata_values(node)?;
            if values.is_empty() {
                return Err(PybertAmiWorkerErrorV1::InvalidInput);
            }
            for value in values {
                let _ = quoted_value(value)?;
            }
            Ok(true)
        }
        _ => Ok(false),
    }
}

fn walk_declaration(
    node: &AmiTextListV1,
    analysis: &mut DeclarationAnalysis,
    in_reserved: bool,
    reserved_direct: bool,
    in_model: bool,
    parent_path: &[String],
) -> Result<(), PybertAmiWorkerErrorV1> {
    let name = list_name(node).ok_or(PybertAmiWorkerErrorV1::InvalidInput)?;
    if name.is_empty() {
        return Err(PybertAmiWorkerErrorV1::InvalidInput);
    }
    let mut path = parent_path.to_vec();
    path.push(name.to_owned());
    if analysis.paths.iter().any(|existing| existing == &path) {
        return Err(PybertAmiWorkerErrorV1::InvalidInput);
    }
    analysis.paths.push(path.clone());
    if matches!(name, "Description" | "List_Tip" | "Labels" | "Label")
        && validate_metadata_node(node)?
    {
        if in_reserved {
            return Err(PybertAmiWorkerErrorV1::InvalidInput);
        }
        return Ok(());
    }
    let typed = typed_parameter(node)?;
    if let Some(parameter) = typed {
        if in_reserved {
            if !reserved_direct || parameter.usage != "Info" {
                return Err(PybertAmiWorkerErrorV1::InvalidInput);
            }
            if name == "GetWave_Exists" {
                if analysis
                    .getwave_exists
                    .replace(parameter.encoded == "True")
                    .is_some()
                {
                    return Err(PybertAmiWorkerErrorV1::InvalidInput);
                }
            } else if name == "Init_Returns_Impulse"
                && analysis
                    .init_returns_impulse
                    .replace(parameter.encoded == "True")
                    .is_some()
            {
                return Err(PybertAmiWorkerErrorV1::InvalidInput);
            }
            analysis.info.push(ParameterDescriptor { path, parameter });
        } else if in_model && matches!(parameter.usage.as_str(), "In" | "InOut") {
            analysis.model.push(ParameterDescriptor { path, parameter });
        }
        return Ok(());
    }
    if validate_metadata_node(node)? {
        return Ok(());
    }
    for child in node.items().iter().skip(1) {
        let AmiTextNodeV1::List(child) = child else {
            return Err(PybertAmiWorkerErrorV1::InvalidInput);
        };
        walk_declaration(
            child,
            analysis,
            in_reserved || name == "Reserved_Parameters",
            false,
            in_model || name == "Model_Specific",
            &path,
        )?;
    }
    Ok(())
}

fn declaration_analysis(
    root: &AmiTextListV1,
) -> Result<DeclarationAnalysis, PybertAmiWorkerErrorV1> {
    let root_name = list_name(root).ok_or(PybertAmiWorkerErrorV1::InvalidInput)?;
    if root_name.is_empty()
        || root
            .items()
            .iter()
            .skip(1)
            .any(|node| !matches!(node, AmiTextNodeV1::List(_)))
    {
        return Err(PybertAmiWorkerErrorV1::InvalidInput);
    }
    let mut analysis = DeclarationAnalysis::default();
    let mut reserved_count = 0;
    let mut model_count = 0;
    let mut description_count = 0;
    for child in root.items().iter().skip(1) {
        let AmiTextNodeV1::List(section) = child else {
            unreachable!()
        };
        let section_name = list_name(section).ok_or(PybertAmiWorkerErrorV1::InvalidInput)?;
        if section_name == "Reserved_Parameters" {
            reserved_count += 1;
            if reserved_count > 1 {
                return Err(PybertAmiWorkerErrorV1::InvalidInput);
            }
            for child in section.items().iter().skip(1) {
                let AmiTextNodeV1::List(child) = child else {
                    return Err(PybertAmiWorkerErrorV1::InvalidInput);
                };
                walk_declaration(child, &mut analysis, true, true, false, &[])?;
            }
        } else if section_name == "Model_Specific" {
            model_count += 1;
            if model_count > 1 {
                return Err(PybertAmiWorkerErrorV1::InvalidInput);
            }
            for child in section.items().iter().skip(1) {
                let AmiTextNodeV1::List(child) = child else {
                    return Err(PybertAmiWorkerErrorV1::InvalidInput);
                };
                walk_declaration(child, &mut analysis, false, false, true, &[])?;
            }
        } else if section_name == "Description" {
            // `example_rx.ami` has one legal top-level metadata node.  It is
            // validated, then intentionally omitted from the AMI init tree.
            description_count += 1;
            if description_count > 1 {
                return Err(PybertAmiWorkerErrorV1::InvalidInput);
            }
            let values = metadata_values(section)?;
            if values.len() != 1 {
                return Err(PybertAmiWorkerErrorV1::InvalidInput);
            }
            let _ = quoted_value(values[0])?;
        } else {
            return Err(PybertAmiWorkerErrorV1::InvalidInput);
        }
    }
    if reserved_count != 1
        || model_count != 1
        || analysis.getwave_exists != Some(true)
        || analysis.init_returns_impulse != Some(true)
    {
        return Err(PybertAmiWorkerErrorV1::InvalidInput);
    }
    Ok(analysis)
}

#[derive(Debug, Clone)]
struct RuntimeLeaf {
    path: Vec<String>,
    value: AmiTextNodeV1,
}

fn flatten_runtime(
    node: &AmiTextListV1,
    parent_path: &[String],
    leaves: &mut Vec<RuntimeLeaf>,
) -> Result<(), PybertAmiWorkerErrorV1> {
    let name = list_name(node).ok_or(PybertAmiWorkerErrorV1::InvalidInput)?;
    if name.is_empty() {
        return Err(PybertAmiWorkerErrorV1::InvalidInput);
    }
    let mut path = parent_path.to_vec();
    path.push(name.to_owned());
    let children = node.items().iter().skip(1).collect::<Vec<_>>();
    if children.is_empty() {
        return Err(PybertAmiWorkerErrorV1::InvalidInput);
    }
    let has_lists = children
        .iter()
        .any(|child| matches!(child, AmiTextNodeV1::List(_)));
    let has_scalars = children
        .iter()
        .any(|child| matches!(child, AmiTextNodeV1::Atom(_) | AmiTextNodeV1::Quoted(_)));
    if has_lists && has_scalars {
        return Err(PybertAmiWorkerErrorV1::InvalidInput);
    }
    if has_lists {
        for child in children {
            let AmiTextNodeV1::List(child) = child else {
                unreachable!()
            };
            flatten_runtime(child, &path, leaves)?;
        }
    } else {
        if children.len() != 1 {
            return Err(PybertAmiWorkerErrorV1::InvalidInput);
        }
        if leaves.iter().any(|leaf| leaf.path == path) {
            return Err(PybertAmiWorkerErrorV1::InvalidInput);
        }
        leaves.push(RuntimeLeaf {
            path,
            value: children[0].clone(),
        });
    }
    Ok(())
}

fn runtime_value(
    parameter: &TypedParameter,
    value: &AmiTextNodeV1,
) -> Result<String, PybertAmiWorkerErrorV1> {
    let format = parameter.format.as_str();
    let encoded = match format {
        "Value" | "Default" => typed_value(parameter.declared_type.as_str(), "Value", &[value])?,
        "Range" if parameter.declared_type == "Integer" => strict_integer(value)?,
        "Range" => python_float_string(parse_numeric(value)?),
        "List" | "Corner" => list_item_value(parameter.declared_type.as_str(), value)?,
        _ => return Err(PybertAmiWorkerErrorV1::InvalidInput),
    };
    if format == "Range" {
        if parameter.declared_type == "Integer" {
            let number = encoded
                .parse::<i64>()
                .map_err(|_| PybertAmiWorkerErrorV1::InvalidInput)?;
            let (minimum, maximum) = parameter
                .integer_range
                .ok_or(PybertAmiWorkerErrorV1::InvalidInput)?;
            if number < minimum || number > maximum {
                return Err(PybertAmiWorkerErrorV1::InvalidInput);
            }
        } else {
            let number = encoded
                .parse::<f64>()
                .map_err(|_| PybertAmiWorkerErrorV1::InvalidInput)?;
            let (minimum, maximum) = parameter
                .range
                .ok_or(PybertAmiWorkerErrorV1::InvalidInput)?;
            if number < minimum || number > maximum {
                return Err(PybertAmiWorkerErrorV1::InvalidInput);
            }
        }
    }
    if matches!(format, "List" | "Corner")
        && !parameter.choices.is_empty()
        && !parameter.choices.iter().any(|choice| choice == &encoded)
    {
        return Err(PybertAmiWorkerErrorV1::InvalidInput);
    }
    Ok(encoded)
}

#[derive(Debug, Default)]
struct OutputNode {
    name: String,
    value: Option<String>,
    children: Vec<OutputNode>,
}

fn insert_output(
    nodes: &mut Vec<OutputNode>,
    path: &[String],
    value: String,
) -> Result<(), PybertAmiWorkerErrorV1> {
    let name = path.first().ok_or(PybertAmiWorkerErrorV1::InvalidInput)?;
    let index = if let Some(index) = nodes.iter().position(|node| &node.name == name) {
        index
    } else {
        nodes.push(OutputNode {
            name: name.clone(),
            value: None,
            children: Vec::new(),
        });
        nodes.len() - 1
    };
    if path.len() == 1 {
        if nodes[index].value.replace(value).is_some() || !nodes[index].children.is_empty() {
            return Err(PybertAmiWorkerErrorV1::InvalidInput);
        }
        return Ok(());
    }
    if nodes[index].value.is_some() {
        return Err(PybertAmiWorkerErrorV1::InvalidInput);
    }
    insert_output(&mut nodes[index].children, &path[1..], value)
}

fn serialize_output_nodes(
    nodes: &[OutputNode],
    output: &mut Vec<u8>,
    separator: bool,
) -> Result<(), PybertAmiWorkerErrorV1> {
    for (index, node) in nodes.iter().enumerate() {
        if index != 0 && separator {
            output.push(b' ');
        }
        output.push(b'(');
        output.extend_from_slice(node.name.as_bytes());
        if let Some(value) = &node.value {
            output.push(b' ');
            output.extend_from_slice(value.as_bytes());
        } else if node.children.is_empty() {
            return Err(PybertAmiWorkerErrorV1::InvalidInput);
        } else {
            output.push(b' ');
            serialize_output_nodes(&node.children, output, true)?;
        }
        output.push(b')');
    }
    Ok(())
}

/// Materialize PyBERT's `_ads_style_ami_init_parameters` boundary without
/// flattening containers or accepting caller-owned Reserved_Parameters.
fn materialize_runtime_parameters(
    declaration: &[u8],
    runtime: &[u8],
) -> Result<Vec<u8>, PybertAmiWorkerErrorV1> {
    let declaration = parse_ami_text_v1(declaration, materializer_parse_limits())
        .map_err(|_| PybertAmiWorkerErrorV1::InvalidInput)?;
    let runtime = parse_ami_text_v1(runtime, materializer_parse_limits())
        .map_err(|_| PybertAmiWorkerErrorV1::InvalidInput)?;
    let declaration_root = single_root(&declaration)?;
    let runtime_root = single_root(&runtime)?;
    let declaration_name =
        list_name(declaration_root).ok_or(PybertAmiWorkerErrorV1::InvalidInput)?;
    let runtime_name = list_name(runtime_root).ok_or(PybertAmiWorkerErrorV1::InvalidInput)?;
    if declaration_name != runtime_name {
        return Err(PybertAmiWorkerErrorV1::InvalidInput);
    }
    let analysis = declaration_analysis(declaration_root)?;
    let mut leaves = Vec::new();
    for child in runtime_root.items().iter().skip(1) {
        let AmiTextNodeV1::List(child) = child else {
            return Err(PybertAmiWorkerErrorV1::InvalidInput);
        };
        flatten_runtime(child, &[], &mut leaves)?;
    }
    let mut output_nodes = Vec::new();
    for descriptor in &analysis.info {
        insert_output(
            &mut output_nodes,
            &descriptor.path,
            descriptor.parameter.encoded.clone(),
        )?;
    }
    for descriptor in &analysis.model {
        let value = if let Some(leaf) = leaves.iter().find(|leaf| leaf.path == descriptor.path) {
            runtime_value(&descriptor.parameter, &leaf.value)?
        } else {
            descriptor.parameter.encoded.clone()
        };
        insert_output(&mut output_nodes, &descriptor.path, value)?;
    }
    if leaves.iter().any(|leaf| {
        !analysis
            .model
            .iter()
            .any(|descriptor| descriptor.path == leaf.path)
    }) {
        return Err(PybertAmiWorkerErrorV1::InvalidInput);
    }
    let mut output = Vec::new();
    output.push(b'(');
    output.extend_from_slice(declaration_name.as_bytes());
    if !output_nodes.is_empty() {
        output.push(b' ');
        serialize_output_nodes(&output_nodes, &mut output, false)?;
    }
    output.push(b')');
    if output.len() > MAX_PARAMETERS_TOTAL_BYTES {
        return Err(PybertAmiWorkerErrorV1::InvalidInput);
    }
    Ok(output)
}

#[cfg(test)]
mod materializer_tests {
    use super::*;

    const DECLARATION: &[u8] = br#"
(example_rx
  (Reserved_Parameters
    (GetWave_Exists (Usage Info) (Type Boolean) (Value True))
    (Init_Returns_Impulse (Usage Info) (Type Boolean) (Value True))
    (First_Info (Usage Info) (Type String) (Value "one"))
    (Second_Info (Usage Info) (Type Boolean) (Value True)))
  (Model_Specific
    (mode (Usage In) (Type String) (Value "NRZ"))))
"#;

    #[test]
    fn materializer_matches_ads_info_order_and_model_override() {
        let runtime = br#"(example_rx (mode "PAM4"))"#;
        let actual = materialize_runtime_parameters(DECLARATION, runtime).expect("materialize");
        assert_eq!(
            actual,
            br#"(example_rx (GetWave_Exists True)(Init_Returns_Impulse True)(First_Info "one")(Second_Info True)(mode "PAM4"))"#
        );
    }

    #[test]
    fn materializer_rejects_missing_info_value_and_root_mismatch() {
        let missing_value =
            br#"(example_rx (Reserved_Parameters (Info (Usage Info) (Type String))))"#;
        assert_eq!(
            materialize_runtime_parameters(missing_value, b"(example_rx (mode 1))")
                .expect_err("missing info value"),
            PybertAmiWorkerErrorV1::InvalidInput
        );
        assert_eq!(
            materialize_runtime_parameters(DECLARATION, b"(other (mode 1))")
                .expect_err("root mismatch"),
            PybertAmiWorkerErrorV1::InvalidInput
        );
    }

    #[test]
    fn materializer_rejects_untyped_legacy_passthrough() {
        assert_eq!(
            materialize_runtime_parameters(b"(mode success)", b"(mode success)")
                .expect_err("untyped declaration"),
            PybertAmiWorkerErrorV1::InvalidInput
        );
    }

    #[test]
    fn materializer_rejects_reserved_override_flatten_and_caller_order() {
        let reserved = br#"(example_rx (Reserved_Parameters (GetWave_Exists False)))"#;
        assert_eq!(
            materialize_runtime_parameters(DECLARATION, reserved).expect_err("reserved override"),
            PybertAmiWorkerErrorV1::InvalidInput
        );
        let arbitrary = br#"(example_rx (raw 1))"#;
        assert_eq!(
            materialize_runtime_parameters(DECLARATION, arbitrary)
                .expect_err("arbitrary top-level"),
            PybertAmiWorkerErrorV1::InvalidInput
        );
        let declaration = br#"(rx
          (Reserved_Parameters
            (GetWave_Exists (Usage Info) (Type Boolean) (Value True))
            (Init_Returns_Impulse (Usage Info) (Type Boolean) (Value True)))
          (Model_Specific
            (first (Usage In) (Type Integer) (Value 1))
            (second (Usage In) (Type String) (Value "two"))))"#;
        let actual =
            materialize_runtime_parameters(declaration, br#"(rx (second "override") (first 7))"#)
                .expect("source order");
        assert_eq!(
            actual,
            br#"(rx (GetWave_Exists True)(Init_Returns_Impulse True)(first 7)(second "override"))"#
        );
    }

    #[test]
    fn materializer_supports_fixed_formats_and_rejects_bad_controls() {
        let declaration = br#"(rx
          (Reserved_Parameters
            (GetWave_Exists (Usage Info) (Type Boolean) (Default True))
            (Init_Returns_Impulse (Usage Info) (Type Boolean) (Value True))
            (f (Usage Info) (Type Float) (Range 1.5 0 2))
            (i (Usage Info) (Type Integer) (Default 1000))
            (s (Usage Info) (Type String) (List "alpha" "beta"))
            (b (Usage Info) (Type Boolean) (Corner False True)))
          (Model_Specific (nested (child (Usage In) (Type UI) (List 3 4)))))"#;
        let actual = materialize_runtime_parameters(declaration, b"(rx)").expect("formats");
        assert_eq!(actual, br#"(rx (GetWave_Exists True)(Init_Returns_Impulse True)(f 1.5)(i 1000)(s ['alpha', 'beta'])(b False)(nested (child 3.0)))"#);
        let false_getwave = br#"(rx
          (Reserved_Parameters
            (GetWave_Exists (Usage Info) (Type Boolean) (Default False))
            (Init_Returns_Impulse (Usage Info) (Type Boolean) (Value True)))
          (Model_Specific (nested (child (Usage In) (Type UI) (List 3 4)))))"#;
        assert_eq!(
            materialize_runtime_parameters(false_getwave, b"(rx)").expect_err("false getwave"),
            PybertAmiWorkerErrorV1::InvalidInput
        );
        let duplicate = br#"(rx
          (Reserved_Parameters
            (GetWave_Exists (Usage Info) (Type Boolean) (Default True))
            (GetWave_Exists (Usage Info) (Type Boolean) (Value True))
            (Init_Returns_Impulse (Usage Info) (Type Boolean) (Value True)))
          (Model_Specific (nested (child (Usage In) (Type UI) (List 3 4)))))"#;
        assert_eq!(
            materialize_runtime_parameters(duplicate, b"(rx)").expect_err("duplicate getwave"),
            PybertAmiWorkerErrorV1::InvalidInput
        );
        let duplicate_format = br#"(rx
          (Reserved_Parameters
            (GetWave_Exists (Usage Info) (Type Boolean) (Value True))
            (Init_Returns_Impulse (Usage Info) (Type Boolean) (Value True)))
          (Model_Specific
            (x (Usage In) (Type Float) (Range 1 0 2) (Range 1 0 2))))"#;
        assert_eq!(
            materialize_runtime_parameters(duplicate_format, b"(rx (x 1))")
                .expect_err("duplicate format"),
            PybertAmiWorkerErrorV1::InvalidInput
        );
        let missing = br#"(rx
          (Reserved_Parameters
            (Init_Returns_Impulse (Usage Info) (Type Boolean) (Value True)))
          (Model_Specific (nested (child (Usage In) (Type UI) (List 3 4)))))"#;
        assert_eq!(
            materialize_runtime_parameters(missing, b"(rx)").expect_err("missing getwave"),
            PybertAmiWorkerErrorV1::InvalidInput
        );
        let bad_integer_range = br#"(rx
          (Reserved_Parameters
            (GetWave_Exists (Usage Info) (Type Boolean) (Value True))
            (Init_Returns_Impulse (Usage Info) (Type Boolean) (Value True)))
          (Model_Specific
            (i (Usage In) (Type Integer) (Range 1.5 0 2))))"#;
        assert_eq!(
            materialize_runtime_parameters(bad_integer_range, b"(rx (i 1))")
                .expect_err("fractional integer range"),
            PybertAmiWorkerErrorV1::InvalidInput
        );
        let bad_integer_list = br#"(rx
          (Reserved_Parameters
            (GetWave_Exists (Usage Info) (Type Boolean) (Value True)))
          (Model_Specific
            (i (Usage In) (Type Integer) (List 1.5 2))))"#;
        assert_eq!(
            materialize_runtime_parameters(bad_integer_list, b"(rx (i 2))")
                .expect_err("fractional integer list"),
            PybertAmiWorkerErrorV1::InvalidInput
        );
        let tap_value = br#"(rx
          (Reserved_Parameters
            (GetWave_Exists (Usage Info) (Type Boolean) (Value True))
            (Init_Returns_Impulse (Usage Info) (Type Boolean) (Value True)))
          (Model_Specific
            (tap (Usage In) (Type Tap) (Value "tap-1"))))"#;
        assert_eq!(
            materialize_runtime_parameters(tap_value, br#"(rx (tap "tap-2"))"#)
                .expect("Tap Value string"),
            br#"(rx (GetWave_Exists True)(Init_Returns_Impulse True)(tap "tap-2"))"#
        );
        let nested_gate = br#"(rx
          (Reserved_Parameters
            (Nested (GetWave_Exists (Usage Info) (Type Boolean) (Value True)))
            (Init_Returns_Impulse (Usage Info) (Type Boolean) (Value True)))
          (Model_Specific (x (Usage In) (Type Float) (Value 1))))"#;
        assert_eq!(
            materialize_runtime_parameters(nested_gate, b"(rx)").expect_err("nested getwave gate"),
            PybertAmiWorkerErrorV1::InvalidInput
        );
        let out_default = br#"(rx
          (Reserved_Parameters
            (GetWave_Exists (Usage Info) (Type Boolean) (Value True))
            (Init_Returns_Impulse (Usage Info) (Type Boolean) (Value True)))
          (Model_Specific (x (Usage Out) (Type Float) (Default 1))))"#;
        assert_eq!(
            materialize_runtime_parameters(out_default, b"(rx)").expect_err("out default"),
            PybertAmiWorkerErrorV1::InvalidInput
        );
        let huge_integer = br#"(rx
          (Reserved_Parameters
            (GetWave_Exists (Usage Info) (Type Boolean) (Value True))
            (Init_Returns_Impulse (Usage Info) (Type Boolean) (Value True)))
          (Model_Specific (x (Usage In) (Type Integer) (Range 1 0 9223372036854775808))))"#;
        assert_eq!(
            materialize_runtime_parameters(huge_integer, b"(rx (x 1) )").expect_err("huge integer"),
            PybertAmiWorkerErrorV1::InvalidInput
        );
    }

    #[test]
    fn archived_example_rx_description_and_metadata_materialize() {
        // This fixture is copied from the pinned PyBERT archive
        // 5bf6d7ea0ace261891aaeb611ffc1c267e160afe:
        // models/ibisami/example_rx.ami.  Description/List_Tip metadata is
        // validated but must not leak into AMIModel.initialize parameters.
        let declaration = include_bytes!(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/tests/fixtures/example_rx.ami"
        ));
        assert_eq!(declaration.len(), 3373);
        assert_eq!(
            sha256_bytes(declaration),
            "5c0c971be411a9af2a9e1cfdf2222086bf9d0c82946ed740c91b364f1d43113d"
        );
        let output = materialize_runtime_parameters(declaration, b"(example_rx (ctle_mode 1))")
            .expect("archived declaration is a supported typed profile");
        let output = String::from_utf8(output).expect("AMI sexpr is UTF-8");
        assert_eq!(
            output,
            "(example_rx (AMI_Version \"5.1\")(Init_Returns_Impulse True)(GetWave_Exists True)(ctle_mode 1)(ctle_freq 5000000000.0)(ctle_mag 0.0)(ctle_bandwidth 12000000000.0)(ctle_dcgain 0.0)(dfe_mode 0)(dfe_ntaps 5)(dfe_tap1 0.0)(dfe_tap2 0.0)(dfe_tap3 0.0)(dfe_tap4 0.0)(dfe_tap5 0.0)(dfe_vout 1.0)(dfe_gain 0.1)(debug (dbg_enable False) (dump_dfe_adaptation False) (dump_adaptation_input False)))"
        );
    }

    #[test]
    fn runtime_uses_range_and_list_descriptor_formats() {
        let declaration = br#"(rx
          (Reserved_Parameters
            (GetWave_Exists (Usage Info) (Type Boolean) (Value True))
            (Init_Returns_Impulse (Usage Info) (Type Boolean) (Value True)))
          (Model_Specific
            (tap_range (Usage In) (Type Tap) (Range 2 0 4))
            (tap_list (Usage In) (Type Tap) (List 1 2) (Default 2))
            (text_list (Usage In) (Type String) (List "a" "b") (Default "b"))
            (integer_list (Usage In) (Type Integer) (List 1 2) (Default 2))))"#;
        let runtime = br#"(rx (tap_range 3) (tap_list 1))"#;
        let output = materialize_runtime_parameters(declaration, runtime).expect("typed runtime");
        assert_eq!(
            output,
            br#"(rx (GetWave_Exists True)(Init_Returns_Impulse True)(tap_range 3.0)(tap_list 1)(text_list "b")(integer_list 2))"#
        );
    }

    #[test]
    fn integer_value_and_default_are_lexical_i64() {
        let controls = br#"(Reserved_Parameters
            (GetWave_Exists (Usage Info) (Type Boolean) (Value True))
            (Init_Returns_Impulse (Usage Info) (Type Boolean) (Value True)))"#;
        let fractional = br#"(rx
          (Reserved_Parameters
            (GetWave_Exists (Usage Info) (Type Boolean) (Value True))
            (Init_Returns_Impulse (Usage Info) (Type Boolean) (Value True)))
          (Model_Specific (x (Usage In) (Type Integer) (Value 1e3))))"#;
        assert_eq!(
            materialize_runtime_parameters(fractional, b"(rx (x 1))")
                .expect_err("fractional integer value"),
            PybertAmiWorkerErrorV1::InvalidInput
        );
        let overflow = br#"(rx
          (Reserved_Parameters
            (GetWave_Exists (Usage Info) (Type Boolean) (Value True))
            (Init_Returns_Impulse (Usage Info) (Type Boolean) (Value True)))
          (Model_Specific (x (Usage In) (Type Integer) (Default 9223372036854775808))))"#;
        assert_eq!(
            materialize_runtime_parameters(overflow, b"(rx)")
                .expect_err("overflow integer default"),
            PybertAmiWorkerErrorV1::InvalidInput
        );
        assert!(controls.starts_with(b"(Reserved_Parameters"));
    }
}

/// Build a fresh, content-addressed worker launch from PyBERT's file bundle.
pub fn prepare_pybert_ami_launch(
    root: &Path,
    request: &PybertAmiRequestV1,
) -> Result<PybertAmiLaunchV2, PybertAmiWorkerErrorV1> {
    let root = checked_root(root)?;
    if request.rows > MAX_ROWS
        || request.aggressors > MAX_AGGRESSORS
        || request.rows == 0
        || !request.sample_interval.is_finite_positive()
        || !request.bit_time.is_finite_positive()
        || request.samples_per_bit == 0
        || request.samples_per_bit > 1_000_000
        || request.block_size_bits == 0
        || request.block_size_bits > 1_000_000
        || request.max_waveform_samples == 0
        || request.max_waveform_samples > 8_000_000
        || request.clock_capacity == 0
        || request.clock_capacity > 1_000_000
        || request.max_parameters_bytes == 0
        || request.max_parameters_bytes > 65_536
        || request.runtime_parameters.is_empty()
        || request.runtime_parameters.len() > request.max_parameters_bytes
        || request.runtime_parameters.bytes().any(|byte| byte == 0)
        || request.deadline_ms == 0
        || !worker_token(&request.artifact_id)
        || request.deadline_ms > 300_000
        || !valid_sha256(&request.expected_worker_sha256)
        || request.expected_worker_bytes == 0
        || request.expected_worker_bytes > 256 * 1024 * 1024
    {
        return Err(PybertAmiWorkerErrorV1::InvalidInput);
    }
    if !matches!(request.mode, PybertAmiModeV1::InitGetWave) {
        return Err(PybertAmiWorkerErrorV1::UnsupportedMode);
    }
    let waveform_bytes = request
        .max_waveform_samples
        .checked_mul(8)
        .ok_or(PybertAmiWorkerErrorV1::InvalidInput)?;
    let matrix_samples = request
        .rows
        .checked_mul(
            request
                .aggressors
                .checked_add(1)
                .ok_or(PybertAmiWorkerErrorV1::InvalidInput)?,
        )
        .ok_or(PybertAmiWorkerErrorV1::InvalidInput)?;
    let matrix_bytes = matrix_samples
        .checked_mul(8)
        .ok_or(PybertAmiWorkerErrorV1::InvalidInput)?;
    if matrix_samples > 4_000_000
        || matrix_bytes > 64 * 1024 * 1024
        || request
            .block_size_bits
            .checked_mul(request.samples_per_bit)
            .is_none_or(|samples| samples > request.max_waveform_samples)
    {
        return Err(PybertAmiWorkerErrorV1::InvalidInput);
    }
    let block_samples = request
        .block_size_bits
        .checked_mul(request.samples_per_bit)
        .ok_or(PybertAmiWorkerErrorV1::InvalidInput)?;
    let block_count = request.max_waveform_samples.div_ceil(block_samples);
    let structure_bytes = block_count
        .checked_mul(std::mem::size_of::<String>() + 8)
        .ok_or(PybertAmiWorkerErrorV1::InvalidInput)?;
    if block_count > 100_000 || structure_bytes > MAX_PARAMETERS_TOTAL_BYTES {
        return Err(PybertAmiWorkerErrorV1::InvalidInput);
    }
    let ibis = identity(&root, &request.ibis_path, ".ibs", MAX_ASSET_BYTES)?;
    let ami = identity(
        &root,
        &request.ami_path,
        ".ami",
        request.max_parameters_bytes as u64,
    )?;
    let ami_source = fs::read(checked_asset_path(&root, &request.ami_path)?)
        .map_err(|_| PybertAmiWorkerErrorV1::AssetUnavailable)?;
    if sha256_bytes(&ami_source) != ami.sha256 || ami_source.len() as u64 != ami.bytes {
        return Err(PybertAmiWorkerErrorV1::AssetIdentity);
    }
    let materialized_runtime =
        materialize_runtime_parameters(&ami_source, request.runtime_parameters.as_bytes())?;
    if materialized_runtime.len() > request.max_parameters_bytes {
        return Err(PybertAmiWorkerErrorV1::InvalidInput);
    }
    let dll = identity(&root, &request.dll_path, ".dll", MAX_ASSET_BYTES)?;
    let nonce = nonce()?;
    let runtime_path = format!("runtime-{nonce}.ami");
    let runtime_file = root.join(&runtime_path);
    write_new(&root, &runtime_path, &nonce, &materialized_runtime)?;
    let mut runtime_guard = RuntimeFileGuard {
        path: runtime_file,
        keep: false,
    };
    let runtime = identity(
        &root,
        &runtime_path,
        ".ami",
        request.max_parameters_bytes as u64,
    )?;
    let matrix = identity(
        &root,
        &request.init_matrix_path,
        ".f64le",
        matrix_bytes as u64,
    )?;
    if matrix.bytes != matrix_bytes as u64 {
        return Err(PybertAmiWorkerErrorV1::AssetIdentity);
    }
    let waveform = identity(
        &root,
        &request.waveform_path,
        ".f64le",
        waveform_bytes as u64,
    )?;
    if runtime.bytes as usize > request.max_parameters_bytes {
        return Err(PybertAmiWorkerErrorV1::InvalidInput);
    }
    let bundle_without_digest = PybertAmiAssetBundleV1 {
        ibis: ibis.clone(),
        ami: ami.clone(),
        dll: dll.clone(),
        closure_sha256: String::new(),
    };
    let closure_sha256 = closure_digest(&[ibis.clone(), ami.clone()])?;
    let bundle = PybertAmiAssetBundleV1 {
        closure_sha256,
        ..bundle_without_digest
    };
    let mut job = AmiWorkerJobV2 {
        schema: "sipi.ami-worker.job.v2".into(),
        job_id: nonce.clone(),
        abi_contract_revision: "p4b-ami-standard-abi-host.v1".into(),
        dll,
        closure: vec![ibis, ami.clone()],
        init_matrix: matrix,
        parameters: runtime,
        waveform,
        rows: request.rows,
        aggressors: request.aggressors,
        sample_interval_s: request.sample_interval.0,
        bit_time_s: request.bit_time.0,
        clock_capacity: request.clock_capacity,
        deadline_ms: request.deadline_ms,
        cancel_file: format!("cancel-{nonce}.flag"),
        artifact_id: request.artifact_id.clone(),
        request_sha256: String::new(),
        root_sha256: digest_root(&root),
        getwave_bits_per_call: request.block_size_bits,
        samples_per_bit: request.samples_per_bit,
        max_parameters_bytes: request.max_parameters_bytes,
    };
    let payload = serde_json::json!({
        "schema": PYBERT_AMI_ADAPTER_SCHEMA_V2,
        "nonce": &nonce,
        "mode": &request.mode,
        "block_size_bits": request.block_size_bits,
        "max_waveform_samples": request.max_waveform_samples,
        "max_parameters_bytes": request.max_parameters_bytes,
        "expected_worker_sha256": &request.expected_worker_sha256,
        "expected_worker_bytes": request.expected_worker_bytes,
        "asset_bundle": &bundle,
        "job": &job,
    });
    let request_sha256 = sha256_bytes(
        &serde_json::to_vec(&payload).map_err(|_| PybertAmiWorkerErrorV1::Serialization)?,
    );
    job.request_sha256 = request_sha256.clone();
    let launch = PybertAmiLaunchV2 {
        schema: PYBERT_AMI_ADAPTER_SCHEMA_V2.into(),
        nonce,
        root_sha256: digest_root(&root),
        mode: request.mode.clone(),
        request_sha256,
        block_size_bits: request.block_size_bits,
        max_waveform_samples: request.max_waveform_samples,
        max_parameters_bytes: request.max_parameters_bytes,
        expected_worker_sha256: request.expected_worker_sha256.clone(),
        expected_worker_bytes: request.expected_worker_bytes,
        asset_bundle: bundle,
        job,
    };
    let worker_bundle = WorkerBundleManifestV2 {
        schema: "sipi.ami-worker.bundle.v2".into(),
        worker_sha256: request.expected_worker_sha256.clone(),
        worker_bytes: request.expected_worker_bytes,
        abi_contract_revision: launch.job.abi_contract_revision.clone(),
    };
    validate_launch_contract(&launch, &root, &worker_bundle)?;
    runtime_guard.keep = true;
    Ok(launch)
}

/// Write the launch and supervise the existing one-job worker process. The
/// worker re-reads and re-hashes every closure member before DLL access.
pub fn supervise_prepared_pybert_ami_job(
    root: &Path,
    launch: &PybertAmiLaunchV2,
    worker: &Path,
    bundle: &WorkerBundleManifestV2,
    timeout: Duration,
) -> Result<SupervisorReceiptV1, PybertAmiWorkerErrorV1> {
    validate_launch_binding(launch)?;
    let root = checked_root(root)?;
    if !root.is_absolute()
        || launch.schema != PYBERT_AMI_ADAPTER_SCHEMA_V2
        || launch.nonce != launch.job.job_id
        || !matches!(launch.mode, PybertAmiModeV1::InitGetWave)
        || launch.block_size_bits == 0
        || launch.max_waveform_samples == 0
        || launch.max_parameters_bytes == 0
        || launch.max_parameters_bytes != launch.job.max_parameters_bytes
        || !valid_sha256(&launch.expected_worker_sha256)
        || launch.expected_worker_bytes == 0
        || launch.expected_worker_bytes > 256 * 1024 * 1024
    {
        return Err(PybertAmiWorkerErrorV1::InvalidInput);
    }
    if launch.root_sha256 != digest_root(&root) {
        return Err(PybertAmiWorkerErrorV1::AssetIdentity);
    }
    validate_launch_contract(launch, &root, bundle)?;
    if launch.expected_worker_sha256 != bundle.worker_sha256
        || launch.expected_worker_bytes != bundle.worker_bytes
    {
        return Err(PybertAmiWorkerErrorV1::AssetIdentity);
    }
    if root.join(JOB_FILE).exists() || root.join(LAUNCH_FILE).exists() {
        return Err(PybertAmiWorkerErrorV1::NonFreshRoot);
    }
    let job_bytes =
        serde_json::to_vec(&launch.job).map_err(|_| PybertAmiWorkerErrorV1::Serialization)?;
    let launch_bytes =
        serde_json::to_vec(launch).map_err(|_| PybertAmiWorkerErrorV1::Serialization)?;
    write_new(&root, LAUNCH_FILE, &launch.nonce, &launch_bytes)?;
    if let Err(error) = write_new(&root, JOB_FILE, &launch.nonce, &job_bytes) {
        let _ = fs::remove_file(root.join(LAUNCH_FILE));
        return Err(error);
    }
    supervise_worker_v2(bundle, worker, &root, timeout, false).map_err(Into::into)
}

fn write_new(
    root: &Path,
    name: &str,
    nonce: &str,
    bytes: &[u8],
) -> Result<(), PybertAmiWorkerErrorV1> {
    let final_path = root.join(name);
    let temp_path = root.join(format!(".{name}.tmp-{nonce}"));
    let mut file = fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&temp_path)
        .map_err(|_| PybertAmiWorkerErrorV1::AssetUnavailable)?;
    if file.write_all(bytes).is_err() || file.sync_all().is_err() {
        let _ = fs::remove_file(&temp_path);
        return Err(PybertAmiWorkerErrorV1::AssetUnavailable);
    }
    drop(file);
    if fs::rename(&temp_path, &final_path).is_err() {
        let _ = fs::remove_file(&temp_path);
        return Err(PybertAmiWorkerErrorV1::NonFreshRoot);
    }
    Ok(())
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct WorkerResultMetadata {
    schema: String,
    job_sha256: String,
    request_sha256: String,
    dll_sha256: String,
    closure_sha256: String,
    waveform_sha256: String,
    waveform_count: usize,
    clock_sha256: String,
    clock_count: usize,
    parameters_out_sha256: String,
    parameters_out_count: usize,
    parameters_out_total_bytes: usize,
    close_status: i32,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct WorkerProvenance {
    schema: String,
    job_sha256: String,
    request_sha256: String,
    dll_sha256: String,
    closure_sha256: String,
    abi_contract_revision: String,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct WorkerParametersOut {
    schema: String,
    blocks: Vec<String>,
    count: usize,
    total_bytes: usize,
}

/// Consume the worker's sealed artifact, rather than accepting an adapter-
/// invented payload. The supervisor receipt carries the worker-verified
/// manifest digest and identity receipt.
pub fn consume_pybert_ami_result(
    artifact_root: &Path,
    launch: &PybertAmiLaunchV2,
    receipt: &SupervisorReceiptV1,
) -> Result<PybertAmiHostResultV2, PybertAmiWorkerErrorV1> {
    validate_launch_binding(launch)?;
    if receipt.outcome != sipi_ami_worker::SupervisorOutcomeV1::Completed
        || receipt.artifact_id != launch.job.artifact_id
        || receipt.worker_pre != receipt.worker_post
        || receipt.worker_pre.sha256.len() != 64
        || receipt.worker_pre.bytes == 0
        || launch.expected_worker_sha256 != receipt.worker_pre.sha256
        || launch.expected_worker_bytes != receipt.worker_pre.bytes
        || !valid_sha256(&receipt.worker_pre.sha256)
    {
        return Err(PybertAmiWorkerErrorV1::InvalidResult);
    }
    let manifest_sha256 = receipt
        .manifest_sha256
        .as_deref()
        .ok_or(PybertAmiWorkerErrorV1::InvalidResult)?;
    if !valid_sha256(manifest_sha256) {
        return Err(PybertAmiWorkerErrorV1::InvalidResult);
    }
    let artifact_root =
        checked_root(artifact_root).map_err(|_| PybertAmiWorkerErrorV1::AssetIdentity)?;
    let sealed_root = artifact_root
        .parent()
        .ok_or(PybertAmiWorkerErrorV1::AssetIdentity)?;
    if artifact_root.file_name().and_then(|name| name.to_str()) != Some("artifacts")
        || digest_root(sealed_root) != launch.root_sha256
    {
        return Err(PybertAmiWorkerErrorV1::AssetIdentity);
    }
    // Re-run the same cross-field contract used before launch.  Consumption
    // must not become a weaker, late-only validation path.
    let receipt_bundle = WorkerBundleManifestV2 {
        schema: "sipi.ami-worker.bundle.v2".into(),
        worker_sha256: launch.expected_worker_sha256.clone(),
        worker_bytes: launch.expected_worker_bytes,
        abi_contract_revision: launch.job.abi_contract_revision.clone(),
    };
    validate_launch_contract(launch, sealed_root, &receipt_bundle)
        .map_err(|_| PybertAmiWorkerErrorV1::InvalidResult)?;
    let root = ArtifactRoot::open_existing(&artifact_root)
        .map_err(|_| PybertAmiWorkerErrorV1::InvalidResult)?;
    let policy = VerifiedConsumptionPolicyV1::try_new(256 * 1024, 96 * 1024 * 1024)
        .map_err(|_| PybertAmiWorkerErrorV1::InvalidResult)?;
    let files = root
        .consume_exact_verified_v1(
            &launch.job.artifact_id,
            manifest_sha256,
            &[
                ("result.json", 256 * 1024),
                ("provenance.json", 256 * 1024),
                ("waveform.f64le", 8 * 8_000_000),
                ("clocks.f64le", 8 * 1_000_000),
                (
                    "parameters_out.json",
                    (MAX_PARAMETERS_TOTAL_BYTES + 256 * 1024) as u64,
                ),
            ],
            policy,
        )
        .map_err(|_| PybertAmiWorkerErrorV1::InvalidResult)?;
    let metadata: WorkerResultMetadata = serde_json::from_slice(
        files
            .file("result.json")
            .ok_or(PybertAmiWorkerErrorV1::InvalidResult)?,
    )
    .map_err(|_| PybertAmiWorkerErrorV1::InvalidResult)?;
    let provenance: WorkerProvenance = serde_json::from_slice(
        files
            .file("provenance.json")
            .ok_or(PybertAmiWorkerErrorV1::InvalidResult)?,
    )
    .map_err(|_| PybertAmiWorkerErrorV1::InvalidResult)?;
    let parameters: WorkerParametersOut = serde_json::from_slice(
        files
            .file("parameters_out.json")
            .ok_or(PybertAmiWorkerErrorV1::InvalidResult)?,
    )
    .map_err(|_| PybertAmiWorkerErrorV1::InvalidResult)?;
    let job_bytes =
        serde_json::to_vec(&launch.job).map_err(|_| PybertAmiWorkerErrorV1::Serialization)?;
    let waveform = decode_f64_bytes(
        files
            .file("waveform.f64le")
            .ok_or(PybertAmiWorkerErrorV1::InvalidResult)?,
        launch.max_waveform_samples,
        false,
    )?;
    let clocks = decode_f64_bytes(
        files
            .file("clocks.f64le")
            .ok_or(PybertAmiWorkerErrorV1::InvalidResult)?,
        1_000_000,
        true,
    )?;
    let block_samples = launch
        .job
        .getwave_bits_per_call
        .checked_mul(launch.job.samples_per_bit)
        .ok_or(PybertAmiWorkerErrorV1::InvalidResult)?;
    if block_samples == 0 {
        return Err(PybertAmiWorkerErrorV1::InvalidResult);
    }
    let expected_waveform_samples = launch.job.waveform.bytes / 8;
    let block_count = waveform.len().div_ceil(block_samples);
    let clock_limit = block_count
        .checked_mul(launch.job.clock_capacity)
        .ok_or(PybertAmiWorkerErrorV1::InvalidResult)?;
    if metadata.schema != "sipi.ami-worker.result.v2"
        || metadata.job_sha256 != sha256_bytes(&job_bytes)
        || metadata.request_sha256 != launch.request_sha256
        || metadata.dll_sha256 != launch.asset_bundle.dll.sha256
        || metadata.closure_sha256 != launch.asset_bundle.closure_sha256
        || metadata.waveform_sha256 != digest_f64(&waveform)
        || metadata.waveform_count != waveform.len()
        || !launch.job.waveform.bytes.is_multiple_of(8)
        || waveform.len() as u64 != expected_waveform_samples
        || metadata.clock_sha256 != digest_f64(&clocks)
        || metadata.clock_count != clocks.len()
        || clocks.len() > clock_limit
        || clocks.iter().any(|value| *value < 0.0)
        || clocks.windows(2).any(|pair| pair[1] < pair[0])
        || metadata.close_status != 1
        || metadata.parameters_out_sha256 != digest_parameters(&parameters.blocks)
        || metadata.parameters_out_count != parameters.blocks.len()
        || metadata.parameters_out_total_bytes != parameters.total_bytes
        || parameters.schema != "sipi.ami-worker.parameters-out.v2"
        || parameters.count != parameters.blocks.len()
        || parameters.total_bytes > MAX_PARAMETERS_TOTAL_BYTES
        || parameters.blocks.iter().any(|value| {
            value.len() > MAX_PARAMETERS_BLOCK_BYTES
                || value.len() > launch.max_parameters_bytes
                || value.bytes().any(|byte| byte == 0)
        })
        || block_samples == 0
        || parameters.blocks.len() != block_count
        || parameters.blocks.iter().map(String::len).sum::<usize>() != parameters.total_bytes
        || provenance.schema != "sipi.ami-worker.provenance.v2"
        || provenance.job_sha256 != sha256_bytes(&job_bytes)
        || provenance.request_sha256 != launch.request_sha256
        || provenance.dll_sha256 != launch.asset_bundle.dll.sha256
        || provenance.closure_sha256 != launch.asset_bundle.closure_sha256
        || provenance.abi_contract_revision != launch.job.abi_contract_revision
    {
        return Err(PybertAmiWorkerErrorV1::InvalidResult);
    }
    Ok(PybertAmiHostResultV2 {
        schema: PYBERT_AMI_ADAPTER_SCHEMA_V2.into(),
        nonce: launch.nonce.clone(),
        request_sha256: launch.request_sha256.clone(),
        mode: launch.mode.clone(),
        status: "ok".into(),
        waveform,
        clocks_s: clocks,
        parameters_out: parameters.blocks,
        close_status: metadata.close_status,
    })
}

fn decode_f64_bytes(
    bytes: &[u8],
    maximum: usize,
    allow_empty: bool,
) -> Result<Vec<f64>, PybertAmiWorkerErrorV1> {
    if (!allow_empty && bytes.is_empty())
        || !bytes.len().is_multiple_of(8)
        || bytes.len() / 8 > maximum
    {
        return Err(PybertAmiWorkerErrorV1::InvalidResult);
    }
    let mut values = Vec::with_capacity(bytes.len() / 8);
    for chunk in bytes.chunks_exact(8) {
        let value = f64::from_le_bytes(
            chunk
                .try_into()
                .map_err(|_| PybertAmiWorkerErrorV1::InvalidResult)?,
        );
        if !value.is_finite() {
            return Err(PybertAmiWorkerErrorV1::InvalidResult);
        }
        values.push(value);
    }
    Ok(values)
}

fn digest_f64(values: &[f64]) -> String {
    let mut hash = Sha256::new();
    for value in values {
        hash.update(value.to_le_bytes());
    }
    format!("{:x}", hash.finalize())
}

fn digest_parameters(values: &[String]) -> String {
    sha256_bytes(&serde_json::to_vec(values).unwrap_or_default())
}
