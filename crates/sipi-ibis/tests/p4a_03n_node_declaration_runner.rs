//! External-only typed node-declaration cross-check runner (P4A-03n).
//!
//! Lifts one typed [Node Declarations] entry from input parameters and reports
//! the node properties for hash-only comparison against an independent reference.
//! Ignored by default; external-custody tooling only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_ibis::{
    lift_node_declaration_v1, NODE_DECLARATION_POLICY_V1,
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
        println!("usage: p4a_03n_node_declaration_runner --input <json> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");
    let nname = value.get("node_name").and_then(|v| v.as_str()).unwrap_or("");
    let sname = value.get("signal_name").and_then(|v| v.as_str());

    let output = match lift_node_declaration_v1(nname, sname) {
        Ok(node) => {
            serde_json::json!({
                "policy": NODE_DECLARATION_POLICY_V1,
                "valid": true,
                "node_name": node.node_name(),
                "signal_name": node.signal_name(),
            })
        }
        Err(e) => {
            serde_json::json!({
                "policy": NODE_DECLARATION_POLICY_V1,
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
