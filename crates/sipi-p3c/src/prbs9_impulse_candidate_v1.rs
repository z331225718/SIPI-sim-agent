//! Fixed PRBS9 discrete candidate bridge for the selected P3C impulse route.
//!
//! The source is a right-continuous OSR32 projection: each PRBS symbol level
//! starts at its UI-boundary sample and is held for 32 samples. The 100 as ADS
//! edge is sub-strobe here and is deliberately not resolved or claimed as ADS
//! `EdgeShape` parity.

use std::{error::Error, fmt};

use sipi_contracts::{
    CausalFirChannelV1, LinkContractError, LinkPlanV1, RxStagesV1, TxStageV1, UniformTimebaseV1,
};
use sipi_ieee_com_sparam::SelectedP3cTruncatedResponseV1;
use sipi_link::{convolve_causal_fir_v1, ConvolutionLimitsV1, LinkError};
use sipi_types::{FiniteF64, Seconds, Volts};

pub const P3C_PRBS9_PERIOD_UI_V1: usize = 511;
pub const P3C_PRBS9_OSR_V1: usize = 32;
pub const P3C_PRBS9_PERIODS_V1: usize = 3;
pub const P3C_PRBS9_TOTAL_SAMPLES_V1: usize =
    P3C_PRBS9_PERIOD_UI_V1 * P3C_PRBS9_OSR_V1 * P3C_PRBS9_PERIODS_V1;
pub const P3C_PRBS9_THIRD_PERIOD_START_V1: usize = P3C_PRBS9_PERIOD_UI_V1 * P3C_PRBS9_OSR_V1 * 2;
pub const P3C_SELECTED_TRUNCATED_RESPONSE_SAMPLES_V1: usize = 10_871;
pub const P3C_SELECTED_FULL_LINEAR_SAMPLES_V1: usize =
    P3C_PRBS9_TOTAL_SAMPLES_V1 + P3C_SELECTED_TRUNCATED_RESPONSE_SAMPLES_V1 - 1;
pub const P3C_SELECTED_FULL_LINEAR_MACS_V1: usize =
    P3C_PRBS9_TOTAL_SAMPLES_V1 * P3C_SELECTED_TRUNCATED_RESPONSE_SAMPLES_V1;
pub const P3C_PRBS9_SAMPLE_INTERVAL_BITS_V1: u64 = 0x3d71_2e0b_e826_d695;
pub const P3C_PRBS9_PERIOD_SHA256_V1: &str =
    "4437fb3beb2fa1ca99b4177673c53fc20089ac9cf68b1adaa1e0fad14d742127";

/// Full linear response plus the fixed strict-grid candidate prefix.
#[derive(Clone, Debug, PartialEq)]
pub struct SelectedP3cPrbs9ImpulseCandidateV1 {
    sample_interval: Seconds,
    full_linear_response: Box<[Volts]>,
}

impl SelectedP3cPrbs9ImpulseCandidateV1 {
    pub fn sample_interval(&self) -> Seconds {
        self.sample_interval
    }

    pub fn full_linear_response(&self) -> &[Volts] {
        &self.full_linear_response
    }

    pub fn waveform_prefix(&self) -> &[Volts] {
        &self.full_linear_response[..P3C_PRBS9_TOTAL_SAMPLES_V1]
    }

    pub fn third_period(&self) -> &[Volts] {
        &self.waveform_prefix()[P3C_PRBS9_THIRD_PERIOD_START_V1..]
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum Prbs9ImpulseCandidateErrorV1 {
    KernelSampleIntervalMismatch,
    KernelSampleCountMismatch,
    Contract(LinkContractError),
    Link(LinkError),
    NonFiniteOutput,
}

impl fmt::Display for Prbs9ImpulseCandidateErrorV1 {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            formatter,
            "selected P3C PRBS9 impulse candidate failed: {self:?}"
        )
    }
}

impl Error for Prbs9ImpulseCandidateErrorV1 {}

impl From<LinkContractError> for Prbs9ImpulseCandidateErrorV1 {
    fn from(value: LinkContractError) -> Self {
        Self::Contract(value)
    }
}

impl From<LinkError> for Prbs9ImpulseCandidateErrorV1 {
    fn from(value: LinkError) -> Self {
        Self::Link(value)
    }
}

/// Generate and convolve the sole selected PRBS9 fixed-grid candidate profile.
pub fn generate_selected_p3c_prbs9_impulse_candidate_v1(
    kernel: &SelectedP3cTruncatedResponseV1,
) -> Result<SelectedP3cPrbs9ImpulseCandidateV1, Prbs9ImpulseCandidateErrorV1> {
    if kernel.sample_interval().get().to_bits() != P3C_PRBS9_SAMPLE_INTERVAL_BITS_V1 {
        return Err(Prbs9ImpulseCandidateErrorV1::KernelSampleIntervalMismatch);
    }
    if kernel.sample_count() != P3C_SELECTED_TRUNCATED_RESPONSE_SAMPLES_V1 {
        return Err(Prbs9ImpulseCandidateErrorV1::KernelSampleCountMismatch);
    }
    let plan = fixed_plan(kernel.samples())?;
    let limits = ConvolutionLimitsV1::try_new(
        P3C_SELECTED_FULL_LINEAR_SAMPLES_V1,
        P3C_SELECTED_FULL_LINEAR_MACS_V1,
    )?;
    let received = convolve_causal_fir_v1(&plan, limits)?;
    let samples = received.waveform().samples();
    if samples.len() != P3C_SELECTED_FULL_LINEAR_SAMPLES_V1
        || samples.iter().any(|sample| !sample.get().is_finite())
    {
        return Err(Prbs9ImpulseCandidateErrorV1::NonFiniteOutput);
    }
    Ok(SelectedP3cPrbs9ImpulseCandidateV1 {
        sample_interval: kernel.sample_interval(),
        full_linear_response: samples.to_vec().into_boxed_slice(),
    })
}

