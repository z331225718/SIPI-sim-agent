//! The explicitly external upstream migration routes.
//!
//! This module is intentionally a transport layer, not a second numerical
//! implementation.  The three adapter crates own process supervision and
//! upstream argument construction.  The CLI only validates a small typed
//! envelope, selects the route named by argv, and publishes bounded metadata;
//! child stdout/stderr and artifact payloads never cross the CLI envelope.

use std::{
    fs,
    path::{Path, PathBuf},
    time::Duration,
};

use serde_json::{Map, Value};
use sipi_agent_com_adapter::{
    AdapterConfig as ComAdapterConfig, AdapterLimits as ComAdapterLimits, AgentComAdapter,
    BackendCommand, CancellationToken, CompareRequest, ConfigValidateRequest,
    PublicWorkflowRequest, RunRequest,
};
use sipi_agent_spice_adapter::{
    AgentSpiceAdapter, FitYparamRequest, ProcessLimits as SpiceLimits,
    ProcessOptions as SpiceOptions, Request as SpiceRequest, RunHspiceRequest, RunRfmRequest,
    TuneYparamTranRequest,
};
use sipi_pybert_adapter::{
    AdapterRequest as PyBertRequest, AdapterResult as PyBertResult, ProcessLimits as PyBertLimits,
    PyBertWorkflow, WorkflowInput as PyBertInput,
};

pub const REQUEST_SCHEMA: &str = "sipi.upstream-migration-request.v1";
pub const RESPONSE_SCHEMA: &str = "sipi.upstream-migration-result.v1";
pub const VALIDATION_RULE: &str = "upstream.external-migration-adapter.v1";

/// This is a request envelope only.  `workflow` is discriminated twice: by
/// the command route and by this field, so a request cannot be replayed on a
/// different named workflow accidentally.
pub const REQUEST_SCHEMA_JSON: &str = r#"{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "sipi.upstream-migration-request.v1",
  "oneOf": [
    {
      "type": "object",
      "additionalProperties": false,
      "required": ["schema", "workflow", "interpreter", "working_directory", "artifact_root", "backend", "args"],
      "properties": {
        "schema": {"const": "sipi.upstream-migration-request.v1"},
        "workflow": {"enum": ["agent-spice.fit-yparam", "agent-spice.tune-yparam-tran", "agent-spice.run-hspice", "agent-spice.run-rfm"]},
        "interpreter": {"type": "string", "minLength": 1},
        "working_directory": {"type": "string", "minLength": 1},
        "artifact_root": {"type": "string", "minLength": 1},
        "backend": {"type": ["string", "null"]},
        "args": {"type": "array", "items": {"type": "string"}},
        "limits": {"type": "object"}
      }
    },
    {
      "type": "object",
      "additionalProperties": false,
      "required": ["schema", "workflow", "executable", "working_directory", "artifact_root", "backend", "input"],
      "properties": {
        "schema": {"const": "sipi.upstream-migration-request.v1"},
        "workflow": {"enum": ["pybert.sim", "pybert.sim-native", "pybert.sim-rust", "pybert.sim-auto", "pybert.sim-compare"]},
        "executable": {"type": "string", "minLength": 1},
        "working_directory": {"type": "string", "minLength": 1},
        "artifact_root": {"type": "string", "minLength": 1},
        "backend": {"type": ["string", "null"]},
        "input": {"type": "object"},
        "limits": {"type": "object"},
        "cancel_file": {"type": ["string", "null"]}
      }
    },
    {
      "type": "object",
      "additionalProperties": false,
      "required": ["schema", "workflow", "executable", "interpreter", "working_directory", "artifact_root", "backend", "input"],
      "properties": {
        "schema": {"const": "sipi.upstream-migration-request.v1"},
        "workflow": {"enum": ["agent-com.config-validate", "agent-com.run", "agent-com.compare", "agent-com.public-api"]},
        "executable": {"type": "string", "minLength": 1},
        "interpreter": {"type": "string", "minLength": 1},
        "working_directory": {"type": "string", "minLength": 1},
        "artifact_root": {"type": "string", "minLength": 1},
        "backend": {"type": ["string", "null"]},
        "input": {"type": "object"},
        "limits": {"type": "object"}
      }
    }
  ]
}"#;

const MAX_REQUEST_BYTES: usize = 1_048_576;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum FailureKind {
    InvalidRequest,
    Spawn,
    NonZeroExit,
    Timeout,
    OutputLimit,
    Cancelled,
    Failure,
}

