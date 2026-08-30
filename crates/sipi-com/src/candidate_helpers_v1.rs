//! Candidate evaluation helpers (port of `equalization/search.py`
//! rejection, DFE-bounds, and jitter-response functions).
//!
//! Ported from agent-com (MIT source, P5-04q source map): the strict FOM
//! upper-bound rejection, candidate BER Q-factor, PDF bin size, BBN Q
//! override, fixed/floating DFE candidate bounds, the Eq. 93A-28 sampled
//! jitter response (with the experimental DFE-span limit), and the jitter
//! sigma. The candidate evaluation body and the C2M eye search remain
//! separate scopes.

use crate::dfe_v1::{DfeErrorV1, find_dfe_bank_locations_v1};
use crate::erf_v1::erfcinv_v1;

/// Explicit scope policy of the candidate helper stage.
pub const CANDIDATE_HELPERS_POLICY_V1: &str =
    "sipi.p5-04q.candidate-helpers-v1.reject-bounds-jitter";

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum CandidateErrorV1 {
    DfeBoundsMismatch,
    FloatingDfeInvalid,
    JitterDfeSpan,
    JitterNumUi,
    BbnQInvalid,
    InvalidControls,
}

impl From<DfeErrorV1> for CandidateErrorV1 {
    fn from(_: DfeErrorV1) -> Self {
        CandidateErrorV1::InvalidControls
    }
}

/// Port of `_r480_pdf_bin_size`.
pub fn r480_pdf_bin_size_v1(
    available_signal_v: f64,
    bin_size: f64,
    force_pdf_bin_size: bool,
) -> f64 {
    if force_pdf_bin_size {
        bin_size
    } else {
        (available_signal_v / 1000.0).min(bin_size)
    }
}

/// Port of `_r480_bbn_q_factor`.
pub fn r480_bbn_q_factor_v1(
    force_bbn_q_factor: bool,
    bbn_q_factor: f64,
) -> Result<Option<f64>, CandidateErrorV1> {
    if !force_bbn_q_factor {
        return Ok(None);
    }
    if !bbn_q_factor.is_finite() || bbn_q_factor < 0.0 {
        return Err(CandidateErrorV1::BbnQInvalid);
    }
    Ok(Some(bbn_q_factor))
}

/// Port of `_cannot_improve_fom` (strict upper-bound rejection).
pub fn cannot_improve_fom_v1(available_signal: f64, sigma: f64, best_fom_db: Option<f64>) -> bool {
    let Some(best_fom_db) = best_fom_db else {
        return false;
    };
    if sigma <= 0.0 {
        return false;
    }
    20.0 * (available_signal / sigma).log10() < best_fom_db
}

/// Port of `_candidate_ber_q`.
pub fn candidate_ber_q_v1(noise_crest_factor: f64, spec_ber: f64) -> f64 {
    if noise_crest_factor != 0.0 {
        noise_crest_factor
    } else {
        std::f64::consts::SQRT_2 * erfcinv_v1(2.0 * spec_ber)
    }
}

/// The DFE candidate bound parameter surface.
#[derive(Clone, Debug, PartialEq)]
pub struct DfeCandidateParamsV1 {
    pub ndfe: i64,
    pub bmax: Vec<f64>,
    pub bmin: Vec<f64>,
    pub floating_dfe: bool,
    pub n_bmax: i64,
    pub n_bf: i64,
    pub n_bg: i64,
    pub bmaxg: f64,
}

