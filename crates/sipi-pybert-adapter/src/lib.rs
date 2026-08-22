#![forbid(unsafe_code)]

//! Process-external transport for the five pinned PyBERT CLI workflows.
//!
//! This crate deliberately does not contain PyBERT numerical code. It builds
//! exact public command lines from typed requests, bounds the child process
//! and its output, records the selected backend when the upstream sim-auto
//! artifact reports one, and inventories produced files. It does not select
//! a backend, rewrite a configuration, align/resample arrays, or decide
//! numerical acceptance.

use sha2::{Digest, Sha256};
use std::{
    error::Error,
    fmt,
    fs::{self, File},
    io::{self, Read},
    path::{Component, Path, PathBuf},
    process::{ChildStderr, ChildStdout, Command, ExitStatus, Stdio},
    sync::mpsc,
    thread,
    time::{Duration, Instant},
};

#[cfg(windows)]
use process_wrap::std::{ChildWrapper, CommandWrap, CommandWrapper, JobObject};
#[cfg(not(windows))]
use std::process::Child;

/// Fixed contract-source identity used by every adapter report. This does not
/// attest the bytes behind the caller-supplied executable.
pub const UPSTREAM_COMMIT: &str = "5bf6d7ea0ace261891aaeb611ffc1c267e160afe";
pub const UPSTREAM_TREE: &str = "5faef6bdb341d444ad65d82a11c0018b15805e24";
pub const UPSTREAM_CLI_PATH: &str = "src/pybert/cli.py";
pub const UPSTREAM_CLI_BLOB_SHA1: &str = "4c1116007d31bcebf8db3252363eed7774c7b349";
pub const UPSTREAM_CLI_SHA256: &str =
    "3826b0c156166e6f04b0e9997ce64a53a53867db6d89143b7c582ca2cf4337c9";

const AUTO_META_NAME: &str = "meta.json";
const MAX_PATH_BYTES: usize = 4096;
const READ_CHUNK: usize = 8192;
const MAX_METADATA_BYTES: usize = 1024 * 1024;
const SECONDARY_REAP_TIMEOUT: Duration = Duration::from_secs(2);

/// One of the stable numeric CLI workflows at the pinned revision.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum PyBertWorkflow {
    /// Legacy Python simulation. Upstream's default result path is preserved
    /// when results is None.
    Sim,
    /// Strict versioned native JSON input.
    SimNative,
    /// Legacy YAML projected into the native Rust subset.
    SimRust,
    /// Upstream validation/parity-gated auto selection.
    SimAuto,
    /// Python reference plus native candidate comparison.
    SimCompare,
}

impl PyBertWorkflow {
    pub const fn command_name(self) -> &'static str {
        match self {
            Self::Sim => "sim",
            Self::SimNative => "sim-native",
            Self::SimRust => "sim-rust",
            Self::SimAuto => "sim-auto",
            Self::SimCompare => "sim-compare",
        }
    }

    pub const fn requested_backend(self) -> &'static str {
        match self {
            Self::Sim => "python",
            Self::SimNative | Self::SimRust => "rust",
            Self::SimAuto => "auto",
            Self::SimCompare => "compare",
        }
    }

    pub const fn output_kind(self) -> OutputKind {
        match self {
            Self::Sim => OutputKind::OptionalResultFile,
            Self::SimNative | Self::SimRust | Self::SimAuto | Self::SimCompare => {
                OutputKind::RequiredDirectory
            }
        }
    }
}

/// Whether a workflow publishes a result file or a directory of artifacts.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum OutputKind {
    /// The result argument is optional, but the resolved result file is
    /// required after a successful child run.
    OptionalResultFile,
    /// The resolved output directory is required after a successful child run.
    RequiredDirectory,
}

/// Typed arguments preserving the upstream CLI's names and optionality.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum WorkflowInput {
    Sim {
        config_file: PathBuf,
        results: Option<PathBuf>,
    },
    SimNative {
        input_file: PathBuf,
        output_dir: PathBuf,
    },
    SimRust {
        config_file: PathBuf,
        output_dir: PathBuf,
        statistical_time_points: Option<u32>,
    },
    SimAuto {
        config_file: PathBuf,
        output_dir: PathBuf,
        statistical_time_points: Option<u32>,
    },
    SimCompare {
        config_file: PathBuf,
        output_dir: PathBuf,
        statistical_time_points: Option<u32>,
    },
}

impl WorkflowInput {
    pub const fn workflow(&self) -> PyBertWorkflow {
        match self {
            Self::Sim { .. } => PyBertWorkflow::Sim,
            Self::SimNative { .. } => PyBertWorkflow::SimNative,
            Self::SimRust { .. } => PyBertWorkflow::SimRust,
            Self::SimAuto { .. } => PyBertWorkflow::SimAuto,
            Self::SimCompare { .. } => PyBertWorkflow::SimCompare,
        }
    }

    fn paths(&self) -> impl Iterator<Item = &Path> {
        let paths: Vec<&Path> = match self {
            Self::Sim {
                config_file,
                results,
            } => std::iter::once(config_file.as_path())
                .chain(results.as_deref())
                .collect(),
            Self::SimNative {
                input_file,
                output_dir,
            } => vec![input_file.as_path(), output_dir.as_path()],
            Self::SimRust {
                config_file,
                output_dir,
                ..
            }
            | Self::SimAuto {
                config_file,
                output_dir,
                ..
            }
            | Self::SimCompare {
                config_file,
                output_dir,
                ..
            } => vec![config_file.as_path(), output_dir.as_path()],
        };
        paths.into_iter()
    }

