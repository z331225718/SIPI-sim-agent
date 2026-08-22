//! Process-external adapters for the six supported Agent-Spice CLI workflows.
//!
//! This crate deliberately does not port Agent-Spice algorithms.  It owns the
//! boundary around the pinned Python command: caller supplied arguments are
//! passed through unchanged, the backend is explicit where the upstream CLI
//! has a backend choice, and all process/output/artifact limits are enforced
//! outside the child process.

use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::ffi::{OsStr, OsString};
use std::fmt::{Display, Formatter};
use std::fs::{self, File, Metadata};
#[cfg(windows)]
use std::io;
use std::io::Read;
use std::path::{Path, PathBuf};
#[cfg(not(windows))]
use std::process::Child;
use std::process::{ChildStderr, ChildStdout, Command, ExitStatus, Stdio};
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc;
use std::thread;
use std::time::{Duration, Instant};

#[cfg(windows)]
use process_wrap::std::{ChildWrapper, CommandWrap, CommandWrapper, JobObject};

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

/// The only upstream source identity accepted by this adapter.
pub const UPSTREAM_REPOSITORY: &str = "agent-spice";
pub const UPSTREAM_COMMIT: &str = "2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5";
pub const UPSTREAM_MODULE: &str = "agent_spice.cli";

/// The six public workflows covered by the upstream-first migration slice.
#[derive(Clone, Copy, Debug, Eq, Ord, PartialEq, PartialOrd)]
pub enum CommandKind {
    FitSparam,
    FitSparamCascade,
    FitYparam,
    TuneYparamTran,
    RunHspice,
    RunRfm,
}

impl CommandKind {
    pub const ALL: [Self; 6] = [
        Self::FitSparam,
        Self::FitSparamCascade,
        Self::FitYparam,
        Self::TuneYparamTran,
        Self::RunHspice,
        Self::RunRfm,
    ];

    pub const fn cli_name(self) -> &'static str {
        match self {
            Self::FitSparam => "fit-sparam",
            Self::FitSparamCascade => "fit-sparam-cascade",
            Self::FitYparam => "fit-yparam",
            Self::TuneYparamTran => "tune-yparam-tran",
            Self::RunHspice => "run-hspice",
            Self::RunRfm => "run-rfm",
        }
    }

    pub const fn request_type(self) -> &'static str {
        match self {
            Self::FitSparam => "FitSparamRequest",
            Self::FitSparamCascade => "FitSparamCascadeRequest",
            Self::FitYparam => "FitYparamRequest",
            Self::TuneYparamTran => "TuneYparamTranRequest",
            Self::RunHspice => "RunHspiceRequest",
            Self::RunRfm => "RunRfmRequest",
        }
    }

    pub const fn requires_explicit_backend(self) -> bool {
        matches!(self, Self::RunHspice | Self::RunRfm)
    }
}

impl Display for CommandKind {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(self.cli_name())
    }
}

/// Backend names accepted by the pinned upstream CLI.
#[derive(Clone, Copy, Debug, Eq, Ord, PartialEq, PartialOrd)]
pub enum Backend {
    Native,
    Ngspice,
    Xyce,
    XyceXdm,
}

impl Backend {
    pub const fn cli_name(self) -> &'static str {
        match self {
            Self::Native => "native",
            Self::Ngspice => "ngspice",
            Self::Xyce => "xyce",
            Self::XyceXdm => "xyce-xdm",
        }
    }

    const fn accepted_by(self, command: CommandKind) -> bool {
        match command {
            CommandKind::RunHspice => true,
            CommandKind::RunRfm => matches!(self, Self::Native | Self::Ngspice),
            _ => false,
        }
    }
}

impl Display for Backend {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(self.cli_name())
    }
}

/// Hard limits enforced by the adapter rather than delegated to Agent-Spice.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct ProcessLimits {
    pub wall_time: Duration,
    pub reader_drain_time: Duration,
    pub stdout_bytes: usize,
    pub stderr_bytes: usize,
    pub artifact_bytes: u64,
    pub artifact_files: usize,
    pub artifact_directories: usize,
    pub artifact_max_depth: usize,
    pub artifact_path_bytes: usize,
    pub argv_bytes: usize,
    pub poll_interval: Duration,
}

impl Default for ProcessLimits {
    fn default() -> Self {
        Self {
            wall_time: Duration::from_secs(30 * 60),
            reader_drain_time: Duration::from_secs(2),
            stdout_bytes: 4 * 1024 * 1024,
            stderr_bytes: 4 * 1024 * 1024,
            artifact_bytes: 512 * 1024 * 1024,
            artifact_files: 16_384,
            artifact_directories: 4_096,
            artifact_max_depth: 64,
            artifact_path_bytes: 4_096,
            argv_bytes: 64 * 1024,
            poll_interval: Duration::from_millis(10),
        }
    }
}

/// Launch settings shared by all typed requests.
#[derive(Clone, Debug)]
pub struct ProcessOptions {
    /// Python executable (or an owner-approved launcher) used for the child.
    pub interpreter: PathBuf,
    pub working_directory: PathBuf,
    /// A caller-owned directory whose files are captured as output custody.
    pub artifact_root: PathBuf,
    pub limits: ProcessLimits,
    pub environment: Vec<(OsString, OsString)>,
    /// Production value is exactly `-m agent_spice.cli`.  Tests may replace it
    /// with a fake interpreter prefix without changing the command arguments.
    pub invocation_prefix: Vec<OsString>,
}

impl ProcessOptions {
    pub fn new(
        interpreter: impl Into<PathBuf>,
        working_directory: impl Into<PathBuf>,
        artifact_root: impl Into<PathBuf>,
    ) -> Self {
        Self {
            interpreter: interpreter.into(),
            working_directory: working_directory.into(),
            artifact_root: artifact_root.into(),
            limits: ProcessLimits::default(),
            environment: Vec::new(),
            invocation_prefix: vec![OsString::from("-m"), OsString::from(UPSTREAM_MODULE)],
        }
    }

