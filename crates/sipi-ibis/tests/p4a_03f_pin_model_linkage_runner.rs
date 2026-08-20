//! External-only typed pin-to-model linkage cross-check runner (P4A-03f).
//!
//! Parses an IBIS-style text input structurally, lifts the typed [Model]
//! and [Pin] declarations, and resolves every pin's driving model through
//! resolve_pin_model_linkage_v1 against the declared models plus an optional
//! caller-supplied marker list (JSON value "markers"). Emits a JSON report.
//! The cross-check harness compares this against an independent reference.

use std::path::PathBuf;

use sipi_ibis::{
    PIN_MODEL_LINKAGE_POLICY_V1, ParseLimitsV1, lift_model_declarations_v1,
    lift_pin_declarations_v1, parse_structural_v1, resolve_pin_model_linkage_v1,
};

fn main() {
    let mut input = None;
    let mut report = None;
    let mut marker_file = None;
    let mut args = std::env::args().skip(1);
    while let Some(argument) = args.next() {
        let mut value = || args.next().expect("argument value");
        match argument.as_str() {
            "--input" => input = Some(PathBuf::from(value())),
            "--report" => report = Some(PathBuf::from(value())),
            "--markers" => marker_file = Some(PathBuf::from(value())),
            other => panic!("unknown argument: {other}"),
        }
    }
    let Some(input) = input else {
        println!(
            "usage: p4a_03f_pin_model_linkage_runner --input <ibs-text> [--report <path>] [--markers <json>]"
        );
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let limits = ParseLimitsV1::try_new(
        8 * 1024 * 1024,
        4 * 1024 * 1024,
        2 * 1024 * 1024,
        4 * 1024 * 1024,
    )
    .expect("limits");
    let document = match parse_structural_v1(&bytes, limits) {
        Ok(doc) => doc,
        Err(e) => {
            let output = serde_json::json!({ "policy": PIN_MODEL_LINKAGE_POLICY_V1, "ok": false, "error": format!("parse_error:{e}") });
            finish(output, report.as_deref());
            return;
        }
    };
    let pins = match lift_pin_declarations_v1(document.records()) {
        Ok(p) => p,
        Err(e) => {
            let output = serde_json::json!({ "policy": PIN_MODEL_LINKAGE_POLICY_V1, "ok": false, "error": format!("pin_error:{e:?}") });
            finish(output, report.as_deref());
            return;
        }
    };
    let models = match lift_model_declarations_v1(document.records()) {
        Ok(m) => m,
        Err(e) => {
            let output = serde_json::json!({ "policy": PIN_MODEL_LINKAGE_POLICY_V1, "ok": false, "error": format!("model_error:{e:?}") });
            finish(output, report.as_deref());
            return;
        }
    };
    let markers: std::collections::BTreeSet<String> = match &marker_file {
        Some(path) => {
            let bytes = std::fs::read(path).expect("read markers");
            let value: serde_json::Value = serde_json::from_slice(&bytes).expect("markers json");
            value
                .as_array()
                .map(|arr| {
                    arr.iter()
                        .map(|e| e.as_str().unwrap().to_string())
                        .collect()
                })
                .unwrap_or_default()
        }
        None => std::collections::BTreeSet::new(),
    };
    let output = match resolve_pin_model_linkage_v1(&pins, &models, &markers) {
        Ok(linkage) => serde_json::json!({
            "policy": PIN_MODEL_LINKAGE_POLICY_V1,
            "ok": true,
            "resolved": linkage.resolved(),
            "marker": linkage.marker(),
            "unresolved": linkage.unresolved(),
        }),
        Err(e) => serde_json::json!({
            "policy": PIN_MODEL_LINKAGE_POLICY_V1,
            "ok": false,
            "error": format!("{e:?}"),
        }),
    };
    finish(output, report.as_deref());
}

fn finish(output: serde_json::Value, report: Option<&std::path::Path>) {
    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string(&output).expect("json"));
    }
}
