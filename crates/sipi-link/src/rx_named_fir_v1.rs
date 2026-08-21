//! Two explicitly selected RX slots backed only by the existing causal-FIR kernel.
//!
//! The `ctle` and `ffe` names express ordering only. They do not claim a CTLE
//! transfer function, UI-spaced FFE semantics, coefficient synthesis, or tuning.

use std::{error::Error, fmt};

use sipi_contracts::{
    CausalFirChannelV1, LinkContractError, LinkPlanV1, RxStagesV1, TxStageV1, UniformTimebaseV1,
};
use sipi_types::{AxisView, FiniteF64, TypeError, Waveform};

use crate::{ConvolutionLimitsV1, LinkError, convolve_causal_fir_v1};

pub const RX_NAMED_FIR_PREREQUISITE_POLICY_V1: &str = "sipi.p3b-02.rx-named-fir-prerequisite-v1";

/// A non-empty, finite, sample-spaced causal FIR with tap zero at time zero.
#[derive(Clone, Debug, PartialEq)]
pub struct ExplicitCausalFirV1 {
    taps: Vec<FiniteF64>,
}

impl ExplicitCausalFirV1 {
    pub fn try_new(taps: Vec<FiniteF64>) -> Result<Self, RxNamedFirErrorV1> {
        if taps.is_empty() {
            return Err(RxNamedFirErrorV1::EmptyTaps);
        }
        Ok(Self { taps })
    }

    pub fn taps(&self) -> &[FiniteF64] {
        &self.taps
    }
}

/// Explicit selection for one named slot. There is deliberately no `Default`.
#[derive(Clone, Debug, PartialEq)]
pub enum RxNamedFirStageV1 {
    Bypass,
    ExplicitCausalFir(ExplicitCausalFirV1),
}

/// Two named slots evaluated in fixed CTLE-slot then FFE-slot order.
#[derive(Clone, Debug, PartialEq)]
pub struct RxNamedFirPlanV1 {
    ctle_named_slot: RxNamedFirStageV1,
    ffe_named_slot: RxNamedFirStageV1,
}

impl RxNamedFirPlanV1 {
    pub const fn new(
        ctle_named_slot: RxNamedFirStageV1,
        ffe_named_slot: RxNamedFirStageV1,
    ) -> Self {
        Self {
            ctle_named_slot,
            ffe_named_slot,
        }
    }

    pub const fn ctle_named_slot(&self) -> &RxNamedFirStageV1 {
        &self.ctle_named_slot
    }

