//! External-only typed parameter tree depth stats cross-check runner (P4B-02b29).
//!
//! Parses raw parenthesized AMI text, builds typed parameter tree hierarchies,
//! computes depth statistics, and reports the stats for hash-only comparison
//! against an independent reference. Ignored by default; external-custody tooling only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_ami_text::{
    build_parameter_trees_v1, compute_parameter_tree_depth_stats_v1, parse_ami_text_v1,
    ParseLimitsV1, PARAMETER_TREE_DEPTH_STATS_POLICY_V1,
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
        println!("usage: p4b_02b29_parameter_tree_depth_stats_runner --input <path> [--report <path>]");
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
                "policy": PARAMETER_TREE_DEPTH_STATS_POLICY_V1,
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
                "policy": PARAMETER_TREE_DEPTH_STATS_POLICY_V1,
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

    let output = match compute_parameter_tree_depth_stats_v1(&trees[0]) {
        Ok(stats) => {
            serde_json::json!({
                "policy": PARAMETER_TREE_DEPTH_STATS_POLICY_V1,
                "valid": true,
                "max_depth": stats.max_depth,
                "min_depth": stats.min_depth,
                "leaf_count": stats.leaf_count,
                "nodes_per_depth": stats.nodes_per_depth,
                "leaves_per_depth": stats.leaves_per_depth,
            })
        }
        Err(e) => {
            serde_json::json!({
                "policy": PARAMETER_TREE_DEPTH_STATS_POLICY_V1,
                "valid": false,
                "stats_error": format!("{e:?}"),
            })
        }
    };

    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string_pretty(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string_pretty(&output).expect("json"));
    }
}
