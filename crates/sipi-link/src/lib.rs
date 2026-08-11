#![forbid(unsafe_code)]

//! Product-owned, deterministic Link primitives for the P3B boundary.
//!
//! It contains direct causal-FIR convolution and one approved fixed,
//! data-aided receiver. It has no S-parameter resolver, equalizer, I/O, CLI,
//! or external-oracle dependency.

use std::{error::Error, fmt, num::NonZeroUsize};

use sipi_contracts::LinkPlanV1;
use sipi_runtime::RunContext;
use sipi_types::{Axis, NonZeroStep, Seconds, TypeError, Volts, Waveform};

mod receiver;

pub use receiver::{
    ReceiverDecisionV1, ReceiverError, ReceiverPhaseSelectionV2, ReceiverResultV1, ReferenceBitsV1,
    run_fixed_receiver_delegated_ambiguity_v2, run_fixed_receiver_v1,
};

/// Stable, explicit bounds for one causal FIR operation.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct ConvolutionLimitsV1 {
    max_output_samples: NonZeroUsize,
    max_multiply_accumulates: NonZeroUsize,
}

impl ConvolutionLimitsV1 {
    pub fn try_new(
        max_output_samples: usize,
        max_multiply_accumulates: usize,
    ) -> Result<Self, LinkError> {
        Ok(Self {
            max_output_samples: NonZeroUsize::new(max_output_samples)
                .ok_or(LinkError::InvalidLimit)?,
            max_multiply_accumulates: NonZeroUsize::new(max_multiply_accumulates)
                .ok_or(LinkError::InvalidLimit)?,
        })
    }

    pub fn max_output_samples(self) -> NonZeroUsize {
        self.max_output_samples
    }

    pub fn max_multiply_accumulates(self) -> NonZeroUsize {
        self.max_multiply_accumulates
    }
}

/// Received samples from a causal FIR operation, relative to common ground.
#[derive(Clone, Debug, PartialEq)]
pub struct ReceivedVoltageSamplesV1 {
    waveform: Waveform,
}

impl ReceivedVoltageSamplesV1 {
    pub fn waveform(&self) -> &Waveform {
        &self.waveform
    }
}

/// Fail-closed errors for the sole v1 Link operation.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum LinkError {
    InvalidLimit,
    ResourceLimitExceeded,
    NumericOverflow { output_index: usize },
    Runtime(sipi_runtime::RuntimeFailure),
    Invariant(TypeError),
}

impl fmt::Display for LinkError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::InvalidLimit => write!(formatter, "convolution limit must be nonzero"),
            Self::ResourceLimitExceeded => write!(formatter, "convolution resource limit exceeded"),
            Self::NumericOverflow { output_index } => {
                write!(
                    formatter,
                    "non-finite convolution result at output {output_index}"
                )
            }
            Self::Runtime(error) => write!(formatter, "runtime failure: {}", error.code()),
            Self::Invariant(error) => error.fmt(formatter),
        }
    }
}

impl Error for LinkError {}

impl From<TypeError> for LinkError {
    fn from(value: TypeError) -> Self {
        Self::Invariant(value)
    }
}

impl From<sipi_runtime::RuntimeFailure> for LinkError {
    fn from(value: sipi_runtime::RuntimeFailure) -> Self {
        Self::Runtime(value)
    }
}

/// Convolves the contract's direct launch with its causal FIR channel.
///
/// The calculation is deterministic: outputs are visited from zero upward and
/// each sum visits kernel indices from zero upward. It intentionally uses a
/// direct linear convolution rather than FFT, circular wrapping, trimming,
/// padding, shifting, resampling, or a second channel resolver.
pub fn convolve_causal_fir_v1(
    plan: &LinkPlanV1,
    limits: ConvolutionLimitsV1,
) -> Result<ReceivedVoltageSamplesV1, LinkError> {
    convolve_causal_fir_checked(plan, limits, || Ok(()))
}

/// Convolves the contract's direct launch while observing cooperative runtime
/// checkpoints. It shares the exact numerical order of the context-free API.
pub fn convolve_causal_fir_with_context_v1(
    plan: &LinkPlanV1,
    limits: ConvolutionLimitsV1,
    context: &RunContext,
) -> Result<ReceivedVoltageSamplesV1, LinkError> {
    convolve_causal_fir_checked(plan, limits, || context.checkpoint().map_err(Into::into))
}

