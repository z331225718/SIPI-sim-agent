//! Real-constrained fixed-pole identification for the selected P3C transfer.
//!
//! This module creates only canonical positive-imaginary pole/residue pairs.
//! It does not read S4P data or execute a waveform recurrence.

use std::{error::Error, fmt};

use faer::{Mat, c64, linalg::solvers::SolveLstsq};
use sipi_types::Complex64;

use crate::SelectedP3cStaticDifferentialTransferV1;

const MAX_FREQUENCY_HZ: f64 = 40_000_000_000.0;
const OMEGA_SCALE: f64 = 2.0 * std::f64::consts::PI * MAX_FREQUENCY_HZ;
const ORDERS: [usize; 3] = [8, 12, 16];
const DAMPING_RATIO: f64 = 0.05;
const LOWEST_POLE_HZ: f64 = 10_000_000.0;
const RELATIVE_RANK_TOLERANCE: f64 = 1.0e-12;
const ZERO_MAGNITUDE_FLOOR: f64 = 1.0e-15;
const RELATIVE_RMS_LIMIT: f64 = 0.005;
const MAX_NORMALIZED_ABSOLUTE_LIMIT: f64 = 0.03;
const DC_RELATIVE_LIMIT: f64 = 0.005;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum RealConstrainedFixedPoleFitErrorV1 {
    TooFewSamples,
    NonFiniteInput,
    InvalidFrequencyRange,
    RankDeficient,
    SolverFailure,
    NonFiniteModel,
    ZeroSignalNorm,
    ZeroDcReference,
    NoOrderMeetsAdmission,
}

impl fmt::Display for RealConstrainedFixedPoleFitErrorV1 {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "selected P3C real-constrained fixed-pole fit is invalid: {self:?}")
    }
}

impl Error for RealConstrainedFixedPoleFitErrorV1 {}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct RealConstrainedFixedPoleFitMetricsV1 {
    relative_rms_error: f64,
    maximum_normalized_absolute_error: f64,
    dc_relative_error: f64,
}

impl RealConstrainedFixedPoleFitMetricsV1 {
    pub fn relative_rms_error(self) -> f64 { self.relative_rms_error }
    pub fn maximum_normalized_absolute_error(self) -> f64 { self.maximum_normalized_absolute_error }
    pub fn dc_relative_error(self) -> f64 { self.dc_relative_error }
}

/// Canonical real-model identity: each entry has positive imaginary pole and
/// residue. The corresponding negative-imaginary member is exact conjugation.
#[derive(Clone, Debug, PartialEq)]
pub struct SelectedP3cRealConstrainedFixedPoleFitV1 {
    order: usize,
    positive_imaginary_poles_per_second: Box<[Complex64]>,
    positive_imaginary_residues_per_second: Box<[Complex64]>,
    metrics: RealConstrainedFixedPoleFitMetricsV1,
}

impl SelectedP3cRealConstrainedFixedPoleFitV1 {
    pub fn order(&self) -> usize { self.order }
    pub fn positive_imaginary_poles_per_second(&self) -> &[Complex64] { &self.positive_imaginary_poles_per_second }
    pub fn positive_imaginary_residues_per_second(&self) -> &[Complex64] { &self.positive_imaginary_residues_per_second }
    pub fn metrics(&self) -> RealConstrainedFixedPoleFitMetricsV1 { self.metrics }
}

fn positive_imaginary_poles_normalized(order: usize) -> Vec<c64> {
    debug_assert!(ORDERS.contains(&order));
    let pairs = order / 2;
    let low = LOWEST_POLE_HZ / MAX_FREQUENCY_HZ;
    (0..pairs)
        .map(|index| {
            let ratio = if pairs == 1 { 1.0 } else { index as f64 / (pairs - 1) as f64 };
            let imaginary = low * (1.0 / low).powf(ratio);
            c64::new(-DAMPING_RATIO * imaginary, imaginary)
        })
        .collect()
}

