//! External-only default-set resolver cross-check runner (P5-02l).
//!
//! Resolves a set of default expressions against a parameter surface and
//! reports each resolved value for hash-only comparison with the oracle.

use std::collections::HashMap;
use std::path::PathBuf;

use serde_json::Value;
use sipi_com::{RESOLVE_PARAMETERS_POLICY_V1, ResolvedDefaultV1, resolve_default_set_v1};

fn value_map(obj: &Value) -> HashMap<String, ResolvedDefaultV1> {
    let mut map = HashMap::new();
    if let Some(fields) = obj.as_object() {
        for (key, value) in fields {
            map.insert(
                key.clone(),
                if let Some(n) = value.as_f64() {
                    ResolvedDefaultV1::Scalar(n)
                } else {
                    ResolvedDefaultV1::Scalar(0.0)
                },
            );
        }
    }
    map
}

fn normalized(value: &ResolvedDefaultV1) -> Value {
    match value {
        ResolvedDefaultV1::Scalar(v) => serde_json::json!({ "kind": "scalar", "value": v }),
        ResolvedDefaultV1::Vector(v) => serde_json::json!({ "kind": "vector", "value": v }),
        ResolvedDefaultV1::Matrix(m) => serde_json::json!({ "kind": "matrix", "value": m }),
        ResolvedDefaultV1::Boolean(b) => serde_json::json!({ "kind": "boolean", "value": b }),
        ResolvedDefaultV1::String(s) => serde_json::json!({ "kind": "string", "value": s }),
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
        println!("usage: p5_02l_resolve_parameters_runner --input <json> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");

    let parameters = value_map(&value["parameters"]);
    let options = value_map(&value["options"]);
    let mut expressions = HashMap::new();
    if let Some(map) = value.get("expressions").and_then(|v| v.as_object()) {
        for (k, v) in map {
            expressions.insert(k.clone(), v.as_str().unwrap_or("").to_string());
        }
    }

    let output = match resolve_default_set_v1(&expressions, &parameters, &options) {
        Ok(resolved) => {
            let mut sorted: Vec<_> = resolved.iter().collect();
            sorted.sort_by(|a, b| a.0.cmp(b.0));
            let mut object = serde_json::Map::new();
            for (k, v) in sorted {
                object.insert(k.clone(), normalized(v));
            }
            serde_json::json!({ "policy": RESOLVE_PARAMETERS_POLICY_V1, "ok": true, "values": Value::Object(object) })
        }
        Err(e) => {
            serde_json::json!({ "policy": RESOLVE_PARAMETERS_POLICY_V1, "ok": false, "error": format!("{e:?}") })
        }
    };
    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string(&output).expect("json"));
    }
}
