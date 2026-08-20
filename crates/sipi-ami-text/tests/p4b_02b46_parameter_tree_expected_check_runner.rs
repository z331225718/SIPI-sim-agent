//! External-only parameter tree expected-value check cross-check runner (P4B-02b46).
//!
//! Parses raw parenthesized AMI text, builds typed parameter tree hierarchies,
//! checks the tree against a caller-supplied expected map, and reports the
//! outcome for hash-only comparison against an independent reference.
//! Ignored by default; external-custody tooling only.

use std::collections::BTreeMap;
use std::path::PathBuf;

use serde_json::Value;
use sipi_ami_text::{
    PARAMETER_TREE_EXPECTED_CHECK_POLICY_V1, ParseLimitsV1, build_parameter_trees_v1,
    check_parameter_tree_against_expected_v1, parse_ami_text_v1,
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
            "usage: p4b_02b46_parameter_tree_expected_check_runner --input <path> [--report <path>]"
        );
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");

    let text = value.get("text").and_then(|v| v.as_str()).unwrap_or("");
    let mut expected = BTreeMap::new();
    if let Some(expected_json) = value.get("expected").and_then(|v| v.as_object()) {
        for (name, tokens) in expected_json {
            let mut token_list = Vec::new();
            if let Some(items) = tokens.as_array() {
                for item in items {
                    if let Some(token) = item.as_str() {
                        token_list.push(token.to_string());
                    }
                }
            }
            expected.insert(name.clone(), token_list);
        }
    }

    let limits = ParseLimitsV1::try_new(8 * 1024 * 1024, 64, 4096, 4096).expect("limits");
    let doc = match parse_ami_text_v1(text.as_bytes(), limits) {
        Ok(d) => d,
        Err(e) => {
            let output = serde_json::json!({
                "policy": PARAMETER_TREE_EXPECTED_CHECK_POLICY_V1,
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
                "policy": PARAMETER_TREE_EXPECTED_CHECK_POLICY_V1,
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

    let output = match check_parameter_tree_against_expected_v1(&trees[0], &expected) {
        Ok(check) => {
            let mismatched_json: Vec<Value> = check
                .mismatched()
                .iter()
                .map(|m| {
                    serde_json::json!({
                        "name": m.name(),
                        "expected": m.expected(),
                        "actual": m.actual(),
                    })
                })
                .collect();
            serde_json::json!({
                "policy": PARAMETER_TREE_EXPECTED_CHECK_POLICY_V1,
                "valid": true,
                "expected_count": check.expected_count(),
                "matched": check.matched(),
                "missing": check.missing(),
                "mismatched": Value::Array(mismatched_json),
            })
        }
        Err(e) => {
            serde_json::json!({
                "policy": PARAMETER_TREE_EXPECTED_CHECK_POLICY_V1,
                "valid": false,
                "expected_error": format!("{e:?}"),
            })
        }
    };

    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string_pretty(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string_pretty(&output).expect("json"));
    }
}
