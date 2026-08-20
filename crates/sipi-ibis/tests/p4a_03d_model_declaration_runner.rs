//! External-only typed model-declaration cross-check runner (P4A-03d).
//!
//! Parses an authorized external IBIS file structurally, lifts the typed
//! [Model] declarations, and reports the Model_type distribution for
//! hash-only comparison against an independent observer. Ignored by
//! default; external-custody tooling only.

use std::collections::BTreeMap;
use std::path::PathBuf;

use sipi_ibis::{
    lift_model_declarations_v1, parse_structural_v1, MODEL_DECLARATION_POLICY_V1, ParseLimitsV1,
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
        println!("usage: p4a_03d_model_declaration_runner --input <path> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let limits = ParseLimitsV1::try_new(8 * 1024 * 1024, 4 * 1024 * 1024, 2 * 1024 * 1024, 4 * 1024 * 1024).expect("limits");
    let document = match parse_structural_v1(&bytes, limits) {
        Ok(doc) => doc,
        Err(e) => {
            println!("{}", serde_json::to_string(&serde_json::json!({
                "policy": MODEL_DECLARATION_POLICY_V1,
                "parse_error": format!("{e}"),
            })).expect("json"));
            return;
        }
    };
    match lift_model_declarations_v1(document.records()) {
        Ok(declarations) => {
            let mut by_type: BTreeMap<String, usize> = BTreeMap::new();
            for decl in &declarations {
                let key = format!("{:?}", decl.model_type());
                *by_type.entry(key).or_insert(0) += 1;
            }
            let output = serde_json::json!({
                "policy": MODEL_DECLARATION_POLICY_V1,
                "declaration_count": declarations.len(),
                "model_types": by_type,
                "model_names": declarations.iter().map(|d| d.model_name().to_string()).collect::<Vec<_>>(),
            });
            if let Some(path) = report {
                std::fs::write(path, serde_json::to_string(&output).expect("json")).expect("write");
            } else {
                println!("{}", serde_json::to_string(&output).expect("json"));
            }
        }
        Err(e) => {
            println!("{}", serde_json::to_string(&serde_json::json!({
                "policy": MODEL_DECLARATION_POLICY_V1,
                "lift_error": format!("{e}"),
            })).expect("json"));
        }
    }
}