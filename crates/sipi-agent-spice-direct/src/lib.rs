#![forbid(unsafe_code)]
#![recursion_limit = "512"]

//! AS-05 admission model plus the lane-local AS-01 `fit-sparam` direct port.
//!
//! The portable control and artifact paths are executable for deck splitting,
//! audit, conversion, dependency admission, and backend dispatch. Solver
//! processes remain caller-owned external runtimes, and numerical parity is
//! not claimed without the pinned differential gate.

pub mod as02_fit_sparam_cascade;
pub mod as03_fit_yparam;
pub mod as04_tune_yparam_tran;
pub mod as06_run_rfm;
pub mod fit_sparam;

use std::collections::{BTreeMap, BTreeSet};
use std::fmt::{Display, Formatter};
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

use serde_json::json;
use sha2::{Digest, Sha256};

pub const UPSTREAM_REPOSITORY: &str = "agent-spice";
pub const UPSTREAM_COMMIT: &str = "2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5";
pub const UPSTREAM_TREE: &str = "b6bde97128030d6cea0d68b2f0a35d807be8c402";
pub const UPSTREAM_LICENSE: &str = "MIT";
pub const WORKFLOW_ID: &str = "AS-05";
pub const WORKFLOW_NAME: &str = "run-hspice";

const SUPPORTED_DIRECTIVES: &[&str] = &[
    ".ac",
    ".alter",
    ".dc",
    ".elif",
    ".else",
    ".elseif",
    ".endl",
    ".end",
    ".endif",
    ".ends",
    ".global",
    ".inc",
    ".include",
    ".if",
    ".lib",
    ".model",
    ".measure",
    ".meas",
    ".op",
    ".option",
    ".options",
    ".param",
    ".print",
    ".probe",
    ".subckt",
    ".temp",
    ".tran",
    ".endcomment",
    ".end*comment",
];
const MAX_DECK_BYTES: u64 = 16 * 1024 * 1024;
const MAX_PROJECT_MANIFEST_BYTES: u64 = 1024 * 1024;

/// Project-level input accepted by the pinned `project.py` path.
///
/// This is intentionally a manifest and dispatch contract only.  It does not
/// imply that a native, ngspice, Xyce, or XDM executable is bundled here.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ProjectManifest {
    pub name: String,
    pub hspice_deck: Option<PathBuf>,
    pub backend: Backend,
    pub output_root: PathBuf,
}

impl ProjectManifest {
    pub fn from_yaml(path: impl AsRef<Path>) -> Result<Self, DirectPortError> {
        let path = path.as_ref();
        let metadata = fs::metadata(path)
            .map_err(|error| DirectPortError::ProjectManifestIo(error.to_string()))?;
        if metadata.len() > MAX_PROJECT_MANIFEST_BYTES {
            return Err(DirectPortError::InvalidProjectManifest(
                "manifest exceeds the bounded 1 MiB input budget".to_owned(),
            ));
        }
        let text = fs::read_to_string(path)
            .map_err(|error| DirectPortError::ProjectManifestIo(error.to_string()))?;
        let value: serde_yaml::Value = serde_yaml::from_str(&text)
            .map_err(|error| DirectPortError::InvalidProjectManifest(error.to_string()))?;
        Self::from_mapping(&value)
    }

    pub fn from_mapping(value: &serde_yaml::Value) -> Result<Self, DirectPortError> {
        let mapping = value.as_mapping().ok_or_else(|| {
            DirectPortError::InvalidProjectManifest("manifest must contain a mapping".to_owned())
        })?;
        let key = |name: &str| serde_yaml::Value::String(name.to_owned());
        let required_string = |field: &str| {
            mapping
                .get(key(field))
                .and_then(serde_yaml::Value::as_str)
                .filter(|value| !value.trim().is_empty())
                .map(ToOwned::to_owned)
                .ok_or_else(|| {
                    DirectPortError::InvalidProjectManifest(format!(
                        "manifest field '{field}' must be a non-empty string"
                    ))
                })
        };
        let name = required_string("name")?;
        let backend_name =
            mapping
                .get(key("backend"))
                .map_or(Ok("native".to_owned()), |value| {
                    value.as_str().map(str::to_ascii_lowercase).ok_or_else(|| {
                        DirectPortError::InvalidProjectManifest(
                            "manifest field 'backend' must be a string".to_owned(),
                        )
                    })
                })?;
        let backend = Backend::parse(&backend_name)?;
        let optional_mapping = |field: &str| {
            mapping.get(key(field)).map_or_else(
                || Ok(None),
                |value| {
                    value.as_mapping().map(Some).ok_or_else(|| {
                        DirectPortError::InvalidProjectManifest(format!(
                            "manifest field '{field}' must be a mapping"
                        ))
                    })
                },
            )
        };
        let inputs = optional_mapping("inputs")?;
        let outputs = optional_mapping("outputs")?;
        let hspice_deck = match inputs.and_then(|mapping| mapping.get(key("hspice_deck"))) {
            None | Some(serde_yaml::Value::Null) => None,
            Some(value) => {
                let raw = value.as_str().ok_or_else(|| {
                    DirectPortError::InvalidProjectManifest(
                        "inputs.hspice_deck must be a string".to_owned(),
                    )
                })?;
                (!raw.is_empty()).then(|| PathBuf::from(raw))
            }
        };
        let output_root = outputs
            .and_then(|mapping| mapping.get(key("root")))
            .map(|value| {
                value.as_str().map(PathBuf::from).ok_or_else(|| {
                    DirectPortError::InvalidProjectManifest(
                        "outputs.root must be a string".to_owned(),
                    )
                })
            })
            .transpose()?
            .unwrap_or_else(|| PathBuf::from("runs"));
        Ok(Self {
            name,
            hspice_deck,
            backend,
            output_root,
        })
    }
}

/// Match `project.prepare_run_directory` without silently launching a solver.
pub fn prepare_project_run_directory(
    root: impl AsRef<Path>,
    project_name: &str,
    case_name: &str,
) -> Result<PathBuf, DirectPortError> {
    if project_name.is_empty() || case_name.is_empty() {
        return Err(DirectPortError::InvalidProjectManifest(
            "project and case names must be non-empty".to_owned(),
        ));
    }
    let run_dir = root.as_ref().join(project_name).join(case_name);
    fs::create_dir_all(&run_dir).map_err(|error| DirectPortError::OutputIo(error.to_string()))?;
    Ok(run_dir)
}

pub(crate) fn absolute_path(path: &Path) -> Result<PathBuf, std::io::Error> {
    if path.is_absolute() {
        Ok(path.to_path_buf())
    } else {
        Ok(std::env::current_dir()?.join(path))
    }
}

fn file_sha256(path: &Path) -> Result<String, DirectPortError> {
    let bytes = fs::read(path).map_err(|e| DirectPortError::InputIo(e.to_string()))?;
    Ok(format!("{:x}", Sha256::digest(bytes)))
}

type StagedCaseDependencies = (
    Vec<serde_json::Value>,
    Vec<ConversionAction>,
    Vec<UnsupportedIssue>,
);

fn stage_case_dependencies(
    source_root: &Path,
    run_root: &Path,
    text: &str,
    backend: Backend,
) -> Result<StagedCaseDependencies, DirectPortError> {
    const MAX_FILES: usize = 4096;
    const MAX_BYTES: u64 = 64 * 1024 * 1024;
    let root = source_root
        .canonicalize()
        .map_err(|e| DirectPortError::InputIo(e.to_string()))?;
    let mut queue = audit_deck(text)
        .includes
        .into_iter()
        .map(|reference| (root.clone(), reference))
        .chain(
            audit_deck(text)
                .libraries
                .into_iter()
                .map(|library| (root.clone(), library.path)),
        )
        .collect::<Vec<_>>();
    let mut seen = BTreeSet::new();
    let mut staged = Vec::new();
    let mut actions = Vec::new();
    let mut unsupported = Vec::new();
    let mut total = 0u64;
    while let Some((parent, reference)) = queue.pop() {
        let path = Path::new(&reference);
        if path.is_absolute() {
            return Err(DirectPortError::UnsupportedExecution(format!(
                "absolute dependency is not staged: {reference}"
            )));
        }
        let source = parent.join(path).canonicalize().map_err(|e| {
            DirectPortError::UnsupportedExecution(format!(
                "dependency {reference} is unavailable: {e}"
            ))
        })?;
        let relative = source.strip_prefix(&root).map_err(|_| {
            DirectPortError::UnsupportedExecution(format!(
                "dependency escapes deck root: {reference}"
            ))
        })?;
        if !seen.insert(source.clone()) {
            continue;
        }
        if seen.len() > MAX_FILES {
            return Err(DirectPortError::UnsupportedExecution(
                "dependency file budget exceeded".to_owned(),
            ));
        }
        let size = fs::metadata(&source)
            .map_err(|e| DirectPortError::UnsupportedExecution(e.to_string()))?
            .len();
        total = total.saturating_add(size);
        if total > MAX_BYTES {
            return Err(DirectPortError::UnsupportedExecution(
                "dependency byte budget exceeded".to_owned(),
            ));
        }
        let target = run_root.join(relative);
        if let Some(parent) = target.parent() {
            fs::create_dir_all(parent).map_err(|e| DirectPortError::OutputIo(e.to_string()))?;
        }
        let nested =
            fs::read_to_string(&source).map_err(|e| DirectPortError::InputIo(e.to_string()))?;
        let (staged_text, nested_actions, nested_unsupported) = convert_deck(&nested, backend);
        actions.extend(nested_actions);
        unsupported.extend(nested_unsupported);
        for directive in audit_deck(&nested).unsupported_directives {
            unsupported.push(UnsupportedIssue {
                line: directive,
                reason: "unsupported_directive_in_dependency".to_owned(),
            });
        }
        fs::write(&target, staged_text).map_err(|e| DirectPortError::OutputIo(e.to_string()))?;
        let nested_audit = audit_deck(&nested);
        for child in nested_audit.includes {
            queue.push((source.parent().unwrap_or(&root).to_path_buf(), child));
        }
        for child in nested_audit.libraries {
            queue.push((source.parent().unwrap_or(&root).to_path_buf(), child.path));
        }
        staged.push(json!({"source": source, "staged": relative.to_string_lossy().replace('\\', "/"), "sha256": file_sha256(&source)?}));
    }
    staged.sort_by(|a, b| a["staged"].as_str().cmp(&b["staged"].as_str()));
    Ok((staged, actions, unsupported))
}

