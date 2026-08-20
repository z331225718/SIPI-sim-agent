//! External-only parameter profile canonical spelling groups cross-check runner (P4B-02b92).
//!
//! Reads one JSON case {profile: {name: {type, value}}}, builds the validated
//! profile, groups names by canonical value spelling, and reports the groups
//! for hash-only comparison against an independent reference. Ignored by
//! default; external-custody tooling only.

use std::collections::BTreeMap;
use std::path::PathBuf;

use serde_json::Value;
use sipi_ami_text::{
    AmiParameterValueV1, PARAMETER_PROFILE_CANONICAL_SPELLING_GROUPS_POLICY_V1,
    group_parameter_profile_names_by_canonical_spelling_v1,
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
            "usage: p4b_02b92_parameter_profile_canonical_spelling_groups_runner --input <path> [--report <path>]"
        );
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");

    let profile = match value.get("profile").and_then(build_profile) {
        Some(p) => p,
        None => {
            let output = serde_json::json!({
                "policy": PARAMETER_PROFILE_CANONICAL_SPELLING_GROUPS_POLICY_V1,
                "valid": false,
                "input_error": "invalid_profile",
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

    let result = group_parameter_profile_names_by_canonical_spelling_v1(&profile);
    let groups: Vec<Value> = result
        .groups()
        .iter()
        .map(|group| {
            serde_json::json!({
                "spelling": group.spelling(),
                "names": group.names(),
            })
        })
        .collect();
    let output = serde_json::json!({
        "policy": PARAMETER_PROFILE_CANONICAL_SPELLING_GROUPS_POLICY_V1,
        "valid": true,
        "group_count": result.group_count(),
        "singleton_count": result.singleton_count(),
        "covered_names": result.covered_names(),
        "groups": groups,
    });
    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string_pretty(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string_pretty(&output).expect("json"));
    }
}
