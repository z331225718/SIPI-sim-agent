#![forbid(unsafe_code)]

//! Versioned wire contracts for P1 foundations.
//!
//! Serialization is deterministic for these fixed structs and lists in this
//! Rust toolchain. It is not a cross-implementation canonical JSON claim.

use std::{error::Error, fmt, num::NonZeroUsize};

use schemars::{JsonSchema, schema_for};
use serde::{Deserialize, Serialize};
use sipi_types::{
    Axis, Complex64, ComplexTensor, FiniteF64, Hertz, PortId, PortList, Seconds, Spectrum,
    TypeError, Volts, Waveform,
};

pub const CAPABILITIES_SCHEMA: &str = "sipi.capabilities.v1";
pub const ARTIFACT_REPORT_REQUEST_SCHEMA: &str = "sipi.artifact-report-request.v1";
pub const VALIDATION_REQUEST_SCHEMA: &str = "sipi.validation-request.v1";
pub const TRAN_RC_PULSE_REQUEST_SCHEMA: &str = "sipi.tran.rc-pulse-request.v1";
pub const LINK_PLAN_SCHEMA: &str = "sipi.link-plan.v1";
pub const LINK_CAUSAL_FIR_REQUEST_SCHEMA: &str = "sipi.link.causal-fir-request.v1";
pub const IBIS_INSPECT_REQUEST_SCHEMA: &str = "sipi.ibis.inspect.request.v1";
pub const IBIS_DC_EVALUATE_REQUEST_SCHEMA: &str = "sipi.ibis.input-typ-dc-evaluate.request.v1";
pub const IBIS_QUASI_STATIC_EVALUATE_REQUEST_SCHEMA: &str =
    "sipi.ibis.input-typ-quasi-static-evaluate.request.v1";
pub const RX_LOAD_DIFFERENTIAL_RC_EVALUATE_REQUEST_SCHEMA: &str =
    "sipi.rx-load.selected-differential-rc-evaluate.request.v1";
pub const RECEIVER_INPUT_SCHEMA: &str = "sipi.receiver-input.v1";
pub const RECEIVER_SEMANTICS_SCHEMA: &str = "sipi.receiver-semantics.v1";
pub const PROJECT_PLAN_SCHEMA: &str = "sipi.project.v1";
pub const FIXED_PROJECT_RUN_REQUEST_SCHEMA: &str =
    "sipi.project.fixed-tran-causal-fir-run-request.v1";
pub const PLANNED_DOMAINS: [&str; 4] = ["tran", "channel", "ibis-ami", "com"];

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ContractError {
    Json(String),
    Type(TypeError),
    Version,
    Link(LinkContractError),
    Receiver(ReceiverContractError),
    ReceiverSemantics(ReceiverSemanticContractError),
    IbisInspect(IbisInspectContractError),
    IbisDcEvaluate(IbisDcEvaluateContractError),
    IbisQuasiStaticEvaluate(IbisQuasiStaticEvaluateContractError),
    RxLoadDifferentialRcEvaluate(RxLoadDifferentialRcEvaluateContractError),
    Project(ProjectContractError),
}

impl fmt::Display for ContractError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Json(_) => write!(formatter, "invalid contract JSON"),
            Self::Type(error) => error.fmt(formatter),
            Self::Version => write!(formatter, "unsupported contract version"),
            Self::Link(error) => error.fmt(formatter),
            Self::Receiver(error) => error.fmt(formatter),
            Self::ReceiverSemantics(error) => error.fmt(formatter),
            Self::IbisInspect(error) => error.fmt(formatter),
            Self::IbisDcEvaluate(error) => error.fmt(formatter),
            Self::IbisQuasiStaticEvaluate(error) => error.fmt(formatter),
            Self::RxLoadDifferentialRcEvaluate(error) => error.fmt(formatter),
            Self::Project(error) => error.fmt(formatter),
        }
    }
}

impl Error for ContractError {}

impl From<TypeError> for ContractError {
    fn from(value: TypeError) -> Self {
        Self::Type(value)
    }
}

impl From<LinkContractError> for ContractError {
    fn from(value: LinkContractError) -> Self {
        Self::Link(value)
    }
}

impl From<ReceiverContractError> for ContractError {
    fn from(value: ReceiverContractError) -> Self {
        Self::Receiver(value)
    }
}

impl From<ReceiverSemanticContractError> for ContractError {
    fn from(value: ReceiverSemanticContractError) -> Self {
        Self::ReceiverSemantics(value)
    }
}

impl From<IbisInspectContractError> for ContractError {
    fn from(value: IbisInspectContractError) -> Self {
        Self::IbisInspect(value)
    }
}

impl From<IbisDcEvaluateContractError> for ContractError {
    fn from(value: IbisDcEvaluateContractError) -> Self {
        Self::IbisDcEvaluate(value)
    }
}

impl From<IbisQuasiStaticEvaluateContractError> for ContractError {
    fn from(value: IbisQuasiStaticEvaluateContractError) -> Self {
        Self::IbisQuasiStaticEvaluate(value)
    }
}

impl From<RxLoadDifferentialRcEvaluateContractError> for ContractError {
    fn from(value: RxLoadDifferentialRcEvaluateContractError) -> Self {
        Self::RxLoadDifferentialRcEvaluate(value)
    }
}

impl From<ProjectContractError> for ContractError {
    fn from(value: ProjectContractError) -> Self {
        Self::Project(value)
    }
}

/// Stable rejections for the non-executing project declaration boundary.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ProjectContractError {
    Version,
    InvalidProjectId,
    InvalidSeed,
    InvalidResourcePolicy,
    EmptyNodes,
    EmptyRequestedOutputs,
}

impl fmt::Display for ProjectContractError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "invalid project contract: {self:?}")
    }
}

impl Error for ProjectContractError {}

/// Stable rejections for the in-memory IBIS structural inspection boundary.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum IbisInspectContractError {
    UnsupportedEncoding,
    EmptyText,
}

impl fmt::Display for IbisInspectContractError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "invalid IBIS inspect request: {self:?}")
    }
}

impl Error for IbisInspectContractError {}

/// Stable request-boundary rejections for the selected Input/TYP DC route.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum IbisDcEvaluateContractError {
    UnsupportedEncoding,
    EmptyText,
    InvalidSelection,
    UnsupportedCorner,
    NonFiniteProbe,
}

impl fmt::Display for IbisDcEvaluateContractError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "invalid IBIS DC evaluate request: {self:?}")
    }
}

impl Error for IbisDcEvaluateContractError {}

/// Stable request-boundary rejections for the selected Input/TYP
/// quasi-static constitutive route.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum IbisQuasiStaticEvaluateContractError {
    UnsupportedEncoding,
    EmptyText,
    InvalidSelection,
    UnsupportedCorner,
    NonFiniteProbe,
    NonFiniteSlope,
}

impl fmt::Display for IbisQuasiStaticEvaluateContractError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            formatter,
            "invalid IBIS quasi-static evaluate request: {self:?}"
        )
    }
}

impl Error for IbisQuasiStaticEvaluateContractError {}

/// Stable request-boundary rejections for the fixed P/N/REF differential R-C
/// constitutive relation.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum RxLoadDifferentialRcEvaluateContractError {
    NonFiniteProbe,
}

impl fmt::Display for RxLoadDifferentialRcEvaluateContractError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            formatter,
            "invalid selected differential R-C load evaluate request: {self:?}"
        )
    }
}

impl Error for RxLoadDifferentialRcEvaluateContractError {}

/// Stable rejections for the deliberately narrow Link-stage contract.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum LinkContractError {
    NonZeroStart,
    NonPositiveSampleInterval,
    EmptySampleCount,
    StimulusLengthMismatch,
    EmptyCausalFir,
    ChannelIntervalMismatch,
    OutputLengthOverflow,
    UnsupportedStage,
    InvalidExecutionLimit,
}

impl fmt::Display for LinkContractError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "invalid Link-stage contract: {self:?}")
    }
}

impl Error for LinkContractError {}

/// Stable rejections for the required RFM receiver input boundary.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ReceiverContractError {
    UnsupportedProfileTimebase,
    UnsupportedSamplesPerUi,
    SampleLengthMismatch,
}

impl fmt::Display for ReceiverContractError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "invalid receiver input contract: {self:?}")
    }
}

impl Error for ReceiverContractError {}

/// Stable rejections for a caller-supplied receiver semantic preparation.
///
/// This describes no receiver algorithm. It only prevents future callers from
/// omitting the reference bits, fixed feedback coefficients, sampling plan, or
/// BER observation window that an algorithm would need.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ReceiverSemanticContractError {
    EmptyKnownBits,
    EmptyDfeCoefficients,
    InvalidDfeCursor,
    EmptyClockPlan,
    NonIncreasingClockSamples,
    EmptyBerWindow,
    BerWindowOverflow,
    BerWindowExceedsKnownBits,
}

impl fmt::Display for ReceiverSemanticContractError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "invalid receiver semantic preparation: {self:?}")
    }
}

impl Error for ReceiverSemanticContractError {}

#[derive(Clone, Debug, Eq, JsonSchema, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CapabilityCatalogV1 {
    pub schema: String,
    pub capabilities: Vec<CapabilityV1>,
}

#[derive(Clone, Debug, Eq, JsonSchema, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CapabilityV1 {
    pub domain: String,
    pub status: String,
    pub reason: String,
}

impl CapabilityCatalogV1 {
    pub fn unsupported() -> Self {
        Self {
            schema: CAPABILITIES_SCHEMA.to_owned(),
            capabilities: PLANNED_DOMAINS
                .iter()
                .map(|domain| CapabilityV1 {
                    domain: (*domain).to_owned(),
                    status: "unsupported".to_owned(),
                    reason: "not_implemented".to_owned(),
                })
                .collect(),
        }
    }
}

#[derive(Clone, Debug, Eq, JsonSchema, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct UnsupportedResultV1 {
    pub schema: String,
    pub domain: String,
    pub code: String,
}

#[derive(Clone, Debug, Eq, JsonSchema, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ContractErrorV1 {
    pub schema: String,
    pub code: String,
    pub rule_id: String,
}

/// A declarative, non-executing cross-domain project plan.
#[derive(Clone, Debug, Eq, JsonSchema, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WireProjectPlanV1 {
    pub schema: String,
    pub project_id: String,
    /// An explicit 32-byte deterministic seed, rendered as lowercase hex.
    pub seed_hex: String,
    pub resource_policy: WireProjectResourcePolicyV1,
    pub inputs: Vec<WireProjectInputV1>,
    pub nodes: Vec<WireProjectNodeV1>,
    pub edges: Vec<WireProjectEdgeV1>,
    pub requested_outputs: Vec<WireProjectOutputRefV1>,
}

/// Product-owned request for the one executable composite project route.
///
/// It intentionally carries no generic node value map, file path, asset, or
/// legacy profile selector. The fixed TRAN request is implicit in the sole
/// admissible project topology; callers provide only the causal-FIR policy.
#[derive(Clone, Debug, JsonSchema, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WireFixedProjectRunRequestV1 {
    pub schema: String,
    pub plan: WireProjectPlanV1,
    pub consumer: WireFixedProjectCausalFirConsumerV1,
}

#[derive(Clone, Debug, JsonSchema, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WireFixedProjectCausalFirConsumerV1 {
    pub sample_interval_seconds: f64,
    pub gain_v_per_v: Vec<f64>,
    pub max_output_samples: usize,
    pub max_multiply_accumulates: usize,
}

#[derive(Clone, Debug, PartialEq)]
pub struct FixedProjectRunRequestV1 {
    plan: WireProjectPlanV1,
    channel: CausalFirChannelV1,
    limits: LinkExecutionLimitsV1,
}

impl FixedProjectRunRequestV1 {
    pub fn plan(&self) -> &WireProjectPlanV1 {
        &self.plan
    }

    pub fn channel(&self) -> &CausalFirChannelV1 {
        &self.channel
    }

    pub const fn limits(&self) -> LinkExecutionLimitsV1 {
        self.limits
    }
}

impl TryFrom<WireFixedProjectRunRequestV1> for FixedProjectRunRequestV1 {
    type Error = ContractError;

    fn try_from(value: WireFixedProjectRunRequestV1) -> Result<Self, Self::Error> {
        if value.schema != FIXED_PROJECT_RUN_REQUEST_SCHEMA {
            return Err(ContractError::Version);
        }
        value.plan.validate_boundary()?;
        let channel = CausalFirChannelV1::try_new(
            Seconds::try_new(value.consumer.sample_interval_seconds)?,
            value
                .consumer
                .gain_v_per_v
                .into_iter()
                .map(|value| FiniteF64::try_new(value, "causal FIR gain"))
                .collect::<Result<Vec<_>, _>>()?,
        )?;
        Ok(Self {
            plan: value.plan,
            channel,
            limits: LinkExecutionLimitsV1::try_new(
                value.consumer.max_output_samples,
                value.consumer.max_multiply_accumulates,
            )?,
        })
    }
}

impl From<&FixedProjectRunRequestV1> for WireFixedProjectRunRequestV1 {
    fn from(value: &FixedProjectRunRequestV1) -> Self {
        Self {
            schema: FIXED_PROJECT_RUN_REQUEST_SCHEMA.to_owned(),
            plan: value.plan.clone(),
            consumer: WireFixedProjectCausalFirConsumerV1 {
                sample_interval_seconds: value.channel.sample_interval().get(),
                gain_v_per_v: value.channel.gain().iter().map(|gain| gain.get()).collect(),
                max_output_samples: value.limits.max_output_samples.get(),
                max_multiply_accumulates: value.limits.max_multiply_accumulates.get(),
            },
        }
    }
}

