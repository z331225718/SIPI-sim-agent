//! External-only typed parameter tree node rename cross-check runner (P4B-02b24).
//!
//! Parses raw parenthesized AMI text, builds typed parameter tree hierarchies,
//! renames the node at a dot-separated canonical path, and reports the renamed tree
//! canonical JSON for hash-only comparison against an independent reference.
//! Ignored by default; external-custody tooling only.

use std::collections::BTreeMap;
use std::path::PathBuf;

use serde_json::{json, Value};
use sipi_ami_text::{
    build_parameter_trees_v1, parse_ami_text_v1, rename_parameter_tree_node_v1,
    AmiParameterTreeNodeV1, ParseLimitsV1, PARAMETER_TREE_RENAME_POLICY_V1,
};

fn node_to_json(node: &AmiParameterTreeNodeV1) -> Value {
    match node {
        AmiParameterTreeNodeV1::Branch { name, children } => {
            let child_map: BTreeMap<String, Value> = children
                .iter()
                .map(|(k, v)| (k.clone(), node_to_json(v)))
                .collect();
            json!({
                "kind": "branch",
                "name": name,
                "children": child_map,
            })
        }
        AmiParameterTreeNodeV1::Leaf { name, value_tokens } => {
            json!({
                "kind": "leaf",
                "name": name,
                "value_tokens": value_tokens,
            })
        }
    }
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
        println!("usage: p4b_02b24_parameter_tree_rename_runner --input <path> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");

    let text = value.get("text").and_then(|v| v.as_str()).unwrap_or("");
    let path = value.get("path").and_then(|v| v.as_str()).unwrap_or("");
    let new_name = value.get("new_name").and_then(|v| v.as_str()).unwrap_or("");

    let limits = ParseLimitsV1::try_new(8 * 1024 * 1024, 64, 4096, 4096).expect("limits");
    let doc = match parse_ami_text_v1(text.as_bytes(), limits) {
        Ok(d) => d,
        Err(e) => {
            let output = serde_json::json!({
                "policy": PARAMETER_TREE_RENAME_POLICY_V1,
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
                "policy": PARAMETER_TREE_RENAME_POLICY_V1,
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

    let output = match rename_parameter_tree_node_v1(&trees[0], path, new_name) {
        Ok(renamed) => {
            serde_json::json!({
                "policy": PARAMETER_TREE_RENAME_POLICY_V1,
                "valid": true,
                "root_name": renamed.root_name(),
                "tree": node_to_json(renamed.root_node()),
            })
        }
        Err(e) => {
            serde_json::json!({
                "policy": PARAMETER_TREE_RENAME_POLICY_V1,
                "valid": false,
                "rename_error": format!("{e:?}"),
            })
        }
    };

    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string_pretty(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string_pretty(&output).expect("json"));
    }
}
