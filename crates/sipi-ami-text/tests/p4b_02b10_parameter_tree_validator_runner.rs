//! External-only typed parameter tree validator cross-check runner (P4B-02b10).
//!
//! Parses raw parenthesized AMI text, builds typed parameter tree hierarchies,
//! validates tree structural invariants against caller limits, and reports the result
//! for hash-only comparison against an independent reference. Ignored by default; external-custody tooling only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_ami_text::{
    PARAMETER_TREE_VALIDATOR_POLICY_V1, ParseLimitsV1, TreeValidationLimitsV1,
    build_parameter_trees_v1, parse_ami_text_v1, validate_parameter_trees_v1,
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
            "usage: p4b_02b10_parameter_tree_validator_runner --input <path> [--report <path>]"
        );
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");
    let text = value.get("text").and_then(|v| v.as_str()).unwrap_or("");
    let max_depth = value
        .get("max_depth")
        .and_then(|v| v.as_u64())
        .unwrap_or(32) as usize;
    let max_leaf_tokens = value
        .get("max_leaf_tokens")
        .and_then(|v| v.as_u64())
        .unwrap_or(1024) as usize;

    let limits = ParseLimitsV1::try_new(8 * 1024 * 1024, 64, 4096, 4096).expect("limits");
    let doc = match parse_ami_text_v1(text.as_bytes(), limits) {
        Ok(d) => d,
        Err(e) => {
            let output = serde_json::json!({
                "policy": PARAMETER_TREE_VALIDATOR_POLICY_V1,
                "valid": false,
                "parse_error": format!("{e:?}"),
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

    let trees = match build_parameter_trees_v1(&doc) {
        Ok(t) => t,
        Err(e) => {
            let output = serde_json::json!({
                "policy": PARAMETER_TREE_VALIDATOR_POLICY_V1,
                "valid": false,
                "build_error": format!("{e:?}"),
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

    let tree_limits =
        TreeValidationLimitsV1::try_new(max_depth, max_leaf_tokens).expect("tree limits");
    let output = match validate_parameter_trees_v1(&trees, tree_limits) {
        Ok(_) => {
            serde_json::json!({
                "policy": PARAMETER_TREE_VALIDATOR_POLICY_V1,
                "valid": true,
                "validated_tree_count": trees.len(),
            })
        }
        Err(e) => {
            serde_json::json!({
                "policy": PARAMETER_TREE_VALIDATOR_POLICY_V1,
                "valid": false,
                "validator_error": format!("{e:?}"),
            })
        }
    };

    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string_pretty(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string_pretty(&output).expect("json"));
    }
}
