//! External-only parameter tree inferred decoding cross-check runner (P4B-02b41).
//!
//! Parses raw parenthesized AMI text, builds typed parameter tree hierarchies,
//! infers one type per leaf and decodes every leaf's single value token into a
//! typed Rust value, and reports the outcome for hash-only comparison against
//! an independent reference. Ignored by default; external-custody tooling only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_ami_text::{
    DecodedLeafValueV1, PARAMETER_TREE_INFERRED_DECODE_POLICY_V1, ParseLimitsV1,
    build_parameter_trees_v1, decode_parameter_tree_with_inferred_types_v1, parse_ami_text_v1,
};

fn decoded_to_json(value: &DecodedLeafValueV1) -> Value {
    match value {
        DecodedLeafValueV1::Float(v) => serde_json::json!({"kind": "Float", "value": v}),
        DecodedLeafValueV1::Integer(v) => serde_json::json!({"kind": "Integer", "value": v}),
        DecodedLeafValueV1::Boolean(v) => serde_json::json!({"kind": "Boolean", "value": v}),
        DecodedLeafValueV1::String(v) => serde_json::json!({"kind": "String", "value": v}),
        DecodedLeafValueV1::List(v) => serde_json::json!({"kind": "List", "value": v}),
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
        println!(
            "usage: p4b_02b41_parameter_tree_inferred_decode_runner --input <path> [--report <path>]"
        );
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
                "policy": PARAMETER_TREE_INFERRED_DECODE_POLICY_V1,
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
                "policy": PARAMETER_TREE_INFERRED_DECODE_POLICY_V1,
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

    let output = match decode_parameter_tree_with_inferred_types_v1(&trees[0]) {
        Ok(result) => {
            let mut leaf_types = serde_json::Map::new();
            for (name, parameter_type) in result.leaf_types() {
                leaf_types.insert(
                    name.clone(),
                    Value::String(parameter_type.token().to_string()),
                );
            }
            let mut values = serde_json::Map::new();
            for (name, decoded) in result.values() {
                values.insert(name.clone(), decoded_to_json(decoded));
            }
            serde_json::json!({
                "policy": PARAMETER_TREE_INFERRED_DECODE_POLICY_V1,
                "valid": true,
                "leaves_decoded": result.leaves_decoded(),
                "leaf_types": Value::Object(leaf_types),
                "values": Value::Object(values),
            })
        }
        Err(e) => {
            serde_json::json!({
                "policy": PARAMETER_TREE_INFERRED_DECODE_POLICY_V1,
                "valid": false,
                "inferred_decode_error": format!("{e:?}"),
            })
        }
    };

    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string_pretty(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string_pretty(&output).expect("json"));
    }
}
