#![forbid(unsafe_code)]

//! Private one-job AMI worker protocol. It is deliberately not a CLI route or
//! a security sandbox: its role is bounded process and artifact mechanics.
//! Artifact consumption assumes the existing `sipi-artifacts` non-hostile
//! writer contract; the worker still rejects symlink/path/identity drift.

use std::{
    error::Error,
    fmt, fs,
    path::{Component, Path, PathBuf},
    process::{Child, Command, Stdio},
    thread,
    time::{Duration, Instant},
};

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use sipi_ami_host::{AmiGetWaveRequestV1, AmiHostV1, AmiInitRequestV1, DllSha256V1};
use sipi_ami_text::{
    AmiForwardedParameterSubsetV1, AmiParameterProfileLimitsV1, AmiParameterProfileRoleV1,
    AmiParameterSelectionV1, AmiTextBindingV1, ParseLimitsV1, build_ami_parameter_tree_v1,
    build_forwarded_parameter_subset_v1, parse_and_bind_v1,
};
use sipi_artifacts::ArtifactRoot;

const JOB_SCHEMA: &str = "sipi.ami-worker.job.v2";
const LEGACY_JOB_SCHEMA: &str = "sipi.ami-worker.job.v1";
const RESULT_SCHEMA: &str = "sipi.ami-worker.result.v2";
const PROVENANCE_SCHEMA: &str = "sipi.ami-worker.provenance.v2";
const JOB_FILE: &str = "job.json";
const ARTIFACT_DIR: &str = "artifacts";
const READY_BEFORE_GET_WAVE: &str = ".ready-before-get-wave";
const MAX_JOB_BYTES: u64 = 256 * 1024;
const MAX_INPUT_BYTES: u64 = 64 * 1024 * 1024;
const MAX_WORKER_BYTES: u64 = 256 * 1024 * 1024;
const MAX_CLOSURE_FILES: usize = 16;
const MAX_ROWS: usize = 1_000_000;
const MAX_AGGRESSORS: usize = 1_024;
const MAX_CLOCKS: usize = 1_000_000;
const MAX_WAVEFORM: usize = 8_000_000;
const MAX_PARAMETERS_BLOCK_BYTES: usize = 65_536;
const MAX_PARAMETERS_TOTAL_BYTES: usize = 4 * 1024 * 1024;
const MAX_PARAMETER_BLOCKS: usize = 100_000;
const PARAMETER_BLOCK_OVERHEAD: usize = std::mem::size_of::<String>() + 8;
const MAX_DEADLINE_MS: u64 = 300_000;
const MAX_SUPERVISOR_TIMEOUT: Duration = Duration::from_secs(300);

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct WorkerBundleManifestV1 {
    pub schema: String,
    pub worker_sha256: String,
    pub abi_contract_revision: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct WorkerBundleManifestV2 {
    pub schema: String,
    pub worker_sha256: String,
    pub worker_bytes: u64,
    pub abi_contract_revision: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct AmiWorkerJobV1 {
    pub schema: String,
    pub job_id: String,
    pub abi_contract_revision: String,
    pub dll: FileIdentityV1,
    pub closure: Vec<FileIdentityV1>,
    pub init_matrix: FileIdentityV1,
    pub parameters: FileIdentityV1,
    pub waveform: FileIdentityV1,
    pub rows: usize,
    pub aggressors: usize,
    pub sample_interval_s: f64,
    pub bit_time_s: f64,
    pub clock_capacity: usize,
    pub deadline_ms: u64,
    pub cancel_file: String,
    pub artifact_id: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct AmiWorkerJobV2 {
    pub schema: String,
    pub job_id: String,
    pub abi_contract_revision: String,
    pub dll: FileIdentityV1,
    pub closure: Vec<FileIdentityV1>,
    pub init_matrix: FileIdentityV1,
    pub parameters: FileIdentityV1,
    pub waveform: FileIdentityV1,
    pub rows: usize,
    pub aggressors: usize,
    pub sample_interval_s: f64,
    pub bit_time_s: f64,
    pub clock_capacity: usize,
    pub deadline_ms: u64,
    pub cancel_file: String,
    pub artifact_id: String,
    pub request_sha256: String,
    pub root_sha256: String,
    pub getwave_bits_per_call: usize,
    pub samples_per_bit: usize,
    pub max_parameters_bytes: usize,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct FileIdentityV1 {
    pub path: String,
    pub sha256: String,
    pub bytes: u64,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum WorkerErrorV1 {
    UnsupportedPlatform,
    InvalidJob,
    InvalidBundle,
    PathEscape,
    IdentityMismatch,
    ReadFailed,
    InvalidSidecar,
    Cancelled,
    DeadlineExceeded,
    Host,
    Artifact,
    SpawnFailed,
    WorkerTimedOut,
    WorkerFailed,
}
impl fmt::Display for WorkerErrorV1 {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "AMI worker error: {self:?}")
    }
}
impl Error for WorkerErrorV1 {}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
pub enum SupervisorOutcomeV1 {
    Completed,
    CancelledBeforeStart,
    TimedOut,
    Failed,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct WorkerIdentityV1 {
    pub sha256: String,
    pub bytes: u64,
    pub modified_nanos: u128,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct SupervisorReceiptV1 {
    pub outcome: SupervisorOutcomeV1,
    pub artifact_id: String,
    pub manifest_sha256: Option<String>,
    pub worker_pre: WorkerIdentityV1,
    pub worker_post: WorkerIdentityV1,
}

/// Parse one exact AMI text binding and validate the caller's explicit typed
/// host-forwarded subset.  This adapter is intentionally independent from the
/// worker's DLL lifecycle and never supplies a declaration default.
pub fn prepare_forwarded_parameter_subset_v1(
    parameters: &[u8],
    role: AmiParameterProfileRoleV1,
    selections: &[AmiParameterSelectionV1],
    parse_limits: ParseLimitsV1,
    profile_limits: AmiParameterProfileLimitsV1,
) -> Result<(AmiTextBindingV1, AmiForwardedParameterSubsetV1), WorkerErrorV1> {
    let binding =
        parse_and_bind_v1(parameters, parse_limits).map_err(|_| WorkerErrorV1::InvalidSidecar)?;
    let tree = build_ami_parameter_tree_v1(&binding, role, profile_limits)
        .map_err(|_| WorkerErrorV1::InvalidSidecar)?;
    let subset = build_forwarded_parameter_subset_v1(&tree, selections)
        .map_err(|_| WorkerErrorV1::InvalidSidecar)?;
    Ok((binding, subset))
}

pub fn run_one_job(root: &Path) -> Result<(), WorkerErrorV1> {
    let checked = checked_root(root)?;
    let job_bytes = read_bounded(&checked.join(JOB_FILE), MAX_JOB_BYTES)?;
    let value: serde_json::Value =
        serde_json::from_slice(&job_bytes).map_err(|_| WorkerErrorV1::InvalidJob)?;
    match value.get("schema").and_then(serde_json::Value::as_str) {
        Some(LEGACY_JOB_SCHEMA) => run_one_job_legacy(&checked, &job_bytes),
        Some(JOB_SCHEMA) => run_one_job_v2(&checked, &job_bytes),
        _ => Err(WorkerErrorV1::InvalidJob),
    }
}

fn run_one_job_v2(root: &Path, supplied_job_bytes: &[u8]) -> Result<(), WorkerErrorV1> {
    if !cfg!(all(windows, target_arch = "x86_64")) {
        return Err(WorkerErrorV1::UnsupportedPlatform);
    }
    let root = checked_root(root)?;
    let job_bytes = supplied_job_bytes.to_vec();
    let job = parse_job(&job_bytes, &root)?;
    validate_job(&job)?;
    if job.root_sha256 != digest_root(&root) {
        return Err(WorkerErrorV1::IdentityMismatch);
    }
    let started = Instant::now();
    checkpoint(&root, &job, started)?;
    let dll = checked_file(&root, &job.dll)?;
    for helper in &job.closure {
        let _ = checked_file(&root, helper)?;
    }
    let matrix_bytes = job
        .rows
        .checked_mul(
            job.aggressors
                .checked_add(1)
                .ok_or(WorkerErrorV1::InvalidJob)?,
        )
        .and_then(|values| values.checked_mul(8))
        .ok_or(WorkerErrorV1::InvalidJob)?;
    if job.init_matrix.bytes != matrix_bytes as u64 {
        return Err(WorkerErrorV1::InvalidJob);
    }
    let matrix = decode_f64_bytes(&checked_file_bytes(&root, &job.init_matrix)?)?;
    let parameters = checked_file_bytes(&root, &job.parameters)?;
    let waveform = decode_f64_bytes(&checked_file_bytes(&root, &job.waveform)?)?;
    let limits = ParseLimitsV1::try_new(65_536, 32, 4_096, 8_192)
        .map_err(|_| WorkerErrorV1::InvalidSidecar)?;
    let binding =
        parse_and_bind_v1(&parameters, limits).map_err(|_| WorkerErrorV1::InvalidSidecar)?;
    let init = AmiInitRequestV1::try_new(
        matrix,
        job.rows,
        job.aggressors,
        job.sample_interval_s,
        job.bit_time_s,
    )
    .map_err(|_| WorkerErrorV1::InvalidSidecar)?;
    let mut instance = AmiHostV1::open(&dll, DllSha256V1::from_bytes(parse_hash(&job.dll.sha256)?))
        .map_err(|_| WorkerErrorV1::Host)?
        .initialize_v2(init, &binding, limits)
        .map_err(|_| WorkerErrorV1::Host)?;
    fs::write(root.join(READY_BEFORE_GET_WAVE), b"ready").map_err(|_| WorkerErrorV1::ReadFailed)?;
    checkpoint(&root, &job, started)?;
    let block_samples = job
        .getwave_bits_per_call
        .checked_mul(job.samples_per_bit)
        .ok_or(WorkerErrorV1::InvalidJob)?;
    let mut output_waveform = Vec::with_capacity(waveform.len());
    let mut output_clocks = Vec::new();
    let block_count = waveform
        .len()
        .checked_add(
            block_samples
                .checked_sub(1)
                .ok_or(WorkerErrorV1::InvalidJob)?,
        )
        .and_then(|value| value.checked_div(block_samples))
        .ok_or(WorkerErrorV1::InvalidJob)?;
    let structure_bytes = block_count
        .checked_mul(PARAMETER_BLOCK_OVERHEAD)
        .ok_or(WorkerErrorV1::InvalidJob)?;
    if block_count > MAX_PARAMETER_BLOCKS || structure_bytes > MAX_PARAMETERS_TOTAL_BYTES {
        return Err(WorkerErrorV1::InvalidJob);
    }
    let mut parameters_out = Vec::with_capacity(block_count);
    let mut parameters_total_bytes = 0_usize;
    for block in waveform.chunks(block_samples) {
        checkpoint(&root, &job, started)?;
        let response = instance
            .get_wave_v2(
                AmiGetWaveRequestV1::try_new(block.to_vec(), job.clock_capacity)
                    .map_err(|_| WorkerErrorV1::InvalidSidecar)?,
            )
            .map_err(|_| WorkerErrorV1::Host)?;
        output_waveform.extend_from_slice(response.waveform());
        output_clocks.extend_from_slice(response.clocks_s());
        let block_parameters = response.parameters_out().to_owned();
        if block_parameters.len() > MAX_PARAMETERS_BLOCK_BYTES
            || block_parameters.len() > job.max_parameters_bytes
        {
            return Err(WorkerErrorV1::InvalidJob);
        }
        parameters_total_bytes = parameters_total_bytes
            .checked_add(block_parameters.len())
            .ok_or(WorkerErrorV1::InvalidJob)?;
        if parameters_total_bytes
            .checked_add(structure_bytes)
            .ok_or(WorkerErrorV1::InvalidJob)?
            > MAX_PARAMETERS_TOTAL_BYTES
        {
            return Err(WorkerErrorV1::InvalidJob);
        }
        parameters_out.push(block_parameters);
        if output_waveform.len() > MAX_WAVEFORM || output_clocks.len() > MAX_CLOCKS {
            return Err(WorkerErrorV1::InvalidJob);
        }
        if output_clocks.windows(2).any(|pair| pair[1] < pair[0]) {
            return Err(WorkerErrorV1::Host);
        }
    }
    instance.close().map_err(|_| WorkerErrorV1::Host)?;
    checkpoint(&root, &job, started)?;
    publish_success(
        &root,
        &job,
        &job_bytes,
        &output_waveform,
        &output_clocks,
        &parameters_out,
        parameters_total_bytes,
    )
}

fn run_one_job_legacy(root: &Path, job_bytes: &[u8]) -> Result<(), WorkerErrorV1> {
    if !cfg!(all(windows, target_arch = "x86_64")) {
        return Err(WorkerErrorV1::UnsupportedPlatform);
    }
    let job: AmiWorkerJobV1 =
        serde_json::from_slice(job_bytes).map_err(|_| WorkerErrorV1::InvalidJob)?;
    validate_legacy_job(&job)?;
    let started = Instant::now();
    checkpoint_legacy(root, &job, started)?;
    let dll = checked_file(root, &job.dll)?;
    for helper in &job.closure {
        let _ = checked_file(root, helper)?;
    }
    let expected_matrix = job
        .rows
        .checked_mul(
            job.aggressors
                .checked_add(1)
                .ok_or(WorkerErrorV1::InvalidJob)?,
        )
        .and_then(|count| count.checked_mul(8))
        .ok_or(WorkerErrorV1::InvalidJob)?;
    if job.init_matrix.bytes != expected_matrix as u64 {
        return Err(WorkerErrorV1::InvalidJob);
    }
    let matrix = decode_f64_bytes(&checked_file_bytes(root, &job.init_matrix)?)?;
    let parameters = checked_file_bytes(root, &job.parameters)?;
    let waveform = decode_f64_bytes(&checked_file_bytes(root, &job.waveform)?)?;
    let limits = ParseLimitsV1::try_new(65_536, 32, 4_096, 8_192)
        .map_err(|_| WorkerErrorV1::InvalidSidecar)?;
    let binding =
        parse_and_bind_v1(&parameters, limits).map_err(|_| WorkerErrorV1::InvalidSidecar)?;
    let init = AmiInitRequestV1::try_new(
        matrix,
        job.rows,
        job.aggressors,
        job.sample_interval_s,
        job.bit_time_s,
    )
    .map_err(|_| WorkerErrorV1::InvalidSidecar)?;
    let mut instance = AmiHostV1::open(&dll, DllSha256V1::from_bytes(parse_hash(&job.dll.sha256)?))
        .map_err(|_| WorkerErrorV1::Host)?
        .initialize(init, &binding, limits)
        .map_err(|_| WorkerErrorV1::Host)?;
    fs::write(root.join(READY_BEFORE_GET_WAVE), b"ready").map_err(|_| WorkerErrorV1::ReadFailed)?;
    checkpoint_legacy(root, &job, started)?;
    let response = instance
        .get_wave(
            AmiGetWaveRequestV1::try_new(waveform, job.clock_capacity)
                .map_err(|_| WorkerErrorV1::InvalidSidecar)?,
        )
        .map_err(|_| WorkerErrorV1::Host)?;
    instance.close().map_err(|_| WorkerErrorV1::Host)?;
    checkpoint_legacy(root, &job, started)?;
    publish_success_v1(
        root,
        &job,
        job_bytes,
        response.waveform(),
        response.clocks_s(),
    )
}

pub fn supervise_test_only(
    bundle: &WorkerBundleManifestV1,
    worker: &Path,
    root: &Path,
    timeout: Duration,
    cancel_before_start: bool,
) -> Result<SupervisorOutcomeV1, WorkerErrorV1> {
    supervise_worker_v1(bundle, worker, root, timeout, cancel_before_start)
}

pub fn supervise_worker_v1(
    bundle: &WorkerBundleManifestV1,
    worker: &Path,
    root: &Path,
    timeout: Duration,
    cancel_before_start: bool,
) -> Result<SupervisorOutcomeV1, WorkerErrorV1> {
    let pre = validate_bundle_v1(bundle, worker)?;
    if cancel_before_start {
        return Ok(SupervisorOutcomeV1::CancelledBeforeStart);
    }
    let root = checked_root(root)?;
    let mut child = Command::new(worker)
        .arg("--job-root")
        .arg(&root)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|_| WorkerErrorV1::SpawnFailed)?;
    let outcome = wait_child(&mut child, timeout);
    let post = validate_bundle_v1(bundle, worker)?;
    if pre != post {
        return Err(WorkerErrorV1::IdentityMismatch);
    }
    outcome
}

pub fn supervise_worker_v2(
    bundle: &WorkerBundleManifestV2,
    worker: &Path,
    root: &Path,
    timeout: Duration,
    cancel_before_start: bool,
) -> Result<SupervisorReceiptV1, WorkerErrorV1> {
    let root = checked_root(root)?;
    let pre = validate_bundle(bundle, worker)?;
    let job_bytes = read_bounded(&root.join(JOB_FILE), MAX_JOB_BYTES)?;
    let job: AmiWorkerJobV2 =
        serde_json::from_slice(&job_bytes).map_err(|_| WorkerErrorV1::InvalidJob)?;
    validate_job(&job)?;
    let timeout = Duration::from_millis(job.deadline_ms)
        .min(timeout)
        .min(MAX_SUPERVISOR_TIMEOUT);
    if cancel_before_start {
        return Ok(SupervisorReceiptV1 {
            outcome: SupervisorOutcomeV1::CancelledBeforeStart,
            artifact_id: job.artifact_id,
            manifest_sha256: None,
            worker_pre: pre.clone(),
            worker_post: pre,
        });
    }
    let mut child = Command::new(worker)
        .arg("--job-root")
        .arg(&root)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|_| WorkerErrorV1::SpawnFailed)?;
    let outcome = wait_child(&mut child, timeout);
    let post = validate_bundle(bundle, worker)?;
    if pre != post {
        return Err(WorkerErrorV1::IdentityMismatch);
    }
    let outcome = outcome?;
    let manifest_sha256 = if outcome == SupervisorOutcomeV1::Completed {
        Some(read_manifest_sha256(&root, &job.artifact_id)?)
    } else {
        None
    };
    Ok(SupervisorReceiptV1 {
        outcome,
        artifact_id: job.artifact_id,
        manifest_sha256,
        worker_pre: pre,
        worker_post: post,
    })
}

fn wait_child(child: &mut Child, timeout: Duration) -> Result<SupervisorOutcomeV1, WorkerErrorV1> {
    let deadline = Instant::now()
        .checked_add(timeout)
        .ok_or(WorkerErrorV1::InvalidBundle)?;
    loop {
        let status = match child.try_wait() {
            Ok(status) => status,
            Err(_) => {
                let _ = child.kill();
                let _ = child.wait();
                return Err(WorkerErrorV1::WorkerFailed);
            }
        };
        if let Some(status) = status {
            return Ok(if status.success() {
                SupervisorOutcomeV1::Completed
            } else {
                SupervisorOutcomeV1::Failed
            });
        }
        if Instant::now() >= deadline {
            let _ = child.kill();
            let _ = child.wait();
            return Ok(SupervisorOutcomeV1::TimedOut);
        }
        thread::sleep(Duration::from_millis(5));
    }
}

fn read_manifest_sha256(root: &Path, artifact_id: &str) -> Result<String, WorkerErrorV1> {
    let artifacts = ArtifactRoot::open_existing(root.join(ARTIFACT_DIR))
        .map_err(|_| WorkerErrorV1::Artifact)?;
    artifacts
        .verify_published(artifact_id)
        .map_err(|_| WorkerErrorV1::Artifact)?;
    let manifest = root
        .join(ARTIFACT_DIR)
        .join(artifact_id)
        .join("success.json");
    Ok(digest_hex(&read_bounded(&manifest, 256 * 1024)?))
}

fn parse_job(bytes: &[u8], root: &Path) -> Result<AmiWorkerJobV2, WorkerErrorV1> {
    let _ = root;
    serde_json::from_slice(bytes).map_err(|_| WorkerErrorV1::InvalidJob)
}

fn validate_legacy_job(job: &AmiWorkerJobV1) -> Result<(), WorkerErrorV1> {
    let columns = job
        .aggressors
        .checked_add(1)
        .ok_or(WorkerErrorV1::InvalidJob)?;
    let matrix_values = job
        .rows
        .checked_mul(columns)
        .ok_or(WorkerErrorV1::InvalidJob)?;
    if job.schema != LEGACY_JOB_SCHEMA
        || job.abi_contract_revision != "p4b-ami-standard-abi-host.v1"
        || !token(&job.job_id)
        || !token(&job.artifact_id)
        || job.deadline_ms == 0
        || job.deadline_ms > MAX_DEADLINE_MS
        || job.rows == 0
        || job.rows > MAX_ROWS
        || job.aggressors > MAX_AGGRESSORS
        || matrix_values > 4_000_000
        || job.clock_capacity == 0
        || job.clock_capacity > MAX_CLOCKS
        || !relative(&job.cancel_file)
        || !job.sample_interval_s.is_finite()
        || !job.bit_time_s.is_finite()
        || job.sample_interval_s <= 0.0
        || job.bit_time_s <= 0.0
        || job.closure.len() > MAX_CLOSURE_FILES
    {
        return Err(WorkerErrorV1::InvalidJob);
    }
    for item in [&job.dll, &job.init_matrix, &job.parameters, &job.waveform] {
        validate_identity(item)?;
    }
    for item in &job.closure {
        validate_identity(item)?;
    }
    Ok(())
}

fn validate_bundle_v1(
    bundle: &WorkerBundleManifestV1,
    worker: &Path,
) -> Result<WorkerIdentityV1, WorkerErrorV1> {
    if bundle.schema != "sipi.ami-worker.bundle.v1"
        || bundle.abi_contract_revision != "p4b-ami-standard-abi-host.v1"
        || !worker.is_absolute()
    {
        return Err(WorkerErrorV1::InvalidBundle);
    }
    let metadata = fs::symlink_metadata(worker).map_err(|_| WorkerErrorV1::ReadFailed)?;
    if metadata.file_type().is_symlink() || !metadata.is_file() || metadata.len() > MAX_WORKER_BYTES
    {
        return Err(WorkerErrorV1::InvalidBundle);
    }
    let bytes = fs::read(worker).map_err(|_| WorkerErrorV1::ReadFailed)?;
    if digest_hex(&bytes) != bundle.worker_sha256 || !is_amd64_pe(&bytes) {
        return Err(WorkerErrorV1::IdentityMismatch);
    }
    let modified_nanos = metadata
        .modified()
        .map_err(|_| WorkerErrorV1::ReadFailed)?
        .duration_since(std::time::UNIX_EPOCH)
        .map_err(|_| WorkerErrorV1::ReadFailed)?
        .as_nanos();
    Ok(WorkerIdentityV1 {
        sha256: bundle.worker_sha256.clone(),
        bytes: bytes.len() as u64,
        modified_nanos,
    })
}

fn validate_bundle(
    bundle: &WorkerBundleManifestV2,
    worker: &Path,
) -> Result<WorkerIdentityV1, WorkerErrorV1> {
    if bundle.schema != "sipi.ami-worker.bundle.v2"
        || bundle.abi_contract_revision != "p4b-ami-standard-abi-host.v1"
        || !worker.is_absolute()
    {
        return Err(WorkerErrorV1::InvalidBundle);
    }
    let metadata = fs::symlink_metadata(worker).map_err(|_| WorkerErrorV1::ReadFailed)?;
    if metadata.file_type().is_symlink() || !metadata.is_file() || metadata.len() > MAX_WORKER_BYTES
    {
        return Err(WorkerErrorV1::InvalidBundle);
    }
    let bytes = fs::read(worker).map_err(|_| WorkerErrorV1::ReadFailed)?;
    if bytes.len() as u64 != bundle.worker_bytes
        || digest_hex(&bytes) != bundle.worker_sha256
        || !is_amd64_pe(&bytes)
    {
        return Err(WorkerErrorV1::IdentityMismatch);
    }
    let modified_nanos = metadata
        .modified()
        .map_err(|_| WorkerErrorV1::ReadFailed)?
        .duration_since(std::time::UNIX_EPOCH)
        .map_err(|_| WorkerErrorV1::ReadFailed)?
        .as_nanos();
    Ok(WorkerIdentityV1 {
        sha256: bundle.worker_sha256.clone(),
        bytes: bundle.worker_bytes,
        modified_nanos,
    })
}
fn is_amd64_pe(bytes: &[u8]) -> bool {
    if bytes.len() < 0x40 || &bytes[..2] != b"MZ" {
        return false;
    }
    let offset = u32::from_le_bytes(match bytes[0x3c..0x40].try_into() {
        Ok(value) => value,
        Err(_) => return false,
    }) as usize;
    let Some(signature) = bytes.get(offset..offset.saturating_add(4)) else {
        return false;
    };
    if signature != b"PE\0\0" {
        return false;
    }
    let Some(machine) = bytes.get(offset.saturating_add(4)..offset.saturating_add(6)) else {
        return false;
    };
    u16::from_le_bytes([machine[0], machine[1]]) == 0x8664
}

fn publish_success_v1(
    root: &Path,
    job: &AmiWorkerJobV1,
    job_bytes: &[u8],
    waveform: &[f64],
    clocks: &[f64],
) -> Result<(), WorkerErrorV1> {
    let artifacts = ArtifactRoot::open_or_create(root.join(ARTIFACT_DIR))
        .map_err(|_| WorkerErrorV1::Artifact)?;
    let result = serde_json::to_vec(&serde_json::json!({
        "schema": "sipi.ami-worker.result.v1",
        "waveform_sha256": digest_f64(waveform),
        "clock_sha256": digest_f64(clocks),
        "clock_count": clocks.len()
    }))
    .map_err(|_| WorkerErrorV1::Artifact)?;
    let provenance = serde_json::to_vec(&serde_json::json!({
        "schema": "sipi.ami-worker.provenance.v1",
        "job_sha256": digest_hex(job_bytes),
        "dll_sha256": job.dll.sha256,
        "abi_contract_revision": job.abi_contract_revision
    }))
    .map_err(|_| WorkerErrorV1::Artifact)?;
    if result.len() > 64 * 1024 || provenance.len() > 64 * 1024 {
        return Err(WorkerErrorV1::Artifact);
    }
    let mut stage = artifacts
        .begin(&job.artifact_id)
        .map_err(|_| WorkerErrorV1::Artifact)?;
    stage
        .stage_reader("result.json", result.as_slice(), 64 * 1024)
        .map_err(|_| WorkerErrorV1::Artifact)?;
    stage
        .stage_reader("provenance.json", provenance.as_slice(), 64 * 1024)
        .map_err(|_| WorkerErrorV1::Artifact)?;
    stage
        .seal()
        .map_err(|_| WorkerErrorV1::Artifact)?
        .publish_new()
        .map_err(|_| WorkerErrorV1::Artifact)?;
    Ok(())
}

fn publish_success(
    root: &Path,
    job: &AmiWorkerJobV2,
    job_bytes: &[u8],
    waveform: &[f64],
    clocks: &[f64],
    parameters_out: &[String],
    parameters_total_bytes: usize,
) -> Result<(), WorkerErrorV1> {
    let artifacts = ArtifactRoot::open_or_create(root.join(ARTIFACT_DIR))
        .map_err(|_| WorkerErrorV1::Artifact)?;
    let result = serde_json::to_vec(&serde_json::json!({
        "schema": RESULT_SCHEMA,
        "job_sha256": digest_hex(job_bytes),
        "request_sha256": job.request_sha256,
        "dll_sha256": job.dll.sha256,
        "closure_sha256": closure_digest(&job.closure),
        "waveform_sha256": digest_f64(waveform),
        "waveform_count": waveform.len(),
        "clock_sha256": digest_f64(clocks),
        "clock_count": clocks.len(),
        "parameters_out_sha256": digest_parameters(parameters_out),
        "parameters_out_count": parameters_out.len(),
        "parameters_out_total_bytes": parameters_total_bytes,
        "close_status": 1
    }))
    .map_err(|_| WorkerErrorV1::Artifact)?;
    let provenance = serde_json::to_vec(&serde_json::json!({
        "schema": PROVENANCE_SCHEMA,
        "job_sha256": digest_hex(job_bytes),
        "request_sha256": job.request_sha256,
        "dll_sha256": job.dll.sha256,
        "closure_sha256": closure_digest(&job.closure),
        "abi_contract_revision": job.abi_contract_revision
    }))
    .map_err(|_| WorkerErrorV1::Artifact)?;
    let mut waveform_bytes = Vec::with_capacity(waveform.len() * 8);
    for value in waveform {
        waveform_bytes.extend_from_slice(&value.to_le_bytes());
    }
    let mut clock_bytes = Vec::with_capacity(clocks.len() * 8);
    for value in clocks {
        clock_bytes.extend_from_slice(&value.to_le_bytes());
    }
    let parameters_json = serde_json::to_vec(&serde_json::json!({
        "schema": "sipi.ami-worker.parameters-out.v2",
        "blocks": parameters_out,
        "count": parameters_out.len(),
        "total_bytes": parameters_total_bytes,
    }))
    .map_err(|_| WorkerErrorV1::Artifact)?;
    if parameters_json.len() > MAX_PARAMETERS_TOTAL_BYTES {
        return Err(WorkerErrorV1::Artifact);
    }
    let mut stage = artifacts
        .begin(&job.artifact_id)
        .map_err(|_| WorkerErrorV1::Artifact)?;
    stage
        .stage_reader("result.json", result.as_slice(), 64 * 1024)
        .map_err(|_| WorkerErrorV1::Artifact)?;
    stage
        .stage_reader("provenance.json", provenance.as_slice(), 64 * 1024)
        .map_err(|_| WorkerErrorV1::Artifact)?;
    stage
        .stage_reader("waveform.f64le", waveform_bytes.as_slice(), 8 * 8_000_000)
        .map_err(|_| WorkerErrorV1::Artifact)?;
    stage
        .stage_reader("clocks.f64le", clock_bytes.as_slice(), 8 * 1_000_000)
        .map_err(|_| WorkerErrorV1::Artifact)?;
    stage
        .stage_reader(
            "parameters_out.json",
            parameters_json.as_slice(),
            (MAX_PARAMETERS_TOTAL_BYTES + 256 * 1024) as u64,
        )
        .map_err(|_| WorkerErrorV1::Artifact)?;
    stage
        .seal()
        .map_err(|_| WorkerErrorV1::Artifact)?
        .publish_new()
        .map_err(|_| WorkerErrorV1::Artifact)?;
    Ok(())
}

fn checkpoint(root: &Path, job: &AmiWorkerJobV2, started: Instant) -> Result<(), WorkerErrorV1> {
    if root.join(&job.cancel_file).exists() {
        return Err(WorkerErrorV1::Cancelled);
    }
    if started.elapsed() >= Duration::from_millis(job.deadline_ms) {
        return Err(WorkerErrorV1::DeadlineExceeded);
    }
    Ok(())
}
fn checkpoint_legacy(
    root: &Path,
    job: &AmiWorkerJobV1,
    started: Instant,
) -> Result<(), WorkerErrorV1> {
    if root.join(&job.cancel_file).exists() {
        return Err(WorkerErrorV1::Cancelled);
    }
    if started.elapsed() >= Duration::from_millis(job.deadline_ms) {
        return Err(WorkerErrorV1::DeadlineExceeded);
    }
    Ok(())
}
fn validate_job(job: &AmiWorkerJobV2) -> Result<(), WorkerErrorV1> {
    let columns = job
        .aggressors
        .checked_add(1)
        .ok_or(WorkerErrorV1::InvalidJob)?;
    let matrix_values = job
        .rows
        .checked_mul(columns)
        .ok_or(WorkerErrorV1::InvalidJob)?;
    if job.schema != JOB_SCHEMA
        || job.abi_contract_revision != "p4b-ami-standard-abi-host.v1"
        || !token(&job.job_id)
        || !token(&job.artifact_id)
        || job.deadline_ms == 0
        || job.deadline_ms > MAX_DEADLINE_MS
        || job.rows == 0
        || job.rows > MAX_ROWS
        || job.aggressors > MAX_AGGRESSORS
        || matrix_values > 4_000_000
        || job.clock_capacity == 0
        || job.clock_capacity > MAX_CLOCKS
        || job.getwave_bits_per_call == 0
        || job.samples_per_bit == 0
        || job.getwave_bits_per_call > 1_000_000
        || job.samples_per_bit > 1_000_000
        || job.max_parameters_bytes == 0
        || job.max_parameters_bytes > MAX_PARAMETERS_BLOCK_BYTES
        || job
            .getwave_bits_per_call
            .checked_mul(job.samples_per_bit)
            .is_none_or(|value| value > MAX_WAVEFORM)
        || !relative(&job.cancel_file)
    {
        return Err(WorkerErrorV1::InvalidJob);
    }
    for item in [&job.dll, &job.init_matrix, &job.parameters, &job.waveform] {
        validate_identity(item)?;
    }
    for item in &job.closure {
        validate_identity(item)?;
    }
    if job.request_sha256.len() != 64
        || !job
            .request_sha256
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit())
    {
        return Err(WorkerErrorV1::InvalidJob);
    }
    if job.root_sha256.len() != 64 || !job.root_sha256.bytes().all(|byte| byte.is_ascii_hexdigit())
    {
        return Err(WorkerErrorV1::InvalidJob);
    }
    if job.closure.len() > MAX_CLOSURE_FILES {
        return Err(WorkerErrorV1::InvalidJob);
    }
    Ok(())
}

/// Validate the complete V2 job contract before a supervisor writes or starts
/// a worker.  This is intentionally the same gate used by `run_one_job_v2`,
/// so adapters cannot drift from the worker's admission rules.
pub fn validate_job_v2_contract(job: &AmiWorkerJobV2) -> Result<(), WorkerErrorV1> {
    validate_job(job)
}

fn validate_identity(item: &FileIdentityV1) -> Result<(), WorkerErrorV1> {
    if !relative(&item.path)
        || item.sha256.len() != 64
        || !item
            .sha256
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
    {
        Err(WorkerErrorV1::InvalidJob)
    } else {
        Ok(())
    }
}
fn checked_root(root: &Path) -> Result<PathBuf, WorkerErrorV1> {
    if !root.is_absolute()
        || !fs::symlink_metadata(root)
            .map_err(|_| WorkerErrorV1::ReadFailed)?
            .is_dir()
        || fs::symlink_metadata(root)
            .map_err(|_| WorkerErrorV1::ReadFailed)?
            .file_type()
            .is_symlink()
    {
        Err(WorkerErrorV1::PathEscape)
    } else {
        no_symlink_components(root)?;
        fs::canonicalize(root).map_err(|_| WorkerErrorV1::ReadFailed)
    }
}

fn no_symlink_components(root: &Path) -> Result<(), WorkerErrorV1> {
    let mut current = PathBuf::new();
    for component in root.components() {
        match component {
            Component::Prefix(prefix) => current.push(prefix.as_os_str()),
            Component::RootDir => current.push(std::path::MAIN_SEPARATOR.to_string()),
            Component::Normal(part) => {
                current.push(part);
                if fs::symlink_metadata(&current)
                    .map_err(|_| WorkerErrorV1::ReadFailed)?
                    .file_type()
                    .is_symlink()
                {
                    return Err(WorkerErrorV1::PathEscape);
                }
            }
            Component::CurDir | Component::ParentDir => return Err(WorkerErrorV1::PathEscape),
        }
    }
    Ok(())
}

fn read_bounded(path: &Path, maximum: u64) -> Result<Vec<u8>, WorkerErrorV1> {
    let metadata = fs::symlink_metadata(path).map_err(|_| WorkerErrorV1::ReadFailed)?;
    if metadata.file_type().is_symlink() || !metadata.is_file() || metadata.len() > maximum {
        return Err(WorkerErrorV1::InvalidJob);
    }
    let bytes = fs::read(path).map_err(|_| WorkerErrorV1::ReadFailed)?;
    if bytes.len() as u64 > maximum {
        return Err(WorkerErrorV1::InvalidJob);
    }
    Ok(bytes)
}

fn digest_root(root: &Path) -> String {
    digest_hex(root.to_string_lossy().as_bytes())
}
fn checked_file(root: &Path, identity: &FileIdentityV1) -> Result<PathBuf, WorkerErrorV1> {
    let _ = checked_file_bytes(root, identity)?;
    Ok(root.join(&identity.path))
}
fn checked_file_bytes(root: &Path, identity: &FileIdentityV1) -> Result<Vec<u8>, WorkerErrorV1> {
    if identity.bytes > MAX_INPUT_BYTES {
        return Err(WorkerErrorV1::InvalidJob);
    }
    let path = root.join(&identity.path);
    if !path.starts_with(root) {
        return Err(WorkerErrorV1::PathEscape);
    }
    let mut current = root.to_path_buf();
    for component in Path::new(&identity.path).components() {
        let Component::Normal(part) = component else {
            return Err(WorkerErrorV1::PathEscape);
        };
        current.push(part);
        if fs::symlink_metadata(&current)
            .map_err(|_| WorkerErrorV1::ReadFailed)?
            .file_type()
            .is_symlink()
        {
            return Err(WorkerErrorV1::PathEscape);
        }
    }
    let metadata = fs::symlink_metadata(&path).map_err(|_| WorkerErrorV1::ReadFailed)?;
    if !metadata.is_file() || metadata.len() > MAX_INPUT_BYTES {
        return Err(WorkerErrorV1::ReadFailed);
    }
    let bytes = fs::read(&path).map_err(|_| WorkerErrorV1::ReadFailed)?;
    if bytes.len() as u64 != identity.bytes || digest_hex(&bytes) != identity.sha256 {
        return Err(WorkerErrorV1::IdentityMismatch);
    }
    Ok(bytes)
}
fn relative(value: &str) -> bool {
    let path = Path::new(value);
    !value.is_empty()
        && !path.is_absolute()
        && path.components().all(|c| matches!(c, Component::Normal(_)))
}
fn token(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 128
        && value
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b == b'-' || b == b'_')
}
fn parse_hash(value: &str) -> Result<[u8; 32], WorkerErrorV1> {
    let mut result = [0; 32];
    for (index, chunk) in value.as_bytes().chunks_exact(2).enumerate() {
        result[index] = u8::from_str_radix(
            std::str::from_utf8(chunk).map_err(|_| WorkerErrorV1::InvalidJob)?,
            16,
        )
        .map_err(|_| WorkerErrorV1::InvalidJob)?;
    }
    Ok(result)
}
fn digest_hex(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
fn digest_f64(values: &[f64]) -> String {
    let mut hash = Sha256::new();
    for value in values {
        hash.update(value.to_le_bytes());
    }
    format!("{:x}", hash.finalize())
}

fn digest_parameters(values: &[String]) -> String {
    digest_hex(&serde_json::to_vec(values).unwrap_or_default())
}

fn closure_digest(values: &[FileIdentityV1]) -> String {
    digest_hex(&serde_json::to_vec(values).unwrap_or_default())
}

fn decode_f64_bytes(bytes: &[u8]) -> Result<Vec<f64>, WorkerErrorV1> {
    if bytes.is_empty() || !bytes.len().is_multiple_of(8) {
        return Err(WorkerErrorV1::InvalidSidecar);
    }
    let mut result = Vec::with_capacity(bytes.len() / 8);
    for item in bytes.chunks_exact(8) {
        let value = f64::from_le_bytes(item.try_into().expect("fixed chunk"));
        if !value.is_finite() {
            return Err(WorkerErrorV1::InvalidSidecar);
        }
        result.push(value);
    }
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;
    use sipi_ami_text::{
        AmiDeclaredParameterTypeV1, AmiParameterSelectionFormatV1, AmiParameterUsageV1,
    };

    const PARAMETERS: &[u8] = br#"(whistler_tx
      (Reserved_Parameters
        (Modulation (Usage In) (Type String) (Value "NRZ"))))"#;

    #[test]
    fn typed_subset_adapter_returns_hash_bound_binding() {
        let parse_limits = ParseLimitsV1::try_new(4096, 16, 128, 256).expect("limits");
        let selections = [AmiParameterSelectionV1::new(
            "whistler_tx/Reserved_Parameters/Modulation",
            AmiParameterUsageV1::In,
            AmiDeclaredParameterTypeV1::String,
            AmiParameterSelectionFormatV1::Value,
            "\"NRZ\"",
        )];
        let (binding, subset) = prepare_forwarded_parameter_subset_v1(
            PARAMETERS,
            AmiParameterProfileRoleV1::Tx,
            &selections,
            parse_limits,
            AmiParameterProfileLimitsV1::selected_profile(),
        )
        .expect("subset");
        assert_eq!(subset.parameters().len(), 1);
        subset.verify_binding_v1(&binding).expect("binding");
    }

    #[test]
    fn parameters_artifact_budget_counts_json_escaping() {
        let blocks = vec!["\"".repeat(MAX_PARAMETERS_TOTAL_BYTES / 2)];
        let encoded = serde_json::to_vec(&serde_json::json!({
            "schema": "sipi.ami-worker.parameters-out.v2",
            "blocks": blocks,
            "count": 1,
            "total_bytes": MAX_PARAMETERS_TOTAL_BYTES / 2,
        }))
        .expect("json");
        assert!(encoded.len() > MAX_PARAMETERS_TOTAL_BYTES);
    }
}
