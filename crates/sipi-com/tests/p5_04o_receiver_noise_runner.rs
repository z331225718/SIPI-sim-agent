//! External-only receiver noise cross-check runner (P5-04o).
//!
//! Runs the filter chain, RxFFE frequency response, and receiver-noise
//! integration on JSON inputs and reports the results. Ignored by
//! default; external-custody tooling only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_com::{
    RECEIVER_NOISE_POLICY_V1, ReceiverNoiseOptionsV1, ReceiverNoiseParamsV1,
    bessel_thomson_filter_v1, butterworth_filter_v1, raised_cosine_filter_v1, receiver_noise_v1,
    rx_ffe_frequency_response_v1,
};
use sipi_types::Complex64;

fn f64s(value: &Value) -> Vec<f64> {
    value
        .as_array()
        .expect("array")
        .iter()
        .map(|item| item.as_f64().expect("f64"))
        .collect()
}

fn complex_json(values: &[Complex64]) -> Value {
    serde_json::json!(
        values
            .iter()
            .map(|value| serde_json::json!({"real": value.real(), "imag": value.imaginary()}))
            .collect::<Vec<_>>()
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
        println!("usage: p5_04o_receiver_noise_runner --input <json> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");
    let mut output = serde_json::json!({ "policy": RECEIVER_NOISE_POLICY_V1 });
    if let Some(case) = value.get("bessel") {
        let result = bessel_thomson_filter_v1(
            &f64s(&case["frequency"]),
            case["order"].as_u64().expect("order") as usize,
            case["cutoff_multiplier"].as_f64().expect("cutoff"),
            case["baud_hz"].as_f64().expect("baud"),
            case["enabled"].as_bool().expect("enabled"),
        )
        .expect("bessel");
        output["bessel"] = serde_json::json!({ "response": complex_json(&result) });
    }
    if let Some(case) = value.get("butterworth") {
        let result = butterworth_filter_v1(
            &f64s(&case["frequency"]),
            case["cutoff_multiplier"].as_f64().expect("cutoff"),
            case["baud_hz"].as_f64().expect("baud"),
            case["enabled"].as_bool().expect("enabled"),
        )
        .expect("bw");
        output["butterworth"] = serde_json::json!({ "response": complex_json(&result) });
    }
    if let Some(case) = value.get("raised_cosine") {
        let result = raised_cosine_filter_v1(
            &f64s(&case["frequency"]),
            case["start_hz"].as_f64().expect("start"),
            case["end_hz"].as_f64().expect("end"),
            case["enabled"].as_bool().expect("enabled"),
        )
        .expect("rc");
        output["raised_cosine"] = serde_json::json!({ "response": result });
    }
    if let Some(case) = value.get("rxffe_fd") {
        let result = rx_ffe_frequency_response_v1(
            &f64s(&case["frequency"]),
            &f64s(&case["taps"]),
            case["precursor_count"].as_u64().expect("pc") as usize,
            case["baud_hz"].as_f64().expect("baud"),
        )
        .expect("rxffe");
        output["rxffe_fd"] = serde_json::json!({ "response": complex_json(&result) });
    }
    if let Some(case) = value.get("receiver_noise") {
        let p = &case["parameters"];
        let parameters = ReceiverNoiseParamsV1 {
            fb: p["fb"].as_f64().expect("fb"),
            btorder: p["btorder"].as_u64().expect("bt") as usize,
            fb_bt_cutoff: p["fb_bt_cutoff"].as_f64().expect("btc"),
            fb_bw_cutoff: p["fb_bw_cutoff"].as_f64().expect("bwc"),
            rc_start: p["rc_start"].as_f64().expect("rcs"),
            rc_end: p["rc_end"].as_f64().expect("rce"),
            eta_0: p["eta_0"].as_f64().expect("eta"),
            accm_max_freq: p["accm_max_freq"].as_f64().expect("accm"),
            ac_cm_rms: f64s(&p["ac_cm_rms"]),
            ctle_gdc_values: f64s(&p["ctle_gdc_values"]),
            ctle_fz: f64s(&p["ctle_fz"]),
            ctle_fp1: f64s(&p["ctle_fp1"]),
            ctle_fp2: f64s(&p["ctle_fp2"]),
            ctle_type: p["ctle_type"].as_str().expect("type").to_string(),
            f_hp: f64s(&p["f_hp"]),
            f_hp_z: f64s(&p["f_hp_z"]),
            f_hp_p: f64s(&p["f_hp_p"]),
        };
        let o = &case["options"];
        let options = ReceiverNoiseOptionsV1 {
            bessel_thomson: o["bessel_thomson"].as_bool().expect("bt"),
            butterworth: o["butterworth"].as_bool().expect("bw"),
            raised_cosine: o["raised_cosine"].as_bool().expect("rc"),
            use_eta0_psd: o["use_eta0_psd"].as_bool().expect("eta0"),
            wc_portz: o["wc_portz"].as_bool().expect("wc"),
            pkg_len_select: case["options"]["pkg_len_select"]
                .as_array()
                .expect("pkg")
                .iter()
                .map(|item| item.as_i64().expect("sel"))
                .collect(),
        };
        let transfers: Vec<Vec<Complex64>> = case["ac_common_mode_transfers"]
            .as_array()
            .map(|rows| {
                rows.iter()
                    .map(|row| {
                        row.as_array()
                            .expect("row")
                            .iter()
                            .map(|item| {
                                Complex64::try_new(
                                    item["real"].as_f64().expect("real"),
                                    item["imag"].as_f64().expect("imag"),
                                )
                                .expect("complex")
                            })
                            .collect()
                    })
                    .collect()
            })
            .unwrap_or_default();
        let taps = case["rx_ffe_taps"].as_array().map(|items| {
            items
                .iter()
                .map(|item| item.as_f64().expect("tap"))
                .collect::<Vec<f64>>()
        });
        let pc = case["rx_ffe_precursor_count"].as_u64().map(|v| v as usize);
        let result = receiver_noise_v1(
            &f64s(&case["frequency"]),
            case["ctle_index"].as_u64().expect("ci") as usize,
            case["high_pass_index"].as_u64().expect("hi") as usize,
            case["high_pass_gain_db"].as_f64().expect("hp"),
            &parameters,
            &options,
            &transfers,
            case["package_case_index"].as_u64().expect("pkg") as usize,
            taps.as_deref(),
            pc,
            case["include_accm"].as_bool().expect("accm"),
        )
        .expect("noise");
        output["receiver_noise"] = serde_json::json!({ "noise": result });
    }
    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string(&output).expect("json"));
    }
}
