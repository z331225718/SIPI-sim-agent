//! The sole P6 cross-domain edge currently admitted by the product.
//!
//! This typed handoff converts the fixed RC/PULSE TRAN source waveform into a
//! DirectLaunch causal-FIR stimulus. It never resamples, pads, trims, shifts,
//! or changes voltage units or signs.

use std::{error::Error, fmt};

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
}