    fn output_target(&self) -> Option<OutputTarget> {
        match self {
            Self::Sim {
                config_file,
                results,
            } => {
                Some(OutputTarget::File(results.clone().unwrap_or_else(|| {
                    config_file.with_extension("pybert_data")
                })))
            }
            Self::SimNative { output_dir, .. }
            | Self::SimRust { output_dir, .. }
            | Self::SimAuto { output_dir, .. }
            | Self::SimCompare { output_dir, .. } => {
                Some(OutputTarget::Directory(output_dir.clone()))
            }
        }
    }

    fn args(&self) -> Result<Vec<String>, AdapterError> {
        let mut args = vec![self.workflow().command_name().to_owned()];
        match self {
            Self::Sim {
                config_file,
                results,
            } => {
                args.push(path_arg(config_file)?);
                if let Some(results) = results {
                    args.push("--results".to_owned());
                    args.push(path_arg(results)?);
                }
            }
            Self::SimNative {
                input_file,
                output_dir,
            } => {
                args.push(path_arg(input_file)?);
                args.push("--output-dir".to_owned());
                args.push(path_arg(output_dir)?);
            }
            Self::SimRust {
                config_file,
                output_dir,
                statistical_time_points,
            }
            | Self::SimAuto {
                config_file,
                output_dir,
                statistical_time_points,
            }
            | Self::SimCompare {
                config_file,
                output_dir,
                statistical_time_points,
            } => {
                args.push(path_arg(config_file)?);
                args.push("--output-dir".to_owned());
                args.push(path_arg(output_dir)?);
                if let Some(value) = statistical_time_points {
                    args.push("--statistical-time-points".to_owned());
                    args.push(value.to_string());
                }
            }
        }
        Ok(args)
    }
}

fn path_arg(path: &Path) -> Result<String, AdapterError> {
    path.to_str()
        .map(str::to_owned)
        .ok_or(AdapterError::InvalidPathEncoding)
}

/// Bounds applied before and during one external invocation.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct ProcessLimits {
    pub max_request_bytes: usize,
    pub max_stdout_bytes: usize,
    pub max_stderr_bytes: usize,
    pub max_artifact_files: usize,
    pub max_artifact_directories: usize,
    pub max_artifact_bytes: u64,
    pub max_artifact_depth: usize,
    pub timeout: Duration,
    pub poll_interval: Duration,
    pub stream_drain_timeout: Duration,
}

impl Default for ProcessLimits {
    fn default() -> Self {
        Self {
            max_request_bytes: 64 * 1024,
            max_stdout_bytes: 1024 * 1024,
            max_stderr_bytes: 1024 * 1024,
            max_artifact_files: 4096,
            max_artifact_directories: 4096,
            max_artifact_bytes: 512 * 1024 * 1024,
            max_artifact_depth: 64,
            timeout: Duration::from_secs(300),
            poll_interval: Duration::from_millis(5),
            stream_drain_timeout: Duration::from_secs(1),
        }
    }
}

impl ProcessLimits {
    fn validate(self) -> Result<Self, AdapterError> {
        if self.max_request_bytes == 0
            || self.max_stdout_bytes == 0
            || self.max_stderr_bytes == 0
            || self.max_artifact_files == 0
            || self.max_artifact_directories == 0
            || self.max_artifact_bytes == 0
            || self.max_artifact_depth == 0
            || self.timeout.is_zero()
            || self.poll_interval.is_zero()
            || self.stream_drain_timeout.is_zero()
            || Instant::now().checked_add(self.timeout).is_none()
            || Instant::now()
                .checked_add(self.stream_drain_timeout)
                .is_none()
        {
            return Err(AdapterError::InvalidLimits);
        }
        Ok(self)
    }
}

/// A request to run one explicit upstream command.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct AdapterRequest {
    pub executable: PathBuf,
    /// Caller-owned directory used as the child process current directory.
    /// It must be an existing, canonicalizable directory without symlink or
    /// junction components.
    pub working_directory: PathBuf,
    pub input: WorkflowInput,
    pub limits: ProcessLimits,
    /// Existence requests cancellation. The adapter does not mutate it.
    pub cancel_file: Option<PathBuf>,
}

impl AdapterRequest {
    pub fn validate(&self) -> Result<(), AdapterError> {
        if self.executable.as_os_str().is_empty() || self.executable.is_dir() {
            return Err(AdapterError::InvalidExecutable);
        }
        validate_path(&self.executable)?;
        let working_directory = validate_working_directory(&self.working_directory)?;
        let limits = self.limits.validate()?;
        let args = self.input.args()?;
        let request_bytes = args
            .iter()
            .map(|arg| arg.len().saturating_add(1))
            .sum::<usize>();
        if request_bytes > limits.max_request_bytes {
            return Err(AdapterError::RequestTooLarge {
                actual: request_bytes,
                maximum: limits.max_request_bytes,
            });
        }
        for path in self.input.paths() {
            validate_path(path)?;
        }
        if let Some(path) = &self.cancel_file {
            validate_path(path)?;
        }
        validate_output_target_path(&self.input.output_target(), &working_directory)?;
        validate_statistical_time_points(&self.input)?;
        if self.input.workflow().output_kind() == OutputKind::RequiredDirectory
            && let Some(OutputTarget::Directory(path)) = self.input.output_target()
            && path.as_os_str().is_empty()
        {
            return Err(AdapterError::InvalidOutputPath);
        }
        Ok(())
    }
}

fn validate_path(path: &Path) -> Result<(), AdapterError> {
    let value = path.to_str().ok_or(AdapterError::InvalidPathEncoding)?;
    if path.as_os_str().is_empty() || value.len() > MAX_PATH_BYTES {
        return Err(AdapterError::InvalidPath);
    }
    if path
        .components()
        .any(|component| matches!(component, Component::ParentDir))
    {
        return Err(AdapterError::InvalidPath);
    }
    Ok(())
}

