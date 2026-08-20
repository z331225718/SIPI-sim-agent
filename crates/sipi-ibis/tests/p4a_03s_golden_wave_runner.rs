//! External-only typed golden waveforms cross-check runner (P4A-03s).
//!
//! Lifts one typed [Golden Waveforms] record from input parameters
//! and reports the properties for hash-only comparison against an independent reference.
//! Ignored by default; external-custody tooling only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_ibis::{GOLDEN_WAVE_DECLARATION_POLICY_V1, lift_golden_wave_declaration_v1};

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
        println!("usage: p4a_03s_golden_wave_runner --input <json> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");
    let wname = value
        .get("waveform_name")
        .and_then(|v| v.as_str())
        .unwrap_or("");
    let dname = value.get("dut_name").and_then(|v| v.as_str());

    let output = match lift_golden_wave_declaration_v1(wname, dname) {
        Ok(wave) => {
            serde_json::json!({
                "policy": GOLDEN_WAVE_DECLARATION_POLICY_V1,
                "valid": true,
                "waveform_name": wave.waveform_name(),
                "dut_name": wave.dut_name(),
            })
        }
        Err(e) => {
            serde_json::json!({
                "policy": GOLDEN_WAVE_DECLARATION_POLICY_V1,
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
