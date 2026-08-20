//! External-only typed submodel / add-submodel cross-check runner (P4A-03l).
//!
//! Lifts one typed [Submodel] or [Add Submodel] declaration from input parameters
//! and reports the properties for hash-only comparison against an independent
//! reference. Ignored by default; external-custody tooling only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_ibis::{
    SUBMODEL_DECLARATION_POLICY_V1, lift_add_submodel_v1, lift_submodel_declaration_v1,
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
        println!("usage: p4a_03l_submodel_runner --input <json> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");

    let output = if value.get("submodel_type").is_some() {
        let sname = value
            .get("submodel_name")
            .and_then(|v| v.as_str())
            .unwrap_or("");
        let stype = value
            .get("submodel_type")
            .and_then(|v| v.as_str())
            .unwrap_or("");
        let mode = value.get("mode").and_then(|v| v.as_str()).unwrap_or("");

        match lift_submodel_declaration_v1(sname, stype, mode) {
            Ok(sub) => {
                serde_json::json!({
                    "policy": SUBMODEL_DECLARATION_POLICY_V1,
                    "valid": true,
                    "kind": "submodel",
                    "submodel_name": sub.submodel_name(),
                    "submodel_type": sub.submodel_type().token(),
                    "mode": sub.mode().token(),
                })
            }
            Err(e) => {
                serde_json::json!({
                    "policy": SUBMODEL_DECLARATION_POLICY_V1,
                    "valid": false,
                    "lift_error": format!("{e:?}"),
                })
            }
        }
    } else {
        let sname = value
            .get("submodel_name")
            .and_then(|v| v.as_str())
            .unwrap_or("");
        let mode = value.get("mode").and_then(|v| v.as_str()).unwrap_or("");

        match lift_add_submodel_v1(sname, mode) {
            Ok(add) => {
                serde_json::json!({
                    "policy": SUBMODEL_DECLARATION_POLICY_V1,
                    "valid": true,
                    "kind": "add_submodel",
                    "submodel_name": add.submodel_name(),
                    "mode": add.mode().token(),
                })
            }
            Err(e) => {
                serde_json::json!({
                    "policy": SUBMODEL_DECLARATION_POLICY_V1,
                    "valid": false,
                    "lift_error": format!("{e:?}"),
                })
            }
        }
    };

    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string_pretty(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string_pretty(&output).expect("json"));
    }
}
