//! External-only equalizer front-end cross-check runner (P5-04i).
//!
//! Runs cursor_sample_index / fd_ctle / td_ctle on JSON inputs and
//! reports the results. Ignored by default; external-custody tooling
//! only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_com::{
    cursor_sample_index_v1, fd_ctle_v1, td_ctle_v1, EQUALIZER_FRONTEND_POLICY_V1,
};

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
        println!("usage: p5_04i_frontend_runner --input <json> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");
    let pulse: Vec<f64> = value["pulse"]
        .as_array()
        .expect("pulse")
        .iter()
        .map(|item| item.as_f64().expect("value"))
        .collect();
    let mut output = serde_json::json!({
        "policy": EQUALIZER_FRONTEND_POLICY_V1,
    });
    if let Some(cursor) = value.get("cursor") {
        let samples_per_ui = cursor["samples_per_ui"].as_u64().expect("spu") as usize;
        let dfe_first_max = cursor["dfe_first_max"].as_f64().unwrap_or(0.0);
        let cdr = cursor["cdr"].as_str().expect("cdr");
        let peak_start = cursor["peak_start"].as_u64().unwrap_or(0) as usize;
        let peak_stop = cursor["peak_stop"].as_u64().map(|v| v as usize);
        let sample = cursor_sample_index_v1(&pulse, samples_per_ui, dfe_first_max, cdr, peak_start, peak_stop)
            .expect("cursor");
        output["cursor"] = serde_json::json!({
            "cursor_index": sample.cursor_index(),
            "no_zero_crossing": sample.no_zero_crossing(),
            "peak_index": sample.peak_index(),
            "zero_crossing_index": sample.zero_crossing_index(),
        });
    }
    if let Some(ctle) = value.get("fd_ctle") {
        let frequencies: Vec<f64> = ctle["frequencies_hz"]
            .as_array()
            .expect("frequencies")
            .iter()
            .map(|item| item.as_f64().expect("f"))
            .collect();
        let response = fd_ctle_v1(
            &frequencies,
            ctle["baud_hz"].as_f64().expect("baud"),
            ctle["fz_multiplier"].as_f64().expect("fz"),
            ctle["fp1_multiplier"].as_f64().expect("fp1"),
            ctle["fp2_multiplier"].as_f64().expect("fp2"),
            ctle["dc_gain_db"].as_f64().expect("gain"),
        )
        .expect("fd ctle");
        output["fd_ctle"] = serde_json::json!({
            "response": response.iter().map(|value| serde_json::json!({
                "real": value.real(),
                "imag": value.imaginary(),
            })).collect::<Vec<_>>(),
        });
    }
    if let Some(ctle) = value.get("td_ctle") {
        let filtered = td_ctle_v1(
            &pulse,
            ctle["baud_hz"].as_f64().expect("baud"),
            ctle["fz_hz"].as_f64().expect("fz"),
            ctle["fp1_hz"].as_f64().expect("fp1"),
            ctle["fp2_hz"].as_f64().expect("fp2"),
            ctle["dc_gain_db"].as_f64().expect("gain"),
            ctle["samples_per_ui"].as_u64().expect("spu") as usize,
        )
        .expect("td ctle");
        output["td_ctle"] = serde_json::json!({ "filtered": filtered });
    }
    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string(&output).expect("json"));
    }
}
