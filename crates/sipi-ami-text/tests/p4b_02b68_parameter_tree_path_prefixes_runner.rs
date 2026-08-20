//! External-only parameter tree path prefix enumeration cross-check runner (P4B-02b68).
//!
//! Enumerates every non-empty prefix of a canonical path and reports them for
//! hash-only comparison against an independent reference. Ignored by default;
//! external-custody tooling only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_ami_text::{
    enumerate_parameter_tree_path_prefixes_v1, PARAMETER_TREE_PATH_PREFIXES_POLICY_V1,
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
        println!("usage: p4b_02b68_parameter_tree_path_prefixes_runner --input <path> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");

    let mut path = Vec::new();
    if let Some(arr) = value.get("path").and_then(|v| v.as_array()) {
        path.extend(arr.iter().filter_map(|v| v.as_str().map(|s| s.to_string())));
    }

    let output = match enumerate_parameter_tree_path_prefixes_v1(&path) {
        Ok(prefixes) => {
            let prefixes_json: Vec<Value> = prefixes
                .iter()
                .map(|p| {
                    Value::Array(p.iter().map(|s| Value::String(s.clone())).collect())
                })
                .collect();
            serde_json::json!({
                "policy": PARAMETER_TREE_PATH_PREFIXES_POLICY_V1,
                "valid": true,
                "prefixes": Value::Array(prefixes_json),
            })
        }
        Err(e) => {
            serde_json::json!({
                "policy": PARAMETER_TREE_PATH_PREFIXES_POLICY_V1,
                "valid": false,
                "prefix_error": format!("{e:?}"),
            })
        }
    };

    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string_pretty(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string_pretty(&output).expect("json"));
    }
}
