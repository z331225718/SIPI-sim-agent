//! External-only typed model selector keywords cross-check runner (P4A-03ad).
//!
//! Lifts one typed [Model Selector] declaration from input parameters
//! and reports the properties for hash-only comparison against an independent reference.
//! Ignored by default; external-custody tooling only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_ibis::{
    lift_model_selector_keywords_v1, ModelOptionEntryV1, MODEL_SELECTOR_KEYWORDS_POLICY_V1,
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
        println!("usage: p4a_03ad_model_selector_keywords_runner --input <json> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");
    let sname = value.get("selector_name").and_then(|v| v.as_str()).unwrap_or("");
    let options = value.get("model_options").and_then(|v| v.as_array()).map(|arr| {
        arr.iter()
            .filter_map(|item| {
                let mn = item.get("model_name").and_then(|v| v.as_str())?;
                let desc = item.get("description").and_then(|v| v.as_str());
                ModelOptionEntryV1::try_new(mn, desc).ok()
            })
            .collect()
    }).unwrap_or_default();

    let output = match lift_model_selector_keywords_v1(sname, options) {
        Ok(sel) => {
            let opts: Vec<serde_json::Value> = sel
                .model_options()
                .iter()
                .map(|o| {
                    serde_json::json!({
                        "model_name": o.model_name(),
                        "description": o.description(),
                    })
                })
                .collect();
            serde_json::json!({
                "policy": MODEL_SELECTOR_KEYWORDS_POLICY_V1,
                "valid": true,
                "selector_name": sel.selector_name(),
                "option_count": sel.model_options().len(),
                "model_options": opts,
            })
        }
        Err(e) => {
            serde_json::json!({
                "policy": MODEL_SELECTOR_KEYWORDS_POLICY_V1,
                "valid": false,
                "lift_error": format!("{e:?}"),
            })
        }
    };

    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string_pretty(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string_pretty(&output).expect("json"));
    }
}
