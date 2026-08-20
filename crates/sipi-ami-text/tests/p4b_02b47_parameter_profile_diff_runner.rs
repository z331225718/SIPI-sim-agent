//! External-only parameter profile diff cross-check runner (P4B-02b47).
//!
//! Compares two caller-supplied parameter maps (name -> type/value) and reports
//! added/removed/changed entries plus a matched count for hash-only comparison
//! against an independent reference. Ignored by default; external-custody
//! tooling only.

use std::collections::BTreeMap;
use std::path::PathBuf;

use serde_json::Value;
use sipi_ami_text::{
    diff_parameter_profiles_v1, AmiParameterValueV1, PARAMETER_PROFILE_DIFF_POLICY_V1,
};

fn parse_profile(value: &Value) -> Option<BTreeMap<String, AmiParameterValueV1>> {
    let mut profile = BTreeMap::new();
    let obj = value.as_object()?;
    for (name, entry) in obj {
        let type_token = entry.get("type")?.as_str()?;
        let value_token = entry.get("value")?.as_str()?;
        let parameter = AmiParameterValueV1::try_new(name, type_token, value_token).ok()?;
        profile.insert(name.clone(), parameter);
    }
    Some(profile)
}

fn parameter_to_json(parameter: &AmiParameterValueV1) -> Value {
    serde_json::json!({
        "type": parameter.parameter_type().token(),
        "value": parameter.value_token(),
    })
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
        println!("usage: p4b_02b47_parameter_profile_diff_runner --input <path> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");

    let a = match value.get("a").and_then(parse_profile) {
        Some(p) => p,
        None => {
            let output = serde_json::json!({
                "policy": PARAMETER_PROFILE_DIFF_POLICY_V1,
                "valid": false,
                "input_error": "invalid_profile_a",
            });
            if let Some(p) = report {
                std::fs::write(p, serde_json::to_string_pretty(&output).expect("json")).expect("write");
            } else {
                println!("{}", serde_json::to_string_pretty(&output).expect("json"));
            }
            return;
        }
    };
    let b = match value.get("b").and_then(parse_profile) {
        Some(p) => p,
        None => {
            let output = serde_json::json!({
                "policy": PARAMETER_PROFILE_DIFF_POLICY_V1,
                "valid": false,
                "input_error": "invalid_profile_b",
            });
            if let Some(p) = report {
                std::fs::write(p, serde_json::to_string_pretty(&output).expect("json")).expect("write");
            } else {
                println!("{}", serde_json::to_string_pretty(&output).expect("json"));
            }
            return;
        }
    };

    let diff = diff_parameter_profiles_v1(&a, &b);
    let changed_json: Vec<Value> = diff
        .changed()
        .iter()
        .map(|change| {
            serde_json::json!({
                "name": change.name(),
                "old": parameter_to_json(change.old()),
                "new": parameter_to_json(change.new()),
            })
        })
        .collect();
    let output = serde_json::json!({
        "policy": PARAMETER_PROFILE_DIFF_POLICY_V1,
        "valid": true,
        "matched": diff.matched(),
        "added": diff.added(),
        "removed": diff.removed(),
        "changed": Value::Array(changed_json),
    });

    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string_pretty(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string_pretty(&output).expect("json"));
    }
}
