//! External-only typed differential-pin-declaration cross-check runner (P4A-03j).
//!
//! Lifts one typed [Diff Pin] declaration from input parameters and reports
//! the differential pin properties for hash-only comparison against an
//! independent reference. Ignored by default; external-custody tooling only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_ibis::{
    lift_diff_pin_declaration_v1, DIFF_PIN_DECLARATION_POLICY_V1,
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
        println!("usage: p4a_03j_diff_pin_runner --input <json> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");
    let pin_non_inv = value.get("pin_non_inv").and_then(|v| v.as_str()).unwrap_or("");
    let pin_inv = value.get("pin_inv").and_then(|v| v.as_str()).unwrap_or("");
    let vdiff_v = value.get("vdiff_v").and_then(|v| v.as_f64());
    let tdelay_s = value.get("tdelay_s").and_then(|v| v.as_f64());

    let output = match lift_diff_pin_declaration_v1(pin_non_inv, pin_inv, vdiff_v, tdelay_s) {
        Ok(diff) => {
            serde_json::json!({
                "policy": DIFF_PIN_DECLARATION_POLICY_V1,
                "valid": true,
                "pin_non_inv": diff.pin_non_inv(),
                "pin_inv": diff.pin_inv(),
                "vdiff_v": diff.vdiff_v().map(|v| v.get()),
                "tdelay_s": diff.tdelay_s().map(|v| v.get()),
            })
        }
        Err(e) => {
            serde_json::json!({
                "policy": DIFF_PIN_DECLARATION_POLICY_V1,
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
