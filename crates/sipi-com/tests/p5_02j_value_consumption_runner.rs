//! External-only value-consumption / default-resolution cross-check runner
//! (P5-02j).
//!
//! Resolves default-rule expressions via resolve_default_value_v1 and reports
//! the normalized result for hash-only comparison against the agent-com
//! oracle (_resolve_default). Ignored by default; external-custody tooling
//! only.

use std::collections::HashMap;
use std::path::PathBuf;

use serde_json::Value;
use sipi_com::{
    resolve_default_value_v1, ResolvedDefaultV1, VALUE_CONSUMPTION_POLICY_V1,
};

fn value_map(obj: &Value) -> HashMap<String, ResolvedDefaultV1> {
    let mut map = HashMap::new();
    if let Some(fields) = obj.as_object() {
        for (key, value) in fields {
            map.insert(
                key.clone(),
                if let Some(number) = value.as_f64() {
                    ResolvedDefaultV1::Scalar(number)
                } else if let Some(boolean) = value.as_bool() {
                    ResolvedDefaultV1::Boolean(boolean)
                } else if let Some(text) = value.as_str() {
                    match text {
                        "__empty__" => ResolvedDefaultV1::Empty,
                        other => ResolvedDefaultV1::String(other.to_string()),
                    }
                } else {
                    ResolvedDefaultV1::Empty
                },
            );
        }
    }
    map
}

fn normalized_map(map: &HashMap<String, ResolvedDefaultV1>) -> Value {
    let mut object = serde_json::Map::new();
    let mut sorted: Vec<_> = map.iter().collect();
    sorted.sort_by(|a, b| a.0.cmp(b.0));
    for (key, value) in sorted {
        object.insert(key.clone(), normalized(value));
    }
    Value::Object(object)
}

fn normalized(value: &ResolvedDefaultV1) -> Value {
    match value {
        ResolvedDefaultV1::Scalar(number) => serde_json::json!({
            "kind": "scalar",
            "value": number,
        }),
        ResolvedDefaultV1::Vector(elements) => serde_json::json!({
            "kind": "vector",
            "value": elements,
        }),
        ResolvedDefaultV1::Matrix(rows) => serde_json::json!({
            "kind": "matrix",
            "value": rows,
        }),
        ResolvedDefaultV1::Boolean(boolean) => serde_json::json!({
            "kind": "boolean",
            "value": boolean,
        }),
        ResolvedDefaultV1::String(text) => serde_json::json!({
            "kind": "string",
            "value": text,
        }),
        ResolvedDefaultV1::Empty => serde_json::json!({ "kind": "empty" }),
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
        println!("usage: p5_05e_value_consumption_runner --input <json> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");
    let parameters = value_map(&value["parameters"]);
    let options = value_map(&value["options"]);
    let mut results = Vec::new();
    if let Some(cases) = value.get("cases").and_then(|item| item.as_array()) {
        for (index, case) in cases.iter().enumerate() {
            let expression = case["expression"].as_str().expect("expression");
            results.push(serde_json::json!({
                "index": index,
                "expression": expression,
                "result": match resolve_default_value_v1(expression, &parameters, &options) {
                    Ok(resolved) => normalized(&resolved),
                    Err(error) => serde_json::json!({ "kind": "error", "value": format!("{error}") }),
                },
            }));
        }
    }
    let output = serde_json::json!({
        "policy": VALUE_CONSUMPTION_POLICY_V1,
        "parameters": normalized_map(&parameters),
        "options": normalized_map(&options),
        "cases": results,
    });
    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string(&output).expect("json"));
    }
}
