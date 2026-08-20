//! External-only parameter profile selection cross-check runner (P4B-02b64).
//!
//! Reads a parameter map and a selection name set, selects the sub-profile, and
//! reports it for hash-only comparison against an independent reference.
//! Ignored by default; external-custody tooling only.

use std::collections::{BTreeMap, BTreeSet};
use std::path::PathBuf;

use serde_json::Value;
use sipi_ami_text::{
    select_parameter_profile_v1, AmiParameterValueV1, PARAMETER_PROFILE_SELECTION_POLICY_V1,
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
        println!("usage: p4b_02b64_parameter_profile_select_runner --input <path> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");

    let parameters = match value.get("parameters").and_then(parse_profile) {
        Some(p) => p,
        None => {
            let output = serde_json::json!({
                "policy": PARAMETER_PROFILE_SELECTION_POLICY_V1,
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
    let mut select = BTreeSet::new();
    if let Some(arr) = value.get("select").and_then(|v| v.as_array()) {
        for item in arr {
            if let Some(name) = item.as_str() {
                select.insert(name.to_string());
            }
        }
    }

    let output = match select_parameter_profile_v1(&parameters, &select) {
        Ok(selection) => {
            let mut selected_json = serde_json::Map::new();
            for (name, parameter) in selection.selected() {
                selected_json.insert(name.clone(), parameter_to_json(parameter));
            }
            serde_json::json!({
                "policy": PARAMETER_PROFILE_SELECTION_POLICY_V1,
                "valid": true,
                "selected_count": selection.selected_count(),
                "selected": Value::Object(selected_json),
            })
        }
        Err(e) => {
            serde_json::json!({
                "policy": PARAMETER_PROFILE_SELECTION_POLICY_V1,
                "valid": false,
                "selection_error": format!("{e:?}"),
            })
        }
    };

    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string_pretty(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string_pretty(&output).expect("json"));
    }
}
