//! External-only typed parameter trees cross-check runner (P4B-02b7).
//!
//! Parses raw parenthesized AMI text, builds typed parameter tree hierarchies from
//! AST forms, and reports root node counts and names for hash-only comparison
//! against an independent reference. Ignored by default; external-custody tooling only.

use std::path::PathBuf;

use sipi_ami_text::{
    AmiParameterTreeNodeV1, PARAMETER_TREES_POLICY_V1, ParseLimitsV1, build_parameter_trees_v1,
    parse_ami_text_v1,
};

fn node_to_json(node: &AmiParameterTreeNodeV1) -> serde_json::Value {
    match node {
        AmiParameterTreeNodeV1::Branch { name, children } => {
            let child_map: std::collections::BTreeMap<String, serde_json::Value> = children
                .iter()
                .map(|(k, v)| (k.clone(), node_to_json(v)))
                .collect();
            serde_json::json!({
                "kind": "branch",
                "name": name,
                "children": child_map,
            })
        }
        AmiParameterTreeNodeV1::Leaf { name, value_tokens } => {
            serde_json::json!({
                "kind": "leaf",
                "name": name,
                "value_tokens": value_tokens,
            })
        }
    }
}

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
        println!("usage: p4b_02b7_parameter_trees_runner --input <path> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let limits = ParseLimitsV1::try_new(8 * 1024 * 1024, 64, 4096, 4096).expect("limits");
    let doc = match parse_ami_text_v1(&bytes, limits) {
        Ok(d) => d,
        Err(e) => {
            let output = serde_json::json!({
                "policy": PARAMETER_TREES_POLICY_V1,
                "valid": false,
                "parse_error": format!("{e:?}"),
            });
            if let Some(path) = report {
                std::fs::write(path, serde_json::to_string_pretty(&output).expect("json"))
                    .expect("write");
            } else {
                println!("{}", serde_json::to_string_pretty(&output).expect("json"));
            }
            return;
        }
    };

    let output = match build_parameter_trees_v1(&doc) {
        Ok(trees) => {
            let tree_json_list: Vec<serde_json::Value> = trees
                .iter()
                .map(|t| {
                    serde_json::json!({
                        "root_name": t.root_name(),
                        "root_node": node_to_json(t.root_node()),
                    })
                })
                .collect();
            serde_json::json!({
                "policy": PARAMETER_TREES_POLICY_V1,
                "valid": true,
                "tree_count": trees.len(),
                "trees": tree_json_list,
            })
        }
        Err(e) => {
            serde_json::json!({
                "policy": PARAMETER_TREES_POLICY_V1,
                "valid": false,
                "build_error": format!("{e:?}"),
            })
        }
    };

    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string_pretty(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string_pretty(&output).expect("json"));
    }
}
