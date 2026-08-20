//! External-only parameter profile typed subset check cross-check runner (P4B-02b90).
//!
//! Reads one JSON case {subset: {name: {type, value}}, superset: {...}},
//! builds validated profiles, checks whether the subset profile is a typed
//! subset of the superset, and reports {is_subset, missing, mismatched} for
//! hash-only comparison against an independent reference. Ignored by default;
//! external-custody tooling only.

use std::collections::BTreeMap;
use std::path::PathBuf;

use serde_json::Value;
use sipi_ami_text::{
    check_parameter_profile_typed_subset_v1, AmiParameterValueV1,
    PARAMETER_PROFILE_TYPED_SUBSET_POLICY_V1,
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
        println!("usage: p4b_02b90_parameter_profile_typed_subset_runner --input <path> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");

    let subset = match value.get("subset").and_then(build_profile) {
        Some(p) => p,
        None => {
            let output = serde_json::json!({
                "policy": PARAMETER_PROFILE_TYPED_SUBSET_POLICY_V1,
                "valid": false,
                "input_error": "invalid_subset_profile",
            });
            if let Some(p) = report {
                std::fs::write(p, serde_json::to_string_pretty(&output).expect("json")).expect("write");
            } else {
                println!("{}", serde_json::to_string_pretty(&output).expect("json"));
            }
            return;
        }
    };
    let superset = match value.get("superset").and_then(build_profile) {
        Some(p) => p,
        None => {
            let output = serde_json::json!({
                "policy": PARAMETER_PROFILE_TYPED_SUBSET_POLICY_V1,
                "valid": false,
                "input_error": "invalid_superset_profile",
            });
            if let Some(p) = report {
                std::fs::write(p, serde_json::to_string_pretty(&output).expect("json")).expect("write");
            } else {
                println!("{}", serde_json::to_string_pretty(&output).expect("json"));
            }
            return;
        }
    };

    let result = check_parameter_profile_typed_subset_v1(&subset, &superset);
    let mismatched: Vec<Value> = result
        .mismatched()
        .iter()
        .map(|m| {
            serde_json::json!({
                "name": m.name(),
                "reason": m.reason().key(),
            })
        })
        .collect();
    let output = serde_json::json!({
        "policy": PARAMETER_PROFILE_TYPED_SUBSET_POLICY_V1,
        "valid": true,
        "is_subset": result.is_subset(),
        "missing": result.missing(),
        "mismatched": mismatched,
    });
    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string_pretty(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string_pretty(&output).expect("json"));
    }
}
