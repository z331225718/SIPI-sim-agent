// SPDX-License-Identifier: BSD-3-Clause
// Copyright (c) 2025, 802-COM Authors
//
// Direct-port source: IEEE 802-COM `src/s21_to_impulse_DC.m` at
// d4ecd4597a98782887933b5df4c4796da2474195, blob
// f426fb2119dc1cf9c2a2f677e60c3a1f31cb27a3, SHA-256
// b2884926b204fdfddc1c309c35d46ed7744c696e19df3abcd7d91157e9e539c0.
// The selected policy and line map are recorded in SOURCE-MAP.md.

//! Fixed, bounded Alternating Projections causality enforcement adapted from
//! the selected BSD source. It is neither delay extraction, truncation,
//! passivity repair, convolution, nor a candidate waveform route.

use std::{error::Error, fmt};

use rustfft::{FftPlanner, num_complex::Complex};
use sipi_types::{FiniteF64, Seconds};

use crate::{
    RawPeriodicTransformErrorV1, SelectedP3cUniformSpectrumV1,
    inverse_selected_p3c_uniform_spectrum_v1,
};

pub const SELECTED_CAUSALITY_PULSE_TOLERANCE_V1: f64 = 0.05;
pub const SELECTED_CAUSALITY_RELATIVE_TOLERANCE_V1: f64 = 0.006;
pub const SELECTED_CAUSALITY_DIFFERENCE_TOLERANCE_V1: f64 = 1.0e-4;
pub const SELECTED_CAUSALITY_MAX_ITERATIONS_V1: usize = 256;
pub const SELECTED_CAUSALITY_INVERSE_ABSOLUTE_RESIDUAL_LIMIT_V1: f64 = 1.0e-12;
pub const SELECTED_CAUSALITY_INVERSE_RELATIVE_RESIDUAL_LIMIT_V1: f64 = 1.0e-10;

/// The fixed stop condition observed by the bounded source loop.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum SelectedP3cCausalityStopV1 {
    RelativeError,
    SuccessiveErrorDifference,
}

/// A finite causal-response candidate from the selected bounded projection.
#[derive(Clone, Debug, PartialEq)]
pub struct SelectedP3cCausalResponseV1 {
    sample_interval: Seconds,
    samples: Box<[FiniteF64]>,
    iteration_count: usize,
    final_error: FiniteF64,
    stop: SelectedP3cCausalityStopV1,
}

impl SelectedP3cCausalResponseV1 {
    pub fn sample_interval(&self) -> Seconds {
        self.sample_interval
    }

    pub fn samples(&self) -> &[FiniteF64] {
        &self.samples
    }

    pub fn sample_count(&self) -> usize {
        self.samples.len()
    }

    pub fn iteration_count(&self) -> usize {
        self.iteration_count
    }

    pub fn final_error(&self) -> FiniteF64 {
        self.final_error
    }

    pub fn stop(&self) -> SelectedP3cCausalityStopV1 {
        self.stop
    }
}

#[cfg(test)]
pub(crate) fn test_causal_response(
    samples: &[f64],
    sample_interval: f64,
) -> SelectedP3cCausalResponseV1 {
    SelectedP3cCausalResponseV1 {
        sample_interval: Seconds::try_new(sample_interval).unwrap(),
        samples: samples
            .iter()
            .map(|value| FiniteF64::try_new(*value, "test causal sample").unwrap())
            .collect::<Vec<_>>()
            .into_boxed_slice(),
        iteration_count: 1,
        final_error: FiniteF64::try_new(0.0, "test final error").unwrap(),
        stop: SelectedP3cCausalityStopV1::RelativeError,
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum CausalityEnforcementErrorV1 {
    RawPeriodicInput(RawPeriodicTransformErrorV1),
    InputAllZero,
    NoFirstHalfThresholdCrossing,
    IterationBecameAllZero,
    NonPositiveErrorDenominator,
    InverseImaginaryResidue,
    NonFiniteCalculation,
    IterationLimitExceeded,
}

impl fmt::Display for CausalityEnforcementErrorV1 {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            formatter,
            "selected IEEE COM bounded causality enforcement failed: {self:?}"
        )
    }
}

impl Error for CausalityEnforcementErrorV1 {}

