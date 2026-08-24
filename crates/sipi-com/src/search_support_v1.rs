//! Equalizer-search support surface (port of `equalization/search.py`
//! parameter and frequency-response helpers).
//!
//! Ported from agent-com (MIT source, P5-04n source map): indexed
//! config values, CL120d high-pass candidates and the G_Qual/G2_Qual
//! admissible pair matrix, SNDR / AC_CM_RMS package selection, the
//! optional eta_0 source-noise shaping, the CTLE frequency response
//! (CL120d / CL120e high-pass variants), and the time-domain CTLE
//! candidate application. The receiver filter chain, crosstalk noise
//! integration, and the search loop itself remain separate scopes.

use sipi_types::Complex64;

use crate::equalizer_frontend_v1::{complex_div, complex_mul, td_ctle_v1};

/// Explicit scope policy of the search support stage.
pub const SEARCH_SUPPORT_POLICY_V1: &str =
    "sipi.p5-04n.search-support-v1.params-frequency-candidates";

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum SearchErrorV1 {
    IndexedConfigValue,
    Cl120dEmptyGains,
    GqualShape,
    PackageCaseIndex,
    SelectedValue,
    InvalidControls,
}

/// Port of `_indexed_config_value`: broadcast a scalar selection.
pub fn indexed_config_value_v1(
    values: &[f64],
    index: usize,
    name: &str,
) -> Result<f64, SearchErrorV1> {
    let _ = name;
    if values.len() == 1 {
        return Ok(values[0]);
    }
    if index >= values.len() {
        return Err(SearchErrorV1::IndexedConfigValue);
    }
    Ok(values[index])
}

/// Port of `_high_pass_candidates`.
pub fn high_pass_candidates_v1(
    ctle_type: &str,
    g_dc_hp_values: &[f64],
) -> Result<Vec<(usize, f64)>, SearchErrorV1> {
    if ctle_type != "CL120d" {
        return Ok(vec![(0, 0.0)]);
    }
    if g_dc_hp_values.is_empty() {
        return Err(SearchErrorV1::Cl120dEmptyGains);
    }
    Ok(g_dc_hp_values
        .iter()
        .enumerate()
        .map(|(index, gain)| (index, *gain))
        .collect())
}

/// Port of Agent-COM's `_selected_package_case`.
///
/// `pkg_len_select` stores one-based workbook package-row selections while
/// `package_case_index` is the zero-based outer-loop ordinal.  Both candidate
/// and receiver-noise consumers use this single checked conversion so they
/// cannot silently select different package rows.
pub fn selected_package_case_v1(
    pkg_len_select: &[i64],
    package_case_index: usize,
) -> Result<usize, SearchErrorV1> {
    if pkg_len_select.is_empty() || package_case_index >= pkg_len_select.len() {
        return Err(SearchErrorV1::PackageCaseIndex);
    }
    let selected = pkg_len_select[package_case_index];
    if selected < 1 {
        return Err(SearchErrorV1::SelectedValue);
    }
    usize::try_from(selected - 1).map_err(|_| SearchErrorV1::SelectedValue)
}

/// Port of `_qualified_ctle_pair` (CL120d G_Qual/G2_Qual matrix).
pub fn qualified_ctle_pair_v1(
    ctle_type: &str,
    g_dc_hp_values: &[f64],
    ctle_gdc_values: &[f64],
    ctle_index: usize,
    high_pass_index: usize,
    gdc_min: f64,
    gqual: &[Vec<f64>],
    g2qual: &[f64],
) -> Result<bool, SearchErrorV1> {
    if ctle_type != "CL120d" {
        return Ok(true);
    }
    let high_pass = indexed_config_value_v1(g_dc_hp_values, high_pass_index, "g_DC_HP_values")?;
    let dc_gain = indexed_config_value_v1(ctle_gdc_values, ctle_index, "ctle_gdc_values")?;
    if gdc_min != 0.0 && dc_gain + high_pass > gdc_min {
        return Ok(false);
    }
    if gqual.is_empty() && g2qual.is_empty() {
        return Ok(true);
    }
    if gqual.len() != g2qual.len() || gqual.iter().any(|row| row.len() != 2) {
        return Err(SearchErrorV1::GqualShape);
    }
    // argsort(g2qual)[::-1]: descending threshold order (stable).
    let mut order: Vec<usize> = (0..g2qual.len()).collect();
    order.sort_by(|a, b| {
        g2qual[*b]
            .partial_cmp(&g2qual[*a])
            .unwrap_or(std::cmp::Ordering::Equal)
    });
    for (row, threshold_index) in order.iter().enumerate() {
        let threshold = g2qual[*threshold_index];
        let upper = if row == 0 {
            threshold + f64::EPSILON
        } else {
            g2qual[order[row - 1]]
        };
        let lower = threshold;
        if lower <= high_pass && high_pass < upper {
            let range = &gqual[*threshold_index];
            let (high, low) = if range[0] >= range[1] {
                (range[0], range[1])
            } else {
                (range[1], range[0])
            };
            return Ok(low <= dc_gain && dc_gain < high);
        }
    }
    Ok(false)
}

