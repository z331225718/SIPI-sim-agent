//! External-only r4.80 noise-PDF build cross-check runner (P5-04h).
//!
//! Reads JSON inputs (sci/fext/next PDFs, jitter response, scalars) and
//! reports the built R480 noise PDF surface (sigmas, ber_q, combined/
//! gaussian/jitter PDFs). Ignored by default; external-custody tooling only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_com::{
    build_r480_noise_pdf_v1, DiscretePdfV1, BUILD_NOISE_PDF_POLICY_V1,
};

fn pdf_from_json(value: &Value) -> DiscretePdfV1 {
    let bin_size = value["bin_size"].as_f64().expect("bin_size");
    let min_bin = value["min_bin"].as_i64().expect("min_bin");
    let probability: Vec<f64> = value["probability"]
        .as_array()
        .expect("probability")
        .iter()
        .map(|item| item.as_f64().expect("mass"))
        .collect();
    DiscretePdfV1::try_new(bin_size, min_bin, probability).expect("pdf")
}

fn pdf_json(pdf: &DiscretePdfV1) -> Value {
    serde_json::json!({
        "bin_size": pdf.bin_size(),
        "min_bin": pdf.min_bin(),
        "probability": pdf.probability(),
    })
}

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
        println!("usage: p5_04h_noise_pdf_runner --input <json> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");
    let sci = pdf_from_json(&value["sci_pdf"]);
    let fext: Vec<DiscretePdfV1> = value["fext_pdfs"]
        .as_array()
        .map(|items| items.iter().map(pdf_from_json).collect())
        .unwrap_or_default();
    let next: Vec<DiscretePdfV1> = value["next_pdfs"]
        .as_array()
        .map(|items| items.iter().map(pdf_from_json).collect())
        .unwrap_or_default();
    let h_j: Vec<f64> = value["jitter_response"]
        .as_array()
        .expect("jitter_response")
        .iter()
        .map(|item| item.as_f64().expect("h"))
        .collect();
    let built = build_r480_noise_pdf_v1(
        &sci,
        &fext,
        &next,
        value["levels"].as_u64().expect("levels") as u32,
        value["available_signal_v"].as_f64().expect("available"),
        value["r_lm_ohm"].as_f64().expect("r_lm"),
        value["tx_snr_db"].as_f64().expect("snr"),
        value["sigma_x"].as_f64().expect("sigma_x"),
        value["sigma_rj_s"].as_f64().expect("sigma_rj_s"),
        &h_j,
        value["sigma_n_v"].as_f64().expect("sigma_n"),
        value["amplitude_dd_v"].as_f64().expect("amplitude"),
        value["spec_ber"].as_f64().expect("spec_ber"),
        value["noise_crest_factor"].as_f64().unwrap_or(0.0),
        value["sigma_ne_v"].as_f64().unwrap_or(0.0),
        value["bbn_q_factor"].as_f64().map(|v| {
            if v.is_nan() { None } else { Some(v) }
        }).flatten(),
        value["sigma_tx_override_v"].as_f64(),
        value["sigma_rj_override_v"].as_f64(),
    )
    .expect("built");
    let combined = built.result();
    let output = serde_json::json!({
        "sigma_tx_v": built.sigma_tx_v(),
        "sigma_rj_v": built.sigma_rj_v(),
        "sigma_gaussian_v": built.sigma_gaussian_v(),
        "ber_q": built.ber_q(),
        "combined": pdf_json(combined.combined()),
        "combined_cdf_tail": combined.cdf().last(),
        "gaussian_pdf": pdf_json(built.gaussian_pdf()),
        "jitter_pdf": pdf_json(built.jitter_pdf()),
        "peak_interference_v": combined.peak_interference_v(),
        "policy": BUILD_NOISE_PDF_POLICY_V1,
    });
    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string(&output).expect("json"));
    }
}
