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
pub const VALIDATION_REQUEST_SCHEMA: &str = "sipi.validation-request.v1";
pub const TRAN_RC_PULSE_REQUEST_SCHEMA: &str = "sipi.tran.rc-pulse-request.v1";
pub const LINK_PLAN_SCHEMA: &str = "sipi.link-plan.v1";
pub const PLANNED_DOMAINS: [&str; 4] = ["tran", "channel", "ibis-ami", "com"];

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ContractError {
    Json(String),
    Type(TypeError),
    Version,
    Link(LinkContractError),
}

impl fmt::Display for ContractError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Json(_) => write!(formatter, "invalid contract JSON"),
            Self::Type(error) => error.fmt(formatter),
            Self::Version => write!(formatter, "unsupported contract version"),
            Self::Link(error) => error.fmt(formatter),
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
}

impl fmt::Display for LinkContractError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "invalid Link-stage contract: {self:?}")
    }
}

impl Error for LinkContractError {}

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

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct RuleLedgerEntry {
    pub id: &'static str,
    pub owner: &'static str,
    pub wire_type: &'static str,
    pub code: &'static str,
    pub test_id: &'static str,
}

pub const RULE_LEDGER_V1: [RuleLedgerEntry; 9] = [
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

pub fn parse_link_plan_v1(input: &[u8]) -> Result<LinkPlanV1, ContractError> {
    serde_json::from_slice::<WireLinkPlanV1>(input)
        .map_err(|error| ContractError::Json(error.to_string()))?
        .try_into()
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

pub fn capability_schema_json() -> Result<Vec<u8>, ContractError> {
    deterministic_json(&schema_for!(CapabilityCatalogV1))
}

pub fn link_plan_schema_json() -> Result<Vec<u8>, ContractError> {
    deterministic_json(&schema_for!(WireLinkPlanV1))
}

fn require_schema(schema: &str) -> Result<(), ContractError> {
    if schema == "sipi.contract.v1" {
        Ok(())
    } else {
        Err(ContractError::Version)
    }
}

fn require_link_schema(schema: &str) -> Result<(), ContractError> {
    if schema == LINK_PLAN_SCHEMA {
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
    fn tracked_schema_baseline_is_exactly_the_registered_export() {
        let baseline = include_bytes!("../schemas/sipi.capabilities.v1.schema.json");
        assert!(baseline.ends_with(b"\n"));
        assert_eq!(
            capability_schema_json().expect("schema"),
            &baseline[..baseline.len() - 1]
        );
    }

    #[test]
    fn validation_request_uses_the_existing_validated_waveform_path() {
        let valid = br#"{"schema":"sipi.validation-request.v1","request_id":"request-1","subject":{"schema":"sipi.contract.v1","axis":{"encoding":"explicit","values":[0.0,1.0]},"samples":[1.0,2.0]}}"#;
        assert!(validate_request_v1(valid).is_ok());
        assert!(validate_request_v1(br#"{"schema":"sipi.validation-request.v1","request_id":"bad/request","subject":{"schema":"sipi.contract.v1","axis":{"encoding":"explicit","values":[0.0]},"samples":[1.0]}}"#).is_err());
        assert!(validate_request_v1(br#"{"schema":"sipi.validation-request.v1","request_id":"request-1","subject":{"schema":"sipi.contract.v1","axis":{"encoding":"explicit","values":[0.0]},"samples":[1.0],"extra":true}}"#).is_err());
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
}
