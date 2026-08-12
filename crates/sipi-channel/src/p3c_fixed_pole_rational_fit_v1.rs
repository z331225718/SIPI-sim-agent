//! Fixed-pole rational identification for the selected P3C scalar transfer.
//!
//! This is a fit-only core. It neither relocates poles nor creates a waveform.

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
pub enum FixedPoleRationalFitErrorV1 {
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

impl fmt::Display for FixedPoleRationalFitErrorV1 {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "selected P3C fixed-pole rational fit is invalid: {self:?}")
    }
}

impl Error for FixedPoleRationalFitErrorV1 {}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct FixedPoleRationalFitMetricsV1 {
    relative_rms_error: f64,
    maximum_normalized_absolute_error: f64,
    dc_relative_error: f64,
}

impl FixedPoleRationalFitMetricsV1 {
    pub fn relative_rms_error(self) -> f64 {
        self.relative_rms_error
    }

    pub fn maximum_normalized_absolute_error(self) -> f64 {
        self.maximum_normalized_absolute_error
    }

    pub fn dc_relative_error(self) -> f64 {
        self.dc_relative_error
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct SelectedP3cFixedPoleRationalFitV1 {
    order: usize,
    poles_per_second: Box<[Complex64]>,
    residues_per_second: Box<[Complex64]>,
    metrics: FixedPoleRationalFitMetricsV1,
}

impl SelectedP3cFixedPoleRationalFitV1 {
    pub fn order(&self) -> usize {
        self.order
    }

    pub fn poles_per_second(&self) -> &[Complex64] {
        &self.poles_per_second
    }

    pub fn residues_per_second(&self) -> &[Complex64] {
        &self.residues_per_second
    }

    pub fn metrics(&self) -> FixedPoleRationalFitMetricsV1 {
        self.metrics
    }
}

fn initial_poles_normalized(order: usize) -> Vec<c64> {
    debug_assert!(ORDERS.contains(&order));
    let pairs = order / 2;
    let low = LOWEST_POLE_HZ / MAX_FREQUENCY_HZ;
    (0..pairs)
        .flat_map(|index| {
            let ratio = if pairs == 1 {
                1.0
            } else {
                index as f64 / (pairs - 1) as f64
            };
            let imaginary = low * (1.0 / low).powf(ratio);
            let real = -DAMPING_RATIO * imaginary;
            [c64::new(real, imaginary), c64::new(real, -imaginary)]
        })
        .collect()
}

fn magnitude(value: c64) -> f64 {
    value.re.hypot(value.im)
}

fn finite(value: c64) -> bool {
    value.re.is_finite() && value.im.is_finite()
}

fn model_value(axis: c64, poles: &[c64], residues: &[c64]) -> Result<c64, FixedPoleRationalFitErrorV1> {
    let value = poles
        .iter()
        .zip(residues)
        .try_fold(c64::new(0.0, 0.0), |sum, (pole, residue)| {
            let denominator = axis - *pole;
            if denominator.re == 0.0 && denominator.im == 0.0 {
                return Err(FixedPoleRationalFitErrorV1::NonFiniteModel);
            }
            let next = sum + *residue / denominator;
            finite(next).then_some(next).ok_or(FixedPoleRationalFitErrorV1::NonFiniteModel)
        })?;
    finite(value).then_some(value).ok_or(FixedPoleRationalFitErrorV1::NonFiniteModel)
}

fn metrics(reference: &[c64], candidate: &[c64]) -> Result<FixedPoleRationalFitMetricsV1, FixedPoleRationalFitErrorV1> {
    let signal_peak = reference.iter().copied().map(magnitude).fold(0.0_f64, f64::max);
    if !signal_peak.is_finite() || signal_peak == 0.0 {
        return Err(FixedPoleRationalFitErrorV1::ZeroSignalNorm);
    }
    let dc_magnitude = magnitude(reference[0]);
    if dc_magnitude <= ZERO_MAGNITUDE_FLOOR {
        return Err(FixedPoleRationalFitErrorV1::ZeroDcReference);
    }
    let (signal_energy, error_energy, max_error) = reference.iter().zip(candidate).try_fold(
        (0.0_f64, 0.0_f64, 0.0_f64),
        |(signal, error, maximum), (expected, actual)| {
            let residual = *actual - *expected;
            let next = (
                signal + expected.norm_sqr(),
                error + residual.norm_sqr(),
                maximum.max(magnitude(residual)),
            );
            (next.0.is_finite() && next.1.is_finite() && next.2.is_finite())
                .then_some(next)
                .ok_or(FixedPoleRationalFitErrorV1::NonFiniteModel)
        },
    )?;
    if signal_energy == 0.0 {
        return Err(FixedPoleRationalFitErrorV1::ZeroSignalNorm);
    }
    let output = FixedPoleRationalFitMetricsV1 {
        relative_rms_error: (error_energy / signal_energy).sqrt(),
        maximum_normalized_absolute_error: max_error / signal_peak,
        dc_relative_error: magnitude(candidate[0] - reference[0]) / dc_magnitude,
    };
    (output.relative_rms_error.is_finite()
        && output.maximum_normalized_absolute_error.is_finite()
        && output.dc_relative_error.is_finite())
        .then_some(output)
        .ok_or(FixedPoleRationalFitErrorV1::NonFiniteModel)
}

fn within_admission(metrics: FixedPoleRationalFitMetricsV1) -> bool {
    metrics.relative_rms_error <= RELATIVE_RMS_LIMIT
        && metrics.maximum_normalized_absolute_error <= MAX_NORMALIZED_ABSOLUTE_LIMIT
        && metrics.dc_relative_error <= DC_RELATIVE_LIMIT
}

fn fit_order(
    input: &SelectedP3cStaticDifferentialTransferV1,
    order: usize,
) -> Result<SelectedP3cFixedPoleRationalFitV1, FixedPoleRationalFitErrorV1> {
    let frequencies = input.frequencies();
    let transfer = input.transfer();
    let poles = initial_poles_normalized(order);
    let axis = frequencies
        .iter()
        .map(|frequency| c64::new(0.0, frequency.get() / MAX_FREQUENCY_HZ))
        .collect::<Vec<_>>();
    let reference = transfer
        .iter()
        .map(|value| c64::new(value.real(), value.imaginary()))
        .collect::<Vec<_>>();
    if axis.iter().copied().any(|value| !finite(value)) || reference.iter().copied().any(|value| !finite(value)) {
        return Err(FixedPoleRationalFitErrorV1::NonFiniteInput);
    }
    let mut system = Mat::from_fn(axis.len(), order, |row, column| {
        c64::new(1.0, 0.0) / (axis[row] - poles[column])
    });
    let mut response = Mat::from_fn(axis.len(), 1, |row, _| reference[row]);
    for row in 0..axis.len() {
        let weight = 1.0 / magnitude(reference[row]).max(ZERO_MAGNITUDE_FLOOR);
        if !weight.is_finite() {
            return Err(FixedPoleRationalFitErrorV1::NonFiniteInput);
        }
        let factor = weight.sqrt();
        for column in 0..order {
            system[(row, column)] *= factor;
        }
        response[(row, 0)] *= factor;
    }
    let singular_values = system
        .as_ref()
        .thin_svd()
        .map_err(|_| FixedPoleRationalFitErrorV1::SolverFailure)?;
    let largest = singular_values.S()[0].re;
    let smallest = singular_values.S()[order - 1].re;
    if !largest.is_finite() || !smallest.is_finite() || smallest <= largest * RELATIVE_RANK_TOLERANCE {
        return Err(FixedPoleRationalFitErrorV1::RankDeficient);
    }
    let residues = system.as_ref().col_piv_qr().solve_lstsq(response.as_ref());
    let residues = (0..order)
        .map(|index| residues[(index, 0)])
        .collect::<Vec<_>>();
    if residues.iter().copied().any(|value| !finite(value)) {
        return Err(FixedPoleRationalFitErrorV1::NonFiniteModel);
    }
    let fitted = axis
        .iter()
        .copied()
        .map(|sample| model_value(sample, &poles, &residues))
        .collect::<Result<Vec<_>, _>>()?;
    let metrics = metrics(&reference, &fitted)?;
    let convert = |value: c64| {
        Complex64::try_new(value.re * OMEGA_SCALE, value.im * OMEGA_SCALE)
            .map_err(|_| FixedPoleRationalFitErrorV1::NonFiniteModel)
    };
    Ok(SelectedP3cFixedPoleRationalFitV1 {
        order,
        poles_per_second: poles.into_iter().map(convert).collect::<Result<_, _>>()?,
        residues_per_second: residues.into_iter().map(convert).collect::<Result<_, _>>()?,
        metrics,
    })
}

/// Fit the selected static scalar transfer with a fixed, single-threaded
/// pole-residue basis. No poles are relocated, reflected, or repaired.
pub fn fit_selected_p3c_fixed_pole_rational_v1(
    input: &SelectedP3cStaticDifferentialTransferV1,
) -> Result<SelectedP3cFixedPoleRationalFitV1, FixedPoleRationalFitErrorV1> {
    if input.frequencies().len() < 2 * ORDERS.last().copied().unwrap_or_default() {
        return Err(FixedPoleRationalFitErrorV1::TooFewSamples);
    }
    if input.frequencies().first().is_none_or(|frequency| frequency.get() != 0.0)
        || input.frequencies().last().is_none_or(|frequency| frequency.get().to_bits() != MAX_FREQUENCY_HZ.to_bits())
    {
        return Err(FixedPoleRationalFitErrorV1::InvalidFrequencyRange);
    }
    let mut best = None;
    for order in ORDERS {
        let candidate = fit_order(input, order)?;
        if within_admission(candidate.metrics) {
            return Ok(candidate);
        }
        if best.as_ref().is_none_or(|current: &SelectedP3cFixedPoleRationalFitV1| {
            candidate.metrics.relative_rms_error < current.metrics.relative_rms_error
        }) {
            best = Some(candidate);
        }
    }
    let _ = best;
    Err(FixedPoleRationalFitErrorV1::NoOrderMeetsAdmission)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{FourPortS, SelectedP3cFourPortSpectrumV1, reduce_selected_p3c_fixed_four_port_bench_v1};
    use sipi_types::{Hertz, Ohms};

    fn c(real: f64, imaginary: f64) -> Complex64 {
        Complex64::try_new(real, imaginary).unwrap()
    }

    fn transfer_from_poles(
        order: usize,
        start_hz: f64,
        end_hz: f64,
    ) -> SelectedP3cStaticDifferentialTransferV1 {
        let poles = initial_poles_normalized(order);
        let residues = poles
            .iter()
            .enumerate()
            .map(|(index, _)| c64::new(0.05 + index as f64 * 0.01, if index % 2 == 0 { 0.02 } else { -0.02 }))
            .collect::<Vec<_>>();
        let frequencies = (0..=64)
            .map(|index| Hertz::try_new(start_hz + (end_hz - start_hz) * index as f64 / 64.0).unwrap())
            .collect::<Vec<_>>();
        let values = frequencies
            .iter()
            .map(|frequency| {
                let value = model_value(c64::new(0.0, frequency.get() / MAX_FREQUENCY_HZ), &poles, &residues).unwrap();
                c(value.re, value.im)
            })
            .collect::<Vec<_>>();
        // This test-only construction still traverses the fixed bench reducer,
        // so the fit cannot accept an arbitrary standalone scalar type.
        let samples = values
            .iter()
            .map(|value| {
                let mut matrix = [[c(0.0, 0.0); 4]; 4];
                matrix[1][0] = c(value.real() * 2.0, value.imaginary() * 2.0);
                matrix[3][2] = c(value.real() * 2.0, value.imaginary() * 2.0);
                FourPortS::new(matrix)
            })
            .collect();
        let spectrum = SelectedP3cFourPortSpectrumV1::try_new(Ohms::try_new(50.0).unwrap(), frequencies, samples).unwrap();
        reduce_selected_p3c_fixed_four_port_bench_v1(&spectrum).unwrap()
    }

    #[test]
    fn fixed_basis_identifies_a_matching_strictly_proper_model() {
        let result = fit_selected_p3c_fixed_pole_rational_v1(
            &transfer_from_poles(8, 0.0, MAX_FREQUENCY_HZ),
        )
        .unwrap();
        assert_eq!(result.order(), 8);
        assert!(result.metrics().relative_rms_error() < 1.0e-10);
        assert!(result.poles_per_second().iter().all(|pole| pole.real() < 0.0));
    }

    #[test]
    fn rejects_missing_dc_or_wrong_band_before_any_fit() {
        let transfer = transfer_from_poles(8, 1.0, MAX_FREQUENCY_HZ);
        assert_eq!(fit_selected_p3c_fixed_pole_rational_v1(&transfer).unwrap_err(), FixedPoleRationalFitErrorV1::InvalidFrequencyRange);
    }

    #[test]
    fn zero_reference_transfer_is_a_structural_rejection() {
        let frequencies = (0..=64)
            .map(|index| Hertz::try_new(MAX_FREQUENCY_HZ * index as f64 / 64.0).unwrap())
            .collect::<Vec<_>>();
        let samples = frequencies
            .iter()
            .map(|_| FourPortS::new([[c(0.0, 0.0); 4]; 4]))
            .collect();
        let spectrum = SelectedP3cFourPortSpectrumV1::try_new(Ohms::try_new(50.0).unwrap(), frequencies, samples).unwrap();
        let transfer = reduce_selected_p3c_fixed_four_port_bench_v1(&spectrum).unwrap();
        assert_eq!(fit_selected_p3c_fixed_pole_rational_v1(&transfer).unwrap_err(), FixedPoleRationalFitErrorV1::ZeroSignalNorm);
    }
}
