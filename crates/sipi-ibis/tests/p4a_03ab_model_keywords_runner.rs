//! External-only typed model declaration keywords cross-check runner (P4A-03ab).
//!
//! Validates IBIS [Model] required sub-keywords for a given Model_type from input parameters
//! and reports the validation result for hash-only comparison against an independent reference.
//! Ignored by default; external-custody tooling only.
use std::path::PathBuf;
use serde_json::Value;
use sipi_ibis::{
    validate_model_keywords_v1, ModelSubKeywordsV1, ModelTypeV1,
    MODEL_DECLARATION_KEYWORDS_POLICY_V1,
};
fn parse_model_type(s: &str) -> ModelTypeV1 {
    match s.trim().to_ascii_lowercase().as_str() {
        "input" => ModelTypeV1::Input,
        "output" => ModelTypeV1::Output,
        "io" | "i/o" => ModelTypeV1::IO,
        "3state" | "3-state" => ModelTypeV1::ThreeState,
        _ => ModelTypeV1::Output,
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
        println!("usage: p4a_03ab_model_keywords_runner --input <json> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");
    let mtype_str = value.get("model_type").and_then(|v| v.as_str()).unwrap_or("Output");
    let model_type = parse_model_type(mtype_str);
    let sub_kw = ModelSubKeywordsV1 {
        has_pullup: value.get("has_pullup").and_then(|v| v.as_bool()).unwrap_or(false),
        has_pulldown: value.get("has_pulldown").and_then(|v| v.as_bool()).unwrap_or(false),
        has_gnd_clamp: value.get("has_gnd_clamp").and_then(|v| v.as_bool()).unwrap_or(false),
        has_power_clamp: value.get("has_power_clamp").and_then(|v| v.as_bool()).unwrap_or(false),
    };
    let output = match validate_model_keywords_v1(model_type.clone(), &sub_kw) {
        Ok(_) => {
            serde_json::json!({
                "policy": MODEL_DECLARATION_KEYWORDS_POLICY_V1,
                "valid": true,
                "model_type": format!("{model_type:?}"),
            })
        }
        Err(e) => {
            serde_json::json!({
                "policy": MODEL_DECLARATION_KEYWORDS_POLICY_V1,
                "valid": false,
                "validation_error": format!("{e:?}"),
            })
        }
    };
    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string_pretty(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string_pretty(&output).expect("json"));
    }
}