/// Apply the selected bounded Alternating Projections loop to the fixed
/// uniform spectrum. The loop is always enabled and retains the source's
/// pre-projection, zero-window response when either stop condition fires.
pub fn enforce_selected_p3c_causality_v1(
    input: &SelectedP3cUniformSpectrumV1,
) -> Result<SelectedP3cCausalResponseV1, CausalityEnforcementErrorV1> {
    let raw = inverse_selected_p3c_uniform_spectrum_v1(input)
        .map_err(CausalityEnforcementErrorV1::RawPeriodicInput)?;
    let mut current = raw
        .samples()
        .iter()
        .map(|sample| sample.get())
        .collect::<Vec<_>>();
    if current.iter().all(|value| *value == 0.0) {
        return Err(CausalityEnforcementErrorV1::InputAllZero);
    }
    let start = first_half_start_index(&current)?;
    let magnitude = hermitian_magnitude(input)?;
    let mut previous_error = f64::INFINITY;
    for iteration in 1..=SELECTED_CAUSALITY_MAX_ITERATIONS_V1 {
        apply_source_zero_windows(&mut current, start)?;
        if current.iter().all(|value| *value == 0.0) {
            return Err(CausalityEnforcementErrorV1::IterationBecameAllZero);
        }
        let modified = fixed_magnitude_projection(&current, &magnitude)?;
        let delta = current
            .iter()
            .zip(&modified)
            .map(|(left, right)| (left - right).abs())
            .fold(0.0_f64, f64::max);
        let denominator = current.iter().copied().fold(f64::NEG_INFINITY, f64::max);
        if !(delta.is_finite() && denominator.is_finite() && denominator > 0.0) {
            return Err(CausalityEnforcementErrorV1::NonPositiveErrorDenominator);
        }
        let error = delta / denominator;
        if !error.is_finite() {
            return Err(CausalityEnforcementErrorV1::NonFiniteCalculation);
        }
        let stop = if error < SELECTED_CAUSALITY_RELATIVE_TOLERANCE_V1 {
            Some(SelectedP3cCausalityStopV1::RelativeError)
        } else if (previous_error - error).abs() < SELECTED_CAUSALITY_DIFFERENCE_TOLERANCE_V1 {
            Some(SelectedP3cCausalityStopV1::SuccessiveErrorDifference)
        } else {
            None
        };
        if let Some(stop) = stop {
            let samples = current
                .into_iter()
                .map(|value| FiniteF64::try_new(value, "causal response sample"))
                .collect::<Result<Vec<_>, _>>()
                .map_err(|_| CausalityEnforcementErrorV1::NonFiniteCalculation)?;
            return Ok(SelectedP3cCausalResponseV1 {
                sample_interval: raw.sample_interval(),
                samples: samples.into_boxed_slice(),
                iteration_count: iteration,
                final_error: FiniteF64::try_new(error, "causality final error")
                    .map_err(|_| CausalityEnforcementErrorV1::NonFiniteCalculation)?,
                stop,
            });
        }
        previous_error = error;
        current = modified;
    }
    Err(CausalityEnforcementErrorV1::IterationLimitExceeded)
}

// MATLAB's `floor(L/2):end` is one-based.  Its zero-based start is therefore
// `floor(L/2) - 1`, retaining the source overlap with the first-half window.
fn apply_source_zero_windows(
    samples: &mut [f64],
    start: usize,
) -> Result<(), CausalityEnforcementErrorV1> {
    let suffix_start = samples
        .len()
        .checked_div(2)
        .and_then(|half| half.checked_sub(1))
        .ok_or(CausalityEnforcementErrorV1::NonFiniteCalculation)?;
    if start >= samples.len() {
        return Err(CausalityEnforcementErrorV1::NonFiniteCalculation);
    }
    samples[..=start].fill(0.0);
    samples[suffix_start..].fill(0.0);
    Ok(())
}

fn first_half_start_index(samples: &[f64]) -> Result<usize, CausalityEnforcementErrorV1> {
    let half = samples.len() / 2;
    let first_half_peak = samples[..half]
        .iter()
        .map(|value| value.abs())
        .fold(0.0_f64, f64::max);
    if !(first_half_peak.is_finite() && first_half_peak > 0.0) {
        return Err(CausalityEnforcementErrorV1::NoFirstHalfThresholdCrossing);
    }
    samples[..half]
        .iter()
        .position(|value| value.abs() > first_half_peak * SELECTED_CAUSALITY_PULSE_TOLERANCE_V1)
        .ok_or(CausalityEnforcementErrorV1::NoFirstHalfThresholdCrossing)
}

fn hermitian_magnitude(
    input: &SelectedP3cUniformSpectrumV1,
) -> Result<Vec<f64>, CausalityEnforcementErrorV1> {
    let values = input.values();
    let length = values
        .len()
        .checked_sub(1)
        .and_then(|count| count.checked_mul(2))
        .ok_or(CausalityEnforcementErrorV1::NonFiniteCalculation)?;
    let mut magnitude = vec![0.0; length];
    magnitude[0] = values[0].real().abs();
    for (index, value) in values.iter().enumerate().skip(1).take(values.len() - 2) {
        let item = value.real().hypot(value.imaginary());
        magnitude[index] = item;
        magnitude[length - index] = item;
    }
    magnitude[length / 2] = values[values.len() - 1].real().abs();
    if magnitude.iter().any(|value| !value.is_finite()) {
        return Err(CausalityEnforcementErrorV1::NonFiniteCalculation);
    }
    Ok(magnitude)
}

