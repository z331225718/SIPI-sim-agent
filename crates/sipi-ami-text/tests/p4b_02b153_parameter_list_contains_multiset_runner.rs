//! External-only parameter list multiset containment cross-check runner (P4B-02b153).
//!
//! Reads one JSON case {name, type, value, query_name, query_type, query_value}, builds both
//! validated values, checks whether the query value is a multiset sub-multiset of the host and
//! reports the boolean (or the fail-closed error) for hash-only comparison against an
//! independent reference. Ignored by default; external-custody tooling only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_ami_text::{
    AmiParameterValueV1, PARAMETER_LIST_CONTAINS_MULTISET_POLICY_V1,
    ParameterListContainsMultisetErrorV1, list_contains_multiset_v1,
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
            "usage: p4b_02b153_parameter_list_contains_multiset_runner --input <path> [--report <path>]"
        );
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");

    let name = value.get("name").and_then(|v| v.as_str()).unwrap_or("");
    let type_token = value.get("type").and_then(|v| v.as_str()).unwrap_or("");
    let value_token = value.get("value").and_then(|v| v.as_str()).unwrap_or("");
    let query_name = value
        .get("query_name")
        .and_then(|v| v.as_str())
        .unwrap_or("");
    let query_type = value
        .get("query_type")
        .and_then(|v| v.as_str())
        .unwrap_or("");
    let query_value = value
        .get("query_value")
        .and_then(|v| v.as_str())
        .unwrap_or("");
    let host = match AmiParameterValueV1::try_new(name, type_token, value_token) {
        Ok(p) => p,
        Err(_) => {
            let output = serde_json::json!({
                "policy": PARAMETER_LIST_CONTAINS_MULTISET_POLICY_V1,
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
    let query = match AmiParameterValueV1::try_new(query_name, query_type, query_value) {
        Ok(p) => p,
        Err(_) => {
            let output = serde_json::json!({
                "policy": PARAMETER_LIST_CONTAINS_MULTISET_POLICY_V1,
                "valid": false,
                "input_error": "invalid_query_value",
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

    let output = match list_contains_multiset_v1(&host, &query) {
        Ok(contains) => serde_json::json!({
            "policy": PARAMETER_LIST_CONTAINS_MULTISET_POLICY_V1,
            "valid": true,
            "contains": contains,
        }),
        Err(ParameterListContainsMultisetErrorV1::NotAList) => serde_json::json!({
            "policy": PARAMETER_LIST_CONTAINS_MULTISET_POLICY_V1,
            "valid": false,
            "error": "NotAList",
        }),
        Err(ParameterListContainsMultisetErrorV1::MalformedList) => serde_json::json!({
            "policy": PARAMETER_LIST_CONTAINS_MULTISET_POLICY_V1,
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
