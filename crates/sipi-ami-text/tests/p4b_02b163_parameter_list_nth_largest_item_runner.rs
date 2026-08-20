//! External-only parameter list nth-largest item cross-check runner (P4B-02b163).
//!
//! Reads one JSON case {name, type, value, nth}, builds the validated value, computes the
//! item at zero-based rank nth in descending sorted order of the trimmed items and reports
//! it (or the fail-closed error) for hash-only comparison against an independent reference.
//! Ignored by default; external-custody tooling only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_ami_text::{
    AmiParameterValueV1, PARAMETER_LIST_NTH_LARGEST_ITEM_POLICY_V1,
    ParameterListNthLargestItemErrorV1, parameter_list_nth_largest_item_v1,
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
            "usage: p4b_02b163_parameter_list_nth_largest_item_runner --input <path> [--report <path>]"
        );
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");

    let name = value.get("name").and_then(|v| v.as_str()).unwrap_or("");
    let type_token = value.get("type").and_then(|v| v.as_str()).unwrap_or("");
    let value_token = value.get("value").and_then(|v| v.as_str()).unwrap_or("");
    let nth = value.get("nth").and_then(|v| v.as_u64()).unwrap_or(0) as usize;
    let parameter = match AmiParameterValueV1::try_new(name, type_token, value_token) {
        Ok(p) => p,
        Err(_) => {
            let output = serde_json::json!({
                "policy": PARAMETER_LIST_NTH_LARGEST_ITEM_POLICY_V1,
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

    let output = match parameter_list_nth_largest_item_v1(&parameter, nth) {
        Ok(item) => serde_json::json!({
            "policy": PARAMETER_LIST_NTH_LARGEST_ITEM_POLICY_V1,
            "valid": true,
            "item": item,
        }),
        Err(ParameterListNthLargestItemErrorV1::NotAList) => serde_json::json!({
            "policy": PARAMETER_LIST_NTH_LARGEST_ITEM_POLICY_V1,
            "valid": false,
            "error": "NotAList",
        }),
        Err(ParameterListNthLargestItemErrorV1::MalformedList) => serde_json::json!({
            "policy": PARAMETER_LIST_NTH_LARGEST_ITEM_POLICY_V1,
            "valid": false,
            "error": "MalformedList",
        }),
        Err(ParameterListNthLargestItemErrorV1::IndexOutOfRange { index, item_count }) => {
            serde_json::json!({
                "policy": PARAMETER_LIST_NTH_LARGEST_ITEM_POLICY_V1,
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
