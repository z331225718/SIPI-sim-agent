//! Bounded FV-LMS/fixed-force RxFFE candidate search.
//!
//! The source's search loop calls the same `force_rx_ffe` primitive for each
//! candidate.  This direct leaf keeps that ordering and strict-best policy,
//! while accepting an already materialized pulse/cursor grid at the API
//! boundary (the channel remains an impulse and is never fitted).

use crate::candidate_eval_v1::{
    CandidateEvalErrorV1, CandidateEvalOptionsV1, CandidateEvalParamsV1, evaluate_candidate_v1,
};
use crate::candidate_helpers_v1::jitter_sigma_v1;
use crate::rx_ffe_v1::{RxFfeErrorV1, force_floating_rx_ffe_v1, force_rx_ffe_v1};

pub const RXFFE_SEARCH_POLICY_V1: &str =
    "sipi.com.equalization.fvlms-rxffe-v1.force-strict-best-search";
pub const MAX_RXFFE_SEARCH_CANDIDATES_V1: usize = 16_384;
pub const MAX_RXFFE_SEARCH_WAVEFORM_SAMPLES_V1: usize = 262_144;

#[derive(Clone, Debug, PartialEq)]
pub struct RxFfeSearchCandidateV1 {
    pub waveform: Vec<f64>,
    pub cursor_index: usize,
    pub precursor_count: usize,
    pub postcursor_count: usize,
    pub samples_per_ui: usize,
    pub dfe_first_max: f64,
    pub unity_cursor: bool,
    pub tap_step: f64,
    pub floating: bool,
    pub maximum_postcursor_count: usize,
    pub floating_start: usize,
    pub taps_per_bank: usize,
    pub bank_count: usize,
    pub coefficient_limit: f64,
    pub selection: String,
    pub rx_ffe_gain_db: f64,
    pub ctle_index: i64,
    pub ctle_gain_db: f64,
    pub high_pass_index: i64,
    pub high_pass_gain_db: f64,
    /// Optional source-shaped FOM evaluation controls.  The force-only form
    /// remains useful for a small reusable FIR leaf; when this is present the
    /// search executes the complete portable FV-LMS candidate evaluator
    /// (DFE bounds, jitter, receiver/TX noise, and C2M admission) instead of
    /// the fallback cursor-to-residual score.
    pub evaluation: Option<RxFfeSearchEvaluationV1>,
}

/// Materialized inputs consumed by the source `_evaluate_fixed_rxffe_candidate`
/// body.  Frequency-domain noise construction and CTLE orchestration happen
/// at the caller boundary; the pure candidate arithmetic is reused here.
#[derive(Clone, Debug, PartialEq)]
pub struct RxFfeSearchEvaluationV1 {
    pub parameters: CandidateEvalParamsV1,
    pub options: CandidateEvalOptionsV1,
    pub sigma_n_v: f64,
    pub sigma_ne_v: f64,
    pub sigma_xt_v: f64,
    pub package_case_index: usize,
    pub tx_taps: Vec<f64>,
    pub tx_precursor_count: usize,
    pub tx_grid_index: i64,
    pub tx_source_indices: Vec<i64>,
    pub itick: i64,
    pub ffe_main_cursor_min: f64,
    pub ffe_pre_tap1_max: f64,
    pub ffe_pre_tapn_max: f64,
    pub ffe_post_tap1_max: f64,
    pub ffe_tapn_max: f64,
}

