//! External-only bathtub curve fit cross-check runner (P3C-02h).
//!
//! Reads bathtub samples plus a fit order, fits a polynomial in the log10(BER)
//! domain, and reports the fit for hash-only comparison against an independent
//! reference. Ignored by default; external-custody tooling only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_com::{fit_bathtub_curve_v1, BathtubSampleV1, BATHTUB_FIT_POLICY_V1};

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
        println!("usage: p3c_02h_bathtub_fit_runner --input <path> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");

    let mut samples = Vec::new();
    if let Some(samples_json) = value.get("samples").and_then(|v| v.as_array()) {
        for item in samples_json {
            let t = item.get("t").and_then(|v| v.as_f64()).unwrap_or(f64::NAN);
            let ber = item.get("ber").and_then(|v| v.as_f64()).unwrap_or(f64::NAN);
            samples.push(BathtubSampleV1::new(t, ber));
        }
    }
    let fit_order = value.get("fit_order").and_then(|v| v.as_u64()).unwrap_or(0) as usize;

    let output = match fit_bathtub_curve_v1(&samples, fit_order) {
        Ok(fit) => {
            let coefficients: Vec<String> = fit
                .coefficients()
                .iter()
                .map(|c| format!("{:.12}", c))
                .collect();
            serde_json::json!({
                "policy": BATHTUB_FIT_POLICY_V1,
                "valid": true,
                "fit_order": fit.fit_order(),
                "coefficients": coefficients,
                "sample_count": fit.sample_count(),
                "max_abs_residual": format!("{:.12}", fit.max_abs_residual()),
            })
        }
        Err(e) => {
            serde_json::json!({
                "policy": BATHTUB_FIT_POLICY_V1,
                "valid": false,
                "fit_error": format!("{e:?}"),
            })
        }
    };

    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string_pretty(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string_pretty(&output).expect("json"));
    }
}
