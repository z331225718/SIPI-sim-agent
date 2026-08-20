//! External-only typed series pin group switch threshold table cross-check runner (P4A-03bc).
//!
//! Lifts one typed [Series Pin Mapping] group switch threshold table record from input parameters
//! and reports the properties for hash-only comparison against an independent reference.
//! Ignored by default; external-custody tooling only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_ibis::{
    lift_series_pin_group_switch_threshold_record_v1, SERIES_PIN_TABLE_GROUP_SWITCH_THRESHOLDS_POLICY_V1,
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
        println!("usage: p4a_03bc_series_pin_table_group_switch_thresholds_runner --input <json> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");
    let gn = value.get("group_name").and_then(|v| v.as_str()).unwrap_or("");
    let on_g = value.get("on_group_name").and_then(|v| v.as_str()).unwrap_or("");
    let off_g = value.get("off_group_name").and_then(|v| v.as_str()).unwrap_or("");
    let vthresh = value.get("vthreshold_v").and_then(|v| v.as_f64());
    let rseries = value.get("rseries_ohm").and_then(|v| v.as_f64());
    let cseries = value.get("cseries_farad").and_then(|v| v.as_f64());
    let lseries = value.get("lseries_henry").and_then(|v| v.as_f64());

    let output = match lift_series_pin_group_switch_threshold_record_v1(gn, on_g, off_g, vthresh, rseries, cseries, lseries) {
        Ok(rec) => {
            serde_json::json!({
                "policy": SERIES_PIN_TABLE_GROUP_SWITCH_THRESHOLDS_POLICY_V1,
                "valid": true,
                "group_name": rec.group_name(),
                "on_group_name": rec.on_group_name(),
                "off_group_name": rec.off_group_name(),
                "vthreshold_v": rec.vthreshold_v().map(|v| v.get()),
                "rseries_ohm": rec.rseries_ohm().map(|v| v.get()),
                "cseries_farad": rec.cseries_farad().map(|v| v.get()),
                "lseries_henry": rec.lseries_henry().map(|v| v.get()),
            })
        }
        Err(e) => {
            serde_json::json!({
                "policy": SERIES_PIN_TABLE_GROUP_SWITCH_THRESHOLDS_POLICY_V1,
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
