//! External-only parameter-catalog cross-check runner (P4B-02b3).
//!
//! Validates candidate parameter sets against a compiled catalog and
//! reports the outcome for hash-only comparison with an independent
//! reference. Ignored by default.

use std::collections::BTreeMap;
use std::path::PathBuf;

use sipi_ami_text::{
    validate_candidate_set_v1, AmiParameterTypeV1, AmiParameterValueV1, AmiUsageV1, CatalogEntryV1,
    ParameterCatalogV1, PARAMETER_CATALOG_POLICY_V1,
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
        println!("usage: p4b_02b3_param_catalog_runner --input <json> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: serde_json::Value = serde_json::from_slice(&bytes).expect("input json");

    // Build catalog.
    let mut entries = Vec::new();
    if let Some(arr) = value.get("catalog").and_then(|v| v.as_array()) {
        for e in arr {
            let name = e["name"].as_str().expect("name").to_string();
            let usage = AmiUsageV1::from_token(e["usage"].as_str().expect("usage")).expect("usage");
            let ty = AmiParameterTypeV1::from_token(e["type"].as_str().expect("type")).expect("type");
            let default = e.get("default").and_then(|d| d.as_str()).map(|s| s.to_string());
            entries.push(CatalogEntryV1::new(name, usage, ty, default));
        }
    }
    let catalog = ParameterCatalogV1::compile(entries).expect("catalog");

    // Build candidate value set.
    let mut values = BTreeMap::new();
    if let Some(cand) = value.get("candidates").and_then(|v| v.as_object()) {
        for (name, spec) in cand {
            let ty_token = spec["type"].as_str().expect("type");
            let val = spec["value"].as_str().expect("value");
            values.insert(name.clone(), AmiParameterValueV1::try_new(name, ty_token, val).expect("value"));
        }
    }

    let result = validate_candidate_set_v1(&catalog, &values);
    let output = serde_json::json!({
        "policy": PARAMETER_CATALOG_POLICY_V1,
        "ok": result.is_ok(),
        "error": result.err().map(|e| format!("{e:?}")),
    });
    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string(&output).expect("json"));
    }
}