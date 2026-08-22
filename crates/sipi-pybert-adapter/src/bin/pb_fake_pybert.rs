#![forbid(unsafe_code)]

//! Test-only process fixture. It is not part of the production adapter and
//! contains no PyBERT logic; integration tests use it for transport checks.

use std::{
    env, fs,
    path::PathBuf,
    process::{Command, Stdio},
    thread,
    time::Duration,
};

#[allow(clippy::zombie_processes)]
fn spawn_long_descendant_and_exit_parent() -> u32 {
    let executable = env::current_exe().expect("fake executable");
    Command::new(executable)
        .arg("--descendant-sleep")
        .stdin(Stdio::null())
        .stdout(Stdio::inherit())
        .stderr(Stdio::inherit())
        .spawn()
        .expect("descendant")
        .id()
}

#[cfg(windows)]
fn create_nested_junction(output: &std::path::Path) {
    let outside = env::current_dir()
        .expect("working directory")
        .join("junction-outside");
    fs::create_dir_all(&outside).expect("outside directory");
    fs::write(outside.join("external.bin"), b"outside").expect("outside artifact");
    let system_root = env::var_os("SystemRoot")
        .map(PathBuf::from)
        .filter(|path| path.is_absolute())
        .unwrap_or_else(|| PathBuf::from(r"C:\Windows"));
    let status = Command::new(system_root.join("System32").join("cmd.exe"))
        .arg("/D")
        .arg("/C")
        .arg("mklink")
        .arg("/J")
        .arg(output.join("nested-junction"))
        .arg(outside)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .expect("mklink junction");
    assert!(status.success(), "junction fixture creation failed");
}

fn main() {
    let args: Vec<String> = env::args().collect();
    if args.get(2).is_some_and(|value| value == "--sleep") {
        thread::sleep(Duration::from_millis(500));
        return;
    }
    if args.get(2).is_some_and(|value| value == "--spam") {
        print!("{}", "x".repeat(32 * 1024));
        return;
    }
    if args.get(2).is_some_and(|value| value == "--no-output") {
        return;
    }
    if args
        .get(2)
        .is_some_and(|value| value == "--many-empty-dirs")
    {
        let output = args
            .windows(2)
            .find(|window| window[0] == "--output-dir")
            .map(|window| PathBuf::from(&window[1]))
            .expect("output");
        fs::create_dir_all(output.join("nested")).expect("nested output");
        fs::write(output.join("meta.json"), b"{}").expect("metadata");
        fs::write(output.join("arrays.npz"), b"fixture").expect("array");
        return;
    }
    if args.get(2).is_some_and(|value| value == "--spam-hold-pipe") {
        let executable = env::current_exe().expect("fake executable");
        let mut descendant = Command::new(executable)
            .arg("--descendant-sleep")
            .stdin(Stdio::null())
            .stdout(Stdio::inherit())
            .stderr(Stdio::inherit())
            .spawn()
            .expect("descendant");
        print!("{}", "x".repeat(32 * 1024));
        thread::sleep(Duration::from_secs(30));
        let _ = descendant.wait();
        return;
    }
    if args.get(2).is_some_and(|value| value == "--hold-pipe") {
        let executable = env::current_exe().expect("fake executable");
        let mut descendant = Command::new(executable)
            .arg("--descendant-sleep")
            .stdin(Stdio::null())
            .stdout(Stdio::inherit())
            .stderr(Stdio::inherit())
            .spawn()
            .expect("descendant");
        thread::sleep(Duration::from_secs(30));
        let _ = descendant.wait();
        return;
    }
    if args.get(2).is_some_and(|value| value == "--exit-hold-pipe") {
        let executable = env::current_exe().expect("fake executable");
        let mut descendant = Command::new(executable)
            .arg("--descendant-short-sleep")
            .stdin(Stdio::null())
            .stdout(Stdio::inherit())
            .stderr(Stdio::inherit())
            .spawn()
            .expect("descendant");
        let _ = descendant.try_wait();
        return;
    }
    if args
        .get(2)
        .is_some_and(|value| value == "--exit-long-descendant")
    {
        let descendant_pid = spawn_long_descendant_and_exit_parent();
        fs::write("descendant.pid", descendant_pid.to_string()).expect("descendant pid");
        return;
    }
    if args
        .get(1)
        .is_some_and(|value| value == "--descendant-sleep")
    {
        thread::sleep(Duration::from_secs(30));
        return;
    }
    if args
        .get(1)
        .is_some_and(|value| value == "--descendant-short-sleep")
    {
        thread::sleep(Duration::from_millis(250));
        return;
    }
    let output = args
        .windows(2)
        .find(|window| window[0] == "--output-dir")
        .map(|window| PathBuf::from(&window[1]));
    if let Some(output) = output {
        fs::create_dir_all(&output).expect("output");
        #[cfg(windows)]
        if args
            .iter()
            .any(|value| value.ends_with("--nested-junction-output"))
        {
            fs::write(output.join("meta.json"), b"{}").expect("metadata");
            fs::write(output.join("arrays.npz"), b"fixture").expect("array");
            create_nested_junction(&output);
            return;
        }
        if args.iter().any(|value| value.ends_with("--empty-output")) {
            return;
        }
        if args
            .iter()
            .any(|value| value.ends_with("--unrelated-output"))
        {
            fs::write(output.join("unrelated.txt"), b"fixture").expect("unrelated");
            return;
        }
        if args
            .iter()
            .any(|value| value.ends_with("--wrong-case-output"))
        {
            fs::write(output.join("Meta.json"), b"{}").expect("wrong-case metadata");
            fs::write(output.join("Arrays.npz"), b"fixture").expect("wrong-case array");
            return;
        }
        let selected = if args.get(1).is_some_and(|value| value == "sim-auto") {
            "python"
        } else {
            "rust"
        };
        if !args.iter().any(|value| value.ends_with("--missing-meta")) {
            let metadata = if args.iter().any(|value| value.ends_with("--no-selection")) {
                r#"{"schema":"pybert.cli-auto-result.v1","diagnostics":{}}"#.to_owned()
            } else if selected == "python" {
                r#"{"schema":"pybert.cli-auto-result.v1","diagnostics":{"engine_selection":{"requested":"auto","selected":"python","fallback_reason":"native validation failed","parity_gate":{"status":"rejected"}}}}"#.to_owned()
            } else {
                format!(
                    r#"{{"schema":"pybert.cli-auto-result.v1","diagnostics":{{"engine_selection":{{"selected":"{}"}}}}}}"#,
                    selected
                )
            };
            fs::write(output.join("meta.json"), metadata).expect("metadata");
        }
        if !args.iter().any(|value| value.ends_with("--missing-arrays")) {
            fs::write(output.join("arrays.npz"), b"fixture").expect("array");
        }
    } else if let Some(config) = args.get(2) {
        let result = args
            .windows(2)
            .find(|window| window[0] == "--results")
            .map(|window| PathBuf::from(&window[1]))
            .unwrap_or_else(|| PathBuf::from(config).with_extension("pybert_data"));
        fs::write(result, b"fixture").expect("result");
    }
}
