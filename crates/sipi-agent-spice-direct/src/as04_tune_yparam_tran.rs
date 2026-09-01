//! AS-04 scenario-bound `tune-yparam-tran` control path.
//!
//! The Rust leaf owns validation, RFM residue mutation, static S-domain gates,
//! exact deck-token replacement, bounded trial orchestration, and measure
//! parsing.  It never substitutes a local waveform or claims a HSPICE result:
//! when the explicitly selected HSPICE executable cannot complete, the run
//! fails closed and no selected output RFM is published.

use std::fmt::{Display, Formatter};
use std::fs;
use std::io::{self, Read, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, ExitStatus, Stdio};
use std::sync::{
    Arc,
    atomic::{AtomicBool, AtomicUsize, Ordering},
};
use std::thread;
use std::time::{Duration, Instant};

use faer::Mat;
use num_complex::Complex64 as Complex;
use serde_json::json;
use sha2::{Digest, Sha256};

use crate::as03_fit_yparam::read_multiport_touchstone;
use crate::as06_run_rfm::{RfmModel, parse_cadence_rfm, write_cadence_rfm};

pub const UPSTREAM_COMMIT: &str = "2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5";
pub const UPSTREAM_TREE: &str = "b6bde97128030d6cea0d68b2f0a35d807be8c402";
pub const WORKFLOW_ID: &str = "AS-04";
pub const WORKFLOW_NAME: &str = "tune-yparam-tran";
const MAX_EVALUATIONS: usize = 150;
const MAX_ARTIFACT_BYTES: usize = 16 * 1024 * 1024;
const MAX_EXTERNAL_PIPE_BYTES: usize = 8 * 1024 * 1024;
const EXTERNAL_TIMEOUT: Duration = Duration::from_secs(120);

#[derive(Clone, Debug, PartialEq)]
pub struct TuneYparamTranRequest {
    pub touchstone: PathBuf,
    pub input_rfm: PathBuf,
    pub deck: PathBuf,
    pub output_rfm: PathBuf,
    pub report: Option<PathBuf>,
    pub work_dir: PathBuf,
    pub rfm_token: String,
    pub rms_measure: String,
    pub peak_measure: Option<String>,
    pub residual_poles: Vec<f64>,
    pub band_boundaries: Vec<f64>,
    pub hspice_bin: String,
    pub license_file: Option<String>,
    pub max_evaluations: usize,
    pub max_static_rms_growth: f64,
    pub max_sigma: f64,
}

impl TuneYparamTranRequest {
    // The public CLI contract intentionally mirrors the upstream positional
    // request; grouping these fields would change that API.
    #[allow(clippy::too_many_arguments)]
    pub fn new(
        touchstone: impl Into<PathBuf>,
        input_rfm: impl Into<PathBuf>,
        deck: impl Into<PathBuf>,
        output_rfm: impl Into<PathBuf>,
        work_dir: impl Into<PathBuf>,
        rfm_token: impl Into<String>,
        rms_measure: impl Into<String>,
        residual_poles: Vec<f64>,
        band_boundaries: Vec<f64>,
    ) -> Result<Self, TuneError> {
        let request = Self {
            touchstone: touchstone.into(),
            input_rfm: input_rfm.into(),
            deck: deck.into(),
            output_rfm: output_rfm.into(),
            report: None,
            work_dir: work_dir.into(),
            rfm_token: rfm_token.into(),
            rms_measure: rms_measure.into(),
            peak_measure: None,
            residual_poles,
            band_boundaries,
            hspice_bin: "hspice".to_owned(),
            license_file: None,
            max_evaluations: 150,
            max_static_rms_growth: 0.003,
            max_sigma: 0.999,
        };
        validate_request(&request)?;
        Ok(request)
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum TuneError {
    InvalidOption(String),
    Input(String),
    StaticGate(String),
    External(String),
    Output(String),
}

impl From<crate::as06_run_rfm::RfmError> for TuneError {
    fn from(error: crate::as06_run_rfm::RfmError) -> Self {
        Self::Input(error.to_string())
    }
}

impl Display for TuneError {
    fn fmt(&self, f: &mut Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::InvalidOption(value) => write!(f, "invalid tune-yparam-tran option: {value}"),
            Self::Input(value) => write!(f, "tune-yparam-tran input error: {value}"),
            Self::StaticGate(value) => write!(f, "tune-yparam-tran static gate failed: {value}"),
            Self::External(value) => write!(f, "tune-yparam-tran HSPICE error: {value}"),
            Self::Output(value) => write!(f, "tune-yparam-tran output error: {value}"),
        }
    }
}

impl std::error::Error for TuneError {}

#[derive(Clone, Debug, PartialEq)]
pub struct TuneYparamTranResult {
    pub report: PathBuf,
    pub output_rfm: PathBuf,
    pub best_tran_rms: f64,
    pub evaluations: usize,
}

/// Caller-attested HSPICE runtime identity.
///
/// The ordinary `tune_yparam_tran` entry point remains preparation-only and
/// fails closed.  External execution is available only through the additive
/// custody entry point below, so a PATH lookup can never select the solver.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct HspiceCustody {
    pub executable: PathBuf,
    pub sha256: String,
}

impl HspiceCustody {
    pub fn new(executable: impl Into<PathBuf>, sha256: impl Into<String>) -> Self {
        Self {
            executable: executable.into(),
            sha256: sha256.into(),
        }
    }
}