#[derive(Clone, Debug, Eq, JsonSchema, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WireProjectResourcePolicyV1 {
    pub timeout_millis: u64,
    pub max_work_units: u64,
    pub max_accounted_bytes: u64,
}

#[derive(Clone, Debug, Eq, JsonSchema, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WireProjectInputV1 {
    pub id: String,
    pub contract: String,
}

#[derive(Clone, Debug, Eq, JsonSchema, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WireProjectNodeV1 {
    pub id: String,
    pub kind: String,
}

#[derive(Clone, Debug, Eq, JsonSchema, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WireProjectPortRefV1 {
    pub node_id: String,
    pub port: String,
}

#[derive(Clone, Debug, Eq, JsonSchema, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WireProjectEdgeV1 {
    pub from: WireProjectEdgeSourceV1,
    pub to: WireProjectPortRefV1,
    pub contract: String,
}

#[derive(Clone, Debug, Eq, JsonSchema, PartialEq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum WireProjectEdgeSourceV1 {
    ProjectInput { input_id: String },
    NodeOutput { node_id: String, port: String },
}

#[derive(Clone, Debug, Eq, JsonSchema, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WireProjectOutputRefV1 {
    pub node_id: String,
    pub port: String,
    pub contract: String,
}

impl WireProjectPlanV1 {
    pub fn validate_boundary(&self) -> Result<(), ProjectContractError> {
        if self.schema != PROJECT_PLAN_SCHEMA {
            return Err(ProjectContractError::Version);
        }
        if !token(&self.project_id) {
            return Err(ProjectContractError::InvalidProjectId);
        }
        if self.seed_hex.len() != 64
            || !self
                .seed_hex
                .bytes()
                .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
        {
            return Err(ProjectContractError::InvalidSeed);
        }
        if self.resource_policy.timeout_millis == 0
            || self.resource_policy.max_work_units == 0
            || self.resource_policy.max_accounted_bytes == 0
        {
            return Err(ProjectContractError::InvalidResourcePolicy);
        }
        if self.nodes.is_empty() {
            return Err(ProjectContractError::EmptyNodes);
        }
        if self.requested_outputs.is_empty() {
            return Err(ProjectContractError::EmptyRequestedOutputs);
        }
        Ok(())
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct RuleLedgerEntry {
    pub id: &'static str,
    pub owner: &'static str,
    pub wire_type: &'static str,
    pub code: &'static str,
    pub test_id: &'static str,
}

pub const RULE_LEDGER_V1: [RuleLedgerEntry; 13] = [
    RuleLedgerEntry {
        id: "contract.v1.version",
        owner: "contract",
        wire_type: "envelope",
        code: "unsupported_version",
        test_id: "contract_version",
    },
    RuleLedgerEntry {
        id: "types.finite",
        owner: "types",
        wire_type: "scalar",
        code: "non_finite",
        test_id: "finite_wrappers",
    },
    RuleLedgerEntry {
        id: "types.port-list",
        owner: "types",
        wire_type: "port_list",
        code: "invalid_port",
        test_id: "ports_unique",
    },
    RuleLedgerEntry {
        id: "types.tensor",
        owner: "types",
        wire_type: "complex_tensor",
        code: "invalid_tensor",
        test_id: "tensor_shape",
    },
    RuleLedgerEntry {
        id: "types.series",
        owner: "types",
        wire_type: "waveform_or_spectrum",
        code: "length_mismatch",
        test_id: "series_length",
    },
    RuleLedgerEntry {
        id: "tran.rc-pulse.profile",
        owner: "contract",
        wire_type: "tran_rc_pulse_request",
        code: "unsupported_profile",
        test_id: "tran_rc_pulse_exact_profile",
    },
    RuleLedgerEntry {
        id: "link.v1.timebase",
        owner: "contract",
        wire_type: "link_plan",
        code: "invalid_timebase",
        test_id: "link_timebase_is_strict",
    },
    RuleLedgerEntry {
        id: "link.v1.causal-fir",
        owner: "contract",
        wire_type: "link_plan",
        code: "invalid_causal_fir",
        test_id: "link_causal_fir_is_strict",
    },
    RuleLedgerEntry {
        id: "link.v1.stages",
        owner: "contract",
        wire_type: "link_plan",
        code: "unsupported_stage",
        test_id: "link_only_direct_bypass_is_accepted",
    },
    RuleLedgerEntry {
        id: "receiver.rfm.v1.timebase",
        owner: "contract",
        wire_type: "receiver_input",
        code: "unsupported_profile_timebase",
        test_id: "receiver_required_timebase_is_strict",
    },
    RuleLedgerEntry {
        id: "receiver.rfm.v1.frontend",
        owner: "contract",
        wire_type: "receiver_input",
        code: "unsupported_stage",
        test_id: "receiver_frontend_is_bypass_only",
    },
    RuleLedgerEntry {
        id: "receiver.semantics.v1.explicit-inputs",
        owner: "contract",
        wire_type: "receiver_semantics",
        code: "missing_receiver_semantics",
        test_id: "receiver_semantics_require_explicit_inputs",
    },
    RuleLedgerEntry {
        id: "receiver.semantics.v1.window",
        owner: "contract",
        wire_type: "receiver_semantics",
        code: "invalid_ber_window",
        test_id: "receiver_semantics_validate_window",
    },
];

#[derive(Clone, Debug, JsonSchema, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WirePortListV1 {
    pub schema: String,
    pub ports: Vec<String>,
}

impl TryFrom<WirePortListV1> for PortList {
    type Error = ContractError;

    fn try_from(value: WirePortListV1) -> Result<Self, Self::Error> {
        require_schema(&value.schema)?;
        value
            .ports
            .into_iter()
            .map(PortId::try_new)
            .collect::<Result<Vec<_>, _>>()?
            .pipe(PortList::try_new)
            .map_err(Into::into)
    }
}

#[derive(Clone, Debug, JsonSchema, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WireComplexV1 {
    pub real: f64,
    pub imaginary: f64,
}

impl TryFrom<WireComplexV1> for Complex64 {
    type Error = ContractError;
    fn try_from(value: WireComplexV1) -> Result<Self, Self::Error> {
        Complex64::try_new(value.real, value.imaginary).map_err(Into::into)
    }
}

#[derive(Clone, Debug, JsonSchema, PartialEq, Serialize, Deserialize)]
#[serde(tag = "encoding", rename_all = "snake_case", deny_unknown_fields)]
pub enum WireAxisV1 {
    Uniform { start: f64, step: f64, count: usize },
    Explicit { values: Vec<f64> },
}

#[derive(Clone, Debug, JsonSchema, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WireComplexTensorV1 {
    pub shape: Vec<usize>,
    pub values: Vec<WireComplexV1>,
}

#[derive(Clone, Debug, JsonSchema, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WireWaveformV1 {
    pub schema: String,
    pub axis: WireAxisV1,
    pub samples: Vec<f64>,
}

#[derive(Clone, Debug, JsonSchema, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ValidationRequestV1 {
    pub schema: String,
    pub request_id: String,
    pub subject: WireWaveformV1,
}

/// Product-owned, typed request for the sole accepted TRAN profile.
///
/// This is deliberately an exact-profile contract: values other than the
/// independently specified RC/PULSE instance are rejected rather than being
/// interpreted as a general circuit or netlist request.
#[derive(Clone, Debug, JsonSchema, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct TranRcPulseRequestV1 {
    pub schema: String,
    pub request_id: String,
    pub resistance_ohms: f64,
    pub capacitance_farads: f64,
    pub initial_voltage_out_volts: f64,
    pub output_times_seconds: Vec<f64>,
    pub pulse: TranPulseV1,
}

#[derive(Clone, Debug, JsonSchema, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct TranPulseV1 {
    pub voltage_low_volts: f64,
    pub voltage_high_volts: f64,
    pub delay_seconds: f64,
    pub rise_seconds: f64,
    pub fall_seconds: f64,
    pub width_seconds: f64,
    pub period_seconds: f64,
}

/// Product-owned Link-stage plan. It is a typed boundary, not an executor.
///
/// Its channel is a causal, finite impulse-response kernel for future linear
/// convolution. In particular, the periodic DFT kernel produced by
/// `sipi-channel` is intentionally not accepted here.
#[derive(Clone, Debug, JsonSchema, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WireLinkPlanV1 {
    pub schema: String,
    pub timebase: WireUniformTimebaseV1,
    pub tx: WireTxStageV1,
    pub stimulus_volts: Vec<f64>,
    pub channel: WireLinkChannelV1,
    pub rx: WireRxStagesV1,
}

/// The sole executable Link request in v1. It deliberately wraps only the
/// direct-launch, bypass-front-end causal-FIR plan.
#[derive(Clone, Debug, JsonSchema, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WireLinkCausalFirRequestV1 {
    pub schema: String,
    pub request_id: String,
    pub plan: WireLinkPlanV1,
    pub limits: WireLinkExecutionLimitsV1,
}

#[derive(Clone, Debug, JsonSchema, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WireLinkExecutionLimitsV1 {
    pub max_output_samples: usize,
    pub max_multiply_accumulates: usize,
}

#[derive(Clone, Debug, JsonSchema, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WireUniformTimebaseV1 {
    pub start_seconds: f64,
    pub sample_interval_seconds: f64,
    pub sample_count: usize,
}

#[derive(Clone, Debug, JsonSchema, PartialEq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum WireTxStageV1 {
    DirectLaunch,
}

#[derive(Clone, Debug, JsonSchema, PartialEq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum WireLinkChannelV1 {
    CausalFir {
        sample_interval_seconds: f64,
        gain_v_per_v: Vec<f64>,
    },
}

#[derive(Clone, Debug, JsonSchema, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WireRxStagesV1 {
    pub ctle: WireCtleStageV1,
    pub ffe: WireFfeStageV1,
}

#[derive(Clone, Debug, JsonSchema, PartialEq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum WireCtleStageV1 {
    Bypass,
}

#[derive(Clone, Debug, JsonSchema, PartialEq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum WireFfeStageV1 {
    Bypass,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct UniformTimebaseV1 {
    start: Seconds,
    sample_interval: Seconds,
    sample_count: NonZeroUsize,
}

impl UniformTimebaseV1 {
    pub fn try_new(
        start: Seconds,
        sample_interval: Seconds,
        sample_count: usize,
    ) -> Result<Self, LinkContractError> {
        if start.get() != 0.0 {
            return Err(LinkContractError::NonZeroStart);
        }
        if sample_interval.get() <= 0.0 {
            return Err(LinkContractError::NonPositiveSampleInterval);
        }
        let sample_count =
            NonZeroUsize::new(sample_count).ok_or(LinkContractError::EmptySampleCount)?;
        Ok(Self {
            start,
            sample_interval,
            sample_count,
        })
    }

    pub fn start(self) -> Seconds {
        self.start
    }

    pub fn sample_interval(self) -> Seconds {
        self.sample_interval
    }

