// SPDX-License-Identifier: BSD-3-Clause
// Copyright (c) 2025, 802-COM Authors
//
// Direct-port source: IEEE 802-COM `src/interp_Sparam.m` at
// d4ecd4597a98782887933b5df4c4796da2474195, blob
// 85b52ff25dbb5bb91f032a03d7cdd311e33af432, SHA-256
// 259762276a3711eb6e9186993ae1cf38b9cb60d4819f263dc7770788a7f90e27.
// The selected policy and line map are recorded in SOURCE-MAP.md.

//! Fixed-policy scalar interpolation adapted from the selected BSD source.
//!
//! This module fixes `linear_trend_to_DC_log_trend_to_inf` and
//! `trend_and_shift_to_DC` with no caller-selected branch or debug bypass.
//! Its uniform output is not an IFFT, a causal impulse response, or an ADS
//! equivalence claim.

use std::{error::Error, fmt};

use sipi_channel::SelectedP3cStaticDifferentialTransferV1;
use sipi_types::{Complex64, Hertz};

pub const SELECTED_SAMPLE_INTERVAL_SECONDS_V1: f64 = 9.765_625e-13;
pub const SELECTED_NYQUIST_HERTZ_V1: f64 = 512.0e9;
pub const SELECTED_MAX_OUTPUT_BINS_V1: usize = 1_048_576;
const EPSILON: f64 = f64::EPSILON;
const REALMIN: f64 = f64::MIN_POSITIVE;
const LOW_FREQUENCY_GROUP_DELAY_COUNT: usize = 50;
const TREND_SAMPLE_COUNT: usize = 10;

/// A uniform one-sided spectrum produced by the fixed selected policy.
#[derive(Clone, Debug, PartialEq)]
pub struct SelectedP3cUniformSpectrumV1 {
    frequency_step: Hertz,
    values: Box<[Complex64]>,
}

impl SelectedP3cUniformSpectrumV1 {
    pub fn frequency_step(&self) -> Hertz {
        self.frequency_step
    }

    pub fn values(&self) -> &[Complex64] {
        &self.values
    }

    pub fn sample_count(&self) -> usize {
        self.values.len()
    }

    pub fn frequency_at(&self, index: usize) -> Option<Hertz> {
        (index < self.values.len())
            .then(|| Hertz::try_new(index as f64 * self.frequency_step.get()).ok())
            .flatten()
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum InterpSparamErrorV1 {
    TooFewInputSamples,
    LengthMismatch,
    NonIncreasingFrequency,
    NonPositiveFrequencyStep,
    OutputGridExceedsLimit,
    AntiCausalPhaseSlope,
    EmptyPhaseTrendInliers,
    UndefinedHighFrequencyLogTrend,
    NonFiniteCalculation,
}

impl fmt::Display for InterpSparamErrorV1 {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            formatter,
            "selected IEEE COM interpolation failed: {self:?}"
        )
    }
}

impl Error for InterpSparamErrorV1 {}

