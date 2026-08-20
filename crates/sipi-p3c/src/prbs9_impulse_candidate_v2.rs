//! Fixed PRBS9 discrete candidate bridge with the selected finite-edge policy.
//!
//! The product grid is unchanged. For every UI after sample zero, phase zero
//! retains the prior symbol and phases 1 through 31 use the current symbol.
//! This is a fixed strobe ownership rule, not alignment or ADS solver parity.

use std::{error::Error, fmt};

use sipi_contracts::{
    CausalFirChannelV1, LinkContractError, LinkPlanV1, RxStagesV1, TxStageV1, UniformTimebaseV1,
};
use sipi_ieee_com_sparam::SelectedP3cTruncatedResponseV1;
use sipi_link::{ConvolutionLimitsV1, LinkError, convolve_causal_fir_v1};
use sipi_types::{FiniteF64, Seconds, Volts};

use crate::{
    P3C_PRBS9_OSR_V1, P3C_PRBS9_PERIOD_UI_V1, P3C_PRBS9_PERIODS_V1,
    P3C_PRBS9_SAMPLE_INTERVAL_BITS_V1, P3C_PRBS9_THIRD_PERIOD_START_V1, P3C_PRBS9_TOTAL_SAMPLES_V1,
    P3C_SELECTED_FULL_LINEAR_MACS_V1, P3C_SELECTED_FULL_LINEAR_SAMPLES_V1,
    P3C_SELECTED_TRUNCATED_RESPONSE_SAMPLES_V1,
};

/// Full linear response plus the fixed strict-grid candidate prefix.
#[derive(Clone, Debug, PartialEq)]
pub struct SelectedP3cPrbs9ImpulseCandidateV2 {
    sample_interval: Seconds,
    full_linear_response: Box<[Volts]>,
}

impl SelectedP3cPrbs9ImpulseCandidateV2 {
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
pub enum Prbs9ImpulseCandidateErrorV2 {
    KernelSampleIntervalMismatch,
    KernelSampleCountMismatch,
    Contract(LinkContractError),
    Link(LinkError),
    NonFiniteOutput,
}

impl fmt::Display for Prbs9ImpulseCandidateErrorV2 {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            formatter,
            "selected P3C PRBS9 finite-edge candidate failed: {self:?}"
        )
    }
}

impl Error for Prbs9ImpulseCandidateErrorV2 {}

impl From<LinkContractError> for Prbs9ImpulseCandidateErrorV2 {
    fn from(value: LinkContractError) -> Self {
        Self::Contract(value)
    }
}

impl From<LinkError> for Prbs9ImpulseCandidateErrorV2 {
    fn from(value: LinkError) -> Self {
        Self::Link(value)
    }
}

/// Generate and convolve the one selected finite-edge PRBS9 candidate profile.
pub fn generate_selected_p3c_prbs9_impulse_candidate_v2(
    kernel: &SelectedP3cTruncatedResponseV1,
) -> Result<SelectedP3cPrbs9ImpulseCandidateV2, Prbs9ImpulseCandidateErrorV2> {
    if kernel.sample_interval().get().to_bits() != P3C_PRBS9_SAMPLE_INTERVAL_BITS_V1 {
        return Err(Prbs9ImpulseCandidateErrorV2::KernelSampleIntervalMismatch);
    }
    if kernel.sample_count() != P3C_SELECTED_TRUNCATED_RESPONSE_SAMPLES_V1 {
        return Err(Prbs9ImpulseCandidateErrorV2::KernelSampleCountMismatch);
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
        return Err(Prbs9ImpulseCandidateErrorV2::NonFiniteOutput);
    }
    Ok(SelectedP3cPrbs9ImpulseCandidateV2 {
        sample_interval: kernel.sample_interval(),
        full_linear_response: samples.to_vec().into_boxed_slice(),
    })
}

fn fixed_plan(kernel: &[FiniteF64]) -> Result<LinkPlanV1, Prbs9ImpulseCandidateErrorV2> {
    let sample_interval = Seconds::try_new(f64::from_bits(P3C_PRBS9_SAMPLE_INTERVAL_BITS_V1))
        .map_err(|_| Prbs9ImpulseCandidateErrorV2::NonFiniteOutput)?;
    let timebase = UniformTimebaseV1::try_new(
        Seconds::try_new(0.0).map_err(|_| Prbs9ImpulseCandidateErrorV2::NonFiniteOutput)?,
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

fn projected_prbs9_stimulus() -> Result<Vec<Volts>, Prbs9ImpulseCandidateErrorV2> {
    let symbols = prbs9_symbols();
    let mut output = Vec::with_capacity(P3C_PRBS9_TOTAL_SAMPLES_V1);
    for period in 0..P3C_PRBS9_PERIODS_V1 {
        for ui in 0..P3C_PRBS9_PERIOD_UI_V1 {
            let current = symbols[ui];
            if period == 0 && ui == 0 {
                output.extend(std::iter::repeat_n(volts(current)?, P3C_PRBS9_OSR_V1));
                continue;
            }
            let prior = if ui == 0 {
                symbols[P3C_PRBS9_PERIOD_UI_V1 - 1]
            } else {
                symbols[ui - 1]
            };
            output.push(volts(prior)?);
            output.extend(std::iter::repeat_n(volts(current)?, P3C_PRBS9_OSR_V1 - 1));
        }
    }
    Ok(output)
}

fn volts(value: f64) -> Result<Volts, Prbs9ImpulseCandidateErrorV2> {
    Volts::try_new(value).map_err(|_| Prbs9ImpulseCandidateErrorV2::NonFiniteOutput)
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
    use crate::P3C_PRBS9_PERIOD_SHA256_V1;
    use sha2::{Digest, Sha256};

    #[test]
    fn frozen_prbs9_sequence_and_finite_edge_boundary_ownership_are_bound() {
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

        assert_eq!(source[P3C_PRBS9_OSR_V1].get(), symbols[0]);
        assert_eq!(source[P3C_PRBS9_OSR_V1 + 1].get(), symbols[1]);
        assert_eq!(source[2 * P3C_PRBS9_OSR_V1].get(), symbols[1]);
        assert_eq!(source[2 * P3C_PRBS9_OSR_V1 + 1].get(), symbols[2]);

        let period = P3C_PRBS9_PERIOD_UI_V1 * P3C_PRBS9_OSR_V1;
        assert_eq!(source[period].get(), symbols[P3C_PRBS9_PERIOD_UI_V1 - 1]);
        assert_eq!(source[period + 1].get(), symbols[0]);
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
    ) -> Result<LinkPlanV1, Prbs9ImpulseCandidateErrorV2> {
        let dt = Seconds::try_new(f64::from_bits(P3C_PRBS9_SAMPLE_INTERVAL_BITS_V1)).unwrap();
        Ok(LinkPlanV1::try_new(
            UniformTimebaseV1::try_new(Seconds::try_new(0.0).unwrap(), dt, stimulus.len())?,
            TxStageV1::DirectLaunch,
            stimulus
                .iter()
                .copied()
                .map(Volts::try_new)
                .collect::<Result<Vec<_>, _>>()
                .map_err(|_| Prbs9ImpulseCandidateErrorV2::NonFiniteOutput)?,
            CausalFirChannelV1::try_new(dt, gain)?,
            RxStagesV1::bypass(),
        )?)
    }
}