    pub fn sample_count(self) -> NonZeroUsize {
        self.sample_count
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct CausalFirChannelV1 {
    sample_interval: Seconds,
    gain: Vec<FiniteF64>,
}

impl CausalFirChannelV1 {
    pub fn try_new(
        sample_interval: Seconds,
        gain: Vec<FiniteF64>,
    ) -> Result<Self, LinkContractError> {
        if sample_interval.get() <= 0.0 {
            return Err(LinkContractError::NonPositiveSampleInterval);
        }
        if gain.is_empty() {
            return Err(LinkContractError::EmptyCausalFir);
        }
        Ok(Self {
            sample_interval,
            gain,
        })
    }

    pub fn sample_interval(&self) -> Seconds {
        self.sample_interval
    }

    pub fn gain(&self) -> &[FiniteF64] {
        &self.gain
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum TxStageV1 {
    DirectLaunch,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum CtleStageV1 {
    Bypass,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum FfeStageV1 {
    Bypass,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct RxStagesV1 {
    ctle: CtleStageV1,
    ffe: FfeStageV1,
}

impl RxStagesV1 {
    pub fn bypass() -> Self {
        Self {
            ctle: CtleStageV1::Bypass,
            ffe: FfeStageV1::Bypass,
        }
    }

    pub fn ctle(self) -> CtleStageV1 {
        self.ctle
    }

    pub fn ffe(self) -> FfeStageV1 {
        self.ffe
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct LinkPlanV1 {
    timebase: UniformTimebaseV1,
    tx: TxStageV1,
    stimulus: Vec<Volts>,
    channel: CausalFirChannelV1,
    rx: RxStagesV1,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct LinkExecutionLimitsV1 {
    max_output_samples: NonZeroUsize,
    max_multiply_accumulates: NonZeroUsize,
}

impl LinkExecutionLimitsV1 {
    pub fn try_new(
        max_output_samples: usize,
        max_multiply_accumulates: usize,
    ) -> Result<Self, LinkContractError> {
        Ok(Self {
            max_output_samples: NonZeroUsize::new(max_output_samples)
                .ok_or(LinkContractError::InvalidExecutionLimit)?,
            max_multiply_accumulates: NonZeroUsize::new(max_multiply_accumulates)
                .ok_or(LinkContractError::InvalidExecutionLimit)?,
        })
    }
    pub fn max_output_samples(self) -> NonZeroUsize {
        self.max_output_samples
    }
    pub fn max_multiply_accumulates(self) -> NonZeroUsize {
        self.max_multiply_accumulates
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct LinkCausalFirRequestV1 {
    request_id: String,
    plan: LinkPlanV1,
    limits: LinkExecutionLimitsV1,
}

impl LinkCausalFirRequestV1 {
    pub fn request_id(&self) -> &str {
        &self.request_id
    }
    pub fn plan(&self) -> &LinkPlanV1 {
        &self.plan
    }
    pub fn limits(&self) -> LinkExecutionLimitsV1 {
        self.limits
    }
}

impl LinkPlanV1 {
    pub fn try_new(
        timebase: UniformTimebaseV1,
        tx: TxStageV1,
        stimulus: Vec<Volts>,
        channel: CausalFirChannelV1,
        rx: RxStagesV1,
    ) -> Result<Self, LinkContractError> {
        if stimulus.len() != timebase.sample_count().get() {
            return Err(LinkContractError::StimulusLengthMismatch);
        }
        if channel.sample_interval() != timebase.sample_interval() {
            return Err(LinkContractError::ChannelIntervalMismatch);
        }
        let _ = stimulus
            .len()
            .checked_add(channel.gain().len())
            .and_then(|count| count.checked_sub(1))
            .ok_or(LinkContractError::OutputLengthOverflow)?;
        Ok(Self {
            timebase,
            tx,
            stimulus,
            channel,
            rx,
        })
    }

    pub fn timebase(&self) -> UniformTimebaseV1 {
        self.timebase
    }

    pub fn tx(&self) -> TxStageV1 {
        self.tx
    }

    pub fn stimulus(&self) -> &[Volts] {
        &self.stimulus
    }

    pub fn channel(&self) -> &CausalFirChannelV1 {
        &self.channel
    }

    pub fn rx(&self) -> RxStagesV1 {
        self.rx
    }

    /// The future linear convolution result has this many samples.
    pub fn output_sample_count(&self) -> usize {
        self.stimulus.len() + self.channel.gain().len() - 1
    }
}

impl TryFrom<WireLinkPlanV1> for LinkPlanV1 {
    type Error = ContractError;

    fn try_from(value: WireLinkPlanV1) -> Result<Self, Self::Error> {
        require_link_schema(&value.schema)?;
        let timebase = UniformTimebaseV1::try_new(
            Seconds::try_new(value.timebase.start_seconds)?,
            Seconds::try_new(value.timebase.sample_interval_seconds)?,
            value.timebase.sample_count,
        )?;
        let stimulus = value
            .stimulus_volts
            .into_iter()
            .map(Volts::try_new)
            .collect::<Result<Vec<_>, _>>()?;
        let channel = match value.channel {
            WireLinkChannelV1::CausalFir {
                sample_interval_seconds,
                gain_v_per_v,
            } => CausalFirChannelV1::try_new(
                Seconds::try_new(sample_interval_seconds)?,
                gain_v_per_v
                    .into_iter()
                    .map(|gain| FiniteF64::try_new(gain, "causal FIR gain"))
                    .collect::<Result<Vec<_>, _>>()?,
            )?,
        };
        let tx = match value.tx {
            WireTxStageV1::DirectLaunch => TxStageV1::DirectLaunch,
        };
        let rx = match value.rx {
            WireRxStagesV1 {
                ctle: WireCtleStageV1::Bypass,
                ffe: WireFfeStageV1::Bypass,
            } => RxStagesV1::bypass(),
        };
        Self::try_new(timebase, tx, stimulus, channel, rx).map_err(Into::into)
    }
}

impl From<&LinkPlanV1> for WireLinkPlanV1 {
    fn from(value: &LinkPlanV1) -> Self {
        Self {
            schema: LINK_PLAN_SCHEMA.to_owned(),
            timebase: WireUniformTimebaseV1 {
                start_seconds: value.timebase.start().get(),
                sample_interval_seconds: value.timebase.sample_interval().get(),
                sample_count: value.timebase.sample_count().get(),
            },
            tx: WireTxStageV1::DirectLaunch,
            stimulus_volts: value.stimulus().iter().map(|sample| sample.get()).collect(),
            channel: WireLinkChannelV1::CausalFir {
                sample_interval_seconds: value.channel().sample_interval().get(),
                gain_v_per_v: value
                    .channel()
                    .gain()
                    .iter()
                    .map(|gain| gain.get())
                    .collect(),
            },
            rx: WireRxStagesV1 {
                ctle: WireCtleStageV1::Bypass,
                ffe: WireFfeStageV1::Bypass,
            },
        }
    }
}

impl TryFrom<WireLinkCausalFirRequestV1> for LinkCausalFirRequestV1 {
    type Error = ContractError;
    fn try_from(value: WireLinkCausalFirRequestV1) -> Result<Self, Self::Error> {
        require_link_causal_fir_request_schema(&value.schema)?;
        if !valid_request_id(&value.request_id) {
            return Err(ContractError::Json("invalid request id".to_owned()));
        }
        Ok(Self {
            request_id: value.request_id,
            plan: value.plan.try_into()?,
            limits: LinkExecutionLimitsV1::try_new(
                value.limits.max_output_samples,
                value.limits.max_multiply_accumulates,
            )?,
        })
    }
}

impl From<&LinkCausalFirRequestV1> for WireLinkCausalFirRequestV1 {
    fn from(value: &LinkCausalFirRequestV1) -> Self {
        Self {
            schema: LINK_CAUSAL_FIR_REQUEST_SCHEMA.to_owned(),
            request_id: value.request_id.clone(),
            plan: WireLinkPlanV1::from(&value.plan),
            limits: WireLinkExecutionLimitsV1 {
                max_output_samples: value.limits.max_output_samples.get(),
                max_multiply_accumulates: value.limits.max_multiply_accumulates.get(),
            },
        }
    }
}

pub fn parse_link_plan_v1(input: &[u8]) -> Result<LinkPlanV1, ContractError> {
    serde_json::from_slice::<WireLinkPlanV1>(input)
        .map_err(|error| ContractError::Json(error.to_string()))?
        .try_into()
}

pub fn parse_link_causal_fir_request_v1(
    input: &[u8],
) -> Result<LinkCausalFirRequestV1, ContractError> {
    serde_json::from_slice::<WireLinkCausalFirRequestV1>(input)
        .map_err(|error| ContractError::Json(error.to_string()))?
        .try_into()
}

/// Parses the only executable P6 composite-project request.
///
/// The wire contract admits the project declaration and its explicit causal
/// FIR consumer policy. `sipi-pipeline` performs the stricter topology
/// admission immediately before execution.
pub fn parse_fixed_project_run_request_v1(
    input: &[u8],
) -> Result<FixedProjectRunRequestV1, ContractError> {
    serde_json::from_slice::<WireFixedProjectRunRequestV1>(input)
        .map_err(|error| ContractError::Json(error.to_string()))?
        .try_into()
}

/// A product-owned request for structural inspection of one JSON UTF-8 text.
/// It deliberately has no file, URL, binary, profile, or evaluation surface.
#[derive(Clone, Debug, JsonSchema, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WireIbisInspectRequestV1 {
    pub schema: String,
    pub source: WireIbisInspectSourceV1,
}

#[derive(Clone, Debug, JsonSchema, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WireIbisInspectSourceV1 {
    pub encoding: String,
    pub text: String,
}

#[derive(Clone, Debug, PartialEq)]
pub struct IbisInspectRequestV1 {
    text: String,
}

impl IbisInspectRequestV1 {
    pub fn text(&self) -> &str {
        &self.text
    }
}

impl TryFrom<WireIbisInspectRequestV1> for IbisInspectRequestV1 {
    type Error = ContractError;

    fn try_from(value: WireIbisInspectRequestV1) -> Result<Self, Self::Error> {
        if value.schema != IBIS_INSPECT_REQUEST_SCHEMA {
            return Err(ContractError::Version);
        }
        if value.source.encoding != "utf-8" {
            return Err(IbisInspectContractError::UnsupportedEncoding.into());
        }
        if value.source.text.is_empty() {
            return Err(IbisInspectContractError::EmptyText.into());
        }
        Ok(Self {
            text: value.source.text,
        })
    }
}

pub fn parse_ibis_inspect_request_v1(input: &[u8]) -> Result<IbisInspectRequestV1, ContractError> {
    serde_json::from_slice::<WireIbisInspectRequestV1>(input)
        .map_err(|error| ContractError::Json(error.to_string()))?
        .try_into()
}

/// A product-owned Input/TYP static clamp request. The text is caller-provided
/// UTF-8; it has no file, URL, asset identity, or external acceptance surface.
#[derive(Clone, Debug, JsonSchema, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WireIbisDcEvaluateRequestV1 {
    pub schema: String,
    pub source: WireIbisInspectSourceV1,
    pub selection: WireIbisDcSelectionV1,
    pub probe: WireIbisDcProbeV1,
}

#[derive(Clone, Debug, JsonSchema, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WireIbisDcSelectionV1 {
    pub ibis_version: String,
    pub model_selector: String,
    pub corner: String,
}

#[derive(Clone, Copy, Debug, JsonSchema, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WireIbisDcProbeV1 {
    pub gnd_clamp_drive_volts: f64,
    pub power_clamp_drive_volts: f64,
}

#[derive(Clone, Debug, PartialEq)]
pub struct IbisDcEvaluateRequestV1 {
    text: String,
    ibis_version: String,
    model_selector: String,
    gnd_clamp_drive_volts: Volts,
    power_clamp_drive_volts: Volts,
}

impl IbisDcEvaluateRequestV1 {
    pub fn text(&self) -> &str {
        &self.text
    }

    pub fn ibis_version(&self) -> &str {
        &self.ibis_version
    }

    pub fn model_selector(&self) -> &str {
        &self.model_selector
    }

    pub const fn gnd_clamp_drive_volts(&self) -> Volts {
        self.gnd_clamp_drive_volts
    }

    pub const fn power_clamp_drive_volts(&self) -> Volts {
        self.power_clamp_drive_volts
    }
}

impl TryFrom<WireIbisDcEvaluateRequestV1> for IbisDcEvaluateRequestV1 {
    type Error = ContractError;

    fn try_from(value: WireIbisDcEvaluateRequestV1) -> Result<Self, Self::Error> {
        if value.schema != IBIS_DC_EVALUATE_REQUEST_SCHEMA {
            return Err(ContractError::Version);
        }
        if value.source.encoding != "utf-8" {
            return Err(IbisDcEvaluateContractError::UnsupportedEncoding.into());
        }
        if value.source.text.is_empty() {
            return Err(IbisDcEvaluateContractError::EmptyText.into());
        }
        if value.selection.corner != "typical" {
            return Err(IbisDcEvaluateContractError::UnsupportedCorner.into());
        }
        if value.selection.ibis_version.is_empty() || value.selection.model_selector.is_empty() {
            return Err(IbisDcEvaluateContractError::InvalidSelection.into());
        }
        let gnd_clamp_drive_volts = Volts::try_new(value.probe.gnd_clamp_drive_volts)
            .map_err(|_| IbisDcEvaluateContractError::NonFiniteProbe)?;
        let power_clamp_drive_volts = Volts::try_new(value.probe.power_clamp_drive_volts)
            .map_err(|_| IbisDcEvaluateContractError::NonFiniteProbe)?;
        Ok(Self {
            text: value.source.text,
            ibis_version: value.selection.ibis_version,
            model_selector: value.selection.model_selector,
            gnd_clamp_drive_volts,
            power_clamp_drive_volts,
        })
    }
}

pub fn parse_ibis_dc_evaluate_request_v1(
    input: &[u8],
) -> Result<IbisDcEvaluateRequestV1, ContractError> {
    serde_json::from_slice::<WireIbisDcEvaluateRequestV1>(input)
        .map_err(|error| ContractError::Json(error.to_string()))?
        .try_into()
}

/// A product-owned Input/TYP quasi-static clamp request. It provides the
/// continuous SIG-to-REF slope explicitly; it does not accept a time step,
/// waveform, history, asset identity, or external acceptance surface.
#[derive(Clone, Debug, JsonSchema, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WireIbisQuasiStaticEvaluateRequestV1 {
    pub schema: String,
    pub source: WireIbisInspectSourceV1,
    pub selection: WireIbisDcSelectionV1,
    pub probe: WireIbisQuasiStaticProbeV1,
}

#[derive(Clone, Copy, Debug, JsonSchema, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WireIbisQuasiStaticProbeV1 {
    pub gnd_clamp_drive_volts: f64,
    pub power_clamp_drive_volts: f64,
    pub sig_to_ref_slope_volts_per_second: f64,
}

#[derive(Clone, Debug, PartialEq)]
pub struct IbisQuasiStaticEvaluateRequestV1 {
    text: String,
    ibis_version: String,
    model_selector: String,
    gnd_clamp_drive_volts: Volts,
    power_clamp_drive_volts: Volts,
    sig_to_ref_slope_volts_per_second: FiniteF64,
}

impl IbisQuasiStaticEvaluateRequestV1 {
    pub fn text(&self) -> &str {
        &self.text
    }

    pub fn ibis_version(&self) -> &str {
        &self.ibis_version
    }

    pub fn model_selector(&self) -> &str {
        &self.model_selector
    }

    pub const fn gnd_clamp_drive_volts(&self) -> Volts {
        self.gnd_clamp_drive_volts
    }

    pub const fn power_clamp_drive_volts(&self) -> Volts {
        self.power_clamp_drive_volts
    }

    pub fn sig_to_ref_slope_volts_per_second(&self) -> f64 {
        self.sig_to_ref_slope_volts_per_second.get()
    }
}

impl TryFrom<WireIbisQuasiStaticEvaluateRequestV1> for IbisQuasiStaticEvaluateRequestV1 {
    type Error = ContractError;

    fn try_from(value: WireIbisQuasiStaticEvaluateRequestV1) -> Result<Self, Self::Error> {
        if value.schema != IBIS_QUASI_STATIC_EVALUATE_REQUEST_SCHEMA {
            return Err(ContractError::Version);
        }
        if value.source.encoding != "utf-8" {
            return Err(IbisQuasiStaticEvaluateContractError::UnsupportedEncoding.into());
        }
        if value.source.text.is_empty() {
            return Err(IbisQuasiStaticEvaluateContractError::EmptyText.into());
        }
        if value.selection.corner != "typical" {
            return Err(IbisQuasiStaticEvaluateContractError::UnsupportedCorner.into());
        }
        if value.selection.ibis_version.is_empty() || value.selection.model_selector.is_empty() {
            return Err(IbisQuasiStaticEvaluateContractError::InvalidSelection.into());
        }
        let gnd_clamp_drive_volts = Volts::try_new(value.probe.gnd_clamp_drive_volts)
            .map_err(|_| IbisQuasiStaticEvaluateContractError::NonFiniteProbe)?;
        let power_clamp_drive_volts = Volts::try_new(value.probe.power_clamp_drive_volts)
            .map_err(|_| IbisQuasiStaticEvaluateContractError::NonFiniteProbe)?;
        let sig_to_ref_slope_volts_per_second = FiniteF64::try_new(
            value.probe.sig_to_ref_slope_volts_per_second,
            "SIG-to-REF voltage slope in volts per second",
        )
        .map_err(|_| IbisQuasiStaticEvaluateContractError::NonFiniteSlope)?;
        Ok(Self {
            text: value.source.text,
            ibis_version: value.selection.ibis_version,
            model_selector: value.selection.model_selector,
            gnd_clamp_drive_volts,
            power_clamp_drive_volts,
            sig_to_ref_slope_volts_per_second,
        })
    }
}

pub fn parse_ibis_quasi_static_evaluate_request_v1(
    input: &[u8],
) -> Result<IbisQuasiStaticEvaluateRequestV1, ContractError> {
    serde_json::from_slice::<WireIbisQuasiStaticEvaluateRequestV1>(input)
        .map_err(|error| ContractError::Json(error.to_string()))?
        .try_into()
}

/// A product-owned request for the one selected continuous P/N/REF R-C load.
/// It does not accept component values, time steps, samples, topology choices,
/// or an implicit global reference node.
#[derive(Clone, Debug, JsonSchema, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WireRxLoadDifferentialRcEvaluateRequestV1 {
    pub schema: String,
    pub probe: WireRxLoadDifferentialRcProbeV1,
}

#[derive(Clone, Copy, Debug, JsonSchema, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WireRxLoadDifferentialRcProbeV1 {
    pub p_to_ref_volts: f64,
    pub n_to_ref_volts: f64,
    pub p_to_ref_slope_volts_per_second: f64,
    pub n_to_ref_slope_volts_per_second: f64,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct RxLoadDifferentialRcEvaluateRequestV1 {
    p_to_ref_volts: Volts,
    n_to_ref_volts: Volts,
    p_to_ref_slope_volts_per_second: FiniteF64,
    n_to_ref_slope_volts_per_second: FiniteF64,
}

impl RxLoadDifferentialRcEvaluateRequestV1 {
    pub const fn p_to_ref_volts(&self) -> Volts {
        self.p_to_ref_volts
    }

    pub const fn n_to_ref_volts(&self) -> Volts {
        self.n_to_ref_volts
    }

    pub fn p_to_ref_slope_volts_per_second(&self) -> f64 {
        self.p_to_ref_slope_volts_per_second.get()
    }

    pub fn n_to_ref_slope_volts_per_second(&self) -> f64 {
        self.n_to_ref_slope_volts_per_second.get()
    }
}

impl TryFrom<WireRxLoadDifferentialRcEvaluateRequestV1> for RxLoadDifferentialRcEvaluateRequestV1 {
    type Error = ContractError;

    fn try_from(value: WireRxLoadDifferentialRcEvaluateRequestV1) -> Result<Self, Self::Error> {
        if value.schema != RX_LOAD_DIFFERENTIAL_RC_EVALUATE_REQUEST_SCHEMA {
            return Err(ContractError::Version);
        }
        let p_to_ref_volts = Volts::try_new(value.probe.p_to_ref_volts)
            .map_err(|_| RxLoadDifferentialRcEvaluateContractError::NonFiniteProbe)?;
        let n_to_ref_volts = Volts::try_new(value.probe.n_to_ref_volts)
            .map_err(|_| RxLoadDifferentialRcEvaluateContractError::NonFiniteProbe)?;
        let p_to_ref_slope_volts_per_second = FiniteF64::try_new(
            value.probe.p_to_ref_slope_volts_per_second,
            "P-to-REF voltage slope in volts per second",
        )
        .map_err(|_| RxLoadDifferentialRcEvaluateContractError::NonFiniteProbe)?;
        let n_to_ref_slope_volts_per_second = FiniteF64::try_new(
            value.probe.n_to_ref_slope_volts_per_second,
            "N-to-REF voltage slope in volts per second",
        )
        .map_err(|_| RxLoadDifferentialRcEvaluateContractError::NonFiniteProbe)?;
        Ok(Self {
            p_to_ref_volts,
            n_to_ref_volts,
            p_to_ref_slope_volts_per_second,
            n_to_ref_slope_volts_per_second,
        })
    }
}

pub fn parse_rx_load_differential_rc_evaluate_request_v1(
    input: &[u8],
) -> Result<RxLoadDifferentialRcEvaluateRequestV1, ContractError> {
    serde_json::from_slice::<WireRxLoadDifferentialRcEvaluateRequestV1>(input)
        .map_err(|error| ContractError::Json(error.to_string()))?
        .try_into()
}

/// A caller-owned request to verify and project one already-published local
/// artifact. It deliberately has no file enumeration, URL, or payload surface.
#[derive(Clone, Debug, JsonSchema, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WireArtifactReportRequestV1 {
    pub schema: String,
    pub artifact_root: String,
    pub artifact_id: String,
}

#[derive(Clone, Debug, PartialEq)]
pub struct ArtifactReportRequestV1 {
    artifact_root: String,
    artifact_id: String,
}

impl ArtifactReportRequestV1 {
    pub fn artifact_root(&self) -> &str {
        &self.artifact_root
    }

    pub fn artifact_id(&self) -> &str {
        &self.artifact_id
    }
}

impl TryFrom<WireArtifactReportRequestV1> for ArtifactReportRequestV1 {
    type Error = ContractError;

    fn try_from(value: WireArtifactReportRequestV1) -> Result<Self, Self::Error> {
        if value.schema != ARTIFACT_REPORT_REQUEST_SCHEMA {
            return Err(ContractError::Version);
        }
        if value.artifact_root.is_empty()
            || value.artifact_root.len() > 4096
            || value.artifact_root.contains('\0')
            || value.artifact_root.contains("://")
            || value
                .artifact_root
                .split(['/', '\\'])
                .any(|segment| matches!(segment, "." | ".."))
        {
            return Err(ContractError::Json("invalid artifact root".to_owned()));
        }
        if !valid_artifact_id(&value.artifact_id) {
            return Err(ContractError::Json("invalid artifact id".to_owned()));
        }
        Ok(Self {
            artifact_root: value.artifact_root,
            artifact_id: value.artifact_id,
        })
    }
}

pub fn parse_artifact_report_request_v1(
    input: &[u8],
) -> Result<ArtifactReportRequestV1, ContractError> {
    serde_json::from_slice::<WireArtifactReportRequestV1>(input)
        .map_err(|error| ContractError::Json(error.to_string()))?
        .try_into()
}

/// Product-owned receiver waveform boundary for the required RFM profile.
///
/// The external RFM/current-drive provenance deliberately does not cross this
/// boundary. DFE, CDR, and BER are not represented because their semantics
/// remain explicitly unselected.
#[derive(Clone, Debug, JsonSchema, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WireReceiverInputV1 {
    pub schema: String,
    pub timebase: WireUniformTimebaseV1,
    pub receive_volts: Vec<f64>,
    pub samples_per_ui: usize,
    pub frontend: WireRxStagesV1,
}

#[derive(Clone, Debug, PartialEq)]
pub struct ReceiverInputV1 {
    timebase: UniformTimebaseV1,
    receive: Vec<Volts>,
    samples_per_ui: NonZeroUsize,
    frontend: RxStagesV1,
}

/// Caller-supplied preparation for a future receiver algorithm.
///
/// No method in this crate evaluates DFE feedback, recovers a clock, makes a
/// decision, or computes BER. The values deliberately have no default.
#[derive(Clone, Debug, JsonSchema, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WireReceiverSemanticsV1 {
    pub schema: String,
    pub known_bits: WireKnownBitsV1,
    pub dfe: WireFixedDfeCoefficientsV1,
    pub clock: WireClockRecoveryPlanV1,
    pub ber: WireBerWindowV1,
}

#[derive(Clone, Debug, JsonSchema, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WireKnownBitsV1 {
    pub bits: Vec<bool>,
    pub positive_voltage_is_one: bool,
}

