//! External-only horizontal-margin cross-check runner (P3C-02g).
//!
//! Composes bathtub opening + sampling-point offset into horizontal margins
//! for hash-only comparison with an independent reference.

use std::path::PathBuf;

use sipi_com::{BathtubSampleV1, HORIZONTAL_MARGIN_POLICY_V1, margins_from_bathtub_v1};

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
        println!("usage: p3c_02g_margin_runner --input <json> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: serde_json::Value = serde_json::from_slice(&bytes).expect("input json");

    let target = value["target_ber"].as_f64().expect("target");
    let sample_off = value["sample_offset_ui"].as_f64().expect("sample_offset");
    let mut samples = Vec::new();
    if let Some(arr) = value.get("samples").and_then(|v| v.as_array()) {
        for s in arr {
            samples.push(BathtubSampleV1::new(
                s[0].as_f64().unwrap(),
                s[1].as_f64().unwrap(),
            ));
        }
    }

    let result = margins_from_bathtub_v1(&samples, target, sample_off);
    let output = match &result {
        Ok(m) => serde_json::json!({ "policy": HORIZONTAL_MARGIN_POLICY_V1, "ok": true,
            "eye_width": m.eye_width_ui(), "left": m.left_margin_ui(), "right": m.right_margin_ui() }),
        Err(e) => {
            serde_json::json!({ "policy": HORIZONTAL_MARGIN_POLICY_V1, "ok": false, "error": format!("{e:?}") })
        }
    };
    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string(&output).expect("json"));
    }
}
