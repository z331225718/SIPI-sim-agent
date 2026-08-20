//! External-only parameter tree longest common prefix cross-check runner (P4B-02b67).
//!
//! Computes the longest common prefix of two canonical paths and reports it for
//! hash-only comparison against an independent reference. Ignored by default;
//! external-custody tooling only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_ami_text::{
    PARAMETER_TREE_LONGEST_COMMON_PREFIX_POLICY_V1, longest_common_path_prefix_v1,
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
            "usage: p4b_02b67_parameter_tree_longest_common_prefix_runner --input <path> [--report <path>]"
        );
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");

    let mut a = Vec::new();
    if let Some(arr) = value.get("a").and_then(|v| v.as_array()) {
        a.extend(arr.iter().filter_map(|v| v.as_str().map(|s| s.to_string())));
    }
    let mut b = Vec::new();
    if let Some(arr) = value.get("b").and_then(|v| v.as_array()) {
        b.extend(arr.iter().filter_map(|v| v.as_str().map(|s| s.to_string())));
    }

    let output = match longest_common_path_prefix_v1(&a, &b) {
        Ok(prefix) => {
            let prefix_json: Vec<Value> = prefix.iter().map(|s| Value::String(s.clone())).collect();
            serde_json::json!({
                "policy": PARAMETER_TREE_LONGEST_COMMON_PREFIX_POLICY_V1,
                "valid": true,
                "prefix": Value::Array(prefix_json),
            })
        }
        Err(e) => {
            serde_json::json!({
                "policy": PARAMETER_TREE_LONGEST_COMMON_PREFIX_POLICY_V1,
                "valid": false,
                "lcp_error": format!("{e:?}"),
            })
        }
    };

    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string_pretty(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string_pretty(&output).expect("json"));
    }
}
