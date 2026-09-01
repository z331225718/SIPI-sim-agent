//! C2M candidate vertical-eye primitive.
//!
//! Ported from agent-com src/agent_com/metrics/c2m.py (MIT source,
//! P5-04r): calculate_c2m_vertical_eye and its private helper chain
//! (resampling, DFE cancellation, phase-shifted residual, per-PAM
//! signal PDF data, histogram-weighted vertical-eye reduction). The
//! final full-contour public eye and the equalizer candidate/loop
//! remain separate scopes.

use crate::dfe_v1::clip_dfe_v1;
use crate::discrete_pdf_v1::{
    DiscretePdfV1, PdfErrorV1, convolve_c2m_accelerated_v1, normal_pdf_v1,
};
use crate::sampled_signal_pdf_v1::sampled_signal_pdf_owned_v1;
use rayon::prelude::*;
use std::cell::RefCell;
use std::sync::OnceLock;
use std::time::{Duration, Instant};

/// Explicit scope policy of the C2M vertical-eye primitive.
pub const C2M_EYE_POLICY_V1: &str = "sipi.p5-04r.c2m-vertical-eye.v1.signal-pdf-reduction";

#[derive(Clone, Copy, Debug, Default)]
pub(crate) struct C2mPerformanceSnapshotV1 {
    pub call_count: usize,
    pub elapsed: Duration,
    pub residual_preparation: Duration,
    pub phase_pdf: Duration,
    pub final_reduction: Duration,
}

thread_local! {
    static C2M_PERFORMANCE_PROFILE_V1: RefCell<C2mPerformanceSnapshotV1> = RefCell::new(C2mPerformanceSnapshotV1::default());
}

fn performance_trace_enabled_v1() -> bool {
    static ENABLED: OnceLock<bool> = OnceLock::new();
    *ENABLED.get_or_init(|| std::env::var_os("SIPI_COM_PERFORMANCE_TRACE_DIR").is_some())
}

fn record_c2m_timing_v1(update: impl FnOnce(&mut C2mPerformanceSnapshotV1)) {
    if performance_trace_enabled_v1() {
        C2M_PERFORMANCE_PROFILE_V1.with_borrow_mut(update);
    }
}

pub(crate) fn reset_c2m_performance_snapshot_v1() {
    if performance_trace_enabled_v1() {
        C2M_PERFORMANCE_PROFILE_V1.set(C2mPerformanceSnapshotV1::default());
    }
}

