// SPDX-License-Identifier: BSD-3-Clause
// Copyright (c) 2025, 802-COM Authors
//
// Direct-port source: IEEE 802-COM `src/s21_to_impulse_DC.m` at
// d4ecd4597a98782887933b5df4c4796da2474195, blob
// f426fb2119dc1cf9c2a2f677e60c3a1f31cb27a3, SHA-256
// b2884926b204fdfddc1c309c35d46ed7744c696e19df3abcd7d91157e9e539c0.
// The selected policy and line map are recorded in SOURCE-MAP.md.

//! Fixed peak-relative response truncation adapted from the selected BSD
//! source. It preserves leading samples and sample interval; it is neither
//! delay extraction nor causal-FIR/candidate-waveform admission.

use std::{error::Error, fmt};

use sipi_types::{FiniteF64, Seconds};

use crate::SelectedP3cCausalResponseV1;

pub const SELECTED_TRUNCATION_THRESHOLD_V1: f64 = 1.0e-3;
pub const SELECTED_TRUNCATION_MAX_INPUT_SAMPLES_V1: usize = 51_200;

/// Whether the source-selected suffix had zero or nonzero L2 norm.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum SelectedP3cTruncationTailV1 {
    ZeroTail,
    NonZeroTail,
}

/// A finite prefix selected by the fixed peak-relative truncation policy.
#[derive(Clone, Debug, PartialEq)]
pub struct SelectedP3cTruncatedResponseV1 {
    sample_interval: Seconds,
    samples: Box<[FiniteF64]>,
    original_sample_count: usize,
    dropped_l2_over_total_l2: FiniteF64,
    tail: SelectedP3cTruncationTailV1,
}

impl SelectedP3cTruncatedResponseV1 {
    pub fn sample_interval(&self) -> Seconds {
        self.sample_interval
    }
    pub fn samples(&self) -> &[FiniteF64] {
        &self.samples
    }
    pub fn sample_count(&self) -> usize {
        self.samples.len()
    }
    pub fn original_sample_count(&self) -> usize {
        self.original_sample_count
    }
    pub fn dropped_l2_over_total_l2(&self) -> FiniteF64 {
        self.dropped_l2_over_total_l2
    }
    pub fn tail(&self) -> SelectedP3cTruncationTailV1 {
        self.tail
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum TruncationErrorV1 {
    EmptyInput,
    InputSampleLimitExceeded,
    NonFiniteCalculation,
    AllZeroInput,
    NoThresholdCrossing,
}

impl fmt::Display for TruncationErrorV1 {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            formatter,
            "selected IEEE COM response truncation failed: {self:?}"
        )
    }
}

impl Error for TruncationErrorV1 {}

/// Keep the prefix through the last sample strictly above `peak * 1e-3`.
/// Leading samples, including leading zeros, retain their original indices.
pub fn truncate_selected_p3c_response_v1(
    input: &SelectedP3cCausalResponseV1,
) -> Result<SelectedP3cTruncatedResponseV1, TruncationErrorV1> {
    let samples = input.samples();
    if samples.is_empty() {
        return Err(TruncationErrorV1::EmptyInput);
    }
    if samples.len() > SELECTED_TRUNCATION_MAX_INPUT_SAMPLES_V1 {
        return Err(TruncationErrorV1::InputSampleLimitExceeded);
    }
    let peak = samples
        .iter()
        .map(|sample| sample.get().abs())
        .fold(0.0_f64, f64::max);
    if !(peak.is_finite() && peak > 0.0) {
        return Err(TruncationErrorV1::AllZeroInput);
    }
    let threshold = peak * SELECTED_TRUNCATION_THRESHOLD_V1;
    if !threshold.is_finite() {
        return Err(TruncationErrorV1::NonFiniteCalculation);
    }
    let retained_count = samples
        .iter()
        .rposition(|sample| sample.get().abs() > threshold)
        .and_then(|index| index.checked_add(1))
        .ok_or(TruncationErrorV1::NoThresholdCrossing)?;
    let total_l2 = scaled_l2(samples)?;
    let dropped_l2 = scaled_l2(&samples[retained_count..])?;
    let ratio = dropped_l2 / total_l2;
    if !(ratio.is_finite() && (0.0..=1.0).contains(&ratio)) {
        return Err(TruncationErrorV1::NonFiniteCalculation);
    }
    let tail = if dropped_l2 == 0.0 {
        SelectedP3cTruncationTailV1::ZeroTail
    } else {
        SelectedP3cTruncationTailV1::NonZeroTail
    };
    Ok(SelectedP3cTruncatedResponseV1 {
        sample_interval: input.sample_interval(),
        samples: samples[..retained_count].to_vec().into_boxed_slice(),
        original_sample_count: samples.len(),
        dropped_l2_over_total_l2: FiniteF64::try_new(ratio, "dropped L2 ratio")
            .map_err(|_| TruncationErrorV1::NonFiniteCalculation)?,
        tail,
    })
}

fn scaled_l2(samples: &[FiniteF64]) -> Result<f64, TruncationErrorV1> {
    let mut scale = 0.0_f64;
    let mut sum = 1.0_f64;
    for sample in samples {
        let value = sample.get().abs();
        if !value.is_finite() {
            return Err(TruncationErrorV1::NonFiniteCalculation);
        }
        if value > scale {
            if scale == 0.0 {
                sum = 1.0;
            } else {
                let relative = scale / value;
                sum = 1.0 + sum * relative * relative;
            }
            scale = value;
        } else if scale != 0.0 {
            let relative = value / scale;
            sum += relative * relative;
        }
        if !sum.is_finite() {
            return Err(TruncationErrorV1::NonFiniteCalculation);
        }
    }
    let norm = scale * sum.sqrt();
    norm.is_finite()
        .then_some(norm)
        .ok_or(TruncationErrorV1::NonFiniteCalculation)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::s21_to_causal_v1::test_causal_response;

    #[test]
    fn retains_leading_delay_and_last_strict_crossing() {
        let input = test_causal_response(&[0.0, 0.0, -2.0, 0.003, 0.003, 0.0], 0.25);
        let output = truncate_selected_p3c_response_v1(&input).unwrap();
        assert_eq!(output.samples().len(), 5);
        assert_eq!(output.samples()[0].get(), 0.0);
        assert_eq!(output.sample_interval().get(), 0.25);
        assert_eq!(output.tail(), SelectedP3cTruncationTailV1::ZeroTail);
    }

    #[test]
    fn threshold_is_strict_and_nonzero_tail_is_diagnostic_only() {
        let input = test_causal_response(&[1.0, 0.001, 0.0005], 1.0);
        let output = truncate_selected_p3c_response_v1(&input).unwrap();
        assert_eq!(output.samples().len(), 1);
        assert_eq!(output.tail(), SelectedP3cTruncationTailV1::NonZeroTail);
        assert!(output.dropped_l2_over_total_l2().get() > 0.0);
    }

    #[test]
    fn zero_and_full_length_edges_are_fail_closed_or_deterministic() {
        let zero = test_causal_response(&[0.0, 0.0], 1.0);
        assert_eq!(
            truncate_selected_p3c_response_v1(&zero).unwrap_err(),
            TruncationErrorV1::AllZeroInput
        );
        let full = test_causal_response(&[0.0, 1.0], 1.0);
        let output = truncate_selected_p3c_response_v1(&full).unwrap();
        assert_eq!(output.sample_count(), 2);
        assert_eq!(output.tail(), SelectedP3cTruncationTailV1::ZeroTail);
        assert_eq!(output.dropped_l2_over_total_l2().get(), 0.0);
    }
}
