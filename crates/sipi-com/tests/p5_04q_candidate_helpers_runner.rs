//! External-only candidate-helper cross-check runner (P5-04q).
//!
//! Runs r480_pdf_bin_size / r480_bbn_q_factor / cannot_improve_fom /
//! candidate_ber_q / dfe_candidate_bounds / jitter_response / jitter_sigma
//! on JSON inputs and reports the results. Ignored by default;
//! external-custody tooling only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_com::{
    cannot_improve_fom_v1, candidate_ber_q_v1, dfe_candidate_bounds_v1, jitter_response_v1,
    jitter_sigma_v1, r480_bbn_q_factor_v1, r480_pdf_bin_size_v1, DfeCandidateParamsV1,
    CANDIDATE_HELPERS_POLICY_V1,
};

fn f64s(value: &Value) -> Vec<f64> {
    value
        .as_array()
        .expect("array")
        .iter()
        .map(|item| item.as_f64().expect("f64"))
        .collect()
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
        println!("usage: p5_04q_candidate_helpers_runner --input <json> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");
    let mut output = serde_json::json!({ "policy": CANDIDATE_HELPERS_POLICY_V1 });
    if let Some(case) = value.get("pdf_bin_size") {
        output["pdf_bin_size"] = serde_json::json!(r480_pdf_bin_size_v1(
            case["available_signal_v"].as_f64().expect("asv"),
            case["bin_size"].as_f64().expect("bs"),
            case["force_pdf_bin_size"].as_bool().unwrap_or(false),
        ));
    }
    if let Some(case) = value.get("bbn_q") {
        let force = case["force_bbn_q_factor"].as_bool().unwrap_or(false);
        let q = case["bbn_q_factor"].as_f64().expect("q");
        match r480_bbn_q_factor_v1(force, q) {
            Ok(result) => output["bbn_q"] = serde_json::json!({ "ok": result }),
            Err(_) => output["bbn_q"] = serde_json::json!({ "error": "bbn-q-invalid" }),
        }
    }
    if let Some(case) = value.get("cannot_improve") {
        let best = case["best_fom_db"].as_f64();
        output["cannot_improve"] = serde_json::json!(cannot_improve_fom_v1(
            case["available_signal"].as_f64().expect("as"),
            case["sigma"].as_f64().expect("sigma"),
            best,
        ));
    }
    if let Some(case) = value.get("ber_q") {
        output["ber_q"] = serde_json::json!(candidate_ber_q_v1(
            case["noise_crest_factor"].as_f64().expect("ncf"),
            case["spec_ber"].as_f64().expect("spec_ber"),
        ));
    }
    if let Some(case) = value.get("dfe_bounds") {
        let parameters = DfeCandidateParamsV1 {
            ndfe: case["ndfe"].as_i64().expect("ndfe"),
            bmax: f64s(&case["bmax"]),
            bmin: f64s(&case["bmin"]),
            floating_dfe: case["floating_dfe"].as_bool().expect("floating"),
            n_bmax: case["n_bmax"].as_i64().expect("n_bmax"),
            n_bf: case["n_bf"].as_i64().expect("n_bf"),
            n_bg: case["n_bg"].as_i64().expect("n_bg"),
            bmaxg: case["bmaxg"].as_f64().expect("bmaxg"),
        };
        match dfe_candidate_bounds_v1(
            &f64s(&case["sbr"]),
            case["cursor_index"].as_u64().expect("ci") as usize,
            case["samples_per_ui"].as_u64().expect("spu") as usize,
            &parameters,
        ) {
            Ok((count, maximum, minimum, locations)) => {
                output["dfe_bounds"] = serde_json::json!({
                    "count": count,
                    "maximum": maximum,
                    "minimum": minimum,
                    "locations": locations,
                    "ok": true,
                });
            }
            Err(_) => output["dfe_bounds"] =
                serde_json::json!({ "ok": false, "error": "dfe-bounds-invalid" }),
        }
    }
    if let Some(case) = value.get("jitter") {
        let limited = case["limit_to_dfe_span"].as_bool().expect("limited");
        let num_ui = case["num_ui"].as_u64().map(|v| v as usize);
        match jitter_response_v1(
            &f64s(&case["sbr"]),
            case["cursor_index"].as_u64().expect("ci") as usize,
            case["samples_per_ui"].as_u64().expect("spu") as usize,
            case["dfe_tap_count"].as_i64().expect("dtc"),
            limited,
            num_ui,
        ) {
            Ok(values) => output["jitter"] = serde_json::json!({ "ok": true, "values": values }),
            Err(_) => output["jitter"] =
                serde_json::json!({ "ok": false, "error": "jitter-invalid" }),
        }
    }
    if let Some(case) = value.get("jitter_sigma") {
        match jitter_sigma_v1(
            &f64s(&case["sbr"]),
            case["cursor_index"].as_u64().expect("ci") as usize,
            case["samples_per_ui"].as_u64().expect("spu") as usize,
            case["a_dd"].as_f64().expect("a_dd"),
            case["sigma_rj"].as_f64().expect("sigma_rj"),
            case["sigma_x"].as_f64().expect("sigma_x"),
            case["dfe_tap_count"].as_i64().expect("dtc"),
            case["limit_to_dfe_span"].as_bool().expect("limited"),
        ) {
            Ok(sigma) => output["jitter_sigma"] = serde_json::json!({ "ok": true, "sigma": sigma }),
            Err(_) => output["jitter_sigma"] =
                serde_json::json!({ "ok": false, "error": "jitter-invalid" }),
        }
    }
    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string(&output).expect("json"));
    }
}
