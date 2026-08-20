//! External-only typed diff pin block keywords cross-check runner (P4A-03al).
//!
//! Lifts one typed [Diff Pin] complete block from input parameters
//! and reports the properties for hash-only comparison against an independent reference.
//! Ignored by default; external-custody tooling only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_ibis::{
    DIFF_PIN_KEYWORDS_POLICY_V1, lift_diff_pin_block_v1, lift_diff_pin_declaration_v1,
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
        println!("usage: p4a_03al_diff_pin_keywords_runner --input <json> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");

    let p1 = value
        .get("pin_non_inv")
        .and_then(|v| v.as_str())
        .unwrap_or("");
    let p2 = value.get("pin_inv").and_then(|v| v.as_str()).unwrap_or("");
    let vdiff = value.get("vdiff_v").and_then(|v| v.as_f64());
    let tdelay = value.get("tdelay_s").and_then(|v| v.as_f64());

    let diff_decl = match lift_diff_pin_declaration_v1(p1, p2, vdiff, tdelay) {
        Ok(d) => d,
        Err(e) => {
            let output = serde_json::json!({
                "policy": DIFF_PIN_KEYWORDS_POLICY_V1,
                "valid": false,
                "diff_error": format!("{e:?}"),
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

    let output = match lift_diff_pin_block_v1(diff_decl) {
        Ok(block) => {
            serde_json::json!({
                "policy": DIFF_PIN_KEYWORDS_POLICY_V1,
                "valid": true,
                "pin_non_inv": block.diff_pin_declaration().pin_non_inv(),
                "pin_inv": block.diff_pin_declaration().pin_inv(),
                "vdiff_v": block.diff_pin_declaration().vdiff_v().map(|v| v.get()),
                "tdelay_s": block.diff_pin_declaration().tdelay_s().map(|v| v.get()),
            })
        }
        Err(e) => {
            serde_json::json!({
                "policy": DIFF_PIN_KEYWORDS_POLICY_V1,
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
