//! External-only AMI text form heads counting cross-check runner (P4B-02b61).
//!
//! Parses raw parenthesized AMI text and reports the top-level form head counts
//! for hash-only comparison against an independent reference.
//! Ignored by default; external-custody tooling only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_ami_text::{
    AMI_TEXT_FORM_HEADS_POLICY_V1, ParseLimitsV1, count_ami_text_form_heads_v1, parse_ami_text_v1,
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
        println!("usage: p4b_02b61_ami_text_form_heads_runner --input <path> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");

    let text = value.get("text").and_then(|v| v.as_str()).unwrap_or("");

    let limits = ParseLimitsV1::try_new(8 * 1024 * 1024, 64, 4096, 4096).expect("limits");
    let doc = match parse_ami_text_v1(text.as_bytes(), limits) {
        Ok(d) => d,
        Err(e) => {
            let output = serde_json::json!({
                "policy": AMI_TEXT_FORM_HEADS_POLICY_V1,
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

    let output = match count_ami_text_form_heads_v1(&doc) {
        Ok(heads) => {
            let mut heads_json = serde_json::Map::new();
            for (head, count) in heads {
                heads_json.insert(head, Value::from(count));
            }
            serde_json::json!({
                "policy": AMI_TEXT_FORM_HEADS_POLICY_V1,
                "valid": true,
                "heads": Value::Object(heads_json),
            })
        }
        Err(e) => {
            serde_json::json!({
                "policy": AMI_TEXT_FORM_HEADS_POLICY_V1,
                "valid": false,
                "heads_error": format!("{e:?}"),
            })
        }
    };

    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string_pretty(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string_pretty(&output).expect("json"));
    }
}
