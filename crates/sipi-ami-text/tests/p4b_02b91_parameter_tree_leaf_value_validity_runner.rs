//! External-only parameter tree leaf value validity cross-check runner (P4B-02b91).
//!
//! Parses raw parenthesized AMI text, builds typed parameter tree hierarchies,
//! reports the value validity of every typed-form leaf (using declared types),
//! and outputs {leaves_total, typed_leaves, valid_leaves, invalid} for
//! hash-only comparison against an independent reference. Ignored by default;
//! external-custody tooling only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_ami_text::{
    PARAMETER_TREE_LEAF_VALUE_VALIDITY_POLICY_V1, ParseLimitsV1, build_parameter_trees_v1,
    check_parameter_tree_leaf_value_validity_v1, parse_ami_text_v1,
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
            "usage: p4b_02b91_parameter_tree_leaf_value_validity_runner --input <path> [--report <path>]"
        );
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");

    let text = value.get("text").and_then(|v| v.as_str()).unwrap_or("");
    let limits = ParseLimitsV1::try_new(8 * 1024 * 1024, 64, 4096, 4096).expect("limits");
    let doc = match parse_ami_text_v1(text.as_bytes(), limits) {
        Ok(d) => d,
        Err(e) => {
            let output = serde_json::json!({
                "policy": PARAMETER_TREE_LEAF_VALUE_VALIDITY_POLICY_V1,
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
                "policy": PARAMETER_TREE_LEAF_VALUE_VALIDITY_POLICY_V1,
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

    let result = check_parameter_tree_leaf_value_validity_v1(&trees[0]);
    let invalid: Vec<Value> = result
        .invalid()
        .iter()
        .map(|issue| {
            serde_json::json!({
                "path": issue.path(),
                "type_token": issue.type_token(),
                "value_token": issue.value_token(),
                "error": format!("{:?}", issue.error()),
            })
        })
        .collect();
    let output = serde_json::json!({
        "policy": PARAMETER_TREE_LEAF_VALUE_VALIDITY_POLICY_V1,
        "valid": true,
        "leaves_total": result.leaves_total(),
        "typed_leaves": result.typed_leaves(),
        "valid_leaves": result.valid_leaves(),
        "invalid": invalid,
    });
    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string_pretty(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string_pretty(&output).expect("json"));
    }
}
