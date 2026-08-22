//! Strict process-external transport for the pinned Agent-COM workflows.
//!
//! This crate deliberately does not reimplement COM.  It starts the exact
//! upstream CLI (or a Python process for the public API workflow), passes the
//! caller's values without filling in product defaults, and turns process,
//! protocol, resource, and upstream failures into stable typed errors.

use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::BTreeMap;
use std::ffi::{OsStr, OsString};
use std::fmt::{Display, Formatter};
use std::fs::{self, Metadata};
use std::io::{self, Read, Write};
use std::path::{Path, PathBuf};
use std::process::{ChildStderr, ChildStdin, ChildStdout, Command, ExitStatus, Stdio};
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::thread;
use std::time::{Duration, Instant};

#[cfg(windows)]
use process_wrap::std::{ChildWrapper, CommandWrap, CommandWrapper, JobObject};
#[cfg(not(windows))]
use std::process::Child;

/// Immutable upstream source identity.  This is evidence, not a runtime
/// claim that the external executable itself is present.
pub const UPSTREAM_REPOSITORY: &str = "https://github.com/z331225718/agent-com.git";
pub const UPSTREAM_COMMIT: &str = "5272ffe74702cd585054d975559b06f8afae7b6e";
pub const ADAPTER_SCHEMA: &str = "sipi.agent-com.process-adapter.v1";

const DEFAULT_TIMEOUT: Duration = Duration::from_secs(30 * 60);
const DEFAULT_MAX_STDOUT: usize = 8 * 1024 * 1024;
const DEFAULT_MAX_STDERR: usize = 8 * 1024 * 1024;
const DEFAULT_MAX_STDIN: usize = 1024 * 1024;
const DEFAULT_MAX_ARTIFACT_BYTES: u64 = 4 * 1024 * 1024 * 1024;
const DEFAULT_MAX_ARTIFACT_ENTRIES: usize = 100_000;
const DEFAULT_POLL_INTERVAL: Duration = Duration::from_millis(20);
const MAX_ARGUMENT_BYTES: usize = 1024 * 1024;
const MAX_ARTIFACT_DEPTH: usize = 64;
const SECONDARY_REAP_TIMEOUT: Duration = Duration::from_secs(2);

/// A cancellation handle that may be shared with a caller-owned worker.
#[derive(Clone, Debug, Default)]
pub struct CancellationToken(Arc<AtomicBool>);

impl CancellationToken {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn cancel(&self) {
        self.0.store(true, Ordering::Release);
    }

    pub fn is_cancelled(&self) -> bool {
        self.0.load(Ordering::Acquire)
    }
}

/// Command plus fixed arguments.  No shell is used, so paths and overrides
/// are passed as individual arguments exactly as supplied.
#[derive(Clone, Debug)]
pub struct BackendCommand {
    pub executable: PathBuf,
    pub fixed_args: Vec<OsString>,
}

impl BackendCommand {
    pub fn new(executable: impl Into<PathBuf>) -> Self {
        Self {
            executable: executable.into(),
            fixed_args: Vec::new(),
        }
    }

    pub fn with_fixed_args<I, S>(mut self, args: I) -> Self
    where
        I: IntoIterator<Item = S>,
        S: Into<OsString>,
    {
        self.fixed_args = args.into_iter().map(Into::into).collect();
        self
    }
}

/// Hard process and artifact limits.  The adapter never silently expands a
/// limit supplied by the caller.
#[derive(Clone, Debug)]
pub struct AdapterLimits {
    pub timeout: Duration,
    pub max_stdout_bytes: usize,
    pub max_stderr_bytes: usize,
    pub max_stdin_bytes: usize,
    pub max_artifact_bytes: u64,
    pub max_artifact_entries: usize,
    pub poll_interval: Duration,
}

impl Default for AdapterLimits {
    fn default() -> Self {
        Self {
            timeout: DEFAULT_TIMEOUT,
            max_stdout_bytes: DEFAULT_MAX_STDOUT,
            max_stderr_bytes: DEFAULT_MAX_STDERR,
            max_stdin_bytes: DEFAULT_MAX_STDIN,
            max_artifact_bytes: DEFAULT_MAX_ARTIFACT_BYTES,
            max_artifact_entries: DEFAULT_MAX_ARTIFACT_ENTRIES,
            poll_interval: DEFAULT_POLL_INTERVAL,
        }
    }
}

impl AdapterLimits {
    fn validate(&self) -> Result<(), AdapterError> {
        if self.timeout.is_zero()
            || self.max_stdout_bytes == 0
            || self.max_stderr_bytes == 0
            || self.max_stdin_bytes == 0
            || self.max_artifact_bytes == 0
            || self.max_artifact_entries == 0
            || self.poll_interval.is_zero()
        {
            return Err(AdapterError::InvalidRequest(
                "adapter limits must be positive".to_owned(),
            ));
        }
        Ok(())
    }
}

/// Adapter configuration.  `cli` points to the installed `com8023` entry
/// point; `python` points to the interpreter used only for the public API
/// workflow bridge.
#[derive(Clone, Debug)]
pub struct AdapterConfig {
    pub cli: BackendCommand,
    pub python: BackendCommand,
    pub working_directory: PathBuf,
    pub limits: AdapterLimits,
    pub cancellation: CancellationToken,
}

impl AdapterConfig {
    pub fn new(
        cli: BackendCommand,
        python: BackendCommand,
        working_directory: impl Into<PathBuf>,
    ) -> Self {
        Self {
            cli,
            python,
            working_directory: working_directory.into(),
            limits: AdapterLimits::default(),
            cancellation: CancellationToken::new(),
        }
    }
}

#[derive(Clone, Debug)]
pub struct AgentComAdapter {
    config: AdapterConfig,
}

impl AgentComAdapter {
    pub fn new(mut config: AdapterConfig) -> Result<Self, AdapterError> {
        config.limits.validate()?;
        config.working_directory = validate_working_directory(&config.working_directory)?;
        Ok(Self { config })
    }

    pub fn config_validate(
        &self,
        request: &ConfigValidateRequest,
    ) -> Result<ConfigValidateResponse, AdapterError> {
        request.validate()?;
        let mut args = vec![OsString::from("config"), OsString::from("validate")];
        args.push(
            resolve_request_path(&self.config.working_directory, &request.config).into_os_string(),
        );
        append_profile_args(
            &mut args,
            request.profile.as_deref(),
            request.reader.as_deref(),
            &request.fix_ids,
            &request.overrides,
        )?;
        if request.materialized_json {
            args.push(OsString::from("--materialized-json"));
        } else if request.json {
            args.push(OsString::from("--json"));
        }
        let output = self.run_backend(&self.config.cli, args, None)?;
        let stdout = output.stdout_text()?;
        let report = if request.json || request.materialized_json {
            Some(parse_json("config validate", &stdout)?)
        } else {
            None
        };
        Ok(ConfigValidateResponse {
            report,
            stdout,
            stderr: output.stderr_text(),
            exit_code: output.exit_code,
        })
    }

