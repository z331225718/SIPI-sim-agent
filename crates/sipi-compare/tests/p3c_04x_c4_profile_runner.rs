//! External-only C4 metric-profile cross-check runner (P3C-03, C4).
//!
//! Reads a JSON object of metric name -> reference value, builds the owner
//! C4 metric specs via c4_metric_specs_v1 (COM_dB / ICN_mV / ERL, 1% relative
//! tolerance), compiles them into a MetricProfileV1, and emits the metric
//! names, per-metric reference/unit/relative-tolerance, and a profile digest.
//! The cross-check harness compares this against an independent reference.

use std::collections::BTreeMap;
use std::path::PathBuf;

use sha2::{Digest, Sha256};

use sipi_compare::{
    c4_metric_names, c4_metric_specs_v1, C4ProfileErrorV1, C4_PROFILE_POLICY_V1,
    C4_RELATIVE_TOLERANCE_V1,
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
        println!("usage: p3c_04x_c4_profile_runner --input <json> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: serde_json::Value = serde_json::from_slice(&bytes).expect("input json");
    let mut references: BTreeMap<String, f64> = BTreeMap::new();
    if let Some(obj) = value.as_object() {
        for (name, v) in obj {
            if let Some(num) = v.as_f64() {
                references.insert(name.clone(), num);
            }
        }
    }
    let output = match c4_metric_specs_v1(&references) {
        Err(error) => serde_json::json!({
            "policy": C4_PROFILE_POLICY_V1,
            "ok": false,
            "error": error_label(&error),
            "metric_names": c4_metric_names(),
            "specs": [],
            "digest": null,
        }),
        Ok(specs) => {
            let spec_json: Vec<serde_json::Value> = specs
                .iter()
                .map(|s| {
                    serde_json::json!({
                        "name": s.name(),
                        "reference": s.reference(),
                        "relative_tolerance": s.tolerance().relative(),
                    })
                })
                .collect();
            let mut hasher = Sha256::new();
            for s in &specs {
                hasher.update(s.name().as_bytes());
                hasher.update(b"\n");
            }
            let digest = format!("{:x}", hasher.finalize());
            serde_json::json!({
                "policy": C4_PROFILE_POLICY_V1,
                "ok": true,
                "error": null,
                "metric_names": c4_metric_names(),
                "relative_tolerance": C4_RELATIVE_TOLERANCE_V1,
                "specs": spec_json,
                "digest": digest,
            })
        }
    };
    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string(&output).expect("json"));
    }
}

fn error_label(error: &C4ProfileErrorV1) -> String {
    match error {
        C4ProfileErrorV1::MissingReference(name) => format!("missing_reference:{name}"),
        C4ProfileErrorV1::NonFiniteReference(name) => format!("non_finite_reference:{name}"),
    }
}