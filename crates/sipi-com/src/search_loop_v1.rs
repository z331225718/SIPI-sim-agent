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

use crate::c2m_eye_v1::C2mEyeErrorV1;
use crate::candidate_eval_v1::{
    evaluate_candidate_v1, CandidateEvalErrorV1, CandidateEvalOptionsV1,
    CandidateEvalParamsV1, NonMmseSearchResultV1,
};
use crate::candidate_helpers_v1::CandidateErrorV1;
use crate::crosstalk_noise_v1::{crosstalk_noise_v1, XtalkChannelV1, XtalkErrorV1, XtalkParamsV1};
use crate::dfe_v1::DfeErrorV1;
use crate::discrete_pdf_v1::PdfErrorV1;
use crate::equalizer_frontend_v1::{cursor_sample_index_v1, EqualizerErrorV1};
use crate::receiver_noise_v1::{
    receiver_noise_v1, ReceiverNoiseOptionsV1, ReceiverNoiseParamsV1,
};
use crate::search_support_v1::{
    apply_ctle_candidate_v1, ctle_frequency_response_v1, high_pass_candidates_v1,
    qualified_ctle_pair_v1, CtleParamsV1, SearchErrorV1,
};
use crate::tx_ffe_v1::{build_txffe_grid_v1, TxFfeGridV1, TxFfeErrorV1};
use sipi_types::Complex64;

/// Explicit scope policy of the search loop stage.
pub const SEARCH_LOOP_POLICY_V1: &str = "sipi.p5-04t.search-loop.v1.nonmmse-no-rxffe";

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

impl From<XtalkErrorV1> for SearchLoopErrorV1 { fn from(_: XtalkErrorV1) -> Self { SearchLoopErrorV1::Xtalk } }
impl From<SearchErrorV1> for SearchLoopErrorV1 { fn from(_: SearchErrorV1) -> Self { SearchLoopErrorV1::Search } }
impl From<DfeErrorV1> for SearchLoopErrorV1 { fn from(_: DfeErrorV1) -> Self { SearchLoopErrorV1::Dfe } }
impl From<CandidateErrorV1> for SearchLoopErrorV1 { fn from(_: CandidateErrorV1) -> Self { SearchLoopErrorV1::Candidate } }
impl From<CandidateEvalErrorV1> for SearchLoopErrorV1 { fn from(_: CandidateEvalErrorV1) -> Self { SearchLoopErrorV1::Candidate } }
impl From<EqualizerErrorV1> for SearchLoopErrorV1 { fn from(_: EqualizerErrorV1) -> Self { SearchLoopErrorV1::Equalizer } }
impl From<crate::receiver_noise_v1::NoiseErrorV1> for SearchLoopErrorV1 { fn from(_: crate::receiver_noise_v1::NoiseErrorV1) -> Self { SearchLoopErrorV1::ReceiverNoise } }
impl From<TxFfeErrorV1> for SearchLoopErrorV1 { fn from(_: TxFfeErrorV1) -> Self { SearchLoopErrorV1::Txffe } }
impl From<PdfErrorV1> for SearchLoopErrorV1 { fn from(_: PdfErrorV1) -> Self { SearchLoopErrorV1::Pdf } }
impl From<C2mEyeErrorV1> for SearchLoopErrorV1 { fn from(_: C2mEyeErrorV1) -> Self { SearchLoopErrorV1::C2mEye } }