/// Port of `_selected_sndr`.
pub fn selected_sndr_v1(
    sndr: &[f64],
    wc_portz: bool,
    tx_rd_sel: i64,
    pkg_len_select: &[i64],
    package_case_index: usize,
) -> Result<f64, SearchErrorV1> {
    let index = if wc_portz {
        let zero_based = tx_rd_sel
            .checked_sub(1)
            .ok_or(SearchErrorV1::SelectedValue)?;
        usize::try_from(zero_based).map_err(|_| SearchErrorV1::SelectedValue)?
    } else {
        selected_package_case_v1(pkg_len_select, package_case_index)?
    };
    if index >= sndr.len() {
        return Err(SearchErrorV1::SelectedValue);
    }
    Ok(sndr[index])
}

/// Port of `_selected_accm_rms`.
pub fn selected_accm_rms_v1(
    ac_cm_rms: &[f64],
    pkg_len_select: &[i64],
    package_case_index: usize,
) -> Result<f64, SearchErrorV1> {
    let source_index = selected_package_case_v1(pkg_len_select, package_case_index)?;
    if source_index >= ac_cm_rms.len() || ac_cm_rms[source_index] < 0.0 {
        return Err(SearchErrorV1::SelectedValue);
    }
    Ok(ac_cm_rms[source_index])
}

/// Port of `_r480_system_noise_response` (normalized sinc squared).
pub fn system_noise_response_v1(frequency: &[f64], use_eta0_psd: bool) -> Vec<f64> {
    if !use_eta0_psd {
        return vec![1.0; frequency.len()];
    }
    let f_spike_hz = 1e9;
    frequency
        .iter()
        .map(|value| {
            let x = std::f64::consts::SQRT_2 * (value - f_spike_hz) / f_spike_hz;
            let sinc = if x == 0.0 {
                1.0
            } else {
                (std::f64::consts::PI * x).sin() / (std::f64::consts::PI * x)
            };
            sinc * sinc
        })
        .collect()
}

/// The CTLE parameter surface used by the frequency/time responses.
#[derive(Clone, Debug, PartialEq)]
pub struct CtleParamsV1 {
    pub ctle_gdc_values: Vec<f64>,
    pub ctle_fz: Vec<f64>,
    pub ctle_fp1: Vec<f64>,
    pub ctle_fp2: Vec<f64>,
    pub ctle_type: String,
    pub f_hp: Vec<f64>,
    pub f_hp_z: Vec<f64>,
    pub f_hp_p: Vec<f64>,
}

/// Port of `_ctle_frequency_response` (complex; CL120d/CL120e variants).
pub fn ctle_frequency_response_v1(
    frequency: &[f64],
    ctle_index: usize,
    high_pass_index: usize,
    high_pass_gain_db: f64,
    parameters: &CtleParamsV1,
) -> Result<Vec<Complex64>, SearchErrorV1> {
    let gain = indexed_config_value_v1(&parameters.ctle_gdc_values, ctle_index, "ctle_gdc_values")?;
    let fz = indexed_config_value_v1(&parameters.ctle_fz, ctle_index, "CTLE_fz")?;
    let fp1 = indexed_config_value_v1(&parameters.ctle_fp1, ctle_index, "CTLE_fp1")?;
    let fp2 = indexed_config_value_v1(&parameters.ctle_fp2, ctle_index, "CTLE_fp2")?;
    let base: Vec<Complex64> = frequency
        .iter()
        .map(|value| {
            let numerator =
                Complex64::try_new(10.0_f64.powf(gain / 20.0), *value / fz).expect("complex");
            let d1 = Complex64::try_new(1.0, *value / fp1).expect("complex");
            let d2 = Complex64::try_new(1.0, *value / fp2).expect("complex");
            complex_div(numerator, complex_mul(d1, d2))
        })
        .collect();
    if parameters.ctle_type == "CL120d" {
        let high_pass = indexed_config_value_v1(&parameters.f_hp, high_pass_index, "f_HP")?;
        let shaped: Vec<Complex64> = frequency
            .iter()
            .zip(base.iter())
            .map(|(value, entry)| {
                let numerator =
                    Complex64::try_new(10.0_f64.powf(high_pass_gain_db / 20.0), *value / high_pass)
                        .expect("complex");
                let denominator = Complex64::try_new(1.0, *value / high_pass).expect("complex");
                complex_mul(*entry, complex_div(numerator, denominator))
            })
            .collect();
        return Ok(shaped);
    }
    if parameters.ctle_type == "CL120e" {
        let high_pass_zero = indexed_config_value_v1(&parameters.f_hp_z, ctle_index, "f_HP_Z")?;
        let high_pass_pole = indexed_config_value_v1(&parameters.f_hp_p, ctle_index, "f_HP_P")?;
        let shaped: Vec<Complex64> = frequency
            .iter()
            .zip(base.iter())
            .map(|(value, entry)| {
                let numerator = Complex64::try_new(1.0, *value / high_pass_zero).expect("complex");
                let denominator =
                    Complex64::try_new(1.0, *value / high_pass_pole).expect("complex");
                complex_mul(*entry, complex_div(numerator, denominator))
            })
            .collect();
        return Ok(shaped);
    }
    Ok(base)
}