#[derive(Clone, Debug, JsonSchema, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WireFixedDfeCoefficientsV1 {
    pub coefficients: Vec<f64>,
    pub cursor_index: usize,
}

#[derive(Clone, Debug, JsonSchema, PartialEq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum WireClockRecoveryPlanV1 {
    ExplicitSampleIndices { sample_indices: Vec<usize> },
}

#[derive(Clone, Debug, JsonSchema, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WireBerWindowV1 {
    pub start_symbol: usize,
    pub symbol_count: usize,
    pub decision_threshold_volts: f64,
    pub ties: WireDecisionTiePolicyV1,
}

#[derive(Clone, Debug, JsonSchema, PartialEq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum WireDecisionTiePolicyV1 {
    Reject,
}

#[derive(Clone, Debug, PartialEq)]
pub struct ReceiverSemanticsV1 {
    known_bits: Vec<bool>,
    positive_voltage_is_one: bool,
    dfe_coefficients: Vec<FiniteF64>,
    dfe_cursor_index: usize,
    clock_sample_indices: Vec<usize>,
    ber_start_symbol: usize,
    ber_symbol_count: NonZeroUsize,
    decision_threshold: Volts,
}

impl ReceiverSemanticsV1 {
    pub fn known_bits(&self) -> &[bool] {
        &self.known_bits
    }

    pub fn positive_voltage_is_one(&self) -> bool {
        self.positive_voltage_is_one
    }

    pub fn dfe_coefficients(&self) -> &[FiniteF64] {
        &self.dfe_coefficients
    }

    pub fn dfe_cursor_index(&self) -> usize {
        self.dfe_cursor_index
    }

    pub fn clock_sample_indices(&self) -> &[usize] {
        &self.clock_sample_indices
    }

    pub fn ber_start_symbol(&self) -> usize {
        self.ber_start_symbol
    }

    pub fn ber_symbol_count(&self) -> NonZeroUsize {
        self.ber_symbol_count
    }

    pub fn decision_threshold(&self) -> Volts {
        self.decision_threshold
    }
}

impl TryFrom<WireReceiverSemanticsV1> for ReceiverSemanticsV1 {
    type Error = ContractError;

    fn try_from(value: WireReceiverSemanticsV1) -> Result<Self, Self::Error> {
        require_receiver_semantics_schema(&value.schema)?;
        if value.known_bits.bits.is_empty() {
            return Err(ReceiverSemanticContractError::EmptyKnownBits.into());
        }
        if value.dfe.coefficients.is_empty() {
            return Err(ReceiverSemanticContractError::EmptyDfeCoefficients.into());
        }
        if value.dfe.cursor_index >= value.dfe.coefficients.len() {
            return Err(ReceiverSemanticContractError::InvalidDfeCursor.into());
        }
        let dfe_coefficients = value
            .dfe
            .coefficients
            .into_iter()
            .map(|value| FiniteF64::try_new(value, "DFE coefficient"))
            .collect::<Result<Vec<_>, _>>()?;
        let clock_sample_indices = match value.clock {
            WireClockRecoveryPlanV1::ExplicitSampleIndices { sample_indices } => sample_indices,
        };
        if clock_sample_indices.is_empty() {
            return Err(ReceiverSemanticContractError::EmptyClockPlan.into());
        }
        if clock_sample_indices
            .windows(2)
            .any(|pair| pair[0] >= pair[1])
        {
            return Err(ReceiverSemanticContractError::NonIncreasingClockSamples.into());
        }
        let ber_symbol_count = NonZeroUsize::new(value.ber.symbol_count)
            .ok_or(ReceiverSemanticContractError::EmptyBerWindow)?;
        let ber_end = value
            .ber
            .start_symbol
            .checked_add(ber_symbol_count.get())
            .ok_or(ReceiverSemanticContractError::BerWindowOverflow)?;
        if ber_end > value.known_bits.bits.len() {
            return Err(ReceiverSemanticContractError::BerWindowExceedsKnownBits.into());
        }
        Ok(Self {
            known_bits: value.known_bits.bits,
            positive_voltage_is_one: value.known_bits.positive_voltage_is_one,
            dfe_coefficients,
            dfe_cursor_index: value.dfe.cursor_index,
            clock_sample_indices,
            ber_start_symbol: value.ber.start_symbol,
            ber_symbol_count,
            decision_threshold: Volts::try_new(value.ber.decision_threshold_volts)?,
        })
    }
}

