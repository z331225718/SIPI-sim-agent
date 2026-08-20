//! External-only dB-tolerance cross-check runner (P3C-03d).
//!
//! Runs the dB-domain tolerance check on (ref, candidate, tolerance) triples
//! for hash-only comparison with an independent reference.

use std::path::PathBuf;

use sipi_com::{db_tolerance_check_v1, DB_TOLERANCE_POLICY_V1};

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
        println!("usage: p3c_03d_db_tolerance_runner --input <json> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: serde_json::Value = serde_json::from_slice(&bytes).expect("input json");

    let mut results = Vec::new();
    if let Some(cases) = value.get("cases").and_then(|v| v.as_array()) {
        for case in cases {
            let reference = case["reference"].as_f64().unwrap();
            let candidate = case["candidate"].as_f64().unwrap();
            let tolerance = case["tolerance"].as_f64().unwrap();
            results.push(serde_json::json!({
                "reference": reference,
                "candidate": candidate,
                "tolerance": tolerance,
                "result": match db_tolerance_check_v1(reference, candidate, tolerance) {
                    Ok(r) => serde_json::json!({ "ok": true, "diff": r.difference_db(), "passed": r.passed() }),
                    Err(e) => serde_json::json!({ "ok": false, "error": format!("{e:?}") }),
                },
            }));
        }
    }
    let output = serde_json::json!({ "policy": DB_TOLERANCE_POLICY_V1, "cases": results });
    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string(&output).expect("json"));
    }
}