/// Interpolate the admitted scalar `Hdiff` with the fixed selected policy.
///
/// The source grid chooses `df = fin[1] - fin[0]`; the output is the exact
/// positive-round MATLAB rule `M = floor(512 GHz / df + 0.5)`, so its bins
/// are `k * 512 GHz / M`, including DC and Nyquist. The method rejects rather
/// than repairs anti-causal phase slope or ill-defined trend branches.
pub fn interpolate_selected_p3c_hdiff_v1(
    input: &SelectedP3cStaticDifferentialTransferV1,
) -> Result<SelectedP3cUniformSpectrumV1, InterpSparamErrorV1> {
    let fin = input.frequencies();
    let sin = input.transfer();
    if fin.len() != sin.len() {
        return Err(InterpSparamErrorV1::LengthMismatch);
    }
    if fin.len() < LOW_FREQUENCY_GROUP_DELAY_COUNT + 1 {
        return Err(InterpSparamErrorV1::TooFewInputSamples);
    }

    let frequencies = fin.iter().map(|value| value.get()).collect::<Vec<_>>();
    if frequencies
        .windows(2)
        .any(|pair| pair[1].partial_cmp(&pair[0]) != Some(std::cmp::Ordering::Greater))
    {
        return Err(InterpSparamErrorV1::NonIncreasingFrequency);
    }
    let source_df = frequencies[1] - frequencies[0];
    if !(source_df.is_finite() && source_df > 0.0) {
        return Err(InterpSparamErrorV1::NonPositiveFrequencyStep);
    }
    let bins = (SELECTED_NYQUIST_HERTZ_V1 / source_df + 0.5).floor();
    if !(bins.is_finite() && bins >= 1.0 && bins <= (SELECTED_MAX_OUTPUT_BINS_V1 - 1) as f64) {
        return Err(InterpSparamErrorV1::OutputGridExceedsLimit);
    }
    let bins = bins as usize;
    let output_step = SELECTED_NYQUIST_HERTZ_V1 / bins as f64;
    if !(output_step.is_finite() && output_step > 0.0) {
        return Err(InterpSparamErrorV1::NonFiniteCalculation);
    }
    let fout = (0..=bins)
        .map(|index| index as f64 * output_step)
        .collect::<Vec<_>>();

    let magnitude = sin.iter().map(magnitude).collect::<Result<Vec<_>, _>>()?;
    let phase = unwrap_phase(sin)?;
    let phase_difference_mean = mean(&differences(&phase)?)?;
    if phase_difference_mean > 0.0 {
        return Err(InterpSparamErrorV1::AntiCausalPhaseSlope);
    }

    let interpolated_magnitude = interpolate_magnitude(&frequencies, &magnitude, &fout)?;
    let interpolated_phase = interpolate_phase(&frequencies, &phase, &fout)?;
    let values = interpolated_magnitude
        .into_iter()
        .zip(interpolated_phase)
        .map(|(magnitude, phase)| {
            let real = magnitude * phase.cos();
            let imaginary = magnitude * phase.sin();
            Complex64::try_new(real, imaginary)
                .map_err(|_| InterpSparamErrorV1::NonFiniteCalculation)
        })
        .collect::<Result<Vec<_>, _>>()?;

    Ok(SelectedP3cUniformSpectrumV1 {
        frequency_step: Hertz::try_new(output_step)
            .map_err(|_| InterpSparamErrorV1::NonFiniteCalculation)?,
        values: values.into_boxed_slice(),
    })
}

fn magnitude(value: &Complex64) -> Result<f64, InterpSparamErrorV1> {
    let result = value.real().hypot(value.imaginary()).max(EPSILON);
    result
        .is_finite()
        .then_some(result)
        .ok_or(InterpSparamErrorV1::NonFiniteCalculation)
}

fn unwrap_phase(values: &[Complex64]) -> Result<Vec<f64>, InterpSparamErrorV1> {
    let mut result = Vec::with_capacity(values.len());
    let mut previous = None;
    for value in values {
        let mut phase = value.imaginary().atan2(value.real());
        if !phase.is_finite() {
            return Err(InterpSparamErrorV1::NonFiniteCalculation);
        }
        if let Some(last) = previous {
            let mut delta = phase - last;
            while delta > std::f64::consts::PI {
                phase -= std::f64::consts::TAU;
                delta -= std::f64::consts::TAU;
            }
            while delta <= -std::f64::consts::PI {
                phase += std::f64::consts::TAU;
                delta += std::f64::consts::TAU;
            }
        }
        previous = Some(phase);
        result.push(phase);
    }
    Ok(result)
}

fn differences(values: &[f64]) -> Result<Vec<f64>, InterpSparamErrorV1> {
    values
        .windows(2)
        .map(|pair| {
            let difference = pair[1] - pair[0];
            difference
                .is_finite()
                .then_some(difference)
                .ok_or(InterpSparamErrorV1::NonFiniteCalculation)
        })
        .collect()
}

