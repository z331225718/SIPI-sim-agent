// SPDX-License-Identifier: MIT
// Direct-port source: Agent-COM `signal/fd_to_td.py` and
// `signal/interpolation.py` at pinned commit/tree recorded in
// `crates/sipi-agent-com-direct/SOURCE-MAP-COM-02.md`.
//
//! Portable frequency-domain to time-domain conversion for the COM signal path.
//!
//! This is the Rust port of the upstream `signal/fd_to_td.py` and its
//! interpolation helper.  It deliberately performs no rational/S-parameter
//! fit: the input trace is interpolated onto the bounded FFT grid and then
//! transformed directly.  The optional insertion-loss fit used by the
//! separate TDILN report lives in `tdiln_v1` and is not a channel resolver.

use std::{error::Error, fmt};

use rustfft::{FftPlanner, num_complex::Complex};
use sipi_types::Complex64;

pub const FD_TO_TD_POLICY_V1: &str = "sipi.com.signal.fd-to-td-v1.r480-interpolation-ifft";
pub const MAX_FD_TO_TD_BINS_V1: usize = 2_097_152;

#[derive(Clone, Debug, PartialEq)]
pub struct FdToTdOptionsV1 {
    pub sample_dt_s: f64,
    pub magnitude_policy: String,
    pub phase_policy: String,
    pub enforce_causality: bool,
    pub ec_pulse_tolerance: f64,
    pub ec_relative_tolerance: f64,
    pub ec_difference_tolerance: f64,
    pub truncation_threshold: f64,
    pub debug: bool,
    pub max_iterations: usize,
}

