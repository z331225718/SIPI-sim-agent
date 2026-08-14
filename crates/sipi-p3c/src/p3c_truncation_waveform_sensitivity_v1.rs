//! Fixed third-period diagnostic for the selected truncation sensitivity lane.
//!
//! This is not a generic link-FIR or a candidate route. It consumes the
//! bounded causality response only to measure the effect of omitting the
//! selected 1e-3 truncation operation on the same zero-prehistory PRBS9 input.

use std::{error::Error, fmt};

use sipi_ieee_com_sparam::SelectedP3cCausalResponseV1;
use sipi_types::{FiniteF64, Seconds, Volts};

pub const P3C_FULL_CAUSAL_RESPONSE_SAMPLES_V1: usize = 51_200;
pub const P3C_TRUNCATION_SENSITIVITY_THIRD_PERIOD_START_V1: usize = 32_704;
pub const P3C_TRUNCATION_SENSITIVITY_THIRD_PERIOD_SAMPLES_V1: usize = 16_352;
pub const P3C_TRUNCATION_SENSITIVITY_TOTAL_PRBS9_SAMPLES_V1: usize = 49_056;
pub const P3C_TRUNCATION_SENSITIVITY_MACS_V1: usize = 668_477_936;
pub const P3C_TRUNCATION_SENSITIVITY_SAMPLE_INTERVAL_BITS_V1: u64 = 0x3d71_2e0b_e826_d695;

/// The untrimmed bounded-causality response over the fixed third PRBS period.
#[derive(Clone, Debug, PartialEq)]
pub struct SelectedP3cFullCausalThirdPeriodDiagnosticV1 {
    sample_interval: Seconds,
    samples: Box<[Volts]>,
}

impl SelectedP3cFullCausalThirdPeriodDiagnosticV1 {
    pub fn sample_interval(&self) -> Seconds {
        self.sample_interval
    }

    pub fn samples(&self) -> &[Volts] {
        &self.samples
    }

    pub fn sample_count(&self) -> usize {
        self.samples.len()
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum TruncationWaveformSensitivityErrorV1 {
    KernelSampleIntervalMismatch,
    KernelSampleCountMismatch,
    FixedWorkMismatch,
    NonFiniteOutput { output_index: usize },
}

impl fmt::Display for TruncationWaveformSensitivityErrorV1 {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            formatter,
            "selected P3C truncation waveform sensitivity diagnostic failed: {self:?}"
        )
    }
}

impl Error for TruncationWaveformSensitivityErrorV1 {}

/// Directly evaluate only the fixed third-period output with zero prehistory.
///
/// The kernel is visited from index zero upward for every output. No FFT,
/// circular wrap, alignment, transform, or tail selection is available.
pub fn diagnose_selected_p3c_full_causal_third_period_v1(
    kernel: &SelectedP3cCausalResponseV1,
) -> Result<SelectedP3cFullCausalThirdPeriodDiagnosticV1, TruncationWaveformSensitivityErrorV1> {
    if kernel.sample_interval().get().to_bits() != P3C_TRUNCATION_SENSITIVITY_SAMPLE_INTERVAL_BITS_V1 {
        return Err(TruncationWaveformSensitivityErrorV1::KernelSampleIntervalMismatch);
    }
    if kernel.sample_count() != P3C_FULL_CAUSAL_RESPONSE_SAMPLES_V1 {
        return Err(TruncationWaveformSensitivityErrorV1::KernelSampleCountMismatch);
    }
    let source = projected_prbs9_source();
    let samples = convolve_fixed_range(&source, kernel.samples(), P3C_TRUNCATION_SENSITIVITY_THIRD_PERIOD_START_V1, P3C_TRUNCATION_SENSITIVITY_TOTAL_PRBS9_SAMPLES_V1)?;
    let endpoint_sum = (P3C_TRUNCATION_SENSITIVITY_THIRD_PERIOD_START_V1 + 1)
        .checked_add(P3C_TRUNCATION_SENSITIVITY_TOTAL_PRBS9_SAMPLES_V1)
        .ok_or(TruncationWaveformSensitivityErrorV1::FixedWorkMismatch)?;
    let expected_work = P3C_TRUNCATION_SENSITIVITY_THIRD_PERIOD_SAMPLES_V1
        .checked_mul(endpoint_sum)
        .and_then(|value| value.checked_div(2))
        .ok_or(TruncationWaveformSensitivityErrorV1::FixedWorkMismatch)?;
    if expected_work != P3C_TRUNCATION_SENSITIVITY_MACS_V1 {
        return Err(TruncationWaveformSensitivityErrorV1::FixedWorkMismatch);
    }
    Ok(SelectedP3cFullCausalThirdPeriodDiagnosticV1 {
        sample_interval: kernel.sample_interval(),
        samples: samples.into_boxed_slice(),
    })
}