fn validate_statistical_time_points(input: &WorkflowInput) -> Result<(), AdapterError> {
    let value = match input {
        WorkflowInput::SimRust {
            statistical_time_points,
            ..
        }
        | WorkflowInput::SimAuto {
            statistical_time_points,
            ..
        }
        | WorkflowInput::SimCompare {
            statistical_time_points,
            ..
        } => *statistical_time_points,
        WorkflowInput::Sim { .. } | WorkflowInput::SimNative { .. } => None,
    };
    if let Some(actual) = value.filter(|value| !(32..=10_000).contains(value)) {
        return Err(AdapterError::InvalidStatisticalTimePoints { actual });
    }
    Ok(())
}

fn validate_working_directory(path: &Path) -> Result<PathBuf, AdapterError> {
    validate_path(path)?;
    for ancestor in path.ancestors() {
        let candidate = if ancestor.as_os_str().is_empty() {
            Path::new(".")
        } else {
            ancestor
        };
        match fs::symlink_metadata(candidate) {
            Ok(metadata) => {
                if metadata.file_type().is_symlink() || is_junction(&metadata) {
                    return Err(AdapterError::WorkingDirectorySymlink);
                }
                fs::canonicalize(candidate)
                    .map_err(|_| AdapterError::WorkingDirectoryCanonicalization)?;
            }
            Err(error) if error.kind() == io::ErrorKind::NotFound => continue,
            Err(_) => return Err(AdapterError::WorkingDirectoryCanonicalization),
        }
    }
    let metadata = match fs::symlink_metadata(path) {
        Ok(metadata) => metadata,
        Err(error) if error.kind() == io::ErrorKind::NotFound => {
            return Err(AdapterError::InvalidWorkingDirectory);
        }
        Err(_) => return Err(AdapterError::WorkingDirectoryCanonicalization),
    };
    if metadata.file_type().is_symlink() || is_junction(&metadata) {
        return Err(AdapterError::WorkingDirectorySymlink);
    }
    if !metadata.is_dir() {
        return Err(AdapterError::InvalidWorkingDirectory);
    }
    fs::canonicalize(path).map_err(|_| AdapterError::WorkingDirectoryCanonicalization)
}

fn resolve_path(path: &Path, working_directory: &Path) -> PathBuf {
    if path.is_absolute() {
        path.to_path_buf()
    } else {
        working_directory.join(path)
    }
}

fn resolve_output_target(
    target: Option<OutputTarget>,
    working_directory: &Path,
) -> Option<OutputTarget> {
    target.map(|target| match target {
        OutputTarget::File(path) => OutputTarget::File(resolve_path(&path, working_directory)),
        OutputTarget::Directory(path) => {
            OutputTarget::Directory(resolve_path(&path, working_directory))
        }
    })
}

fn validate_output_target_path(
    target: &Option<OutputTarget>,
    working_directory: &Path,
) -> Result<(), AdapterError> {
    let Some(target) = target else {
        return Ok(());
    };
    let path = match target {
        OutputTarget::File(path) | OutputTarget::Directory(path) => path,
    };
    if path.as_os_str().is_empty() {
        return Err(AdapterError::InvalidOutputPath);
    }
    let resolved = resolve_path(path, working_directory);
    validate_existing_ancestors(&resolved)?;
    match fs::symlink_metadata(&resolved) {
        Ok(_) => return Err(AdapterError::OutputTargetAlreadyExists),
        Err(error) if error.kind() == io::ErrorKind::NotFound => {}
        Err(_) => return Err(AdapterError::OutputPathCanonicalization),
    }
    Ok(())
}

fn validate_existing_ancestors(path: &Path) -> Result<(), AdapterError> {
    for ancestor in path.ancestors() {
        let candidate = if ancestor.as_os_str().is_empty() {
            Path::new(".")
        } else {
            ancestor
        };
        match fs::symlink_metadata(candidate) {
            Ok(metadata) => {
                if metadata.file_type().is_symlink() || is_junction(&metadata) {
                    return Err(AdapterError::OutputPathSymlink);
                }
                fs::canonicalize(candidate)
                    .map_err(|_| AdapterError::OutputPathCanonicalization)?;
            }
            Err(error) if error.kind() == io::ErrorKind::NotFound => continue,
            Err(_) => return Err(AdapterError::OutputPathCanonicalization),
        }
    }
    Ok(())
}

#[cfg(windows)]
fn is_junction(metadata: &fs::Metadata) -> bool {
    use std::os::windows::fs::MetadataExt;

    const FILE_ATTRIBUTE_REPARSE_POINT: u32 = 0x0400;
    metadata.file_attributes() & FILE_ATTRIBUTE_REPARSE_POINT != 0
}

#[cfg(not(windows))]
fn is_junction(_metadata: &fs::Metadata) -> bool {
    false
}

#[derive(Clone, Debug, Eq, PartialEq)]
enum OutputTarget {
    File(PathBuf),
    Directory(PathBuf),
}

/// Bounded child result. Streams are retained only up to their limits.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct AdapterResult {
    pub workflow: PyBertWorkflow,
    pub requested_backend: String,
    pub selected_backend: Option<String>,
    pub backend_selection: Option<BackendSelection>,
    pub exit: ExitSummary,
    pub stdout: CapturedStream,
    pub stderr: CapturedStream,
    pub artifacts: Vec<ArtifactRecord>,
    pub contract_source: SourceIdentity,
    pub runtime_identity: String,
    pub runtime_source_authenticated: bool,
}

