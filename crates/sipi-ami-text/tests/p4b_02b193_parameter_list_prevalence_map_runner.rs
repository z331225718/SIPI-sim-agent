//! External-only parameter list prevalence map cross-check runner (P4B-02b193).
//!
//! Reads one JSON case {name, type, value}, builds the validated value, computes the
//! prevalence map and reports it (or the fail-closed error) for hash-only comparison
//! against an independent reference. Each proportion is formatted with 12 decimals. Ignored
//! by default; external-custody tooling only.

use std::collections::BTreeMap;

use serde_json::Value;
use sipi_ami_text::{
    parameter_list_prevalence_map_v1, AmiParameterValueV1, ParameterListPrevalenceMapErrorV1,
    PARAMETER_LIST_PREVALENCE_MAP_POLICY_V1,
};

fn main() {
    let mut input = None;
    let mut report = None;
    let mut args = std::env::args().skip(1);
    while let Some(argument) = args.next() {
        let mut value = || args.next().expect("argument value");
        match argument.as_str() {
            "--input" => input = Some(std::path::PathBuf::from(value())),
            "--report" => report = Some(std::path::PathBuf::from(value())),
            other => panic!("unknown argument: {other}"),
        }
    }
    let Some(input) = input else {
        println!("usage: p4b_02b193_parameter_list_prevalence_map_runner --input <path> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");

    let name = value.get("name").and_then(|v| v.as_str()).unwrap_or("");
    let type_token = value.get("type").and_then(|v| v.as_str()).unwrap_or("");
    let value_token = value.get("value").and_then(|v| v.as_str()).unwrap_or("");
    let parameter = match AmiParameterValueV1::try_new(name, type_token, value_token) {
        Ok(p) => p,
        Err(_) => {
            let output = serde_json::json!({
                "policy": PARAMETER_LIST_PREVALENCE_MAP_POLICY_V1,
                "valid": false,
                "input_error": "invalid_value",
            });
            if let Some(p) = report {
                std::fs::write(p, serde_json::to_string_pretty(&output).expect("json")).expect("write");
            } else {
                println!("{}", serde_json::to_string_pretty(&output).expect("json"));
            }
            return;
        }
    };

    let output = match parameter_list_prevalence_map_v1(&parameter) {
        Ok(map) => {
            let map_json: BTreeMap<String, Value> = map
                .into_iter()
                .map(|(k, v)| (k, Value::String(format!("{v:.12}"))))
                .collect();
            serde_json::json!({
                "policy": PARAMETER_LIST_PREVALENCE_MAP_POLICY_V1,
                "valid": true,
                "prevalence_map": map_json,
            })
        }
        Err(ParameterListPrevalenceMapErrorV1::NotAList) => serde_json::json!({
            "policy": PARAMETER_LIST_PREVALENCE_MAP_POLICY_V1,
            "valid": false,
            "error": "NotAList",
        }),
        Err(ParameterListPrevalenceMapErrorV1::MalformedList) => serde_json::json!({
            "policy": PARAMETER_LIST_PREVALENCE_MAP_POLICY_V1,
            "valid": false,
            "error": "MalformedList",
        }),
    };
    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string_pretty(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string_pretty(&output).expect("json"));
    }
}
