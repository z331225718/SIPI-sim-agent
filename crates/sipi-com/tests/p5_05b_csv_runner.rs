//! External-only CSV configuration cross-check runner (P5-05b).
//!
//! Reads one CSV configuration with the product reader and reports the
//! raw-cell grid, keyword lookups, and a hash of the exact input bytes.
//! Ignored by default; external-custody tooling only.

use std::path::PathBuf;

use sha2::{Digest, Sha256};
use sipi_com::{read_com_settings_csv_v1, CellValueV1, RawCellV1, CSV_READER_POLICY_V1};

fn cell_json(cell: &RawCellV1) -> serde_json::Value {
    let value = match cell.value() {
        CellValueV1::None => serde_json::json!({"kind": "None"}),
        CellValueV1::Integer(value) => serde_json::json!({"kind": "Integer", "value": value}),
        CellValueV1::Number(value) => serde_json::json!({"kind": "Number", "value": value}),
        CellValueV1::Bool(value) => serde_json::json!({"kind": "Bool", "value": value}),
        CellValueV1::String(value) => serde_json::json!({"kind": "String", "value": value}),
        CellValueV1::Array { dims, data } => serde_json::json!({"kind": "Array", "dims": dims, "data": data}),
    };
    serde_json::json!({
        "coordinate": cell.coordinate(),
        "value": value,
        "formula": cell.formula(),
    })
}

fn main() {
    let mut csv = None;
    let mut lookups: Vec<String> = Vec::new();
    let mut report = None;
    let mut args = std::env::args().skip(1);
    while let Some(argument) = args.next() {
        let mut value = || args.next().expect("argument value");
        match argument.as_str() {
            "--csv" => csv = Some(PathBuf::from(value())),
            "--lookup" => lookups.push(value()),
            "--report" => report = Some(PathBuf::from(value())),
            other => panic!("unknown argument: {other}"),
        }
    }
    let Some(csv) = csv else {
        println!("usage: p5_05b_csv_runner --csv <path> [--lookup <keyword> ...] [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&csv).expect("read csv");
    let digest = format!("{:x}", Sha256::digest(&bytes));
    let settings = read_com_settings_csv_v1(&csv).expect("settings");
    let rows: Vec<serde_json::Value> = settings
        .rows()
        .iter()
        .map(|row| serde_json::json!({"cells": row.iter().map(cell_json).collect::<Vec<_>>()}))
        .collect();
    let lookup_results: Vec<serde_json::Value> = lookups
        .iter()
        .map(|keyword| match settings.lookup_optional_v1(keyword) {
            Ok(Some(cell)) => serde_json::json!({
                "keyword": keyword,
                "found": true,
                "cell": cell_json(&cell),
            }),
            Ok(None) => serde_json::json!({"keyword": keyword, "found": false}),
            Err(error) => {
                let name = match &error {
                    sipi_com::WorkbookErrorV1::DuplicateParameter(_) => "DuplicateParameterError",
                    sipi_com::WorkbookErrorV1::MissingParameter(_) => "MissingParameterError",
                    _ => "ConfigError",
                };
                serde_json::json!({
                    "keyword": keyword,
                    "found": false,
                    "error": name,
                })
            }
        })
        .collect();
    let report_json = serde_json::json!({
        "csv_sha256": digest,
        "rows": rows.len(),
        "columns": rows.iter().map(|row| row["cells"].as_array().map(|cells| cells.len()).unwrap_or(0)).max().unwrap_or(0),
        "grid": rows,
        "lookups": lookup_results,
        "policy": CSV_READER_POLICY_V1,
    });
    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string(&report_json).expect("json"))
            .expect("write");
    } else {
        println!("{}", serde_json::to_string(&report_json).expect("json"));
    }
}