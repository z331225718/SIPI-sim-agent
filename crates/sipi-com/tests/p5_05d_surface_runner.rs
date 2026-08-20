//! External-only parameter surface cross-check runner (P5-05d).
//!
//! Reads one workbook surface (xlsx/csv/mat) plus the canonical
//! consumption key set and reports every extracted (key, value) pair
//! with coordinates, the consumed/unconsumed split, and a hash of the
//! input bytes. Ignored by default; external-custody tooling only.

use std::collections::BTreeSet;
use std::path::PathBuf;

use sha2::{Digest, Sha256};
use sipi_com::{
    classify_parameter_surface_v1, read_com_settings_csv_v1, read_com_settings_mat_v1,
    read_com_settings_xlsx_v1, ParameterSurfaceReportV1, PARAMETER_SURFACE_POLICY_V1,
};

fn report_json(report: &ParameterSurfaceReportV1) -> serde_json::Value {
    serde_json::json!({
        "pairs": report.pairs().iter().map(|pair| serde_json::json!({
            "key": pair.key(),
            "left": pair.left_coordinate(),
            "right": pair.right_coordinate(),
            "value_kind": pair.value_kind(),
        })).collect::<Vec<_>>(),
        "consumed": report.consumed(),
        "unconsumed": report.unconsumed(),
        "policy": PARAMETER_SURFACE_POLICY_V1,
    })
}

fn main() {
    let mut settings_path = None;
    let mut settings_kind = String::new();
    let mut canonical = None;
    let mut report_path = None;
    let mut args = std::env::args().skip(1);
    while let Some(argument) = args.next() {
        let mut value = || args.next().expect("argument value");
        match argument.as_str() {
            "--settings" => settings_path = Some(PathBuf::from(value())),
            "--kind" => settings_kind = value(),
            "--canonical" => canonical = Some(PathBuf::from(value())),
            "--report" => report_path = Some(PathBuf::from(value())),
            other => panic!("unknown argument: {other}"),
        }
    }
    let (Some(settings_path), Some(canonical)) = (settings_path, canonical) else {
        println!("usage: p5_05d_surface_runner --settings <path> --kind <xlsx|csv|mat> --canonical <json> [--report <path>]");
        return;
    };
    let settings_bytes = std::fs::read(&settings_path).expect("read settings");
    let settings_hash = format!("{:x}", Sha256::digest(&settings_bytes));
    let settings = match settings_kind.as_str() {
        "xlsx" => read_com_settings_xlsx_v1(&settings_path).expect("xlsx"),
        "csv" => read_com_settings_csv_v1(&settings_path).expect("csv"),
        "mat" => read_com_settings_mat_v1(&settings_path).expect("mat"),
        other => panic!("unknown kind: {other}"),
    };
    let canonical_bytes = std::fs::read(&canonical).expect("read canonical");
    let canonical_hash = format!("{:x}", Sha256::digest(&canonical_bytes));
    let canonical_keys: Vec<String> =
        serde_json::from_slice(&canonical_bytes).expect("canonical json");
    let canonical_set: BTreeSet<String> = canonical_keys.into_iter().collect();
    let report = classify_parameter_surface_v1(&settings, &canonical_set).expect("report");
    let output = serde_json::json!({
        "settings_sha256": settings_hash,
        "canonical_sha256": canonical_hash,
        "canonical_keys": canonical_set.len(),
        "surface": report_json(&report),
    });
    if let Some(path) = report_path {
        std::fs::write(path, serde_json::to_string(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string(&output).expect("json"));
    }
}
