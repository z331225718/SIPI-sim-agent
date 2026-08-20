//! External-only parameter tree leaf projection cross-check runner (P4B-02b35).
//!
//! Parses raw parenthesized AMI text, builds typed parameter tree hierarchies,
//! projects the tree onto a caller-supplied leaf name set, and reports the
//! projected tree for hash-only comparison against an independent reference.
//! Ignored by default; external-custody tooling only.

use std::collections::BTreeSet;
use std::path::PathBuf;

use serde_json::Value;
use sipi_ami_text::{
    build_parameter_trees_v1, parse_ami_text_v1, project_parameter_tree_leaves_v1,
    AmiParameterTreeNodeV1, ParseLimitsV1, PARAMETER_TREE_LEAF_PROJECTION_POLICY_V1,
};

fn node_to_json(node: &AmiParameterTreeNodeV1) -> Value {
    match node {
        AmiParameterTreeNodeV1::Branch { name, children } => {
            let mut map = serde_json::Map::new();
            map.insert("kind".to_string(), Value::String("branch".to_string()));
            map.insert("name".to_string(), Value::String(name.clone()));
            let children_json: Vec<Value> =
                children.values().map(node_to_json).collect();
            map.insert("children".to_string(), Value::Array(children_json));
            Value::Object(map)
        }
        AmiParameterTreeNodeV1::Leaf {
            name,
            value_tokens,
        } => {
            let mut map = serde_json::Map::new();
            map.insert("kind".to_string(), Value::String("leaf".to_string()));
            map.insert("name".to_string(), Value::String(name.clone()));
            map.insert(
                "value_tokens".to_string(),
                Value::Array(value_tokens.iter().map(|t| Value::String(t.clone())).collect()),
            );
            Value::Object(map)
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
        println!("usage: p4b_02b35_parameter_tree_leaf_projection_runner --input <path> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");

    let text = value.get("text").and_then(|v| v.as_str()).unwrap_or("");
    let mut keep = BTreeSet::new();
    if let Some(keep_json) = value.get("keep").and_then(|v| v.as_array()) {
        for item in keep_json {
            if let Some(name) = item.as_str() {
                keep.insert(name.to_string());
            }
        }
    }

    let limits = ParseLimitsV1::try_new(8 * 1024 * 1024, 64, 4096, 4096).expect("limits");
    let doc = match parse_ami_text_v1(text.as_bytes(), limits) {
        Ok(d) => d,
        Err(e) => {
            let output = serde_json::json!({
                "policy": PARAMETER_TREE_LEAF_PROJECTION_POLICY_V1,
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
                "policy": PARAMETER_TREE_LEAF_PROJECTION_POLICY_V1,
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

    let output = match project_parameter_tree_leaves_v1(&trees[0], &keep) {
        Ok(projected) => {
            serde_json::json!({
                "policy": PARAMETER_TREE_LEAF_PROJECTION_POLICY_V1,
                "valid": true,
                "root_name": projected.root_name(),
                "tree": node_to_json(projected.root_node()),
            })
        }
        Err(e) => {
            serde_json::json!({
                "policy": PARAMETER_TREE_LEAF_PROJECTION_POLICY_V1,
                "valid": false,
                "project_error": format!("{e:?}"),
            })
        }
    };

    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string_pretty(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string_pretty(&output).expect("json"));
    }
}
