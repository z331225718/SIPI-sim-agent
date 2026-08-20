//! External-only typed parameter extractor cross-check runner (P4B-02b6).
//!
//! Parses raw parenthesized AMI text, extracts typed parameter values from
//! AST triples, and reports parameter names and values for hash-only comparison
//! against an independent reference. Ignored by default; external-custody tooling only.

use std::collections::BTreeMap;
use std::path::PathBuf;

use sipi_ami_text::{
    extract_parameter_values_v1, parse_ami_text_v1, ParseLimitsV1,
    PARAMETER_EXTRACTOR_POLICY_V1,
};

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
        println!("usage: p4b_02b6_parameter_extractor_runner --input <path> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let limits = ParseLimitsV1::try_new(8 * 1024 * 1024, 64, 4096, 4096).expect("limits");
    let doc = match parse_ami_text_v1(&bytes, limits) {
        Ok(d) => d,
        Err(e) => {
            let output = serde_json::json!({
                "policy": PARAMETER_EXTRACTOR_POLICY_V1,
                "valid": false,
                "parse_error": format!("{e:?}"),
            });
            if let Some(path) = report {
                std::fs::write(path, serde_json::to_string_pretty(&output).expect("json")).expect("write");
            } else {
                println!("{}", serde_json::to_string_pretty(&output).expect("json"));
            }
            return;
        }
    };

    let output = match extract_parameter_values_v1(&doc) {
        Ok(map) => {
            let mut params = BTreeMap::new();
            for (name, val) in &map {
                params.insert(name.clone(), serde_json::json!({
                    "type": val.parameter_type().token(),
                    "value_token": val.value_token(),
                }));
            }
            serde_json::json!({
                "policy": PARAMETER_EXTRACTOR_POLICY_V1,
                "valid": true,
                "parameter_count": map.len(),
                "parameters": params,
            })
        }
        Err(e) => {
            serde_json::json!({
                "policy": PARAMETER_EXTRACTOR_POLICY_V1,
                "valid": false,
                "extract_error": format!("{e:?}"),
            })
        }
    };

    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string_pretty(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string_pretty(&output).expect("json"));
    }
}
