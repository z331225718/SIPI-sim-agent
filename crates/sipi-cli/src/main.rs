#![forbid(unsafe_code)]

use std::{
    env,
    io::{self, Cursor, Read},
    path::Path,
    process,
    time::Duration,
};

use sha2::{Digest, Sha256};
use sipi_contracts::{
    ARTIFACT_REPORT_REQUEST_SCHEMA, CAPABILITIES_SCHEMA, CapabilityCatalogV1,
    FIXED_PROJECT_RUN_REQUEST_SCHEMA, IBIS_DC_EVALUATE_REQUEST_SCHEMA, LINK_PLAN_SCHEMA,
    PLANNED_DOMAINS, RULE_LEDGER_V1, artifact_report_request_schema_json, capability_schema_json,
    deterministic_json, fixed_project_run_request_schema_json,
    ibis_dc_evaluate_request_schema_json, ibis_inspect_request_schema_json,
    link_causal_fir_request_schema_json, link_plan_schema_json, parse_artifact_report_request_v1,
    parse_fixed_project_run_request_v1, parse_ibis_dc_evaluate_request_v1,
    parse_ibis_inspect_request_v1, parse_link_causal_fir_request_v1,
    parse_tran_rc_pulse_request_v1, product_example_request_json_v1, project_plan_schema_json,
    receiver_input_schema_json, receiver_semantics_schema_json, tran_rc_pulse_request_schema_json,
    validate_request_v1, validation_request_schema_json,
};
use sipi_ibis::{
    DcClampCornerV1, DcClampProbeV1, IbisDcEvaluateServiceV1, IbisInspectServiceV1, ParseLimitsV1,
    SelectedDcClampProfileV1,
};
use sipi_link::{ConvolutionLimitsV1, convolve_causal_fir_v1};
use sipi_pipeline::{
    CausalFirConsumerConfigV1, FixedTranCausalFirProjectBindingV1,
    run_fixed_tran_causal_fir_project_attempt_v1, validate_fixed_tran_causal_fir_project_v1,
};
use sipi_runtime::{CacheKeyBuilder, ResourceCost, RunId, RunPolicy, Runtime};
use sipi_tran::{RcPulseTransientV1, simulate_rc_pulse_with_context};
use sipi_types::AxisView;

const VERSION: &str = env!("CARGO_PKG_VERSION");
const TARGET: &str = "x86_64-pc-windows-msvc";
const COMMAND_MANIFEST_SCHEMA: &str = "sipi.command-manifest.v1";
const COMMAND_PROTOCOL_CATALOG_SCHEMA: &str = "sipi.command-protocol-catalog.v1";

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum CommandAvailabilityV1 {
    Available,
    Unavailable,
}

