//! External-only bathtub opening-width cross-check runner (P3C-02f).
//!
//! Computes the bathtub opening width at a target BER from a V-shaped
//! BER-vs-time sample set for hash-only comparison with an independent
//! reference. Ignored by default.

use std::path::PathBuf;

use sipi_com::{bathtub_opening_width_v1, BathtubSampleV1, BATHTUB_POLICY_V1};

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
        println!("usage: p3c_02f_bathtub_runner --input <json> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: serde_json::Value = serde_json::from_slice(&bytes).expect("input json");
    let target = value["target_ber"].as_f64().expect("target");

    let mut samples = Vec::new();
    if let Some(arr) = value.get("samples").and_then(|v| v.as_array()) {
        for s in arr {
            samples.push(BathtubSampleV1::new(s[0].as_f64().unwrap(), s[1].as_f64().unwrap()));
        }
    }

    let width_result = bathtub_opening_width_v1(&samples, target);
    let output = match &width_result {
        Ok(w) => serde_json::json!({ "policy": BATHTUB_POLICY_V1, "width": w, "error": null }),
        Err(e) => serde_json::json!({ "policy": BATHTUB_POLICY_V1, "width": null, "error": format!("{e:?}") }),
    };
    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string(&output).expect("json"));
    }
}