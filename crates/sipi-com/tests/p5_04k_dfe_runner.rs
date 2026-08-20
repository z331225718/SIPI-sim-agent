//! External-only DFE bank cross-check runner (P5-04k).
//!
//! Runs apply_tail_rss_bounds / clip_dfe / find_dfe_bank_locations /
//! apply_dfe_bank on JSON inputs and reports the results. Ignored by
//! default; external-custody tooling only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_com::{
    apply_dfe_bank_v1, apply_tail_rss_bounds_v1, clip_dfe_v1, find_dfe_bank_locations_v1,
    DFE_POLICY_V1,
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
        println!("usage: p5_04k_dfe_runner --input <json> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");
    let mut output = serde_json::json!({ "policy": DFE_POLICY_V1 });
    if let Some(case) = value.get("tail_rss") {
        let taps = f64s(&case["taps"]);
        let maximum = f64s(&case["maximum"]);
        let minimum = f64s(&case["minimum"]);
        let start = case["tail_start_index"].as_u64().map(|v| v as usize);
        let bounds = apply_tail_rss_bounds_v1(
            &taps,
            &maximum,
            &minimum,
            start,
            case["rss_max"].as_f64().expect("rss_max"),
        )
        .expect("bounds");
        output["tail_rss"] = serde_json::json!({
            "tail_rss": bounds.tail_rss(),
            "maximum": bounds.maximum(),
            "minimum": bounds.minimum(),
        });
    }
    if let Some(case) = value.get("clip") {
        let clipped = clip_dfe_v1(
            &f64s(&case["values"]),
            &f64s(&case["maximum"]),
            &f64s(&case["minimum"]),
        )
        .expect("clip");
        output["clip"] = serde_json::json!({ "clipped": clipped });
    }
    if let Some(case) = value.get("bank_locations") {
        let locations = find_dfe_bank_locations_v1(
            &f64s(&case["hisi"]),
            case["start_index"].as_u64().expect("start") as usize,
            case["end_index"].as_u64().expect("end") as usize,
            case["taps_per_bank"].as_u64().expect("tpb") as usize,
            case["cursor"].as_f64().expect("cursor"),
            case["coefficient_limit"].as_f64().expect("cl"),
            case["bank_count"].as_u64().expect("banks") as usize,
        )
        .expect("locations");
        output["bank_locations"] = serde_json::json!({ "locations": locations });
    }
    if let Some(case) = value.get("apply_bank") {
        let result = apply_dfe_bank_v1(
            &f64s(&case["hisi"]),
            &f64s(&case["hisi_ref"]),
            case["start_index"].as_u64().expect("start") as usize,
            case["tap_count"].as_u64().expect("taps") as usize,
            case["cursor"].as_f64().expect("cursor"),
            case["coefficient_limit"].as_f64().expect("cl"),
            case["quantization_step"].as_f64().unwrap_or(0.0),
        )
        .expect("bank");
        output["apply_bank"] = serde_json::json!({
            "residual": result.residual(),
            "reference": result.reference(),
            "coefficients": result.coefficients(),
        });
    }
    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string(&output).expect("json"));
    }
}
