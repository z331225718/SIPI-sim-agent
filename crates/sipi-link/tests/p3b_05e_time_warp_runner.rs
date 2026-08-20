//! External-only time-warp shift cross-check runner (P3B-05e).
//!
//! Reads a JSON input describing a samples array and a per-sample shift
//! array, applies time_warp_shift_v1, and emits a JSON report with the
//! resulting waveform or a stable error label. The cross-check harness
//! compares this against an independent Python reference.

use std::path::PathBuf;

use sipi_link::{time_warp_shift_v1, TimeWarpErrorV1, TIME_WARP_POLICY_V1};

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
        println!("usage: p3b_05e_time_warp_runner --input <json> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: serde_json::Value = serde_json::from_slice(&bytes).expect("input json");

    let samples: Vec<f64> = value["samples"]
        .as_array()
        .expect("samples array")
        .iter()
        .map(|v| v.as_f64().expect("sample f64"))
        .collect();
    let shifts: Vec<f64> = value["shifts"]
        .as_array()
        .expect("shifts array")
        .iter()
        .map(|v| v.as_f64().expect("shift f64"))
        .collect();

    let output = match time_warp_shift_v1(&samples, &shifts) {
        Err(error) => serde_json::json!({
            "policy": TIME_WARP_POLICY_V1,
            "ok": false,
            "error": error_label(&error),
            "samples": [],
        }),
        Ok(out) => serde_json::json!({
            "policy": TIME_WARP_POLICY_V1,
            "ok": true,
            "error": null,
            "samples": out,
        }),
    };
    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string(&output).expect("json"));
    }
}

fn error_label(error: &TimeWarpErrorV1) -> String {
    match error {
        TimeWarpErrorV1::EmptyWaveform => "empty_waveform".to_string(),
        TimeWarpErrorV1::LengthMismatch => "length_mismatch".to_string(),
        TimeWarpErrorV1::NonFiniteSample => "non_finite_sample".to_string(),
        TimeWarpErrorV1::NonFiniteShift => "non_finite_shift".to_string(),
        TimeWarpErrorV1::OutOfDomain { index } => format!("out_of_domain:{index}"),
    }
}