    /// Test-only launcher hook.  The normal adapter must retain the default
    /// `-m agent_spice.cli` prefix.
    pub fn with_invocation_prefix(mut self, prefix: Vec<OsString>) -> Self {
        self.invocation_prefix = prefix;
        self
    }
}

/// Cooperative cancellation shared with the parent worker.
#[derive(Clone, Debug, Default)]
pub struct CancellationToken {
    cancelled: Arc<AtomicBool>,
}

impl CancellationToken {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn cancel(&self) {
        self.cancelled.store(true, Ordering::Release);
    }

    pub fn is_cancelled(&self) -> bool {
        self.cancelled.load(Ordering::Acquire)
    }
}

macro_rules! typed_request {
    ($name:ident, $kind:expr) => {
        #[derive(Clone, Debug)]
        pub struct $name {
            pub args: Vec<OsString>,
            pub options: ProcessOptions,
        }

        impl $name {
            pub fn new(args: Vec<OsString>, options: ProcessOptions) -> Self {
                Self { args, options }
            }

            pub const fn command_kind(&self) -> CommandKind {
                $kind
            }
        }
    };
}

typed_request!(FitSparamRequest, CommandKind::FitSparam);
typed_request!(FitSparamCascadeRequest, CommandKind::FitSparamCascade);
typed_request!(FitYparamRequest, CommandKind::FitYparam);
typed_request!(TuneYparamTranRequest, CommandKind::TuneYparamTran);

/// A run request records the backend parsed from the caller's exact argv.  No
/// backend is inserted when it is absent: construction fails instead.
#[derive(Clone, Debug)]
pub struct RunHspiceRequest {
    pub args: Vec<OsString>,
    pub options: ProcessOptions,
    pub backend: Backend,
}

// no_upstream_cli_default: the adapter rejects absent run backends instead of
// silently selecting Agent-Spice's native default.

impl RunHspiceRequest {
    pub fn new(args: Vec<OsString>, options: ProcessOptions) -> Result<Self, AdapterError> {
        let backend = explicit_backend(CommandKind::RunHspice, &args)?;
        Ok(Self {
            args,
            options,
            backend,
        })
    }

    pub const fn command_kind(&self) -> CommandKind {
        CommandKind::RunHspice
    }
}

#[derive(Clone, Debug)]
pub struct RunRfmRequest {
    pub args: Vec<OsString>,
    pub options: ProcessOptions,
    pub backend: Backend,
}

impl RunRfmRequest {
    pub fn new(args: Vec<OsString>, options: ProcessOptions) -> Result<Self, AdapterError> {
        let backend = explicit_backend(CommandKind::RunRfm, &args)?;
        Ok(Self {
            args,
            options,
            backend,
        })
    }

    pub const fn command_kind(&self) -> CommandKind {
        CommandKind::RunRfm
    }
}

/// All six typed request variants.  The enum makes it impossible to dispatch
/// an unlisted command through this adapter.
#[derive(Clone, Debug)]
pub enum Request {
    FitSparam(FitSparamRequest),
    FitSparamCascade(FitSparamCascadeRequest),
    FitYparam(FitYparamRequest),
    TuneYparamTran(TuneYparamTranRequest),
    RunHspice(RunHspiceRequest),
    RunRfm(RunRfmRequest),
}

impl Request {
    pub const fn command_kind(&self) -> CommandKind {
        match self {
            Self::FitSparam(request) => request.command_kind(),
            Self::FitSparamCascade(request) => request.command_kind(),
            Self::FitYparam(request) => request.command_kind(),
            Self::TuneYparamTran(request) => request.command_kind(),
            Self::RunHspice(request) => request.command_kind(),
            Self::RunRfm(request) => request.command_kind(),
        }
    }

    fn args(&self) -> &[OsString] {
        match self {
            Self::FitSparam(request) => &request.args,
            Self::FitSparamCascade(request) => &request.args,
            Self::FitYparam(request) => &request.args,
            Self::TuneYparamTran(request) => &request.args,
            Self::RunHspice(request) => &request.args,
            Self::RunRfm(request) => &request.args,
        }
    }

    fn options(&self) -> &ProcessOptions {
        match self {
            Self::FitSparam(request) => &request.options,
            Self::FitSparamCascade(request) => &request.options,
            Self::FitYparam(request) => &request.options,
            Self::TuneYparamTran(request) => &request.options,
            Self::RunHspice(request) => &request.options,
            Self::RunRfm(request) => &request.options,
        }
    }