fn validate_request(request: &TuneYparamTranRequest) -> Result<(), TuneError> {
    if request.touchstone.as_os_str().is_empty()
        || request.input_rfm.as_os_str().is_empty()
        || request.deck.as_os_str().is_empty()
        || request.output_rfm.as_os_str().is_empty()
    {
        return Err(TuneError::InvalidOption(
            "touchstone, input-rfm, deck, and output-rfm are required".to_owned(),
        ));
    }
    if request.rfm_token.is_empty() || request.rms_measure.is_empty() {
        return Err(TuneError::InvalidOption(
            "rfm-token and rms-measure are required".to_owned(),
        ));
    }
    if request.residual_poles.is_empty()
        || request
            .residual_poles
            .iter()
            .any(|value| !value.is_finite() || *value <= 0.0)
        || request
            .residual_poles
            .windows(2)
            .any(|pair| pair[1] <= pair[0])
    {
        return Err(TuneError::InvalidOption(
            "residual-poles must be strictly increasing positive finite values".to_owned(),
        ));
    }
    if request.band_boundaries.iter().any(|value| {
        !value.is_finite()
            || *value <= request.residual_poles[0]
            || *value >= *request.residual_poles.last().unwrap_or(&0.0)
    }) || request
        .band_boundaries
        .windows(2)
        .any(|pair| pair[1] <= pair[0])
    {
        return Err(TuneError::InvalidOption(
            "band-boundaries must be strictly increasing inside residual-poles".to_owned(),
        ));
    }
    if request.max_evaluations < 2 || request.max_evaluations > MAX_EVALUATIONS {
        return Err(TuneError::InvalidOption(format!(
            "max-evaluations must be in 2..={MAX_EVALUATIONS}"
        )));
    }
    if !request.max_static_rms_growth.is_finite()
        || !(0.0..=1.0).contains(&request.max_static_rms_growth)
        || !request.max_sigma.is_finite()
        || !(0.0..=1.0).contains(&request.max_sigma)
        || request.max_sigma == 0.0
    {
        return Err(TuneError::InvalidOption(
            "static growth and sigma gates are outside bounds".to_owned(),
        ));
    }
    Ok(())
}

fn response_groups(nports: usize) -> Vec<Vec<usize>> {
    if nports == 2 {
        vec![vec![0], vec![1, 2], vec![3]]
    } else {
        (0..nports * nports).map(|index| vec![index]).collect()
    }
}

fn correction_indices(model: &RfmModel, damping: &[f64]) -> Result<Vec<usize>, TuneError> {
    let mut result = Vec::with_capacity(damping.len());
    for value in damping {
        let matches = model
            .poles
            .iter()
            .enumerate()
            .filter(|(_, pole)| {
                pole.im == 0.0 && (-pole.re - *value).abs() <= 1e-10 + value.abs() * 2e-12
            })
            .map(|(index, _)| index)
            .collect::<Vec<_>>();
        if matches.len() != 1 {
            return Err(TuneError::Input(format!(
                "residual pole {value:.12e} is not uniquely present in the RFM"
            )));
        }
        result.push(matches[0]);
    }
    Ok(result)
}

fn evaluate_model(model: &RfmModel, frequency: f64) -> Vec<Complex> {
    model.evaluate_s(frequency)
}

fn max_sigma(values: &[Complex], nports: usize) -> f64 {
    if values.len() != nports.saturating_mul(nports) || nports == 0 {
        return f64::INFINITY;
    }
    let matrix = Mat::from_fn(nports, nports, |row, column| values[row * nports + column]);
    matrix
        .singular_values()
        .ok()
        .and_then(|values| values.first().copied())
        .unwrap_or(f64::INFINITY)
}

fn static_metrics(model: &RfmModel, frequencies: &[f64], samples: &[Vec<Complex>]) -> (f64, f64) {
    let mut sum = 0.0;
    let mut sigma: f64 = 0.0;
    for (frequency, original) in frequencies.iter().zip(samples) {
        let fitted = evaluate_model(model, *frequency);
        for (left, right) in fitted.iter().zip(original) {
            sum += (*left - *right).norm_sqr();
        }
        sigma = sigma.max(max_sigma(&fitted, model.nports));
    }
    (
        (sum / (frequencies.len() * samples.first().map_or(1, Vec::len)) as f64).sqrt(),
        sigma,
    )
}

fn band_pole_indices(damping: &[f64], boundaries: &[f64], correction: &[usize]) -> Vec<Vec<usize>> {
    let mut bands = vec![Vec::new(); boundaries.len() + 1];
    for (index, pole) in correction.iter().enumerate() {
        let band = boundaries.partition_point(|boundary| damping[index] >= *boundary);
        bands[band].push(*pole);
    }
    bands
}

fn scaled_trial(
    base: &RfmModel,
    band_poles: &[Vec<usize>],
    groups: &[Vec<usize>],
    scales: &[f64],
) -> RfmModel {
    let mut trial = base.clone();
    for (band_index, pole_group) in band_poles.iter().enumerate() {
        let scale_base = band_index * groups.len();
        for (group_index, responses) in groups.iter().enumerate() {
            let scale = scales.get(scale_base + group_index).copied().unwrap_or(1.0);
            for pole in pole_group {
                for response in responses {
                    trial.residues[*response][*pole] *= scale;
                }
            }
        }
    }
    trial
}

fn replace_token(source: &str, token: &str, replacement: &str) -> Result<String, TuneError> {
    if source.matches(token).count() != 1 {
        return Err(TuneError::Input(
            "rfm-token must occur exactly once in the deck".to_owned(),
        ));
    }
    Ok(source.replace(token, replacement))
}

fn relative_path(target: &Path, base: &Path) -> Result<String, TuneError> {
    let target = if target.is_absolute() {
        target.to_path_buf()
    } else {
        std::env::current_dir()
            .map_err(|error| TuneError::Output(error.to_string()))?
            .join(target)
    };
    let base = if base.is_absolute() {
        base.to_path_buf()
    } else {
        std::env::current_dir()
            .map_err(|error| TuneError::Output(error.to_string()))?
            .join(base)
    };
    let target = target.components().collect::<Vec<_>>();
    let base = base.components().collect::<Vec<_>>();
    let common = target.iter().zip(&base).take_while(|(a, b)| a == b).count();
    if common == 0 {
        return Err(TuneError::Input(
            "trial RFM and deck must share a path root".to_owned(),
        ));
    }
    let mut parts = Vec::new();
    for _ in common..base.len() {
        parts.push("..".to_owned());
    }
    for component in &target[common..] {
        parts.push(component.as_os_str().to_string_lossy().into_owned());
    }
    Ok(if parts.is_empty() {
        ".".to_owned()
    } else {
        parts.join("/")
    })
}

fn resolve_hspice_path(path: &Path) -> Result<PathBuf, TuneError> {
    if path.as_os_str().is_empty() || !path.is_absolute() {
        return Err(TuneError::External(
            "HSPICE execution requires an absolute executable path for custody".to_owned(),
        ));
    }
    let metadata = fs::symlink_metadata(path).map_err(|error| {
        TuneError::External(format!(
            "HSPICE executable is unavailable for custody: {error}"
        ))
    })?;
    if metadata.file_type().is_symlink() || !metadata.is_file() {
        return Err(TuneError::External(
            "HSPICE executable must be a regular non-symlink file for custody".to_owned(),
        ));
    }
    let resolved = fs::canonicalize(path).map_err(|error| {
        TuneError::External(format!(
            "HSPICE executable path could not be canonicalized for custody: {error}"
        ))
    })?;
    let resolved_metadata = fs::symlink_metadata(&resolved).map_err(|error| {
        TuneError::External(format!(
            "HSPICE executable could not be rechecked for custody: {error}"
        ))
    })?;
    if resolved_metadata.file_type().is_symlink() || !resolved_metadata.is_file() {
        return Err(TuneError::External(
            "resolved HSPICE executable must be a regular non-symlink file".to_owned(),
        ));
    }
    Ok(resolved)
}

