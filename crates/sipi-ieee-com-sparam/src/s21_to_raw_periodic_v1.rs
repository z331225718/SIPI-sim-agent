// SPDX-License-Identifier: BSD-3-Clause
// Copyright (c) 2025, 802-COM Authors
//
// Direct-port source: IEEE 802-COM `src/s21_to_impulse_DC.m` at
// d4ecd4597a98782887933b5df4c4796da2474195, blob
// f426fb2119dc1cf9c2a2f677e60c3a1f31cb27a3, SHA-256
// b2884926b204fdfddc1c309c35d46ed7744c696e19df3abcd7d91157e9e539c0.
// The selected policy and line map are recorded in SOURCE-MAP.md.

//! Fixed Hermitian construction and inverse transform adapted from the selected
//! BSD source. The result is a raw periodic response, not a causal impulse or
//! FIR admission. Causality enforcement, delay removal, truncation, pulse
//! construction, and convolution are deliberately excluded.

use std::{error::Error, fmt};

use rustfft::{FftPlanner, num_complex::Complex};
use sipi_types::{FiniteF64, Seconds};

use crate::SelectedP3cUniformSpectrumV1;

pub const SELECTED_ENDPOINT_ABSOLUTE_RESIDUAL_LIMIT_V1: f64 = 1.0e-12;
pub const SELECTED_ENDPOINT_RELATIVE_RESIDUAL_LIMIT_V1: f64 = 1.0e-10;
pub const SELECTED_INVERSE_ABSOLUTE_RESIDUAL_LIMIT_V1: f64 = 1.0e-12;
pub const SELECTED_INVERSE_RELATIVE_RESIDUAL_LIMIT_V1: f64 = 1.0e-10;
pub const SELECTED_MAX_RAW_PERIODIC_SAMPLES_V1: usize = 2_097_150;

/// A finite, unshifted, untruncated inverse transform over one DFT period.
#[derive(Clone, Debug, PartialEq)]
pub struct SelectedP3cRawPeriodicResponseV1 {
    sample_interval: Seconds,
    samples: Box<[FiniteF64]>,
    endpoint_imaginary_residue: FiniteF64,
    inverse_imaginary_residue: FiniteF64,
}

impl SelectedP3cRawPeriodicResponseV1 {
    pub fn sample_interval(&self) -> Seconds {
        self.sample_interval
    }

    pub fn samples(&self) -> &[FiniteF64] {
        &self.samples
    }

    pub fn sample_count(&self) -> usize {
        self.samples.len()
    }

    pub fn endpoint_imaginary_residue(&self) -> FiniteF64 {
        self.endpoint_imaginary_residue
    }

    pub fn inverse_imaginary_residue(&self) -> FiniteF64 {
        self.inverse_imaginary_residue
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum RawPeriodicTransformErrorV1 {
    TooFewOneSidedBins,
    OutputLengthOverflow,
    OutputSampleLimitExceeded,
    EndpointImaginaryResidue,
    InverseImaginaryResidue,
    NonFiniteCalculation,
}

impl fmt::Display for RawPeriodicTransformErrorV1 {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            formatter,
            "selected IEEE COM raw periodic inverse transform failed: {self:?}"
        )
    }
}

impl Error for RawPeriodicTransformErrorV1 {}

/// Construct the fixed Hermitian spectrum and calculate its positive-sign,
/// `1/N`-normalized inverse DFT. Endpoints must be real within the frozen
/// residual bound before their imaginary components are projected to zero.
pub fn inverse_selected_p3c_uniform_spectrum_v1(
    input: &SelectedP3cUniformSpectrumV1,
) -> Result<SelectedP3cRawPeriodicResponseV1, RawPeriodicTransformErrorV1> {
    inverse_uniform_values(input.values(), input.frequency_step().get())
}