impl ReceiverInputV1 {
    pub fn try_new(
        timebase: UniformTimebaseV1,
        receive: Vec<Volts>,
        samples_per_ui: usize,
        frontend: RxStagesV1,
    ) -> Result<Self, ReceiverContractError> {
        if timebase.sample_interval().get() != 1.0e-12 || timebase.sample_count().get() != 1024 {
            return Err(ReceiverContractError::UnsupportedProfileTimebase);
        }
        let samples_per_ui = NonZeroUsize::new(samples_per_ui)
            .ok_or(ReceiverContractError::UnsupportedSamplesPerUi)?;
        if samples_per_ui.get() != 8 {
            return Err(ReceiverContractError::UnsupportedSamplesPerUi);
        }
        if receive.len() != timebase.sample_count().get() {
            return Err(ReceiverContractError::SampleLengthMismatch);
        }
        Ok(Self {
            timebase,
            receive,
            samples_per_ui,
            frontend,
        })
    }

    pub fn timebase(&self) -> UniformTimebaseV1 {
        self.timebase
    }

    pub fn receive(&self) -> &[Volts] {
        &self.receive
    }

    pub fn samples_per_ui(&self) -> NonZeroUsize {
        self.samples_per_ui
    }

    pub fn frontend(&self) -> RxStagesV1 {
        self.frontend
    }
}

impl TryFrom<WireReceiverInputV1> for ReceiverInputV1 {
    type Error = ContractError;

    fn try_from(value: WireReceiverInputV1) -> Result<Self, Self::Error> {
        require_receiver_schema(&value.schema)?;
        let timebase = UniformTimebaseV1::try_new(
            Seconds::try_new(value.timebase.start_seconds)?,
            Seconds::try_new(value.timebase.sample_interval_seconds)?,
            value.timebase.sample_count,
        )?;
        let receive = value
            .receive_volts
            .into_iter()
            .map(Volts::try_new)
            .collect::<Result<Vec<_>, _>>()?;
        let frontend = match value.frontend {
            WireRxStagesV1 {
                ctle: WireCtleStageV1::Bypass,
                ffe: WireFfeStageV1::Bypass,
            } => RxStagesV1::bypass(),
        };
        Self::try_new(timebase, receive, value.samples_per_ui, frontend).map_err(Into::into)
    }
}

impl From<&ReceiverInputV1> for WireReceiverInputV1 {
    fn from(value: &ReceiverInputV1) -> Self {
        Self {
            schema: RECEIVER_INPUT_SCHEMA.to_owned(),
            timebase: WireUniformTimebaseV1 {
                start_seconds: value.timebase().start().get(),
                sample_interval_seconds: value.timebase().sample_interval().get(),
                sample_count: value.timebase().sample_count().get(),
            },
            receive_volts: value.receive().iter().map(|sample| sample.get()).collect(),
            samples_per_ui: value.samples_per_ui().get(),
            frontend: WireRxStagesV1 {
                ctle: WireCtleStageV1::Bypass,
                ffe: WireFfeStageV1::Bypass,
            },
        }
    }
}

pub fn parse_receiver_input_v1(input: &[u8]) -> Result<ReceiverInputV1, ContractError> {
    serde_json::from_slice::<WireReceiverInputV1>(input)
        .map_err(|error| ContractError::Json(error.to_string()))?
        .try_into()
}

pub fn parse_receiver_semantics_v1(input: &[u8]) -> Result<ReceiverSemanticsV1, ContractError> {
    serde_json::from_slice::<WireReceiverSemanticsV1>(input)
        .map_err(|error| ContractError::Json(error.to_string()))?
        .try_into()
}

pub fn parse_project_plan_v1(input: &[u8]) -> Result<WireProjectPlanV1, ContractError> {
    let plan: WireProjectPlanV1 =
        serde_json::from_slice(input).map_err(|error| ContractError::Json(error.to_string()))?;
    plan.validate_boundary()?;
    Ok(plan)
}

pub fn parse_tran_rc_pulse_request_v1(input: &[u8]) -> Result<TranRcPulseRequestV1, ContractError> {
    let request: TranRcPulseRequestV1 =
        serde_json::from_slice(input).map_err(|error| ContractError::Json(error.to_string()))?;
    if request.schema != TRAN_RC_PULSE_REQUEST_SCHEMA
        || !valid_request_id(&request.request_id)
        || !is_exact_rc_pulse_profile(&request)
    {
        return Err(ContractError::Version);
    }
    Ok(request)
}

fn is_exact_rc_pulse_profile(request: &TranRcPulseRequestV1) -> bool {
    request.resistance_ohms == 1.0e3
        && request.capacitance_farads == 1.0e-6
        && request.initial_voltage_out_volts == 0.0
        && request.output_times_seconds == [0.0, 1.0e-6, 2.0e-6, 3.0e-6]
        && request.pulse
            == TranPulseV1 {
                voltage_low_volts: 0.0,
                voltage_high_volts: 1.0,
                delay_seconds: 1.0e-6,
                rise_seconds: 1.0e-9,
                fall_seconds: 1.0e-9,
                width_seconds: 1.0e-5,
                period_seconds: 2.0e-5,
            }
}

pub fn validate_request_v1(input: &[u8]) -> Result<(), ContractError> {
    let request: ValidationRequestV1 =
        serde_json::from_slice(input).map_err(|error| ContractError::Json(error.to_string()))?;
    if request.schema != VALIDATION_REQUEST_SCHEMA || !valid_request_id(&request.request_id) {
        return Err(ContractError::Version);
    }
    let _: Waveform = request.subject.try_into()?;
    Ok(())
}

#[derive(Clone, Debug, JsonSchema, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WireSpectrumV1 {
    pub schema: String,
    pub axis: WireAxisV1,
    pub bins: Vec<WireComplexV1>,
}

impl TryFrom<WireComplexTensorV1> for ComplexTensor {
    type Error = ContractError;
    fn try_from(value: WireComplexTensorV1) -> Result<Self, Self::Error> {
        value
            .values
            .into_iter()
            .map(TryInto::try_into)
            .collect::<Result<Vec<Complex64>, ContractError>>()?
            .pipe(|values| ComplexTensor::try_new(value.shape, values))
            .map_err(Into::into)
    }
}

impl TryFrom<WireWaveformV1> for Waveform {
    type Error = ContractError;
    fn try_from(value: WireWaveformV1) -> Result<Self, Self::Error> {
        require_schema(&value.schema)?;
        let axis = seconds_axis(value.axis)?;
        value
            .samples
            .into_iter()
            .map(Volts::try_new)
            .collect::<Result<Vec<_>, _>>()?
            .pipe(|samples| Waveform::try_new(axis, samples))
            .map_err(Into::into)
    }
}

impl From<&Waveform> for WireWaveformV1 {
    fn from(value: &Waveform) -> Self {
        Self {
            schema: "sipi.contract.v1".to_owned(),
            axis: seconds_axis_wire(value.axis()),
            samples: value.samples().iter().map(|sample| sample.get()).collect(),
        }
    }
}

impl TryFrom<WireSpectrumV1> for Spectrum {
    type Error = ContractError;
    fn try_from(value: WireSpectrumV1) -> Result<Self, Self::Error> {
        require_schema(&value.schema)?;
        let axis = hertz_axis(value.axis)?;
        value
            .bins
            .into_iter()
            .map(TryInto::try_into)
            .collect::<Result<Vec<Complex64>, ContractError>>()?
            .pipe(|bins| Spectrum::try_new(axis, bins))
            .map_err(Into::into)
    }
}

impl From<&Spectrum> for WireSpectrumV1 {
    fn from(value: &Spectrum) -> Self {
        Self {
            schema: "sipi.contract.v1".to_owned(),
            axis: hertz_axis_wire(value.axis()),
            bins: value
                .bins()
                .iter()
                .map(|bin| WireComplexV1 {
                    real: bin.real(),
                    imaginary: bin.imaginary(),
                })
                .collect(),
        }
    }
}

pub fn parse_waveform_v1(input: &[u8]) -> Result<Waveform, ContractError> {
    serde_json::from_slice::<WireWaveformV1>(input)
        .map_err(|error| ContractError::Json(error.to_string()))?
        .try_into()
}

pub fn deterministic_json<T: Serialize>(value: &T) -> Result<Vec<u8>, ContractError> {
    serde_json::to_vec(value).map_err(|error| ContractError::Json(error.to_string()))
}

/// Returns a minimal, product-owned request for an admitted stdin command.
/// It contains no filesystem path, external asset, or computed result.
pub fn product_example_request_json_v1(command_id: &str) -> Result<Option<Vec<u8>>, ContractError> {
    match command_id {
        "validate" => deterministic_json(&ValidationRequestV1 {
            schema: VALIDATION_REQUEST_SCHEMA.to_owned(),
            request_id: "example-validation-1".to_owned(),
            subject: WireWaveformV1 {
                schema: "sipi.contract.v1".to_owned(),
                axis: WireAxisV1::Explicit {
                    values: vec![0.0, 1.0],
                },
                samples: vec![0.0, 1.0],
            },
        })
        .map(Some),
        "tran.run" => deterministic_json(&TranRcPulseRequestV1 {
            schema: TRAN_RC_PULSE_REQUEST_SCHEMA.to_owned(),
            request_id: "example-rc-pulse-1".to_owned(),
            resistance_ohms: 1_000.0,
            capacitance_farads: 1.0e-6,
            initial_voltage_out_volts: 0.0,
            output_times_seconds: vec![0.0, 1.0e-6, 2.0e-6, 3.0e-6],
            pulse: TranPulseV1 {
                voltage_low_volts: 0.0,
                voltage_high_volts: 1.0,
                delay_seconds: 1.0e-6,
                rise_seconds: 1.0e-9,
                fall_seconds: 1.0e-9,
                width_seconds: 1.0e-5,
                period_seconds: 2.0e-5,
            },
        })
        .map(Some),
        "link.run" => deterministic_json(&WireLinkCausalFirRequestV1 {
            schema: LINK_CAUSAL_FIR_REQUEST_SCHEMA.to_owned(),
            request_id: "example-causal-fir-1".to_owned(),
            plan: WireLinkPlanV1 {
                schema: LINK_PLAN_SCHEMA.to_owned(),
                timebase: WireUniformTimebaseV1 {
                    start_seconds: 0.0,
                    sample_interval_seconds: 1.0,
                    sample_count: 2,
                },
                tx: WireTxStageV1::DirectLaunch,
                stimulus_volts: vec![1.0, 2.0],
                channel: WireLinkChannelV1::CausalFir {
                    sample_interval_seconds: 1.0,
                    gain_v_per_v: vec![3.0, 4.0],
                },
                rx: WireRxStagesV1 {
                    ctle: WireCtleStageV1::Bypass,
                    ffe: WireFfeStageV1::Bypass,
                },
            },
            limits: WireLinkExecutionLimitsV1 {
                max_output_samples: 8,
                max_multiply_accumulates: 8,
            },
        })
        .map(Some),
        "ibis.inspect" => deterministic_json(&WireIbisInspectRequestV1 {
            schema: IBIS_INSPECT_REQUEST_SCHEMA.to_owned(),
            source: WireIbisInspectSourceV1 {
                encoding: "utf-8".to_owned(),
                text: "[IBIS Ver] 7.1\n[Model] product_example\n".to_owned(),
            },
        })
        .map(Some),
        "ibis.dc-evaluate" => deterministic_json(&WireIbisDcEvaluateRequestV1 {
            schema: IBIS_DC_EVALUATE_REQUEST_SCHEMA.to_owned(),
            source: WireIbisInspectSourceV1 {
                encoding: "utf-8".to_owned(),
                text: "[IBIS Ver] 7.1\n[Model] product_input\nModel_type Input\nC_comp 1pF\n[GND_clamp]\n-1V -1A\n1V 1A\n[POWER_clamp]\n-1V 1A\n1V -1A\n".to_owned(),
            },
            selection: WireIbisDcSelectionV1 {
                ibis_version: "7.1".to_owned(),
                model_selector: "product_input".to_owned(),
                corner: "typical".to_owned(),
            },
            probe: WireIbisDcProbeV1 {
                gnd_clamp_drive_volts: 0.5,
                power_clamp_drive_volts: 0.0,
            },
        })
        .map(Some),
        "ibis.quasi-static-evaluate" => {
            deterministic_json(&WireIbisQuasiStaticEvaluateRequestV1 {
                schema: IBIS_QUASI_STATIC_EVALUATE_REQUEST_SCHEMA.to_owned(),
                source: WireIbisInspectSourceV1 {
                    encoding: "utf-8".to_owned(),
                    text: "[IBIS Ver] 7.1\n[Model] product_input\nModel_type Input\nC_comp 1pF\n[GND_clamp]\n-1V -1A\n1V 1A\n[POWER_clamp]\n-1V 1A\n1V -1A\n".to_owned(),
                },
                selection: WireIbisDcSelectionV1 {
                    ibis_version: "7.1".to_owned(),
                    model_selector: "product_input".to_owned(),
                    corner: "typical".to_owned(),
                },
                probe: WireIbisQuasiStaticProbeV1 {
                    gnd_clamp_drive_volts: 0.5,
                    power_clamp_drive_volts: 0.0,
                    sig_to_ref_slope_volts_per_second: 1.0e9,
                },
            })
            .map(Some)
        }
        "rx-load.differential-rc-evaluate" => {
            deterministic_json(&WireRxLoadDifferentialRcEvaluateRequestV1 {
                schema: RX_LOAD_DIFFERENTIAL_RC_EVALUATE_REQUEST_SCHEMA.to_owned(),
                probe: WireRxLoadDifferentialRcProbeV1 {
                    p_to_ref_volts: 0.5,
                    n_to_ref_volts: -0.5,
                    p_to_ref_slope_volts_per_second: 1.0e9,
                    n_to_ref_slope_volts_per_second: -1.0e9,
                },
            })
            .map(Some)
        }
        "project.run" => deterministic_json(&WireFixedProjectRunRequestV1 {
            schema: FIXED_PROJECT_RUN_REQUEST_SCHEMA.to_owned(),
            plan: WireProjectPlanV1 {
                schema: PROJECT_PLAN_SCHEMA.to_owned(),
                project_id: "example-fixed-project-1".to_owned(),
                seed_hex: "00".repeat(32),
                resource_policy: WireProjectResourcePolicyV1 {
                    timeout_millis: 1_000,
                    max_work_units: 100,
                    max_accounted_bytes: 2_048,
                },
                inputs: vec![WireProjectInputV1 {
                    id: "binding".to_owned(),
                    contract: "sipi.project.tran-rc-pulse-to-causal-fir-binding.v1".to_owned(),
                }],
                nodes: vec![WireProjectNodeV1 {
                    id: "run".to_owned(),
                    kind: "project.tran-rc-pulse-to-causal-fir".to_owned(),
                }],
                edges: vec![WireProjectEdgeV1 {
                    from: WireProjectEdgeSourceV1::ProjectInput {
                        input_id: "binding".to_owned(),
                    },
                    to: WireProjectPortRefV1 {
                        node_id: "run".to_owned(),
                        port: "binding".to_owned(),
                    },
                    contract: "sipi.project.tran-rc-pulse-to-causal-fir-binding.v1".to_owned(),
                }],
                requested_outputs: vec![WireProjectOutputRefV1 {
                    node_id: "run".to_owned(),
                    port: "received".to_owned(),
                    contract: "sipi.link.causal-fir-result.v1".to_owned(),
                }],
            },
            consumer: WireFixedProjectCausalFirConsumerV1 {
                sample_interval_seconds: 1.0e-6,
                gain_v_per_v: vec![1.0],
                max_output_samples: 8,
                max_multiply_accumulates: 16,
            },
        })
        .map(Some),
        _ => Ok(None),
    }
}

