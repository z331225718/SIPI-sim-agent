//! External-only COM parameter DTO merge cross-check runner (P5-05e).
//!
//! Merges workbook values and resolved defaults into a typed COM parameter
//! DTO and reports the consumed/unconsumed split for hash-only comparison
//! with an independent reference. Ignored by default.

use std::collections::BTreeMap;
use std::path::PathBuf;

use sipi_com::{
    merge_com_parameters_v1, ResolvedDefaultV1, COM_PARAMETERS_POLICY_V1,
};

fn read_resolved(value: &serde_json::Value) -> ResolvedDefaultV1 {
    match value["kind"].as_str().unwrap_or("scalar") {
        "scalar" => ResolvedDefaultV1::Scalar(value["value"].as_f64().unwrap_or(0.0)),
        _ => ResolvedDefaultV1::Scalar(value["value"].as_f64().unwrap_or(0.0)),
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
        println!("usage: p5_05e_com_parameters_runner --input <json> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: serde_json::Value = serde_json::from_slice(&bytes).expect("input json");

    let consumed_keys: Vec<String> = value["consumed_keys"].as_array().unwrap().iter().map(|v| v.as_str().unwrap().to_string()).collect();
    let mut workbook = BTreeMap::new();
    if let Some(o) = value.get("workbook").and_then(|v| v.as_object()) {
        for (k, v) in o { workbook.insert(k.clone(), read_resolved(v)); }
    }
    let mut defaults = BTreeMap::new();
    if let Some(o) = value.get("defaults").and_then(|v| v.as_object()) {
        for (k, v) in o { defaults.insert(k.clone(), read_resolved(v)); }
    }
    let unconsumed: Vec<String> = value["unconsumed"].as_array().map(|a| a.iter().map(|v| v.as_str().unwrap_or("").to_string()).collect()).unwrap_or_default();

    let output = match merge_com_parameters_v1(&consumed_keys, &workbook, &defaults, &unconsumed) {
        Ok(dto) => {
            let consumed_out: BTreeMap<String, f64> = dto.consumed().iter().map(|(k, v)| {
                let scalar = match v { ResolvedDefaultV1::Scalar(s) => *s, _ => 0.0 };
                (k.clone(), scalar)
            }).collect();
            serde_json::json!({
                "policy": COM_PARAMETERS_POLICY_V1,
                "ok": true,
                "consumed": consumed_out,
                "consumed_keys": dto.consumed_keys(),
                "unconsumed": dto.unconsumed(),
            })
        }
        Err(e) => serde_json::json!({ "policy": COM_PARAMETERS_POLICY_V1, "ok": false, "error": format!("{e:?}") }),
    };
    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string(&output).expect("json"));
    }
}