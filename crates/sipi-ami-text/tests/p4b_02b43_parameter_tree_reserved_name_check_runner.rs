//! External-only parameter tree reserved-name check cross-check runner (P4B-02b43).
//!
//! Parses raw parenthesized AMI text, builds typed parameter tree hierarchies,
//! checks every distinct leaf name against a caller-supplied reserved-name set,
//! and reports the outcome for hash-only comparison against an independent
//! reference. Ignored by default; external-custody tooling only.

use std::collections::BTreeSet;
use std::path::PathBuf;

use serde_json::Value;
use sipi_ami_text::{
    PARAMETER_TREE_RESERVED_NAME_CHECK_POLICY_V1, ParseLimitsV1, build_parameter_trees_v1,
    check_parameter_tree_reserved_names_v1, parse_ami_text_v1,
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
            "usage: p4b_02b43_parameter_tree_reserved_name_check_runner --input <path> [--report <path>]"
        );
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");

    let text = value.get("text").and_then(|v| v.as_str()).unwrap_or("");
    let mut reserved = BTreeSet::new();
    if let Some(reserved_json) = value.get("reserved").and_then(|v| v.as_array()) {
        for item in reserved_json {
            if let Some(name) = item.as_str() {
                reserved.insert(name.to_string());
            }
        }
    }

    let limits = ParseLimitsV1::try_new(8 * 1024 * 1024, 64, 4096, 4096).expect("limits");
    let doc = match parse_ami_text_v1(text.as_bytes(), limits) {
        Ok(d) => d,
        Err(e) => {
            let output = serde_json::json!({
                "policy": PARAMETER_TREE_RESERVED_NAME_CHECK_POLICY_V1,
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
                "policy": PARAMETER_TREE_RESERVED_NAME_CHECK_POLICY_V1,
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

    let output = match check_parameter_tree_reserved_names_v1(&trees[0], &reserved) {
        Ok(check) => {
            serde_json::json!({
                "policy": PARAMETER_TREE_RESERVED_NAME_CHECK_POLICY_V1,
                "valid": true,
                "leaves_checked": check.leaves_checked(),
                "clean": check.is_clean(),
                "violations": check.violations(),
            })
        }
        Err(e) => {
            serde_json::json!({
                "policy": PARAMETER_TREE_RESERVED_NAME_CHECK_POLICY_V1,
                "valid": false,
                "reserved_error": format!("{e:?}"),
            })
        }
    };

    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string_pretty(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string_pretty(&output).expect("json"));
    }
}
