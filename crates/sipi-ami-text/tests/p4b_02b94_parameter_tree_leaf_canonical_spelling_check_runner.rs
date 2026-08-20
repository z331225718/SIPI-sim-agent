//! External-only parameter tree leaf canonical spelling check cross-check runner (P4B-02b94).
//!
//! Parses raw parenthesized AMI text, builds typed parameter tree hierarchies,
//! checks the canonical spelling of every try_new-valid typed-form leaf, and
//! reports {typed_leaves, non_canonical} for hash-only comparison against an
//! independent reference. Ignored by default; external-custody tooling only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_ami_text::{
    build_parameter_trees_v1, check_parameter_tree_leaf_spellings_canonical_v1, parse_ami_text_v1,
    ParseLimitsV1, PARAMETER_TREE_LEAF_CANONICAL_SPELLING_CHECK_POLICY_V1,
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
        println!("usage: p4b_02b94_parameter_tree_leaf_canonical_spelling_check_runner --input <path> [--report <path>]");
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
                "policy": PARAMETER_TREE_LEAF_CANONICAL_SPELLING_CHECK_POLICY_V1,
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
                "policy": PARAMETER_TREE_LEAF_CANONICAL_SPELLING_CHECK_POLICY_V1,
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

    let result = check_parameter_tree_leaf_spellings_canonical_v1(&trees[0]);
    let non_canonical: Vec<Value> = result
        .non_canonical()
        .iter()
        .map(|issue| {
            serde_json::json!({
                "path": issue.path(),
                "type_token": issue.type_token(),
                "value_token": issue.value_token(),
                "canonical": issue.canonical(),
            })
        })
        .collect();
    let output = serde_json::json!({
        "policy": PARAMETER_TREE_LEAF_CANONICAL_SPELLING_CHECK_POLICY_V1,
        "valid": true,
        "typed_leaves": result.typed_leaves(),
        "canonical": result.canonical(),
        "non_canonical": non_canonical,
    });
    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string_pretty(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string_pretty(&output).expect("json"));
    }
}