impl CommandAvailabilityV1 {
    const fn as_str(self) -> &'static str {
        match self {
            Self::Available => "available",
            Self::Unavailable => "unavailable",
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct CommandDescriptorV1 {
    id: &'static str,
    route: &'static [&'static str],
    availability: CommandAvailabilityV1,
    transport: &'static str,
    request_schema: Option<&'static str>,
    response_schema: Option<&'static str>,
    unavailable_reason: Option<&'static str>,
    nonclaim: &'static str,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct CommandProtocolProfileV1 {
    command_id: &'static str,
    example_id: Option<&'static str>,
    required_options: &'static [&'static str],
    caller_bindings: &'static [CallerBindingV1],
    validation_rule_id: Option<&'static str>,
    successful_exit: i32,
    diagnostic_contract: &'static str,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct CallerBindingV1 {
    pointer: &'static str,
    role: &'static str,
    explicit_required: bool,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct DiagnosticCodeV1 {
    code: &'static str,
    stage: &'static str,
    rule_id: &'static str,
}

const ARTIFACT_DESTINATION_BINDINGS: &[CallerBindingV1] = &[
    CallerBindingV1 {
        pointer: "/invocation/artifact_root",
        role: "local_artifact_destination",
        explicit_required: true,
    },
    CallerBindingV1 {
        pointer: "/invocation/artifact_id",
        role: "artifact_identity",
        explicit_required: true,
    },
];

const ARTIFACT_INSPECTION_BINDINGS: &[CallerBindingV1] = &[
    CallerBindingV1 {
        pointer: "/artifact_root",
        role: "caller_owned_artifact_root",
        explicit_required: true,
    },
    CallerBindingV1 {
        pointer: "/artifact_id",
        role: "published_artifact_identity",
        explicit_required: true,
    },
];

const DIAGNOSTIC_CODES_V1: &[DiagnosticCodeV1] = &[
    DiagnosticCodeV1 {
        code: "usage",
        stage: "protocol",
        rule_id: "cli.route.v1",
    },
    DiagnosticCodeV1 {
        code: "invalid_input",
        stage: "protocol",
        rule_id: "cli.stdin-json.v1",
    },
    DiagnosticCodeV1 {
        code: "contract_rejected",
        stage: "schema",
        rule_id: "contract.cross-field.v1",
    },
    DiagnosticCodeV1 {
        code: "capability_unavailable",
        stage: "protocol",
        rule_id: "cli.capability-admission.v1",
    },
    DiagnosticCodeV1 {
        code: "unsupported",
        stage: "protocol",
        rule_id: "cli.command-shape.v1",
    },
    DiagnosticCodeV1 {
        code: "example_not_applicable",
        stage: "protocol",
        rule_id: "cli.example-admission.v1",
    },
    DiagnosticCodeV1 {
        code: "unknown_command_example",
        stage: "protocol",
        rule_id: "cli.example-admission.v1",
    },
    DiagnosticCodeV1 {
        code: "unknown_schema",
        stage: "schema",
        rule_id: "cli.schema-registry.v1",
    },
    DiagnosticCodeV1 {
        code: "unknown_capability",
        stage: "protocol",
        rule_id: "cli.capability-registry.v1",
    },
    DiagnosticCodeV1 {
        code: "invalid_artifact_id",
        stage: "admission",
        rule_id: "artifact.id.v1",
    },
    DiagnosticCodeV1 {
        code: "operational_failure",
        stage: "runtime",
        rule_id: "runtime.execution.v1",
    },
    DiagnosticCodeV1 {
        code: "internal_failure",
        stage: "runtime",
        rule_id: "runtime.internal.v1",
    },
    DiagnosticCodeV1 {
        code: "internal_contract_error",
        stage: "schema",
        rule_id: "contract.registry.v1",
    },
    DiagnosticCodeV1 {
        code: "self_check_failed",
        stage: "schema",
        rule_id: "cli.self-check.v1",
    },
];

const COMMAND_MANIFEST_V1: &[CommandDescriptorV1] = &[
    CommandDescriptorV1 {
        id: "version",
        route: &["version"],
        availability: CommandAvailabilityV1::Available,
        transport: "none",
        request_schema: None,
        response_schema: Some("sipi.cli-version.v1"),
        unavailable_reason: None,
        nonclaim: "static_product_identity_only",
    },
    CommandDescriptorV1 {
        id: "doctor",
        route: &["doctor"],
        availability: CommandAvailabilityV1::Available,
        transport: "none",
        request_schema: None,
        response_schema: Some("sipi.cli-doctor.v1"),
        unavailable_reason: None,
        nonclaim: "external_runtime_not_checked",
    },
    CommandDescriptorV1 {
        id: "capabilities",
        route: &["capabilities"],
        availability: CommandAvailabilityV1::Available,
        transport: "none",
        request_schema: None,
        response_schema: Some(CAPABILITIES_SCHEMA),
        unavailable_reason: None,
        nonclaim: "capabilities_are_scope_limited",
    },
    CommandDescriptorV1 {
        id: "commands",
        route: &["commands"],
        availability: CommandAvailabilityV1::Available,
        transport: "none",
        request_schema: None,
        response_schema: Some(COMMAND_MANIFEST_SCHEMA),
        unavailable_reason: None,
        nonclaim: "command_discovery_only",
    },
    CommandDescriptorV1 {
        id: "protocols",
        route: &["protocols"],
        availability: CommandAvailabilityV1::Available,
        transport: "none",
        request_schema: None,
        response_schema: Some(COMMAND_PROTOCOL_CATALOG_SCHEMA),
        unavailable_reason: None,
        nonclaim: "protocol_discovery_only",
    },
    CommandDescriptorV1 {
        id: "example",
        route: &["example"],
        availability: CommandAvailabilityV1::Available,
        transport: "none",
        request_schema: None,
        response_schema: None,
        unavailable_reason: None,
        nonclaim: "example_is_not_a_result_or_artifact",
    },
    CommandDescriptorV1 {
        id: "schema",
        route: &["schema"],
        availability: CommandAvailabilityV1::Available,
        transport: "none",
        request_schema: None,
        response_schema: Some("sipi.cli-schema-list.v1"),
        unavailable_reason: None,
        nonclaim: "schema_discovery_only",
    },
    CommandDescriptorV1 {
        id: "validate",
        route: &["validate"],
        availability: CommandAvailabilityV1::Available,
        transport: "stdin_json_v1",
        request_schema: Some("sipi.validation-request.v1"),
        response_schema: Some("sipi.cli-validate.v1"),
        unavailable_reason: None,
        nonclaim: "validation_does_not_execute_a_simulation",
    },
    CommandDescriptorV1 {
        id: "inspect.self",
        route: &["inspect", "self"],
        availability: CommandAvailabilityV1::Available,
        transport: "none",
        request_schema: None,
        response_schema: Some("sipi.cli-inspect.v1"),
        unavailable_reason: None,
        nonclaim: "static_discovery_only",
    },
    CommandDescriptorV1 {
        id: "ibis.inspect",
        route: &["ibis", "inspect"],
        availability: CommandAvailabilityV1::Available,
        transport: "stdin_json_v1",
        request_schema: Some(sipi_contracts::IBIS_INSPECT_REQUEST_SCHEMA),
        response_schema: Some("sipi.ibis.inspect.response.v1"),
        unavailable_reason: None,
        nonclaim: "structural_inspection_only",
    },
    CommandDescriptorV1 {
        id: "ibis.dc-evaluate",
        route: &["ibis", "dc-evaluate"],
        availability: CommandAvailabilityV1::Available,
        transport: "stdin_json_v1",
        request_schema: Some(IBIS_DC_EVALUATE_REQUEST_SCHEMA),
        response_schema: Some("sipi.ibis.input-typ-dc-evaluate.response.v1"),
        unavailable_reason: None,
        nonclaim: "caller_input_static_dc_only",
    },
    CommandDescriptorV1 {
        id: "tran.run",
        route: &["tran", "run"],
        availability: CommandAvailabilityV1::Available,
        transport: "stdin_json_v1",
        request_schema: Some(sipi_contracts::TRAN_RC_PULSE_REQUEST_SCHEMA),
        response_schema: Some("sipi.tran.run-result.v1"),
        unavailable_reason: None,
        nonclaim: "fixed_rc_pulse_profile_only",
    },
    CommandDescriptorV1 {
        id: "link.run",
        route: &["link", "run"],
        availability: CommandAvailabilityV1::Available,
        transport: "stdin_json_v1",
        request_schema: Some(sipi_contracts::LINK_CAUSAL_FIR_REQUEST_SCHEMA),
        response_schema: Some("sipi.link.run-result.v1"),
        unavailable_reason: None,
        nonclaim: "causal_fir_direct_launch_only",
    },
    CommandDescriptorV1 {
        id: "channel.run",
        route: &["channel", "run"],
        availability: CommandAvailabilityV1::Unavailable,
        transport: "none",
        request_schema: None,
        response_schema: None,
        unavailable_reason: Some("channel_profile_not_admitted"),
        nonclaim: "no_s_parameter_or_channel_resolver",
    },
    CommandDescriptorV1 {
        id: "ami.run",
        route: &["ami", "run"],
        availability: CommandAvailabilityV1::Unavailable,
        transport: "none",
        request_schema: None,
        response_schema: None,
        unavailable_reason: Some("ami_runtime_not_admitted"),
        nonclaim: "no_vendor_dll_or_ami_workflow",
    },
    CommandDescriptorV1 {
        id: "com.run",
        route: &["com", "run"],
        availability: CommandAvailabilityV1::Unavailable,
        transport: "none",
        request_schema: None,
        response_schema: None,
        unavailable_reason: Some("com_profile_not_admitted"),
        nonclaim: "no_com_solver_or_oracle_workflow",
    },
    CommandDescriptorV1 {
        id: "project.validate",
        route: &["project", "validate"],
        availability: CommandAvailabilityV1::Unavailable,
        transport: "none",
        request_schema: None,
        response_schema: None,
        unavailable_reason: Some("project_execution_not_implemented"),
        nonclaim: "no_project_execution",
    },
    CommandDescriptorV1 {
        id: "project.run",
        route: &["project", "run"],
        availability: CommandAvailabilityV1::Available,
        transport: "stdin_json_v1",
        request_schema: Some(FIXED_PROJECT_RUN_REQUEST_SCHEMA),
        response_schema: Some("sipi.project.fixed-tran-causal-fir-run-result.v1"),
        unavailable_reason: None,
        nonclaim: "one_fixed_composite_project_route_only",
    },
    CommandDescriptorV1 {
        id: "compare.run",
        route: &["compare", "run"],
        availability: CommandAvailabilityV1::Unavailable,
        transport: "none",
        request_schema: None,
        response_schema: None,
        unavailable_reason: Some("external_comparator_not_exposed"),
        nonclaim: "no_oracle_or_comparison_workflow",
    },
    CommandDescriptorV1 {
        id: "report.inspect",
        route: &["report", "inspect"],
        availability: CommandAvailabilityV1::Available,
        transport: "stdin_json_v1",
        request_schema: Some(ARTIFACT_REPORT_REQUEST_SCHEMA),
        response_schema: Some(sipi_artifacts::ARTIFACT_REPORT_SCHEMA_V1),
        unavailable_reason: None,
        nonclaim: "verified_integrity_metadata_only",
    },
    CommandDescriptorV1 {
        id: "report.show",
        route: &["report", "show"],
        availability: CommandAvailabilityV1::Unavailable,
        transport: "none",
        request_schema: None,
        response_schema: None,
        unavailable_reason: Some("artifact_payload_preview_not_implemented"),
        nonclaim: "no_payload_or_external_provenance_viewer",
    },
];

const COMMAND_PROTOCOL_PROFILES_V1: &[CommandProtocolProfileV1] = &[
    CommandProtocolProfileV1 {
        command_id: "version",
        example_id: None,
        required_options: &[],
        caller_bindings: &[],
        validation_rule_id: None,
        successful_exit: 0,
        diagnostic_contract: "no_stdin_or_diagnostics_on_success",
    },
    CommandProtocolProfileV1 {
        command_id: "doctor",
        example_id: None,
        required_options: &[],
        caller_bindings: &[],
        validation_rule_id: None,
        successful_exit: 0,
        diagnostic_contract: "no_stdin_or_diagnostics_on_success",
    },
    CommandProtocolProfileV1 {
        command_id: "capabilities",
        example_id: None,
        required_options: &[],
        caller_bindings: &[],
        validation_rule_id: None,
        successful_exit: 0,
        diagnostic_contract: "no_stdin_or_diagnostics_on_success",
    },
    CommandProtocolProfileV1 {
        command_id: "commands",
        example_id: None,
        required_options: &[],
        caller_bindings: &[],
        validation_rule_id: None,
        successful_exit: 0,
        diagnostic_contract: "no_stdin_or_diagnostics_on_success",
    },
    CommandProtocolProfileV1 {
        command_id: "protocols",
        example_id: None,
        required_options: &[],
        caller_bindings: &[],
        validation_rule_id: None,
        successful_exit: 0,
        diagnostic_contract: "no_stdin_or_diagnostics_on_success",
    },
    CommandProtocolProfileV1 {
        command_id: "example",
        example_id: None,
        required_options: &[],
        caller_bindings: &[],
        validation_rule_id: None,
        successful_exit: 0,
        diagnostic_contract: "example_not_applicable_to_static_discovery",
    },
    CommandProtocolProfileV1 {
        command_id: "schema",
        example_id: None,
        required_options: &[],
        caller_bindings: &[],
        validation_rule_id: None,
        successful_exit: 0,
        diagnostic_contract: "no_stdin_or_diagnostics_on_success",
    },
    CommandProtocolProfileV1 {
        command_id: "validate",
        example_id: Some("product-owned-minimal-v1"),
        required_options: &[],
        caller_bindings: &[],
        validation_rule_id: Some("contract.v1.version"),
        successful_exit: 0,
        diagnostic_contract: "single_json_stdout_and_zero_stderr_on_success",
    },
    CommandProtocolProfileV1 {
        command_id: "inspect.self",
        example_id: None,
        required_options: &[],
        caller_bindings: &[],
        validation_rule_id: None,
        successful_exit: 0,
        diagnostic_contract: "no_stdin_or_diagnostics_on_success",
    },
    CommandProtocolProfileV1 {
        command_id: "ibis.inspect",
        example_id: Some("product-owned-minimal-v1"),
        required_options: &[],
        caller_bindings: &[],
        validation_rule_id: Some("ibis.inspect.structural.v1"),
        successful_exit: 0,
        diagnostic_contract: "single_json_stdout_and_zero_stderr_on_success",
    },
    CommandProtocolProfileV1 {
        command_id: "ibis.dc-evaluate",
        example_id: Some("product-owned-minimal-v1"),
        required_options: &[],
        caller_bindings: &[],
        validation_rule_id: Some("ibis.input-typ.static-dc.v1"),
        successful_exit: 0,
        diagnostic_contract: "single_json_stdout_and_zero_stderr_on_success",
    },
    CommandProtocolProfileV1 {
        command_id: "tran.run",
        example_id: Some("product-owned-minimal-v1"),
        required_options: &["--artifact-root", "--artifact-id"],
        caller_bindings: ARTIFACT_DESTINATION_BINDINGS,
        validation_rule_id: Some("tran.rc-pulse.profile"),
        successful_exit: 0,
        diagnostic_contract: "single_json_stdout_and_zero_stderr_on_success",
    },
    CommandProtocolProfileV1 {
        command_id: "link.run",
        example_id: Some("product-owned-minimal-v1"),
        required_options: &["--artifact-root", "--artifact-id"],
        caller_bindings: ARTIFACT_DESTINATION_BINDINGS,
        validation_rule_id: Some("link.v1.causal-fir"),
        successful_exit: 0,
        diagnostic_contract: "single_json_stdout_and_zero_stderr_on_success",
    },
    CommandProtocolProfileV1 {
        command_id: "project.run",
        example_id: Some("product-owned-minimal-v1"),
        required_options: &["--artifact-root", "--artifact-id"],
        caller_bindings: ARTIFACT_DESTINATION_BINDINGS,
        validation_rule_id: Some("project.fixed-tran-causal-fir.admission"),
        successful_exit: 0,
        diagnostic_contract: "single_json_stdout_and_zero_stderr_on_success",
    },
    CommandProtocolProfileV1 {
        command_id: "report.inspect",
        example_id: None,
        required_options: &[],
        caller_bindings: ARTIFACT_INSPECTION_BINDINGS,
        validation_rule_id: Some("artifact.report.request.v1"),
        successful_exit: 0,
        diagnostic_contract: "single_json_stdout_and_zero_stderr_on_success",
    },
];

struct Response {
    code: i32,
    stdout: Option<String>,
    stderr: Option<String>,
}

struct CommandService;

fn main() {
    let arguments = env::args().skip(1).collect::<Vec<_>>();
    let command = arguments.first().map_or("help", String::as_str);
    let response = if arguments == ["validate", "--stdin"] {
        ProcessAdapter::validate_stdin()
    } else if arguments == ["ibis", "inspect", "--stdin"] {
        ProcessAdapter::ibis_inspect_stdin()
    } else if arguments == ["ibis", "dc-evaluate", "--stdin"] {
        ProcessAdapter::ibis_dc_evaluate_stdin()
    } else if arguments == ["report", "inspect", "--stdin"] {
        ProcessAdapter::report_inspect_stdin()
    } else if let [command, action, stdin, root, artifact_root, id, artifact_id] = &arguments[..]
        && command == "tran"
        && action == "run"
        && stdin == "--stdin"
        && root == "--artifact-root"
        && id == "--artifact-id"
    {
        ProcessAdapter::tran_run_stdin(artifact_root, artifact_id)
    } else if let [command, action, stdin, root, artifact_root, id, artifact_id] = &arguments[..]
        && command == "link"
        && action == "run"
        && stdin == "--stdin"
        && root == "--artifact-root"
        && id == "--artifact-id"
    {
        ProcessAdapter::link_run_stdin(artifact_root, artifact_id)
    } else if let [command, action, stdin, root, artifact_root, id, artifact_id] = &arguments[..]
        && command == "project"
        && action == "run"
        && stdin == "--stdin"
        && root == "--artifact-root"
        && id == "--artifact-id"
    {
        ProcessAdapter::project_run_stdin(artifact_root, artifact_id)
    } else {
        dispatch(&arguments)
    };
    println!("{}", envelope_json(command, &response));
    if let Some(stderr) = response.stderr.as_deref() {
        eprintln!("{}", diagnostic_json(command, stderr));
    }
    process::exit(response.code);
}

struct ProcessAdapter;

impl ProcessAdapter {
    fn validate_stdin() -> Response {
        const MAXIMUM: usize = 1_048_576;
        let mut input = Vec::with_capacity(8192);
        if io::stdin()
            .take((MAXIMUM + 1) as u64)
            .read_to_end(&mut input)
            .is_err()
        {
            return error(5, "operational_failure", "stdin could not be read");
        }
        if input.len() > MAXIMUM || input.is_empty() || input.starts_with(&[0xEF, 0xBB, 0xBF]) {
            return error(2, "invalid_input", "stdin request is invalid");
        }
        match validate_request_v1(&input) {
            Ok(()) => success("{\"subject\":\"validation-request\"}".to_owned()),
            Err(_) => error(3, "contract_rejected", "stdin request was rejected"),
        }
    }

