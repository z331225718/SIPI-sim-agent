//! External-only typed parameter tree diff patch cross-check runner (P4B-02b17).
//!
//! Parses two raw parenthesized AMI texts, computes diff entries between them,
//! applies the diff patch to the left tree, and reports the formatted patched tree
//! for hash-only comparison against an independent reference. Ignored by default; external-custody tooling only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_ami_text::{
    apply_parameter_tree_diff_patch_v1, apply_parameter_tree_diff_patch_with_context_v1, build_parameter_trees_v1, diff_parameter_trees_v1,
    format_parameter_trees_v1, parse_ami_text_v1, ParseLimitsV1,
    PARAMETER_TREE_DIFF_PATCH_POLICY_V1,
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
        println!("usage: p4b_02b17_parameter_tree_diff_patch_runner --input <path> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");

    let text_left = value.get("text_left").and_then(|v| v.as_str()).unwrap_or("");
    let text_right = value.get("text_right").and_then(|v| v.as_str()).unwrap_or("");

    let limits = ParseLimitsV1::try_new(8 * 1024 * 1024, 64, 4096, 4096).expect("limits");
    let doc_l = match parse_ami_text_v1(text_left.as_bytes(), limits) {
        Ok(d) => d,
        Err(e) => {
            let output = serde_json::json!({
                "policy": PARAMETER_TREE_DIFF_PATCH_POLICY_V1,
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
    let doc_r = match parse_ami_text_v1(text_right.as_bytes(), limits) {
        Ok(d) => d,
        Err(e) => {
            let output = serde_json::json!({
                "policy": PARAMETER_TREE_DIFF_PATCH_POLICY_V1,
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

    let t_l = match build_parameter_trees_v1(&doc_l) {
        Ok(t) => t,
        Err(e) => {
            let output = serde_json::json!({
                "policy": PARAMETER_TREE_DIFF_PATCH_POLICY_V1,
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
    let t_r = match build_parameter_trees_v1(&doc_r) {
        Ok(t) => t,
        Err(e) => {
            let output = serde_json::json!({
                "policy": PARAMETER_TREE_DIFF_PATCH_POLICY_V1,
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

    let diffs = match diff_parameter_trees_v1(&t_l[0], &t_r[0]) {
        Ok(d) => d,
        Err(e) => {
            let output = serde_json::json!({
                "policy": PARAMETER_TREE_DIFF_PATCH_POLICY_V1,
                "valid": false,
                "diff_error": format!("{e:?}"),
            });
            if let Some(p) = report {
                std::fs::write(p, serde_json::to_string_pretty(&output).expect("json")).expect("write");
            } else {
                println!("{}", serde_json::to_string_pretty(&output).expect("json"));
            }
            return;
        }
    };

    let output = match apply_parameter_tree_diff_patch_with_context_v1(&t_l[0], &diffs, &t_r[0]) {
        Ok(patched) => {
            let formatted = format_parameter_trees_v1(&[patched]).expect("format");
            serde_json::json!({
                "policy": PARAMETER_TREE_DIFF_PATCH_POLICY_V1,
                "valid": true,
                "patched_formatted_text": formatted,
            })
        }
        Err(e) => {
            serde_json::json!({
                "policy": PARAMETER_TREE_DIFF_PATCH_POLICY_V1,
                "valid": false,
                "patch_error": format!("{e:?}"),
            })
        }
    };

    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string_pretty(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string_pretty(&output).expect("json"));
    }
}
