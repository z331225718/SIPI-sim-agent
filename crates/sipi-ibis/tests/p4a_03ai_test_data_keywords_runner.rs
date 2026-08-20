//! External-only typed test data block keywords cross-check runner (P4A-03ai).
//!
//! Lifts one typed [Test Data] / [Test Load] complete block from input parameters
//! and reports the properties for hash-only comparison against an independent reference.
//! Ignored by default; external-custody tooling only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_ibis::{
    lift_test_data_block_v1, lift_test_data_declaration_v1, TEST_DATA_KEYWORDS_POLICY_V1,
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
        println!("usage: p4a_03ai_test_data_keywords_runner --input <json> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");

    let fname = value.get("fixture_name").and_then(|v| v.as_str()).unwrap_or("");
    let r_fix = value.get("r_fixture_ohm").and_then(|v| v.as_f64());
    let c_fix = value.get("c_fixture_farad").and_then(|v| v.as_f64());
    let l_fix = value.get("l_fixture_henry").and_then(|v| v.as_f64());
    let v_fix = value.get("v_fixture_volts").and_then(|v| v.as_f64());

    let fix_decl = match lift_test_data_declaration_v1(fname, r_fix, c_fix, l_fix, v_fix) {
        Ok(d) => d,
        Err(e) => {
            let output = serde_json::json!({
                "policy": TEST_DATA_KEYWORDS_POLICY_V1,
                "valid": false,
                "fixture_error": format!("{e:?}"),
            });
            if let Some(p) = report {
                std::fs::write(p, serde_json::to_string_pretty(&output).expect("json")).expect("write");
            } else {
                println!("{}", serde_json::to_string_pretty(&output).expect("json"));
            }
            return;
        }
    };

    let output = match lift_test_data_block_v1(fix_decl) {
        Ok(block) => {
            serde_json::json!({
                "policy": TEST_DATA_KEYWORDS_POLICY_V1,
                "valid": true,
                "fixture_name": block.fixture_declaration().fixture_name(),
                "r_fixture_ohm": block.fixture_declaration().r_fixture_ohm().map(|v| v.get()),
                "c_fixture_farad": block.fixture_declaration().c_fixture_farad().map(|v| v.get()),
                "l_fixture_henry": block.fixture_declaration().l_fixture_henry().map(|v| v.get()),
                "v_fixture_volts": block.fixture_declaration().v_fixture_volts().map(|v| v.get()),
            })
        }
        Err(e) => {
            serde_json::json!({
                "policy": TEST_DATA_KEYWORDS_POLICY_V1,
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