/// The four backend selectors accepted by the pinned CLI.
#[derive(Clone, Copy, Debug, Eq, Ord, PartialEq, PartialOrd)]
pub enum Backend {
    Native,
    Ngspice,
    Xyce,
    XyceXdm,
}

impl Backend {
    pub const ALL: [Self; 4] = [Self::Native, Self::Ngspice, Self::Xyce, Self::XyceXdm];

    pub const fn name(self) -> &'static str {
        match self {
            Self::Native => "native",
            Self::Ngspice => "ngspice",
            Self::Xyce => "xyce",
            Self::XyceXdm => "xyce-xdm",
        }
    }

    pub fn parse(value: &str) -> Result<Self, DirectPortError> {
        match value {
            "native" => Ok(Self::Native),
            "ngspice" => Ok(Self::Ngspice),
            "xyce" => Ok(Self::Xyce),
            "xyce-xdm" => Ok(Self::XyceXdm),
            other => Err(DirectPortError::UnsupportedBackend(other.to_owned())),
        }
    }
}

impl Display for Backend {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(self.name())
    }
}

/// Caller-visible options that affect the upstream branch graph.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RunHspiceRequest {
    pub backend: Backend,
    pub output_root: PathBuf,
    pub execute: bool,
    pub native_engine: Option<PathBuf>,
    pub rfm: Option<PathBuf>,
    pub rfm_subcircuit: String,
    pub dotnet_executable: String,
}

impl RunHspiceRequest {
    pub fn new(
        backend: &str,
        output_root: impl Into<PathBuf>,
        execute: bool,
    ) -> Result<Self, DirectPortError> {
        let output_root = output_root.into();
        if output_root.as_os_str().is_empty() {
            return Err(DirectPortError::EmptyOutputRoot);
        }
        Ok(Self {
            backend: Backend::parse(backend)?,
            output_root,
            execute,
            native_engine: None,
            rfm: None,
            rfm_subcircuit: "rfm_direct".to_owned(),
            dotnet_executable: "dotnet".to_owned(),
        })
    }

    pub fn with_native_engine(mut self, path: impl Into<PathBuf>) -> Self {
        self.native_engine = Some(path.into());
        self
    }

    pub fn with_rfm(mut self, path: impl Into<PathBuf>, subcircuit: impl Into<String>) -> Self {
        self.rfm = Some(path.into());
        self.rfm_subcircuit = subcircuit.into();
        self
    }

    pub fn with_dotnet(mut self, executable: impl Into<String>) -> Self {
        self.dotnet_executable = executable.into();
        self
    }
}

/// Stable rejection categories for this admission layer.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum DirectPortError {
    UnsupportedBackend(String),
    EmptyOutputRoot,
    EmptyDeckStem,
    ProjectManifestIo(String),
    InvalidProjectManifest(String),
    InputIo(String),
    OutputIo(String),
    UnsupportedExecution(String),
}

impl Display for DirectPortError {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::UnsupportedBackend(value) => write!(formatter, "unsupported backend '{value}'"),
            Self::EmptyOutputRoot => formatter.write_str("output root must not be empty"),
            Self::EmptyDeckStem => formatter.write_str("deck stem must not be empty"),
            Self::ProjectManifestIo(value) => {
                write!(formatter, "project manifest I/O failed: {value}")
            }
            Self::InvalidProjectManifest(value) => {
                write!(formatter, "invalid project manifest: {value}")
            }
            Self::InputIo(value) => write!(formatter, "input I/O failed: {value}"),
            Self::OutputIo(value) => write!(formatter, "output I/O failed: {value}"),
            Self::UnsupportedExecution(value) => {
                write!(formatter, "execution unavailable: {value}")
            }
        }
    }
}

