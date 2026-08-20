//! External-only Q-factor/BER cross-check runner (P3C-02e).
//!
//! Evaluates Q-FACTOR <-> BER conversions for hash-only comparison
//! against the independent scipy reference. Ignored by default.

use std::path::PathBuf;

use sipi_com::{QFACTOR_BER_POLICY_V1, ber_to_q_factor_v1, q_factor_to_ber_v1};

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
        println!("usage: p3c_02e_qfactor_ber_runner --input <json> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: serde_json::Value = serde_json::from_slice(&bytes).expect("input json");
    let mut cases = Vec::new();
    if let Some(qs) = value.get("q_values").and_then(|v| v.as_array()) {
        for q in qs {
            let q = q.as_f64().expect("q");
            cases.push(serde_json::json!({
                "q": q,
                "ber": q_factor_to_ber_v1(q).map(|b| format!("{:.17e}", b)).unwrap_or_else(|e| format!("ERR:{e:?}")),
            }));
        }
    }
    if let Some(bers) = value.get("ber_values").and_then(|v| v.as_array()) {
        for ber in bers {
            let ber = ber.as_f64().expect("ber");
            cases.push(serde_json::json!({
                "ber": ber,
                "q_inv": ber_to_q_factor_v1(ber).map(|q| format!("{:.15e}", q)).unwrap_or_else(|e| format!("ERR:{e:?}")),
            }));
        }
    }
    let output = serde_json::json!({
        "policy": QFACTOR_BER_POLICY_V1,
        "cases": cases,
    });
    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string(&output).expect("json"));
    }
}
