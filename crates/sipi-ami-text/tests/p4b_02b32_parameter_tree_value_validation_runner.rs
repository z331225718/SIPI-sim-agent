//! External-only typed parameter tree leaf value validation cross-check runner (P4B-02b32).
//!
//! Parses raw parenthesized AMI text, builds typed parameter tree hierarchies,
//! validates every leaf value token against a caller-supplied type map, and reports
//! the outcome for hash-only comparison against an independent reference.
//! Ignored by default; external-custody tooling only.

use std::collections::BTreeMap;
use std::path::PathBuf;

use serde_json::Value;
use sipi_ami_text::{
    AmiParameterTypeV1, PARAMETER_TREE_VALUE_VALIDATION_POLICY_V1, ParseLimitsV1,
    build_parameter_trees_v1, parse_ami_text_v1, validate_parameter_tree_values_v1,
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
            "usage: p4b_02b32_parameter_tree_value_validation_runner --input <path> [--report <path>]"
        );
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");

    let text = value.get("text").and_then(|v| v.as_str()).unwrap_or("");

    let mut type_map = BTreeMap::new();
    if let Some(types) = value.get("types").and_then(|v| v.as_object()) {
        for (name, type_token) in types {
            let Some(type_token) = type_token.as_str() else {
                let output = serde_json::json!({
                    "policy": PARAMETER_TREE_VALUE_VALIDATION_POLICY_V1,
                    "valid": false,
                    "types_error": "type_token_not_string",
                });
                if let Some(p) = report {
                    std::fs::write(p, serde_json::to_string_pretty(&output).expect("json"))
                        .expect("write");
                } else {
                    println!("{}", serde_json::to_string_pretty(&output).expect("json"));
                }
                return;
            };
            let Some(parameter_type) = AmiParameterTypeV1::from_token(type_token) else {
                let output = serde_json::json!({
                    "policy": PARAMETER_TREE_VALUE_VALIDATION_POLICY_V1,
                    "valid": false,
                    "types_error": format!("unknown_type_token: {type_token}"),
                });
                if let Some(p) = report {
                    std::fs::write(p, serde_json::to_string_pretty(&output).expect("json"))
                        .expect("write");
                } else {
                    println!("{}", serde_json::to_string_pretty(&output).expect("json"));
                }
                return;
            };
            type_map.insert(name.clone(), parameter_type);
        }
    }

    let limits = ParseLimitsV1::try_new(8 * 1024 * 1024, 64, 4096, 4096).expect("limits");
    let doc = match parse_ami_text_v1(text.as_bytes(), limits) {
        Ok(d) => d,
        Err(e) => {
            let output = serde_json::json!({
                "policy": PARAMETER_TREE_VALUE_VALIDATION_POLICY_V1,
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
                "policy": PARAMETER_TREE_VALUE_VALIDATION_POLICY_V1,
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

    let output = match validate_parameter_tree_values_v1(&trees[0], &type_map) {
        Ok(validation) => {
            let mut leaf_types = serde_json::Map::new();
            for (name, parameter_type) in validation.leaf_types() {
                leaf_types.insert(
                    name.clone(),
                    Value::String(parameter_type.token().to_string()),
                );
            }
            serde_json::json!({
                "policy": PARAMETER_TREE_VALUE_VALIDATION_POLICY_V1,
                "valid": true,
                "leaves_checked": validation.leaves_checked(),
                "tokens_checked": validation.tokens_checked(),
                "leaf_types": Value::Object(leaf_types),
            })
        }
        Err(e) => {
            serde_json::json!({
                "policy": PARAMETER_TREE_VALUE_VALIDATION_POLICY_V1,
                "valid": false,
                "validation_error": format!("{e:?}"),
            })
        }
    };

    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string_pretty(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string_pretty(&output).expect("json"));
    }
}
