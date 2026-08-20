//! External-only parameter tree relative path cross-check runner (P4B-02b66).
//!
//! Derives the relative path of one canonical path with respect to an ancestor
//! and reports it for hash-only comparison against an independent reference.
//! Ignored by default; external-custody tooling only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_ami_text::{PARAMETER_TREE_RELATIVE_PATH_POLICY_V1, relative_parameter_tree_path_v1};

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
            "usage: p4b_02b66_parameter_tree_relative_path_runner --input <path> [--report <path>]"
        );
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");

    let mut ancestor = Vec::new();
    if let Some(arr) = value.get("ancestor").and_then(|v| v.as_array()) {
        ancestor.extend(arr.iter().filter_map(|v| v.as_str().map(|s| s.to_string())));
    }
    let mut path = Vec::new();
    if let Some(arr) = value.get("path").and_then(|v| v.as_array()) {
        path.extend(arr.iter().filter_map(|v| v.as_str().map(|s| s.to_string())));
    }

    let output = match relative_parameter_tree_path_v1(&ancestor, &path) {
        Ok(relative) => {
            let relative_json: Vec<Value> =
                relative.iter().map(|s| Value::String(s.clone())).collect();
            serde_json::json!({
                "policy": PARAMETER_TREE_RELATIVE_PATH_POLICY_V1,
                "valid": true,
                "relative": Value::Array(relative_json),
            })
        }
        Err(e) => {
            serde_json::json!({
                "policy": PARAMETER_TREE_RELATIVE_PATH_POLICY_V1,
                "valid": false,
                "relative_error": format!("{e:?}"),
            })
        }
    };

    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string_pretty(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string_pretty(&output).expect("json"));
    }
}
