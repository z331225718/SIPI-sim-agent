//! External-only parameter tree typed-form conformance report cross-check runner (P4B-02b58).
//!
//! Parses raw parenthesized AMI text, builds typed parameter tree hierarchies,
//! reports the typed-form conformance of every leaf, and emits the report for
//! hash-only comparison against an independent reference.
//! Ignored by default; external-custody tooling only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_ami_text::{
    build_parameter_trees_v1, check_parameter_tree_typed_form_conformance_v1,
    parse_ami_text_v1, ParseLimitsV1, TypedFormViolationV1,
    PARAMETER_TREE_TYPED_FORM_CONFORMANCE_POLICY_V1,
};

fn violation_to_json(violation: &TypedFormViolationV1) -> Value {
    match violation {
        TypedFormViolationV1::EmptyValueTokens => {
            serde_json::json!({"kind": "EmptyValueTokens"})
        }
        TypedFormViolationV1::NotTypedForm => {
            serde_json::json!({"kind": "NotTypedForm"})
        }
        TypedFormViolationV1::MultiTokenForm { token_count } => {
            serde_json::json!({"kind": "MultiTokenForm", "token_count": token_count})
        }
        TypedFormViolationV1::UnknownTypeToken { token } => {
            serde_json::json!({"kind": "UnknownTypeToken", "token": token})
        }
        TypedFormViolationV1::InvalidValue { error } => {
            serde_json::json!({"kind": "InvalidValue", "error": format!("{error:?}")})
        }
        TypedFormViolationV1::InvalidParameterName => {
            serde_json::json!({"kind": "InvalidParameterName"})
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
        println!("usage: p4b_02b58_parameter_tree_typed_form_report_runner --input <path> [--report <path>]");
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
                "policy": PARAMETER_TREE_TYPED_FORM_CONFORMANCE_POLICY_V1,
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
                "policy": PARAMETER_TREE_TYPED_FORM_CONFORMANCE_POLICY_V1,
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

    let conformance = check_parameter_tree_typed_form_conformance_v1(&trees[0]);
    let entries_json: Vec<Value> = conformance
        .entries()
        .iter()
        .map(|entry| {
            serde_json::json!({
                "leaf": entry.leaf(),
                "conforming": entry.is_conforming(),
                "violation": entry.violation().map(violation_to_json),
            })
        })
        .collect();
    let output = serde_json::json!({
        "policy": PARAMETER_TREE_TYPED_FORM_CONFORMANCE_POLICY_V1,
        "valid": true,
        "conforming_count": conformance.conforming_count(),
        "non_conforming_count": conformance.non_conforming_count(),
        "entries": Value::Array(entries_json),
    });

    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string_pretty(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string_pretty(&output).expect("json"));
    }
}
