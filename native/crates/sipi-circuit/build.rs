use std::env;
use std::process::Command;

fn git_output(args: &[&str]) -> Option<String> {
    let output = Command::new("git").args(args).output().ok()?;
    output
        .status
        .success()
        .then(|| String::from_utf8_lossy(&output.stdout).trim().to_owned())
        .filter(|value| !value.is_empty())
}

fn main() {
    println!("cargo:rerun-if-env-changed=AGENT_SPICE_GIT_REVISION");
    println!("cargo:rerun-if-env-changed=AGENT_SPICE_GIT_DIRTY");
    println!("cargo:rerun-if-changed=src");
    if let Some(head) = git_output(&["rev-parse", "--git-path", "HEAD"]) {
        println!("cargo:rerun-if-changed={head}");
    }
    if let Some(index) = git_output(&["rev-parse", "--git-path", "index"]) {
        println!("cargo:rerun-if-changed={index}");
    }
    if let Some(reference) = git_output(&["symbolic-ref", "-q", "HEAD"])
        && let Some(git_dir) = git_output(&["rev-parse", "--git-dir"])
    {
        println!("cargo:rerun-if-changed={git_dir}/{reference}");
    }

    let revision = env::var("AGENT_SPICE_GIT_REVISION")
        .ok()
        .or_else(|| git_output(&["rev-parse", "HEAD"]))
        .unwrap_or_else(|| "unknown".into());
    let dirty = env::var("AGENT_SPICE_GIT_DIRTY").ok().unwrap_or_else(|| {
        git_output(&["status", "--porcelain", "--untracked-files=all"])
            .map(|status| (!status.is_empty()).to_string())
            .unwrap_or_else(|| "unknown".into())
    });
    println!("cargo:rustc-env=AGENT_SPICE_GIT_REVISION={revision}");
    println!("cargo:rustc-env=AGENT_SPICE_GIT_DIRTY={dirty}");
    println!(
        "cargo:rustc-env=AGENT_SPICE_TARGET={}",
        env::var("TARGET").unwrap_or_else(|_| "unknown".into())
    );
    println!(
        "cargo:rustc-env=AGENT_SPICE_PROFILE={}",
        env::var("PROFILE").unwrap_or_else(|_| "unknown".into())
    );
}