fn attest_hspice(
    request: &TuneYparamTranRequest,
    custody: &HspiceCustody,
) -> Result<(PathBuf, String), TuneError> {
    let requested = resolve_hspice_path(Path::new(&request.hspice_bin))?;
    let (attested, sha256) =
        crate::attest_external_executable(&custody.executable, Some(&custody.sha256), "HSPICE")
            .map_err(|error| TuneError::External(error.to_string()))?;
    let attested = resolve_hspice_path(&attested)?;
    if requested != attested {
        return Err(TuneError::External(
            "request HSPICE path and custody executable must resolve to the same file".to_owned(),
        ));
    }
    Ok((requested, sha256))
}

fn read_hspice_output<R: Read>(
    mut reader: R,
    total: Arc<AtomicUsize>,
    overflow: Arc<AtomicBool>,
    read_error: Arc<AtomicBool>,
) -> Result<Vec<u8>, io::Error> {
    let mut output = Vec::new();
    let mut chunk = [0_u8; 16 * 1024];
    loop {
        match reader.read(&mut chunk) {
            Ok(0) => break,
            Ok(count) => {
                let mut reserved = false;
                loop {
                    let current = total.load(Ordering::Acquire);
                    let Some(next) = current.checked_add(count) else {
                        overflow.store(true, Ordering::Release);
                        break;
                    };
                    if next > MAX_EXTERNAL_PIPE_BYTES {
                        overflow.store(true, Ordering::Release);
                        break;
                    }
                    if total
                        .compare_exchange(current, next, Ordering::AcqRel, Ordering::Acquire)
                        .is_ok()
                    {
                        reserved = true;
                        break;
                    }
                }
                if !reserved {
                    break;
                }
                output.extend_from_slice(&chunk[..count]);
            }
            Err(error) => {
                read_error.store(true, Ordering::Release);
                return Err(error);
            }
        }
    }
    Ok(output)
}

struct HspiceProcessResult {
    status: ExitStatus,
    stdout: Vec<u8>,
    stderr: Vec<u8>,
}

fn run_hspice_process(
    program: &Path,
    arguments: &[PathBuf],
    current_dir: &Path,
    environment: &std::collections::HashMap<std::ffi::OsString, std::ffi::OsString>,
) -> Result<HspiceProcessResult, TuneError> {
    let mut command = Command::new(program);
    command
        .args(arguments.iter().map(|value| value.as_os_str()))
        .current_dir(current_dir)
        .envs(environment.iter())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    let mut child = command
        .spawn()
        .map_err(|error| TuneError::External(format!("HSPICE process could not start: {error}")))?;
    let overflow = Arc::new(AtomicBool::new(false));
    let total = Arc::new(AtomicUsize::new(0));
    let read_error = Arc::new(AtomicBool::new(false));
    let stdout = child.stdout.take().ok_or_else(|| {
        let _ = child.kill();
        let _ = child.wait();
        TuneError::External("HSPICE stdout pipe was unavailable".to_owned())
    })?;
    let stderr = child.stderr.take().ok_or_else(|| {
        let _ = child.kill();
        let _ = child.wait();
        TuneError::External("HSPICE stderr pipe was unavailable".to_owned())
    })?;
    let stdout_thread = {
        let total = Arc::clone(&total);
        let overflow = Arc::clone(&overflow);
        let read_error = Arc::clone(&read_error);
        thread::spawn(move || read_hspice_output(stdout, total, overflow, read_error))
    };
    let stderr_thread = {
        let total = Arc::clone(&total);
        let overflow = Arc::clone(&overflow);
        let read_error = Arc::clone(&read_error);
        thread::spawn(move || read_hspice_output(stderr, total, overflow, read_error))
    };
    let deadline = Instant::now() + EXTERNAL_TIMEOUT;
    let mut failure = None;
    let status = loop {
        if overflow.load(Ordering::Acquire) {
            failure = Some("HSPICE output exceeded the bounded 8 MiB pipe budget".to_owned());
            break None;
        }
        if read_error.load(Ordering::Acquire) {
            failure = Some("HSPICE output read failed".to_owned());
            break None;
        }
        match child.try_wait() {
            Ok(Some(status)) => break Some(status),
            Ok(None) if Instant::now() >= deadline => {
                failure = Some("HSPICE exceeded the 120 second timeout".to_owned());
                break None;
            }
            Ok(None) => thread::sleep(Duration::from_millis(10)),
            Err(error) => {
                failure = Some(format!("HSPICE status check failed: {error}"));
                break None;
            }
        }
    };
    if failure.is_some() {
        let _ = child.kill();
    }
    if failure.is_some() || status.is_none() {
        let _ = child.wait();
    }
    let stdout = stdout_thread
        .join()
        .map_err(|_| TuneError::External("HSPICE stdout reader failed".to_owned()))?
        .map_err(|error| TuneError::External(format!("HSPICE stdout read failed: {error}")))?;
    let stderr = stderr_thread
        .join()
        .map_err(|_| TuneError::External("HSPICE stderr reader failed".to_owned()))?
        .map_err(|error| TuneError::External(format!("HSPICE stderr read failed: {error}")))?;
    if let Some(error) = failure {
        return Err(TuneError::External(error));
    }
    if overflow.load(Ordering::Acquire) {
        return Err(TuneError::External(
            "HSPICE output exceeded the bounded 8 MiB pipe budget".to_owned(),
        ));
    }
    Ok(HspiceProcessResult {
        status: status.expect("successful HSPICE process must have a status"),
        stdout,
        stderr,
    })
}