fn inverse_uniform_values(
    values: &[sipi_types::Complex64],
    frequency_step: f64,
) -> Result<SelectedP3cRawPeriodicResponseV1, RawPeriodicTransformErrorV1> {
    if values.len() < 2 {
        return Err(RawPeriodicTransformErrorV1::TooFewOneSidedBins);
    }
    if !(frequency_step.is_finite() && frequency_step > 0.0) {
        return Err(RawPeriodicTransformErrorV1::NonFiniteCalculation);
    }
    let length = values
        .len()
        .checked_sub(1)
        .and_then(|count| count.checked_mul(2))
        .ok_or(RawPeriodicTransformErrorV1::OutputLengthOverflow)?;
    if length > SELECTED_MAX_RAW_PERIODIC_SAMPLES_V1 {
        return Err(RawPeriodicTransformErrorV1::OutputSampleLimitExceeded);
    }

    let maximum_magnitude = values
        .iter()
        .map(|value| value.real().hypot(value.imaginary()))
        .fold(0.0_f64, f64::max);
    if !maximum_magnitude.is_finite() {
        return Err(RawPeriodicTransformErrorV1::NonFiniteCalculation);
    }
    let endpoint_imaginary_residue = values[0]
        .imaginary()
        .abs()
        .max(values[values.len() - 1].imaginary().abs());
    if !within_residual_bound(
        endpoint_imaginary_residue,
        maximum_magnitude,
        SELECTED_ENDPOINT_ABSOLUTE_RESIDUAL_LIMIT_V1,
        SELECTED_ENDPOINT_RELATIVE_RESIDUAL_LIMIT_V1,
    ) {
        return Err(RawPeriodicTransformErrorV1::EndpointImaginaryResidue);
    }

    let mut spectrum = vec![Complex::new(0.0, 0.0); length];
    spectrum[0] = Complex::new(values[0].real(), 0.0);
    for (index, value) in values.iter().enumerate().skip(1).take(values.len() - 2) {
        spectrum[index] = Complex::new(value.real(), value.imaginary());
        spectrum[length - index] = spectrum[index].conj();
    }
    spectrum[length / 2] = Complex::new(values[values.len() - 1].real(), 0.0);

    FftPlanner::<f64>::new()
        .plan_fft_inverse(length)
        .process(&mut spectrum);
    let scale = 1.0 / length as f64;
    let maximum_real = spectrum
        .iter()
        .map(|value| (value.re * scale).abs())
        .fold(0.0_f64, f64::max);
    let inverse_imaginary_residue = spectrum
        .iter()
        .map(|value| (value.im * scale).abs())
        .fold(0.0_f64, f64::max);
    if !(maximum_real.is_finite() && inverse_imaginary_residue.is_finite()) {
        return Err(RawPeriodicTransformErrorV1::NonFiniteCalculation);
    }
    if !within_residual_bound(
        inverse_imaginary_residue,
        maximum_real,
        SELECTED_INVERSE_ABSOLUTE_RESIDUAL_LIMIT_V1,
        SELECTED_INVERSE_RELATIVE_RESIDUAL_LIMIT_V1,
    ) {
        return Err(RawPeriodicTransformErrorV1::InverseImaginaryResidue);
    }
    let samples = spectrum
        .into_iter()
        .map(|value| {
            FiniteF64::try_new(value.re * scale, "raw periodic response sample")
                .map_err(|_| RawPeriodicTransformErrorV1::NonFiniteCalculation)
        })
        .collect::<Result<Vec<_>, _>>()?;
    let sample_interval = 1.0 / (length as f64 * frequency_step);
    Ok(SelectedP3cRawPeriodicResponseV1 {
        sample_interval: Seconds::try_new(sample_interval)
            .map_err(|_| RawPeriodicTransformErrorV1::NonFiniteCalculation)?,
        samples: samples.into_boxed_slice(),
        endpoint_imaginary_residue: FiniteF64::try_new(
            endpoint_imaginary_residue,
            "endpoint imaginary residue",
        )
        .map_err(|_| RawPeriodicTransformErrorV1::NonFiniteCalculation)?,
        inverse_imaginary_residue: FiniteF64::try_new(
            inverse_imaginary_residue,
            "inverse imaginary residue",
        )
        .map_err(|_| RawPeriodicTransformErrorV1::NonFiniteCalculation)?,
    })
}

fn within_residual_bound(residue: f64, scale: f64, absolute: f64, relative: f64) -> bool {
    residue.is_finite()
        && scale.is_finite()
        && residue <= absolute + relative * scale
}

#[cfg(test)]
mod tests {
    use super::*;
    use sipi_channel::{
        FourPortS, SelectedP3cFourPortSpectrumV1, reduce_selected_p3c_fixed_four_port_bench_v1,
    };
    use sipi_types::Complex64;
    use sipi_types::{Hertz, Ohms};

    fn complex(real: f64, imaginary: f64) -> Complex64 {
        Complex64::try_new(real, imaginary).unwrap()
    }

    #[test]
    fn constant_spectrum_is_delta_at_zero_without_a_shift() {
        let response = inverse_uniform_values(&[complex(1.0, 0.0); 5], 2.0).unwrap();
        assert_eq!(response.sample_count(), 8);
        assert!((response.sample_interval().get() - 1.0 / 16.0).abs() < 1.0e-15);
        assert!((response.samples()[0].get() - 1.0).abs() < 1.0e-12);
        assert!(response.samples()[1..]
            .iter()
            .all(|sample| sample.get().abs() < 1.0e-12));
    }

    #[test]
    fn integer_delay_uses_positive_sign_inverse_without_rotation() {
        let length = 8usize;
        let delayed = (0..=length / 2)
            .map(|index| {
                let phase = -std::f64::consts::TAU * 2.0 * index as f64 / length as f64;
                complex(phase.cos(), phase.sin())
            })
            .collect::<Vec<_>>();
        let response = inverse_uniform_values(&delayed, 1.0).unwrap();
        let peak = response
            .samples()
            .iter()
            .enumerate()
            .max_by(|(_, left), (_, right)| left.get().abs().total_cmp(&right.get().abs()))
            .unwrap();
        assert_eq!(peak.0, 2);
        assert!((peak.1.get() - 1.0).abs() < 1.0e-12);
    }