    fn tran_run_stdin(artifact_root: &str, artifact_id: &str) -> Response {
        let input = match read_stdin_request() {
            Ok(input) => input,
            Err(code) => return error(2, code, "stdin request is invalid"),
        };
        if parse_tran_rc_pulse_request_v1(&input).is_err() {
            return error(3, "contract_rejected", "TRAN request was rejected");
        }
        run_fixed_tran(artifact_root, artifact_id, &input)
    }

    fn link_run_stdin(artifact_root: &str, artifact_id: &str) -> Response {
        let input = match read_stdin_request() {
            Ok(input) => input,
            Err(code) => return error(2, code, "stdin request is invalid"),
        };
        let request = match parse_link_causal_fir_request_v1(&input) {
            Ok(request) => request,
            Err(_) => return error(3, "contract_rejected", "Link request was rejected"),
        };
        run_causal_fir_link(artifact_root, artifact_id, &request)
    }

    fn project_run_stdin(artifact_root: &str, artifact_id: &str) -> Response {
        let input = match read_stdin_request() {
            Ok(input) => input,
            Err(code) => return error(2, code, "stdin request is invalid"),
        };
        let request = match parse_fixed_project_run_request_v1(&input) {
            Ok(request) => request,
            Err(_) => return error(3, "contract_rejected", "project request was rejected"),
        };
        run_fixed_project(artifact_root, artifact_id, &request)
    }

    fn ibis_inspect_stdin() -> Response {
        let input = match read_stdin_request() {
            Ok(input) => input,
            Err(code) => return error(2, code, "stdin request is invalid"),
        };
        let request = match parse_ibis_inspect_request_v1(&input) {
            Ok(request) => request,
            Err(_) => return error(3, "contract_rejected", "IBIS inspect request was rejected"),
        };
        run_ibis_inspect(request.text())
    }

    fn ibis_dc_evaluate_stdin() -> Response {
        let input = match read_stdin_request() {
            Ok(input) => input,
            Err(code) => return error(2, code, "stdin request is invalid"),
        };
        let request = match parse_ibis_dc_evaluate_request_v1(&input) {
            Ok(request) => request,
            Err(_) => return error(3, "contract_rejected", "IBIS DC request was rejected"),
        };
        run_ibis_dc_evaluate(&request)
    }

    fn report_inspect_stdin() -> Response {
        let input = match read_stdin_request() {
            Ok(input) => input,
            Err(code) => return error(2, code, "stdin request is invalid"),
        };
        let request = match parse_artifact_report_request_v1(&input) {
            Ok(request) => request,
            Err(_) => {
                return error(
                    3,
                    "contract_rejected",
                    "artifact report request was rejected",
                );
            }
        };
        run_artifact_report(request.artifact_root(), request.artifact_id())
    }
}

fn read_stdin_request() -> Result<Vec<u8>, &'static str> {
    const MAXIMUM: usize = 1_048_576;
    let mut input = Vec::with_capacity(8192);
    io::stdin()
        .take((MAXIMUM + 1) as u64)
        .read_to_end(&mut input)
        .map_err(|_| "operational_failure")?;
    if input.len() > MAXIMUM || input.is_empty() || input.starts_with(&[0xEF, 0xBB, 0xBF]) {
        Err("invalid_input")
    } else {
        Ok(input)
    }
}

fn run_fixed_tran(artifact_root: &str, artifact_id: &str, request: &[u8]) -> Response {
    let policy = match RunPolicy::try_new(Duration::from_secs(1), 16, 1_048_576) {
        Ok(policy) => policy,
        Err(_) => return error(6, "internal_failure", "run policy is unavailable"),
    };
    run_fixed_tran_with_policy(artifact_root, artifact_id, request, policy)
}

fn run_fixed_tran_with_policy(
    artifact_root: &str,
    artifact_id: &str,
    request: &[u8],
    policy: RunPolicy,
) -> Response {
    let id = match RunId::try_new(artifact_id) {
        Ok(id) => id,
        Err(_) => return error(2, "invalid_artifact_id", "artifact id is invalid"),
    };
    let (_, context) = match Runtime::start(id, policy) {
        Ok(run) => run,
        Err(_) => return error(6, "internal_failure", "runtime is unavailable"),
    };
    let request_key = cache_key("request", request);
    let root = Path::new(artifact_root);
    let result = Runtime::execute(&context, |context| -> Result<_, ()> {
        context
            .consume(ResourceCost {
                work_units: 1,
                accounted_bytes: request.len() as u64 + 4096,
            })
            .map_err(|_| ())?;
        let simulation =
            simulate_rc_pulse_with_context(RcPulseTransientV1::fixed_profile(), context)
                .map_err(|_| ())?;
        let result_json = result_json(&simulation).map_err(|_| ())?;
        let result_key = cache_key("result", result_json.as_bytes());
        let provenance = format!(
            "{{\"schema\":\"sipi.tran.provenance.v1\",\"algorithm\":\"backward_euler_rc_pulse_v1\",\"request_cache_key\":\"{request_key}\",\"result_cache_key\":\"{result_key}\",\"run_policy_id\":\"sipi.tran.fixed-policy.v1\",\"contract\":\"sipi.tran.rc-pulse-request.v1\",\"target\":\"{TARGET}\"}}"
        );
        let store = sipi_artifacts::ArtifactRoot::open_or_create(root).map_err(|_| ())?;
        let mut staging = store.begin(artifact_id).map_err(|_| ())?;
        staging
            .stage_reader(
                "result.json",
                Cursor::new(result_json.into_bytes()),
                1_048_576,
            )
            .map_err(|_| ())?;
        staging
            .stage_reader(
                "provenance.json",
                Cursor::new(provenance.into_bytes()),
                16_384,
            )
            .map_err(|_| ())?;
        let manifest = staging
            .seal()
            .and_then(|sealed| sealed.publish_new())
            .map_err(|_| ())?;
        Ok((request_key, manifest))
    });
    match result {
        Ok((request_key, manifest)) => success(format!(
            "{{\"schema\":\"sipi.tran.run-result.v1\",\"artifact_id\":\"{}\",\"request_cache_key\":\"{}\",\"manifest_schema\":\"{}\",\"file_count\":{}}}",
            manifest.artifact_id,
            request_key,
            manifest.schema,
            manifest.files.len()
        )),
        Err(_) => error(
            5,
            "operational_failure",
            "TRAN run did not publish an artifact",
        ),
    }
}

fn run_causal_fir_link(
    artifact_root: &str,
    artifact_id: &str,
    request: &sipi_contracts::LinkCausalFirRequestV1,
) -> Response {
    let canonical_request =
        match deterministic_json(&sipi_contracts::WireLinkCausalFirRequestV1::from(request)) {
            Ok(bytes) => bytes,
            Err(_) => {
                return error(
                    6,
                    "internal_contract_error",
                    "Link request cannot be serialized",
                );
            }
        };
    let limits = match ConvolutionLimitsV1::try_new(
        request.limits().max_output_samples().get(),
        request.limits().max_multiply_accumulates().get(),
    ) {
        Ok(limits) => limits,
        Err(_) => return error(5, "operational_failure", "Link limits are unavailable"),
    };
    let received = match convolve_causal_fir_v1(request.plan(), limits) {
        Ok(received) => received,
        Err(_) => return error(5, "operational_failure", "Link convolution failed"),
    };
    let result_json = match link_result_json(&received) {
        Ok(result) => result,
        Err(_) => {
            return error(
                6,
                "internal_contract_error",
                "Link result cannot be serialized",
            );
        }
    };
    let request_key = cache_key("link-request", &canonical_request);
    let kernel_json =
        match deterministic_json(&sipi_contracts::WireLinkPlanV1::from(request.plan())) {
            Ok(bytes) => bytes,
            Err(_) => {
                return error(
                    6,
                    "internal_contract_error",
                    "Link kernel cannot be serialized",
                );
            }
        };
    let kernel_key = cache_key("link-kernel", &kernel_json);
    let result_key = cache_key("link-result", result_json.as_bytes());
    let provenance = format!(
        "{{\"schema\":\"sipi.link.provenance.v1\",\"algorithm\":\"causal-fir-convolution.v1\",\"request_cache_key\":\"{request_key}\",\"kernel_cache_key\":\"{kernel_key}\",\"result_cache_key\":\"{result_key}\",\"contract\":\"sipi.link.causal-fir-request.v1\",\"max_output_samples\":{},\"max_multiply_accumulates\":{},\"target\":\"{TARGET}\"}}",
        request.limits().max_output_samples(),
        request.limits().max_multiply_accumulates()
    );
    let store = match sipi_artifacts::ArtifactRoot::open_or_create(Path::new(artifact_root)) {
        Ok(store) => store,
        Err(_) => {
            return error(
                5,
                "operational_failure",
                "Link artifact root is unavailable",
            );
        }
    };
    let mut staging = match store.begin(artifact_id) {
        Ok(staging) => staging,
        Err(_) => return error(5, "operational_failure", "Link artifact cannot be created"),
    };
    let publication = staging
        .stage_reader("request.json", Cursor::new(canonical_request), 1_048_576)
        .and_then(|_| {
            staging.stage_reader(
                "received-waveform.json",
                Cursor::new(result_json.into_bytes()),
                1_048_576,
            )
        })
        .and_then(|_| {
            staging.stage_reader(
                "provenance.json",
                Cursor::new(provenance.into_bytes()),
                16_384,
            )
        })
        .and_then(|_| staging.seal())
        .and_then(|sealed| sealed.publish_new());
    match publication {
        Ok(manifest) => success(format!(
            "{{\"schema\":\"sipi.link.run-result.v1\",\"artifact_id\":\"{}\",\"request_cache_key\":\"{request_key}\",\"result_cache_key\":\"{result_key}\",\"manifest_schema\":\"{}\",\"file_count\":{}}}",
            manifest.artifact_id,
            manifest.schema,
            manifest.files.len()
        )),
        Err(_) => error(
            5,
            "operational_failure",
            "Link run did not publish an artifact",
        ),
    }
}