/// Port of rectangular_pulse_response (zero-state filter of ones span).
pub fn rectangular_pulse_response_v1(impulse: &[f64], samples_per_ui: usize) -> Result<Vec<f64>, SearchLoopErrorV1> {
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

/// Port of _tx_grid_values.
pub fn tx_grid_values(parameters: &SearchLoopParamsV1) -> Result<BTreeMap<String, Vec<f64>>, SearchLoopErrorV1> {
    // The product maps tx_ffe_*_values into a BTreeMap ahead of time; on the
    // full parameter surface this mirrors the source's name-prefix/suffix
    // scan. The caller provides tx_ffe_values; absence is a hard error here.
    if parameters.tx_ffe_values.is_empty() {
        return Err(SearchLoopErrorV1::NoTxffe);
    }
    Ok(parameters.tx_ffe_values.clone())
}

/// Port of _peak_window (TDMODE pulse vs FD impulse window).
pub fn peak_window(response: &[f64], samples_per_ui: usize, is_pulse: bool) -> Result<(usize, usize), SearchLoopErrorV1> {
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
pub fn shift_matrix(pulse: &[f64], precursor_count: usize, samples_per_ui: usize, tap_count: usize) -> Vec<Vec<f64>> {
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

/// Port of _skip_local_search.
pub fn skip_local_search(
    current: &[i64], best: Option<&[i64]>, sweep: &[usize], local_search: f64,
) -> bool {
    let Some(best) = best else { return false; };
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
    ctle_index: usize, high_pass_index: i64, best_high_pass_index: Option<i64>, local_search: f64,
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
        if let Some(values) = parameters.tx_ffe_values.get(name) {
            if values.len() > 1 {
                sizes.push((name_index, values.len()));
            }
        }
    }
    sizes.sort_by(|a, b| b.1.cmp(&a.1));
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
pub fn r480_sample_offsets(ts_sample_adj_range: &[i64], ts_srch_mode: &str) -> Result<Vec<i64>, SearchLoopErrorV1> {
    let values = ts_sample_adj_range;
    if values.is_empty() {
        return Err(SearchLoopErrorV1::Invalid);
    }
    let range: Vec<i64> = if values.len() == 1 { vec![0, values[0]] } else { values.to_vec() };
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
    cursor: i64, peak: i64, ts_anchor: i64, sbr: &[f64], samples_per_ui: usize,
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
    let (peak_start, peak_stop) = peak_window(
        peak_window_pulse.unwrap_or(unequalized_impulse),
        spu,
        peak_window_pulse.is_some(),
    )?;
    let tap_count = grid.taps()[0].len();
    let sample_offsets = r480_sample_offsets(&full.ts_sample_adj_range, &options.ts_srch_mode)?;
    let middle = options.ts_srch_mode.eq_ignore_ascii_case("middle");
    let gdc_values = &full.ctle.ctle_gdc_values;
    let sweep_params = SearchLoopParamsV1 {
        samples_per_ui: spu, fb: full.fb, tx_ffe_values: full.tx_ffe_values.clone(),
        tx_ffe_c0_min: full.tx_ffe_c0_min, ts_anchor: full.ts_anchor, local_search: full.local_search,
        ts_sample_adj_range: full.ts_sample_adj_range.clone(),
        ctle_gdc_values: full.ctle.ctle_gdc_values.clone(), ctle_type: full.ctle.ctle_type.clone(),
        g_dc_hp_values: full.ctle.f_hp.clone(), gdc_min: full.gdc_min, gqual: full.gqual.clone(),
        g2qual: full.g2qual.clone(), dfe_first_max: full.dfe_first_max, cdle_include_ctle: full.include_ctle,
    };
    let sweep = sweep_order(&sweep_params)?;
    let mut best_fom: Option<f64> = None;
    let mut best_result: Option<SearchLoopResultV1> = None;
    let mut best_indices: Option<Vec<i64>> = None;
    let mut best_high_pass: Option<i64> = None;

    for ctle_index in 0..gdc_values.len() {
        let ctle_gain_db = gdc_values[ctle_index];
        let hp_candidates = high_pass_candidates_v1(&full.ctle.ctle_type, &full.ctle.f_hp)?;
        for (high_pass_index, high_pass_gain_db) in hp_candidates {
            if !qualified_ctle_pair_v1(
                &full.ctle.ctle_type, &full.ctle.f_hp, gdc_values, ctle_index, high_pass_index,
                full.gdc_min, &full.gqual, &full.g2qual,
            )? { continue; }
            if skip_high_pass_local_search(ctle_index, high_pass_index as i64, best_high_pass, full.local_search) { continue; }
            let sigma_n = receiver_noise_v1(
                noise_frequency_hz, ctle_index, high_pass_index, high_pass_gain_db,
                &full.receiver_noise, &options.receiver, ac_common_mode_transfers,
                package_case_index, None, None, true,
            )?;
            let h_ctf = ctle_frequency_response_v1(
                frequency_hz, ctle_index, high_pass_index, high_pass_gain_db, &full.ctle,
            )?;
            let h_ctf_crosstalk = if crosstalk_frequency_hz.len() == frequency_hz.len() {
                h_ctf.clone()
            } else {
                ctle_frequency_response_v1(crosstalk_frequency_hz, ctle_index, high_pass_index, high_pass_gain_db, &full.ctle)?
            };
            let sigma_ne = calibration_noise(ctle_index, high_pass_index, high_pass_gain_db);
            let ctle_impulse = if full.include_ctle {
                apply_ctle_candidate_v1(unequalized_impulse, full.fb, spu, ctle_index, ctle_gain_db, high_pass_index, high_pass_gain_db, &full.ctle)?
            } else {
                unequalized_impulse.to_vec()
            };
            let pulse = rectangular_pulse_response_v1(&ctle_impulse, spu)?;
            let shifted = shift_matrix(&pulse, grid.precursor_count(), spu, tap_count);
            let n_samples = shifted.iter().map(|col| col.len()).next().unwrap_or(0);
            for candidate_index in 0..grid.taps().len() {
                let taps = &grid.taps()[candidate_index];
                if grid.cursor()[candidate_index] < full.tx_ffe_c0_min { continue; }
                let current = grid.source_indices()[candidate_index].clone();
                if skip_local_search(&current, best_indices.as_deref(), &sweep, full.local_search) { continue; }
                let mut sbr = vec![0.0f64; n_samples.max(shifted[0].len())];
                for c in 0..tap_count {
                    let col = &shifted[c];
                    for r in 0..sbr.len() {
                        sbr[r] += col[r] * taps[c];
                    }
                }
                let sample = cursor_sample_index_v1(&sbr, spu, full.dfe_first_max, &options.cdr, peak_start, Some(peak_stop))?;
                if sample.no_zero_crossing() || sample.cursor_index().is_none() { continue; }
                let cursor_index = anchored_cursor(sample.cursor_index().unwrap(), sample.peak_index(), full.ts_anchor, &sbr, spu)?;
                let sigma_xt = crosstalk_noise_v1(
                    crosstalk_frequency_hz, &h_ctf_crosstalk, taps, crosstalk,
                    &XtalkParamsV1 { fb: full.fb, f2: full.fb, sigma_x: full.candidate.sigma_x },
                    td_crosstalk_outer_product, None, None,
                )?;
                let mut best_pos_fom = f64::NEG_INFINITY;
                let mut best_neg_fom = f64::NEG_INFINITY;
                let mut best_pos_tick: Option<i64> = None;
                let mut best_neg_tick: Option<i64> = None;
                for &itick in &sample_offsets {
                    if middle && full.local_search > 0.0 {
                        if itick >= 0 && best_pos_tick.is_some() && (best_pos_tick.unwrap() - itick).abs() as f64 >= full.local_search { continue; }
                        if itick <= 0 && best_neg_tick.is_some() && (best_neg_tick.unwrap() - itick).abs() as f64 >= full.local_search { continue; }
                    }
                    let candidate = evaluate_candidate_v1(
                        &sbr, best_fom, (cursor_index + itick) as usize,
                        ctle_index as i64, ctle_gain_db, high_pass_index as i64, high_pass_gain_db,
                        taps, grid.precursor_count(), candidate_index as i64, &current,
                        sigma_n, sigma_ne, sigma_xt, &full.candidate, &options.candidate,
                        package_case_index, itick, middle,
                    )?;
                    if let Some(cand) = candidate {
                        if middle {
                            if itick >= 0 && cand.fom_db > best_pos_fom { best_pos_fom = cand.fom_db; best_pos_tick = Some(itick); }
                            if itick <= 0 && cand.fom_db > best_neg_fom { best_neg_fom = cand.fom_db; best_neg_tick = Some(itick); }
                        }
                        if best_fom.is_none() || cand.fom_db > best_fom.unwrap() {
                            best_fom = Some(cand.fom_db);
                            best_indices = Some(current.clone());
                            best_high_pass = Some(high_pass_index as i64);
                            best_result = Some(SearchLoopResultV1 {
                                fom_db: cand.fom_db, ctle_index: ctle_index as i64,
                                high_pass_index: high_pass_index as i64, tx_grid_index: candidate_index as i64,
                                cursor_index: cand.cursor_index, sigma_tx_v: cand.sigma_tx_v,
                            });
                        }
                    }
                }
            }
        }
    }
    best_result.ok_or(SearchLoopErrorV1::NoCandidate)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn policy_string_is_fixed() {
        assert_eq!(SEARCH_LOOP_POLICY_V1, "sipi.p5-04t.search-loop.v1.nonmmse-no-rxffe");
    }

    #[test]
    fn rectangular_pulse_response_basic() {
        let out = rectangular_pulse_response_v1(&[1.0, 2.0, 3.0], 2).expect("rect");
        // cov([1,2,3], [1,1]) full = [1,3,5,3], truncated [:3] = [1,3,5]
        assert_eq!(out, vec![1.0, 3.0, 5.0]);
    }

    #[test]
    fn peak_window_matches() {
        let pulse: Vec<f64> = (0..400).map(|i| { let t = i as f64; 0.5 * (-((t - 160.0) * (t - 160.0) / 800.0)).exp() }).collect();
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
    fn skip_local_search_heuristics() {
        // best None -> never skip
        assert!(!skip_local_search(&[1, 1, 1], None, &[0, 1], 4.0));
        // previous index (current[0] = 1) not > 1 -> no skip
        assert!(!skip_local_search(&[1, 3, 0], Some(&[1, 1, 1]), &[1, 2], 1.0));
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
        let opts = SearchLoopOptionsV1 { ffe_opt_method: "FV-LMS".into(), rxffe: false, cdr: "MM".into(), ts_srch_mode: "full-sweep".into(), include_ctle: true, local_search_enabled: false };
        assert!(validate_supported_branch(&opts).is_ok());
        let bad = SearchLoopOptionsV1 { ffe_opt_method: "MMSE".into(), rxffe: true, cdr: "MM".into(), ts_srch_mode: "full-sweep".into(), include_ctle: true, local_search_enabled: false };
        assert!(validate_supported_branch(&bad).is_err());
    }

    #[test]
    fn composite_loop_produces_result_on_pulse() {
        use std::collections::BTreeMap;
        use crate::receiver_noise_v1::{ReceiverNoiseParamsV1, ReceiverNoiseOptionsV1};
        use crate::search_support_v1::CtleParamsV1;
        use crate::candidate_eval_v1::{CandidateEvalParamsV1, CandidateEvalOptionsV1};
        let spu = 10usize; let n = 300usize;
        let mut imp = vec![0.0f64; n];
        for k in 0..(n - 5 * spu) { imp[5 * spu + k] = (-(k as f64) / 16.0).exp(); }
        imp[5 * spu] = 1.0;
        let freq: Vec<f64> = (0..200).map(|i| i as f64 * 1e7).collect();
        let mut txv = BTreeMap::new();
        txv.insert("tx_ffe_cm1_values".to_string(), vec![0.3]);
        txv.insert("tx_ffe_c0_values".to_string(), vec![0.6, 0.8]);
        txv.insert("tx_ffe_cp1_values".to_string(), vec![-0.1]);
        let receiver = ReceiverNoiseParamsV1 { fb: 26.5625e9, btorder: 3, fb_bt_cutoff: 0.75, fb_bw_cutoff: 0.75, rc_start: 8e9, rc_end: 12e9, eta_0: 1e-3, accm_max_freq: 30e9, ac_cm_rms: vec![0.0], ctle_gdc_values: vec![6.0], ctle_fz: vec![10e9], ctle_fp1: vec![30e9], ctle_fp2: vec![40e9], ctle_type: "CTLE".into(), f_hp: vec![0.0], f_hp_z: vec![5e9], f_hp_p: vec![1e9] };
        let ctle = CtleParamsV1 { ctle_gdc_values: vec![6.0], ctle_fz: vec![10e9], ctle_fp1: vec![30e9], ctle_fp2: vec![40e9], ctle_type: "CTLE".into(), f_hp: vec![0.0], f_hp_z: vec![5e9], f_hp_p: vec![1e9] };
        let candidate = CandidateEvalParamsV1 { samples_per_ui: spu, r_lm: 50.0, levels: 4, sigma_x: 0.03, dfe_delta: 1e-3, n_tail_start: 0, b_float_rss_max: 0.0, a_dd: 0.1, sigma_rj: 1e-4, t_o: 0.0, min_veo_test: 0.0, noise_crest_factor: 0.0, spec_ber: 1e-4, samples_for_c2m: 8, ql: 1.0, floating_dfe: false, ndfe: 2, n_bmax: 2, n_bf: 1, n_bg: 1, bmaxg: 0.3, bmax: vec![0.5, 0.5], bmin: vec![-0.5, -0.5] };
        let full = SearchFullParamsV1 { samples_per_ui: spu, fb: 26.5625e9, tx_ffe_values: txv, tx_ffe_c0_min: 0.2, ts_anchor: 0, local_search: 0.0, ts_sample_adj_range: vec![-1, 1], include_ctle: true, gdc_min: 0.0, gqual: vec![vec![0.0]], g2qual: vec![0.0], dfe_first_max: 0.5, receiver_noise: receiver, ctle, candidate };
        let opts = SearchFullOptionsV1 { ffe_opt_method: "MMSE".into(), rx_ffe_enabled: false, ts_srch_mode: "full-sweep".into(), cdr: "MM".into(), receiver: ReceiverNoiseOptionsV1 { bessel_thomson: false, butterworth: false, raised_cosine: false, use_eta0_psd: false, wc_portz: false, pkg_len_select: vec![1] }, candidate: CandidateEvalOptionsV1 { snr_txw_c0: false, wc_portz: false, tx_rd_sel: 1, pkg_len_select: vec![1], sndr: vec![30.0], limit_jitter_contrib_to_dfe_span: false, force_pdf_bin_size: false, bin_size: 1e-3, force_bbn_q_factor: false, bbn_q_factor: 0.0, histogram_window_weight: "rectangle".into() } };
        let result = search_r480_nonmmse_no_xtalk_v1(&imp, &freq, &freq, &freq, &[], |_, _, _| 0.0, None, false, &[], 0, &full, &opts);
        let result = result.expect("composite result");
        assert!(result.fom_db > 0.0, "fom should be positive");
        assert!((result.cursor_index as i64 - 56).abs() <= 1, "cursor near 56, got {}", result.cursor_index);
        // oracle returns fom=53.4266 on this scenario; assert tight agreement.
        assert!((result.fom_db - 53.42661625274711).abs() < 1e-9, "fom {}, expected 53.42661625274711", result.fom_db);
    }
}
