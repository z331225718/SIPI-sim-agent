//! External-only canonical-input-key signature cross-check runner (P5-06d).
//!
//! Reads a JSON array of [key, canonical value token] pairs, applies
//! canonical_input_keys_v1, and emits the sorted 'key=value' signature lines
//! plus a SHA-256 digest over the lines joined with '\n'. The cross-check
//! harness compares both against an independent Python reference.

use std::path::PathBuf;

use sha2::{Digest, Sha256};

use sipi_com::{
    CANONICAL_INPUT_KEYS_POLICY_V1, CanonicalInputKeysErrorV1, canonical_input_keys_v1,
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
        println!("usage: p5_06d_canonical_input_keys_runner --input <json> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: serde_json::Value = serde_json::from_slice(&bytes).expect("input json");
    let mut entries: Vec<(String, String)> = Vec::new();
    if let Some(arr) = value.as_array() {
        for pair in arr {
            let key = pair[0].as_str().unwrap().to_string();
            let val = pair[1].as_str().unwrap().to_string();
            entries.push((key, val));
        }
    }
    let output = match canonical_input_keys_v1(&entries) {
        Err(error) => serde_json::json!({
            "policy": CANONICAL_INPUT_KEYS_POLICY_V1,
            "ok": false,
            "error": error_label(&error),
            "lines": [],
            "digest": null,
        }),
        Ok(lines) => {
            let joined = lines.join("\n");
            let mut hasher = Sha256::new();
            hasher.update(joined.as_bytes());
            let digest = format!("{:x}", hasher.finalize());
            serde_json::json!({
                "policy": CANONICAL_INPUT_KEYS_POLICY_V1,
                "ok": true,
                "error": null,
                "lines": lines,
                "digest": digest,
            })
        }
    };
    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string(&output).expect("json"));
    }
}

fn error_label(error: &CanonicalInputKeysErrorV1) -> String {
    match error {
        CanonicalInputKeysErrorV1::EmptyInput => "empty_input".to_string(),
        CanonicalInputKeysErrorV1::EmptyKey => "empty_key".to_string(),
        CanonicalInputKeysErrorV1::EmptyValue => "empty_value".to_string(),
        CanonicalInputKeysErrorV1::DuplicateKey(k) => format!("duplicate_key:{k}"),
    }
}