impl AdapterResult {
    pub fn succeeded(&self) -> bool {
        self.exit.success && !self.stdout.truncated && !self.stderr.truncated
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct CapturedStream {
    pub bytes: Vec<u8>,
    pub truncated: bool,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ExitSummary {
    pub success: bool,
    pub code: Option<i32>,
    pub signal: Option<i32>,
    pub timed_out: bool,
    pub cancelled: bool,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ArtifactRecord {
    pub relative_path: String,
    pub bytes: u64,
    pub sha256: String,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SourceIdentity {
    pub repository: String,
    pub commit: String,
    pub tree: String,
    pub cli_path: String,
    pub cli_blob_sha1: String,
    pub cli_sha256: String,
}

/// Upstream sim-auto's actual decision record. The optional parity payload is
/// retained as opaque JSON because the adapter is not allowed to redefine its
/// numerical gate.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct BackendSelection {
    pub requested: Option<String>,
    pub selected: String,
    pub fallback_reason: Option<String>,
    pub parity_gate: Option<serde_json::Value>,
}

impl Default for SourceIdentity {
    fn default() -> Self {
        Self {
            repository: "pybert".to_owned(),
            commit: UPSTREAM_COMMIT.to_owned(),
            tree: UPSTREAM_TREE.to_owned(),
            cli_path: UPSTREAM_CLI_PATH.to_owned(),
            cli_blob_sha1: UPSTREAM_CLI_BLOB_SHA1.to_owned(),
            cli_sha256: UPSTREAM_CLI_SHA256.to_owned(),
        }
    }
}

/// Fail-closed adapter errors. Numerical failures remain child evidence.
#[derive(Debug)]
pub enum AdapterError {
    InvalidExecutable,
    InvalidPath,
    InvalidPathEncoding,
    InvalidWorkingDirectory,
    WorkingDirectorySymlink,
    WorkingDirectoryCanonicalization,
    InvalidOutputPath,
    OutputTargetAlreadyExists,
    OutputPathSymlink,
    OutputPathCanonicalization,
    InvalidLimits,
    InvalidStatisticalTimePoints { actual: u32 },
    RequestTooLarge { actual: usize, maximum: usize },
    Spawn(io::Error),
    ProcessIsolation(io::Error),
    ChildIo(io::Error),
    OutputLimitExceeded { stream: &'static str },
    StreamDrainTimedOut { stream: &'static str },
    TimedOut,
    Cancelled,
    MissingAutoSelection,
    ArtifactIo(io::Error),
    ArtifactLimitExceeded,
    RequiredArtifactMissing,
    ArtifactSymlink,
    ArtifactPathEscape,
    ArtifactMetadata,
    MetadataJson(serde_json::Error),
}

impl fmt::Display for AdapterError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::InvalidExecutable => write!(f, "executable must be a non-directory path"),
            Self::InvalidPath => write!(f, "path is empty, too long, or contains '..'"),
            Self::InvalidPathEncoding => {
                write!(f, "path cannot be represented without lossy conversion")
            }
            Self::InvalidWorkingDirectory => {
                write!(f, "working directory must be an existing directory")
            }
            Self::WorkingDirectorySymlink => {
                write!(
                    f,
                    "working directory or one of its ancestors is a symlink or junction"
                )
            }
            Self::WorkingDirectoryCanonicalization => {
                write!(
                    f,
                    "working directory canonical boundary could not be established"
                )
            }
            Self::InvalidOutputPath => write!(f, "output path is invalid"),
            Self::OutputTargetAlreadyExists => {
                write!(f, "output target must not exist before spawn")
            }
            Self::OutputPathSymlink => {
                write!(
                    f,
                    "output path or one of its ancestors is a symlink or junction"
                )
            }
            Self::OutputPathCanonicalization => {
                write!(f, "output path canonical boundary could not be established")
            }
            Self::InvalidLimits => write!(f, "all process limits must be non-zero"),
            Self::InvalidStatisticalTimePoints { actual } => {
                write!(f, "statistical_time_points {actual} is outside 32..=10000")
            }
            Self::RequestTooLarge { actual, maximum } => {
                write!(f, "request is {actual} bytes, maximum is {maximum}")
            }
            Self::Spawn(error) => write!(f, "could not spawn PyBERT: {error}"),
            Self::ProcessIsolation(error) => {
                write!(
                    f,
                    "could not establish fail-closed process isolation: {error}"
                )
            }
            Self::ChildIo(error) => write!(f, "PyBERT child I/O failed: {error}"),
            Self::OutputLimitExceeded { stream } => {
                write!(f, "{stream} exceeded its capture limit")
            }
            Self::StreamDrainTimedOut { stream } => {
                write!(f, "{stream} did not close before the drain deadline")
            }
            Self::TimedOut => write!(f, "PyBERT timed out"),
            Self::Cancelled => write!(f, "PyBERT was cancelled"),
            Self::MissingAutoSelection => write!(f, "sim-auto artifact omitted engine selection"),
            Self::ArtifactIo(error) => write!(f, "artifact inventory failed: {error}"),
            Self::ArtifactLimitExceeded => {
                write!(f, "artifact inventory exceeded configured bounds")
            }
            Self::RequiredArtifactMissing => {
                write!(f, "required output directory was not produced")
            }
            Self::ArtifactSymlink => write!(f, "symlinks are not accepted in PyBERT artifacts"),
            Self::ArtifactPathEscape => write!(f, "artifact path escaped its output root"),
            Self::ArtifactMetadata => write!(f, "artifact metadata was not a regular file"),
            Self::MetadataJson(error) => write!(f, "could not parse PyBERT metadata: {error}"),
        }
    }
}

impl Error for AdapterError {}

#[cfg(windows)]
type ManagedChild = Box<dyn ChildWrapper>;
#[cfg(not(windows))]
type ManagedChild = Child;

// This wrapper is installed inside JobObject. If job creation or assignment
// fails, dropping the partially wrapped suspended child kills it instead of
// allowing an uncontained process to resume.
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
            let _ = child.start_kill();
        }
    }
}

// Once the suspended child has been assigned, retain a Job-level RAII guard.
// Any later early return (including an unexpected polling I/O error) drops
// this wrapper and attempts to terminate every process still in the Job.
#[cfg(windows)]
#[derive(Debug)]
struct KillJobOnDropSetup;

