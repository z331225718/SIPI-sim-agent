#![forbid(unsafe_code)]

//! Private one-job AMI worker protocol. It is deliberately not a CLI route or
//! a security sandbox: its role is bounded process and artifact mechanics.

use std::{
    error::Error,
    fmt, fs,
    io::Read,
    path::{Component, Path, PathBuf},
    process::{Child, Command, Stdio},
    thread,
    time::{Duration, Instant},
};

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use sipi_ami_host::{AmiGetWaveRequestV1, AmiHostV1, AmiInitRequestV1, DllSha256V1};
use sipi_ami_text::{ParseLimitsV1, parse_and_bind_v1};
use sipi_artifacts::ArtifactRoot;

const JOB_SCHEMA: &str = "sipi.ami-worker.job.v1";
const RESULT_SCHEMA: &str = "sipi.ami-worker.result.v1";
const PROVENANCE_SCHEMA: &str = "sipi.ami-worker.provenance.v1";
const JOB_FILE: &str = "job.json";
const ARTIFACT_DIR: &str = "artifacts";
const READY_BEFORE_GET_WAVE: &str = ".ready-before-get-wave";

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct WorkerBundleManifestV1 {
    pub schema: String,
    pub worker_sha256: String,
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

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum SupervisorOutcomeV1 {
    Completed,
    CancelledBeforeStart,
    TimedOut,
    Failed,
}

pub fn run_one_job(root: &Path) -> Result<(), WorkerErrorV1> {
    if !cfg!(all(windows, target_arch = "x86_64")) {
        return Err(WorkerErrorV1::UnsupportedPlatform);
    }
    let root = checked_root(root)?;
    let job_bytes = fs::read(root.join(JOB_FILE)).map_err(|_| WorkerErrorV1::ReadFailed)?;
    let job: AmiWorkerJobV1 =
        serde_json::from_slice(&job_bytes).map_err(|_| WorkerErrorV1::InvalidJob)?;
    validate_job(&job)?;
    let started = Instant::now();
    checkpoint(&root, &job, started)?;
    let dll = checked_file(&root, &job.dll)?;
    for helper in &job.closure {
        let _ = checked_file(&root, helper)?;
    }
    let matrix = decode_f64(&checked_file(&root, &job.init_matrix)?)?;
    let parameters =
        fs::read(checked_file(&root, &job.parameters)?).map_err(|_| WorkerErrorV1::ReadFailed)?;
    let waveform = decode_f64(&checked_file(&root, &job.waveform)?)?;
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
    checkpoint(&root, &job, started)?;
    let response = instance
        .get_wave(
            AmiGetWaveRequestV1::try_new(waveform, job.clock_capacity)
                .map_err(|_| WorkerErrorV1::InvalidSidecar)?,
        )
        .map_err(|_| WorkerErrorV1::Host)?;
    instance.close().map_err(|_| WorkerErrorV1::Host)?;
    checkpoint(&root, &job, started)?;
    publish_success(
        &root,
        &job,
        &job_bytes,
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
    validate_bundle(bundle, worker)?;
    if cancel_before_start {
        return Ok(SupervisorOutcomeV1::CancelledBeforeStart);
    }
    let mut child = Command::new(worker)
        .arg("--job-root")
        .arg(root)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|_| WorkerErrorV1::SpawnFailed)?;
    wait_child(&mut child, timeout)
}

fn wait_child(child: &mut Child, timeout: Duration) -> Result<SupervisorOutcomeV1, WorkerErrorV1> {
    let deadline = Instant::now()
        .checked_add(timeout)
        .ok_or(WorkerErrorV1::InvalidBundle)?;
    loop {
        if let Some(status) = child.try_wait().map_err(|_| WorkerErrorV1::WorkerFailed)? {
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

fn validate_bundle(bundle: &WorkerBundleManifestV1, worker: &Path) -> Result<(), WorkerErrorV1> {
    if bundle.schema != "sipi.ami-worker.bundle.v1"
        || bundle.abi_contract_revision != "p4b-ami-standard-abi-host.v1"
        || !worker.is_absolute()
    {
        return Err(WorkerErrorV1::InvalidBundle);
    }
    let bytes = fs::read(worker).map_err(|_| WorkerErrorV1::ReadFailed)?;
    if digest_hex(&bytes) != bundle.worker_sha256 || !is_amd64_pe(&bytes) {
        return Err(WorkerErrorV1::IdentityMismatch);
    }
    Ok(())
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

fn publish_success(
    root: &Path,
    job: &AmiWorkerJobV1,
    job_bytes: &[u8],
    waveform: &[f64],
    clocks: &[f64],
) -> Result<(), WorkerErrorV1> {
    let artifacts = ArtifactRoot::open_or_create(root.join(ARTIFACT_DIR))
        .map_err(|_| WorkerErrorV1::Artifact)?;
    let result = serde_json::to_vec(&serde_json::json!({"schema": RESULT_SCHEMA, "waveform_sha256": digest_f64(waveform), "clock_sha256": digest_f64(clocks), "clock_count": clocks.len()})).map_err(|_| WorkerErrorV1::Artifact)?;
    let provenance = serde_json::to_vec(&serde_json::json!({"schema": PROVENANCE_SCHEMA, "job_sha256": digest_hex(job_bytes), "dll_sha256": job.dll.sha256, "abi_contract_revision": job.abi_contract_revision})).map_err(|_| WorkerErrorV1::Artifact)?;
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

fn checkpoint(root: &Path, job: &AmiWorkerJobV1, started: Instant) -> Result<(), WorkerErrorV1> {
    if root.join(&job.cancel_file).exists() {
        return Err(WorkerErrorV1::Cancelled);
    }
    if started.elapsed() >= Duration::from_millis(job.deadline_ms) {
        return Err(WorkerErrorV1::DeadlineExceeded);
    }
    Ok(())
}
fn validate_job(job: &AmiWorkerJobV1) -> Result<(), WorkerErrorV1> {
    if job.schema != JOB_SCHEMA
        || job.abi_contract_revision != "p4b-ami-standard-abi-host.v1"
        || !token(&job.job_id)
        || !token(&job.artifact_id)
        || job.deadline_ms == 0
        || job.clock_capacity == 0
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
    Ok(())
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
        || fs::symlink_metadata(root)
            .map_err(|_| WorkerErrorV1::ReadFailed)?
            .file_type()
            .is_symlink()
    {
        Err(WorkerErrorV1::PathEscape)
    } else {
        Ok(root.to_path_buf())
    }
}
fn checked_file(root: &Path, identity: &FileIdentityV1) -> Result<PathBuf, WorkerErrorV1> {
    let path = root.join(&identity.path);
    if !path.starts_with(root)
        || fs::symlink_metadata(&path)
            .map_err(|_| WorkerErrorV1::ReadFailed)?
            .file_type()
            .is_symlink()
    {
        return Err(WorkerErrorV1::PathEscape);
    }
    let bytes = fs::read(&path).map_err(|_| WorkerErrorV1::ReadFailed)?;
    if bytes.len() as u64 != identity.bytes || digest_hex(&bytes) != identity.sha256 {
        return Err(WorkerErrorV1::IdentityMismatch);
    }
    Ok(path)
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
fn decode_f64(path: &Path) -> Result<Vec<f64>, WorkerErrorV1> {
    let mut bytes = Vec::new();
    fs::File::open(path)
        .map_err(|_| WorkerErrorV1::ReadFailed)?
        .read_to_end(&mut bytes)
        .map_err(|_| WorkerErrorV1::ReadFailed)?;
    if bytes.is_empty() || bytes.len() % 8 != 0 {
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