    fn backend(&self) -> Option<Backend> {
        match self {
            Self::RunHspice(request) => Some(request.backend),
            Self::RunRfm(request) => Some(request.backend),
            _ => None,
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum OutputStream {
    Stdout,
    Stderr,
}

impl Display for OutputStream {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(match self {
            Self::Stdout => "stdout",
            Self::Stderr => "stderr",
        })
    }
}

/// Stable error classes exposed at the process boundary.
#[derive(Debug)]
pub enum AdapterError {
    InvalidArgument(String),
    BackendRequired(CommandKind),
    BackendUnsupported {
        command: CommandKind,
        backend: Backend,
    },
    ConflictingBackend(CommandKind),
    WorkingDirectoryUnavailable(PathBuf),
    ArtifactRootUnavailable(PathBuf),
    ArtifactSymlink(PathBuf),
    ArtifactLimitExceeded {
        files: usize,
        bytes: u64,
    },
    ArtifactDirectoryLimitExceeded {
        directories: usize,
        limit: usize,
    },
    ArtifactDepthLimitExceeded {
        depth: usize,
        limit: usize,
    },
    ArtifactPathLimitExceeded {
        bytes: usize,
        limit: usize,
    },
    ArtifactRead(PathBuf),
    NonUtf8Path(PathBuf),
    SpawnFailed(PathBuf),
    ProcessIsolationFailed(PathBuf),
    ProcessTerminationFailed(String),
    RequiredArtifactMissing {
        flag: String,
        path: PathBuf,
        expected: &'static str,
    },
    ArgvLimitExceeded {
        bytes: usize,
        limit: usize,
    },
    OutputLimitExceeded(OutputStream),
    ReaderDrainTimedOut(OutputStream),
    TimedOut,
    Cancelled,
    CaptureThreadFailed,
}

impl AdapterError {
    pub const fn code(&self) -> &'static str {
        match self {
            Self::InvalidArgument(_) => "invalid_argument",
            Self::BackendRequired(_) => "backend_required",
            Self::BackendUnsupported { .. } => "backend_unsupported",
            Self::ConflictingBackend(_) => "conflicting_backend",
            Self::WorkingDirectoryUnavailable(_) => "working_directory_unavailable",
            Self::ArtifactRootUnavailable(_) => "artifact_root_unavailable",
            Self::ArtifactSymlink(_) => "artifact_symlink",
            Self::ArtifactLimitExceeded { .. } => "artifact_limit_exceeded",
            Self::ArtifactDirectoryLimitExceeded { .. } => "artifact_directory_limit_exceeded",
            Self::ArtifactDepthLimitExceeded { .. } => "artifact_depth_limit_exceeded",
            Self::ArtifactPathLimitExceeded { .. } => "artifact_path_limit_exceeded",
            Self::ArtifactRead(_) => "artifact_read_failed",
            Self::NonUtf8Path(_) => "non_utf8_path",
            Self::SpawnFailed(_) => "spawn_failed",
            Self::ProcessIsolationFailed(_) => "process_isolation_failed",
            Self::ProcessTerminationFailed(_) => "process_termination_failed",
            Self::RequiredArtifactMissing { .. } => "required_artifact_missing",
            Self::ArgvLimitExceeded { .. } => "argv_limit_exceeded",
            Self::OutputLimitExceeded(_) => "output_limit_exceeded",
            Self::ReaderDrainTimedOut(_) => "reader_drain_timeout",
            Self::TimedOut => "timed_out",
            Self::Cancelled => "cancelled",
            Self::CaptureThreadFailed => "capture_thread_failed",
        }
    }
}

impl Display for AdapterError {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::InvalidArgument(detail) => write!(formatter, "{}: {detail}", self.code()),
            Self::BackendRequired(command) => write!(formatter, "{}: {command}", self.code()),
            Self::BackendUnsupported { command, backend } => {
                write!(
                    formatter,
                    "{}: {command} does not accept {backend}",
                    self.code()
                )
            }
            Self::ConflictingBackend(command) => write!(formatter, "{}: {command}", self.code()),
            Self::WorkingDirectoryUnavailable(path)
            | Self::ArtifactRootUnavailable(path)
            | Self::ArtifactSymlink(path)
            | Self::ArtifactRead(path)
            | Self::NonUtf8Path(path)
            | Self::SpawnFailed(path)
            | Self::ProcessIsolationFailed(path) => {
                write!(formatter, "{}: {}", self.code(), path.display())
            }
            Self::RequiredArtifactMissing {
                flag,
                path,
                expected,
            } => write!(
                formatter,
                "{}: flag={flag} expected={expected} path={}",
                self.code(),
                path.display()
            ),
            Self::ProcessTerminationFailed(detail) => {
                write!(formatter, "{}: {detail}", self.code())
            }
            Self::ArtifactLimitExceeded { files, bytes } => {
                write!(formatter, "{}: files={files} bytes={bytes}", self.code())
            }
            Self::ArtifactDirectoryLimitExceeded { directories, limit } => {
                write!(
                    formatter,
                    "{}: directories={directories} limit={limit}",
                    self.code()
                )
            }
            Self::ArtifactDepthLimitExceeded { depth, limit } => {
                write!(formatter, "{}: depth={depth} limit={limit}", self.code())
            }
            Self::ArtifactPathLimitExceeded { bytes, limit } => {
                write!(formatter, "{}: bytes={bytes} limit={limit}", self.code())
            }
            Self::ArgvLimitExceeded { bytes, limit } => {
                write!(formatter, "{}: bytes={bytes} limit={limit}", self.code())
            }
            Self::OutputLimitExceeded(stream) => write!(formatter, "{}: {stream}", self.code()),
            Self::ReaderDrainTimedOut(stream) => write!(formatter, "{}: {stream}", self.code()),
            Self::TimedOut | Self::Cancelled | Self::CaptureThreadFailed => {
                formatter.write_str(self.code())
            }
        }
    }
}

impl std::error::Error for AdapterError {}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ProcessStatus {
    Exited { code: Option<i32> },
}

impl ProcessStatus {
    pub const fn success(self) -> bool {
        match self {
            Self::Exited { code } => matches!(code, Some(0)),
        }
    }

