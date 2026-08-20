//! External-only crosstalk noise cross-check runner (P5-04p).
//!
//! Runs the FEXT/NEXT power integration and the TD outer-product path
//! on JSON inputs and reports the results. Ignored by default;
//! external-custody tooling only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_types::Complex64;
use sipi_com::{
    crosstalk_noise_v1, td_source_crosstalk_noise_v1, XtalkChannelV1, XtalkParamsV1,
    CROSSTALK_NOISE_POLICY_V1,
};

fn f64s(value: &Value) -> Vec<f64> {
    value
        .as_array()
        .expect("array")
        .iter()
        .map(|item| item.as_f64().expect("f64"))
        .collect()
}

fn complex_values(value: &Value) -> Vec<Complex64> {
    value
        .as_array()
        .expect("array")
        .iter()
        .map(|item| {
            Complex64::try_new(
                item["real"].as_f64().expect("real"),
                item["imag"].as_f64().expect("imag"),
            )
            .expect("complex")
        })
        .collect()
}

fn channels_from_json(value: &Value) -> Vec<XtalkChannelV1> {
    value
        .as_array()
        .map(|rows| {
            rows.iter()
                .map(|row| {
                    (
                        row["role"].as_str().expect("role").to_string(),
                        complex_values(&row["response"]),
                        row["amplitude"].as_f64().expect("amplitude"),
                    )
                })
                .collect()
        })
        .unwrap_or_default()
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
        println!("usage: p5_04p_crosstalk_runner --input <json> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");
    let mut output = serde_json::json!({ "policy": CROSSTALK_NOISE_POLICY_V1 });
    if let Some(case) = value.get("crosstalk") {
        let parameters = XtalkParamsV1 {
            fb: case["parameters"]["fb"].as_f64().expect("fb"),
            f2: case["parameters"]["f2"].as_f64().expect("f2"),
            sigma_x: case["parameters"]["sigma_x"].as_f64().expect("sigma"),
        };
        let taps = case["rx_ffe_taps"].as_array().map(|items| {
            items.iter().map(|item| item.as_f64().expect("tap")).collect::<Vec<f64>>()
        });
        let pc = case["rx_ffe_precursor_count"].as_u64().map(|v| v as usize);
        let result = crosstalk_noise_v1(
            &f64s(&case["frequency"]),
            &complex_values(&case["h_ctf"]),
            &f64s(&case["taps"]),
            &channels_from_json(&case["channels"]),
            &parameters,
            case["td_source_outer_product"].as_bool().expect("td"),
            taps.as_deref(),
            pc,
        )
        .expect("crosstalk");
        output["crosstalk"] = serde_json::json!({ "noise": result });
    }
    if let Some(case) = value.get("td_crosstalk") {
        let parameters = XtalkParamsV1 {
            fb: case["parameters"]["fb"].as_f64().expect("fb"),
            f2: case["parameters"]["f2"].as_f64().expect("f2"),
            sigma_x: case["parameters"]["sigma_x"].as_f64().expect("sigma"),
        };
        let result = td_source_crosstalk_noise_v1(
            &f64s(&case["frequency"]),
            &complex_values(&case["h_ctf"]),
            &complex_values(&case["tx_filter"]),
            &f64s(&case["sinc"]),
            &channels_from_json(&case["channels"]),
            &parameters,
        )
        .expect("td");
        output["td_crosstalk"] = serde_json::json!({ "noise": result });
    }
    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string(&output).expect("json"));
    }
}
