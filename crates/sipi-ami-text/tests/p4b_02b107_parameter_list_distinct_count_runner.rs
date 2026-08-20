//! External-only parameter list distinct item count cross-check runner (P4B-02b107).
//!
//! Reads one JSON case {name, type, value}, builds the validated value, counts
//! its distinct trimmed items, and reports the count (or the fail-closed
//! error) for hash-only comparison against an independent reference. Ignored
//! by default; external-custody tooling only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_ami_text::{
    count_distinct_parameter_list_items_v1, AmiParameterValueV1,
    ParameterListDistinctCountErrorV1, PARAMETER_LIST_DISTINCT_COUNT_POLICY_V1,
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
        println!("usage: p4b_02b107_parameter_list_distinct_count_runner --input <path> [--report <path>]");
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
                "policy": PARAMETER_LIST_DISTINCT_COUNT_POLICY_V1,
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

    let output = match count_distinct_parameter_list_items_v1(&parameter) {
        Ok(distinct) => serde_json::json!({
            "policy": PARAMETER_LIST_DISTINCT_COUNT_POLICY_V1,
            "valid": true,
            "distinct": distinct,
        }),
        Err(ParameterListDistinctCountErrorV1::NotAList) => serde_json::json!({
            "policy": PARAMETER_LIST_DISTINCT_COUNT_POLICY_V1,
            "valid": false,
            "error": "NotAList",
        }),
        Err(ParameterListDistinctCountErrorV1::MalformedList) => serde_json::json!({
            "policy": PARAMETER_LIST_DISTINCT_COUNT_POLICY_V1,
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
