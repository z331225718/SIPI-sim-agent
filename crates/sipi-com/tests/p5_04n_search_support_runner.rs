//! External-only search support cross-check runner (P5-04n).
//!
//! Runs the parameter/frequency-response helpers on JSON inputs and
//! reports the results. Ignored by default; external-custody tooling
//! only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_com::{
    CtleParamsV1, SEARCH_SUPPORT_POLICY_V1, apply_ctle_candidate_v1, ctle_frequency_response_v1,
    high_pass_candidates_v1, indexed_config_value_v1, qualified_ctle_pair_v1, selected_accm_rms_v1,
    selected_sndr_v1, system_noise_response_v1,
};

fn f64s(value: &Value) -> Vec<f64> {
    value
        .as_array()
        .expect("array")
        .iter()
        .map(|item| item.as_f64().expect("f64"))
        .collect()
}

fn i64s(value: &Value) -> Vec<i64> {
    value
        .as_array()
        .expect("array")
        .iter()
        .map(|item| item.as_i64().expect("i64"))
        .collect()
}

fn params_from_json(value: &Value) -> CtleParamsV1 {
    CtleParamsV1 {
        ctle_gdc_values: f64s(&value["ctle_gdc_values"]),
        ctle_fz: f64s(&value["ctle_fz"]),
        ctle_fp1: f64s(&value["ctle_fp1"]),
        ctle_fp2: f64s(&value["ctle_fp2"]),
        ctle_type: value["ctle_type"].as_str().expect("type").to_string(),
        f_hp: f64s(&value["f_hp"]),
        f_hp_z: f64s(&value["f_hp_z"]),
        f_hp_p: f64s(&value["f_hp_p"]),
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
        println!("usage: p5_04n_search_support_runner --input <json> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");
    let mut output = serde_json::json!({ "policy": SEARCH_SUPPORT_POLICY_V1 });
    if let Some(case) = value.get("indexed") {
        let result = indexed_config_value_v1(
            &f64s(&case["values"]),
            case["index"].as_u64().expect("index") as usize,
            "x",
        )
        .expect("indexed");
        output["indexed"] = serde_json::json!({ "value": result });
    }
    if let Some(case) = value.get("high_pass") {
        let result = high_pass_candidates_v1(
            case["ctle_type"].as_str().expect("type"),
            &f64s(&case["g_dc_hp_values"]),
        )
        .expect("candidates");
        output["high_pass"] = serde_json::json!({ "candidates": result });
    }
    if let Some(case) = value.get("qualified") {
        let gqual: Vec<Vec<f64>> = case["gqual"]
            .as_array()
            .map(|rows| rows.iter().map(f64s).collect())
            .unwrap_or_default();
        let result = qualified_ctle_pair_v1(
            case["ctle_type"].as_str().expect("type"),
            &f64s(&case["g_dc_hp_values"]),
            &f64s(&case["ctle_gdc_values"]),
            case["ctle_index"].as_u64().expect("ci") as usize,
            case["high_pass_index"].as_u64().expect("hi") as usize,
            case["gdc_min"].as_f64().unwrap_or(0.0),
            &gqual,
            &f64s(&case["g2qual"]),
        )
        .expect("qualified");
        output["qualified"] = serde_json::json!({ "admissible": result });
    }
    if let Some(case) = value.get("sndr") {
        let result = selected_sndr_v1(
            &f64s(&case["sndr"]),
            case["wc_portz"].as_bool().expect("wc"),
            case["tx_rd_sel"].as_i64().expect("tx"),
            &i64s(&case["pkg_len_select"]),
            case["package_case_index"].as_u64().expect("pkg") as usize,
        )
        .expect("sndr");
        output["sndr"] = serde_json::json!({ "value": result });
    }
    if let Some(case) = value.get("accm") {
        let result = selected_accm_rms_v1(
            &f64s(&case["ac_cm_rms"]),
            &i64s(&case["pkg_len_select"]),
            case["package_case_index"].as_u64().expect("pkg") as usize,
        )
        .expect("accm");
        output["accm"] = serde_json::json!({ "value": result });
    }
    if let Some(case) = value.get("system_noise") {
        let result = system_noise_response_v1(
            &f64s(&case["frequency"]),
            case["use_eta0_psd"].as_bool().expect("eta0"),
        );
        output["system_noise"] = serde_json::json!({ "response": result });
    }
    if let Some(case) = value.get("ctle_fd") {
        let result = ctle_frequency_response_v1(
            &f64s(&case["frequency"]),
            case["ctle_index"].as_u64().expect("ci") as usize,
            case["high_pass_index"].as_u64().expect("hi") as usize,
            case["high_pass_gain_db"].as_f64().expect("gain"),
            &params_from_json(&case["parameters"]),
        )
        .expect("fd");
        output["ctle_fd"] = serde_json::json!({
            "response": result.iter().map(|value| serde_json::json!({
                "real": value.real(),
                "imag": value.imaginary(),
            })).collect::<Vec<_>>(),
        });
    }
    if let Some(case) = value.get("ctle_td") {
        let result = apply_ctle_candidate_v1(
            &f64s(&case["impulse"]),
            case["baud_hz"].as_f64().expect("baud"),
            case["samples_per_ui"].as_u64().expect("spu") as usize,
            case["ctle_index"].as_u64().expect("ci") as usize,
            case["ctle_gain_db"].as_f64().expect("gain"),
            case["high_pass_index"].as_u64().expect("hi") as usize,
            case["high_pass_gain_db"].as_f64().expect("hp gain"),
            &params_from_json(&case["parameters"]),
        )
        .expect("td");
        output["ctle_td"] = serde_json::json!({ "filtered": result });
    }
    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string(&output).expect("json"));
    }
}
