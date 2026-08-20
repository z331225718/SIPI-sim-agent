//! External-only typed pin-declaration cross-check runner (P4A-03e).

use std::path::PathBuf;

use sipi_ibis::{
    PIN_DECLARATION_POLICY_V1, ParseLimitsV1, lift_pin_declarations_v1, parse_structural_v1,
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
        println!("usage: p4a_03e_pin_declaration_runner --input <path> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let limits = ParseLimitsV1::try_new(
        8 * 1024 * 1024,
        4 * 1024 * 1024,
        2 * 1024 * 1024,
        4 * 1024 * 1024,
    )
    .expect("limits");
    let document = match parse_structural_v1(&bytes, limits) {
        Ok(d) => d,
        Err(e) => {
            println!(
                "{}",
                serde_json::to_string(&serde_json::json!({ "parse_error": format!("{e}") }))
                    .expect("json")
            );
            return;
        }
    };
    match lift_pin_declarations_v1(document.records()) {
        Ok(pins) => {
            let mut sample = Vec::new();
            for p in pins.iter().take(5) {
                sample.push(serde_json::json!({ "pin": p.pin_name(), "signal": p.signal_name(), "model": p.model_name() }));
            }
            let output = serde_json::json!({ "policy": PIN_DECLARATION_POLICY_V1, "pin_count": pins.len(), "sample": sample });
            if let Some(path) = report {
                std::fs::write(path, serde_json::to_string(&output).expect("json")).expect("write");
            } else {
                println!("{}", serde_json::to_string(&output).expect("json"));
            }
        }
        Err(e) => println!(
            "{}",
            serde_json::to_string(&serde_json::json!({ "lift_error": format!("{e:?}") }))
                .expect("json")
        ),
    }
}
