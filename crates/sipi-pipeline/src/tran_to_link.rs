//! The sole P6 cross-domain edge currently admitted by the product.
//!
//! This typed handoff converts the fixed RC/PULSE TRAN source waveform into a
//! DirectLaunch causal-FIR stimulus. It never resamples, pads, trims, shifts,
//! or changes voltage units or signs.

use std::{error::Error, fmt};

use sha2::{Digest, Sha256};
use sipi_contracts::{
    CausalFirChannelV1, LinkContractError, LinkPlanV1, RxStagesV1, TxStageV1, UniformTimebaseV1,
};
use sipi_link::{ConvolutionLimitsV1, LinkError, ReceivedVoltageSamplesV1, convolve_causal_fir_v1};
use sipi_tran::{RcPulseTransientResultV1, RcPulseTransientV1, TranError, simulate_rc_pulse};
use sipi_types::{AxisView, Seconds, TypeError, Waveform};

const FIXED_LAUNCH_TIMES_S: [f64; 4] = [0.0, 1.0e-6, 2.0e-6, 3.0e-6];
const FIXED_LAUNCH_INTERVAL_S: f64 = 1.0e-6;

/// Product-owned identity for the admitted four-sample launch waveform.
pub const TRAN_RC_PULSE_LAUNCH_CONTRACT_V1: &str = "sipi.tran.rc-pulse-launch.v1";
pub const TRAN_RC_PULSE_TO_CAUSAL_FIR_EDGE_SCHEMA_V1: &str =
    "sipi.edge.tran-rc-pulse-to-causal-fir.v1";
const EDGE_IMPLEMENTATION_REVISION_V1: &str = "p6-03a";
const EDGE_SIGNAL_MAP_V1: &str = "single_ended_voltage_to_common_reference";

/// A validated launch artifact derived only from `tran-rc-pulse-v1` input voltage.
#[derive(Clone, Debug, PartialEq)]
pub struct TranRcPulseLaunchArtifactV1 {
    waveform: Waveform,
}

impl TranRcPulseLaunchArtifactV1 {
    pub fn waveform(&self) -> &Waveform {
        &self.waveform
    }
}

/// SHA-256 identity for one canonical edge value or policy.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct EdgeDigestV1([u8; 32]);

impl EdgeDigestV1 {
    pub const fn bytes(&self) -> &[u8; 32] {
        &self.0
    }

    pub fn hex(&self) -> String {
        let mut value = String::with_capacity(self.0.len() * 2);
        for byte in self.0 {
            use std::fmt::Write as _;
            let _ = write!(value, "{byte:02x}");
        }
        value
    }
}

/// Versioned identity record for the sole admitted TRAN-to-Link edge.
///
/// It is not an artifact manifest or complete execution provenance. It binds
/// only the typed values and policy of this in-process edge.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct TranRcPulseToCausalFirEdgeRecordV1 {
    schema: &'static str,
    implementation_revision: &'static str,
    producer_contract: &'static str,
    producer_profile: &'static str,
    producer_output_port: &'static str,
    consumer_contract: &'static str,
    consumer_input_port: &'static str,
    signal_map: &'static str,
    producer_artifact_digest: EdgeDigestV1,
    consumer_input_digest: EdgeDigestV1,
    consumer_policy_digest: EdgeDigestV1,
    received_output_digest: EdgeDigestV1,
}

