//! External-only residual-channel PDF cross-check runner (P5-04g).
//!
//! Reads a JSON float64 pulse array plus residual PDF controls and
//! reports the product result surface: sampled PDF, residual pulse,
//! selected phase, and a hash of the exact input bytes. Ignored by
//! default; external-custody tooling only.

use std::path::PathBuf;

use sha2::{Digest, Sha256};
use sipi_com::{RESIDUAL_CHANNEL_PDF_POLICY_V1, residual_channel_pdf_v1};

fn read_f64_array(path: &PathBuf, label: &str) -> Vec<f64> {
    let bytes = std::fs::read(path).expect("read");
    let values: Vec<f64> = serde_json::from_slice(&bytes).expect("json array");
    if values.is_empty() {
        panic!("{label} array is empty");
    }
    values
}

fn main() {
    let mut pulse = None;
    let mut channel_type = String::new();
    let mut cursor_index = 0usize;
    let mut samples_per_ui = 8usize;
    let mut levels = 4u32;
    let mut bin_size = 1e-2_f64;
    let mut dfe_tap_count = 0i64;
    let mut dfe_max = None;
    let mut dfe_min = None;
    let mut dfe_step = 0.0_f64;
    let mut floating_dfe = false;
    let mut dfe_max_count = None;
    let mut phase_index = None;
    let mut report = None;
    let mut args = std::env::args().skip(1);
    while let Some(argument) = args.next() {
        let mut value = || args.next().expect("argument value");
        match argument.as_str() {
            "--pulse" => pulse = Some(PathBuf::from(value())),
            "--channel-type" => channel_type = value(),
            "--cursor-index" => cursor_index = value().parse().expect("cursor"),
            "--samples-per-ui" => samples_per_ui = value().parse().expect("samples per ui"),
            "--levels" => levels = value().parse().expect("levels"),
            "--bin-size" => bin_size = value().parse().expect("bin size"),
            "--dfe-tap-count" => dfe_tap_count = value().parse().expect("dfe taps"),
            "--dfe-max" => dfe_max = Some(PathBuf::from(value())),
            "--dfe-min" => dfe_min = Some(PathBuf::from(value())),
            "--dfe-step" => dfe_step = value().parse().expect("dfe step"),
            "--floating-dfe" => floating_dfe = true,
            "--dfe-max-count" => dfe_max_count = Some(value().parse().expect("dfe max count")),
            "--phase-index" => phase_index = Some(value().parse().expect("phase index")),
            "--report" => report = Some(PathBuf::from(value())),
            other => panic!("unknown argument: {other}"),
        }
    }
    let Some(pulse) = pulse else {
        println!(
            "usage: p5_04g_residual_pdf_runner --pulse <json> --channel-type <kind> [--cursor-index <n>] [--samples-per-ui <n>] [--levels <n>] [--bin-size <f>] [--dfe-tap-count <n>] [--dfe-max <json>] [--dfe-min <json>] [--dfe-step <f>] [--floating-dfe] [--dfe-max-count <n>] [--phase-index <n>] [--report <path>]"
        );
        return;
    };
    let bytes = std::fs::read(&pulse).expect("read pulse");
    let digest = format!("{:x}", Sha256::digest(&bytes));
    let values: Vec<f64> = serde_json::from_slice(&bytes).expect("pulse json");
    let dfe_max_values = dfe_max.as_ref().map(|path| read_f64_array(path, "dfe-max"));
    let dfe_min_values = dfe_min.as_ref().map(|path| read_f64_array(path, "dfe-min"));
    let result = residual_channel_pdf_v1(
        &values,
        &channel_type,
        cursor_index,
        samples_per_ui,
        levels,
        bin_size,
        dfe_tap_count,
        dfe_max_values.as_deref(),
        dfe_min_values.as_deref(),
        dfe_step,
        floating_dfe,
        dfe_max_count,
        phase_index,
    )
    .expect("residual pdf");
    let report_json = serde_json::json!({
        "pulse_sha256": digest,
        "channel_type": channel_type,
        "pdf": {
            "bin_size": result.pdf().bin_size(),
            "min_bin": result.pdf().min_bin(),
            "probability": result.pdf().probability(),
        },
        "residual_pulse": result.residual_pulse(),
        "selected_phase": result.selected_phase(),
        "policy": RESIDUAL_CHANNEL_PDF_POLICY_V1,
    });
    if let Some(path) = report {
        std::fs::write(
            path,
            serde_json::to_string_pretty(&report_json).expect("json"),
        )
        .expect("write");
    } else {
        println!(
            "{}",
            serde_json::to_string_pretty(&report_json).expect("json")
        );
    }
}