impl FailureKind {
    pub const fn diagnostic_code(self) -> &'static str {
        match self {
            Self::InvalidRequest => "external_adapter_invalid_request",
            Self::Spawn => "external_adapter_spawn_failed",
            Self::NonZeroExit => "external_adapter_nonzero_exit",
            Self::Timeout => "external_adapter_timeout",
            Self::OutputLimit => "external_adapter_output_limit",
            Self::Cancelled => "external_adapter_cancelled",
            Self::Failure => "external_adapter_failure",
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct Failure {
    pub kind: FailureKind,
}

impl Failure {
    const fn invalid() -> Self {
        Self {
            kind: FailureKind::InvalidRequest,
        }
    }
}

/// Execute one of the fifteen pinned routes and return only path-free result
/// metadata.  The route is selected by the caller from the static manifest;
/// this function still checks the discriminator in stdin for defense in depth.
pub fn execute(route: &str, input: &[u8]) -> Result<String, Failure> {
    let value: Value = serde_json::from_slice(input).map_err(|_| Failure::invalid())?;
    let object = value.as_object().ok_or_else(Failure::invalid)?;
    validate_top_level_route(object, route)?;
    if string(object, "schema")? != REQUEST_SCHEMA || string(object, "workflow")? != route {
        return Err(Failure::invalid());
    }
    let working_directory = canonical_directory(&path(object, "working_directory")?)?;
    let artifact_root = canonical_directory(&path(object, "artifact_root")?)?;

    if route.starts_with("agent-spice.") {
        execute_spice(route, object, working_directory, artifact_root)
    } else if route.starts_with("pybert.") {
        execute_pybert(route, object, working_directory, artifact_root)
    } else if route.starts_with("agent-com.") {
        execute_com(route, object, working_directory, artifact_root)
    } else {
        Err(Failure::invalid())
    }
}

fn execute_spice(
    route: &str,
    object: &Map<String, Value>,
    working_directory: PathBuf,
    artifact_root: PathBuf,
) -> Result<String, Failure> {
    let interpreter = absolute_path(object, "interpreter")?;
    let args = string_array(object, "args")?;
    let options = SpiceOptions {
        interpreter,
        working_directory,
        artifact_root,
        limits: spice_limits(object)?,
        environment: Vec::new(),
        invocation_prefix: vec!["-m".into(), "agent_spice.cli".into()],
    };
    let request = match route {
        "agent-spice.fit-yparam" => SpiceRequest::FitYparam(FitYparamRequest::new(args, options)),
        "agent-spice.tune-yparam-tran" => {
            SpiceRequest::TuneYparamTran(TuneYparamTranRequest::new(args, options))
        }
        "agent-spice.run-hspice" => SpiceRequest::RunHspice(
            RunHspiceRequest::new(args, options).map_err(|error| map_spice_error(&error))?,
        ),
        "agent-spice.run-rfm" => SpiceRequest::RunRfm(
            RunRfmRequest::new(args, options).map_err(|error| map_spice_error(&error))?,
        ),
        _ => return Err(Failure::invalid()),
    };
    let backend = string_or_null(object, "backend")?;
    validate_spice_backend(backend.as_deref(), &request)?;
    let result = AgentSpiceAdapter::new()
        .execute(request, &sipi_agent_spice_adapter::CancellationToken::new())
        .map_err(|error| map_spice_error(&error))?;
    if !result.status.success() {
        return Err(Failure {
            kind: FailureKind::NonZeroExit,
        });
    }
    Ok(spice_result_json(route, &result))
}

fn validate_spice_backend(requested: Option<&str>, request: &SpiceRequest) -> Result<(), Failure> {
    let expected = match request {
        SpiceRequest::RunHspice(value) => Some(value.backend.to_string()),
        SpiceRequest::RunRfm(value) => Some(value.backend.to_string()),
        _ => None,
    };
    match (expected.as_deref(), requested) {
        (Some(expected), Some(actual)) if expected == actual => Ok(()),
        (Some(_), _) => Err(Failure::invalid()),
        (None, None) => Ok(()),
        (None, Some(_)) => Err(Failure::invalid()),
    }
}

fn execute_pybert(
    route: &str,
    object: &Map<String, Value>,
    working_directory: PathBuf,
    artifact_root: PathBuf,
) -> Result<String, Failure> {
    let executable = absolute_path(object, "executable")?;
    let input = object.get("input").ok_or_else(Failure::invalid)?.clone();
    let workflow = match route {
        "pybert.sim" => PyBertInput::Sim {
            config_file: value_path_checked(&input, "config_file", &["config_file", "results"])?,
            results: value_optional_path_checked(&input, "results", &["config_file", "results"])?,
        },
        "pybert.sim-native" => PyBertInput::SimNative {
            input_file: value_path_checked(&input, "input_file", &["input_file", "output_dir"])?,
            output_dir: value_path_checked(&input, "output_dir", &["input_file", "output_dir"])?,
        },
        "pybert.sim-rust" => PyBertInput::SimRust {
            config_file: value_path_checked(
                &input,
                "config_file",
                &["config_file", "output_dir", "statistical_time_points"],
            )?,
            output_dir: value_path_checked(
                &input,
                "output_dir",
                &["config_file", "output_dir", "statistical_time_points"],
            )?,
            statistical_time_points: value_optional_u32(&input, "statistical_time_points")?,
        },
        "pybert.sim-auto" => PyBertInput::SimAuto {
            config_file: value_path_checked(
                &input,
                "config_file",
                &["config_file", "output_dir", "statistical_time_points"],
            )?,
            output_dir: value_path_checked(
                &input,
                "output_dir",
                &["config_file", "output_dir", "statistical_time_points"],
            )?,
            statistical_time_points: value_optional_u32(&input, "statistical_time_points")?,
        },
        "pybert.sim-compare" => PyBertInput::SimCompare {
            config_file: value_path_checked(
                &input,
                "config_file",
                &["config_file", "output_dir", "statistical_time_points"],
            )?,
            output_dir: value_path_checked(
                &input,
                "output_dir",
                &["config_file", "output_dir", "statistical_time_points"],
            )?,
            statistical_time_points: value_optional_u32(&input, "statistical_time_points")?,
        },
        _ => return Err(Failure::invalid()),
    };
    let requested_backend = string_or_null(object, "backend")?;
    let expected_backend = workflow.workflow().requested_backend();
    if requested_backend.as_deref() != Some(expected_backend) {
        return Err(Failure::invalid());
    }
    let output_root =
        resolve_future_directory(&workflow_output_root(&workflow)?, &working_directory)?;
    if !is_within(&artifact_root, &output_root) {
        return Err(Failure::invalid());
    }
    let request = PyBertRequest {
        executable,
        working_directory,
        input: workflow,
        limits: pybert_limits(object)?,
        cancel_file: object_optional_path(object, "cancel_file")?,
    };
    let result =
        sipi_pybert_adapter::run(&request).map_err(|error| map_text_error(&error.to_string()))?;
    if !result.exit.success {
        return Err(Failure {
            kind: FailureKind::NonZeroExit,
        });
    }
    if result.workflow == PyBertWorkflow::SimAuto && result.selected_backend.is_none() {
        return Err(Failure::invalid());
    }
    Ok(pybert_result_json(&result))
}

fn execute_com(
    route: &str,
    object: &Map<String, Value>,
    working_directory: PathBuf,
    artifact_root: PathBuf,
) -> Result<String, Failure> {
    let executable = absolute_path(object, "executable")?;
    let interpreter = absolute_path(object, "interpreter")?;
    let requested_backend = string_or_null(object, "backend")?;
    let expected_backend = if route == "agent-com.public-api" {
        "python"
    } else {
        "cli"
    };
    if requested_backend.as_deref() != Some(expected_backend) {
        return Err(Failure::invalid());
    }
    let limits = com_limits(object)?;
    let adapter = AgentComAdapter::new(ComAdapterConfig {
        cli: BackendCommand::new(executable),
        python: BackendCommand::new(interpreter),
        working_directory: working_directory.clone(),
        limits,
        cancellation: CancellationToken::new(),
    })
    .map_err(|error| map_text_error(&error.to_string()))?;
    let input = object.get("input").ok_or_else(Failure::invalid)?.clone();
    match route {
        "agent-com.config-validate" => {
            require_object_keys(
                input.as_object().ok_or_else(Failure::invalid)?,
                &[
                    "config",
                    "profile",
                    "reader",
                    "fix_ids",
                    "overrides",
                    "json",
                    "materialized_json",
                ],
                &["config"],
            )?;
            let request: ConfigValidateRequest =
                serde_json::from_value(input).map_err(|_| Failure::invalid())?;
            let result = adapter
                .config_validate(&request)
                .map_err(|error| map_text_error(&error.to_string()))?;
            if result.exit_code != 0 {
                return Err(Failure {
                    kind: FailureKind::NonZeroExit,
                });
            }
            Ok(com_result_json(route, result.exit_code, None, None, None))
        }
        "agent-com.run" => {
            require_object_keys(
                input.as_object().ok_or_else(Failure::invalid)?,
                &[
                    "config",
                    "thru",
                    "fext",
                    "next",
                    "calibration_noise",
                    "profile",
                    "reader",
                    "fix_ids",
                    "overrides",
                    "output_dir",
                    "overwrite",
                    "log_file",
                    "progress_jsonl",
                    "diagnostics",
                    "legacy_csv",
                ],
                &["config", "thru", "output_dir"],
            )?;
            let request: RunRequest =
                serde_json::from_value(input).map_err(|_| Failure::invalid())?;
            let output_dir = resolve_future_directory(&request.output_dir, &working_directory)?;
            if !is_within(&artifact_root, &output_dir) {
                return Err(Failure::invalid());
            }
            let result = adapter
                .run(&request)
                .map_err(|error| map_text_error(&error.to_string()))?;
            if result.exit_code != 0 {
                return Err(Failure {
                    kind: FailureKind::NonZeroExit,
                });
            }
            Ok(com_result_json(
                route,
                result.exit_code,
                Some(result.artifacts.total_bytes),
                Some(result.artifacts.report.as_path()),
                result.artifacts.diagnostics.as_deref(),
            ))
        }
        "agent-com.compare" => {
            require_object_keys(
                input.as_object().ok_or_else(Failure::invalid)?,
                &["golden", "result", "atol"],
                &["golden", "result"],
            )?;
            let request: CompareRequest =
                serde_json::from_value(input).map_err(|_| Failure::invalid())?;
            let result = adapter
                .compare(&request)
                .map_err(|error| map_text_error(&error.to_string()))?;
            Ok(com_compare_result_json(&result))
        }
        "agent-com.public-api" => {
            require_object_keys(
                input.as_object().ok_or_else(Failure::invalid)?,
                &[
                    "config",
                    "thru",
                    "fext",
                    "next",
                    "calibration_noise",
                    "profile",
                    "overrides",
                    "output_dir",
                    "overwrite",
                    "diagnostics",
                ],
                &["config", "thru", "output_dir"],
            )?;
            let request: PublicWorkflowRequest =
                serde_json::from_value(input).map_err(|_| Failure::invalid())?;
            let output_dir = resolve_future_directory(&request.output_dir, &working_directory)?;
            if !is_within(&artifact_root, &output_dir) {
                return Err(Failure::invalid());
            }
            let result = adapter
                .public_workflow(&request)
                .map_err(|error| map_text_error(&error.to_string()))?;
            if result.exit_code != 0 {
                return Err(Failure {
                    kind: FailureKind::NonZeroExit,
                });
            }
            Ok(com_result_json(
                route,
                result.exit_code,
                Some(result.artifacts.total_bytes),
                Some(result.artifacts.report.as_path()),
                result.artifacts.diagnostics.as_deref(),
            ))
        }
        _ => Err(Failure::invalid()),
    }
}

fn spice_limits(object: &Map<String, Value>) -> Result<SpiceLimits, Failure> {
    let mut limits = SpiceLimits::default();
    if let Some(value) = object.get("limits") {
        let object = value.as_object().ok_or_else(Failure::invalid)?;
        require_limit_keys(
            object,
            &[
                "timeout_millis",
                "stdout_bytes",
                "stderr_bytes",
                "artifact_bytes",
                "artifact_files",
                "artifact_directories",
                "artifact_depth",
                "artifact_path_bytes",
                "argv_bytes",
            ],
        )?;
        if let Some(value) = object.get("timeout_millis") {
            limits.wall_time = Duration::from_millis(bounded_u64(value, 30 * 60 * 1000)?);
        }
        if let Some(value) = object.get("stdout_bytes") {
            limits.stdout_bytes = bounded_usize(value, 4 * 1024 * 1024)?;
        }
        if let Some(value) = object.get("stderr_bytes") {
            limits.stderr_bytes = bounded_usize(value, 4 * 1024 * 1024)?;
        }
        if let Some(value) = object.get("artifact_bytes") {
            limits.artifact_bytes = bounded_u64(value, 512 * 1024 * 1024)?;
        }
        if let Some(value) = object.get("artifact_files") {
            limits.artifact_files = bounded_usize(value, 16_384)?;
        }
        if let Some(value) = object.get("artifact_directories") {
            limits.artifact_directories = bounded_usize(value, 4_096)?;
        }
        if let Some(value) = object.get("artifact_depth") {
            limits.artifact_max_depth = bounded_usize(value, 64)?;
        }
        if let Some(value) = object.get("artifact_path_bytes") {
            limits.artifact_path_bytes = bounded_usize(value, 4_096)?;
        }
        if let Some(value) = object.get("argv_bytes") {
            limits.argv_bytes = bounded_usize(value, 64 * 1024)?;
        }
    }
    Ok(limits)
}

fn pybert_limits(object: &Map<String, Value>) -> Result<PyBertLimits, Failure> {
    let mut limits = PyBertLimits::default();
    if let Some(value) = object.get("limits") {
        let object = value.as_object().ok_or_else(Failure::invalid)?;
        require_limit_keys(
            object,
            &[
                "timeout_millis",
                "request_bytes",
                "stdout_bytes",
                "stderr_bytes",
                "artifact_bytes",
                "artifact_files",
                "artifact_directories",
                "artifact_depth",
            ],
        )?;
        if let Some(value) = object.get("timeout_millis") {
            limits.timeout = Duration::from_millis(bounded_u64(value, 5 * 60 * 1000)?);
        }
        if let Some(value) = object.get("request_bytes") {
            limits.max_request_bytes = bounded_usize(value, 64 * 1024)?;
        }
        if let Some(value) = object.get("stdout_bytes") {
            limits.max_stdout_bytes = bounded_usize(value, 1024 * 1024)?;
        }
        if let Some(value) = object.get("stderr_bytes") {
            limits.max_stderr_bytes = bounded_usize(value, 1024 * 1024)?;
        }
        if let Some(value) = object.get("artifact_bytes") {
            limits.max_artifact_bytes = bounded_u64(value, 512 * 1024 * 1024)?;
        }
        if let Some(value) = object.get("artifact_files") {
            limits.max_artifact_files = bounded_usize(value, 4_096)?;
        }
        if let Some(value) = object.get("artifact_directories") {
            limits.max_artifact_directories = bounded_usize(value, 4_096)?;
        }
        if let Some(value) = object.get("artifact_depth") {
            limits.max_artifact_depth = bounded_usize(value, 64)?;
        }
    }
    Ok(limits)
}

fn com_limits(object: &Map<String, Value>) -> Result<ComAdapterLimits, Failure> {
    let mut limits = ComAdapterLimits::default();
    if let Some(value) = object.get("limits") {
        let object = value.as_object().ok_or_else(Failure::invalid)?;
        require_limit_keys(
            object,
            &[
                "timeout_millis",
                "stdout_bytes",
                "stderr_bytes",
                "stdin_bytes",
                "artifact_bytes",
                "artifact_files",
            ],
        )?;
        if let Some(value) = object.get("timeout_millis") {
            limits.timeout = Duration::from_millis(bounded_u64(value, 30 * 60 * 1000)?);
        }
        if let Some(value) = object.get("stdout_bytes") {
            limits.max_stdout_bytes = bounded_usize(value, 8 * 1024 * 1024)?;
        }
        if let Some(value) = object.get("stderr_bytes") {
            limits.max_stderr_bytes = bounded_usize(value, 8 * 1024 * 1024)?;
        }
        if let Some(value) = object.get("stdin_bytes") {
            limits.max_stdin_bytes = bounded_usize(value, 1024 * 1024)?;
        }
        if let Some(value) = object.get("artifact_bytes") {
            limits.max_artifact_bytes = bounded_u64(value, 4 * 1024 * 1024 * 1024)?;
        }
        if let Some(value) = object.get("artifact_files") {
            limits.max_artifact_entries = bounded_usize(value, 100_000)?;
        }
    }
    Ok(limits)
}

fn require_limit_keys(object: &Map<String, Value>, allowed: &[&str]) -> Result<(), Failure> {
    if object.keys().all(|key| allowed.contains(&key.as_str())) {
        Ok(())
    } else {
        Err(Failure::invalid())
    }
}

fn validate_top_level_route(object: &Map<String, Value>, route: &str) -> Result<(), Failure> {
    const SPICE_ALLOWED: &[&str] = &[
        "schema",
        "workflow",
        "working_directory",
        "artifact_root",
        "backend",
        "interpreter",
        "args",
        "limits",
    ];
    const SPICE_REQUIRED: &[&str] = &[
        "schema",
        "workflow",
        "working_directory",
        "artifact_root",
        "backend",
        "interpreter",
        "args",
    ];
    const PYBERT_ALLOWED: &[&str] = &[
        "schema",
        "workflow",
        "working_directory",
        "artifact_root",
        "backend",
        "executable",
        "input",
        "limits",
        "cancel_file",
    ];
    const PYBERT_REQUIRED: &[&str] = &[
        "schema",
        "workflow",
        "working_directory",
        "artifact_root",
        "backend",
        "executable",
        "input",
    ];
    const COM_ALLOWED: &[&str] = &[
        "schema",
        "workflow",
        "working_directory",
        "artifact_root",
        "backend",
        "executable",
        "interpreter",
        "input",
        "limits",
    ];
    const COM_REQUIRED: &[&str] = &[
        "schema",
        "workflow",
        "working_directory",
        "artifact_root",
        "backend",
        "executable",
        "interpreter",
        "input",
    ];
    let (allowed, required): (&[&str], &[&str]) = if route.starts_with("agent-spice.") {
        (SPICE_ALLOWED, SPICE_REQUIRED)
    } else if route.starts_with("pybert.") {
        (PYBERT_ALLOWED, PYBERT_REQUIRED)
    } else if route.starts_with("agent-com.") {
        (COM_ALLOWED, COM_REQUIRED)
    } else {
        return Err(Failure::invalid());
    };
    require_object_keys(object, allowed, required)
}

fn require_object_keys(
    object: &Map<String, Value>,
    allowed: &[&str],
    required: &[&str],
) -> Result<(), Failure> {
    if object.keys().all(|key| allowed.contains(&key.as_str()))
        && required.iter().all(|key| object.contains_key(*key))
    {
        Ok(())
    } else {
        Err(Failure::invalid())
    }
}

fn spice_result_json(route: &str, result: &sipi_agent_spice_adapter::ExecutionResult) -> String {
    let backend = result
        .backend
        .map_or_else(|| "null".to_owned(), |value| quote(&value.to_string()));
    let bytes = result
        .artifacts
        .entries
        .iter()
        .map(|entry| entry.byte_length)
        .sum::<u64>();
    format!(
        "{{\"schema\":\"{RESPONSE_SCHEMA}\",\"workflow\":\"{route}\",\"backend\":{backend},\"contract_source\":{{\"repository\":\"{}\",\"commit\":\"{}\",\"module\":\"{}\"}},\"runtime_identity\":{{\"attestation\":\"not_performed\",\"launcher\":\"caller_supplied\"}},\"exit\":{{\"success\":true,\"code\":{}}},\"artifacts\":{{\"file_count\":{},\"byte_length\":{},\"manifest_sha256\":\"{}\"}},\"provenance\":{{\"invocation_sha256\":\"{}\",\"artifact_manifest_sha256\":\"{}\"}},\"scope\":{{\"transport\":\"external_migration_adapter\",\"product_capability\":\"not_claimed\",\"acceptance\":\"not_evaluated\",\"release\":false}}}}",
        result.provenance.upstream_repository,
        result.provenance.upstream_commit,
        result.provenance.upstream_module,
        result.status.exit_code().unwrap_or_default(),
        result.artifacts.entries.len(),
        bytes,
        result.artifacts.sha256,
        result.provenance.invocation_sha256,
        result.provenance.artifact_manifest_sha256,
    )
}

fn pybert_result_json(result: &PyBertResult) -> String {
    let selection = result.backend_selection.as_ref().map_or_else(
        || "null".to_owned(),
        |value| {
            format!(
                "{{\"requested\":{},\"selected\":{}}}",
                value
                    .requested
                    .as_deref()
                    .map_or_else(|| "null".to_owned(), quote),
                quote(&value.selected),
            )
        },
    );
    let bytes = result
        .artifacts
        .iter()
        .map(|entry| entry.bytes)
        .sum::<u64>();
    format!(
        "{{\"schema\":\"{RESPONSE_SCHEMA}\",\"workflow\":\"pybert.{}\",\"backend\":\"{}\",\"selected_backend\":{},\"backend_selection\":{},\"contract_source\":{{\"commit\":\"{}\",\"tree\":\"{}\",\"cli_path\":\"{}\",\"cli_blob_sha1\":\"{}\",\"cli_sha256\":\"{}\"}},\"runtime_identity\":{{\"attestation\":\"not_performed\",\"launcher\":\"caller_supplied\"}},\"exit\":{{\"success\":true,\"code\":{}}},\"artifacts\":{{\"file_count\":{},\"byte_length\":{}}},\"scope\":{{\"transport\":\"external_migration_adapter\",\"product_capability\":\"not_claimed\",\"acceptance\":\"not_evaluated\",\"release\":false}}}}",
        result.workflow.command_name(),
        result.requested_backend,
        result
            .selected_backend
            .as_deref()
            .map_or_else(|| "null".to_owned(), quote),
        selection,
        result.contract_source.commit,
        result.contract_source.tree,
        result.contract_source.cli_path,
        result.contract_source.cli_blob_sha1,
        result.contract_source.cli_sha256,
        result.exit.code.unwrap_or_default(),
        result.artifacts.len(),
        bytes,
    )
}

fn com_result_json(
    route: &str,
    exit_code: i32,
    total_bytes: Option<u64>,
    _report: Option<&Path>,
    _diagnostics: Option<&Path>,
) -> String {
    format!(
        "{{\"schema\":\"{RESPONSE_SCHEMA}\",\"workflow\":\"{route}\",\"contract_source\":{{\"repository\":\"agent-com\",\"commit\":\"5272ffe74702cd585054d975559b06f8afae7b6e\"}},\"runtime_identity\":{{\"attestation\":\"not_performed\",\"launcher\":\"caller_supplied\"}},\"exit\":{{\"success\":true,\"code\":{exit_code}}},\"artifacts\":{{\"byte_length\":{},\"payload\":\"omitted\"}},\"scope\":{{\"transport\":\"external_migration_adapter\",\"product_capability\":\"not_claimed\",\"acceptance\":\"not_evaluated\",\"release\":false}}}}",
        total_bytes.unwrap_or(0),
    )
}

fn com_compare_result_json(result: &sipi_agent_com_adapter::CompareResponse) -> String {
    serde_json::json!({
        "schema": RESPONSE_SCHEMA,
        "workflow": "agent-com.compare",
        "contract_source": {
            "repository": "agent-com",
            "commit": "5272ffe74702cd585054d975559b06f8afae7b6e",
        },
        "runtime_identity": {
            "attestation": "not_performed",
            "launcher": "caller_supplied",
        },
        "comparison": {
            "matched": result.report.matched,
            "mismatch_count": result.report.mismatches.len(),
        },
        "exit": {
            "success": result.exit_code == 0,
            "code": result.exit_code,
        },
        "artifacts": {
            "byte_length": 0,
            "payload": "omitted",
        },
        "scope": {
            "transport": "external_migration_adapter",
            "product_capability": "not_claimed",
            "acceptance": "not_evaluated",
            "release": false,
        },
    })
    .to_string()
}

fn map_spice_error(error: &impl std::fmt::Display) -> Failure {
    map_text_error(&error.to_string())
}

fn map_text_error(text: &str) -> Failure {
    let lower = text.to_ascii_lowercase();
    let kind = if lower.contains("timed out") || lower.contains("timed_out") {
        FailureKind::Timeout
    } else if lower.contains("cancel") {
        FailureKind::Cancelled
    } else if lower.contains("output") && lower.contains("limit") {
        FailureKind::OutputLimit
    } else if lower.contains("spawn")
        || lower.contains("could not spawn")
        || lower.contains("cannot launch")
    {
        FailureKind::Spawn
    } else if lower.contains("upstream") && lower.contains("exit") {
        FailureKind::NonZeroExit
    } else if lower.contains("invalid") || lower.contains("required") || lower.contains("backend") {
        FailureKind::InvalidRequest
    } else {
        FailureKind::Failure
    };
    Failure { kind }
}

fn workflow_output_root(input: &PyBertInput) -> Result<PathBuf, Failure> {
    let root = match input {
        PyBertInput::Sim { results, .. } => results
            .as_ref()
            .and_then(|path| path.parent().map(Path::to_path_buf))
            .or_else(|| match input {
                PyBertInput::Sim { config_file, .. } => config_file.parent().map(Path::to_path_buf),
                _ => None,
            })
            .unwrap_or_else(|| PathBuf::from(".")),
        PyBertInput::SimNative { output_dir, .. }
        | PyBertInput::SimRust { output_dir, .. }
        | PyBertInput::SimAuto { output_dir, .. }
        | PyBertInput::SimCompare { output_dir, .. } => output_dir.clone(),
    };
    Ok(root)
}

fn is_within(root: &Path, candidate: &Path) -> bool {
    candidate == root || candidate.starts_with(root)
}

fn canonical_directory(path: &Path) -> Result<PathBuf, Failure> {
    if path.as_os_str().is_empty() || !path.is_absolute() {
        return Err(Failure::invalid());
    }
    reject_link_ancestors(path)?;
    let metadata = fs::symlink_metadata(path).map_err(|_| Failure::invalid())?;
    if !metadata.is_dir() || metadata.file_type().is_symlink() {
        return Err(Failure::invalid());
    }
    fs::canonicalize(path).map_err(|_| Failure::invalid())
}

fn resolve_future_directory(path: &Path, working_directory: &Path) -> Result<PathBuf, Failure> {
    let resolved = if path.is_absolute() {
        path.to_path_buf()
    } else {
        working_directory.join(path)
    };
    if resolved
        .components()
        .any(|component| matches!(component, std::path::Component::ParentDir))
    {
        return Err(Failure::invalid());
    }
    reject_link_ancestors(&resolved)?;

    let mut cursor = resolved.clone();
    let mut missing = Vec::new();
    loop {
        match fs::symlink_metadata(&cursor) {
            Ok(metadata) => {
                if metadata.file_type().is_symlink() || !metadata.is_dir() {
                    return Err(Failure::invalid());
                }
                let mut canonical = fs::canonicalize(&cursor).map_err(|_| Failure::invalid())?;
                for component in missing.iter().rev() {
                    canonical.push(component);
                }
                return Ok(canonical);
            }
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                let name = cursor.file_name().ok_or_else(Failure::invalid)?.to_owned();
                missing.push(name);
                if !cursor.pop() {
                    return Err(Failure::invalid());
                }
            }
            Err(_) => return Err(Failure::invalid()),
        }
    }
}

fn reject_link_ancestors(path: &Path) -> Result<(), Failure> {
    for ancestor in path.ancestors() {
        let candidate = if ancestor.as_os_str().is_empty() {
            Path::new(".")
        } else {
            ancestor
        };
        match fs::symlink_metadata(candidate) {
            Ok(metadata) if metadata.file_type().is_symlink() => return Err(Failure::invalid()),
            Ok(_) => {}
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            Err(_) => return Err(Failure::invalid()),
        }
    }
    Ok(())
}

fn string<'a>(object: &'a Map<String, Value>, name: &str) -> Result<&'a str, Failure> {
    object
        .get(name)
        .and_then(Value::as_str)
        .filter(|value| !value.is_empty())
        .ok_or_else(Failure::invalid)
}

