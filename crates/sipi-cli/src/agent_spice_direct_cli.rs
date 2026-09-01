//! Feature-gated typed argv boundary for the quarantined Agent-Spice leaves.
//!
//! The root CLI owns only this small adapter. Solver work is delegated to
//! sipi-agent-spice-direct through its Rust API; no Python interpreter or
//! standalone direct-port binary is started here. Paths are accepted as
//! inputs but never appear in the receipt or in an error diagnostic.

use std::fs;
use std::path::{Path, PathBuf};

use serde::Serialize;
use sha2::{Digest, Sha256};
use sipi_agent_spice_direct::as06_run_rfm::{
    RfmBackend, RfmError, RfmNativeCustody, RfmNgspiceCustody, RunRfmRequest,
    run_rfm_with_native_custody, run_rfm_with_ngspice_custody,
};
use sipi_agent_spice_direct::{
    Backend, DirectPortError, NgspiceCustody, RunHspiceRequest, run_hspice,
    run_hspice_with_ngspice_custody,
};

/// Stable receipt schema emitted by the two retained direct Agent-Spice routes.
pub(crate) const AGENT_SPICE_DIRECT_RECEIPT_SCHEMA_V1: &str =
    "sipi.agent-spice.direct-cli-receipt.v1";

const MAX_RECEIPT_ARTIFACT_BYTES: u64 = 16 * 1024 * 1024;

/// Stable root-CLI error classes. Contained direct-port diagnostics are
/// deliberately not forwarded because they can contain host paths or child
/// process text.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum AgentSpiceDirectCliError {
    Usage,
    InvalidInput,
    Unsupported,
    OperationalFailure,
    ReceiptSerialization,
}

impl AgentSpiceDirectCliError {
    pub(crate) const fn exit_code(self) -> i32 {
        match self {
            Self::Usage | Self::InvalidInput | Self::ReceiptSerialization => 2,
            Self::Unsupported => 4,
            Self::OperationalFailure => 1,
        }
    }

    pub(crate) const fn diagnostic_code(self) -> &'static str {
        match self {
            Self::Usage => "usage",
            Self::InvalidInput => "invalid_input",
            Self::Unsupported => "unsupported",
            Self::OperationalFailure => "operational_failure",
            Self::ReceiptSerialization => "internal_contract_error",
        }
    }
}

/// The two explicitly retained Agent-Spice workflow names.
#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
pub(crate) enum AgentSpiceWorkflow {
    #[serde(rename = "run-hspice")]
    RunHspice,
    #[serde(rename = "run-rfm")]
    RunRfm,
}

/// Backend identity included in a path-free receipt.
#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
pub(crate) enum AgentSpiceBackend {
    #[serde(rename = "native")]
    Native,
    #[serde(rename = "ngspice")]
    Ngspice,
}

/// The upstream provenance frozen by the direct crate.
#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
pub(crate) struct UpstreamReceipt {
    pub repository: &'static str,
    pub commit: &'static str,
    pub tree: &'static str,
}

/// A content-addressed artifact identity without its host path.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub(crate) struct ArtifactReceipt {
    pub kind: ArtifactKind,
    pub byte_length: u64,
    pub sha256: String,
}

