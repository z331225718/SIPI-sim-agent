//! External-only typed test data cross-check runner (P4A-03r).
//!
//! Lifts one typed [Test Data] / [Test Load] record from input parameters
//! and reports the properties for hash-only comparison against an independent reference.
//! Ignored by default; external-custody tooling only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_ibis::{
    lift_test_data_declaration_v1, TEST_DATA_DECLARATION_POLICY_V1,
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
        println!("usage: p4a_03r_test_data_runner --input <json> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");
    let fname = value.get("fixture_name").and_then(|v| v.as_str()).unwrap_or("");
    let r_fix = value.get("r_fixture_ohm").and_then(|v| v.as_f64());
    let c_fix = value.get("c_fixture_farad").and_then(|v| v.as_f64());
    let l_fix = value.get("l_fixture_henry").and_then(|v| v.as_f64());
    let v_fix = value.get("v_fixture_volts").and_then(|v| v.as_f64());

    let output = match lift_test_data_declaration_v1(fname, r_fix, c_fix, l_fix, v_fix) {
        Ok(fix) => {
            serde_json::json!({
                "policy": TEST_DATA_DECLARATION_POLICY_V1,
                "valid": true,
                "fixture_name": fix.fixture_name(),
                "r_fixture_ohm": fix.r_fixture_ohm().map(|v| v.get()),
                "c_fixture_farad": fix.c_fixture_farad().map(|v| v.get()),
                "l_fixture_henry": fix.l_fixture_henry().map(|v| v.get()),
                "v_fixture_volts": fix.v_fixture_volts().map(|v| v.get()),
            })
        }
        Err(e) => {
            serde_json::json!({
                "policy": TEST_DATA_DECLARATION_POLICY_V1,
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
