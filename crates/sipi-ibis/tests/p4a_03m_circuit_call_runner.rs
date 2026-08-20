//! External-only typed circuit-call cross-check runner (P4A-03m).
//!
//! Lifts one typed [Circuit Call] declaration from input parameters
//! and reports the properties for hash-only comparison against an
//! independent reference. Ignored by default; external-custody tooling only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_ibis::{CIRCUIT_CALL_DECLARATION_POLICY_V1, PortMapV1, lift_circuit_call_declaration_v1};

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
        println!("usage: p4a_03m_circuit_call_runner --input <json> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");
    let cname = value
        .get("circuit_name")
        .and_then(|v| v.as_str())
        .unwrap_or("");
    let port_mappings = value
        .get("port_mappings")
        .and_then(|v| v.as_array())
        .map(|arr| {
            arr.iter()
                .map(|pm| {
                    let p = pm.get("port_name").and_then(|v| v.as_str()).unwrap_or("");
                    let n = pm.get("node_name").and_then(|v| v.as_str()).unwrap_or("");
                    PortMapV1::new(p, n)
                })
                .collect()
        })
        .unwrap_or_default();

    let output = match lift_circuit_call_declaration_v1(cname, port_mappings) {
        Ok(call) => {
            let mappings: Vec<serde_json::Value> = call
                .port_mappings()
                .iter()
                .map(|pm| {
                    serde_json::json!({
                        "port_name": pm.port_name(),
                        "node_name": pm.node_name(),
                    })
                })
                .collect();
            serde_json::json!({
                "policy": CIRCUIT_CALL_DECLARATION_POLICY_V1,
                "valid": true,
                "circuit_name": call.circuit_name(),
                "port_mapping_count": call.port_mappings().len(),
                "port_mappings": mappings,
            })
        }
        Err(e) => {
            serde_json::json!({
                "policy": CIRCUIT_CALL_DECLARATION_POLICY_V1,
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
