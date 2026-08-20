//! External-only parameter tree leaf typed diff cross-check runner (P4B-02b89).
//!
//! Parses two parenthesized AMI texts, builds typed parameter tree
//! hierarchies, diffs their leaves at matching canonical paths under typed
//! semantics, and reports {matched, added, removed, changed} for hash-only
//! comparison against an independent reference. Ignored by default;
//! external-custody tooling only.

use std::collections::BTreeMap;
use std::path::PathBuf;

use serde_json::Value;
use sipi_ami_text::{
    build_parameter_trees_v1, diff_parameter_tree_leaves_typed_v1, parse_ami_text_v1,
    AmiParameterTreeV1, ParseLimitsV1, PARAMETER_TREE_LEAF_TYPED_DIFF_POLICY_V1,
};

fn build_tree(text: &str) -> Result<AmiParameterTreeV1, String> {
    let limits = ParseLimitsV1::try_new(8 * 1024 * 1024, 64, 4096, 4096).expect("limits");
    let doc = parse_ami_text_v1(text.as_bytes(), limits).map_err(|e| format!("{e:?}"))?;
    let mut trees = build_parameter_trees_v1(&doc).map_err(|e| format!("{e:?}"))?;
    Ok(trees.remove(0))
}

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
        println!("usage: p4b_02b89_parameter_tree_leaf_typed_diff_runner --input <path> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");

    let left_text = value.get("left_text").and_then(|v| v.as_str()).unwrap_or("");
    let right_text = value.get("right_text").and_then(|v| v.as_str()).unwrap_or("");
    let left = match build_tree(left_text) {
        Ok(t) => t,
        Err(e) => {
            let output = serde_json::json!({
                "policy": PARAMETER_TREE_LEAF_TYPED_DIFF_POLICY_V1,
                "valid": false,
                "left_error": e,
            });
            if let Some(p) = report {
                std::fs::write(p, serde_json::to_string_pretty(&output).expect("json")).expect("write");
            } else {
                println!("{}", serde_json::to_string_pretty(&output).expect("json"));
            }
            return;
        }
    };
    let right = match build_tree(right_text) {
        Ok(t) => t,
        Err(e) => {
            let output = serde_json::json!({
                "policy": PARAMETER_TREE_LEAF_TYPED_DIFF_POLICY_V1,
                "valid": false,
                "right_error": e,
            });
            if let Some(p) = report {
                std::fs::write(p, serde_json::to_string_pretty(&output).expect("json")).expect("write");
            } else {
                println!("{}", serde_json::to_string_pretty(&output).expect("json"));
            }
            return;
        }
    };

    let diff = diff_parameter_tree_leaves_typed_v1(&left, &right);
    let changed: Vec<Value> = diff
        .changed()
        .iter()
        .map(|c| {
            serde_json::json!({
                "path": c.path(),
                "old_tokens": c.old_tokens(),
                "new_tokens": c.new_tokens(),
                "reason": c.reason().map(|r| r.key()),
            })
        })
        .collect();
    let output = serde_json::json!({
        "policy": PARAMETER_TREE_LEAF_TYPED_DIFF_POLICY_V1,
        "valid": true,
        "matched": diff.matched(),
        "added": diff.added(),
        "removed": diff.removed(),
        "changed": changed,
    });
    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string_pretty(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string_pretty(&output).expect("json"));
    }
}