fn run_fixed_project(
    artifact_root: &str,
    artifact_id: &str,
    request: &sipi_contracts::FixedProjectRunRequestV1,
) -> Response {
    let canonical_request =
        match deterministic_json(&sipi_contracts::WireFixedProjectRunRequestV1::from(request)) {
            Ok(bytes) => bytes,
            Err(_) => {
                return error(
                    6,
                    "internal_contract_error",
                    "project request cannot be serialized",
                );
            }
        };
    let limits = match ConvolutionLimitsV1::try_new(
        request.limits().max_output_samples().get(),
        request.limits().max_multiply_accumulates().get(),
    ) {
        Ok(limits) => limits,
        Err(_) => return error(3, "contract_rejected", "project limits were rejected"),
    };
    let consumer = match CausalFirConsumerConfigV1::try_new(request.channel().clone(), limits) {
        Ok(consumer) => consumer,
        Err(_) => {
            return error(
                3,
                "contract_rejected",
                "project consumer policy was rejected",
            );
        }
    };
    let binding =
        FixedTranCausalFirProjectBindingV1::new(RcPulseTransientV1::fixed_profile(), consumer);
    let admission = match validate_fixed_tran_causal_fir_project_v1(request.plan().clone(), binding)
    {
        Ok(admission) => admission,
        Err(_) => {
            return error(3, "contract_rejected", "project topology was rejected");
        }
    };
    let project_policy = admission.plan().resource_policy();
    let policy = match RunPolicy::try_new(
        Duration::from_millis(project_policy.timeout_millis()),
        project_policy.max_work_units(),
        project_policy.max_accounted_bytes(),
    ) {
        Ok(policy) => policy,
        Err(_) => return error(3, "contract_rejected", "project policy was rejected"),
    };
    let run_id = match RunId::try_new(admission.plan().project_id()) {
        Ok(id) => id,
        Err(_) => return error(3, "contract_rejected", "project id was rejected"),
    };
    let (_, context) = match Runtime::start(run_id, policy) {
        Ok(run) => run,
        Err(_) => return error(6, "internal_failure", "project runtime is unavailable"),
    };
    let attempt = match run_fixed_tran_causal_fir_project_attempt_v1(&admission, &context) {
        Ok(attempt) => attempt,
        Err(_) => return error(5, "operational_failure", "project attempt did not complete"),
    };
    let received_json = match link_result_json(attempt.received()) {
        Ok(result) => result,
        Err(_) => {
            return error(
                6,
                "internal_contract_error",
                "project result cannot be serialized",
            );
        }
    };
    let edge_json = project_edge_record_json(attempt.edge_record());
    let project_digest = attempt.project_digest().hex();
    let binding_digest = attempt.binding_digest().hex();
    let received_digest = attempt.edge_record().received_output_digest().hex();
    let request_digest = cache_key("project-request", &canonical_request);
    let provenance = format!(
        "{{\"schema\":\"sipi.project.fixed-tran-causal-fir-provenance.v1\",\"algorithm\":\"fixed-tran-to-causal-fir.v1\",\"project_digest\":\"{project_digest}\",\"binding_digest\":\"{binding_digest}\",\"request_digest\":\"{request_digest}\",\"received_output_digest\":\"{received_digest}\",\"attempt_index\":1,\"target\":\"{TARGET}\"}}"
    );
    let publication = sipi_artifacts::ArtifactRoot::open_or_create(Path::new(artifact_root))
        .and_then(|store| store.begin(artifact_id))
        .and_then(|mut staging| {
            staging.stage_reader("request.json", Cursor::new(canonical_request), 1_048_576)?;
            staging.stage_reader(
                "received-waveform.json",
                Cursor::new(received_json.into_bytes()),
                1_048_576,
            )?;
            staging.stage_reader(
                "edge-record.json",
                Cursor::new(edge_json.into_bytes()),
                16_384,
            )?;
            staging.stage_reader(
                "provenance.json",
                Cursor::new(provenance.into_bytes()),
                16_384,
            )?;
            staging.seal()?.publish_new()
        });
    match publication {
        Ok(manifest) => success(format!(
            "{{\"schema\":\"sipi.project.fixed-tran-causal-fir-run-result.v1\",\"artifact_id\":\"{}\",\"project_digest\":\"{project_digest}\",\"binding_digest\":\"{binding_digest}\",\"received_output_digest\":\"{received_digest}\",\"manifest_schema\":\"{}\",\"file_count\":{}}}",
            manifest.artifact_id,
            manifest.schema,
            manifest.files.len()
        )),
        Err(_) => error(
            5,
            "operational_failure",
            "project run did not publish an artifact",
        ),
    }
}

fn project_edge_record_json(record: &sipi_pipeline::TranRcPulseToCausalFirEdgeRecordV1) -> String {
    format!(
        "{{\"schema\":\"{}\",\"implementation_revision\":\"{}\",\"producer_contract\":\"{}\",\"producer_profile\":\"{}\",\"producer_output_port\":\"{}\",\"consumer_contract\":\"{}\",\"consumer_input_port\":\"{}\",\"signal_map\":\"{}\",\"producer_artifact_digest\":\"{}\",\"consumer_input_digest\":\"{}\",\"consumer_policy_digest\":\"{}\",\"received_output_digest\":\"{}\"}}",
        record.schema(),
        record.implementation_revision(),
        record.producer_contract(),
        record.producer_profile(),
        record.producer_output_port(),
        record.consumer_contract(),
        record.consumer_input_port(),
        record.signal_map(),
        record.producer_artifact_digest().hex(),
        record.consumer_input_digest().hex(),
        record.consumer_policy_digest().hex(),
        record.received_output_digest().hex(),
    )
}

fn run_artifact_report(artifact_root: &str, artifact_id: &str) -> Response {
    let root = match sipi_artifacts::ArtifactRoot::open_existing(Path::new(artifact_root)) {
        Ok(root) => root,
        Err(_) => return error(5, "operational_failure", "artifact root is unavailable"),
    };
    let policy =
        match sipi_artifacts::ArtifactReportPolicyV1::try_new(65_536, 64, 16 * 1024 * 1024, 16_384)
        {
            Ok(policy) => policy,
            Err(_) => {
                return error(
                    6,
                    "internal_failure",
                    "artifact report policy is unavailable",
                );
            }
        };
    match root.inspect_verified_v1(artifact_id, policy) {
        Ok(report) => match deterministic_json(&report) {
            Ok(bytes) => match String::from_utf8(bytes) {
                Ok(value) => success(value),
                Err(_) => error(6, "internal_failure", "artifact report is not UTF-8"),
            },
            Err(_) => error(6, "internal_failure", "artifact report is unavailable"),
        },
        Err(sipi_artifacts::ArtifactError::InvalidId) => {
            error(2, "invalid_artifact_id", "artifact id is invalid")
        }
        Err(_) => error(
            5,
            "operational_failure",
            "artifact report verification failed",
        ),
    }
}

fn run_ibis_inspect(text: &str) -> Response {
    let limits = match ParseLimitsV1::try_new(1_048_576, 65_536, 16_384, 16_384) {
        Ok(limits) => limits,
        Err(_) => return error(6, "internal_contract_error", "IBIS limits are unavailable"),
    };
    match IbisInspectServiceV1::inspect(text, limits) {
        Ok(report) => success(format!(
            "{{\"schema\":\"sipi.ibis.inspect.response.v1\",\"input_byte_length\":{},\"input_sha256\":\"{}\",\"declared_version\":\"{}\",\"component_count\":{},\"model_count\":{},\"block_count\":{},\"structural_parse\":\"accepted\",\"typed_envelope\":\"accepted\",\"electrical_behavior\":\"{}\",\"external_profile_acceptance\":\"{}\",\"capability_matrix_id\":\"{}\"}}",
            report.input_byte_length(),
            report.input_sha256(),
            report.declared_version(),
            report.component_count(),
            report.model_count(),
            report.block_count(),
            report.electrical_behavior_status(),
            report.external_profile_acceptance_status(),
            report.capability_matrix_id(),
        )),
        Err(_) => error(3, "contract_rejected", "IBIS text was rejected"),
    }
}

fn run_ibis_dc_evaluate(request: &sipi_contracts::IbisDcEvaluateRequestV1) -> Response {
    let limits = match ParseLimitsV1::try_new(1_048_576, 65_536, 16_384, 16_384) {
        Ok(limits) => limits,
        Err(_) => return error(6, "internal_contract_error", "IBIS limits are unavailable"),
    };
    let profile = match SelectedDcClampProfileV1::try_new(
        request.ibis_version(),
        request.model_selector(),
        DcClampCornerV1::Typical,
    ) {
        Ok(profile) => profile,
        Err(_) => return error(3, "contract_rejected", "IBIS selection was rejected"),
    };
    let probe = DcClampProbeV1::new(
        request.gnd_clamp_drive_volts(),
        request.power_clamp_drive_volts(),
    );
    match IbisDcEvaluateServiceV1::evaluate(request.text(), &profile, probe, limits) {
        Ok(report) => success(format!(
            "{{\"schema\":\"sipi.ibis.input-typ-dc-evaluate.response.v1\",\"input_byte_length\":{},\"input_sha256\":\"{}\",\"selection\":{{\"ibis_version\":\"{}\",\"model_selector\":\"{}\",\"corner\":\"typical\"}},\"gnd_clamp_current_amps\":{},\"power_clamp_current_amps\":{},\"total_shunt_current_amps\":{},\"c_comp_current_amps\":0,\"evaluation_scope\":\"input_typical_static_dc\",\"external_profile_acceptance\":\"caller_input_unattested\",\"capability_matrix_id\":\"sipi.p4a-ibis-conformance-matrix.v1\"}}",
            report.input_byte_length(),
            report.input_sha256(),
            report.ibis_version(),
            report.model_selector(),
            report.gnd_current().get(),
            report.power_current().get(),
            report.total_shunt_current().get(),
        )),
        Err(_) => error(3, "contract_rejected", "IBIS DC evaluation was rejected"),
    }
}