pub(crate) fn c2m_performance_snapshot_v1() -> C2mPerformanceSnapshotV1 {
    C2M_PERFORMANCE_PROFILE_V1.with_borrow(|profile| *profile)
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum C2mEyeErrorV1 {
    InvalidControls,
    PdfMismatch,
    ToRangeWindowExceedsUi,
    InterpRange,
    DfeSpan,
    ZeroCursor,
    DfeWindow,
    PulseShort,
    BerRange,
    PhaseSelection,
}

impl From<PdfErrorV1> for C2mEyeErrorV1 {
    fn from(_: PdfErrorV1) -> Self {
        C2mEyeErrorV1::InvalidControls
    }
}

fn matlab_round(value: f64) -> i64 {
    if value >= 0.0 {
        (value + 0.5).floor() as i64
    } else {
        (value - 0.5).ceil() as i64
    }
}

fn center_of_ui(samples_per_ui: usize) -> usize {
    samples_per_ui / 2
}

fn matlab_colon(start: f64, step: f64, stop: f64) -> Vec<f64> {
    if step == 0.0 || (stop - start) * step < 0.0 {
        return Vec::new();
    }
    let count = (((stop - start) / step + 1e-12).floor() + 1.0) as usize;
    (0..count).map(|i| start + step * i as f64).collect()
}

fn interp1_linear(x: &[f64], values: &[f64], query: &[f64]) -> Vec<f64> {
    debug_assert_eq!(x.len(), values.len());
    debug_assert!(x.len() >= 2);
    debug_assert!(x.windows(2).all(|pair| pair[0] < pair[1]));
    // `new_time` is constructed from two MATLAB-colon ranges and is ordered.
    // Advancing from the previous bracket avoids restarting a linear scan for
    // every resampled point in the C2M search hot path.
    let mut result = Vec::with_capacity(query.len());
    let mut idx = 0usize;
    for &q in query {
        if q < x[0] || q > x[x.len() - 1] {
            result.push(f64::NAN);
            continue;
        }
        if q == x[x.len() - 1] {
            result.push(values[x.len() - 1]);
            continue;
        }
        while idx + 1 < x.len() && x[idx + 1] <= q {
            idx += 1;
        }
        let x0 = x[idx];
        let x1 = x[idx + 1];
        let y0 = values[idx];
        let y1 = values[idx + 1];
        if x1 == x0 {
            result.push(y0);
        } else {
            let frac = (q - x0) / (x1 - x0);
            result.push(y0 + (y1 - y0) * frac);
        }
    }
    result
}

fn argmin_abs(values: &[f64]) -> usize {
    let mut best = 0usize;
    for (i, value) in values.iter().enumerate() {
        if value.abs() < values[best].abs() {
            best = i;
        }
    }
    best
}

struct C2mResidualJitter {
    residual_matrix: Vec<Vec<f64>>,
    cursor: usize,
    available_signal: Vec<f64>,
    jitter: Vec<Vec<f64>>,
}

fn c2m_residual_and_jitter(
    pulse: &[f64],
    cursor_index: usize,
    samples_per_ui: usize,
    samples_for_c2m: usize,
    levels: usize,
    r_lm_ohm: f64,
    dfe_tap_count: i64,
    dfe_max: &[f64],
    dfe_min: &[f64],
    dfe_step: f64,
    phase_indices: &[i64],
) -> Result<C2mResidualJitter, C2mEyeErrorV1> {
    let mut old_time: Vec<f64> = (0..pulse.len())
        .map(|i| i as f64 / samples_per_ui as f64)
        .collect();
    let shift_ref = old_time[cursor_index];
    for value in old_time.iter_mut() {
        *value -= shift_ref;
    }
    let old_min = old_time.iter().cloned().fold(f64::INFINITY, f64::min);
    let old_max = old_time.iter().cloned().fold(f64::NEG_INFINITY, f64::max);
    let mut left = matlab_colon(0.0, -1.0 / samples_for_c2m as f64, old_min);
    left.reverse();
    let mut right = matlab_colon(0.0, 1.0 / samples_for_c2m as f64, old_max);
    if !right.is_empty() {
        right.remove(0);
    }
    left.extend_from_slice(&right);
    let new_time = left;
    let raw = interp1_linear(&old_time, pulse, &new_time);
    if raw.iter().any(|v| !v.is_finite()) {
        return Err(C2mEyeErrorV1::InterpRange);
    }
    let cursor = argmin_abs(&new_time);
    let count: usize = if dfe_tap_count < 0 {
        return Err(C2mEyeErrorV1::InvalidControls);
    } else {
        dfe_tap_count as usize
    };
    if dfe_max.len() < count || dfe_min.len() < count {
        return Err(C2mEyeErrorV1::InvalidControls);
    }
    let tap_indices: Vec<usize> = (0..count)
        .map(|k| cursor + samples_for_c2m * (k + 1))
        .collect();
    if !tap_indices.is_empty() && tap_indices[tap_indices.len() - 1] >= raw.len() {
        return Err(C2mEyeErrorV1::DfeSpan);
    }
    let cursor_value = raw[cursor];
    if cursor_value == 0.0 {
        return Err(C2mEyeErrorV1::ZeroCursor);
    }
    let mut cancellation: Vec<f64> = tap_indices.iter().map(|&ti| raw[ti]).collect();
    if dfe_step != 0.0 {
        for value in cancellation.iter_mut() {
            let mag = (*value / (cursor_value * dfe_step)).abs().floor() * cursor_value * dfe_step;
            *value = mag * value.signum();
        }
    }
    let upper_scaled: Vec<f64> = dfe_max[..count].iter().map(|v| cursor_value * v).collect();
    let lower_scaled: Vec<f64> = dfe_min[..count].iter().map(|v| cursor_value * v).collect();
    let cancelled = clip_dfe_v1(&cancellation, &upper_scaled, &lower_scaled)
        .map_err(|_| C2mEyeErrorV1::InvalidControls)?;
    let mut residual = raw.clone();
    let half = center_of_ui(samples_for_c2m);
    let cancel_start = cursor - half + samples_for_c2m;
    let cancel_stop = cancel_start + count * samples_for_c2m;
    let cursor_start = cancel_start - samples_for_c2m;
    let cursor_stop = cursor_start + samples_for_c2m;
    if cursor_start >= residual.len() || cancel_stop > residual.len() {
        return Err(C2mEyeErrorV1::DfeWindow);
    }
    for (k, value) in cancelled.iter().enumerate() {
        let base = cancel_start + k * samples_for_c2m;
        for offset in 0..samples_for_c2m {
            residual[base + offset] -= *value;
        }
    }
    let available_signal: Vec<f64> = (cursor_start..cursor_stop)
        .map(|i| r_lm_ohm * raw[i] / (levels as f64 - 1.0))
        .collect();
    for value in residual[cursor_start..cursor_stop].iter_mut() {
        *value = 0.0;
    }
    let nui = (residual.len() as f64 / samples_for_c2m as f64 + 0.5).floor() as usize;
    let required = samples_for_c2m * (nui - 1);
    if nui < 3 || required > residual.len() {
        return Err(C2mEyeErrorV1::PulseShort);
    }
    let rows = samples_for_c2m;
    let cols = nui - 2;
    let build = |source: &[f64]| -> Vec<Vec<f64>> {
        let mut m = vec![vec![0.0f64; rows]; cols];
        for c in 0..cols {
            for r in 0..rows {
                m[c][r] = source[c * rows + r];
            }
        }
        m
    };
    let residual_matrix = build(&residual[samples_for_c2m..required]);
    let raw_matrix = build(&raw[samples_for_c2m..required]);
    let phase = cursor % samples_for_c2m;
    let shift = center_of_ui(samples_for_c2m) as i64 - phase as i64;
    let jitter = c2m_jitter_response(&raw_matrix, shift, samples_for_c2m, phase_indices)?;
    Ok(C2mResidualJitter {
        residual_matrix,
        cursor,
        available_signal,
        jitter,
    })
}

fn c2m_jitter_response(
    raw: &[Vec<f64>],
    shift: i64,
    samples_for_c2m: usize,
    phase_indices: &[i64],
) -> Result<Vec<Vec<f64>>, C2mEyeErrorV1> {
    let length = raw.len();
    if phase_indices
        .iter()
        .any(|&p| p < 0 || p as usize >= samples_for_c2m)
    {
        return Err(C2mEyeErrorV1::PhaseSelection);
    }
    let mut output = vec![vec![0.0f64; phase_indices.len()]; length];
    for (out_index, &phase) in phase_indices.iter().enumerate() {
        let hk = (((phase - shift) % samples_for_c2m as i64) + samples_for_c2m as i64)
            % samples_for_c2m as i64;
        if hk == 0 {
            for i in 0..length - 1 {
                output[i][out_index] =
                    (raw[i + 1][1] - raw[i][samples_for_c2m - 1]) * samples_for_c2m as f64 / 2.0;
            }
        } else if hk == samples_for_c2m as i64 - 1 {
            for i in 0..length - 1 {
                output[i][out_index] =
                    (raw[i + 1][0] - raw[i][samples_for_c2m - 2]) * samples_for_c2m as f64 / 2.0;
            }
        } else {
            for i in 0..length {
                output[i][out_index] = (raw[i][hk as usize + 1] - raw[i][hk as usize - 1])
                    * samples_for_c2m as f64
                    / 2.0;
            }
        }
    }
    Ok(output)
}

fn shift_residual_columns(
    residual: &[Vec<f64>],
    cursor: usize,
    samples_for_c2m: usize,
    phase_indices: &[i64],
) -> Result<Vec<Vec<f64>>, C2mEyeErrorV1> {
    if phase_indices.is_empty()
        || phase_indices
            .iter()
            .any(|&p| p < 0 || p as usize >= samples_for_c2m)
    {
        return Err(C2mEyeErrorV1::PhaseSelection);
    }
    let shift = center_of_ui(samples_for_c2m) as i64 - (cursor % samples_for_c2m) as i64;
    let rows = residual.len();
    let mut out = vec![vec![0.0f64; phase_indices.len()]; rows];
    for (j, &phase) in phase_indices.iter().enumerate() {
        let col = (((phase - shift) % samples_for_c2m as i64) + samples_for_c2m as i64)
            % samples_for_c2m as i64;
        for r in 0..rows {
            out[r][j] = residual[r][col as usize];
        }
    }
    Ok(out)
}

struct SignalLevelPdfData {
    probability: Vec<f64>,
    origins: Vec<i64>,
}

#[allow(clippy::too_many_arguments)]
fn phase_signal_level_pdf_data_v1(
    phase_position: usize,
    shifted_residual: &[Vec<f64>],
    jitter: &[Vec<f64>],
    available_signal: &[f64],
    phase_indices: &[i64],
    levels: usize,
    bin_size: f64,
    sigma_rj_s: f64,
    sigma_x: f64,
    sigma_n_v: f64,
    sigma_tx_v: f64,
    ber_q: f64,
    ne_noise_pdf: &DiscretePdfV1,
    cci_pdf: &DiscretePdfV1,
    amplitude_dd_v: f64,
    symbol_levels: &[f64],
) -> Result<SignalLevelPdfData, C2mEyeErrorV1> {
    let column: Vec<f64> = (0..shifted_residual.len())
        .map(|row| shifted_residual[row][phase_position])
        .collect();
    let self_pdf = sampled_signal_pdf_owned_v1(column, levels as u32, bin_size, true)
        .map_err(|_| C2mEyeErrorV1::InvalidControls)?;
    let jitter_norm: f64 = jitter
        .iter()
        .map(|row| row[phase_position] * row[phase_position])
        .sum::<f64>()
        .sqrt();
    let gaussian_std = ((sigma_rj_s * sigma_x * jitter_norm).powi(2)
        + sigma_n_v * sigma_n_v
        + sigma_tx_v * sigma_tx_v)
        .sqrt();
    let gaussian =
        normal_pdf_v1(gaussian_std, ber_q, bin_size).map_err(|_| C2mEyeErrorV1::InvalidControls)?;
    let dual_dirac_values: Vec<f64> = (0..jitter.len())
        .map(|row| amplitude_dd_v * jitter[row][phase_position])
        .collect();
    let dual_dirac = sampled_signal_pdf_owned_v1(dual_dirac_values, levels as u32, bin_size, true)
        .map_err(|_| C2mEyeErrorV1::InvalidControls)?;
    let gaussian = convolve_c2m_accelerated_v1(&gaussian, ne_noise_pdf)?;
    let noise = convolve_c2m_accelerated_v1(&gaussian, &dual_dirac)?;
    let phase_abs = phase_indices[phase_position];
    signal_level_pdf_data(
        &self_pdf,
        cci_pdf,
        &noise,
        available_signal[phase_abs as usize] * (levels as f64 - 1.0),
        symbol_levels,
    )
}

fn signal_level_pdf_data(
    self_pdf: &DiscretePdfV1,
    cci_pdf: &DiscretePdfV1,
    noise_pdf: &DiscretePdfV1,
    signal_scale_v: f64,
    symbol_levels: &[f64],
) -> Result<SignalLevelPdfData, C2mEyeErrorV1> {
    let shared = convolve_c2m_accelerated_v1(self_pdf, cci_pdf)?;
    let shared = convolve_c2m_accelerated_v1(&shared, noise_pdf)?;
    let bin_size = shared.bin_size();
    let total: f64 = shared.probability().iter().sum();
    let probability: Vec<f64> = shared.probability().iter().map(|v| v / total).collect();
    let mut origins = Vec::with_capacity(symbol_levels.len());
    for &symbol in symbol_levels {
        let shifted_origin = self_pdf.min_bin() as f64 + signal_scale_v * symbol / bin_size;
        let after_cci = matlab_round(shifted_origin + cci_pdf.min_bin() as f64);
        origins.push(matlab_round(after_cci as f64 + noise_pdf.min_bin() as f64));
    }
    Ok(SignalLevelPdfData {
        probability,
        origins,
    })
}

fn ber_contour(pdf: &DiscretePdfV1, spec_ber: f64) -> Result<(f64, f64), C2mEyeErrorV1> {
    if !(spec_ber > 0.0 && spec_ber < 1.0) {
        return Err(C2mEyeErrorV1::InvalidControls);
    }
    let n = pdf.probability().len();
    let p = pdf.probability();
    // Low-voltage tail crossing: first index (forward) where the forward
    // cumulative exceeds spec_ber.
    let mut running = 0.0f64;
    let mut bottom_index: Option<usize> = None;
    for i in 0..n {
        running += p[i];
        if running > spec_ber {
            bottom_index = Some(i);
            break;
        }
    }
    // High-voltage tail crossing: largest index whose right-tail cumulative
    // exceeds spec_ber (scan from the high end, mirroring cdf[::-1]).
    let mut running_high = 0.0f64;
    let mut top_index: Option<usize> = None;
    for i in (0..n).rev() {
        running_high += p[i];
        if running_high > spec_ber {
            top_index = Some(i);
            break;
        }
    }
    let (Some(bi), Some(ti)) = (bottom_index, top_index) else {
        return Err(C2mEyeErrorV1::BerRange);
    };
    Ok((pdf.x(ti), pdf.x(bi)))
}

fn histogram_weights(span: usize, window: &str, ql: f64) -> Result<Vec<f64>, C2mEyeErrorV1> {
    let len = 2 * span + 1;
    let x: Vec<f64> = (0..len).map(|i| i as f64 - span as f64).collect();
    let key = window.to_ascii_lowercase();
    match key.as_str() {
        "rectangle" => Ok(vec![1.0; len]),
        _ if span == 0 => Ok(vec![1.0]),
        "gaussian" | "norm" | "normal" | "guassian" => {
            let scale = span as f64 / ql;
            Ok(x.iter()
                .map(|&v| (-0.5 * (v / scale) * (v / scale)).exp())
                .collect())
        }
        "triangle" => Ok(x.iter().map(|&v| 1.0 - v.abs() / span as f64).collect()),
        "dual_rayleigh" => {
            let sigma = span as f64 / ql;
            let s2 = sigma * sigma;
            let terms: Vec<f64> = x
                .iter()
                .map(|&v| {
                    let a =
                        (v + span as f64) / s2 * (-0.5 * ((v + span as f64) / sigma).powi(2)).exp();
                    let b =
                        (v - span as f64) / s2 * (-0.5 * ((v - span as f64) / sigma).powi(2)).exp();
                    a - b
                })
                .collect();
            let max = terms.iter().cloned().fold(f64::NEG_INFINITY, f64::max);
            Ok(terms.iter().map(|v| v / max).collect())
        }
        _ => Err(C2mEyeErrorV1::InvalidControls),
    }
}

fn weighted_sum_shared_integer_axis(
    probabilities: &[&[f64]],
    origins: &[i64],
    weights: &[f64],
    bin_size: f64,
) -> Result<DiscretePdfV1, C2mEyeErrorV1> {
    if probabilities.is_empty()
        || probabilities.len() != origins.len()
        || probabilities.len() != weights.len()
    {
        return Err(C2mEyeErrorV1::PhaseSelection);
    }
    let mut origin = origins[0];
    let mut probability: Vec<f64> = probabilities[0].iter().map(|v| v * weights[0]).collect();
    for index in 1..probabilities.len() {
        let mut incoming: Vec<f64> = probabilities[index]
            .iter()
            .map(|v| v * weights[index])
            .collect();
        let shift = (origin - origins[index]).unsigned_abs() as usize;
        if origin < origins[index] {
            let mut padded = vec![0.0; shift];
            padded.extend_from_slice(&incoming);
            incoming = padded;
        } else {
            let mut padded = vec![0.0; shift];
            padded.extend_from_slice(&probability);
            probability = padded;
            origin = origins[index];
        }
        if probability.len() > incoming.len() {
            incoming.resize(probability.len(), 0.0);
        } else {
            probability.resize(incoming.len(), 0.0);
        }
        for i in 0..probability.len() {
            probability[i] += incoming[i];
        }
    }
    DiscretePdfV1::try_new(bin_size, origin, probability)
        .map_err(|_| C2mEyeErrorV1::InvalidControls)
}

fn vertical_eye_window_from_shared_levels(
    per_phase: &[SignalLevelPdfData],
    bin_size: f64,
    levels: usize,
    span: usize,
    histogram_window: &str,
    ql: f64,
    spec_ber: f64,
) -> Result<(Option<f64>, Option<f64>), C2mEyeErrorV1> {
    let weights = histogram_weights(span, histogram_window, ql)?;
    if per_phase.len() != weights.len() {
        return Err(C2mEyeErrorV1::PhaseSelection);
    }
    let probabilities: Vec<&[f64]> = per_phase.iter().map(|p| p.probability.as_slice()).collect();
    let mut contours = Vec::with_capacity(levels);
    for level in 0..levels {
        let origins: Vec<i64> = per_phase.iter().map(|p| p.origins[level]).collect();
        let aggregate =
            weighted_sum_shared_integer_axis(&probabilities, &origins, &weights, bin_size)?;
        contours.push(ber_contour(&aggregate, spec_ber)?);
    }
    let mut best = 0usize;
    let mut best_width = f64::INFINITY;
    for index in 0..levels - 1 {
        let width = contours[index + 1].1 - contours[index].0;
        if width < best_width {
            best_width = width;
            best = index;
        }
    }
    Ok((Some(contours[best + 1].1), Some(contours[best].0)))
}

/// `calculate_c2m_vertical_eye` port (candidate window only).
#[allow(clippy::too_many_arguments)]
pub fn calculate_c2m_vertical_eye_v1(
    pulse_response: &[f64],
    cursor_index: usize,
    samples_per_ui: usize,
    samples_for_c2m: usize,
    levels: usize,
    bin_size: f64,
    r_lm_ohm: f64,
    dfe_tap_count: i64,
    dfe_max: &[f64],
    dfe_min: &[f64],
    dfe_step: f64,
    sigma_rj_s: f64,
    sigma_x: f64,
    sigma_n_v: f64,
    sigma_tx_v: f64,
    ber_q: f64,
    ne_noise_pdf: &DiscretePdfV1,
    cci_pdf: &DiscretePdfV1,
    amplitude_dd_v: f64,
    spec_ber: f64,
    t_o_mui: f64,
    histogram_window: &str,
    ql: f64,
) -> Result<(Option<f64>, Option<f64>), C2mEyeErrorV1> {
    let started = performance_trace_enabled_v1().then(Instant::now);
    let result = calculate_c2m_vertical_eye_inner_v1(
        pulse_response,
        cursor_index,
        samples_per_ui,
        samples_for_c2m,
        levels,
        bin_size,
        r_lm_ohm,
        dfe_tap_count,
        dfe_max,
        dfe_min,
        dfe_step,
        sigma_rj_s,
        sigma_x,
        sigma_n_v,
        sigma_tx_v,
        ber_q,
        ne_noise_pdf,
        cci_pdf,
        amplitude_dd_v,
        spec_ber,
        t_o_mui,
        histogram_window,
        ql,
    );
    if let Some(started) = started {
        C2M_PERFORMANCE_PROFILE_V1.with_borrow_mut(|profile| {
            profile.call_count += 1;
            profile.elapsed += started.elapsed();
        });
    }
    result
}

#[allow(clippy::too_many_arguments)]
fn calculate_c2m_vertical_eye_inner_v1(
    pulse_response: &[f64],
    cursor_index: usize,
    samples_per_ui: usize,
    samples_for_c2m: usize,
    levels: usize,
    bin_size: f64,
    r_lm_ohm: f64,
    dfe_tap_count: i64,
    dfe_max: &[f64],
    dfe_min: &[f64],
    dfe_step: f64,
    sigma_rj_s: f64,
    sigma_x: f64,
    sigma_n_v: f64,
    sigma_tx_v: f64,
    ber_q: f64,
    ne_noise_pdf: &DiscretePdfV1,
    cci_pdf: &DiscretePdfV1,
    amplitude_dd_v: f64,
    spec_ber: f64,
    t_o_mui: f64,
    histogram_window: &str,
    ql: f64,
) -> Result<(Option<f64>, Option<f64>), C2mEyeErrorV1> {
    if t_o_mui == 0.0 {
        return Ok((None, None));
    }
    // This function is called for every viable TX-FFE candidate.  The
    // residual/jitter helpers are read-only, so copying the complete pulse
    // here only adds allocation and memory traffic to the search hot path.
    // Borrow it through the full calculation instead; the source semantics
    // are unchanged because no helper mutates the response.
    let pulse = pulse_response;
    if samples_per_ui < 1
        || samples_for_c2m < 2
        || levels < 2
        || bin_size <= 0.0
        || r_lm_ohm <= 0.0
        || !(spec_ber > 0.0 && spec_ber < 1.0)
        || cursor_index >= pulse.len()
        || dfe_tap_count < 0
        || dfe_step < 0.0
        || sigma_rj_s < 0.0
        || sigma_x < 0.0
        || sigma_n_v < 0.0
        || sigma_tx_v < 0.0
        || amplitude_dd_v < 0.0
        || ber_q < 0.0
        || ql <= 0.0
    {
        return Err(C2mEyeErrorV1::InvalidControls);
    }
    if ne_noise_pdf.bin_size() != bin_size || cci_pdf.bin_size() != bin_size {
        return Err(C2mEyeErrorV1::PdfMismatch);
    }
    let span = (t_o_mui / 1000.0 * samples_for_c2m as f64).floor() as usize;
    let center = center_of_ui(samples_for_c2m);
    if center < span || center + span >= samples_for_c2m {
        return Err(C2mEyeErrorV1::ToRangeWindowExceedsUi);
    }
    let start = center - span;
    let stop = center + span;
    let phase_indices: Vec<i64> = (start as i64..=stop as i64).collect();
    let residual_started = performance_trace_enabled_v1().then(Instant::now);
    let rj = c2m_residual_and_jitter(
        pulse,
        cursor_index,
        samples_per_ui,
        samples_for_c2m,
        levels,
        r_lm_ohm,
        dfe_tap_count,
        dfe_max,
        dfe_min,
        dfe_step,
        &phase_indices,
    )?;
    if let Some(started) = residual_started {
        record_c2m_timing_v1(|profile| profile.residual_preparation += started.elapsed());
    }
    let shifted_residual = shift_residual_columns(
        &rj.residual_matrix,
        rj.cursor,
        samples_for_c2m,
        &phase_indices,
    )?;
    let symbol_levels: Vec<f64> = (0..levels)
        .map(|i| 2.0 * i as f64 / (levels as f64 - 1.0) - 1.0)
        .collect();
    let phase_started = performance_trace_enabled_v1().then(Instant::now);
    // Each phase owns its sampled-signal/PDF work.  `collect` retains source
    // phase order for the reduction, so no arithmetic or winner ordering is
    // changed while the independent leaves use the configured Rayon pool.
    let per_phase: Vec<SignalLevelPdfData> = (0..phase_indices.len())
        .into_par_iter()
        .map(|phase_position| {
            phase_signal_level_pdf_data_v1(
                phase_position,
                &shifted_residual,
                &rj.jitter,
                &rj.available_signal,
                &phase_indices,
                levels,
                bin_size,
                sigma_rj_s,
                sigma_x,
                sigma_n_v,
                sigma_tx_v,
                ber_q,
                ne_noise_pdf,
                cci_pdf,
                amplitude_dd_v,
                &symbol_levels,
            )
        })
        .collect::<Result<_, _>>()?;
    if let Some(started) = phase_started {
        record_c2m_timing_v1(|profile| profile.phase_pdf += started.elapsed());
    }
    let reduction_started = performance_trace_enabled_v1().then(Instant::now);
    let result = vertical_eye_window_from_shared_levels(
        &per_phase,
        bin_size,
        levels,
        span,
        histogram_window,
        ql,
        spec_ber,
    );
    if let Some(started) = reduction_started {
        record_c2m_timing_v1(|profile| profile.final_reduction += started.elapsed());
    }
    result
}

#[cfg(test)]
mod tests {
    use super::*;

    fn reference_interp1_linear(x: &[f64], values: &[f64], query: &[f64]) -> Vec<f64> {
        query
            .iter()
            .map(|&q| {
                if q < x[0] || q > x[x.len() - 1] {
                    return f64::NAN;
                }
                if q == x[x.len() - 1] {
                    return values[x.len() - 1];
                }
                let mut index = 0usize;
                while index + 1 < x.len() && x[index + 1] <= q {
                    index += 1;
                }
                let x0 = x[index];
                let x1 = x[index + 1];
                let y0 = values[index];
                let y1 = values[index + 1];
                if x1 == x0 {
                    y0
                } else {
                    let fraction = (q - x0) / (x1 - x0);
                    y0 + (y1 - y0) * fraction
                }
            })
            .collect()
    }

    fn pulse() -> Vec<f64> {
        (0..240)
            .map(|i| {
                let t = i as f64;
                (0.5 * (-(t - 96.0) * (t - 96.0) / 500.0).exp() + 0.05).max(0.02)
            })
            .collect()
    }
    fn delta(bin_size: f64) -> DiscretePdfV1 {
        DiscretePdfV1::try_new(bin_size, 0, vec![1.0]).expect("delta")
    }
    #[test]
    fn center_and_round() {
        assert_eq!(center_of_ui(8), 4);
        assert_eq!(center_of_ui(7), 3);
        assert_eq!(matlab_round(0.5), 1);
        assert_eq!(matlab_round(-0.5), -1);
        assert_eq!(matlab_round(1.5), 2);
        assert_eq!(matlab_round(-1.5), -2);
    }

    #[test]
    fn monotonic_interpolation_preserves_reference_bits() {
        let x = vec![-2.0, -0.5, 0.0, 0.75, 3.0];
        let values = vec![1.5, -2.0, 0.25, 4.0, -3.5];
        let query = vec![
            -2.5, -2.0, -1.25, -0.5, -0.25, 0.0, 0.5, 0.75, 2.0, 3.0, 3.5,
        ];
        let expected = reference_interp1_linear(&x, &values, &query);
        let actual = interp1_linear(&x, &values, &query);
        assert_eq!(actual.len(), expected.len());
        for (actual, expected) in actual.iter().zip(expected) {
            assert_eq!(actual.to_bits(), expected.to_bits());
        }
    }
    #[test]
    fn t_o_zero_returns_none() {
        let cci = delta(1e-3);
        let ne = DiscretePdfV1::try_new(1e-3, 0, vec![1.0]).expect("ne");
        let (top, bottom) = calculate_c2m_vertical_eye_v1(
            &pulse(),
            100,
            10,
            8,
            4,
            1e-3,
            50.0,
            2,
            &[0.5, 0.5],
            &[-0.5, -0.5],
            1e-3,
            1e-4,
            0.03,
            1e-4,
            1e-4,
            3.7,
            &ne,
            &cci,
            0.1,
            1e-4,
            0.0,
            "rectangle",
            1.0,
        )
        .expect("calc");
        assert_eq!(top, None);
        assert_eq!(bottom, None);
    }
    #[test]
    fn policy_string_is_fixed() {
        assert_eq!(
            C2M_EYE_POLICY_V1,
            "sipi.p5-04r.c2m-vertical-eye.v1.signal-pdf-reduction"
        );
    }
    #[test]
    fn rejects_bad_controls() {
        let cci = delta(1e-3);
        let ne = DiscretePdfV1::try_new(1e-3, 0, vec![1.0]).expect("ne");
        let result = calculate_c2m_vertical_eye_v1(
            &pulse(),
            100,
            0,
            8,
            4,
            1e-3,
            50.0,
            2,
            &[0.5, 0.5],
            &[-0.5, -0.5],
            1e-3,
            1e-4,
            0.03,
            1e-4,
            1e-4,
            3.7,
            &ne,
            &cci,
            0.1,
            1e-4,
            0.5,
            "rectangle",
            1.0,
        );
        assert!(result.is_err());
    }
    #[test]
    fn histogram_weights_known() {
        let w = histogram_weights(2, "rectangle", 1.0).expect("rect");
        assert_eq!(w, vec![1.0; 5]);
        let tri = histogram_weights(2, "triangle", 1.0).expect("tri");
        assert_eq!(tri, vec![0.0, 0.5, 1.0, 0.5, 0.0]);
    }
    #[test]
    fn residual_and_jitter_shape() {
        let rj = c2m_residual_and_jitter(
            &pulse(),
            100,
            10,
            8,
            4,
            50.0,
            2,
            &[0.5, 0.5],
            &[-0.5, -0.5],
            1e-3,
            &[3, 4, 5],
        )
        .expect("rj");
        assert_eq!(rj.residual_matrix[0].len(), 8);
        assert_eq!(rj.jitter[0].len(), 3);
    }
}
