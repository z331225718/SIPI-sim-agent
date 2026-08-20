//! External-only COM parameter surface resolver cross-check runner (P5-05f).
//!
//! Resolves a COM DTO into ComChainControlsV1 and reports the result for
//! hash-only comparison against an independent reference. Ignored by default;
//! external-custody tooling only.

use std::collections::BTreeMap;
use std::path::PathBuf;

use serde_json::Value;
use sipi_com::{
    COM_PARAMETER_RESOLVER_POLICY_V1, ResolvedDefaultV1, merge_com_parameters_v1,
    resolve_com_parameter_controls_v1,
};

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
        println!("usage: p5_05f_parameter_resolver_runner --input <json> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");
    let mut map = BTreeMap::new();
    if let Some(obj) = value.get("consumed").and_then(|v| v.as_object()) {
        for (k, v) in obj {
            if let Some(res) = parse_resolved_default(v) {
                map.insert(k.clone(), res);
            }
        }
    }

    let keys: Vec<String> = map.keys().cloned().collect();
    let dto = match merge_com_parameters_v1(&keys, &map, &BTreeMap::new(), &[]) {
        Ok(d) => d,
        Err(e) => {
            let output = serde_json::json!({
                "policy": COM_PARAMETER_RESOLVER_POLICY_V1,
                "valid": false,
                "dto_error": format!("{e:?}"),
            });
            if let Some(path) = report {
                std::fs::write(path, serde_json::to_string_pretty(&output).expect("json"))
                    .expect("write");
            } else {
                println!("{}", serde_json::to_string_pretty(&output).expect("json"));
            }
            return;
        }
    };

    let output = match resolve_com_parameter_controls_v1(&dto) {
        Ok(_) => {
            serde_json::json!({
                "policy": COM_PARAMETER_RESOLVER_POLICY_V1,
                "valid": true,
                "consumed_count": map.len(),
            })
        }
        Err(e) => {
            serde_json::json!({
                "policy": COM_PARAMETER_RESOLVER_POLICY_V1,
                "valid": false,
                "resolver_error": format!("{e:?}"),
            })
        }
    };

    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string_pretty(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string_pretty(&output).expect("json"));
    }
}