fn magnitude(value: c64) -> f64 { value.re.hypot(value.im) }
fn finite(value: c64) -> bool { value.re.is_finite() && value.im.is_finite() }

fn pair_basis(axis: c64, pole: c64) -> Result<(c64, c64), RealConstrainedFixedPoleFitErrorV1> {
    let positive = axis - pole;
    let negative = axis - pole.conj();
    if (positive.re == 0.0 && positive.im == 0.0) || (negative.re == 0.0 && negative.im == 0.0) {
        return Err(RealConstrainedFixedPoleFitErrorV1::NonFiniteModel);
    }
    let real_residue = c64::new(1.0, 0.0) / positive + c64::new(1.0, 0.0) / negative;
    let imaginary_residue = c64::new(0.0, 1.0) * (c64::new(1.0, 0.0) / positive - c64::new(1.0, 0.0) / negative);
    (finite(real_residue) && finite(imaginary_residue))
        .then_some((real_residue, imaginary_residue))
        .ok_or(RealConstrainedFixedPoleFitErrorV1::NonFiniteModel)
}

fn model_value(axis: c64, poles: &[c64], residues: &[c64]) -> Result<c64, RealConstrainedFixedPoleFitErrorV1> {
    let value = poles.iter().zip(residues).try_fold(c64::new(0.0, 0.0), |sum, (pole, residue)| {
        let positive = axis - *pole;
        let negative = axis - pole.conj();
        if (positive.re == 0.0 && positive.im == 0.0) || (negative.re == 0.0 && negative.im == 0.0) {
            return Err(RealConstrainedFixedPoleFitErrorV1::NonFiniteModel);
        }
        let next = sum + *residue / positive + residue.conj() / negative;
        finite(next).then_some(next).ok_or(RealConstrainedFixedPoleFitErrorV1::NonFiniteModel)
    })?;
    finite(value).then_some(value).ok_or(RealConstrainedFixedPoleFitErrorV1::NonFiniteModel)
}

fn metrics(reference: &[c64], candidate: &[c64]) -> Result<RealConstrainedFixedPoleFitMetricsV1, RealConstrainedFixedPoleFitErrorV1> {
    let peak = reference.iter().copied().map(magnitude).fold(0.0_f64, f64::max);
    if !peak.is_finite() || peak == 0.0 { return Err(RealConstrainedFixedPoleFitErrorV1::ZeroSignalNorm); }
    let dc = magnitude(reference[0]);
    if dc <= ZERO_MAGNITUDE_FLOOR { return Err(RealConstrainedFixedPoleFitErrorV1::ZeroDcReference); }
    let (signal, error, maximum) = reference.iter().zip(candidate).try_fold((0.0_f64, 0.0_f64, 0.0_f64), |(signal, error, maximum), (expected, actual)| {
        let residual = *actual - *expected;
        let next = (signal + expected.norm_sqr(), error + residual.norm_sqr(), maximum.max(magnitude(residual)));
        (next.0.is_finite() && next.1.is_finite() && next.2.is_finite())
            .then_some(next).ok_or(RealConstrainedFixedPoleFitErrorV1::NonFiniteModel)
    })?;
    if signal == 0.0 { return Err(RealConstrainedFixedPoleFitErrorV1::ZeroSignalNorm); }
    let output = RealConstrainedFixedPoleFitMetricsV1 {
        relative_rms_error: (error / signal).sqrt(),
        maximum_normalized_absolute_error: maximum / peak,
        dc_relative_error: magnitude(candidate[0] - reference[0]) / dc,
    };
    (output.relative_rms_error.is_finite() && output.maximum_normalized_absolute_error.is_finite() && output.dc_relative_error.is_finite())
        .then_some(output).ok_or(RealConstrainedFixedPoleFitErrorV1::NonFiniteModel)
}