impl Default for FdToTdOptionsV1 {
    fn default() -> Self {
        Self {
            sample_dt_s: 1.0e-12,
            magnitude_policy: "trend_to_DC".to_owned(),
            phase_policy: "interp_to_DC".to_owned(),
            enforce_causality: false,
            ec_pulse_tolerance: 0.05,
            ec_relative_tolerance: 0.006,
            ec_difference_tolerance: 1.0e-4,
            truncation_threshold: 1.0e-7,
            debug: false,
            max_iterations: 10_000,
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct ImpulseResultV1 {
    pub voltage: Vec<f64>,
    pub time_s: Vec<f64>,
    pub causality_correction_db: f64,
    pub truncation_db: f64,
    pub causality_iterations: usize,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum FdToTdErrorV1 {
    InvalidInput(&'static str),
    LengthMismatch,
    UnsupportedMagnitudePolicy(String),
    UnsupportedPhasePolicy(String),
    TooManyBins,
    NoFrequencyInterval,
    NoCausalStart,
    CausalityLimit,
    CausalityAllZero,
    NonFiniteCalculation,
}

impl fmt::Display for FdToTdErrorV1 {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "R480 FD-to-TD failed: {self:?}")
    }
}

impl Error for FdToTdErrorV1 {}

/// Convert one complex S-parameter trace to a finite causal/truncated impulse.
pub fn s21_to_impulse_dc_v1(
    s21: &[Complex64],
    frequency_hz: &[f64],
    options: &FdToTdOptionsV1,
) -> Result<ImpulseResultV1, FdToTdErrorV1> {
    if s21.len() < 3 || frequency_hz.len() < 3 {
        return Err(FdToTdErrorV1::InvalidInput(
            "at least three samples are required",
        ));
    }
    if s21.len() != frequency_hz.len() {
        return Err(FdToTdErrorV1::LengthMismatch);
    }
    if frequency_hz
        .iter()
        .any(|value| !value.is_finite() || *value < 0.0)
        || frequency_hz.windows(2).any(|pair| pair[1] <= pair[0])
    {
        return Err(FdToTdErrorV1::InvalidInput(
            "frequency axis must be increasing and non-negative",
        ));
    }
    if !(options.sample_dt_s > 0.0)
        || !(0.0 < options.ec_pulse_tolerance && options.ec_pulse_tolerance <= 1.0)
        || options.ec_relative_tolerance < 0.0
        || options.ec_difference_tolerance < 0.0
        || options.truncation_threshold < 0.0
        || options.max_iterations == 0
    {
        return Err(FdToTdErrorV1::InvalidInput("invalid FD-to-TD controls"));
    }
    let fmax = 1.0 / (2.0 * options.sample_dt_s);
    let source_df = frequency_hz[2] - frequency_hz[1];
    if !(source_df.is_finite() && source_df > 0.0) {
        return Err(FdToTdErrorV1::NoFrequencyInterval);
    }
    let points_float = (fmax / source_df + 0.5).floor();
    if !(points_float.is_finite() && points_float >= 1.0)
        || points_float > MAX_FD_TO_TD_BINS_V1 as f64
    {
        return Err(FdToTdErrorV1::TooManyBins);
    }
    let points = points_float as usize;
    let fout = (0..=points)
        .map(|index| index as f64 * fmax / points as f64)
        .collect::<Vec<_>>();
    let all_zero = s21
        .iter()
        .all(|value| value.real() == 0.0 && value.imaginary() == 0.0);
    let interpolated = if all_zero {
        // NumPy's all-zero branch uses eps rather than an exact zero so that
        // log-domain magnitude interpolation remains defined.
        vec![Complex::new(f64::EPSILON, 0.0); fout.len()]
    } else {
        interpolate_sparameter_v1(
            s21,
            frequency_hz,
            &fout,
            &options.magnitude_policy,
            &options.phase_policy,
            options.debug,
        )?
    };
    let mut symmetric = Vec::with_capacity(points * 2);
    symmetric.push(Complex::new(interpolated[0].re, 0.0));
    for value in interpolated
        .iter()
        .skip(1)
        .take(interpolated.len().saturating_sub(2))
    {
        symmetric.push(*value);
    }
    symmetric.push(Complex::new(interpolated[points].re, 0.0));
    for value in interpolated[1..points].iter().rev() {
        symmetric.push(value.conj());
    }
    let mut spectrum = symmetric;
    let length = spectrum.len();
    FftPlanner::<f64>::new()
        .plan_fft_inverse(length)
        .process(&mut spectrum);
    let scale = 1.0 / length as f64;
    let mut impulse = spectrum
        .iter()
        .map(|value| value.re * scale)
        .collect::<Vec<_>>();
    if impulse.iter().any(|value| !value.is_finite()) {
        return Err(FdToTdErrorV1::NonFiniteCalculation);
    }
    let original = impulse.clone();
    let iterations = if options.enforce_causality {
        enforce_causality_v1(&mut impulse, &spectrum_from_values(&interpolated), options)?
    } else {
        0
    };
    let correction = db_ratio_v1(
        norm_v1(
            &impulse
                .iter()
                .zip(&original)
                .map(|(left, right)| left - right)
                .collect::<Vec<_>>(),
        ),
        norm_v1(&impulse),
    );
    let peak = impulse.iter().map(|value| value.abs()).fold(0.0, f64::max);
    if !(peak.is_finite() && peak > 0.0) {
        return Err(FdToTdErrorV1::NonFiniteCalculation);
    }
    let last = impulse
        .iter()
        .rposition(|value| value.abs() > peak * options.truncation_threshold)
        .map(|index| index + 1)
        .ok_or(FdToTdErrorV1::NonFiniteCalculation)?;
    let truncation = db_ratio_v1(norm_v1(&impulse[last..]), norm_v1(&impulse[..last]));
    let voltage = impulse[..last].to_vec();
    let time_s = (0..last)
        .map(|index| index as f64 / (source_df * length as f64))
        .collect::<Vec<_>>();
    Ok(ImpulseResultV1 {
        voltage,
        time_s,
        causality_correction_db: correction,
        truncation_db: truncation,
        causality_iterations: iterations,
    })
}

/// The source's zero-state rectangular pulse response.
pub fn rectangular_pulse_response_fd_v1(
    impulse: &[f64],
    samples_per_ui: usize,
) -> Result<Vec<f64>, FdToTdErrorV1> {
    if impulse.is_empty() || samples_per_ui == 0 {
        return Err(FdToTdErrorV1::InvalidInput(
            "rectangular pulse requires samples and a positive span",
        ));
    }
    let mut result = vec![0.0; impulse.len()];
    let mut running = 0.0;
    for index in 0..impulse.len() {
        running += impulse[index];
        if index >= samples_per_ui {
            running -= impulse[index - samples_per_ui];
        }
        result[index] = running;
    }
    Ok(result)
}

fn interpolate_sparameter_v1(
    values: &[Complex64],
    fin: &[f64],
    fout: &[f64],
    magnitude_policy: &str,
    phase_policy: &str,
    debug: bool,
) -> Result<Vec<Complex<f64>>, FdToTdErrorV1> {
    if values.len() != fin.len() || fin.len() < 2 || fout.is_empty() {
        return Err(FdToTdErrorV1::LengthMismatch);
    }
    let magnitudes = values
        .iter()
        .map(|value| value.real().hypot(value.imaginary()).max(f64::EPSILON))
        .collect::<Vec<_>>();
    let phase = unwrap_phase_v1(values)?;
    if has_positive_unwrapped_phase_slope_from_phase_v1(&phase)? && !debug {
        return Err(FdToTdErrorV1::InvalidInput("anti-causal response found"));
    }
    let magnitude = interpolate_magnitude_v1(&magnitudes, fin, fout, magnitude_policy)?;
    let phase = interpolate_phase_v1(&phase, fin, fout, phase_policy)?;
    magnitude
        .into_iter()
        .zip(phase)
        .map(|(magnitude, phase)| {
            let value = Complex::from_polar(magnitude, phase);
            (value.re.is_finite() && value.im.is_finite())
                .then_some(value)
                .ok_or(FdToTdErrorV1::NonFiniteCalculation)
        })
        .collect()
}

/// Exact R4.80 anti-causal guard used before S-parameter interpolation.
///
/// The source predicate is `mean(diff(unwrap(angle(s)))) > 0`. This helper
/// exposes that predicate without changing the FD-to-TD result: callers that
/// deliberately enable the source DEBUG bypass can report the degraded state
/// while the converter keeps its existing reject-or-proceed semantics.
pub fn has_positive_unwrapped_phase_slope_v1(values: &[Complex64]) -> Result<bool, FdToTdErrorV1> {
    if values.len() < 2 {
        return Err(FdToTdErrorV1::LengthMismatch);
    }
    let phase = unwrap_phase_v1(values)?;
    has_positive_unwrapped_phase_slope_from_phase_v1(&phase)
}

fn has_positive_unwrapped_phase_slope_from_phase_v1(phase: &[f64]) -> Result<bool, FdToTdErrorV1> {
    if phase.len() < 2 {
        return Err(FdToTdErrorV1::LengthMismatch);
    }
    let mean_slope =
        phase.windows(2).map(|pair| pair[1] - pair[0]).sum::<f64>() / (phase.len() - 1) as f64;
    if !mean_slope.is_finite() {
        return Err(FdToTdErrorV1::NonFiniteCalculation);
    }
    Ok(mean_slope > 0.0)
}

fn interpolate_magnitude_v1(
    magnitude: &[f64],
    fin: &[f64],
    fout: &[f64],
    policy: &str,
) -> Result<Vec<f64>, FdToTdErrorV1> {
    match policy {
        "linear_trend_to_DC" | "linear_trend_to_DC_log_trend_to_inf" => {
            need_points_v1(fin, 10, policy)?;
            let mut x = fin.to_vec();
            let mut y = magnitude.to_vec();
            if fin[0] > 0.0 {
                let (_, intercept) = line_fit_v1(&fin[..10], &magnitude[..10])?;
                x.insert(0, 0.0);
                y.insert(0, intercept);
            }
            let mut high_log_value = None;
            if fin[fin.len() - 1] < fout[fout.len() - 1] {
                let start = ((fin.len() as f64 / 2.0 + 0.5).floor() as usize).saturating_sub(1);
                let (slope, intercept) = line_fit_v1(&fin[start..], &magnitude[start..])?;
                let mut high = slope * fout[fout.len() - 1] + intercept;
                if high > magnitude[magnitude.len() - 1] {
                    high = magnitude[magnitude.len() - 1];
                    high_log_value = Some(high);
                } else if high < f64::EPSILON {
                    high = f64::EPSILON;
                    high_log_value = Some(f64::MIN_POSITIVE);
                } else {
                    high_log_value = Some(high);
                }
                x.push(fout[fout.len() - 1]);
                y.push(high);
            } else if policy == "linear_trend_to_DC_log_trend_to_inf" {
                return Err(FdToTdErrorV1::InvalidInput(
                    "log high-frequency trend needs output above input",
                ));
            }
            let linear = linear_interp_extrap_v1(&x, &y, fout)?;
            if policy == "linear_trend_to_DC_log_trend_to_inf"
                && fin[fin.len() - 1] < fout[fout.len() - 1]
            {
                let mut log_y = y[..y.len() - 1]
                    .iter()
                    .map(|value| value.ln())
                    .collect::<Vec<_>>();
                log_y.push(
                    high_log_value
                        .ok_or(FdToTdErrorV1::NonFiniteCalculation)?
                        .ln(),
                );
                let log_linear = linear_interp_extrap_v1(&x, &log_y, fout)?;
                Ok(linear
                    .into_iter()
                    .zip(log_linear)
                    .zip(fout)
                    .map(|((value, log_value), frequency)| {
                        if *frequency > fin[fin.len() - 1] {
                            log_value
                                .is_finite()
                                .then_some(log_value.exp())
                                .ok_or(FdToTdErrorV1::NonFiniteCalculation)
                        } else {
                            Ok(value)
                        }
                    })
                    .collect::<Result<Vec<_>, _>>()?)
            } else {
                Ok(linear)
            }
        }
        "trend_to_DC" => {
            need_points_v1(fin, 10, policy)?;
            let mut x = fin.to_vec();
            let original_log_y = magnitude
                .iter()
                .map(|value| value.log10())
                .collect::<Vec<_>>();
            let mut log_y = original_log_y.clone();
            if fin[0] > 0.0 {
                let (slope, intercept) = line_fit_v1(&fin[..10], &original_log_y[..10])?;
                x.insert(0, 0.0);
                log_y.insert(0, intercept + slope * 0.0);
            }
            if fin[fin.len() - 1] < fout[fout.len() - 1] {
                let start = ((fin.len() as f64 / 2.0 + 0.5).floor() as usize).saturating_sub(1);
                let (slope, intercept) = line_fit_v1(&fin[start..], &original_log_y[start..])?;
                let high = 10.0_f64
                    .powf(slope * fout[fout.len() - 1] + intercept)
                    .min(*magnitude.last().expect("magnitude"));
                x.push(fout[fout.len() - 1]);
                log_y.push(high.log10());
            }
            Ok(linear_interp_extrap_v1(&x, &log_y, fout)?
                .into_iter()
                .map(|value| 10.0_f64.powf(value))
                .collect())
        }
        "extrap_to_DC_or_zero" | "extrap_to_DC" => {
            let selected = fout
                .iter()
                .map(|value| *value <= fin[fin.len() - 1])
                .collect::<Vec<_>>();
            let (x, y) = if policy == "extrap_to_DC_or_zero"
                && fin[0] > 0.0
                && 20.0 * magnitude[0].log10() < -20.0
            {
                let mut x = vec![0.0];
                x.extend_from_slice(fin);
                let mut y = vec![-100.0];
                y.extend(magnitude.iter().map(|value| value.log10()));
                (x, y)
            } else {
                (
                    fin.to_vec(),
                    magnitude.iter().map(|value| value.log10()).collect(),
                )
            };
            let selected_targets = fout
                .iter()
                .zip(&selected)
                .filter_map(|(value, take)| take.then_some(*value))
                .collect::<Vec<_>>();
            let selected_result = linear_interp_extrap_v1(&x, &y, &selected_targets)?;
            let mut result = Vec::with_capacity(fout.len());
            let mut cursor = 0;
            for take in selected {
                if take {
                    result.push(10.0_f64.powf(selected_result[cursor]));
                    cursor += 1;
                } else {
                    result.push(*magnitude.last().expect("magnitude"));
                }
            }
            Ok(result)
        }
        "old" => linear_interp_extrap_v1(fin, magnitude, fout),
        other => Err(FdToTdErrorV1::UnsupportedMagnitudePolicy(other.to_owned())),
    }
}

fn interpolate_phase_v1(
    phase: &[f64],
    fin: &[f64],
    fout: &[f64],
    policy: &str,
) -> Result<Vec<f64>, FdToTdErrorV1> {
    let result = linear_interp_extrap_v1(fin, phase, fout)?;
    match policy {
        "old" => {
            let first = result[0];
            Ok(result.into_iter().map(|value| value - first).collect())
        }
        "zero_DC" => {
            let mut result = result;
            result[0] = 0.0;
            Ok(result)
        }
        "interp_to_DC" => {
            if fin[0] == 0.0 {
                Ok(result)
            } else {
                let mut x = vec![0.0];
                x.extend_from_slice(fin);
                let mut y = vec![0.0];
                y.extend_from_slice(phase);
                linear_interp_extrap_v1(&x, &y, fout)
            }
        }
        "interp_and_shift_to_DC" => {
            if fin[0] == 0.0 {
                Ok(result)
            } else {
                let dc_phase = phase[0] - (phase[1] - phase[0]) / (fin[1] - fin[0]) * fin[0];
                let mut x = vec![0.0];
                x.extend_from_slice(fin);
                let mut y = vec![0.0];
                y.extend(phase.iter().map(|value| value - dc_phase));
                linear_interp_extrap_v1(&x, &y, fout)
            }
        }
        "trend_and_shift_to_DC" => {
            need_points_v1(fin, 51, policy)?;
            let group_delay = phase
                .windows(2)
                .zip(fin.windows(2))
                .map(|(p, f)| -(p[1] - p[0]) / (f[1] - f[0]))
                .collect::<Vec<_>>();
            let trend = inlier_mean_v1(&group_delay[..50])?;
            let mut x = fin.to_vec();
            let mut y = phase.to_vec();
            if fin[0] != 0.0 {
                for index in (0..10).rev() {
                    y[index] = y[index + 1] + trend * (fin[index + 1] - fin[index]);
                }
                let dc_phase = y[0] + trend * fin[0];
                x.insert(0, 0.0);
                y = y.into_iter().map(|value| value - dc_phase).collect();
                y.insert(0, 0.0);
            }
            if fout[fout.len() - 1] > fin[fin.len() - 1] {
                let high_trend = median_v1(
                    &x.windows(2)
                        .zip(y.windows(2))
                        .map(|(f, p)| -(p[1] - p[0]) / (f[1] - f[0]))
                        .collect::<Vec<_>>(),
                )?;
                x.push(fout[fout.len() - 1]);
                y.push(y[y.len() - 1] - high_trend * (fout[fout.len() - 1] - x[x.len() - 2]));
            }
            linear_interp_extrap_v1(&x, &y, fout)
        }
        "extrap_cubic_to_dc_linear_to_inf" => {
            need_points_v1(fin, 51, policy)?;
            if fin[0] == 0.0 {
                return Ok(result);
            }
            let group_delay = phase
                .windows(2)
                .zip(fin.windows(2))
                .map(|(p, f)| -(p[1] - p[0]) / (f[1] - f[0]))
                .collect::<Vec<_>>();
            let low_trend = inlier_mean_v1(&group_delay[..50])?;
            let mut corrected = phase.to_vec();
            for index in (0..10).rev() {
                corrected[index] = corrected[index + 1] + low_trend * (fin[index + 1] - fin[index]);
            }
            let mut linear = linear_interp_extrap_v1(fin, &corrected, fout)?;
            let high = fout
                .iter()
                .enumerate()
                .filter(|(_, value)| **value > *fin.last().expect("frequency"))
                .map(|(index, _)| index)
                .collect::<Vec<_>>();
            if !high.is_empty() {
                // The source uses ``group_delay[-51:]``.  A 51-point input
                // has only 50 interval samples, so the Python slice keeps
                // the complete interval vector instead of underflowing a
                // Rust range.
                let high_trend =
                    -inlier_mean_v1(&group_delay[group_delay.len().saturating_sub(51)..])?;
                let first = high[0].saturating_sub(1);
                for index in high {
                    linear[index] = linear[first] + (fout[index] - fout[first]) * high_trend;
                }
            }
            Ok(linear)
        }
        other => Err(FdToTdErrorV1::UnsupportedPhasePolicy(other.to_owned())),
    }
}

fn enforce_causality_v1(
    impulse: &mut [f64],
    spectrum: &[Complex<f64>],
    options: &FdToTdOptionsV1,
) -> Result<usize, FdToTdErrorV1> {
    let half = impulse.len() / 2;
    let first_peak = impulse[..half]
        .iter()
        .map(|value| value.abs())
        .fold(0.0, f64::max);
    let start = impulse[..half]
        .iter()
        .position(|value| value.abs() > first_peak * options.ec_pulse_tolerance)
        .map(|index| index + 1)
        .ok_or(FdToTdErrorV1::NoCausalStart)?;
    let mut current = impulse.to_vec();
    let mut previous = f64::INFINITY;
    for iteration in 0..options.max_iterations {
        if current.iter().all(|value| *value == 0.0) {
            return Err(FdToTdErrorV1::CausalityAllZero);
        }
        current[..start].fill(0.0);
        current[half.saturating_sub(1)..].fill(0.0);
        let mut transformed = current
            .iter()
            .map(|value| Complex::new(*value, 0.0))
            .collect::<Vec<_>>();
        FftPlanner::<f64>::new()
            .plan_fft_forward(transformed.len())
            .process(&mut transformed);
        for (value, source) in transformed.iter_mut().zip(spectrum) {
            *value = Complex::from_polar(source.norm(), value.arg());
        }
        FftPlanner::<f64>::new()
            .plan_fft_inverse(transformed.len())
            .process(&mut transformed);
        let scale = 1.0 / transformed.len() as f64;
        let modified = transformed
            .iter()
            .map(|value| value.re * scale)
            .collect::<Vec<_>>();
        let delta = current
            .iter()
            .zip(&modified)
            .map(|(left, right)| (left - right).abs())
            .fold(0.0, f64::max);
        let denominator = current.iter().copied().fold(f64::NEG_INFINITY, f64::max);
        if !(delta.is_finite() && denominator.is_finite() && denominator > 0.0) {
            return Err(FdToTdErrorV1::NonFiniteCalculation);
        }
        let error = delta / denominator;
        if error < options.ec_relative_tolerance
            || (previous - error).abs() < options.ec_difference_tolerance
        {
            impulse.copy_from_slice(&current);
            return Ok(iteration + 1);
        }
        previous = error;
        current = modified;
    }
    Err(FdToTdErrorV1::CausalityLimit)
}

fn spectrum_from_values(values: &[Complex<f64>]) -> Vec<Complex<f64>> {
    let points = values.len() - 1;
    let mut result = Vec::with_capacity(points * 2);
    result.push(Complex::new(values[0].re, 0.0));
    result.extend(values[1..points].iter().copied());
    result.push(Complex::new(values[points].re, 0.0));
    result.extend(values[1..points].iter().rev().map(Complex::conj));
    result
}

fn unwrap_phase_v1(values: &[Complex64]) -> Result<Vec<f64>, FdToTdErrorV1> {
    let mut result = Vec::with_capacity(values.len());
    for value in values {
        let mut phase = value.imaginary().atan2(value.real());
        if !phase.is_finite() {
            return Err(FdToTdErrorV1::NonFiniteCalculation);
        }
        if let Some(previous) = result.last().copied() {
            let mut delta = phase - previous;
            while delta > std::f64::consts::PI {
                phase -= std::f64::consts::TAU;
                delta -= std::f64::consts::TAU;
            }
            while delta <= -std::f64::consts::PI {
                phase += std::f64::consts::TAU;
                delta += std::f64::consts::TAU;
            }
        }
        result.push(phase);
    }
    Ok(result)
}

fn linear_interp_extrap_v1(
    x: &[f64],
    y: &[f64],
    targets: &[f64],
) -> Result<Vec<f64>, FdToTdErrorV1> {
    if x.len() != y.len() || x.len() < 2 || x.windows(2).any(|pair| pair[1] <= pair[0]) {
        return Err(FdToTdErrorV1::InvalidInput(
            "interpolation axis is not increasing",
        ));
    }
    if targets.windows(2).all(|pair| pair[0] <= pair[1]) {
        // All FD-to-TD call sites provide a monotonic frequency grid. Reuse
        // the previous bracket instead of binary-searching every output bin;
        // the loop preserves the same rightmost-`<=` bracket and arithmetic.
        let mut upper = 1usize;
        return targets
            .iter()
            .map(|target| {
                while upper < x.len() - 1 && x[upper] <= *target {
                    upper += 1;
                }
                let lower = upper - 1;
                let fraction = (*target - x[lower]) / (x[upper] - x[lower]);
                let value = y[lower] + fraction * (y[upper] - y[lower]);
                value
                    .is_finite()
                    .then_some(value)
                    .ok_or(FdToTdErrorV1::NonFiniteCalculation)
            })
            .collect();
    }
    targets
        .iter()
        .map(|target| {
            let upper = x
                .partition_point(|value| *value <= *target)
                .clamp(1, x.len() - 1);
            let lower = upper - 1;
            let fraction = (*target - x[lower]) / (x[upper] - x[lower]);
            let value = y[lower] + fraction * (y[upper] - y[lower]);
            value
                .is_finite()
                .then_some(value)
                .ok_or(FdToTdErrorV1::NonFiniteCalculation)
        })
        .collect()
}

fn line_fit_v1(x: &[f64], y: &[f64]) -> Result<(f64, f64), FdToTdErrorV1> {
    if x.len() != y.len() || x.len() < 2 {
        return Err(FdToTdErrorV1::InvalidInput(
            "linear trend needs at least two points",
        ));
    }
    let x_mean = x.iter().sum::<f64>() / x.len() as f64;
    let y_mean = y.iter().sum::<f64>() / y.len() as f64;
    let numerator = x
        .iter()
        .zip(y)
        .map(|(x, y)| (x - x_mean) * (y - y_mean))
        .sum::<f64>();
    let denominator = x.iter().map(|x| (x - x_mean).powi(2)).sum::<f64>();
    if !(denominator.is_finite() && denominator > 0.0) {
        return Err(FdToTdErrorV1::NonFiniteCalculation);
    }
    let slope = numerator / denominator;
    let intercept = y_mean - slope * x_mean;
    (slope.is_finite() && intercept.is_finite())
        .then_some((slope, intercept))
        .ok_or(FdToTdErrorV1::NonFiniteCalculation)
}

fn need_points_v1(values: &[f64], minimum: usize, policy: &str) -> Result<(), FdToTdErrorV1> {
    if values.len() < minimum {
        return Err(FdToTdErrorV1::InvalidInput(match policy {
            "trend_to_DC" => "trend-to-DC needs at least ten frequency points",
            _ => "selected interpolation policy needs more frequency points",
        }));
    }
    Ok(())
}

fn median_v1(values: &[f64]) -> Result<f64, FdToTdErrorV1> {
    if values.is_empty() {
        return Err(FdToTdErrorV1::NonFiniteCalculation);
    }
    let mut sorted = values.to_vec();
    sorted.sort_by(f64::total_cmp);
    let middle = sorted.len() / 2;
    let value = if sorted.len().is_multiple_of(2) {
        (sorted[middle - 1] + sorted[middle]) / 2.0
    } else {
        sorted[middle]
    };
    value
        .is_finite()
        .then_some(value)
        .ok_or(FdToTdErrorV1::NonFiniteCalculation)
}

fn inlier_mean_v1(values: &[f64]) -> Result<f64, FdToTdErrorV1> {
    let median = median_v1(values)?;
    let mean = values.iter().sum::<f64>() / values.len() as f64;
    let sigma = (values
        .iter()
        .map(|value| (value - mean).powi(2))
        .sum::<f64>()
        / values.len() as f64)
        .sqrt();
    let selected = values
        .iter()
        .copied()
        .filter(|value| (*value - median).abs() < sigma)
        .collect::<Vec<_>>();
    let result = if selected.is_empty() {
        median
    } else {
        selected.iter().sum::<f64>() / selected.len() as f64
    };
    result
        .is_finite()
        .then_some(result)
        .ok_or(FdToTdErrorV1::NonFiniteCalculation)
}

fn norm_v1(values: &[f64]) -> f64 {
    values.iter().map(|value| value * value).sum::<f64>().sqrt()
}

fn db_ratio_v1(numerator: f64, denominator: f64) -> f64 {
    if numerator == 0.0 {
        f64::NEG_INFINITY
    } else if denominator == 0.0 {
        f64::INFINITY
    } else {
        20.0 * (numerator / denominator).log10()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn reference_linear_interp_extrap(x: &[f64], y: &[f64], targets: &[f64]) -> Vec<f64> {
        targets
            .iter()
            .map(|target| {
                let upper = x
                    .partition_point(|value| *value <= *target)
                    .clamp(1, x.len() - 1);
                let lower = upper - 1;
                let fraction = (*target - x[lower]) / (x[upper] - x[lower]);
                y[lower] + fraction * (y[upper] - y[lower])
            })
            .collect()
    }

    fn trace(count: usize) -> (Vec<Complex64>, Vec<f64>) {
        let frequencies = (0..count)
            .map(|index| index as f64 * 1.0e9)
            .collect::<Vec<_>>();
        let values = frequencies
            .iter()
            .map(|frequency| Complex64::try_new((-(frequency / 8.0e10)).exp(), 0.0).unwrap())
            .collect::<Vec<_>>();
        (values, frequencies)
    }

    #[test]
    fn converts_without_s_parameter_fit_and_builds_time_axis() {
        let (values, frequencies) = trace(64);
        let options = FdToTdOptionsV1 {
            sample_dt_s: 1.0e-12,
            ..Default::default()
        };
        let result = s21_to_impulse_dc_v1(&values, &frequencies, &options).expect("impulse");
        assert!(!result.voltage.is_empty());
        assert_eq!(result.voltage.len(), result.time_s.len());
        assert!(result.time_s.windows(2).all(|pair| pair[1] > pair[0]));
    }

    #[test]
    fn monotonic_interpolation_preserves_reference_bits_and_unordered_fallback() {
        let x = vec![-1.0, 0.0, 0.25, 1.0, 2.5];
        let y = vec![4.0, -1.0, 0.5, 3.0, -2.0];
        for targets in [
            vec![-2.0, -1.0, -0.5, 0.0, 0.25, 0.75, 1.0, 2.5, 3.0],
            vec![1.0, -0.5, 2.5, 0.25],
        ] {
            let expected = reference_linear_interp_extrap(&x, &y, &targets);
            let actual = linear_interp_extrap_v1(&x, &y, &targets).expect("interpolation");
            assert_eq!(actual.len(), expected.len());
            for (actual, expected) in actual.iter().zip(expected) {
                assert_eq!(actual.to_bits(), expected.to_bits());
            }
        }
    }

    #[test]
    fn supports_upstream_magnitude_and_phase_policy_names() {
        let (values, frequencies) = trace(64);
        for magnitude_policy in [
            "linear_trend_to_DC",
            "linear_trend_to_DC_log_trend_to_inf",
            "trend_to_DC",
            "extrap_to_DC_or_zero",
            "extrap_to_DC",
            "old",
        ] {
            for phase_policy in ["old", "zero_DC", "interp_to_DC", "interp_and_shift_to_DC"] {
                let options = FdToTdOptionsV1 {
                    magnitude_policy: magnitude_policy.to_owned(),
                    phase_policy: phase_policy.to_owned(),
                    debug: true,
                    ..Default::default()
                };
                let result = s21_to_impulse_dc_v1(&values, &frequencies, &options);
                assert!(
                    result.is_ok(),
                    "{magnitude_policy}/{phase_policy}: {result:?}"
                );
            }
        }
    }

    #[test]
    fn rejects_anti_causal_trace_unless_debug_is_enabled() {
        let frequencies = (0..64)
            .map(|index| index as f64 * 1.0e9)
            .collect::<Vec<_>>();
        let values = frequencies
            .iter()
            .map(|frequency| {
                let phase = frequency / 1.0e10;
                Complex64::try_new(phase.cos(), phase.sin()).unwrap()
            })
            .collect::<Vec<_>>();
        let options = FdToTdOptionsV1::default();
        assert!(matches!(
            s21_to_impulse_dc_v1(&values, &frequencies, &options),
            Err(FdToTdErrorV1::InvalidInput(_))
        ));
        assert!(has_positive_unwrapped_phase_slope_v1(&values).expect("phase slope"));
    }

    #[test]
    fn phase_slope_guard_unwraps_boundaries_and_keeps_zero_non_positive() {
        let wrapped_negative = [-3.0, 3.0, 2.8]
            .into_iter()
            .map(|phase: f64| Complex64::try_new(phase.cos(), phase.sin()).expect("finite"))
            .collect::<Vec<_>>();
        assert!(!has_positive_unwrapped_phase_slope_v1(&wrapped_negative).expect("negative"));

        let zero = [0.5, 0.5, 0.5]
            .into_iter()
            .map(|phase: f64| Complex64::try_new(phase.cos(), phase.sin()).expect("finite"))
            .collect::<Vec<_>>();
        assert!(!has_positive_unwrapped_phase_slope_v1(&zero).expect("zero"));
    }

    #[test]
    fn extrap_cubic_phase_policy_accepts_the_source_51_point_tail_window() {
        // The source's ``group_delay[-51:]`` slice is 50 samples when the
        // input has exactly 51 frequencies.  Keep this boundary executable:
        // a direct Rust range ``len - 51`` would underflow here.
        let frequencies = (1..=51)
            .map(|index| index as f64 * 1.0e9)
            .collect::<Vec<_>>();
        let values = frequencies
            .iter()
            .map(|frequency| {
                let phase = -*frequency / 2.0e10;
                Complex64::try_new(0.8 * phase.cos(), 0.8 * phase.sin()).unwrap()
            })
            .collect::<Vec<_>>();
        let options = FdToTdOptionsV1 {
            sample_dt_s: 5.0e-12,
            magnitude_policy: "old".to_owned(),
            phase_policy: "extrap_cubic_to_dc_linear_to_inf".to_owned(),
            debug: true,
            ..Default::default()
        };
        let result = s21_to_impulse_dc_v1(&values, &frequencies, &options).expect("phase tail");
        assert!(!result.voltage.is_empty());
        assert_eq!(result.voltage.len(), result.time_s.len());
    }

    #[test]
    fn causality_and_rectangular_pulse_are_bounded() {
        let (values, frequencies) = trace(64);
        let options = FdToTdOptionsV1 {
            enforce_causality: true,
            max_iterations: 64,
            ..Default::default()
        };
        let result = s21_to_impulse_dc_v1(&values, &frequencies, &options).expect("causal impulse");
        let pulse = rectangular_pulse_response_fd_v1(&result.voltage, 4).expect("pulse");
        assert_eq!(pulse.len(), result.voltage.len());
        assert!(result.causality_iterations > 0);
    }
}