fn fixed_magnitude_projection(
    samples: &[f64],
    magnitude: &[f64],
) -> Result<Vec<f64>, CausalityEnforcementErrorV1> {
    if samples.len() != magnitude.len() {
        return Err(CausalityEnforcementErrorV1::NonFiniteCalculation);
    }
    let mut spectrum = samples
        .iter()
        .map(|value| Complex::new(*value, 0.0))
        .collect::<Vec<_>>();
    FftPlanner::<f64>::new()
        .plan_fft_forward(spectrum.len())
        .process(&mut spectrum);
    for (value, fixed_magnitude) in spectrum.iter_mut().zip(magnitude) {
        let phase = value.arg();
        if !(phase.is_finite() && fixed_magnitude.is_finite()) {
            return Err(CausalityEnforcementErrorV1::NonFiniteCalculation);
        }
        *value = Complex::from_polar(*fixed_magnitude, phase);
    }
    FftPlanner::<f64>::new()
        .plan_fft_inverse(spectrum.len())
        .process(&mut spectrum);
    let scale = 1.0 / spectrum.len() as f64;
    let maximum_real = spectrum
        .iter()
        .map(|value| (value.re * scale).abs())
        .fold(0.0_f64, f64::max);
    let maximum_imaginary = spectrum
        .iter()
        .map(|value| (value.im * scale).abs())
        .fold(0.0_f64, f64::max);
    if !(maximum_real.is_finite() && maximum_imaginary.is_finite()) {
        return Err(CausalityEnforcementErrorV1::NonFiniteCalculation);
    }
    if maximum_imaginary
        > SELECTED_CAUSALITY_INVERSE_ABSOLUTE_RESIDUAL_LIMIT_V1
            + SELECTED_CAUSALITY_INVERSE_RELATIVE_RESIDUAL_LIMIT_V1 * maximum_real
    {
        return Err(CausalityEnforcementErrorV1::InverseImaginaryResidue);
    }
    spectrum
        .into_iter()
        .map(|value| {
            let real = value.re * scale;
            real.is_finite()
                .then_some(real)
                .ok_or(CausalityEnforcementErrorV1::NonFiniteCalculation)
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::interp_sparam_v1::test_uniform_spectrum;
    use sipi_types::Complex64;

    fn complex(real: f64, imaginary: f64) -> Complex64 {
        Complex64::try_new(real, imaginary).unwrap()
    }

    #[test]
    fn all_zero_window_rejects_before_projection() {
        let input = test_uniform_spectrum(vec![complex(1.0, 0.0); 5], 1.0);
        assert_eq!(
            enforce_selected_p3c_causality_v1(&input).unwrap_err(),
            CausalityEnforcementErrorV1::IterationBecameAllZero
        );
    }

    #[test]
    fn all_zero_input_and_no_first_half_peak_reject() {
        let zero = test_uniform_spectrum(vec![complex(0.0, 0.0); 5], 1.0);
        assert_eq!(
            enforce_selected_p3c_causality_v1(&zero).unwrap_err(),
            CausalityEnforcementErrorV1::InputAllZero
        );
        assert_eq!(
            first_half_start_index(&[0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0]),
            Err(CausalityEnforcementErrorV1::NoFirstHalfThresholdCrossing)
        );
        let projected = test_uniform_spectrum(
            (0..5)
                .map(|index| {
                    let phase = -std::f64::consts::TAU * 2.0 * index as f64 / 8.0;
                    complex(1.0 + 0.5 * phase.cos(), 0.5 * phase.sin())
                })
                .collect(),
            1.0,
        );
        assert!(matches!(
            enforce_selected_p3c_causality_v1(&projected)
                .unwrap()
                .stop(),
            SelectedP3cCausalityStopV1::RelativeError
                | SelectedP3cCausalityStopV1::SuccessiveErrorDifference
        ));
    }

    #[test]
    fn public_api_only_accepts_fixed_uniform_spectrum() {
        let function: fn(
            &SelectedP3cUniformSpectrumV1,
        )
            -> Result<SelectedP3cCausalResponseV1, CausalityEnforcementErrorV1> =
            enforce_selected_p3c_causality_v1;
        let _ = function;
    }

    #[test]
    fn source_one_based_suffix_window_includes_zero_based_half_minus_one() {
        let mut samples = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0];
        apply_source_zero_windows(&mut samples, 1).unwrap();
        assert_eq!(samples, [0.0, 0.0, 3.0, 0.0, 0.0, 0.0, 0.0, 0.0]);
    }
}
