//! External-only metric-compare cross-check runner (P3C-03c).
//!
//! Compares a candidate metric set against a compiled profile and reports
//! per-metric allowed error / pass for hash-only comparison with an
//! independent reference. Ignored by default.

use std::collections::BTreeMap;
use std::path::PathBuf;

use sipi_compare::{
    METRIC_COMPARE_POLICY_V1, MetricProfileV1, MetricSpecV1, ToleranceV1, UnitTagV1,
    compare_metric_profile_v1,
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
        println!("usage: p3c_03c_metric_compare_runner --input <json> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: serde_json::Value = serde_json::from_slice(&bytes).expect("input json");

    // Build profile from the input spec array.
    let mut specs = Vec::new();
    if let Some(spec_array) = value.get("specs").and_then(|v| v.as_array()) {
        for spec in spec_array {
            let name = spec["name"].as_str().expect("name").to_string();
            let unit =
                UnitTagV1::try_new(spec["unit"].as_str().expect("unit").to_string()).unwrap();
            let reference = spec["reference"].as_f64().expect("reference");
            let abs = spec["abs"].as_f64().expect("abs");
            let rel = spec["rel"].as_f64().expect("rel");
            let tolerance = ToleranceV1::try_new(abs, rel).unwrap();
            specs.push(MetricSpecV1::new(name, unit, reference, tolerance).unwrap());
        }
    }
    let profile = MetricProfileV1::compile(specs).expect("profile");

    let mut candidates = BTreeMap::new();
    if let Some(cand_map) = value.get("candidates").and_then(|v| v.as_object()) {
        for (name, val) in cand_map {
            candidates.insert(name.clone(), val.as_f64().expect("candidate"));
        }
    }

    let output = match compare_metric_profile_v1(&profile, &candidates) {
        Ok(rpt) => serde_json::json!({
            "policy": METRIC_COMPARE_POLICY_V1,
            "passed": rpt.passed(),
            "results": rpt.results().iter().map(|r| serde_json::json!({
                "name": r.name(),
                "candidate": r.candidate(),
                "allowed_error": r.allowed_error(),
                "passed": r.passed(),
            })).collect::<Vec<_>>(),
        }),
        Err(e) => {
            serde_json::json!({ "error": format!("{e:?}"), "policy": METRIC_COMPARE_POLICY_V1 })
        }
    };
    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string(&output).expect("json"));
    }
}
