//! External-only parameter list value join cross-check runner (P4B-02b106).
//!
//! Reads one JSON case {left: {name, type, value}, right: {name, type, value}},
//! builds the validated values, joins their trimmed items, and reports the
//! resulting canonical list token (or the fail-closed error) for hash-only
//! comparison against an independent reference. Ignored by default;
//! external-custody tooling only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_ami_text::{
    AmiParameterValueV1, PARAMETER_LIST_JOIN_POLICY_V1, ParameterListJoinErrorV1,
    join_parameter_list_values_v1,
};

fn build_value(entry: &Value) -> Option<AmiParameterValueV1> {
    let name = entry.get("name")?.as_str()?;
    let type_token = entry.get("type")?.as_str()?;
    let value_token = entry.get("value")?.as_str()?;
    AmiParameterValueV1::try_new(name, type_token, value_token).ok()
}

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
        println!("usage: p4b_02b106_parameter_list_join_runner --input <path> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");

    let left = match value.get("left").and_then(build_value) {
        Some(v) => v,
        None => {
            let output = serde_json::json!({
                "policy": PARAMETER_LIST_JOIN_POLICY_V1,
                "valid": false,
                "input_error": "invalid_left_value",
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
    let right = match value.get("right").and_then(build_value) {
        Some(v) => v,
        None => {
            let output = serde_json::json!({
                "policy": PARAMETER_LIST_JOIN_POLICY_V1,
                "valid": false,
                "input_error": "invalid_right_value",
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

    let output = match join_parameter_list_values_v1(&left, &right) {
        Ok(joined) => serde_json::json!({
            "policy": PARAMETER_LIST_JOIN_POLICY_V1,
            "valid": true,
            "joined": joined,
        }),
        Err(ParameterListJoinErrorV1::NotAList) => serde_json::json!({
            "policy": PARAMETER_LIST_JOIN_POLICY_V1,
            "valid": false,
            "error": "NotAList",
        }),
        Err(ParameterListJoinErrorV1::MalformedList) => serde_json::json!({
            "policy": PARAMETER_LIST_JOIN_POLICY_V1,
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
