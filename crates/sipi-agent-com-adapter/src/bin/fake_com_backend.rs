//! Tiny deterministic backend used only by adapter contract tests.
//! It is not an Agent-COM implementation and is never used by production.

use std::env;
use std::fs;
use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::time::Duration;

fn main() {
    if env::args().any(|arg| arg == "--holder") {
        std::thread::sleep(Duration::from_secs(30));
        return;
    }
    if env::args().any(|arg| arg == "-c") {
        let request: serde_json::Value = serde_json::from_slice(&read_stdin()).unwrap();
        let output_dir = PathBuf::from(request["output_dir"].as_str().unwrap());
        fs::create_dir_all(&output_dir).unwrap();
        fs::write(output_dir.join("result.json"), b"{}\n").unwrap();
        fs::write(output_dir.join("report.html"), b"<html></html>\n").unwrap();
        println!(
            "{}",
            serde_json::json!({
                "workflow": ["load_config", "run_com", "write_artifacts"],
                "report": output_dir.join("report.html"),
                "result": output_dir.join("result.json"),
                "diagnostics": null,
            })
        );
        return;
    }
    let args: Vec<String> = env::args().skip(1).collect();
    if args.iter().any(|arg| arg == "--spawn-holder-exit") {
        let pid_file = args
            .windows(2)
            .find(|window| window[0] == "--holder-pid-file")
            .map(|window| PathBuf::from(&window[1]))
            .unwrap();
        let executable = env::current_exe().unwrap();
        let holder = Command::new(executable)
            .arg("--holder")
            .stdin(Stdio::inherit())
            .stdout(Stdio::inherit())
            .stderr(Stdio::inherit())
            .spawn()
            .unwrap();
        fs::write(pid_file, holder.id().to_string()).unwrap();
        std::mem::forget(holder);
        return;
    }
    if args.iter().any(|arg| arg == "--spawn-holder") {
        let executable = env::current_exe().unwrap();
        let mut holder = Command::new(executable)
            .arg("--holder")
            .stdin(Stdio::inherit())
            .stdout(Stdio::inherit())
            .stderr(Stdio::inherit())
            .spawn()
            .unwrap();
        std::thread::sleep(Duration::from_secs(30));
        let _ = holder.kill();
        let _ = holder.wait();
        return;
    }
    if let Some(index) = args.iter().position(|arg| arg == "--sleep-ms") {
        let millis = args[index + 1].parse::<u64>().unwrap();
        std::thread::sleep(Duration::from_millis(millis));
        return;
    }
    if args.iter().any(|arg| arg == "--large-output") {
        println!("{}", "x".repeat(128 * 1024));
        return;
    }
    match args.first().map(String::as_str) {
        Some("config") => println!(
            "{}",
            serde_json::json!({
                "config": args.get(2),
                "working_directory": env::current_dir().unwrap(),
                "parameters": 1,
                "options": 1,
                "package_blocks": 0,
                "warnings": [],
                "profile": "r480"
            })
        ),
        Some("run") => {
            let output_dir = args
                .windows(2)
                .find(|window| window[0] == "--output-dir")
                .map(|window| PathBuf::from(&window[1]))
                .unwrap();
            fs::create_dir_all(&output_dir).unwrap();
            fs::write(output_dir.join("result.json"), b"{}\n").unwrap();
            fs::write(output_dir.join("report.html"), b"<html></html>\n").unwrap();
            println!(
                "{}",
                serde_json::json!({
                    "report": output_dir.join("report.html"),
                    "result": output_dir.join("result.json"),
                    "diagnostics": null,
                })
            );
        }
        Some("compare") => {
            if env::var_os("FAKE_COM_MISMATCH").is_some() {
                println!(
                    "{}",
                    serde_json::json!({"matched":false,"mismatches":["$.x"]})
                );
                std::process::exit(3);
            }
            println!("{}", serde_json::json!({"matched":true,"mismatches":[]}));
        }
        _ => std::process::exit(2),
    }
}

fn read_stdin() -> Vec<u8> {
    let mut bytes = Vec::new();
    std::io::Read::read_to_end(&mut std::io::stdin(), &mut bytes).unwrap();
    bytes
}
