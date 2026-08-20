//! External-only parameter list item removal cross-check runner (P4B-02b100).
//!
//! Reads one JSON case {name, type, value, index}, builds the validated value,
//! removes the trimmed item at the index, and reports the resulting canonical
//! list token (or the fail-closed error) for hash-only comparison against an
//! independent reference. Ignored by default; external-custody tooling only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_ami_text::{
    remove_parameter_list_item_v1, AmiParameterValueV1, ParameterListRemoveErrorV1,
    PARAMETER_LIST_REMOVE_POLICY_V1,
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
        println!("usage: p4b_02b100_parameter_list_remove_runner --input <path> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");

    let name = value.get("name").and_then(|v| v.as_str()).unwrap_or("");
    let type_token = value.get("type").and_then(|v| v.as_str()).unwrap_or("");
    let value_token = value.get("value").and_then(|v| v.as_str()).unwrap_or("");
    let index = value.get("index").and_then(|v| v.as_u64()).unwrap_or(0) as usize;
    let parameter = match AmiParameterValueV1::try_new(name, type_token, value_token) {
        Ok(p) => p,
        Err(_) => {
            let output = serde_json::json!({
                "policy": PARAMETER_LIST_REMOVE_POLICY_V1,
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

    let output = match remove_parameter_list_item_v1(&parameter, index) {
        Ok(removed) => serde_json::json!({
            "policy": PARAMETER_LIST_REMOVE_POLICY_V1,
            "valid": true,
            "removed": removed,
        }),
        Err(ParameterListRemoveErrorV1::NotAList) => serde_json::json!({
            "policy": PARAMETER_LIST_REMOVE_POLICY_V1,
            "valid": false,
            "error": "NotAList",
        }),
        Err(ParameterListRemoveErrorV1::MalformedList) => serde_json::json!({
            "policy": PARAMETER_LIST_REMOVE_POLICY_V1,
            "valid": false,
            "error": "MalformedList",
        }),
        Err(ParameterListRemoveErrorV1::IndexOutOfRange { index, item_count }) => {
            serde_json::json!({
                "policy": PARAMETER_LIST_REMOVE_POLICY_V1,
                "valid": false,
                "error": "IndexOutOfRange",
                "index": index,
                "item_count": item_count,
            })
        }
    };
    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string_pretty(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string_pretty(&output).expect("json"));
    }
}