impl TranRcPulseToCausalFirEdgeRecordV1 {
    pub const fn schema(&self) -> &'static str {
        self.schema
    }

    pub const fn implementation_revision(&self) -> &'static str {
        self.implementation_revision
    }

    pub const fn producer_contract(&self) -> &'static str {
        self.producer_contract
    }

    pub const fn producer_profile(&self) -> &'static str {
        self.producer_profile
    }

    pub const fn producer_output_port(&self) -> &'static str {
        self.producer_output_port
    }

    pub const fn consumer_contract(&self) -> &'static str {
        self.consumer_contract
    }

    pub const fn consumer_input_port(&self) -> &'static str {
        self.consumer_input_port
    }

    pub const fn signal_map(&self) -> &'static str {
        self.signal_map
    }

    pub const fn producer_artifact_digest(&self) -> EdgeDigestV1 {
        self.producer_artifact_digest
    }

    pub const fn consumer_input_digest(&self) -> EdgeDigestV1 {
        self.consumer_input_digest
    }

    pub const fn consumer_policy_digest(&self) -> EdgeDigestV1 {
        self.consumer_policy_digest
    }

    pub const fn received_output_digest(&self) -> EdgeDigestV1 {
        self.received_output_digest
    }

    /// Recomputes every identity binding from the supplied typed values.
    pub fn verify_against(
        &self,
        launch: &TranRcPulseLaunchArtifactV1,
        consumer: &CausalFirConsumerConfigV1,
        received: &ReceivedVoltageSamplesV1,
    ) -> Result<(), TranToLinkEdgeError> {
        if self != &record_for_v1(launch, consumer, received)? {
            return Err(TranToLinkEdgeError::EdgeRecordMismatch);
        }
        Ok(())
    }
}

/// Result of the recorded in-process edge execution.
#[derive(Clone, Debug, PartialEq)]
pub struct RecordedTranToLinkExecutionV1 {
    received: ReceivedVoltageSamplesV1,
    record: TranRcPulseToCausalFirEdgeRecordV1,
}

impl RecordedTranToLinkExecutionV1 {
    pub fn received(&self) -> &ReceivedVoltageSamplesV1 {
        &self.received
    }

    pub fn record(&self) -> &TranRcPulseToCausalFirEdgeRecordV1 {
        &self.record
    }
}

/// Explicit causal-FIR consumer configuration for the admitted edge.
#[derive(Clone, Debug, PartialEq)]
pub struct CausalFirConsumerConfigV1 {
    channel: CausalFirChannelV1,
    limits: ConvolutionLimitsV1,
}

impl CausalFirConsumerConfigV1 {
    pub fn try_new(
        channel: CausalFirChannelV1,
        limits: ConvolutionLimitsV1,
    ) -> Result<Self, TranToLinkEdgeError> {
        if channel.sample_interval().get().to_bits() != FIXED_LAUNCH_INTERVAL_S.to_bits() {
            return Err(TranToLinkEdgeError::ChannelSampleIntervalMismatch);
        }
        Ok(Self { channel, limits })
    }

    pub fn channel(&self) -> &CausalFirChannelV1 {
        &self.channel
    }

    pub const fn limits(&self) -> ConvolutionLimitsV1 {
        self.limits
    }
}

/// Fail-closed errors for the fixed TRAN-to-Link handoff.
#[derive(Debug)]
pub enum TranToLinkEdgeError {
    UnsupportedProducerAxis,
    ChannelSampleIntervalMismatch,
    Type(TypeError),
    LinkContract(LinkContractError),
    Tran(TranError),
    Link(LinkError),
    InvalidReceivedAxis,
    EdgeRecordMismatch,
}

impl TranToLinkEdgeError {
    pub const fn code(&self) -> &'static str {
        match self {
            Self::UnsupportedProducerAxis => "unsupported_tran_launch_axis",
            Self::ChannelSampleIntervalMismatch => "channel_sample_interval_mismatch",
            Self::Type(_) => "tran_launch_type_error",
            Self::LinkContract(_) => "link_contract_error",
            Self::Tran(_) => "tran_failure",
            Self::Link(_) => "link_failure",
            Self::InvalidReceivedAxis => "invalid_received_axis",
            Self::EdgeRecordMismatch => "edge_record_mismatch",
        }
    }
}

impl fmt::Display for TranToLinkEdgeError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.code())
    }
}

impl Error for TranToLinkEdgeError {}

impl From<TypeError> for TranToLinkEdgeError {
    fn from(value: TypeError) -> Self {
        Self::Type(value)
    }
}

impl From<LinkContractError> for TranToLinkEdgeError {
    fn from(value: LinkContractError) -> Self {
        Self::LinkContract(value)
    }
}

