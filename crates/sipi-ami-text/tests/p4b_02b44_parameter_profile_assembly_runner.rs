//! External-only parameter profile assembly cross-check runner (P4B-02b44).
//!
//! Parses raw parenthesized AMI texts (one tree per text), assembles a strict
//! parameter profile (multi-tree typed-form extraction + typed defaults fill +
//! reserved-name rejection), and reports the outcome for hash-only comparison
//! against an independent reference. Ignored by default; external-custody tooling only.

use std::collections::{BTreeMap, BTreeSet};
use std::path::PathBuf;

use serde_json::Value;
use sipi_ami_text::{
    AmiParameterTreeV1, PARAMETER_PROFILE_ASSEMBLY_POLICY_V1, ParseLimitsV1,
    assemble_parameter_profile_v1, build_parameter_trees_v1, parse_ami_text_v1,
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
            "usage: p4b_02b44_parameter_profile_assembly_runner --input <path> [--report <path>]"
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

    let mut defaults = BTreeMap::new();
    if let Some(defaults_json) = value.get("defaults").and_then(|v| v.as_object()) {
        for (name, tokens) in defaults_json {
            let mut token_list = Vec::new();
            if let Some(items) = tokens.as_array() {
                for item in items {
                    if let Some(token) = item.as_str() {
                        token_list.push(token.to_string());
                    }
                }
            }
            defaults.insert(name.clone(), token_list);
        }
    }

    let mut reserved = BTreeSet::new();
    if let Some(reserved_json) = value.get("reserved").and_then(|v| v.as_array()) {
        for item in reserved_json {
            if let Some(name) = item.as_str() {
                reserved.insert(name.to_string());
            }
        }
    }

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
            "policy": PARAMETER_PROFILE_ASSEMBLY_POLICY_V1,
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

    let output = match assemble_parameter_profile_v1(&trees, &defaults, &reserved) {
        Ok(assembly) => {
            let mut parameters = serde_json::Map::new();
            for (name, parameter) in assembly.parameters() {
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
                "policy": PARAMETER_PROFILE_ASSEMBLY_POLICY_V1,
                "valid": true,
                "leaves_consumed": assembly.leaves_consumed(),
                "defaults_applied": assembly.defaults_applied(),
                "defaults_skipped": assembly.defaults_skipped(),
                "parameters": Value::Object(parameters),
            })
        }
        Err(e) => {
            serde_json::json!({
                "policy": PARAMETER_PROFILE_ASSEMBLY_POLICY_V1,
                "valid": false,
                "assembly_error": format!("{e:?}"),
            })
        }
    };

    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string_pretty(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string_pretty(&output).expect("json"));
    }
}
