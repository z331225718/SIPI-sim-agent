//! COM parameter surface resolver core (P5-05f).
//!
//! Resolves a merged `ComParametersV1` DTO (P5-05e) into typed COM execution
//! controls (`ComChainControlsV1`, P5-06f).
//! Fail-closed: missing consumed keys, unexpected parameter value types, or
//! invalid control scalar bounds are strictly rejected.

use std::collections::BTreeMap;

use crate::com_chain_v1::{ComChainControlsV1, ComChainErrorV1};
use crate::com_parameters_v1::ComParametersV1;
use crate::value_consumption_v1::ResolvedDefaultV1;

/// Scope policy of the COM parameter surface resolver core.
pub const COM_PARAMETER_RESOLVER_POLICY_V1: &str =
    "sipi.p5-05f.com-parameter-resolver-v1.dto-to-controls";

/// Fail-closed errors when resolving COM parameters into controls.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ComParameterResolverErrorV1 {
    EmptyDto,
    MissingKey(String),
    InvalidType(String),
    ChainControls(ComChainErrorV1),
}

impl From<ComChainErrorV1> for ComParameterResolverErrorV1 {
    fn from(err: ComChainErrorV1) -> Self {
        ComParameterResolverErrorV1::ChainControls(err)
    }
}

fn get_scalar(
    map: &BTreeMap<String, ResolvedDefaultV1>,
    keys: &[&str],
) -> Result<f64, ComParameterResolverErrorV1> {
    for key in keys {
        if let Some(val) = map.get(*key) {
            return match val {
                ResolvedDefaultV1::Scalar(v) => Ok(*v),
                ResolvedDefaultV1::Vector(v) if v.len() == 1 => Ok(v[0]),
                _ => Err(ComParameterResolverErrorV1::InvalidType((*key).to_string())),
            };
        }
    }
    Err(ComParameterResolverErrorV1::MissingKey(keys[0].to_string()))
}

fn get_vector(
    map: &BTreeMap<String, ResolvedDefaultV1>,
    keys: &[&str],
) -> Result<Vec<f64>, ComParameterResolverErrorV1> {
    for key in keys {
        if let Some(val) = map.get(*key) {
            return match val {
                ResolvedDefaultV1::Vector(v) => Ok(v.clone()),
                ResolvedDefaultV1::Scalar(v) => Ok(vec![*v]),
                _ => Err(ComParameterResolverErrorV1::InvalidType((*key).to_string())),
            };
        }
    }
    Err(ComParameterResolverErrorV1::MissingKey(keys[0].to_string()))
}

fn get_string(
    map: &BTreeMap<String, ResolvedDefaultV1>,
    keys: &[&str],
    default_str: &str,
) -> String {
    for key in keys {
        if let Some(ResolvedDefaultV1::String(s)) = map.get(*key) {
            return s.clone();
        }
    }
    default_str.to_string()
}

