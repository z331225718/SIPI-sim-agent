//! External-only statistical eye contour cross-check runner (P3C-02i).
//!
//! Reads a statistical eye grid plus a target Q, computes the Q-threshold
//! contour, and reports the per-column crossings for hash-only comparison
//! against an independent reference. Ignored by default; external-custody
//! tooling only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_com::{statistical_eye_contour_v1, EyeGridV1, EYE_CONTOUR_POLICY_V1};

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
        println!("usage: p3c_02i_eye_contour_runner --input <path> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");

    let mut time_offsets = Vec::new();
    if let Some(arr) = value.get("time_offsets").and_then(|v| v.as_array()) {
        time_offsets.extend(arr.iter().filter_map(|v| v.as_f64()));
    }
    let mut voltage_levels = Vec::new();
    if let Some(arr) = value.get("voltage_levels").and_then(|v| v.as_array()) {
        voltage_levels.extend(arr.iter().filter_map(|v| v.as_f64()));
    }
    let mut q_grid = Vec::new();
    if let Some(arr) = value.get("q_grid").and_then(|v| v.as_array()) {
        for column in arr {
            let mut row_values = Vec::new();
            if let Some(items) = column.as_array() {
                row_values.extend(items.iter().filter_map(|v| v.as_f64()));
            }
            q_grid.push(row_values);
        }
    }
    let target_q = value.get("target_q").and_then(|v| v.as_f64()).unwrap_or(f64::NAN);

    let grid = EyeGridV1::new(time_offsets, voltage_levels, q_grid);
    let output = match statistical_eye_contour_v1(&grid, target_q) {
        Ok(contour) => {
            let columns_json: Vec<Value> = contour
                .columns()
                .iter()
                .map(|c| {
                    serde_json::json!({
                        "time_offset_ui": c.time_offset_ui(),
                        "lower_voltage": c.lower_voltage(),
                        "upper_voltage": c.upper_voltage(),
                    })
                })
                .collect();
            serde_json::json!({
                "policy": EYE_CONTOUR_POLICY_V1,
                "valid": true,
                "target_q": contour.target_q(),
                "columns": Value::Array(columns_json),
            })
        }
        Err(e) => {
            serde_json::json!({
                "policy": EYE_CONTOUR_POLICY_V1,
                "valid": false,
                "contour_error": format!("{e:?}"),
            })
        }
    };

    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string_pretty(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string_pretty(&output).expect("json"));
    }
}
