//! Benchmark the existing AS-06 RFM response kernel without changing the
//! product surface. Parsing and report serialization are outside the timed
//! region so the result can be compared with the MATLAB kernel harness.

use std::hint::black_box;
use std::path::{Path, PathBuf};
use std::time::Instant;

use num_complex::Complex64;
use rayon::current_num_threads;
use serde_json::json;
use sha2::{Digest, Sha256};
use sipi_agent_spice_direct::as06_run_rfm::parse_cadence_rfm;

const DEFAULT_FREQUENCY_COUNT: usize = 262_144;
const DEFAULT_WARMUPS: usize = 3;
const DEFAULT_REPETITIONS: usize = 7;
const DEFAULT_FMAX_HZ: f64 = 200.0e9;
const MAX_FREQUENCY_COUNT: usize = 2_000_000;
const MAX_RUNS: usize = 100;

fn usage() -> ! {
    eprintln!(
        "usage: as-performance-rfm-kernel-bench --rfm FILE --output FILE \
         [--frequency-count N] [--fmax-hz HZ] [--warmups N] [--repetitions N]"
    );
    std::process::exit(2);
}

fn next_value(args: &[String], index: &mut usize, option: &str) -> String {
    *index = index.checked_add(1).unwrap_or_else(|| usage());
    args.get(*index).cloned().unwrap_or_else(|| usage_for(option))
}

fn usage_for(option: &str) -> ! {
    eprintln!("{option} requires a value");
    std::process::exit(2);
}

fn parse_usize(value: String, option: &str, minimum: usize, maximum: usize) -> usize {
    let parsed = value.parse::<usize>().unwrap_or_else(|_| {
        eprintln!("{option} must be an integer");
        std::process::exit(2);
    });
    if !(minimum..=maximum).contains(&parsed) {
        eprintln!("{option} is outside the bounded range");
        std::process::exit(2);
    }
    parsed
}

fn parse_f64(value: String, option: &str) -> f64 {
    let parsed = value.parse::<f64>().unwrap_or_else(|_| {
        eprintln!("{option} must be finite");
        std::process::exit(2);
    });
    if !parsed.is_finite() || parsed <= 0.0 {
        eprintln!("{option} must be finite and positive");
        std::process::exit(2);
    }
    parsed
}

fn sha256(path: &Path) -> String {
    let bytes = std::fs::read(path).unwrap_or_else(|error| {
        eprintln!("cannot read {}: {error}", path.display());
        std::process::exit(1);
    });
    format!("{:x}", Sha256::digest(bytes))
}

fn median(values: &[u128]) -> u128 {
    let mut sorted = values.to_vec();
    sorted.sort_unstable();
    sorted[sorted.len() / 2]
}

fn checksum(samples: &[Vec<Complex64>]) -> (f64, f64, f64, Complex64, [u64; 4]) {
    let mut real = 0.0;
    let mut imag = 0.0;
    let mut abs_squared = 0.0;
    let mut first_value = Complex64::new(0.0, 0.0);
    let mut first = [0_u64; 4];
    for (frequency_index, row) in samples.iter().enumerate() {
        for (response_index, value) in row.iter().enumerate() {
            real += value.re;
            imag += value.im;
            abs_squared += value.norm_sqr();
            if frequency_index == 0 && response_index == 0 {
                first_value = *value;
                first = [value.re.to_bits(), value.im.to_bits(), row.len() as u64, samples.len() as u64];
            }
        }
    }
    (real, imag, abs_squared, first_value, first)
}