fn convolve_causal_fir_checked(
    plan: &LinkPlanV1,
    limits: ConvolutionLimitsV1,
    mut checkpoint: impl FnMut() -> Result<(), LinkError>,
) -> Result<ReceivedVoltageSamplesV1, LinkError> {
    let launch = plan.stimulus();
    let gain = plan.channel().gain();
    let output_count = plan.output_sample_count();
    let work = launch
        .len()
        .checked_mul(gain.len())
        .ok_or(LinkError::ResourceLimitExceeded)?;

    if output_count > limits.max_output_samples().get()
        || work > limits.max_multiply_accumulates().get()
    {
        return Err(LinkError::ResourceLimitExceeded);
    }

    let mut received = Vec::with_capacity(output_count);
    for output_index in 0..output_count {
        checkpoint()?;
        let first_kernel = output_index.saturating_sub(launch.len() - 1);
        let last_kernel = output_index.min(gain.len() - 1);
        let mut sum = 0.0;
        for (kernel_index, gain_sample) in gain
            .iter()
            .enumerate()
            .skip(first_kernel)
            .take(last_kernel - first_kernel + 1)
        {
            let launch_index = output_index - kernel_index;
            let product = launch[launch_index].get() * gain_sample.get();
            if !product.is_finite() {
                return Err(LinkError::NumericOverflow { output_index });
            }
            sum += product;
            if !sum.is_finite() {
                return Err(LinkError::NumericOverflow { output_index });
            }
        }
        received.push(Volts::try_new(sum)?);
    }

    let timebase = plan.timebase();
    let axis = Axis::uniform(
        Seconds::try_new(0.0)?,
        NonZeroStep::try_new(timebase.sample_interval())?,
        NonZeroUsize::new(output_count).ok_or(LinkError::ResourceLimitExceeded)?,
    );
    Ok(ReceivedVoltageSamplesV1 {
        waveform: Waveform::try_new(axis, received)?,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use sipi_contracts::{
        CausalFirChannelV1, CtleStageV1, LinkPlanV1, RxStagesV1, TxStageV1, UniformTimebaseV1,
    };
    use sipi_types::FiniteF64;

    fn plan(launch: &[f64], gain: &[f64]) -> LinkPlanV1 {
        let timebase = UniformTimebaseV1::try_new(
            Seconds::try_new(0.0).unwrap(),
            Seconds::try_new(1.0).unwrap(),
            launch.len(),
        )
        .unwrap();
        let channel = CausalFirChannelV1::try_new(
            Seconds::try_new(1.0).unwrap(),
            gain.iter()
                .copied()
                .map(|value| FiniteF64::try_new(value, "test gain"))
                .collect::<Result<Vec<_>, _>>()
                .unwrap(),
        )
        .unwrap();
        LinkPlanV1::try_new(
            timebase,
            TxStageV1::DirectLaunch,
            launch
                .iter()
                .copied()
                .map(Volts::try_new)
                .collect::<Result<Vec<_>, _>>()
                .unwrap(),
            channel,
            RxStagesV1::bypass(),
        )
        .unwrap()
    }

    fn limits() -> ConvolutionLimitsV1 {
        ConvolutionLimitsV1::try_new(64, 256).unwrap()
    }

    fn values(result: ReceivedVoltageSamplesV1) -> Vec<f64> {
        result
            .waveform()
            .samples()
            .iter()
            .map(|sample| sample.get())
            .collect()
    }

    #[test]
    fn identity_delay_and_full_tail_are_linear_not_circular() {
        assert_eq!(
            values(convolve_causal_fir_v1(&plan(&[2.0, 3.0], &[1.0]), limits()).unwrap()),
            [2.0, 3.0]
        );
        assert_eq!(
            values(convolve_causal_fir_v1(&plan(&[2.0, 3.0], &[0.0, 0.0, 1.0]), limits()).unwrap()),
            [0.0, 0.0, 2.0, 3.0]
        );
        assert_eq!(
            values(convolve_causal_fir_v1(&plan(&[1.0, 2.0], &[3.0, 4.0]), limits()).unwrap()),
            [3.0, 10.0, 8.0]
        );
    }

    #[test]
    fn scaling_and_output_axis_are_deterministic() {
        let base =
            values(convolve_causal_fir_v1(&plan(&[1.0, -2.0], &[0.5, 0.25]), limits()).unwrap());
        let scaled = convolve_causal_fir_v1(&plan(&[3.0, -6.0], &[0.5, 0.25]), limits()).unwrap();
        assert_eq!(
            values(scaled.clone()),
            base.iter().map(|value| value * 3.0).collect::<Vec<_>>()
        );
        assert_eq!(scaled.waveform().axis().len(), 3);
        assert!(scaled.waveform().axis().is_uniform());
    }

    #[test]
    fn limits_and_numeric_overflow_fail_closed() {
        assert_eq!(
            ConvolutionLimitsV1::try_new(0, 1),
            Err(LinkError::InvalidLimit)
        );
        assert_eq!(
            convolve_causal_fir_v1(
                &plan(&[1.0, 2.0], &[1.0, 2.0]),
                ConvolutionLimitsV1::try_new(2, 4).unwrap()
            ),
            Err(LinkError::ResourceLimitExceeded)
        );
        assert_eq!(
            convolve_causal_fir_v1(&plan(&[1.0e308], &[1.0e308]), limits()),
            Err(LinkError::NumericOverflow { output_index: 0 })
        );
    }

    #[test]
    fn contract_keeps_all_stages_as_identity_only() {
        let result = convolve_causal_fir_v1(&plan(&[1.0], &[1.0]), limits()).unwrap();
        assert_eq!(values(result), [1.0]);
        assert_eq!(RxStagesV1::bypass().ctle(), CtleStageV1::Bypass);
    }
}
