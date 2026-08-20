//! External-only warning-report aggregator cross-check runner (P5-02n).
//!
//! Reads a JSON array of [slice_name, anti_causal_flagged, high_freq_flagged]
//! triples, applies aggregate_warning_report_v1, and emits the sorted active
//! warning codes, per-code flagging slices, and flagged-total. The cross-check
//! harness compares this against an independent Python reference.

use std::path::PathBuf;

use sipi_com::{
    WARNING_REPORT_POLICY_V1, WarningReportErrorV1, WarningSliceReportV1,
    aggregate_warning_report_v1,
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
        println!("usage: p5_02n_warning_report_runner --input <json> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: serde_json::Value = serde_json::from_slice(&bytes).expect("input json");
    let mut slices: Vec<WarningSliceReportV1> = Vec::new();
    if let Some(arr) = value.as_array() {
        for row in arr {
            let name = row[0].as_str().unwrap().to_string();
            let anti = row[1].as_bool().unwrap_or(false);
            let high = row[2].as_bool().unwrap_or(false);
            slices.push(WarningSliceReportV1::new(name, anti, high));
        }
    }
    let output = match aggregate_warning_report_v1(&slices) {
        Err(error) => serde_json::json!({
            "policy": WARNING_REPORT_POLICY_V1,
            "ok": false,
            "error": error_label(&error),
            "active_codes": [],
            "flagged_total": 0,
            "per_code": [],
        }),
        Ok(report) => {
            let active: Vec<String> = report
                .active_codes()
                .iter()
                .map(|c| c.token().to_string())
                .collect();
            let per_code: Vec<serde_json::Value> = report
                .per_code_slices()
                .iter()
                .map(|(code, names)| serde_json::json!({ "code": code.token(), "slices": names }))
                .collect();
            serde_json::json!({
                "policy": WARNING_REPORT_POLICY_V1,
                "ok": true,
                "error": null,
                "active_codes": active,
                "flagged_total": report.flagged_slices_total(),
                "per_code": per_code,
            })
        }
    };
    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string(&output).expect("json"));
    }
}

fn error_label(error: &WarningReportErrorV1) -> String {
    match error {
        WarningReportErrorV1::EmptyReports => "empty_reports".to_string(),
        WarningReportErrorV1::EmptySliceName => "empty_slice_name".to_string(),
    }
}
