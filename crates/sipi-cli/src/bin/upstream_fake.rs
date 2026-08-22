#![forbid(unsafe_code)]

//! Test-only process fixture for the CLI external migration routes.
//! It has no upstream numerical behavior and is not a product capability.

use std::{env, fs, path::PathBuf, thread, time::Duration};

fn main() {
    let args = env::args().collect::<Vec<_>>();
    if args.iter().any(|arg| arg == "--sleep") {
        thread::sleep(Duration::from_secs(30));
    }
    if args.iter().any(|arg| arg == "--fail") {
        eprintln!("fixture failure");
        std::process::exit(23);
    }

    if args.iter().any(|arg| {
        arg == "fit-sparam"
            || arg == "fit-yparam"
            || arg == "FitSparamRequest"
            || arg == "FitYparamRequest"
    }) {
        fs::write(option_after(&args, "--output"), b"fixture touchstone").expect("output file");
        println!("{{\"fixture\":true}}");
        return;
    }
    if args
        .iter()
        .any(|arg| arg == "fit-sparam-cascade" || arg == "FitSparamCascadeRequest")
    {
        fs::create_dir_all(option_after(&args, "--output-root")).expect("output root");
        println!("{{\"fixture\":true}}");
        return;
    }
    if args
        .iter()
        .any(|arg| arg == "tune-yparam-tran" || arg == "TuneYparamTranRequest")
    {
        fs::write(option_after(&args, "--output-rfm"), b"fixture rfm").expect("output rfm");
        fs::create_dir_all(option_after(&args, "--work-dir")).expect("work directory");
        println!("{{\"fixture\":true}}");
        return;
    }
    if args.iter().any(|arg| {
        arg == "run-hspice"
            || arg == "run-rfm"
            || arg == "RunHspiceRequest"
            || arg == "RunRfmRequest"
    }) {
        fs::create_dir_all(option_after(&args, "--output-root")).expect("output root");
        println!("{{\"fixture\":true}}");
        return;
    }

    if args.iter().any(|arg| arg == "sim-auto") {
        let output = option_after(&args, "--output-dir");
        fs::create_dir_all(&output).expect("output directory");
        fs::write(
            output.join("meta.json"),
            br#"{"diagnostics":{"engine_selection":{"requested":"auto","selected":"python","fallback_reason":"fixture fallback"}}}"#,
        )
        .expect("metadata");
        fs::write(output.join("arrays.npz"), b"fixture").expect("arrays");
        return;
    }
    if args
        .iter()
        .any(|arg| arg == "sim-native" || arg == "sim-rust" || arg == "sim-compare")
    {
        let output = option_after(&args, "--output-dir");
        fs::create_dir_all(&output).expect("output directory");
        fs::write(output.join("arrays.npz"), b"fixture").expect("arrays");
        return;
    }
    if args.iter().any(|arg| arg == "run") && args.iter().any(|arg| arg == "--output-dir") {
        let output = option_after(&args, "--output-dir");
        fs::create_dir_all(&output).expect("output directory");
        fs::write(output.join("report.html"), b"fixture report").expect("report");
        fs::write(output.join("result.json"), b"{}").expect("result");
        println!(
            "{}",
            serde_json::json!({
                "report": output.join("report.html"),
                "result": output.join("result.json"),
                "diagnostics": null,
            })
        );
        return;
    }
    if args.iter().any(|arg| arg == "compare") {
        if args.iter().any(|arg| arg.contains("malformed")) {
            println!("not-json");
            std::process::exit(3);
        }
        if args.iter().any(|arg| arg.contains("exit3-no-report")) {
            eprintln!("fixture compare failure");
            std::process::exit(3);
        }
        if args.iter().any(|arg| arg.contains("exit4")) {
            eprintln!("fixture input failure");
            std::process::exit(4);
        }
        if args.iter().any(|arg| arg.contains("mismatch")) {
            println!("{{\"matched\":false,\"mismatches\":[\"fixture\"]}}");
            std::process::exit(3);
        }
        println!("{{\"matched\":true,\"mismatches\":[]}}");
        return;
    }
    println!("{{\"fixture\":true}}");
}

fn option_after(args: &[String], name: &str) -> PathBuf {
    args.windows(2)
        .find(|window| window[0] == name)
        .map(|window| PathBuf::from(&window[1]))
        .expect("option value")
}
