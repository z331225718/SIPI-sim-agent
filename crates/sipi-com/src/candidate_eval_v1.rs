//! Candidate evaluation body (P5-04s).
//!
//! Ported from agent-com src/agent_com/equalization/search.py (MIT
//! source, P5-04s): _evaluate_candidate (sigma-ISI rejections, DFE
//! bounds with tail RSS, jitter sigma, SNDR/TX noise, C2M vertical-eye
//! branch, strict-FOM improvement gate) and _c2m_candidate_fom. The
//! search loop (search_r480_nonmmse_no_xtalk) remains a separate scope.

use crate::c2m_eye_v1::{C2mEyeErrorV1, calculate_c2m_vertical_eye_v1};
use crate::candidate_helpers_v1::{
    CandidateErrorV1, DfeCandidateParamsV1, candidate_ber_q_v1, cannot_improve_fom_v1,
    dfe_candidate_bounds_v1, jitter_response_v1, jitter_sigma_v1, r480_bbn_q_factor_v1,
    r480_pdf_bin_size_v1,
};
use crate::dfe_v1::{DfeErrorV1, apply_tail_rss_bounds_v1, clip_dfe_v1};
use crate::discrete_pdf_v1::{DiscretePdfV1, PdfErrorV1};
use crate::search_support_v1::{SearchErrorV1, selected_sndr_v1};

/// Explicit scope policy of the candidate evaluation stage.
pub const CANDIDATE_EVAL_POLICY_V1: &str = "sipi.p5-04s.candidate-eval.v1.fom-c2m-rejection";

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum CandidateEvalErrorV1 {
    InvalidControls,
    Dfe,
    Candidate,
    Search,
    C2mEye,
    Pdf,
}

impl From<DfeErrorV1> for CandidateEvalErrorV1 {
    fn from(_: DfeErrorV1) -> Self {
        CandidateEvalErrorV1::Dfe
    }
}
impl From<CandidateErrorV1> for CandidateEvalErrorV1 {
    fn from(_: CandidateErrorV1) -> Self {
        CandidateEvalErrorV1::Candidate
    }
}
impl From<SearchErrorV1> for CandidateEvalErrorV1 {
    fn from(_: SearchErrorV1) -> Self {
        CandidateEvalErrorV1::Search
    }
}
impl From<C2mEyeErrorV1> for CandidateEvalErrorV1 {
    fn from(_: C2mEyeErrorV1) -> Self {
        CandidateEvalErrorV1::C2mEye
    }
}
impl From<PdfErrorV1> for CandidateEvalErrorV1 {
    fn from(_: PdfErrorV1) -> Self {
        CandidateEvalErrorV1::Pdf
    }
}

/// The R480 equalizer-search parameter surface used by one candidate.
#[derive(Clone, Debug, PartialEq)]
pub struct CandidateEvalParamsV1 {
    pub samples_per_ui: usize,
    pub r_lm: f64,
    pub levels: usize,
    pub sigma_x: f64,
    pub dfe_delta: f64,
    pub n_tail_start: i64,
    pub b_float_rss_max: f64,
    pub a_dd: f64,
    pub sigma_rj: f64,
    pub t_o: f64,
    pub min_veo_test: f64,
    pub noise_crest_factor: f64,
    pub spec_ber: f64,
    pub samples_for_c2m: usize,
    pub ql: f64,
    pub floating_dfe: bool,
    pub ndfe: i64,
    pub n_bmax: i64,
    pub n_bf: i64,
    pub n_bg: i64,
    pub bmaxg: f64,
    pub bmax: Vec<f64>,
    pub bmin: Vec<f64>,
}

/// The R480 search options referenced by candidate evaluation.
#[derive(Clone, Debug, PartialEq)]
pub struct CandidateEvalOptionsV1 {
    pub snr_txw_c0: bool,
    pub wc_portz: bool,
    pub tx_rd_sel: i64,
    pub pkg_len_select: Vec<i64>,
    pub sndr: Vec<f64>,
    pub limit_jitter_contrib_to_dfe_span: bool,
    pub force_pdf_bin_size: bool,
    pub bin_size: f64,
    pub force_bbn_q_factor: bool,
    pub bbn_q_factor: f64,
    pub histogram_window_weight: String,
}

