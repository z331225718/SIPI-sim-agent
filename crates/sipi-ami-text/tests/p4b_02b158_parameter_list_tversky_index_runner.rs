//! External-only parameter list Tversky index cross-check runner (P4B-02b158).
//!
//! Reads one JSON case {name, type, value, other_name, other_type, other_value, alpha, beta},
//! builds both validated values, computes the Tversky index of their distinct trimmed item
//! sets with the given non-negative parameters and reports the ratio formatted with 12
//! decimals (or the fail-closed error) for hash-only comparison against an independent
//! reference. Ignored by default; external-custody tooling only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_ami_text::{
    AmiParameterValueV1, PARAMETER_LIST_TVERSKY_INDEX_POLICY_V1, ParameterListTverskyIndexErrorV1,
    list_tversky_index_v1,
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
            "usage: p4b_02b158_parameter_list_tversky_index_runner --input <path> [--report <path>]"
        );
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");

    let name = value.get("name").and_then(|v| v.as_str()).unwrap_or("");
    let type_token = value.get("type").and_then(|v| v.as_str()).unwrap_or("");
    let value_token = value.get("value").and_then(|v| v.as_str()).unwrap_or("");
    let other_name = value
        .get("other_name")
        .and_then(|v| v.as_str())
        .unwrap_or("");
    let other_type = value
        .get("other_type")
        .and_then(|v| v.as_str())
        .unwrap_or("");
    let other_value = value
        .get("other_value")
        .and_then(|v| v.as_str())
        .unwrap_or("");
    let alpha = value.get("alpha").and_then(|v| v.as_f64()).unwrap_or(1.0);
    let beta = value.get("beta").and_then(|v| v.as_f64()).unwrap_or(1.0);
    let left = match AmiParameterValueV1::try_new(name, type_token, value_token) {
        Ok(p) => p,
        Err(_) => {
            let output = serde_json::json!({
                "policy": PARAMETER_LIST_TVERSKY_INDEX_POLICY_V1,
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
    let right = match AmiParameterValueV1::try_new(other_name, other_type, other_value) {
        Ok(p) => p,
        Err(_) => {
            let output = serde_json::json!({
                "policy": PARAMETER_LIST_TVERSKY_INDEX_POLICY_V1,
                "valid": false,
                "input_error": "invalid_other_value",
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

    let output = match list_tversky_index_v1(&left, &right, alpha, beta) {
        Ok(index) => serde_json::json!({
            "policy": PARAMETER_LIST_TVERSKY_INDEX_POLICY_V1,
            "valid": true,
            "index": format!("{index:.12}"),
        }),
        Err(ParameterListTverskyIndexErrorV1::NotAList) => serde_json::json!({
            "policy": PARAMETER_LIST_TVERSKY_INDEX_POLICY_V1,
            "valid": false,
            "error": "NotAList",
        }),
        Err(ParameterListTverskyIndexErrorV1::MalformedList) => serde_json::json!({
            "policy": PARAMETER_LIST_TVERSKY_INDEX_POLICY_V1,
            "valid": false,
            "error": "MalformedList",
        }),
        Err(ParameterListTverskyIndexErrorV1::InvalidParameters) => serde_json::json!({
            "policy": PARAMETER_LIST_TVERSKY_INDEX_POLICY_V1,
            "valid": false,
            "error": "InvalidParameters",
        }),
    };
    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string_pretty(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string_pretty(&output).expect("json"));
    }
}
