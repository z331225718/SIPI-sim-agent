// SPDX-License-Identifier: MIT
// Direct-port source: Agent-COM `metrics/fd.py` at pinned commit
// `5272ffe74702cd585054d975559b06f8afae7b6e` (tree
// `7094ab6e84989b218730c52432c70da10261f8ea`).  The source map and notice in
// this crate bind the upstream Git object and license text.

//! R4.80 frequency-domain final metrics.
//!
//! This module ports the source `fit_insertion_loss`, `power_weight_function`,
//! `fd_loss_metrics`, `icn_rms`, and `r480_fd_icn_metrics` functions.  It
//! consumes an already supplied frequency axis and complex SDD21 traces.  It
//! does not read a touchstone file, perform a port transform, or resolve a
//! channel.  The four-term insertion-loss regression is the report metric
//! called by the source FD path; it is not a rational, vector, or other
//! S-parameter channel fit.

use std::{error::Error, fmt};

use sipi_types::Complex64;

/// Scope and provenance policy for the R4.80 FD final-metric leaf.
pub const FD_METRICS_POLICY_V1: &str = "sipi.com.metrics.fd-v1.r480-final-metrics";

/// Source-order insertion-loss report values.
#[derive(Clone, Debug, PartialEq)]
pub struct FdLossMetricsV1 {
    /// `20*log10(|S21|) - fitted_log_magnitude` for every input frequency.
    pub ild_db: Vec<f64>,
    /// The fitted log-magnitude trace returned by source `get_ILN`.
    pub fitted_loss_db: Vec<f64>,
    /// Raw insertion loss at the requested Nyquist frequency, in dB.
    pub insertion_loss_at_nyquist_db: f64,
    /// Negative fitted log-magnitude at the requested Nyquist frequency, dB.
    pub fitted_loss_at_nyquist_db: f64,
    /// Source `FOM_ILD` value.
    pub fom_ild: f64,
}

impl FdLossMetricsV1 {
    pub fn ild_db(&self) -> &[f64] {
        &self.ild_db
    }

    pub fn fitted_loss_db(&self) -> &[f64] {
        &self.fitted_loss_db
    }

    pub fn insertion_loss_at_nyquist_db(&self) -> f64 {
        self.insertion_loss_at_nyquist_db
    }

    pub fn fitted_loss_at_nyquist_db(&self) -> f64 {
        self.fitted_loss_at_nyquist_db
    }

    pub fn fom_ild(&self) -> f64 {
        self.fom_ild
    }
}

/// One raw SDD21 crosstalk contribution consumed by the source FD ICN path.
///
/// The source applies `amplitude_v` to the magnitude before squaring.  The
/// role is deliberately a borrowed string so the leaf does not invent a
/// network/channel ownership model.
#[derive(Clone, Copy, Debug)]
pub struct FdIcnAggressorV1<'a> {
    pub role: &'a str,
    pub frequency_hz: &'a [f64],
    pub transfer: &'a [Complex64],
    pub amplitude_v: f64,
}

/// Source-order FD ICN report values.
#[derive(Clone, Debug, PartialEq)]
pub struct FdIcnMetricsV1 {
    pub icn_v: f64,
    pub fext_icn_v: f64,
    pub next_icn_v: f64,
    /// Equation 93A-57 weight on the complete source frequency axis.
    pub power_weight: Vec<f64>,
    /// Combined `sqrt(sum((|PSXT|*amplitude)^2))` on the complete axis.
    pub psxt_v: Vec<f64>,
    /// Inclusive integration start index after source `searchsorted(...,
    /// side="right") - 1` and clamping.
    pub start_index: usize,
    /// Inclusive integration end index after source `searchsorted(...,
    /// side="left")` and clamping.  Empty-aggressor results use `-1`.
    pub end_index: isize,
}

impl FdIcnMetricsV1 {
    pub fn icn_v(&self) -> f64 {
        self.icn_v
    }

    pub fn fext_icn_v(&self) -> f64 {
        self.fext_icn_v
    }

    pub fn next_icn_v(&self) -> f64 {
        self.next_icn_v
    }