/// Best candidate result from the fixed-DFE non-RxFFE branch.
#[derive(Clone, Debug, PartialEq)]
pub struct NonMmseSearchResultV1 {
    pub fom_db: f64,
    pub ctle_index: i64,
    pub ctle_gain_db: f64,
    pub high_pass_index: i64,
    pub high_pass_gain_db: f64,
    pub tx_ffe_taps: Vec<f64>,
    pub tx_ffe_precursor_count: usize,
    pub cursor_index: usize,
    pub sbr: Vec<f64>,
    pub dfe_taps: Vec<f64>,
    pub dfe_max: Vec<f64>,
    pub dfe_min: Vec<f64>,
    pub floating_dfe_locations: Vec<i64>,
    pub available_signal_v: f64,
    pub sigma_n_v: f64,
    pub sigma_ne_v: f64,
    pub h_j: Vec<f64>,
    pub tx_grid_index: i64,
    pub tx_source_indices: Vec<i64>,
    pub itick: i64,
    pub sigma_tx_v: f64,
}

fn l2_norm(values: &[f64]) -> f64 {
    values.iter().map(|v| v * v).sum::<f64>().sqrt()
}

fn accumulate_squared_strided(
    mut sum: f64,
    values: &[f64],
    start: usize,
    stop: usize,
    stride: usize,
) -> f64 {
    for value in values[start..stop].iter().step_by(stride) {
        sum += value * value;
    }
    sum
}

/// Port of _c2m_candidate_fom (C2M vertical-eye FOM replacement).
#[allow(clippy::too_many_arguments)]
pub fn c2m_candidate_fom_v1(
    sbr: &[f64],
    cursor_index: usize,
    available_signal: f64,
    sigma_n_v: f64,
    sigma_tx_v: f64,
    dfe_tap_count: i64,
    dfe_max: &[f64],
    dfe_min: &[f64],
    parameters: &CandidateEvalParamsV1,
    options: &CandidateEvalOptionsV1,
) -> Result<Option<f64>, CandidateEvalErrorV1> {
    let ber_q = candidate_ber_q_v1(parameters.noise_crest_factor, parameters.spec_ber);
    let bin_size = r480_pdf_bin_size_v1(
        available_signal,
        options.bin_size,
        options.force_pdf_bin_size,
    );
    let _nsigma = match r480_bbn_q_factor_v1(options.force_bbn_q_factor, options.bbn_q_factor)? {
        Some(value) => value,
        None => ber_q,
    };
    // ne_noise_pdf = normal_pdf(0.0, nsigma, bin_size): sigma 0 -> unit delta.
    let ne = DiscretePdfV1::try_new(bin_size, 0, vec![1.0])?;
    let cci = DiscretePdfV1::try_new(bin_size, 0, vec![1.0])?;
    let (veo_top, veo_bottom) = calculate_c2m_vertical_eye_v1(
        sbr,
        cursor_index,
        parameters.samples_per_ui,
        parameters.samples_for_c2m,
        parameters.levels,
        bin_size,
        parameters.r_lm,
        dfe_tap_count,
        dfe_max,
        dfe_min,
        parameters.dfe_delta,
        parameters.sigma_rj,
        parameters.sigma_x,
        sigma_n_v,
        sigma_tx_v,
        ber_q,
        &ne,
        &cci,
        parameters.a_dd,
        parameters.spec_ber,
        parameters.t_o,
        &options.histogram_window_weight,
        parameters.ql,
    )?;
    let (Some(top), Some(bottom)) = (veo_top, veo_bottom) else {
        return Ok(None);
    };
    let eye_height = top - bottom;
    if eye_height <= parameters.min_veo_test / 1000.0 {
        return Ok(None);
    }
    let interference = (2.0 * available_signal - eye_height) / 2.0;
    if interference <= 0.0 {
        return Ok(None);
    }
    Ok(Some(20.0 * (available_signal / interference).log10()))
}