fn mean(values: &[f64]) -> Result<f64, InterpSparamErrorV1> {
    if values.is_empty() {
        return Err(InterpSparamErrorV1::NonFiniteCalculation);
    }
    let value = values.iter().sum::<f64>() / values.len() as f64;
    value
        .is_finite()
        .then_some(value)
        .ok_or(InterpSparamErrorV1::NonFiniteCalculation)
}

fn linear_regression(x: &[f64], y: &[f64]) -> Result<(f64, f64), InterpSparamErrorV1> {
    if x.len() != y.len() || x.len() < 2 {
        return Err(InterpSparamErrorV1::NonFiniteCalculation);
    }
    let x_mean = mean(x)?;
    let y_mean = mean(y)?;
    let (numerator, denominator) = x.iter().zip(y).try_fold((0.0, 0.0), |(n, d), (&x, &y)| {
        let dx = x - x_mean;
        let dy = y - y_mean;
        let n = n + dx * dy;
        let d = d + dx * dx;
        (n.is_finite() && d.is_finite())
            .then_some((n, d))
            .ok_or(InterpSparamErrorV1::NonFiniteCalculation)
    })?;
    if !(denominator.is_finite() && denominator > 0.0) {
        return Err(InterpSparamErrorV1::NonFiniteCalculation);
    }
    let slope = numerator / denominator;
    let intercept = y_mean - slope * x_mean;
    (slope.is_finite() && intercept.is_finite())
        .then_some((slope, intercept))
        .ok_or(InterpSparamErrorV1::NonFiniteCalculation)
}

fn interpolate_magnitude(
    fin: &[f64],
    magnitude: &[f64],
    fout: &[f64],
) -> Result<Vec<f64>, InterpSparamErrorV1> {
    let mut x = fin.to_vec();
    let mut y = magnitude.to_vec();
    if fin[0] > 0.0 {
        let (slope, intercept) =
            linear_regression(&fin[..TREND_SAMPLE_COUNT], &magnitude[..TREND_SAMPLE_COUNT])?;
        let dc = intercept;
        if !(dc.is_finite() && dc > 0.0 && slope.is_finite()) {
            return Err(InterpSparamErrorV1::NonFiniteCalculation);
        }
        x.insert(0, 0.0);
        y.insert(0, dc);
    }
    let mut high_log = None;
    if fin[fin.len() - 1] < fout[fout.len() - 1] {
        let midpoint = fin.len().div_ceil(2) - 1;
        let (slope, intercept) = linear_regression(&fin[midpoint..], &magnitude[midpoint..])?;
        let mut high = slope * fout[fout.len() - 1] + intercept;
        if high > magnitude[magnitude.len() - 1] {
            high = magnitude[magnitude.len() - 1];
            high_log = Some(high);
        } else if high < EPSILON {
            high = EPSILON;
            high_log = Some(REALMIN);
        }
        x.push(fout[fout.len() - 1]);
        y.push(high);
    }
    let linear = linear_interpolate(&x, &y, fout)?;
    if let Some(high_log) = high_log {
        let mut log_y = y[..y.len() - 1]
            .iter()
            .map(|value| value.ln())
            .collect::<Vec<_>>();
        log_y.push(high_log.ln());
        let log_linear = linear_interpolate(&x, &log_y, fout)?;
        Ok(linear
            .into_iter()
            .enumerate()
            .map(|(index, value)| {
                if fout[index] > fin[fin.len() - 1] {
                    log_linear[index].exp()
                } else {
                    value
                }
            })
            .collect())
    } else if fin[fin.len() - 1] < fout[fout.len() - 1] {
        Err(InterpSparamErrorV1::UndefinedHighFrequencyLogTrend)
    } else {
        Ok(linear)
    }
}

