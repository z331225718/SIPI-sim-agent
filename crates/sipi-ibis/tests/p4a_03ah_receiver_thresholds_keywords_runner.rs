//! External-only typed receiver thresholds block keywords cross-check runner (P4A-03ah).
//!
//! Lifts one typed [Receiver Thresholds] complete block from input parameters
//! and reports the properties for hash-only comparison against an independent reference.
//! Ignored by default; external-custody tooling only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_ibis::{
    lift_receiver_thresholds_block_v1, lift_receiver_thresholds_v1,
    RECEIVER_THRESHOLDS_KEYWORDS_POLICY_V1,
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
        println!("usage: p4a_03ah_receiver_thresholds_keywords_runner --input <json> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");

    let vcross_low = value.get("vcross_low_v").and_then(|v| v.as_f64());
    let vcross_high = value.get("vcross_high_v").and_then(|v| v.as_f64());
    let vdiff_ac = value.get("vdiff_ac_v").and_then(|v| v.as_f64());
    let vdiff_dc = value.get("vdiff_dc_v").and_then(|v| v.as_f64());
    let tskew = value.get("tskew_s").and_then(|v| v.as_f64());

    let rx = match lift_receiver_thresholds_v1(vcross_low, vcross_high, vdiff_ac, vdiff_dc, tskew) {
        Ok(t) => t,
        Err(e) => {
            let output = serde_json::json!({
                "policy": RECEIVER_THRESHOLDS_KEYWORDS_POLICY_V1,
                "valid": false,
                "threshold_error": format!("{e:?}"),
            });
            if let Some(p) = report {
                std::fs::write(p, serde_json::to_string_pretty(&output).expect("json")).expect("write");
            } else {
                println!("{}", serde_json::to_string_pretty(&output).expect("json"));
            }
            return;
        }
    };

    let vsensitivity = value.get("vsensitivity_v").and_then(|v| v.as_f64());

    let output = match lift_receiver_thresholds_block_v1(rx, vsensitivity) {
        Ok(block) => {
            serde_json::json!({
                "policy": RECEIVER_THRESHOLDS_KEYWORDS_POLICY_V1,
                "valid": true,
                "vcross_low_v": block.thresholds().vcross_low_v().map(|v| v.get()),
                "vcross_high_v": block.thresholds().vcross_high_v().map(|v| v.get()),
                "vdiff_ac_v": block.thresholds().vdiff_ac_v().map(|v| v.get()),
                "vdiff_dc_v": block.thresholds().vdiff_dc_v().map(|v| v.get()),
                "tskew_s": block.thresholds().tskew_s().map(|v| v.get()),
                "vsensitivity_v": block.vsensitivity_v().map(|v| v.get()),
            })
        }
        Err(e) => {
            serde_json::json!({
                "policy": RECEIVER_THRESHOLDS_KEYWORDS_POLICY_V1,
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
