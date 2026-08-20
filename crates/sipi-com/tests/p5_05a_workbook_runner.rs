//! External-only workbook importer cross-check runner (P5-05a).
//!
//! Reads one authorized COM_Settings xlsx with the product importer and
//! reports the raw-cell grid, keyword lookups, strict flag, and a hash
//! of the exact input bytes. Ignored by default; external-custody
//! tooling only.

use std::path::PathBuf;

use sha2::{Digest, Sha256};
use sipi_com::{
    is_strict_ooxml_v1, read_com_settings_xlsx_v1, CellValueV1, RawCellV1,
    WORKBOOK_IMPORT_POLICY_V1,
};

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
    let mut xlsx = None;
    let mut lookups: Vec<String> = Vec::new();
    let mut report = None;
    let mut args = std::env::args().skip(1);
    while let Some(argument) = args.next() {
        let mut value = || args.next().expect("argument value");
        match argument.as_str() {
            "--xlsx" => xlsx = Some(PathBuf::from(value())),
            "--lookup" => lookups.push(value()),
            "--report" => report = Some(PathBuf::from(value())),
            other => panic!("unknown argument: {other}"),
        }
    }
    let Some(xlsx) = xlsx else {
        println!(
            "usage: p5_05a_workbook_runner --xlsx <path> [--lookup <keyword> ...] [--report <path>]"
        );
        return;
    };
    let bytes = std::fs::read(&xlsx).expect("read xlsx");
    let digest = format!("{:x}", Sha256::digest(&bytes));
    let strict = is_strict_ooxml_v1(&xlsx).expect("strict probe");
    let settings = read_com_settings_xlsx_v1(&xlsx).expect("settings");
    let rows: Vec<serde_json::Value> = settings
        .rows()
        .iter()
        .map(|row| {
            serde_json::json!({
                "cells": row.iter().map(cell_json).collect::<Vec<_>>(),
            })
        })
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
            Err(error) => serde_json::json!({
                "keyword": keyword,
                "found": false,
                "error": format!("{error:?}"),
            }),
        })
        .collect();
    let report_json = serde_json::json!({
        "xlsx_sha256": digest,
        "strict": strict,
        "rows": rows.len(),
        "columns": rows.iter().map(|row| row["cells"].as_array().map(|cells| cells.len()).unwrap_or(0)).max().unwrap_or(0),
        "grid": rows,
        "lookups": lookup_results,
        "policy": WORKBOOK_IMPORT_POLICY_V1,
    });
    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string(&report_json).expect("json"))
            .expect("write");
    } else {
        println!("{}", serde_json::to_string(&report_json).expect("json"));
    }
}