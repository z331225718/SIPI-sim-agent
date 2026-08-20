//! External-only parameter list item append cross-check runner (P4B-02b101).
//!
//! Reads one JSON case {name, type, value, new_item}, builds the validated
//! value, appends the trimmed new item, and reports the resulting canonical
//! list token (or the fail-closed error) for hash-only comparison against an
//! independent reference. Ignored by default; external-custody tooling only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_ami_text::{
    append_parameter_list_item_v1, AmiParameterValueV1, ParameterListAppendErrorV1,
    PARAMETER_LIST_APPEND_POLICY_V1,
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
        println!("usage: p4b_02b101_parameter_list_append_runner --input <path> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");

    let name = value.get("name").and_then(|v| v.as_str()).unwrap_or("");
    let type_token = value.get("type").and_then(|v| v.as_str()).unwrap_or("");
    let value_token = value.get("value").and_then(|v| v.as_str()).unwrap_or("");
    let new_item = value.get("new_item").and_then(|v| v.as_str()).unwrap_or("");
    let parameter = match AmiParameterValueV1::try_new(name, type_token, value_token) {
        Ok(p) => p,
        Err(_) => {
            let output = serde_json::json!({
                "policy": PARAMETER_LIST_APPEND_POLICY_V1,
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

    let output = match append_parameter_list_item_v1(&parameter, new_item) {
        Ok(appended) => serde_json::json!({
            "policy": PARAMETER_LIST_APPEND_POLICY_V1,
            "valid": true,
            "appended": appended,
        }),
        Err(ParameterListAppendErrorV1::NotAList) => serde_json::json!({
            "policy": PARAMETER_LIST_APPEND_POLICY_V1,
            "valid": false,
            "error": "NotAList",
        }),
        Err(ParameterListAppendErrorV1::MalformedList) => serde_json::json!({
            "policy": PARAMETER_LIST_APPEND_POLICY_V1,
            "valid": false,
            "error": "MalformedList",
        }),
        Err(ParameterListAppendErrorV1::EmptyNewItem) => serde_json::json!({
            "policy": PARAMETER_LIST_APPEND_POLICY_V1,
            "valid": false,
            "error": "EmptyNewItem",
        }),
    };
    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string_pretty(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string_pretty(&output).expect("json"));
    }
}
