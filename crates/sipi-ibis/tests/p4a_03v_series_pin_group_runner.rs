//! External-only typed series pin group cross-check runner (P4A-03v).
//!
//! Lifts one typed [Series Pin Mapping] group declaration from input parameters
//! and reports the properties for hash-only comparison against an independent reference.
//! Ignored by default; external-custody tooling only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_ibis::{
    lift_series_pin_group_v1, SeriesPinPairV1, SERIES_PIN_MAPPING_GROUP_POLICY_V1,
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
        println!("usage: p4a_03v_series_pin_group_runner --input <json> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");
    let gname = value.get("group_name").and_then(|v| v.as_str()).unwrap_or("");
    let pin_pairs = value.get("pin_pairs").and_then(|v| v.as_array()).map(|arr| {
        arr.iter()
            .filter_map(|item| {
                let p1 = item.get("pin_first").and_then(|v| v.as_str())?;
                let p2 = item.get("pin_second").and_then(|v| v.as_str())?;
                SeriesPinPairV1::try_new(p1, p2).ok()
            })
            .collect()
    }).unwrap_or_default();

    let output = match lift_series_pin_group_v1(gname, pin_pairs) {
        Ok(group) => {
            let pairs: Vec<serde_json::Value> = group
                .pin_pairs()
                .iter()
                .map(|p| {
                    serde_json::json!({
                        "pin_first": p.pin_first(),
                        "pin_second": p.pin_second(),
                    })
                })
                .collect();
            serde_json::json!({
                "policy": SERIES_PIN_MAPPING_GROUP_POLICY_V1,
                "valid": true,
                "group_name": group.group_name(),
                "pin_pair_count": group.pin_pairs().len(),
                "pin_pairs": pairs,
            })
        }
        Err(e) => {
            serde_json::json!({
                "policy": SERIES_PIN_MAPPING_GROUP_POLICY_V1,
                "valid": false,
                "lift_error": format!("{e:?}"),
            })
        }
    };

    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string_pretty(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string_pretty(&output).expect("json"));
    }
}
