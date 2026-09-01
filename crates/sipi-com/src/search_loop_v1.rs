//! R480 non-MMSE no-RxFFE equalizer search loop (P5-04t).
//!
//! Ported from agent-com src/agent_com/equalization/search.py (MIT
//! source, P5-04t): the optimize_fom no-RxFFE branch over the TX FFE
//! grid and CTLE/high-pass pairs, plus its private support helpers
//! (validate, tx-grid values, peak window, shift matrix, local-search
//! skips, sweep order, sample offsets, tap numbers, anchored cursor,
//! rectangular pulse response). Candidate evaluation is reused from
//! candidate_eval_v1 (P5-04s).
#![allow(unused_imports)]

use std::collections::BTreeMap;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::time::{Duration, Instant};

use faer::linalg::matmul::matmul;
use faer::{Accum, Mat, Par};
use rayon::prelude::*;

use crate::c2m_eye_v1::{
    C2mEyeErrorV1, c2m_performance_snapshot_v1, reset_c2m_performance_snapshot_v1,
};
use crate::candidate_eval_v1::{
    CandidateEvalErrorV1, CandidateEvalOptionsV1, CandidateEvalParamsV1, NonMmseSearchResultV1,
    evaluate_candidate_v1,
};
use crate::candidate_helpers_v1::CandidateErrorV1;
use crate::com_chain_v1::{ComWinnerC2mContextV1, ComWinnerContextV1};
use crate::crosstalk_noise_v1::{
    XtalkChannelV1, XtalkErrorV1, XtalkParamsV1, crosstalk_noise_v1, prepare_crosstalk_noise_v1,
    tx_filter_magnitude_v1,
};
use crate::dfe_v1::DfeErrorV1;
use crate::discrete_pdf_v1::PdfErrorV1;
use crate::equalizer_frontend_v1::{EqualizerErrorV1, cursor_sample_index_v1};
use crate::receiver_noise_v1::{ReceiverNoiseOptionsV1, ReceiverNoiseParamsV1, receiver_noise_v1};
use crate::rx_ffe_v1::{RxFfeErrorV1, apply_rx_ffe_v1};
use crate::search_support_v1::{
    CtleParamsV1, SearchErrorV1, apply_ctle_candidate_v1, ctle_frequency_response_with_gdc_v1,
    high_pass_candidates_v1, qualified_ctle_pair_v1,
};
use crate::tx_ffe_v1::{TxFfeErrorV1, TxFfeGridV1, build_txffe_grid_v1};
use sipi_types::Complex64;

/// Explicit scope policy of the search loop stage.
pub const SEARCH_LOOP_POLICY_V1: &str = "sipi.p5-04t.search-loop.v1.nonmmse-no-rxffe";
const MAX_TX_CROSSTALK_MAGNITUDE_CACHE_ELEMENTS_V1: usize = 64 * 1024 * 1024;
static SEARCH_PROFILE_SEQUENCE_V1: AtomicUsize = AtomicUsize::new(0);

/// Opt-in, best-effort timing for the scalar equalizer path.  It is kept out
/// of the COM result surface so profiling cannot affect an acceptance payload.
struct SearchPerformanceTraceV1 {
    started: Instant,
    candidate_evaluation: Duration,
    candidate_evaluation_count: usize,
    c2m_evaluation: Duration,
    c2m_evaluation_count: usize,
    c2m_residual_preparation: Duration,
    c2m_phase_pdf: Duration,
    c2m_final_reduction: Duration,
    qualified_ctle_pairs: usize,
    tx_grid_candidates: usize,
}

impl SearchPerformanceTraceV1 {
    fn from_environment(tx_grid_candidates: usize) -> Option<Self> {
        std::env::var_os("SIPI_COM_PERFORMANCE_TRACE_DIR").map(|_| Self {
            started: Instant::now(),
            candidate_evaluation: Duration::ZERO,
            candidate_evaluation_count: 0,
            c2m_evaluation: Duration::ZERO,
            c2m_evaluation_count: 0,
            c2m_residual_preparation: Duration::ZERO,
            c2m_phase_pdf: Duration::ZERO,
            c2m_final_reduction: Duration::ZERO,
            qualified_ctle_pairs: 0,
            tx_grid_candidates,
        })
    }

