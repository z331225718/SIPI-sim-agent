//! External-only typed series-switch-group cross-check runner (P4A-03k).
//!
//! Lifts one typed [Series Switch Groups] declaration from input parameters
//! and reports the properties for hash-only comparison against an
//! independent reference. Ignored by default; external-custody tooling only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_ibis::{
    lift_series_switch_group_v1, SERIES_SWITCH_GROUPS_POLICY_V1,
};

fn str_list(value: Option<&Value>) -> Vec<String> {
    value
        .and_then(|v| v.as_array())
        .map(|arr| {
            arr.iter()
                .filter_map(|item| item.as_str().map(|s| s.to_string()))
                .collect()
        })
        .unwrap_or_default()
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
        println!("usage: p4a_03k_series_switch_runner --input <json> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");
    let group_name = value.get("group_name").and_then(|v| v.as_str()).unwrap_or("");
    let on_models = str_list(value.get("on_state_models"));
    let off_models = str_list(value.get("off_state_models"));

    let output = match lift_series_switch_group_v1(group_name, on_models, off_models) {
        Ok(group) => {
            serde_json::json!({
                "policy": SERIES_SWITCH_GROUPS_POLICY_V1,
                "valid": true,
                "group_name": group.group_name(),
                "on_state_models": group.on_state_models(),
                "off_state_models": group.off_state_models(),
            })
        }
        Err(e) => {
            serde_json::json!({
                "policy": SERIES_SWITCH_GROUPS_POLICY_V1,
                "valid": false,
                "lift_error": format!("{e:?}"),
            })
        }
    };

    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string_pretty(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string_pretty(&output).expect("json"));
    }
}
