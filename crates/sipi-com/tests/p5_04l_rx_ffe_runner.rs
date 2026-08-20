//! External-only RX FFE cross-check runner (P5-04l).
//!
//! Runs apply_rx_ffe / force_rx_ffe on JSON inputs and reports the
//! results. Ignored by default; external-custody tooling only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_com::{RX_FFE_POLICY_V1, apply_rx_ffe_v1, force_floating_rx_ffe_v1, force_rx_ffe_v1};

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
        println!("usage: p5_04l_rx_ffe_runner --input <json> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");
    let mut output = serde_json::json!({ "policy": RX_FFE_POLICY_V1 });
    if let Some(case) = value.get("apply") {
        let filtered = apply_rx_ffe_v1(
            &f64s(&case["taps"]),
            case["precursor_count"].as_u64().expect("pc") as usize,
            case["samples_per_ui"].as_u64().expect("spu") as usize,
            &f64s(&case["waveform"]),
        )
        .expect("filtered");
        output["apply"] = serde_json::json!({ "filtered": filtered });
    }
    if let Some(case) = value.get("force") {
        let result = force_rx_ffe_v1(
            &f64s(&case["waveform"]),
            case["cursor_index"].as_u64().expect("cursor") as usize,
            case["precursor_count"].as_u64().expect("pc") as usize,
            case["postcursor_count"].as_u64().expect("post") as usize,
            case["samples_per_ui"].as_u64().expect("spu") as usize,
            case["dfe_first_max"].as_f64().unwrap_or(0.0),
            case["unity_cursor"].as_bool().unwrap_or(false),
            case["tap_step"].as_f64().unwrap_or(0.0),
            case["return_filtered"].as_bool().unwrap_or(true),
        )
        .expect("forced");
        output["force"] = serde_json::json!({
            "taps": result.taps(),
            "filtered": result.filtered(),
            "matrix": result.matrix(),
        });
    }
    if let Some(case) = value.get("force_floating") {
        let (result, locations) = force_floating_rx_ffe_v1(
            &f64s(&case["waveform"]),
            case["cursor_index"].as_u64().expect("cursor") as usize,
            case["precursor_count"].as_u64().expect("pc") as usize,
            case["fixed_postcursor_count"].as_u64().expect("fixed_post") as usize,
            case["maximum_postcursor_count"].as_u64().expect("max_post") as usize,
            case["samples_per_ui"].as_u64().expect("spu") as usize,
            case["dfe_first_max"].as_f64().unwrap_or(0.0),
            case["unity_cursor"].as_bool().unwrap_or(false),
            case["tap_step"].as_f64().unwrap_or(0.0),
            case["floating_start"].as_u64().expect("floating_start") as usize,
            case["taps_per_bank"].as_u64().expect("tpb") as usize,
            case["bank_count"].as_u64().expect("banks") as usize,
            case["coefficient_limit"].as_f64().expect("cl"),
            case["selection"].as_str().expect("selection"),
            case["return_filtered"].as_bool().unwrap_or(true),
        )
        .expect("floating");
        output["force_floating"] = serde_json::json!({
            "taps": result.taps(),
            "filtered": result.filtered(),
            "matrix": result.matrix(),
            "locations_one_based": locations,
        });
    }
    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string(&output).expect("json"));
    }
}
