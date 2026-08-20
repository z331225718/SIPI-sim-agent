//! External-only sampled-signal PDF cross-check runner (P5-04f).
//!
//! Reads a JSON array of float64 samples plus PDF controls and reports
//! the product sampled-signal PDF (bin size, minimum bin, probability
//! array) and a hash of the exact input bytes. Ignored by default;
//! external-custody tooling only.

use std::path::PathBuf;

use sha2::{Digest, Sha256};
use sipi_com::{sampled_signal_pdf_v1, SAMPLED_SIGNAL_PDF_POLICY_V1};

fn main() {
    let mut samples = None;
    let mut levels = 4u32;
    let mut bin_size = 1e-2_f64;
    let mut sparse = false;
    let mut report = None;
    let mut args = std::env::args().skip(1);
    while let Some(argument) = args.next() {
        let mut value = || args.next().expect("argument value");
        match argument.as_str() {
            "--samples" => samples = Some(PathBuf::from(value())),
            "--levels" => levels = value().parse().expect("levels"),
            "--bin-size" => bin_size = value().parse().expect("bin size"),
            "--sparse" => sparse = true,
            "--report" => report = Some(PathBuf::from(value())),
            other => panic!("unknown argument: {other}"),
        }
    }
    let Some(samples) = samples else {
        println!(
            "usage: p5_04f_sampled_signal_runner --samples <json> [--levels <n>] [--bin-size <f>] [--sparse] [--report <path>]"
        );
        return;
    };
    let bytes = std::fs::read(&samples).expect("read samples");
    let digest = format!("{:x}", Sha256::digest(&bytes));
    let values: Vec<f64> = serde_json::from_slice(&bytes).expect("samples json");
    let pdf = sampled_signal_pdf_v1(&values, levels, bin_size, sparse).expect("pdf");
    let report_json = serde_json::json!({
        "samples_sha256": digest,
        "levels": levels,
        "bin_size": bin_size,
        "sparse_pam": sparse,
        "bin_size_out": pdf.bin_size(),
        "min_bin": pdf.min_bin(),
        "probability": pdf.probability(),
        "policy": SAMPLED_SIGNAL_PDF_POLICY_V1,
    });
    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string_pretty(&report_json).expect("json"))
            .expect("write");
    } else {
        println!("{}", serde_json::to_string_pretty(&report_json).expect("json"));
    }
}