#[cfg(windows)]
impl CommandWrapper for KillJobOnDropSetup {
    fn wrap_child(
        &mut self,
        child: Box<dyn ChildWrapper>,
        _core: &CommandWrap,
    ) -> io::Result<Box<dyn ChildWrapper>> {
        Ok(Box::new(KillJobOnDrop(Some(child))))
    }
}

#[cfg(windows)]
#[derive(Debug)]
struct KillJobOnDrop(Option<Box<dyn ChildWrapper>>);

#[cfg(windows)]
impl ChildWrapper for KillJobOnDrop {
    fn inner(&self) -> &dyn ChildWrapper {
        self.0.as_deref().expect("job child is present")
    }

    fn inner_mut(&mut self) -> &mut dyn ChildWrapper {
        self.0.as_deref_mut().expect("job child is present")
    }

    fn into_inner(mut self: Box<Self>) -> Box<dyn ChildWrapper> {
        self.0.take().expect("job child is present")
    }
}

#[cfg(windows)]
impl Drop for KillJobOnDrop {
    fn drop(&mut self) {
        if let Some(child) = self.0.as_deref_mut() {
            let _ = child.start_kill();
        }
    }
}

// JobObject's default try_wait waits for the whole job. The adapter instead
// observes the direct parent, then explicitly terminates the job before it
// drains inherited pipes. That closes the parent-exited descendant gap.
#[cfg(windows)]
#[derive(Debug)]
struct PreserveParentCompletionPoll;

#[cfg(windows)]
impl CommandWrapper for PreserveParentCompletionPoll {
    fn wrap_child(
        &mut self,
        child: Box<dyn ChildWrapper>,
        _core: &CommandWrap,
    ) -> io::Result<Box<dyn ChildWrapper>> {
        Ok(Box::new(ParentCompletionChild(child)))
    }
}

#[cfg(windows)]
#[derive(Debug)]
struct ParentCompletionChild(Box<dyn ChildWrapper>);

