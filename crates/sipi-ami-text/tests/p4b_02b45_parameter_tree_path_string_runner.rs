//! External-only parameter tree path-string parsing cross-check runner (P4B-02b45).
//!
//! Parses a dotted path string into segments and reports them for hash-only
//! comparison against an independent reference. Ignored by default;
//! external-custody tooling only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_ami_text::{PARAMETER_TREE_PATH_STRING_POLICY_V1, parse_parameter_tree_path_string_v1};

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
            "usage: p4b_02b45_parameter_tree_path_string_runner --input <path> [--report <path>]"
        );
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");

    let path = value.get("path").and_then(|v| v.as_str()).unwrap_or("");

    let output = match parse_parameter_tree_path_string_v1(path) {
        Ok(segments) => {
            let segments_json: Vec<Value> =
                segments.iter().map(|s| Value::String(s.clone())).collect();
            serde_json::json!({
                "policy": PARAMETER_TREE_PATH_STRING_POLICY_V1,
                "valid": true,
                "segments": Value::Array(segments_json),
            })
        }
        Err(e) => {
            serde_json::json!({
                "policy": PARAMETER_TREE_PATH_STRING_POLICY_V1,
                "valid": false,
                "path_error": format!("{e:?}"),
            })
        }
    };

    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string_pretty(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string_pretty(&output).expect("json"));
    }
}