impl From<TranError> for TranToLinkEdgeError {
    fn from(value: TranError) -> Self {
        Self::Tran(value)
    }
}

impl From<LinkError> for TranToLinkEdgeError {
    fn from(value: LinkError) -> Self {
        Self::Link(value)
    }
}

/// Admits the fixed TRAN source waveform as a product launch artifact.
///
/// This selects `voltage_in` by contract. It cannot consume the RC output,
/// resample explicit times, or accept a different fixed-profile revision.
pub fn derive_fixed_tran_launch_v1(
    result: &RcPulseTransientResultV1,
) -> Result<TranRcPulseLaunchArtifactV1, TranToLinkEdgeError> {
    admit_fixed_launch_waveform(result.voltage_in())
}

/// Builds the only legal Link plan for this edge: DirectLaunch with bypass RX.
pub fn build_direct_launch_plan_v1(
    launch: &TranRcPulseLaunchArtifactV1,
    consumer: &CausalFirConsumerConfigV1,
) -> Result<LinkPlanV1, TranToLinkEdgeError> {
    let timebase = UniformTimebaseV1::try_new(
        Seconds::try_new(0.0)?,
        Seconds::try_new(FIXED_LAUNCH_INTERVAL_S)?,
        FIXED_LAUNCH_TIMES_S.len(),
    )?;
    Ok(LinkPlanV1::try_new(
        timebase,
        TxStageV1::DirectLaunch,
        launch.waveform.samples().to_vec(),
        consumer.channel.clone(),
        RxStagesV1::bypass(),
    )?)
}

/// Executes the existing fixed TRAN solver and existing causal-FIR primitive in-process.
///
/// It does not publish artifacts, execute a project, start a worker, or add a CLI route.
pub fn run_fixed_tran_to_causal_fir_v1(
    request: RcPulseTransientV1,
    consumer: &CausalFirConsumerConfigV1,
) -> Result<ReceivedVoltageSamplesV1, TranToLinkEdgeError> {
    let result = simulate_rc_pulse(request)?;
    let launch = derive_fixed_tran_launch_v1(&result)?;
    let plan = build_direct_launch_plan_v1(&launch, consumer)?;
    Ok(convolve_causal_fir_v1(&plan, consumer.limits())?)
}

/// Runs the admitted edge and returns its specialized P6 identity record.
pub fn run_fixed_tran_to_causal_fir_recorded_v1(
    request: RcPulseTransientV1,
    consumer: &CausalFirConsumerConfigV1,
) -> Result<RecordedTranToLinkExecutionV1, TranToLinkEdgeError> {
    let result = simulate_rc_pulse(request)?;
    let launch = derive_fixed_tran_launch_v1(&result)?;
    let plan = build_direct_launch_plan_v1(&launch, consumer)?;
    let received = convolve_causal_fir_v1(&plan, consumer.limits())?;
    let record = record_for_v1(&launch, consumer, &received)?;
    Ok(RecordedTranToLinkExecutionV1 { received, record })
}

/// Binds the supplied typed launch, causal-FIR policy, and output identities.
pub fn record_tran_rc_pulse_to_causal_fir_v1(
    launch: &TranRcPulseLaunchArtifactV1,
    consumer: &CausalFirConsumerConfigV1,
    received: &ReceivedVoltageSamplesV1,
) -> Result<TranRcPulseToCausalFirEdgeRecordV1, TranToLinkEdgeError> {
    record_for_v1(launch, consumer, received)
}

fn admit_fixed_launch_waveform(
    waveform: &Waveform,
) -> Result<TranRcPulseLaunchArtifactV1, TranToLinkEdgeError> {
    let AxisView::Explicit(times) = waveform.axis().view() else {
        return Err(TranToLinkEdgeError::UnsupportedProducerAxis);
    };
    if times.len() != FIXED_LAUNCH_TIMES_S.len()
        || waveform.samples().len() != FIXED_LAUNCH_TIMES_S.len()
        || !times
            .iter()
            .zip(FIXED_LAUNCH_TIMES_S)
            .all(|(actual, expected)| actual.get().to_bits() == expected.to_bits())
    {
        return Err(TranToLinkEdgeError::UnsupportedProducerAxis);
    }
    Ok(TranRcPulseLaunchArtifactV1 {
        waveform: waveform.clone(),
    })
}

