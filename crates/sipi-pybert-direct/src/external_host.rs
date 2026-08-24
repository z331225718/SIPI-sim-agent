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
    let dll = identity(&root, &request.dll_path, ".dll", MAX_ASSET_BYTES)?;
    let nonce = nonce()?;
    let runtime_path = format!("runtime-{nonce}.ami");
    let runtime_file = root.join(&runtime_path);
    write_new(
        &root,
        &runtime_path,
        &nonce,
        request.runtime_parameters.as_bytes(),
    )?;
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
