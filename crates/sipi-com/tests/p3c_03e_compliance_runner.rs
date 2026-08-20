//! External-only compliance report cross-check runner (P3C-03e).

use std::collections::BTreeMap;
use std::path::PathBuf;

use sipi_com::{COMPLIANCE_REPORT_POLICY_V1, ComplianceMetricSpecV1, compliance_report_v1};

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
        println!("usage: p3c_03e_compliance_runner --input <json> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: serde_json::Value = serde_json::from_slice(&bytes).expect("input json");

    let mut profile = Vec::new();
    if let Some(arr) = value.get("profile").and_then(|v| v.as_array()) {
        for s in arr {
            profile.push(ComplianceMetricSpecV1::new(
                s["name"].as_str().unwrap(),
                s["reference"].as_f64().unwrap(),
                s["tolerance"].as_f64().unwrap(),
                s["unit"].as_str().unwrap_or("db"),
            ));
        }
    }
    let mut candidates = BTreeMap::new();
    if let Some(o) = value.get("candidates").and_then(|v| v.as_object()) {
        for (k, v) in o {
            candidates.insert(k.clone(), v.as_f64().unwrap());
        }
    }

    let output = match compliance_report_v1(&profile, &candidates) {
        Ok(rpt) => {
            let results: Vec<serde_json::Value> = rpt.results().iter().map(|m| serde_json::json!({
                "name": m.name(), "candidate_db": m.candidate_db(), "difference_db": m.difference_db(), "passed": m.passed(),
            })).collect();
            serde_json::json!({ "policy": COMPLIANCE_REPORT_POLICY_V1, "ok": true, "passed": rpt.passed(), "results": results })
        }
        Err(e) => {
            serde_json::json!({ "policy": COMPLIANCE_REPORT_POLICY_V1, "ok": false, "error": format!("{e:?}") })
        }
    };
    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string(&output).expect("json"));
    }
}