fn record_for_v1(
    launch: &TranRcPulseLaunchArtifactV1,
    consumer: &CausalFirConsumerConfigV1,
    received: &ReceivedVoltageSamplesV1,
) -> Result<TranRcPulseToCausalFirEdgeRecordV1, TranToLinkEdgeError> {
    let producer_artifact_digest = fixed_launch_digest(launch.waveform())?;
    let consumer_input_digest = fixed_launch_digest(launch.waveform())?;
    let consumer_policy_digest = consumer_policy_digest(consumer);
    let received_output_digest = received_digest(received, consumer)?;
    Ok(TranRcPulseToCausalFirEdgeRecordV1 {
        schema: TRAN_RC_PULSE_TO_CAUSAL_FIR_EDGE_SCHEMA_V1,
        implementation_revision: EDGE_IMPLEMENTATION_REVISION_V1,
        producer_contract: TRAN_RC_PULSE_LAUNCH_CONTRACT_V1,
        producer_profile: "tran-rc-pulse-v1",
        producer_output_port: "voltage_in",
        consumer_contract: "sipi.link-plan.v1",
        consumer_input_port: "direct_launch_voltage",
        signal_map: EDGE_SIGNAL_MAP_V1,
        producer_artifact_digest,
        consumer_input_digest,
        consumer_policy_digest,
        received_output_digest,
    })
}

fn fixed_launch_digest(waveform: &Waveform) -> Result<EdgeDigestV1, TranToLinkEdgeError> {
    admit_fixed_launch_waveform(waveform)?;
    Ok(canonical_waveform_digest(
        "sipi.edge.waveform.v1",
        FIXED_LAUNCH_INTERVAL_S,
        waveform.samples(),
    ))
}

fn received_digest(
    received: &ReceivedVoltageSamplesV1,
    consumer: &CausalFirConsumerConfigV1,
) -> Result<EdgeDigestV1, TranToLinkEdgeError> {
    let waveform = received.waveform();
    let AxisView::Uniform { start, step, count } = waveform.axis().view() else {
        return Err(TranToLinkEdgeError::InvalidReceivedAxis);
    };
    if start.get().to_bits() != 0.0f64.to_bits()
        || step.get().to_bits() != consumer.channel.sample_interval().get().to_bits()
        || count.get() != waveform.samples().len()
    {
        return Err(TranToLinkEdgeError::InvalidReceivedAxis);
    }
    Ok(canonical_waveform_digest(
        "sipi.edge.received-waveform.v1",
        step.get(),
        waveform.samples(),
    ))
}

fn consumer_policy_digest(consumer: &CausalFirConsumerConfigV1) -> EdgeDigestV1 {
    let mut hasher = Sha256::new();
    hash_bytes(&mut hasher, b"sipi.edge.policy.v1\0");
    hash_text(&mut hasher, TRAN_RC_PULSE_TO_CAUSAL_FIR_EDGE_SCHEMA_V1);
    hash_text(&mut hasher, "direct_launch");
    hash_text(&mut hasher, "causal_fir");
    hash_text(&mut hasher, "bypass");
    hash_text(&mut hasher, "bypass");
    hash_f64(&mut hasher, consumer.channel.sample_interval().get());
    hash_u64(&mut hasher, consumer.channel.gain().len() as u64);
    for gain in consumer.channel.gain() {
        hash_f64(&mut hasher, gain.get());
    }
    hash_u64(
        &mut hasher,
        consumer.limits.max_output_samples().get() as u64,
    );
    hash_u64(
        &mut hasher,
        consumer.limits.max_multiply_accumulates().get() as u64,
    );
    EdgeDigestV1(hasher.finalize().into())
}

