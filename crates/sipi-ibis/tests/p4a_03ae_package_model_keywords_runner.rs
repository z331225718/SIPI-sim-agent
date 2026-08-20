//! External-only typed package model keywords cross-check runner (P4A-03ae).
//!
//! Lifts one typed [Package Model] required keywords declaration from input parameters
//! and reports the properties for hash-only comparison against an independent reference.
//! Ignored by default; external-custody tooling only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_ibis::{
    lift_package_model_keywords_v1, PACKAGE_MODEL_KEYWORDS_POLICY_V1,
};

fn str_list(value: Option<&Value>) -> Vec<String> {
    value
        .and_then(|v| v.as_array())
        .map(|arr| {
            arr.iter()
                .filter_map(|item| item.as_str().map(|s| s.to_string()))
                .collect()
        })
        .unwrap_or_default()
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
        println!("usage: p4a_03ae_package_model_keywords_runner --input <json> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");
    let pname = value.get("package_model_name").and_then(|v| v.as_str()).unwrap_or("");
    let npins = value.get("number_of_pins").and_then(|v| v.as_u64()).unwrap_or(0) as usize;
    let pins = str_list(value.get("pin_numbers"));

    let output = match lift_package_model_keywords_v1(pname, npins, pins) {
        Ok(pkg) => {
            serde_json::json!({
                "policy": PACKAGE_MODEL_KEYWORDS_POLICY_V1,
                "valid": true,
                "package_model_name": pkg.package_model_name(),
                "number_of_pins": pkg.number_of_pins(),
                "pin_numbers": pkg.pin_numbers(),
            })
        }
        Err(e) => {
            serde_json::json!({
                "policy": PACKAGE_MODEL_KEYWORDS_POLICY_V1,
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