/// Port of `_dfe_candidate_bounds` (fixed/floating DFE bounds).
pub fn dfe_candidate_bounds_v1(
    sbr: &[f64],
    cursor_index: usize,
    samples_per_ui: usize,
    parameters: &DfeCandidateParamsV1,
) -> Result<(i64, Vec<f64>, Vec<f64>, Vec<i64>), CandidateErrorV1> {
    let fixed_count = parameters.ndfe;
    let fixed_max = parameters.bmax.clone();
    let fixed_min = parameters.bmin.clone();
    if fixed_count < 0
        || fixed_max.len() != fixed_count as usize
        || fixed_min.len() != fixed_count as usize
    {
        return Err(CandidateErrorV1::DfeBoundsMismatch);
    }
    if !parameters.floating_dfe {
        return Ok((fixed_count, fixed_max, fixed_min, Vec::new()));
    }
    let maximum_count = parameters.n_bmax;
    let taps_per_bank = parameters.n_bf;
    let bank_count = parameters.n_bg;
    if maximum_count < fixed_count || taps_per_bank < 1 || bank_count < 1 {
        return Err(CandidateErrorV1::FloatingDfeInvalid);
    }
    let mut postcursors: Vec<f64> = sbr
        .iter()
        .skip(cursor_index + samples_per_ui)
        .step_by(samples_per_ui)
        .copied()
        .collect();
    if postcursors.len() < maximum_count as usize {
        postcursors.resize(maximum_count as usize, 0.0);
    }
    let cursor = sbr[cursor_index];
    let locations = find_dfe_bank_locations_v1(
        &postcursors,
        fixed_count as usize,
        maximum_count as usize - 1,
        taps_per_bank as usize,
        cursor,
        parameters.bmaxg,
        bank_count as usize,
    )?;
    let mut floating_max = vec![0.0_f64; (maximum_count - fixed_count) as usize];
    for location in &locations {
        let index = *location - fixed_count;
        if index >= 0 && index < floating_max.len() as i64 {
            floating_max[index as usize] = parameters.bmaxg;
        }
    }
    let mut maximum = fixed_max.clone();
    maximum.extend_from_slice(&floating_max);
    let mut minimum = fixed_min.clone();
    minimum.extend(floating_max.iter().map(|value| -*value));
    Ok((maximum_count, maximum, minimum, locations))
}

/// Port of `_jitter_response` (Eq. 93A-28 sampled jitter response).
pub fn jitter_response_v1(
    sbr: &[f64],
    cursor_index: usize,
    samples_per_ui: usize,
    dfe_tap_count: i64,
    limit_to_dfe_span: bool,
    num_ui: Option<usize>,
) -> Result<Vec<f64>, CandidateErrorV1> {
    let result: Vec<f64> = if limit_to_dfe_span {
        if dfe_tap_count < 0 {
            return Err(CandidateErrorV1::JitterDfeSpan);
        }
        let mut early = Vec::new();
        let mut late = Vec::new();
        for offset in -1i64..=dfe_tap_count {
            let early_index = cursor_index as i64 - 1 + samples_per_ui as i64 * offset;
            let late_index = cursor_index as i64 + 1 + samples_per_ui as i64 * offset;
            if early_index < 0 || late_index >= sbr.len() as i64 {
                return Err(CandidateErrorV1::JitterDfeSpan);
            }
            early.push(sbr[early_index as usize]);
            late.push(sbr[late_index as usize]);
        }
        early
            .iter()
            .zip(late.iter())
            .map(|(e, l)| (l - e) * samples_per_ui as f64 / 2.0)
            .collect()
    } else {
        let mut sampling_offset = (cursor_index + 1) % samples_per_ui;
        if sampling_offset <= 1 {
            sampling_offset += samples_per_ui;
        }
        let early_start = sampling_offset - 2;
        let late_start = sampling_offset;
        let early: Vec<f64> = sbr
            .iter()
            .skip(early_start)
            .step_by(samples_per_ui)
            .copied()
            .collect();
        let late: Vec<f64> = sbr
            .iter()
            .skip(late_start)
            .step_by(samples_per_ui)
            .copied()
            .collect();
        let length = early.len().min(late.len());
        early
            .iter()
            .take(length)
            .zip(late.iter().take(length))
            .map(|(e, l)| (l - e) * samples_per_ui as f64 / 2.0)
            .collect()
    };
    let Some(num_ui) = num_ui else {
        return Ok(result);
    };
    if num_ui < 1 {
        return Err(CandidateErrorV1::JitterNumUi);
    }
    let mut padded = result;
    if padded.len() < num_ui {
        padded.resize(num_ui, 0.0);
    }
    padded.truncate(num_ui);
    Ok(padded)
}

