//! External-only parameter profile value reverse lookup cross-check runner (P4B-02b80).
//!
//! Reads one JSON case {profile: {name: {type, value}}, query: {name, type,
//! value}}, finds every profile name whose entry is typed-equivalent to the
//! query, and reports {matches} for hash-only comparison against an
//! independent reference. Ignored by default; external-custody tooling only.

use std::collections::BTreeMap;
use std::path::PathBuf;

use serde_json::Value;
use sipi_ami_text::{
    find_parameter_profile_names_by_value_v1, AmiParameterValueV1,
    ParameterProfileValueLookupErrorV1, PARAMETER_PROFILE_VALUE_LOOKUP_POLICY_V1,
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
        println!("usage: p4b_02b80_parameter_profile_value_lookup_runner --input <path> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");

    let profile = match value.get("profile").and_then(build_profile) {
        Some(p) => p,
        None => {
            let output = serde_json::json!({
                "policy": PARAMETER_PROFILE_VALUE_LOOKUP_POLICY_V1,
                "valid": false,
                "input_error": "invalid_profile",
            });
            if let Some(p) = report {
                std::fs::write(p, serde_json::to_string_pretty(&output).expect("json")).expect("write");
            } else {
                println!("{}", serde_json::to_string_pretty(&output).expect("json"));
            }
            return;
        }
    };
    let query = value.get("query").cloned().unwrap_or(Value::Null);
    let query_name = query.get("name").and_then(|v| v.as_str()).unwrap_or("");
    let query_type_token = query.get("type").and_then(|v| v.as_str()).unwrap_or("");
    let query_value_token = query.get("value").and_then(|v| v.as_str()).unwrap_or("");

    let output = match find_parameter_profile_names_by_value_v1(
        &profile,
        query_name,
        query_type_token,
        query_value_token,
    ) {
        Ok(result) => serde_json::json!({
            "policy": PARAMETER_PROFILE_VALUE_LOOKUP_POLICY_V1,
            "valid": true,
            "matches": result.matches(),
        }),
        Err(ParameterProfileValueLookupErrorV1::InvalidQueryValue(error)) => {
            serde_json::json!({
                "policy": PARAMETER_PROFILE_VALUE_LOOKUP_POLICY_V1,
                "valid": false,
                "error": "InvalidQueryValue".to_string(),
            })
        }
    };
    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string_pretty(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string_pretty(&output).expect("json"));
    }
}
