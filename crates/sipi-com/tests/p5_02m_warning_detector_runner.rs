//! External-only warning-detector cross-check runner (P5-02m).
//!
//! Runs the anti-causal and high-frequency non-decay detectors for hash-only
//! comparison with independent references. Ignored by default.

use std::path::PathBuf;

use sipi_com::{
    anti_causal_precursor_fraction_v1, detect_anti_causal_v1, detect_high_freq_non_decay_v1,
    WARNING_DETECTOR_POLICY_V1,
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
        println!("usage: p5_02m_warning_detector_runner --input <json> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: serde_json::Value = serde_json::from_slice(&bytes).expect("input json");

    let impulse: Vec<f64> = value["impulse"].as_array().unwrap().iter().map(|v| v.as_f64().unwrap()).collect();
    let exclusion = value["exclusion"].as_u64().unwrap_or(2) as usize;
    let threshold = value["threshold"].as_f64().unwrap_or(0.05);
    let mag: Vec<f64> = value["mag"].as_array().unwrap().iter().map(|v| v.as_f64().unwrap()).collect();
    let tail = value["tail"].as_u64().unwrap_or(2) as usize;

    let output = serde_json::json!({
        "policy": WARNING_DETECTOR_POLICY_V1,
        "fraction": anti_causal_precursor_fraction_v1(&impulse, exclusion).unwrap_or(0.0),
        "anti_causal": detect_anti_causal_v1(&impulse, exclusion, threshold).unwrap_or(false),
        "non_decay": detect_high_freq_non_decay_v1(&mag, tail).unwrap_or(false),
    });
    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string(&output).expect("json"));
    }
}