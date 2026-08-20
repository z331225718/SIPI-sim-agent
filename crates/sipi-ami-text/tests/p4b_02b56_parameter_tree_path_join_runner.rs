//! External-only parameter tree path join cross-check runner (P4B-02b56).
//!
//! Joins path segments into a dotted path string and reports it for hash-only
//! comparison against an independent reference. Ignored by default;
//! external-custody tooling only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_ami_text::{join_parameter_tree_path_v1, PARAMETER_TREE_PATH_JOIN_POLICY_V1};

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
        println!("usage: p4b_02b56_parameter_tree_path_join_runner --input <path> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");

    let mut segments = Vec::new();
    if let Some(arr) = value.get("segments").and_then(|v| v.as_array()) {
        for item in arr {
            if let Some(segment) = item.as_str() {
                segments.push(segment.to_string());
            }
        }
    }
    let segment_refs: Vec<&str> = segments.iter().map(|s| s.as_str()).collect();

    let output = match join_parameter_tree_path_v1(&segment_refs) {
        Ok(path) => {
            serde_json::json!({
                "policy": PARAMETER_TREE_PATH_JOIN_POLICY_V1,
                "valid": true,
                "path": path,
            })
        }
        Err(e) => {
            serde_json::json!({
                "policy": PARAMETER_TREE_PATH_JOIN_POLICY_V1,
                "valid": false,
                "join_error": format!("{e:?}"),
            })
        }
    };

    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string_pretty(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string_pretty(&output).expect("json"));
    }
}