fn string_or_null(object: &Map<String, Value>, name: &str) -> Result<Option<String>, Failure> {
    match object.get(name) {
        None | Some(Value::Null) => Ok(None),
        Some(Value::String(value)) if !value.is_empty() => Ok(Some(value.clone())),
        _ => Err(Failure::invalid()),
    }
}

fn path(object: &Map<String, Value>, name: &str) -> Result<PathBuf, Failure> {
    Ok(PathBuf::from(string(object, name)?))
}

fn absolute_path(object: &Map<String, Value>, name: &str) -> Result<PathBuf, Failure> {
    let path = path(object, name)?;
    if path.is_absolute() {
        Ok(path)
    } else {
        Err(Failure::invalid())
    }
}

fn value_path(value: &Value, name: &str) -> Result<PathBuf, Failure> {
    value
        .get(name)
        .and_then(Value::as_str)
        .filter(|value| !value.is_empty())
        .map(PathBuf::from)
        .ok_or_else(Failure::invalid)
}

fn value_path_checked(value: &Value, name: &str, allowed: &[&str]) -> Result<PathBuf, Failure> {
    let object = value.as_object().ok_or_else(Failure::invalid)?;
    require_object_keys(object, allowed, &[name])?;
    value_path(value, name)
}

fn value_optional_path(value: &Value, name: &str) -> Result<Option<PathBuf>, Failure> {
    match value.get(name) {
        None | Some(Value::Null) => Ok(None),
        Some(Value::String(path)) if !path.is_empty() => Ok(Some(PathBuf::from(path))),
        _ => Err(Failure::invalid()),
    }
}

