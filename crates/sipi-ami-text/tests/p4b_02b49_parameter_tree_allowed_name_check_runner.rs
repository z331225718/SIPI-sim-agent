//! External-only parameter tree allowed-name check cross-check runner (P4B-02b49).
//!
//! Parses raw parenthesized AMI text, builds typed parameter tree hierarchies,
//! checks every distinct leaf name against a caller-supplied allowed-name set,
//! and reports the outcome for hash-only comparison against an independent
//! reference. Ignored by default; external-custody tooling only.

use std::collections::BTreeSet;
use std::path::PathBuf;

use serde_json::Value;
use sipi_ami_text::{
    build_parameter_trees_v1, check_parameter_tree_allowed_names_v1, parse_ami_text_v1,
    ParseLimitsV1, PARAMETER_TREE_ALLOWED_NAME_CHECK_POLICY_V1,
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
        println!("usage: p4b_02b49_parameter_tree_allowed_name_check_runner --input <path> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");

    let text = value.get("text").and_then(|v| v.as_str()).unwrap_or("");
    let mut allowed = BTreeSet::new();
    if let Some(allowed_json) = value.get("allowed").and_then(|v| v.as_array()) {
        for item in allowed_json {
            if let Some(name) = item.as_str() {
                allowed.insert(name.to_string());
            }
        }
    }

    let limits = ParseLimitsV1::try_new(8 * 1024 * 1024, 64, 4096, 4096).expect("limits");
    let doc = match parse_ami_text_v1(text.as_bytes(), limits) {
        Ok(d) => d,
        Err(e) => {
            let output = serde_json::json!({
                "policy": PARAMETER_TREE_ALLOWED_NAME_CHECK_POLICY_V1,
                "valid": false,
                "parse_error": format!("{e:?}"),
            });
            if let Some(p) = report {
                std::fs::write(p, serde_json::to_string_pretty(&output).expect("json")).expect("write");
            } else {
                println!("{}", serde_json::to_string_pretty(&output).expect("json"));
            }
            return;
        }
    };
    let trees = match build_parameter_trees_v1(&doc) {
        Ok(t) => t,
        Err(e) => {
            let output = serde_json::json!({
                "policy": PARAMETER_TREE_ALLOWED_NAME_CHECK_POLICY_V1,
                "valid": false,
                "build_error": format!("{e:?}"),
            });
            if let Some(p) = report {
                std::fs::write(p, serde_json::to_string_pretty(&output).expect("json")).expect("write");
            } else {
                println!("{}", serde_json::to_string_pretty(&output).expect("json"));
            }
            return;
        }
    };

    let output = match check_parameter_tree_allowed_names_v1(&trees[0], &allowed) {
        Ok(check) => {
            serde_json::json!({
                "policy": PARAMETER_TREE_ALLOWED_NAME_CHECK_POLICY_V1,
                "valid": true,
                "leaves_checked": check.leaves_checked(),
                "clean": check.is_clean(),
                "violations": check.violations(),
            })
        }
        Err(e) => {
            serde_json::json!({
                "policy": PARAMETER_TREE_ALLOWED_NAME_CHECK_POLICY_V1,
                "valid": false,
                "allowed_error": format!("{e:?}"),
            })
        }
    };

    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string_pretty(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string_pretty(&output).expect("json"));
    }
}
