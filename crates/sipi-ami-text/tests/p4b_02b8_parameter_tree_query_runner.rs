//! External-only typed parameter tree query cross-check runner (P4B-02b8).
//!
//! Parses raw parenthesized AMI text, builds typed parameter tree hierarchies,
//! queries target path segments, and reports the query result for hash-only comparison
//! against an independent reference. Ignored by default; external-custody tooling only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_ami_text::{
    build_parameter_trees_v1, parse_ami_text_v1, query_parameter_tree_v1, AmiParameterTreeNodeV1,
    ParseLimitsV1, QueryResultV1, PARAMETER_TREE_QUERY_POLICY_V1,
};

fn node_name(node: &AmiParameterTreeNodeV1) -> &str {
    node.name()
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
        println!("usage: p4b_02b8_parameter_tree_query_runner --input <path> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");

    let text = value.get("text").and_then(|v| v.as_str()).unwrap_or("");
    let path_segments: Vec<&str> = value
        .get("path")
        .and_then(|v| v.as_array())
        .map(|arr| arr.iter().filter_map(|x| x.as_str()).collect())
        .unwrap_or_default();

    let limits = ParseLimitsV1::try_new(8 * 1024 * 1024, 64, 4096, 4096).expect("limits");
    let doc = match parse_ami_text_v1(text.as_bytes(), limits) {
        Ok(d) => d,
        Err(e) => {
            let output = serde_json::json!({
                "policy": PARAMETER_TREE_QUERY_POLICY_V1,
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
                "policy": PARAMETER_TREE_QUERY_POLICY_V1,
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

    let output = match query_parameter_tree_v1(&trees[0], &path_segments) {
        Ok(res) => match res {
            QueryResultV1::Branch(node) => {
                serde_json::json!({
                    "policy": PARAMETER_TREE_QUERY_POLICY_V1,
                    "valid": true,
                    "kind": "branch",
                    "target_name": node_name(node),
                })
            }
            QueryResultV1::Leaf(node) => {
                serde_json::json!({
                    "policy": PARAMETER_TREE_QUERY_POLICY_V1,
                    "valid": true,
                    "kind": "leaf",
                    "target_name": node_name(node),
                })
            }
        },
        Err(e) => {
            serde_json::json!({
                "policy": PARAMETER_TREE_QUERY_POLICY_V1,
                "valid": false,
                "query_error": format!("{e:?}"),
            })
        }
    };

    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string_pretty(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string_pretty(&output).expect("json"));
    }
}