fn measure(path: &Path, name: &str) -> Result<f64, TuneError> {
    let (bytes, _) = bounded_artifact(path)
        .map_err(|error| TuneError::External(format!("HSPICE listing read failed: {error}")))?;
    let text = String::from_utf8_lossy(&bytes);
    let lower = text.to_ascii_lowercase();
    let needle = name.to_ascii_lowercase();
    let mut token = None;
    for (offset, _) in lower.match_indices(&needle) {
        let before_ok = offset == 0
            || !lower[..offset]
                .chars()
                .next_back()
                .is_some_and(|value| value.is_ascii_alphanumeric() || value == '_');
        let after_name = offset + needle.len();
        if !before_ok {
            continue;
        }
        let remainder = text[after_name..].trim_start();
        if let Some(value) = remainder.strip_prefix('=') {
            token = Some(
                value
                    .split_whitespace()
                    .next()
                    .unwrap_or_default()
                    .trim_matches(|value: char| value == ',' || value == ';')
                    .to_owned(),
            );
        }
    }
    let token = token.ok_or_else(|| {
        TuneError::External(format!(
            "measure '{name}' is missing from {}",
            path.display()
        ))
    })?;
    if let Ok(value) = token.parse::<f64>() {
        return Ok(value);
    }
    let (number, suffix) = token
        .chars()
        .position(|value| value.is_ascii_alphabetic())
        .map_or((token.as_str(), ""), |index| token.split_at(index));
    let value = number
        .parse::<f64>()
        .map_err(|_| TuneError::External(format!("measure '{name}' is not numeric")))?;
    let scale = match suffix.to_ascii_lowercase().as_str() {
        "m" => 1e-3,
        "u" => 1e-6,
        "n" => 1e-9,
        "p" => 1e-12,
        "f" => 1e-15,
        _ => {
            return Err(TuneError::External(format!(
                "unsupported measure suffix '{suffix}'"
            )));
        }
    };
    Ok(value * scale)
}

#[derive(Clone, Debug, PartialEq)]
struct ArtifactReceipt {
    bytes: usize,
    sha256: String,
}

#[derive(Clone, Debug, PartialEq)]
struct FrozenArtifactReceipt {
    source: ArtifactReceipt,
    target: ArtifactReceipt,
}

fn bounded_artifact(path: &Path) -> Result<(Vec<u8>, ArtifactReceipt), TuneError> {
    let before = fs::symlink_metadata(path)
        .map_err(|error| TuneError::Output(format!("artifact could not be inspected: {error}")))?;
    if before.file_type().is_symlink() || !before.is_file() {
        return Err(TuneError::Output(
            "bounded artifact must be a regular non-symlink file".to_owned(),
        ));
    }
    if before.len() > MAX_ARTIFACT_BYTES as u64 {
        return Err(TuneError::Output(
            "bounded artifact exceeds the 16 MiB byte budget".to_owned(),
        ));
    }
    let mut file = fs::File::open(path).map_err(|error| TuneError::Output(error.to_string()))?;
    let mut bytes = Vec::new();
    Read::by_ref(&mut file)
        .take((MAX_ARTIFACT_BYTES + 1) as u64)
        .read_to_end(&mut bytes)
        .map_err(|error| TuneError::Output(error.to_string()))?;
    if bytes.len() > MAX_ARTIFACT_BYTES {
        return Err(TuneError::Output(
            "RFM artifact exceeds the bounded byte budget".to_owned(),
        ));
    }
    let after = fs::symlink_metadata(path)
        .map_err(|error| TuneError::Output(format!("artifact could not be rechecked: {error}")))?;
    if after.file_type().is_symlink() || !after.is_file() || after.len() != before.len() {
        return Err(TuneError::Output(
            "bounded artifact changed during read".to_owned(),
        ));
    }
    let byte_len = bytes.len();
    let sha256 = format!("{:x}", Sha256::digest(&bytes));
    Ok((
        bytes,
        ArtifactReceipt {
            bytes: byte_len,
            sha256,
        },
    ))
}

fn freeze_best_rfm(path: &Path, source_path: &Path) -> Result<FrozenArtifactReceipt, TuneError> {
    let (bytes, source) = bounded_artifact(source_path)?;
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|error| TuneError::Output(error.to_string()))?;
    }
    let mut target = fs::OpenOptions::new()
        .create(true)
        .truncate(true)
        .write(true)
        .open(path)
        .map_err(|error| TuneError::Output(error.to_string()))?;
    target
        .write_all(&bytes)
        .and_then(|_| target.flush())
        .and_then(|_| target.sync_all())
        .map_err(|error| TuneError::Output(error.to_string()))?;
    drop(target);
    let (_, target_receipt) = bounded_artifact(path)?;
    if target_receipt != source {
        return Err(TuneError::Output(
            "frozen best RFM receipt differs from scored trial".to_owned(),
        ));
    }
    Ok(FrozenArtifactReceipt {
        source,
        target: target_receipt,
    })
}

fn publish_frozen_best(best_path: &Path, output_path: &Path) -> Result<ArtifactReceipt, TuneError> {
    let (bytes, source_receipt) = bounded_artifact(best_path)?;
    if output_path.exists() {
        return Err(TuneError::Output(
            "refusing to replace an existing output RFM".to_owned(),
        ));
    }
    let parent = output_path.parent().unwrap_or_else(|| Path::new("."));
    fs::create_dir_all(parent).map_err(|error| TuneError::Output(error.to_string()))?;
    let name = output_path
        .file_name()
        .and_then(|value| value.to_str())
        .ok_or_else(|| TuneError::Output("output RFM filename is invalid".to_owned()))?;
    let temporary = parent.join(format!(".{name}.sipi-new"));
    let mut file = fs::OpenOptions::new()
        .create_new(true)
        .write(true)
        .open(&temporary)
        .map_err(|error| TuneError::Output(error.to_string()))?;
    let write_result = file
        .write_all(&bytes)
        .and_then(|_| file.flush())
        .and_then(|_| file.sync_all());
    drop(file);
    if let Err(error) = write_result {
        let _ = fs::remove_file(&temporary);
        return Err(TuneError::Output(error.to_string()));
    }
    if let Err(error) = fs::rename(&temporary, output_path) {
        let _ = fs::remove_file(&temporary);
        return Err(TuneError::Output(error.to_string()));
    }
    let (_, target_receipt) = bounded_artifact(output_path)?;
    if target_receipt != source_receipt {
        let _ = fs::remove_file(output_path);
        return Err(TuneError::Output(
            "published output RFM receipt differs from frozen best".to_owned(),
        ));
    }
    Ok(target_receipt)
}

