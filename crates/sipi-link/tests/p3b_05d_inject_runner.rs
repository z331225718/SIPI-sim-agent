//! External-only PRBS9 injection-waveform cross-check runner (P3B-05d).
//!
//! Builds a deterministic PRBS9 injection waveform and reports a hash of the
//! packed bytes for comparison with an independent reference.

use std::path::PathBuf;

use sipi_link::{prbs9_inject_waveform_v1, PRBS9_INJECT_POLICY_V1};

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
        println!("usage: p3b_05d_inject_runner --input <json> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: serde_json::Value = serde_json::from_slice(&bytes).expect("input json");
    let seed = value["seed"].as_u64().unwrap_or(1) as u16;
    let bits = value["bits"].as_u64().expect("bits") as usize;
    let spu = value["spu"].as_u64().expect("spu") as usize;
    let amp = value["amp"].as_f64().expect("amp");

    let waveform = prbs9_inject_waveform_v1(seed, bits, spu, amp).expect("waveform");
    // Pack each sample into a deterministic 0/1-level byte for hashing.
    let packed: Vec<u8> = waveform.iter().map(|v| if *v > 0.0 { 1u8 } else { 0u8 }).collect();

    let output = serde_json::json!({
        "policy": PRBS9_INJECT_POLICY_V1,
        "length": waveform.len(),
        "first_16": waveform.iter().take(16).cloned().collect::<Vec<_>>(),
        "packed": packed,
    });
    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string(&output).expect("json"));
    }
}