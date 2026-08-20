//! External-only AMI runtime-parameter-table cross-check runner (P4B-02b5).
//!
//! Reads a JSON input describing a catalog (entries with name/usage/type/
//! optional default) plus an optional candidate value map, builds the ordered
//! runtime table via build_ami_runtime_params_v1, and emits a JSON report with
//! the resolved parameter tokens and any error surface. Compare against an
//! independent reference in the cross-check harness.

use std::path::PathBuf;

use sipi_ami_text::{
    AMI_RUNTIME_PARAMS_POLICY_V1, AmiParameterTypeV1, AmiUsageV1, CatalogEntryV1,
    ParameterCatalogV1, RuntimeParamsErrorV1, build_ami_runtime_params_v1,
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
        println!("usage: p4b_02b5_ami_runtime_params_runner --input <json> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: serde_json::Value = serde_json::from_slice(&bytes).expect("input json");

    let mut entries = Vec::new();
    if let Some(arr) = value.get("catalog").and_then(|v| v.as_array()) {
        for e in arr {
            let name = e["name"].as_str().unwrap().to_string();
            let usage = AmiUsageV1::from_token(e["usage"].as_str().unwrap()).expect("usage");
            let ty = AmiParameterTypeV1::from_token(e["type"].as_str().unwrap()).expect("type");
            let default = e
                .get("default")
                .and_then(|d| d.as_str())
                .map(|s| s.to_string());
            entries.push(CatalogEntryV1::new(name, usage, ty, default));
        }
    }

    // Candidate values are keyed by name; type and value token provided here.
    let mut candidates = std::collections::BTreeMap::new();
    if let Some(obj) = value.get("candidates").and_then(|v| v.as_object()) {
        for (name, spec) in obj {
            let type_token = spec["type"].as_str().unwrap();
            let value_token = spec["value"].as_str().unwrap();
            let parameter_type = AmiParameterTypeV1::from_token(type_token).expect("can-type");
            // Reuse the value construction through a typed entry check below.
            let _ = parameter_type;
            candidates.insert(
                name.clone(),
                sipi_ami_text::AmiParameterValueV1::try_new(name, type_token, value_token)
                    .expect("candidate value"),
            );
        }
    }

    let output = match ParameterCatalogV1::compile(entries) {
        Err(error) => serde_json::json!({
            "policy": AMI_RUNTIME_PARAMS_POLICY_V1,
            "ok": false,
            "error": format!("catalog_error:{error:?}"),
            "params": [],
        }),
        Ok(catalog) => match build_ami_runtime_params_v1(&catalog, &candidates) {
            Err(error) => serde_json::json!({
                "policy": AMI_RUNTIME_PARAMS_POLICY_V1,
                "ok": false,
                "error": error_label(&error),
                "params": [],
            }),
            Ok(table) => {
                let params: Vec<serde_json::Value> = table
                    .params()
                    .iter()
                    .map(|p| {
                        serde_json::json!({
                            "name": p.name(),
                            "usage": p.usage().token(),
                            "type": p.parameter_type().token(),
                            "value": p.value().value_token(),
                        })
                    })
                    .collect();
                serde_json::json!({
                    "policy": AMI_RUNTIME_PARAMS_POLICY_V1,
                    "ok": true,
                    "error": null,
                    "params": params,
                })
            }
        },
    };
    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string(&output).expect("json"));
    }
}

fn error_label(error: &RuntimeParamsErrorV1) -> String {
    match error {
        RuntimeParamsErrorV1::MissingRuntimeValue(n) => format!("missing_runtime_value:{n}"),
        RuntimeParamsErrorV1::CatalogLookup(n) => format!("catalog_lookup:{n}"),
        RuntimeParamsErrorV1::TypeMismatch { name, .. } => format!("type_mismatch:{name}"),
    }
}
