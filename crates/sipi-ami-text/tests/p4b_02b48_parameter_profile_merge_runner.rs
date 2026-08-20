//! External-only parameter profile merge cross-check runner (P4B-02b48).
//!
//! Merges two caller-supplied parameter maps (name -> type/value) and reports
//! the merged map and matched count for hash-only comparison against an
//! independent reference. Ignored by default; external-custody tooling only.

use std::collections::BTreeMap;
use std::path::PathBuf;

use serde_json::Value;
use sipi_ami_text::{
    AmiParameterValueV1, PARAMETER_PROFILE_MERGE_POLICY_V1, merge_parameter_profiles_v1,
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

pub(crate) fn main() {
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
        println!(
            "usage: p4b_02b48_parameter_profile_merge_runner --input <path> [--report <path>]"
        );
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");

    let a = match value.get("a").and_then(parse_profile) {
        Some(p) => p,
        None => {
            let output = serde_json::json!({
                "policy": PARAMETER_PROFILE_MERGE_POLICY_V1,
                "valid": false,
                "input_error": "invalid_profile_a",
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
    let b = match value.get("b").and_then(parse_profile) {
        Some(p) => p,
        None => {
            let output = serde_json::json!({
                "policy": PARAMETER_PROFILE_MERGE_POLICY_V1,
                "valid": false,
                "input_error": "invalid_profile_b",
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

    let output = match merge_parameter_profiles_v1(&a, &b) {
        Ok(merge) => {
            let mut parameters = serde_json::Map::new();
            for (name, parameter) in merge.parameters() {
                parameters.insert(name.clone(), parameter_to_json(parameter));
            }
            serde_json::json!({
                "policy": PARAMETER_PROFILE_MERGE_POLICY_V1,
                "valid": true,
                "matched": merge.matched(),
                "parameters": Value::Object(parameters),
            })
        }
        Err(e) => {
            serde_json::json!({
                "policy": PARAMETER_PROFILE_MERGE_POLICY_V1,
                "valid": false,
                "merge_error": format!("{e:?}"),
            })
        }
    };

    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string_pretty(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string_pretty(&output).expect("json"));
    }
}