    pub fn run(&self, request: &RunRequest) -> Result<RunResponse, AdapterError> {
        request.validate()?;
        let config = resolve_request_path(&self.config.working_directory, &request.config);
        let thru = resolve_request_path(&self.config.working_directory, &request.thru);
        let fext = request
            .fext
            .iter()
            .map(|path| resolve_request_path(&self.config.working_directory, path))
            .collect::<Vec<_>>();
        let next = request
            .next
            .iter()
            .map(|path| resolve_request_path(&self.config.working_directory, path))
            .collect::<Vec<_>>();
        let output_dir = resolve_request_path(&self.config.working_directory, &request.output_dir);
        reject_link_ancestors(&output_dir)?;
        let log_file = request
            .log_file
            .as_deref()
            .map(|path| {
                resolve_designated_output_path(&self.config.working_directory, &output_dir, path)
            })
            .transpose()?;
        let progress_jsonl = request
            .progress_jsonl
            .as_deref()
            .map(|path| {
                resolve_designated_output_path(&self.config.working_directory, &output_dir, path)
            })
            .transpose()?;
        let mut args = vec![OsString::from("run")];
        args.push(OsString::from("--config"));
        args.push(config.into_os_string());
        args.push(OsString::from("--thru"));
        args.push(thru.into_os_string());
        append_path_args(&mut args, "--fext", &fext);
        append_path_args(&mut args, "--next", &next);
        if let Some(path) = &request.calibration_noise {
            args.push(OsString::from("--calibration-noise"));
            args.push(resolve_request_path(&self.config.working_directory, path).into_os_string());
        }
        append_profile_args(
            &mut args,
            request.profile.as_deref(),
            request.reader.as_deref(),
            &request.fix_ids,
            &request.overrides,
        )?;
        args.push(OsString::from("--output-dir"));
        args.push(output_dir.as_os_str().to_owned());
        if request.overwrite {
            args.push(OsString::from("--overwrite"));
        }
        if let Some(log_file) = &log_file {
            args.push(OsString::from("--log-file"));
            args.push(log_file.as_os_str().to_owned());
        }
        if let Some(progress_jsonl) = &progress_jsonl {
            args.push(OsString::from("--progress-jsonl"));
            args.push(progress_jsonl.as_os_str().to_owned());
        }
        if request.diagnostics == Some(false) {
            args.push(OsString::from("--no-plots"));
        }
        if request.legacy_csv {
            args.push(OsString::from("--legacy-csv"));
        }
        let output = self.run_backend(&self.config.cli, args, None)?;
        let stdout = output.stdout_text()?;
        let paths: CliArtifactPaths =
            serde_json::from_str(&stdout).map_err(|error| AdapterError::Protocol {
                operation: "run".to_owned(),
                message: format!("stdout is not the upstream artifact manifest: {error}"),
            })?;
        let artifacts = self.validate_artifacts(&output_dir, paths)?;
        Ok(RunResponse {
            artifacts,
            stdout,
            stderr: output.stderr_text(),
            exit_code: output.exit_code,
        })
    }

    pub fn compare(&self, request: &CompareRequest) -> Result<CompareResponse, AdapterError> {
        request.validate()?;
        let mut args = vec![OsString::from("compare"), OsString::from("--golden")];
        args.push(
            resolve_request_path(&self.config.working_directory, &request.golden).into_os_string(),
        );
        args.push(OsString::from("--result"));
        args.push(
            resolve_request_path(&self.config.working_directory, &request.result).into_os_string(),
        );
        if let Some(atol) = request.atol {
            args.push(OsString::from("--atol"));
            args.push(OsString::from(atol.to_string()));
        }
        let output = self.run_backend_allow_compare_mismatch(&self.config.cli, args, None)?;
        let stdout = output.stdout_text()?;
        let report: CompareReport =
            serde_json::from_str(&stdout).map_err(|error| AdapterError::Protocol {
                operation: "compare".to_owned(),
                message: format!("stdout is not the upstream compare report: {error}"),
            })?;
        if report.matched && output.exit_code != 0 {
            return Err(AdapterError::Protocol {
                operation: "compare".to_owned(),
                message: format!(
                    "upstream reported matched=true with exit code {}",
                    output.exit_code
                ),
            });
        }
        if !report.matched && output.exit_code != 3 {
            return Err(AdapterError::Upstream(UpstreamFailure::from_output(
                output.exit_code,
                output.stderr_text(),
            )));
        }
        Ok(CompareResponse {
            report,
            stdout,
            stderr: output.stderr_text(),
            exit_code: output.exit_code,
        })
    }

    /// Run the real public Python sequence in one external process:
    /// `load_config -> run_com -> write_artifacts`.  No result bytes are
    /// interpreted or recalculated by Rust; only the returned paths and the
    /// bounded artifact directory are checked.
    pub fn public_workflow(
        &self,
        request: &PublicWorkflowRequest,
    ) -> Result<PublicWorkflowResponse, AdapterError> {
        request.validate()?;
        let mut resolved_request = request.clone();
        resolved_request.config =
            resolve_request_path(&self.config.working_directory, &request.config);
        resolved_request.thru = resolve_request_path(&self.config.working_directory, &request.thru);
        resolved_request.fext = request
            .fext
            .iter()
            .map(|path| resolve_request_path(&self.config.working_directory, path))
            .collect();
        resolved_request.next = request
            .next
            .iter()
            .map(|path| resolve_request_path(&self.config.working_directory, path))
            .collect();
        resolved_request.calibration_noise = request
            .calibration_noise
            .as_deref()
            .map(|path| resolve_request_path(&self.config.working_directory, path));
        resolved_request.output_dir =
            resolve_request_path(&self.config.working_directory, &request.output_dir);
        let payload =
            serde_json::to_vec(&resolved_request).map_err(|error| AdapterError::Protocol {
                operation: "public workflow".to_owned(),
                message: format!("cannot encode bridge request: {error}"),
            })?;
        if payload.len() > self.config.limits.max_stdin_bytes {
            return Err(AdapterError::InputLimit {
                stream: "stdin",
                limit: self.config.limits.max_stdin_bytes,
            });
        }
        let mut args = self.config.python.fixed_args.clone();
        args.push(OsString::from("-c"));
        args.push(OsString::from(PYTHON_PUBLIC_WORKFLOW));
        let output = self.run_backend(&self.config.python, args, Some(payload))?;
        let stdout = output.stdout_text()?;
        let response: BridgeResponse =
            serde_json::from_str(&stdout).map_err(|error| AdapterError::Protocol {
                operation: "public workflow".to_owned(),
                message: format!("stdout is not the bridge response: {error}"),
            })?;
        if response.workflow != ["load_config", "run_com", "write_artifacts"] {
            return Err(AdapterError::Protocol {
                operation: "public workflow".to_owned(),
                message: "bridge did not report the required public API sequence".to_owned(),
            });
        }
        let paths = CliArtifactPaths {
            report: response.report,
            result: response.result,
            diagnostics: response.diagnostics,
        };
        let artifacts = self.validate_artifacts(&resolved_request.output_dir, paths)?;
        Ok(PublicWorkflowResponse {
            artifacts,
            stdout,
            stderr: output.stderr_text(),
            exit_code: output.exit_code,
        })
    }