/// Port of `_apply_ctle_candidate` (time-domain; reuses td_ctle_v1).
pub fn apply_ctle_candidate_v1(
    impulse: &[f64],
    baud_hz: f64,
    samples_per_ui: usize,
    ctle_index: usize,
    ctle_gain_db: f64,
    high_pass_index: usize,
    high_pass_gain_db: f64,
    parameters: &CtleParamsV1,
) -> Result<Vec<f64>, SearchErrorV1> {
    let fz = indexed_config_value_v1(&parameters.ctle_fz, ctle_index, "CTLE_fz")?;
    let fp1 = indexed_config_value_v1(&parameters.ctle_fp1, ctle_index, "CTLE_fp1")?;
    let fp2 = indexed_config_value_v1(&parameters.ctle_fp2, ctle_index, "CTLE_fp2")?;
    let result = td_ctle_v1(impulse, baud_hz, fz, fp1, fp2, ctle_gain_db, samples_per_ui)
        .map_err(|_| SearchErrorV1::InvalidControls)?;
    if parameters.ctle_type == "CL120d" {
        let high_pass = indexed_config_value_v1(&parameters.f_hp, high_pass_index, "f_HP")?;
        return td_ctle_v1(
            &result,
            baud_hz,
            high_pass,
            high_pass,
            1e100,
            high_pass_gain_db,
            samples_per_ui,
        )
        .map_err(|_| SearchErrorV1::InvalidControls);
    }
    if parameters.ctle_type == "CL120e" {
        let high_pass_zero = indexed_config_value_v1(&parameters.f_hp_z, ctle_index, "f_HP_Z")?;
        let high_pass_pole = indexed_config_value_v1(&parameters.f_hp_p, ctle_index, "f_HP_P")?;
        return td_ctle_v1(
            &result,
            baud_hz,
            high_pass_zero,
            high_pass_pole,
            1e99,
            0.0,
            samples_per_ui,
        )
        .map_err(|_| SearchErrorV1::InvalidControls);
    }
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn indexed_scalar_and_range() {
        assert_eq!(
            indexed_config_value_v1(&[2.5], 7, "x").expect("scalar"),
            2.5
        );
        assert_eq!(
            indexed_config_value_v1(&[1.0, 2.0], 1, "x").expect("index"),
            2.0
        );
        assert!(indexed_config_value_v1(&[1.0, 2.0], 2, "x").is_err());
    }

    #[test]
    fn high_pass_candidates_branches() {
        assert_eq!(
            high_pass_candidates_v1("CL120e", &[]).expect("e"),
            vec![(0, 0.0)]
        );
        let gains = high_pass_candidates_v1("CL120d", &[0.0, -3.0, -6.0]).expect("d");
        assert_eq!(gains.len(), 3);
        assert_eq!(gains[1], (1, -3.0));
        assert!(high_pass_candidates_v1("CL120d", &[]).is_err());
    }

    #[test]
    fn qualified_pair_gdc_ceiling_and_table() {
        let gqual = vec![vec![0.0, 6.0], vec![-6.0, 0.0]];
        let g2qual = vec![0.0, -6.0];
        // g2qual descending: [0.0, -6.0]; high_pass = -3 -> row 1 range [-6, 0]
        let ok = qualified_ctle_pair_v1(
            "CL120d",
            &[0.0, -3.0, -6.0],
            &[-3.0],
            0,
            1,
            0.0,
            &gqual,
            &g2qual,
        )
        .expect("qualified");
        assert!(ok);
        // dc_gain outside the admissible range -> false
        let outside = qualified_ctle_pair_v1(
            "CL120d",
            &[0.0, -3.0, -6.0],
            &[3.0],
            0,
            1,
            0.0,
            &gqual,
            &g2qual,
        )
        .expect("outside");
        assert!(!outside);
        // dc_gain + high_pass = 0.0 > 0.0? no; ceiling 0.0 sentinel off
        let ceiling = qualified_ctle_pair_v1("CL120d", &[0.0, -3.0], &[4.0], 0, 1, 1.0, &[], &[])
            .expect("ceiling");
        // 4.0 + (-3.0) = 1.0 > 1.0? no (equality admissible); dc 4 < 0? -> no table, true
        assert!(ceiling);
        let over = qualified_ctle_pair_v1("CL120d", &[0.0, -3.0], &[5.0], 0, 1, 1.0, &[], &[])
            .expect("over");
        assert!(!over);
        assert!(
            qualified_ctle_pair_v1(
                "CL120d",
                &[0.0],
                &[1.0],
                0,
                0,
                0.0,
                &[vec![1.0]],
                &[0.0, 1.0]
            )
            .is_err()
        );
    }

    #[test]
    fn selected_sndr_and_accm() {
        assert_eq!(selected_package_case_v1(&[2, 3], 0).expect("package"), 1);
        assert_eq!(selected_package_case_v1(&[2, 3], 1).expect("package"), 2);
        assert!(selected_package_case_v1(&[], 0).is_err());
        assert!(selected_package_case_v1(&[0], 0).is_err());
        assert!(selected_package_case_v1(&[1], 1).is_err());
        assert_eq!(
            selected_package_case_v1(&vec![1; 4097], 0).expect("long package vector"),
            0
        );
        let sndr = selected_sndr_v1(&[30.0, 28.0, 32.0], false, 1, &[2, 3], 0).expect("sndr");
        assert_eq!(sndr, 28.0);
        let wc = selected_sndr_v1(&[30.0, 28.0, 32.0], true, 3, &[1], 0).expect("wc");
        assert_eq!(wc, 32.0);
        assert!(selected_sndr_v1(&[30.0], true, i64::MIN, &[1], 0).is_err());
        assert!(selected_sndr_v1(&[30.0], true, 5, &[1], 0).is_err());
        let accm = selected_accm_rms_v1(&[0.1, 0.2], &[2], 0).expect("accm");
        assert_eq!(accm, 0.2);
        assert!(selected_accm_rms_v1(&[0.1], &[2], 0).is_err());
    }

    #[test]
    fn package_case_order_matches_pinned_outer_loop() {
        // The Python orchestration enumerates selections in source order;
        // sparse/repeated one-based rows must remain observable to both
        // consumers rather than being sorted or deduplicated.
        let selections = [3, 1, 3];
        let sndr = [10.0, 20.0, 30.0];
        let accm = [0.1, 0.2, 0.3];
        for (case_index, expected) in [2usize, 0, 2].into_iter().enumerate() {
            assert_eq!(
                selected_sndr_v1(&sndr, false, 1, &selections, case_index).expect("SNDR"),
                sndr[expected]
            );
            assert_eq!(
                selected_accm_rms_v1(&accm, &selections, case_index).expect("ACCM"),
                accm[expected]
            );
        }
    }

    #[test]
    fn system_noise_response() {
        let off = system_noise_response_v1(&[0.0, 1e9, 2e9], false);
        assert_eq!(off, vec![1.0, 1.0, 1.0]);
        let on = system_noise_response_v1(&[1e9], true);
        assert!((on[0] - 1.0).abs() < 1e-12);
    }

    #[test]
    fn ctle_frequency_and_time_domain() {
        let parameters = CtleParamsV1 {
            ctle_gdc_values: vec![6.0],
            ctle_fz: vec![10e9],
            ctle_fp1: vec![30e9],
            ctle_fp2: vec![40e9],
            ctle_type: "CL120e".to_string(),
            f_hp: vec![1.0],
            f_hp_z: vec![5e9],
            f_hp_p: vec![1e9],
        };
        let frequencies: Vec<f64> = (0..4).map(|index| index as f64 * 5e9).collect();
        let response =
            ctle_frequency_response_v1(&frequencies, 0, 0, 0.0, &parameters).expect("fd");
        assert_eq!(response.len(), 4);
        let impulse: Vec<f64> = (0..32)
            .map(|index| (-(index as f64 - 16.0) * (index as f64 - 16.0) / 60.0).exp())
            .collect();
        let filtered = apply_ctle_candidate_v1(&impulse, 53.125e9, 4, 0, 6.0, 0, 0.0, &parameters)
            .expect("td");
        assert_eq!(filtered.len(), impulse.len());
        assert!(filtered.iter().all(|value| value.is_finite()));
    }

    #[test]
    fn policy_string_is_fixed() {
        assert_eq!(
            SEARCH_SUPPORT_POLICY_V1,
            "sipi.p5-04n.search-support-v1.params-frequency-candidates",
        );
    }
}
