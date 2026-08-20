//! External-only runner: authorized DLL raw ABI observation (P4B-07a).
//!
//! Loads one hash-pinned authorized Windows x64 AMI DLL through the
//! clean-room host and runs a fixed probe matrix (init-only, single or
//! multiple GetWave calls with caller-chosen legal lengths). Output is a
//! hash-only JSON report: raw waveforms/clocks are hashed, never written
//! verbatim. This runner is external-custody tooling; it is ignored by
//! default and asserts nothing about AMI semantics, compatibility, or
//! numerical parity.

use std::path::{Path, PathBuf};

use sha2::{Digest, Sha256};
use sipi_ami_host::{AmiGetWaveRequestV1, AmiHostV1, AmiInitRequestV1, DllSha256V1};
use sipi_ami_text::{ParseLimitsV1, parse_and_bind_v1};

fn sha256_hex(bytes: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(bytes);
    format!("{:x}", hasher.finalize())
}

fn sha256_f64(values: &[f64]) -> String {
    let bytes: Vec<u8> = values
        .iter()
        .flat_map(|value| value.to_le_bytes())
        .collect();
    sha256_hex(&bytes)
}

fn hex_to_bytes(hex: &str) -> Vec<u8> {
    (0..hex.len())
        .step_by(2)
        .map(|index| u8::from_str_radix(&hex[index..index + 2], 16).expect("hex"))
        .collect()
}

fn fixed_matrix(variant: &str, rows: usize, aggressors: usize) -> Vec<f64> {
    // Fixed caller-supplied probe inputs, charter-bound; no physical
    // assertion. Variants:
    // - identity_like: main diagonal 1.0, elsewhere 0.0 (07a/07b surface);
    // - decay: victim column (column 0) decays as 2^-row, aggressors 0.0;
    // - uniform: all entries 1.0;
    // - decay_coupled: victim column decays 2^-row, aggressor columns at
    //   0.1 of the victim value per row.
    let columns = aggressors + 1;
    (0..rows * columns)
        .map(|index| {
            let row = index / columns;
            let column = index % columns;
            match variant {
                "identity_like" => {
                    if column == 0 {
                        1.0
                    } else {
                        0.0
                    }
                }
                "decay" => {
                    if column == 0 {
                        2.0_f64.powi(-(row as i32))
                    } else {
                        0.0
                    }
                }
                "uniform" => 1.0,
                "decay_coupled" => {
                    let victim = 2.0_f64.powi(-(row as i32));
                    if column == 0 { victim } else { 0.1 * victim }
                }
                _ => panic!("unknown matrix variant: {variant}"),
            }
        })
        .collect()
}