pub fn capability_schema_json() -> Result<Vec<u8>, ContractError> {
    deterministic_json(&schema_for!(CapabilityCatalogV1))
}

pub fn validation_request_schema_json() -> Result<Vec<u8>, ContractError> {
    deterministic_json(&schema_for!(ValidationRequestV1))
}

pub fn tran_rc_pulse_request_schema_json() -> Result<Vec<u8>, ContractError> {
    deterministic_json(&schema_for!(TranRcPulseRequestV1))
}

pub fn link_plan_schema_json() -> Result<Vec<u8>, ContractError> {
    deterministic_json(&schema_for!(WireLinkPlanV1))
}

pub fn link_causal_fir_request_schema_json() -> Result<Vec<u8>, ContractError> {
    deterministic_json(&schema_for!(WireLinkCausalFirRequestV1))
}

pub fn ibis_inspect_request_schema_json() -> Result<Vec<u8>, ContractError> {
    deterministic_json(&schema_for!(WireIbisInspectRequestV1))
}

pub fn ibis_dc_evaluate_request_schema_json() -> Result<Vec<u8>, ContractError> {
    deterministic_json(&schema_for!(WireIbisDcEvaluateRequestV1))
}

pub fn ibis_quasi_static_evaluate_request_schema_json() -> Result<Vec<u8>, ContractError> {
    deterministic_json(&schema_for!(WireIbisQuasiStaticEvaluateRequestV1))
}

pub fn rx_load_differential_rc_evaluate_request_schema_json() -> Result<Vec<u8>, ContractError> {
    deterministic_json(&schema_for!(WireRxLoadDifferentialRcEvaluateRequestV1))
}

pub fn artifact_report_request_schema_json() -> Result<Vec<u8>, ContractError> {
    deterministic_json(&schema_for!(WireArtifactReportRequestV1))
}

pub fn receiver_input_schema_json() -> Result<Vec<u8>, ContractError> {
    deterministic_json(&schema_for!(WireReceiverInputV1))
}

pub fn receiver_semantics_schema_json() -> Result<Vec<u8>, ContractError> {
    deterministic_json(&schema_for!(WireReceiverSemanticsV1))
}

pub fn project_plan_schema_json() -> Result<Vec<u8>, ContractError> {
    deterministic_json(&schema_for!(WireProjectPlanV1))
}

pub fn fixed_project_run_request_schema_json() -> Result<Vec<u8>, ContractError> {
    deterministic_json(&schema_for!(WireFixedProjectRunRequestV1))
}

fn require_schema(schema: &str) -> Result<(), ContractError> {
    if schema == "sipi.contract.v1" {
        Ok(())
    } else {
        Err(ContractError::Version)
    }
}

fn token(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 128
        && value.bytes().all(|byte| {
            byte.is_ascii_lowercase() || byte.is_ascii_digit() || matches!(byte, b'.' | b'_' | b'-')
        })
}

fn valid_artifact_id(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 128
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_'))
}

fn require_link_schema(schema: &str) -> Result<(), ContractError> {
    if schema == LINK_PLAN_SCHEMA {
        Ok(())
    } else {
        Err(ContractError::Version)
    }
}

fn require_link_causal_fir_request_schema(schema: &str) -> Result<(), ContractError> {
    if schema == LINK_CAUSAL_FIR_REQUEST_SCHEMA {
        Ok(())
    } else {
        Err(ContractError::Version)
    }
}

fn require_receiver_schema(schema: &str) -> Result<(), ContractError> {
    if schema == RECEIVER_INPUT_SCHEMA {
        Ok(())
    } else {
        Err(ContractError::Version)
    }
}

fn require_receiver_semantics_schema(schema: &str) -> Result<(), ContractError> {
    if schema == RECEIVER_SEMANTICS_SCHEMA {
        Ok(())
    } else {
        Err(ContractError::Version)
    }
}

fn valid_request_id(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'.' | b'_' | b'-'))
}

fn seconds_axis(value: WireAxisV1) -> Result<Axis<Seconds>, ContractError> {
    match value {
        WireAxisV1::Explicit { values } => values
            .into_iter()
            .map(Seconds::try_new)
            .collect::<Result<Vec<_>, _>>()?
            .pipe(Axis::explicit)
            .map_err(Into::into),
        WireAxisV1::Uniform { start, step, count } => Ok(Axis::uniform(
            Seconds::try_new(start)?,
            sipi_types::NonZeroStep::try_new(Seconds::try_new(step)?)?,
            std::num::NonZeroUsize::new(count).ok_or(TypeError::Empty { kind: "axis count" })?,
        )),
    }
}

fn hertz_axis(value: WireAxisV1) -> Result<Axis<Hertz>, ContractError> {
    match value {
        WireAxisV1::Explicit { values } => values
            .into_iter()
            .map(Hertz::try_new)
            .collect::<Result<Vec<_>, _>>()?
            .pipe(Axis::explicit)
            .map_err(Into::into),
        WireAxisV1::Uniform { start, step, count } => Ok(Axis::uniform(
            Hertz::try_new(start)?,
            sipi_types::NonZeroStep::try_new(Hertz::try_new(step)?)?,
            std::num::NonZeroUsize::new(count).ok_or(TypeError::Empty { kind: "axis count" })?,
        )),
    }
}

fn seconds_axis_wire(value: &Axis<Seconds>) -> WireAxisV1 {
    match value.view() {
        sipi_types::AxisView::Uniform { start, step, count } => WireAxisV1::Uniform {
            start: start.get(),
            step: step.get(),
            count: count.get(),
        },
        sipi_types::AxisView::Explicit(values) => WireAxisV1::Explicit {
            values: values.iter().map(|item| item.get()).collect(),
        },
    }
}

fn hertz_axis_wire(value: &Axis<Hertz>) -> WireAxisV1 {
    match value.view() {
        sipi_types::AxisView::Uniform { start, step, count } => WireAxisV1::Uniform {
            start: start.get(),
            step: step.get(),
            count: count.get(),
        },
        sipi_types::AxisView::Explicit(values) => WireAxisV1::Explicit {
            values: values.iter().map(|item| item.get()).collect(),
        },
    }
}

