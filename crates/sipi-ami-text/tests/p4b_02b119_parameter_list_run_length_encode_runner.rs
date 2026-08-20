//! External-only parameter list run-length encoding cross-check runner (P4B-02b119).
//!
//! Reads one JSON case {name, type, value}, builds the validated value,
//! run-length encodes the trimmed items and reports the (item, length) pairs
//! (or the fail-closed error) for hash-only comparison against an independent
//! reference. Ignored by default; external-custody tooling only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_ami_text::{
    run_length_encode_parameter_list_v1, AmiParameterValueV1,
    ParameterListRunLengthEncodeErrorV1, PARAMETER_LIST_RUN_LENGTH_ENCODE_POLICY_V1,
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
        println!("usage: p4b_02b119_parameter_list_run_length_encode_runner --input <path> [--report <path>]");
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
                "policy": PARAMETER_LIST_RUN_LENGTH_ENCODE_POLICY_V1,
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

    let output = match run_length_encode_parameter_list_v1(&parameter) {
        Ok(runs) => serde_json::json!({
            "policy": PARAMETER_LIST_RUN_LENGTH_ENCODE_POLICY_V1,
            "valid": true,
            "runs": runs,
        }),
        Err(ParameterListRunLengthEncodeErrorV1::NotAList) => serde_json::json!({
            "policy": PARAMETER_LIST_RUN_LENGTH_ENCODE_POLICY_V1,
            "valid": false,
            "error": "NotAList",
        }),
        Err(ParameterListRunLengthEncodeErrorV1::MalformedList) => serde_json::json!({
            "policy": PARAMETER_LIST_RUN_LENGTH_ENCODE_POLICY_V1,
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