/// Port of _evaluate_candidate (fixed-DFE non-RxFFE candidate).
#[allow(clippy::too_many_arguments)]
pub fn evaluate_candidate_v1(
    sbr: &[f64],
    best_fom_db: Option<f64>,
    cursor_index: usize,
    ctle_index: i64,
    ctle_gain_db: f64,
    high_pass_index: i64,
    high_pass_gain_db: f64,
    tx_taps: &[f64],
    precursor_count: usize,
    tx_grid_index: i64,
    tx_source_indices: &[i64],
    sigma_n_v: f64,
    sigma_ne_v: f64,
    sigma_xt_v: f64,
    parameters: &CandidateEvalParamsV1,
    options: &CandidateEvalOptionsV1,
    package_case_index: usize,
    itick: i64,
    retain_non_improving: bool,
) -> Result<Option<NonMmseSearchResultV1>, CandidateEvalErrorV1> {
    let samples_per_ui = parameters.samples_per_ui;
    if cursor_index < samples_per_ui || cursor_index >= sbr.len() || sbr[cursor_index] <= 0.0 {
        return Ok(None);
    }
    let unbounded_ndfe: i64 = if parameters.floating_dfe {
        parameters.n_bmax
    } else {
        parameters.ndfe
    };
    let required = cursor_index + samples_per_ui * (unbounded_ndfe as usize + 1) + 1;
    // Most workbook candidates already span the required DFE tail.  Preserve
    // the legacy zero-padding path exactly when it is needed, but otherwise
    // borrow the scratch waveform until a candidate actually wins.
    let padded_storage = (sbr.len() < required).then(|| {
        let mut values = sbr.to_vec();
        values.resize(required, 0.0);
        values
    });
    let padded = padded_storage.as_deref().unwrap_or(sbr);
    let cursor = padded[cursor_index];
    let available_signal = parameters.r_lm * cursor / (parameters.levels as f64 - 1.0);
    if available_signal <= 0.0 {
        return Ok(None);
    }
    let far_start = cursor_index + samples_per_ui * (unbounded_ndfe as usize + 1);
    let precursor_start = cursor_index % samples_per_ui;
    let precursor_squared =
        accumulate_squared_strided(0.0, padded, precursor_start, cursor_index, samples_per_ui);
    let ignore_dfe_squared = accumulate_squared_strided(
        precursor_squared,
        padded,
        far_start,
        padded.len(),
        samples_per_ui,
    );
    let sigma_ignore_dfe = parameters.sigma_x * ignore_dfe_squared.sqrt();
    if cannot_improve_fom_v1(available_signal, sigma_ignore_dfe, best_fom_db) {
        return Ok(None);
    }

    let dfe_params = DfeCandidateParamsV1 {
        ndfe: parameters.ndfe,
        bmax: parameters.bmax.clone(),
        bmin: parameters.bmin.clone(),
        floating_dfe: parameters.floating_dfe,
        n_bmax: parameters.n_bmax,
        n_bf: parameters.n_bf,
        n_bg: parameters.n_bg,
        bmaxg: parameters.bmaxg,
    };
    let (ndfe, mut dfe_max, mut dfe_min, floating_locations) =
        dfe_candidate_bounds_v1(padded, cursor_index, samples_per_ui, &dfe_params)?;

    let dfe_values: Vec<f64> = padded
        [cursor_index + samples_per_ui..cursor_index + samples_per_ui * (ndfe as usize + 1)]
        .iter()
        .step_by(samples_per_ui)
        .copied()
        .collect();
    let mut dfe_values_q = dfe_values.clone();
    if parameters.dfe_delta != 0.0 {
        let step = parameters.dfe_delta;
        for value in dfe_values_q.iter_mut() {
            *value = ((*value / cursor).abs() / step).floor() * step * value.signum() * cursor;
        }
    }
    let maximum: Vec<f64> = dfe_max.iter().map(|v| cursor * v).collect();
    let minimum: Vec<f64> = dfe_min.iter().map(|v| cursor * v).collect();
    let mut cancelled = clip_dfe_v1(&dfe_values_q, &maximum, &minimum)?;
    let tail_start = parameters.n_tail_start;
    if tail_start > 0 && (tail_start as usize) <= cancelled.len() {
        let taps_n = cancelled.iter().map(|v| v / cursor).collect::<Vec<f64>>();
        let tail_bounds = apply_tail_rss_bounds_v1(
            &taps_n,
            &dfe_max,
            &dfe_min,
            Some((tail_start - 1) as usize),
            parameters.b_float_rss_max,
        )?;
        dfe_max = tail_bounds.maximum().to_vec();
        dfe_min = tail_bounds.minimum().to_vec();
        let maximum2: Vec<f64> = dfe_max.iter().map(|v| cursor * v).collect();
        let minimum2: Vec<f64> = dfe_min.iter().map(|v| cursor * v).collect();
        cancelled = clip_dfe_v1(&dfe_values_q, &maximum2, &minimum2)?;
    }
    let excess: Vec<f64> = dfe_values
        .iter()
        .zip(cancelled.iter())
        .map(|(a, b)| a - b)
        .collect();
    let isi_squared = excess
        .iter()
        .fold(precursor_squared, |sum, value| sum + value * value);
    let isi_squared =
        accumulate_squared_strided(isi_squared, padded, far_start, padded.len(), samples_per_ui);
    let sigma_isi = parameters.sigma_x * isi_squared.sqrt();
    if cannot_improve_fom_v1(available_signal, sigma_isi, best_fom_db) {
        return Ok(None);
    }

    let sigma_j = jitter_sigma_v1(
        padded,
        cursor_index,
        samples_per_ui,
        parameters.a_dd,
        parameters.sigma_rj,
        parameters.sigma_x,
        ndfe,
        options.limit_jitter_contrib_to_dfe_span,
    )?;
    let sndr = selected_sndr_v1(
        &options.sndr,
        options.wc_portz,
        options.tx_rd_sel,
        &options.pkg_len_select,
        package_case_index,
    )?;
    let sigma_tx = if options.snr_txw_c0 {
        let main_tap = tx_taps[precursor_count];
        if main_tap == 0.0 {
            return Ok(None);
        }
        cursor / main_tap * 10f64.powf(-sndr / 20.0)
    } else {
        cursor * 10f64.powf(-sndr / 20.0)
    };
    let total = l2_norm(&[
        sigma_isi, sigma_j, sigma_xt_v, sigma_n_v, sigma_tx, sigma_ne_v,
    ]);
    if total == 0.0 {
        return Ok(None);
    }
    let mut fom = 20.0 * (available_signal / total).log10();

    if parameters.t_o != 0.0 && parameters.min_veo_test != 0.0 {
        let ber_q = candidate_ber_q_v1(parameters.noise_crest_factor, parameters.spec_ber);
        let first_eye_height = 2.0 * (available_signal - ber_q * total);
        if first_eye_height <= parameters.min_veo_test / 1000.0 - 0.001 {
            return Ok(None);
        }
        match c2m_candidate_fom_v1(
            padded,
            cursor_index,
            available_signal,
            sigma_n_v,
            sigma_tx,
            ndfe,
            &dfe_max,
            &dfe_min,
            parameters,
            options,
        )? {
            Some(value) => fom = value,
            None => return Ok(None),
        }
    }
    if best_fom_db.is_some() && !(fom > best_fom_db.unwrap()) && !retain_non_improving {
        return Ok(None);
    }
    let h_j = jitter_response_v1(
        padded,
        cursor_index,
        samples_per_ui,
        ndfe,
        options.limit_jitter_contrib_to_dfe_span,
        None,
    )?;
    Ok(Some(NonMmseSearchResultV1 {
        fom_db: fom,
        ctle_index,
        ctle_gain_db,
        high_pass_index,
        high_pass_gain_db,
        tx_ffe_taps: tx_taps.to_vec(),
        tx_ffe_precursor_count: precursor_count,
        cursor_index,
        sbr: padded.to_vec(),
        dfe_taps: cancelled.iter().map(|v| v / cursor).collect(),
        dfe_max,
        dfe_min,
        floating_dfe_locations: floating_locations,
        available_signal_v: available_signal,
        sigma_n_v,
        sigma_ne_v,
        h_j,
        tx_grid_index,
        tx_source_indices: tx_source_indices.to_vec(),
        itick,
        sigma_tx_v: sigma_tx,
    }))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn params_fn() -> CandidateEvalParamsV1 {
        CandidateEvalParamsV1 {
            samples_per_ui: 10,
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
        }
    }

    fn options_fn() -> CandidateEvalOptionsV1 {
        CandidateEvalOptionsV1 {
            snr_txw_c0: false,
            wc_portz: false,
            tx_rd_sel: 0,
            pkg_len_select: vec![1],
            sndr: vec![30.0, 30.0, 30.0, 30.0],
            limit_jitter_contrib_to_dfe_span: false,
            force_pdf_bin_size: false,
            bin_size: 1e-3,
            force_bbn_q_factor: false,
            bbn_q_factor: 0.0,
            histogram_window_weight: "rectangle".to_string(),
        }
    }

    fn pulse() -> Vec<f64> {
        (0..260)
            .map(|i| {
                let t = i as f64;
                (0.5 * (-((t - 104.0) * (t - 104.0) / 400.0)).exp() + 0.05).max(0.02)
            })
            .collect()
    }

    #[test]
    fn policy_string_is_fixed() {
        assert_eq!(
            CANDIDATE_EVAL_POLICY_V1,
            "sipi.p5-04s.candidate-eval.v1.fom-c2m-rejection"
        );
    }

    #[test]
    fn invalid_cursor_returns_none() {
        let p = pulse();
        let result = evaluate_candidate_v1(
            &p,
            None,
            0,
            0,
            0.0,
            0,
            0.0,
            &[],
            0,
            0,
            &[],
            1e-4,
            1e-4,
            1e-4,
            &params_fn(),
            &options_fn(),
            0,
            0,
            false,
        )
        .expect("eval");
        assert!(result.is_none());
    }

    #[test]
    fn c2m_fom_returns_none_when_eye_closed() {
        let p = pulse();
        let mut params = params_fn();
        params.t_o = 0.5;
        params.min_veo_test = 20000.0; // threshold 20 V > any feasible eye -> None
        let result = c2m_candidate_fom_v1(
            &p,
            100,
            8.0,
            1e-4,
            1e-3,
            2,
            &[0.5, 0.5],
            &[-0.5, -0.5],
            &params,
            &options_fn(),
        )
        .expect("fom");
        assert!(result.is_none());
    }

    #[test]
    fn c2m_fom_returns_some_for_open_eye() {
        let p = pulse();
        let mut params = params_fn();
        params.t_o = 0.5;
        params.min_veo_test = 1.0;
        let result = c2m_candidate_fom_v1(
            &p,
            100,
            8.0,
            1e-4,
            1e-3,
            2,
            &[0.5, 0.5],
            &[-0.5, -0.5],
            &params,
            &options_fn(),
        )
        .expect("fom");
        assert!(result.is_some());
    }

    #[test]
    fn happy_path_produces_result() {
        let p = pulse();
        let result = evaluate_candidate_v1(
            &p,
            None,
            104,
            1,
            2.0,
            0,
            0.0,
            &[0.5, 1.0, -0.25],
            1,
            0,
            &[],
            1e-4,
            1e-4,
            1e-4,
            &params_fn(),
            &options_fn(),
            0,
            0,
            false,
        )
        .expect("eval");
        let result = result.expect("result");
        assert!(result.fom_db.is_finite());
        assert!(result.fom_db >= 0.0);
        assert_eq!(result.cursor_index, 104);
        assert_eq!(result.dfe_taps.len(), 2);
    }

    #[test]
    fn strict_improvement_rejects_without_retain() {
        let p = pulse();
        let result = evaluate_candidate_v1(
            &p,
            Some(100.0),
            104,
            1,
            2.0,
            0,
            0.0,
            &[0.5, 1.0, -0.25],
            1,
            0,
            &[],
            1e-4,
            1e-4,
            1e-4,
            &params_fn(),
            &options_fn(),
            0,
            0,
            false,
        )
        .expect("eval");
        assert!(result.is_none());
    }

    #[test]
    fn retain_non_improving_keeps_result() {
        let p = pulse();
        let base = evaluate_candidate_v1(
            &p,
            None,
            104,
            1,
            2.0,
            0,
            0.0,
            &[0.5, 1.0, -0.25],
            1,
            0,
            &[],
            1e-4,
            1e-4,
            1e-4,
            &params_fn(),
            &options_fn(),
            0,
            0,
            false,
        )
        .expect("eval")
        .expect("base");
        let best = Some(base.fom_db + 0.5);
        let rejected = evaluate_candidate_v1(
            &p,
            best,
            104,
            1,
            2.0,
            0,
            0.0,
            &[0.5, 1.0, -0.25],
            1,
            0,
            &[],
            1e-4,
            1e-4,
            1e-4,
            &params_fn(),
            &options_fn(),
            0,
            0,
            false,
        )
        .expect("rej");
        assert!(rejected.is_none());
        let kept = evaluate_candidate_v1(
            &p,
            best,
            104,
            1,
            2.0,
            0,
            0.0,
            &[0.5, 1.0, -0.25],
            1,
            0,
            &[],
            1e-4,
            1e-4,
            1e-4,
            &params_fn(),
            &options_fn(),
            0,
            0,
            true,
        )
        .expect("ret");
        assert!(kept.is_some());
    }
}
