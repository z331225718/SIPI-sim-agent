//! External-only CDR lock semantics cross-check runner (P3B-04b).
//!
//! Reads a CDR lock configuration and a timing error sequence, tracks the lock
//! state machine, and reports the per-sample records for hash-only comparison
//! against an independent reference. Ignored by default; external-custody
//! tooling only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_channel::{
    CDR_LOCK_POLICY_V1, CdrLockConfigV1, CdrLockStateV1, CdrSampleClassificationV1,
    track_cdr_lock_v1,
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
        println!("usage: p3b_04b_cdr_lock_runner --input <path> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");

    let lock_threshold = value
        .get("lock_threshold")
        .and_then(|v| v.as_f64())
        .unwrap_or(f64::NAN);
    let unlock_threshold = value
        .get("unlock_threshold")
        .and_then(|v| v.as_f64())
        .unwrap_or(f64::NAN);
    let lock_count = value
        .get("lock_count")
        .and_then(|v| v.as_u64())
        .unwrap_or(0) as usize;
    let unlock_count = value
        .get("unlock_count")
        .and_then(|v| v.as_u64())
        .unwrap_or(0) as usize;
    let mut errors = Vec::new();
    if let Some(arr) = value.get("errors").and_then(|v| v.as_array()) {
        errors.extend(arr.iter().filter_map(|v| v.as_f64()));
    }

    let config = match CdrLockConfigV1::try_new(
        lock_threshold,
        unlock_threshold,
        lock_count,
        unlock_count,
    ) {
        Ok(c) => c,
        Err(e) => {
            let output = serde_json::json!({
                "policy": CDR_LOCK_POLICY_V1,
                "valid": false,
                "cdr_error": format!("{e:?}"),
            });
            if let Some(p) = report {
                std::fs::write(p, serde_json::to_string_pretty(&output).expect("json"))
                    .expect("write");
            } else {
                println!("{}", serde_json::to_string_pretty(&output).expect("json"));
            }
            return;
        }
    };

    let output = match track_cdr_lock_v1(config, &errors) {
        Ok(tracking) => {
            let samples_json: Vec<Value> = tracking
                .samples()
                .iter()
                .map(|record| {
                    serde_json::json!({
                        "sample_index": record.sample_index(),
                        "error": record.error(),
                        "classification": match record.classification() {
                            CdrSampleClassificationV1::Good => "Good",
                            CdrSampleClassificationV1::Neutral => "Neutral",
                            CdrSampleClassificationV1::Bad => "Bad",
                        },
                        "state_after": match record.state_after() {
                            CdrLockStateV1::Locked => "Locked",
                            CdrLockStateV1::Unlocked => "Unlocked",
                        },
                    })
                })
                .collect();
            serde_json::json!({
                "policy": CDR_LOCK_POLICY_V1,
                "valid": true,
                "final_state": match tracking.final_state() {
                    CdrLockStateV1::Locked => "Locked",
                    CdrLockStateV1::Unlocked => "Unlocked",
                },
                "lock_transitions": tracking.lock_transitions(),
                "unlock_transitions": tracking.unlock_transitions(),
                "samples": Value::Array(samples_json),
            })
        }
        Err(e) => {
            serde_json::json!({
                "policy": CDR_LOCK_POLICY_V1,
                "valid": false,
                "cdr_error": format!("{e:?}"),
            })
        }
    };

    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string_pretty(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string_pretty(&output).expect("json"));
    }
}