    pub const fn ffe_named_slot(&self) -> &RxNamedFirStageV1 {
        &self.ffe_named_slot
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct RxNamedFirResultV1 {
    ctle_named_slot_output: Waveform,
    ffe_named_slot_output: Waveform,
}

impl RxNamedFirResultV1 {
    pub fn ctle_named_slot_output(&self) -> &Waveform {
        &self.ctle_named_slot_output
    }

    pub fn output(&self) -> &Waveform {
        &self.ffe_named_slot_output
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum RxNamedFirErrorV1 {
    EmptyTaps,
    NonUniformInputAxis,
    ResourceLimitExceeded,
    ResourceCountOverflow,
    Contract(LinkContractError),
    Link(LinkError),
    Invariant(TypeError),
}

impl fmt::Display for RxNamedFirErrorV1 {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::EmptyTaps => write!(formatter, "explicit causal FIR taps must not be empty"),
            Self::NonUniformInputAxis => write!(formatter, "RX FIR input axis must be uniform"),
            Self::ResourceLimitExceeded => write!(formatter, "RX FIR resource limit exceeded"),
            Self::ResourceCountOverflow => write!(formatter, "RX FIR resource count overflow"),
            Self::Contract(error) => error.fmt(formatter),
            Self::Link(error) => error.fmt(formatter),
            Self::Invariant(error) => error.fmt(formatter),
        }
    }
}

impl Error for RxNamedFirErrorV1 {}

impl From<LinkContractError> for RxNamedFirErrorV1 {
    fn from(value: LinkContractError) -> Self {
        Self::Contract(value)
    }
}

impl From<LinkError> for RxNamedFirErrorV1 {
    fn from(value: LinkError) -> Self {
        Self::Link(value)
    }
}

impl From<TypeError> for RxNamedFirErrorV1 {
    fn from(value: TypeError) -> Self {
        Self::Invariant(value)
    }
}

/// Applies the two named slots with zero prehistory and full-linear output.
///
/// Each non-bypass slot delegates to `convolve_causal_fir_v1`; the cumulative
/// multiply-accumulate count and every intermediate output are bounded first.
pub fn apply_rx_named_fir_prerequisite_v1(
    input: &Waveform,
    plan: &RxNamedFirPlanV1,
    limits: ConvolutionLimitsV1,
) -> Result<RxNamedFirResultV1, RxNamedFirErrorV1> {
    preflight(input.samples().len(), plan, limits)?;
    let ctle_named_slot_output = apply_stage(input, plan.ctle_named_slot(), limits)?;
    let ffe_named_slot_output =
        apply_stage(&ctle_named_slot_output, plan.ffe_named_slot(), limits)?;
    Ok(RxNamedFirResultV1 {
        ctle_named_slot_output,
        ffe_named_slot_output,
    })
}

fn preflight(
    input_len: usize,
    plan: &RxNamedFirPlanV1,
    limits: ConvolutionLimitsV1,
) -> Result<(), RxNamedFirErrorV1> {
    let mut length = input_len;
    let mut work = 0usize;
    for stage in [plan.ctle_named_slot(), plan.ffe_named_slot()] {
        if let RxNamedFirStageV1::ExplicitCausalFir(fir) = stage {
            work = work
                .checked_add(
                    length
                        .checked_mul(fir.taps().len())
                        .ok_or(RxNamedFirErrorV1::ResourceCountOverflow)?,
                )
                .ok_or(RxNamedFirErrorV1::ResourceCountOverflow)?;
            length = length
                .checked_add(fir.taps().len())
                .and_then(|value| value.checked_sub(1))
                .ok_or(RxNamedFirErrorV1::ResourceCountOverflow)?;
        }
        if length > limits.max_output_samples().get()
            || work > limits.max_multiply_accumulates().get()
        {
            return Err(RxNamedFirErrorV1::ResourceLimitExceeded);
        }
    }
    Ok(())
}

fn apply_stage(
    input: &Waveform,
    stage: &RxNamedFirStageV1,
    limits: ConvolutionLimitsV1,
) -> Result<Waveform, RxNamedFirErrorV1> {
    let RxNamedFirStageV1::ExplicitCausalFir(fir) = stage else {
        return Ok(input.clone());
    };
    let AxisView::Uniform { start, step, count } = input.axis().view() else {
        return Err(RxNamedFirErrorV1::NonUniformInputAxis);
    };
    let timebase = UniformTimebaseV1::try_new(start, step, count.get())?;
    let channel = CausalFirChannelV1::try_new(step, fir.taps().to_vec())?;
    let link_plan = LinkPlanV1::try_new(
        timebase,
        TxStageV1::DirectLaunch,
        input.samples().to_vec(),
        channel,
        RxStagesV1::bypass(),
    )?;
    Ok(convolve_causal_fir_v1(&link_plan, limits)?
        .waveform()
        .clone())
}

#[cfg(test)]
mod tests {
    use std::num::NonZeroUsize;

    use sipi_types::{Axis, NonZeroStep, Seconds, Volts};

    use super::*;

    fn waveform(values: &[f64]) -> Waveform {
        let axis = Axis::uniform(
            Seconds::try_new(0.0).unwrap(),
            NonZeroStep::try_new(Seconds::try_new(1.0).unwrap()).unwrap(),
            NonZeroUsize::new(values.len()).unwrap(),
        );
        Waveform::try_new(
            axis,
            values
                .iter()
                .copied()
                .map(Volts::try_new)
                .collect::<Result<Vec<_>, _>>()
                .unwrap(),
        )
        .unwrap()
    }

    fn fir(values: &[f64]) -> RxNamedFirStageV1 {
        RxNamedFirStageV1::ExplicitCausalFir(
            ExplicitCausalFirV1::try_new(
                values
                    .iter()
                    .copied()
                    .map(|value| FiniteF64::try_new(value, "test tap"))
                    .collect::<Result<Vec<_>, _>>()
                    .unwrap(),
            )
            .unwrap(),
        )
    }

    fn values(waveform: &Waveform) -> Vec<f64> {
        waveform.samples().iter().map(|value| value.get()).collect()
    }

    fn limits() -> ConvolutionLimitsV1 {
        ConvolutionLimitsV1::try_new(32, 128).unwrap()
    }

    #[test]
    fn explicit_bypass_is_identity() {
        let input = waveform(&[1.0, -2.0]);
        let plan = RxNamedFirPlanV1::new(RxNamedFirStageV1::Bypass, RxNamedFirStageV1::Bypass);
        let result = apply_rx_named_fir_prerequisite_v1(&input, &plan, limits()).unwrap();
        assert_eq!(result.ctle_named_slot_output(), &input);
        assert_eq!(result.output(), &input);
    }

    #[test]
    fn named_slots_are_full_linear_and_ordered_ctle_then_ffe() {
        let plan = RxNamedFirPlanV1::new(fir(&[1.0, 1.0]), fir(&[1.0, -1.0]));
        let result =
            apply_rx_named_fir_prerequisite_v1(&waveform(&[1.0, 2.0]), &plan, limits()).unwrap();
        assert_eq!(values(result.ctle_named_slot_output()), [1.0, 3.0, 2.0]);
        assert_eq!(values(result.output()), [1.0, 2.0, -1.0, -2.0]);
    }

    #[test]
    fn invalid_taps_axes_and_cumulative_limits_fail_closed() {
        assert_eq!(
            ExplicitCausalFirV1::try_new(Vec::new()),
            Err(RxNamedFirErrorV1::EmptyTaps)
        );
        let explicit = Waveform::try_new(
            Axis::explicit(vec![Seconds::try_new(0.0).unwrap()]).unwrap(),
            vec![Volts::try_new(1.0).unwrap()],
        )
        .unwrap();
        let one_stage = RxNamedFirPlanV1::new(fir(&[1.0]), RxNamedFirStageV1::Bypass);
        assert_eq!(
            apply_rx_named_fir_prerequisite_v1(&explicit, &one_stage, limits()),
            Err(RxNamedFirErrorV1::NonUniformInputAxis)
        );
        let two_stages = RxNamedFirPlanV1::new(fir(&[1.0, 1.0]), fir(&[1.0, 1.0]));
        assert_eq!(
            apply_rx_named_fir_prerequisite_v1(
                &waveform(&[1.0, 2.0]),
                &two_stages,
                ConvolutionLimitsV1::try_new(4, 9).unwrap(),
            ),
            Err(RxNamedFirErrorV1::ResourceLimitExceeded)
        );
    }
}
