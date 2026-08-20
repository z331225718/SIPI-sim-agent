//! External-only parameter tree path relation cross-check runner (P4B-02b65).
//!
//! Classifies the relation of two canonical paths and reports it for hash-only
//! comparison against an independent reference. Ignored by default;
//! external-custody tooling only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_ami_text::{
    classify_parameter_tree_path_relation_v1, ParameterTreePathRelationV1,
    PARAMETER_TREE_PATH_RELATION_POLICY_V1,
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
        println!("usage: p4b_02b65_parameter_tree_path_relation_runner --input <path> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");

    let mut a = Vec::new();
    if let Some(arr) = value.get("a").and_then(|v| v.as_array()) {
        a.extend(arr.iter().filter_map(|v| v.as_str().map(|s| s.to_string())));
    }
    let mut b = Vec::new();
    if let Some(arr) = value.get("b").and_then(|v| v.as_array()) {
        b.extend(arr.iter().filter_map(|v| v.as_str().map(|s| s.to_string())));
    }

    let output = match classify_parameter_tree_path_relation_v1(&a, &b) {
        Ok(relation) => {
            serde_json::json!({
                "policy": PARAMETER_TREE_PATH_RELATION_POLICY_V1,
                "valid": true,
                "relation": match relation {
                    ParameterTreePathRelationV1::Identical => "Identical",
                    ParameterTreePathRelationV1::Ancestor => "Ancestor",
                    ParameterTreePathRelationV1::Descendant => "Descendant",
                    ParameterTreePathRelationV1::Disjoint => "Disjoint",
                },
            })
        }
        Err(e) => {
            serde_json::json!({
                "policy": PARAMETER_TREE_PATH_RELATION_POLICY_V1,
                "valid": false,
                "relation_error": format!("{e:?}"),
            })
        }
    };

    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string_pretty(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string_pretty(&output).expect("json"));
    }
}