fn cache_key(label: &str, value: &[u8]) -> String {
    let mut builder = CacheKeyBuilder::new();
    builder
        .add_bytes(label, value)
        .expect("constant cache label");
    builder.finish().as_str().to_owned()
}

fn result_json(result: &sipi_tran::RcPulseTransientResultV1) -> Result<String, &'static str> {
    let AxisView::Explicit(times) = result.time_axis().view() else {
        return Err("fixed profile must have explicit time axis");
    };
    Ok(format!(
        "{{\"schema\":\"sipi.tran.rc-pulse-result.v1\",\"profile_id\":\"tran-rc-pulse-v1\",\"time_seconds\":{},\"voltage_in_volts\":{},\"voltage_out_volts\":{}}}",
        json_values(times.iter().map(|value| value.get())),
        json_values(
            result
                .voltage_in()
                .samples()
                .iter()
                .map(|value| value.get())
        ),
        json_values(
            result
                .voltage_out()
                .samples()
                .iter()
                .map(|value| value.get())
        ),
    ))
}

fn link_result_json(result: &sipi_link::ReceivedVoltageSamplesV1) -> Result<String, &'static str> {
    let AxisView::Uniform { start, step, count } = result.waveform().axis().view() else {
        return Err("Link result must have a uniform time axis");
    };
    Ok(format!(
        "{{\"schema\":\"sipi.link.received-waveform.v1\",\"start_seconds\":{},\"sample_interval_seconds\":{},\"sample_count\":{},\"voltage_volts\":{}}}",
        start.get(),
        step.get(),
        count.get(),
        json_values(result.waveform().samples().iter().map(|value| value.get())),
    ))
}

fn json_values(values: impl ExactSizeIterator<Item = f64>) -> String {
    let mut result = String::from("[");
    for (index, value) in values.enumerate() {
        if index != 0 {
            result.push(',');
        }
        result.push_str(&value.to_string());
    }
    result.push(']');
    result
}

fn dispatch(arguments: &[String]) -> Response {
    CommandService::execute(arguments)
}

fn command_manifest_is_valid(manifest: &[CommandDescriptorV1]) -> bool {
    manifest.iter().enumerate().all(|(index, descriptor)| {
        !descriptor.id.is_empty()
            && !descriptor.route.is_empty()
            && descriptor.route.iter().all(|token| {
                !token.is_empty()
                    && token
                        .bytes()
                        .all(|byte| byte.is_ascii_lowercase() || byte == b'-')
            })
            && matches!(descriptor.transport, "none" | "stdin_json_v1")
            && match descriptor.availability {
                CommandAvailabilityV1::Available => {
                    descriptor.unavailable_reason.is_none()
                        && available_route_has_handler(descriptor.route)
                }
                CommandAvailabilityV1::Unavailable => {
                    descriptor.unavailable_reason.is_some()
                        && !available_route_has_handler(descriptor.route)
                }
            }
            && manifest[..index]
                .iter()
                .all(|previous| previous.id != descriptor.id && previous.route != descriptor.route)
    })
}

fn command_protocol_profiles_are_valid(
    manifest: &[CommandDescriptorV1],
    profiles: &[CommandProtocolProfileV1],
) -> bool {
    manifest
        .iter()
        .filter(|descriptor| descriptor.availability == CommandAvailabilityV1::Available)
        .all(|descriptor| {
            let matches = profiles
                .iter()
                .filter(|profile| profile.command_id == descriptor.id)
                .collect::<Vec<_>>();
            matches.len() == 1
                && matches[0].successful_exit == 0
                && matches[0]
                    .required_options
                    .iter()
                    .all(|option| option.starts_with("--"))
                && matches[0].caller_bindings.iter().all(|binding| {
                    binding.pointer.starts_with('/')
                        && !binding.role.is_empty()
                        && binding.explicit_required
                })
                && if descriptor.transport == "stdin_json_v1" {
                    descriptor.request_schema.is_some()
                        && matches[0].validation_rule_id.is_some()
                        && match matches[0].example_id {
                            Some(_) => product_example_request_json_v1(descriptor.id)
                                .ok()
                                .flatten()
                                .is_some(),
                            None => !matches[0].caller_bindings.is_empty(),
                        }
                } else {
                    matches[0].example_id.is_none() && matches[0].validation_rule_id.is_none()
                }
        })
        && profiles.iter().all(|profile| {
            manifest.iter().any(|descriptor| {
                descriptor.id == profile.command_id
                    && descriptor.availability == CommandAvailabilityV1::Available
            })
        })
}

fn available_route_has_handler(route: &[&str]) -> bool {
    matches!(
        route,
        ["version"]
            | ["doctor"]
            | ["capabilities"]
            | ["commands"]
            | ["protocols"]
            | ["example"]
            | ["schema"]
            | ["validate"]
            | ["inspect", "self"]
            | ["ibis", "inspect"]
            | ["ibis", "dc-evaluate"]
            | ["tran", "run"]
            | ["link", "run"]
            | ["project", "run"]
            | ["report", "inspect"]
    )
}

fn descriptor_for_route(arguments: &[String]) -> Option<&'static CommandDescriptorV1> {
    COMMAND_MANIFEST_V1.iter().find(|descriptor| {
        arguments.len() >= descriptor.route.len()
            && arguments
                .iter()
                .zip(descriptor.route)
                .all(|(argument, token)| argument == token)
    })
}

fn command_manifest_json() -> String {
    let commands = COMMAND_MANIFEST_V1
        .iter()
        .map(|descriptor| {
            let route = descriptor
                .route
                .iter()
                .map(|token| format!("\"{token}\""))
                .collect::<Vec<_>>()
                .join(",");
            let request_schema = descriptor
                .request_schema
                .map_or_else(|| "null".to_owned(), |schema| format!("\"{schema}\""));
            let response_schema = descriptor
                .response_schema
                .map_or_else(|| "null".to_owned(), |schema| format!("\"{schema}\""));
            let reason = descriptor.unavailable_reason.map_or_else(
                || "null".to_owned(),
                |reason| format!("\"{reason}\""),
            );
            format!(
                "{{\"id\":\"{}\",\"route\":[{route}],\"availability\":\"{}\",\"transport\":\"{}\",\"request_schema\":{request_schema},\"response_schema\":{response_schema},\"unavailable_reason\":{reason},\"nonclaim\":\"{}\"}}",
                descriptor.id,
                descriptor.availability.as_str(),
                descriptor.transport,
                descriptor.nonclaim,
            )
        })
        .collect::<Vec<_>>()
        .join(",");
    format!("{{\"schema\":\"{COMMAND_MANIFEST_SCHEMA}\",\"commands\":[{commands}]}}")
}

fn sha256_hex(bytes: &[u8]) -> String {
    let digest = Sha256::digest(bytes);
    let mut result = String::with_capacity(digest.len() * 2);
    for byte in digest {
        use std::fmt::Write;
        let _ = write!(&mut result, "{byte:02x}");
    }
    result
}

fn schema_bytes(id: &str) -> Result<Option<Vec<u8>>, sipi_contracts::ContractError> {
    if id == CAPABILITIES_SCHEMA {
        capability_schema_json().map(Some)
    } else if id == sipi_contracts::VALIDATION_REQUEST_SCHEMA {
        validation_request_schema_json().map(Some)
    } else if id == sipi_contracts::TRAN_RC_PULSE_REQUEST_SCHEMA {
        tran_rc_pulse_request_schema_json().map(Some)
    } else if id == LINK_PLAN_SCHEMA {
        link_plan_schema_json().map(Some)
    } else if id == sipi_contracts::LINK_CAUSAL_FIR_REQUEST_SCHEMA {
        link_causal_fir_request_schema_json().map(Some)
    } else if id == sipi_contracts::IBIS_INSPECT_REQUEST_SCHEMA {
        ibis_inspect_request_schema_json().map(Some)
    } else if id == IBIS_DC_EVALUATE_REQUEST_SCHEMA {
        ibis_dc_evaluate_request_schema_json().map(Some)
    } else if id == ARTIFACT_REPORT_REQUEST_SCHEMA {
        artifact_report_request_schema_json().map(Some)
    } else if id == sipi_contracts::PROJECT_PLAN_SCHEMA {
        project_plan_schema_json().map(Some)
    } else if id == FIXED_PROJECT_RUN_REQUEST_SCHEMA {
        fixed_project_run_request_schema_json().map(Some)
    } else if id == sipi_contracts::RECEIVER_INPUT_SCHEMA {
        receiver_input_schema_json().map(Some)
    } else if id == sipi_contracts::RECEIVER_SEMANTICS_SCHEMA {
        receiver_semantics_schema_json().map(Some)
    } else {
        Ok(None)
    }
}

fn command_protocol_catalog_json() -> Result<String, sipi_contracts::ContractError> {
    let profiles = COMMAND_PROTOCOL_PROFILES_V1
        .iter()
        .map(|profile| {
            let descriptor = COMMAND_MANIFEST_V1
                .iter()
                .find(|descriptor| descriptor.id == profile.command_id)
                .expect("validated profile refers to a command");
            let request_schema = descriptor
                .request_schema
                .map_or_else(|| "null".to_owned(), |value| format!("\"{value}\""));
            let request_schema_sha256 = match descriptor.request_schema {
                Some(id) => schema_bytes(id)
                    .expect("registered request schema serializes")
                    .map_or_else(|| "null".to_owned(), |bytes| format!("\"{}\"", sha256_hex(&bytes))),
                None => "null".to_owned(),
            };
            let response_schema = descriptor
                .response_schema
                .map_or_else(|| "null".to_owned(), |value| format!("\"{value}\""));
            let example_id = profile
                .example_id
                .map_or_else(|| "null".to_owned(), |value| format!("\"{value}\""));
            let validation_rule_id = profile.validation_rule_id.map_or_else(
                || "null".to_owned(),
                |value| format!("\"{value}\""),
            );
            let options = profile
                .required_options
                .iter()
                .map(|option| format!("\"{option}\""))
                .collect::<Vec<_>>()
                .join(",");
            let caller_bindings = profile
                .caller_bindings
                .iter()
                .map(|binding| {
                    format!(
                        "{{\"pointer\":\"{}\",\"role\":\"{}\",\"explicit_required\":{}}}",
                        binding.pointer, binding.role, binding.explicit_required
                    )
                })
                .collect::<Vec<_>>()
                .join(",");
            format!(
                "{{\"command_id\":\"{}\",\"transport\":\"{}\",\"request_schema\":{request_schema},\"request_schema_sha256\":{request_schema_sha256},\"response_schema\":{response_schema},\"example_id\":{example_id},\"construction_state\":\"{}\",\"validation_rule_id\":{validation_rule_id},\"caller_bindings\":[{caller_bindings}],\"required_options\":[{options}],\"successful_exit\":{},\"diagnostic_contract\":\"{}\"}}",
                profile.command_id,
                descriptor.transport,
                if descriptor.transport == "stdin_json_v1" {
                    "constructible"
                } else {
                    "not_applicable"
                },
                profile.successful_exit,
                profile.diagnostic_contract,
            )
        })
        .collect::<Vec<_>>()
        .join(",");
    let diagnostics = DIAGNOSTIC_CODES_V1
        .iter()
        .map(|diagnostic| {
            format!(
                "{{\"code\":\"{}\",\"stage\":\"{}\",\"rule_id\":\"{}\"}}",
                diagnostic.code, diagnostic.stage, diagnostic.rule_id
            )
        })
        .collect::<Vec<_>>()
        .join(",");
    Ok(format!(
        "{{\"schema\":\"{COMMAND_PROTOCOL_CATALOG_SCHEMA}\",\"profiles\":[{profiles}],\"diagnostic_codes\":[{diagnostics}]}}"
    ))
}

