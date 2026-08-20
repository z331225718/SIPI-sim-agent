//! External-only parameter list item index-of cross-check runner (P4B-02b110).
//!
//! Reads one JSON case {name, type, value, item}, builds the validated value,
//! locates the first trimmed item equal to the raw query item and reports the
//! index (or the fail-closed error) for hash-only comparison against an
//! independent reference. Ignored by default; external-custody tooling only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_ami_text::{
    AmiParameterValueV1, PARAMETER_LIST_INDEX_OF_POLICY_V1, ParameterListIndexOfErrorV1,
    index_of_parameter_list_item_v1,
};

pub(crate) fn main() {
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
        println!(
            "usage: p4b_02b110_parameter_list_index_of_runner --input <path> [--report <path>]"
        );
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");

    let name = value.get("name").and_then(|v| v.as_str()).unwrap_or("");
    let type_token = value.get("type").and_then(|v| v.as_str()).unwrap_or("");
    let value_token = value.get("value").and_then(|v| v.as_str()).unwrap_or("");
    let item = value.get("item").and_then(|v| v.as_str()).unwrap_or("");
    let parameter = match AmiParameterValueV1::try_new(name, type_token, value_token) {
        Ok(p) => p,
        Err(_) => {
            let output = serde_json::json!({
                "policy": PARAMETER_LIST_INDEX_OF_POLICY_V1,
                "valid": false,
                "input_error": "invalid_value",
            });
            if let Some(p) = report {
                std::fs::write(p, serde_json::to_string_pretty(&output).expect("json"))
                    .expect("write");
            } else {
                println!("{}", serde_json::to_string_pretty(&output).expect("json"));
            }
            return;
        }
    };

    let output = match index_of_parameter_list_item_v1(&parameter, item) {
        Ok(index) => serde_json::json!({
            "policy": PARAMETER_LIST_INDEX_OF_POLICY_V1,
            "valid": true,
            "index": index,
        }),
        Err(ParameterListIndexOfErrorV1::NotAList) => serde_json::json!({
            "policy": PARAMETER_LIST_INDEX_OF_POLICY_V1,
            "valid": false,
            "error": "NotAList",
        }),
        Err(ParameterListIndexOfErrorV1::MalformedList) => serde_json::json!({
            "policy": PARAMETER_LIST_INDEX_OF_POLICY_V1,
            "valid": false,
            "error": "MalformedList",
        }),
        Err(ParameterListIndexOfErrorV1::ItemNotFound) => serde_json::json!({
            "policy": PARAMETER_LIST_INDEX_OF_POLICY_V1,
            "valid": false,
            "error": "ItemNotFound",
        }),
    };
    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string_pretty(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string_pretty(&output).expect("json"));
    }
}
