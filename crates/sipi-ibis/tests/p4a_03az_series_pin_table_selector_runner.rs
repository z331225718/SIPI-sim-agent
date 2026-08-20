//! External-only typed series pin Model Selector binding cross-check runner (P4A-03az).
//!
//! Lifts one typed [Series Pin Mapping] Model Selector binding record from input parameters
//! and reports the properties for hash-only comparison against an independent reference.
//! Ignored by default; external-custody tooling only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_ibis::{
    lift_series_pin_selector_binding_record_az_v1, SERIES_PIN_TABLE_SELECTOR_BINDING_AZ_POLICY_V1,
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
        println!("usage: p4a_03az_series_pin_table_selector_runner --input <json> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");
    let pf = value.get("pin_first").and_then(|v| v.as_str()).unwrap_or("");
    let ps = value.get("pin_second").and_then(|v| v.as_str()).unwrap_or("");
    let ms = value.get("model_selector_name").and_then(|v| v.as_str()).unwrap_or("");
    let ftg = value.get("function_table_group").and_then(|v| v.as_str());

    let output = match lift_series_pin_selector_binding_record_az_v1(pf, ps, ms, ftg) {
        Ok(rec) => {
            serde_json::json!({
                "policy": SERIES_PIN_TABLE_SELECTOR_BINDING_AZ_POLICY_V1,
                "valid": true,
                "pin_first": rec.pin_first(),
                "pin_second": rec.pin_second(),
                "model_selector_name": rec.model_selector_name(),
                "function_table_group": rec.function_table_group(),
            })
        }
        Err(e) => {
            serde_json::json!({
                "policy": SERIES_PIN_TABLE_SELECTOR_BINDING_AZ_POLICY_V1,
                "valid": false,
                "lift_error": format!("{e:?}"),
            })
        }
    };

    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string_pretty(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string_pretty(&output).expect("json"));
    }
}