impl std::error::Error for DirectPortError {}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum CaseKind {
    Base,
    Alter,
    Other,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct DeckCase {
    pub name: String,
    pub text: String,
    pub kind: CaseKind,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct LibraryReference {
    pub path: String,
    pub section: Option<String>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct DeckAudit {
    pub directive_counts: BTreeMap<String, usize>,
    pub includes: Vec<String>,
    pub libraries: Vec<LibraryReference>,
    pub unsupported_directives: Vec<String>,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum DependencyAdmission {
    RelativeRequiresSourceRoot,
    AbsoluteNotStaged,
    LexicallyEscapesSourceRoot,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct DependencyReference {
    pub reference: String,
    pub admission: DependencyAdmission,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ConversionAction {
    pub kind: String,
    pub source: String,
    pub target: String,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct UnsupportedIssue {
    pub line: String,
    pub reason: String,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum PreparationStatus {
    Compatible,
    AutoConverted,
    Blocked,
}

impl PreparationStatus {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Compatible => "compatible",
            Self::AutoConverted => "auto_converted",
            Self::Blocked => "blocked",
        }
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct PreparedCase {
    pub case: DeckCase,
    pub deck_text: String,
    pub audit: DeckAudit,
    pub dependencies: Vec<DependencyReference>,
    pub actions: Vec<ConversionAction>,
    pub unsupported: Vec<UnsupportedIssue>,
    pub preparation_status: PreparationStatus,
    pub output_paths: Vec<String>,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ExecutionStage {
    NotExecuted,
    NativeEngine,
    Ngspice,
    Xyce,
    XdmThenXyce,
}

impl ExecutionStage {
    pub const fn for_request(request: &RunHspiceRequest) -> Self {
        if !request.execute {
            return Self::NotExecuted;
        }
        match request.backend {
            Backend::Native => Self::NativeEngine,
            Backend::Ngspice => Self::Ngspice,
            Backend::Xyce => Self::Xyce,
            Backend::XyceXdm => Self::XdmThenXyce,
        }
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RunHspiceAdmission {
    pub deck_id: String,
    pub backend: Backend,
    pub execute: bool,
    pub execution_stage: ExecutionStage,
    pub cases: Vec<PreparedCase>,
    pub external_solver_required: bool,
    pub numerical_parity: ParityStatus,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ParityStatus {
    NotEvaluated,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RunHspiceResult {
    pub status: PreparationStatus,
    pub output_root: PathBuf,
    pub case_count: usize,
    pub execution_returncodes: Vec<Option<i32>>,
    pub numerical_parity: ParityStatus,
}

/// Build the AS-05 branch plan from the same deck text accepted by upstream.
/// No file is opened and no backend process is launched here.
pub fn admit_run_hspice(
    deck_stem: &str,
    deck_text: &str,
    request: RunHspiceRequest,
) -> Result<RunHspiceAdmission, DirectPortError> {
    if deck_stem.is_empty() {
        return Err(DirectPortError::EmptyDeckStem);
    }
    let cases = split_alter_cases(deck_text, deck_stem);
    let prepared = cases
        .into_iter()
        .map(|case| prepare_case(case, request.backend))
        .collect();
    Ok(RunHspiceAdmission {
        deck_id: deck_stem.to_owned(),
        backend: request.backend,
        execute: request.execute,
        execution_stage: ExecutionStage::for_request(&request),
        cases: prepared,
        external_solver_required: request.execute,
        numerical_parity: ParityStatus::NotEvaluated,
    })
}

/// Execute the portable AS-05 preparation path and, only when explicitly
/// requested with a caller-provided executable, the selected solver branch.
///
/// The function writes source, converted deck, and compatibility JSON for
/// every case.  Dependency staging, runtime identity attestation, and solver
/// waveform parity remain open; unsupported cases are reported as BLOCKED and
/// never turned into successful artifacts.
pub fn run_hspice(
    deck_path: impl AsRef<Path>,
    request: RunHspiceRequest,
) -> Result<RunHspiceResult, DirectPortError> {
    if request.execute && !external_execution_available() {
        return Err(DirectPortError::UnsupportedExecution(
            "external simulator execution is fail-closed: executable custody is required"
                .to_owned(),
        ));
    }
    let deck_path = absolute_path(deck_path.as_ref())
        .map_err(|error| DirectPortError::InputIo(error.to_string()))?;
    if deck_path
        .metadata()
        .map(|metadata| metadata.len() > MAX_DECK_BYTES)
        .unwrap_or(false)
    {
        return Err(DirectPortError::InputIo(
            "deck exceeds the bounded 16 MiB input budget".to_owned(),
        ));
    }
    let source = fs::read_to_string(&deck_path)
        .map_err(|error| DirectPortError::InputIo(error.to_string()))?;
    let stem = deck_path
        .file_stem()
        .and_then(|value| value.to_str())
        .ok_or(DirectPortError::EmptyDeckStem)?;
    if stem.is_empty() {
        return Err(DirectPortError::EmptyDeckStem);
    }
    fs::create_dir_all(&request.output_root)
        .map_err(|error| DirectPortError::OutputIo(error.to_string()))?;
    let output_root = absolute_path(&request.output_root)
        .map_err(|error| DirectPortError::OutputIo(error.to_string()))?;
    let rfm = request
        .rfm
        .as_ref()
        .map(|path| absolute_path(path))
        .transpose()
        .map_err(|error| DirectPortError::InputIo(error.to_string()))?;
    let admission = admit_run_hspice(stem, &source, request.clone())?;
    let source_hash = format!("{:x}", Sha256::digest(source.as_bytes()));
    let source_name = stable_source_path(&deck_path, stem);
    let mut returncodes = Vec::with_capacity(admission.cases.len());
    let mut overall_status = PreparationStatus::Compatible;
    let project_root = output_root.join(stem);
    for case in &admission.cases {
        let mut case_status = case.preparation_status;
        if case_status == PreparationStatus::Blocked {
            overall_status = PreparationStatus::Blocked;
        } else if case_status == PreparationStatus::AutoConverted
            && overall_status == PreparationStatus::Compatible
        {
            overall_status = PreparationStatus::AutoConverted;
        }
        let directory = prepare_project_run_directory(&output_root, stem, &case.case.name)?;
        fs::create_dir_all(&directory)
            .map_err(|error| DirectPortError::OutputIo(error.to_string()))?;
        let (runtime_deck, sparam_actions, sparam_unsupported) =
            if admission.backend == Backend::Ngspice {
                compile_touchstone_s_elements(
                    &case.deck_text,
                    deck_path.parent().unwrap_or_else(|| Path::new(".")),
                    &directory,
                )?
            } else {
                (case.deck_text.clone(), Vec::new(), Vec::new())
            };
        if !sparam_unsupported.is_empty() {
            case_status = PreparationStatus::Blocked;
            overall_status = PreparationStatus::Blocked;
        } else if !sparam_actions.is_empty() && case_status == PreparationStatus::Compatible {
            case_status = PreparationStatus::AutoConverted;
            if overall_status == PreparationStatus::Compatible {
                overall_status = PreparationStatus::AutoConverted;
            }
        }
        fs::write(directory.join("case.source.sp"), &case.case.text)
            .map_err(|error| DirectPortError::OutputIo(error.to_string()))?;
        fs::write(directory.join("case.cir"), &runtime_deck)
            .map_err(|error| DirectPortError::OutputIo(error.to_string()))?;
        if admission.backend == Backend::XyceXdm {
            fs::write(directory.join("case.sp"), &case.case.text)
                .map_err(|error| DirectPortError::OutputIo(error.to_string()))?;
        }
        let (staged_dependencies, dependency_actions, dependency_unsupported) =
            if case_status == PreparationStatus::Blocked {
                (Vec::new(), Vec::new(), Vec::new())
            } else {
                stage_case_dependencies(
                    deck_path.parent().unwrap_or_else(|| Path::new(".")),
                    &directory,
                    &case.case.text,
                    admission.backend,
                )?
            };
        if !dependency_unsupported.is_empty() {
            case_status = PreparationStatus::Blocked;
            overall_status = PreparationStatus::Blocked;
        } else if !dependency_actions.is_empty() && case_status == PreparationStatus::Compatible {
            case_status = PreparationStatus::AutoConverted;
            if overall_status == PreparationStatus::Compatible {
                overall_status = PreparationStatus::AutoConverted;
            }
        }
        fs::write(
            directory.join("dependencies.json"),
            serde_json::to_string_pretty(&staged_dependencies)
                .map_err(|error| DirectPortError::OutputIo(error.to_string()))?
                + "\n",
        )
        .map_err(|error| DirectPortError::OutputIo(error.to_string()))?;
        let case_source_sha = file_sha256(&directory.join("case.source.sp"))?;
        let prepared_sha = file_sha256(&directory.join("case.cir"))?;
        let compatibility = json!({
            "schema": "sipi.agent-spice-as-05-compatibility-report.v2",
            "schema_version": 2,
            "case": {"name": case.case.name, "kind": match case.case.kind { CaseKind::Base => "base", CaseKind::Alter => "alter", CaseKind::Other => "other" }},
            "backend": admission.backend.name(),
            "status": case_status.as_str(),
            "deck": {"id": stem, "source": source_name, "sha256": source_hash, "case_source": "case.source.sp", "case_source_sha256": case_source_sha, "prepared": "case.cir", "prepared_sha256": prepared_sha},
            "audit": {"directive_counts": case.audit.directive_counts, "includes": case.audit.includes, "libraries": case.audit.libraries.iter().map(|library| json!([library.path, library.section])).collect::<Vec<_>>(), "unsupported_directives": case.audit.unsupported_directives},
            "outputs": {"probes": output_probes(&case.case.text), "measures": output_measures(&case.case.text)},
            "actions": case.actions.iter().chain(&sparam_actions).chain(&dependency_actions).map(|action| json!({"kind": action.kind, "source": action.source, "target": action.target})).collect::<Vec<_>>(),
            "unsupported": case.audit.unsupported_directives.iter().map(|line| json!({"line": line, "reason": "unsupported_directive"})).chain(case.unsupported.iter().chain(&sparam_unsupported).chain(&dependency_unsupported).map(|issue| json!({"line": issue.line, "reason": issue.reason}))).collect::<Vec<_>>(),
            "dependencies": staged_dependencies,
            "summary": {"status": case_status.as_str(), "rewrites": case.actions.len() + sparam_actions.len() + dependency_actions.len(), "drops": case.actions.iter().chain(&dependency_actions).filter(|action| action.kind == "drop_option").count(), "unsupported": case.unsupported.len() + sparam_unsupported.len() + dependency_unsupported.len() + case.audit.unsupported_directives.len()},
        });
        let report_text = serde_json::to_string_pretty(&compatibility)
            .map_err(|error| DirectPortError::OutputIo(error.to_string()))?;
        fs::write(directory.join("compat_report.json"), report_text + "\n")
            .map_err(|error| DirectPortError::OutputIo(error.to_string()))?;
        if !sparam_actions.is_empty()
            || !sparam_unsupported.is_empty()
            || !dependency_actions.is_empty()
            || !dependency_unsupported.is_empty()
        {
            let mut preflight = sparam_actions
                .iter()
                .map(|action| format!("{}: {} -> {}", action.kind, action.source, action.target))
                .collect::<Vec<_>>();
            preflight.extend(dependency_actions.iter().map(|action| {
                format!(
                    "dependency {}: {} -> {}",
                    action.kind, action.source, action.target
                )
            }));
            preflight.extend(
                sparam_unsupported
                    .iter()
                    .map(|issue| format!("BLOCKED: {} ({})", issue.line, issue.reason)),
            );
            preflight.extend(
                dependency_unsupported
                    .iter()
                    .map(|issue| format!("BLOCKED: dependency {} ({})", issue.line, issue.reason)),
            );
            fs::write(directory.join("preflight.log"), preflight.join("\n") + "\n")
                .map_err(|error| DirectPortError::OutputIo(error.to_string()))?;
        }

        let returncode = if request.execute
            && case_status != PreparationStatus::Blocked
            && sparam_unsupported.is_empty()
        {
            let (program, args): (PathBuf, Vec<PathBuf>) = match admission.backend {
                Backend::Native => {
                    let engine = request
                        .native_engine
                        .as_ref()
                        .map(|path| absolute_path(path))
                        .transpose()
                        .map_err(|error| DirectPortError::InputIo(error.to_string()))?
                        .ok_or_else(|| {
                            DirectPortError::UnsupportedExecution(
                                "native backend requires --native-engine".to_owned(),
                            )
                        })?;
                    let mut args = Vec::new();
                    let program = if engine
                        .extension()
                        .is_some_and(|value| value.eq_ignore_ascii_case("dll"))
                    {
                        args.push(engine);
                        PathBuf::from(&request.dotnet_executable)
                    } else {
                        engine
                    };
                    args.extend([
                        directory.join("case.cir"),
                        PathBuf::from("--waveform-csv"),
                        directory.join("waveform.csv"),
                        PathBuf::from("--output-json"),
                        directory.join("native_result.json"),
                    ]);
                    if let Some(rfm) = &rfm {
                        args.push(PathBuf::from("--rfm"));
                        args.push(rfm.clone());
                        args.push(PathBuf::from("--rfm-subckt"));
                        args.push(PathBuf::from(&request.rfm_subcircuit));
                    }
                    (program, args)
                }
                Backend::Ngspice => (
                    PathBuf::from("ngspice"),
                    vec![
                        PathBuf::from("-b"),
                        directory.join("case.cir"),
                        PathBuf::from("-o"),
                        directory.join("case"),
                    ],
                ),
                Backend::Xyce => (PathBuf::from("Xyce"), vec![directory.join("case.cir")]),
                Backend::XyceXdm => (
                    PathBuf::from("xdm_bdl"),
                    vec![
                        PathBuf::from("-s"),
                        PathBuf::from("hspice"),
                        PathBuf::from("-d"),
                        directory.join("xdm-out"),
                        PathBuf::from("-o"),
                        PathBuf::from("xyce"),
                        directory.join("case.sp"),
                    ],
                ),
            };
            let output = Command::new(&program)
                .args(args.iter().map(|value| value.as_os_str()))
                .current_dir(&directory)
                .output()
                .map_err(|error| {
                    DirectPortError::UnsupportedExecution(format!("{}: {error}", program.display()))
                })?;
            fs::write(directory.join("stdout.log"), &output.stdout)
                .map_err(|error| DirectPortError::OutputIo(error.to_string()))?;
            fs::write(directory.join("stderr.log"), &output.stderr)
                .map_err(|error| DirectPortError::OutputIo(error.to_string()))?;
            if admission.backend == Backend::XyceXdm {
                fs::write(directory.join("xdm.stdout.log"), &output.stdout)
                    .map_err(|error| DirectPortError::OutputIo(error.to_string()))?;
                fs::write(directory.join("xdm.stderr.log"), &output.stderr)
                    .map_err(|error| DirectPortError::OutputIo(error.to_string()))?;
                let generated = directory.join("xdm-out").join("case.sp");
                let xdm_returncode = output.status.code().unwrap_or(-1);
                if !output.status.success() {
                    let summary = json!({
                        "schema_version": 1,
                        "backend": "xyce-xdm",
                        "ok": false,
                        "returncode": xdm_returncode,
                        "stages": {
                            "xdm": {"ok": false, "returncode": xdm_returncode, "stdout": "xdm.stdout.log", "stderr": "xdm.stderr.log"},
                            "xyce": null,
                        },
                    });
                    fs::write(
                        directory.join("run_summary.json"),
                        serde_json::to_string_pretty(&summary)
                            .map_err(|error| DirectPortError::OutputIo(error.to_string()))?
                            + "\n",
                    )
                    .map_err(|error| DirectPortError::OutputIo(error.to_string()))?;
                    Some(xdm_returncode)
                } else if !generated.is_file() {
                    let message = format!(
                        "xdm_bdl completed without a generated Xyce deck: {}",
                        generated.display()
                    );
                    fs::write(directory.join("xdm.stderr.log"), &message)
                        .map_err(|error| DirectPortError::OutputIo(error.to_string()))?;
                    let summary = json!({
                        "schema_version": 1,
                        "backend": "xyce-xdm",
                        "ok": false,
                        "returncode": 1,
                        "stages": {
                            "xdm": {"ok": false, "returncode": 1, "stdout": "xdm.stdout.log", "stderr": "xdm.stderr.log"},
                            "xyce": null,
                        },
                    });
                    fs::write(
                        directory.join("run_summary.json"),
                        serde_json::to_string_pretty(&summary)
                            .map_err(|error| DirectPortError::OutputIo(error.to_string()))?
                            + "\n",
                    )
                    .map_err(|error| DirectPortError::OutputIo(error.to_string()))?;
                    Some(1)
                } else {
                    // The upstream XDM backend feeds `case.sp` and receives
                    // a generated deck with the same basename before Xyce.
                    let xyce_deck = directory.join("case.cir");
                    fs::copy(&generated, &xyce_deck)
                        .map_err(|error| DirectPortError::OutputIo(error.to_string()))?;
                    let xyce = Command::new("Xyce")
                        .arg(&xyce_deck)
                        .current_dir(&directory)
                        .output()
                        .map_err(|error| {
                            DirectPortError::UnsupportedExecution(error.to_string())
                        })?;
                    fs::write(directory.join("xyce.stdout.log"), &xyce.stdout)
                        .map_err(|error| DirectPortError::OutputIo(error.to_string()))?;
                    fs::write(directory.join("xyce.stderr.log"), &xyce.stderr)
                        .map_err(|error| DirectPortError::OutputIo(error.to_string()))?;
                    let summary = json!({
                        "schema_version": 1,
                        "backend": "xyce-xdm",
                        "ok": xyce.status.success(),
                        "returncode": xyce.status.code().unwrap_or(-1),
                        "stages": {
                            "xdm": {"ok": true, "returncode": xdm_returncode, "stdout": "xdm.stdout.log", "stderr": "xdm.stderr.log"},
                            "xyce": {"ok": xyce.status.success(), "returncode": xyce.status.code().unwrap_or(-1), "stdout": "xyce.stdout.log", "stderr": "xyce.stderr.log"},
                        },
                    });
                    fs::write(
                        directory.join("run_summary.json"),
                        serde_json::to_string_pretty(&summary)
                            .map_err(|error| DirectPortError::OutputIo(error.to_string()))?
                            + "\n",
                    )
                    .map_err(|error| DirectPortError::OutputIo(error.to_string()))?;
                    Some(xyce.status.code().unwrap_or(-1))
                }
            } else {
                let error_text = if output.status.success() {
                    serde_json::Value::Null
                } else {
                    let stderr = String::from_utf8_lossy(&output.stderr);
                    let stdout = String::from_utf8_lossy(&output.stdout);
                    serde_json::Value::String(if !stderr.trim().is_empty() {
                        stderr.trim().to_owned()
                    } else if !stdout.trim().is_empty() {
                        stdout.trim().to_owned()
                    } else {
                        "backend failed without output".to_owned()
                    })
                };
                let mut summary = json!({"schema_version":1,"backend":admission.backend.name(),"returncode":output.status.code(),"ok":output.status.success(),"logs":{"stdout":"stdout.log","stderr":"stderr.log"},"waveform":null,"measurements":[],"error":error_text});
                let backend_text = if admission.backend == Backend::Ngspice {
                    let mut text = String::from_utf8_lossy(&output.stdout).into_owned();
                    let transcript = directory.join("case");
                    if transcript.is_file()
                        && let Ok(value) = fs::read_to_string(transcript)
                    {
                        if !text.is_empty() {
                            text.push('\n');
                        }
                        text.push_str(&value);
                    }
                    text
                } else {
                    String::from_utf8_lossy(&output.stdout).into_owned()
                };
                if admission.backend == Backend::Ngspice {
                    let waveform = directory.join("waveform.csv");
                    let rows = write_ngspice_waveform_csv(&backend_text, &waveform);
                    summary["waveform"] = json!({"path":"waveform.csv","format":"csv","exists":waveform.is_file(),"rows":rows});
                    summary["measurements"] = json!(parse_ngspice_measurements(&backend_text));
                }
                if admission.backend == Backend::Native {
                    let result_path = directory.join("native_result.json");
                    if output.status.success() && !result_path.is_file() {
                        return Err(DirectPortError::UnsupportedExecution(
                            "native engine returned success without native_result.json".to_owned(),
                        ));
                    }
                    if output.status.success() && result_path.is_file() {
                        let result: serde_json::Value = serde_json::from_slice(
                            &fs::read(&result_path)
                                .map_err(|error| DirectPortError::InputIo(error.to_string()))?,
                        )
                        .map_err(|error| {
                            DirectPortError::UnsupportedExecution(format!(
                                "native result JSON is invalid: {error}"
                            ))
                        })?;
                        if !result.is_object() {
                            return Err(DirectPortError::UnsupportedExecution(
                                "native result must be a JSON object".to_owned(),
                            ));
                        }
                        let waveform_rows = result
                            .get("waveformRows")
                            .and_then(serde_json::Value::as_u64)
                            .unwrap_or(0);
                        summary["waveform"] = json!({
                            "path": "waveform.csv",
                            "format": "csv",
                            "exists": directory.join("waveform.csv").is_file(),
                            "rows": waveform_rows,
                        });
                        if let Some(measurements) = result.get("measurements")
                            && measurements.is_array()
                        {
                            summary["measurements"] = measurements.clone();
                        }
                        summary["native_result"] = json!({
                            "path": "native_result.json",
                            "exists": true,
                        });
                    }
                    if !summary
                        .get("native_result")
                        .is_some_and(|value| value.is_object())
                    {
                        summary["native_result"] = json!({
                            "path": "native_result.json",
                            "exists": result_path.is_file(),
                        });
                    }
                }
                fs::write(
                    directory.join("run_summary.json"),
                    serde_json::to_string_pretty(&summary)
                        .map_err(|error| DirectPortError::OutputIo(error.to_string()))?
                        + "\n",
                )
                .map_err(|error| DirectPortError::OutputIo(error.to_string()))?;
                Some(output.status.code().unwrap_or(-1))
            }
        } else {
            None
        };
        returncodes.push(returncode);
        if returncode.is_some_and(|code| code != 0) {
            overall_status = PreparationStatus::Blocked;
        }
    }
    let run_report = json!({
        "schema": "sipi.agent-spice-as-05-run-hspice-result.v2",
        "schema_version": 2,
        "workflow": WORKFLOW_NAME,
        "upstream_commit": UPSTREAM_COMMIT,
        "upstream_tree": UPSTREAM_TREE,
        "backend": request.backend.name(),
        "execute": request.execute,
        "status": overall_status.as_str(),
        "case_count": admission.cases.len(),
        "execution_returncodes": returncodes,
        "numerical_parity": "not_evaluated",
        "portable_branches": ["alter-case-splitting", "quoted-comment-and-continuation-audit", "recursive-dependency-staging", "ngspice-conversion", "measure/probe-contract", "native-result-validation", "xdm-two-stage-dispatch"],
        "external_runtime_boundary": ["native-engine", "ngspice", "Xyce", "xdm_bdl"],
    });
    let report_text = serde_json::to_string_pretty(&run_report)
        .map_err(|error| DirectPortError::OutputIo(error.to_string()))?;
    fs::write(project_root.join("run_report.json"), report_text + "\n")
        .map_err(|error| DirectPortError::OutputIo(error.to_string()))?;
    Ok(RunHspiceResult {
        status: overall_status,
        output_root,
        case_count: admission.cases.len(),
        execution_returncodes: returncodes,
        numerical_parity: ParityStatus::NotEvaluated,
    })
}

fn external_execution_available() -> bool {
    false
}

/// Resolve and dispatch the upstream project-manifest branch through the
/// same deck/backend/result contract as the direct deck entry point.
pub fn run_hspice_project(
    manifest_path: impl AsRef<Path>,
    execute: bool,
    native_engine: Option<PathBuf>,
) -> Result<RunHspiceResult, DirectPortError> {
    let manifest_path = absolute_path(manifest_path.as_ref())
        .map_err(|error| DirectPortError::ProjectManifestIo(error.to_string()))?;
    let manifest = ProjectManifest::from_yaml(&manifest_path)?;
    let manifest_dir = manifest_path.parent().unwrap_or_else(|| Path::new("."));
    let deck = manifest.hspice_deck.ok_or_else(|| {
        DirectPortError::InvalidProjectManifest(
            "inputs.hspice_deck is required for run-hspice project dispatch".to_owned(),
        )
    })?;
    let deck = if deck.is_absolute() {
        deck
    } else {
        manifest_dir.join(deck)
    };
    let output_root = if manifest.output_root.is_absolute() {
        manifest.output_root
    } else {
        manifest_dir.join(manifest.output_root)
    };
    let mut request = RunHspiceRequest::new(manifest.backend.name(), output_root, execute)?;
    request.native_engine = native_engine;
    run_hspice(deck, request)
}

fn output_probes(text: &str) -> Vec<String> {
    let mut probes = Vec::new();
    for raw in text.lines() {
        let line = raw.trim();
        if line.is_empty() || line.starts_with('*') {
            continue;
        }
        let parts = line.split_whitespace().collect::<Vec<_>>();
        let Some(directive) = parts.first() else {
            continue;
        };
        if matches!(directive.to_ascii_lowercase().as_str(), ".probe" | ".print")
            && parts.len() >= 3
        {
            probes.extend(parts[2..].iter().map(|value| (*value).to_owned()));
        }
    }
    probes
}

fn stable_source_path(deck_path: &Path, stem: &str) -> String {
    let fallback = deck_path
        .file_name()
        .and_then(|value| value.to_str())
        .unwrap_or(stem)
        .to_owned();
    let Ok(current) = std::env::current_dir() else {
        return fallback;
    };
    let Ok(relative) = deck_path.strip_prefix(current) else {
        return fallback;
    };
    let value = relative.to_string_lossy().replace('\\', "/");
    if value.is_empty() { fallback } else { value }
}

fn output_measures(text: &str) -> Vec<serde_json::Value> {
    let mut measures = Vec::new();
    for raw in text.lines() {
        let line = raw.trim();
        if line.is_empty() || line.starts_with('*') {
            continue;
        }
        let parts = line.split_whitespace().collect::<Vec<_>>();
        let Some(directive) = parts.first() else {
            continue;
        };
        if !matches!(
            directive.to_ascii_lowercase().as_str(),
            ".measure" | ".meas"
        ) || parts.len() < 4
        {
            continue;
        }
        let operation_token = parts[3];
        let mut operation = operation_token.to_ascii_lowercase();
        let target = if operation.starts_with("param=") {
            operation = "param".to_owned();
            operation_token
                .split_once('=')
                .map(|(_, value)| value.to_owned())
        } else if operation == "param" {
            if parts.len() >= 6 && parts[4] == "=" {
                Some(parts[5].to_owned())
            } else {
                parts.get(4).map(|value| (*value).to_owned())
            }
        } else {
            parts.get(4).map(|value| (*value).to_owned())
        };
        let Some(target) = target else {
            continue;
        };
        measures.push(json!({
            "analysis": parts[1].to_ascii_lowercase(),
            "name": parts[2],
            "operation": operation,
            "target": target,
            "raw": line,
        }));
    }
    measures
}

fn parse_ngspice_measurements(text: &str) -> Vec<serde_json::Value> {
    let mut measurements = Vec::new();
    for line in text.lines() {
        let fields = line.split_whitespace().collect::<Vec<_>>();
        let Some(first) = fields.first() else {
            continue;
        };
        let (name, number_token, suffix_start) = if let Some((name, value)) = first.split_once('=')
        {
            (name, value, 1usize)
        } else if fields.get(1).is_some_and(|value| *value == "=") {
            let Some(value) = fields.get(2) else {
                continue;
            };
            (*first, *value, 3usize)
        } else {
            continue;
        };
        let Some(number) = number_token.parse::<f64>().ok() else {
            continue;
        };
        let mut entry = json!({"name": name, "value": number});
        let at = fields[suffix_start..]
            .iter()
            .enumerate()
            .find_map(|(index, field)| {
                let lower = field.to_ascii_lowercase();
                if let Some(value) = lower.strip_prefix("at=") {
                    return value.parse::<f64>().ok();
                }
                if lower == "at=" {
                    return fields.get(suffix_start + index + 1)?.parse::<f64>().ok();
                }
                None
            });
        if let Some(at) = at {
            entry["at"] = json!(at);
        }
        measurements.push(entry);
    }
    measurements
}

fn write_ngspice_waveform_csv(text: &str, path: &Path) -> usize {
    let mut columns: Option<Vec<&str>> = None;
    let mut rows = Vec::<Vec<f64>>::new();
    for line in text.lines() {
        let fields = line.split_whitespace().collect::<Vec<_>>();
        if fields.first() == Some(&"Index") && fields.len() >= 3 {
            let candidate = fields[1..].to_vec();
            if columns.as_ref().is_none_or(|value| *value != candidate) {
                columns = Some(candidate);
                rows.clear();
            }
            continue;
        }
        let Some(header) = columns.as_ref() else {
            continue;
        };
        if fields.len() != header.len() + 1
            || fields
                .first()
                .is_none_or(|value| !value.chars().all(|c| c.is_ascii_digit()))
        {
            continue;
        }
        let Ok(values) = fields[1..]
            .iter()
            .map(|value| value.parse::<f64>())
            .collect::<Result<Vec<_>, _>>()
        else {
            continue;
        };
        rows.push(values);
    }
    let Some(columns) = columns else {
        return 0;
    };
    if rows.is_empty() {
        return 0;
    }
    let mut csv = columns.join(",");
    csv.push('\n');
    for row in &rows {
        csv.push_str(
            &row.iter()
                .map(|value| format!("{value:.17e}"))
                .collect::<Vec<_>>()
                .join(","),
        );
        csv.push('\n');
    }
    if csv.len() > MAX_DECK_BYTES as usize {
        return 0;
    }
    if fs::write(path, csv).is_err() {
        return 0;
    }
    rows.len()
}

fn touchstone_port_count(path: &Path) -> Option<usize> {
    let name = path.file_name()?.to_str()?.to_ascii_lowercase();
    let marker = name.rfind(".s")?;
    let digits = name.get(marker + 2..)?.strip_suffix('p')?;
    let ports = digits.parse::<usize>().ok()?;
    (ports > 0 && ports <= 32).then_some(ports)
}

fn compile_touchstone_s_elements(
    text: &str,
    source_dir: &Path,
    _run_dir: &Path,
) -> Result<(String, Vec<ConversionAction>, Vec<UnsupportedIssue>), DirectPortError> {
    let mut output = Vec::new();
    let actions = Vec::new();
    let mut unsupported = Vec::new();
    let lines = text.lines().collect::<Vec<_>>();
    let mut line_index = 0usize;
    while line_index < lines.len() {
        let raw = lines[line_index];
        let first_token = tokens(raw).into_iter().next().unwrap_or_default();
        let mut end_index = line_index + 1;
        // The pinned CLI consumes an S-element as one logical record, so a
        // TSTONEFILE parameter on a `+` continuation must be fitted too.
        if first_token.len() > 1
            && first_token.starts_with(['S', 's'])
            && !first_token.starts_with(['.', '*'])
        {
            while end_index < lines.len() && lines[end_index].trim_start().starts_with('+') {
                end_index += 1;
            }
        }
        let block = lines[line_index..end_index].join("\n");
        let normalized = block.replace('+', " ");
        let upper = normalized.to_ascii_uppercase();
        if !first_token.starts_with(['S', 's']) || !upper.contains("TSTONEFILE") {
            output.extend(
                lines[line_index..end_index]
                    .iter()
                    .map(|line| (*line).to_owned()),
            );
            line_index = end_index;
            continue;
        }
        let Some(tstone_index) = upper.find("TSTONEFILE") else {
            output.extend(
                lines[line_index..end_index]
                    .iter()
                    .map(|line| (*line).to_owned()),
            );
            line_index = end_index;
            continue;
        };
        let Some(equal_offset) = normalized[tstone_index..].find('=') else {
            output.extend(
                lines[line_index..end_index]
                    .iter()
                    .map(|line| (*line).to_owned()),
            );
            line_index = end_index;
            continue;
        };
        let equal = tstone_index + equal_offset;
        let file_token = normalized[equal + 1..]
            .split_whitespace()
            .next()
            .unwrap_or("")
            .trim_matches(['\'', '"', ',', ')']);
        let touchstone = source_dir.join(file_token);
        let fields = tokens(&normalized)
            .into_iter()
            .filter(|field| field != "+")
            .collect::<Vec<_>>();
        let nodes = fields
            .iter()
            .skip(1)
            .take_while(|field| !field.contains('='))
            .cloned()
            .collect::<Vec<_>>();
        let Some(ports) = touchstone_port_count(&touchstone) else {
            unsupported.push(UnsupportedIssue {
                line: raw.trim().to_owned(),
                reason: "touchstone_port_count_is_invalid".to_owned(),
            });
            output.extend(
                lines[line_index..end_index]
                    .iter()
                    .map(|line| (*line).to_owned()),
            );
            line_index = end_index;
            continue;
        };
        if nodes.len() != ports + 1 || nodes.last().is_none_or(|value| value != "0") {
            unsupported.push(UnsupportedIssue {
                line: raw.trim().to_owned(),
                reason: "touchstone_s_element_requires_common_ground_reference".to_owned(),
            });
            output.extend(
                lines[line_index..end_index]
                    .iter()
                    .map(|line| (*line).to_owned()),
            );
            line_index = end_index;
            continue;
        }
        if !touchstone.is_file() {
            unsupported.push(UnsupportedIssue {
                line: raw.trim().to_owned(),
                reason: "touchstone_file_not_found".to_owned(),
            });
            output.extend(
                lines[line_index..end_index]
                    .iter()
                    .map(|line| (*line).to_owned()),
            );
            line_index = end_index;
            continue;
        }
        // The pinned Python workflow has no portable S-domain exporter for
        // an HSPICE `S` element.  Do not silently substitute AS-03's Y fit:
        // that changes the element's semantics and can produce a plausible
        // but incorrect transient deck.  Preserve the source line and make
        // the unsupported boundary explicit.
        unsupported.push(UnsupportedIssue {
            line: raw.trim().to_owned(),
            reason: "touchstone_s_element_s_domain_exporter_unavailable".to_owned(),
        });
        output.extend(
            lines[line_index..end_index]
                .iter()
                .map(|line| (*line).to_owned()),
        );
        line_index = end_index;
    }
    Ok((
        format!("{}\n", output.join("\n").trim()),
        actions,
        unsupported,
    ))
}

fn prepare_case(case: DeckCase, backend: Backend) -> PreparedCase {
    let audit = audit_deck(&case.text);
    let dependencies = audit
        .includes
        .iter()
        .cloned()
        .chain(audit.libraries.iter().map(|library| library.path.clone()))
        .map(|reference| DependencyReference {
            admission: classify_dependency(&reference),
            reference,
        })
        .collect::<Vec<_>>();
    let (deck_text, actions, unsupported) = convert_deck(&case.text, backend);
    let mut output_paths = vec![
        format!("{}/case.cir", case.name),
        format!("{}/case.source.sp", case.name),
        format!("{}/compat_report.json", case.name),
    ];
    if backend == Backend::XyceXdm {
        output_paths.push(format!("{}/case.sp", case.name));
    }
    let status = if !audit.unsupported_directives.is_empty()
        || !unsupported.is_empty()
        || dependencies.iter().any(|dependency| {
            dependency.admission != DependencyAdmission::RelativeRequiresSourceRoot
        }) {
        PreparationStatus::Blocked
    } else if actions.is_empty() {
        PreparationStatus::Compatible
    } else {
        PreparationStatus::AutoConverted
    };
    PreparedCase {
        case,
        deck_text,
        audit,
        dependencies,
        actions,
        unsupported,
        preparation_status: status,
        output_paths,
    }
}

/// Mirrors `split_alter_cases` from the pinned Python object, including its
/// permissive `.alter*` prefix and missing-`.end` behavior.
pub fn split_alter_cases(text: &str, stem: &str) -> Vec<DeckCase> {
    let mut base = Vec::<String>::new();
    let mut alters = Vec::<(String, Vec<String>)>::new();
    let mut current_header: Option<String> = None;
    let mut current_lines = Vec::<String>::new();
    let mut end_line: Option<String> = None;
    for line in text.lines() {
        let stripped = line.trim();
        if stripped.eq_ignore_ascii_case(".end") {
            end_line = Some(stripped.to_owned());
            continue;
        }
        if stripped.to_ascii_lowercase().starts_with(".alter") {
            if let Some(header) = current_header.take() {
                alters.push((header, std::mem::take(&mut current_lines)));
            }
            current_header = Some(stripped.to_owned());
            continue;
        }
        if current_header.is_none() {
            base.push(line.to_owned());
        } else {
            current_lines.push(line.to_owned());
        }
    }
    if let Some(header) = current_header {
        alters.push((header, current_lines));
    }
    let base_text = case_text(&base, end_line.as_deref());
    let mut cases = vec![DeckCase {
        name: format!("{stem}__base"),
        text: base_text.clone(),
        kind: CaseKind::Base,
    }];
    for (index, (header, body)) in alters.into_iter().enumerate() {
        let suffix = case_suffix(&header, index + 1);
        let name = format!("{stem}__{suffix}");
        cases.push(DeckCase {
            name,
            text: case_text(&[base.clone(), body].concat(), end_line.as_deref()),
            kind: CaseKind::Alter,
        });
    }
    cases
}

fn case_text(lines: &[String], end_line: Option<&str>) -> String {
    let body = lines.join("\n").trim().to_owned();
    let body = match end_line {
        Some(end) if body.is_empty() => end.to_owned(),
        Some(end) => format!("{body}\n{end}"),
        None => body,
    };
    format!("{body}\n")
}

fn case_suffix(header: &str, index: usize) -> String {
    let mut words = header.split_whitespace();
    let _directive = words.next();
    let label = words.collect::<Vec<_>>().join(" ");
    if label.is_empty() {
        return format!("alter_{index:03}");
    }
    let mut sanitized = label
        .chars()
        .map(|character| {
            if character.is_ascii_alphanumeric() || character == '_' {
                character.to_ascii_lowercase()
            } else {
                '_'
            }
        })
        .collect::<String>();
    while sanitized.starts_with('_') {
        sanitized.remove(0);
    }
    while sanitized.ends_with('_') {
        sanitized.pop();
    }
    if sanitized.is_empty() {
        format!("alter_{index:03}")
    } else {
        format!("alter_{index:03}_{sanitized}")
    }
}

fn strip_hspice_comment(line: &str) -> String {
    let mut quote = None;
    for (index, character) in line.char_indices() {
        if matches!(character, '\'' | '"') && quote.is_none() {
            quote = Some(character);
        } else if quote == Some(character) {
            quote = None;
        } else if character == '$' && quote.is_none() {
            return line[..index].to_owned();
        }
    }
    line.to_owned()
}

fn logical_lines(text: &str) -> Vec<String> {
    let mut lines = Vec::new();
    let mut current = String::new();
    for raw in text.lines() {
        let stripped = strip_hspice_comment(raw).trim().to_owned();
        if stripped.is_empty() || stripped.starts_with('*') {
            continue;
        }
        if let Some(rest) = stripped.strip_prefix('+') {
            current.push(' ');
            current.push_str(rest.trim());
        } else {
            if !current.is_empty() {
                lines.push(std::mem::take(&mut current));
            }
            current = stripped;
        }
    }
    if !current.is_empty() {
        lines.push(current);
    }
    lines
}

fn tokens(line: &str) -> Vec<String> {
    let characters = line.chars().collect::<Vec<_>>();
    let mut output = Vec::new();
    let mut cursor = 0;
    while cursor < characters.len() {
        while cursor < characters.len() && characters[cursor].is_whitespace() {
            cursor += 1;
        }
        if cursor == characters.len() {
            break;
        }
        let start = cursor;
        if matches!(characters[cursor], '\'' | '"') {
            let quote = characters[cursor];
            cursor += 1;
            while cursor < characters.len() {
                let character = characters[cursor];
                cursor += 1;
                if character == quote {
                    break;
                }
            }
        } else {
            while cursor < characters.len() && !characters[cursor].is_whitespace() {
                cursor += 1;
            }
        }
        output.push(characters[start..cursor].iter().collect());
    }
    output
}

fn clean_path(token: &str) -> String {
    token.trim_matches(['\'', '"']).to_owned()
}

/// Mirrors the upstream directive, include, library, and unsupported audit.
pub fn audit_deck(text: &str) -> DeckAudit {
    let supported = SUPPORTED_DIRECTIVES
        .iter()
        .copied()
        .collect::<BTreeSet<_>>();
    let mut directive_counts = BTreeMap::new();
    let mut includes = Vec::new();
    let mut libraries = Vec::new();
    let mut unsupported_directives = Vec::new();
    for line in logical_lines(text) {
        if !line.starts_with('.') {
            continue;
        }
        let fields = tokens(&line);
        let Some(directive) = fields.first().map(|field| field.to_ascii_lowercase()) else {
            continue;
        };
        *directive_counts.entry(directive.clone()).or_insert(0) += 1;
        if matches!(directive.as_str(), ".include" | ".inc") && fields.len() >= 2 {
            includes.push(clean_path(&fields[1]));
        }
        if directive == ".lib" && fields.len() >= 2 {
            libraries.push(LibraryReference {
                path: clean_path(&fields[1]),
                section: fields.get(2).map(|field| clean_path(field)),
            });
        }
        if !supported.contains(directive.as_str()) {
            unsupported_directives.push(directive);
        }
    }
    DeckAudit {
        directive_counts,
        includes,
        libraries,
        unsupported_directives,
    }
}

fn classify_dependency(reference: &str) -> DependencyAdmission {
    let path = Path::new(reference);
    if path.is_absolute() {
        return DependencyAdmission::AbsoluteNotStaged;
    }
    if path
        .components()
        .next()
        .is_some_and(|component| matches!(component, std::path::Component::ParentDir))
    {
        return DependencyAdmission::LexicallyEscapesSourceRoot;
    }
    DependencyAdmission::RelativeRequiresSourceRoot
}

fn has_post_option(line: &str) -> bool {
    let fields = tokens(line);
    fields
        .first()
        .is_some_and(|field| field.eq_ignore_ascii_case(".option"))
        && fields[1..].iter().any(|field| {
            field.eq_ignore_ascii_case("post") || field.to_ascii_lowercase().starts_with("post=")
        })
}

const PWL_TIME_UNITS: [(&str, f64); 6] = [
    ("fs", 1e-15),
    ("ps", 1e-12),
    ("ns", 1e-9),
    ("us", 1e-6),
    ("ms", 1e-3),
    ("s", 1.0),
];

fn parse_pwl_time(token: &str) -> Option<(f64, String)> {
    let lower = token.to_ascii_lowercase();
    for (unit, scale) in PWL_TIME_UNITS {
        if let Some(number) = lower.strip_suffix(unit) {
            if number.is_empty()
                || !number
                    .chars()
                    .all(|character| character.is_ascii_digit() || ".eE+-".contains(character))
            {
                continue;
            }
            let seconds = number.parse::<f64>().ok()? * scale;
            return Some((seconds, unit.to_owned()));
        }
    }
    None
}

fn is_pwl_value(token: &str) -> bool {
    !token.is_empty()
        && token
            .chars()
            .all(|character| character.is_ascii_digit() || ".eE+-".contains(character))
}

fn parse_pwl_points(text: &str) -> Vec<(f64, String)> {
    let fields = text.split_whitespace().collect::<Vec<_>>();
    let mut points = Vec::new();
    for pair in fields.windows(2) {
        let Some((seconds, _unit)) = parse_pwl_time(pair[0]) else {
            continue;
        };
        if is_pwl_value(pair[1]) {
            points.push((seconds, pair[1].to_owned()));
        }
    }
    points
}

fn parse_repeat_line(line: &str) -> Option<(f64, String, Option<String>)> {
    let trimmed = line.trim_start();
    let remainder = trimmed.strip_prefix('+')?.trim_start();
    let remainder_lower = remainder.to_ascii_lowercase();
    let mut cursor = 0;
    if !remainder_lower[cursor..].starts_with('r') {
        return None;
    }
    cursor += 1;
    while remainder
        .as_bytes()
        .get(cursor)
        .is_some_and(u8::is_ascii_whitespace)
    {
        cursor += 1;
    }
    if remainder.as_bytes().get(cursor) != Some(&b'=') {
        return None;
    }
    cursor += 1;
    while remainder
        .as_bytes()
        .get(cursor)
        .is_some_and(u8::is_ascii_whitespace)
    {
        cursor += 1;
    }
    let number_start = cursor;
    while remainder.as_bytes().get(cursor).is_some_and(|character| {
        character.is_ascii_digit() || matches!(character, b'.' | b'e' | b'E' | b'+' | b'-')
    }) {
        cursor += 1;
    }
    if cursor == number_start {
        return None;
    }
    let number_text = remainder.get(number_start..cursor)?.to_owned();
    let number = number_text.parse::<f64>().ok()?;
    let unit_start = cursor;
    while remainder
        .as_bytes()
        .get(cursor)
        .is_some_and(u8::is_ascii_alphabetic)
    {
        cursor += 1;
    }
    let unit = remainder.get(unit_start..cursor)?;
    let scale = PWL_TIME_UNITS
        .iter()
        .find(|(candidate, _)| candidate.eq_ignore_ascii_case(unit))
        .map(|(_, scale)| *scale)?;
    while remainder
        .as_bytes()
        .get(cursor)
        .is_some_and(u8::is_ascii_whitespace)
    {
        cursor += 1;
    }
    if remainder.as_bytes().get(cursor) != Some(&b')') {
        return None;
    }
    cursor += 1;
    while remainder
        .as_bytes()
        .get(cursor)
        .is_some_and(u8::is_ascii_whitespace)
    {
        cursor += 1;
    }
    let multiplicity = if remainder_lower[cursor..].starts_with('m') {
        cursor += 1;
        while remainder
            .as_bytes()
            .get(cursor)
            .is_some_and(u8::is_ascii_whitespace)
        {
            cursor += 1;
        }
        if remainder.as_bytes().get(cursor) != Some(&b'=') {
            return None;
        }
        cursor += 1;
        while remainder
            .as_bytes()
            .get(cursor)
            .is_some_and(u8::is_ascii_whitespace)
        {
            cursor += 1;
        }
        let value_start = cursor;
        while remainder
            .as_bytes()
            .get(cursor)
            .is_some_and(|character| !character.is_ascii_whitespace())
        {
            cursor += 1;
        }
        Some(remainder.get(value_start..cursor)?.to_owned())
    } else {
        None
    };
    if !remainder[cursor..].trim().is_empty() {
        return None;
    }
    Some((number * scale, format!("{number_text}{unit}"), multiplicity))
}

fn current_pwl_open(line: &str) -> Option<usize> {
    if !line.starts_with(['I', 'i']) {
        return None;
    }
    let first_space = line.find(char::is_whitespace)?;
    if first_space <= 1 {
        return None;
    }
    let lower = line.to_ascii_lowercase();
    let pwl = lower.rfind("pwl")?;
    if pwl > 0 && line.as_bytes()[pwl - 1].is_ascii_alphanumeric() {
        return None;
    }
    let mut open = pwl + 3;
    while line
        .as_bytes()
        .get(open)
        .is_some_and(u8::is_ascii_whitespace)
    {
        open += 1;
    }
    if line.as_bytes().get(open) != Some(&b'(') {
        return None;
    }
    Some(open)
}

fn format_pwl_number(value: f64) -> String {
    if value == 0.0 {
        return "0".to_owned();
    }
    let absolute = value.abs();
    if (1e-4..1e6).contains(&absolute) {
        let exponent = absolute.log10().floor() as i32;
        let decimals = (5 - exponent).max(0) as usize;
        let mut result = format!("{:.*}", decimals, value);
        while result.ends_with('0') {
            result.pop();
        }
        if result.ends_with('.') {
            result.pop();
        }
        return result;
    }
    let scientific = format!("{value:.5e}");
    let (mantissa, exponent) = scientific
        .split_once('e')
        .expect("Rust scientific formatting includes an exponent");
    let mut mantissa = mantissa
        .trim_end_matches('0')
        .trim_end_matches('.')
        .to_owned();
    if mantissa == "-0" {
        mantissa = "0".to_owned();
    }
    let exponent = exponent.parse::<i32>().expect("Rust exponent is numeric");
    format!("{mantissa}e{exponent:+03}")
}

fn rewrite_current_pwl_source(
    group: &str,
    repeat_start: f64,
    repeat_end: f64,
    points: &[(f64, String)],
    multiplicity: Option<&str>,
) -> String {
    let mut source = group.to_owned();
    source.replace_range(0..1, "B");
    let lower = source.to_ascii_lowercase();
    let open = source
        .rfind('(')
        .expect("current PWL group has an opening parenthesis");
    let pwl = lower[..open]
        .rfind("pwl")
        .expect("current PWL group has a PWL function");
    let multiplier = multiplicity.map_or_else(String::new, |value| format!("({value}) * "));
    source.replace_range(pwl..open + 1, &format!("I = {multiplier}pwl("));
    let start = format_pwl_number(repeat_start / 1e-12);
    let period = format_pwl_number((repeat_end - repeat_start) / 1e-12);
    let mut lines = vec![format!(
        "{source}(time <= {start}ps ? time : {start}ps + (time - {start}ps) - {period}ps * floor((time - {start}ps) / {period}ps)),"
    )];
    for (chunk_index, chunk) in points.chunks(4).enumerate() {
        let values = chunk
            .iter()
            .map(|(seconds, value)| format!("{}ps, {value}", format_pwl_number(seconds / 1e-12)))
            .collect::<Vec<_>>()
            .join(", ");
        let suffix = if (chunk_index + 1) * 4 >= points.len() {
            ""
        } else {
            ","
        };
        lines.push(format!("+ {values}{suffix}"));
    }
    lines.push("+ )".to_owned());
    lines.join("\n")
}

fn rewrite_current_pwl_repeats_for_ngspice(
    text: &str,
    actions: &mut Vec<ConversionAction>,
    unsupported: &mut Vec<UnsupportedIssue>,
) -> String {
    let lines = text.split_inclusive('\n').collect::<Vec<_>>();
    let mut output = String::new();
    let mut index = 0;
    while index < lines.len() {
        let raw_line = lines[index];
        let line = raw_line.trim_end_matches(['\r', '\n']);
        let Some(open) = current_pwl_open(line) else {
            output.push_str(raw_line);
            index += 1;
            continue;
        };
        let mut point_text = line[open + 1..].to_owned();
        let mut repeat = None;
        let mut end_index = index + 1;
        while end_index < lines.len() {
            let candidate = lines[end_index].trim_end_matches(['\r', '\n']);
            if let Some(parsed) = parse_repeat_line(candidate) {
                repeat = Some(parsed);
                break;
            }
            point_text.push(' ');
            point_text.push_str(candidate);
            end_index += 1;
        }
        let Some((repeat_start, repeat_text, multiplicity)) = repeat else {
            output.push_str(raw_line);
            index += 1;
            continue;
        };
        let points = parse_pwl_points(&point_text);
        let first_line = line.to_owned();
        let repeat_end = points.last().map(|(seconds, _)| *seconds);
        if !points
            .iter()
            .any(|(seconds, _)| (*seconds - repeat_start).abs() <= 1e-18)
        {
            unsupported.push(UnsupportedIssue {
                line: first_line,
                reason: "current_pwl_repeat_point_not_found".to_owned(),
            });
            output.push_str(raw_line);
            index += 1;
            continue;
        }
        let Some(repeat_end) = repeat_end else {
            unsupported.push(UnsupportedIssue {
                line: first_line,
                reason: "current_pwl_repeat_point_not_found".to_owned(),
            });
            output.push_str(raw_line);
            index += 1;
            continue;
        };
        if repeat_end <= repeat_start {
            unsupported.push(UnsupportedIssue {
                line: first_line,
                reason: "invalid_current_pwl_repeat_window".to_owned(),
            });
            output.push_str(raw_line);
            index += 1;
            continue;
        }
        let group = &line[..open + 1];
        let converted = rewrite_current_pwl_source(
            group,
            repeat_start,
            repeat_end,
            &points,
            multiplicity.as_deref(),
        );
        actions.push(ConversionAction {
            kind: "rewrite_current_pwl_repeat".to_owned(),
            source: format!("{}... R={repeat_text}", group.trim()),
            target: format!(
                "behavioral current PWL: repeat {}ps to {}ps{}",
                format_pwl_number(repeat_start / 1e-12),
                format_pwl_number(repeat_end / 1e-12),
                multiplicity
                    .as_deref()
                    .map_or(String::new(), |value| format!("; preserves M={value}"))
            ),
        });
        output.push_str(&converted);
        if lines[end_index].ends_with('\n') {
            output.push('\n');
        }
        index = end_index + 1;
    }
    output
}

/// Mirrors the deterministic text conversions in `convert_hspice_deck`.
pub(crate) fn convert_deck(
    text: &str,
    backend: Backend,
) -> (String, Vec<ConversionAction>, Vec<UnsupportedIssue>) {
    if backend != Backend::Ngspice {
        return (text.to_owned(), Vec::new(), Vec::new());
    }
    let mut actions = Vec::new();
    let mut unsupported = Vec::new();
    let source_text = rewrite_current_pwl_repeats_for_ngspice(text, &mut actions, &mut unsupported);
    let mut output = Vec::new();
    for raw in source_text.lines() {
        let stripped = raw.trim();
        let lower = stripped.to_ascii_lowercase();
        if lower.starts_with(".inc ") {
            let target = format!(
                ".include {}",
                stripped
                    .split_once(char::is_whitespace)
                    .map_or("", |(_, rest)| rest)
            );
            actions.push(ConversionAction {
                kind: "rewrite".to_owned(),
                source: stripped.to_owned(),
                target: target.clone(),
            });
            output.push(target);
        } else if lower.starts_with(".probe ") {
            let target = format!(
                ".print {}",
                stripped
                    .split_once(char::is_whitespace)
                    .map_or("", |(_, rest)| rest)
            );
            actions.push(ConversionAction {
                kind: "rewrite".to_owned(),
                source: stripped.to_owned(),
                target: target.clone(),
            });
            output.push(target);
        } else if has_post_option(stripped) {
            actions.push(ConversionAction {
                kind: "drop_option".to_owned(),
                source: stripped.to_owned(),
                target: String::new(),
            });
        } else {
            output.push(raw.to_owned());
        }
    }
    let deck_text = format!("{}\n", output.join("\n").trim());
    (deck_text, actions, unsupported)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn all_backend_and_execute_branches_are_explicit() {
        for backend in Backend::ALL {
            for execute in [false, true] {
                let request = RunHspiceRequest::new(backend.name(), "runs", execute).unwrap();
                let admission = admit_run_hspice("demo", ".tran 1p 1n\n.end\n", request).unwrap();
                assert_eq!(admission.backend, backend);
                assert_eq!(admission.execute, execute);
                assert_eq!(
                    admission.execution_stage,
                    match (backend, execute) {
                        (_, false) => ExecutionStage::NotExecuted,
                        (Backend::Native, true) => ExecutionStage::NativeEngine,
                        (Backend::Ngspice, true) => ExecutionStage::Ngspice,
                        (Backend::Xyce, true) => ExecutionStage::Xyce,
                        (Backend::XyceXdm, true) => ExecutionStage::XdmThenXyce,
                    }
                );
            }
        }
    }

    #[test]
    fn alter_split_matches_pinned_case_names_and_end_ownership() {
        let cases = split_alter_cases(
            ".param c=1u\n.tran 1p 1n\n.alter high decap\n.param c=2u\n.alter slow\n.param c=3u\n.end\n",
            "deck",
        );
        assert_eq!(
            cases
                .iter()
                .map(|case| case.name.as_str())
                .collect::<Vec<_>>(),
            [
                "deck__base",
                "deck__alter_001_high_decap",
                "deck__alter_002_slow"
            ]
        );
        assert!(cases.iter().all(|case| case.text.ends_with(".end\n")));
        assert!(cases[1].text.contains(".param c=2u"));
        assert!(!cases[1].text.contains(".param c=3u"));
    }

    #[test]
    fn audit_and_ngspice_conversion_cover_includes_libs_measure_and_actions() {
        let source = ".inc 'models.inc'\n.lib './corners.lib' tt\n.probe tran v(out)\n.measure tran m max v(out)\n.option post=2\n.end\n";
        let audit = audit_deck(source);
        assert_eq!(audit.includes, ["models.inc"]);
        assert_eq!(audit.libraries[0].path, "./corners.lib");
        assert_eq!(audit.directive_counts[".measure"], 1);
        let admission = admit_run_hspice(
            "deck",
            source,
            RunHspiceRequest::new("ngspice", "runs", false).unwrap(),
        )
        .unwrap();
        assert_eq!(
            admission.cases[0].preparation_status,
            PreparationStatus::AutoConverted
        );
        assert!(
            admission.cases[0]
                .deck_text
                .contains(".include 'models.inc'")
        );
        assert!(admission.cases[0].deck_text.contains(".print tran v(out)"));
        assert!(!admission.cases[0].deck_text.contains("post=2"));
    }

    #[test]
    fn normalized_outputs_match_pinned_hspice_measure_contract() {
        let source = concat!(
            ".probe tran v(out) i(v1)\n",
            ".print ac vm(out)\n",
            ".measure tran m max v(out) from=1n to=2n\n",
            ".meas op p PARAM='v(out)'\n",
            ".measure op q PARAM = sqrt(v(out))\n",
        );
        assert_eq!(
            output_probes(source),
            vec![
                "v(out)".to_owned(),
                "i(v1)".to_owned(),
                "vm(out)".to_owned()
            ]
        );
        let measures = output_measures(source);
        assert_eq!(measures.len(), 3);
        assert_eq!(measures[0]["analysis"], "tran");
        assert_eq!(measures[0]["name"], "m");
        assert_eq!(measures[0]["operation"], "max");
        assert_eq!(measures[0]["target"], "v(out)");
        assert_eq!(measures[1]["operation"], "param");
        assert_eq!(measures[1]["target"], "'v(out)'");
        assert_eq!(measures[2]["target"], "sqrt(v(out))");
    }

    #[test]
    fn ngspice_s_element_parser_consumes_continuation_lines() {
        let root = std::env::temp_dir().join(format!("sipi-as05-s-cont-{}", std::process::id()));
        let run = root.join("run");
        fs::create_dir_all(&run).unwrap();
        let (prepared, actions, unsupported) = compile_touchstone_s_elements(
            "Sfoo p1 p2 0\n+ TSTONEFILE='missing.s2p'\n.end\n",
            &root,
            &run,
        )
        .unwrap();
        assert!(actions.is_empty());
        assert_eq!(unsupported[0].reason, "touchstone_file_not_found");
        assert!(prepared.contains("+ TSTONEFILE='missing.s2p'"));
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn ngspice_result_helpers_parse_measurements_and_waveforms() {
        let root = std::env::temp_dir().join(format!("sipi-as05-results-{}", std::process::id()));
        fs::create_dir_all(&root).unwrap();
        let transcript = "m_rms = 1.25e-3 at=2e-9\nIndex time v(out)\n0 0 1\n1 1e-9 2\n";
        let measurements = parse_ngspice_measurements(transcript);
        assert_eq!(measurements[0]["name"], "m_rms");
        assert_eq!(measurements[0]["at"], 2e-9);
        let path = root.join("waveform.csv");
        assert_eq!(write_ngspice_waveform_csv(transcript, &path), 2);
        assert!(
            fs::read_to_string(path)
                .unwrap()
                .starts_with("time,v(out)\n")
        );
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn ngspice_touchstone_s_element_fails_closed_without_s_domain_exporter() {
        let root = std::env::temp_dir().join(format!("sipi-as05-sparam-{}", std::process::id()));
        fs::create_dir_all(&root).unwrap();
        let mut s2p = String::from("# Hz S RI R 50\n");
        for index in 0..20 {
            let frequency = 1.0e6 * (index + 1) as f64;
            s2p.push_str(&format!("{frequency:.0} 0.01 0 0.8 0 0.8 0 0.01 0\n"));
        }
        fs::write(root.join("line.s2p"), s2p).unwrap();
        let deck = root.join("two.sp");
        fs::write(&deck, "Sfoo p1 p2 0\n+ TSTONEFILE='line.s2p'\n.end\n").unwrap();
        let request = RunHspiceRequest::new("ngspice", root.join("two-out"), false).unwrap();
        let result = run_hspice(&deck, request).unwrap();
        assert_eq!(result.status, PreparationStatus::Blocked);
        let report =
            fs::read_to_string(root.join("two-out/two/two__base/compat_report.json")).unwrap();
        assert!(report.contains("touchstone_s_element_s_domain_exporter_unavailable"));
        assert!(
            !root
                .join("two-out/two/two__base/sparam/Sfoo.y.sp")
                .is_file()
        );

        let values = "0 ".repeat(18);
        let mut s3p = String::from("# GHz S RI R 50\n");
        for index in 0..12 {
            s3p.push_str(&format!("{} {values}\n", 0.1 + index as f64 * 0.05));
        }
        fs::write(root.join("network.s3p"), s3p).unwrap();
        let deck = root.join("three.sp");
        fs::write(&deck, "Sfoo p1 p2 p3 0\n+ TSTONEFILE='network.s3p'\n.end\n").unwrap();
        let request = RunHspiceRequest::new("ngspice", root.join("three-out"), false).unwrap();
        let result = run_hspice(&deck, request).unwrap();
        assert_eq!(result.status, PreparationStatus::Blocked);
        let report =
            fs::read_to_string(root.join("three-out/three/three__base/compat_report.json"))
                .unwrap();
        assert!(report.contains("touchstone_s_element_s_domain_exporter_unavailable"));
        assert!(
            !root
                .join("three-out/three/three__base/sparam/Sfoo.y.sp")
                .is_file()
        );
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn unsupported_directive_is_reported_without_silent_deletion() {
        let admission = admit_run_hspice(
            "deck",
            ".fft v(out)\n.end\n",
            RunHspiceRequest::new("native", "runs", false).unwrap(),
        )
        .unwrap();
        assert_eq!(
            admission.cases[0].preparation_status,
            PreparationStatus::Blocked
        );
        assert_eq!(admission.cases[0].audit.unsupported_directives, [".fft"]);
        assert!(admission.cases[0].deck_text.contains(".fft v(out)"));
    }

    #[test]
    fn model_and_endcomment_are_audited_without_hard_blocking() {
        let audit = audit_deck(
            ".model sw sw(Ron=1 Roff=2)\n.endcomment preserved by source audit\n.end*comment preserved by source audit\n.end\n",
        );
        assert!(audit.unsupported_directives.is_empty());
        assert_eq!(audit.directive_counts[".model"], 1);
        assert_eq!(audit.directive_counts[".endcomment"], 1);
        assert_eq!(audit.directive_counts[".end*comment"], 1);
    }

    #[test]
    fn xdm_plan_contains_two_stage_case_artifact() {
        let admission = admit_run_hspice(
            "deck",
            ".end\n",
            RunHspiceRequest::new("xyce-xdm", "runs", true).unwrap(),
        )
        .unwrap();
        assert!(
            admission.cases[0]
                .output_paths
                .iter()
                .any(|path| path.ends_with("/case.sp"))
        );
        assert_eq!(admission.execution_stage, ExecutionStage::XdmThenXyce);
        assert!(admission.external_solver_required);
        assert_eq!(admission.numerical_parity, ParityStatus::NotEvaluated);
    }

    #[test]
    fn invalid_backend_and_empty_stem_fail_closed() {
        assert_eq!(
            RunHspiceRequest::new("hspice", "runs", false).unwrap_err(),
            DirectPortError::UnsupportedBackend("hspice".to_owned())
        );
        assert_eq!(
            admit_run_hspice(
                "",
                ".end\n",
                RunHspiceRequest::new("native", "runs", false).unwrap()
            )
            .unwrap_err(),
            DirectPortError::EmptyDeckStem
        );
    }

    #[test]
    fn file_runner_requires_explicit_native_engine_before_execution() {
        let root = std::env::temp_dir().join(format!("sipi-as05-run-{}", std::process::id()));
        fs::create_dir_all(&root).unwrap();
        let deck = root.join("deck.sp");
        fs::write(&deck, ".tran 1p 1n\n.end\n").unwrap();
        let request = RunHspiceRequest::new("native", root.join("out"), true).unwrap();
        let result = run_hspice(&deck, request);
        assert!(matches!(
            result,
            Err(DirectPortError::UnsupportedExecution(_))
        ));
        assert!(!root.join("out").exists());
        assert!(!root.join("out/deck/deck__base/native_result.json").exists());
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn execute_never_resolves_fake_path_or_alias_executables() {
        let root = std::env::temp_dir().join(format!("sipi-as05-custody-{}", std::process::id()));
        let request = RunHspiceRequest::new("native", root.join("out"), true)
            .unwrap()
            .with_native_engine(root.join("alias.exe"));
        let result = run_hspice(root.join("deck.sp"), request);
        assert!(
            matches!(result, Err(DirectPortError::UnsupportedExecution(message)) if message.contains("custody"))
        );
        assert!(!root.join("out").exists());
    }

    #[test]
    fn file_runner_stages_recursive_dependencies_and_hashes_compatibility() {
        let root = std::env::temp_dir().join(format!("sipi-as05-deps-{}", std::process::id()));
        fs::create_dir_all(root.join("models")).unwrap();
        fs::write(
            root.join("models/top.inc"),
            ".include 'nested.inc'\n.param x=1\n",
        )
        .unwrap();
        fs::write(root.join("models/nested.inc"), ".param y=2\n").unwrap();
        let deck = root.join("deck.sp");
        fs::write(&deck, ".include 'models/top.inc'\n.tran 1p 1n\n.end\n").unwrap();
        let request = RunHspiceRequest::new("native", root.join("out"), false).unwrap();
        run_hspice(&deck, request).unwrap();
        let case_root = root.join("out/deck/deck__base");
        assert!(case_root.join("models/top.inc").is_file());
        assert!(case_root.join("models/nested.inc").is_file());
        let report: serde_json::Value =
            serde_json::from_slice(&fs::read(case_root.join("compat_report.json")).unwrap())
                .unwrap();
        assert_eq!(report["schema_version"], 2);
        assert!(report["deck"]["sha256"].as_str().is_some());
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn ngspice_dependency_staging_converts_nested_decks() {
        let root = std::env::temp_dir().join(format!("sipi-as05-ng-deps-{}", std::process::id()));
        fs::create_dir_all(root.join("models")).unwrap();
        fs::write(
            root.join("models/top.inc"),
            ".include 'nested.inc'\n.probe tran v(out)\n.option post=2\n",
        )
        .unwrap();
        fs::write(root.join("models/nested.inc"), ".param y=2\n").unwrap();
        let deck = root.join("deck.sp");
        fs::write(&deck, ".inc 'models/top.inc'\n.tran 1p 1n\n.end\n").unwrap();
        let request = RunHspiceRequest::new("ngspice", root.join("out"), false).unwrap();
        let result = run_hspice(&deck, request).unwrap();
        assert_eq!(result.status, PreparationStatus::AutoConverted);
        let case_root = root.join("out/deck/deck__base");
        let nested = fs::read_to_string(case_root.join("models/top.inc")).unwrap();
        assert!(nested.contains(".include 'nested.inc'"));
        assert!(nested.contains(".print tran v(out)"));
        assert!(!nested.contains("post=2"));
        let report: serde_json::Value =
            serde_json::from_slice(&fs::read(case_root.join("compat_report.json")).unwrap())
                .unwrap();
        assert!(
            report["actions"]
                .as_array()
                .unwrap()
                .iter()
                .any(|action| { action["source"] == ".probe tran v(out)" })
        );
        let _ = fs::remove_dir_all(root);
    }
}