fn convolve_fixed_range(
    source: &[Volts],
    kernel: &[FiniteF64],
    first_output: usize,
    end_output: usize,
) -> Result<Vec<Volts>, TruncationWaveformSensitivityErrorV1> {
    let mut output = Vec::with_capacity(end_output.saturating_sub(first_output));
    for output_index in first_output..end_output {
        let last_kernel = output_index.min(kernel.len() - 1);
        let mut sum = 0.0;
        for kernel_index in 0..=last_kernel {
            let source_index = output_index - kernel_index;
            let source_value = source.get(source_index).map_or(0.0, |value| value.get());
            let product = source_value * kernel[kernel_index].get();
            if !product.is_finite() {
                return Err(TruncationWaveformSensitivityErrorV1::NonFiniteOutput { output_index });
            }
            sum += product;
            if !sum.is_finite() {
                return Err(TruncationWaveformSensitivityErrorV1::NonFiniteOutput { output_index });
            }
        }
        output.push(
            Volts::try_new(sum).map_err(|_| {
                TruncationWaveformSensitivityErrorV1::NonFiniteOutput { output_index }
            })?,
        );
    }
    Ok(output)
}

fn projected_prbs9_source() -> Vec<Volts> {
    let mut state = 0x1a5_u16;
    let mut symbols = [-1.0_f64; 511];
    for level in &mut symbols {
        *level = if (state >> 8) & 1 == 0 { -1.0 } else { 1.0 };
        let feedback = ((state >> 8) ^ (state >> 4)) & 1;
        state = ((state << 1) & 0x1ff) | feedback;
    }
    (0..P3C_TRUNCATION_SENSITIVITY_TOTAL_PRBS9_SAMPLES_V1)
        .map(|index| Volts::try_new(symbols[(index / 32) % 511]).expect("fixed PRBS level"))
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn source(values: &[f64]) -> Vec<Volts> {
        values.iter().copied().map(Volts::try_new).collect::<Result<_, _>>().unwrap()
    }

    fn kernel(values: &[f64]) -> Vec<FiniteF64> {
        values
            .iter()
            .copied()
            .map(|value| FiniteF64::try_new(value, "test kernel"))
            .collect::<Result<_, _>>()
            .unwrap()
    }

    #[test]
    fn direct_range_keeps_kernel_order_and_zero_prehistory() {
        let values = convolve_fixed_range(&source(&[2.0, 3.0, 5.0]), &kernel(&[7.0, 11.0]), 0, 4)
            .unwrap()
            .into_iter()
            .map(|value| value.get())
            .collect::<Vec<_>>();
        assert_eq!(values, [14.0, 43.0, 68.0, 55.0]);
    }

    #[test]
    fn zero_tail_has_no_effect_in_the_same_direct_order() {
        let input = source(&[1.0, -2.0, 4.0]);
        assert_eq!(
            convolve_fixed_range(&input, &kernel(&[3.0]), 0, 3).unwrap(),
            convolve_fixed_range(&input, &kernel(&[3.0, 0.0, 0.0]), 0, 3).unwrap(),
        );
    }

    #[test]
    fn fixed_prbs_projection_is_right_continuous() {
        let source = projected_prbs9_source();
        assert_eq!(source.len(), P3C_TRUNCATION_SENSITIVITY_TOTAL_PRBS9_SAMPLES_V1);
        assert_eq!(source[0], source[31]);
        assert!(source
            .chunks_exact(32)
            .any(|ui| ui.first().is_some_and(|first| ui.iter().all(|value| value == first))));
        assert!(source
            .chunks_exact(32)
            .collect::<Vec<_>>()
            .windows(2)
            .any(|pair| pair[0][0] != pair[1][0]));
    }

    #[test]
    fn fixed_work_count_preserves_the_half_operation() {
        let endpoint_sum = (P3C_TRUNCATION_SENSITIVITY_THIRD_PERIOD_START_V1 + 1)
            + P3C_TRUNCATION_SENSITIVITY_TOTAL_PRBS9_SAMPLES_V1;
        assert_eq!(
            P3C_TRUNCATION_SENSITIVITY_THIRD_PERIOD_SAMPLES_V1 * endpoint_sum / 2,
            P3C_TRUNCATION_SENSITIVITY_MACS_V1,
        );
    }
}
