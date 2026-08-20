//! External-only typed model-selector / series-pin-mapping cross-check runner (P4A-03i).
//!
//! Lifts one typed [Model Selector] or [Series Pin Mapping] declaration from
//! input parameters and reports the properties for hash-only comparison against an
//! independent reference. Ignored by default; external-custody tooling only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_ibis::{
    lift_model_selector_declaration_v1, lift_series_pin_mapping_v1, ModelBranchV1,
    MODEL_SELECTOR_DECLARATION_POLICY_V1,
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
        println!("usage: p4a_03i_model_selector_runner --input <json> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");

    let output = if value.get("selector_name").is_some() {
        let sname = value["selector_name"].as_str().unwrap_or("");
        let branches = value.get("branches").and_then(|v| v.as_array()).map(|arr| {
            arr.iter()
                .map(|b| {
                    let mn = b.get("model_name").and_then(|v| v.as_str()).unwrap_or("");
                    let desc = b.get("description").and_then(|v| v.as_str()).map(|s| s.to_string());
                    ModelBranchV1::new(mn, desc)
                })
                .collect()
        }).unwrap_or_default();

        match lift_model_selector_declaration_v1(sname, branches) {
            Ok(sel) => {
                serde_json::json!({
                    "policy": MODEL_SELECTOR_DECLARATION_POLICY_V1,
                    "valid": true,
                    "kind": "selector",
                    "selector_name": sel.selector_name(),
                    "branch_count": sel.branches().len(),
                })
            }
            Err(e) => {
                serde_json::json!({
                    "policy": MODEL_SELECTOR_DECLARATION_POLICY_V1,
                    "valid": false,
                    "lift_error": format!("{e:?}"),
                })
            }
        }
    } else {
        let pf = value.get("pin_first").and_then(|v| v.as_str()).unwrap_or("");
        let ps = value.get("pin_second").and_then(|v| v.as_str()).unwrap_or("");
        let mn = value.get("model_name").and_then(|v| v.as_str()).unwrap_or("");

        match lift_series_pin_mapping_v1(pf, ps, mn) {
            Ok(map) => {
                serde_json::json!({
                    "policy": MODEL_SELECTOR_DECLARATION_POLICY_V1,
                    "valid": true,
                    "kind": "series_pin_mapping",
                    "pin_first": map.pin_first(),
                    "pin_second": map.pin_second(),
                    "model_name": map.model_name(),
                })
            }
            Err(e) => {
                serde_json::json!({
                    "policy": MODEL_SELECTOR_DECLARATION_POLICY_V1,
                    "valid": false,
                    "lift_error": format!("{e:?}"),
                })
            }
        }
    };

    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string_pretty(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string_pretty(&output).expect("json"));
    }
}
