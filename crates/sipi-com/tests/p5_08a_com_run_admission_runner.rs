//! External-only COM run-request admission cross-check runner (P5-08a).
//!
//! Reads a JSON input describing a raw COM run-request payload (the request
//! text) plus an optional label, applies com_run_admission_v1, and emits the
//! deterministic admission verdict. The cross-check harness compares this
//! against an independent Python reference.

use std::path::PathBuf;

use sipi_com::{COM_RUN_ADMISSION_POLICY_V1, ComRunAdmissionErrorV1, com_run_admission_v1};

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
        println!("usage: p5_08a_com_run_admission_runner --input <json> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: serde_json::Value = serde_json::from_slice(&bytes).expect("input json");
    let payload = value["request"].as_str().unwrap().as_bytes().to_vec();

    let output = match com_run_admission_v1(&payload) {
        Err(error) => serde_json::json!({
            "policy": COM_RUN_ADMISSION_POLICY_V1,
            "ok": false,
            "error": error_label(&error),
        }),
        Ok(adm) => serde_json::json!({
            "policy": COM_RUN_ADMISSION_POLICY_V1,
            "ok": true,
            "admitted": adm.admitted(),
            "schema_matched": adm.schema_matched(),
            "artifact_bound": adm.artifact_bound(),
            "consumed_key_count": adm.consumed_key_count(),
            "invalid_reason": adm.invalid_reason(),
        }),
    };
    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string(&output).expect("json"));
    }
}

fn error_label(error: &ComRunAdmissionErrorV1) -> String {
    match error {
        ComRunAdmissionErrorV1::InvalidJson => "invalid_json".to_string(),
        ComRunAdmissionErrorV1::SchemaMismatch => "schema_mismatch".to_string(),
        ComRunAdmissionErrorV1::MissingArtifactRoot => "missing_artifact_root".to_string(),
        ComRunAdmissionErrorV1::MissingArtifactId => "missing_artifact_id".to_string(),
        ComRunAdmissionErrorV1::EmptyParams => "empty_params".to_string(),
        ComRunAdmissionErrorV1::NonScalarParam => "non_scalar_param".to_string(),
    }
}
