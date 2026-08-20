//! External-only typed series switch block keywords cross-check runner (P4A-03ag).
//!
//! Lifts one typed [Series Switch Groups] complete block from input parameters
//! and reports the properties for hash-only comparison against an independent reference.
//! Ignored by default; external-custody tooling only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_ibis::{
    SERIES_SWITCH_KEYWORDS_POLICY_V1, lift_series_switch_block_v1, lift_series_switch_record_v1,
    lift_series_switch_thresholds_v1,
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
        println!("usage: p4a_03ag_series_switch_keywords_runner --input <json> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");

    let on_g = value
        .get("on_group_name")
        .and_then(|v| v.as_str())
        .unwrap_or("");
    let off_g = value
        .get("off_group_name")
        .and_then(|v| v.as_str())
        .unwrap_or("");

    let switch_rec = match lift_series_switch_record_v1(on_g, off_g) {
        Ok(r) => r,
        Err(e) => {
            let output = serde_json::json!({
                "policy": SERIES_SWITCH_KEYWORDS_POLICY_V1,
                "valid": false,
                "record_error": format!("{e:?}"),
            });
            if let Some(p) = report {
                std::fs::write(p, serde_json::to_string_pretty(&output).expect("json"))
                    .expect("write");
            } else {
                println!("{}", serde_json::to_string_pretty(&output).expect("json"));
            }
            return;
        }
    };

    let vthresh = value.get("vthreshold_v").and_then(|v| v.as_f64());
    let rseries = value.get("rseries_ohm").and_then(|v| v.as_f64());
    let cseries = value.get("cseries_farad").and_then(|v| v.as_f64());
    let lseries = value.get("lseries_henry").and_then(|v| v.as_f64());

    let thresholds =
        if vthresh.is_some() || rseries.is_some() || cseries.is_some() || lseries.is_some() {
            match lift_series_switch_thresholds_v1(vthresh, rseries, cseries, lseries) {
                Ok(t) => Some(t),
                Err(e) => {
                    let output = serde_json::json!({
                        "policy": SERIES_SWITCH_KEYWORDS_POLICY_V1,
                        "valid": false,
                        "threshold_error": format!("{e:?}"),
                    });
                    if let Some(p) = report {
                        std::fs::write(p, serde_json::to_string_pretty(&output).expect("json"))
                            .expect("write");
                    } else {
                        println!("{}", serde_json::to_string_pretty(&output).expect("json"));
                    }
                    return;
                }
            }
        } else {
            None
        };

    let output = match lift_series_switch_block_v1(switch_rec, thresholds) {
        Ok(block) => {
            let thresh_json = block.thresholds().map(|t| {
                serde_json::json!({
                    "vthreshold_v": t.vthreshold_v().map(|v| v.get()),
                    "rseries_ohm": t.rseries_ohm().map(|v| v.get()),
                    "cseries_farad": t.cseries_farad().map(|v| v.get()),
                    "lseries_henry": t.lseries_henry().map(|v| v.get()),
                })
            });

            serde_json::json!({
                "policy": SERIES_SWITCH_KEYWORDS_POLICY_V1,
                "valid": true,
                "on_group_name": block.switch_record().on_group_name(),
                "off_group_name": block.switch_record().off_group_name(),
                "thresholds": thresh_json,
            })
        }
        Err(e) => {
            serde_json::json!({
                "policy": SERIES_SWITCH_KEYWORDS_POLICY_V1,
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