fn canonical_waveform_digest(
    domain: &str,
    interval_s: f64,
    samples: &[sipi_types::Volts],
) -> EdgeDigestV1 {
    let mut hasher = Sha256::new();
    hash_bytes(&mut hasher, domain.as_bytes());
    hash_text(&mut hasher, "seconds");
    hash_text(&mut hasher, "volts");
    hash_text(&mut hasher, "uniform");
    hash_f64(&mut hasher, 0.0);
    hash_f64(&mut hasher, interval_s);
    hash_u64(&mut hasher, samples.len() as u64);
    for sample in samples {
        hash_f64(&mut hasher, sample.get());
    }
    EdgeDigestV1(hasher.finalize().into())
}

fn hash_text(hasher: &mut Sha256, value: &str) {
    hash_bytes(hasher, value.as_bytes());
}

fn hash_bytes(hasher: &mut Sha256, value: &[u8]) {
    hash_u64(hasher, value.len() as u64);
    hasher.update(value);
}

fn hash_u64(hasher: &mut Sha256, value: u64) {
    hasher.update(value.to_le_bytes());
}

fn hash_f64(hasher: &mut Sha256, value: f64) {
    hasher.update(value.to_bits().to_le_bytes());
}

#[cfg(test)]
mod tests {
    use super::*;
    use sipi_types::{Axis, FiniteF64, Volts};

    fn consumer(gain: &[f64], max_output: usize) -> CausalFirConsumerConfigV1 {
        CausalFirConsumerConfigV1::try_new(
            CausalFirChannelV1::try_new(
                Seconds::try_new(FIXED_LAUNCH_INTERVAL_S).unwrap(),
                gain.iter()
                    .copied()
                    .map(|value| FiniteF64::try_new(value, "test gain"))
                    .collect::<Result<Vec<_>, _>>()
                    .unwrap(),
            )
            .unwrap(),
            ConvolutionLimitsV1::try_new(max_output, 64).unwrap(),
        )
        .unwrap()
    }

    #[test]
    fn fixed_tran_input_is_admitted_without_changing_samples() {
        let result = simulate_rc_pulse(RcPulseTransientV1::fixed_profile()).unwrap();
        let launch = derive_fixed_tran_launch_v1(&result).unwrap();

        assert_eq!(
            launch
                .waveform()
                .samples()
                .iter()
                .map(|sample| sample.get())
                .collect::<Vec<_>>(),
            vec![0.0, 0.0, 1.0, 1.0]
        );
        assert_ne!(launch.waveform(), result.voltage_out());
    }

    #[test]
    fn fixed_launch_preserves_linear_tail_through_the_existing_fir() {
        let received = run_fixed_tran_to_causal_fir_v1(
            RcPulseTransientV1::fixed_profile(),
            &consumer(&[1.0, 0.5], 5),
        )
        .unwrap();

        assert_eq!(
            received
                .waveform()
                .samples()
                .iter()
                .map(|sample| sample.get())
                .collect::<Vec<_>>(),
            vec![0.0, 0.0, 1.0, 1.5, 0.5]
        );
    }

    #[test]
    fn rejects_axis_changes_and_consumer_interval_mismatch() {
        let waveform = Waveform::try_new(
            Axis::explicit(
                [0.0, 1.0e-6, 2.1e-6, 3.0e-6]
                    .into_iter()
                    .map(Seconds::try_new)
                    .collect::<Result<Vec<_>, _>>()
                    .unwrap(),
            )
            .unwrap(),
            vec![Volts::try_new(0.0).unwrap(); 4],
        )
        .unwrap();
        assert!(matches!(
            admit_fixed_launch_waveform(&waveform),
            Err(TranToLinkEdgeError::UnsupportedProducerAxis)
        ));

        let channel = CausalFirChannelV1::try_new(
            Seconds::try_new(2.0e-6).unwrap(),
            vec![FiniteF64::try_new(1.0, "test gain").unwrap()],
        )
        .unwrap();
        assert!(matches!(
            CausalFirConsumerConfigV1::try_new(
                channel,
                ConvolutionLimitsV1::try_new(4, 4).unwrap()
            ),
            Err(TranToLinkEdgeError::ChannelSampleIntervalMismatch)
        ));
    }