#[cfg(windows)]
impl ChildWrapper for ParentCompletionChild {
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
        .wrap(KillJobOnDropSetup)
        .wrap(PreserveParentCompletionPoll)
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

/// Run a pinned PyBERT workflow with explicit process and artifact bounds.
pub fn run(request: &AdapterRequest) -> Result<AdapterResult, AdapterError> {
    request.validate()?;
    let working_directory = validate_working_directory(&request.working_directory)?;
    let cancel_file = request
        .cancel_file
        .as_ref()
        .map(|path| resolve_path(path, &working_directory));
    if cancel_file.as_ref().is_some_and(|path| path.exists()) {
        return Err(AdapterError::Cancelled);
    }
    let workflow = request.input.workflow();
    let args = request.input.args()?;
    let target = resolve_output_target(request.input.output_target(), &working_directory);
    let deadline = Instant::now()
        .checked_add(request.limits.timeout)
        .ok_or(AdapterError::InvalidLimits)?;
    let _ = Instant::now()
        .checked_add(request.limits.stream_drain_timeout)
        .ok_or(AdapterError::InvalidLimits)?;
    let mut command = Command::new(&request.executable);
    command
        .args(&args)
        .current_dir(&working_directory)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    let mut child = spawn_managed(command).map_err(map_spawn_error)?;
    let stdout = match take_child_stdout(&mut child) {
        Some(stdout) => stdout,
        None => {
            let _ = kill_process_tree(&mut child);
            let _ = wait_child_after_termination(&mut child);
            return Err(AdapterError::ChildIo(io::Error::other("missing stdout")));
        }
    };
    let stderr = match take_child_stderr(&mut child) {
        Some(stderr) => stderr,
        None => {
            let _ = kill_process_tree(&mut child);
            let _ = wait_child_after_termination(&mut child);
            return Err(AdapterError::ChildIo(io::Error::other("missing stderr")));
        }
    };
    let (out_tx, out_rx) = mpsc::channel();
    let (err_tx, err_rx) = mpsc::channel();
    let max_stdout = request.limits.max_stdout_bytes;
    let max_stderr = request.limits.max_stderr_bytes;
    thread::spawn(move || {
        let _ = out_tx.send(read_bounded(stdout, max_stdout));
    });
    thread::spawn(move || {
        let _ = err_tx.send(read_bounded(stderr, max_stderr));
    });

    let mut timed_out = false;
    let mut cancelled = false;
    let mut child_killed = false;
    let mut output_limit = None;
    let mut stdout = None;
    let mut stderr = None;
    let status = loop {
        receive_capture(&out_rx, &mut stdout, &mut output_limit, "stdout");
        receive_capture(&err_rx, &mut stderr, &mut output_limit, "stderr");
        if output_limit.is_some() && !child_killed {
            kill_process_tree(&mut child)?;
            child_killed = true;
        }
        if !child_killed && cancel_file.as_ref().is_some_and(|path| path.exists()) {
            cancelled = true;
            kill_process_tree(&mut child)?;
            child_killed = true;
        }
        if !child_killed && Instant::now() >= deadline {
            timed_out = true;
            kill_process_tree(&mut child)?;
            child_killed = true;
        }
        if child_killed {
            break wait_child_after_termination(&mut child)?;
        }
        if let Some(status) = child.try_wait().map_err(AdapterError::ChildIo)? {
            break status;
        }
        thread::sleep(request.limits.poll_interval);
    };

    // A successful direct parent can leave descendants holding inherited
    // pipes. On Windows every invocation is isolated in a Job Object, so kill
    // that job before stream drain even when the direct parent already exited.
    #[cfg(windows)]
    if !child_killed {
        kill_process_tree(&mut child)?;
    }

    // ProcessLimits validated this addition before spawn; using infallible
    // addition here
    // keeps the post-spawn path non-fallible and leak-free.
    let drain_deadline = Instant::now() + request.limits.stream_drain_timeout;
    while stdout.is_none() || stderr.is_none() {
        receive_capture(&out_rx, &mut stdout, &mut output_limit, "stdout");
        receive_capture(&err_rx, &mut stderr, &mut output_limit, "stderr");
        if stdout.is_some() && stderr.is_some() {
            break;
        }
        if Instant::now() >= drain_deadline {
            let stream = if stdout.is_none() { "stdout" } else { "stderr" };
            let _ = kill_process_tree(&mut child);
            return Err(AdapterError::StreamDrainTimedOut { stream });
        }
        thread::sleep(request.limits.poll_interval);
    }
    let stdout = stdout.expect("stdout capture completed");
    let stderr = stderr.expect("stderr capture completed");
    if let Some(stream) = output_limit {
        return Err(AdapterError::OutputLimitExceeded { stream });
    }
    if timed_out {
        return Err(AdapterError::TimedOut);
    }
    if cancelled {
        return Err(AdapterError::Cancelled);
    }
    let target_path = target.as_ref().map(|target| match target {
        OutputTarget::File(path) | OutputTarget::Directory(path) => path.as_path(),
    });
    if let Some(target_path) = target_path {
        validate_existing_ancestors(target_path)?;
    }
    let artifacts = inventory_target(target_path, &request.limits, workflow, status.success())?;
    let backend_selection = if workflow == PyBertWorkflow::SimAuto && status.success() {
        let selection = selected_auto_backend(target.as_ref())?;
        if selection.is_none() {
            return Err(AdapterError::MissingAutoSelection);
        }
        selection
    } else {
        None
    };
    let selected_backend = backend_selection
        .as_ref()
        .map(|selection| selection.selected.clone());
    Ok(AdapterResult {
        workflow,
        requested_backend: workflow.requested_backend().to_owned(),
        selected_backend,
        backend_selection,
        exit: ExitSummary {
            success: status.success(),
            code: status.code(),
            signal: exit_signal(&status),
            timed_out,
            cancelled,
        },
        stdout,
        stderr,
        artifacts,
        contract_source: SourceIdentity::default(),
        runtime_identity: "caller_supplied_unverified".to_owned(),
        runtime_source_authenticated: false,
    })
}

fn receive_capture(
    receiver: &mpsc::Receiver<CapturedStream>,
    slot: &mut Option<CapturedStream>,
    output_limit: &mut Option<&'static str>,
    stream: &'static str,
) {
    if slot.is_none()
        && let Ok(capture) = receiver.try_recv()
    {
        if capture.truncated && output_limit.is_none() {
            *output_limit = Some(stream);
        }
        *slot = Some(capture);
    }
}

#[cfg(windows)]
fn map_spawn_error(error: io::Error) -> AdapterError {
    AdapterError::ProcessIsolation(error)
}

#[cfg(not(windows))]
fn map_spawn_error(error: io::Error) -> AdapterError {
    AdapterError::Spawn(error)
}

#[cfg(windows)]
fn kill_process_tree(child: &mut ManagedChild) -> Result<(), AdapterError> {
    child.start_kill().map_err(AdapterError::ProcessIsolation)
}

#[cfg(not(windows))]
fn kill_process_tree(child: &mut ManagedChild) -> Result<(), AdapterError> {
    match child.kill() {
        Ok(()) => Ok(()),
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(()),
        Err(error) => Err(AdapterError::ChildIo(error)),
    }
}

fn wait_child_after_termination(child: &mut ManagedChild) -> Result<ExitStatus, AdapterError> {
    let deadline = Instant::now() + SECONDARY_REAP_TIMEOUT;
    loop {
        match child.try_wait().map_err(AdapterError::ChildIo)? {
            Some(status) => return Ok(status),
            None if Instant::now() < deadline => {
                thread::sleep(Duration::from_millis(5));
            }
            None => {
                return Err(AdapterError::ChildIo(io::Error::new(
                    io::ErrorKind::TimedOut,
                    "terminated child did not exit before secondary deadline",
                )));
            }
        }
    }
}

fn read_bounded<R: Read>(mut reader: R, maximum: usize) -> CapturedStream {
    let mut bytes = Vec::new();
    let mut buffer = [0_u8; READ_CHUNK];
    let mut truncated = false;
    loop {
        match reader.read(&mut buffer) {
            Ok(0) => break,
            Ok(count) => {
                if bytes.len().saturating_add(count) > maximum {
                    let remaining = maximum.saturating_sub(bytes.len());
                    bytes.extend_from_slice(&buffer[..remaining]);
                    truncated = true;
                    break;
                }
                bytes.extend_from_slice(&buffer[..count]);
            }
            Err(_) => {
                truncated = true;
                break;
            }
        }
    }
    CapturedStream { bytes, truncated }
}

fn exit_signal(status: &ExitStatus) -> Option<i32> {
    #[cfg(unix)]
    {
        use std::os::unix::process::ExitStatusExt;
        status.signal()
    }
    #[cfg(not(unix))]
    {
        let _ = status;
        None
    }
}

fn inventory_target(
    target: Option<&Path>,
    limits: &ProcessLimits,
    workflow: PyBertWorkflow,
    require_output: bool,
) -> Result<Vec<ArtifactRecord>, AdapterError> {
    let Some(target) = target else {
        if !require_output {
            return Ok(Vec::new());
        }
        return Err(AdapterError::RequiredArtifactMissing);
    };
    let metadata = match fs::symlink_metadata(target) {
        Ok(metadata) => metadata,
        Err(error) if error.kind() == io::ErrorKind::NotFound => {
            if !require_output {
                return Ok(Vec::new());
            }
            return Err(AdapterError::RequiredArtifactMissing);
        }
        Err(error) => return Err(AdapterError::ArtifactIo(error)),
    };
    if metadata.file_type().is_symlink() || is_junction(&metadata) {
        return Err(AdapterError::ArtifactSymlink);
    }
    if workflow.output_kind() == OutputKind::OptionalResultFile {
        if !metadata.is_file() {
            return Err(AdapterError::RequiredArtifactMissing);
        }
        let root = target.parent().unwrap_or_else(|| Path::new("."));
        return Ok(vec![record_file(root, target, limits)?]);
    }
    if !metadata.is_dir() {
        return Err(AdapterError::RequiredArtifactMissing);
    }
    let mut records = Vec::new();
    let mut total = 0_u64;
    let mut directories = 1_usize;
    walk_directory(
        target,
        target,
        0,
        limits,
        &mut records,
        &mut total,
        &mut directories,
    )?;
    records.sort_by(|left, right| left.relative_path.cmp(&right.relative_path));
    validate_required_regular_artifacts(&records, workflow)?;
    Ok(records)
}

fn validate_required_regular_artifacts(
    records: &[ArtifactRecord],
    workflow: PyBertWorkflow,
) -> Result<(), AdapterError> {
    let required: &[&str] = match workflow {
        PyBertWorkflow::Sim => &[],
        PyBertWorkflow::SimNative
        | PyBertWorkflow::SimRust
        | PyBertWorkflow::SimAuto
        | PyBertWorkflow::SimCompare => &["meta.json", "arrays.npz"],
    };
    for name in required {
        if !records
            .iter()
            .any(|artifact| artifact.relative_path == *name)
        {
            return Err(AdapterError::RequiredArtifactMissing);
        }
    }
    Ok(())
}

fn walk_directory(
    root: &Path,
    current: &Path,
    depth: usize,
    limits: &ProcessLimits,
    records: &mut Vec<ArtifactRecord>,
    total: &mut u64,
    directories: &mut usize,
) -> Result<(), AdapterError> {
    if depth > limits.max_artifact_depth {
        return Err(AdapterError::ArtifactLimitExceeded);
    }
    for entry in fs::read_dir(current).map_err(AdapterError::ArtifactIo)? {
        let entry = entry.map_err(AdapterError::ArtifactIo)?;
        let path = entry.path();
        let metadata = fs::symlink_metadata(&path).map_err(AdapterError::ArtifactIo)?;
        if metadata.file_type().is_symlink() || is_junction(&metadata) {
            return Err(AdapterError::ArtifactSymlink);
        }
        if metadata.is_dir() {
            *directories = (*directories)
                .checked_add(1)
                .ok_or(AdapterError::ArtifactLimitExceeded)?;
            if *directories > limits.max_artifact_directories {
                return Err(AdapterError::ArtifactLimitExceeded);
            }
            walk_directory(
                root,
                &path,
                depth.saturating_add(1),
                limits,
                records,
                total,
                directories,
            )?;
            continue;
        }
        if !metadata.is_file() {
            return Err(AdapterError::ArtifactMetadata);
        }
        if records.len() >= limits.max_artifact_files {
            return Err(AdapterError::ArtifactLimitExceeded);
        }
        let record = record_file(root, &path, limits)?;
        *total = total
            .checked_add(record.bytes)
            .ok_or(AdapterError::ArtifactLimitExceeded)?;
        if *total > limits.max_artifact_bytes {
            return Err(AdapterError::ArtifactLimitExceeded);
        }
        records.push(record);
    }
    Ok(())
}

fn record_file(
    root: &Path,
    path: &Path,
    limits: &ProcessLimits,
) -> Result<ArtifactRecord, AdapterError> {
    let link_metadata = fs::symlink_metadata(path).map_err(AdapterError::ArtifactIo)?;
    if link_metadata.file_type().is_symlink() || is_junction(&link_metadata) {
        return Err(AdapterError::ArtifactSymlink);
    }
    if !link_metadata.is_file() {
        return Err(AdapterError::ArtifactMetadata);
    }
    let canonical_root = fs::canonicalize(root).map_err(AdapterError::ArtifactIo)?;
    let canonical_path = fs::canonicalize(path).map_err(AdapterError::ArtifactIo)?;
    if !canonical_path.starts_with(&canonical_root) {
        return Err(AdapterError::ArtifactPathEscape);
    }
    let relative = path
        .strip_prefix(root)
        .map_err(|_| AdapterError::ArtifactPathEscape)?;
    let relative_path = if relative == Path::new("") || relative == Path::new(".") {
        path.file_name()
            .and_then(|name| name.to_str())
            .ok_or(AdapterError::ArtifactPathEscape)?
            .to_owned()
    } else {
        normalize_relative(relative)?
    };
    let metadata = fs::metadata(&canonical_path).map_err(AdapterError::ArtifactIo)?;
    if metadata.len() > limits.max_artifact_bytes {
        return Err(AdapterError::ArtifactLimitExceeded);
    }
    let mut file = File::open(canonical_path).map_err(AdapterError::ArtifactIo)?;
    let mut hash = Sha256::new();
    let mut bytes = 0_u64;
    let mut buffer = [0_u8; READ_CHUNK];
    loop {
        let count = file.read(&mut buffer).map_err(AdapterError::ArtifactIo)?;
        if count == 0 {
            break;
        }
        bytes = bytes
            .checked_add(count as u64)
            .ok_or(AdapterError::ArtifactLimitExceeded)?;
        if bytes > limits.max_artifact_bytes {
            return Err(AdapterError::ArtifactLimitExceeded);
        }
        hash.update(&buffer[..count]);
    }
    Ok(ArtifactRecord {
        relative_path,
        bytes,
        sha256: format!("{:x}", hash.finalize()),
    })
}

fn normalize_relative(path: &Path) -> Result<String, AdapterError> {
    let mut pieces = Vec::new();
    for component in path.components() {
        match component {
            Component::Normal(value) => pieces.push(
                value
                    .to_str()
                    .ok_or(AdapterError::ArtifactPathEscape)?
                    .to_owned(),
            ),
            Component::CurDir => {}
            _ => return Err(AdapterError::ArtifactPathEscape),
        }
    }
    if pieces.is_empty() {
        return Err(AdapterError::ArtifactPathEscape);
    }
    Ok(pieces.join("/"))
}

fn selected_auto_backend(
    target: Option<&OutputTarget>,
) -> Result<Option<BackendSelection>, AdapterError> {
    let Some(OutputTarget::Directory(directory)) = target else {
        return Ok(None);
    };
    let metadata_path = directory.join(AUTO_META_NAME);
    if !metadata_path.exists() {
        return Ok(None);
    }
    let file = File::open(&metadata_path).map_err(AdapterError::ArtifactIo)?;
    let metadata = read_bounded(file, MAX_METADATA_BYTES);
    if metadata.truncated {
        return Err(AdapterError::ArtifactLimitExceeded);
    }
    let value: serde_json::Value =
        serde_json::from_slice(&metadata.bytes).map_err(AdapterError::MetadataJson)?;
    let selection = value
        .get("diagnostics")
        .and_then(|value| value.get("engine_selection"))
        .map(|value| BackendSelection {
            requested: value
                .get("requested")
                .and_then(serde_json::Value::as_str)
                .map(str::to_owned),
            selected: value
                .get("selected")
                .and_then(serde_json::Value::as_str)
                .unwrap_or_default()
                .to_owned(),
            fallback_reason: value.get("fallback_reason").and_then(|value| {
                if value.is_null() {
                    None
                } else {
                    value.as_str().map(str::to_owned)
                }
            }),
            parity_gate: value.get("parity_gate").cloned(),
        });
    Ok(selection.filter(|selection| !selection.selected.is_empty()))
}

/// Return a deterministic argument manifest without starting a child process.
pub fn command_manifest(request: &AdapterRequest) -> Result<Vec<String>, AdapterError> {
    request.validate()?;
    request.input.args()
}

/// Compact path-free description suitable for evidence files.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct WorkflowDescription {
    pub id: &'static str,
    pub command: &'static str,
    pub requested_backend: &'static str,
    pub output_kind: OutputKind,
}

