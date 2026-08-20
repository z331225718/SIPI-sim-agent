//! External-only parameter list Dice index cross-check runner (P4B-02b155).
//!
//! Reads one JSON case {name, type, value, other_name, other_type, other_value}, builds both
//! validated values, computes the Sorensen-Dice index of their distinct trimmed item sets and
//! reports the ratio formatted with 12 decimals (or the fail-closed error) for hash-only
//! comparison against an independent reference. Ignored by default; external-custody tooling
//! only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_ami_text::{
    list_dice_index_v1, AmiParameterValueV1, ParameterListDiceIndexErrorV1,
    PARAMETER_LIST_DICE_INDEX_POLICY_V1,
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
        println!("usage: p4b_02b155_parameter_list_dice_index_runner --input <path> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");

    let name = value.get("name").and_then(|v| v.as_str()).unwrap_or("");
    let type_token = value.get("type").and_then(|v| v.as_str()).unwrap_or("");
    let value_token = value.get("value").and_then(|v| v.as_str()).unwrap_or("");
    let other_name = value.get("other_name").and_then(|v| v.as_str()).unwrap_or("");
    let other_type = value.get("other_type").and_then(|v| v.as_str()).unwrap_or("");
    let other_value = value.get("other_value").and_then(|v| v.as_str()).unwrap_or("");
    let left = match AmiParameterValueV1::try_new(name, type_token, value_token) {
        Ok(p) => p,
        Err(_) => {
            let output = serde_json::json!({
                "policy": PARAMETER_LIST_DICE_INDEX_POLICY_V1,
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
    let right = match AmiParameterValueV1::try_new(other_name, other_type, other_value) {
        Ok(p) => p,
        Err(_) => {
            let output = serde_json::json!({
                "policy": PARAMETER_LIST_DICE_INDEX_POLICY_V1,
                "valid": false,
                "input_error": "invalid_other_value",
            });
            if let Some(p) = report {
                std::fs::write(p, serde_json::to_string_pretty(&output).expect("json")).expect("write");
            } else {
                println!("{}", serde_json::to_string_pretty(&output).expect("json"));
            }
            return;
        }
    };

    let output = match list_dice_index_v1(&left, &right) {
        Ok(index) => serde_json::json!({
            "policy": PARAMETER_LIST_DICE_INDEX_POLICY_V1,
            "valid": true,
            "index": format!("{index:.12}"),
        }),
        Err(ParameterListDiceIndexErrorV1::NotAList) => serde_json::json!({
            "policy": PARAMETER_LIST_DICE_INDEX_POLICY_V1,
            "valid": false,
            "error": "NotAList",
        }),
        Err(ParameterListDiceIndexErrorV1::MalformedList) => serde_json::json!({
            "policy": PARAMETER_LIST_DICE_INDEX_POLICY_V1,
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
