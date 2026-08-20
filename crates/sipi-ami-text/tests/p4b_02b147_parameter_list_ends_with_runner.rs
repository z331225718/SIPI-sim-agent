//! External-only parameter list ends-with cross-check runner (P4B-02b147).
//!
//! Reads one JSON case {name, type, value, suffix_name, suffix_type, suffix_value}, builds both
//! validated values, checks whether the value's trimmed items end with the suffix's trimmed
//! items and reports the boolean (or the fail-closed error) for hash-only comparison against an
//! independent reference. Ignored by default; external-custody tooling only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_ami_text::{
    list_ends_with_v1, AmiParameterValueV1, ParameterListEndsWithErrorV1,
    PARAMETER_LIST_ENDS_WITH_POLICY_V1,
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
        println!("usage: p4b_02b147_parameter_list_ends_with_runner --input <path> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");

    let name = value.get("name").and_then(|v| v.as_str()).unwrap_or("");
    let type_token = value.get("type").and_then(|v| v.as_str()).unwrap_or("");
    let value_token = value.get("value").and_then(|v| v.as_str()).unwrap_or("");
    let suffix_name = value.get("suffix_name").and_then(|v| v.as_str()).unwrap_or("");
    let suffix_type = value.get("suffix_type").and_then(|v| v.as_str()).unwrap_or("");
    let suffix_value = value.get("suffix_value").and_then(|v| v.as_str()).unwrap_or("");
    let main = match AmiParameterValueV1::try_new(name, type_token, value_token) {
        Ok(p) => p,
        Err(_) => {
            let output = serde_json::json!({
                "policy": PARAMETER_LIST_ENDS_WITH_POLICY_V1,
                "valid": false,
                "input_error": "invalid_value",
            });
            if let Some(p) = report {
                std::fs::write(p, serde_json::to_string_pretty(&output).expect("json")).expect("write");
            } else {
                println!("{}", serde_json::to_string_pretty(&output).expect("json"));
            }
            return;
        }
    };
    let suffix = match AmiParameterValueV1::try_new(suffix_name, suffix_type, suffix_value) {
        Ok(p) => p,
        Err(_) => {
            let output = serde_json::json!({
                "policy": PARAMETER_LIST_ENDS_WITH_POLICY_V1,
                "valid": false,
                "input_error": "invalid_suffix_value",
            });
            if let Some(p) = report {
                std::fs::write(p, serde_json::to_string_pretty(&output).expect("json")).expect("write");
            } else {
                println!("{}", serde_json::to_string_pretty(&output).expect("json"));
            }
            return;
        }
    };

    let output = match list_ends_with_v1(&main, &suffix) {
        Ok(ends) => serde_json::json!({
            "policy": PARAMETER_LIST_ENDS_WITH_POLICY_V1,
            "valid": true,
            "ends": ends,
        }),
        Err(ParameterListEndsWithErrorV1::NotAList) => serde_json::json!({
            "policy": PARAMETER_LIST_ENDS_WITH_POLICY_V1,
            "valid": false,
            "error": "NotAList",
        }),
        Err(ParameterListEndsWithErrorV1::MalformedList) => serde_json::json!({
            "policy": PARAMETER_LIST_ENDS_WITH_POLICY_V1,
            "valid": false,
            "error": "MalformedList",
        }),
    };
    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string_pretty(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string_pretty(&output).expect("json"));
    }
}
