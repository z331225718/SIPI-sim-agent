//! External-only typed component-declaration cross-check runner (P4A-03g).
//!
//! Lifts one typed [Component] header from input parameters and reports
//! the component properties for hash-only comparison against an
//! independent reference. Ignored by default; external-custody tooling only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_ibis::{
    lift_component_declaration_v1, COMPONENT_DECLARATION_POLICY_V1,
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
        println!("usage: p4a_03g_component_declaration_runner --input <json> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");
    let name = value["name"].as_str().unwrap_or("");
    let manufacturer = value.get("manufacturer").and_then(|v| v.as_str());
    let package_name = value.get("package_name").and_then(|v| v.as_str());

    let output = match lift_component_declaration_v1(name, manufacturer, package_name) {
        Ok(comp) => {
            serde_json::json!({
                "policy": COMPONENT_DECLARATION_POLICY_V1,
                "valid": true,
                "name": comp.name(),
                "manufacturer": comp.manufacturer(),
                "package_name": comp.package_name(),
            })
        }
        Err(e) => {
            serde_json::json!({
                "policy": COMPONENT_DECLARATION_POLICY_V1,
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