    fn write(&self, package_case_index: usize) {
        let Some(root) = std::env::var_os("SIPI_COM_PERFORMANCE_TRACE_DIR") else {
            return;
        };
        let sequence = SEARCH_PROFILE_SEQUENCE_V1.fetch_add(1, Ordering::Relaxed);
        let payload = serde_json::json!({
            "schema": "sipi.com.search-performance-trace.v1",
            "package_case_index": package_case_index,
            "process_id": std::process::id(),
            "sequence": sequence,
            "elapsed_seconds": self.started.elapsed().as_secs_f64(),
            "candidate_evaluation_seconds": self.candidate_evaluation.as_secs_f64(),
            "candidate_evaluation_count": self.candidate_evaluation_count,
            "c2m_evaluation_seconds": self.c2m_evaluation.as_secs_f64(),
            "c2m_evaluation_count": self.c2m_evaluation_count,
            "c2m_residual_preparation_seconds": self.c2m_residual_preparation.as_secs_f64(),
            "c2m_phase_pdf_seconds": self.c2m_phase_pdf.as_secs_f64(),
            "c2m_final_reduction_seconds": self.c2m_final_reduction.as_secs_f64(),
            "qualified_ctle_pairs": self.qualified_ctle_pairs,
            "tx_grid_candidates": self.tx_grid_candidates,
        });
        let path = std::path::PathBuf::from(root).join(format!(
            "search-package-case-{package_case_index}-{}-{sequence}.json",
            std::process::id()
        ));
        let _ = std::fs::write(path, payload.to_string());
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum SearchLoopErrorV1 {
    Input,
    NoTxffe,
    NoCandidate,
    Anchor,
    Xtalk,
    ReceiverNoise,
    Dfe,
    Candidate,
    Search,
    Txffe,
    Pdf,
    C2mEye,
    Equalizer,
    UnsupportedBranch,
    CalibrationNoise,
    Invalid,
}

impl From<XtalkErrorV1> for SearchLoopErrorV1 {
    fn from(_: XtalkErrorV1) -> Self {
        SearchLoopErrorV1::Xtalk
    }
}
impl From<SearchErrorV1> for SearchLoopErrorV1 {
    fn from(_: SearchErrorV1) -> Self {
        SearchLoopErrorV1::Search
    }
}
impl From<DfeErrorV1> for SearchLoopErrorV1 {
    fn from(_: DfeErrorV1) -> Self {
        SearchLoopErrorV1::Dfe
    }
}
impl From<CandidateErrorV1> for SearchLoopErrorV1 {
    fn from(_: CandidateErrorV1) -> Self {
        SearchLoopErrorV1::Candidate
    }
}
impl From<CandidateEvalErrorV1> for SearchLoopErrorV1 {
    fn from(_: CandidateEvalErrorV1) -> Self {
        SearchLoopErrorV1::Candidate
    }
}
impl From<EqualizerErrorV1> for SearchLoopErrorV1 {
    fn from(_: EqualizerErrorV1) -> Self {
        SearchLoopErrorV1::Equalizer
    }
}
impl From<RxFfeErrorV1> for SearchLoopErrorV1 {
    fn from(_: RxFfeErrorV1) -> Self {
        SearchLoopErrorV1::Equalizer
    }
}
impl From<crate::receiver_noise_v1::NoiseErrorV1> for SearchLoopErrorV1 {
    fn from(_: crate::receiver_noise_v1::NoiseErrorV1) -> Self {
        SearchLoopErrorV1::ReceiverNoise
    }
}
impl From<TxFfeErrorV1> for SearchLoopErrorV1 {
    fn from(_: TxFfeErrorV1) -> Self {
        SearchLoopErrorV1::Txffe
    }
}
impl From<PdfErrorV1> for SearchLoopErrorV1 {
    fn from(_: PdfErrorV1) -> Self {
        SearchLoopErrorV1::Pdf
    }
}
impl From<C2mEyeErrorV1> for SearchLoopErrorV1 {
    fn from(_: C2mEyeErrorV1) -> Self {
        SearchLoopErrorV1::C2mEye
    }
}

/// Port of rectangular_pulse_response (zero-state filter of ones span).
pub fn rectangular_pulse_response_v1(
    impulse: &[f64],
    samples_per_ui: usize,
) -> Result<Vec<f64>, SearchLoopErrorV1> {
    if impulse.is_empty() || samples_per_ui < 1 {
        return Err(SearchLoopErrorV1::Invalid);
    }
    let n = impulse.len();
    let mut out = vec![0.0f64; n];
    let mut running = 0.0;
    for i in 0..n {
        running += impulse[i];
        if i >= samples_per_ui {
            running -= impulse[i - samples_per_ui];
        }
        out[i] = running;
    }
    Ok(out)
}

/// Port of _validate_supported_branch.
pub fn validate_supported_branch(options: &SearchLoopOptionsV1) -> Result<(), SearchLoopErrorV1> {
    let method = options.ffe_opt_method.to_uppercase();
    if (method != "FV-LMS" && method != "MMSE") || options.rxffe {
        return Err(SearchLoopErrorV1::UnsupportedBranch);
    }
    Ok(())
}

/// Port of _peak_window (TDMODE pulse vs FD impulse window).
pub fn peak_window(
    response: &[f64],
    samples_per_ui: usize,
    is_pulse: bool,
) -> Result<(usize, usize), SearchLoopErrorV1> {
    let values: Vec<f64> = if is_pulse {
        response.to_vec()
    } else {
        rectangular_pulse_response_v1(response, samples_per_ui)?
    };
    if values.is_empty() {
        return Err(SearchLoopErrorV1::Invalid);
    }
    let initial_peak = argmax_first(&values);
    let start = initial_peak.saturating_sub(20 * samples_per_ui);
    let stop = (initial_peak + 20 * samples_per_ui + 1).min(values.len());
    Ok((start, stop))
}

/// Port of _shift_matrix (column-stacked rolled pulse).
pub fn shift_matrix(
    pulse: &[f64],
    precursor_count: usize,
    samples_per_ui: usize,
    tap_count: usize,
) -> Vec<Vec<f64>> {
    let n = pulse.len();
    let mut out = Vec::with_capacity(tap_count);
    for index in 0..tap_count {
        let shift = (index as i64 - precursor_count as i64) * samples_per_ui as i64;
        let mut col = vec![0.0f64; n];
        for i in 0..n {
            let src = (i as i64 - shift).rem_euclid(n as i64) as usize;
            col[i] = pulse[src];
        }
        out.push(col);
    }
    out
}

/// Computes a whole eligible TX-FFE grid against one shifted pulse in one
/// bounded dense multiply.  This is deliberately restricted to the ordinary
/// full-grid, zero-offset sweep: local-search ordering and multi-offset
/// sweeps retain the scalar path below.
fn tx_ffe_sbr_matrix_v1(
    shifted: &[Vec<f64>],
    grid: &TxFfeGridV1,
    eligible_indices: &[usize],
) -> Mat<f64> {
    let samples = shifted[0].len();
    let taps = shifted.len();
    let shifted_matrix = Mat::from_fn(samples, taps, |sample, tap| shifted[tap][sample]);
    let tap_matrix = Mat::from_fn(taps, eligible_indices.len(), |tap, candidate| {
        grid.taps()[eligible_indices[candidate]][tap]
    });
    let mut output = Mat::zeros(samples, eligible_indices.len());
    // The output is sample-major by column, so each following candidate
    // evaluation borrows a contiguous waveform without another allocation.
    matmul(
        &mut output,
        Accum::Replace,
        &shifted_matrix,
        &tap_matrix,
        1.0,
        Par::rayon(0),
    );
    output
}

/// Evaluates one candidate from the batched ordinary-grid fast path.  Its
/// result is independent of the rest of the grid except for the supplied
/// rejection bound, so callers may evaluate stable contiguous chunks in
/// parallel and replay the strict first-winner reduction afterwards.
#[allow(clippy::too_many_arguments)]
fn evaluate_batched_grid_candidate_v1(
    waveform: &[f64],
    best_fom: Option<f64>,
    candidate_index: usize,
    ctle_index: usize,
    ctle_gain_db: f64,
    high_pass_index: usize,
    high_pass_gain_db: f64,
    grid: &TxFfeGridV1,
    samples_per_ui: usize,
    dfe_first_max: f64,
    cdr: &str,
    peak_start: usize,
    peak_stop: usize,
    ts_anchor: i64,
    sigma_n: f64,
    sigma_ne: f64,
    sigma_xt: f64,
    candidate_parameters: &CandidateEvalParamsV1,
    candidate_options: &CandidateEvalOptionsV1,
    package_case_index: usize,
) -> Result<Option<NonMmseSearchResultV1>, SearchLoopErrorV1> {
    let sample = cursor_sample_index_v1(
        waveform,
        samples_per_ui,
        dfe_first_max,
        cdr,
        peak_start,
        Some(peak_stop),
    )?;
    let Some(sample_cursor) = sample.cursor_index() else {
        return Ok(None);
    };
    if sample.no_zero_crossing() {
        return Ok(None);
    }
    let cursor_index = anchored_cursor(
        sample_cursor,
        sample.peak_index(),
        ts_anchor,
        waveform,
        samples_per_ui,
    )?;
    evaluate_candidate_v1(
        waveform,
        best_fom,
        cursor_index as usize,
        ctle_index as i64,
        ctle_gain_db,
        high_pass_index as i64,
        high_pass_gain_db,
        &grid.taps()[candidate_index],
        grid.precursor_count(),
        candidate_index as i64,
        &grid.source_indices()[candidate_index],
        sigma_n,
        sigma_ne,
        sigma_xt,
        candidate_parameters,
        candidate_options,
        package_case_index,
        0,
        false,
    )
    .map_err(SearchLoopErrorV1::from)
}

/// Port of _skip_local_search.
pub fn skip_local_search(
    current: &[i64],
    best: Option<&[i64]>,
    sweep: &[usize],
    local_search: f64,
) -> bool {
    let Some(best) = best else {
        return false;
    };
    if local_search <= 0.0 {
        return false;
    }
    for &index in sweep {
        let previous = if index == 0 { 1 } else { current[index - 1] };
        if previous > 1 && (current[index] - best[index]).abs() as f64 > local_search {
            return true;
        }
    }
    false
}

/// Port of _skip_high_pass_local_search.
pub fn skip_high_pass_local_search(
    ctle_index: usize,
    high_pass_index: i64,
    best_high_pass_index: Option<i64>,
    local_search: f64,
) -> bool {
    best_high_pass_index.is_some()
        && ctle_index > 0
        && local_search > 0.0
        && (high_pass_index - best_high_pass_index.unwrap()).abs() as f64 > local_search
}

/// Port of _sweep_order.
pub fn sweep_order(parameters: &SearchLoopParamsV1) -> Result<Vec<usize>, SearchLoopErrorV1> {
    let mut cm: Vec<i64> = Vec::new();
    let mut cp: Vec<i64> = Vec::new();
    for (name, values) in &parameters.tx_ffe_values {
        if let Some(num) = tap_number_from_name(name, "cm") {
            cm.push(num);
        } else if let Some(num) = tap_number_from_name(name, "cp") {
            cp.push(num);
        }
        let _ = values;
    }
    cm.sort_by(|a, b| b.cmp(a));
    cp.sort();
    let mut ordered_names = Vec::new();
    for num in &cm {
        ordered_names.push(format!("tx_ffe_cm{num}_values"));
    }
    for num in &cp {
        ordered_names.push(format!("tx_ffe_cp{num}_values"));
    }
    // variable = indices where size > 1
    let mut sizes: Vec<(usize, usize)> = Vec::new();
    for (name_index, name) in ordered_names.iter().enumerate() {
        if let Some(values) = parameters.tx_ffe_values.get(name)
            && values.len() > 1
        {
            sizes.push((name_index, values.len()));
        }
    }
    sizes.sort_by_key(|entry| std::cmp::Reverse(entry.1));
    let mut order = Vec::with_capacity(sizes.len());
    for (idx, _) in sizes {
        order.push(idx);
    }
    // stable sort by descending size; sizes already sorted by size; need stable original.
    Ok(order)
}

/// Parse tap number from a dynamic name (tx_ffe_cmN_values).
pub fn tap_number_from_name(name: &str, direction: &str) -> Option<i64> {
    let prefix = format!("tx_ffe_{direction}");
    let suffix = "_values";
    if !(name.starts_with(&prefix) && name.ends_with(suffix)) {
        return None;
    }
    let mid = &name[prefix.len()..name.len() - suffix.len()];
    mid.parse::<i64>().ok()
}

/// Port of _r480_sample_offsets (inclusive range, mode ordering).
pub fn r480_sample_offsets(
    ts_sample_adj_range: &[i64],
    ts_srch_mode: &str,
) -> Result<Vec<i64>, SearchLoopErrorV1> {
    let values = ts_sample_adj_range;
    if values.is_empty() {
        return Err(SearchLoopErrorV1::Invalid);
    }
    let range: Vec<i64> = if values.len() == 1 {
        vec![0, values[0]]
    } else {
        values.to_vec()
    };
    let (start, stop) = (range[0], range[1]);
    if stop < start {
        return Err(SearchLoopErrorV1::Invalid);
    }
    let offsets: Vec<i64> = (start..=stop).collect();
    match ts_srch_mode.to_ascii_lowercase().as_str() {
        "full-sweep" => Ok(offsets),
        "middle" => {
            let mut with_abs: Vec<(i64, i64)> = offsets.iter().map(|v| (v.abs(), *v)).collect();
            with_abs.sort_by_key(|(a, _)| *a);
            Ok(with_abs.into_iter().map(|(_, v)| v).collect())
        }
        _ => Err(SearchLoopErrorV1::Invalid),
    }
}

/// Port of _anchored_cursor.
pub fn anchored_cursor(
    cursor: i64,
    peak: i64,
    ts_anchor: i64,
    sbr: &[f64],
    samples_per_ui: usize,
) -> Result<i64, SearchLoopErrorV1> {
    if ts_anchor == 0 {
        return Ok(cursor);
    }
    if ts_anchor == 1 {
        return Ok(peak);
    }
    if ts_anchor == 2 {
        let peak_u = peak as usize;
        let start = peak_u.saturating_sub(samples_per_ui);
        let stop = peak_u + samples_per_ui + 1;
        if start >= sbr.len() || stop > sbr.len() || peak_u < 2 * samples_per_ui {
            return Err(SearchLoopErrorV1::Anchor);
        }
        let mut best_index = 0usize;
        let mut diff_ref: f64;
        let mut best_diff = f64::NEG_INFINITY;
        for (i, &value) in sbr[start..stop].iter().enumerate() {
            let prev = sbr[peak_u - 2 * samples_per_ui + i];
            diff_ref = value - prev;
            if i == 0 || diff_ref > best_diff {
                best_diff = diff_ref;
                best_index = i;
            }
        }
        return Ok(peak_u as i64 - samples_per_ui as i64 + best_index as i64);
    }
    Err(SearchLoopErrorV1::Anchor)
}

fn argmax_first(values: &[f64]) -> usize {
    let mut best = 0usize;
    for i in 1..values.len() {
        if values[i] > values[best] {
            best = i;
        }
    }
    best
}

pub struct SearchLoopParamsV1 {
    pub samples_per_ui: usize,
    pub fb: f64,
    pub tx_ffe_values: BTreeMap<String, Vec<f64>>,
    pub tx_ffe_c0_min: f64,
    pub ts_anchor: i64,
    pub local_search: f64,
    pub ts_sample_adj_range: Vec<i64>,
    pub ctle_gdc_values: Vec<f64>,
    pub ctle_type: String,
    pub g_dc_hp_values: Vec<f64>,
    pub gdc_min: f64,
    pub gqual: Vec<Vec<f64>>,
    pub g2qual: Vec<f64>,
    pub dfe_first_max: f64,
    pub cdle_include_ctle: bool,
}

pub struct SearchLoopOptionsV1 {
    pub ffe_opt_method: String,
    pub rxffe: bool,
    pub cdr: String,
    pub ts_srch_mode: String,
    pub include_ctle: bool,
    pub local_search_enabled: bool,
}

/// Composite-search parameter surface (no-RxFFE branch).
pub struct SearchFullParamsV1 {
    pub samples_per_ui: usize,
    pub fb: f64,
    /// Integration limit used by the pinned r4.80 crosstalk consumer. It is
    /// intentionally distinct from the baud rate when the source resolves a
    /// separate `f2` control.
    pub f2: f64,
    pub tx_ffe_values: BTreeMap<String, Vec<f64>>,
    pub tx_ffe_c0_min: f64,
    pub ts_anchor: i64,
    pub local_search: f64,
    pub ts_sample_adj_range: Vec<i64>,
    pub include_ctle: bool,
    pub gdc_min: f64,
    pub gqual: Vec<Vec<f64>>,
    pub g2qual: Vec<f64>,
    pub dfe_first_max: f64,
    pub receiver_noise: ReceiverNoiseParamsV1,
    pub ctle: CtleParamsV1,
    pub candidate: CandidateEvalParamsV1,
}

/// Composite-search options (no-RxFFE branch).
pub struct SearchFullOptionsV1 {
    pub ffe_opt_method: String,
    pub rx_ffe_enabled: bool,
    pub ts_srch_mode: String,
    pub cdr: String,
    pub receiver: ReceiverNoiseOptionsV1,
    pub candidate: CandidateEvalOptionsV1,
}

/// Composite-search best result summary.
pub struct SearchLoopResultV1 {
    pub fom_db: f64,
    pub ctle_index: i64,
    pub high_pass_index: i64,
    pub tx_grid_index: i64,
    pub cursor_index: usize,
    pub sigma_tx_v: f64,
    /// Selected source-order SBR/pulse.  The caller must use this waveform
    /// for the final COM chain rather than publishing FOM alone.
    pub selected_pulse: Vec<f64>,
    pub selected_tx_taps: Vec<f64>,
}

/// Additive result surface for the workbook-aware route. The historical V1
/// result remains source-compatible.
#[derive(Clone, Debug)]
pub struct SearchLoopResultWithMetricsV1 {
    pub fom_db: f64,
    pub ctle_index: i64,
    /// CTLE gain selected by the same candidate as `ctle_index`.
    pub ctle_gain_db: f64,
    pub high_pass_index: i64,
    /// High-pass gain selected by the same candidate as `high_pass_index`.
    pub high_pass_gain_db: f64,
    pub tx_grid_index: i64,
    pub cursor_index: usize,
    pub sigma_tx_v: f64,
    pub selected_pulse: Vec<f64>,
    pub selected_tx_taps: Vec<f64>,
    pub available_signal_v: f64,
    pub sigma_n_v: f64,
    pub sigma_ne_v: f64,
    pub h_j: Vec<f64>,
    /// Sample timing adjustment selected by the winning candidate.
    pub itick: i64,
}

impl SearchLoopResultWithMetricsV1 {
    fn legacy(&self) -> SearchLoopResultV1 {
        SearchLoopResultV1 {
            fom_db: self.fom_db,
            ctle_index: self.ctle_index,
            high_pass_index: self.high_pass_index,
            tx_grid_index: self.tx_grid_index,
            cursor_index: self.cursor_index,
            sigma_tx_v: self.sigma_tx_v,
            selected_pulse: self.selected_pulse.clone(),
            selected_tx_taps: self.selected_tx_taps.clone(),
        }
    }
}

/// Opaque winner handoff for the additive COM consumer route.
///
/// The winner state cannot be constructed by request callers: it is created
/// only by the V2 search entrypoint and consumed by the typed COM execution
/// entrypoint. The historical V1 result remains a normal source-compatible
/// struct.
#[derive(Clone, Debug)]
pub struct SearchLoopResultWithWinnerV2 {
    result: SearchLoopResultWithMetricsV1,
    winner: ComWinnerContextV1,
    tx_ffe_precursor_count: usize,
    final_pulse: Vec<f64>,
}

impl SearchLoopResultWithWinnerV2 {
    pub fn result(&self) -> &SearchLoopResultWithMetricsV1 {
        &self.result
    }

    /// Selected DFE taps owned by the same winner consumed by the final COM
    /// chain. This exposes no winner construction or mutable context.
    pub fn selected_dfe_taps(&self) -> &[f64] {
        &self.winner.dfe_taps
    }

    pub fn selected_tx_ffe_precursor_count(&self) -> usize {
        self.tx_ffe_precursor_count
    }

    pub(crate) fn winner(&self) -> &ComWinnerContextV1 {
        &self.winner
    }

    pub(crate) fn final_pulse(&self) -> &[f64] {
        &self.final_pulse
    }
}

/// Port of search_r480_nonmmse_no_xtalk (no-RxFFE composite loop).
pub fn search_r480_nonmmse_no_xtalk_v1(
    unequalized_impulse: &[f64],
    frequency_hz: &[f64],
    noise_frequency_hz: &[f64],
    crosstalk_frequency_hz: &[f64],
    crosstalk: &[XtalkChannelV1],
    calibration_noise: fn(usize, usize, f64) -> f64,
    peak_window_pulse: Option<&[f64]>,
    td_crosstalk_outer_product: bool,
    ac_common_mode_transfers: &[Vec<Complex64>],
    package_case_index: usize,
    full: &SearchFullParamsV1,
    options: &SearchFullOptionsV1,
) -> Result<SearchLoopResultV1, SearchLoopErrorV1> {
    search_r480_nonmmse_no_xtalk_with_sigma_and_gdc_v1(
        unequalized_impulse,
        frequency_hz,
        noise_frequency_hz,
        crosstalk_frequency_hz,
        crosstalk,
        calibration_noise,
        None,
        peak_window_pulse,
        td_crosstalk_outer_product,
        ac_common_mode_transfers,
        package_case_index,
        &full.ctle.f_hp,
        full,
        options,
    )
    .map(|result| result.legacy())
}

/// Search variant used by calibration orchestration.  When supplied, the
/// per-sigma calibrated receiver noise replaces the source callback result
/// for every CTLE/high-pass candidate; the legacy wrapper above preserves the
/// source callback API for callers without an outer calibration loop.
pub fn search_r480_nonmmse_no_xtalk_with_sigma_v1(
    unequalized_impulse: &[f64],
    frequency_hz: &[f64],
    noise_frequency_hz: &[f64],
    crosstalk_frequency_hz: &[f64],
    crosstalk: &[XtalkChannelV1],
    calibration_noise: fn(usize, usize, f64) -> f64,
    calibration_sigma_ne_v: Option<f64>,
    peak_window_pulse: Option<&[f64]>,
    td_crosstalk_outer_product: bool,
    ac_common_mode_transfers: &[Vec<Complex64>],
    package_case_index: usize,
    full: &SearchFullParamsV1,
    options: &SearchFullOptionsV1,
) -> Result<SearchLoopResultV1, SearchLoopErrorV1> {
    search_r480_nonmmse_no_xtalk_with_sigma_and_gdc_v1(
        unequalized_impulse,
        frequency_hz,
        noise_frequency_hz,
        crosstalk_frequency_hz,
        crosstalk,
        calibration_noise,
        calibration_sigma_ne_v,
        peak_window_pulse,
        td_crosstalk_outer_product,
        ac_common_mode_transfers,
        package_case_index,
        &full.ctle.f_hp,
        full,
        options,
    )
    .map(|result| result.legacy())
}

/// Workbook-aware search entrypoint with an explicit CTLE high-pass gain
/// vector.  Keeping it additive avoids changing the V1 parameter/result
/// structs used by the historical Python crosscheck runners.
pub fn search_r480_nonmmse_no_xtalk_with_sigma_and_gdc_v1(
    unequalized_impulse: &[f64],
    frequency_hz: &[f64],
    noise_frequency_hz: &[f64],
    crosstalk_frequency_hz: &[f64],
    crosstalk: &[XtalkChannelV1],
    calibration_noise: fn(usize, usize, f64) -> f64,
    calibration_sigma_ne_v: Option<f64>,
    peak_window_pulse: Option<&[f64]>,
    td_crosstalk_outer_product: bool,
    ac_common_mode_transfers: &[Vec<Complex64>],
    package_case_index: usize,
    g_dc_hp_values: &[f64],
    full: &SearchFullParamsV1,
    options: &SearchFullOptionsV1,
) -> Result<SearchLoopResultWithMetricsV1, SearchLoopErrorV1> {
    search_r480_nonmmse_no_xtalk_with_sigma_and_gdc_v2(
        unequalized_impulse,
        frequency_hz,
        noise_frequency_hz,
        crosstalk_frequency_hz,
        crosstalk,
        calibration_noise,
        calibration_sigma_ne_v,
        peak_window_pulse,
        td_crosstalk_outer_product,
        ac_common_mode_transfers,
        package_case_index,
        g_dc_hp_values,
        full,
        options,
    )
    .map(|result| result.result.clone())
}

/// Additive opaque winner entrypoint for the typed COM final chain.
pub fn search_r480_nonmmse_no_xtalk_with_sigma_and_gdc_v2(
    unequalized_impulse: &[f64],
    frequency_hz: &[f64],
    noise_frequency_hz: &[f64],
    crosstalk_frequency_hz: &[f64],
    crosstalk: &[XtalkChannelV1],
    calibration_noise: fn(usize, usize, f64) -> f64,
    calibration_sigma_ne_v: Option<f64>,
    peak_window_pulse: Option<&[f64]>,
    td_crosstalk_outer_product: bool,
    ac_common_mode_transfers: &[Vec<Complex64>],
    package_case_index: usize,
    g_dc_hp_values: &[f64],
    full: &SearchFullParamsV1,
    options: &SearchFullOptionsV1,
) -> Result<SearchLoopResultWithWinnerV2, SearchLoopErrorV1> {
    if unequalized_impulse.is_empty() || frequency_hz.len() < 2 {
        return Err(SearchLoopErrorV1::Input);
    }
    validate_supported_branch(&SearchLoopOptionsV1 {
        ffe_opt_method: options.ffe_opt_method.clone(),
        rxffe: options.rx_ffe_enabled,
        cdr: options.cdr.clone(),
        ts_srch_mode: options.ts_srch_mode.clone(),
        include_ctle: full.include_ctle,
        local_search_enabled: full.local_search > 0.0,
    })?;
    let spu = full.samples_per_ui;
    let grid = build_txffe_grid_v1(&full.tx_ffe_values, full.tx_ffe_c0_min, true)?;
    if grid.taps().is_empty() {
        return Err(SearchLoopErrorV1::NoTxffe);
    }
    let mut performance_trace = SearchPerformanceTraceV1::from_environment(grid.taps().len());
    if performance_trace.is_some() {
        reset_c2m_performance_snapshot_v1();
    }
    let (peak_start, peak_stop) = peak_window(
        peak_window_pulse.unwrap_or(unequalized_impulse),
        spu,
        peak_window_pulse.is_some(),
    )?;
    let tap_count = grid.taps()[0].len();
    // TX-FFE frequency magnitude is invariant across CTLE/high-pass pairs.
    // Bound this optional cache so unusually large caller grids keep the
    // established streaming evaluator rather than reserving host memory.
    let tx_crosstalk_magnitudes = (!td_crosstalk_outer_product && !crosstalk.is_empty())
        .then(|| {
            grid.taps()
                .len()
                .checked_mul(crosstalk_frequency_hz.len())
                .filter(|elements| *elements <= MAX_TX_CROSSTALK_MAGNITUDE_CACHE_ELEMENTS_V1)
                .map(|_| {
                    grid.taps()
                        .par_iter()
                        .map(|taps| tx_filter_magnitude_v1(crosstalk_frequency_hz, taps, full.fb))
                        .collect::<Vec<_>>()
                })
        })
        .flatten();
    let sample_offsets = r480_sample_offsets(&full.ts_sample_adj_range, &options.ts_srch_mode)?;
    let middle = options.ts_srch_mode.eq_ignore_ascii_case("middle");
    let gdc_values = &full.ctle.ctle_gdc_values;
    let sweep_params = SearchLoopParamsV1 {
        samples_per_ui: spu,
        fb: full.fb,
        tx_ffe_values: full.tx_ffe_values.clone(),
        tx_ffe_c0_min: full.tx_ffe_c0_min,
        ts_anchor: full.ts_anchor,
        local_search: full.local_search,
        ts_sample_adj_range: full.ts_sample_adj_range.clone(),
        ctle_gdc_values: full.ctle.ctle_gdc_values.clone(),
        ctle_type: full.ctle.ctle_type.clone(),
        g_dc_hp_values: g_dc_hp_values.to_vec(),
        gdc_min: full.gdc_min,
        gqual: full.gqual.clone(),
        g2qual: full.g2qual.clone(),
        dfe_first_max: full.dfe_first_max,
        cdle_include_ctle: full.include_ctle,
    };
    let sweep = sweep_order(&sweep_params)?;
    let mut best_fom: Option<f64> = None;
    let mut best_result: Option<SearchLoopResultWithWinnerV2> = None;
    let mut best_indices: Option<Vec<i64>> = None;
    let mut best_high_pass: Option<i64> = None;

    for ctle_index in 0..gdc_values.len() {
        let ctle_gain_db = gdc_values[ctle_index];
        let hp_candidates = high_pass_candidates_v1(&full.ctle.ctle_type, g_dc_hp_values)?;
        for (high_pass_index, high_pass_gain_db) in hp_candidates {
            if !qualified_ctle_pair_v1(
                &full.ctle.ctle_type,
                g_dc_hp_values,
                gdc_values,
                ctle_index,
                high_pass_index,
                full.gdc_min,
                &full.gqual,
                &full.g2qual,
            )? {
                continue;
            }
            if let Some(trace) = performance_trace.as_mut() {
                trace.qualified_ctle_pairs += 1;
            }
            if skip_high_pass_local_search(
                ctle_index,
                high_pass_index as i64,
                best_high_pass,
                full.local_search,
            ) {
                continue;
            }
            let sigma_n = receiver_noise_v1(
                noise_frequency_hz,
                ctle_index,
                high_pass_index,
                high_pass_gain_db,
                &full.receiver_noise,
                &options.receiver,
                ac_common_mode_transfers,
                package_case_index,
                None,
                None,
                true,
            )?;
            let h_ctf = ctle_frequency_response_with_gdc_v1(
                frequency_hz,
                ctle_index,
                high_pass_index,
                high_pass_gain_db,
                g_dc_hp_values,
                &full.ctle,
            )?;
            let h_ctf_crosstalk = if crosstalk_frequency_hz.len() == frequency_hz.len() {
                h_ctf.clone()
            } else {
                ctle_frequency_response_with_gdc_v1(
                    crosstalk_frequency_hz,
                    ctle_index,
                    high_pass_index,
                    high_pass_gain_db,
                    g_dc_hp_values,
                    &full.ctle,
                )?
            };
            let xtalk_parameters = XtalkParamsV1 {
                fb: full.fb,
                f2: full.f2,
                sigma_x: full.candidate.sigma_x,
            };
            // The channel/CTLE side of the FD crosstalk integral is invariant
            // over TX-FFE candidates.  Prepare it only for this CTLE/HP pair;
            // TDMODE keeps its separately certified outer-product path.
            let prepared_crosstalk = (!td_crosstalk_outer_product)
                .then(|| {
                    prepare_crosstalk_noise_v1(
                        crosstalk_frequency_hz,
                        &h_ctf_crosstalk,
                        crosstalk,
                        &xtalk_parameters,
                        None,
                        None,
                    )
                })
                .transpose()?
                .flatten();
            let sigma_ne = calibration_sigma_ne_v.unwrap_or_else(|| {
                calibration_noise(ctle_index, high_pass_index, high_pass_gain_db)
            });
            let ctle_impulse = if full.include_ctle {
                apply_ctle_candidate_v1(
                    unequalized_impulse,
                    full.fb,
                    spu,
                    ctle_index,
                    ctle_gain_db,
                    high_pass_index,
                    high_pass_gain_db,
                    &full.ctle,
                )?
            } else {
                unequalized_impulse.to_vec()
            };
            let pulse = rectangular_pulse_response_v1(&ctle_impulse, spu)?;
            let shifted = shift_matrix(&pulse, grid.precursor_count(), spu, tap_count);
            let n_samples = shifted.iter().map(|col| col.len()).next().unwrap_or(0);
            // The broad, ordinary workbook sweep has neither local-search
            // dependency nor multiple sample offsets.  Keep its candidate
            // order but form all eligible SBRs with a SIMD/parallel GEMM;
            // the scalar path remains the semantic reference for the two
            // order-sensitive modes.
            let batched_indices =
                (full.local_search <= 0.0 && !middle && sample_offsets.len() == 1).then(|| {
                    (0..grid.taps().len())
                        .filter(|&index| grid.cursor()[index] >= full.tx_ffe_c0_min)
                        .collect::<Vec<_>>()
                });
            let batched_sbr = batched_indices
                .as_deref()
                .filter(|indices| !indices.is_empty())
                .map(|indices| tx_ffe_sbr_matrix_v1(&shifted, &grid, indices));
            if let (Some(indices), Some(sbr_matrix), Some(prepared)) = (
                batched_indices.as_deref(),
                batched_sbr.as_ref(),
                prepared_crosstalk.as_ref(),
            ) {
                // Each chunk computes a local strict winner from the same
                // incoming bound.  Reducing chunks back in source order with
                // the same strict `>` rule yields the scalar grid's winner,
                // while allowing the independent candidate work to occupy
                // the host cores.
                let chunk_winners: Result<Vec<_>, SearchLoopErrorV1> = indices
                    .par_chunks(64)
                    .enumerate()
                    .map(|(chunk_index, chunk)| {
                        let mut chunk_best = best_fom;
                        let mut winner = None;
                        for (offset, &candidate_index) in chunk.iter().enumerate() {
                            let taps = &grid.taps()[candidate_index];
                            let sigma_xt = tx_crosstalk_magnitudes
                                .as_ref()
                                .map(|magnitudes| {
                                    prepared
                                        .evaluate_with_tx_magnitude(&magnitudes[candidate_index])
                                })
                                .unwrap_or_else(|| prepared.evaluate(taps))?;
                            let candidate = evaluate_batched_grid_candidate_v1(
                                sbr_matrix.col_as_slice(chunk_index * 64 + offset),
                                chunk_best,
                                candidate_index,
                                ctle_index,
                                ctle_gain_db,
                                high_pass_index,
                                high_pass_gain_db,
                                &grid,
                                spu,
                                full.dfe_first_max,
                                &options.cdr,
                                peak_start,
                                peak_stop,
                                full.ts_anchor,
                                sigma_n,
                                sigma_ne,
                                sigma_xt,
                                &full.candidate,
                                &options.candidate,
                                package_case_index,
                            )?;
                            if let Some(candidate) = candidate
                                && (chunk_best.is_none() || candidate.fom_db > chunk_best.unwrap())
                            {
                                chunk_best = Some(candidate.fom_db);
                                winner = Some(candidate);
                            }
                        }
                        Ok(winner)
                    })
                    .collect();
                for candidate in chunk_winners?.into_iter().flatten() {
                    if best_fom.is_none() || candidate.fom_db > best_fom.unwrap() {
                        best_fom = Some(candidate.fom_db);
                        best_indices = Some(candidate.tx_source_indices.clone());
                        best_high_pass = Some(high_pass_index as i64);
                        best_result = Some(SearchLoopResultWithWinnerV2 {
                            result: SearchLoopResultWithMetricsV1 {
                                fom_db: candidate.fom_db,
                                ctle_index: ctle_index as i64,
                                ctle_gain_db: candidate.ctle_gain_db,
                                high_pass_index: high_pass_index as i64,
                                high_pass_gain_db: candidate.high_pass_gain_db,
                                tx_grid_index: candidate.tx_grid_index,
                                cursor_index: candidate.cursor_index,
                                sigma_tx_v: candidate.sigma_tx_v,
                                selected_pulse: candidate.sbr.clone(),
                                selected_tx_taps: candidate.tx_ffe_taps.clone(),
                                available_signal_v: candidate.available_signal_v,
                                sigma_n_v: candidate.sigma_n_v,
                                sigma_ne_v: candidate.sigma_ne_v,
                                h_j: candidate.h_j.clone(),
                                itick: candidate.itick,
                            },
                            winner: ComWinnerContextV1 {
                                cursor_index: candidate.cursor_index,
                                dfe_taps: candidate.dfe_taps.clone(),
                                dfe_max: candidate.dfe_max.clone(),
                                dfe_min: candidate.dfe_min.clone(),
                                dfe_step: full.candidate.dfe_delta,
                                floating_dfe: full.candidate.floating_dfe,
                                dfe_max_count: full
                                    .candidate
                                    .floating_dfe
                                    .then_some(candidate.dfe_max.len() as i64),
                                sigma_n_v: candidate.sigma_n_v,
                                c2m: (full.candidate.t_o != 0.0).then(|| ComWinnerC2mContextV1 {
                                    samples_for_c2m: full.candidate.samples_for_c2m,
                                    t_o_mui: full.candidate.t_o,
                                    histogram_window: options
                                        .candidate
                                        .histogram_window_weight
                                        .clone(),
                                    ql: full.candidate.ql,
                                }),
                            },
                            tx_ffe_precursor_count: grid.precursor_count(),
                            final_pulse: candidate.sbr,
                        });
                    }
                }
                continue;
            }
            // The candidate waveform is scratch space until a strict winner
            // is promoted by `evaluate_candidate_v1`.  Reuse it across the
            // TX-FFE grid so the search preserves order/ties without making
            // one full allocation per candidate.
            let mut sbr = vec![0.0f64; n_samples.max(shifted[0].len())];
            let candidate_count = batched_indices
                .as_ref()
                .map_or_else(|| grid.taps().len(), Vec::len);
            for candidate_position in 0..candidate_count {
                let candidate_index = batched_indices
                    .as_ref()
                    .map_or(candidate_position, |indices| indices[candidate_position]);
                let taps = &grid.taps()[candidate_index];
                if grid.cursor()[candidate_index] < full.tx_ffe_c0_min {
                    continue;
                }
                let current = &grid.source_indices()[candidate_index];
                if skip_local_search(current, best_indices.as_deref(), &sweep, full.local_search) {
                    continue;
                }
                let waveform = if let Some(batched_sbr) = batched_sbr.as_ref() {
                    batched_sbr.col_as_slice(candidate_position)
                } else {
                    sbr.fill(0.0);
                    for c in 0..tap_count {
                        let col = &shifted[c];
                        for r in 0..sbr.len() {
                            sbr[r] += col[r] * taps[c];
                        }
                    }
                    &sbr
                };
                let sample = cursor_sample_index_v1(
                    waveform,
                    spu,
                    full.dfe_first_max,
                    &options.cdr,
                    peak_start,
                    Some(peak_stop),
                )?;
                if sample.no_zero_crossing() || sample.cursor_index().is_none() {
                    continue;
                }
                let cursor_index = anchored_cursor(
                    sample.cursor_index().unwrap(),
                    sample.peak_index(),
                    full.ts_anchor,
                    waveform,
                    spu,
                )?;
                let sigma_xt = if let Some(prepared) = prepared_crosstalk.as_ref() {
                    tx_crosstalk_magnitudes
                        .as_ref()
                        .map(|magnitudes| {
                            prepared.evaluate_with_tx_magnitude(&magnitudes[candidate_index])
                        })
                        .unwrap_or_else(|| prepared.evaluate(taps))?
                } else {
                    crosstalk_noise_v1(
                        crosstalk_frequency_hz,
                        &h_ctf_crosstalk,
                        taps,
                        crosstalk,
                        &xtalk_parameters,
                        td_crosstalk_outer_product,
                        None,
                        None,
                    )?
                };
                let mut best_pos_fom = f64::NEG_INFINITY;
                let mut best_neg_fom = f64::NEG_INFINITY;
                let mut best_pos_tick: Option<i64> = None;
                let mut best_neg_tick: Option<i64> = None;
                for &itick in &sample_offsets {
                    if middle && full.local_search > 0.0 {
                        if itick >= 0
                            && best_pos_tick.is_some()
                            && (best_pos_tick.unwrap() - itick).abs() as f64 >= full.local_search
                        {
                            continue;
                        }
                        if itick <= 0
                            && best_neg_tick.is_some()
                            && (best_neg_tick.unwrap() - itick).abs() as f64 >= full.local_search
                        {
                            continue;
                        }
                    }
                    let candidate_started = performance_trace.as_ref().map(|_| Instant::now());
                    let candidate = evaluate_candidate_v1(
                        waveform,
                        best_fom,
                        (cursor_index + itick) as usize,
                        ctle_index as i64,
                        ctle_gain_db,
                        high_pass_index as i64,
                        high_pass_gain_db,
                        taps,
                        grid.precursor_count(),
                        candidate_index as i64,
                        current,
                        sigma_n,
                        sigma_ne,
                        sigma_xt,
                        &full.candidate,
                        &options.candidate,
                        package_case_index,
                        itick,
                        middle,
                    )?;
                    if let (Some(trace), Some(started)) =
                        (performance_trace.as_mut(), candidate_started)
                    {
                        trace.candidate_evaluation += started.elapsed();
                        trace.candidate_evaluation_count += 1;
                    }
                    if let Some(cand) = candidate {
                        if middle {
                            if itick >= 0 && cand.fom_db > best_pos_fom {
                                best_pos_fom = cand.fom_db;
                                best_pos_tick = Some(itick);
                            }
                            if itick <= 0 && cand.fom_db > best_neg_fom {
                                best_neg_fom = cand.fom_db;
                                best_neg_tick = Some(itick);
                            }
                        }
                        if best_fom.is_none() || cand.fom_db > best_fom.unwrap() {
                            best_fom = Some(cand.fom_db);
                            best_indices = Some(current.clone());
                            best_high_pass = Some(high_pass_index as i64);
                            best_result = Some(SearchLoopResultWithWinnerV2 {
                                result: SearchLoopResultWithMetricsV1 {
                                    fom_db: cand.fom_db,
                                    ctle_index: ctle_index as i64,
                                    ctle_gain_db: cand.ctle_gain_db,
                                    high_pass_index: high_pass_index as i64,
                                    high_pass_gain_db: cand.high_pass_gain_db,
                                    tx_grid_index: candidate_index as i64,
                                    cursor_index: cand.cursor_index,
                                    sigma_tx_v: cand.sigma_tx_v,
                                    selected_pulse: cand.sbr.clone(),
                                    selected_tx_taps: taps.clone(),
                                    available_signal_v: cand.available_signal_v,
                                    sigma_n_v: cand.sigma_n_v,
                                    sigma_ne_v: cand.sigma_ne_v,
                                    h_j: cand.h_j.clone(),
                                    itick: cand.itick,
                                },
                                winner: ComWinnerContextV1 {
                                    cursor_index: cand.cursor_index,
                                    dfe_taps: cand.dfe_taps.clone(),
                                    dfe_max: cand.dfe_max.clone(),
                                    dfe_min: cand.dfe_min.clone(),
                                    dfe_step: full.candidate.dfe_delta,
                                    floating_dfe: full.candidate.floating_dfe,
                                    dfe_max_count: full
                                        .candidate
                                        .floating_dfe
                                        .then_some(cand.dfe_max.len() as i64),
                                    sigma_n_v: cand.sigma_n_v,
                                    c2m: (full.candidate.t_o != 0.0).then(|| {
                                        ComWinnerC2mContextV1 {
                                            samples_for_c2m: full.candidate.samples_for_c2m,
                                            t_o_mui: full.candidate.t_o,
                                            histogram_window: options
                                                .candidate
                                                .histogram_window_weight
                                                .clone(),
                                            ql: full.candidate.ql,
                                        }
                                    }),
                                },
                                tx_ffe_precursor_count: grid.precursor_count(),
                                final_pulse: cand.sbr.clone(),
                            });
                        }
                    }
                }
            }
        }
    }
    let mut best = best_result.ok_or(SearchLoopErrorV1::NoCandidate)?;
    if full.candidate.t_o != 0.0
        && full.candidate.min_veo_test == 0.0
        && full.candidate.floating_dfe
    {
        let required = best.result.selected_pulse.len();
        if unequalized_impulse.len() > required {
            return Err(SearchLoopErrorV1::Input);
        }
        let mut padded = unequalized_impulse.to_vec();
        padded.resize(required, 0.0);
        let equalized = apply_ctle_candidate_v1(
            &padded,
            full.fb,
            spu,
            best.result.ctle_index as usize,
            best.result.ctle_gain_db,
            best.result.high_pass_index as usize,
            best.result.high_pass_gain_db,
            &full.ctle,
        )?;
        let pulse = rectangular_pulse_response_v1(&equalized, spu)?;
        best.final_pulse = apply_rx_ffe_v1(
            &best.result.selected_tx_taps,
            grid.precursor_count(),
            spu,
            &pulse,
        )?;
    }
    if let Some(trace) = performance_trace.as_mut() {
        let c2m = c2m_performance_snapshot_v1();
        trace.c2m_evaluation = c2m.elapsed;
        trace.c2m_evaluation_count = c2m.call_count;
        trace.c2m_residual_preparation = c2m.residual_preparation;
        trace.c2m_phase_pdf = c2m.phase_pdf;
        trace.c2m_final_reduction = c2m.final_reduction;
        trace.write(package_case_index);
    }
    Ok(best)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn winner_with_dfe(taps: Vec<f64>, floating_dfe: bool) -> SearchLoopResultWithWinnerV2 {
        let tap_count = taps.len();
        SearchLoopResultWithWinnerV2 {
            result: SearchLoopResultWithMetricsV1 {
                fom_db: 1.0,
                ctle_index: 0,
                ctle_gain_db: 2.5,
                high_pass_index: 0,
                high_pass_gain_db: -1.25,
                tx_grid_index: 0,
                cursor_index: 1,
                sigma_tx_v: 0.0,
                selected_pulse: vec![0.0, 1.0],
                selected_tx_taps: vec![1.0],
                available_signal_v: 1.0,
                sigma_n_v: 0.0,
                sigma_ne_v: 0.0,
                h_j: vec![0.0],
                itick: -2,
            },
            winner: ComWinnerContextV1 {
                cursor_index: 1,
                dfe_taps: taps,
                dfe_max: vec![0.5; tap_count],
                dfe_min: vec![-0.5; tap_count],
                dfe_step: 0.01,
                floating_dfe,
                dfe_max_count: floating_dfe.then_some(tap_count as i64),
                sigma_n_v: 0.0,
                c2m: None,
            },
            tx_ffe_precursor_count: 0,
            final_pulse: vec![0.0, 1.0, 0.0],
        }
    }

    #[test]
    fn selected_dfe_taps_are_read_from_fixed_and_floating_winners() {
        for (taps, floating) in [(vec![0.2, -0.1], false), (vec![0.3, 0.0], true)] {
            let result = winner_with_dfe(taps.clone(), floating);
            assert_eq!(result.selected_dfe_taps(), taps);
            assert_eq!(result.winner().dfe_taps, taps);
            assert_eq!(result.result().ctle_gain_db, 2.5);
            assert_eq!(result.result().high_pass_gain_db, -1.25);
            assert_eq!(result.result().itick, -2);
        }
    }

    #[test]
    fn historical_v1_result_shape_remains_exact() {
        let result = SearchLoopResultV1 {
            fom_db: 1.0,
            ctle_index: 2,
            high_pass_index: 3,
            tx_grid_index: 4,
            cursor_index: 5,
            sigma_tx_v: 0.1,
            selected_pulse: vec![0.0, 1.0],
            selected_tx_taps: vec![1.0],
        };
        let SearchLoopResultV1 {
            fom_db,
            ctle_index,
            high_pass_index,
            tx_grid_index,
            cursor_index,
            sigma_tx_v,
            selected_pulse,
            selected_tx_taps,
        } = result;
        assert_eq!(
            (
                fom_db,
                ctle_index,
                high_pass_index,
                tx_grid_index,
                cursor_index,
                sigma_tx_v,
                selected_pulse,
                selected_tx_taps,
            ),
            (1.0, 2, 3, 4, 5, 0.1, vec![0.0, 1.0], vec![1.0])
        );
    }

    #[test]
    fn policy_string_is_fixed() {
        assert_eq!(
            SEARCH_LOOP_POLICY_V1,
            "sipi.p5-04t.search-loop.v1.nonmmse-no-rxffe"
        );
    }

    #[test]
    fn rectangular_pulse_response_basic() {
        let out = rectangular_pulse_response_v1(&[1.0, 2.0, 3.0], 2).expect("rect");
        // cov([1,2,3], [1,1]) full = [1,3,5,3], truncated [:3] = [1,3,5]
        assert_eq!(out, vec![1.0, 3.0, 5.0]);
    }

    #[test]
    fn peak_window_matches() {
        let pulse: Vec<f64> = (0..400)
            .map(|i| {
                let t = i as f64;
                0.5 * (-((t - 160.0) * (t - 160.0) / 800.0)).exp()
            })
            .collect();
        let (start, stop) = peak_window(&pulse, 10, true).expect("peak");
        assert!(start <= 160 && stop >= 161);
        // is_pulse=true uses values directly; peak at 160, window [0, 160+200+1)
        assert_eq!(start, 0);
        assert_eq!(stop, 361);
    }

    #[test]
    fn shift_matrix_columns() {
        let pulse = vec![1.0, 2.0, 3.0, 4.0];
        let m = shift_matrix(&pulse, 1, 1, 3);
        assert_eq!(m.len(), 3);
        // roll by (0-1)*1 = -1: np.roll(pulse,-1) = [2,3,4,1]
        assert_eq!(m[0][0], 2.0);
        assert_eq!(m[0][3], 1.0);
    }

    #[test]
    fn batched_txffe_sbr_matches_scalar_columns() {
        let shifted = vec![
            vec![1.0, -2.0, 3.0, -4.0, 5.0],
            vec![0.5, 1.5, -2.5, 3.5, -4.5],
            vec![-1.0, 0.25, 0.75, -1.25, 1.5],
        ];
        let grid = TxFfeGridV1::try_new(
            vec![vec![0.1, -0.2], vec![0.3, -0.4]],
            vec![0.7, 0.6],
            vec![vec![0.1, 0.7, -0.2], vec![0.3, 0.6, -0.4]],
            vec![vec![0, 0], vec![0, 1]],
            1,
        )
        .expect("grid");
        let output = tx_ffe_sbr_matrix_v1(&shifted, &grid, &[1, 0]);
        for (column, &candidate) in [1usize, 0].iter().enumerate() {
            let expected: Vec<f64> = (0..shifted[0].len())
                .map(|sample| {
                    (0..shifted.len())
                        .map(|tap| shifted[tap][sample] * grid.taps()[candidate][tap])
                        .sum()
                })
                .collect();
            for (actual, expected) in output.col_as_slice(column).iter().zip(expected) {
                assert!((actual - expected).abs() <= 1e-14);
            }
        }
    }

    #[test]
    fn skip_local_search_heuristics() {
        // best None -> never skip
        assert!(!skip_local_search(&[1, 1, 1], None, &[0, 1], 4.0));
        // previous index (current[0] = 1) not > 1 -> no skip
        assert!(!skip_local_search(
            &[1, 3, 0],
            Some(&[1, 1, 1]),
            &[1, 2],
            1.0
        ));
        // previous == 2 (>1) and |3-1|>1 -> skip
        assert!(skip_local_search(&[2, 3, 0], Some(&[1, 1, 1]), &[1], 1.0));
    }

    #[test]
    fn sample_offsets_full_and_middle() {
        let full = r480_sample_offsets(&[-2, 2], "full-sweep").expect("full");
        assert_eq!(full, vec![-2, -1, 0, 1, 2]);
        let mid = r480_sample_offsets(&[-2, 2], "middle").expect("mid");
        // stable sort by abs: [0, -1, 1, -2, 2]
        assert_eq!(mid, vec![0, -1, 1, -2, 2]);
    }

    #[test]
    fn anchored_cursor_anchor_zero_and_one() {
        assert_eq!(anchored_cursor(10, 20, 0, &[0.0; 50], 10).expect("a0"), 10);
        assert_eq!(anchored_cursor(10, 20, 1, &[0.0; 50], 10).expect("a1"), 20);
    }

    #[test]
    fn validate_branch_ok_and_reject() {
        let opts = SearchLoopOptionsV1 {
            ffe_opt_method: "FV-LMS".into(),
            rxffe: false,
            cdr: "MM".into(),
            ts_srch_mode: "full-sweep".into(),
            include_ctle: true,
            local_search_enabled: false,
        };
        assert!(validate_supported_branch(&opts).is_ok());
        let bad = SearchLoopOptionsV1 {
            ffe_opt_method: "MMSE".into(),
            rxffe: true,
            cdr: "MM".into(),
            ts_srch_mode: "full-sweep".into(),
            include_ctle: true,
            local_search_enabled: false,
        };
        assert!(validate_supported_branch(&bad).is_err());
    }

    #[test]
    fn composite_loop_produces_result_on_pulse() {
        use crate::candidate_eval_v1::{CandidateEvalOptionsV1, CandidateEvalParamsV1};
        use crate::receiver_noise_v1::{ReceiverNoiseOptionsV1, ReceiverNoiseParamsV1};
        use crate::search_support_v1::CtleParamsV1;
        use std::collections::BTreeMap;
        let spu = 10usize;
        let n = 300usize;
        let mut imp = vec![0.0f64; n];
        for k in 0..(n - 5 * spu) {
            imp[5 * spu + k] = (-(k as f64) / 16.0).exp();
        }
        imp[5 * spu] = 1.0;
        let freq: Vec<f64> = (0..200).map(|i| i as f64 * 1e7).collect();
        let mut txv = BTreeMap::new();
        txv.insert("tx_ffe_cm1_values".to_string(), vec![0.3]);
        txv.insert("tx_ffe_c0_values".to_string(), vec![0.6, 0.8]);
        txv.insert("tx_ffe_cp1_values".to_string(), vec![-0.1]);
        let receiver = ReceiverNoiseParamsV1 {
            fb: 26.5625e9,
            btorder: 3,
            fb_bt_cutoff: 0.75,
            fb_bw_cutoff: 0.75,
            rc_start: 8e9,
            rc_end: 12e9,
            eta_0: 1e-3,
            accm_max_freq: 30e9,
            ac_cm_rms: vec![0.0],
            ctle_gdc_values: vec![6.0],
            ctle_fz: vec![10e9],
            ctle_fp1: vec![30e9],
            ctle_fp2: vec![40e9],
            ctle_type: "CTLE".into(),
            f_hp: vec![0.0],
            f_hp_z: vec![5e9],
            f_hp_p: vec![1e9],
        };
        let ctle = CtleParamsV1 {
            ctle_gdc_values: vec![6.0],
            ctle_fz: vec![10e9],
            ctle_fp1: vec![30e9],
            ctle_fp2: vec![40e9],
            ctle_type: "CTLE".into(),
            f_hp: vec![0.0],
            f_hp_z: vec![5e9],
            f_hp_p: vec![1e9],
        };
        let candidate = CandidateEvalParamsV1 {
            samples_per_ui: spu,
            r_lm: 50.0,
            levels: 4,
            sigma_x: 0.03,
            dfe_delta: 1e-3,
            n_tail_start: 0,
            b_float_rss_max: 0.0,
            a_dd: 0.1,
            sigma_rj: 1e-4,
            t_o: 0.0,
            min_veo_test: 0.0,
            noise_crest_factor: 0.0,
            spec_ber: 1e-4,
            samples_for_c2m: 8,
            ql: 1.0,
            floating_dfe: false,
            ndfe: 2,
            n_bmax: 2,
            n_bf: 1,
            n_bg: 1,
            bmaxg: 0.3,
            bmax: vec![0.5, 0.5],
            bmin: vec![-0.5, -0.5],
        };
        let full = SearchFullParamsV1 {
            samples_per_ui: spu,
            fb: 26.5625e9,
            f2: 26.5625e9,
            tx_ffe_values: txv,
            tx_ffe_c0_min: 0.2,
            ts_anchor: 0,
            local_search: 0.0,
            ts_sample_adj_range: vec![-1, 1],
            include_ctle: true,
            gdc_min: 0.0,
            gqual: vec![vec![0.0]],
            g2qual: vec![0.0],
            dfe_first_max: 0.5,
            receiver_noise: receiver,
            ctle,
            candidate,
        };
        let opts = SearchFullOptionsV1 {
            ffe_opt_method: "MMSE".into(),
            rx_ffe_enabled: false,
            ts_srch_mode: "full-sweep".into(),
            cdr: "MM".into(),
            receiver: ReceiverNoiseOptionsV1 {
                bessel_thomson: false,
                butterworth: false,
                raised_cosine: false,
                use_eta0_psd: false,
                wc_portz: false,
                pkg_len_select: vec![1],
            },
            candidate: CandidateEvalOptionsV1 {
                snr_txw_c0: false,
                wc_portz: false,
                tx_rd_sel: 1,
                pkg_len_select: vec![1],
                sndr: vec![30.0],
                limit_jitter_contrib_to_dfe_span: false,
                force_pdf_bin_size: false,
                bin_size: 1e-3,
                force_bbn_q_factor: false,
                bbn_q_factor: 0.0,
                histogram_window_weight: "rectangle".into(),
            },
        };
        let winner = search_r480_nonmmse_no_xtalk_with_sigma_and_gdc_v2(
            &imp,
            &freq,
            &freq,
            &freq,
            &[],
            |_, _, _| 0.0,
            None,
            None,
            false,
            &[],
            0,
            &[0.0],
            &full,
            &opts,
        )
        .expect("composite winner");
        let metrics = winner.result();
        assert_eq!(metrics.ctle_gain_db, 6.0);
        assert_eq!(metrics.high_pass_gain_db, 0.0);
        assert_eq!(metrics.itick, 1);
        assert_eq!(winner.final_pulse(), metrics.selected_pulse);

        let result = search_r480_nonmmse_no_xtalk_v1(
            &imp,
            &freq,
            &freq,
            &freq,
            &[],
            |_, _, _| 0.0,
            None,
            false,
            &[],
            0,
            &full,
            &opts,
        );
        let result = result.expect("composite result");
        assert!(result.fom_db > 0.0, "fom should be positive");

        assert!(
            (result.cursor_index as i64 - 56).abs() <= 1,
            "cursor near 56, got {}",
            result.cursor_index
        );
        // oracle returns fom=53.4266 on this scenario; assert tight agreement.
        assert!(
            (result.fom_db - 53.42661625274711).abs() < 1e-9,
            "fom {}, expected 53.42661625274711",
            result.fom_db
        );
    }
}
