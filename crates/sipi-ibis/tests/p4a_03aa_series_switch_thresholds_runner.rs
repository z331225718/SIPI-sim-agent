//! External-only typed series switch threshold parameters cross-check runner (P4A-03aa).
//!
//! Lifts one typed [Series Switch Groups] threshold declaration from input parameters
//! and reports the properties for hash-only comparison against an independent reference.
//! Ignored by default; external-custody tooling only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_ibis::{SERIES_SWITCH_THRESHOLDS_POLICY_V1, lift_series_switch_thresholds_v1};

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
        println!(
            "usage: p4a_03aa_series_switch_thresholds_runner --input <json> [--report <path>]"
        );
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");
    let vthresh = value.get("vthreshold_v").and_then(|v| v.as_f64());
    let rseries = value.get("rseries_ohm").and_then(|v| v.as_f64());
    let cseries = value.get("cseries_farad").and_then(|v| v.as_f64());
    let lseries = value.get("lseries_henry").and_then(|v| v.as_f64());

    let output = match lift_series_switch_thresholds_v1(vthresh, rseries, cseries, lseries) {
        Ok(thresh) => {
            serde_json::json!({
                "policy": SERIES_SWITCH_THRESHOLDS_POLICY_V1,
                "valid": true,
                "vthreshold_v": thresh.vthreshold_v().map(|v| v.get()),
                "rseries_ohm": thresh.rseries_ohm().map(|v| v.get()),
                "cseries_farad": thresh.cseries_farad().map(|v| v.get()),
                "lseries_henry": thresh.lseries_henry().map(|v| v.get()),
            })
        }
        Err(e) => {
            serde_json::json!({
                "policy": SERIES_SWITCH_THRESHOLDS_POLICY_V1,
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