fn main() {
    let args = std::env::args().skip(1).collect::<Vec<_>>();
    if args.iter().any(|value| value == "--help" || value == "-h") {
        usage();
    }
    let mut rfm = None::<PathBuf>;
    let mut output = None::<PathBuf>;
    let mut frequency_count = DEFAULT_FREQUENCY_COUNT;
    let mut fmax_hz = DEFAULT_FMAX_HZ;
    let mut warmups = DEFAULT_WARMUPS;
    let mut repetitions = DEFAULT_REPETITIONS;
    let mut index = 0;
    while index < args.len() {
        match args[index].as_str() {
            "--rfm" => rfm = Some(PathBuf::from(next_value(&args, &mut index, "--rfm"))),
            "--output" => output = Some(PathBuf::from(next_value(&args, &mut index, "--output"))),
            "--frequency-count" => {
                frequency_count = parse_usize(next_value(&args, &mut index, "--frequency-count"), "--frequency-count", 1, MAX_FREQUENCY_COUNT)
            }
            "--fmax-hz" => fmax_hz = parse_f64(next_value(&args, &mut index, "--fmax-hz"), "--fmax-hz"),
            "--warmups" => warmups = parse_usize(next_value(&args, &mut index, "--warmups"), "--warmups", 0, MAX_RUNS),
            "--repetitions" => repetitions = parse_usize(next_value(&args, &mut index, "--repetitions"), "--repetitions", 1, MAX_RUNS),
            other => {
                eprintln!("unknown option {other}");
                usage();
            }
        }
        index += 1;
    }
    let rfm = rfm.unwrap_or_else(|| usage_for("--rfm"));
    let output = output.unwrap_or_else(|| usage_for("--output"));
    let model = parse_cadence_rfm(&rfm).unwrap_or_else(|error| {
        eprintln!("RFM parse failed: {error}");
        std::process::exit(1);
    });
    let frequencies = if frequency_count == 1 {
        vec![0.0]
    } else {
        (0..frequency_count)
            .map(|index| fmax_hz * (index as f64) / ((frequency_count - 1) as f64))
            .collect::<Vec<_>>()
    };
    let mut warmup_checksum = None;
    for _ in 0..warmups {
        let samples = black_box(model.evaluate_s_many(black_box(&frequencies)).unwrap());
        warmup_checksum = Some(checksum(&samples));
        black_box(samples);
    }
    let mut durations_ns = Vec::with_capacity(repetitions);
    let mut final_samples = Vec::new();
    for _ in 0..repetitions {
        let started = Instant::now();
        let samples = black_box(model.evaluate_s_many(black_box(&frequencies)).unwrap());
        let elapsed = started.elapsed().as_nanos();
        durations_ns.push(elapsed);
        final_samples = samples;
    }
    let (sum_real, sum_imag, sum_abs_squared, first_value, first) = checksum(&final_samples);
    let payload = json!({
        "schema": "sipi.as-performance-rfm-kernel.v1",
        "status": "observed",
        "engine": "rust",
        "timing_scope": "evaluate_s_many_only_after_single_parse",
        "timing_clock": "std::time::Instant",
        "input": {
            "file_name": rfm.file_name().and_then(|value| value.to_str()).unwrap_or("rfm"),
            "sha256": sha256(&rfm),
            "bytes": std::fs::metadata(&rfm).map(|value| value.len()).unwrap_or(0),
            "nports": model.nports,
            "stored_poles": model.poles.len(),
            "effective_order": model.effective_order(),
        },
        "workload": {
            "frequency_count": frequency_count,
            "fmax_hz": fmax_hz,
            "response_count": model.response_count(),
            "warmup_count": warmups,
            "repetition_count": repetitions,
        },
        "durations_ns": durations_ns,
        "median_ns": median(&durations_ns),
        "checksum": {
            "sum_real": sum_real,
            "sum_imag": sum_imag,
            "sum_abs_squared": sum_abs_squared,
            "first_re": first_value.re,
            "first_im": first_value.im,
            "first_re_bits": format!("{:016x}", first[0]),
            "first_im_bits": format!("{:016x}", first[1]),
            "response_count": first[2],
            "frequency_count": first[3],
        },
        "warmup_completed": warmup_checksum.is_some() || warmups == 0,
        "execution": {
            "rayon_threads": current_num_threads(),
        },
        "limitations": [
            "kernel-only timing; RFM parse, process launch, filesystem and JSON serialization are excluded",
            "same mathematical pole/residue evaluator is compared; this is not a MATLAB SPICE solver comparison",
            "no performance acceptance threshold is asserted by this observation",
        ],
    });
    if let Some(parent) = output.parent() {
        std::fs::create_dir_all(parent).unwrap_or_else(|error| {
            eprintln!("cannot create {}: {error}", parent.display());
            std::process::exit(1);
        });
    }
    std::fs::write(&output, serde_json::to_vec_pretty(&payload).unwrap()).unwrap_or_else(|error| {
        eprintln!("cannot write {}: {error}", output.display());
        std::process::exit(1);
    });
    println!("{}", serde_json::to_string(&payload).unwrap());
}
