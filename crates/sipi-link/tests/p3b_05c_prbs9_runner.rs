//! External-only PRBS9 sequence cross-check runner (P3B-05c).
//!
//! Emits deterministic PRBS9 bits/bytes from the product core for
//! hash-only comparison against the independent ITU-T O.150 PRBS9
//! reference. Ignored by default; external-custody tooling only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_link::{Prbs9V1, PRBS9_POLICY_V1};

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
        println!("usage: p3b_05c_prbs9_runner --input <json> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");

    let seed = value["seed"].as_u64().unwrap_or(0x1) as u16;
    let bits = value["bits"].as_u64().expect("bits") as usize;
    let mut generator = Prbs9V1::new(seed);

    // Raw output bits (0/1) as an array for exact comparison.
    let mut bit_values = Vec::with_capacity(bits);
    for _ in 0..bits {
        bit_values.push(generator.next_bit() as u64);
    }

    // LSB-first packed bytes over the same stream (fresh generator).
    let mut gen2 = Prbs9V1::new(seed);
    let byte_values = gen2.next_bytes(bits);

    let output = serde_json::json!({
        "policy": PRBS9_POLICY_V1,
        "seed": seed,
        "bits": bits,
        "first_16": bit_values.iter().take(16).cloned().collect::<Vec<_>>(),
        "bit_values": bit_values,
        "bytes": byte_values,
    });
    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string(&output).expect("json"));
    }
}