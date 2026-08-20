//! External-only TX FFE grid cross-check runner (P5-04j).
//!
//! Runs full_grid_matrix / build_txffe_grid / first_strict_best /
//! select_fom_tracker on JSON inputs and reports the results. Ignored
//! by default; external-custody tooling only.

use std::collections::BTreeMap;
use std::path::PathBuf;

use serde_json::Value;
use sipi_com::{
    TX_FFE_POLICY_V1, build_txffe_grid_v1, first_strict_best_v1, full_grid_matrix_v1,
    select_fom_tracker_v1,
};

fn f64s(value: &Value) -> Vec<f64> {
    value
        .as_array()
        .expect("array")
        .iter()
        .map(|item| item.as_f64().expect("f64"))
        .collect()
}

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
        println!("usage: p5_04j_tx_ffe_runner --input <json> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");
    let mut output = serde_json::json!({ "policy": TX_FFE_POLICY_V1 });
    if let Some(case) = value.get("full_grid") {
        let columns: Vec<Vec<f64>> = case["columns"]
            .as_array()
            .expect("columns")
            .iter()
            .map(f64s)
            .collect();
        let grid = full_grid_matrix_v1(&columns).expect("grid");
        output["full_grid"] = serde_json::json!({ "grid": grid });
    }
    if let Some(case) = value.get("build_grid") {
        let mut values = BTreeMap::new();
        for (key, column) in case["values"].as_object().expect("values") {
            values.insert(key.clone(), f64s(column));
        }
        let grid = build_txffe_grid_v1(
            &values,
            case["c0_min"].as_f64().expect("c0_min"),
            case["retain_invalid"].as_bool().unwrap_or(false),
        )
        .expect("grid");
        output["build_grid"] = serde_json::json!({
            "cursor": grid.cursor(),
            "taps": grid.taps(),
            "source_indices": grid.source_indices(),
            "precursor_count": grid.precursor_count(),
        });
    }
    if let Some(case) = value.get("first_best") {
        let best = first_strict_best_v1(&f64s(&case["scores"])).expect("best");
        output["first_best"] = serde_json::json!({ "index": best });
    }
    if let Some(case) = value.get("fom_tracker") {
        let values = f64s(&case["values"]);
        let shape: Vec<usize> = case["shape"]
            .as_array()
            .expect("shape")
            .iter()
            .map(|item| item.as_u64().expect("dim") as usize)
            .collect();
        let valid = case.get("valid").map(|mask| {
            mask.as_array()
                .expect("mask")
                .iter()
                .map(|item| item.as_bool().expect("bool"))
                .collect::<Vec<bool>>()
        });
        let selection = select_fom_tracker_v1(&values, &shape, valid.as_deref()).expect("fom");
        output["fom_tracker"] = serde_json::json!({
            "indices": selection.indices(),
            "score": selection.score(),
        });
    }
    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string(&output).expect("json"));
    }
}