fn fixed_plan(kernel: &[FiniteF64]) -> Result<LinkPlanV1, Prbs9ImpulseCandidateErrorV1> {
    let sample_interval = Seconds::try_new(f64::from_bits(P3C_PRBS9_SAMPLE_INTERVAL_BITS_V1))
        .map_err(|_| Prbs9ImpulseCandidateErrorV1::NonFiniteOutput)?;
    let timebase = UniformTimebaseV1::try_new(
        Seconds::try_new(0.0).map_err(|_| Prbs9ImpulseCandidateErrorV1::NonFiniteOutput)?,
        sample_interval,
        P3C_PRBS9_TOTAL_SAMPLES_V1,
    )?;
    let stimulus = projected_prbs9_stimulus()?;
    let channel = CausalFirChannelV1::try_new(sample_interval, kernel.to_vec())?;
    Ok(LinkPlanV1::try_new(
        timebase,
        TxStageV1::DirectLaunch,
        stimulus,
        channel,
        RxStagesV1::bypass(),
    )?)
}

fn projected_prbs9_stimulus() -> Result<Vec<Volts>, Prbs9ImpulseCandidateErrorV1> {
    let symbols = prbs9_symbols();
    let mut output = Vec::with_capacity(P3C_PRBS9_TOTAL_SAMPLES_V1);
    for _ in 0..P3C_PRBS9_PERIODS_V1 {
        for level in symbols {
            output.extend(std::iter::repeat_n(
                Volts::try_new(level).map_err(|_| Prbs9ImpulseCandidateErrorV1::NonFiniteOutput)?,
                P3C_PRBS9_OSR_V1,
            ));
        }
    }
    Ok(output)
}

fn prbs9_symbols() -> [f64; P3C_PRBS9_PERIOD_UI_V1] {
    let mut state = 0x1a5_u16;
    let mut result = [-1.0_f64; P3C_PRBS9_PERIOD_UI_V1];
    for level in &mut result {
        let bit = (state >> 8) & 1;
        *level = if bit == 0 { -1.0 } else { 1.0 };
        let feedback = ((state >> 8) ^ (state >> 4)) & 1;
        state = ((state << 1) & 0x1ff) | feedback;
    }
    result
}

#[cfg(test)]
mod tests {
    use super::*;
    use sha2::{Digest, Sha256};

    #[test]
    fn frozen_prbs9_projection_is_right_continuous_and_digest_bound() {
        let symbols = prbs9_symbols();
        let serialized: String = symbols
            .iter()
            .map(|level| if *level > 0.0 { '1' } else { '0' })
            .collect();
        assert_eq!(
            format!("{:x}", Sha256::digest(serialized.as_bytes())),
            P3C_PRBS9_PERIOD_SHA256_V1
        );
        let source = projected_prbs9_stimulus().unwrap();
        assert_eq!(source.len(), P3C_PRBS9_TOTAL_SAMPLES_V1);
        assert_eq!(source[0].get(), symbols[0]);
        assert_eq!(source[P3C_PRBS9_OSR_V1 - 1].get(), symbols[0]);
        assert_eq!(source[P3C_PRBS9_OSR_V1].get(), symbols[1]);
        assert_eq!(
            &source[..P3C_PRBS9_PERIOD_UI_V1 * P3C_PRBS9_OSR_V1],
            &source[P3C_PRBS9_PERIOD_UI_V1 * P3C_PRBS9_OSR_V1
                ..2 * P3C_PRBS9_PERIOD_UI_V1 * P3C_PRBS9_OSR_V1]
        );
    }

    #[test]
    fn private_convolution_has_zero_prehistory_full_tail_and_no_dt_scaling() {
        let gain = vec![
            FiniteF64::try_new(1.0, "gain").unwrap(),
            FiniteF64::try_new(0.5, "gain").unwrap(),
        ];
        let plan = fixed_plan_for_test(&[1.0, -1.0], gain).unwrap();
        let output =
            convolve_causal_fir_v1(&plan, ConvolutionLimitsV1::try_new(3, 4).unwrap()).unwrap();
        let values: Vec<f64> = output
            .waveform()
            .samples()
            .iter()
            .map(|sample| sample.get())
            .collect();
        assert_eq!(values, [1.0, -0.5, -0.5]);
    }

    fn fixed_plan_for_test(
        stimulus: &[f64],
        gain: Vec<FiniteF64>,
    ) -> Result<LinkPlanV1, Prbs9ImpulseCandidateErrorV1> {
        let dt = Seconds::try_new(f64::from_bits(P3C_PRBS9_SAMPLE_INTERVAL_BITS_V1)).unwrap();
        Ok(LinkPlanV1::try_new(
            UniformTimebaseV1::try_new(Seconds::try_new(0.0).unwrap(), dt, stimulus.len())?,
            TxStageV1::DirectLaunch,
            stimulus
                .iter()
                .copied()
                .map(Volts::try_new)
                .collect::<Result<Vec<_>, _>>()
                .map_err(|_| Prbs9ImpulseCandidateErrorV1::NonFiniteOutput)?,
            CausalFirChannelV1::try_new(dt, gain)?,
            RxStagesV1::bypass(),
        )?)
    }
}
