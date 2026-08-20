//! External-only typed parameter profile override merge cross-check runner (P4B-02b76).
//!
//! Reads one JSON case {base: {name: {type, value}}, override: {...}}, builds
//! validated profiles, merges them with override semantics under typed value
//! rules, and reports {matched, overridden, parameters} for hash-only
//! comparison against an independent reference. Ignored by default;
//! external-custody tooling only.

use std::collections::BTreeMap;
use std::path::PathBuf;

use serde_json::Value;
use sipi_ami_text::{
    merge_parameter_profiles_with_override_v1, AmiParameterValueV1,
    PARAMETER_PROFILE_OVERRIDE_MERGE_POLICY_V1,
};

fn build_profile(entry: &Value) -> Option<BTreeMap<String, AmiParameterValueV1>> {
    let mut profile = BTreeMap::new();
    let obj = entry.as_object()?;
    for (name, value) in obj {
        let type_token = value.get("type")?.as_str()?;
        let value_token = value.get("value")?.as_str()?;
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
        println!("usage: p4b_02b76_parameter_profile_override_merge_runner --input <path> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");

    let base = match value.get("base").and_then(build_profile) {
        Some(p) => p,
        None => {
            let output = serde_json::json!({
                "policy": PARAMETER_PROFILE_OVERRIDE_MERGE_POLICY_V1,
                "valid": false,
                "input_error": "invalid_base_profile",
            });
            if let Some(p) = report {
                std::fs::write(p, serde_json::to_string_pretty(&output).expect("json")).expect("write");
            } else {
                println!("{}", serde_json::to_string_pretty(&output).expect("json"));
            }
            return;
        }
    };
    let override_profile = match value.get("override").and_then(build_profile) {
        Some(p) => p,
        None => {
            let output = serde_json::json!({
                "policy": PARAMETER_PROFILE_OVERRIDE_MERGE_POLICY_V1,
                "valid": false,
                "input_error": "invalid_override_profile",
            });
            if let Some(p) = report {
                std::fs::write(p, serde_json::to_string_pretty(&output).expect("json")).expect("write");
            } else {
                println!("{}", serde_json::to_string_pretty(&output).expect("json"));
            }
            return;
        }
    };

    let result = merge_parameter_profiles_with_override_v1(&base, &override_profile);
    let parameters: Value = result
        .parameters()
        .iter()
        .map(|(name, parameter)| {
            (
                name.clone(),
                serde_json::json!({
                    "type": parameter.parameter_type().token(),
                    "value": parameter.value_token(),
                }),
            )
        })
        .collect();
    let output = serde_json::json!({
        "policy": PARAMETER_PROFILE_OVERRIDE_MERGE_POLICY_V1,
        "valid": true,
        "matched": result.matched(),
        "overridden": result.overridden(),
        "parameters": parameters,
    });
    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string_pretty(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string_pretty(&output).expect("json"));
    }
}
