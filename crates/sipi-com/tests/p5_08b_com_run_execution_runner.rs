//! External-only COM run execution cross-check runner (P5-08b).
//!
//! Executes a "sipi com run" request against a pulse response and COM DTO,
//! reporting the result envelope for hash-only comparison against an
//! independent reference. Ignored by default; external-custody tooling only.

use std::collections::BTreeMap;
use std::path::PathBuf;

use serde_json::Value;
use sipi_com::{
    execute_com_run_v1, merge_com_parameters_v1, ResolvedDefaultV1,
    COM_RUN_EXECUTION_POLICY_V1, COM_RUN_RESULT_SCHEMA_V1,
};

fn f64s(value: &Value) -> Vec<f64> {
    value
        .as_array()
        .expect("array")
        .iter()
        .map(|item| item.as_f64().expect("f64"))
        .collect()
}

fn parse_resolved_default(v: &Value) -> Option<ResolvedDefaultV1> {
    if let Some(num) = v.get("Scalar").and_then(|x| x.as_f64()) {
        return Some(ResolvedDefaultV1::Scalar(num));
    }
    if let Some(arr) = v.get("Vector").and_then(|x| x.as_array()) {
        let vec: Vec<f64> = arr.iter().filter_map(|x| x.as_f64()).collect();
        return Some(ResolvedDefaultV1::Vector(vec));
    }
    if let Some(b) = v.get("Boolean").and_then(|x| x.as_bool()) {
        return Some(ResolvedDefaultV1::Boolean(b));
    }
    if let Some(s) = v.get("String").and_then(|x| x.as_str()) {
        return Some(ResolvedDefaultV1::String(s.to_string()));
    }
    None
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
        println!("usage: p5_08b_com_run_execution_runner --input <json> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");
    let request_bytes = serde_json::to_vec(&value["request"]).expect("request json");
    let pulse = f64s(&value["pulse"]);

    let mut map = BTreeMap::new();
    if let Some(obj) = value.get("consumed").and_then(|v| v.as_object()) {
        for (k, v) in obj {
            if let Some(res) = parse_resolved_default(v) {
                map.insert(k.clone(), res);
            }
        }
    }
    let keys: Vec<String> = map.keys().cloned().collect();
    let dto = merge_com_parameters_v1(&keys, &map, &BTreeMap::new(), &[]).expect("dto");

    let output = match execute_com_run_v1(&request_bytes, &pulse, &dto) {
        Ok(env) => {
            serde_json::json!({
                "policy": COM_RUN_EXECUTION_POLICY_V1,
                "result_schema": COM_RUN_RESULT_SCHEMA_V1,
                "admitted": env.admitted(),
                "com_db": env.com_db(),
                "vec_db": env.vec_db(),
                "veo_mv": env.veo_mv(),
                "sigma_n_v": env.sigma_n_v(),
                "invalid_reason": env.invalid_reason(),
            })
        }
        Err(e) => {
            serde_json::json!({
                "policy": COM_RUN_EXECUTION_POLICY_V1,
                "result_schema": COM_RUN_RESULT_SCHEMA_V1,
                "admitted": false,
                "execution_error": format!("{e:?}"),
            })
        }
    };

    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string_pretty(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string_pretty(&output).expect("json"));
    }
}