pub const fn workflow_descriptions() -> [WorkflowDescription; 5] {
    [
        WorkflowDescription {
            id: "PB-01",
            command: "sim",
            requested_backend: "python",
            output_kind: OutputKind::OptionalResultFile,
        },
        WorkflowDescription {
            id: "PB-02",
            command: "sim-native",
            requested_backend: "rust",
            output_kind: OutputKind::RequiredDirectory,
        },
        WorkflowDescription {
            id: "PB-03",
            command: "sim-rust",
            requested_backend: "rust",
            output_kind: OutputKind::RequiredDirectory,
        },
        WorkflowDescription {
            id: "PB-04",
            command: "sim-auto",
            requested_backend: "auto",
            output_kind: OutputKind::RequiredDirectory,
        },
        WorkflowDescription {
            id: "PB-05",
            command: "sim-compare",
            requested_backend: "compare",
            output_kind: OutputKind::RequiredDirectory,
        },
    ]
}

#[cfg(test)]
mod tests {
    use super::*;

    fn request(input: WorkflowInput) -> AdapterRequest {
        AdapterRequest {
            executable: PathBuf::from("pybert"),
            working_directory: std::env::current_dir().expect("current directory"),
            input,
            limits: ProcessLimits::default(),
            cancel_file: None,
        }
    }