    #[test]
    fn resource_limits_remain_fail_closed() {
        assert!(matches!(
            run_fixed_tran_to_causal_fir_v1(
                RcPulseTransientV1::fixed_profile(),
                &consumer(&[1.0, 1.0], 4),
            ),
            Err(TranToLinkEdgeError::Link(LinkError::ResourceLimitExceeded))
        ));
    }

    #[test]
    fn recorded_edge_binds_the_same_launch_on_both_sides() {
        let execution = run_fixed_tran_to_causal_fir_recorded_v1(
            RcPulseTransientV1::fixed_profile(),
            &consumer(&[1.0, 0.5], 5),
        )
        .unwrap();
        let record = execution.record();

        assert_eq!(record.schema(), TRAN_RC_PULSE_TO_CAUSAL_FIR_EDGE_SCHEMA_V1);
        assert_eq!(record.producer_output_port(), "voltage_in");
        assert_eq!(record.consumer_input_port(), "direct_launch_voltage");
        assert_eq!(record.signal_map(), EDGE_SIGNAL_MAP_V1);
        assert_eq!(
            record.producer_artifact_digest(),
            record.consumer_input_digest()
        );

        let result = simulate_rc_pulse(RcPulseTransientV1::fixed_profile()).unwrap();
        let launch = derive_fixed_tran_launch_v1(&result).unwrap();
        record
            .verify_against(&launch, &consumer(&[1.0, 0.5], 5), execution.received())
            .unwrap();
    }

    #[test]
    fn record_digest_changes_for_launch_or_policy_drift_and_rejects_tampering() {
        let result = simulate_rc_pulse(RcPulseTransientV1::fixed_profile()).unwrap();
        let launch = derive_fixed_tran_launch_v1(&result).unwrap();
        let first_consumer = consumer(&[1.0], 4);
        let first_plan = build_direct_launch_plan_v1(&launch, &first_consumer).unwrap();
        let first_received = convolve_causal_fir_v1(&first_plan, first_consumer.limits()).unwrap();
        let first_record =
            record_tran_rc_pulse_to_causal_fir_v1(&launch, &first_consumer, &first_received)
                .unwrap();

        let changed_waveform = Waveform::try_new(
            launch.waveform().axis().clone(),
            vec![
                Volts::try_new(-0.0).unwrap(),
                Volts::try_new(0.0).unwrap(),
                Volts::try_new(1.0).unwrap(),
                Volts::try_new(1.0).unwrap(),
            ],
        )
        .unwrap();
        let changed_launch = admit_fixed_launch_waveform(&changed_waveform).unwrap();
        let changed_plan = build_direct_launch_plan_v1(&changed_launch, &first_consumer).unwrap();
        let changed_received =
            convolve_causal_fir_v1(&changed_plan, first_consumer.limits()).unwrap();
        let changed_record = record_tran_rc_pulse_to_causal_fir_v1(
            &changed_launch,
            &first_consumer,
            &changed_received,
        )
        .unwrap();
        assert_ne!(
            first_record.producer_artifact_digest(),
            changed_record.producer_artifact_digest()
        );

        let policy_changed = consumer(&[0.5], 4);
        let policy_plan = build_direct_launch_plan_v1(&launch, &policy_changed).unwrap();
        let policy_received =
            convolve_causal_fir_v1(&policy_plan, policy_changed.limits()).unwrap();
        let policy_record =
            record_tran_rc_pulse_to_causal_fir_v1(&launch, &policy_changed, &policy_received)
                .unwrap();
        assert_ne!(
            first_record.consumer_policy_digest(),
            policy_record.consumer_policy_digest()
        );

        let mut tampered = first_record.clone();
        tampered.received_output_digest = policy_record.received_output_digest;
        assert!(matches!(
            tampered.verify_against(&launch, &first_consumer, &first_received),
            Err(TranToLinkEdgeError::EdgeRecordMismatch)
        ));
    }
}