/// Resolve a merged COM DTO into validated ComChainControlsV1.
pub fn resolve_com_parameter_controls_v1(
    dto: &ComParametersV1,
) -> Result<ComChainControlsV1, ComParameterResolverErrorV1> {
    let map = dto.consumed();
    if map.is_empty() {
        return Err(ComParameterResolverErrorV1::EmptyDto);
    }

    let samples_per_ui = get_scalar(map, &["samples_per_ui", "SAMP_PER_UI", "N_v"])? as usize;
    let levels = get_scalar(map, &["LEVELS", "PAM_LEVELS", "levels"])? as u32;
    let bin_size = get_scalar(map, &["bin_size", "BIN_SIZE"])?;
    let dfe_first_max = get_scalar(map, &["dfe_first_max", "DFE_FIRST_MAX"]).unwrap_or(0.0);
    let cdr = get_string(map, &["cdr", "CDR"], "MM");
    let peak_start = get_scalar(map, &["peak_start", "PEAK_START"]).unwrap_or(16.0) as usize;
    let peak_stop = get_scalar(map, &["peak_stop", "PEAK_STOP"])
        .ok()
        .map(|v| v as usize);

    let dfe_max = get_vector(map, &["dfe_max", "DFE_MAX"]).unwrap_or_default();
    let dfe_min = get_vector(map, &["dfe_min", "DFE_MIN"]).unwrap_or_default();
    let dfe_tap_count =
        get_scalar(map, &["dfe_tap_count", "DFE_TAP_COUNT"]).unwrap_or(dfe_max.len() as f64) as i64;
    let dfe_step = get_scalar(map, &["dfe_step", "DFE_STEP"]).unwrap_or(0.0);
    let floating_dfe = get_scalar(map, &["floating_dfe", "FLOATING_DFE"])
        .map(|v| v != 0.0)
        .unwrap_or(false);

    let available_signal_v = get_scalar(map, &["A_v", "AVAILABLE_SIGNAL"])?;
    let r_lm_ohm = get_scalar(map, &["R_LM", "R_LM_OHM"])?;
    let tx_snr_db = get_scalar(map, &["SNR_TX", "TX_SNR_DB"])?;
    let sigma_x = get_scalar(map, &["sigma_X", "SIGMA_X"])?;
    let sigma_rj_s = get_scalar(map, &["sigma_RJ", "SIGMA_RJ"])?;
    let jitter_response = get_vector(map, &["h_J", "JITTER_RESPONSE"])?;
    let sigma_n_v = get_scalar(map, &["sigma_N", "SIGMA_N"])?;
    let amplitude_dd_v = get_scalar(map, &["A_DD", "AMPLITUDE_DD"])?;
    let spec_ber = get_scalar(map, &["spec_ber", "SPEC_BER"])?;
    let noise_crest_factor =
        get_scalar(map, &["noise_crest_factor", "NOISE_CREST_FACTOR"]).unwrap_or(0.0);
    let sigma_ne_v = get_scalar(map, &["sigma_ne", "SIGMA_NE"]).unwrap_or(0.0);
    let pass_threshold_db =
        get_scalar(map, &["pass_threshold_db", "PASS_THRESHOLD"]).unwrap_or(3.0);
    let t_o_s = get_scalar(map, &["t_o_s", "T_O_S"]).unwrap_or(0.0);

    let controls = ComChainControlsV1::try_new(
        samples_per_ui,
        levels,
        bin_size,
        dfe_first_max,
        cdr,
        peak_start,
        peak_stop,
        dfe_tap_count,
        dfe_max,
        dfe_min,
        dfe_step,
        floating_dfe,
        None,
        available_signal_v,
        r_lm_ohm,
        tx_snr_db,
        sigma_x,
        sigma_rj_s,
        jitter_response,
        sigma_n_v,
        amplitude_dd_v,
        spec_ber,
        noise_crest_factor,
        sigma_ne_v,
        None,
        None,
        None,
        pass_threshold_db,
        t_o_s,
        None,
    )?;

    Ok(controls)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::com_parameters_v1::merge_com_parameters_v1;

    fn sample_dto() -> ComParametersV1 {
        let mut map = BTreeMap::new();
        map.insert("samples_per_ui".to_string(), ResolvedDefaultV1::Scalar(8.0));
        map.insert("LEVELS".to_string(), ResolvedDefaultV1::Scalar(4.0));
        map.insert("bin_size".to_string(), ResolvedDefaultV1::Scalar(0.01));
        map.insert("A_v".to_string(), ResolvedDefaultV1::Scalar(0.5));
        map.insert("R_LM".to_string(), ResolvedDefaultV1::Scalar(50.0));
        map.insert("SNR_TX".to_string(), ResolvedDefaultV1::Scalar(30.0));
        map.insert("sigma_X".to_string(), ResolvedDefaultV1::Scalar(0.03));
        map.insert("sigma_RJ".to_string(), ResolvedDefaultV1::Scalar(1e-4));
        map.insert(
            "h_J".to_string(),
            ResolvedDefaultV1::Vector(vec![0.3, 0.5, 0.2]),
        );
        map.insert("sigma_N".to_string(), ResolvedDefaultV1::Scalar(0.01));
        map.insert("A_DD".to_string(), ResolvedDefaultV1::Scalar(0.4));
        map.insert("spec_ber".to_string(), ResolvedDefaultV1::Scalar(1e-4));
        let keys: Vec<String> = map.keys().cloned().collect();
        merge_com_parameters_v1(&keys, &map, &BTreeMap::new(), &[]).expect("dto")
    }

    #[test]
    fn policy_fixed() {
        assert_eq!(
            COM_PARAMETER_RESOLVER_POLICY_V1,
            "sipi.p5-05f.com-parameter-resolver-v1.dto-to-controls"
        );
    }

    #[test]
    fn resolves_valid_dto_to_controls() {
        let dto = sample_dto();
        let controls = resolve_com_parameter_controls_v1(&dto).expect("controls");
        let _ = controls;
    }

    #[test]
    fn rejects_empty_dto() {
        let empty_dto =
            merge_com_parameters_v1(&["x".to_string()], &BTreeMap::new(), &BTreeMap::new(), &[])
                .unwrap_err();
        let _ = empty_dto;
    }

    #[test]
    fn rejects_missing_required_key() {
        let mut map = BTreeMap::new();
        map.insert("samples_per_ui".to_string(), ResolvedDefaultV1::Scalar(8.0));
        let dto =
            merge_com_parameters_v1(&["samples_per_ui".to_string()], &map, &BTreeMap::new(), &[])
                .unwrap();
        assert!(matches!(
            resolve_com_parameter_controls_v1(&dto),
            Err(ComParameterResolverErrorV1::MissingKey(_))
        ));
    }

    #[test]
    fn rejects_invalid_type() {
        let mut map = BTreeMap::new();
        map.insert(
            "samples_per_ui".to_string(),
            ResolvedDefaultV1::String("eight".to_string()),
        );
        let dto =
            merge_com_parameters_v1(&["samples_per_ui".to_string()], &map, &BTreeMap::new(), &[])
                .unwrap();
        assert!(matches!(
            resolve_com_parameter_controls_v1(&dto),
            Err(ComParameterResolverErrorV1::InvalidType(_))
        ));
    }

    #[test]
    fn rejects_out_of_range_scalar() {
        let mut map = BTreeMap::new();
        map.insert("samples_per_ui".to_string(), ResolvedDefaultV1::Scalar(0.0)); // spu < 1
        map.insert("LEVELS".to_string(), ResolvedDefaultV1::Scalar(4.0));
        map.insert("bin_size".to_string(), ResolvedDefaultV1::Scalar(0.01));
        map.insert("A_v".to_string(), ResolvedDefaultV1::Scalar(0.5));
        map.insert("R_LM".to_string(), ResolvedDefaultV1::Scalar(50.0));
        map.insert("SNR_TX".to_string(), ResolvedDefaultV1::Scalar(30.0));
        map.insert("sigma_X".to_string(), ResolvedDefaultV1::Scalar(0.03));
        map.insert("sigma_RJ".to_string(), ResolvedDefaultV1::Scalar(1e-4));
        map.insert(
            "h_J".to_string(),
            ResolvedDefaultV1::Vector(vec![0.3, 0.5, 0.2]),
        );
        map.insert("sigma_N".to_string(), ResolvedDefaultV1::Scalar(0.01));
        map.insert("A_DD".to_string(), ResolvedDefaultV1::Scalar(0.4));
        map.insert("spec_ber".to_string(), ResolvedDefaultV1::Scalar(1e-4));
        let keys: Vec<String> = map.keys().cloned().collect();
        let dto = merge_com_parameters_v1(&keys, &map, &BTreeMap::new(), &[]).unwrap();
        assert!(matches!(
            resolve_com_parameter_controls_v1(&dto),
            Err(ComParameterResolverErrorV1::ChainControls(_))
        ));
    }
}
