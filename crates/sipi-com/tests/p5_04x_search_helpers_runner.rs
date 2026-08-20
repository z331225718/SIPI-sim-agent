//! External-only search-loop helper cross-check runner (P5-04t-x).
//!
//! Evaluates the pure-numeric search-loop helpers (rectangular pulse
//! response, peak window, shift matrix) for hash-only comparison against
//! independent references. Ignored by default.

use std::path::PathBuf;

use sipi_com::{SEARCH_LOOP_POLICY_V1, peak_window, rectangular_pulse_response_v1, shift_matrix};

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
        println!("usage: p5_04x_search_helpers_runner --input <json> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: serde_json::Value = serde_json::from_slice(&bytes).expect("input json");

    let impulse: Vec<f64> = value["impulse"]
        .as_array()
        .unwrap()
        .iter()
        .map(|v| v.as_f64().unwrap())
        .collect();
    let spu = value["samples_per_ui"].as_u64().expect("spu") as usize;

    let pulse = rectangular_pulse_response_v1(&impulse, spu).expect("pulse");
    let window = peak_window(&pulse, spu, true).expect("window");

    let precursor = value["precursor"].as_u64().expect("precursor") as usize;
    let taps = value["taps"].as_u64().expect("taps") as usize;
    let matrix = shift_matrix(&pulse, precursor, spu, taps);

    let output = serde_json::json!({
        "policy": SEARCH_LOOP_POLICY_V1,
        "pulse": pulse,
        "window": window,
        "matrix": matrix,
    });
    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string(&output).expect("json"));
    }
}
