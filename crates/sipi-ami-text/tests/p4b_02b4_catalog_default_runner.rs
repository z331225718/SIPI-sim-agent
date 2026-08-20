//! External-only catalog-default validity cross-check runner (P4B-02b4).

use std::path::PathBuf;

use sipi_ami_text::{
    AmiParameterTypeV1, AmiUsageV1, CATALOG_DEFAULT_POLICY_V1, CatalogEntryV1, ParameterCatalogV1,
    token_valid_for_type_v1, validate_catalog_defaults_v1,
};

pub(crate) fn main() {
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
        println!("usage: p4b_02b4_catalog_default_runner --input <json> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: serde_json::Value = serde_json::from_slice(&bytes).expect("input json");

    let mut entries = Vec::new();
    let mut per_case: Vec<(String, bool)> = Vec::new();
    if let Some(arr) = value.get("cases").and_then(|v| v.as_array()) {
        for e in arr {
            let name = e["name"].as_str().unwrap().to_string();
            let type_token = e["type"].as_str().unwrap().to_string();
            let ty = AmiParameterTypeV1::from_token(&type_token).expect("type");
            let default = e
                .get("default")
                .and_then(|d| d.as_str())
                .map(|s| s.to_string());
            let valid = match &default {
                None => true,
                Some(s) => token_valid_for_type_v1(&type_token, s),
            };
            per_case.push((name.clone(), valid));
            entries.push(CatalogEntryV1::new(name, AmiUsageV1::In, ty, default));
        }
    }
    let catalog = ParameterCatalogV1::compile(entries).expect("catalog");
    let overall = validate_catalog_defaults_v1(&catalog).is_ok();

    let per_case_json: Vec<serde_json::Value> = per_case
        .iter()
        .map(|(n, v)| serde_json::json!({ "name": n, "valid": v }))
        .collect();
    let output = serde_json::json!({
        "policy": CATALOG_DEFAULT_POLICY_V1,
        "valid": overall,
        "per_case": per_case_json,
    });
    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string(&output).expect("json"));
    }
}