trait Pipe: Sized {
    fn pipe<T>(self, function: impl FnOnce(Self) -> T) -> T {
        function(self)
    }
}
impl<T> Pipe for T {}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn catalog_is_all_unsupported() {
        let catalog = CapabilityCatalogV1::unsupported();
        assert_eq!(catalog.schema, CAPABILITIES_SCHEMA);
        assert!(
            catalog
                .capabilities
                .iter()
                .all(|item| item.status == "unsupported")
        );
    }

    #[test]
    fn wire_input_runs_through_type_validation() {
        let input = br#"{"schema":"sipi.contract.v1","axis":{"encoding":"explicit","values":[0.0,1.0]},"samples":[1.0,2.0]}"#;
        assert!(parse_waveform_v1(input).is_ok());
        assert!(parse_waveform_v1(br#"{"schema":"sipi.contract.v1","axis":{"encoding":"explicit","values":[0.0,1.0]},"samples":[1.0]}"#).is_err());
        assert!(parse_waveform_v1(br#"{"schema":"sipi.contract.v1","axis":{"encoding":"explicit","values":[0.0]},"samples":[1.0],"extra":true}"#).is_err());
    }

    #[test]
    fn schema_and_deterministic_profile_are_available() {
        let first = deterministic_json(&CapabilityCatalogV1::unsupported()).unwrap();
        assert_eq!(
            first,
            deterministic_json(&CapabilityCatalogV1::unsupported()).unwrap()
        );
        assert!(capability_schema_json().unwrap().starts_with(b"{"));
    }

    #[test]
    fn project_plan_boundary_requires_a_versioned_seed_and_policy() {
        let valid = br#"{"schema":"sipi.project.v1","project_id":"project-1","seed_hex":"0000000000000000000000000000000000000000000000000000000000000000","resource_policy":{"timeout_millis":1,"max_work_units":1,"max_accounted_bytes":1},"inputs":[],"nodes":[{"id":"tran","kind":"tran.rc_pulse"}],"edges":[],"requested_outputs":[{"node_id":"tran","port":"result","contract":"sipi.tran.rc-pulse-result.v1"}]}"#;
        assert!(parse_project_plan_v1(valid).is_ok());
        assert_eq!(
            parse_project_plan_v1(
                br#"{"schema":"sipi.project.v0","project_id":"project-1","seed_hex":"0000000000000000000000000000000000000000000000000000000000000000","resource_policy":{"timeout_millis":1,"max_work_units":1,"max_accounted_bytes":1},"inputs":[],"nodes":[{"id":"tran","kind":"tran.rc_pulse"}],"edges":[],"requested_outputs":[{"node_id":"tran","port":"result","contract":"sipi.tran.rc-pulse-result.v1"}]}"#
            ),
            Err(ContractError::Project(ProjectContractError::Version))
        );
        assert!(parse_project_plan_v1(
            br#"{"schema":"sipi.project.v1","project_id":"project-1","seed_hex":"not-hex","resource_policy":{"timeout_millis":1,"max_work_units":1,"max_accounted_bytes":1},"inputs":[],"nodes":[{"id":"tran","kind":"tran.rc_pulse"}],"edges":[],"requested_outputs":[{"node_id":"tran","port":"result","contract":"sipi.tran.rc-pulse-result.v1"]}"#
        )
        .is_err());
        assert!(
            project_plan_schema_json()
                .expect("schema")
                .starts_with(b"{")
        );
    }

    #[test]
    fn fixed_project_run_request_requires_its_versioned_consumer_policy() {
        let example = product_example_request_json_v1("project.run")
            .expect("example")
            .expect("project example");
        let request = parse_fixed_project_run_request_v1(&example).expect("request");
        assert_eq!(request.plan().project_id, "example-fixed-project-1");
        assert_eq!(request.channel().sample_interval().get(), 1.0e-6);
        assert_eq!(request.limits().max_output_samples().get(), 8);
        assert!(parse_fixed_project_run_request_v1(
            br#"{"schema":"sipi.project.fixed-tran-causal-fir-run-request.v0","plan":{},"consumer":{}}"#
        )
        .is_err());
    }

    #[test]
    fn tracked_fixed_project_run_schema_baseline_is_exactly_the_registered_export() {
        let baseline = include_bytes!(
            "../schemas/sipi.project.fixed-tran-causal-fir-run-request.v1.schema.json"
        );
        let exported = fixed_project_run_request_schema_json().expect("schema");
        assert_eq!(baseline.strip_suffix(b"\n").unwrap_or(baseline), exported);
    }

    #[test]
    fn tracked_ibis_dc_evaluate_schema_baseline_is_exactly_the_registered_export() {
        let baseline =
            include_bytes!("../schemas/sipi.ibis.input-typ-dc-evaluate.request.v1.schema.json");
        let exported = ibis_dc_evaluate_request_schema_json().expect("schema");
        assert_eq!(baseline.strip_suffix(b"\n").unwrap_or(baseline), exported);
    }

    #[test]
    fn tracked_ibis_quasi_static_evaluate_schema_baseline_is_exactly_the_registered_export() {
        let baseline = include_bytes!(
            "../schemas/sipi.ibis.input-typ-quasi-static-evaluate.request.v1.schema.json"
        );
        let exported = ibis_quasi_static_evaluate_request_schema_json().expect("schema");
        assert_eq!(baseline.strip_suffix(b"\n").unwrap_or(baseline), exported);
    }

    #[test]
    fn tracked_rx_load_differential_rc_evaluate_schema_baseline_is_exactly_the_registered_export() {
        let baseline = include_bytes!(
            "../schemas/sipi.rx-load.selected-differential-rc-evaluate.request.v1.schema.json"
        );
        let exported = rx_load_differential_rc_evaluate_request_schema_json().expect("schema");
        assert_eq!(baseline.strip_suffix(b"\n").unwrap_or(baseline), exported);
    }

    #[test]
    fn tracked_project_schema_baseline_is_exactly_the_registered_export() {
        let baseline = include_bytes!("../schemas/sipi.project.v1.schema.json");
        assert!(baseline.ends_with(b"\n"));
        assert_eq!(
            project_plan_schema_json().expect("schema"),
            &baseline[..baseline.len() - 1]
        );
    }

    #[test]
    fn tracked_schema_baseline_is_exactly_the_registered_export() {
        let baseline = include_bytes!("../schemas/sipi.capabilities.v1.schema.json");
        assert!(baseline.ends_with(b"\n"));
        assert_eq!(
            capability_schema_json().expect("schema"),
            &baseline[..baseline.len() - 1]
        );
    }

    #[test]
    fn tracked_validation_request_schema_baseline_is_exactly_the_registered_export() {
        let baseline = include_bytes!("../schemas/sipi.validation-request.v1.schema.json");
        let exported = validation_request_schema_json().expect("schema");
        assert_eq!(baseline.strip_suffix(b"\n").unwrap_or(baseline), exported);
    }

    #[test]
    fn tracked_artifact_report_request_schema_baseline_is_exactly_the_registered_export() {
        let baseline = include_bytes!("../schemas/sipi.artifact-report-request.v1.schema.json");
        let exported = artifact_report_request_schema_json().expect("schema");
        assert_eq!(baseline.strip_suffix(b"\n").unwrap_or(baseline), exported);
    }

    #[test]
    fn tracked_tran_request_schema_baseline_is_exactly_the_registered_export() {
        let baseline = include_bytes!("../schemas/sipi.tran.rc-pulse-request.v1.schema.json");
        let exported = tran_rc_pulse_request_schema_json().expect("schema");
        assert_eq!(baseline.strip_suffix(b"\n").unwrap_or(baseline), exported);
    }

    #[test]
    fn validation_request_uses_the_existing_validated_waveform_path() {
        let valid = br#"{"schema":"sipi.validation-request.v1","request_id":"request-1","subject":{"schema":"sipi.contract.v1","axis":{"encoding":"explicit","values":[0.0,1.0]},"samples":[1.0,2.0]}}"#;
        assert!(validate_request_v1(valid).is_ok());
        assert!(validate_request_v1(br#"{"schema":"sipi.validation-request.v1","request_id":"bad/request","subject":{"schema":"sipi.contract.v1","axis":{"encoding":"explicit","values":[0.0]},"samples":[1.0]}}"#).is_err());
        assert!(validate_request_v1(br#"{"schema":"sipi.validation-request.v1","request_id":"request-1","subject":{"schema":"sipi.contract.v1","axis":{"encoding":"explicit","values":[0.0]},"samples":[1.0],"extra":true}}"#).is_err());
    }

    #[test]
    fn ibis_inspect_request_is_utf8_text_only_and_strict() {
        let valid = br#"{"schema":"sipi.ibis.inspect.request.v1","source":{"encoding":"utf-8","text":"[IBIS Ver] 7.1\n"}}"#;
        assert_eq!(
            parse_ibis_inspect_request_v1(valid)
                .expect("request")
                .text(),
            "[IBIS Ver] 7.1\n"
        );
        assert_eq!(
            parse_ibis_inspect_request_v1(
                br#"{"schema":"sipi.ibis.inspect.request.v1","source":{"encoding":"binary","text":"x"}}"#
            ),
            Err(ContractError::IbisInspect(
                IbisInspectContractError::UnsupportedEncoding
            ))
        );
        assert!(parse_ibis_inspect_request_v1(
            br#"{"schema":"sipi.ibis.inspect.request.v1","source":{"encoding":"utf-8","text":"x","file":"sample.ibs"}}"#
        )
        .is_err());
        assert!(
            ibis_inspect_request_schema_json()
                .expect("schema")
                .starts_with(b"{")
        );
    }

    #[test]
    fn ibis_dc_evaluate_request_is_typical_only_and_strict() {
        let valid = br#"{"schema":"sipi.ibis.input-typ-dc-evaluate.request.v1","source":{"encoding":"utf-8","text":"[IBIS Ver] 7.1\n"},"selection":{"ibis_version":"7.1","model_selector":"product_input","corner":"typical"},"probe":{"gnd_clamp_drive_volts":0.0,"power_clamp_drive_volts":1.0}}"#;
        let request = parse_ibis_dc_evaluate_request_v1(valid).expect("valid request");
        assert_eq!(request.ibis_version(), "7.1");
        assert_eq!(request.model_selector(), "product_input");
        assert_eq!(request.gnd_clamp_drive_volts().get(), 0.0);
        assert!(matches!(
            parse_ibis_dc_evaluate_request_v1(
                br#"{"schema":"sipi.ibis.input-typ-dc-evaluate.request.v1","source":{"encoding":"utf-8","text":"x"},"selection":{"ibis_version":"7.1","model_selector":"m","corner":"minimum"},"probe":{"gnd_clamp_drive_volts":0.0,"power_clamp_drive_volts":0.0}}"#
            ),
            Err(ContractError::IbisDcEvaluate(
                IbisDcEvaluateContractError::UnsupportedCorner
            ))
        ));
        assert!(parse_ibis_dc_evaluate_request_v1(
            br#"{"schema":"sipi.ibis.input-typ-dc-evaluate.request.v1","source":{"encoding":"utf-8","text":"x","path":"sample.ibs"},"selection":{"ibis_version":"7.1","model_selector":"m","corner":"typical"},"probe":{"gnd_clamp_drive_volts":0.0,"power_clamp_drive_volts":0.0}}"#
        )
        .is_err());
        assert!(parse_ibis_dc_evaluate_request_v1(
            br#"{"schema":"sipi.ibis.input-typ-dc-evaluate.request.v1","source":{"encoding":"utf-8","text":"x"},"selection":{"ibis_version":"7.1","model_selector":"m","corner":"typical"},"probe":{"gnd_clamp_drive_volts":null,"power_clamp_drive_volts":0.0}}"#
        )
        .is_err());
    }

    #[test]
    fn ibis_quasi_static_evaluate_request_requires_a_finite_explicit_slope() {
        let valid = br#"{"schema":"sipi.ibis.input-typ-quasi-static-evaluate.request.v1","source":{"encoding":"utf-8","text":"[IBIS Ver] 7.1\n"},"selection":{"ibis_version":"7.1","model_selector":"product_input","corner":"typical"},"probe":{"gnd_clamp_drive_volts":0.0,"power_clamp_drive_volts":1.0,"sig_to_ref_slope_volts_per_second":-1.0e9}}"#;
        let request = parse_ibis_quasi_static_evaluate_request_v1(valid).expect("valid request");
        assert_eq!(request.sig_to_ref_slope_volts_per_second(), -1.0e9);
        assert!(matches!(
            parse_ibis_quasi_static_evaluate_request_v1(
                br#"{"schema":"sipi.ibis.input-typ-quasi-static-evaluate.request.v1","source":{"encoding":"utf-8","text":"x"},"selection":{"ibis_version":"7.1","model_selector":"m","corner":"typical"},"probe":{"gnd_clamp_drive_volts":0.0,"power_clamp_drive_volts":0.0,"sig_to_ref_slope_volts_per_second":null}}"#
            ),
            Err(ContractError::Json(_))
        ));
        assert!(matches!(
            parse_ibis_quasi_static_evaluate_request_v1(
                br#"{"schema":"sipi.ibis.input-typ-quasi-static-evaluate.request.v1","source":{"encoding":"utf-8","text":"x"},"selection":{"ibis_version":"7.1","model_selector":"m","corner":"maximum"},"probe":{"gnd_clamp_drive_volts":0.0,"power_clamp_drive_volts":0.0,"sig_to_ref_slope_volts_per_second":0.0}}"#
            ),
            Err(ContractError::IbisQuasiStaticEvaluate(
                IbisQuasiStaticEvaluateContractError::UnsupportedCorner
            ))
        ));
        assert!(parse_ibis_quasi_static_evaluate_request_v1(
            br#"{"schema":"sipi.ibis.input-typ-quasi-static-evaluate.request.v1","source":{"encoding":"utf-8","text":"x","file":"sample.ibs"},"selection":{"ibis_version":"7.1","model_selector":"m","corner":"typical"},"probe":{"gnd_clamp_drive_volts":0.0,"power_clamp_drive_volts":0.0,"sig_to_ref_slope_volts_per_second":0.0}}"#
        )
        .is_err());
    }

    #[test]
    fn selected_differential_rc_load_request_is_strict_and_requires_all_probe_terms() {
        let valid = br#"{"schema":"sipi.rx-load.selected-differential-rc-evaluate.request.v1","probe":{"p_to_ref_volts":0.5,"n_to_ref_volts":-0.5,"p_to_ref_slope_volts_per_second":1000000000.0,"n_to_ref_slope_volts_per_second":-1000000000.0}}"#;
        let request = parse_rx_load_differential_rc_evaluate_request_v1(valid).expect("request");
        assert_eq!(request.p_to_ref_volts().get(), 0.5);
        assert_eq!(request.n_to_ref_slope_volts_per_second(), -1.0e9);
        assert!(matches!(
            parse_rx_load_differential_rc_evaluate_request_v1(
                br#"{"schema":"sipi.rx-load.selected-differential-rc-evaluate.request.v1","probe":{"p_to_ref_volts":0.0,"n_to_ref_volts":0.0,"p_to_ref_slope_volts_per_second":null,"n_to_ref_slope_volts_per_second":0.0}}"#
            ),
            Err(ContractError::Json(_))
        ));
        assert!(parse_rx_load_differential_rc_evaluate_request_v1(
            br#"{"schema":"sipi.rx-load.selected-differential-rc-evaluate.request.v1","probe":{"p_to_ref_volts":0.0,"n_to_ref_volts":0.0,"p_to_ref_slope_volts_per_second":0.0,"n_to_ref_slope_volts_per_second":0.0,"resistance_ohms":50.0}}"#
        )
        .is_err());
    }

    #[test]
    fn artifact_report_request_requires_explicit_local_root_and_artifact_identity() {
        let valid = br#"{"schema":"sipi.artifact-report-request.v1","artifact_root":"external-artifacts","artifact_id":"result-1"}"#;
        let request = parse_artifact_report_request_v1(valid).expect("valid report request");
        assert_eq!(request.artifact_root(), "external-artifacts");
        assert_eq!(request.artifact_id(), "result-1");
        for invalid in [
            br#"{"schema":"sipi.artifact-report-request.v1","artifact_root":"https://example.invalid","artifact_id":"result-1"}"#.as_slice(),
            br#"{"schema":"sipi.artifact-report-request.v1","artifact_root":"../outside","artifact_id":"result-1"}"#.as_slice(),
            br#"{"schema":"sipi.artifact-report-request.v1","artifact_root":"root","artifact_id":"../result"}"#.as_slice(),
            br#"{"schema":"sipi.artifact-report-request.v1","artifact_root":"root","artifact_id":"result-1","file":"payload.json"}"#.as_slice(),
        ] {
            assert!(parse_artifact_report_request_v1(invalid).is_err());
        }
    }

    #[test]
    fn tran_rc_pulse_request_is_typed_and_exact_profile_only() {
        let valid = br#"{"schema":"sipi.tran.rc-pulse-request.v1","request_id":"rc-pulse-1","resistance_ohms":1000.0,"capacitance_farads":0.000001,"initial_voltage_out_volts":0.0,"output_times_seconds":[0.0,0.000001,0.000002,0.000003],"pulse":{"voltage_low_volts":0.0,"voltage_high_volts":1.0,"delay_seconds":0.000001,"rise_seconds":0.000000001,"fall_seconds":0.000000001,"width_seconds":0.00001,"period_seconds":0.00002}}"#;
        assert!(parse_tran_rc_pulse_request_v1(valid).is_ok());
        assert!(parse_tran_rc_pulse_request_v1(
            br#"{"schema":"sipi.tran.rc-pulse-request.v1","request_id":"rc-pulse-1","resistance_ohms":999.0,"capacitance_farads":0.000001,"initial_voltage_out_volts":0.0,"output_times_seconds":[0.0,0.000001,0.000002,0.000003],"pulse":{"voltage_low_volts":0.0,"voltage_high_volts":1.0,"delay_seconds":0.000001,"rise_seconds":0.000000001,"fall_seconds":0.000000001,"width_seconds":0.00001,"period_seconds":0.00002}}"#
        )
        .is_err());
        assert!(parse_tran_rc_pulse_request_v1(
            br#"{"schema":"sipi.tran.rc-pulse-request.v1","request_id":"rc-pulse-1","resistance_ohms":1000.0,"capacitance_farads":0.000001,"initial_voltage_out_volts":0.0,"output_times_seconds":[0.0,0.000001,0.000002,0.000003],"pulse":{"voltage_low_volts":0.0,"voltage_high_volts":1.0,"delay_seconds":0.000001,"rise_seconds":0.000000001,"fall_seconds":0.000000001,"width_seconds":0.00001,"period_seconds":0.00002},"legacy_netlist":"rc.cir"}"#
        )
        .is_err());
    }

    #[test]
    fn validated_waveform_round_trips_to_product_wire_shape() {
        let waveform = parse_waveform_v1(
            br#"{"schema":"sipi.contract.v1","axis":{"encoding":"explicit","values":[0.0,1.0]},"samples":[1.0,2.0]}"#,
        )
        .unwrap();

        assert_eq!(
            deterministic_json(&WireWaveformV1::from(&waveform)).unwrap(),
            br#"{"schema":"sipi.contract.v1","axis":{"encoding":"explicit","values":[0.0,1.0]},"samples":[1.0,2.0]}"#,
        );
    }

    #[test]
    fn link_plan_is_typed_and_strictly_causal() {
        let valid = br#"{"schema":"sipi.link-plan.v1","timebase":{"start_seconds":0.0,"sample_interval_seconds":1e-12,"sample_count":3},"tx":{"kind":"direct_launch"},"stimulus_volts":[0.0,1.0,0.0],"channel":{"kind":"causal_fir","sample_interval_seconds":1e-12,"gain_v_per_v":[1.0,0.5]},"rx":{"ctle":{"kind":"bypass"},"ffe":{"kind":"bypass"}}}"#;
        let plan = parse_link_plan_v1(valid).expect("valid Link plan");
        assert_eq!(plan.output_sample_count(), 4);
        assert_eq!(plan.tx(), TxStageV1::DirectLaunch);
        assert_eq!(plan.rx(), RxStagesV1::bypass());
        assert_eq!(
            deterministic_json(&WireLinkPlanV1::from(&plan)).expect("wire"),
            valid
        );
    }

    #[test]
    fn link_plan_rejects_periodic_or_inconsistent_channel_shapes() {
        let valid = br#"{"schema":"sipi.link-plan.v1","timebase":{"start_seconds":0.0,"sample_interval_seconds":1e-12,"sample_count":2},"tx":{"kind":"direct_launch"},"stimulus_volts":[0.0,1.0],"channel":{"kind":"causal_fir","sample_interval_seconds":1e-12,"gain_v_per_v":[1.0]},"rx":{"ctle":{"kind":"bypass"},"ffe":{"kind":"bypass"}}}"#;
        assert!(parse_link_plan_v1(valid).is_ok());
        assert!(parse_link_plan_v1(
            br#"{"schema":"sipi.link-plan.v1","timebase":{"start_seconds":1.0,"sample_interval_seconds":1e-12,"sample_count":2},"tx":{"kind":"direct_launch"},"stimulus_volts":[0.0,1.0],"channel":{"kind":"causal_fir","sample_interval_seconds":1e-12,"gain_v_per_v":[1.0]},"rx":{"ctle":{"kind":"bypass"},"ffe":{"kind":"bypass"}}}"#
        )
        .is_err());
        assert!(parse_link_plan_v1(
            br#"{"schema":"sipi.link-plan.v1","timebase":{"start_seconds":0.0,"sample_interval_seconds":1e-12,"sample_count":2},"tx":{"kind":"direct_launch"},"stimulus_volts":[0.0,1.0],"channel":{"kind":"causal_fir","sample_interval_seconds":2e-12,"gain_v_per_v":[1.0]},"rx":{"ctle":{"kind":"bypass"},"ffe":{"kind":"bypass"}}}"#
        )
        .is_err());
        assert!(parse_link_plan_v1(
            br#"{"schema":"sipi.link-plan.v1","timebase":{"start_seconds":0.0,"sample_interval_seconds":1e-12,"sample_count":2},"tx":{"kind":"direct_launch"},"stimulus_volts":[0.0,1.0],"channel":{"kind":"periodic_kernel","sample_interval_seconds":1e-12,"gain_v_per_v":[1.0]},"rx":{"ctle":{"kind":"bypass"},"ffe":{"kind":"bypass"}}}"#
        )
        .is_err());
        assert!(parse_link_plan_v1(
            br#"{"schema":"sipi.link-plan.v1","timebase":{"start_seconds":0.0,"sample_interval_seconds":1e-12,"sample_count":2},"tx":{"kind":"direct_launch"},"stimulus_volts":[0.0,1.0],"channel":{"kind":"causal_fir","sample_interval_seconds":1e-12,"gain_v_per_v":[]},"rx":{"ctle":{"kind":"bypass"},"ffe":{"kind":"bypass"}}}"#
        )
        .is_err());
    }

    #[test]
    fn link_schema_is_available_from_the_contract_authority() {
        assert!(link_plan_schema_json().expect("schema").starts_with(b"{"));
    }

    #[test]
    fn tracked_link_schema_baseline_is_exactly_the_registered_export() {
        let baseline = include_bytes!("../schemas/sipi.link-plan.v1.schema.json");
        assert!(baseline.ends_with(b"\n"));
        assert_eq!(
            link_plan_schema_json().expect("schema"),
            &baseline[..baseline.len() - 1]
        );
    }

    #[test]
    fn tracked_link_causal_fir_request_schema_baseline_is_exactly_the_registered_export() {
        let baseline = include_bytes!("../schemas/sipi.link.causal-fir-request.v1.schema.json");
        let exported = link_causal_fir_request_schema_json().expect("schema");
        assert_eq!(baseline.strip_suffix(b"\n").unwrap_or(baseline), exported);
    }

    #[test]
    fn tracked_ibis_inspect_schema_baseline_is_exactly_the_registered_export() {
        let baseline = include_bytes!("../schemas/sipi.ibis.inspect.request.v1.schema.json");
        assert!(baseline.ends_with(b"\n"));
        assert_eq!(
            ibis_inspect_request_schema_json().expect("schema"),
            &baseline[..baseline.len() - 1]
        );
    }

    fn required_receiver_wire() -> WireReceiverInputV1 {
        WireReceiverInputV1 {
            schema: RECEIVER_INPUT_SCHEMA.to_owned(),
            timebase: WireUniformTimebaseV1 {
                start_seconds: 0.0,
                sample_interval_seconds: 1.0e-12,
                sample_count: 1024,
            },
            receive_volts: vec![0.0; 1024],
            samples_per_ui: 8,
            frontend: WireRxStagesV1 {
                ctle: WireCtleStageV1::Bypass,
                ffe: WireFfeStageV1::Bypass,
            },
        }
    }

    #[test]
    fn required_receiver_input_is_typed_and_bypass_only() {
        let wire = required_receiver_wire();
        let bytes = deterministic_json(&wire).expect("wire");
        let receiver = parse_receiver_input_v1(&bytes).expect("required receiver input");
        assert_eq!(receiver.receive().len(), 1024);
        assert_eq!(receiver.samples_per_ui().get(), 8);
        assert_eq!(receiver.frontend(), RxStagesV1::bypass());
        assert_eq!(
            deterministic_json(&WireReceiverInputV1::from(&receiver)).unwrap(),
            bytes
        );
    }

    #[test]
    fn required_receiver_input_rejects_profile_drift_and_receiver_knobs() {
        let mut wire = required_receiver_wire();
        wire.timebase.sample_interval_seconds = 2.0e-12;
        assert_eq!(
            ReceiverInputV1::try_from(wire),
            Err(ContractError::Receiver(
                ReceiverContractError::UnsupportedProfileTimebase
            ))
        );
        let mut wire = required_receiver_wire();
        wire.samples_per_ui = 7;
        assert_eq!(
            ReceiverInputV1::try_from(wire),
            Err(ContractError::Receiver(
                ReceiverContractError::UnsupportedSamplesPerUi
            ))
        );
        assert!(parse_receiver_input_v1(
            br#"{"schema":"sipi.receiver-input.v1","timebase":{"start_seconds":0.0,"sample_interval_seconds":1e-12,"sample_count":1024},"receive_volts":[],"samples_per_ui":8,"frontend":{"ctle":{"kind":"bypass"},"ffe":{"kind":"bypass"}},"dfe":{"kind":"legacy"}}"#
        )
        .is_err());
    }

    #[test]
    fn receiver_schema_is_available_from_the_contract_authority() {
        assert!(
            receiver_input_schema_json()
                .expect("schema")
                .starts_with(b"{")
        );
    }

    fn required_receiver_semantics_wire() -> WireReceiverSemanticsV1 {
        WireReceiverSemanticsV1 {
            schema: RECEIVER_SEMANTICS_SCHEMA.to_owned(),
            known_bits: WireKnownBitsV1 {
                bits: vec![false, true, true, false],
                positive_voltage_is_one: true,
            },
            dfe: WireFixedDfeCoefficientsV1 {
                coefficients: vec![0.0, 0.25],
                cursor_index: 0,
            },
            clock: WireClockRecoveryPlanV1::ExplicitSampleIndices {
                sample_indices: vec![3, 11, 19, 27],
            },
            ber: WireBerWindowV1 {
                start_symbol: 1,
                symbol_count: 3,
                decision_threshold_volts: 0.0,
                ties: WireDecisionTiePolicyV1::Reject,
            },
        }
    }

    #[test]
    fn receiver_semantics_require_explicit_inputs_without_an_algorithm() {
        let wire = required_receiver_semantics_wire();
        let semantics = ReceiverSemanticsV1::try_from(wire).expect("explicit inputs");
        assert_eq!(semantics.known_bits(), [false, true, true, false]);
        assert_eq!(semantics.dfe_coefficients().len(), 2);
        assert_eq!(semantics.clock_sample_indices(), [3, 11, 19, 27]);
        assert_eq!(semantics.ber_start_symbol(), 1);
        assert_eq!(semantics.ber_symbol_count().get(), 3);
        assert_eq!(semantics.decision_threshold().get(), 0.0);
        assert!(parse_receiver_semantics_v1(
            br#"{"schema":"sipi.receiver-semantics.v1","known_bits":{"bits":[true],"positive_voltage_is_one":true},"dfe":{"coefficients":[0.0],"cursor_index":0},"clock":{"kind":"explicit_sample_indices","sample_indices":[0]},"ber":{"start_symbol":0,"symbol_count":1,"decision_threshold_volts":0.0,"ties":{"kind":"reject"}},"legacy_cdr":{"kind":"bang_bang"}}"#
        )
        .is_err());
    }

    #[test]
    fn receiver_semantics_validate_window_and_clock_without_defaults() {
        let mut wire = required_receiver_semantics_wire();
        wire.dfe.coefficients.clear();
        assert_eq!(
            ReceiverSemanticsV1::try_from(wire),
            Err(ContractError::ReceiverSemantics(
                ReceiverSemanticContractError::EmptyDfeCoefficients
            ))
        );
        let mut wire = required_receiver_semantics_wire();
        wire.clock = WireClockRecoveryPlanV1::ExplicitSampleIndices {
            sample_indices: vec![3, 3],
        };
        assert_eq!(
            ReceiverSemanticsV1::try_from(wire),
            Err(ContractError::ReceiverSemantics(
                ReceiverSemanticContractError::NonIncreasingClockSamples
            ))
        );
        let mut wire = required_receiver_semantics_wire();
        wire.ber.symbol_count = 4;
        assert_eq!(
            ReceiverSemanticsV1::try_from(wire),
            Err(ContractError::ReceiverSemantics(
                ReceiverSemanticContractError::BerWindowExceedsKnownBits
            ))
        );
    }

    #[test]
    fn receiver_semantics_schema_is_available_from_the_contract_authority() {
        assert!(
            receiver_semantics_schema_json()
                .expect("schema")
                .starts_with(b"{")
        );
    }

    #[test]
    fn tracked_receiver_semantics_schema_baseline_is_exactly_the_registered_export() {
        let baseline = include_bytes!("../schemas/sipi.receiver-semantics.v1.schema.json");
        assert!(baseline.ends_with(b"\n"));
        assert_eq!(
            receiver_semantics_schema_json().expect("schema"),
            &baseline[..baseline.len() - 1]
        );
    }

    #[test]
    fn tracked_receiver_schema_baseline_is_exactly_the_registered_export() {
        let baseline = include_bytes!("../schemas/sipi.receiver-input.v1.schema.json");
        assert!(baseline.ends_with(b"\n"));
        assert_eq!(
            receiver_input_schema_json().expect("schema"),
            &baseline[..baseline.len() - 1]
        );
    }
}
