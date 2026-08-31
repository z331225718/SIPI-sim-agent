#![forbid(unsafe_code)]

#[cfg(feature = "com-direct-integration")]
mod com_direct_cli_contract_v1;
#[cfg(feature = "com-direct-integration")]
mod com_direct_integration;
mod com_run_artifact_preflight_v1;
mod upstream_migration;

use std::{
    collections::BTreeMap,
    env,
    io::{self, Cursor, Read},
    num::NonZeroUsize,
    path::Path,
    process,
    time::Duration,
};

use com_run_artifact_preflight_v1::preflight_com_run_artifact_request_v1;
use sha2::{Digest, Sha256};
use sipi_artifacts::{ArtifactRoot, VerifiedConsumptionPolicyV1};
use sipi_channel::{ChannelLimitsV1, resolve_matched_kernel_v1};
use sipi_com::{
    COM_RUN_ARTIFACT_REQUEST_MAX_BYTES_V1, COM_RUN_ARTIFACT_SPECIFIED_RESULT_SCHEMA_V1,
    ComRunPulseArtifactIdentityV1, ResolvedDefaultV1,
    execute_com_run_artifact_from_product_values_v1,
};
use sipi_compare::{
    ARRAY_COMPARE_POLICY_V1, AlignedArrayV1, ArrayShapeV1, SemanticBindingDigestV1, ToleranceV1,
    UnitTagV1, compare_arrays_v1,
    prbs9_waveform_v2::{Prbs9WaveformPairV2, compare_prbs9_metrics_v2},
    selected_highloss_prbs9_waveform_only_v3::{
        SelectedHighlossPrbs9WaveformPairV3, compare_selected_highloss_prbs9_waveform_only_v3,
    },
};
use sipi_contracts::{
    ARRAY_COMPARE_REQUEST_SCHEMA, ARTIFACT_REPORT_REQUEST_SCHEMA, CAPABILITIES_SCHEMA,
    CHANNEL_MATCHED_TWO_PORT_KERNEL_RUN_REQUEST_SCHEMA, COM_RUN_ARTIFACT_REQUEST_SCHEMA,
    CapabilityCatalogV1, ComParameterValueV1, FIXED_PROJECT_RUN_REQUEST_SCHEMA,
    IBIS_DC_EVALUATE_REQUEST_SCHEMA, IBIS_QUASI_STATIC_ARTIFACT_BATCH_EVALUATE_REQUEST_SCHEMA,
    IBIS_QUASI_STATIC_ARTIFACT_EVALUATE_REQUEST_SCHEMA, IBIS_QUASI_STATIC_EVALUATE_REQUEST_SCHEMA,
    LINK_PLAN_SCHEMA, PLANNED_DOMAINS, PRBS9_METRIC_ARTIFACTS_REQUEST_SCHEMA,
    PRBS9_WAVEFORM_ARTIFACT_BYTE_LENGTH_V1, RECEIVER_DIAGNOSTIC_RUN_REQUEST_SCHEMA, RULE_LEDGER_V1,
    SELECTED_HIGHLOSS_PRBS9_WAVEFORM_ONLY_ARTIFACTS_REQUEST_SCHEMA_V3,
    SELECTED_HIGHLOSS_PRBS9_WAVEFORM_ONLY_BYTE_LENGTH_V3, TRAN_ONE_NODE_RC_PULSE_REQUEST_SCHEMA,
    TRAN_ONE_NODE_RC_PWL_REQUEST_SCHEMA, array_compare_request_schema_json,
    artifact_report_request_schema_json, capability_schema_json,
    channel_matched_two_port_kernel_run_request_schema_json, com_run_artifact_request_schema_json,
    deterministic_json, fixed_project_run_request_schema_json,
    ibis_dc_evaluate_request_schema_json, ibis_inspect_request_schema_json,
    ibis_quasi_static_artifact_batch_evaluate_request_schema_json,
    ibis_quasi_static_artifact_evaluate_request_schema_json,
    ibis_quasi_static_evaluate_request_schema_json, link_causal_fir_request_schema_json,
    link_plan_schema_json, parse_array_compare_request_v1, parse_artifact_report_request_v1,
    parse_channel_matched_two_port_kernel_run_request_v1, parse_com_run_artifact_request_v1,
    parse_fixed_project_run_request_v1, parse_ibis_dc_evaluate_request_v1,
    parse_ibis_inspect_request_v1, parse_ibis_quasi_static_artifact_batch_evaluate_request_v1,
    parse_ibis_quasi_static_artifact_evaluate_request_v1,
    parse_ibis_quasi_static_evaluate_request_v1, parse_link_causal_fir_request_v1,
    parse_prbs9_metric_artifacts_request_v1, parse_prbs9_waveform_artifact_v1,
    parse_receiver_diagnostic_run_request_v1, parse_rx_load_differential_rc_evaluate_request_v1,
    parse_selected_highloss_prbs9_waveform_only_artifact_v3,
    parse_selected_highloss_prbs9_waveform_only_artifacts_request_v3,
    parse_tran_one_node_rc_pulse_request_v1, parse_tran_one_node_rc_pwl_request_v1,
    parse_tran_rc_pulse_request_v1, prbs9_metric_artifacts_request_schema_json,
    product_example_request_json_v1, project_plan_schema_json,
    receiver_diagnostic_run_request_schema_json, receiver_input_schema_json,
    receiver_semantics_schema_json, rx_load_differential_rc_evaluate_request_schema_json,
    selected_highloss_prbs9_waveform_only_artifacts_request_schema_json,
    tran_one_node_rc_pulse_request_schema_json, tran_one_node_rc_pwl_request_schema_json,
    tran_rc_pulse_request_schema_json, validate_request_v1, validation_request_schema_json,
};
use sipi_ibis::{
    DcClampCornerV1, DcClampProbeV1, IbisDcEvaluateServiceV1, IbisInspectServiceV1,
    IbisQuasiStaticBatchEvaluateServiceV1, IbisQuasiStaticEvaluateServiceV1, ParseLimitsV1,
    QuasiStaticClampStateV1, SelectedDcClampProfileV1,
};
use sipi_link::{
    ConvolutionLimitsV1, ReceiverPhaseSelectionV2, ReferenceBitsV1, convolve_causal_fir_v1,
    run_fixed_receiver_delegated_ambiguity_v2,
};
use sipi_pipeline::{
    CausalFirConsumerConfigV1, FixedTranCausalFirProjectBindingV1,
    run_fixed_tran_causal_fir_project_attempt_v1, validate_fixed_tran_causal_fir_project_v1,
};
use sipi_runtime::{CacheKeyBuilder, ResourceCost, RunId, RunPolicy, Runtime};
use sipi_rx_load::{
    DIFFERENTIAL_RESISTANCE_OHMS, DifferentialRcLoadProbeV1, LEG_CAPACITANCE_FARADS,
    evaluate_selected_differential_rc_load_v1,
};
use sipi_touchstone::{
    TouchstoneParseLimitsV1, admit_matched_two_port_spectrum_v1,
    parse_touchstone_hz_s_ri_50_two_port_v1,
};
use sipi_tran::{
    IdealPulseV1, OneNodeRcPulseLimitsV1, OneNodeRcPulseRequestV1, OneNodeRcPwlLimitsV1,
    OneNodeRcPwlRequestV1, PiecewiseLinearVoltageV1, RcPulseTransientV1,
    simulate_one_node_rc_pulse_with_context, simulate_one_node_rc_pwl_with_context,
    simulate_rc_pulse_with_context,
};
use sipi_types::{AxisView, FiniteF64, Ohms, Seconds, Volts};
use upstream_migration::{
    REQUEST_SCHEMA as UPSTREAM_MIGRATION_REQUEST_SCHEMA,
    RESPONSE_SCHEMA as UPSTREAM_MIGRATION_RESPONSE_SCHEMA,
};

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

const COM_RUN_ARTIFACT_BINDINGS: &[CallerBindingV1] = &[
    CallerBindingV1 {
        pointer: "/invocation/pulse_root",
        role: "caller_owned_pulse_artifact_root",
        explicit_required: true,
    },
    CallerBindingV1 {
        pointer: "/pulse_artifact_id",
        role: "sealed_pulse_artifact_identity",
        explicit_required: true,
    },
    CallerBindingV1 {
        pointer: "/pulse_manifest_sha256",
        role: "sealed_pulse_manifest_identity",
        explicit_required: true,
    },
    CallerBindingV1 {
        pointer: "/artifact_root",
        role: "caller_owned_result_artifact_root",
        explicit_required: true,
    },
    CallerBindingV1 {
        pointer: "/artifact_id",
        role: "result_artifact_identity",
        explicit_required: true,
    },
];

#[cfg(feature = "com-direct-integration")]
const COM_R480_ARGV_BINDINGS: &[CallerBindingV1] = &[
    CallerBindingV1 {
        pointer: "/argv/config",
        role: "caller_owned_local_workbook_or_json_config",
        explicit_required: true,
    },
    CallerBindingV1 {
        pointer: "/argv/thru",
        role: "caller_owned_local_thru_channel",
        explicit_required: true,
    },
    CallerBindingV1 {
        pointer: "/argv/output_dir",
        role: "caller_owned_new_local_output_directory",
        explicit_required: true,
    },
];

const PRBS9_METRIC_ARTIFACT_BINDINGS: &[CallerBindingV1] = &[
    CallerBindingV1 {
        pointer: "/invocation/artifact_root",
        role: "caller_selected_sipi_published_root_no_hostile_concurrent_writer",
        explicit_required: true,
    },
    CallerBindingV1 {
        pointer: "/reference/artifact_id",
        role: "sealed_reference_artifact_identity",
        explicit_required: true,
    },
    CallerBindingV1 {
        pointer: "/reference/manifest_sha256",
        role: "sealed_reference_manifest_identity",
        explicit_required: true,
    },
    CallerBindingV1 {
        pointer: "/candidate/artifact_id",
        role: "sealed_candidate_artifact_identity",
        explicit_required: true,
    },
    CallerBindingV1 {
        pointer: "/candidate/manifest_sha256",
        role: "sealed_candidate_manifest_identity",
        explicit_required: true,
    },
];

const IBIS_QUASI_STATIC_ARTIFACT_BINDINGS: &[CallerBindingV1] = &[
    CallerBindingV1 {
        pointer: "/invocation/artifact_root",
        role: "caller_selected_sipi_published_root_no_hostile_concurrent_writer",
        explicit_required: true,
    },
    CallerBindingV1 {
        pointer: "/artifact/artifact_id",
        role: "sealed_ibis_artifact_identity",
        explicit_required: true,
    },
    CallerBindingV1 {
        pointer: "/artifact/manifest_sha256",
        role: "sealed_ibis_manifest_identity",
        explicit_required: true,
    },
];

const UPSTREAM_SPICE_BINDINGS: &[CallerBindingV1] = &[
    CallerBindingV1 {
        pointer: "/interpreter",
        role: "caller_selected_external_interpreter",
        explicit_required: true,
    },
    CallerBindingV1 {
        pointer: "/args",
        role: "caller_selected_upstream_workflow_arguments",
        explicit_required: true,
    },
    CallerBindingV1 {
        pointer: "/backend",
        role: "caller_selected_upstream_backend_or_null",
        explicit_required: true,
    },
    CallerBindingV1 {
        pointer: "/working_directory",
        role: "caller_owned_working_directory",
        explicit_required: true,
    },
    CallerBindingV1 {
        pointer: "/artifact_root",
        role: "caller_owned_external_artifact_root",
        explicit_required: true,
    },
];

const UPSTREAM_PYBERT_BINDINGS: &[CallerBindingV1] = &[
    CallerBindingV1 {
        pointer: "/executable",
        role: "caller_selected_external_executable",
        explicit_required: true,
    },
    CallerBindingV1 {
        pointer: "/input",
        role: "caller_selected_upstream_workflow_input",
        explicit_required: true,
    },
    CallerBindingV1 {
        pointer: "/backend",
        role: "caller_selected_upstream_backend",
        explicit_required: true,
    },
    CallerBindingV1 {
        pointer: "/working_directory",
        role: "caller_owned_working_directory",
        explicit_required: true,
    },
    CallerBindingV1 {
        pointer: "/artifact_root",
        role: "caller_owned_external_artifact_root",
        explicit_required: true,
    },
];