    pub fn power_weight(&self) -> &[f64] {
        &self.power_weight
    }

    pub fn psxt_v(&self) -> &[f64] {
        &self.psxt_v
    }

    pub fn start_index(&self) -> usize {
        self.start_index
    }

    pub fn end_index(&self) -> isize {
        self.end_index
    }
}

/// Errors raised while reproducing the source FD metric path.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum FdMetricsErrorV1 {
    InvalidFrequency,
    LengthMismatch,
    InvalidControls(&'static str),
    EmptyRange,
    SingularFit,
    AxisMismatch,
    NegativeAmplitude,
    UnsupportedRole(String),
    NonFiniteCalculation,
}

impl fmt::Display for FdMetricsErrorV1 {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "R480 FD metrics failed: {self:?}")
    }
}

impl Error for FdMetricsErrorV1 {}

/// Port `fit_insertion_loss` / source `get_ILN`.
///
/// The returned pair is `(ild_db, fitted_log_magnitude_db)`, matching the
/// Python function's return order and signs.  The fit is only a report
/// regression over the supplied SDD21 trace; it is not used to construct an
/// impulse response.
pub fn fit_insertion_loss_v1(
    s21: &[Complex64],
    frequency_hz: &[f64],
) -> Result<(Vec<f64>, Vec<f64>), FdMetricsErrorV1> {
    let frequency = validate_frequency(frequency_hz)?;
    if s21.len() != frequency.len() {
        return Err(FdMetricsErrorV1::LengthMismatch);
    }
    let magnitudes = s21
        .iter()
        .map(|value| {
            let result = value.real().hypot(value.imaginary());
            (result.is_finite()).then_some(result)
        })
        .collect::<Option<Vec<_>>>()
        .ok_or(FdMetricsErrorV1::NonFiniteCalculation)?;
    let loss = magnitudes
        .iter()
        .map(|value| db_from_magnitude(*value))
        .collect::<Vec<_>>();

    let mut normal = [[0.0_f64; 4]; 4];
    let mut rhs = [0.0_f64; 4];
    for (index, (magnitude, frequency)) in magnitudes.iter().zip(&frequency).enumerate() {
        let row = [
            *magnitude,
            frequency.sqrt() * magnitude,
            frequency * magnitude,
            frequency * frequency * magnitude,
        ];
        if row.iter().any(|value| !value.is_finite()) {
            return Err(FdMetricsErrorV1::NonFiniteCalculation);
        }
        for left in 0..4 {
            for right in 0..4 {
                normal[left][right] += row[left] * row[right];
            }
            rhs[left] += row[left] * (*magnitude * loss[index]);
        }
    }
    let alpha = solve_real_4x4(normal, rhs)?;
    let fitted = frequency
        .iter()
        .map(|frequency| {
            let value = alpha[0]
                + alpha[1] * frequency.sqrt()
                + alpha[2] * frequency
                + alpha[3] * frequency * frequency;
            value.is_finite().then_some(value)
        })
        .collect::<Option<Vec<_>>>()
        .ok_or(FdMetricsErrorV1::NonFiniteCalculation)?;
    let ild = loss
        .iter()
        .zip(&fitted)
        .map(|(raw, fit)| raw - fit)
        .collect::<Vec<_>>();
    if ild.iter().any(|value| !value.is_finite()) {
        return Err(FdMetricsErrorV1::NonFiniteCalculation);
    }
    Ok((ild, fitted))
}

