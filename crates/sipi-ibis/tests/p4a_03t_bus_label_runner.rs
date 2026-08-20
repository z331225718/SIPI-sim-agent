//! External-only typed bus label cross-check runner (P4A-03t).
//!
//! Lifts one typed [Bus Label] declaration from input parameters
//! and reports the properties for hash-only comparison against an independent reference.
//! Ignored by default; external-custody tooling only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_ibis::{BUS_LABEL_DECLARATION_POLICY_V1, lift_bus_label_declaration_v1};

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
        println!("usage: p4a_03t_bus_label_runner --input <json> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");
    let bname = value
        .get("bus_label_name")
        .and_then(|v| v.as_str())
        .unwrap_or("");
    let pins = str_list(value.get("member_pins"));

    let output = match lift_bus_label_declaration_v1(bname, pins) {
        Ok(bus) => {
            serde_json::json!({
                "policy": BUS_LABEL_DECLARATION_POLICY_V1,
                "valid": true,
                "bus_label_name": bus.bus_label_name(),
                "member_pins": bus.member_pins(),
            })
        }
        Err(e) => {
            serde_json::json!({
                "policy": BUS_LABEL_DECLARATION_POLICY_V1,
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