fn validate_artifact_paths(
    request: &TuneYparamTranRequest,
) -> Result<(PathBuf, PathBuf), TuneError> {
    let requested_work_dir = if request.work_dir.as_os_str().is_empty() {
        let stem = request
            .output_rfm
            .file_stem()
            .and_then(|value| value.to_str())
            .filter(|value| !value.is_empty())
            .unwrap_or("tuned");
        request
            .output_rfm
            .parent()
            .unwrap_or_else(|| Path::new("."))
            .join(format!("{stem}_tran_tune"))
    } else {
        request.work_dir.clone()
    };
    let report = request
        .report
        .clone()
        .unwrap_or_else(|| request.output_rfm.with_extension("json"));
    let planned_best = requested_work_dir.join("best.rfm");
    let planned_paths = [
        ("input RFM", request.input_rfm.as_path()),
        ("output RFM", request.output_rfm.as_path()),
        ("best RFM", planned_best.as_path()),
        ("report", report.as_path()),
    ];
    for (left_name, left) in planned_paths {
        for (right_name, right) in planned_paths {
            if left_name >= right_name {
                continue;
            }
            let left =
                crate::absolute_path(left).map_err(|error| TuneError::Output(error.to_string()))?;
            let right = crate::absolute_path(right)
                .map_err(|error| TuneError::Output(error.to_string()))?;
            if left == right {
                return Err(TuneError::Output(format!(
                    "{left_name} and {right_name} must not alias"
                )));
            }
        }
    }
    if fs::symlink_metadata(&request.output_rfm).is_ok() || fs::symlink_metadata(&report).is_ok() {
        return Err(TuneError::Output(
            "output and report must be fresh create-new paths".to_owned(),
        ));
    }
    if let Ok(metadata) = fs::symlink_metadata(&requested_work_dir) {
        if metadata.file_type().is_symlink() || !metadata.is_dir() {
            return Err(TuneError::Output(
                "work directory must be a regular non-symlink directory".to_owned(),
            ));
        }
        if fs::symlink_metadata(&planned_best).is_ok() {
            return Err(TuneError::Output(
                "best RFM path must be a fresh create-new artifact".to_owned(),
            ));
        }
    }
    Ok((requested_work_dir, report))
}

/// Execute the bounded external HSPICE residual search.
pub fn tune_yparam_tran(
    request: &TuneYparamTranRequest,
) -> Result<TuneYparamTranResult, TuneError> {
    tune_yparam_tran_internal(request, None)
}

/// Execute the external HSPICE residual search with explicit caller custody.
///
/// The requested `hspice_bin` and the attested executable must resolve to the
/// same regular file, and the file digest is checked again after each trial.
/// This keeps the upstream Rust controller and HSPICE runtime boundary while
/// leaving the default entry point fail-closed.
pub fn tune_yparam_tran_with_hspice_custody(
    request: &TuneYparamTranRequest,
    custody: &HspiceCustody,
) -> Result<TuneYparamTranResult, TuneError> {
    tune_yparam_tran_internal(request, Some(custody))
}