fn value_optional_path_checked(
    value: &Value,
    name: &str,
    allowed: &[&str],
) -> Result<Option<PathBuf>, Failure> {
    let object = value.as_object().ok_or_else(Failure::invalid)?;
    require_object_keys(object, allowed, &[])?;
    value_optional_path(value, name)
}

fn object_optional_path(
    object: &Map<String, Value>,
    name: &str,
) -> Result<Option<PathBuf>, Failure> {
    match object.get(name) {
        None | Some(Value::Null) => Ok(None),
        Some(Value::String(path)) if !path.is_empty() => Ok(Some(PathBuf::from(path))),
        _ => Err(Failure::invalid()),
    }
}

fn value_optional_u32(value: &Value, name: &str) -> Result<Option<u32>, Failure> {
    match value.get(name) {
        None | Some(Value::Null) => Ok(None),
        Some(value) => value
            .as_u64()
            .and_then(|value| u32::try_from(value).ok())
            .ok_or_else(Failure::invalid)
            .map(Some),
    }
}

fn string_array(
    object: &Map<String, Value>,
    name: &str,
) -> Result<Vec<std::ffi::OsString>, Failure> {
    object
        .get(name)
        .and_then(Value::as_array)
        .ok_or_else(Failure::invalid)?
        .iter()
        .map(|value| {
            value
                .as_str()
                .filter(|value| !value.contains('\0'))
                .map(Into::into)
                .ok_or_else(Failure::invalid)
        })
        .collect()
}

