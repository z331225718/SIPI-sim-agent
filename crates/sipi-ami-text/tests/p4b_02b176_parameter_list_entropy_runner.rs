//! External-only parameter list Shannon entropy cross-check runner (P4B-02b176).
//!
//! Reads one JSON case {name, type, value}, builds the validated value, computes the Shannon
//! entropy in bits of the trimmed-item frequency distribution and reports it formatted with
//! 12 decimals (or the fail-closed error) for hash-only comparison against an independent
//! reference. Ignored by default; external-custody tooling only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_ami_text::{
    AmiParameterValueV1, PARAMETER_LIST_ENTROPY_POLICY_V1, ParameterListEntropyErrorV1,
    parameter_list_entropy_v1,
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
            "usage: p4b_02b176_parameter_list_entropy_runner --input <path> [--report <path>]"
        );
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");

    let name = value.get("name").and_then(|v| v.as_str()).unwrap_or("");
    let type_token = value.get("type").and_then(|v| v.as_str()).unwrap_or("");
    let value_token = value.get("value").and_then(|v| v.as_str()).unwrap_or("");
    let parameter = match AmiParameterValueV1::try_new(name, type_token, value_token) {
        Ok(p) => p,
        Err(_) => {
            let output = serde_json::json!({
                "policy": PARAMETER_LIST_ENTROPY_POLICY_V1,
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

    let output = match parameter_list_entropy_v1(&parameter) {
        Ok(entropy) => serde_json::json!({
            "policy": PARAMETER_LIST_ENTROPY_POLICY_V1,
            "valid": true,
            "entropy": format!("{entropy:.12}"),
        }),
        Err(ParameterListEntropyErrorV1::NotAList) => serde_json::json!({
            "policy": PARAMETER_LIST_ENTROPY_POLICY_V1,
            "valid": false,
            "error": "NotAList",
        }),
        Err(ParameterListEntropyErrorV1::MalformedList) => serde_json::json!({
            "policy": PARAMETER_LIST_ENTROPY_POLICY_V1,
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