    pub const fn exit_code(self) -> Option<i32> {
        match self {
            Self::Exited { code } => code,
        }
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ArtifactEntry {
    pub relative_path: String,
    pub byte_length: u64,
    pub sha256: String,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ArtifactManifest {
    pub root: String,
    pub entries: Vec<ArtifactEntry>,
    pub sha256: String,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Provenance {
    /// Pinned migration source used to define the command contract. The
    /// process boundary does not authenticate the installed Python package.
    pub upstream_repository: String,
    pub upstream_commit: String,
    pub upstream_module: String,
    pub contract_source: String,
    pub runtime_identity: String,
    pub runtime_source_authenticated: bool,
    pub command: CommandKind,
    pub backend: Option<Backend>,
    pub invocation_sha256: String,
    pub artifact_manifest_sha256: String,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ExecutionResult {
    pub command: CommandKind,
    pub backend: Option<Backend>,
    /// The exact launcher and arguments given to `std::process::Command`.
    pub invocation: Vec<String>,
    pub status: ProcessStatus,
    pub stdout: Vec<u8>,
    pub stderr: Vec<u8>,
    pub elapsed: Duration,
    pub artifacts: ArtifactManifest,
    pub provenance: Provenance,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum RequiredArtifactKind {
    File,
    Directory,
}

impl RequiredArtifactKind {
    const fn label(self) -> &'static str {
        match self {
            Self::File => "file",
            Self::Directory => "directory",
        }
    }

    fn matches(self, metadata: &Metadata) -> bool {
        match self {
            Self::File => metadata.is_file(),
            Self::Directory => metadata.is_dir(),
        }
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct RequiredArtifactTarget {
    flag: &'static str,
    path: PathBuf,
    kind: RequiredArtifactKind,
}

impl RequiredArtifactTarget {
    fn missing_error(&self) -> AdapterError {
        AdapterError::RequiredArtifactMissing {
            flag: self.flag.to_owned(),
            path: self.path.clone(),
            expected: self.kind.label(),
        }
    }
}

/// Stateless adapter.  All policy is carried by the typed request and its
/// `ProcessOptions`; keeping this type stateless prevents hidden defaults.
#[derive(Clone, Copy, Debug, Default)]
pub struct AgentSpiceAdapter;

impl AgentSpiceAdapter {
    pub const fn new() -> Self {
        Self
    }

    pub fn execute(
        &self,
        request: Request,
        cancellation: &CancellationToken,
    ) -> Result<ExecutionResult, AdapterError> {
        validate_request(&request)?;
        let kind = request.command_kind();
        let options = request.options();
        let (working_directory, artifact_root) = validate_options(options)?;
        let required_artifacts =
            validate_output_admission(&request, &working_directory, &artifact_root)?;

        // The pre-run snapshot makes the custody boundary explicit even when
        // the child exits non-zero.  It also applies the same byte/file cap to
        // old files that the child is allowed to leave in the output root.
        let _before = capture_artifacts(&artifact_root, options.limits)?;
        let mut command = Command::new(&options.interpreter);
        command
            .args(&options.invocation_prefix)
            .arg(kind.cli_name())
            .args(request.args())
            .current_dir(&working_directory)
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());
        for (key, value) in &options.environment {
            command.env(key, value);
        }

        let invocation = invocation_display(
            &options.interpreter,
            &options.invocation_prefix,
            kind,
            request.args(),
        )?;
        let argv_bytes = invocation
            .iter()
            .map(|argument| argument.len().saturating_add(1))
            .sum::<usize>();
        if argv_bytes > options.limits.argv_bytes {
            return Err(AdapterError::ArgvLimitExceeded {
                bytes: argv_bytes,
                limit: options.limits.argv_bytes,
            });
        }
        let started = Instant::now();
        let mut child = spawn_managed_process(command, &options.interpreter)?;
        let stdout_exceeded = Arc::new(AtomicBool::new(false));
        let stderr_exceeded = Arc::new(AtomicBool::new(false));
        let stdout_pipe = match take_child_stdout(&mut child) {
            Some(pipe) => pipe,
            None => {
                return Err(terminate_with_reason(
                    &mut child,
                    AdapterError::CaptureThreadFailed,
                ));
            }
        };
        let stdout = spawn_capture(
            stdout_pipe,
            options.limits.stdout_bytes,
            Arc::clone(&stdout_exceeded),
        );
        let stderr_pipe = match take_child_stderr(&mut child) {
            Some(pipe) => pipe,
            None => {
                let error = terminate_with_reason(&mut child, AdapterError::CaptureThreadFailed);
                let _ = receive_capture(
                    &stdout,
                    Instant::now() + options.limits.reader_drain_time,
                    OutputStream::Stdout,
                );
                return Err(error);
            }
        };
        let stderr = spawn_capture(
            stderr_pipe,
            options.limits.stderr_bytes,
            Arc::clone(&stderr_exceeded),
        );

        let termination = match wait_for_child(
            &mut child,
            cancellation,
            &stdout_exceeded,
            &stderr_exceeded,
            options.limits,
        ) {
            Ok(termination) => termination,
            Err(error) => {
                let deadline = Instant::now() + options.limits.reader_drain_time;
                let _ = receive_capture(&stdout, deadline, OutputStream::Stdout);
                let _ = receive_capture(&stderr, deadline, OutputStream::Stderr);
                return Err(error);
            }
        };
        finish_process_scope(&mut child)?;
        let deadline = Instant::now() + options.limits.reader_drain_time;
        let stdout = match receive_capture(&stdout, deadline, OutputStream::Stdout) {
            Ok(output) => output,
            Err(error) => {
                let error = terminate_with_reason(&mut child, error);
                let _ = receive_capture(&stderr, deadline, OutputStream::Stderr);
                return Err(error);
            }
        };
        let stderr = match receive_capture(&stderr, deadline, OutputStream::Stderr) {
            Ok(output) => output,
            Err(error) => {
                return Err(terminate_with_reason(&mut child, error));
            }
        };
        if stdout.read_failed || stderr.read_failed {
            return Err(terminate_with_reason(
                &mut child,
                AdapterError::CaptureThreadFailed,
            ));
        }
        if stdout.exceeded {
            return Err(terminate_with_reason(
                &mut child,
                AdapterError::OutputLimitExceeded(OutputStream::Stdout),
            ));
        }
        if stderr.exceeded {
            return Err(terminate_with_reason(
                &mut child,
                AdapterError::OutputLimitExceeded(OutputStream::Stderr),
            ));
        }
        let status = match termination {
            Termination::Exited(status) => ProcessStatus::Exited {
                code: status.code(),
            },
        };
        if status.success()
            && let Err(error) = validate_required_artifacts(&required_artifacts, &artifact_root)
        {
            return Err(terminate_with_reason(&mut child, error));
        }
        let artifacts = match capture_artifacts(&artifact_root, options.limits) {
            Ok(artifacts) => artifacts,
            Err(error) => return Err(terminate_with_reason(&mut child, error)),
        };
        let artifact_manifest = build_manifest(&artifact_root, artifacts)?;
        let invocation_sha256 = hash_lines(&invocation);
        let provenance = Provenance {
            upstream_repository: UPSTREAM_REPOSITORY.to_owned(),
            upstream_commit: UPSTREAM_COMMIT.to_owned(),
            upstream_module: UPSTREAM_MODULE.to_owned(),
            contract_source: format!("{UPSTREAM_REPOSITORY}@{UPSTREAM_COMMIT}"),
            runtime_identity: "caller_supplied_unverified".to_owned(),
            runtime_source_authenticated: false,
            command: kind,
            backend: request.backend(),
            invocation_sha256,
            artifact_manifest_sha256: artifact_manifest.sha256.clone(),
        };
        Ok(ExecutionResult {
            command: kind,
            backend: request.backend(),
            invocation,
            status,
            stdout: stdout.bytes,
            stderr: stderr.bytes,
            elapsed: started.elapsed(),
            artifacts: artifact_manifest,
            provenance,
        })
    }
}

#[cfg(windows)]
fn spawn_managed_process(
    command: Command,
    interpreter: &Path,
) -> Result<ManagedChild, AdapterError> {
    let mut command = CommandWrap::from(command);
    command
        .wrap(FailClosedJobSetup)
        .wrap(JobObject)
        .wrap(PreserveJobCompletionPoll);
    command
        .spawn()
        .map_err(|_| AdapterError::ProcessIsolationFailed(interpreter.to_path_buf()))
}

#[cfg(not(windows))]
fn spawn_managed_process(
    mut command: Command,
    interpreter: &Path,
) -> Result<ManagedChild, AdapterError> {
    command
        .spawn()
        .map_err(|_| AdapterError::SpawnFailed(interpreter.to_path_buf()))
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

fn validate_request(request: &Request) -> Result<(), AdapterError> {
    for argument in request.args() {
        let text = argument_text(argument, "argument")?;
        if text.contains('\0') {
            return Err(AdapterError::InvalidArgument(
                "argument contains NUL".to_owned(),
            ));
        }
    }
    if request.command_kind().requires_explicit_backend() {
        let parsed = explicit_backend(request.command_kind(), request.args())?;
        if request.backend() != Some(parsed) {
            return Err(AdapterError::ConflictingBackend(request.command_kind()));
        }
    }
    Ok(())
}

fn validate_options(options: &ProcessOptions) -> Result<(PathBuf, PathBuf), AdapterError> {
    if options.invocation_prefix.is_empty() {
        return Err(AdapterError::InvalidArgument(
            "invocation prefix is empty".to_owned(),
        ));
    }
    if options.limits.wall_time.is_zero() {
        return Err(AdapterError::InvalidArgument(
            "wall time must be positive".to_owned(),
        ));
    }
    if options.limits.poll_interval.is_zero() {
        return Err(AdapterError::InvalidArgument(
            "poll interval must be positive".to_owned(),
        ));
    }
    if options.limits.reader_drain_time.is_zero() {
        return Err(AdapterError::InvalidArgument(
            "reader drain time must be positive".to_owned(),
        ));
    }
    if options.limits.artifact_directories == 0 {
        return Err(AdapterError::InvalidArgument(
            "artifact directory limit must be positive".to_owned(),
        ));
    }
    if options.limits.artifact_path_bytes == 0 {
        return Err(AdapterError::InvalidArgument(
            "artifact path limit must be positive".to_owned(),
        ));
    }
    if options.limits.argv_bytes == 0 {
        return Err(AdapterError::InvalidArgument(
            "argv limit must be positive".to_owned(),
        ));
    }
    validate_os_string(options.interpreter.as_os_str(), "interpreter")?;
    validate_os_string(options.working_directory.as_os_str(), "working directory")?;
    validate_os_string(options.artifact_root.as_os_str(), "artifact root")?;
    for prefix in &options.invocation_prefix {
        validate_os_string(prefix, "invocation prefix")?;
    }
    for (key, value) in &options.environment {
        validate_os_string(key, "environment key")?;
        validate_os_string(value, "environment value")?;
    }
    let work_metadata = fs::metadata(&options.working_directory).map_err(|_| {
        AdapterError::WorkingDirectoryUnavailable(options.working_directory.clone())
    })?;
    if !work_metadata.is_dir() {
        return Err(AdapterError::WorkingDirectoryUnavailable(
            options.working_directory.clone(),
        ));
    }
    let root_metadata = fs::metadata(&options.artifact_root)
        .map_err(|_| AdapterError::ArtifactRootUnavailable(options.artifact_root.clone()))?;
    if !root_metadata.is_dir() {
        return Err(AdapterError::ArtifactRootUnavailable(
            options.artifact_root.clone(),
        ));
    }
    let working_directory = fs::canonicalize(&options.working_directory).map_err(|_| {
        AdapterError::WorkingDirectoryUnavailable(options.working_directory.clone())
    })?;
    let artifact_root = fs::canonicalize(&options.artifact_root)
        .map_err(|_| AdapterError::ArtifactRootUnavailable(options.artifact_root.clone()))?;
    Ok((working_directory, artifact_root))
}

fn argument_text(value: &OsStr, label: &str) -> Result<String, AdapterError> {
    value
        .to_str()
        .map(ToOwned::to_owned)
        .ok_or_else(|| AdapterError::InvalidArgument(format!("{label} is not valid UTF-8")))
}

fn validate_os_string(value: &OsStr, label: &str) -> Result<(), AdapterError> {
    let text = argument_text(value, label)?;
    if text.contains('\0') {
        return Err(AdapterError::InvalidArgument(format!(
            "{label} contains NUL"
        )));
    }
    Ok(())
}

fn validate_output_admission(
    request: &Request,
    working_directory: &Path,
    artifact_root: &Path,
) -> Result<Vec<RequiredArtifactTarget>, AdapterError> {
    let (required, optional): (&[(&str, RequiredArtifactKind)], &[&str]) =
        match request.command_kind() {
            CommandKind::FitSparam => (
                &[("--output", RequiredArtifactKind::File)],
                &[
                    "--report",
                    "--html-report",
                    "--fitted-touchstone",
                    "--rfm",
                    "--rfm-wrapper",
                    "--log",
                ],
            ),
            CommandKind::FitSparamCascade => (
                &[("--output-root", RequiredArtifactKind::Directory)],
                &["--report"],
            ),
            CommandKind::FitYparam => (
                &[("--output", RequiredArtifactKind::File)],
                &[
                    "--derived-s-touchstone",
                    "--report",
                    "--html-report",
                    "--log",
                    "--exact-s-rfm",
                    "--exact-s-touchstone",
                    "--exact-s-rfm-wrapper",
                ],
            ),
            CommandKind::TuneYparamTran => (
                &[
                    ("--output-rfm", RequiredArtifactKind::File),
                    ("--work-dir", RequiredArtifactKind::Directory),
                ],
                &["--report"],
            ),
            CommandKind::RunHspice | CommandKind::RunRfm => {
                (&[("--output-root", RequiredArtifactKind::Directory)], &[])
            }
        };
    let mut keys = required.iter().map(|(key, _)| *key).collect::<Vec<_>>();
    keys.extend_from_slice(optional);
    let mut found = BTreeMap::<String, PathBuf>::new();
    let args = request.args();
    let mut index = 0;
    while index < args.len() {
        let argument = argument_text(&args[index], "argument")?;
        let (key, inline_value) = match argument.split_once('=') {
            Some((key, value)) => (key, Some(value.to_owned())),
            None => (argument.as_str(), None),
        };
        if !keys.contains(&key) {
            index += 1;
            continue;
        }
        let value = match inline_value {
            Some(value) => value,
            None => {
                index += 1;
                if index >= args.len() {
                    return Err(AdapterError::InvalidArgument(format!(
                        "{key} requires an output path"
                    )));
                }
                argument_text(&args[index], key)?
            }
        };
        if value.is_empty() {
            return Err(AdapterError::InvalidArgument(format!(
                "{key} output path is empty"
            )));
        }
        let admitted_path = validate_output_path(key, &value, working_directory, artifact_root)?;
        if found.insert(key.to_owned(), admitted_path).is_some() {
            return Err(AdapterError::InvalidArgument(format!(
                "{key} was provided more than once"
            )));
        }
        index += 1;
    }
    required
        .iter()
        .map(|(flag, kind)| {
            let path = found.get(*flag).cloned().ok_or_else(|| {
                AdapterError::InvalidArgument(format!(
                    "{flag} must be explicit and inside artifact root"
                ))
            })?;
            Ok(RequiredArtifactTarget {
                flag,
                path,
                kind: *kind,
            })
        })
        .collect()
}

fn validate_output_path(
    key: &str,
    value: &str,
    working_directory: &Path,
    artifact_root: &Path,
) -> Result<PathBuf, AdapterError> {
    let raw = Path::new(value);
    let resolved = if raw.is_absolute() {
        raw.to_path_buf()
    } else {
        working_directory.join(raw)
    };
    let parent = resolved
        .parent()
        .ok_or_else(|| AdapterError::InvalidArgument(format!("{key} has no usable parent")))?;
    let canonical_parent = fs::canonicalize(parent).map_err(|_| {
        AdapterError::InvalidArgument(format!(
            "{key} parent must already exist inside artifact root"
        ))
    })?;
    if !canonical_parent.starts_with(artifact_root) {
        return Err(AdapterError::InvalidArgument(format!(
            "{key} resolves outside artifact root"
        )));
    }
    match fs::symlink_metadata(&resolved) {
        Ok(metadata)
            if metadata.file_type().is_symlink() || is_windows_reparse_point(&metadata) =>
        {
            // Check dangling links too: `Path::exists` is false for a
            // dangling link, but a child would still follow it when creating
            // the output and could write outside the custody root.
            return Err(AdapterError::InvalidArgument(format!(
                "{key} output path must not be a symlink"
            )));
        }
        Ok(_) => {
            return Err(AdapterError::InvalidArgument(format!(
                "{key} output target must not already exist"
            )));
        }
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
        Err(_) => {
            return Err(AdapterError::InvalidArgument(format!(
                "{key} cannot be inspected"
            )));
        }
    }
    Ok(resolved)
}

fn validate_required_artifacts(
    targets: &[RequiredArtifactTarget],
    artifact_root: &Path,
) -> Result<(), AdapterError> {
    for target in targets {
        let metadata = fs::symlink_metadata(&target.path).map_err(|_| target.missing_error())?;
        if metadata.file_type().is_symlink()
            || is_windows_reparse_point(&metadata)
            || !target.kind.matches(&metadata)
        {
            return Err(target.missing_error());
        }
        let canonical = fs::canonicalize(&target.path).map_err(|_| target.missing_error())?;
        if !canonical.starts_with(artifact_root) {
            return Err(target.missing_error());
        }
    }
    Ok(())
}

fn explicit_backend(command: CommandKind, args: &[OsString]) -> Result<Backend, AdapterError> {
    let mut found = None;
    let mut index = 0;
    while index < args.len() {
        let text = argument_text(&args[index], "backend argument")?;
        let value = if text == "--backend" {
            index += 1;
            if index >= args.len() {
                return Err(AdapterError::InvalidArgument(
                    "--backend requires a value".to_owned(),
                ));
            }
            argument_text(&args[index], "backend value")?
        } else if let Some(value) = text.strip_prefix("--backend=") {
            value.to_owned()
        } else {
            index += 1;
            continue;
        };
        let backend = match value.as_str() {
            "native" => Backend::Native,
            "ngspice" => Backend::Ngspice,
            "xyce" => Backend::Xyce,
            "xyce-xdm" => Backend::XyceXdm,
            _ => {
                return Err(AdapterError::InvalidArgument(format!(
                    "unknown backend {value}"
                )));
            }
        };
        if found.replace(backend).is_some() {
            return Err(AdapterError::ConflictingBackend(command));
        }
        index += 1;
    }
    let backend = found.ok_or(AdapterError::BackendRequired(command))?;
    if !backend.accepted_by(command) {
        return Err(AdapterError::BackendUnsupported { command, backend });
    }
    Ok(backend)
}

fn invocation_display(
    interpreter: &Path,
    prefix: &[OsString],
    kind: CommandKind,
    args: &[OsString],
) -> Result<Vec<String>, AdapterError> {
    std::iter::once(interpreter.as_os_str())
        .chain(prefix.iter().map(OsString::as_os_str))
        .chain(std::iter::once(OsStr::new(kind.cli_name())))
        .chain(args.iter().map(OsString::as_os_str))
        .map(|value| argument_text(value, "invocation argument"))
        .collect()
}

struct CapturedOutput {
    bytes: Vec<u8>,
    exceeded: bool,
    read_failed: bool,
}

struct CaptureHandle {
    receiver: mpsc::Receiver<CapturedOutput>,
}

fn spawn_capture<R: Read + Send + 'static>(
    mut reader: R,
    limit: usize,
    exceeded: Arc<AtomicBool>,
) -> CaptureHandle {
    let (sender, receiver) = mpsc::channel();
    let _reader_thread = thread::spawn(move || {
        let mut output = || {
            let mut bytes = Vec::with_capacity(limit.min(8192));
            let mut buffer = [0_u8; 8192];
            loop {
                match reader.read(&mut buffer) {
                    Ok(0) => {
                        return CapturedOutput {
                            bytes,
                            exceeded: false,
                            read_failed: false,
                        };
                    }
                    Ok(read) => {
                        if bytes.len().saturating_add(read) > limit {
                            let remaining = limit.saturating_sub(bytes.len());
                            bytes.extend_from_slice(&buffer[..remaining]);
                            exceeded.store(true, Ordering::Release);
                            return CapturedOutput {
                                bytes,
                                exceeded: true,
                                read_failed: false,
                            };
                        }
                        bytes.extend_from_slice(&buffer[..read]);
                    }
                    Err(_) => {
                        return CapturedOutput {
                            bytes,
                            exceeded: false,
                            read_failed: true,
                        };
                    }
                }
            }
        };
        let _ = sender.send(output());
    });
    CaptureHandle { receiver }
}

fn receive_capture(
    handle: &CaptureHandle,
    deadline: Instant,
    stream: OutputStream,
) -> Result<CapturedOutput, AdapterError> {
    let remaining = deadline.saturating_duration_since(Instant::now());
    handle
        .receiver
        .recv_timeout(remaining)
        .map_err(|_| AdapterError::ReaderDrainTimedOut(stream))
}

enum Termination {
    Exited(ExitStatus),
}

fn wait_for_child(
    child: &mut ManagedChild,
    cancellation: &CancellationToken,
    stdout_exceeded: &AtomicBool,
    stderr_exceeded: &AtomicBool,
    limits: ProcessLimits,
) -> Result<Termination, AdapterError> {
    let started = Instant::now();
    loop {
        if stdout_exceeded.load(Ordering::Acquire) || stderr_exceeded.load(Ordering::Acquire) {
            let error =
                AdapterError::OutputLimitExceeded(if stdout_exceeded.load(Ordering::Acquire) {
                    OutputStream::Stdout
                } else {
                    OutputStream::Stderr
                });
            return Err(terminate_with_reason(child, error));
        }
        if cancellation.is_cancelled() {
            return Err(terminate_with_reason(child, AdapterError::Cancelled));
        }
        if started.elapsed() >= limits.wall_time {
            return Err(terminate_with_reason(child, AdapterError::TimedOut));
        }
        match child.try_wait() {
            Ok(Some(status)) => return Ok(Termination::Exited(status)),
            Ok(None) => thread::sleep(limits.poll_interval),
            Err(_) => {
                return Err(terminate_with_reason(
                    child,
                    AdapterError::CaptureThreadFailed,
                ));
            }
        }
    }
}

fn terminate_with_reason(child: &mut ManagedChild, reason: AdapterError) -> AdapterError {
    terminate_process_tree(child).err().unwrap_or(reason)
}

#[cfg(windows)]
fn finish_process_scope(child: &mut ManagedChild) -> Result<(), AdapterError> {
    terminate_process_tree(child)
}

#[cfg(not(windows))]
fn finish_process_scope(_child: &mut ManagedChild) -> Result<(), AdapterError> {
    Ok(())
}

fn terminate_process_tree(child: &mut ManagedChild) -> Result<(), AdapterError> {
    #[cfg(windows)]
    child.start_kill().map_err(|error| {
        AdapterError::ProcessTerminationFailed(format!(
            "cannot terminate Windows Job Object: {error}"
        ))
    })?;
    #[cfg(not(windows))]
    child.kill().map_err(|error| {
        AdapterError::ProcessTerminationFailed(format!("cannot terminate child: {error}"))
    })?;
    reap_child_until(child, Instant::now() + Duration::from_secs(1));
    Ok(())
}

fn reap_child_until(child: &mut ManagedChild, deadline: Instant) {
    loop {
        match child.try_wait() {
            Ok(Some(_)) | Err(_) => return,
            Ok(None) => {
                let remaining = deadline.saturating_duration_since(Instant::now());
                if remaining.is_zero() {
                    return;
                }
                thread::sleep(std::cmp::min(remaining, Duration::from_millis(5)));
            }
        }
    }
}

fn capture_artifacts(
    root: &Path,
    limits: ProcessLimits,
) -> Result<BTreeMap<String, ArtifactEntry>, AdapterError> {
    let metadata = fs::symlink_metadata(root)
        .map_err(|_| AdapterError::ArtifactRootUnavailable(root.to_path_buf()))?;
    if metadata.file_type().is_symlink()
        || is_windows_reparse_point(&metadata)
        || !metadata.is_dir()
    {
        return Err(AdapterError::ArtifactRootUnavailable(root.to_path_buf()));
    }
    let mut entries = BTreeMap::new();
    let mut bytes = 0_u64;
    let mut directories = 1_usize;
    walk_artifacts(
        root,
        root,
        0,
        limits,
        &mut entries,
        &mut bytes,
        &mut directories,
    )?;
    Ok(entries)
}

fn walk_artifacts(
    root: &Path,
    directory: &Path,
    depth: usize,
    limits: ProcessLimits,
    entries: &mut BTreeMap<String, ArtifactEntry>,
    total_bytes: &mut u64,
    directories: &mut usize,
) -> Result<(), AdapterError> {
    let read_dir =
        fs::read_dir(directory).map_err(|_| AdapterError::ArtifactRead(directory.to_path_buf()))?;
    for entry in read_dir {
        let entry = entry.map_err(|_| AdapterError::ArtifactRead(directory.to_path_buf()))?;
        let path = entry.path();
        let metadata =
            fs::symlink_metadata(&path).map_err(|_| AdapterError::ArtifactRead(path.clone()))?;
        if metadata.file_type().is_symlink() || is_windows_reparse_point(&metadata) {
            return Err(AdapterError::ArtifactSymlink(path));
        }
        let relative = relative_artifact_path(root, &path, limits.artifact_path_bytes)?;
        if metadata.is_dir() {
            if depth >= limits.artifact_max_depth {
                return Err(AdapterError::ArtifactDepthLimitExceeded {
                    depth: depth.saturating_add(1),
                    limit: limits.artifact_max_depth,
                });
            }
            if *directories >= limits.artifact_directories {
                return Err(AdapterError::ArtifactDirectoryLimitExceeded {
                    directories: (*directories).saturating_add(1),
                    limit: limits.artifact_directories,
                });
            }
            *directories = directories.saturating_add(1);
            walk_artifacts(
                root,
                &path,
                depth.saturating_add(1),
                limits,
                entries,
                total_bytes,
                directories,
            )?;
            continue;
        }
        if !metadata.is_file() {
            return Err(AdapterError::ArtifactRead(path));
        }
        if entries.len() >= limits.artifact_files {
            return Err(AdapterError::ArtifactLimitExceeded {
                files: entries.len().saturating_add(1),
                bytes: *total_bytes,
            });
        }
        let length = metadata.len();
        *total_bytes = (*total_bytes).saturating_add(length);
        if *total_bytes > limits.artifact_bytes {
            return Err(AdapterError::ArtifactLimitExceeded {
                files: entries.len().saturating_add(1),
                bytes: *total_bytes,
            });
        }
        let hash = hash_file(&path, length)?;
        entries.insert(
            relative.clone(),
            ArtifactEntry {
                relative_path: relative,
                byte_length: length,
                sha256: hash,
            },
        );
    }
    Ok(())
}

fn relative_artifact_path(root: &Path, path: &Path, limit: usize) -> Result<String, AdapterError> {
    let relative_path = path
        .strip_prefix(root)
        .map_err(|_| AdapterError::ArtifactRead(path.to_path_buf()))?;
    let relative = relative_path
        .to_str()
        .ok_or_else(|| AdapterError::NonUtf8Path(path.to_path_buf()))?
        .replace('\\', "/");
    if relative.len() > limit {
        return Err(AdapterError::ArtifactPathLimitExceeded {
            bytes: relative.len(),
            limit,
        });
    }
    Ok(relative)
}

#[cfg(windows)]
fn is_windows_reparse_point(metadata: &Metadata) -> bool {
    use std::os::windows::fs::MetadataExt;

    const FILE_ATTRIBUTE_REPARSE_POINT: u32 = 0x0400;
    metadata.file_attributes() & FILE_ATTRIBUTE_REPARSE_POINT != 0
}

#[cfg(not(windows))]
fn is_windows_reparse_point(_metadata: &Metadata) -> bool {
    false
}

fn hash_file(path: &Path, expected_length: u64) -> Result<String, AdapterError> {
    let mut file = File::open(path).map_err(|_| AdapterError::ArtifactRead(path.to_path_buf()))?;
    let mut hasher = Sha256::new();
    let mut buffer = [0_u8; 8192];
    let mut observed = 0_u64;
    loop {
        let read = file
            .read(&mut buffer)
            .map_err(|_| AdapterError::ArtifactRead(path.to_path_buf()))?;
        if read == 0 {
            break;
        }
        observed = observed.saturating_add(read as u64);
        hasher.update(&buffer[..read]);
    }
    if observed != expected_length {
        return Err(AdapterError::ArtifactRead(path.to_path_buf()));
    }
    Ok(hex_digest(hasher.finalize()))
}

fn build_manifest(
    root: &Path,
    entries: BTreeMap<String, ArtifactEntry>,
) -> Result<ArtifactManifest, AdapterError> {
    let entries: Vec<ArtifactEntry> = entries.into_values().collect();
    let lines = entries.iter().map(|entry| {
        format!(
            "{}\t{}\t{}",
            entry.relative_path, entry.byte_length, entry.sha256
        )
    });
    let root = root
        .to_str()
        .ok_or_else(|| AdapterError::NonUtf8Path(root.to_path_buf()))?;
    Ok(ArtifactManifest {
        root: root.to_owned(),
        sha256: hash_lines(lines),
        entries,
    })
}

fn hash_lines<I, S>(lines: I) -> String
where
    I: IntoIterator<Item = S>,
    S: AsRef<str>,
{
    let mut hasher = Sha256::new();
    for line in lines {
        let line = line.as_ref();
        hasher.update((line.len() as u64).to_le_bytes());
        hasher.update(line.as_bytes());
        hasher.update(*b"\n");
    }
    hex_digest(hasher.finalize())
}

fn hex_digest(digest: impl AsRef<[u8]>) -> String {
    digest
        .as_ref()
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

#[allow(dead_code)]
fn metadata_is_regular_file(metadata: &Metadata) -> bool {
    metadata.is_file()
}

#[cfg(test)]
mod unit_tests {
    use super::*;

    struct FailingReader;

    impl Read for FailingReader {
        fn read(&mut self, _buffer: &mut [u8]) -> std::io::Result<usize> {
            Err(std::io::Error::other("fixture read failure"))
        }
    }

    #[test]
    fn backend_must_be_explicit_and_supported() {
        let options = ProcessOptions::new("python", ".", ".");
        assert_eq!(
            RunHspiceRequest::new(vec![], options.clone())
                .unwrap_err()
                .code(),
            "backend_required"
        );
        let request =
            RunRfmRequest::new(vec![OsString::from("--backend=xyce")], options).unwrap_err();
        assert_eq!(request.code(), "backend_unsupported");
    }

    #[test]
    fn manifest_hash_is_order_stable() {
        let one = hash_lines(["a", "b"]);
        let two = hash_lines(["a", "b"]);
        assert_eq!(one, two);
    }

    #[test]
    fn capture_reader_failure_is_not_reported_as_clean_eof() {
        let handle = spawn_capture(FailingReader, 16, Arc::new(AtomicBool::new(false)));
        let output = receive_capture(
            &handle,
            Instant::now() + Duration::from_secs(1),
            OutputStream::Stdout,
        )
        .expect("capture report");
        assert!(output.read_failed);
        assert!(!output.exceeded);
    }
}