fn command_example(id: &str) -> Response {
    let Some(descriptor) = COMMAND_MANIFEST_V1
        .iter()
        .find(|descriptor| descriptor.id == id)
    else {
        return error(
            64,
            "unknown_command_example",
            "command example is not registered",
        );
    };
    if descriptor.availability != CommandAvailabilityV1::Available
        || descriptor.transport != "stdin_json_v1"
    {
        return error(
            4,
            "example_not_applicable",
            "command does not accept a stdin example",
        );
    }
    let Some(profile) = COMMAND_PROTOCOL_PROFILES_V1
        .iter()
        .find(|profile| profile.command_id == id)
    else {
        return error(
            6,
            "internal_contract_error",
            "command protocol profile is missing",
        );
    };
    if profile.example_id.is_none() {
        return error(
            4,
            "example_not_applicable",
            "command requires caller-owned admission bindings",
        );
    }
    match product_example_request_json_v1(id) {
        Ok(Some(bytes)) => match String::from_utf8(bytes) {
            Ok(request) => success(format!(
                "{{\"schema\":\"sipi.command-example.v1\",\"command_id\":\"{id}\",\"example_id\":\"{}\",\"request_schema\":\"{}\",\"request\":{request}}}",
                profile
                    .example_id
                    .expect("profile was admitted as example-bearing"),
                descriptor
                    .request_schema
                    .expect("validated stdin descriptor has a request schema"),
            )),
            Err(_) => error(6, "internal_contract_error", "example request is not UTF-8"),
        },
        Ok(None) => error(6, "internal_contract_error", "example request is missing"),
        Err(_) => error(
            6,
            "internal_contract_error",
            "example request is unavailable",
        ),
    }
}

fn unavailable(descriptor: &CommandDescriptorV1) -> Response {
    let reason = descriptor
        .unavailable_reason
        .expect("validated unavailable descriptor has a reason");
    Response {
        code: 4,
        stdout: Some(format!(
            "{{\"schema\":\"sipi.command-unavailable.v1\",\"command_id\":\"{}\",\"reason\":\"{reason}\"}}",
            descriptor.id
        )),
        stderr: Some("capability_unavailable".to_owned()),
    }
}

impl CommandService {
    fn execute(arguments: &[String]) -> Response {
        if !command_manifest_is_valid(COMMAND_MANIFEST_V1)
            || !command_protocol_profiles_are_valid(
                COMMAND_MANIFEST_V1,
                COMMAND_PROTOCOL_PROFILES_V1,
            )
        {
            return error(6, "internal_contract_error", "command manifest is invalid");
        }
        if let Some(descriptor) = descriptor_for_route(arguments)
            && descriptor.availability == CommandAvailabilityV1::Unavailable
        {
            return unavailable(descriptor);
        }
        match arguments {
            [command, format] if command == "commands" && format == "--json" => {
                success(command_manifest_json())
            }
            [command, format] if command == "protocols" && format == "--json" => {
                match command_protocol_catalog_json() {
                    Ok(catalog) => success(catalog),
                    Err(_) => error(
                        6,
                        "internal_contract_error",
                        "command protocol catalog is unavailable",
                    ),
                }
            }
            [command, format] if command == "example" && format == "--json" => error(
                4,
                "example_not_applicable",
                "a stdin command id is required for an example",
            ),
            [command, id, format] if command == "example" && format == "--json" => {
                command_example(id)
            }
            [command] if command == "--version" || command == "version" => success(version_json()),
            [command, format] if command == "version" && format == "--json" => {
                success(version_json())
            }
            [command, format] if command == "doctor" && format == "--json" => {
                success(doctor_json())
            }
            [command, format] if command == "capabilities" && format == "--json" => {
                success(capabilities_json())
            }
            [command, action, format]
                if command == "schema" && action == "list" && format == "--json" =>
            {
                success(schema_list_json())
            }
            [command, action, id, format]
                if command == "schema" && action == "show" && format == "--json" =>
            {
                schema_show(id)
            }
            [command, action, format]
                if command == "validate" && action == "self" && format == "--json" =>
            {
                validate_self(None)
            }
            [command, action, schema, id, format]
                if command == "validate"
                    && action == "self"
                    && schema == "--schema"
                    && format == "--json" =>
            {
                validate_self(Some(id))
            }
            [command, format] if command == "validate" && format == "--stdin" => error(
                2,
                "invalid_input",
                "stdin validation requires the process adapter",
            ),
            [command, action, format]
                if command == "inspect" && action == "self" && format == "--json" =>
            {
                success(inspect_self_json())
            }
            [command, action, id, format]
                if command == "inspect" && action == "capability" && format == "--json" =>
            {
                inspect_capability(id)
            }
            [command, action, id, format]
                if command == "inspect" && action == "schema" && format == "--json" =>
            {
                schema_show(id)
            }
            [command, ..] if command == "run" => error(
                4,
                "unsupported",
                "simulation domains are not implemented in the P1-01 foundation",
            ),
            [command, ..] if command == "tran" => error(
                4,
                "unsupported",
                "TRAN requires the exact run --stdin artifact command",
            ),
            [command, ..] if command == "link" => error(
                4,
                "unsupported",
                "Link requires the exact run --stdin artifact command",
            ),
            [command, ..] if command == "project" => error(
                4,
                "unsupported",
                "Project requires the exact run --stdin artifact command",
            ),
            [command, ..] if command == "ibis" => error(
                4,
                "unsupported",
                "IBIS requires an exact supported --stdin command",
            ),
            [command, ..] if command == "report" => error(
                4,
                "unsupported",
                "report requires the exact inspect --stdin command",
            ),
            _ => error(
                64,
                "usage",
                "supported commands are version, doctor, capabilities, schema, validate, run, and inspect with --json",
            ),
        }
    }
}

fn success(body: String) -> Response {
    Response {
        code: 0,
        stdout: Some(body),
        stderr: None,
    }
}

fn error(code: i32, name: &str, _message: &str) -> Response {
    Response {
        code,
        stdout: None,
        stderr: Some(name.to_owned()),
    }
}

fn envelope_json(command: &str, response: &Response) -> String {
    let status = match response.code {
        0 => "ok",
        2 | 3 => "invalid",
        4 => "unsupported",
        _ => "failed",
    };
    let result = response.stdout.as_deref().unwrap_or("null");
    format!(
        "{{\"schema\":\"sipi.cli.response.v1\",\"protocol\":1,\"command\":\"{command}\",\"request_id\":null,\"status\":\"{status}\",\"result\":{result},\"diagnostic_count\":{}}}",
        usize::from(response.stderr.is_some())
    )
}

fn diagnostic_json(command: &str, message: &str) -> String {
    let diagnostic = DIAGNOSTIC_CODES_V1
        .iter()
        .find(|diagnostic| diagnostic.code == message)
        .unwrap_or_else(|| {
            DIAGNOSTIC_CODES_V1
                .iter()
                .find(|diagnostic| diagnostic.code == "internal_failure")
                .expect("diagnostic registry has an internal fallback")
        });
    format!(
        "{{\"schema\":\"sipi.cli.diagnostic.v1\",\"sequence\":1,\"severity\":\"error\",\"code\":\"{}\",\"command\":\"{command}\",\"command_id\":\"{command}\",\"request_id\":null,\"stage\":\"{}\",\"location\":null,\"pointer\":null,\"rule_id\":\"{}\",\"message\":\"command failed\"}}",
        diagnostic.code, diagnostic.stage, diagnostic.rule_id
    )
}

fn version_json() -> String {
    format!(
        "{{\"schema\":\"sipi.cli-version.v1\",\"name\":\"sipi\",\"version\":\"{VERSION}\",\"foundation_stage\":\"{}\"}}",
        sipi_types::FOUNDATION_STAGE
    )
}

fn capabilities_json() -> String {
    let capabilities = PLANNED_DOMAINS
        .iter()
        .map(|domain| {
            if *domain == "tran" && manifest_available("tran.run") {
                "{\"domain\":\"tran\",\"status\":\"limited\",\"reason\":\"fixed_rc_pulse_profile_only\"}".to_owned()
            } else if *domain == "channel" && manifest_available("link.run") {
                "{\"domain\":\"channel\",\"status\":\"limited\",\"reason\":\"causal_fir_link_only\"}".to_owned()
            } else {
                format!(
                    "{{\"domain\":\"{domain}\",\"status\":\"unsupported\",\"reason\":\"not_implemented\"}}"
                )
            }
        })
        .collect::<Vec<_>>()
        .join(",");
    format!(
        "{{\"schema\":\"{CAPABILITIES_SCHEMA}\",\"product\":{{\"name\":\"sipi\",\"version\":\"{VERSION}\"}},\"platform\":{{\"target\":\"{TARGET}\",\"certification\":\"uncertified\"}},\"capabilities\":[{capabilities}]}}"
    )
}

fn manifest_available(id: &str) -> bool {
    COMMAND_MANIFEST_V1
        .iter()
        .find(|descriptor| descriptor.id == id)
        .is_some_and(|descriptor| descriptor.availability == CommandAvailabilityV1::Available)
}

