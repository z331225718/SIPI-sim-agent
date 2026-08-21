//! External-custody declaration/linkage observation runner (P4A-03).
//!
//! This test-only target accepts one explicit file path and marker set. It is
//! not a product asset route and does not select electrical behavior.

use std::{collections::BTreeSet, path::PathBuf};

use serde_json::json;
use sipi_ibis::{IBIS_TYPED_INVENTORY_POLICY_V1, IbisTypedInventoryServiceV1, ParseLimitsV1};

fn main() {
    let mut input = None;
    let mut markers = BTreeSet::new();
    let mut args = std::env::args().skip(1);
    while let Some(argument) = args.next() {
        match argument.as_str() {
            "--input" => input = args.next().map(PathBuf::from),
            "--marker" => {
                markers.insert(args.next().expect("--marker value"));
            }
            other => panic!("unknown argument: {other}"),
        }
    }
    let input = input.expect("--input <path>");
    let bytes = std::fs::read(input).expect("read input");
    let limits = ParseLimitsV1::try_new(8 * 1024 * 1024, 4 * 1024 * 1024, 128 * 1024, 256 * 1024)
        .expect("limits");

    match IbisTypedInventoryServiceV1::inspect(&bytes, limits, &markers) {
        Ok(report) => println!(
            "{}",
            json!({
                "policy": IBIS_TYPED_INVENTORY_POLICY_V1,
                "valid": true,
                "input_byte_length": report.input_byte_length(),
                "input_sha256": report.input_sha256(),
                "declared_version": report.declared_version(),
                "component_names": report.component_names(),
                "model_count": report.models().len(),
                "selector_count": report.selectors().len(),
                "pin_count": report.pins().len(),
                "direct_model_pin_count": report.linkage().direct_model_count(),
                "selector_pin_count": report.linkage().selector_count(),
                "marker_pin_count": report.linkage().marker_count(),
                "electrical_behavior_status": report.electrical_behavior_status(),
                "profile_selection_status": report.profile_selection_status(),
            })
        ),
        Err(error) => {
            println!(
                "{}",
                json!({
                    "policy": IBIS_TYPED_INVENTORY_POLICY_V1,
                    "valid": false,
                    "error": error.to_string(),
                })
            );
            std::process::exit(2);
        }
    }
}