/// The only artifact kinds exposed by the direct CLI receipt.
#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
pub(crate) enum ArtifactKind {
    #[serde(rename = "report")]
    Report,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub(crate) struct RunHspiceSummary {
    pub case_count: usize,
    pub execution_returncodes: Vec<Option<i32>>,
    pub numerical_parity: &'static str,
}

#[derive(Clone, Debug, PartialEq, Serialize)]
pub(crate) struct RunRfmSummary {
    pub response_samples: usize,
    pub response_max_error: f64,
    pub nports: usize,
    pub response_count: usize,
    pub effective_order: usize,
    pub artifacts: Vec<ArtifactReceipt>,
}

/// Workflow-specific typed data; no untyped JSON object is used as a DTO.
#[derive(Clone, Debug, PartialEq, Serialize)]
#[serde(tag = "kind", content = "data")]
pub(crate) enum AgentSpiceDirectSummary {
    #[serde(rename = "run_hspice")]
    RunHspice(RunHspiceSummary),
    #[serde(rename = "run_rfm")]
    RunRfm(RunRfmSummary),
}

/// Path-free, versioned result envelope for the root CLI.
#[derive(Clone, Debug, PartialEq, Serialize)]
pub(crate) struct AgentSpiceDirectReceipt {
    pub schema: &'static str,
    pub workflow: AgentSpiceWorkflow,
    pub upstream: UpstreamReceipt,
    pub backend: AgentSpiceBackend,
    pub execute: bool,
    pub status: String,
    pub summary: AgentSpiceDirectSummary,
}

impl AgentSpiceDirectReceipt {
    pub(crate) fn to_json(&self) -> Result<String, AgentSpiceDirectCliError> {
        serde_json::to_string(self).map_err(|_| AgentSpiceDirectCliError::ReceiptSerialization)
    }
}

#[derive(Clone, Debug, PartialEq)]
pub(crate) enum AgentSpiceDirectRequest {
    RunHspice(RunHspiceCliRequest),
    RunRfm(RunRfmCliRequest),
}

#[derive(Clone, Debug, PartialEq)]
pub(crate) struct RunHspiceCliRequest {
    pub deck: PathBuf,
    pub request: RunHspiceRequest,
    pub ngspice: Option<PathBuf>,
    pub ngspice_sha256: Option<String>,
}

#[derive(Clone, Debug, PartialEq)]
pub(crate) struct RunRfmCliRequest {
    pub request: RunRfmRequest,
    pub native_engine_sha256: Option<String>,
    pub dotnet_sha256: Option<String>,
    pub ngspice_sha256: Option<String>,
    pub code_model_sha256: Option<String>,
}

/// Parse arguments beginning with one of run-hspice or run-rfm. Every
/// singleton option is rejected when repeated.
pub(crate) fn parse_agent_spice_direct_argv(
    arguments: &[String],
) -> Result<AgentSpiceDirectRequest, AgentSpiceDirectCliError> {
    let workflow = arguments.first().ok_or(AgentSpiceDirectCliError::Usage)?;
    match workflow.as_str() {
        "run-hspice" => parse_run_hspice(&arguments[1..]),
        "run-rfm" => parse_run_rfm(&arguments[1..]),
        _ => Err(AgentSpiceDirectCliError::Usage),
    }
}

/// Parse and execute one direct workflow through its Rust API.
pub(crate) fn execute_agent_spice_direct(
    arguments: &[String],
) -> Result<AgentSpiceDirectReceipt, AgentSpiceDirectCliError> {
    match parse_agent_spice_direct_argv(arguments)? {
        AgentSpiceDirectRequest::RunHspice(request) => execute_hspice(request),
        AgentSpiceDirectRequest::RunRfm(request) => execute_rfm(request),
    }
}

/// Parse, execute, and serialize one direct workflow.
pub(crate) fn execute_agent_spice_direct_json(
    arguments: &[String],
) -> Result<String, AgentSpiceDirectCliError> {
    execute_agent_spice_direct(arguments)?.to_json()
}

fn parse_run_hspice(
    arguments: &[String],
) -> Result<AgentSpiceDirectRequest, AgentSpiceDirectCliError> {
    let (positionals, mut index) = leading_positionals(arguments, 1)?;
    let deck = positionals[0].clone();
    let mut backend = None;
    let mut output_root = None;
    let mut execute = false;
    let mut rfm = None;
    let mut rfm_subckt = None;
    let mut ngspice = None;
    let mut ngspice_sha256 = None;

    while index < arguments.len() {
        let option = arguments[index].as_str();
        match option {
            "--backend" => set_once(
                &mut backend,
                parse_string_value(arguments, &mut index, option)?,
            )?,
            "--output-root" => set_once(
                &mut output_root,
                parse_path_value(arguments, &mut index, option)?,
            )?,
            "--execute" => {
                if execute {
                    return Err(AgentSpiceDirectCliError::Usage);
                }
                execute = true;
                index += 1;
            }
            "--native-engine" | "--dotnet" => {
                return Err(AgentSpiceDirectCliError::Unsupported);
            }
            "--rfm" => set_once(&mut rfm, parse_path_value(arguments, &mut index, option)?)?,
            "--rfm-subckt" => set_once(
                &mut rfm_subckt,
                parse_string_value(arguments, &mut index, option)?,
            )?,
            "--ngspice" => set_once(
                &mut ngspice,
                parse_absolute_executable(arguments, &mut index, option)?,
            )?,
            "--ngspice-sha256" => set_once(
                &mut ngspice_sha256,
                parse_sha256(arguments, &mut index, option)?,
            )?,
            _ => return Err(AgentSpiceDirectCliError::Usage),
        }
    }

    let backend = backend.ok_or(AgentSpiceDirectCliError::Usage)?;
    let output_root = output_root.ok_or(AgentSpiceDirectCliError::Usage)?;
    let backend_kind = parse_backend(&backend)?;
    if rfm.is_none() && rfm_subckt.is_some() {
        return Err(AgentSpiceDirectCliError::Usage);
    }
    if execute && backend_kind != Backend::Ngspice {
        return Err(AgentSpiceDirectCliError::Unsupported);
    }
    if ngspice.is_some() != ngspice_sha256.is_some() {
        return Err(AgentSpiceDirectCliError::Usage);
    }
    if execute && (ngspice.is_none() || ngspice_sha256.is_none()) {
        return Err(AgentSpiceDirectCliError::Usage);
    }
    if !execute && (ngspice.is_some() || ngspice_sha256.is_some()) {
        return Err(AgentSpiceDirectCliError::Usage);
    }

    let mut request =
        RunHspiceRequest::new(&backend, output_root, execute).map_err(map_direct_port_error)?;
    if let Some(rfm) = rfm {
        request = request.with_rfm(rfm, rfm_subckt.unwrap_or_else(|| "rfm_direct".to_owned()));
    }
    Ok(AgentSpiceDirectRequest::RunHspice(RunHspiceCliRequest {
        deck,
        request,
        ngspice,
        ngspice_sha256,
    }))
}

fn parse_run_rfm(
    arguments: &[String],
) -> Result<AgentSpiceDirectRequest, AgentSpiceDirectCliError> {
    let (positionals, mut index) = leading_positionals(arguments, 1)?;
    let deck = positionals[0].clone();
    let mut rfm = None;
    let mut backend = "native".to_owned();
    let mut output_root = None;
    let mut subckt_name = "rfm_direct".to_owned();
    let mut code_model = None;
    let mut native_engine = None;
    let mut native_engine_sha256 = None;
    let mut ngspice = None;
    let mut ngspice_sha256 = None;
    let mut code_model_sha256 = None;
    let mut dotnet = None;
    let mut dotnet_sha256 = None;
    let mut execute = false;

    let mut seen_backend = false;
    let mut seen_rfm = false;
    let mut seen_output_root = false;
    let mut seen_subckt = false;
    let mut seen_code_model = false;
    let mut seen_native_engine = false;
    let mut seen_native_engine_sha = false;
    let mut seen_ngspice = false;
    let mut seen_ngspice_sha = false;
    let mut seen_code_model_sha = false;
    let mut seen_dotnet = false;
    let mut seen_dotnet_sha = false;

    while index < arguments.len() {
        let option = arguments[index].as_str();
        match option {
            "--rfm" => {
                ensure_not_seen(&mut seen_rfm)?;
                rfm = Some(parse_path_value(arguments, &mut index, option)?);
            }
            "--backend" => {
                ensure_not_seen(&mut seen_backend)?;
                backend = parse_string_value(arguments, &mut index, option)?;
            }
            "--output-root" => {
                ensure_not_seen(&mut seen_output_root)?;
                output_root = Some(parse_path_value(arguments, &mut index, option)?);
            }
            "--subckt-name" => {
                ensure_not_seen(&mut seen_subckt)?;
                subckt_name = parse_string_value(arguments, &mut index, option)?;
            }
            "--code-model" => {
                ensure_not_seen(&mut seen_code_model)?;
                code_model = Some(parse_path_value(arguments, &mut index, option)?);
            }
            "--native-engine" => {
                ensure_not_seen(&mut seen_native_engine)?;
                native_engine = Some(parse_absolute_executable(arguments, &mut index, option)?);
            }
            "--native-engine-sha256" => {
                ensure_not_seen(&mut seen_native_engine_sha)?;
                native_engine_sha256 = Some(parse_sha256(arguments, &mut index, option)?);
            }
            "--ngspice" => {
                ensure_not_seen(&mut seen_ngspice)?;
                ngspice = Some(parse_absolute_executable(arguments, &mut index, option)?);
            }
            "--ngspice-sha256" => {
                ensure_not_seen(&mut seen_ngspice_sha)?;
                ngspice_sha256 = Some(parse_sha256(arguments, &mut index, option)?);
            }
            "--code-model-sha256" => {
                ensure_not_seen(&mut seen_code_model_sha)?;
                code_model_sha256 = Some(parse_sha256(arguments, &mut index, option)?);
            }
            "--dotnet" => {
                ensure_not_seen(&mut seen_dotnet)?;
                dotnet = Some(parse_absolute_executable(arguments, &mut index, option)?);
            }
            "--dotnet-sha256" => {
                ensure_not_seen(&mut seen_dotnet_sha)?;
                dotnet_sha256 = Some(parse_sha256(arguments, &mut index, option)?);
            }
            "--execute" => {
                if execute {
                    return Err(AgentSpiceDirectCliError::Usage);
                }
                execute = true;
                index += 1;
            }
            _ => return Err(AgentSpiceDirectCliError::Usage),
        }
    }

    let rfm = rfm.ok_or(AgentSpiceDirectCliError::Usage)?;
    let output_root = output_root.ok_or(AgentSpiceDirectCliError::Usage)?;
    if native_engine.is_some() != native_engine_sha256.is_some()
        || ngspice.is_some() != ngspice_sha256.is_some()
        || code_model.is_some() != code_model_sha256.is_some()
        || dotnet.is_some() != dotnet_sha256.is_some()
    {
        return Err(AgentSpiceDirectCliError::Usage);
    }
    let backend_kind = parse_rfm_backend(&backend)?;
    let has_native_engine = native_engine.is_some();
    let has_ngspice = ngspice.is_some() || code_model.is_some();
    let has_dotnet = dotnet.is_some();

    if !execute && (has_native_engine || has_ngspice || has_dotnet) {
        return Err(AgentSpiceDirectCliError::Usage);
    }
    match backend_kind {
        RfmBackend::Native if execute => {
            if native_engine.is_none() {
                return Err(AgentSpiceDirectCliError::Usage);
            }
            if has_ngspice {
                return Err(AgentSpiceDirectCliError::Unsupported);
            }
            let is_dll = native_engine
                .as_ref()
                .and_then(|path| path.extension())
                .is_some_and(|extension| extension.eq_ignore_ascii_case("dll"));
            if is_dll != has_dotnet {
                return Err(AgentSpiceDirectCliError::Usage);
            }
        }
        RfmBackend::Ngspice if execute => {
            if native_engine.is_some() || has_dotnet {
                return Err(AgentSpiceDirectCliError::Unsupported);
            }
            if ngspice.is_none() || code_model.is_none() {
                return Err(AgentSpiceDirectCliError::Usage);
            }
            if !code_model.as_ref().is_some_and(|path| path.is_absolute()) {
                return Err(AgentSpiceDirectCliError::InvalidInput);
            }
        }
        _ => {}
    }

    let mut request =
        RunRfmRequest::new(deck, rfm, &backend, output_root).map_err(map_rfm_error)?;
    request.subckt_name = subckt_name;
    request.execute = execute;
    request.native_engine = native_engine;
    request.code_model = code_model;
    if let Some(path) = ngspice {
        request.ngspice = path.to_string_lossy().into_owned();
    }
    if let Some(path) = dotnet {
        request.dotnet = path.to_string_lossy().into_owned();
    }

    Ok(AgentSpiceDirectRequest::RunRfm(RunRfmCliRequest {
        request,
        native_engine_sha256,
        dotnet_sha256,
        ngspice_sha256,
        code_model_sha256,
    }))
}

fn execute_hspice(
    parsed: RunHspiceCliRequest,
) -> Result<AgentSpiceDirectReceipt, AgentSpiceDirectCliError> {
    let RunHspiceCliRequest {
        deck,
        request,
        ngspice,
        ngspice_sha256,
    } = parsed;
    let backend = request.backend;
    let execute = request.execute;
    let result = match (execute, ngspice, ngspice_sha256) {
        (true, Some(executable), Some(sha256)) => {
            run_hspice_with_ngspice_custody(&deck, request, NgspiceCustody::new(executable, sha256))
        }
        (false, None, None) => run_hspice(&deck, request),
        _ => return Err(AgentSpiceDirectCliError::Usage),
    }
    .map_err(map_direct_port_error)?;
    let backend = match backend {
        Backend::Native => AgentSpiceBackend::Native,
        Backend::Ngspice => AgentSpiceBackend::Ngspice,
        Backend::Xyce | Backend::XyceXdm => return Err(AgentSpiceDirectCliError::Unsupported),
    };
    Ok(AgentSpiceDirectReceipt {
        schema: AGENT_SPICE_DIRECT_RECEIPT_SCHEMA_V1,
        workflow: AgentSpiceWorkflow::RunHspice,
        upstream: UpstreamReceipt {
            repository: sipi_agent_spice_direct::UPSTREAM_REPOSITORY,
            commit: sipi_agent_spice_direct::UPSTREAM_COMMIT,
            tree: sipi_agent_spice_direct::UPSTREAM_TREE,
        },
        backend,
        execute,
        status: result.status.as_str().to_owned(),
        summary: AgentSpiceDirectSummary::RunHspice(RunHspiceSummary {
            case_count: result.case_count,
            execution_returncodes: result.execution_returncodes,
            numerical_parity: "not_evaluated",
        }),
    })
}

fn execute_rfm(
    parsed: RunRfmCliRequest,
) -> Result<AgentSpiceDirectReceipt, AgentSpiceDirectCliError> {
    let RunRfmCliRequest {
        request,
        native_engine_sha256,
        dotnet_sha256,
        ngspice_sha256,
        code_model_sha256,
    } = parsed;
    let backend = request.backend;
    let execute = request.execute;
    let result = match backend {
        RfmBackend::Native if execute => {
            let engine = request
                .native_engine
                .as_ref()
                .ok_or(AgentSpiceDirectCliError::Usage)?;
            let engine_sha = native_engine_sha256.ok_or(AgentSpiceDirectCliError::Usage)?;
            let mut custody = RfmNativeCustody::new(NgspiceCustody::new(engine, engine_sha));
            if engine
                .extension()
                .is_some_and(|extension| extension.eq_ignore_ascii_case("dll"))
            {
                let dotnet_sha = dotnet_sha256.ok_or(AgentSpiceDirectCliError::Usage)?;
                custody =
                    custody.with_dotnet(NgspiceCustody::new(request.dotnet.clone(), dotnet_sha));
            }
            run_rfm_with_native_custody(&request, &custody).map_err(map_rfm_error)
        }
        RfmBackend::Ngspice if execute => {
            let ngspice_sha = ngspice_sha256.ok_or(AgentSpiceDirectCliError::Usage)?;
            let code_model_sha = code_model_sha256.ok_or(AgentSpiceDirectCliError::Usage)?;
            let _code_model = request
                .code_model
                .as_ref()
                .ok_or(AgentSpiceDirectCliError::Usage)?;
            run_rfm_with_ngspice_custody(
                &request,
                &RfmNgspiceCustody::new(
                    NgspiceCustody::new(&request.ngspice, ngspice_sha),
                    code_model_sha,
                ),
            )
            .map_err(map_rfm_error)
        }
        _ => sipi_agent_spice_direct::as06_run_rfm::run_rfm(&request).map_err(map_rfm_error),
    }?;
    let report = artifact_receipt(&result.report, ArtifactKind::Report)?;
    Ok(AgentSpiceDirectReceipt {
        schema: AGENT_SPICE_DIRECT_RECEIPT_SCHEMA_V1,
        workflow: AgentSpiceWorkflow::RunRfm,
        upstream: UpstreamReceipt {
            repository: sipi_agent_spice_direct::UPSTREAM_REPOSITORY,
            commit: sipi_agent_spice_direct::as06_run_rfm::UPSTREAM_COMMIT,
            tree: sipi_agent_spice_direct::UPSTREAM_TREE,
        },
        backend: match backend {
            RfmBackend::Native => AgentSpiceBackend::Native,
            RfmBackend::Ngspice => AgentSpiceBackend::Ngspice,
        },
        execute,
        status: result.status,
        summary: AgentSpiceDirectSummary::RunRfm(RunRfmSummary {
            response_samples: result.response_samples,
            response_max_error: result.response_max_error,
            nports: result.model.nports,
            response_count: result.model.response_count(),
            effective_order: result.model.effective_order(),
            artifacts: vec![report],
        }),
    })
}

fn leading_positionals(
    arguments: &[String],
    expected: usize,
) -> Result<(Vec<PathBuf>, usize), AgentSpiceDirectCliError> {
    let mut positionals = Vec::with_capacity(expected);
    let mut index = 0usize;
    while index < arguments.len() && !arguments[index].starts_with('-') {
        positionals.push(parse_local_path(&arguments[index])?);
        index += 1;
    }
    if positionals.len() != expected {
        return Err(AgentSpiceDirectCliError::Usage);
    }
    Ok((positionals, index))
}

fn parse_local_path(value: &str) -> Result<PathBuf, AgentSpiceDirectCliError> {
    if value.is_empty() || value.starts_with("--") {
        return Err(AgentSpiceDirectCliError::Usage);
    }
    Ok(PathBuf::from(value))
}

fn parse_path_value(
    arguments: &[String],
    index: &mut usize,
    option: &str,
) -> Result<PathBuf, AgentSpiceDirectCliError> {
    Ok(PathBuf::from(parse_string_value(arguments, index, option)?))
}

fn parse_string_value(
    arguments: &[String],
    index: &mut usize,
    _option: &str,
) -> Result<String, AgentSpiceDirectCliError> {
    let value = arguments
        .get(
            index
                .checked_add(1)
                .ok_or(AgentSpiceDirectCliError::Usage)?,
        )
        .ok_or(AgentSpiceDirectCliError::Usage)?;
    let value = parse_local_path(value)?;
    *index += 2;
    Ok(value.to_string_lossy().into_owned())
}

fn parse_absolute_executable(
    arguments: &[String],
    index: &mut usize,
    option: &str,
) -> Result<PathBuf, AgentSpiceDirectCliError> {
    let path = parse_path_value(arguments, index, option)?;
    if !path.is_absolute() {
        return Err(AgentSpiceDirectCliError::InvalidInput);
    }
    Ok(path)
}

fn parse_sha256(
    arguments: &[String],
    index: &mut usize,
    option: &str,
) -> Result<String, AgentSpiceDirectCliError> {
    let value = parse_string_value(arguments, index, option)?;
    if value.len() != 64 || !value.bytes().all(|byte| byte.is_ascii_hexdigit()) {
        return Err(AgentSpiceDirectCliError::InvalidInput);
    }
    Ok(value.to_ascii_lowercase())
}

fn set_once<T>(slot: &mut Option<T>, value: T) -> Result<(), AgentSpiceDirectCliError> {
    if slot.is_some() {
        return Err(AgentSpiceDirectCliError::Usage);
    }
    *slot = Some(value);
    Ok(())
}

fn ensure_not_seen(seen: &mut bool) -> Result<(), AgentSpiceDirectCliError> {
    if *seen {
        return Err(AgentSpiceDirectCliError::Usage);
    }
    *seen = true;
    Ok(())
}

fn parse_backend(value: &str) -> Result<Backend, AgentSpiceDirectCliError> {
    if matches!(value, "xyce" | "xyce-xdm") {
        return Err(AgentSpiceDirectCliError::Unsupported);
    }
    Backend::parse(value).map_err(map_direct_port_error)
}

fn parse_rfm_backend(value: &str) -> Result<RfmBackend, AgentSpiceDirectCliError> {
    if matches!(value, "xyce" | "xyce-xdm") {
        return Err(AgentSpiceDirectCliError::Unsupported);
    }
    RfmBackend::parse(value).map_err(map_rfm_error)
}

fn artifact_receipt(
    path: &Path,
    kind: ArtifactKind,
) -> Result<ArtifactReceipt, AgentSpiceDirectCliError> {
    let before =
        fs::symlink_metadata(path).map_err(|_| AgentSpiceDirectCliError::OperationalFailure)?;
    if before.file_type().is_symlink() || !before.is_file() {
        return Err(AgentSpiceDirectCliError::OperationalFailure);
    }
    if before.len() > MAX_RECEIPT_ARTIFACT_BYTES {
        return Err(AgentSpiceDirectCliError::OperationalFailure);
    }
    let bytes = fs::read(path).map_err(|_| AgentSpiceDirectCliError::OperationalFailure)?;
    let after =
        fs::symlink_metadata(path).map_err(|_| AgentSpiceDirectCliError::OperationalFailure)?;
    if before.len() != after.len()
        || before.modified().ok() != after.modified().ok()
        || bytes.len() as u64 != after.len()
    {
        return Err(AgentSpiceDirectCliError::OperationalFailure);
    }
    Ok(ArtifactReceipt {
        kind,
        byte_length: bytes.len() as u64,
        sha256: format!("{:x}", Sha256::digest(&bytes)),
    })
}

fn map_direct_port_error(error: DirectPortError) -> AgentSpiceDirectCliError {
    match error {
        DirectPortError::UnsupportedBackend(_) => AgentSpiceDirectCliError::Unsupported,
        DirectPortError::UnsupportedExecution(_) => AgentSpiceDirectCliError::Unsupported,
        DirectPortError::EmptyOutputRoot
        | DirectPortError::EmptyDeckStem
        | DirectPortError::InvalidProjectManifest(_) => AgentSpiceDirectCliError::InvalidInput,
        DirectPortError::ProjectManifestIo(_)
        | DirectPortError::InputIo(_)
        | DirectPortError::OutputIo(_) => AgentSpiceDirectCliError::OperationalFailure,
    }
}

fn map_rfm_error(error: RfmError) -> AgentSpiceDirectCliError {
    match error {
        RfmError::InvalidOption(_) | RfmError::Input(_) | RfmError::Parse(_) => {
            AgentSpiceDirectCliError::InvalidInput
        }
        RfmError::Unsupported(_) => AgentSpiceDirectCliError::Unsupported,
        RfmError::Execution(_) | RfmError::Output(_) => {
            AgentSpiceDirectCliError::OperationalFailure
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn args(values: &[&str]) -> Vec<String> {
        values.iter().map(|value| (*value).to_owned()).collect()
    }

    fn current_exe_string() -> String {
        std::env::current_exe()
            .expect("current executable")
            .to_string_lossy()
            .into_owned()
    }

    #[test]
    fn unknown_and_duplicate_options_are_rejected() {
        assert_eq!(
            parse_agent_spice_direct_argv(&args(&["fit-yparam"])),
            Err(AgentSpiceDirectCliError::Usage)
        );
        assert_eq!(
            parse_agent_spice_direct_argv(&args(&["tune-yparam-tran"])),
            Err(AgentSpiceDirectCliError::Usage)
        );
        assert_eq!(
            parse_agent_spice_direct_argv(&args(&[
                "run-rfm",
                "deck.sp",
                "--rfm",
                "model.rfm",
                "--rfm",
                "other.rfm",
                "--output-root",
                "out",
            ])),
            Err(AgentSpiceDirectCliError::Usage)
        );
        assert_eq!(
            parse_agent_spice_direct_argv(&args(&[
                "run-rfm",
                "deck.sp",
                "--rfm",
                "model.rfm",
                "--output-root",
                "out",
                "--unknown",
                "x",
            ])),
            Err(AgentSpiceDirectCliError::Usage)
        );
    }

    #[test]
    fn as05_rejects_excluded_backends_and_native_execution() {
        assert_eq!(
            parse_agent_spice_direct_argv(&args(&[
                "run-hspice",
                "deck.sp",
                "--backend",
                "xyce",
                "--output-root",
                "out",
            ])),
            Err(AgentSpiceDirectCliError::Unsupported)
        );
        assert_eq!(
            parse_agent_spice_direct_argv(&args(&[
                "run-hspice",
                "deck.sp",
                "--backend",
                "native",
                "--output-root",
                "out",
                "--execute",
            ])),
            Err(AgentSpiceDirectCliError::Unsupported)
        );
    }

    #[test]
    fn as06_requires_complete_custody_for_execution() {
        let exe = current_exe_string();
        assert_eq!(
            parse_agent_spice_direct_argv(&args(&[
                "run-rfm",
                "deck.sp",
                "--rfm",
                "model.rfm",
                "--output-root",
                "out",
                "--execute",
                "--native-engine",
                &exe,
            ])),
            Err(AgentSpiceDirectCliError::Usage)
        );
    }

    #[test]
    fn receipt_serialization_is_path_free_and_typed() {
        let receipt = AgentSpiceDirectReceipt {
            schema: AGENT_SPICE_DIRECT_RECEIPT_SCHEMA_V1,
            workflow: AgentSpiceWorkflow::RunRfm,
            upstream: UpstreamReceipt {
                repository: "agent-spice",
                commit: "commit",
                tree: "tree",
            },
            backend: AgentSpiceBackend::Native,
            execute: false,
            status: "PREPARED".to_owned(),
            summary: AgentSpiceDirectSummary::RunRfm(RunRfmSummary {
                response_samples: 1,
                response_max_error: 0.0,
                nports: 1,
                response_count: 1,
                effective_order: 1,
                artifacts: Vec::new(),
            }),
        };
        let text = receipt.to_json().expect("receipt JSON");
        assert!(text.contains("sipi.agent-spice.direct-cli-receipt.v1"));
        assert!(!text.contains("C:\\Users"));
        assert!(!text.contains("/Users/"));
    }
}
