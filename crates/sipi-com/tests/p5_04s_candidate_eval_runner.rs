//! External-only candidate-evaluation cross-check runner (P5-04s).
//!
//! Runs evaluate_candidate_v1 / c2m_candidate_fom_v1 on a JSON input and
//! reports the selected result or the fail-closed error. Ignored by default;
//! external-custody tooling only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_com::{
    evaluate_candidate_v1, CandidateEvalOptionsV1, CandidateEvalParamsV1,
    CANDIDATE_EVAL_POLICY_V1,
};

fn f64s(value: &Value) -> Vec<f64> {
    value.as_array().expect("array").iter().map(|i| i.as_f64().expect("f64")).collect()
}
fn i64s(value: &Value) -> Vec<i64> {
    value.as_array().expect("array").iter().map(|i| i.as_i64().expect("i64")).collect()
}

fn parameters(value: &Value) -> CandidateEvalParamsV1 {
    CandidateEvalParamsV1 {
        samples_per_ui: value["samples_per_ui"].as_u64().expect("spu") as usize,
        r_lm: value["r_lm"].as_f64().expect("rlm"),
        levels: value["levels"].as_u64().expect("lv") as usize,
        sigma_x: value["sigma_x"].as_f64().expect("sx"),
        dfe_delta: value["dfe_delta"].as_f64().expect("dfe_delta"),
        n_tail_start: value["n_tail_start"].as_i64().expect("nts"),
        b_float_rss_max: value["b_float_rss_max"].as_f64().expect("brss"),
        a_dd: value["a_dd"].as_f64().expect("add"),
        sigma_rj: value["sigma_rj"].as_f64().expect("srj"),
        t_o: value["t_o"].as_f64().expect("to"),
        min_veo_test: value["min_veo_test"].as_f64().expect("mvt"),
        noise_crest_factor: value["noise_crest_factor"].as_f64().expect("ncf"),
        spec_ber: value["spec_ber"].as_f64().expect("sb"),
        samples_for_c2m: value["samples_for_c2m"].as_u64().expect("sfc") as usize,
        ql: value["ql"].as_f64().expect("ql"),
        floating_dfe: value["floating_dfe"].as_bool().expect("fd"),
        ndfe: value["ndfe"].as_i64().expect("ndfe"),
        n_bmax: value["n_bmax"].as_i64().expect("nbmax"),
        n_bf: value["n_bf"].as_i64().expect("nbf"),
        n_bg: value["n_bg"].as_i64().expect("nbg"),
        bmaxg: value["bmaxg"].as_f64().expect("bmaxg"),
        bmax: f64s(&value["bmax"]),
        bmin: f64s(&value["bmin"]),
    }
}

fn options(value: &Value) -> CandidateEvalOptionsV1 {
    CandidateEvalOptionsV1 {
        snr_txw_c0: value["snr_txw_c0"].as_bool().expect("st0"),
        wc_portz: value["wc_portz"].as_bool().expect("wcz"),
        tx_rd_sel: value["tx_rd_sel"].as_i64().expect("trs"),
        pkg_len_select: i64s(&value["pkg_len_select"]),
        sndr: f64s(&value["sndr"]),
        limit_jitter_contrib_to_dfe_span: value["limit_jitter_contrib_to_dfe_span"].as_bool().expect("lj"),
        force_pdf_bin_size: value["force_pdf_bin_size"].as_bool().expect("fps"),
        bin_size: value["bin_size"].as_f64().expect("bs"),
        force_bbn_q_factor: value["force_bbn_q_factor"].as_bool().expect("fbq"),
        bbn_q_factor: value["bbn_q_factor"].as_f64().expect("bq"),
        histogram_window_weight: value["histogram_window_weight"].as_str().expect("hww").to_string(),
    }
}

fn main() {
    let mut input = None;
    let mut report = None;
    let mut args = std::env::args().skip(1);
    while let Some(argument) = args.next() {
        let mut value = || args.next().expect("argument value");
        match argument.as_str() {
            "--input" => input = Some(PathBuf::from(value())),
            "--report" => report = Some(PathBuf::from(value())),
            other => panic!("unknown argument: {other}"),
        }
    }
    let Some(input) = input else {
        println!("usage: p5_04s_candidate_eval_runner --input <json> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");
    let c = &value["candidate"];
    let params = parameters(&c["parameters"]);
    let opts = options(&c["options"]);
    let sbr = f64s(&c["sbr"]);
    let tx_taps = f64s(&c["tx_taps"]);
    let tx_src = i64s(&c["tx_source_indices"]);
    let best_fom = c["best_fom_db"].as_f64();
    let package_case_index = c["package_case_index"].as_u64().unwrap_or(0) as usize;
    let itick = c["itick"].as_i64().unwrap_or(0);
    let retain = c["retain_non_improving"].as_bool().unwrap_or(false);
    let result = evaluate_candidate_v1(
        &sbr,
        best_fom,
        c["cursor_index"].as_u64().expect("ci") as usize,
        c["ctle_index"].as_i64().expect("cti"),
        c["ctle_gain_db"].as_f64().expect("ctg"),
        c["high_pass_index"].as_i64().expect("hpi"),
        c["high_pass_gain_db"].as_f64().expect("hpg"),
        &tx_taps,
        c["precursor_count"].as_u64().expect("pc") as usize,
        c["tx_grid_index"].as_i64().expect("tgi"),
        &tx_src,
        c["sigma_n_v"].as_f64().expect("sn"),
        c["sigma_ne_v"].as_f64().expect("sne"),
        c["sigma_xt_v"].as_f64().expect("sxt"),
        &params,
        &opts,
        package_case_index,
        itick,
        retain,
    );
    let output = match result {
        Ok(Some(res)) => serde_json::json!({
            "policy": CANDIDATE_EVAL_POLICY_V1,
            "ok": true,
            "has_result": true,
            "fom_db": res.fom_db,
            "cursor_index": res.cursor_index,
            "available_signal_v": res.available_signal_v,
            "sigma_tx_v": res.sigma_tx_v,
            "dfe_taps": res.dfe_taps,
            "dfe_max": res.dfe_max,
            "dfe_min": res.dfe_min,
            "floating_dfe_locations": res.floating_dfe_locations,
            "h_j": res.h_j,
        }),
        Ok(None) => serde_json::json!({
            "policy": CANDIDATE_EVAL_POLICY_V1,
            "ok": true,
            "has_result": false,
        }),
        Err(err) => serde_json::json!({
            "policy": CANDIDATE_EVAL_POLICY_V1,
            "ok": false,
            "error": format!("{err:?}"),
        }),
    };
    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string(&output).expect("json"));
    }
}
