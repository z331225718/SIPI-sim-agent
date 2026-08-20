//! External-only parameter value semantic equivalence cross-check runner (P4B-02b70).
//!
//! Reads one JSON case {left: {name,type,value}, right: {name,type,value}},
//! builds validated AmiParameterValueV1 values, compares them by typed
//! semantics, and reports {equivalent, reason} for hash-only comparison
//! against an independent reference. Ignored by default; external-custody
//! tooling only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_ami_text::{
    parameter_values_equivalent_v1, AmiParameterValueV1, ParameterValueEquivalenceV1,
    ParameterValueInequivalenceReasonV1, PARAMETER_VALUE_EQUIVALENCE_POLICY_V1,
};

fn build_value(entry: &Value) -> Option<AmiParameterValueV1> {
    let name = entry.get("name")?.as_str()?;
    let type_token = entry.get("type")?.as_str()?;
    let value_token = entry.get("value")?.as_str()?;
    AmiParameterValueV1::try_new(name, type_token, value_token).ok()
}

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
        println!("usage: p4b_02b70_parameter_value_equivalence_runner --input <path> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");

    let left = match value.get("left").and_then(build_value) {
        Some(v) => v,
        None => {
            let output = serde_json::json!({
                "policy": PARAMETER_VALUE_EQUIVALENCE_POLICY_V1,
                "valid": false,
                "input_error": "invalid_left_value",
            });
            if let Some(p) = report {
                std::fs::write(p, serde_json::to_string_pretty(&output).expect("json")).expect("write");
            } else {
                println!("{}", serde_json::to_string_pretty(&output).expect("json"));
            }
            return;
        }
    };
    let right = match value.get("right").and_then(build_value) {
        Some(v) => v,
        None => {
            let output = serde_json::json!({
                "policy": PARAMETER_VALUE_EQUIVALENCE_POLICY_V1,
                "valid": false,
                "input_error": "invalid_right_value",
            });
            if let Some(p) = report {
                std::fs::write(p, serde_json::to_string_pretty(&output).expect("json")).expect("write");
            } else {
                println!("{}", serde_json::to_string_pretty(&output).expect("json"));
            }
            return;
        }
    };

    let (equivalent, reason) = match parameter_values_equivalent_v1(&left, &right) {
        ParameterValueEquivalenceV1::Equivalent => (true, None),
        ParameterValueEquivalenceV1::NotEquivalent(reason) => (false, Some(reason.key())),
    };
    let output = serde_json::json!({
        "policy": PARAMETER_VALUE_EQUIVALENCE_POLICY_V1,
        "valid": true,
        "equivalent": equivalent,
        "reason": reason,
        "left": {
            "name": left.name(),
            "type": left.parameter_type().token(),
            "value": left.value_token(),
        },
        "right": {
            "name": right.name(),
            "type": right.parameter_type().token(),
            "value": right.value_token(),
        },
    });
    if let Some(p) = report {
        std::fs::write(p, serde_json::to_string_pretty(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string_pretty(&output).expect("json"));
    }
}