    #[test]
    fn endpoint_projection_is_bounded_and_inverse_is_real() {
        let response = inverse_uniform_values(
            &[
                complex(1.0, 1.0e-13),
                complex(0.5, 0.25),
                complex(0.25, -5.0e-13),
            ],
            4.0,
        )
        .unwrap();
        assert_eq!(response.sample_count(), 4);
        assert!((response.endpoint_imaginary_residue().get() - 5.0e-13).abs() < 1.0e-24);
        assert!(response.inverse_imaginary_residue().get() <= 1.0e-12);
    }

    #[test]
    fn matches_a_small_direct_positive_sign_inverse_and_parseval() {
        let values = [
            complex(0.75, 0.0),
            complex(0.5, -0.25),
            complex(-0.125, 0.75),
            complex(0.25, 0.0),
        ];
        let response = inverse_uniform_values(&values, 2.0).unwrap();
        let length = response.sample_count();
        for (time_index, sample) in response.samples().iter().enumerate() {
            let direct = values[0].real()
                + values[values.len() - 1].real()
                    * (-1.0_f64).powi(time_index as i32)
                + (1..values.len() - 1)
                    .map(|frequency_index| {
                        let phase = std::f64::consts::TAU
                            * frequency_index as f64
                            * time_index as f64
                            / length as f64;
                        2.0
                            * (values[frequency_index].real() * phase.cos()
                                - values[frequency_index].imaginary() * phase.sin())
                    })
                    .sum::<f64>();
            assert!((sample.get() - direct / length as f64).abs() < 1.0e-12);
        }
        let time_energy = response
            .samples()
            .iter()
            .map(|sample| sample.get().powi(2))
            .sum::<f64>();
        let frequency_energy = values[0].real().powi(2)
            + values[values.len() - 1].real().powi(2)
            + 2.0
                * values[1..values.len() - 1]
                    .iter()
                    .map(|value| value.real().powi(2) + value.imaginary().powi(2))
                    .sum::<f64>();
        assert!((time_energy - frequency_energy / length as f64).abs() < 1.0e-12);
    }

    #[test]
    fn public_api_consumes_only_the_fixed_uniform_spectrum_type() {
        let frequencies = (0..60)
            .map(|index| Hertz::try_new(index as f64 * 1.0e9).unwrap())
            .collect::<Vec<_>>();
        let samples = (0..60)
            .map(|index| {
                let amplitude = 1.0 + index as f64 * 0.01;
                let phase = -std::f64::consts::TAU * index as f64 / 512.0;
                let mut matrix = [[complex(0.0, 0.0); 4]; 4];
                matrix[1][0] = complex(amplitude * phase.cos(), amplitude * phase.sin());
                matrix[3][2] = complex(amplitude * phase.cos(), amplitude * phase.sin());
                FourPortS::new(matrix)
            })
            .collect::<Vec<_>>();
        let four_port = SelectedP3cFourPortSpectrumV1::try_new(
            Ohms::try_new(50.0).unwrap(),
            frequencies,
            samples,
        )
        .unwrap();
        let transfer = reduce_selected_p3c_fixed_four_port_bench_v1(&four_port).unwrap();
        let uniform = crate::interpolate_selected_p3c_hdiff_v1(&transfer).unwrap();
        let response = inverse_selected_p3c_uniform_spectrum_v1(&uniform).unwrap();
        assert_eq!(response.sample_count(), 1024);
        assert!((response.sample_interval().get() - 9.765_625e-13).abs() < 1.0e-24);
    }

    #[test]
    fn nontrivial_endpoint_residue_and_bad_shape_reject() {
        assert_eq!(
            inverse_uniform_values(&[complex(1.0, 1.0e-4), complex(1.0, 0.0)], 1.0)
                .unwrap_err(),
            RawPeriodicTransformErrorV1::EndpointImaginaryResidue
        );
        assert_eq!(
            inverse_uniform_values(&[complex(1.0, 0.0)], 1.0).unwrap_err(),
            RawPeriodicTransformErrorV1::TooFewOneSidedBins
        );
        assert_eq!(
            inverse_uniform_values(&[complex(1.0, 0.0); 2], 0.0).unwrap_err(),
            RawPeriodicTransformErrorV1::NonFiniteCalculation
        );
        let over_limit = vec![complex(0.0, 0.0); SELECTED_MAX_RAW_PERIODIC_SAMPLES_V1 / 2 + 2];
        assert_eq!(
            inverse_uniform_values(&over_limit, 1.0).unwrap_err(),
            RawPeriodicTransformErrorV1::OutputSampleLimitExceeded
        );
        assert!(!within_residual_bound(1.0e-9, 1.0, 1.0e-12, 1.0e-10));
    }
}
