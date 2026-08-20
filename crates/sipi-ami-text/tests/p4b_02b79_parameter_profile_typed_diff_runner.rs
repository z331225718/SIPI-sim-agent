//! External-only typed parameter profile diff cross-check runner (P4B-02b79).
//!
//! Reads one JSON case {left: {name: {type, value}}, right: {...}}, builds
//! validated profiles, diffs them under typed value semantics, and reports
//! {matched, added, removed, changed} for hash-only comparison against an
//! independent reference. Ignored by default; external-custody tooling only.

use std::collections::BTreeMap;
use std::path::PathBuf;

use serde_json::Value;
use sipi_ami_text::{
    AmiParameterValueV1, PARAMETER_PROFILE_TYPED_DIFF_POLICY_V1, diff_parameter_profiles_typed_v1,
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
            "usage: p4b_02b79_parameter_profile_typed_diff_runner --input <path> [--report <path>]"
        );
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");

    let left = match value.get("left").and_then(build_profile) {
        Some(p) => p,
        None => {
            let output = serde_json::json!({
                "policy": PARAMETER_PROFILE_TYPED_DIFF_POLICY_V1,
                "valid": false,
                "input_error": "invalid_left_profile",
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
    let right = match value.get("right").and_then(build_profile) {
        Some(p) => p,
        None => {
            let output = serde_json::json!({
                "policy": PARAMETER_PROFILE_TYPED_DIFF_POLICY_V1,
                "valid": false,
                "input_error": "invalid_right_profile",
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

    let diff = diff_parameter_profiles_typed_v1(&left, &right);
    let changed: Vec<Value> = diff
        .changed()
        .iter()
        .map(|c| {
            serde_json::json!({
                "name": c.name(),
                "old_type": c.old_type(),
                "old_value": c.old_value(),
                "new_type": c.new_type(),
                "new_value": c.new_value(),
                "reason": c.reason().key(),
            })
        })
        .collect();
    let output = serde_json::json!({
        "policy": PARAMETER_PROFILE_TYPED_DIFF_POLICY_V1,
        "valid": true,
        "matched": diff.matched(),
        "added": diff.added(),
        "removed": diff.removed(),
        "changed": changed,
    });
    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string_pretty(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string_pretty(&output).expect("json"));
    }
}
