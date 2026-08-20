//! External-only parameter profile canonical deserialization cross-check runner (P4B-02b82).
//!
//! Reads one JSON case {json: "..."}, deserializes the canonical profile
//! document, and reports the profile map or the fail-closed error for hash-only
//! comparison against an independent reference. Ignored by default;
//! external-custody tooling only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_ami_text::{
    PARAMETER_PROFILE_DESERIALIZATION_POLICY_V1, ParameterProfileDeserializationErrorV1,
    deserialize_parameter_profile_v1,
};

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
            "usage: p4b_02b82_parameter_profile_deserialization_runner --input <path> [--report <path>]"
        );
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");

    let json_text = value.get("json").and_then(|v| v.as_str()).unwrap_or("");

    let output = match deserialize_parameter_profile_v1(json_text) {
        Ok(result) => {
            let profile: Value = result
                .profile()
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
            serde_json::json!({
                "policy": PARAMETER_PROFILE_DESERIALIZATION_POLICY_V1,
                "valid": true,
                "profile": profile,
            })
        }
        Err(ParameterProfileDeserializationErrorV1::InvalidJson(_)) => {
            serde_json::json!({
                "policy": PARAMETER_PROFILE_DESERIALIZATION_POLICY_V1,
                "valid": false,
                "error": "InvalidJson",
            })
        }
        Err(ParameterProfileDeserializationErrorV1::NotAnObject) => {
            serde_json::json!({
                "policy": PARAMETER_PROFILE_DESERIALIZATION_POLICY_V1,
                "valid": false,
                "error": "NotAnObject",
            })
        }
        Err(ParameterProfileDeserializationErrorV1::EntryNotObject(name)) => {
            serde_json::json!({
                "policy": PARAMETER_PROFILE_DESERIALIZATION_POLICY_V1,
                "valid": false,
                "error": "EntryNotObject",
                "name": name,
            })
        }
        Err(ParameterProfileDeserializationErrorV1::MissingType(name)) => {
            serde_json::json!({
                "policy": PARAMETER_PROFILE_DESERIALIZATION_POLICY_V1,
                "valid": false,
                "error": "MissingType",
                "name": name,
            })
        }
        Err(ParameterProfileDeserializationErrorV1::MissingValue(name)) => {
            serde_json::json!({
                "policy": PARAMETER_PROFILE_DESERIALIZATION_POLICY_V1,
                "valid": false,
                "error": "MissingValue",
                "name": name,
            })
        }
        Err(ParameterProfileDeserializationErrorV1::InvalidValue { name, .. }) => {
            serde_json::json!({
                "policy": PARAMETER_PROFILE_DESERIALIZATION_POLICY_V1,
                "valid": false,
                "error": "InvalidValue",
                "name": name,
            })
        }
    };
    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string_pretty(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string_pretty(&output).expect("json"));
    }
}