const UPSTREAM_COM_BINDINGS: &[CallerBindingV1] = &[
    CallerBindingV1 {
        pointer: "/executable",
        role: "caller_selected_external_cli_executable",
        explicit_required: true,
    },
    CallerBindingV1 {
        pointer: "/interpreter",
        role: "caller_selected_external_python_interpreter",
        explicit_required: true,
    },
    CallerBindingV1 {
        pointer: "/input",
        role: "caller_selected_upstream_workflow_input",
        explicit_required: true,
    },
    CallerBindingV1 {
        pointer: "/backend",
        role: "caller_selected_upstream_backend",
        explicit_required: true,
    },
    CallerBindingV1 {
        pointer: "/working_directory",
        role: "caller_owned_working_directory",
        explicit_required: true,
    },
    CallerBindingV1 {
        pointer: "/artifact_root",
        role: "caller_owned_external_artifact_root",
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
    DiagnosticCodeV1 {
        code: "external_adapter_invalid_request",
        stage: "admission",
        rule_id: "upstream.external-migration-adapter.v1",
    },
    DiagnosticCodeV1 {
        code: "external_adapter_spawn_failed",
        stage: "runtime",
        rule_id: "upstream.external-migration-adapter.v1",
    },
    DiagnosticCodeV1 {
        code: "external_adapter_nonzero_exit",
        stage: "runtime",
        rule_id: "upstream.external-migration-adapter.v1",
    },
    DiagnosticCodeV1 {
        code: "external_adapter_timeout",
        stage: "runtime",
        rule_id: "upstream.external-migration-adapter.v1",
    },
    DiagnosticCodeV1 {
        code: "external_adapter_output_limit",
        stage: "runtime",
        rule_id: "upstream.external-migration-adapter.v1",
    },
    DiagnosticCodeV1 {
        code: "external_adapter_cancelled",
        stage: "runtime",
        rule_id: "upstream.external-migration-adapter.v1",
    },
    DiagnosticCodeV1 {
        code: "external_adapter_failure",
        stage: "runtime",
        rule_id: "upstream.external-migration-adapter.v1",
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
        id: "ibis.quasi-static-evaluate",
        route: &["ibis", "quasi-static-evaluate"],
        availability: CommandAvailabilityV1::Available,
        transport: "stdin_json_v1",
        request_schema: Some(IBIS_QUASI_STATIC_EVALUATE_REQUEST_SCHEMA),
        response_schema: Some("sipi.ibis.input-typ-quasi-static-evaluate.response.v1"),
        unavailable_reason: None,
        nonclaim: "caller_input_quasi_static_constitutive_only",
    },
    CommandDescriptorV1 {
        id: "ibis.quasi-static-evaluate-artifact-batch",
        route: &["ibis", "quasi-static-evaluate-artifact-batch"],
        availability: CommandAvailabilityV1::Available,
        transport: "stdin_json_v1",
        request_schema: Some(IBIS_QUASI_STATIC_ARTIFACT_BATCH_EVALUATE_REQUEST_SCHEMA),
        response_schema: Some(
            "sipi.ibis.input-typ-quasi-static-artifact-batch-evaluate.response.v1",
        ),
        unavailable_reason: None,
        nonclaim: "sealed_caller_asset_bounded_quasi_static_constitutive_batch_only",
    },
    CommandDescriptorV1 {
        id: "ibis.quasi-static-evaluate-artifact",
        route: &["ibis", "quasi-static-evaluate-artifact"],
        availability: CommandAvailabilityV1::Available,
        transport: "stdin_json_v1",
        request_schema: Some(IBIS_QUASI_STATIC_ARTIFACT_EVALUATE_REQUEST_SCHEMA),
        response_schema: Some("sipi.ibis.input-typ-quasi-static-artifact-evaluate.response.v1"),
        unavailable_reason: None,
        nonclaim: "sealed_caller_asset_quasi_static_constitutive_only",
    },
    CommandDescriptorV1 {
        id: "rx-load.differential-rc-evaluate",
        route: &["rx-load", "differential-rc-evaluate"],
        availability: CommandAvailabilityV1::Available,
        transport: "stdin_json_v1",
        request_schema: Some(sipi_contracts::RX_LOAD_DIFFERENTIAL_RC_EVALUATE_REQUEST_SCHEMA),
        response_schema: Some("sipi.rx-load.selected-differential-rc-evaluate.response.v1"),
        unavailable_reason: None,
        nonclaim: "selected_continuous_constitutive_relation_only",
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
        id: "tran.one-node-rc-pulse",
        route: &["tran", "one-node-rc-pulse"],
        availability: CommandAvailabilityV1::Available,
        transport: "stdin_json_v1",
        request_schema: Some(TRAN_ONE_NODE_RC_PULSE_REQUEST_SCHEMA),
        response_schema: Some("sipi.tran.one-node-rc-pulse-run-result.v1"),
        unavailable_reason: None,
        nonclaim: "bounded_product_owned_one_node_rc_pulse_only",
    },
    CommandDescriptorV1 {
        id: "tran.one-node-rc-pwl",
        route: &["tran", "one-node-rc-pwl"],
        availability: CommandAvailabilityV1::Available,
        transport: "stdin_json_v1",
        request_schema: Some(TRAN_ONE_NODE_RC_PWL_REQUEST_SCHEMA),
        response_schema: Some("sipi.tran.one-node-rc-pwl-run-result.v1"),
        unavailable_reason: None,
        nonclaim: "bounded_product_owned_one_node_rc_pwl_only",
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
        id: "link.receiver.run",
        route: &["link", "receiver", "run"],
        availability: CommandAvailabilityV1::Available,
        transport: "stdin_json_v1",
        request_schema: Some(RECEIVER_DIAGNOSTIC_RUN_REQUEST_SCHEMA),
        response_schema: Some("sipi.receiver.diagnostic-run-result.v1"),
        unavailable_reason: None,
        nonclaim: "product_owned_diagnostic_not_rfm_parity_or_clock_lock",
    },
    CommandDescriptorV1 {
        id: "channel.run",
        route: &["channel", "run"],
        availability: CommandAvailabilityV1::Available,
        transport: "stdin_json_v1",
        request_schema: Some(CHANNEL_MATCHED_TWO_PORT_KERNEL_RUN_REQUEST_SCHEMA),
        response_schema: Some("sipi.channel.matched-two-port-kernel-run-result.v1"),
        unavailable_reason: None,
        nonclaim: "matched_s21_periodic_kernel_only",
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
    #[cfg(feature = "com-direct-integration")]
    CommandDescriptorV1 {
        id: "com.run",
        route: &["com", "run"],
        availability: CommandAvailabilityV1::Available,
        transport: "argv_r480_v1",
        request_schema: Some(com_direct_cli_contract_v1::COM_R480_ARGV_SCHEMA_V1),
        response_schema: Some("sipi.com.r480-cli-receipt.v1"),
        unavailable_reason: None,
        nonclaim: "r480_direct_port_scoped_no_oracle_acceptance_or_release",
    },
    #[cfg(not(feature = "com-direct-integration"))]
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
        id: "com.run-artifact",
        route: &["com", "run-artifact"],
        availability: CommandAvailabilityV1::Available,
        transport: "stdin_json_v1",
        request_schema: Some(COM_RUN_ARTIFACT_REQUEST_SCHEMA),
        response_schema: Some("sipi.com.run-artifact-specified-result.v1"),
        unavailable_reason: None,
        nonclaim: "product_owned_bounded_artifact_execution_non_oracle_only",
    },
    CommandDescriptorV1 {
        id: "upstream.agent-spice.fit-sparam",
        route: &["upstream", "agent-spice", "fit-sparam"],
        availability: CommandAvailabilityV1::Available,
        transport: "external_migration_adapter",
        request_schema: Some(UPSTREAM_MIGRATION_REQUEST_SCHEMA),
        response_schema: Some(UPSTREAM_MIGRATION_RESPONSE_SCHEMA),
        unavailable_reason: None,
        nonclaim: "external_upstream_transport_only_no_product_capability_or_acceptance",
    },
    CommandDescriptorV1 {
        id: "upstream.agent-spice.fit-sparam-cascade",
        route: &["upstream", "agent-spice", "fit-sparam-cascade"],
        availability: CommandAvailabilityV1::Available,
        transport: "external_migration_adapter",
        request_schema: Some(UPSTREAM_MIGRATION_REQUEST_SCHEMA),
        response_schema: Some(UPSTREAM_MIGRATION_RESPONSE_SCHEMA),
        unavailable_reason: None,
        nonclaim: "external_upstream_transport_only_no_product_capability_or_acceptance",
    },
    CommandDescriptorV1 {
        id: "upstream.agent-spice.fit-yparam",
        route: &["upstream", "agent-spice", "fit-yparam"],
        availability: CommandAvailabilityV1::Available,
        transport: "external_migration_adapter",
        request_schema: Some(UPSTREAM_MIGRATION_REQUEST_SCHEMA),
        response_schema: Some(UPSTREAM_MIGRATION_RESPONSE_SCHEMA),
        unavailable_reason: None,
        nonclaim: "external_upstream_transport_only_no_product_capability_or_acceptance",
    },
    CommandDescriptorV1 {
        id: "upstream.agent-spice.tune-yparam-tran",
        route: &["upstream", "agent-spice", "tune-yparam-tran"],
        availability: CommandAvailabilityV1::Available,
        transport: "external_migration_adapter",
        request_schema: Some(UPSTREAM_MIGRATION_REQUEST_SCHEMA),
        response_schema: Some(UPSTREAM_MIGRATION_RESPONSE_SCHEMA),
        unavailable_reason: None,
        nonclaim: "external_upstream_transport_only_no_product_capability_or_acceptance",
    },
    CommandDescriptorV1 {
        id: "upstream.agent-spice.run-hspice",
        route: &["upstream", "agent-spice", "run-hspice"],
        availability: CommandAvailabilityV1::Available,
        transport: "external_migration_adapter",
        request_schema: Some(UPSTREAM_MIGRATION_REQUEST_SCHEMA),
        response_schema: Some(UPSTREAM_MIGRATION_RESPONSE_SCHEMA),
        unavailable_reason: None,
        nonclaim: "external_upstream_transport_only_no_product_capability_or_acceptance",
    },
    CommandDescriptorV1 {
        id: "upstream.agent-spice.run-rfm",
        route: &["upstream", "agent-spice", "run-rfm"],
        availability: CommandAvailabilityV1::Available,
        transport: "external_migration_adapter",
        request_schema: Some(UPSTREAM_MIGRATION_REQUEST_SCHEMA),
        response_schema: Some(UPSTREAM_MIGRATION_RESPONSE_SCHEMA),
        unavailable_reason: None,
        nonclaim: "external_upstream_transport_only_no_product_capability_or_acceptance",
    },
    CommandDescriptorV1 {
        id: "upstream.pybert.sim",
        route: &["upstream", "pybert", "sim"],
        availability: CommandAvailabilityV1::Available,
        transport: "external_migration_adapter",
        request_schema: Some(UPSTREAM_MIGRATION_REQUEST_SCHEMA),
        response_schema: Some(UPSTREAM_MIGRATION_RESPONSE_SCHEMA),
        unavailable_reason: None,
        nonclaim: "external_upstream_transport_only_no_product_capability_or_acceptance",
    },
    CommandDescriptorV1 {
        id: "upstream.pybert.sim-native",
        route: &["upstream", "pybert", "sim-native"],
        availability: CommandAvailabilityV1::Available,
        transport: "external_migration_adapter",
        request_schema: Some(UPSTREAM_MIGRATION_REQUEST_SCHEMA),
        response_schema: Some(UPSTREAM_MIGRATION_RESPONSE_SCHEMA),
        unavailable_reason: None,
        nonclaim: "external_upstream_transport_only_no_product_capability_or_acceptance",
    },
    CommandDescriptorV1 {
        id: "upstream.pybert.sim-rust",
        route: &["upstream", "pybert", "sim-rust"],
        availability: CommandAvailabilityV1::Available,
        transport: "external_migration_adapter",
        request_schema: Some(UPSTREAM_MIGRATION_REQUEST_SCHEMA),
        response_schema: Some(UPSTREAM_MIGRATION_RESPONSE_SCHEMA),
        unavailable_reason: None,
        nonclaim: "external_upstream_transport_only_no_product_capability_or_acceptance",
    },
    CommandDescriptorV1 {
        id: "upstream.pybert.sim-auto",
        route: &["upstream", "pybert", "sim-auto"],
        availability: CommandAvailabilityV1::Available,
        transport: "external_migration_adapter",
        request_schema: Some(UPSTREAM_MIGRATION_REQUEST_SCHEMA),
        response_schema: Some(UPSTREAM_MIGRATION_RESPONSE_SCHEMA),
        unavailable_reason: None,
        nonclaim: "external_upstream_transport_only_no_product_capability_or_acceptance",
    },
    CommandDescriptorV1 {
        id: "upstream.pybert.sim-compare",
        route: &["upstream", "pybert", "sim-compare"],
        availability: CommandAvailabilityV1::Available,
        transport: "external_migration_adapter",
        request_schema: Some(UPSTREAM_MIGRATION_REQUEST_SCHEMA),
        response_schema: Some(UPSTREAM_MIGRATION_RESPONSE_SCHEMA),
        unavailable_reason: None,
        nonclaim: "external_upstream_transport_only_no_product_capability_or_acceptance",
    },
    CommandDescriptorV1 {
        id: "upstream.agent-com.config-validate",
        route: &["upstream", "agent-com", "config-validate"],
        availability: CommandAvailabilityV1::Available,
        transport: "external_migration_adapter",
        request_schema: Some(UPSTREAM_MIGRATION_REQUEST_SCHEMA),
        response_schema: Some(UPSTREAM_MIGRATION_RESPONSE_SCHEMA),
        unavailable_reason: None,
        nonclaim: "external_upstream_transport_only_no_product_capability_or_acceptance",
    },
    CommandDescriptorV1 {
        id: "upstream.agent-com.run",
        route: &["upstream", "agent-com", "run"],
        availability: CommandAvailabilityV1::Available,
        transport: "external_migration_adapter",
        request_schema: Some(UPSTREAM_MIGRATION_REQUEST_SCHEMA),
        response_schema: Some(UPSTREAM_MIGRATION_RESPONSE_SCHEMA),
        unavailable_reason: None,
        nonclaim: "external_upstream_transport_only_no_product_capability_or_acceptance",
    },
    CommandDescriptorV1 {
        id: "upstream.agent-com.compare",
        route: &["upstream", "agent-com", "compare"],
        availability: CommandAvailabilityV1::Available,
        transport: "external_migration_adapter",
        request_schema: Some(UPSTREAM_MIGRATION_REQUEST_SCHEMA),
        response_schema: Some(UPSTREAM_MIGRATION_RESPONSE_SCHEMA),
        unavailable_reason: None,
        nonclaim: "external_upstream_transport_only_no_product_capability_or_acceptance",
    },
    CommandDescriptorV1 {
        id: "upstream.agent-com.public-api",
        route: &["upstream", "agent-com", "public-api"],
        availability: CommandAvailabilityV1::Available,
        transport: "external_migration_adapter",
        request_schema: Some(UPSTREAM_MIGRATION_REQUEST_SCHEMA),
        response_schema: Some(UPSTREAM_MIGRATION_RESPONSE_SCHEMA),
        unavailable_reason: None,
        nonclaim: "external_upstream_transport_only_no_product_capability_or_acceptance",
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
        availability: CommandAvailabilityV1::Available,
        transport: "stdin_json_v1",
        request_schema: Some(ARRAY_COMPARE_REQUEST_SCHEMA),
        response_schema: Some("sipi.compare.aligned-arrays-run-result.v1"),
        unavailable_reason: None,
        nonclaim: "caller_aligned_arrays_only",
    },
    CommandDescriptorV1 {
        id: "compare.prbs9-metrics.run",
        route: &["compare", "prbs9-metrics"],
        availability: CommandAvailabilityV1::Available,
        transport: "stdin_json_v1",
        request_schema: Some(sipi_contracts::PRBS9_METRIC_ARTIFACTS_REQUEST_SCHEMA),
        response_schema: Some("sipi.compare.prbs9-metric-artifacts-run-result.v1"),
        unavailable_reason: None,
        nonclaim: "caller_selected_sealed_artifacts_only",
    },
    CommandDescriptorV1 {
        id: "compare.prbs9-waveform-only.run",
        route: &["compare", "prbs9-waveform-only"],
        availability: CommandAvailabilityV1::Available,
        transport: "stdin_json_v1",
        request_schema: Some(SELECTED_HIGHLOSS_PRBS9_WAVEFORM_ONLY_ARTIFACTS_REQUEST_SCHEMA_V3),
        response_schema: Some(
            "sipi.compare.selected-highloss-prbs9-waveform-only-artifacts-run-result.v3",
        ),
        unavailable_reason: None,
        nonclaim: "selected_highloss_raw_post_channel_waveform_only",
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
        command_id: "ibis.quasi-static-evaluate",
        example_id: Some("product-owned-minimal-v1"),
        required_options: &[],
        caller_bindings: &[],
        validation_rule_id: Some("ibis.input-typ.quasi-static.v1"),
        successful_exit: 0,
        diagnostic_contract: "single_json_stdout_and_zero_stderr_on_success",
    },
    CommandProtocolProfileV1 {
        command_id: "ibis.quasi-static-evaluate-artifact-batch",
        example_id: None,
        required_options: &["--artifact-root"],
        caller_bindings: IBIS_QUASI_STATIC_ARTIFACT_BINDINGS,
        validation_rule_id: Some("ibis.input-typ.quasi-static.sealed-artifact-batch.v1"),
        successful_exit: 0,
        diagnostic_contract: "single_json_stdout_and_zero_stderr_on_success",
    },
    CommandProtocolProfileV1 {
        command_id: "ibis.quasi-static-evaluate-artifact",
        example_id: None,
        required_options: &["--artifact-root"],
        caller_bindings: IBIS_QUASI_STATIC_ARTIFACT_BINDINGS,
        validation_rule_id: Some("ibis.input-typ.quasi-static.sealed-artifact.v1"),
        successful_exit: 0,
        diagnostic_contract: "single_json_stdout_and_zero_stderr_on_success",
    },
    CommandProtocolProfileV1 {
        command_id: "rx-load.differential-rc-evaluate",
        example_id: Some("product-owned-minimal-v1"),
        required_options: &[],
        caller_bindings: &[],
        validation_rule_id: Some("rx-load.selected-differential-rc.v1"),
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
        command_id: "tran.one-node-rc-pulse",
        example_id: Some("product-owned-minimal-v1"),
        required_options: &["--artifact-root", "--artifact-id"],
        caller_bindings: ARTIFACT_DESTINATION_BINDINGS,
        validation_rule_id: Some("tran.one-node-rc-pulse.v1"),
        successful_exit: 0,
        diagnostic_contract: "single_json_stdout_and_zero_stderr_on_success",
    },
    CommandProtocolProfileV1 {
        command_id: "tran.one-node-rc-pwl",
        example_id: Some("product-owned-minimal-v1"),
        required_options: &["--artifact-root", "--artifact-id"],
        caller_bindings: ARTIFACT_DESTINATION_BINDINGS,
        validation_rule_id: Some("tran.one-node-rc-pwl.v1"),
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
        command_id: "link.receiver.run",
        example_id: Some("product-owned-minimal-v1"),
        required_options: &["--artifact-root", "--artifact-id"],
        caller_bindings: ARTIFACT_DESTINATION_BINDINGS,
        validation_rule_id: Some("receiver.diagnostic.v1.profile"),
        successful_exit: 0,
        diagnostic_contract: "single_json_stdout_and_zero_stderr_on_success",
    },
    CommandProtocolProfileV1 {
        command_id: "channel.run",
        example_id: Some("product-owned-minimal-v1"),
        required_options: &[],
        caller_bindings: &[],
        validation_rule_id: Some("channel.matched-two-port-kernel.v1"),
        successful_exit: 0,
        diagnostic_contract: "single_json_stdout_and_zero_stderr_on_success",
    },
    CommandProtocolProfileV1 {
        command_id: "compare.run",
        example_id: Some("product-owned-minimal-v1"),
        required_options: &[],
        caller_bindings: &[],
        validation_rule_id: Some("compare.aligned-arrays.v1"),
        successful_exit: 0,
        diagnostic_contract: "single_json_stdout_and_zero_stderr_on_success",
    },
    CommandProtocolProfileV1 {
        command_id: "compare.prbs9-metrics.run",
        example_id: None,
        required_options: &["--artifact-root"],
        caller_bindings: PRBS9_METRIC_ARTIFACT_BINDINGS,
        validation_rule_id: Some("compare.prbs9-metrics.sealed-artifacts.v1"),
        successful_exit: 0,
        diagnostic_contract: "single_json_stdout_and_zero_stderr_on_success",
    },
    CommandProtocolProfileV1 {
        command_id: "compare.prbs9-waveform-only.run",
        example_id: None,
        required_options: &["--artifact-root"],
        caller_bindings: PRBS9_METRIC_ARTIFACT_BINDINGS,
        validation_rule_id: Some(
            "compare.selected-highloss.prbs9-waveform-only.sealed-artifacts.v3",
        ),
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
    CommandProtocolProfileV1 {
        command_id: "com.run-artifact",
        example_id: None,
        required_options: &["--pulse-root"],
        caller_bindings: COM_RUN_ARTIFACT_BINDINGS,
        validation_rule_id: Some("com.run-artifact.specified-non-oracle.v1"),
        successful_exit: 0,
        diagnostic_contract: "single_json_stdout_and_zero_stderr_on_success",
    },
    #[cfg(feature = "com-direct-integration")]
    CommandProtocolProfileV1 {
        command_id: "com.run",
        example_id: None,
        required_options: &["--config", "--thru", "--output-dir"],
        caller_bindings: COM_R480_ARGV_BINDINGS,
        validation_rule_id: None,
        successful_exit: 0,
        diagnostic_contract: "single_path_free_typed_receipt_stdout_and_zero_stderr_on_success",
    },
    CommandProtocolProfileV1 {
        command_id: "upstream.agent-spice.fit-sparam",
        example_id: None,
        required_options: &["--stdin"],
        caller_bindings: UPSTREAM_SPICE_BINDINGS,
        validation_rule_id: Some(upstream_migration::VALIDATION_RULE),
        successful_exit: 0,
        diagnostic_contract: "single_json_stdout_and_zero_stderr_on_success_no_external_payload",
    },
    CommandProtocolProfileV1 {
        command_id: "upstream.agent-spice.fit-sparam-cascade",
        example_id: None,
        required_options: &["--stdin"],
        caller_bindings: UPSTREAM_SPICE_BINDINGS,
        validation_rule_id: Some(upstream_migration::VALIDATION_RULE),
        successful_exit: 0,
        diagnostic_contract: "single_json_stdout_and_zero_stderr_on_success_no_external_payload",
    },
    CommandProtocolProfileV1 {
        command_id: "upstream.agent-spice.fit-yparam",
        example_id: None,
        required_options: &["--stdin"],
        caller_bindings: UPSTREAM_SPICE_BINDINGS,
        validation_rule_id: Some(upstream_migration::VALIDATION_RULE),
        successful_exit: 0,
        diagnostic_contract: "single_json_stdout_and_zero_stderr_on_success_no_external_payload",
    },
    CommandProtocolProfileV1 {
        command_id: "upstream.agent-spice.tune-yparam-tran",
        example_id: None,
        required_options: &["--stdin"],
        caller_bindings: UPSTREAM_SPICE_BINDINGS,
        validation_rule_id: Some(upstream_migration::VALIDATION_RULE),
        successful_exit: 0,
        diagnostic_contract: "single_json_stdout_and_zero_stderr_on_success_no_external_payload",
    },
    CommandProtocolProfileV1 {
        command_id: "upstream.agent-spice.run-hspice",
        example_id: None,
        required_options: &["--stdin"],
        caller_bindings: UPSTREAM_SPICE_BINDINGS,
        validation_rule_id: Some(upstream_migration::VALIDATION_RULE),
        successful_exit: 0,
        diagnostic_contract: "single_json_stdout_and_zero_stderr_on_success_no_external_payload",
    },
    CommandProtocolProfileV1 {
        command_id: "upstream.agent-spice.run-rfm",
        example_id: None,
        required_options: &["--stdin"],
        caller_bindings: UPSTREAM_SPICE_BINDINGS,
        validation_rule_id: Some(upstream_migration::VALIDATION_RULE),
        successful_exit: 0,
        diagnostic_contract: "single_json_stdout_and_zero_stderr_on_success_no_external_payload",
    },
    CommandProtocolProfileV1 {
        command_id: "upstream.pybert.sim",
        example_id: None,
        required_options: &["--stdin"],
        caller_bindings: UPSTREAM_PYBERT_BINDINGS,
        validation_rule_id: Some(upstream_migration::VALIDATION_RULE),
        successful_exit: 0,
        diagnostic_contract: "single_json_stdout_and_zero_stderr_on_success_no_external_payload",
    },
    CommandProtocolProfileV1 {
        command_id: "upstream.pybert.sim-native",
        example_id: None,
        required_options: &["--stdin"],
        caller_bindings: UPSTREAM_PYBERT_BINDINGS,
        validation_rule_id: Some(upstream_migration::VALIDATION_RULE),
        successful_exit: 0,
        diagnostic_contract: "single_json_stdout_and_zero_stderr_on_success_no_external_payload",
    },
    CommandProtocolProfileV1 {
        command_id: "upstream.pybert.sim-rust",
        example_id: None,
        required_options: &["--stdin"],
        caller_bindings: UPSTREAM_PYBERT_BINDINGS,
        validation_rule_id: Some(upstream_migration::VALIDATION_RULE),
        successful_exit: 0,
        diagnostic_contract: "single_json_stdout_and_zero_stderr_on_success_no_external_payload",
    },
    CommandProtocolProfileV1 {
        command_id: "upstream.pybert.sim-auto",
        example_id: None,
        required_options: &["--stdin"],
        caller_bindings: UPSTREAM_PYBERT_BINDINGS,
        validation_rule_id: Some(upstream_migration::VALIDATION_RULE),
        successful_exit: 0,
        diagnostic_contract: "single_json_stdout_and_zero_stderr_on_success_no_external_payload",
    },
    CommandProtocolProfileV1 {
        command_id: "upstream.pybert.sim-compare",
        example_id: None,
        required_options: &["--stdin"],
        caller_bindings: UPSTREAM_PYBERT_BINDINGS,
        validation_rule_id: Some(upstream_migration::VALIDATION_RULE),
        successful_exit: 0,
        diagnostic_contract: "single_json_stdout_and_zero_stderr_on_success_no_external_payload",
    },
    CommandProtocolProfileV1 {
        command_id: "upstream.agent-com.config-validate",
        example_id: None,
        required_options: &["--stdin"],
        caller_bindings: UPSTREAM_COM_BINDINGS,
        validation_rule_id: Some(upstream_migration::VALIDATION_RULE),
        successful_exit: 0,
        diagnostic_contract: "single_json_stdout_and_zero_stderr_on_success_no_external_payload",
    },
    CommandProtocolProfileV1 {
        command_id: "upstream.agent-com.run",
        example_id: None,
        required_options: &["--stdin"],
        caller_bindings: UPSTREAM_COM_BINDINGS,
        validation_rule_id: Some(upstream_migration::VALIDATION_RULE),
        successful_exit: 0,
        diagnostic_contract: "single_json_stdout_and_zero_stderr_on_success_no_external_payload",
    },
    CommandProtocolProfileV1 {
        command_id: "upstream.agent-com.compare",
        example_id: None,
        required_options: &["--stdin"],
        caller_bindings: UPSTREAM_COM_BINDINGS,
        validation_rule_id: Some(upstream_migration::VALIDATION_RULE),
        successful_exit: 0,
        diagnostic_contract: "single_json_stdout_and_zero_stderr_on_success_no_external_payload",
    },
    CommandProtocolProfileV1 {
        command_id: "upstream.agent-com.public-api",
        example_id: None,
        required_options: &["--stdin"],
        caller_bindings: UPSTREAM_COM_BINDINGS,
        validation_rule_id: Some(upstream_migration::VALIDATION_RULE),
        successful_exit: 0,
        diagnostic_contract: "single_json_stdout_and_zero_stderr_on_success_no_external_payload",
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
    } else if let [command, repository, workflow, stdin] = &arguments[..]
        && command == "upstream"
        && stdin == "--stdin"
    {
        ProcessAdapter::upstream_migration_stdin(&format!("{repository}.{workflow}"))
    } else if arguments == ["ibis", "inspect", "--stdin"] {
        ProcessAdapter::ibis_inspect_stdin()
    } else if arguments == ["ibis", "dc-evaluate", "--stdin"] {
        ProcessAdapter::ibis_dc_evaluate_stdin()
    } else if arguments == ["ibis", "quasi-static-evaluate", "--stdin"] {
        ProcessAdapter::ibis_quasi_static_evaluate_stdin()
    } else if let [command, action, stdin, root, artifact_root] = &arguments[..]
        && command == "ibis"
        && action == "quasi-static-evaluate-artifact-batch"
        && stdin == "--stdin"
        && root == "--artifact-root"
    {
        ProcessAdapter::ibis_quasi_static_evaluate_artifact_batch_stdin(artifact_root)
    } else if let [command, action, stdin, root, artifact_root] = &arguments[..]
        && command == "ibis"
        && action == "quasi-static-evaluate-artifact"
        && stdin == "--stdin"
        && root == "--artifact-root"
    {
        ProcessAdapter::ibis_quasi_static_evaluate_artifact_stdin(artifact_root)
    } else if arguments == ["rx-load", "differential-rc-evaluate", "--stdin"] {
        ProcessAdapter::rx_load_differential_rc_evaluate_stdin()
    } else if arguments == ["channel", "run", "--stdin"] {
        ProcessAdapter::channel_run_stdin()
    } else if arguments == ["compare", "run", "--stdin"] {
        ProcessAdapter::compare_run_stdin()
    } else if let [command, action, stdin, root, artifact_root] = &arguments[..]
        && command == "compare"
        && action == "prbs9-metrics"
        && stdin == "--stdin"
        && root == "--artifact-root"
    {
        ProcessAdapter::compare_prbs9_metrics_stdin(artifact_root)
    } else if let [command, action, stdin, root, artifact_root] = &arguments[..]
        && command == "compare"
        && action == "prbs9-waveform-only"
        && stdin == "--stdin"
        && root == "--artifact-root"
    {
        ProcessAdapter::compare_selected_highloss_prbs9_waveform_only_stdin(artifact_root)
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
        && command == "tran"
        && action == "one-node-rc-pulse"
        && stdin == "--stdin"
        && root == "--artifact-root"
        && id == "--artifact-id"
    {
        ProcessAdapter::tran_one_node_rc_pulse_stdin(artifact_root, artifact_id)
    } else if let [command, action, stdin, root, artifact_root, id, artifact_id] = &arguments[..]
        && command == "tran"
        && action == "one-node-rc-pwl"
        && stdin == "--stdin"
        && root == "--artifact-root"
        && id == "--artifact-id"
    {
        ProcessAdapter::tran_one_node_rc_pwl_stdin(artifact_root, artifact_id)
    } else if let [command, action, stdin, root, artifact_root, id, artifact_id] = &arguments[..]
        && command == "link"
        && action == "run"
        && stdin == "--stdin"
        && root == "--artifact-root"
        && id == "--artifact-id"
    {
        ProcessAdapter::link_run_stdin(artifact_root, artifact_id)
    } else if let [
        command,
        receiver,
        action,
        stdin,
        root,
        artifact_root,
        id,
        artifact_id,
    ] = &arguments[..]
        && command == "link"
        && receiver == "receiver"
        && action == "run"
        && stdin == "--stdin"
        && root == "--artifact-root"
        && id == "--artifact-id"
    {
        ProcessAdapter::link_receiver_run_stdin(artifact_root, artifact_id)
    } else if let [command, action, stdin, root, artifact_root, id, artifact_id] = &arguments[..]
        && command == "project"
        && action == "run"
        && stdin == "--stdin"
        && root == "--artifact-root"
        && id == "--artifact-id"
    {
        ProcessAdapter::project_run_stdin(artifact_root, artifact_id)
    } else if let [command, action, stdin, pulse, pulse_root] = &arguments[..]
        && command == "com"
        && action == "run-artifact"
        && stdin == "--stdin"
        && pulse == "--pulse-root"
    {
        ProcessAdapter::com_run_artifact_stdin(pulse_root)
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

    fn upstream_migration_stdin(route: &str) -> Response {
        if !upstream_migration::known_route(route) {
            return error(64, "usage", "unknown upstream migration workflow");
        }
        let input = match read_bounded_stdin_request(upstream_migration::max_request_bytes()) {
            Ok(input) => input,
            Err(code) => return error(2, code, "stdin request is invalid"),
        };
        match upstream_migration::execute(route, &input) {
            Ok(result) => success(result),
            Err(failure) => error(3, failure.kind.diagnostic_code(), "external adapter failed"),
        }
    }

    fn tran_run_stdin(artifact_root: &str, artifact_id: &str) -> Response {
        let input = match read_stdin_request() {
            Ok(input) => input,
            Err(code) => return error(2, code, "stdin request is invalid"),
        };
        if input.len() > COM_RUN_ARTIFACT_REQUEST_MAX_BYTES_V1 {
            return error(
                3,
                "contract_rejected",
                "specified COM artifact request was rejected",
            );
        }
        if parse_tran_rc_pulse_request_v1(&input).is_err() {
            return error(3, "contract_rejected", "TRAN request was rejected");
        }
        run_fixed_tran(artifact_root, artifact_id, &input)
    }

    fn tran_one_node_rc_pulse_stdin(artifact_root: &str, artifact_id: &str) -> Response {
        let input = match read_stdin_request() {
            Ok(input) => input,
            Err(code) => return error(2, code, "stdin request is invalid"),
        };
        let request = match parse_tran_one_node_rc_pulse_request_v1(&input) {
            Ok(request) => request,
            Err(_) => return error(3, "contract_rejected", "one-node TRAN request was rejected"),
        };
        run_one_node_tran(artifact_root, artifact_id, &request)
    }

    fn tran_one_node_rc_pwl_stdin(artifact_root: &str, artifact_id: &str) -> Response {
        let input = match read_stdin_request() {
            Ok(input) => input,
            Err(code) => return error(2, code, "stdin request is invalid"),
        };
        let request = match parse_tran_one_node_rc_pwl_request_v1(&input) {
            Ok(request) => request,
            Err(_) => {
                return error(
                    3,
                    "contract_rejected",
                    "one-node PWL TRAN request was rejected",
                );
            }
        };
        run_one_node_pwl_tran(artifact_root, artifact_id, &request)
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

    fn link_receiver_run_stdin(artifact_root: &str, artifact_id: &str) -> Response {
        let input = match read_stdin_request() {
            Ok(input) => input,
            Err(code) => return error(2, code, "stdin request is invalid"),
        };
        let request = match parse_receiver_diagnostic_run_request_v1(&input) {
            Ok(request) => request,
            Err(_) => {
                return error(
                    3,
                    "contract_rejected",
                    "diagnostic receiver request was rejected",
                );
            }
        };
        run_diagnostic_receiver(artifact_root, artifact_id, &request)
    }

    fn channel_run_stdin() -> Response {
        let input = match read_stdin_request() {
            Ok(input) => input,
            Err(code) => return error(2, code, "stdin request is invalid"),
        };
        let request = match parse_channel_matched_two_port_kernel_run_request_v1(&input) {
            Ok(request) => request,
            Err(_) => return error(3, "contract_rejected", "channel request was rejected"),
        };
        run_matched_channel_kernel(request.text())
    }

    fn compare_run_stdin() -> Response {
        let input = match read_stdin_request() {
            Ok(input) => input,
            Err(code) => return error(2, code, "stdin request is invalid"),
        };
        let request = match parse_array_compare_request_v1(&input) {
            Ok(request) => request,
            Err(_) => {
                return error(
                    3,
                    "contract_rejected",
                    "aligned-array compare request was rejected",
                );
            }
        };
        run_array_compare(&request)
    }

    fn compare_prbs9_metrics_stdin(artifact_root: &str) -> Response {
        let input = match read_stdin_request() {
            Ok(input) => input,
            Err(code) => return error(2, code, "stdin request is invalid"),
        };
        let request = match parse_prbs9_metric_artifacts_request_v1(&input) {
            Ok(request) => request,
            Err(_) => return error(3, "contract_rejected", "PRBS9 metric request was rejected"),
        };
        run_prbs9_metric_artifact_compare(artifact_root, &request)
    }

    fn compare_selected_highloss_prbs9_waveform_only_stdin(artifact_root: &str) -> Response {
        let input = match read_stdin_request() {
            Ok(input) => input,
            Err(code) => return error(2, code, "stdin request is invalid"),
        };
        let request = match parse_selected_highloss_prbs9_waveform_only_artifacts_request_v3(&input)
        {
            Ok(request) => request,
            Err(_) => {
                return error(
                    3,
                    "contract_rejected",
                    "selected highloss waveform-only request was rejected",
                );
            }
        };
        run_selected_highloss_prbs9_waveform_only_artifact_compare(artifact_root, &request)
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

    fn ibis_quasi_static_evaluate_stdin() -> Response {
        let input = match read_stdin_request() {
            Ok(input) => input,
            Err(code) => return error(2, code, "stdin request is invalid"),
        };
        let request = match parse_ibis_quasi_static_evaluate_request_v1(&input) {
            Ok(request) => request,
            Err(_) => {
                return error(
                    3,
                    "contract_rejected",
                    "IBIS quasi-static request was rejected",
                );
            }
        };
        run_ibis_quasi_static_evaluate(&request)
    }

    fn ibis_quasi_static_evaluate_artifact_stdin(artifact_root: &str) -> Response {
        let input = match read_stdin_request() {
            Ok(input) => input,
            Err(code) => return error(2, code, "stdin request is invalid"),
        };
        let request = match parse_ibis_quasi_static_artifact_evaluate_request_v1(&input) {
            Ok(request) => request,
            Err(_) => {
                return error(
                    3,
                    "contract_rejected",
                    "sealed IBIS quasi-static request was rejected",
                );
            }
        };
        run_ibis_quasi_static_artifact_evaluate(artifact_root, &request)
    }

    fn ibis_quasi_static_evaluate_artifact_batch_stdin(artifact_root: &str) -> Response {
        let input = match read_stdin_request() {
            Ok(input) => input,
            Err(code) => return error(2, code, "stdin request is invalid"),
        };
        let request = match parse_ibis_quasi_static_artifact_batch_evaluate_request_v1(&input) {
            Ok(request) => request,
            Err(_) => {
                return error(
                    3,
                    "contract_rejected",
                    "sealed IBIS quasi-static batch request was rejected",
                );
            }
        };
        run_ibis_quasi_static_artifact_batch_evaluate(artifact_root, &request)
    }

    fn rx_load_differential_rc_evaluate_stdin() -> Response {
        let input = match read_stdin_request() {
            Ok(input) => input,
            Err(code) => return error(2, code, "stdin request is invalid"),
        };
        let request = match parse_rx_load_differential_rc_evaluate_request_v1(&input) {
            Ok(request) => request,
            Err(_) => {
                return error(
                    3,
                    "contract_rejected",
                    "selected differential R-C load request was rejected",
                );
            }
        };
        run_rx_load_differential_rc_evaluate(&request)
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

    fn com_run_artifact_stdin(pulse_root: &str) -> Response {
        let input = match read_bounded_stdin_request(COM_RUN_ARTIFACT_REQUEST_MAX_BYTES_V1) {
            Ok(input) => input,
            Err(code) => return error(2, code, "stdin request is invalid"),
        };
        if preflight_com_run_artifact_request_v1(&input).is_err() {
            return error(
                3,
                "contract_rejected",
                "specified COM artifact request was rejected",
            );
        }
        let request = match parse_com_run_artifact_request_v1(&input) {
            Ok(request) => request,
            Err(_) => {
                return error(
                    3,
                    "contract_rejected",
                    "specified COM artifact request was rejected",
                );
            }
        };
        run_com_artifact(pulse_root, &request)
    }
}

fn read_stdin_request() -> Result<Vec<u8>, &'static str> {
    read_bounded_stdin_request(1_048_576)
}

fn read_bounded_stdin_request(maximum: usize) -> Result<Vec<u8>, &'static str> {
    let mut input = Vec::with_capacity(maximum.min(8192));
    io::stdin()
        .take((maximum + 1) as u64)
        .read_to_end(&mut input)
        .map_err(|_| "operational_failure")?;
    if input.len() > maximum || input.is_empty() || input.starts_with(&[0xEF, 0xBB, 0xBF]) {
        Err("invalid_input")
    } else {
        Ok(input)
    }
}

fn run_com_artifact(
    pulse_root_path: &str,
    request: &sipi_contracts::ComRunArtifactRequestV1,
) -> Response {
    let pulse_root = match ArtifactRoot::open_existing(Path::new(pulse_root_path)) {
        Ok(root) => root,
        Err(_) => {
            return error(
                5,
                "operational_failure",
                "pulse artifact root is unavailable",
            );
        }
    };
    let pulse_identity = match ComRunPulseArtifactIdentityV1::try_new(
        request.pulse_artifact_id.clone(),
        request.pulse_manifest_sha256.clone(),
    ) {
        Ok(identity) => identity,
        Err(_) => {
            return error(
                3,
                "contract_rejected",
                "pulse artifact identity was rejected",
            );
        }
    };
    let provided_values = match product_parameter_values(&request.params) {
        Ok(values) => values,
        Err(_) => return error(3, "contract_rejected", "COM parameter values were rejected"),
    };
    let defaults = match product_parameter_values(&request.defaults) {
        Ok(values) => values,
        Err(_) => return error(3, "contract_rejected", "COM default values were rejected"),
    };
    let report = match execute_com_run_artifact_from_product_values_v1(
        &request.artifact_root,
        &request.artifact_id,
        &pulse_root,
        &pulse_identity,
        &request.consumed_keys,
        &provided_values,
        &defaults,
        &request.unconsumed_keys,
    ) {
        Ok(report) => report,
        Err(_) => {
            return error(
                5,
                "operational_failure",
                "COM artifact execution did not complete",
            );
        }
    };
    let result = report.result();
    let parameters = report.parameter_consumption();
    success(format!(
        "{{\"schema\":\"{}\",\"policy\":\"{}\",\"input\":{{\"artifact_id\":\"{}\",\"manifest_sha256\":\"{}\",\"payload\":\"pulse.f64le\",\"pulse_sample_count\":{}}},\"output_artifact_id\":\"{}\",\"parameters\":{{\"policy\":\"{}\",\"consumed_keys\":{},\"provided_value_keys\":{},\"defaulted_keys\":{},\"unconsumed_keys\":{},\"workbook_value_keys\":[]}},\"result\":{{\"schema\":\"{}\",\"policy\":\"{}\",\"admitted\":{},\"com_db\":{},\"vec_db\":{},\"veo_mv\":{},\"sigma_n_v\":{},\"invalid_reason\":null}},\"scope\":{{\"behavioral_replication\":\"not_claimed\",\"agent_com_parity\":\"not_claimed\",\"external_acceptance\":\"blocked\",\"ieee_certification\":false,\"release_evidence\":false}}}}",
        COM_RUN_ARTIFACT_SPECIFIED_RESULT_SCHEMA_V1,
        sipi_com::COM_RUN_ARTIFACT_SPECIFIED_POLICY_V1,
        report.input_artifact_id(),
        report.input_manifest_sha256(),
        report.pulse_sample_count(),
        report.output_provenance().binding().artifact_id(),
        sipi_com::COM_SPECIFIED_PARAMETER_INGESTION_POLICY_V1,
        json_string_array(parameters.consumed_keys()),
        json_string_array(parameters.provided_value_keys()),
        json_string_array(parameters.defaulted_keys()),
        json_string_array(parameters.unconsumed_keys()),
        result.schema(),
        result.policy(),
        result.admitted(),
        result.com_db().map_or_else(|| "null".to_owned(), json_f64),
        result.vec_db().map_or_else(|| "null".to_owned(), json_f64),
        result.veo_mv().map_or_else(|| "null".to_owned(), json_f64),
        result
            .sigma_n_v()
            .map_or_else(|| "null".to_owned(), json_f64),
    ))
}

fn json_f64(value: f64) -> String {
    serde_json::to_string(&value).unwrap_or_else(|_| "null".to_owned())
}

fn product_parameter_values(
    values: &BTreeMap<String, ComParameterValueV1>,
) -> Result<BTreeMap<String, ResolvedDefaultV1>, ()> {
    values
        .iter()
        .map(|(key, value)| {
            let resolved = match value {
                ComParameterValueV1::Scalar(value) if value.is_finite() => {
                    ResolvedDefaultV1::Scalar(*value)
                }
                ComParameterValueV1::Boolean(value) => ResolvedDefaultV1::Boolean(*value),
                ComParameterValueV1::String(value) => ResolvedDefaultV1::String(value.clone()),
                ComParameterValueV1::Vector(values) => ResolvedDefaultV1::Vector(values.clone()),
                ComParameterValueV1::Matrix(values) => ResolvedDefaultV1::Matrix(values.clone()),
                ComParameterValueV1::Scalar(_) => return Err(()),
            };
            Ok((key.clone(), resolved))
        })
        .collect()
}

fn json_string_array(values: &[String]) -> String {
    let encoded = values
        .iter()
        .map(|value| serde_json::to_string(value).unwrap_or_else(|_| "\"\"".to_owned()))
        .collect::<Vec<_>>()
        .join(",");
    format!("[{encoded}]")
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

fn run_one_node_tran(
    artifact_root: &str,
    artifact_id: &str,
    request: &sipi_contracts::TranOneNodeRcPulseRequestV1,
) -> Response {
    const MAX_OUTPUT_SAMPLES: usize = 4096;
    const MAX_BREAKPOINTS: usize = 16_384;
    let policy = match RunPolicy::try_new(Duration::from_secs(1), 32_768, 8 * 1_024 * 1_024) {
        Ok(policy) => policy,
        Err(_) => return error(6, "internal_failure", "run policy is unavailable"),
    };
    let id = match RunId::try_new(artifact_id) {
        Ok(id) => id,
        Err(_) => return error(2, "invalid_artifact_id", "artifact id is invalid"),
    };
    let (_, context) = match Runtime::start(id, policy) {
        Ok(run) => run,
        Err(_) => return error(6, "internal_failure", "runtime is unavailable"),
    };
    let canonical_request = match deterministic_json(request) {
        Ok(bytes) => bytes,
        Err(_) => {
            return error(
                6,
                "internal_contract_error",
                "TRAN request cannot be serialized",
            );
        }
    };
    let typed_request = match one_node_request(request) {
        Ok(request) => request,
        Err(_) => return error(3, "contract_rejected", "one-node TRAN request was rejected"),
    };
    let limits = OneNodeRcPulseLimitsV1::new(
        NonZeroUsize::new(MAX_OUTPUT_SAMPLES).expect("constant output limit"),
        NonZeroUsize::new(MAX_BREAKPOINTS).expect("constant breakpoint limit"),
    );
    let request_key = cache_key("request", &canonical_request);
    let root = Path::new(artifact_root);
    let result = Runtime::execute(&context, |context| -> Result<_, ()> {
        context
            .consume(ResourceCost {
                work_units: MAX_BREAKPOINTS as u64,
                accounted_bytes: canonical_request.len() as u64 + 4 * 1_024 * 1_024,
            })
            .map_err(|_| ())?;
        let simulation = simulate_one_node_rc_pulse_with_context(&typed_request, limits, context)
            .map_err(|_| ())?;
        let result_json = one_node_result_json(&simulation).map_err(|_| ())?;
        let result_key = cache_key("result", result_json.as_bytes());
        let provenance = format!(
            "{{\"schema\":\"sipi.tran.one-node-rc-pulse.provenance.v1\",\"topology\":\"ideal_pulse_series_r_capacitor_to_explicit_ref\",\"algorithm\":\"backward_euler_one_node_rc_pulse_v1\",\"request_cache_key\":\"{request_key}\",\"result_cache_key\":\"{result_key}\",\"max_output_samples\":{MAX_OUTPUT_SAMPLES},\"max_integration_breakpoints\":{MAX_BREAKPOINTS},\"contract\":\"{TRAN_ONE_NODE_RC_PULSE_REQUEST_SCHEMA}\",\"target\":\"{TARGET}\"}}"
        );
        let store = sipi_artifacts::ArtifactRoot::open_or_create(root).map_err(|_| ())?;
        let mut staging = store.begin(artifact_id).map_err(|_| ())?;
        staging
            .stage_reader(
                "request.json",
                Cursor::new(canonical_request.as_slice()),
                1_048_576,
            )
            .map_err(|_| ())?;
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
        Ok((request_key, result_key, manifest))
    });
    match result {
        Ok((request_key, result_key, manifest)) => success(format!(
            "{{\"schema\":\"sipi.tran.one-node-rc-pulse-run-result.v1\",\"artifact_id\":\"{}\",\"request_cache_key\":\"{}\",\"result_cache_key\":\"{}\",\"manifest_schema\":\"{}\",\"file_count\":{}}}",
            manifest.artifact_id,
            request_key,
            result_key,
            manifest.schema,
            manifest.files.len()
        )),
        Err(_) => error(
            5,
            "operational_failure",
            "one-node TRAN run did not publish an artifact",
        ),
    }
}

fn one_node_request(
    request: &sipi_contracts::TranOneNodeRcPulseRequestV1,
) -> Result<OneNodeRcPulseRequestV1, ()> {
    let pulse = IdealPulseV1::try_new(
        Volts::try_new(request.pulse.voltage_low_volts).map_err(|_| ())?,
        Volts::try_new(request.pulse.voltage_high_volts).map_err(|_| ())?,
        Seconds::try_new(request.pulse.delay_seconds).map_err(|_| ())?,
        Seconds::try_new(request.pulse.rise_seconds).map_err(|_| ())?,
        Seconds::try_new(request.pulse.fall_seconds).map_err(|_| ())?,
        Seconds::try_new(request.pulse.width_seconds).map_err(|_| ())?,
        Seconds::try_new(request.pulse.period_seconds).map_err(|_| ())?,
    )
    .map_err(|_| ())?;
    let output_times = request
        .output_times_seconds
        .iter()
        .copied()
        .map(|value| Seconds::try_new(value).map_err(|_| ()))
        .collect::<Result<Vec<_>, _>>()?;
    OneNodeRcPulseRequestV1::try_new(
        output_times,
        Ohms::try_new(request.resistance_ohms).map_err(|_| ())?,
        FiniteF64::try_new(request.capacitance_farads, "capacitance farads").map_err(|_| ())?,
        Volts::try_new(request.initial_voltage_out_volts).map_err(|_| ())?,
        pulse,
    )
    .map_err(|_| ())
}

fn run_one_node_pwl_tran(
    artifact_root: &str,
    artifact_id: &str,
    request: &sipi_contracts::TranOneNodeRcPwlRequestV1,
) -> Response {
    const MAX_OUTPUT_SAMPLES: usize = 4096;
    const MAX_BREAKPOINTS: usize = 16_384;
    let policy = match RunPolicy::try_new(Duration::from_secs(1), 32_768, 8 * 1_024 * 1_024) {
        Ok(policy) => policy,
        Err(_) => return error(6, "internal_failure", "run policy is unavailable"),
    };
    let id = match RunId::try_new(artifact_id) {
        Ok(id) => id,
        Err(_) => return error(2, "invalid_artifact_id", "artifact id is invalid"),
    };
    let (_, context) = match Runtime::start(id, policy) {
        Ok(run) => run,
        Err(_) => return error(6, "internal_failure", "runtime is unavailable"),
    };
    let canonical_request = match deterministic_json(request) {
        Ok(bytes) => bytes,
        Err(_) => {
            return error(
                6,
                "internal_contract_error",
                "TRAN request cannot be serialized",
            );
        }
    };
    let typed_request = match one_node_pwl_request(request) {
        Ok(request) => request,
        Err(_) => {
            return error(
                3,
                "contract_rejected",
                "one-node PWL TRAN request was rejected",
            );
        }
    };
    let limits = OneNodeRcPwlLimitsV1::new(
        NonZeroUsize::new(MAX_OUTPUT_SAMPLES).expect("constant output limit"),
        NonZeroUsize::new(MAX_BREAKPOINTS).expect("constant breakpoint limit"),
    );
    let request_key = cache_key("request", &canonical_request);
    let root = Path::new(artifact_root);
    let result = Runtime::execute(&context, |context| -> Result<_, ()> {
        context
            .consume(ResourceCost {
                work_units: MAX_BREAKPOINTS as u64,
                accounted_bytes: canonical_request.len() as u64 + 4 * 1_024 * 1_024,
            })
            .map_err(|_| ())?;
        let simulation = simulate_one_node_rc_pwl_with_context(&typed_request, limits, context)
            .map_err(|_| ())?;
        let result_json = one_node_pwl_result_json(&simulation).map_err(|_| ())?;
        let result_key = cache_key("result", result_json.as_bytes());
        let provenance = format!(
            "{{\"schema\":\"sipi.tran.one-node-rc-pwl.provenance.v1\",\"topology\":\"piecewise_linear_voltage_source_series_r_capacitor_to_explicit_ref\",\"algorithm\":\"backward_euler_one_node_rc_pwl_v1\",\"request_cache_key\":\"{request_key}\",\"result_cache_key\":\"{result_key}\",\"max_output_samples\":{MAX_OUTPUT_SAMPLES},\"max_integration_breakpoints\":{MAX_BREAKPOINTS},\"contract\":\"{TRAN_ONE_NODE_RC_PWL_REQUEST_SCHEMA}\",\"target\":\"{TARGET}\"}}"
        );
        let store = sipi_artifacts::ArtifactRoot::open_or_create(root).map_err(|_| ())?;
        let mut staging = store.begin(artifact_id).map_err(|_| ())?;
        staging
            .stage_reader(
                "request.json",
                Cursor::new(canonical_request.as_slice()),
                1_048_576,
            )
            .map_err(|_| ())?;
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
        Ok((request_key, result_key, manifest))
    });
    match result {
        Ok((request_key, result_key, manifest)) => success(format!(
            "{{\"schema\":\"sipi.tran.one-node-rc-pwl-run-result.v1\",\"artifact_id\":\"{}\",\"request_cache_key\":\"{}\",\"result_cache_key\":\"{}\",\"manifest_schema\":\"{}\",\"file_count\":{}}}",
            manifest.artifact_id,
            request_key,
            result_key,
            manifest.schema,
            manifest.files.len()
        )),
        Err(_) => error(
            5,
            "operational_failure",
            "one-node PWL TRAN run did not publish an artifact",
        ),
    }
}

fn one_node_pwl_request(
    request: &sipi_contracts::TranOneNodeRcPwlRequestV1,
) -> Result<OneNodeRcPwlRequestV1, ()> {
    let output_times = request
        .output_times_seconds
        .iter()
        .copied()
        .map(|value| Seconds::try_new(value).map_err(|_| ()))
        .collect::<Result<Vec<_>, _>>()?;
    let source_times = request
        .source_knot_times_seconds
        .iter()
        .copied()
        .map(|value| Seconds::try_new(value).map_err(|_| ()))
        .collect::<Result<Vec<_>, _>>()?;
    let source_values = request
        .source_knot_voltages
        .iter()
        .copied()
        .map(|value| Volts::try_new(value).map_err(|_| ()))
        .collect::<Result<Vec<_>, _>>()?;
    let source = PiecewiseLinearVoltageV1::try_new(source_times, source_values).map_err(|_| ())?;
    OneNodeRcPwlRequestV1::try_new(
        output_times,
        Ohms::try_new(request.resistance_ohms).map_err(|_| ())?,
        FiniteF64::try_new(request.capacitance_farads, "capacitance farads").map_err(|_| ())?,
        Volts::try_new(request.initial_voltage_out_volts).map_err(|_| ())?,
        source,
    )
    .map_err(|_| ())
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

fn run_diagnostic_receiver(
    artifact_root: &str,
    artifact_id: &str,
    request: &sipi_contracts::ReceiverDiagnosticRunRequestV1,
) -> Response {
    const MAX_ACCOUNTED_BYTES: u64 = 128 * 1024;
    let policy = match RunPolicy::try_new(Duration::from_secs(1), 4_096, MAX_ACCOUNTED_BYTES) {
        Ok(policy) => policy,
        Err(_) => return error(6, "internal_failure", "run policy is unavailable"),
    };
    let id = match RunId::try_new(artifact_id) {
        Ok(id) => id,
        Err(_) => return error(2, "invalid_artifact_id", "artifact id is invalid"),
    };
    let (_, context) = match Runtime::start(id, policy) {
        Ok(run) => run,
        Err(_) => return error(6, "internal_failure", "runtime is unavailable"),
    };
    let canonical_input =
        match deterministic_json(&sipi_contracts::WireReceiverInputV1::from(request.input())) {
            Ok(value) => value,
            Err(_) => {
                return error(
                    6,
                    "internal_contract_error",
                    "receiver input cannot be serialized",
                );
            }
        };
    let canonical_reference = match deterministic_json(&request.reference_bits().to_vec()) {
        Ok(value) => value,
        Err(_) => {
            return error(
                6,
                "internal_contract_error",
                "receiver reference cannot be serialized",
            );
        }
    };
    let reference = match ReferenceBitsV1::try_new(request.reference_bits().to_vec()) {
        Ok(reference) => reference,
        Err(_) => {
            return error(
                3,
                "contract_rejected",
                "receiver reference bits were rejected",
            );
        }
    };
    let input_digest = sha256_hex(&canonical_input);
    let reference_digest = sha256_hex(&canonical_reference);
    let root = Path::new(artifact_root);
    let result = Runtime::execute(&context, |context| -> Result<_, ()> {
        context
            .consume(ResourceCost {
                work_units: 1_024,
                accounted_bytes: canonical_input
                    .len()
                    .checked_add(canonical_reference.len())
                    .and_then(|size| size.checked_add(16_384))
                    .ok_or(())? as u64,
            })
            .map_err(|_| ())?;
        context.checkpoint().map_err(|_| ())?;
        let receiver = run_fixed_receiver_delegated_ambiguity_v2(request.input(), &reference)
            .map_err(|_| ())?;
        context.checkpoint().map_err(|_| ())?;
        let result_json =
            diagnostic_receiver_result_json(request.profile_id(), &receiver).map_err(|_| ())?;
        let result_digest = sha256_hex(result_json.as_bytes());
        let provenance = format!(
            "{{\"schema\":\"sipi.receiver.diagnostic.provenance.v1\",\"mode\":\"product_owned_diagnostic\",\"clock_policy\":\"policy_selected_not_locked\",\"external_rfm\":false,\"acceptance\":false,\"profile_id\":\"{}\",\"input_sha256\":\"{input_digest}\",\"reference_bits_sha256\":\"{reference_digest}\",\"result_sha256\":\"{result_digest}\",\"algorithm\":\"data_aided_fixed_training_receiver_delegated_ambiguity_v2\",\"contract\":\"{RECEIVER_DIAGNOSTIC_RUN_REQUEST_SCHEMA}\",\"target\":\"{TARGET}\"}}",
            request.profile_id()
        );
        let store = sipi_artifacts::ArtifactRoot::open_or_create(root).map_err(|_| ())?;
        let mut staging = store.begin(artifact_id).map_err(|_| ())?;
        staging
            .stage_reader("result.json", Cursor::new(result_json.into_bytes()), 16_384)
            .map_err(|_| ())?;
        staging
            .stage_reader(
                "provenance.json",
                Cursor::new(provenance.into_bytes()),
                16_384,
            )
            .map_err(|_| ())?;
        context.checkpoint().map_err(|_| ())?;
        let manifest = staging
            .seal()
            .and_then(|sealed| sealed.publish_new())
            .map_err(|_| ())?;
        Ok((result_digest, manifest))
    });
    match result {
        Ok((result_digest, manifest)) => success(format!(
            "{{\"schema\":\"sipi.receiver.diagnostic-run-result.v1\",\"artifact_id\":\"{}\",\"result_sha256\":\"{result_digest}\",\"mode\":\"product_owned_diagnostic\",\"clock_policy\":\"policy_selected_not_locked\",\"external_rfm\":false,\"acceptance\":false,\"manifest_schema\":\"{}\",\"file_count\":{}}}",
            manifest.artifact_id,
            manifest.schema,
            manifest.files.len()
        )),
        Err(_) => error(
            5,
            "operational_failure",
            "diagnostic receiver run did not publish an artifact",
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

fn run_matched_channel_kernel(text: &str) -> Response {
    const MAXIMUM_ONE_SIDED_SAMPLES: usize = 201;
    let limits = TouchstoneParseLimitsV1::new(
        NonZeroUsize::new(1_048_576).expect("nonzero input limit"),
        NonZeroUsize::new(65_536).expect("nonzero line limit"),
        NonZeroUsize::new(MAXIMUM_ONE_SIDED_SAMPLES).expect("nonzero record limit"),
    );
    let parsed = match parse_touchstone_hz_s_ri_50_two_port_v1(text.as_bytes(), limits) {
        Ok(parsed) => parsed,
        Err(_) => return error(3, "contract_rejected", "channel text was rejected"),
    };
    let spectrum = match admit_matched_two_port_spectrum_v1(&parsed) {
        Ok(spectrum) => spectrum,
        Err(_) => return error(3, "contract_rejected", "channel spectrum was rejected"),
    };
    let kernel = match resolve_matched_kernel_v1(
        &spectrum,
        ChannelLimitsV1::new(
            NonZeroUsize::new(MAXIMUM_ONE_SIDED_SAMPLES).expect("nonzero kernel limit"),
        ),
    ) {
        Ok(kernel) => kernel,
        Err(_) => return error(3, "contract_rejected", "channel kernel was rejected"),
    };
    let gain = kernel
        .gain()
        .iter()
        .map(|value| value.get().to_string())
        .collect::<Vec<_>>()
        .join(",");
    success(format!(
        "{{\"schema\":\"sipi.channel.matched-two-port-kernel-run-result.v1\",\"input_byte_length\":{},\"input_sha256\":\"{}\",\"one_sided_sample_count\":{},\"frequency_step_hz\":{},\"reference_impedance_ohms\":{},\"kernel_sample_count\":{},\"sample_interval_seconds\":{},\"gain_v_per_v\":[{gain}],\"evaluation_scope\":\"matched_s21_periodic_kernel_only\",\"external_profile_acceptance\":\"caller_input_unattested\"}}",
        text.len(),
        sha256_hex(text.as_bytes()),
        spectrum.sample_count(),
        spectrum.frequency_step().get(),
        spectrum.reference_impedance().get(),
        kernel.gain().len(),
        kernel.sample_interval().get(),
    ))
}

fn run_array_compare(request: &sipi_contracts::ArrayCompareRequestV1) -> Response {
    let reference = match compare_input_from_contract(request.reference()) {
        Ok(value) => value,
        Err(()) => return error(3, "contract_rejected", "reference array was rejected"),
    };
    let candidate = match compare_input_from_contract(request.candidate()) {
        Ok(value) => value,
        Err(()) => return error(3, "contract_rejected", "candidate array was rejected"),
    };
    let tolerance = match ToleranceV1::try_new(
        request.tolerance().absolute(),
        request.tolerance().relative(),
    ) {
        Ok(value) => value,
        Err(_) => return error(3, "contract_rejected", "comparison tolerance was rejected"),
    };
    let report = match compare_arrays_v1(Some(&reference), Some(&candidate), tolerance) {
        Ok(report) => report,
        Err(_) => return error(3, "contract_rejected", "aligned arrays were rejected"),
    };
    let shape = report
        .shape()
        .dimensions()
        .iter()
        .map(usize::to_string)
        .collect::<Vec<_>>()
        .join(",");
    let first_mismatch_index = report
        .first_mismatch_index()
        .map_or_else(|| "null".to_owned(), |index| index.to_string());
    success(format!(
        "{{\"schema\":\"sipi.compare.aligned-arrays-run-result.v1\",\"policy\":\"{}\",\"reference_digest\":\"{}\",\"candidate_digest\":\"{}\",\"shape\":[{shape}],\"unit\":\"{}\",\"semantic_binding_sha256\":\"{}\",\"passed\":{},\"mismatch_count\":{},\"max_absolute_error\":{},\"max_allowed_error\":{},\"first_mismatch_index\":{first_mismatch_index},\"evaluation_scope\":\"caller_aligned_arrays_only\",\"external_profile_acceptance\":\"not_evaluated\"}}",
        ARRAY_COMPARE_POLICY_V1,
        report.reference_digest(),
        report.candidate_digest(),
        report.unit().as_str(),
        report.semantic_binding().as_str(),
        report.passed(),
        report.mismatch_count(),
        report.max_absolute_error(),
        report.max_allowed_error(),
    ))
}

fn run_prbs9_metric_artifact_compare(
    artifact_root: &str,
    request: &sipi_contracts::Prbs9MetricArtifactsRequestV1,
) -> Response {
    let store = match ArtifactRoot::open_existing(Path::new(artifact_root)) {
        Ok(store) => store,
        Err(_) => {
            return error(
                3,
                "contract_rejected",
                "sealed artifact inputs were rejected",
            );
        }
    };
    let reference = match consume_prbs9_waveform_artifact(
        &store,
        request.reference().artifact_id(),
        request.reference().manifest_sha256(),
    ) {
        Ok(waveform) => waveform,
        Err(()) => {
            return error(
                3,
                "contract_rejected",
                "sealed artifact inputs were rejected",
            );
        }
    };
    let candidate = match consume_prbs9_waveform_artifact(
        &store,
        request.candidate().artifact_id(),
        request.candidate().manifest_sha256(),
    ) {
        Ok(waveform) => waveform,
        Err(()) => {
            return error(
                3,
                "contract_rejected",
                "sealed artifact inputs were rejected",
            );
        }
    };
    let pair = match Prbs9WaveformPairV2::try_new(reference.values, candidate.values) {
        Ok(pair) => pair,
        Err(_) => return error(3, "contract_rejected", "PRBS9 waveforms were rejected"),
    };
    let report = match compare_prbs9_metrics_v2(&pair) {
        Ok(report) => report,
        Err(_) => return error(3, "contract_rejected", "PRBS9 metrics were rejected"),
    };
    let reference_eye = report.reference_eye();
    let candidate_eye = report.candidate_eye();
    let reference_tie = report.reference_tie();
    let candidate_tie = report.candidate_tie();
    success(format!(
        "{{\"schema\":\"sipi.compare.prbs9-metric-artifacts-run-result.v1\",\"contract_sha256\":\"{}\",\"reference\":{{\"artifact_id\":\"{}\",\"manifest_sha256\":\"{}\",\"payload_sha256\":\"{}\",\"waveform_digest\":\"{}\"}},\"candidate\":{{\"artifact_id\":\"{}\",\"manifest_sha256\":\"{}\",\"payload_sha256\":\"{}\",\"waveform_digest\":\"{}\"}},\"compared_start\":{},\"compared_samples\":{},\"waveform_nrmse\":{},\"waveform_nrmse_limit\":{},\"within_waveform_nrmse_limit\":{},\"reference_eye\":{{\"height_volts\":{},\"width_seconds\":{}}},\"candidate_eye\":{{\"height_volts\":{},\"width_seconds\":{}}},\"eye_height_relative_error\":{},\"eye_width_relative_error\":{},\"within_eye_limits\":{},\"reference_tie\":{{\"raw_rms_seconds\":{},\"crossing_count\":{}}},\"candidate_tie\":{{\"raw_rms_seconds\":{},\"crossing_count\":{}}},\"paired_tie_rmse_seconds\":{},\"within_tie_limit\":{},\"within_metric_limits\":{},\"evaluation_scope\":\"caller_selected_sealed_artifacts_only\",\"external_reference_binding\":\"not_evaluated\",\"external_profile_acceptance\":\"not_evaluated\"}}",
        report.contract_sha256(),
        request.reference().artifact_id(),
        request.reference().manifest_sha256(),
        reference.payload_sha256,
        report.reference_digest(),
        request.candidate().artifact_id(),
        request.candidate().manifest_sha256(),
        candidate.payload_sha256,
        report.candidate_digest(),
        report.compared_start(),
        report.compared_samples(),
        report.waveform_nrmse(),
        report.waveform_nrmse_limit(),
        report.within_waveform_nrmse_limit(),
        reference_eye.height_volts(),
        reference_eye.width_seconds(),
        candidate_eye.height_volts(),
        candidate_eye.width_seconds(),
        report.eye_height_relative_error(),
        report.eye_width_relative_error(),
        report.within_eye_limits(),
        reference_tie.raw_rms_seconds(),
        reference_tie.crossing_count(),
        candidate_tie.raw_rms_seconds(),
        candidate_tie.crossing_count(),
        report.paired_tie_rmse_seconds(),
        report.within_tie_limit(),
        report.within_metric_limits(),
    ))
}

fn run_selected_highloss_prbs9_waveform_only_artifact_compare(
    artifact_root: &str,
    request: &sipi_contracts::SelectedHighlossPrbs9WaveformOnlyArtifactsRequestV3,
) -> Response {
    let store = match ArtifactRoot::open_existing(Path::new(artifact_root)) {
        Ok(store) => store,
        Err(_) => {
            return error(
                3,
                "contract_rejected",
                "sealed artifact inputs were rejected",
            );
        }
    };
    let reference = match consume_selected_highloss_prbs9_waveform_only_artifact(
        &store,
        request.reference().artifact_id(),
        request.reference().manifest_sha256(),
    ) {
        Ok(waveform) => waveform,
        Err(()) => {
            return error(
                3,
                "contract_rejected",
                "sealed artifact inputs were rejected",
            );
        }
    };
    let candidate = match consume_selected_highloss_prbs9_waveform_only_artifact(
        &store,
        request.candidate().artifact_id(),
        request.candidate().manifest_sha256(),
    ) {
        Ok(waveform) => waveform,
        Err(()) => {
            return error(
                3,
                "contract_rejected",
                "sealed artifact inputs were rejected",
            );
        }
    };
    let pair =
        match SelectedHighlossPrbs9WaveformPairV3::try_new(reference.values, candidate.values) {
            Ok(pair) => pair,
            Err(_) => return error(3, "contract_rejected", "selected waveforms were rejected"),
        };
    let report = match compare_selected_highloss_prbs9_waveform_only_v3(&pair) {
        Ok(report) => report,
        Err(_) => {
            return error(
                3,
                "contract_rejected",
                "selected waveform comparison was rejected",
            );
        }
    };
    success(format!(
        "{{\"schema\":\"sipi.compare.selected-highloss-prbs9-waveform-only-artifacts-run-result.v3\",\"contract_sha256\":\"{}\",\"reference\":{{\"artifact_id\":\"{}\",\"manifest_sha256\":\"{}\",\"payload_sha256\":\"{}\",\"waveform_digest\":\"{}\"}},\"candidate\":{{\"artifact_id\":\"{}\",\"manifest_sha256\":\"{}\",\"payload_sha256\":\"{}\",\"waveform_digest\":\"{}\"}},\"compared_start\":{},\"compared_samples\":{},\"waveform_nrmse\":{},\"waveform_nrmse_limit\":{},\"within_waveform_nrmse_limit\":{},\"within_selected_waveform_only_profile\":{},\"sampled_eye\":\"excluded_not_evaluated_for_this_selected_closed_eye_profile\",\"crossing_tie\":\"excluded_not_evaluated_for_this_selected_closed_eye_profile\",\"evaluation_scope\":\"selected_highloss_raw_post_channel_sealed_artifacts_only\",\"external_reference_binding\":\"not_evaluated\",\"external_profile_acceptance\":\"not_evaluated\"}}",
        report.contract_sha256(),
        request.reference().artifact_id(),
        request.reference().manifest_sha256(),
        reference.payload_sha256,
        report.reference_digest(),
        request.candidate().artifact_id(),
        request.candidate().manifest_sha256(),
        candidate.payload_sha256,
        report.candidate_digest(),
        report.compared_start(),
        report.compared_samples(),
        report.waveform_nrmse(),
        report.waveform_nrmse_limit(),
        report.within_waveform_nrmse_limit(),
        report.within_selected_waveform_only_profile(),
    ))
}

struct ConsumedPrbs9WaveformArtifact {
    values: Vec<f64>,
    payload_sha256: String,
}

fn consume_prbs9_waveform_artifact(
    store: &ArtifactRoot,
    artifact_id: &str,
    manifest_sha256: &str,
) -> Result<ConsumedPrbs9WaveformArtifact, ()> {
    let files = store
        .consume_exact_verified_v1(
            artifact_id,
            manifest_sha256,
            &[
                ("waveform.json", 4096),
                ("waveform.f64le", PRBS9_WAVEFORM_ARTIFACT_BYTE_LENGTH_V1),
            ],
            VerifiedConsumptionPolicyV1::try_new(65_536, 396_544).map_err(|_| ())?,
        )
        .map_err(|_| ())?;
    let metadata =
        parse_prbs9_waveform_artifact_v1(files.file("waveform.json").ok_or(())?).map_err(|_| ())?;
    let payload = files.file("waveform.f64le").ok_or(())?;
    if payload.len() as u64 != PRBS9_WAVEFORM_ARTIFACT_BYTE_LENGTH_V1
        || metadata.payload_sha256() != sha256_hex(payload)
    {
        return Err(());
    }
    let mut values = Vec::with_capacity(payload.len() / 8);
    let chunks = payload.chunks_exact(8);
    if !chunks.remainder().is_empty() {
        return Err(());
    }
    for bytes in chunks {
        let array: [u8; 8] = bytes.try_into().map_err(|_| ())?;
        let value = f64::from_le_bytes(array);
        if !value.is_finite() {
            return Err(());
        }
        values.push(value);
    }
    Ok(ConsumedPrbs9WaveformArtifact {
        values,
        payload_sha256: metadata.payload_sha256().to_owned(),
    })
}

fn consume_selected_highloss_prbs9_waveform_only_artifact(
    store: &ArtifactRoot,
    artifact_id: &str,
    manifest_sha256: &str,
) -> Result<ConsumedPrbs9WaveformArtifact, ()> {
    let files = store
        .consume_exact_verified_v1(
            artifact_id,
            manifest_sha256,
            &[
                ("waveform.json", 4096),
                (
                    "waveform.f64le",
                    SELECTED_HIGHLOSS_PRBS9_WAVEFORM_ONLY_BYTE_LENGTH_V3,
                ),
            ],
            VerifiedConsumptionPolicyV1::try_new(65_536, 396_544).map_err(|_| ())?,
        )
        .map_err(|_| ())?;
    let metadata = parse_selected_highloss_prbs9_waveform_only_artifact_v3(
        files.file("waveform.json").ok_or(())?,
    )
    .map_err(|_| ())?;
    let payload = files.file("waveform.f64le").ok_or(())?;
    if payload.len() as u64 != SELECTED_HIGHLOSS_PRBS9_WAVEFORM_ONLY_BYTE_LENGTH_V3
        || metadata.payload_sha256() != sha256_hex(payload)
    {
        return Err(());
    }
    let mut values = Vec::with_capacity(payload.len() / 8);
    let chunks = payload.chunks_exact(8);
    if !chunks.remainder().is_empty() {
        return Err(());
    }
    for bytes in chunks {
        let array: [u8; 8] = bytes.try_into().map_err(|_| ())?;
        let value = f64::from_le_bytes(array);
        if !value.is_finite() {
            return Err(());
        }
        values.push(value);
    }
    Ok(ConsumedPrbs9WaveformArtifact {
        values,
        payload_sha256: metadata.payload_sha256().to_owned(),
    })
}

fn compare_input_from_contract(
    input: &sipi_contracts::AlignedArrayCompareInputV1,
) -> Result<AlignedArrayV1, ()> {
    let shape = ArrayShapeV1::try_new(input.shape().to_vec()).map_err(|_| ())?;
    let unit = UnitTagV1::try_new(input.unit()).map_err(|_| ())?;
    let binding =
        SemanticBindingDigestV1::try_new(input.semantic_binding_sha256()).map_err(|_| ())?;
    AlignedArrayV1::try_new(shape, unit, binding, input.values().to_vec()).map_err(|_| ())
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

fn run_ibis_quasi_static_evaluate(
    request: &sipi_contracts::IbisQuasiStaticEvaluateRequestV1,
) -> Response {
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
    let state = match QuasiStaticClampStateV1::try_new(
        request.gnd_clamp_drive_volts(),
        request.power_clamp_drive_volts(),
        request.sig_to_ref_slope_volts_per_second(),
    ) {
        Ok(state) => state,
        Err(_) => {
            return error(
                3,
                "contract_rejected",
                "IBIS quasi-static state was rejected",
            );
        }
    };
    match IbisQuasiStaticEvaluateServiceV1::evaluate(request.text(), &profile, state, limits) {
        Ok(report) => success(format!(
            "{{\"schema\":\"sipi.ibis.input-typ-quasi-static-evaluate.response.v1\",\"input_byte_length\":{},\"input_sha256\":\"{}\",\"selection\":{{\"ibis_version\":\"{}\",\"model_selector\":\"{}\",\"corner\":\"typical\"}},\"gnd_clamp_current_amps\":{},\"power_clamp_current_amps\":{},\"c_comp_current_amps\":{},\"total_shunt_current_amps\":{},\"evaluation_scope\":\"input_typical_quasi_static_constitutive\",\"external_profile_acceptance\":\"not_evaluated\",\"capability_matrix_id\":\"sipi.p4a-ibis-conformance-matrix.v1\"}}",
            report.input_byte_length(),
            report.input_sha256(),
            report.ibis_version(),
            report.model_selector(),
            report.gnd_current().get(),
            report.power_current().get(),
            report.c_comp_current().get(),
            report.total_shunt_current().get(),
        )),
        Err(_) => error(
            3,
            "contract_rejected",
            "IBIS quasi-static evaluation was rejected",
        ),
    }
}

fn run_ibis_quasi_static_artifact_evaluate(
    artifact_root: &str,
    request: &sipi_contracts::IbisQuasiStaticArtifactEvaluateRequestV1,
) -> Response {
    const MAXIMUM_IBIS_BYTES: u64 = 1_048_576;
    let store = match ArtifactRoot::open_existing(Path::new(artifact_root)) {
        Ok(store) => store,
        Err(_) => {
            return error(3, "contract_rejected", "sealed IBIS artifact was rejected");
        }
    };
    let files = match store.consume_exact_verified_v1(
        request.artifact().artifact_id(),
        request.artifact().manifest_sha256(),
        &[("model.ibs", MAXIMUM_IBIS_BYTES)],
        match VerifiedConsumptionPolicyV1::try_new(65_536, MAXIMUM_IBIS_BYTES) {
            Ok(policy) => policy,
            Err(_) => {
                return error(
                    6,
                    "internal_contract_error",
                    "sealed IBIS artifact policy is unavailable",
                );
            }
        },
    ) {
        Ok(files) => files,
        Err(_) => {
            return error(3, "contract_rejected", "sealed IBIS artifact was rejected");
        }
    };
    let bytes = match files.file("model.ibs") {
        Some(bytes) => bytes,
        None => {
            return error(3, "contract_rejected", "sealed IBIS artifact was rejected");
        }
    };
    let text = match std::str::from_utf8(bytes) {
        Ok(text) => text,
        Err(_) => {
            return error(3, "contract_rejected", "sealed IBIS artifact was rejected");
        }
    };
    let limits = match ParseLimitsV1::try_new(MAXIMUM_IBIS_BYTES as usize, 65_536, 16_384, 16_384) {
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
    let state = match QuasiStaticClampStateV1::try_new(
        request.gnd_clamp_drive_volts(),
        request.power_clamp_drive_volts(),
        request.sig_to_ref_slope_volts_per_second(),
    ) {
        Ok(state) => state,
        Err(_) => {
            return error(
                3,
                "contract_rejected",
                "IBIS quasi-static state was rejected",
            );
        }
    };
    match IbisQuasiStaticEvaluateServiceV1::evaluate(text, &profile, state, limits) {
        Ok(report) => success(format!(
            "{{\"schema\":\"sipi.ibis.input-typ-quasi-static-artifact-evaluate.response.v1\",\"artifact\":{{\"artifact_id\":\"{}\",\"manifest_sha256\":\"{}\",\"payload_sha256\":\"{}\",\"payload_byte_length\":{}}},\"selection\":{{\"ibis_version\":\"{}\",\"model_selector\":\"{}\",\"corner\":\"typical\"}},\"gnd_clamp_current_amps\":{},\"power_clamp_current_amps\":{},\"c_comp_current_amps\":{},\"total_shunt_current_amps\":{},\"evaluation_scope\":\"input_typical_quasi_static_constitutive_sealed_caller_artifact\",\"artifact_custody\":\"caller_asset_identity_verified\",\"artifact_root_threat_model\":\"caller_selected_sipi_published_root_no_hostile_concurrent_writer\",\"external_profile_acceptance\":\"not_evaluated\",\"capability_matrix_id\":\"sipi.p4a-ibis-conformance-matrix.v1\"}}",
            request.artifact().artifact_id(),
            request.artifact().manifest_sha256(),
            sha256_hex(bytes),
            bytes.len(),
            report.ibis_version(),
            report.model_selector(),
            report.gnd_current().get(),
            report.power_current().get(),
            report.c_comp_current().get(),
            report.total_shunt_current().get(),
        )),
        Err(_) => error(
            3,
            "contract_rejected",
            "IBIS quasi-static evaluation was rejected",
        ),
    }
}

fn run_ibis_quasi_static_artifact_batch_evaluate(
    artifact_root: &str,
    request: &sipi_contracts::IbisQuasiStaticArtifactBatchEvaluateRequestV1,
) -> Response {
    const MAXIMUM_IBIS_BYTES: u64 = 1_048_576;
    let states = match request
        .probes()
        .iter()
        .map(|probe| {
            QuasiStaticClampStateV1::try_new(
                probe.gnd_clamp_drive_volts(),
                probe.power_clamp_drive_volts(),
                probe.sig_to_ref_slope_volts_per_second(),
            )
        })
        .collect::<Result<Vec<_>, _>>()
    {
        Ok(states) => states,
        Err(_) => {
            return error(
                3,
                "contract_rejected",
                "IBIS quasi-static batch state was rejected",
            );
        }
    };
    let store = match ArtifactRoot::open_existing(Path::new(artifact_root)) {
        Ok(store) => store,
        Err(_) => {
            return error(3, "contract_rejected", "sealed IBIS artifact was rejected");
        }
    };
    let files = match store.consume_exact_verified_v1(
        request.artifact().artifact_id(),
        request.artifact().manifest_sha256(),
        &[("model.ibs", MAXIMUM_IBIS_BYTES)],
        match VerifiedConsumptionPolicyV1::try_new(65_536, MAXIMUM_IBIS_BYTES) {
            Ok(policy) => policy,
            Err(_) => {
                return error(
                    6,
                    "internal_contract_error",
                    "sealed IBIS artifact policy is unavailable",
                );
            }
        },
    ) {
        Ok(files) => files,
        Err(_) => {
            return error(3, "contract_rejected", "sealed IBIS artifact was rejected");
        }
    };
    let bytes = match files.file("model.ibs") {
        Some(bytes) => bytes,
        None => {
            return error(3, "contract_rejected", "sealed IBIS artifact was rejected");
        }
    };
    let text = match std::str::from_utf8(bytes) {
        Ok(text) => text,
        Err(_) => {
            return error(3, "contract_rejected", "sealed IBIS artifact was rejected");
        }
    };
    let limits = match ParseLimitsV1::try_new(MAXIMUM_IBIS_BYTES as usize, 65_536, 16_384, 16_384) {
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
    match IbisQuasiStaticBatchEvaluateServiceV1::evaluate(text, &profile, &states, limits) {
        Ok(report) => {
            let probes = report
                .probes()
                .iter()
                .map(|probe| {
                    format!(
                        "{{\"gnd_clamp_current_amps\":{},\"power_clamp_current_amps\":{},\"c_comp_current_amps\":{},\"total_shunt_current_amps\":{}}}",
                        probe.gnd_current().get(),
                        probe.power_current().get(),
                        probe.c_comp_current().get(),
                        probe.total_shunt_current().get(),
                    )
                })
                .collect::<Vec<_>>()
                .join(",");
            success(format!(
                "{{\"schema\":\"sipi.ibis.input-typ-quasi-static-artifact-batch-evaluate.response.v1\",\"artifact\":{{\"artifact_id\":\"{}\",\"manifest_sha256\":\"{}\",\"payload_sha256\":\"{}\",\"payload_byte_length\":{}}},\"selection\":{{\"ibis_version\":\"{}\",\"model_selector\":\"{}\",\"corner\":\"typical\"}},\"probe_count\":{},\"probes\":[{}],\"evaluation_scope\":\"input_typical_quasi_static_constitutive_sealed_caller_artifact_bounded_batch\",\"artifact_custody\":\"caller_asset_identity_verified\",\"artifact_root_threat_model\":\"caller_selected_sipi_published_root_no_hostile_concurrent_writer\",\"external_profile_acceptance\":\"not_evaluated\",\"capability_matrix_id\":\"sipi.p4a-ibis-conformance-matrix.v1\"}}",
                request.artifact().artifact_id(),
                request.artifact().manifest_sha256(),
                sha256_hex(bytes),
                bytes.len(),
                report.ibis_version(),
                report.model_selector(),
                report.probes().len(),
                probes,
            ))
        }
        Err(_) => error(
            3,
            "contract_rejected",
            "IBIS quasi-static batch evaluation was rejected",
        ),
    }
}

fn run_rx_load_differential_rc_evaluate(
    request: &sipi_contracts::RxLoadDifferentialRcEvaluateRequestV1,
) -> Response {
    let probe = match DifferentialRcLoadProbeV1::try_new(
        request.p_to_ref_volts().get(),
        request.n_to_ref_volts().get(),
        request.p_to_ref_slope_volts_per_second(),
        request.n_to_ref_slope_volts_per_second(),
    ) {
        Ok(probe) => probe,
        Err(_) => {
            return error(
                3,
                "contract_rejected",
                "selected differential R-C load probe was rejected",
            );
        }
    };
    match evaluate_selected_differential_rc_load_v1(probe) {
        Ok(currents) => success(format!(
            "{{\"schema\":\"sipi.rx-load.selected-differential-rc-evaluate.response.v1\",\"topology\":{{\"id\":\"selected-differential-rc-100ohm-1pf-to-ref-v1\",\"reference_terminal\":\"ref\",\"differential_resistance_ohms\":{},\"p_to_ref_capacitance_farads\":{},\"n_to_ref_capacitance_farads\":{}}},\"current_sign\":\"positive_into_load_terminal\",\"resistor_p_to_n_current_amps\":{},\"p_capacitor_to_ref_current_amps\":{},\"n_capacitor_to_ref_current_amps\":{},\"p_terminal_current_amps\":{},\"n_terminal_current_amps\":{},\"ref_terminal_current_amps\":{},\"evaluation_scope\":\"selected_continuous_constitutive_relation\",\"external_profile_acceptance\":\"not_evaluated\",\"capability_matrix_id\":\"sipi.p4a-ibis-conformance-matrix.v1\"}}",
            DIFFERENTIAL_RESISTANCE_OHMS,
            LEG_CAPACITANCE_FARADS,
            LEG_CAPACITANCE_FARADS,
            currents.resistor_p_to_n().get(),
            currents.p_capacitor_to_ref().get(),
            currents.n_capacitor_to_ref().get(),
            currents.p_terminal().get(),
            currents.n_terminal().get(),
            currents.ref_terminal().get(),
        )),
        Err(_) => error(
            3,
            "contract_rejected",
            "selected differential R-C load evaluation was rejected",
        ),
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

fn one_node_result_json(
    result: &sipi_tran::RcPulseTransientResultV1,
) -> Result<String, &'static str> {
    let AxisView::Explicit(times) = result.time_axis().view() else {
        return Err("one-node result must have an explicit time axis");
    };
    Ok(format!(
        "{{\"schema\":\"sipi.tran.one-node-rc-pulse-result.v1\",\"topology\":\"ideal_pulse_series_r_capacitor_to_explicit_ref\",\"time_seconds\":{},\"voltage_in_volts\":{},\"voltage_out_volts\":{}}}",
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

fn one_node_pwl_result_json(
    result: &sipi_tran::RcPulseTransientResultV1,
) -> Result<String, &'static str> {
    let AxisView::Explicit(times) = result.time_axis().view() else {
        return Err("one-node PWL result must have an explicit time axis");
    };
    Ok(format!(
        "{{\"schema\":\"sipi.tran.one-node-rc-pwl-result.v1\",\"topology\":\"piecewise_linear_voltage_source_series_r_capacitor_to_explicit_ref\",\"time_seconds\":{},\"voltage_in_volts\":{},\"voltage_out_volts\":{}}}",
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

fn diagnostic_receiver_result_json(
    profile_id: &str,
    result: &sipi_link::ReceiverResultV1,
) -> Result<String, &'static str> {
    let phase_selection = match result.phase_selection() {
        ReceiverPhaseSelectionV2::UniqueLocked => "unique_phase",
        ReceiverPhaseSelectionV2::DelegatedAmbiguousTieBreak => "delegated_ambiguous_tie_break",
    };
    let decision_digest = receiver_decision_digest(result.decisions());
    Ok(format!(
        "{{\"schema\":\"sipi.receiver.diagnostic-result.v1\",\"mode\":\"product_owned_diagnostic\",\"clock_policy\":\"policy_selected_not_locked\",\"external_rfm\":false,\"acceptance\":false,\"profile_id\":\"{profile_id}\",\"phase\":{},\"phase_selection\":\"{phase_selection}\",\"phase_score\":{},\"phase_margin\":{},\"center_volts\":{},\"amplitude_volts\":{},\"frozen_taps\":{},\"error_count\":{},\"ber_denominator\":{},\"ber\":{},\"decision_sha256\":\"{decision_digest}\"}}",
        result.phase(),
        result.phase_score().get(),
        result.phase_margin().get(),
        result.center().get(),
        result.amplitude().get(),
        json_values(result.frozen_taps().iter().map(|tap| tap.get())),
        result.error_count(),
        result.ber_denominator(),
        result.ber(),
    ))
}

fn receiver_decision_digest(decisions: &[sipi_link::ReceiverDecisionV1]) -> String {
    let mut encoded = Vec::with_capacity(decisions.len());
    for decision in decisions {
        encoded.push(match decision {
            sipi_link::ReceiverDecisionV1::Positive => b'P',
            sipi_link::ReceiverDecisionV1::Negative => b'N',
            sipi_link::ReceiverDecisionV1::Erasure => b'E',
        });
    }
    sha256_hex(&encoded)
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
                    && token.bytes().all(|byte| {
                        byte.is_ascii_lowercase() || byte.is_ascii_digit() || byte == b'-'
                    })
            })
            && matches!(
                descriptor.transport,
                "none" | "stdin_json_v1" | "external_migration_adapter" | "argv_r480_v1"
            )
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
                && if is_stdin_transport(descriptor.transport) {
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
    let standard_handler = matches!(
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
            | ["ibis", "quasi-static-evaluate"]
            | ["ibis", "quasi-static-evaluate-artifact-batch"]
            | ["ibis", "quasi-static-evaluate-artifact"]
            | ["rx-load", "differential-rc-evaluate"]
            | ["tran", "run"]
            | ["tran", "one-node-rc-pulse"]
            | ["tran", "one-node-rc-pwl"]
            | ["link", "run"]
            | ["link", "receiver", "run"]
            | ["channel", "run"]
            | ["compare", "run"]
            | ["compare", "prbs9-metrics"]
            | ["compare", "prbs9-waveform-only"]
            | ["project", "run"]
            | ["report", "inspect"]
            | ["com", "run-artifact"]
            | ["upstream", "agent-spice", "fit-sparam"]
            | ["upstream", "agent-spice", "fit-sparam-cascade"]
            | ["upstream", "agent-spice", "fit-yparam"]
            | ["upstream", "agent-spice", "tune-yparam-tran"]
            | ["upstream", "agent-spice", "run-hspice"]
            | ["upstream", "agent-spice", "run-rfm"]
            | ["upstream", "pybert", "sim"]
            | ["upstream", "pybert", "sim-native"]
            | ["upstream", "pybert", "sim-rust"]
            | ["upstream", "pybert", "sim-auto"]
            | ["upstream", "pybert", "sim-compare"]
            | ["upstream", "agent-com", "config-validate"]
            | ["upstream", "agent-com", "run"]
            | ["upstream", "agent-com", "compare"]
            | ["upstream", "agent-com", "public-api"]
    );
    #[cfg(feature = "com-direct-integration")]
    {
        standard_handler || matches!(route, ["com", "run"])
    }
    #[cfg(not(feature = "com-direct-integration"))]
    {
        standard_handler
    }
}

fn is_stdin_transport(transport: &str) -> bool {
    matches!(transport, "stdin_json_v1" | "external_migration_adapter")
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
    if id == UPSTREAM_MIGRATION_REQUEST_SCHEMA {
        Ok(Some(
            upstream_migration::REQUEST_SCHEMA_JSON.as_bytes().to_vec(),
        ))
    } else if id == CAPABILITIES_SCHEMA {
        capability_schema_json().map(Some)
    } else if id == sipi_contracts::VALIDATION_REQUEST_SCHEMA {
        validation_request_schema_json().map(Some)
    } else if id == sipi_contracts::TRAN_RC_PULSE_REQUEST_SCHEMA {
        tran_rc_pulse_request_schema_json().map(Some)
    } else if id == TRAN_ONE_NODE_RC_PULSE_REQUEST_SCHEMA {
        tran_one_node_rc_pulse_request_schema_json().map(Some)
    } else if id == TRAN_ONE_NODE_RC_PWL_REQUEST_SCHEMA {
        tran_one_node_rc_pwl_request_schema_json().map(Some)
    } else if id == LINK_PLAN_SCHEMA {
        link_plan_schema_json().map(Some)
    } else if id == sipi_contracts::LINK_CAUSAL_FIR_REQUEST_SCHEMA {
        link_causal_fir_request_schema_json().map(Some)
    } else if id == CHANNEL_MATCHED_TWO_PORT_KERNEL_RUN_REQUEST_SCHEMA {
        channel_matched_two_port_kernel_run_request_schema_json().map(Some)
    } else if id == ARRAY_COMPARE_REQUEST_SCHEMA {
        array_compare_request_schema_json().map(Some)
    } else if id == PRBS9_METRIC_ARTIFACTS_REQUEST_SCHEMA {
        prbs9_metric_artifacts_request_schema_json().map(Some)
    } else if id == SELECTED_HIGHLOSS_PRBS9_WAVEFORM_ONLY_ARTIFACTS_REQUEST_SCHEMA_V3 {
        selected_highloss_prbs9_waveform_only_artifacts_request_schema_json().map(Some)
    } else if id == sipi_contracts::IBIS_INSPECT_REQUEST_SCHEMA {
        ibis_inspect_request_schema_json().map(Some)
    } else if id == IBIS_DC_EVALUATE_REQUEST_SCHEMA {
        ibis_dc_evaluate_request_schema_json().map(Some)
    } else if id == IBIS_QUASI_STATIC_EVALUATE_REQUEST_SCHEMA {
        ibis_quasi_static_evaluate_request_schema_json().map(Some)
    } else if id == IBIS_QUASI_STATIC_ARTIFACT_BATCH_EVALUATE_REQUEST_SCHEMA {
        ibis_quasi_static_artifact_batch_evaluate_request_schema_json().map(Some)
    } else if id == IBIS_QUASI_STATIC_ARTIFACT_EVALUATE_REQUEST_SCHEMA {
        ibis_quasi_static_artifact_evaluate_request_schema_json().map(Some)
    } else if id == sipi_contracts::RX_LOAD_DIFFERENTIAL_RC_EVALUATE_REQUEST_SCHEMA {
        rx_load_differential_rc_evaluate_request_schema_json().map(Some)
    } else if id == ARTIFACT_REPORT_REQUEST_SCHEMA {
        artifact_report_request_schema_json().map(Some)
    } else if id == sipi_contracts::PROJECT_PLAN_SCHEMA {
        project_plan_schema_json().map(Some)
    } else if id == FIXED_PROJECT_RUN_REQUEST_SCHEMA {
        fixed_project_run_request_schema_json().map(Some)
    } else if id == COM_RUN_ARTIFACT_REQUEST_SCHEMA {
        com_run_artifact_request_schema_json().map(Some)
    } else if id == sipi_contracts::RECEIVER_INPUT_SCHEMA {
        receiver_input_schema_json().map(Some)
    } else if id == RECEIVER_DIAGNOSTIC_RUN_REQUEST_SCHEMA {
        receiver_diagnostic_run_request_schema_json().map(Some)
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
                if is_stdin_transport(descriptor.transport) {
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
            #[cfg(feature = "com-direct-integration")]
            [command, action, tail @ ..] if command == "com" && action == "run" => {
                match com_direct_cli_contract_v1::execute_com_r480_argv_v1(tail) {
                    Ok(receipt) => success(receipt),
                    Err(error_value) => error(
                        error_value.exit_code(),
                        error_value.diagnostic_code(),
                        "bounded COM argv route failed",
                    ),
                }
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
            [command, ..] if command == "channel" => error(
                4,
                "unsupported",
                "Channel requires the exact run --stdin command",
            ),
            [command, ..] if command == "compare" => error(
                4,
                "unsupported",
                "compare requires the exact run --stdin command",
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
            [command, ..] if command == "upstream" => error(
                64,
                "usage",
                "upstream requires one named migration workflow with --stdin",
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
                "{\"domain\":\"tran\",\"status\":\"limited\",\"reason\":\"fixed_rc_pulse_and_bounded_one_node_rc_sources_only\"}".to_owned()
            } else if *domain == "channel" && manifest_available("channel.run") {
                "{\"domain\":\"channel\",\"status\":\"limited\",\"reason\":\"matched_s21_periodic_kernel_only\"}".to_owned()
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
    let schemas = [
        UPSTREAM_MIGRATION_REQUEST_SCHEMA,
        CAPABILITIES_SCHEMA,
        ARTIFACT_REPORT_REQUEST_SCHEMA,
        CHANNEL_MATCHED_TWO_PORT_KERNEL_RUN_REQUEST_SCHEMA,
        ARRAY_COMPARE_REQUEST_SCHEMA,
        PRBS9_METRIC_ARTIFACTS_REQUEST_SCHEMA,
        SELECTED_HIGHLOSS_PRBS9_WAVEFORM_ONLY_ARTIFACTS_REQUEST_SCHEMA_V3,
        IBIS_DC_EVALUATE_REQUEST_SCHEMA,
        IBIS_QUASI_STATIC_ARTIFACT_BATCH_EVALUATE_REQUEST_SCHEMA,
        IBIS_QUASI_STATIC_ARTIFACT_EVALUATE_REQUEST_SCHEMA,
        IBIS_QUASI_STATIC_EVALUATE_REQUEST_SCHEMA,
        sipi_contracts::IBIS_INSPECT_REQUEST_SCHEMA,
        LINK_PLAN_SCHEMA,
        sipi_contracts::LINK_CAUSAL_FIR_REQUEST_SCHEMA,
        FIXED_PROJECT_RUN_REQUEST_SCHEMA,
        sipi_contracts::PROJECT_PLAN_SCHEMA,
        sipi_contracts::RECEIVER_INPUT_SCHEMA,
        sipi_contracts::RECEIVER_SEMANTICS_SCHEMA,
        RECEIVER_DIAGNOSTIC_RUN_REQUEST_SCHEMA,
        sipi_contracts::RX_LOAD_DIFFERENTIAL_RC_EVALUATE_REQUEST_SCHEMA,
        TRAN_ONE_NODE_RC_PULSE_REQUEST_SCHEMA,
        sipi_contracts::TRAN_RC_PULSE_REQUEST_SCHEMA,
        sipi_contracts::VALIDATION_REQUEST_SCHEMA,
        COM_RUN_ARTIFACT_REQUEST_SCHEMA,
    ]
    .into_iter()
    .map(|schema| format!("\"{schema}\""))
    .collect::<Vec<_>>()
    .join(",");
    format!("{{\"schema\":\"sipi.cli-schema-list.v1\",\"schemas\":[{schemas}]}}")
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
        id != UPSTREAM_MIGRATION_REQUEST_SCHEMA
            && id != CAPABILITIES_SCHEMA
            && id != ARTIFACT_REPORT_REQUEST_SCHEMA
            && id != CHANNEL_MATCHED_TWO_PORT_KERNEL_RUN_REQUEST_SCHEMA
            && id != ARRAY_COMPARE_REQUEST_SCHEMA
            && id != PRBS9_METRIC_ARTIFACTS_REQUEST_SCHEMA
            && id != SELECTED_HIGHLOSS_PRBS9_WAVEFORM_ONLY_ARTIFACTS_REQUEST_SCHEMA_V3
            && id != sipi_contracts::VALIDATION_REQUEST_SCHEMA
            && id != sipi_contracts::TRAN_RC_PULSE_REQUEST_SCHEMA
            && id != TRAN_ONE_NODE_RC_PULSE_REQUEST_SCHEMA
            && id != sipi_contracts::IBIS_INSPECT_REQUEST_SCHEMA
            && id != IBIS_DC_EVALUATE_REQUEST_SCHEMA
            && id != IBIS_QUASI_STATIC_EVALUATE_REQUEST_SCHEMA
            && id != IBIS_QUASI_STATIC_ARTIFACT_BATCH_EVALUATE_REQUEST_SCHEMA
            && id != IBIS_QUASI_STATIC_ARTIFACT_EVALUATE_REQUEST_SCHEMA
            && id != sipi_contracts::RX_LOAD_DIFFERENTIAL_RC_EVALUATE_REQUEST_SCHEMA
            && id != LINK_PLAN_SCHEMA
            && id != sipi_contracts::LINK_CAUSAL_FIR_REQUEST_SCHEMA
            && id != sipi_contracts::PROJECT_PLAN_SCHEMA
            && id != FIXED_PROJECT_RUN_REQUEST_SCHEMA
            && id != COM_RUN_ARTIFACT_REQUEST_SCHEMA
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
        && schema_bytes(UPSTREAM_MIGRATION_REQUEST_SCHEMA)
            .ok()
            .flatten()
            .is_some()
        && validation_request_schema_json().is_ok()
        && artifact_report_request_schema_json().is_ok()
        && channel_matched_two_port_kernel_run_request_schema_json().is_ok()
        && array_compare_request_schema_json().is_ok()
        && prbs9_metric_artifacts_request_schema_json().is_ok()
        && tran_rc_pulse_request_schema_json().is_ok()
        && tran_one_node_rc_pulse_request_schema_json().is_ok()
        && ibis_inspect_request_schema_json().is_ok()
        && ibis_dc_evaluate_request_schema_json().is_ok()
        && ibis_quasi_static_evaluate_request_schema_json().is_ok()
        && ibis_quasi_static_artifact_batch_evaluate_request_schema_json().is_ok()
        && ibis_quasi_static_artifact_evaluate_request_schema_json().is_ok()
        && rx_load_differential_rc_evaluate_request_schema_json().is_ok()
        && link_plan_schema_json().is_ok()
        && link_causal_fir_request_schema_json().is_ok()
        && project_plan_schema_json().is_ok()
        && fixed_project_run_request_schema_json().is_ok()
        && com_run_artifact_request_schema_json().is_ok()
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
    use std::{
        fs,
        sync::atomic::{AtomicUsize, Ordering},
    };

    static TEST_NONCE: AtomicUsize = AtomicUsize::new(0);

    fn args(values: &[&str]) -> Vec<String> {
        values.iter().map(|value| (*value).to_owned()).collect()
    }

    fn rc_pulse_request() -> &'static [u8] {
        br#"{"schema":"sipi.tran.rc-pulse-request.v1","request_id":"rc-pulse-1","resistance_ohms":1000.0,"capacitance_farads":0.000001,"initial_voltage_out_volts":0.0,"output_times_seconds":[0.0,0.000001,0.000002,0.000003],"pulse":{"voltage_low_volts":0.0,"voltage_high_volts":1.0,"delay_seconds":0.000001,"rise_seconds":0.000000001,"fall_seconds":0.000000001,"width_seconds":0.00001,"period_seconds":0.00002}}"#
    }

    #[test]
    fn capability_inventory_exposes_the_bounded_matched_channel_kernel() {
        let response = dispatch(&args(&["capabilities", "--json"]));

        assert_eq!(response.code, 0);
        assert_eq!(response.stderr, None);
        assert_eq!(
            response.stdout.as_deref(),
            Some(
                "{\"schema\":\"sipi.capabilities.v1\",\"product\":{\"name\":\"sipi\",\"version\":\"0.1.0\"},\"platform\":{\"target\":\"x86_64-pc-windows-msvc\",\"certification\":\"uncertified\"},\"capabilities\":[{\"domain\":\"tran\",\"status\":\"limited\",\"reason\":\"fixed_rc_pulse_and_bounded_one_node_rc_sources_only\"},{\"domain\":\"channel\",\"status\":\"limited\",\"reason\":\"matched_s21_periodic_kernel_only\"},{\"domain\":\"ibis-ami\",\"status\":\"unsupported\",\"reason\":\"not_implemented\"},{\"domain\":\"com\",\"status\":\"unsupported\",\"reason\":\"not_implemented\"}]}"
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

        #[cfg(feature = "com-direct-integration")]
        let unavailable = vec![
            ["ami", "run"].as_slice(),
            ["project", "validate"].as_slice(),
            ["report", "show"].as_slice(),
        ];
        #[cfg(not(feature = "com-direct-integration"))]
        let unavailable = vec![
            ["ami", "run"].as_slice(),
            ["com", "run"].as_slice(),
            ["project", "validate"].as_slice(),
            ["report", "show"].as_slice(),
        ];
        for command in unavailable {
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
            "ibis.quasi-static-evaluate",
            "rx-load.differential-rc-evaluate",
            "channel.run",
            "compare.run",
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

        let channel = product_example_request_json_v1("channel.run")
            .expect("channel example")
            .expect("registered channel example");
        assert!(parse_channel_matched_two_port_kernel_run_request_v1(&channel).is_ok());

        let ibis_dc = product_example_request_json_v1("ibis.dc-evaluate")
            .expect("IBIS DC example")
            .expect("registered IBIS DC example");
        assert!(parse_ibis_dc_evaluate_request_v1(&ibis_dc).is_ok());

        let ibis_quasi_static = product_example_request_json_v1("ibis.quasi-static-evaluate")
            .expect("IBIS quasi-static example")
            .expect("registered IBIS quasi-static example");
        assert!(parse_ibis_quasi_static_evaluate_request_v1(&ibis_quasi_static).is_ok());

        let rx_load = product_example_request_json_v1("rx-load.differential-rc-evaluate")
            .expect("RX load example")
            .expect("registered RX load example");
        assert!(parse_rx_load_differential_rc_evaluate_request_v1(&rx_load).is_ok());

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
    }

    #[test]
    fn channel_kernel_route_is_bounded_and_does_not_claim_link_acceptance() {
        let response = run_matched_channel_kernel(
            "# Hz S RI R 50.0\n0 0 0 1 0 0 0 0 0\n1000000 0 0 1 0 0 0 0 0\n",
        );
        assert_eq!(response.code, 0);
        let body = response.stdout.expect("channel response");
        assert!(body.contains("sipi.channel.matched-two-port-kernel-run-result.v1"));
        assert!(body.contains("\"gain_v_per_v\":[1,0]"));
        assert!(body.contains("\"evaluation_scope\":\"matched_s21_periodic_kernel_only\""));
        assert!(body.contains("\"external_profile_acceptance\":\"caller_input_unattested\""));
        assert_eq!(
            run_matched_channel_kernel("# Hz S MA R 50.0\n0 0 0 1 0 0 0 0 0\n").code,
            3
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
    fn specified_com_artifact_route_is_explicit_and_com_route_matches_the_feature_gate() {
        let manifest = command_manifest_json();
        assert!(manifest.contains("\"id\":\"com.run-artifact\""));
        assert!(manifest.contains("product_owned_bounded_artifact_execution_non_oracle_only"));
        #[cfg(feature = "com-direct-integration")]
        assert!(manifest.contains(
            "\"id\":\"com.run\",\"route\":[\"com\",\"run\"],\"availability\":\"available\""
        ));
        #[cfg(not(feature = "com-direct-integration"))]
        assert!(!manifest.contains(
            "\"id\":\"com.run\",\"route\":[\"com\",\"run\"],\"availability\":\"available\""
        ));
        let catalog = command_protocol_catalog_json().expect("catalog");
        assert!(catalog.contains("\"command_id\":\"com.run-artifact\""));
        assert!(
            catalog.contains("\"validation_rule_id\":\"com.run-artifact.specified-non-oracle.v1\"")
        );
        assert!(
            schema_bytes(COM_RUN_ARTIFACT_REQUEST_SCHEMA)
                .unwrap()
                .is_some()
        );
        #[cfg(feature = "com-direct-integration")]
        assert_eq!(dispatch(&args(&["com", "run"])).code, 2);
        #[cfg(not(feature = "com-direct-integration"))]
        assert_eq!(dispatch(&args(&["com", "run"])).code, 4);
    }

    #[test]
    fn specified_com_request_result_and_cli_route_share_one_bounded_schema() {
        let nonce = TEST_NONCE.fetch_add(1, Ordering::Relaxed);
        let pulse_root = std::env::temp_dir().join(format!("sipi-cli-com-specified-pulse-{nonce}"));
        let output_root =
            std::env::temp_dir().join(format!("sipi-cli-com-specified-output-{nonce}"));
        let _ = fs::remove_dir_all(&pulse_root);
        let _ = fs::remove_dir_all(&output_root);
        let pulse_store = ArtifactRoot::open_or_create(&pulse_root).expect("pulse root");
        let pulse = (0..64)
            .map(|index| {
                let index = index as f64;
                0.5 * (-(index - 28.0) * (index - 28.0) / 80.0).exp() * (index - 28.0) * 0.4
                    + 0.002 * (index * 0.9).sin()
            })
            .collect::<Vec<_>>();
        let pulse_bytes = pulse
            .iter()
            .flat_map(|value| value.to_le_bytes())
            .collect::<Vec<_>>();
        let mut pulse_stage = pulse_store.begin("pulse-1").expect("pulse staging");
        pulse_stage
            .stage_reader("pulse.f64le", Cursor::new(pulse_bytes), 524_288)
            .expect("pulse payload");
        pulse_stage
            .seal()
            .expect("pulse seal")
            .publish_new()
            .expect("pulse publish");
        let manifest_bytes =
            fs::read(pulse_root.join("pulse-1").join("success.json")).expect("pulse manifest");
        let pulse_manifest_sha256 = format!("{:x}", Sha256::digest(&manifest_bytes));

        let consumed_keys = [
            "samples_per_ui",
            "LEVELS",
            "bin_size",
            "A_v",
            "R_LM",
            "SNR_TX",
            "sigma_X",
            "sigma_RJ",
            "h_J",
            "sigma_N",
            "A_DD",
            "spec_ber",
        ]
        .into_iter()
        .map(str::to_owned)
        .collect::<Vec<_>>();
        let mut params = BTreeMap::new();
        params.insert(
            "samples_per_ui".to_owned(),
            ComParameterValueV1::Scalar(8.0),
        );
        params.insert("LEVELS".to_owned(), ComParameterValueV1::Scalar(4.0));
        params.insert("bin_size".to_owned(), ComParameterValueV1::Scalar(0.01));
        params.insert("A_v".to_owned(), ComParameterValueV1::Scalar(0.5));
        params.insert("R_LM".to_owned(), ComParameterValueV1::Scalar(50.0));
        params.insert("SNR_TX".to_owned(), ComParameterValueV1::Scalar(30.0));
        params.insert("sigma_X".to_owned(), ComParameterValueV1::Scalar(0.03));
        params.insert("sigma_RJ".to_owned(), ComParameterValueV1::Scalar(1e-4));
        params.insert(
            "h_J".to_owned(),
            ComParameterValueV1::Vector(vec![0.3, 0.5, 0.2]),
        );
        params.insert("sigma_N".to_owned(), ComParameterValueV1::Scalar(0.01));
        params.insert("A_DD".to_owned(), ComParameterValueV1::Scalar(0.4));
        params.insert("spec_ber".to_owned(), ComParameterValueV1::Scalar(1e-4));
        let request = sipi_contracts::ComRunArtifactRequestV1 {
            schema: COM_RUN_ARTIFACT_REQUEST_SCHEMA.to_owned(),
            request_id: "com-artifact-1".to_owned(),
            pulse_artifact_id: "pulse-1".to_owned(),
            pulse_manifest_sha256,
            artifact_root: output_root.to_string_lossy().into_owned(),
            artifact_id: "result-1".to_owned(),
            consumed_keys,
            params,
            defaults: BTreeMap::new(),
            unconsumed_keys: Vec::new(),
        };
        let request_bytes = serde_json::to_vec(&request).expect("request JSON");
        let parsed = parse_com_run_artifact_request_v1(&request_bytes).expect("request contract");
        let response = run_com_artifact(&pulse_root.to_string_lossy(), &parsed);
        assert_eq!(response.code, 0);
        let response_json: serde_json::Value =
            serde_json::from_str(&response.stdout.expect("CLI response")).expect("response JSON");
        let result_bytes =
            fs::read(output_root.join("result-1").join("result.json")).expect("result artifact");
        let result_json: serde_json::Value =
            serde_json::from_slice(&result_bytes).expect("result JSON");
        assert_eq!(response_json, result_json);
        assert_eq!(
            response_json["schema"],
            COM_RUN_ARTIFACT_SPECIFIED_RESULT_SCHEMA_V1
        );
        assert_eq!(response_json["scope"]["agent_com_parity"], "not_claimed");
        assert!(
            ArtifactRoot::open_existing(&output_root)
                .expect("output root")
                .verify_published("result-1")
                .is_ok()
        );
        #[cfg(feature = "com-direct-integration")]
        assert_eq!(dispatch(&args(&["com", "run"])).code, 2);
        #[cfg(not(feature = "com-direct-integration"))]
        assert_eq!(dispatch(&args(&["com", "run"])).code, 4);
        let _ = fs::remove_dir_all(pulse_root);
        let _ = fs::remove_dir_all(output_root);
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
            "{\"schema\":\"sipi.cli-schema-list.v1\",\"schemas\":[\"sipi.upstream-migration-request.v1\",\"sipi.capabilities.v1\",\"sipi.artifact-report-request.v1\",\"sipi.channel.matched-two-port-kernel-run-request.v1\",\"sipi.compare.aligned-arrays-request.v1\",\"sipi.compare.prbs9-metric-artifacts-request.v1\",\"sipi.compare.selected-highloss-prbs9-waveform-only-artifacts-request.v3\",\"sipi.ibis.input-typ-dc-evaluate.request.v1\",\"sipi.ibis.input-typ-quasi-static-artifact-batch-evaluate.request.v1\",\"sipi.ibis.input-typ-quasi-static-artifact-evaluate.request.v1\",\"sipi.ibis.input-typ-quasi-static-evaluate.request.v1\",\"sipi.ibis.inspect.request.v1\",\"sipi.link-plan.v1\",\"sipi.link.causal-fir-request.v1\",\"sipi.project.fixed-tran-causal-fir-run-request.v1\",\"sipi.project.v1\",\"sipi.receiver-input.v1\",\"sipi.receiver-semantics.v1\",\"sipi.receiver.diagnostic-run-request.v1\",\"sipi.rx-load.selected-differential-rc-evaluate.request.v1\",\"sipi.tran.one-node-rc-pulse-request.v1\",\"sipi.tran.rc-pulse-request.v1\",\"sipi.validation-request.v1\",\"sipi.com.run-artifact-request.v1\"]}"
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