    fn validate_artifacts(
        &self,
        output_dir: &Path,
        paths: CliArtifactPaths,
    ) -> Result<ArtifactSet, AdapterError> {
        let requested_output = resolve_request_path(&self.config.working_directory, output_dir);
        reject_link_ancestors(&requested_output)?;
        let base = fs::canonicalize(&requested_output).map_err(|error| AdapterError::Artifact {
            path: requested_output,
            message: format!("cannot resolve output directory: {error}"),
        })?;
        let base_metadata =
            fs::symlink_metadata(&base).map_err(|error| AdapterError::Artifact {
                path: base.clone(),
                message: error.to_string(),
            })?;
        if !base_metadata.is_dir() || is_link_or_reparse(&base_metadata) {
            return Err(AdapterError::Artifact {
                path: base,
                message: "output root is not a regular directory".to_owned(),
            });
        }
        let report_path = resolve_request_path(&self.config.working_directory, &paths.report);
        let result_path = resolve_request_path(&self.config.working_directory, &paths.result);
        let report = validate_artifact_path(&base, &report_path)?;
        let result = validate_artifact_path(&base, &result_path)?;
        let diagnostics = paths
            .diagnostics
            .as_deref()
            .map(|path| {
                let resolved = resolve_request_path(&self.config.working_directory, path);
                validate_artifact_path(&base, &resolved)
            })
            .transpose()?;
        let mut entries = 0usize;
        let bytes = scan_artifact_bytes(
            &base,
            0,
            self.config.limits.max_artifact_bytes,
            self.config.limits.max_artifact_entries,
            &mut entries,
        )?;
        Ok(ArtifactSet {
            output_dir: base,
            report,
            result,
            diagnostics,
            total_bytes: bytes,
        })
    }

    fn run_backend(
        &self,
        backend: &BackendCommand,
        args: Vec<OsString>,
        stdin: Option<Vec<u8>>,
    ) -> Result<ProcessOutput, AdapterError> {
        let output = run_process(
            backend,
            args,
            stdin,
            &self.config.working_directory,
            &self.config.limits,
            &self.config.cancellation,
        )?;
        if output.exit_code != 0 {
            return Err(AdapterError::Upstream(UpstreamFailure::from_output(
                output.exit_code,
                output.stderr_text(),
            )));
        }
        Ok(output)
    }