    #[test]
    fn command_manifest_preserves_upstream_cli_shapes() {
        let cases = [
            (
                WorkflowInput::Sim {
                    config_file: PathBuf::from("cfg.yaml"),
                    results: None,
                },
                vec!["sim", "cfg.yaml"],
            ),
            (
                WorkflowInput::SimNative {
                    input_file: PathBuf::from("input.json"),
                    output_dir: PathBuf::from("out"),
                },
                vec!["sim-native", "input.json", "--output-dir", "out"],
            ),
            (
                WorkflowInput::SimRust {
                    config_file: PathBuf::from("cfg.yaml"),
                    output_dir: PathBuf::from("out"),
                    statistical_time_points: Some(64),
                },
                vec![
                    "sim-rust",
                    "cfg.yaml",
                    "--output-dir",
                    "out",
                    "--statistical-time-points",
                    "64",
                ],
            ),
        ];
        for (input, expected) in cases {
            let actual = command_manifest(&request(input)).expect("manifest");
            assert_eq!(actual, expected);
        }
    }

    #[test]
    fn invalid_relative_parent_paths_fail_closed() {
        let input = WorkflowInput::SimNative {
            input_file: PathBuf::from("../input.json"),
            output_dir: PathBuf::from("out"),
        };
        assert!(matches!(
            command_manifest(&request(input)),
            Err(AdapterError::InvalidPath)
        ));
    }

    #[test]
    fn source_identity_is_pinned_without_local_paths() {
        let source = SourceIdentity::default();
        assert_eq!(source.commit, UPSTREAM_COMMIT);
        assert!(!source.repository.contains(':'));
        assert!(!source.cli_path.contains('\\'));
    }

    #[test]
    fn bounded_reader_marks_overflow_without_returning_extra_bytes() {
        let result = read_bounded(&b"0123456789"[..], 4);
        assert_eq!(result.bytes, b"0123");
        assert!(result.truncated);
    }

    #[test]
    fn workflow_table_covers_exactly_five_rows() {
        let descriptions = workflow_descriptions();
        assert_eq!(descriptions.len(), 5);
        assert_eq!(descriptions[4].id, "PB-05");
    }
}