fn tune_yparam_tran_internal(
    request: &TuneYparamTranRequest,
    custody: Option<&HspiceCustody>,
) -> Result<TuneYparamTranResult, TuneError> {
    validate_request(request)?;
    let (requested_work_dir, report) = validate_artifact_paths(request)?;
    let (hspice_path, hspice_sha256) = custody.map_or_else(
        || {
            Err(TuneError::External(
                "HSPICE execution is unavailable: explicit executable custody is required"
                    .to_owned(),
            ))
        },
        |custody| attest_hspice(request, custody),
    )?;
    if !request.touchstone.is_file() || !request.input_rfm.is_file() || !request.deck.is_file() {
        return Err(TuneError::Input(
            "touchstone, input RFM, and deck must exist".to_owned(),
        ));
    }
    if request
        .deck
        .metadata()
        .map(|metadata| metadata.len() > MAX_ARTIFACT_BYTES as u64)
        .unwrap_or(false)
    {
        return Err(TuneError::Input(
            "HSPICE deck exceeds the bounded input budget".to_owned(),
        ));
    }
    let network = read_multiport_touchstone(&request.touchstone)
        .map_err(|error| TuneError::Input(error.to_string()))?;
    let base = parse_cadence_rfm(&request.input_rfm)?;
    if network.ports() != base.nports {
        return Err(TuneError::Input(
            "Touchstone and RFM port counts differ".to_owned(),
        ));
    }
    let correction = correction_indices(&base, &request.residual_poles)?;
    let band_poles = band_pole_indices(
        &request.residual_poles,
        &request.band_boundaries,
        &correction,
    );
    let groups = response_groups(base.nports);
    let (baseline_rms, baseline_sigma) =
        static_metrics(&base, network.frequencies_hz(), network.samples());
    let deck_path =
        fs::canonicalize(&request.deck).map_err(|error| TuneError::Input(error.to_string()))?;
    let deck_source =
        fs::read_to_string(&deck_path).map_err(|error| TuneError::Input(error.to_string()))?;
    let deck_dir = deck_path.parent().unwrap_or_else(|| Path::new("."));
    fs::create_dir_all(&requested_work_dir)
        .map_err(|error| TuneError::Output(error.to_string()))?;
    let work_dir = fs::canonicalize(&requested_work_dir)
        .map_err(|error| TuneError::Output(error.to_string()))?;
    let mut environment = std::env::vars_os().collect::<std::collections::HashMap<_, _>>();
    if let Some(license) = &request.license_file {
        environment.insert("SNPSLMD_LICENSE_FILE".into(), license.into());
        environment.insert("LM_LICENSE_FILE".into(), license.into());
    }
    let mut history = Vec::new();
    let mut best: Option<(RfmModel, f64, usize, Option<f64>)> = None;
    let mut best_receipt: Option<FrozenArtifactReceipt> = None;
    let best_path = work_dir.join("best.rfm");
    let parameter_count = groups.len() * band_poles.len().max(1);
    // Keep the upstream Nelder-Mead branch, but make every evaluation finite,
    // bounded by max_evaluations, and observable in the result history.  The
    // HSPICE process remains the only non-portable part of the objective.
    let mut evaluation_count = 0usize;
    let mut evaluate = |scales: &[f64], ordinal: usize| -> Result<f64, TuneError> {
        if scales.len() != parameter_count || scales.iter().any(|value| !value.is_finite()) {
            return Err(TuneError::InvalidOption(
                "Nelder-Mead produced non-finite scales".to_owned(),
            ));
        }
        let scales = scales.to_vec();
        let trial = scaled_trial(&base, &band_poles, &groups, &scales);
        let trial_rfm = work_dir.join(format!("trial_{ordinal:03}.rfm"));
        write_cadence_rfm(&trial_rfm, &trial)?;
        let (static_rms, sigma) =
            static_metrics(&trial, network.frequencies_hz(), network.samples());
        let mut record =
            json!({"ordinal": ordinal, "scales": scales, "s_rms": static_rms, "max_sigma": sigma});
        if static_rms > baseline_rms * (1.0 + request.max_static_rms_growth)
            || sigma > request.max_sigma
        {
            record["status"] = json!("STATIC_REJECT");
            record["objective"] = json!(1.0 + static_rms);
            history.push(record);
            return Ok(1.0 + static_rms);
        }
        let relative_rfm = relative_path(&trial_rfm, deck_dir)?;
        let trial_deck = work_dir.join(format!("trial_{ordinal:03}.sp"));
        fs::write(
            &trial_deck,
            replace_token(&deck_source, &request.rfm_token, &relative_rfm)?,
        )
        .map_err(|error| TuneError::Output(error.to_string()))?;
        let output_stem = work_dir.join(format!("trial_{ordinal:03}"));
        let listing = output_stem.with_extension("lis");
        if fs::symlink_metadata(&listing).is_ok() {
            return Err(TuneError::External(
                "HSPICE listing path must be fresh before each trial".to_owned(),
            ));
        }
        let relative_trial_deck = relative_path(&trial_deck, deck_dir)?;
        let relative_output_stem = relative_path(&output_stem, deck_dir)?;
        let result = run_hspice_process(
            &hspice_path,
            &[
                PathBuf::from(relative_trial_deck),
                PathBuf::from("-o"),
                PathBuf::from(relative_output_stem),
            ],
            deck_dir,
            &environment,
        )?;
        let after_hspice_sha256 = crate::file_sha256(&hspice_path).map_err(|error| {
            TuneError::External(format!("HSPICE executable re-attestation failed: {error}"))
        })?;
        if after_hspice_sha256 != hspice_sha256 {
            return Err(TuneError::External(
                "HSPICE executable changed during tuning".to_owned(),
            ));
        }
        if !result.status.success() || !listing.is_file() {
            record["status"] = json!("HSPICE_REJECT");
            record["returncode"] = json!(result.status.code());
            record["stdout_bytes"] = json!(result.stdout.len());
            record["stderr_bytes"] = json!(result.stderr.len());
            record["objective"] = json!(2.0);
            history.push(record);
            return Ok(2.0);
        }
        record["stdout_bytes"] = json!(result.stdout.len());
        record["stderr_bytes"] = json!(result.stderr.len());
        let tran_rms = measure(&listing, &request.rms_measure)?;
        let tran_peak = request
            .peak_measure
            .as_deref()
            .map(|name| measure(&listing, name))
            .transpose()?;
        record["status"] = json!("PASS");
        record["objective"] = json!(tran_rms);
        record["tran_rms"] = json!(tran_rms);
        if let Some(value) = tran_peak {
            record["tran_peak"] = json!(value);
        }
        if best
            .as_ref()
            .is_none_or(|(_, current, _, _)| tran_rms < *current)
        {
            best_receipt = Some(freeze_best_rfm(&best_path, &trial_rfm)?);
            best = Some((trial, tran_rms, ordinal, tran_peak));
        }
        history.push(record);
        Ok(tran_rms)
    };

    let initial = vec![1.0; parameter_count];
    let mut simplex = Vec::with_capacity(parameter_count + 1);
    simplex.push(initial.clone());
    for index in 0..parameter_count {
        let mut point = initial.clone();
        point[index] += 0.012;
        simplex.push(point);
    }
    let mut scores = Vec::with_capacity(simplex.len());
    for point in &simplex {
        if evaluation_count >= request.max_evaluations {
            break;
        }
        scores.push(evaluate(point, evaluation_count)?);
        evaluation_count += 1;
    }
    let mut optimizer_success = false;
    let mut optimizer_message = "maximum evaluations reached".to_owned();
    while evaluation_count < request.max_evaluations && scores.len() == simplex.len() {
        let mut order = (0..simplex.len()).collect::<Vec<_>>();
        order.sort_by(|left, right| scores[*left].total_cmp(&scores[*right]));
        let best_index = order[0];
        let worst_index = *order.last().expect("Nelder-Mead simplex is non-empty");
        let second_worst = order[order.len().saturating_sub(2)];
        let mut centroid = vec![0.0; parameter_count];
        for index in order.iter().take(order.len() - 1) {
            for (axis, value) in simplex[*index].iter().enumerate() {
                centroid[axis] += value;
            }
        }
        let denominator = (order.len() - 1) as f64;
        for value in &mut centroid {
            *value /= denominator;
        }
        let reflected = centroid
            .iter()
            .zip(&simplex[worst_index])
            .map(|(center, worst)| 2.0 * center - worst)
            .collect::<Vec<_>>();
        let reflected_score = evaluate(&reflected, evaluation_count)?;
        evaluation_count += 1;
        if evaluation_count >= request.max_evaluations {
            break;
        }
        if reflected_score < scores[best_index] {
            let expanded = centroid
                .iter()
                .zip(&reflected)
                .map(|(center, point)| center + 2.0 * (point - center))
                .collect::<Vec<_>>();
            if evaluation_count < request.max_evaluations {
                let expanded_score = evaluate(&expanded, evaluation_count)?;
                evaluation_count += 1;
                if expanded_score < reflected_score {
                    simplex[worst_index] = expanded;
                    scores[worst_index] = expanded_score;
                } else {
                    simplex[worst_index] = reflected;
                    scores[worst_index] = reflected_score;
                }
            } else {
                simplex[worst_index] = reflected;
                scores[worst_index] = reflected_score;
            }
        } else if reflected_score < scores[second_worst] {
            simplex[worst_index] = reflected;
            scores[worst_index] = reflected_score;
        } else {
            let contracted = centroid
                .iter()
                .zip(&simplex[worst_index])
                .map(|(center, worst)| center + 0.5 * (worst - center))
                .collect::<Vec<_>>();
            let contracted_score = evaluate(&contracted, evaluation_count)?;
            evaluation_count += 1;
            if contracted_score < scores[worst_index] {
                simplex[worst_index] = contracted;
                scores[worst_index] = contracted_score;
            } else {
                let best_point = simplex[best_index].clone();
                for index in order.iter().skip(1) {
                    if evaluation_count >= request.max_evaluations {
                        break;
                    }
                    let shrunk = best_point
                        .iter()
                        .zip(&simplex[*index])
                        .map(|(best, point)| best + 0.5 * (point - best))
                        .collect::<Vec<_>>();
                    scores[*index] = evaluate(&shrunk, evaluation_count)?;
                    evaluation_count += 1;
                    simplex[*index] = shrunk;
                }
            }
        }
        let spread = scores.iter().fold(0.0_f64, |maximum, value| {
            maximum.max((*value - scores[best_index]).abs())
        });
        let coordinate_spread = simplex[best_index]
            .iter()
            .zip(&simplex[worst_index])
            .map(|(left, right)| (left - right).abs())
            .fold(0.0_f64, f64::max);
        if spread <= 1e-7 && coordinate_spread <= 4.0e-4 {
            optimizer_success = true;
            optimizer_message = "converged".to_owned();
            break;
        }
    }
    if evaluation_count >= request.max_evaluations && !optimizer_success {
        optimizer_message = "maximum evaluations reached".to_owned();
    }
    let (_best_model, best_rms, best_ordinal, best_peak) = best.ok_or_else(|| {
        TuneError::External("no candidate completed HSPICE transient scoring".to_owned())
    })?;
    let frozen_receipt = best_receipt
        .ok_or_else(|| TuneError::Output("best RFM receipt was not recorded".to_owned()))?;
    let published_receipt = publish_frozen_best(&best_path, &request.output_rfm)?;
    if published_receipt != frozen_receipt.target {
        let _ = fs::remove_file(&request.output_rfm);
        return Err(TuneError::Output(
            "published output receipt differs from frozen best target".to_owned(),
        ));
    }
    let payload = json!({
        "schema": "sipi.agent-spice-as-04-tune-yparam-tran-result.v1",
        "workflow": WORKFLOW_NAME,
        "upstream_commit": UPSTREAM_COMMIT,
        "upstream_tree": UPSTREAM_TREE,
        "touchstone": request.touchstone,
        "input_rfm": request.input_rfm,
        "deck": request.deck,
        "output_rfm": request.output_rfm,
        "rms_measure": request.rms_measure,
        "peak_measure": request.peak_measure,
        "residual_poles_rad_per_s": request.residual_poles,
        "residual_damping_rad_per_s": request.residual_poles,
        "band_boundaries_rad_per_s": request.band_boundaries,
        "baseline": {"s_rms": baseline_rms, "max_sigma": baseline_sigma},
        "hspice": {
            "executable": hspice_path.file_name().map(|value| value.to_string_lossy()).unwrap_or_default(),
            "sha256": hspice_sha256,
            "path_redacted": true,
        },
        "best": {"ordinal": best_ordinal, "tran_rms": best_rms, "tran_peak": best_peak},
        "best_artifact": {
            "frozen_source": {"bytes": frozen_receipt.source.bytes, "sha256": frozen_receipt.source.sha256},
            "frozen_target": {"bytes": frozen_receipt.target.bytes, "sha256": frozen_receipt.target.sha256},
            "published_output": {"bytes": published_receipt.bytes, "sha256": published_receipt.sha256}
        },
        "evaluations": history.len(),
        "optimizer": {"method": "Nelder-Mead", "xatol": 4.0e-4, "fatol": 1.0e-7, "success": optimizer_success, "message": optimizer_message},
        "history": history,
        "portable_branches": ["response-grouping", "static-gates", "exact-token-replacement", "bounded-trial-artifacts", "best-rfm-freeze-and-final-copy", "Nelder-Mead", "measure-parsing"],
        "external_runtime_boundary": ["commercial HSPICE result requires the caller-selected executable"],
    });
    let text = serde_json::to_string_pretty(&payload)
        .map_err(|error| TuneError::Output(error.to_string()))?
        + "\n";
    if text.len() > MAX_ARTIFACT_BYTES {
        return Err(TuneError::Output("report exceeds byte budget".to_owned()));
    }
    if let Some(parent) = report.parent() {
        fs::create_dir_all(parent).map_err(|error| TuneError::Output(error.to_string()))?;
    }
    let mut report_file = match fs::OpenOptions::new()
        .create_new(true)
        .write(true)
        .open(&report)
    {
        Ok(file) => file,
        Err(error) => {
            let _ = fs::remove_file(&request.output_rfm);
            return Err(TuneError::Output(error.to_string()));
        }
    };
    if let Err(error) = report_file
        .write_all(text.as_bytes())
        .and_then(|_| report_file.flush())
        .and_then(|_| report_file.sync_all())
    {
        drop(report_file);
        let _ = fs::remove_file(&report);
        let _ = fs::remove_file(&request.output_rfm);
        return Err(TuneError::Output(error.to_string()));
    }
    Ok(TuneYparamTranResult {
        report,
        output_rfm: request.output_rfm.clone(),
        best_tran_rms: best_rms,
        evaluations: history.len(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn token_replacement_requires_exactly_one_occurrence() {
        assert!(replace_token("x a x", "x", "y").is_err());
        assert_eq!(replace_token("x a", "x", "y").unwrap(), "y a");
    }

    #[test]
    fn trial_rfm_reference_is_relative_outside_deck_directory() {
        let root = std::env::temp_dir().join(format!("sipi-as04-relative-{}", std::process::id()));
        let deck_dir = root.join("deck");
        let trial = root.join("work").join("trial_000.rfm");
        fs::create_dir_all(&deck_dir).unwrap();
        fs::create_dir_all(trial.parent().unwrap()).unwrap();
        assert_eq!(
            relative_path(&trial, &deck_dir).unwrap(),
            "../work/trial_000.rfm"
        );
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn malformed_measure_is_rejected() {
        let root = std::env::temp_dir().join(format!("sipi-as04-{}", std::process::id()));
        fs::create_dir_all(&root).unwrap();
        let path = root.join("x.lis");
        fs::write(&path, "foo=1k\n").unwrap();
        assert!(measure(&path, "foo").is_err());
        fs::write(&path, "foo = 2.5m\n").unwrap();
        assert!((measure(&path, "foo").unwrap() - 2.5e-3).abs() < 1e-15);
        fs::write(&path, "foox = 1\nfoo = 3u\n").unwrap();
        assert!((measure(&path, "foo").unwrap() - 3e-6).abs() < 1e-18);
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn hspice_executable_requires_explicit_regular_absolute_file() {
        let relative = resolve_hspice_path(Path::new("hspice"));
        assert!(matches!(
            relative,
            Err(TuneError::External(message)) if message.contains("absolute") && message.contains("custody")
        ));
        let missing = resolve_hspice_path(
            &std::env::temp_dir().join(format!("sipi-as04-missing-{}", std::process::id())),
        );
        assert!(
            matches!(missing, Err(TuneError::External(message)) if message.contains("unavailable"))
        );
        let current = std::env::current_exe().unwrap();
        assert_eq!(
            resolve_hspice_path(&current).unwrap(),
            fs::canonicalize(current).unwrap()
        );
    }

    #[test]
    fn hspice_custody_binds_request_path_and_digest() {
        let executable = std::env::current_exe().unwrap();
        let digest = crate::file_sha256(&executable).unwrap();
        let mut request = TuneYparamTranRequest::new(
            "input.s2p",
            "input.rfm",
            "deck.sp",
            "output.rfm",
            "work",
            "model.rfm",
            "rms",
            vec![1.0, 2.0],
            vec![1.5],
        )
        .unwrap();
        request.hspice_bin = executable.display().to_string();
        let custody = HspiceCustody::new(&executable, &digest);
        let (resolved, actual) = attest_hspice(&request, &custody).unwrap();
        assert_eq!(resolved, fs::canonicalize(&executable).unwrap());
        assert_eq!(actual, digest);

        let wrong = HspiceCustody::new(&executable, "0".repeat(64));
        assert!(matches!(
            attest_hspice(&request, &wrong),
            Err(TuneError::External(message)) if message.contains("does not match")
        ));
    }

    #[test]
    fn oversized_hspice_listing_is_rejected_before_read() {
        let root = std::env::temp_dir().join(format!("sipi-as04-listing-{}", std::process::id()));
        fs::create_dir_all(&root).unwrap();
        let path = root.join("oversized.lis");
        let file = fs::File::create(&path).unwrap();
        file.set_len((MAX_ARTIFACT_BYTES + 1) as u64).unwrap();
        assert!(matches!(
            measure(&path, "rms"),
            Err(TuneError::External(message)) if message.contains("16 MiB")
        ));
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn accepted_model_is_frozen_before_final_publish() {
        let root = std::env::temp_dir().join(format!("sipi-as04-freeze-{}", std::process::id()));
        fs::create_dir_all(&root).unwrap();
        let model = RfmModel {
            version: 200600,
            nports: 1,
            matrix_type: "S".to_owned(),
            z0: 50.0,
            poles: vec![Complex::new(-1.0, 0.0)],
            residues: vec![vec![Complex::new(0.5, 0.0)]],
            constant: vec![Complex::new(0.0, 0.0)],
        };
        let frozen = root.join("work").join("best.rfm");
        let output = root.join("published").join("best.rfm");
        let trial = root.join("work").join("trial.rfm");
        write_cadence_rfm(&trial, &model).unwrap();
        let receipt = freeze_best_rfm(&frozen, &trial).unwrap();
        let published = publish_frozen_best(&frozen, &output).unwrap();
        assert_eq!(receipt.source, receipt.target);
        assert_eq!(receipt.target, published);
        assert_eq!(fs::read(&frozen).unwrap(), fs::read(&output).unwrap());
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn final_publish_rejects_existing_output_and_cleans_temp() {
        let root = std::env::temp_dir().join(format!("sipi-as04-publish-{}", std::process::id()));
        fs::create_dir_all(&root).unwrap();
        let frozen = root.join("best.rfm");
        fs::write(&frozen, b"candidate").unwrap();
        let output = root.join("out.rfm");
        fs::write(&output, b"old").unwrap();
        assert!(matches!(
            publish_frozen_best(&frozen, &output),
            Err(TuneError::Output(message)) if message.contains("existing")
        ));
        assert_eq!(fs::read(&output).unwrap(), b"old");
        assert!(!root.join(".out.rfm.sipi-new").exists());
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn artifact_aliases_are_rejected_before_external_execution() {
        let root = std::env::temp_dir().join(format!("sipi-as04-alias-{}", std::process::id()));
        let request = TuneYparamTranRequest::new(
            root.join("input.s2p"),
            root.join("input.rfm"),
            root.join("deck.sp"),
            root.join("input.rfm"),
            root.join("work"),
            "model.rfm",
            "rms",
            vec![1.0, 2.0],
            vec![1.5],
        )
        .unwrap();
        assert!(matches!(
            tune_yparam_tran(&request),
            Err(TuneError::Output(message)) if message.contains("alias")
        ));
    }

    #[cfg(unix)]
    #[test]
    fn hardlink_output_is_rejected_as_existing_alias() {
        let root = std::env::temp_dir().join(format!("sipi-as04-hardlink-{}", std::process::id()));
        fs::create_dir_all(&root).unwrap();
        let input = root.join("input.rfm");
        let output = root.join("output.rfm");
        fs::write(&input, b"input").unwrap();
        fs::hard_link(&input, &output).unwrap();
        let request = TuneYparamTranRequest::new(
            root.join("input.s2p"),
            &input,
            root.join("deck.sp"),
            &output,
            root.join("work"),
            "model.rfm",
            "rms",
            vec![1.0, 2.0],
            vec![1.5],
        )
        .unwrap();
        assert!(matches!(
            tune_yparam_tran(&request),
            Err(TuneError::Output(message)) if message.contains("fresh")
        ));
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn hspice_path_execution_is_fail_closed_before_path_lookup() {
        let root = std::env::temp_dir().join(format!("sipi-as04-custody-{}", std::process::id()));
        let request = TuneYparamTranRequest::new(
            root.join("input.s2p"),
            root.join("input.rfm"),
            root.join("deck.sp"),
            root.join("out.rfm"),
            root.join("work"),
            "model.rfm",
            "rms",
            vec![1.0, 2.0],
            vec![1.5],
        )
        .unwrap();
        let result = tune_yparam_tran(&request);
        assert!(matches!(result, Err(TuneError::External(message)) if message.contains("custody")));
        assert!(!root.join("work").exists());
    }
}
