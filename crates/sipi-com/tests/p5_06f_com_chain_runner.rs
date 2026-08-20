//! Fixed-tap COM chain integration runner (P5-06f).
//!
//! Reads a JSON input {pulse: [...], controls: {...}} and runs the
//! product fixed-tap chain (cursor -> residual PDF -> noise build ->
//! combined noise -> metrics), reporting every stage checkpoint plus an
//! exact SHA-256 of the input bytes. Ignored by default; external
//! cross-check tooling only.

use std::path::PathBuf;

use serde_json::Value;
use sha2::{Digest, Sha256};
use sipi_com::{COM_CHAIN_POLICY_V1, ComChainControlsV1, ComChainErrorV1, run_com_chain_v1};

fn f64s(value: &Value) -> Vec<f64> {
    value
        .as_array()
        .expect("array")
        .iter()
        .map(|item| item.as_f64().expect("f64"))
        .collect()
}

fn build_controls(c: &Value) -> Result<ComChainControlsV1, ComChainErrorV1> {
    let opt = |key: &str| c.get(key).and_then(|v| v.as_f64());
    ComChainControlsV1::try_new(
        c["samples_per_ui"].as_u64().expect("spu") as usize,
        c["levels"].as_u64().expect("levels") as u32,
        c["bin_size"].as_f64().expect("bin"),
        c["dfe_first_max"].as_f64().expect("dfm"),
        c["cdr"].as_str().expect("cdr").to_string(),
        c["peak_start"].as_u64().expect("ps") as usize,
        c.get("peak_stop")
            .and_then(|v| v.as_u64())
            .map(|v| v as usize),
        c["dfe_tap_count"].as_i64().expect("dfc"),
        f64s(&c["dfe_max"]),
        f64s(&c["dfe_min"]),
        c["dfe_step"].as_f64().expect("dfs"),
        c["floating_dfe"].as_bool().expect("fd"),
        c.get("dfe_max_count").and_then(|v| v.as_i64()),
        c["available_signal_v"].as_f64().expect("asv"),
        c["r_lm_ohm"].as_f64().expect("rlm"),
        c["tx_snr_db"].as_f64().expect("txsnr"),
        c["sigma_x"].as_f64().expect("sx"),
        c["sigma_rj_s"].as_f64().expect("srj"),
        f64s(&c["jitter_response"]),
        c["sigma_n_v"].as_f64().expect("sn"),
        c["amplitude_dd_v"].as_f64().expect("add"),
        c["spec_ber"].as_f64().expect("sb"),
        c["noise_crest_factor"].as_f64().expect("ncf"),
        c["sigma_ne_v"].as_f64().expect("sne"),
        opt("bbn_q_factor"),
        opt("sigma_tx_override_v"),
        opt("sigma_rj_override_v"),
        c["pass_threshold_db"].as_f64().expect("pt"),
        c["t_o_s"].as_f64().expect("tos"),
        opt("eye_opening_v"),
    )
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
        println!("usage: p5_06f_com_chain_runner --input <json> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let digest = format!("{:x}", Sha256::digest(&bytes));
    let value: Value = serde_json::from_slice(&bytes).expect("input json");
    let pulse = f64s(&value["pulse"]);
    let controls = build_controls(&value["controls"]).expect("controls");
    let chain = run_com_chain_v1(&pulse, &controls).expect("chain");
    let pdf_json = |pdf: &sipi_com::DiscretePdfV1| {
        serde_json::json!({
            "bin_size": pdf.bin_size(),
            "min_bin": pdf.min_bin(),
            "probability": pdf.probability(),
        })
    };
    let report_json = serde_json::json!({
        "inputs_sha256": digest,
        "policy": COM_CHAIN_POLICY_V1,
        "cursor": {
            "cursor_index": chain.cursor().cursor_index(),
            "peak_index": chain.cursor().peak_index(),
            "no_zero_crossing": chain.cursor().no_zero_crossing(),
        },
        "residual": {
            "selected_phase": chain.residual().selected_phase(),
            "residual_pulse": chain.residual().residual_pulse(),
            "pdf": pdf_json(chain.residual().pdf()),
        },
        "noise": {
            "sigma_tx_v": chain.noise().sigma_tx_v(),
            "sigma_rj_v": chain.noise().sigma_rj_v(),
            "sigma_gaussian_v": chain.noise().sigma_gaussian_v(),
            "ber_q": chain.noise().ber_q(),
            "gaussian_pdf": pdf_json(chain.noise().gaussian_pdf()),
            "jitter_pdf": pdf_json(chain.noise().jitter_pdf()),
        },
        "combined": {
            "peak_interference_v": chain.combined().peak_interference_v(),
            "cdf": chain.combined().cdf(),
            "combined_pdf": pdf_json(chain.combined().combined()),
        },
        "metrics": {
            "com_db": chain.metrics().com_db(),
            "vec_db": chain.metrics().vec_db(),
            "veo_mv": chain.metrics().veo_mv(),
        },
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
