//! External-only MATLAB numeric-literal cross-check runner (P5-02k).
//!
//! Parses numeric-literal expressions via parse_literal_v1 and reports the
//! normalized result for hash-only comparison against the agent-com oracle
//! (literals.parse_matlab_literal). Ignored by default; external-custody
//! tooling only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_com::{LiteralV1, VALUE_CONSUMPTION_POLICY_V1, parse_literal_v1};

fn normalized(value: &LiteralV1) -> Value {
    match value {
        LiteralV1::Scalar(v) => serde_json::json!({ "kind": "scalar", "value": v }),
        LiteralV1::Vector(elements) => serde_json::json!({ "kind": "vector", "value": elements }),
        LiteralV1::Matrix(rows) => serde_json::json!({ "kind": "matrix", "value": rows }),
        LiteralV1::Empty => serde_json::json!({ "kind": "empty" }),
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
        println!("usage: p5_02k_matlab_literal_runner --input <json> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");
    let mut results = Vec::new();
    if let Some(cases) = value.get("cases").and_then(|item| item.as_array()) {
        for (index, case) in cases.iter().enumerate() {
            let expression = case["expression"].as_str().expect("expression");
            results.push(serde_json::json!({
                "index": index,
                "expression": expression,
                "result": match parse_literal_v1(expression) {
                    Ok(literal) => normalized(&literal),
                    Err(error) => serde_json::json!({ "kind": "error", "value": format!("{error}") }),
                },
            }));
        }
    }
    let output = serde_json::json!({
        "policy": VALUE_CONSUMPTION_POLICY_V1,
        "cases": results,
    });
    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string(&output).expect("json"));
    }
}