/// Port `power_weight_function` (Equation 93A-57 in the source FD path).
pub fn power_weight_function_v1(
    frequency_hz: &[f64],
    samples_per_ui: usize,
    sample_dt_s: f64,
    transition_cutoff_hz: f64,
    receiver_cutoff_hz: f64,
) -> Result<Vec<f64>, FdMetricsErrorV1> {
    let frequency = validate_frequency(frequency_hz)?;
    if samples_per_ui == 0
        || !(sample_dt_s > 0.0)
        || !sample_dt_s.is_finite()
        || !(transition_cutoff_hz > 0.0)
        || !transition_cutoff_hz.is_finite()
        || !(receiver_cutoff_hz > 0.0)
        || !receiver_cutoff_hz.is_finite()
    {
        return Err(FdMetricsErrorV1::InvalidControls(
            "invalid FD power-weight parameters",
        ));
    }
    frequency
        .iter()
        .map(|frequency| {
            let angle = samples_per_ui as f64 * sample_dt_s * std::f64::consts::PI * *frequency;
            let safe_angle = if *frequency == 0.0 { 1.0e-20 } else { angle };
            let sinc = safe_angle.sin() / safe_angle;
            let value = sinc.powi(2)
                * (1.0 + (*frequency / transition_cutoff_hz).powi(4)).powi(-1)
                * (1.0 + (*frequency / receiver_cutoff_hz).powi(8)).powi(-1);
            value.is_finite().then_some(value)
        })
        .collect::<Option<Vec<_>>>()
        .ok_or(FdMetricsErrorV1::NonFiniteCalculation)
}

/// Port the source THRU FD insertion-loss report and `FOM_ILD` calculation.
#[allow(clippy::too_many_arguments)]
pub fn fd_loss_metrics_v1(
    s21: &[Complex64],
    frequency_hz: &[f64],
    nyquist_hz: f64,
    integration_start_hz: f64,
    integration_end_hz: f64,
    baud_hz: f64,
    samples_per_ui: usize,
    sample_dt_s: f64,
    transition_cutoff_hz: f64,
    receiver_cutoff_hz: f64,
) -> Result<FdLossMetricsV1, FdMetricsErrorV1> {
    let frequency = validate_frequency(frequency_hz)?;
    if s21.len() != frequency.len() {
        return Err(FdMetricsErrorV1::LengthMismatch);
    }
    if !nyquist_hz.is_finite()
        || !integration_start_hz.is_finite()
        || !integration_end_hz.is_finite()
        || !baud_hz.is_finite()
        || !(baud_hz > 0.0)
    {
        return Err(FdMetricsErrorV1::InvalidControls(
            "invalid FD loss controls",
        ));
    }
    let (ild, fitted) = fit_insertion_loss_v1(s21, &frequency)?;
    let raw_loss = s21
        .iter()
        .map(|value| -db_from_magnitude(value.real().hypot(value.imaginary())))
        .collect::<Vec<_>>();
    let mut start = upper_bound(&frequency, integration_start_hz).saturating_sub(1);
    let mut end = lower_bound(&frequency, integration_end_hz);
    if start >= frequency.len() {
        start = frequency.len() - 1;
    }
    if end >= frequency.len() {
        end = frequency.len() - 1;
    }
    if end < start {
        return Err(FdMetricsErrorV1::EmptyRange);
    }
    let power = power_weight_function_v1(
        &frequency,
        samples_per_ui,
        sample_dt_s,
        transition_cutoff_hz,
        receiver_cutoff_hz,
    )?;
    let delta_f = if frequency.len() >= 11 {
        frequency[10] - frequency[9]
    } else {
        frequency[1] - frequency[0]
    };
    // The source uses the residual, not the fitted trace, in FOM_ILD.  Keep
    // this separate from the full-trace result to preserve the source's
    // `(ild, fit)` return ordering.
    let (local_ild, _) = fit_insertion_loss_v1(&s21[start..=end], &frequency[start..=end])?;
    let sum = power[start..=end]
        .iter()
        .zip(&local_ild)
        .map(|(weight, value)| weight * value * value)
        .sum::<f64>();
    let fom = (delta_f / baud_hz * sum).sqrt();
    if !fom.is_finite() {
        return Err(FdMetricsErrorV1::NonFiniteCalculation);
    }
    let fitted_loss = fitted.iter().map(|value| -*value).collect::<Vec<_>>();
    Ok(FdLossMetricsV1 {
        ild_db: ild,
        fitted_loss_db: fitted,
        insertion_loss_at_nyquist_db: interpolate_clamped(&frequency, &raw_loss, nyquist_hz),
        fitted_loss_at_nyquist_db: interpolate_clamped(&frequency, &fitted_loss, nyquist_hz),
        fom_ild: fom,
    })
}