fn interpolate_phase(
    fin: &[f64],
    phase: &[f64],
    fout: &[f64],
) -> Result<Vec<f64>, InterpSparamErrorV1> {
    let group_delay = phase_group_delay(fin, phase)?;
    let low = &group_delay[..LOW_FREQUENCY_GROUP_DELAY_COUNT];
    let trend = mean_strict_inliers(low)?;
    let mut x = fin.to_vec();
    let mut y = phase.to_vec();
    if fin[0] != 0.0 {
        for index in (0..TREND_SAMPLE_COUNT).rev() {
            y[index] = y[index + 1] + trend * (fin[index + 1] - fin[index]);
        }
        let dc_phase_trend = y[0] + trend * fin[0];
        x.insert(0, 0.0);
        y = y.into_iter().map(|value| value - dc_phase_trend).collect();
        y.insert(0, 0.0);
    }
    if fout[fout.len() - 1] > fin[fin.len() - 1] {
        let high_group_delay = phase_group_delay(&x, &y)?;
        let high_phase =
            y[y.len() - 1] - median(&high_group_delay)? * (fout[fout.len() - 1] - x[x.len() - 1]);
        if !high_phase.is_finite() {
            return Err(InterpSparamErrorV1::NonFiniteCalculation);
        }
        x.push(fout[fout.len() - 1]);
        y.push(high_phase);
    }
    linear_interpolate(&x, &y, fout)
}

fn phase_group_delay(frequencies: &[f64], phase: &[f64]) -> Result<Vec<f64>, InterpSparamErrorV1> {
    frequencies
        .windows(2)
        .zip(phase.windows(2))
        .map(|(f, p)| {
            let value = -(p[1] - p[0]) / (f[1] - f[0]);
            value
                .is_finite()
                .then_some(value)
                .ok_or(InterpSparamErrorV1::NonFiniteCalculation)
        })
        .collect()
}

fn median(values: &[f64]) -> Result<f64, InterpSparamErrorV1> {
    if values.is_empty() {
        return Err(InterpSparamErrorV1::NonFiniteCalculation);
    }
    let mut sorted = values.to_vec();
    sorted.sort_by(f64::total_cmp);
    let midpoint = sorted.len() / 2;
    let value = if sorted.len().is_multiple_of(2) {
        (sorted[midpoint - 1] + sorted[midpoint]) / 2.0
    } else {
        sorted[midpoint]
    };
    value
        .is_finite()
        .then_some(value)
        .ok_or(InterpSparamErrorV1::NonFiniteCalculation)
}

fn mean_strict_inliers(values: &[f64]) -> Result<f64, InterpSparamErrorV1> {
    let median = median(values)?;
    let average = mean(values)?;
    let variance = values
        .iter()
        .map(|value| (value - average).powi(2))
        .sum::<f64>()
        / (values.len() - 1) as f64;
    let standard_deviation = variance.sqrt();
    if !standard_deviation.is_finite() {
        return Err(InterpSparamErrorV1::NonFiniteCalculation);
    }
    let inliers = values
        .iter()
        .copied()
        .filter(|value| (value - median).abs() < standard_deviation)
        .collect::<Vec<_>>();
    if inliers.is_empty() {
        return Err(InterpSparamErrorV1::EmptyPhaseTrendInliers);
    }
    mean(&inliers)
}

