use std::env;
use std::fs;
use std::io::{self, Write};
use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::thread;
use std::time::Duration;

fn argument_value(arguments: &[String], flag: &str) -> Option<PathBuf> {
    let mut index = 0;
    while index < arguments.len() {
        if arguments[index] == flag {
            return arguments.get(index + 1).map(PathBuf::from);
        }
        if let Some(value) = arguments[index].strip_prefix(&format!("{flag}=")) {
            return Some(PathBuf::from(value));
        }
        index += 1;
    }
    None
}

fn create_required_file(arguments: &[String], flag: &str) {
    let path = argument_value(arguments, flag).expect("required file flag");
    if let Some(parent) = path.parent()
        && !parent.as_os_str().is_empty()
    {
        fs::create_dir_all(parent).expect("required file parent");
    }
    fs::write(path, b"required artifact\n").expect("required file");
}

fn create_required_directory(arguments: &[String], flag: &str) {
    let path = argument_value(arguments, flag).expect("required directory flag");
    fs::create_dir_all(path).expect("required directory");
}

fn create_required_artifacts(arguments: &[String]) {
    let command = arguments
        .iter()
        .find(|argument| {
            matches!(
                argument.as_str(),
                "fit-sparam"
                    | "fit-sparam-cascade"
                    | "fit-yparam"
                    | "tune-yparam-tran"
                    | "run-hspice"
                    | "run-rfm"
            )
        })
        .expect("adapter command");
    match command.as_str() {
        "fit-sparam" | "fit-yparam" => create_required_file(arguments, "--output"),
        "fit-sparam-cascade" | "run-hspice" | "run-rfm" => {
            create_required_directory(arguments, "--output-root");
        }
        "tune-yparam-tran" => {
            create_required_file(arguments, "--output-rfm");
            create_required_directory(arguments, "--work-dir");
        }
        _ => unreachable!(),
    }
}

// The parent-exit fixture intentionally leaves the live descendant to the
// adapter's Windows Job Object; the test verifies that PID is terminated.
#[allow(clippy::zombie_processes)]
fn spawn_descendant(wait: bool, child_mode: &str) {
    let pid_path = env::var("SIPI_FAKE_PID_FILE").expect("descendant pid path");
    let executable = env::current_exe().expect("fake executable");
    let mut command = Command::new(executable);
    command.env("SIPI_FAKE_MODE", child_mode);
    if child_mode == "descendant-output-child" {
        command.stderr(Stdio::null());
    } else if child_mode == "descendant-detached-child" {
        command.stdout(Stdio::null()).stderr(Stdio::null());
    }
    let mut child = command.spawn().expect("descendant spawn");
    fs::write(pid_path, child.id().to_string()).expect("pid write");
    if wait {
        let _ = child.wait();
    }
}

fn main() {
    let arguments = env::args().collect::<Vec<_>>();
    let mode = env::var("SIPI_FAKE_MODE").unwrap_or_else(|_| "success".to_owned());
    if let Ok(path) = env::var("SIPI_FAKE_CAPTURE") {
        let mut file = fs::File::create(path).expect("capture path");
        for argument in &arguments {
            writeln!(file, "{argument}").expect("capture write");
        }
    }
    match mode.as_str() {
        "sleep" => thread::sleep(Duration::from_secs(30)),
        "descendant" => spawn_descendant(true, "descendant-child"),
        "descendant-output" => spawn_descendant(true, "descendant-output-child"),
        "descendant-exit" => {
            create_required_artifacts(&arguments);
            spawn_descendant(false, "descendant-child");
        }
        "descendant-clean-exit" => {
            create_required_artifacts(&arguments);
            spawn_descendant(false, "descendant-detached-child");
        }
        "descendant-child" | "descendant-detached-child" => {
            thread::sleep(Duration::from_secs(30));
        }
        "descendant-output-child" => {
            print!("{}", "x".repeat(4096));
            io::stdout().flush().expect("descendant stdout flush");
            thread::sleep(Duration::from_secs(30));
        }
        "required-artifacts" => create_required_artifacts(&arguments),
        "tune-output-only" => create_required_file(&arguments, "--output-rfm"),
        "wrong-file-kind" => {
            create_required_directory(&arguments, "--output");
        }
        "wrong-directory-kind" => {
            create_required_file(&arguments, "--output-root");
        }
        "stdout" => {
            let count = env::var("SIPI_FAKE_COUNT")
                .ok()
                .and_then(|value| value.parse::<usize>().ok())
                .unwrap_or(8192);
            print!("{}", "x".repeat(count));
            io::stdout().flush().expect("stdout flush");
        }
        "stderr" => {
            let count = env::var("SIPI_FAKE_COUNT")
                .ok()
                .and_then(|value| value.parse::<usize>().ok())
                .unwrap_or(8192);
            eprint!("{}", "e".repeat(count));
            io::stderr().flush().expect("stderr flush");
        }
        "artifact" => {
            let path = env::var("SIPI_FAKE_ARTIFACT").expect("artifact path");
            fs::write(path, b"fixture artifact\n").expect("artifact write");
            println!("fake artifact complete");
        }
        "fail" => {
            eprintln!("fake failure");
            std::process::exit(23);
        }
        _ => println!("fake success"),
    }
}
