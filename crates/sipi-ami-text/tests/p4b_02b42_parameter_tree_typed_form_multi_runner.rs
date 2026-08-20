//! External-only multi-tree typed-form extraction cross-check runner (P4B-02b42).
//!
//! Parses raw parenthesized AMI texts (one tree per text), extracts typed
//! AmiParameterValueV1 entries from every tree, merges them by name, and reports
//! the outcome for hash-only comparison against an independent reference.
//! Ignored by default; external-custody tooling only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_ami_text::{
    AmiParameterTreeV1, PARAMETER_TREE_TYPED_FORM_MULTI_POLICY_V1, ParseLimitsV1,
    build_parameter_trees_v1, extract_typed_parameter_forms_multi_v1, parse_ami_text_v1,
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
            "usage: p4b_02b42_parameter_tree_typed_form_multi_runner --input <path> [--report <path>]"
        );
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");

    let texts: Vec<String> = value
        .get("texts")
        .and_then(|v| v.as_array())
        .map(|arr| {
            arr.iter()
                .filter_map(|t| t.as_str().map(|s| s.to_string()))
                .collect()
        })
        .unwrap_or_default();

    let limits = ParseLimitsV1::try_new(8 * 1024 * 1024, 64, 4096, 4096).expect("limits");
    let mut trees: Vec<AmiParameterTreeV1> = Vec::new();
    let mut build_failed: Option<String> = None;
    for text in &texts {
        let doc = match parse_ami_text_v1(text.as_bytes(), limits) {
            Ok(d) => d,
            Err(e) => {
                build_failed = Some(format!("{e:?}"));
                break;
            }
        };
        match build_parameter_trees_v1(&doc) {
            Ok(mut t) => {
                if let Some(first) = t.drain(..).next() {
                    trees.push(first);
                }
            }
            Err(e) => {
                build_failed = Some(format!("{e:?}"));
                break;
            }
        }
    }
    if let Some(error) = build_failed {
        let output = serde_json::json!({
            "policy": PARAMETER_TREE_TYPED_FORM_MULTI_POLICY_V1,
            "valid": false,
            "parse_error": error,
        });
        if let Some(p) = report {
            std::fs::write(p, serde_json::to_string_pretty(&output).expect("json")).expect("write");
        } else {
            println!("{}", serde_json::to_string_pretty(&output).expect("json"));
        }
        return;
    }

    let output = match extract_typed_parameter_forms_multi_v1(&trees) {
        Ok(forms) => {
            let mut parameters = serde_json::Map::new();
            for (name, parameter) in forms.parameters() {
                parameters.insert(
                    name.clone(),
                    serde_json::json!({
                        "name": parameter.name(),
                        "type": parameter.parameter_type().token(),
                        "value": parameter.value_token(),
                    }),
                );
            }
            serde_json::json!({
                "policy": PARAMETER_TREE_TYPED_FORM_MULTI_POLICY_V1,
                "valid": true,
                "leaves_consumed": forms.leaves_consumed(),
                "parameters": Value::Object(parameters),
            })
        }
        Err(e) => {
            serde_json::json!({
                "policy": PARAMETER_TREE_TYPED_FORM_MULTI_POLICY_V1,
                "valid": false,
                "multi_form_error": format!("{e:?}"),
            })
        }
    };

    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string_pretty(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string_pretty(&output).expect("json"));
    }
}