fn bounded_u64(value: &Value, maximum: u64) -> Result<u64, Failure> {
    let value = value.as_u64().ok_or_else(Failure::invalid)?;
    (value > 0 && value <= maximum)
        .then_some(value)
        .ok_or_else(Failure::invalid)
}

fn bounded_usize(value: &Value, maximum: usize) -> Result<usize, Failure> {
    let value = value.as_u64().ok_or_else(Failure::invalid)?;
    usize::try_from(value)
        .ok()
        .filter(|value| *value > 0 && *value <= maximum)
        .ok_or_else(Failure::invalid)
}

fn quote(value: &str) -> String {
    serde_json::to_string(value).unwrap_or_else(|_| "\"\"".to_owned())
}

/// Kept as a compile-time assertion that all upstream route spellings remain
/// explicit and cannot accidentally grow a wildcard dispatch.
pub fn known_route(route: &str) -> bool {
    matches!(
        route,
        "agent-spice.fit-yparam"
            | "agent-spice.tune-yparam-tran"
            | "agent-spice.run-hspice"
            | "agent-spice.run-rfm"
            | "pybert.sim"
            | "pybert.sim-native"
            | "pybert.sim-rust"
            | "pybert.sim-auto"
            | "pybert.sim-compare"
            | "agent-com.config-validate"
            | "agent-com.run"
            | "agent-com.compare"
            | "agent-com.public-api"
    )
}

pub const fn max_request_bytes() -> usize {
    MAX_REQUEST_BYTES
}
