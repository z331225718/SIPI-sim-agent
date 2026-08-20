//! External-only parameter profile completeness check cross-check runner (P4B-02b55).
//!
//! Reads a parameter map and a required-name set, checks completeness, and
//! reports the outcome for hash-only comparison against an independent
//! reference. Ignored by default; external-custody tooling only.

use std::collections::{BTreeMap, BTreeSet};
use std::path::PathBuf;

use serde_json::Value;
use sipi_ami_text::{
    check_parameter_profile_completeness_v1, AmiParameterValueV1,
    PARAMETER_PROFILE_COMPLETENESS_POLICY_V1,
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
        println!("usage: p4b_02b55_parameter_profile_completeness_runner --input <path> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");

    let parameters = match value.get("parameters").and_then(parse_profile) {
        Some(p) => p,
        None => {
            let output = serde_json::json!({
                "policy": PARAMETER_PROFILE_COMPLETENESS_POLICY_V1,
                "valid": false,
                "input_error": "invalid_parameters",
            });
            if let Some(p) = report {
                std::fs::write(p, serde_json::to_string_pretty(&output).expect("json")).expect("write");
            } else {
                println!("{}", serde_json::to_string_pretty(&output).expect("json"));
            }
            return;
        }
    };
    let mut required = BTreeSet::new();
    if let Some(arr) = value.get("required").and_then(|v| v.as_array()) {
        for item in arr {
            if let Some(name) = item.as_str() {
                required.insert(name.to_string());
            }
        }
    }

    let output = match check_parameter_profile_completeness_v1(&parameters, &required) {
        Ok(check) => {
            serde_json::json!({
                "policy": PARAMETER_PROFILE_COMPLETENESS_POLICY_V1,
                "valid": true,
                "expected": check.expected(),
                "present": check.present(),
                "missing": check.missing(),
                "complete": check.is_complete(),
            })
        }
        Err(e) => {
            serde_json::json!({
                "policy": PARAMETER_PROFILE_COMPLETENESS_POLICY_V1,
                "valid": false,
                "completeness_error": format!("{e:?}"),
            })
        }
    };

    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string_pretty(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string_pretty(&output).expect("json"));
    }
}
