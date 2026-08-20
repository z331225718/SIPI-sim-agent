//! External-only parameter profile tree coverage cross-check runner (P4B-02b72).
//!
//! Parses raw parenthesized AMI text, builds typed parameter tree hierarchies,
//! and reports how an assembled profile covers the tree leaves (covered /
//! ambiguous / missing) for hash-only comparison against an independent
//! reference. Ignored by default; external-custody tooling only.

use std::collections::BTreeMap;
use std::path::PathBuf;

use serde_json::Value;
use sipi_ami_text::{
    AmiParameterValueV1, PARAMETER_PROFILE_TREE_COVERAGE_POLICY_V1, ParseLimitsV1,
    build_parameter_trees_v1, check_parameter_profile_tree_coverage_v1, parse_ami_text_v1,
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
            "usage: p4b_02b72_parameter_profile_tree_coverage_runner --input <path> [--report <path>]"
        );
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");

    let text = value.get("text").and_then(|v| v.as_str()).unwrap_or("");
    let profile = match value.get("profile").and_then(parse_profile) {
        Some(p) => p,
        None => {
            let output = serde_json::json!({
                "policy": PARAMETER_PROFILE_TREE_COVERAGE_POLICY_V1,
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

    let limits = ParseLimitsV1::try_new(8 * 1024 * 1024, 64, 4096, 4096).expect("limits");
    let doc = match parse_ami_text_v1(text.as_bytes(), limits) {
        Ok(d) => d,
        Err(e) => {
            let output = serde_json::json!({
                "policy": PARAMETER_PROFILE_TREE_COVERAGE_POLICY_V1,
                "valid": false,
                "parse_error": format!("{e:?}"),
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
    let trees = match build_parameter_trees_v1(&doc) {
        Ok(t) => t,
        Err(e) => {
            let output = serde_json::json!({
                "policy": PARAMETER_PROFILE_TREE_COVERAGE_POLICY_V1,
                "valid": false,
                "build_error": format!("{e:?}"),
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

    let coverage = check_parameter_profile_tree_coverage_v1(&trees[0], &profile);
    let output = serde_json::json!({
        "policy": PARAMETER_PROFILE_TREE_COVERAGE_POLICY_V1,
        "valid": true,
        "profile_names": coverage.profile_names(),
        "covered": coverage.covered(),
        "ambiguous": coverage.ambiguous(),
        "missing": coverage.missing(),
        "complete": coverage.complete(),
        "unambiguous": coverage.unambiguous(),
    });
    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string_pretty(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string_pretty(&output).expect("json"));
    }
}
