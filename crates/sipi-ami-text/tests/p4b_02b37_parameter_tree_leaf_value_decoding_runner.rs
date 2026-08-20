//! External-only parameter tree leaf value decoding cross-check runner (P4B-02b37).
//!
//! Parses raw parenthesized AMI text, builds typed parameter tree hierarchies,
//! decodes every leaf value token into a typed Rust value per a caller-supplied
//! type map, and reports the outcome for hash-only comparison against an
//! independent reference. Ignored by default; external-custody tooling only.

use std::collections::BTreeMap;
use std::path::PathBuf;

use serde_json::Value;
use sipi_ami_text::{
    AmiParameterTypeV1, DecodedLeafValueV1, PARAMETER_TREE_LEAF_VALUE_DECODING_POLICY_V1,
    ParseLimitsV1, build_parameter_trees_v1, decode_parameter_tree_leaf_values_v1,
    parse_ami_text_v1,
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
            "usage: p4b_02b37_parameter_tree_leaf_value_decoding_runner --input <path> [--report <path>]"
        );
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");

    let text = value.get("text").and_then(|v| v.as_str()).unwrap_or("");
    let mut type_map = BTreeMap::new();
    if let Some(types) = value.get("types").and_then(|v| v.as_object()) {
        for (name, type_token) in types {
            if let Some(parameter_type) =
                type_token.as_str().and_then(AmiParameterTypeV1::from_token)
            {
                type_map.insert(name.clone(), parameter_type);
            }
        }
    }

    let limits = ParseLimitsV1::try_new(8 * 1024 * 1024, 64, 4096, 4096).expect("limits");
    let doc = match parse_ami_text_v1(text.as_bytes(), limits) {
        Ok(d) => d,
        Err(e) => {
            let output = serde_json::json!({
                "policy": PARAMETER_TREE_LEAF_VALUE_DECODING_POLICY_V1,
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
                "policy": PARAMETER_TREE_LEAF_VALUE_DECODING_POLICY_V1,
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

    let output = match decode_parameter_tree_leaf_values_v1(&trees[0], &type_map) {
        Ok(decoding) => {
            let mut values = serde_json::Map::new();
            for (name, decoded) in decoding.values() {
                values.insert(name.clone(), decoded_to_json(decoded));
            }
            serde_json::json!({
                "policy": PARAMETER_TREE_LEAF_VALUE_DECODING_POLICY_V1,
                "valid": true,
                "leaves_decoded": decoding.leaves_decoded(),
                "values": Value::Object(values),
            })
        }
        Err(e) => {
            serde_json::json!({
                "policy": PARAMETER_TREE_LEAF_VALUE_DECODING_POLICY_V1,
                "valid": false,
                "decode_error": format!("{e:?}"),
            })
        }
    };

    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string_pretty(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string_pretty(&output).expect("json"));
    }
}