fn within_admission(metrics: RealConstrainedFixedPoleFitMetricsV1) -> bool {
    metrics.relative_rms_error <= RELATIVE_RMS_LIMIT
        && metrics.maximum_normalized_absolute_error <= MAX_NORMALIZED_ABSOLUTE_LIMIT
        && metrics.dc_relative_error <= DC_RELATIVE_LIMIT
}

fn fit_order(input: &SelectedP3cStaticDifferentialTransferV1, order: usize) -> Result<SelectedP3cRealConstrainedFixedPoleFitV1, RealConstrainedFixedPoleFitErrorV1> {
    let axis = input.frequencies().iter().map(|frequency| c64::new(0.0, frequency.get() / MAX_FREQUENCY_HZ)).collect::<Vec<_>>();
    let reference = input.transfer().iter().map(|value| c64::new(value.real(), value.imaginary())).collect::<Vec<_>>();
    if axis.iter().copied().any(|value| !finite(value)) || reference.iter().copied().any(|value| !finite(value)) {
        return Err(RealConstrainedFixedPoleFitErrorV1::NonFiniteInput);
    }
    let poles = positive_imaginary_poles_normalized(order);
    let rows = axis.len() * 2;
    let columns = poles.len() * 2;
    let mut system = Mat::<f64>::from_fn(rows, columns, |row, column| {
        let sample = row % axis.len();
        let (for_real_residue, for_imaginary_residue) = pair_basis(axis[sample], poles[column / 2]).expect("finite admitted basis");
        let basis = if column % 2 == 0 { for_real_residue } else { for_imaginary_residue };
        if row < axis.len() { basis.re } else { basis.im }
    });
    let mut response = Mat::<f64>::from_fn(rows, 1, |row, _| if row < axis.len() { reference[row].re } else { reference[row - axis.len()].im });
    for sample in 0..axis.len() {
        let weight = 1.0 / magnitude(reference[sample]).max(ZERO_MAGNITUDE_FLOOR);
        if !weight.is_finite() { return Err(RealConstrainedFixedPoleFitErrorV1::NonFiniteInput); }
        let factor = weight.sqrt();
        for column in 0..columns {
            system[(sample, column)] *= factor;
            system[(sample + axis.len(), column)] *= factor;
        }
        response[(sample, 0)] *= factor;
        response[(sample + axis.len(), 0)] *= factor;
    }
    let singular_values = system.as_ref().thin_svd().map_err(|_| RealConstrainedFixedPoleFitErrorV1::SolverFailure)?;
    let largest = singular_values.S()[0];
    let smallest = singular_values.S()[columns - 1];
    if !largest.is_finite() || !smallest.is_finite() || smallest <= largest * RELATIVE_RANK_TOLERANCE {
        return Err(RealConstrainedFixedPoleFitErrorV1::RankDeficient);
    }
    let coefficients = system.as_ref().col_piv_qr().solve_lstsq(response.as_ref());
    let residues = (0..poles.len()).map(|pair| c64::new(coefficients[(2 * pair, 0)], coefficients[(2 * pair + 1, 0)])).collect::<Vec<_>>();
    if residues.iter().copied().any(|value| !finite(value)) { return Err(RealConstrainedFixedPoleFitErrorV1::NonFiniteModel); }
    let fitted = axis.iter().copied().map(|sample| model_value(sample, &poles, &residues)).collect::<Result<Vec<_>, _>>()?;
    let metrics = metrics(&reference, &fitted)?;
    let convert = |value: c64| Complex64::try_new(value.re * OMEGA_SCALE, value.im * OMEGA_SCALE).map_err(|_| RealConstrainedFixedPoleFitErrorV1::NonFiniteModel);
    Ok(SelectedP3cRealConstrainedFixedPoleFitV1 {
        order,
        positive_imaginary_poles_per_second: poles.into_iter().map(convert).collect::<Result<_, _>>()?,
        positive_imaginary_residues_per_second: residues.into_iter().map(convert).collect::<Result<_, _>>()?,
        metrics,
    })
}