/// Port the source scalar ICN equation.
pub fn icn_rms_v1(
    crosstalk_transfer: &[Complex64],
    frequency_hz: &[f64],
    power_weight: &[f64],
    delta_f_hz: f64,
    baud_hz: f64,
) -> Result<f64, FdMetricsErrorV1> {
    let frequency = validate_frequency(frequency_hz)?;
    if crosstalk_transfer.len() != frequency.len()
        || power_weight.len() != frequency.len()
        || !(delta_f_hz > 0.0)
        || !delta_f_hz.is_finite()
        || !(baud_hz > 0.0)
        || !baud_hz.is_finite()
    {
        return Err(FdMetricsErrorV1::InvalidControls(
            "invalid ICN integration inputs",
        ));
    }
    let sum = crosstalk_transfer
        .iter()
        .zip(power_weight)
        .map(|(transfer, weight)| {
            let magnitude = transfer.real().hypot(transfer.imaginary());
            weight * magnitude * magnitude
        })
        .sum::<f64>();
    let result = (2.0 * delta_f_hz / baud_hz * sum).sqrt();
    result
        .is_finite()
        .then_some(result)
        .ok_or(FdMetricsErrorV1::NonFiniteCalculation)
}

/// Port the source raw-SDD21 FD ICN report path.
pub fn r480_fd_icn_metrics_v1(
    aggressors: &[FdIcnAggressorV1<'_>],
    f1_hz: f64,
    f2_hz: f64,
    baud_hz: f64,
    samples_per_ui: usize,
    sample_dt_s: f64,
    transition_cutoff_hz: f64,
    receiver_cutoff_hz: f64,
) -> Result<FdIcnMetricsV1, FdMetricsErrorV1> {
    if aggressors.is_empty() {
        return Ok(FdIcnMetricsV1 {
            icn_v: 0.0,
            fext_icn_v: 0.0,
            next_icn_v: 0.0,
            power_weight: Vec::new(),
            psxt_v: Vec::new(),
            start_index: 0,
            end_index: -1,
        });
    }
    if !f1_hz.is_finite()
        || !f2_hz.is_finite()
        || f1_hz < 0.0
        || f2_hz < f1_hz
        || !(baud_hz > 0.0)
        || !baud_hz.is_finite()
    {
        return Err(FdMetricsErrorV1::InvalidControls(
            "invalid r4.80 ICN integration controls",
        ));
    }
    let axis = validate_frequency(aggressors[0].frequency_hz)?;
    let mut start = upper_bound(&axis, f1_hz).saturating_sub(1);
    let mut end = lower_bound(&axis, f2_hz);
    if start >= axis.len() {
        start = axis.len() - 1;
    }
    if end >= axis.len() {
        end = axis.len() - 1;
    }
    if start > end {
        return Err(FdMetricsErrorV1::EmptyRange);
    }
    let power = power_weight_function_v1(
        &axis,
        samples_per_ui,
        sample_dt_s,
        transition_cutoff_hz,
        receiver_cutoff_hz,
    )?;
    let mut psxt_squared = vec![0.0_f64; axis.len()];
    let mut fext_squared = vec![0.0_f64; axis.len()];
    let mut next_squared = vec![0.0_f64; axis.len()];
    for aggressor in aggressors {
        let current_axis = validate_frequency(aggressor.frequency_hz)?;
        if aggressor.transfer.len() != axis.len()
            || current_axis.len() != axis.len()
            || current_axis
                .iter()
                .zip(&axis)
                .map(|(left, right)| (left - right).abs())
                .fold(0.0_f64, f64::max)
                > 1.0
        {
            return Err(FdMetricsErrorV1::AxisMismatch);
        }
        if !aggressor.amplitude_v.is_finite() || aggressor.amplitude_v < 0.0 {
            return Err(FdMetricsErrorV1::NegativeAmplitude);
        }
        let role = aggressor.role.to_ascii_uppercase();
        if role != "FEXT" && role != "NEXT" {
            return Err(FdMetricsErrorV1::UnsupportedRole(aggressor.role.to_owned()));
        }
        for index in 0..axis.len() {
            let transfer = aggressor.transfer[index];
            let magnitude = transfer.real().hypot(transfer.imaginary());
            let contribution = magnitude * aggressor.amplitude_v;
            let contribution = contribution * contribution;
            if !contribution.is_finite() {
                return Err(FdMetricsErrorV1::NonFiniteCalculation);
            }
            psxt_squared[index] += contribution;
            match role.as_str() {
                "FEXT" => fext_squared[index] += contribution,
                "NEXT" => next_squared[index] += contribution,
                _ => unreachable!("role was validated above"),
            }
        }
    }
    let delta_f = if axis.len() >= 11 {
        axis[10] - axis[9]
    } else {
        axis[1] - axis[0]
    };
    let icn_v = icn_rms_real_v1(
        &psxt_squared[start..=end],
        &power[start..=end],
        delta_f,
        baud_hz,
    )?;
    let fext_icn_v = icn_rms_real_v1(
        &fext_squared[start..=end],
        &power[start..=end],
        delta_f,
        baud_hz,
    )?;
    let next_icn_v = icn_rms_real_v1(
        &next_squared[start..=end],
        &power[start..=end],
        delta_f,
        baud_hz,
    )?;
    let psxt_v = psxt_squared.into_iter().map(f64::sqrt).collect::<Vec<_>>();
    Ok(FdIcnMetricsV1 {
        icn_v,
        fext_icn_v,
        next_icn_v,
        power_weight: power,
        psxt_v,
        start_index: start,
        end_index: end as isize,
    })
}

fn validate_frequency(values: &[f64]) -> Result<Vec<f64>, FdMetricsErrorV1> {
    if values.len() < 2
        || values
            .iter()
            .any(|value| !value.is_finite() || *value < 0.0)
        || values.windows(2).any(|pair| pair[1] <= pair[0])
    {
        return Err(FdMetricsErrorV1::InvalidFrequency);
    }
    Ok(values.to_vec())
}

fn db_from_magnitude(value: f64) -> f64 {
    20.0 * value.max(f64::MIN_POSITIVE).log10()
}

fn upper_bound(values: &[f64], target: f64) -> usize {
    values.partition_point(|value| *value <= target)
}

fn lower_bound(values: &[f64], target: f64) -> usize {
    values.partition_point(|value| *value < target)
}

fn interpolate_clamped(axis: &[f64], values: &[f64], target: f64) -> f64 {
    if target <= axis[0] {
        return values[0];
    }
    if target >= axis[axis.len() - 1] {
        return values[values.len() - 1];
    }
    let right = lower_bound(axis, target);
    if axis[right] == target {
        return values[right];
    }
    let left = right - 1;
    let fraction = (target - axis[left]) / (axis[right] - axis[left]);
    values[left] + fraction * (values[right] - values[left])
}

fn solve_real_4x4(
    mut matrix: [[f64; 4]; 4],
    mut rhs: [f64; 4],
) -> Result<[f64; 4], FdMetricsErrorV1> {
    for column in 0..4 {
        let pivot = (column..4)
            .max_by(|left, right| {
                matrix[*left][column]
                    .abs()
                    .total_cmp(&matrix[*right][column].abs())
            })
            .ok_or(FdMetricsErrorV1::SingularFit)?;
        if !matrix[pivot][column].is_finite() || matrix[pivot][column] == 0.0 {
            return Err(FdMetricsErrorV1::SingularFit);
        }
        if pivot != column {
            matrix.swap(pivot, column);
            rhs.swap(pivot, column);
        }
        for row in (column + 1)..4 {
            let factor = matrix[row][column] / matrix[column][column];
            matrix[row][column] = 0.0;
            for entry in (column + 1)..4 {
                matrix[row][entry] -= factor * matrix[column][entry];
            }
            rhs[row] -= factor * rhs[column];
        }
    }
    let mut result = [0.0_f64; 4];
    for row in (0..4).rev() {
        let mut value = rhs[row];
        for column in (row + 1)..4 {
            value -= matrix[row][column] * result[column];
        }
        if !matrix[row][row].is_finite() || matrix[row][row] == 0.0 {
            return Err(FdMetricsErrorV1::SingularFit);
        }
        result[row] = value / matrix[row][row];
    }
    if result.iter().any(|value| !value.is_finite()) {
        return Err(FdMetricsErrorV1::NonFiniteCalculation);
    }
    Ok(result)
}

fn icn_rms_real_v1(
    squared_transfer: &[f64],
    power_weight: &[f64],
    delta_f_hz: f64,
    baud_hz: f64,
) -> Result<f64, FdMetricsErrorV1> {
    if squared_transfer.len() != power_weight.len() || !(delta_f_hz > 0.0) || !(baud_hz > 0.0) {
        return Err(FdMetricsErrorV1::InvalidControls(
            "invalid ICN integration inputs",
        ));
    }
    let sum = squared_transfer
        .iter()
        .zip(power_weight)
        .map(|(transfer, weight)| weight * transfer)
        .sum::<f64>();
    let result = (2.0 * delta_f_hz / baud_hz * sum).sqrt();
    result
        .is_finite()
        .then_some(result)
        .ok_or(FdMetricsErrorV1::NonFiniteCalculation)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn transfer(index: usize) -> Complex64 {
        let frequency_ghz = index as f64;
        let magnitude = 0.92 - 0.006 * frequency_ghz;
        let phase = 0.1 + 0.017 * frequency_ghz;
        Complex64::try_new(magnitude * phase.cos(), -magnitude * phase.sin()).expect("finite")
    }

    #[test]
    fn source_vector_fit_and_power_weight() {
        let frequency = (0..16)
            .map(|index| index as f64 * 1.0e9)
            .collect::<Vec<_>>();
        let values = (0..16).map(transfer).collect::<Vec<_>>();
        let (ild, fitted) = fit_insertion_loss_v1(&values, &frequency).expect("fit");
        assert_eq!(ild.len(), 16);
        assert_eq!(fitted.len(), 16);
        assert!((fitted[0] - (-0.7242145816817659)).abs() < 2.0e-12);
        assert!((ild[0] - (-2.8871407127262216e-5)).abs() < 2.0e-12);
        let power =
            power_weight_function_v1(&frequency, 4, 1.0e-12, 20.0e9, 50.0e9).expect("weight");
        assert_eq!(power[0], 1.0);
        assert!((power[15] - 0.7506403192933225).abs() < 2.0e-14);
    }

    #[test]
    fn source_vector_loss_metrics_and_interpolation() {
        let frequency = (0..16)
            .map(|index| index as f64 * 1.0e9)
            .collect::<Vec<_>>();
        let values = (0..16).map(transfer).collect::<Vec<_>>();
        let metrics = fd_loss_metrics_v1(
            &values, &frequency, 8.0e9, 2.0e9, 13.0e9, 16.0e9, 4, 1.0e-12, 20.0e9, 50.0e9,
        )
        .expect("loss metrics");
        assert!((metrics.insertion_loss_at_nyquist_db - 1.1896703013486556).abs() < 2.0e-12);
        assert!((metrics.fitted_loss_at_nyquist_db - 1.189662099777845).abs() < 2.0e-12);
        assert!((metrics.fom_ild - 7.2189565329015015e-6).abs() < 2.0e-12);
    }

    #[test]
    fn tp0v_thru_source_canary_fitted_loss_at_nyquist() {
        // This is the pinned COM synthetic TP0V THRU law: 0..80 GHz in
        // 10 MHz steps, a one-pole low-pass normalized to -10 dB at 26.56
        // GHz, and a 1 ns delay.  The fit consumes only its magnitude, but
        // keeping the complex transfer here also exercises the SDD21 input
        // shape used by the source path.
        let frequency = (0..=8000)
            .map(|index| index as f64 * 1.0e7)
            .collect::<Vec<_>>();
        let target_magnitude = 10.0_f64.powf(-10.0 / 20.0);
        let pole_hz = 26.56e9 / (1.0 / target_magnitude.powi(2) - 1.0).sqrt();
        let transfer = frequency
            .iter()
            .map(|frequency| {
                let ratio = *frequency / pole_hz;
                let denominator = 1.0 + ratio * ratio;
                let low_pass_real = 1.0 / denominator;
                let low_pass_imaginary = -ratio / denominator;
                let (sin, cos) = (2.0 * std::f64::consts::PI * *frequency * 1.0e-9).sin_cos();
                Complex64::try_new(
                    low_pass_real * cos + low_pass_imaginary * sin,
                    low_pass_imaginary * cos - low_pass_real * sin,
                )
                .expect("finite TP0V synthetic transfer")
            })
            .collect::<Vec<_>>();
        let (_, fitted) = fit_insertion_loss_v1(&transfer, &frequency).expect("TP0V fit");
        let fitted_loss = fitted.iter().map(|value| -*value).collect::<Vec<_>>();
        let fitted_at_nyquist = interpolate_clamped(&frequency, &fitted_loss, 26.5625e9);
        assert!(
            (fitted_at_nyquist - 9.834_912_844_951_186).abs() < 2.0e-12,
            "TP0V fitted IL at Fnq was {fitted_at_nyquist:.16}, expected 9.8349128449511856"
        );
    }

    #[test]
    fn source_vector_icn_and_roles() {
        let frequency = (0..16)
            .map(|index| index as f64 * 1.0e9)
            .collect::<Vec<_>>();
        let fext = (0..16)
            .map(|index| Complex64::try_new(0.01, 0.002 * (index + 1) as f64).expect("finite"))
            .collect::<Vec<_>>();
        let next = (0..16)
            .map(|index| Complex64::try_new(0.014, -0.001 * (index + 2) as f64).expect("finite"))
            .collect::<Vec<_>>();
        let metrics = r480_fd_icn_metrics_v1(
            &[
                FdIcnAggressorV1 {
                    role: "FEXT",
                    frequency_hz: &frequency,
                    transfer: &fext,
                    amplitude_v: 0.5,
                },
                FdIcnAggressorV1 {
                    role: "NEXT",
                    frequency_hz: &frequency,
                    transfer: &next,
                    amplitude_v: 0.25,
                },
            ],
            2.0e9,
            13.0e9,
            16.0e9,
            4,
            1.0e-12,
            20.0e9,
            50.0e9,
        )
        .expect("icn");
        assert_eq!((metrics.start_index, metrics.end_index), (2, 13));
        assert!((metrics.icn_v - 0.013354460909082991).abs() < 2.0e-14);
        assert!((metrics.fext_icn_v - 0.012327028142642924).abs() < 2.0e-14);
        assert!((metrics.next_icn_v - 0.0051367308030219995).abs() < 2.0e-14);
    }

    #[test]
    fn malformed_axis_and_role_fail_closed() {
        let frequency = [0.0, 1.0, 2.0, 3.0];
        let transfer = [Complex64::try_new(1.0, 0.0).expect("finite"); 4];
        assert_eq!(
            fit_insertion_loss_v1(&transfer[..3], &frequency),
            Err(FdMetricsErrorV1::LengthMismatch)
        );
        let error = r480_fd_icn_metrics_v1(
            &[FdIcnAggressorV1 {
                role: "THRU",
                frequency_hz: &frequency,
                transfer: &transfer,
                amplitude_v: 1.0,
            }],
            0.0,
            2.0,
            1.0,
            1,
            1.0,
            1.0,
            1.0,
        )
        .expect_err("unsupported role");
        assert_eq!(error, FdMetricsErrorV1::UnsupportedRole("THRU".to_owned()));
    }

    #[test]
    fn four_point_source_fit_is_supported() {
        let frequency = [1.0, 2.0, 3.0, 4.0];
        let values = (1..=4)
            .map(|index| {
                let index = index as f64;
                let magnitude = (-0.01 * index).exp();
                let phase = index - 1.0;
                Complex64::try_new(magnitude * phase.cos(), -magnitude * phase.sin())
                    .expect("finite")
            })
            .collect::<Vec<_>>();
        let result = fit_insertion_loss_v1(&values, &frequency);
        assert!(result.is_ok());
    }
}