#[derive(Clone, Debug, PartialEq)]
pub struct RxFfeSearchResultV1 {
    pub candidate_index: usize,
    pub fom_db: f64,
    pub cursor_v: f64,
    pub residual_rms_v: f64,
    pub taps: Vec<f64>,
    pub filtered: Vec<f64>,
    pub floating_locations: Vec<i64>,
    pub rx_ffe_gain_db: f64,
    pub ctle_index: i64,
    pub ctle_gain_db: f64,
    pub high_pass_index: i64,
    pub high_pass_gain_db: f64,
    pub dfe_taps: Vec<f64>,
    pub dfe_max: Vec<f64>,
    pub dfe_min: Vec<f64>,
    pub available_signal_v: f64,
    pub sigma_n_v: f64,
    pub sigma_ne_v: f64,
    pub sigma_xt_v: f64,
    pub sigma_isi_v: f64,
    pub sigma_j_v: f64,
    pub sigma_tx_v: f64,
    pub sigma_total_v: f64,
    pub h_j: Vec<f64>,
    pub tx_taps: Vec<f64>,
    pub tx_precursor_count: usize,
    pub tx_grid_index: i64,
    pub tx_source_indices: Vec<i64>,
    pub itick: i64,
    pub full_fom_evaluation: bool,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum RxFfeSearchErrorV1 {
    EmptySearch,
    CandidateLimit,
    InvalidInput,
    Force(RxFfeErrorV1),
    CandidateEval(CandidateEvalErrorV1),
    NonFinite,
}

impl From<RxFfeErrorV1> for RxFfeSearchErrorV1 {
    fn from(value: RxFfeErrorV1) -> Self {
        Self::Force(value)
    }
}

impl From<CandidateEvalErrorV1> for RxFfeSearchErrorV1 {
    fn from(value: CandidateEvalErrorV1) -> Self {
        Self::CandidateEval(value)
    }
}

fn rxffe_is_illegal(
    taps: &[f64],
    candidate: &RxFfeSearchCandidateV1,
    evaluation: &RxFfeSearchEvaluationV1,
) -> bool {
    let fixed_count = candidate
        .precursor_count
        .saturating_add(candidate.postcursor_count)
        .saturating_add(1);
    if taps.len() < fixed_count || candidate.precursor_count >= taps.len() {
        return true;
    }
    if taps[candidate.precursor_count] < evaluation.ffe_main_cursor_min {
        return true;
    }
    if candidate.precursor_count > 0
        && taps[candidate.precursor_count - 1].abs() > evaluation.ffe_pre_tap1_max
    {
        return true;
    }
    if candidate.precursor_count > 1
        && taps[..candidate.precursor_count - 1]
            .iter()
            .any(|value| value.abs() > evaluation.ffe_pre_tapn_max)
    {
        return true;
    }
    if candidate.postcursor_count > 0
        && taps[candidate.precursor_count + 1].abs() > evaluation.ffe_post_tap1_max
    {
        return true;
    }
    candidate.postcursor_count > 1
        && taps[candidate.precursor_count + 2..fixed_count]
            .iter()
            .any(|value| value.abs() > evaluation.ffe_tapn_max)
}

fn full_evaluation(
    candidate: &RxFfeSearchCandidateV1,
    forced: &[f64],
    evaluation: &RxFfeSearchEvaluationV1,
    best_fom_db: Option<f64>,
) -> Result<
    Option<(
        f64,
        f64,
        f64,
        crate::candidate_eval_v1::NonMmseSearchResultV1,
    )>,
    RxFfeSearchErrorV1,
> {
    if evaluation.parameters.floating_dfe {
        return Ok(None);
    }
    if rxffe_is_illegal(forced, candidate, evaluation) {
        return Ok(None);
    }
    let result = evaluate_candidate_v1(
        forced,
        best_fom_db,
        candidate.cursor_index,
        candidate.ctle_index,
        candidate.ctle_gain_db,
        candidate.high_pass_index,
        candidate.high_pass_gain_db,
        &evaluation.tx_taps,
        evaluation.tx_precursor_count,
        evaluation.tx_grid_index,
        &evaluation.tx_source_indices,
        evaluation.sigma_n_v,
        evaluation.sigma_ne_v,
        evaluation.sigma_xt_v,
        &evaluation.parameters,
        &evaluation.options,
        evaluation.package_case_index,
        evaluation.itick,
        false,
    )?;
    let Some(result) = result else {
        return Ok(None);
    };
    let cursor_v = result.sbr[candidate.cursor_index];
    let ndfe = result.dfe_taps.len();
    let mut dfe_values = Vec::with_capacity(ndfe);
    for tap in 1..=ndfe {
        let index = tap
            .checked_mul(candidate.samples_per_ui)
            .and_then(|offset| candidate.cursor_index.checked_add(offset))
            .unwrap_or(usize::MAX);
        dfe_values.push(result.sbr.get(index).copied().unwrap_or(0.0));
    }
    let mut precursor_values = Vec::new();
    let mut index = candidate.cursor_index;
    while index >= candidate.samples_per_ui {
        index -= candidate.samples_per_ui;
        precursor_values.push(result.sbr[index]);
    }
    precursor_values.reverse();
    let far_start = ndfe
        .checked_add(1)
        .and_then(|tap| tap.checked_mul(candidate.samples_per_ui))
        .and_then(|offset| candidate.cursor_index.checked_add(offset))
        .unwrap_or(usize::MAX);
    let far = result
        .sbr
        .iter()
        .skip(far_start)
        .step_by(candidate.samples_per_ui)
        .copied();
    let mut isi = precursor_values;
    isi.extend(
        dfe_values
            .iter()
            .zip(result.dfe_taps.iter())
            .map(|(value, tap)| value - tap * cursor_v),
    );
    isi.extend(far);
    let sigma_isi_v =
        evaluation.parameters.sigma_x * isi.iter().map(|value| value * value).sum::<f64>().sqrt();
    let sigma_j_v = jitter_sigma_v1(
        &result.sbr,
        candidate.cursor_index,
        candidate.samples_per_ui,
        evaluation.parameters.a_dd,
        evaluation.parameters.sigma_rj,
        evaluation.parameters.sigma_x,
        ndfe as i64,
        evaluation.options.limit_jitter_contrib_to_dfe_span,
    )
    .map_err(|_| RxFfeSearchErrorV1::NonFinite)?;
    if !sigma_isi_v.is_finite() || !sigma_j_v.is_finite() {
        return Err(RxFfeSearchErrorV1::NonFinite);
    }
    Ok(Some((sigma_isi_v, sigma_j_v, cursor_v, result)))
}

/// Execute fixed or floating force for each candidate and keep the first
/// strict best.  The score is a semantic signal-to-residual metric computed
/// from the returned waveform, not a candidate status flag.
pub fn search_fvlms_rxffe_candidates_v1(
    candidates: &[RxFfeSearchCandidateV1],
) -> Result<RxFfeSearchResultV1, RxFfeSearchErrorV1> {
    if candidates.is_empty() {
        return Err(RxFfeSearchErrorV1::EmptySearch);
    }
    if candidates.len() > MAX_RXFFE_SEARCH_CANDIDATES_V1 {
        return Err(RxFfeSearchErrorV1::CandidateLimit);
    }
    let mut best: Option<RxFfeSearchResultV1> = None;
    for (candidate_index, candidate) in candidates.iter().enumerate() {
        if !candidate.rx_ffe_gain_db.is_finite()
            || candidate.waveform.is_empty()
            || candidate.waveform.len() > MAX_RXFFE_SEARCH_WAVEFORM_SAMPLES_V1
            || candidate.waveform.iter().any(|value| !value.is_finite())
        {
            return Err(RxFfeSearchErrorV1::InvalidInput);
        }
        if candidate
            .evaluation
            .as_ref()
            .is_some_and(|evaluation| evaluation.parameters.floating_dfe)
        {
            return Err(RxFfeSearchErrorV1::InvalidInput);
        }
        let (forced, floating_locations) = if candidate.floating {
            force_floating_rx_ffe_v1(
                &candidate.waveform,
                candidate.cursor_index,
                candidate.precursor_count,
                candidate.postcursor_count,
                candidate.maximum_postcursor_count,
                candidate.samples_per_ui,
                candidate.dfe_first_max,
                candidate.unity_cursor,
                candidate.tap_step,
                candidate.floating_start,
                candidate.taps_per_bank,
                candidate.bank_count,
                candidate.coefficient_limit,
                &candidate.selection,
                true,
            )?
        } else {
            (
                force_rx_ffe_v1(
                    &candidate.waveform,
                    candidate.cursor_index,
                    candidate.precursor_count,
                    candidate.postcursor_count,
                    candidate.samples_per_ui,
                    candidate.dfe_first_max,
                    candidate.unity_cursor,
                    candidate.tap_step,
                    true,
                )?,
                Vec::new(),
            )
        };
        let filtered = forced
            .filtered()
            .ok_or(RxFfeSearchErrorV1::InvalidInput)?
            .to_vec();
        let full = candidate
            .evaluation
            .as_ref()
            .map(|evaluation| {
                full_evaluation(
                    candidate,
                    &filtered,
                    evaluation,
                    best.as_ref().map(|item| item.fom_db),
                )
            })
            .transpose()?;
        let (fom_db, cursor_v, residual_rms_v, details, full_fom_evaluation) =
            if let Some(Some((sigma_isi_v, sigma_j_v, cursor_v, result))) = full {
                let residual_rms_v = (sigma_isi_v * sigma_isi_v + sigma_j_v * sigma_j_v).sqrt();
                (
                    result.fom_db,
                    cursor_v,
                    residual_rms_v,
                    Some((sigma_isi_v, sigma_j_v, result)),
                    true,
                )
            } else if candidate.evaluation.is_some() {
                continue;
            } else {
                return Err(RxFfeSearchErrorV1::InvalidInput);
            };
        if best
            .as_ref()
            .is_none_or(|previous| fom_db > previous.fom_db)
        {
            let (sigma_isi_v, sigma_j_v) = details
                .as_ref()
                .map(|value| (value.0, value.1))
                .unwrap_or((0.0, 0.0));
            let (
                dfe_taps,
                dfe_max,
                dfe_min,
                available_signal_v,
                sigma_n_v,
                sigma_ne_v,
                sigma_xt_v,
                sigma_tx_v,
                h_j,
                tx_taps,
                tx_precursor_count,
                tx_grid_index,
                tx_source_indices,
                itick,
                sigma_total_v,
            ) = if let (Some(evaluation), Some((sigma_isi_v, sigma_j_v, result))) =
                (candidate.evaluation.as_ref(), details.as_ref())
            {
                let sigma_total_v = (sigma_isi_v * sigma_isi_v
                    + sigma_j_v * sigma_j_v
                    + evaluation.sigma_xt_v * evaluation.sigma_xt_v
                    + result.sigma_n_v * result.sigma_n_v
                    + result.sigma_tx_v * result.sigma_tx_v)
                    .sqrt();
                (
                    result.dfe_taps.clone(),
                    result.dfe_max.clone(),
                    result.dfe_min.clone(),
                    result.available_signal_v,
                    result.sigma_n_v,
                    result.sigma_ne_v,
                    evaluation.sigma_xt_v,
                    result.sigma_tx_v,
                    result.h_j.clone(),
                    result.tx_ffe_taps.clone(),
                    result.tx_ffe_precursor_count,
                    result.tx_grid_index,
                    result.tx_source_indices.clone(),
                    result.itick,
                    sigma_total_v,
                )
            } else {
                (
                    Vec::new(),
                    Vec::new(),
                    Vec::new(),
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    Vec::new(),
                    Vec::new(),
                    candidate.precursor_count,
                    0,
                    Vec::new(),
                    0,
                    0.0,
                )
            };
            best = Some(RxFfeSearchResultV1 {
                candidate_index,
                fom_db,
                cursor_v,
                residual_rms_v,
                taps: forced.taps().to_vec(),
                filtered,
                floating_locations,
                rx_ffe_gain_db: candidate.rx_ffe_gain_db,
                ctle_index: candidate.ctle_index,
                ctle_gain_db: candidate.ctle_gain_db,
                high_pass_index: candidate.high_pass_index,
                high_pass_gain_db: candidate.high_pass_gain_db,
                dfe_taps,
                dfe_max,
                dfe_min,
                available_signal_v,
                sigma_n_v,
                sigma_ne_v,
                sigma_xt_v,
                sigma_isi_v,
                sigma_j_v,
                sigma_tx_v,
                sigma_total_v,
                h_j,
                tx_taps,
                tx_precursor_count,
                tx_grid_index,
                tx_source_indices,
                itick,
                full_fom_evaluation,
            });
        }
    }
    best.ok_or(RxFfeSearchErrorV1::EmptySearch)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn candidate(gain: f64) -> RxFfeSearchCandidateV1 {
        let mut waveform = vec![0.0; 32];
        waveform[8] = 0.01;
        waveform[12] = 0.1;
        waveform[16] = 1.0;
        waveform[20] = 0.05;
        waveform[24] = 0.02;
        waveform[28] = 0.01;
        RxFfeSearchCandidateV1 {
            waveform,
            cursor_index: 16,
            precursor_count: 1,
            postcursor_count: 2,
            samples_per_ui: 4,
            dfe_first_max: 0.0,
            unity_cursor: true,
            tap_step: 0.0,
            floating: false,
            maximum_postcursor_count: 0,
            floating_start: 0,
            taps_per_bank: 0,
            bank_count: 0,
            coefficient_limit: 0.0,
            selection: "taps".to_owned(),
            rx_ffe_gain_db: gain,
            ctle_index: 0,
            ctle_gain_db: 0.0,
            high_pass_index: 0,
            high_pass_gain_db: 0.0,
            evaluation: None,
        }
    }

    #[test]
    fn fixed_force_search_requires_full_evaluator() {
        assert!(matches!(
            search_fvlms_rxffe_candidates_v1(&[candidate(0.0), candidate(2.0)]),
            Err(RxFfeSearchErrorV1::InvalidInput)
        ));
    }

    #[test]
    fn full_fvlms_evaluation_publishes_dfe_and_noise_payload() {
        let mut item = candidate(0.0);
        item.evaluation = Some(RxFfeSearchEvaluationV1 {
            parameters: CandidateEvalParamsV1 {
                samples_per_ui: 4,
                r_lm: 50.0,
                levels: 4,
                sigma_x: 0.03,
                dfe_delta: 0.0,
                n_tail_start: 0,
                b_float_rss_max: 0.0,
                a_dd: 0.4,
                sigma_rj: 1.0e-4,
                t_o: 0.0,
                min_veo_test: 0.0,
                noise_crest_factor: 0.0,
                spec_ber: 1.0e-4,
                samples_for_c2m: 8,
                ql: 1.0,
                floating_dfe: false,
                ndfe: 1,
                n_bmax: 1,
                n_bf: 1,
                n_bg: 0,
                bmaxg: 0.3,
                bmax: vec![0.5],
                bmin: vec![-0.5],
            },
            options: CandidateEvalOptionsV1 {
                snr_txw_c0: false,
                wc_portz: false,
                tx_rd_sel: 0,
                pkg_len_select: vec![1],
                sndr: vec![30.0],
                limit_jitter_contrib_to_dfe_span: false,
                force_pdf_bin_size: false,
                bin_size: 0.01,
                force_bbn_q_factor: false,
                bbn_q_factor: 0.0,
                histogram_window_weight: "rectangle".to_owned(),
            },
            sigma_n_v: 0.001,
            sigma_ne_v: 0.0,
            sigma_xt_v: 0.0,
            package_case_index: 0,
            tx_taps: vec![1.0],
            tx_precursor_count: 0,
            tx_grid_index: 0,
            tx_source_indices: vec![0],
            itick: 0,
            ffe_main_cursor_min: 0.0,
            ffe_pre_tap1_max: f64::INFINITY,
            ffe_pre_tapn_max: f64::INFINITY,
            ffe_post_tap1_max: 1.0,
            ffe_tapn_max: 1.0,
        });
        let result = search_fvlms_rxffe_candidates_v1(&[item]).expect("full FvLMS search");
        assert!(result.full_fom_evaluation);
        assert!(result.available_signal_v > 0.0);
        assert_eq!(result.dfe_taps.len(), 1);
        assert!(result.sigma_n_v > 0.0);
        assert!(result.sigma_total_v > result.sigma_n_v);
        assert_eq!(result.tx_taps, vec![1.0]);
    }
}