fn doctor_json() -> String {
    format!(
        "{{\"schema\":\"sipi.cli-doctor.v1\",\"target\":\"{TARGET}\",\"checks\":[{{\"id\":\"contract_registry\",\"status\":\"ok\"}},{{\"id\":\"rule_ledger\",\"status\":\"ok\"}},{{\"id\":\"external_runtime\",\"status\":\"not_checked\"}}]}}"
    )
}

fn schema_list_json() -> String {
    format!(
        "{{\"schema\":\"sipi.cli-schema-list.v1\",\"schemas\":[\"{CAPABILITIES_SCHEMA}\",\"{ARTIFACT_REPORT_REQUEST_SCHEMA}\",\"{}\",\"{}\",\"{}\",\"{}\",\"{}\",\"{}\",\"{}\",\"{}\",\"{}\",\"{}\"]}}",
        IBIS_DC_EVALUATE_REQUEST_SCHEMA,
        sipi_contracts::IBIS_INSPECT_REQUEST_SCHEMA,
        LINK_PLAN_SCHEMA,
        sipi_contracts::LINK_CAUSAL_FIR_REQUEST_SCHEMA,
        FIXED_PROJECT_RUN_REQUEST_SCHEMA,
        sipi_contracts::PROJECT_PLAN_SCHEMA,
        sipi_contracts::RECEIVER_INPUT_SCHEMA,
        sipi_contracts::RECEIVER_SEMANTICS_SCHEMA,
        sipi_contracts::TRAN_RC_PULSE_REQUEST_SCHEMA,
        sipi_contracts::VALIDATION_REQUEST_SCHEMA,
    )
}

fn schema_show(id: &str) -> Response {
    let bytes = match schema_bytes(id) {
        Ok(Some(bytes)) => bytes,
        Ok(None) => return error(64, "unknown_schema", "schema is not registered"),
        Err(_) => {
            return error(
                70,
                "internal_contract_error",
                "registered schema is unavailable",
            );
        }
    };
    match String::from_utf8(bytes)
        .map_err(|_| sipi_contracts::ContractError::Json("schema is not UTF-8".to_owned()))
    {
        Ok(schema) => success(schema),
        Err(_) => error(
            70,
            "internal_contract_error",
            "registered schema is unavailable",
        ),
    }
}

fn validate_self(schema: Option<&str>) -> Response {
    if schema.is_some_and(|id| {
        id != CAPABILITIES_SCHEMA
            && id != ARTIFACT_REPORT_REQUEST_SCHEMA
            && id != sipi_contracts::VALIDATION_REQUEST_SCHEMA
            && id != sipi_contracts::TRAN_RC_PULSE_REQUEST_SCHEMA
            && id != sipi_contracts::IBIS_INSPECT_REQUEST_SCHEMA
            && id != IBIS_DC_EVALUATE_REQUEST_SCHEMA
            && id != LINK_PLAN_SCHEMA
            && id != sipi_contracts::LINK_CAUSAL_FIR_REQUEST_SCHEMA
            && id != sipi_contracts::PROJECT_PLAN_SCHEMA
            && id != FIXED_PROJECT_RUN_REQUEST_SCHEMA
            && id != sipi_contracts::RECEIVER_INPUT_SCHEMA
            && id != sipi_contracts::RECEIVER_SEMANTICS_SCHEMA
    }) {
        return error(64, "unknown_schema", "schema is not registered");
    }
    let catalog = CapabilityCatalogV1::unsupported();
    let valid = catalog.schema == CAPABILITIES_SCHEMA
        && catalog.capabilities.len() == PLANNED_DOMAINS.len()
        && catalog
            .capabilities
            .iter()
            .all(|item| item.status == "unsupported")
        && deterministic_json(&catalog).is_ok()
        && !RULE_LEDGER_V1.is_empty()
        && validation_request_schema_json().is_ok()
        && artifact_report_request_schema_json().is_ok()
        && tran_rc_pulse_request_schema_json().is_ok()
        && ibis_inspect_request_schema_json().is_ok()
        && ibis_dc_evaluate_request_schema_json().is_ok()
        && link_plan_schema_json().is_ok()
        && link_causal_fir_request_schema_json().is_ok()
        && project_plan_schema_json().is_ok()
        && fixed_project_run_request_schema_json().is_ok()
        && receiver_input_schema_json().is_ok()
        && receiver_semantics_schema_json().is_ok()
        && command_protocol_profiles_are_valid(COMMAND_MANIFEST_V1, COMMAND_PROTOCOL_PROFILES_V1)
        && command_protocol_catalog_json().is_ok();
    if valid {
        success(
            "{\"schema\":\"sipi.cli-validate.v1\",\"subject\":\"self\",\"status\":\"ok\"}"
                .to_owned(),
        )
    } else {
        error(
            70,
            "self_check_failed",
            "built-in contract self-check failed",
        )
    }
}

fn inspect_self_json() -> String {
    format!(
        "{{\"schema\":\"sipi.cli-inspect.v1\",\"subject\":\"self\",\"scope\":\"static_discovery\",\"status\":\"quarantine\",\"command_manifest\":\"{COMMAND_MANIFEST_SCHEMA}\"}}"
    )
}