    fn run_backend_allow_compare_mismatch(
        &self,
        backend: &BackendCommand,
        args: Vec<OsString>,
        stdin: Option<Vec<u8>>,
    ) -> Result<ProcessOutput, AdapterError> {
        let output = run_process(
            backend,
            args,
            stdin,
            &self.config.working_directory,
            &self.config.limits,
            &self.config.cancellation,
        )?;
        if output.exit_code != 0 && output.exit_code != 3 {
            return Err(AdapterError::Upstream(UpstreamFailure::from_output(
                output.exit_code,
                output.stderr_text(),
            )));
        }
        Ok(output)
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ConfigValidateRequest {
    pub config: PathBuf,
    pub profile: Option<String>,
    pub reader: Option<String>,
    pub fix_ids: Vec<String>,
    pub overrides: Vec<String>,
    pub json: bool,
    pub materialized_json: bool,
}

impl ConfigValidateRequest {
    fn validate(&self) -> Result<(), AdapterError> {
        if self.json && self.materialized_json {
            return Err(AdapterError::InvalidRequest(
                "config validate JSON modes are mutually exclusive".to_owned(),
            ));
        }
        validate_profile_args(
            self.profile.as_deref(),
            self.reader.as_deref(),
            &self.fix_ids,
        )?;
        validate_arguments(&[
            self.config.as_os_str(),
            self.profile.as_deref().map(OsStr::new).unwrap_or_default(),
            self.reader.as_deref().map(OsStr::new).unwrap_or_default(),
        ])?;
        Ok(())
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ConfigValidateResponse {
    pub report: Option<Value>,
    pub stdout: String,
    pub stderr: String,
    pub exit_code: i32,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct RunRequest {
    pub config: PathBuf,
    pub thru: PathBuf,
    pub fext: Vec<PathBuf>,
    pub next: Vec<PathBuf>,
    pub calibration_noise: Option<PathBuf>,
    pub profile: Option<String>,
    pub reader: Option<String>,
    pub fix_ids: Vec<String>,
    pub overrides: Vec<String>,
    pub output_dir: PathBuf,
    pub overwrite: bool,
    pub log_file: Option<PathBuf>,
    pub progress_jsonl: Option<PathBuf>,
    /// `None` omits the flag and preserves the upstream CLI default.
    pub diagnostics: Option<bool>,
    pub legacy_csv: bool,
}

impl RunRequest {
    fn validate(&self) -> Result<(), AdapterError> {
        validate_profile_args(
            self.profile.as_deref(),
            self.reader.as_deref(),
            &self.fix_ids,
        )?;
        if self.calibration_noise.is_some() && (!self.fext.is_empty() || !self.next.is_empty()) {
            return Err(AdapterError::InvalidRequest(
                "calibration-noise cannot be combined with FEXT/NEXT".to_owned(),
            ));
        }
        let mut values = vec![
            self.config.as_os_str(),
            self.thru.as_os_str(),
            self.output_dir.as_os_str(),
        ];
        values.extend(self.fext.iter().map(|path| path.as_os_str()));
        values.extend(self.next.iter().map(|path| path.as_os_str()));
        values.extend(self.log_file.iter().map(|path| path.as_os_str()));
        values.extend(self.progress_jsonl.iter().map(|path| path.as_os_str()));
        validate_arguments(&values)?;
        Ok(())
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct RunResponse {
    pub artifacts: ArtifactSet,
    pub stdout: String,
    pub stderr: String,
    pub exit_code: i32,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct CompareRequest {
    pub golden: PathBuf,
    pub result: PathBuf,
    /// `None` omits `--atol` and preserves the upstream default.
    pub atol: Option<f64>,
}

impl CompareRequest {
    fn validate(&self) -> Result<(), AdapterError> {
        if let Some(atol) = self.atol
            && (!atol.is_finite() || atol < 0.0)
        {
            return Err(AdapterError::InvalidRequest(
                "comparison atol must be finite and non-negative".to_owned(),
            ));
        }
        validate_arguments(&[self.golden.as_os_str(), self.result.as_os_str()])
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct CompareResponse {
    pub report: CompareReport,
    pub stdout: String,
    pub stderr: String,
    pub exit_code: i32,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct CompareReport {
    pub matched: bool,
    pub mismatches: Vec<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ProfileSpec {
    pub name: Option<String>,
    pub reader: Option<String>,
    pub fix_ids: Vec<String>,
}

impl ProfileSpec {
    fn validate_public_workflow(&self) -> Result<(), AdapterError> {
        let name = self.name.as_deref().ok_or_else(|| {
            AdapterError::InvalidRequest(
                "public workflow profile must name a preset or custom profile".to_owned(),
            )
        })?;
        if name == "custom" && self.reader.is_none() {
            return Err(AdapterError::InvalidRequest(
                "public workflow custom profile requires an explicit reader".to_owned(),
            ));
        }
        validate_profile_args(Some(name), self.reader.as_deref(), &self.fix_ids)
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct PublicWorkflowRequest {
    pub config: PathBuf,
    pub thru: PathBuf,
    pub fext: Vec<PathBuf>,
    pub next: Vec<PathBuf>,
    pub calibration_noise: Option<PathBuf>,
    pub profile: Option<ProfileSpec>,
    pub overrides: BTreeMap<String, Value>,
    pub output_dir: PathBuf,
    pub overwrite: bool,
    pub diagnostics: bool,
}

impl PublicWorkflowRequest {
    fn validate(&self) -> Result<(), AdapterError> {
        if self.calibration_noise.is_some() && (!self.fext.is_empty() || !self.next.is_empty()) {
            return Err(AdapterError::InvalidRequest(
                "calibration-noise cannot be combined with FEXT/NEXT".to_owned(),
            ));
        }
        if let Some(profile) = &self.profile {
            profile.validate_public_workflow()?;
        }
        let mut values = vec![
            self.config.as_os_str(),
            self.thru.as_os_str(),
            self.output_dir.as_os_str(),
        ];
        values.extend(self.fext.iter().map(|path| path.as_os_str()));
        values.extend(self.next.iter().map(|path| path.as_os_str()));
        validate_arguments(&values)
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct PublicWorkflowResponse {
    pub artifacts: ArtifactSet,
    pub stdout: String,
    pub stderr: String,
    pub exit_code: i32,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ArtifactSet {
    pub output_dir: PathBuf,
    pub report: PathBuf,
    pub result: PathBuf,
    pub diagnostics: Option<PathBuf>,
    pub total_bytes: u64,
}

#[derive(Clone, Debug)]
struct CliArtifactPaths {
    report: PathBuf,
    result: PathBuf,
    diagnostics: Option<PathBuf>,
}

impl<'de> Deserialize<'de> for CliArtifactPaths {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: serde::Deserializer<'de>,
    {
        #[derive(Deserialize)]
        struct Raw {
            report: String,
            result: String,
            diagnostics: Option<String>,
        }
        let raw = Raw::deserialize(deserializer)?;
        Ok(Self {
            report: PathBuf::from(raw.report),
            result: PathBuf::from(raw.result),
            diagnostics: raw.diagnostics.map(PathBuf::from),
        })
    }
}

#[derive(Clone, Debug, Deserialize)]
struct BridgeResponse {
    workflow: Vec<String>,
    report: PathBuf,
    result: PathBuf,
    diagnostics: Option<PathBuf>,
}

#[derive(Clone, Debug)]
struct ProcessOutput {
    stdout: Vec<u8>,
    stderr: Vec<u8>,
    exit_code: i32,
}

impl ProcessOutput {
    fn stdout_text(&self) -> Result<String, AdapterError> {
        String::from_utf8(self.stdout.clone()).map_err(|error| AdapterError::Protocol {
            operation: "process stdout".to_owned(),
            message: format!("stdout is not UTF-8: {error}"),
        })
    }

    fn stderr_text(&self) -> String {
        String::from_utf8_lossy(&self.stderr).into_owned()
    }
}

#[derive(Clone, Debug)]
pub enum AdapterError {
    InvalidRequest(String),
    Launch {
        executable: PathBuf,
        message: String,
    },
    Io {
        stream: &'static str,
        message: String,
    },
    Timeout {
        timeout: Duration,
    },
    Cancelled,
    InputLimit {
        stream: &'static str,
        limit: usize,
    },
    OutputLimit {
        stream: &'static str,
        limit: usize,
    },
    ArtifactLimit {
        limit: u64,
        observed: u64,
    },
    ArtifactEntryLimit {
        limit: usize,
        observed: usize,
    },
    Artifact {
        path: PathBuf,
        message: String,
    },
    Protocol {
        operation: String,
        message: String,
    },
    Upstream(UpstreamFailure),
}

impl Display for AdapterError {
    fn fmt(&self, f: &mut Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::InvalidRequest(message) => write!(f, "invalid request: {message}"),
            Self::Launch {
                executable,
                message,
            } => write!(f, "cannot launch {}: {message}", executable.display()),
            Self::Io { stream, message } => write!(f, "{stream} I/O failed: {message}"),
            Self::Timeout { timeout } => {
                write!(f, "upstream timed out after {} ms", timeout.as_millis())
            }
            Self::Cancelled => write!(f, "upstream execution cancelled"),
            Self::InputLimit { stream, limit } => {
                write!(f, "{stream} input exceeded {limit} bytes")
            }
            Self::OutputLimit { stream, limit } => {
                write!(f, "{stream} output exceeded {limit} bytes")
            }
            Self::ArtifactLimit { limit, observed } => {
                write!(f, "artifacts exceeded {limit} bytes (observed {observed})")
            }
            Self::ArtifactEntryLimit { limit, observed } => {
                write!(
                    f,
                    "artifacts exceeded {limit} entries (observed {observed})"
                )
            }
            Self::Artifact { path, message } => {
                write!(f, "artifact {} invalid: {message}", path.display())
            }
            Self::Protocol { operation, message } => {
                write!(f, "{operation} protocol error: {message}")
            }
            Self::Upstream(failure) => Display::fmt(failure, f),
        }
    }
}

impl std::error::Error for AdapterError {}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum UpstreamErrorKind {
    Usage,
    Config,
    Input,
    Unsupported,
    Convergence,
    Internal,
    Unknown,
}

#[derive(Clone, Debug)]
pub struct UpstreamFailure {
    pub exit_code: i32,
    pub kind: UpstreamErrorKind,
    pub stderr: String,
}

impl UpstreamFailure {
    fn from_output(exit_code: i32, stderr: String) -> Self {
        let kind = match exit_code {
            2 => UpstreamErrorKind::Usage,
            3 => UpstreamErrorKind::Config,
            4 => UpstreamErrorKind::Input,
            5 => UpstreamErrorKind::Unsupported,
            6 => UpstreamErrorKind::Convergence,
            8 => UpstreamErrorKind::Internal,
            _ => UpstreamErrorKind::Unknown,
        };
        Self {
            exit_code,
            kind,
            stderr,
        }
    }
}

impl Display for UpstreamFailure {
    fn fmt(&self, f: &mut Formatter<'_>) -> std::fmt::Result {
        write!(
            f,
            "upstream {:?} failure (exit {}): {}",
            self.kind,
            self.exit_code,
            self.stderr.trim()
        )
    }
}

fn append_path_args(args: &mut Vec<OsString>, flag: &str, paths: &[PathBuf]) {
    for path in paths {
        args.push(OsString::from(flag));
        args.push(path.as_os_str().to_owned());
    }
}

fn append_profile_args(
    args: &mut Vec<OsString>,
    profile: Option<&str>,
    reader: Option<&str>,
    fix_ids: &[String],
    overrides: &[String],
) -> Result<(), AdapterError> {
    validate_profile_args(profile, reader, fix_ids)?;
    if let Some(profile) = profile {
        args.push(OsString::from("--profile"));
        args.push(OsString::from(profile));
    }
    if let Some(reader) = reader {
        args.push(OsString::from("--reader"));
        args.push(OsString::from(reader));
    }
    for fix_id in fix_ids {
        args.push(OsString::from("--fix-id"));
        args.push(OsString::from(fix_id));
    }
    for override_value in overrides {
        args.push(OsString::from("--override"));
        args.push(OsString::from(override_value));
    }
    Ok(())
}

fn validate_profile_args(
    profile: Option<&str>,
    reader: Option<&str>,
    fix_ids: &[String],
) -> Result<(), AdapterError> {
    if (reader.is_some() || !fix_ids.is_empty()) && profile != Some("custom") {
        return Err(AdapterError::InvalidRequest(
            "reader and fix-id require profile=custom".to_owned(),
        ));
    }
    if profile == Some("custom") && reader.is_none() && fix_ids.is_empty() {
        return Err(AdapterError::InvalidRequest(
            "profile=custom requires reader or at least one fix-id".to_owned(),
        ));
    }
    Ok(())
}

fn validate_arguments(arguments: &[&OsStr]) -> Result<(), AdapterError> {
    let total = arguments
        .iter()
        .map(|argument| argument.as_encoded_bytes().len())
        .try_fold(0usize, |sum, len| sum.checked_add(len))
        .ok_or_else(|| AdapterError::InvalidRequest("argument byte count overflow".to_owned()))?;
    if total > MAX_ARGUMENT_BYTES {
        return Err(AdapterError::InputLimit {
            stream: "arguments",
            limit: MAX_ARGUMENT_BYTES,
        });
    }
    Ok(())
}

fn parse_json(operation: &str, stdout: &str) -> Result<Value, AdapterError> {
    serde_json::from_str(stdout).map_err(|error| AdapterError::Protocol {
        operation: operation.to_owned(),
        message: format!("stdout is not JSON: {error}"),
    })
}

fn validate_artifact_path(base: &Path, path: &Path) -> Result<PathBuf, AdapterError> {
    reject_link_ancestors(path)?;
    let canonical = fs::canonicalize(path).map_err(|error| AdapterError::Artifact {
        path: path.to_path_buf(),
        message: format!("cannot resolve path: {error}"),
    })?;
    if !canonical.starts_with(base) {
        return Err(AdapterError::Artifact {
            path: canonical,
            message: "path escapes requested output directory".to_owned(),
        });
    }
    let metadata = fs::symlink_metadata(&canonical).map_err(|error| AdapterError::Artifact {
        path: canonical.clone(),
        message: error.to_string(),
    })?;
    if is_link_or_reparse(&metadata) || !metadata.is_file() {
        return Err(AdapterError::Artifact {
            path: canonical,
            message: "path is not a regular file".to_owned(),
        });
    }
    Ok(canonical)
}

fn scan_artifact_bytes(
    base: &Path,
    depth: usize,
    byte_limit: u64,
    entry_limit: usize,
    entries_seen: &mut usize,
) -> Result<u64, AdapterError> {
    if depth > MAX_ARTIFACT_DEPTH {
        return Err(AdapterError::Artifact {
            path: base.to_path_buf(),
            message: "artifact directory nesting exceeds bound".to_owned(),
        });
    }
    let mut total = 0u64;
    let entries = fs::read_dir(base).map_err(|error| AdapterError::Artifact {
        path: base.to_path_buf(),
        message: error.to_string(),
    })?;
    for entry in entries {
        let entry = entry.map_err(|error| AdapterError::Artifact {
            path: base.to_path_buf(),
            message: error.to_string(),
        })?;
        *entries_seen = entries_seen
            .checked_add(1)
            .ok_or(AdapterError::ArtifactEntryLimit {
                limit: entry_limit,
                observed: usize::MAX,
            })?;
        if *entries_seen > entry_limit {
            return Err(AdapterError::ArtifactEntryLimit {
                limit: entry_limit,
                observed: *entries_seen,
            });
        }
        let path = entry.path();
        let metadata = fs::symlink_metadata(&path).map_err(|error| AdapterError::Artifact {
            path: path.clone(),
            message: error.to_string(),
        })?;
        let file_type = metadata.file_type();
        if is_link_or_reparse(&metadata) {
            return Err(AdapterError::Artifact {
                path,
                message: "symlink/junction artifacts are not accepted".to_owned(),
            });
        }
        let size = if file_type.is_dir() {
            scan_artifact_bytes(&path, depth + 1, byte_limit, entry_limit, entries_seen)?
        } else if file_type.is_file() {
            metadata.len()
        } else {
            return Err(AdapterError::Artifact {
                path,
                message: "artifact entry is not a regular file or directory".to_owned(),
            });
        };
        total = total.checked_add(size).ok_or(AdapterError::ArtifactLimit {
            limit: byte_limit,
            observed: u64::MAX,
        })?;
        if total > byte_limit {
            return Err(AdapterError::ArtifactLimit {
                limit: byte_limit,
                observed: total,
            });
        }
    }
    Ok(total)
}

fn reject_link_ancestors(path: &Path) -> Result<(), AdapterError> {
    let absolute = if path.is_absolute() {
        path.to_path_buf()
    } else {
        std::env::current_dir()
            .map_err(|error| AdapterError::Artifact {
                path: path.to_path_buf(),
                message: format!("cannot resolve current directory: {error}"),
            })?
            .join(path)
    };
    let mut current = Some(absolute.as_path());
    while let Some(candidate) = current {
        match fs::symlink_metadata(candidate) {
            Ok(metadata) if is_link_or_reparse(&metadata) => {
                return Err(AdapterError::Artifact {
                    path: candidate.to_path_buf(),
                    message: "path or ancestor is a symlink/junction".to_owned(),
                });
            }
            Ok(_) => {}
            Err(error) if error.kind() == io::ErrorKind::NotFound => {}
            Err(error) => {
                return Err(AdapterError::Artifact {
                    path: candidate.to_path_buf(),
                    message: format!("cannot inspect output root ancestor: {error}"),
                });
            }
        }
        current = candidate.parent();
    }
    Ok(())
}

fn validate_working_directory(path: &Path) -> Result<PathBuf, AdapterError> {
    reject_link_ancestors(path)?;
    let canonical = fs::canonicalize(path).map_err(|error| AdapterError::Artifact {
        path: path.to_path_buf(),
        message: format!("cannot resolve working directory: {error}"),
    })?;
    let metadata = fs::symlink_metadata(&canonical).map_err(|error| AdapterError::Artifact {
        path: canonical.clone(),
        message: format!("cannot inspect working directory: {error}"),
    })?;
    if !metadata.is_dir() || is_link_or_reparse(&metadata) {
        return Err(AdapterError::Artifact {
            path: canonical,
            message: "working directory is not a regular directory".to_owned(),
        });
    }
    Ok(canonical)
}

fn resolve_request_path(working_directory: &Path, path: &Path) -> PathBuf {
    if path.is_absolute() {
        path.to_path_buf()
    } else {
        working_directory.join(path)
    }
}

fn resolve_designated_output_path(
    working_directory: &Path,
    output_dir: &Path,
    path: &Path,
) -> Result<PathBuf, AdapterError> {
    if path
        .components()
        .any(|component| matches!(component, std::path::Component::ParentDir))
    {
        return Err(AdapterError::InvalidRequest(
            "designated output path contains a parent component".to_owned(),
        ));
    }
    let resolved = resolve_request_path(working_directory, path);
    if resolved == output_dir || !resolved.starts_with(output_dir) {
        return Err(AdapterError::InvalidRequest(
            "designated output path escapes output-dir".to_owned(),
        ));
    }
    reject_link_ancestors(&resolved)?;
    Ok(resolved)
}

fn is_link_or_reparse(metadata: &Metadata) -> bool {
    if metadata.file_type().is_symlink() {
        return true;
    }
    #[cfg(windows)]
    {
        use std::os::windows::fs::MetadataExt;
        const FILE_ATTRIBUTE_REPARSE_POINT: u32 = 0x0400;
        metadata.file_attributes() & FILE_ATTRIBUTE_REPARSE_POINT != 0
    }
    #[cfg(not(windows))]
    {
        let _ = metadata;
        false
    }
}

#[cfg(windows)]
type ManagedChild = Box<dyn ChildWrapper>;
#[cfg(not(windows))]
type ManagedChild = Child;

#[cfg(windows)]
#[derive(Debug)]
struct FailClosedJobSetup;

#[cfg(windows)]
impl CommandWrapper for FailClosedJobSetup {
    fn wrap_child(
        &mut self,
        child: Box<dyn ChildWrapper>,
        _core: &CommandWrap,
    ) -> io::Result<Box<dyn ChildWrapper>> {
        Ok(Box::new(KillSuspendedOnDrop(Some(child))))
    }
}

#[cfg(windows)]
#[derive(Debug)]
struct KillSuspendedOnDrop(Option<Box<dyn ChildWrapper>>);

#[cfg(windows)]
impl ChildWrapper for KillSuspendedOnDrop {
    fn inner(&self) -> &dyn ChildWrapper {
        self.0.as_deref().expect("inner child is present")
    }

    fn inner_mut(&mut self) -> &mut dyn ChildWrapper {
        self.0.as_deref_mut().expect("inner child is present")
    }

    fn into_inner(mut self: Box<Self>) -> Box<dyn ChildWrapper> {
        self.0.take().expect("inner child is present")
    }
}

#[cfg(windows)]
impl Drop for KillSuspendedOnDrop {
    fn drop(&mut self) {
        if let Some(child) = self.0.as_deref_mut() {
            let _ = child.kill();
        }
    }
}

#[cfg(windows)]
#[derive(Debug)]
struct PreserveJobCompletionPoll;

#[cfg(windows)]
impl CommandWrapper for PreserveJobCompletionPoll {
    fn wrap_child(
        &mut self,
        child: Box<dyn ChildWrapper>,
        _core: &CommandWrap,
    ) -> io::Result<Box<dyn ChildWrapper>> {
        Ok(Box::new(JobCompletionChild(child)))
    }
}

#[cfg(windows)]
#[derive(Debug)]
struct JobCompletionChild(Box<dyn ChildWrapper>);

#[cfg(windows)]
impl ChildWrapper for JobCompletionChild {
    fn inner(&self) -> &dyn ChildWrapper {
        &*self.0
    }

    fn inner_mut(&mut self) -> &mut dyn ChildWrapper {
        &mut *self.0
    }

    fn into_inner(self: Box<Self>) -> Box<dyn ChildWrapper> {
        self.0
    }

    fn start_kill(&mut self) -> io::Result<()> {
        self.0.start_kill()
    }

    fn try_wait(&mut self) -> io::Result<Option<ExitStatus>> {
        self.0.inner_mut().try_wait()
    }

    fn wait(&mut self) -> io::Result<ExitStatus> {
        self.0.wait()
    }
}

#[cfg(windows)]
fn spawn_managed(command: Command) -> io::Result<ManagedChild> {
    let mut command = CommandWrap::from(command);
    command
        .wrap(FailClosedJobSetup)
        .wrap(JobObject)
        .wrap(PreserveJobCompletionPoll)
        .spawn()
}

#[cfg(not(windows))]
fn spawn_managed(mut command: Command) -> io::Result<ManagedChild> {
    command.spawn()
}

#[cfg(windows)]
fn take_child_stdout(child: &mut ManagedChild) -> Option<ChildStdout> {
    child.stdout().take()
}

#[cfg(not(windows))]
fn take_child_stdout(child: &mut ManagedChild) -> Option<ChildStdout> {
    child.stdout.take()
}

#[cfg(windows)]
fn take_child_stderr(child: &mut ManagedChild) -> Option<ChildStderr> {
    child.stderr().take()
}

#[cfg(not(windows))]
fn take_child_stderr(child: &mut ManagedChild) -> Option<ChildStderr> {
    child.stderr.take()
}

#[cfg(windows)]
fn take_child_stdin(child: &mut ManagedChild) -> Option<ChildStdin> {
    child.stdin().take()
}

#[cfg(not(windows))]
fn take_child_stdin(child: &mut ManagedChild) -> Option<ChildStdin> {
    child.stdin.take()
}

fn child_try_wait(child: &mut ManagedChild) -> io::Result<Option<ExitStatus>> {
    #[cfg(windows)]
    {
        child.try_wait()
    }
    #[cfg(not(windows))]
    {
        child.try_wait()
    }
}

fn run_process(
    backend: &BackendCommand,
    args: Vec<OsString>,
    stdin: Option<Vec<u8>>,
    working_directory: &Path,
    limits: &AdapterLimits,
    cancellation: &CancellationToken,
) -> Result<ProcessOutput, AdapterError> {
    limits.validate()?;
    validate_final_argv(backend, &args)?;
    let mut command = Command::new(&backend.executable);
    command.args(&backend.fixed_args);
    command.args(&args);
    command.current_dir(working_directory);
    command.stdin(if stdin.is_some() {
        Stdio::piped()
    } else {
        Stdio::null()
    });
    command.stdout(Stdio::piped());
    command.stderr(Stdio::piped());
    let mut child = spawn_managed(command).map_err(|error| AdapterError::Launch {
        executable: backend.executable.clone(),
        message: error.to_string(),
    })?;
    let stdout = match take_child_stdout(&mut child) {
        Some(stdout) => stdout,
        None => {
            return Err(terminate_with_reason(
                &mut child,
                AdapterError::Io {
                    stream: "stdout",
                    message: "child stdout pipe unavailable".to_owned(),
                },
            ));
        }
    };
    let stderr = match take_child_stderr(&mut child) {
        Some(stderr) => stderr,
        None => {
            return Err(terminate_with_reason(
                &mut child,
                AdapterError::Io {
                    stream: "stderr",
                    message: "child stderr pipe unavailable".to_owned(),
                },
            ));
        }
    };
    let stdout_overflow = Arc::new(AtomicBool::new(false));
    let stderr_overflow = Arc::new(AtomicBool::new(false));
    let stdout_thread = spawn_reader(
        stdout,
        limits.max_stdout_bytes,
        "stdout",
        stdout_overflow.clone(),
    );
    let stderr_thread = spawn_reader(
        stderr,
        limits.max_stderr_bytes,
        "stderr",
        stderr_overflow.clone(),
    );
    let input_thread = stdin.map(|bytes| {
        let mut stream = take_child_stdin(&mut child).expect("stdin was requested");
        thread::spawn(move || stream.write_all(&bytes))
    });
    let started = Instant::now();
    let mut termination: Option<AdapterError> = None;
    loop {
        if cancellation.is_cancelled() {
            termination = Some(terminate_with_reason(&mut child, AdapterError::Cancelled));
            break;
        }
        if stdout_overflow.load(Ordering::Acquire) {
            termination = Some(terminate_with_reason(
                &mut child,
                AdapterError::OutputLimit {
                    stream: "stdout",
                    limit: limits.max_stdout_bytes,
                },
            ));
            break;
        }
        if stderr_overflow.load(Ordering::Acquire) {
            termination = Some(terminate_with_reason(
                &mut child,
                AdapterError::OutputLimit {
                    stream: "stderr",
                    limit: limits.max_stderr_bytes,
                },
            ));
            break;
        }
        if started.elapsed() >= limits.timeout {
            termination = Some(terminate_with_reason(
                &mut child,
                AdapterError::Timeout {
                    timeout: limits.timeout,
                },
            ));
            break;
        }
        match child_try_wait(&mut child) {
            Ok(Some(_)) => break,
            Ok(None) => thread::sleep(limits.poll_interval),
            Err(error) => {
                termination = Some(terminate_with_reason(
                    &mut child,
                    AdapterError::Io {
                        stream: "process",
                        message: error.to_string(),
                    },
                ));
                break;
            }
        }
    }
    #[cfg(windows)]
    if termination.is_none()
        && let Err(error) = terminate_process_tree(&mut child)
    {
        termination = Some(error);
    }
    let status_result = wait_child_bounded(child);
    let join_deadline = Instant::now() + SECONDARY_REAP_TIMEOUT;
    let input_result = input_thread
        .map(|thread| join_stdin_bounded(thread, join_deadline))
        .transpose();
    let stdout_result = join_reader_bounded(stdout_thread, "stdout", join_deadline);
    let stderr_result = join_reader_bounded(stderr_thread, "stderr", join_deadline);
    let status = match status_result {
        Ok(status) => status,
        Err(error) => {
            // The bounded joins above are deliberately completed before
            // returning a process-reap error, so a descendant holding a pipe
            // cannot strand this caller in an unbounded JoinHandle::join.
            let _ = input_result;
            let _ = stdout_result;
            let _ = stderr_result;
            return Err(error);
        }
    };
    input_result?;
    let stdout = stdout_result?;
    let stderr = stderr_result?;
    if let Some(error) = termination {
        return Err(error);
    }
    Ok(ProcessOutput {
        stdout,
        stderr,
        exit_code: exit_code(status),
    })
}

fn validate_final_argv(backend: &BackendCommand, args: &[OsString]) -> Result<(), AdapterError> {
    let total = backend
        .executable
        .as_os_str()
        .as_encoded_bytes()
        .len()
        .checked_add(
            backend
                .fixed_args
                .iter()
                .chain(args.iter())
                .map(|argument| argument.as_os_str().as_encoded_bytes().len())
                .try_fold(0usize, |sum, len| sum.checked_add(len))
                .ok_or_else(|| {
                    AdapterError::InvalidRequest("argument byte count overflow".to_owned())
                })?,
        )
        .ok_or_else(|| AdapterError::InvalidRequest("argument byte count overflow".to_owned()))?;
    if total > MAX_ARGUMENT_BYTES {
        return Err(AdapterError::InputLimit {
            stream: "argv",
            limit: MAX_ARGUMENT_BYTES,
        });
    }
    Ok(())
}

fn wait_child_bounded(mut child: ManagedChild) -> Result<ExitStatus, AdapterError> {
    let wait_thread = thread::spawn(move || {
        #[cfg(windows)]
        {
            child.wait()
        }
        #[cfg(not(windows))]
        {
            child.wait()
        }
    });
    let deadline = Instant::now() + SECONDARY_REAP_TIMEOUT;
    let mut wait_thread = Some(wait_thread);
    loop {
        let handle = wait_thread.take().expect("wait thread remains available");
        if handle.is_finished() {
            return handle
                .join()
                .map_err(|_| AdapterError::Io {
                    stream: "process",
                    message: "process wait thread panicked".to_owned(),
                })?
                .map_err(|error| AdapterError::Io {
                    stream: "process",
                    message: error.to_string(),
                });
        }
        if Instant::now() >= deadline {
            drop(handle);
            return Err(AdapterError::Io {
                stream: "process",
                message: "terminated process job did not drain before secondary deadline"
                    .to_owned(),
            });
        }
        wait_thread = Some(handle);
        thread::sleep(DEFAULT_POLL_INTERVAL);
    }
}

fn join_stdin_bounded(
    thread: thread::JoinHandle<io::Result<()>>,
    deadline: Instant,
) -> Result<(), AdapterError> {
    let mut thread = Some(thread);
    while let Some(handle) = thread.take() {
        if handle.is_finished() {
            return handle
                .join()
                .map_err(|_| AdapterError::Io {
                    stream: "stdin",
                    message: "stdin writer panicked".to_owned(),
                })?
                .map_err(|error| AdapterError::Io {
                    stream: "stdin",
                    message: error.to_string(),
                });
        }
        if Instant::now() >= deadline {
            drop(handle);
            return Err(AdapterError::Io {
                stream: "stdin",
                message: "stdin writer did not finish before secondary deadline".to_owned(),
            });
        }
        thread = Some(handle);
        thread::sleep(DEFAULT_POLL_INTERVAL);
    }
    unreachable!()
}

fn join_reader_bounded(
    thread: thread::JoinHandle<Result<Vec<u8>, AdapterError>>,
    stream: &'static str,
    deadline: Instant,
) -> Result<Vec<u8>, AdapterError> {
    let mut thread = Some(thread);
    while let Some(handle) = thread.take() {
        if handle.is_finished() {
            return handle.join().map_err(|_| AdapterError::Io {
                stream,
                message: "output reader panicked".to_owned(),
            })?;
        }
        if Instant::now() >= deadline {
            drop(handle);
            return Err(AdapterError::Io {
                stream,
                message: "output reader did not finish before secondary deadline".to_owned(),
            });
        }
        thread = Some(handle);
        thread::sleep(DEFAULT_POLL_INTERVAL);
    }
    unreachable!()
}

fn spawn_reader<R>(
    mut reader: R,
    limit: usize,
    stream: &'static str,
    overflow: Arc<AtomicBool>,
) -> thread::JoinHandle<Result<Vec<u8>, AdapterError>>
where
    R: Read + Send + 'static,
{
    thread::spawn(move || {
        let mut output = Vec::new();
        let mut buffer = [0u8; 16 * 1024];
        loop {
            let count = reader.read(&mut buffer).map_err(|error| AdapterError::Io {
                stream,
                message: error.to_string(),
            })?;
            if count == 0 {
                break;
            }
            let remaining = limit.saturating_sub(output.len());
            output.extend_from_slice(&buffer[..count.min(remaining)]);
            if count > remaining {
                overflow.store(true, Ordering::Release);
            }
        }
        Ok(output)
    })
}

fn terminate_with_reason(child: &mut ManagedChild, reason: AdapterError) -> AdapterError {
    terminate_process_tree(child).err().unwrap_or(reason)
}

#[cfg(windows)]
fn terminate_process_tree(child: &mut ManagedChild) -> Result<(), AdapterError> {
    child.start_kill().map_err(|error| AdapterError::Io {
        stream: "process-job",
        message: format!("cannot terminate Windows Job Object: {error}"),
    })
}

#[cfg(not(windows))]
fn terminate_process_tree(child: &mut ManagedChild) -> Result<(), AdapterError> {
    child.kill().map_err(|error| AdapterError::Io {
        stream: "process",
        message: error.to_string(),
    })
}

fn exit_code(status: ExitStatus) -> i32 {
    status.code().unwrap_or(1)
}

/// Embedded bridge kept intentionally small: it invokes the upstream public
/// API, not the candidate SIPI implementation.  It receives only paths and
/// typed JSON values; no upstream bytes are vendored into this crate.
const PYTHON_PUBLIC_WORKFLOW: &str = r#"
import json
import sys
from pathlib import Path
from agent_com import BehaviorProfile, ChannelSet, RunOptions, load_config, run_com, write_artifacts

request = json.load(sys.stdin)
spec = request.get("profile")
profile = None
if spec is not None:
    name = spec["name"]
    reader = spec.get("reader")
    fix_ids = frozenset(spec.get("fix_ids", []))
    if name != "custom":
        profile = BehaviorProfile.from_name(name)
    else:
        profile = BehaviorProfile("r480", reader, fix_ids)

config = load_config(
    request["config"],
    overrides=request.get("overrides") or None,
    profile=profile,
)
channels = ChannelSet(
    request["thru"],
    fext=tuple(request.get("fext", [])),
    next=tuple(request.get("next", [])),
    calibration_noise=request.get("calibration_noise"),
)
result = run_com(
    config=config,
    channels=channels,
    options=RunOptions(config.profile, diagnostics=bool(request.get("diagnostics", False))),
)
result_path, diagnostics_path = write_artifacts(
    result,
    request["output_dir"],
    overwrite=bool(request.get("overwrite", False)),
)
report_path = Path(request["output_dir"]) / "report.html"
print(json.dumps({
    "workflow": ["load_config", "run_com", "write_artifacts"],
    "report": str(report_path.resolve()),
    "result": str(result_path.resolve()),
    "diagnostics": None if diagnostics_path is None else str(diagnostics_path.resolve()),
}, sort_keys=True))
"#;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn custom_profile_requires_explicit_reader_or_fix() {
        let error = validate_profile_args(Some("custom"), None, &[]).unwrap_err();
        assert!(error.to_string().contains("requires reader"));
    }

    #[test]
    fn compare_default_omits_atol() {
        let request = CompareRequest {
            golden: PathBuf::from("golden.json"),
            result: PathBuf::from("result.json"),
            atol: None,
        };
        request.validate().unwrap();
    }

    #[test]
    fn public_workflow_rejects_empty_profile_spec() {
        let profile = ProfileSpec {
            name: None,
            reader: None,
            fix_ids: vec![],
        };
        assert!(matches!(
            profile.validate_public_workflow(),
            Err(AdapterError::InvalidRequest(_))
        ));
    }

    #[test]
    fn public_workflow_custom_profile_requires_explicit_reader() {
        let profile = ProfileSpec {
            name: Some("custom".to_owned()),
            reader: None,
            fix_ids: vec!["fix.example".to_owned()],
        };
        assert!(matches!(
            profile.validate_public_workflow(),
            Err(AdapterError::InvalidRequest(_))
        ));
    }

    #[test]
    fn artifact_limit_is_enforced() {
        let root = tempfile_dir("bytes");
        fs::write(root.join("one"), b"1234").unwrap();
        let error = scan_artifact_bytes(&root, 0, 3, 10, &mut 0).unwrap_err();
        assert!(matches!(error, AdapterError::ArtifactLimit { .. }));
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn artifact_entry_limit_is_enforced() {
        let root = tempfile_dir("entries");
        fs::write(root.join("one"), b"").unwrap();
        fs::write(root.join("two"), b"").unwrap();
        let error = scan_artifact_bytes(&root, 0, 10, 1, &mut 0).unwrap_err();
        assert!(matches!(error, AdapterError::ArtifactEntryLimit { .. }));
        let _ = fs::remove_dir_all(root);
    }

    fn tempfile_dir(name: &str) -> PathBuf {
        let path =
            std::env::temp_dir().join(format!("sipi-agent-com-test-{name}-{}", std::process::id()));
        let _ = fs::remove_dir_all(&path);
        fs::create_dir_all(&path).unwrap();
        path
    }
}