/// Port of `_jitter_sigma`.
pub fn jitter_sigma_v1(
    sbr: &[f64],
    cursor_index: usize,
    samples_per_ui: usize,
    a_dd: f64,
    sigma_rj: f64,
    sigma_x: f64,
    dfe_tap_count: i64,
    limit_to_dfe_span: bool,
) -> Result<f64, CandidateErrorV1> {
    let h_j = jitter_response_v1(
        sbr,
        cursor_index,
        samples_per_ui,
        dfe_tap_count,
        limit_to_dfe_span,
        None,
    )?;
    let norm_j = h_j.iter().map(|value| value * value).sum::<f64>().sqrt();
    let norm_ad = (a_dd * a_dd + sigma_rj * sigma_rj).sqrt();
    Ok(norm_ad * sigma_x * norm_j)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn pulse() -> Vec<f64> {
        (0..200)
            .map(|index| {
                let i = index as f64;
                (-(i - 80.0) * (i - 80.0) / 300.0).exp() * (i * 0.3).sin() + 0.05
            })
            .collect()
    }

    #[test]
    fn bin_size_and_bbn() {
        assert_eq!(r480_pdf_bin_size_v1(0.1, 1e-3, false), 1e-4);
        assert_eq!(r480_pdf_bin_size_v1(0.1, 1e-3, true), 1e-3);
        assert_eq!(r480_bbn_q_factor_v1(false, 3.5).expect("none"), None);
        assert_eq!(r480_bbn_q_factor_v1(true, 3.5).expect("q"), Some(3.5));
        assert!(r480_bbn_q_factor_v1(true, -1.0).is_err());
        assert!(r480_bbn_q_factor_v1(true, f64::NAN).is_err());
    }

    #[test]
    fn cannot_improve_strict() {
        assert!(!cannot_improve_fom_v1(0.5, 0.1, None));
        assert!(!cannot_improve_fom_v1(0.5, 0.0, Some(10.0)));
        assert!(cannot_improve_fom_v1(0.5, 0.1, Some(14.0)));
        assert!(!cannot_improve_fom_v1(0.5, 0.1, Some(13.0)));
    }

    #[test]
    fn candidate_ber_q() {
        let q = candidate_ber_q_v1(0.0, 1e-4);
        assert!((q - 3.71901648545571).abs() < 1e-9);
        assert_eq!(candidate_ber_q_v1(3.8, 1e-4), 3.8);
    }

    #[test]
    fn dfe_bounds_fixed_and_floating() {
        let pulse = pulse();
        let fixed = DfeCandidateParamsV1 {
            ndfe: 2,
            bmax: vec![0.5, 0.5],
            bmin: vec![-0.5, -0.5],
            floating_dfe: false,
            n_bmax: 2,
            n_bf: 1,
            n_bg: 1,
            bmaxg: 0.3,
        };
        let (count, maximum, _minimum, locations) =
            dfe_candidate_bounds_v1(&pulse, 80, 8, &fixed).expect("fixed");
        assert_eq!(count, 2);
        assert_eq!(maximum, vec![0.5, 0.5]);
        assert!(locations.is_empty());
        let floating = DfeCandidateParamsV1 {
            ndfe: 1,
            bmax: vec![0.5],
            bmin: vec![-0.5],
            floating_dfe: true,
            n_bmax: 4,
            n_bf: 1,
            n_bg: 1,
            bmaxg: 0.3,
        };
        let (count, maximum, minimum, locations) =
            dfe_candidate_bounds_v1(&pulse, 80, 8, &floating).expect("floating");
        assert_eq!(count, 4);
        assert_eq!(maximum.len(), 4);
        assert_eq!(minimum.len(), 4);
        assert_eq!(locations.len(), 1);
    }

    #[test]
    fn jitter_response_and_sigma() {
        let pulse = pulse();
        let response = jitter_response_v1(&pulse, 80, 8, 2, false, None).expect("jitter");
        assert!(!response.is_empty());
        let limited = jitter_response_v1(&pulse, 80, 8, 2, true, None).expect("limited");
        assert_eq!(limited.len(), 4);
        let padded = jitter_response_v1(&pulse, 80, 8, 2, true, Some(10)).expect("padded");
        assert_eq!(padded.len(), 10);
        assert!(jitter_response_v1(&pulse, 80, 8, 2, true, Some(0)).is_err());
        let sigma = jitter_sigma_v1(&pulse, 80, 8, 0.4, 1e-4, 0.03, 2, false).expect("sigma");
        assert!(sigma.is_finite() && sigma > 0.0);
    }

    #[test]
    fn policy_string_is_fixed() {
        assert_eq!(
            CANDIDATE_HELPERS_POLICY_V1,
            "sipi.p5-04q.candidate-helpers-v1.reject-bounds-jitter",
        );
    }
}