#[allow(clippy::too_many_arguments)]
fn run_probe(
    dll: &Path,
    ami: &Path,
    expected: DllSha256V1,
    mode: &str,
    matrix_variant: &str,
    wave_length: usize,
    clock_capacity: usize,
    rows: usize,
    aggressors: usize,
) -> serde_json::Value {
    let host = match AmiHostV1::open(dll, expected) {
        Ok(host) => host,
        Err(error) => return serde_json::json!({ "phase": "open", "error": format!("{error}") }),
    };
    let matrix = fixed_matrix(matrix_variant, rows, aggressors);
    let request = AmiInitRequestV1::try_new(matrix, rows, aggressors, 1.0e-12, 31.25e-12)
        .expect("init request");
    let limits = match ParseLimitsV1::try_new(65536, 16, 1024, 4096) {
        Ok(limits) => limits,
        Err(error) => {
            return serde_json::json!({ "phase": "limits", "error": format!("{error:?}") });
        }
    };
    let ami_bytes = match std::fs::read(ami) {
        Ok(bytes) => bytes,
        Err(error) => {
            return serde_json::json!({ "phase": "ami_read", "error": format!("{error}") });
        }
    };
    let binding = match parse_and_bind_v1(&ami_bytes, limits) {
        Ok(binding) => binding,
        Err(error) => {
            return serde_json::json!({ "phase": "ami_binding", "error": format!("{error:?}") });
        }
    };
    let mut instance = match host.initialize(request, &binding, limits) {
        Ok(instance) => instance,
        Err(error) => {
            return serde_json::json!({ "phase": "init", "error": format!("{error}") });
        }
    };
    if mode == "init" {
        let close_status = instance
            .close()
            .map(|_| "ok".to_string())
            .unwrap_or_else(|e| format!("{e}"));
        return serde_json::json!({
            "phase": "init_only",
            "init": "ok",
            "close": close_status,
        });
    }
    let mut probes = Vec::new();
    let count = if mode == "multi" { 3 } else { 1 };
    for _ in 0..count {
        let waveform: Vec<f64> = (0..wave_length)
            .map(|index| if index % 2 == 0 { 1.0 } else { -1.0 })
            .collect();
        let get_wave_request = AmiGetWaveRequestV1::try_new(waveform.clone(), clock_capacity)
            .expect("get wave request");
        let probe = match instance.get_wave(get_wave_request) {
            Ok(result) => serde_json::json!({
                "input_waveform_hash": sha256_f64(&waveform),
                "output_waveform_hash": sha256_f64(result.waveform()),
                "output_waveform_len": result.waveform().len(),
                "clocks_hash": sha256_f64(result.clocks_s()),
                "clocks_len": result.clocks_s().len(),
                "error": null,
            }),
            Err(error) => serde_json::json!({ "error": format!("{error}") }),
        };
        probes.push(probe);
    }
    let close_status = instance
        .close()
        .map(|_| "ok".to_string())
        .unwrap_or_else(|e| format!("{e}"));
    serde_json::json!({
        "phase": "get_wave",
        "probe_count": count,
        "probes": probes,
        "close": close_status,
    })
}

fn main() {
    let mut dll = None;
    let mut ami = None;
    let mut expected = None;
    let mut mode = "single".to_string();
    let mut matrix_variant = "identity_like".to_string();
    let mut wave_length = 1024usize;
    let mut clock_capacity = 1024usize;
    let mut rows = 1usize;
    let mut aggressors = 0usize;
    let mut report = None;
    let mut args = std::env::args().skip(1);
    while let Some(argument) = args.next() {
        let mut value = || args.next().expect("argument value");
        match argument.as_str() {
            "--dll" => dll = Some(PathBuf::from(value())),
            "--ami" => ami = Some(PathBuf::from(value())),
            "--expected-sha256" => expected = Some(value()),
            "--mode" => mode = value(),
            "--matrix-variant" => matrix_variant = value(),
            "--wave-length" => wave_length = value().parse().expect("wave length"),
            "--clock-capacity" => clock_capacity = value().parse().expect("clock capacity"),
            "--rows" => rows = value().parse().expect("rows"),
            "--aggressors" => aggressors = value().parse().expect("aggressors"),
            "--report" => report = Some(PathBuf::from(value())),
            other => panic!("unknown argument: {other}"),
        }
    }
    let dll = dll.expect("--dll required");
    let ami = ami.expect("--ami required");
    let expected = expected.expect("--expected-sha256 required");
    let expected_bytes: [u8; 32] = hex_to_bytes(&expected).try_into().expect("32 bytes");
    let result = run_probe(
        &dll,
        &ami,
        DllSha256V1::from_bytes(expected_bytes),
        &mode,
        &matrix_variant,
        wave_length,
        clock_capacity,
        rows,
        aggressors,
    );
    let report_json = serde_json::json!({
        "dll_sha256": expected.to_lowercase(),
        "ami_sha256": sha256_hex(&std::fs::read(&ami).expect("ami read")),
        "mode": mode,
        "matrix_variant": matrix_variant,
        "wave_length": wave_length,
        "clock_capacity": clock_capacity,
        "rows": rows,
        "aggressors": aggressors,
        "probe": result,
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