fn inspect_capability(id: &str) -> Response {
    if PLANNED_DOMAINS.contains(&id) {
        success(format!(
            "{{\"schema\":\"sipi.cli-inspect.v1\",\"subject\":\"capability\",\"id\":\"{id}\",\"status\":\"unsupported\",\"reason\":\"not_implemented\"}}"
        ))
    } else {
        error(64, "unknown_capability", "capability is not registered")
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicUsize, Ordering};

    static TEST_NONCE: AtomicUsize = AtomicUsize::new(0);

    fn args(values: &[&str]) -> Vec<String> {
        values.iter().map(|value| (*value).to_owned()).collect()
    }

    fn rc_pulse_request() -> &'static [u8] {
        br#"{"schema":"sipi.tran.rc-pulse-request.v1","request_id":"rc-pulse-1","resistance_ohms":1000.0,"capacitance_farads":0.000001,"initial_voltage_out_volts":0.0,"output_times_seconds":[0.0,0.000001,0.000002,0.000003],"pulse":{"voltage_low_volts":0.0,"voltage_high_volts":1.0,"delay_seconds":0.000001,"rise_seconds":0.000000001,"fall_seconds":0.000000001,"width_seconds":0.00001,"period_seconds":0.00002}}"#
    }

    #[test]
    fn capability_inventory_exposes_only_the_fixed_tran_and_causal_fir_profiles() {
        let response = dispatch(&args(&["capabilities", "--json"]));

        assert_eq!(response.code, 0);
        assert_eq!(response.stderr, None);
        assert_eq!(
            response.stdout.as_deref(),
            Some(
                "{\"schema\":\"sipi.capabilities.v1\",\"product\":{\"name\":\"sipi\",\"version\":\"0.1.0\"},\"platform\":{\"target\":\"x86_64-pc-windows-msvc\",\"certification\":\"uncertified\"},\"capabilities\":[{\"domain\":\"tran\",\"status\":\"limited\",\"reason\":\"fixed_rc_pulse_profile_only\"},{\"domain\":\"channel\",\"status\":\"limited\",\"reason\":\"causal_fir_link_only\"},{\"domain\":\"ibis-ami\",\"status\":\"unsupported\",\"reason\":\"not_implemented\"},{\"domain\":\"com\",\"status\":\"unsupported\",\"reason\":\"not_implemented\"}]}"
            )
        );
    }

    #[test]
    fn command_manifest_is_canonical_and_unavailable_routes_fail_closed() {
        assert!(command_manifest_is_valid(COMMAND_MANIFEST_V1));
        assert!(command_protocol_profiles_are_valid(
            COMMAND_MANIFEST_V1,
            COMMAND_PROTOCOL_PROFILES_V1,
        ));
        let manifest = command_manifest_json();
        assert!(manifest.starts_with("{\"schema\":\"sipi.command-manifest.v1\""));
        assert!(manifest.contains("\"id\":\"tran.run\""));
        assert!(manifest.contains("\"id\":\"ami.run\""));
        let commands_response = dispatch(&args(&["commands", "--json"]));
        assert_eq!(commands_response.code, 0);
        assert_eq!(commands_response.stdout.as_deref(), Some(manifest.as_str()));

        for command in [
            ["channel", "run"].as_slice(),
            ["ami", "run"].as_slice(),
            ["com", "run"].as_slice(),
            ["project", "validate"].as_slice(),
            ["compare", "run"].as_slice(),
            ["report", "show"].as_slice(),
        ] {
            let response = dispatch(&args(command));
            assert_eq!(response.code, 4);
            assert_eq!(response.stderr.as_deref(), Some("capability_unavailable"));
            assert!(
                response
                    .stdout
                    .as_deref()
                    .is_some_and(|value| value.contains("command_id"))
            );
        }
    }

    #[test]
    fn protocol_catalog_binds_examples_or_explicit_caller_admission() {
        let catalog = command_protocol_catalog_json().expect("protocol catalog");
        assert!(catalog.starts_with("{\"schema\":\"sipi.command-protocol-catalog.v1\""));
        for command in [
            "validate",
            "ibis.inspect",
            "ibis.dc-evaluate",
            "tran.run",
            "link.run",
            "project.run",
        ] {
            assert!(catalog.contains(&format!("\"command_id\":\"{command}\"")));
            assert!(catalog.contains("\"example_id\":\"product-owned-minimal-v1\""));
            let response = dispatch(&args(&["example", command, "--json"]));
            assert_eq!(response.code, 0, "{command}");
            assert!(response.stderr.is_none());
            assert!(
                response
                    .stdout
                    .as_deref()
                    .is_some_and(|body| body.contains("sipi.command-example.v1"))
            );
        }
        assert!(catalog.contains("\"request_schema_sha256\":\""));
        assert!(catalog.contains("\"construction_state\":\"constructible\""));
        assert!(catalog.contains("\"pointer\":\"/invocation/artifact_root\""));
        assert!(catalog.contains("\"validation_rule_id\":\"tran.rc-pulse.profile\""));
        assert!(catalog.contains("\"diagnostic_codes\":["));
        assert!(catalog.contains("\"command_id\":\"report.inspect\""));
        assert!(catalog.contains("\"pointer\":\"/artifact_root\""));
        assert!(catalog.contains("\"role\":\"caller_owned_artifact_root\""));
        assert_eq!(
            dispatch(&args(&["example", "channel.run", "--json"])).code,
            4
        );
        assert_eq!(
            dispatch(&args(&["example", "report.inspect", "--json"])).code,
            4
        );
        assert_eq!(dispatch(&args(&["example", "version", "--json"])).code, 4);
    }

    #[test]
    fn product_examples_are_accepted_by_their_single_contract_entry_points() {
        let validate = product_example_request_json_v1("validate")
            .expect("validation example")
            .expect("registered validation example");
        assert!(validate_request_v1(&validate).is_ok());

        let ibis = product_example_request_json_v1("ibis.inspect")
            .expect("IBIS example")
            .expect("registered IBIS example");
        assert!(parse_ibis_inspect_request_v1(&ibis).is_ok());

        let ibis_dc = product_example_request_json_v1("ibis.dc-evaluate")
            .expect("IBIS DC example")
            .expect("registered IBIS DC example");
        assert!(parse_ibis_dc_evaluate_request_v1(&ibis_dc).is_ok());

        let tran = product_example_request_json_v1("tran.run")
            .expect("TRAN example")
            .expect("registered TRAN example");
        assert!(parse_tran_rc_pulse_request_v1(&tran).is_ok());

        let link = product_example_request_json_v1("link.run")
            .expect("Link example")
            .expect("registered Link example");
        assert!(parse_link_causal_fir_request_v1(&link).is_ok());

        let project = product_example_request_json_v1("project.run")
            .expect("project example")
            .expect("registered project example");
        assert!(parse_fixed_project_run_request_v1(&project).is_ok());
        assert!(
            product_example_request_json_v1("channel.run")
                .expect("unknown example lookup")
                .is_none()
        );
    }

    #[test]
    fn diagnostics_are_registered_machine_fields_without_user_text() {
        let unavailable = diagnostic_json("channel", "capability_unavailable");
        assert!(unavailable.contains("\"stage\":\"protocol\""));
        assert!(unavailable.contains("\"rule_id\":\"cli.capability-admission.v1\""));
        assert!(unavailable.contains("\"pointer\":null"));
        assert!(!unavailable.contains("C:\\"));

        let unknown = diagnostic_json("unknown", "not-in-the-registry");
        assert!(unknown.contains("\"code\":\"internal_failure\""));
        assert!(unknown.contains("\"stage\":\"runtime\""));
    }

    #[test]
    fn malformed_command_manifest_entries_are_rejected() {
        let duplicate = [
            CommandDescriptorV1 {
                id: "one",
                route: &["one"],
                availability: CommandAvailabilityV1::Available,
                transport: "none",
                request_schema: None,
                response_schema: None,
                unavailable_reason: None,
                nonclaim: "test",
            },
            CommandDescriptorV1 {
                id: "two",
                route: &["one"],
                availability: CommandAvailabilityV1::Available,
                transport: "none",
                request_schema: None,
                response_schema: None,
                unavailable_reason: None,
                nonclaim: "test",
            },
        ];
        assert!(!command_manifest_is_valid(&duplicate));

        let unavailable_with_handler = [CommandDescriptorV1 {
            id: "bad",
            route: &["tran", "run"],
            availability: CommandAvailabilityV1::Unavailable,
            transport: "none",
            request_schema: None,
            response_schema: None,
            unavailable_reason: Some("test"),
            nonclaim: "test",
        }];
        assert!(!command_manifest_is_valid(&unavailable_with_handler));
    }

    #[test]
    fn run_is_fail_closed() {
        let response = dispatch(&args(&["run"]));

        assert_eq!(response.code, 4);
        assert_eq!(response.stdout, None);
        assert_eq!(response.stderr.as_deref(), Some("unsupported"));

        let project = dispatch(&args(&["project", "run"]));
        assert_eq!(project.code, 4);
        assert_eq!(project.stdout, None);
        assert_eq!(project.stderr.as_deref(), Some("unsupported"));
    }

    #[test]
    fn discovery_and_self_commands_are_static_and_fail_closed() {
        for command in [
            args(&["doctor", "--json"]),
            args(&["schema", "list", "--json"]),
            args(&["schema", "show", "sipi.capabilities.v1", "--json"]),
            args(&["validate", "self", "--json"]),
            args(&["inspect", "self", "--json"]),
            args(&["inspect", "capability", "tran", "--json"]),
        ] {
            let response = dispatch(&command);
            assert_eq!(response.code, 0);
            assert!(response.stderr.is_none());
        }
        assert_eq!(
            dispatch(&args(&["schema", "show", "unknown", "--json"])).code,
            64
        );
        assert_eq!(
            dispatch(&args(&["inspect", "capability", "unknown", "--json"])).code,
            64
        );
    }

    #[test]
    fn schema_list_uses_the_schema_inventory_order() {
        assert_eq!(
            schema_list_json(),
            "{\"schema\":\"sipi.cli-schema-list.v1\",\"schemas\":[\"sipi.capabilities.v1\",\"sipi.artifact-report-request.v1\",\"sipi.ibis.input-typ-dc-evaluate.request.v1\",\"sipi.ibis.inspect.request.v1\",\"sipi.link-plan.v1\",\"sipi.link.causal-fir-request.v1\",\"sipi.project.fixed-tran-causal-fir-run-request.v1\",\"sipi.project.v1\",\"sipi.receiver-input.v1\",\"sipi.receiver-semantics.v1\",\"sipi.tran.rc-pulse-request.v1\",\"sipi.validation-request.v1\"]}"
        );
    }

    #[test]
    fn ibis_inspect_is_structural_only_and_rejects_other_ibis_commands() {
        let response = run_ibis_inspect("[IBIS Ver] 7.1\n[Model] rx_0\n");
        assert_eq!(response.code, 0);
        let body = response.stdout.expect("response");
        assert!(body.contains("\"structural_parse\":\"accepted\""));
        assert!(body.contains("\"electrical_behavior\":\"not_evaluated\""));
        assert!(body.contains("\"external_profile_acceptance\":\"not_evaluated\""));
        assert_eq!(
            dispatch(&args(&["ibis", "inspect", "--file", "sample.ibs"])).code,
            4
        );
        assert_eq!(
            dispatch(&args(&["report", "inspect", "--file", "artifact"])).code,
            4
        );
    }

    #[test]
    fn fixed_tran_run_publishes_only_a_verified_artifact() {
        let nonce = TEST_NONCE.fetch_add(1, Ordering::Relaxed);
        let root = std::env::temp_dir().join(format!("sipi-cli-tran-{nonce}"));
        let root_text = root.to_string_lossy();
        let response = run_fixed_tran(&root_text, "rc-pulse-1", rc_pulse_request());
        assert_eq!(response.code, 0);
        assert!(
            response
                .stdout
                .as_deref()
                .is_some_and(|value| value.contains("artifact_id"))
        );
        let store = sipi_artifacts::ArtifactRoot::open_or_create(&root).expect("artifact root");
        let manifest = store
            .verify_published("rc-pulse-1")
            .expect("published artifact");
        assert_eq!(manifest.files.len(), 2);
        assert_eq!(
            run_fixed_tran(&root_text, "rc-pulse-1", rc_pulse_request()).code,
            5
        );
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn fixed_project_run_publishes_the_admitted_edge_record() {
        let nonce = TEST_NONCE.fetch_add(1, Ordering::Relaxed);
        let root = std::env::temp_dir().join(format!("sipi-cli-project-{nonce}"));
        let request_bytes = product_example_request_json_v1("project.run")
            .expect("request")
            .expect("project request");
        let request = parse_fixed_project_run_request_v1(&request_bytes).expect("parse request");
        let response = run_fixed_project(
            &root.to_string_lossy(),
            "fixed-project-artifact-1",
            &request,
        );
        assert_eq!(response.code, 0);
        assert!(
            response.stdout.as_deref().is_some_and(
                |body| body.contains("sipi.project.fixed-tran-causal-fir-run-result.v1")
            )
        );
        let artifact = root.join("fixed-project-artifact-1");
        for entry in [
            "success.json",
            "request.json",
            "received-waveform.json",
            "edge-record.json",
            "provenance.json",
        ] {
            assert!(artifact.join(entry).is_file(), "{entry}");
        }
        let report = run_artifact_report(&root.to_string_lossy(), "fixed-project-artifact-1");
        assert_eq!(report.code, 0);
        assert!(
            !run_fixed_project(
                &root.to_string_lossy(),
                "fixed-project-artifact-1",
                &request
            )
            .stdout
            .is_some_and(|body| body.contains("run-result"))
        );
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn artifact_report_is_verified_metadata_without_payload_or_path_leaks() {
        let nonce = TEST_NONCE.fetch_add(1, Ordering::Relaxed);
        let root = std::env::temp_dir().join(format!("sipi-cli-report-{nonce}"));
        let root_text = root.to_string_lossy();
        assert_eq!(
            run_fixed_tran(&root_text, "rc-pulse-1", rc_pulse_request()).code,
            0
        );
        let report = run_artifact_report(&root_text, "rc-pulse-1");
        assert_eq!(report.code, 0);
        let body = report.stdout.expect("report body");
        assert!(body.contains("\"schema\":\"sipi.artifact-report.v1\""));
        assert!(body.contains("\"verified\":true"));
        assert!(body.contains("\"integrity_lineage\":\"unavailable\""));
        assert!(!body.contains(root_text.as_ref()));
        assert!(!body.contains("result.json"));
        assert!(!body.contains("backward_euler_rc_pulse_v1"));
        std::fs::write(root.join("rc-pulse-1").join("result.json"), b"tampered")
            .expect("tamper payload");
        let rejected = run_artifact_report(&root_text, "rc-pulse-1");
        assert_eq!(rejected.code, 5);
        assert!(rejected.stdout.is_none());
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn accounted_byte_limit_rejects_before_an_artifact_can_be_published() {
        let nonce = TEST_NONCE.fetch_add(1, Ordering::Relaxed);
        let root = std::env::temp_dir().join(format!("sipi-cli-tran-quota-{nonce}"));
        let root_text = root.to_string_lossy();
        let policy = RunPolicy::try_new(Duration::from_secs(1), 16, 1).expect("policy");

        let response =
            run_fixed_tran_with_policy(&root_text, "rc-pulse-1", rc_pulse_request(), policy);

        assert_eq!(response.code, 5);
        assert_eq!(response.stderr.as_deref(), Some("operational_failure"));
        assert!(!root.join("rc-pulse-1").join("success.json").exists());
        let _ = std::fs::remove_dir_all(root);
    }
}