/// Fit the selected transfer using a real-constrained, canonical pair basis.
/// No pair is post-fit repaired, and no waveform or external asset is used.
pub fn fit_selected_p3c_real_constrained_fixed_pole_v1(input: &SelectedP3cStaticDifferentialTransferV1) -> Result<SelectedP3cRealConstrainedFixedPoleFitV1, RealConstrainedFixedPoleFitErrorV1> {
    if input.frequencies().len() < 2 * ORDERS.last().copied().unwrap_or_default() {
        return Err(RealConstrainedFixedPoleFitErrorV1::TooFewSamples);
    }
    if input.frequencies().first().is_none_or(|frequency| frequency.get() != 0.0)
        || input.frequencies().last().is_none_or(|frequency| frequency.get().to_bits() != MAX_FREQUENCY_HZ.to_bits()) {
        return Err(RealConstrainedFixedPoleFitErrorV1::InvalidFrequencyRange);
    }
    for order in ORDERS {
        let candidate = fit_order(input, order)?;
        if within_admission(candidate.metrics) { return Ok(candidate); }
    }
    Err(RealConstrainedFixedPoleFitErrorV1::NoOrderMeetsAdmission)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{FourPortS, SelectedP3cFourPortSpectrumV1, reduce_selected_p3c_fixed_four_port_bench_v1};
    use sipi_types::{Hertz, Ohms};

    fn c(real: f64, imaginary: f64) -> Complex64 { Complex64::try_new(real, imaginary).unwrap() }

    fn transfer_from_real_pairs(order: usize, start_hz: f64, end_hz: f64) -> SelectedP3cStaticDifferentialTransferV1 {
        let poles = positive_imaginary_poles_normalized(order);
        let residues = poles.iter().enumerate().map(|(index, _)| c64::new(0.05 + index as f64 * 0.01, 0.02 + index as f64 * 0.005)).collect::<Vec<_>>();
        let frequencies = (0..=96).map(|index| Hertz::try_new(start_hz + (end_hz - start_hz) * index as f64 / 96.0).unwrap()).collect::<Vec<_>>();
        let samples = frequencies.iter().map(|frequency| {
            let value = model_value(c64::new(0.0, frequency.get() / MAX_FREQUENCY_HZ), &poles, &residues).unwrap();
            let mut matrix = [[c(0.0, 0.0); 4]; 4];
            matrix[1][0] = c(value.re * 2.0, value.im * 2.0);
            matrix[3][2] = c(value.re * 2.0, value.im * 2.0);
            FourPortS::new(matrix)
        }).collect();
        let spectrum = SelectedP3cFourPortSpectrumV1::try_new(Ohms::try_new(50.0).unwrap(), frequencies, samples).unwrap();
        reduce_selected_p3c_fixed_four_port_bench_v1(&spectrum).unwrap()
    }

    #[test]
    fn real_constrained_basis_recovers_a_canonical_real_model() {
        let result = fit_selected_p3c_real_constrained_fixed_pole_v1(&transfer_from_real_pairs(8, 0.0, MAX_FREQUENCY_HZ)).unwrap();
        assert_eq!(result.order(), 8);
        assert_eq!(result.positive_imaginary_poles_per_second().len(), 4);
        assert!(result.positive_imaginary_poles_per_second().iter().all(|pole| pole.real() < 0.0 && pole.imaginary() > 0.0));
        assert!(result.metrics().relative_rms_error() < 1.0e-10);
    }

    #[test]
    fn rejects_a_missing_dc_before_constructing_pair_coefficients() {
        let transfer = transfer_from_real_pairs(8, 1.0, MAX_FREQUENCY_HZ);
        assert_eq!(fit_selected_p3c_real_constrained_fixed_pole_v1(&transfer).unwrap_err(), RealConstrainedFixedPoleFitErrorV1::InvalidFrequencyRange);
    }
}
