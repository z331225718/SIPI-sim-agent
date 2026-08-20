//! External-only typed series pin group switch association cross-check runner (P4A-03bb).
//!
//! Lifts one typed [Series Pin Mapping] group switch association record from input parameters
//! and reports the properties for hash-only comparison against an independent reference.
//! Ignored by default; external-custody tooling only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_ibis::{
    lift_series_pin_group_switch_record_v1, SERIES_PIN_TABLE_GROUP_SWITCH_POLICY_V1,
};

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
        println!("usage: p4a_03bb_series_pin_table_group_switch_runner --input <json> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");
    let gn = value.get("group_name").and_then(|v| v.as_str()).unwrap_or("");
    let on_g = value.get("on_group_name").and_then(|v| v.as_str()).unwrap_or("");
    let off_g = value.get("off_group_name").and_then(|v| v.as_str()).unwrap_or("");
    let ftg = value.get("function_table_group").and_then(|v| v.as_str());

    let output = match lift_series_pin_group_switch_record_v1(gn, on_g, off_g, ftg) {
        Ok(rec) => {
            serde_json::json!({
                "policy": SERIES_PIN_TABLE_GROUP_SWITCH_POLICY_V1,
                "valid": true,
                "group_name": rec.group_name(),
                "on_group_name": rec.on_group_name(),
                "off_group_name": rec.off_group_name(),
                "function_table_group": rec.function_table_group(),
            })
        }
        Err(e) => {
            serde_json::json!({
                "policy": SERIES_PIN_TABLE_GROUP_SWITCH_POLICY_V1,
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
