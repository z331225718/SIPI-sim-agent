//! External-only C2M vertical-eye cross-check runner (P5-04r).
//!
//! Runs calculate_c2m_vertical_eye_v1 on a JSON input and reports the
//! resulting (veo_top, veo_bottom) pair or the fail-closed error. Ignored
//! by default; external-custody tooling only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_com::{C2M_EYE_POLICY_V1, DiscretePdfV1, calculate_c2m_vertical_eye_v1};

fn f64s(value: &Value) -> Vec<f64> {
    value
        .as_array()
        .expect("array")
        .iter()
        .map(|item| item.as_f64().expect("f64"))
        .collect()
}

fn pdf(value: &Value) -> DiscretePdfV1 {
    let bin_size = value["bin_size"].as_f64().expect("bin_size");
    let min_bin = value["min_bin"].as_i64().expect("min_bin");
    let probability = f64s(&value["probability"]);
    DiscretePdfV1::try_new(bin_size, min_bin, probability).expect("pdf")
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
        println!("usage: p5_04r_c2m_eye_runner --input <json> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");
    let c = &value["c2m"];
    let pulse = f64s(&c["pulse"]);
    let ne = pdf(&c["ne_noise_pdf"]);
    let cci = pdf(&c["cci_pdf"]);
    let result = calculate_c2m_vertical_eye_v1(
        &pulse,
        c["cursor_index"].as_u64().expect("ci") as usize,
        c["samples_per_ui"].as_u64().expect("spu") as usize,
        c["samples_for_c2m"].as_u64().expect("sfc") as usize,
        c["levels"].as_u64().expect("lv") as usize,
        c["bin_size"].as_f64().expect("bs"),
        c["r_lm_ohm"].as_f64().expect("rlm"),
        c["dfe_tap_count"].as_i64().expect("dtc"),
        &f64s(&c["dfe_max"]),
        &f64s(&c["dfe_min"]),
        c["dfe_step"].as_f64().expect("dstep"),
        c["sigma_rj_s"].as_f64().expect("srj"),
        c["sigma_x"].as_f64().expect("sx"),
        c["sigma_n_v"].as_f64().expect("sn"),
        c["sigma_tx_v"].as_f64().expect("stx"),
        c["ber_q"].as_f64().expect("bq"),
        &ne,
        &cci,
        c["amplitude_dd_v"].as_f64().expect("add"),
        c["spec_ber"].as_f64().expect("sb"),
        c["t_o_mui"].as_f64().expect("to"),
        c["histogram_window"].as_str().expect("hw"),
        c["ql"].as_f64().expect("ql"),
    );
    let output = match result {
        Ok((top, bottom)) => serde_json::json!({
            "policy": C2M_EYE_POLICY_V1,
            "ok": true,
            "top": top,
            "bottom": bottom,
        }),
        Err(err) => serde_json::json!({
            "policy": C2M_EYE_POLICY_V1,
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