fn linear_interpolate(
    x: &[f64],
    y: &[f64],
    targets: &[f64],
) -> Result<Vec<f64>, InterpSparamErrorV1> {
    if x.len() != y.len()
        || x.len() < 2
        || x.windows(2)
            .any(|pair| pair[1].partial_cmp(&pair[0]) != Some(std::cmp::Ordering::Greater))
    {
        return Err(InterpSparamErrorV1::NonIncreasingFrequency);
    }
    let mut upper = 1usize;
    targets
        .iter()
        .map(|&target| {
            while upper < x.len() - 1 && target > x[upper] {
                upper += 1;
            }
            let lower = upper - 1;
            let fraction = (target - x[lower]) / (x[upper] - x[lower]);
            let value = y[lower] + fraction * (y[upper] - y[lower]);
            value
                .is_finite()
                .then_some(value)
                .ok_or(InterpSparamErrorV1::NonFiniteCalculation)
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use sipi_channel::{
        FourPortS, SelectedP3cFourPortSpectrumV1, reduce_selected_p3c_fixed_four_port_bench_v1,
    };
    use sipi_types::Ohms;

    fn complex(real: f64, imaginary: f64) -> Complex64 {
        Complex64::try_new(real, imaginary).unwrap()
    }

    fn transfer(
        phase_step: f64,
        amplitude: impl Fn(usize) -> f64,
    ) -> SelectedP3cStaticDifferentialTransferV1 {
        let frequencies = (0..60)
            .map(|index| Hertz::try_new(index as f64 * 1.0e9).unwrap())
            .collect::<Vec<_>>();
        let samples = (0..60)
            .map(|index| {
                let phase = index as f64 * phase_step;
                let value = complex(
                    amplitude(index) * phase.cos(),
                    amplitude(index) * phase.sin(),
                );
                let mut entries = [[complex(0.0, 0.0); 4]; 4];
                entries[1][0] = value;
                entries[3][2] = value;
                FourPortS::new(entries)
            })
            .collect::<Vec<_>>();
        let spectrum = SelectedP3cFourPortSpectrumV1::try_new(
            Ohms::try_new(50.0).unwrap(),
            frequencies,
            samples,
        )
        .unwrap();
        reduce_selected_p3c_fixed_four_port_bench_v1(&spectrum).unwrap()
    }

    #[test]
    fn fixed_grid_reconstructs_knots_and_dc() {
        let result =
            interpolate_selected_p3c_hdiff_v1(&transfer(-0.05, |index| 1.0 + index as f64 * 0.01))
                .unwrap();
        assert_eq!(result.sample_count(), 513);
        assert_eq!(result.frequency_at(0).unwrap().get(), 0.0);
        assert_eq!(
            result.frequency_at(512).unwrap().get(),
            SELECTED_NYQUIST_HERTZ_V1
        );
        let first = result.values()[0];
        assert!((first.real() - 0.5).abs() < 1e-10);
        let knot = result.values()[20];
        assert!((knot.real() - 0.6 * (-1.0_f64).cos()).abs() < 1e-12);
    }

    #[test]
    fn anti_causal_phase_and_undefined_log_branch_reject() {
        assert_eq!(
            interpolate_selected_p3c_hdiff_v1(&transfer(0.05, |_| 1.0)).unwrap_err(),
            InterpSparamErrorV1::AntiCausalPhaseSlope
        );
        let fin = (0..60).map(|index| index as f64).collect::<Vec<_>>();
        let magnitude = (0..60)
            .map(|index| 1.0 - index as f64 * 0.001)
            .collect::<Vec<_>>();
        assert_eq!(
            interpolate_magnitude(&fin, &magnitude, &[0.0, 60.0]).unwrap_err(),
            InterpSparamErrorV1::UndefinedHighFrequencyLogTrend
        );
    }

    #[test]
    fn capacity_and_phase_wrap_are_fail_closed_or_deterministic() {
        let frequencies = (0..60)
            .map(|index| Hertz::try_new(index as f64).unwrap())
            .collect::<Vec<_>>();
        let zero = complex(0.0, 0.0);
        let samples = (0..60)
            .map(|_| FourPortS::new([[zero; 4]; 4]))
            .collect::<Vec<_>>();
        let spectrum = SelectedP3cFourPortSpectrumV1::try_new(
            Ohms::try_new(50.0).unwrap(),
            frequencies,
            samples,
        )
        .unwrap();
        let input = reduce_selected_p3c_fixed_four_port_bench_v1(&spectrum).unwrap();
        assert_eq!(
            interpolate_selected_p3c_hdiff_v1(&input).unwrap_err(),
            InterpSparamErrorV1::OutputGridExceedsLimit
        );
        let wrapped = unwrap_phase(&[complex(-1.0, 0.1), complex(-1.0, -0.1)]).unwrap();
        assert!(wrapped[1] > wrapped[0]);
    }
}
