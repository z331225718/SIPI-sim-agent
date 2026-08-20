//! External-only typed parameter tree transformer cross-check runner (P4B-02b15).
//!
//! Parses raw parenthesized AMI text, builds typed parameter tree hierarchies,
//! applies target leaf/branch node transformations, and reports the formatted transformed tree
//! for hash-only comparison against an independent reference. Ignored by default; external-custody tooling only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_ami_text::{
    AmiParameterTreeNodeV1, PARAMETER_TREE_TRANSFORMER_POLICY_V1, ParseLimitsV1,
    build_parameter_trees_v1, format_parameter_trees_v1, parse_ami_text_v1,
    transform_parameter_trees_v1,
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
            "usage: p4b_02b15_parameter_tree_transformer_runner --input <path> [--report <path>]"
        );
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");

    let text = value.get("text").and_then(|v| v.as_str()).unwrap_or("");
    let target_path = value
        .get("target_path")
        .and_then(|v| v.as_str())
        .unwrap_or("");
    let new_leaf_tokens: Vec<String> = value
        .get("new_leaf_tokens")
        .and_then(|v| v.as_array())
        .map(|arr| {
            arr.iter()
                .filter_map(|x| x.as_str().map(|s| s.to_string()))
                .collect()
        })
        .unwrap_or_default();

    let limits = ParseLimitsV1::try_new(8 * 1024 * 1024, 64, 4096, 4096).expect("limits");
    let doc = match parse_ami_text_v1(text.as_bytes(), limits) {
        Ok(d) => d,
        Err(e) => {
            let output = serde_json::json!({
                "policy": PARAMETER_TREE_TRANSFORMER_POLICY_V1,
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
                "policy": PARAMETER_TREE_TRANSFORMER_POLICY_V1,
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

    let output = match transform_parameter_trees_v1(&trees, |path, node| {
        if path == target_path {
            let name = node.name().to_string();
            Some(AmiParameterTreeNodeV1::Leaf {
                name,
                value_tokens: new_leaf_tokens.clone(),
            })
        } else {
            None
        }
    }) {
        Ok(transformed) => {
            let formatted = format_parameter_trees_v1(&transformed).expect("format");
            serde_json::json!({
                "policy": PARAMETER_TREE_TRANSFORMER_POLICY_V1,
                "valid": true,
                "transformed_formatted_text": formatted,
            })
        }
        Err(e) => {
            serde_json::json!({
                "policy": PARAMETER_TREE_TRANSFORMER_POLICY_V1,
                "valid": false,
                "transformer_error": format!("{e:?}"),
            })
        }
    };

    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string_pretty(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string_pretty(&output).expect("json"));
    }
}
