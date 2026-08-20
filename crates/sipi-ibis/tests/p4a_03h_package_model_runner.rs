//! External-only typed package-model-declaration cross-check runner (P4A-03h).
//!
//! Lifts one typed [Package Model] header from input parameters and reports
//! the package electrical properties for hash-only comparison against an
//! independent reference. Ignored by default; external-custody tooling only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_ibis::{
    lift_package_model_declaration_v1, PACKAGE_MODEL_DECLARATION_POLICY_V1,
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
        println!("usage: p4a_03h_package_model_runner --input <json> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");
    let name = value["name"].as_str().unwrap_or("");
    let r_pkg = value.get("r_pkg_ohm").and_then(|v| v.as_f64());
    let l_pkg = value.get("l_pkg_henry").and_then(|v| v.as_f64());
    let c_pkg = value.get("c_pkg_farad").and_then(|v| v.as_f64());

    let output = match lift_package_model_declaration_v1(name, r_pkg, l_pkg, c_pkg) {
        Ok(pkg) => {
            serde_json::json!({
                "policy": PACKAGE_MODEL_DECLARATION_POLICY_V1,
                "valid": true,
                "name": pkg.name(),
                "r_pkg_ohm": pkg.r_pkg_ohm().map(|v| v.get()),
                "l_pkg_henry": pkg.l_pkg_henry().map(|v| v.get()),
                "c_pkg_farad": pkg.c_pkg_farad().map(|v| v.get()),
            })
        }
        Err(e) => {
            serde_json::json!({
                "policy": PACKAGE_MODEL_DECLARATION_POLICY_V1,
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
