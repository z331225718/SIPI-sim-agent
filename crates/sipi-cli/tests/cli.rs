use std::{
    io::Write,
    path::Path,
    process::{Command, Output, Stdio},
};

fn sipi() -> Command {
    Command::new(env!("CARGO_BIN_EXE_sipi"))
}

const RC_PULSE_REQUEST: &[u8] = br#"{"schema":"sipi.tran.rc-pulse-request.v1","request_id":"rc-pulse-1","resistance_ohms":1000.0,"capacitance_farads":0.000001,"initial_voltage_out_volts":0.0,"output_times_seconds":[0.0,0.000001,0.000002,0.000003],"pulse":{"voltage_low_volts":0.0,"voltage_high_volts":1.0,"delay_seconds":0.000001,"rise_seconds":0.000000001,"fall_seconds":0.000000001,"width_seconds":0.00001,"period_seconds":0.00002}}"#;
const LINK_REQUEST: &[u8] = br#"{"schema":"sipi.link.causal-fir-request.v1","request_id":"link-1","plan":{"schema":"sipi.link-plan.v1","timebase":{"start_seconds":0.0,"sample_interval_seconds":1.0,"sample_count":2},"tx":{"kind":"direct_launch"},"stimulus_volts":[1.0,2.0],"channel":{"kind":"causal_fir","sample_interval_seconds":1.0,"gain_v_per_v":[3.0,4.0]},"rx":{"ctle":{"kind":"bypass"},"ffe":{"kind":"bypass"}}},"limits":{"max_output_samples":8,"max_multiply_accumulates":8}}"#;

fn run_fixed_tran(root: &Path) -> Output {
    let mut child = sipi()
        .args([
            "tran",
            "run",
            "--stdin",
            "--artifact-root",
            root.to_string_lossy().as_ref(),
            "--artifact-id",
            "rc-pulse-1",
        ])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .expect("start sipi");
    child
        .stdin
        .take()
        .expect("stdin")
        .write_all(RC_PULSE_REQUEST)
        .expect("write request");
    child.wait_with_output().expect("wait sipi")
}

fn run_link(root: &Path, request: &[u8]) -> Output {
    let mut child = sipi()
        .args([
            "link",
            "run",
            "--stdin",
            "--artifact-root",
            root.to_string_lossy().as_ref(),
            "--artifact-id",
            "link-1",
        ])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .expect("start sipi");
    child
        .stdin
        .take()
        .expect("stdin")
        .write_all(request)
        .expect("write request");
    child.wait_with_output().expect("wait sipi")
}

#[test]
fn capabilities_are_machine_readable_and_uncertified() {
    let output = sipi()
        .args(["capabilities", "--json"])
        .output()
        .expect("run sipi capabilities");

    assert!(output.status.success());
    assert_eq!(
        String::from_utf8(output.stdout).expect("UTF-8 stdout"),
        "{\"schema\":\"sipi.cli.response.v1\",\"protocol\":1,\"command\":\"capabilities\",\"request_id\":null,\"status\":\"ok\",\"result\":{\"schema\":\"sipi.capabilities.v1\",\"product\":{\"name\":\"sipi\",\"version\":\"0.1.0\"},\"platform\":{\"target\":\"x86_64-pc-windows-msvc\",\"certification\":\"uncertified\"},\"capabilities\":[{\"domain\":\"tran\",\"status\":\"limited\",\"reason\":\"fixed_rc_pulse_profile_only\"},{\"domain\":\"channel\",\"status\":\"limited\",\"reason\":\"causal_fir_link_only\"},{\"domain\":\"ibis-ami\",\"status\":\"unsupported\",\"reason\":\"not_implemented\"},{\"domain\":\"com\",\"status\":\"unsupported\",\"reason\":\"not_implemented\"}]},\"diagnostic_count\":0}\n"
    );
    assert!(output.stderr.is_empty());
}

#[test]
fn causal_fir_link_run_publishes_full_linear_tail() {
    let root = std::env::temp_dir().join(format!("sipi-cli-process-link-{}", std::process::id()));
    let output = run_link(&root, LINK_REQUEST);
    assert!(output.status.success());
    assert!(
        String::from_utf8(output.stdout)
            .expect("stdout")
            .contains("sipi.link.run-result.v1")
    );
    let artifact = root.join("link-1");
    assert!(artifact.join("success.json").is_file());
    assert!(artifact.join("request.json").is_file());
    assert!(artifact.join("received-waveform.json").is_file());
    let received =
        std::fs::read_to_string(artifact.join("received-waveform.json")).expect("received");
    assert!(received.contains("[3,10,8]"));
    assert_eq!(run_link(&root, LINK_REQUEST).status.code(), Some(5));
    let bad = run_link(
        &std::env::temp_dir().join(format!("sipi-cli-process-link-bad-{}", std::process::id())),
        br#"{"schema":"sipi.link.causal-fir-request.v1","request_id":"link-1","unexpected":true}"#,
    );
    assert_eq!(bad.status.code(), Some(3));
    let _ = std::fs::remove_dir_all(root);
}

#[test]
fn run_is_explicitly_unsupported() {
    let output = sipi().arg("run").output().expect("run sipi run");

    assert_eq!(output.status.code(), Some(4));
    assert!(
        String::from_utf8(output.stdout)
            .unwrap()
            .contains("\"status\":\"unsupported\"")
    );
    assert_eq!(
        String::from_utf8(output.stderr).expect("UTF-8 stderr"),
        "{\"schema\":\"sipi.cli.diagnostic.v1\",\"sequence\":1,\"severity\":\"error\",\"code\":\"unsupported\",\"command\":\"run\",\"request_id\":null,\"location\":null,\"message\":\"command failed\"}\n"
    );
}

#[test]
fn stdin_validation_is_noninteractive_and_contract_checked() {
    let valid = br#"{"schema":"sipi.validation-request.v1","request_id":"request-1","subject":{"schema":"sipi.contract.v1","axis":{"encoding":"explicit","values":[0.0,1.0]},"samples":[1.0,2.0]}}"#;
    let mut child = sipi()
        .args(["validate", "--stdin"])
        .stdin(std::process::Stdio::piped())
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .spawn()
        .expect("start sipi");
    child
        .stdin
        .take()
        .expect("stdin")
        .write_all(valid)
        .expect("write request");
    let output = child.wait_with_output().expect("wait sipi");
    assert!(output.status.success());
    assert!(
        String::from_utf8(output.stdout)
            .expect("UTF-8 stdout")
            .contains("\"command\":\"validate\"")
    );
    assert!(output.stderr.is_empty());
}

#[test]
fn fixed_tran_stdin_run_publishes_a_two_file_artifact() {
    let root = std::env::temp_dir().join(format!("sipi-cli-process-tran-{}", std::process::id()));
    let output = run_fixed_tran(&root);
    assert!(output.status.success());
    assert!(
        String::from_utf8(output.stdout)
            .expect("stdout")
            .contains("sipi.tran.run-result.v1")
    );
    assert!(output.stderr.is_empty());
    assert!(root.join("rc-pulse-1").join("success.json").is_file());
    assert!(root.join("rc-pulse-1").join("result.json").is_file());
    assert!(root.join("rc-pulse-1").join("provenance.json").is_file());
    let success = std::fs::read(root.join("rc-pulse-1").join("success.json")).expect("success");
    let result = std::fs::read(root.join("rc-pulse-1").join("result.json")).expect("result");
    let provenance =
        std::fs::read(root.join("rc-pulse-1").join("provenance.json")).expect("provenance");

    let duplicate = run_fixed_tran(&root);
    assert_eq!(duplicate.status.code(), Some(5));
    assert_eq!(
        String::from_utf8(duplicate.stdout).expect("duplicate stdout"),
        "{\"schema\":\"sipi.cli.response.v1\",\"protocol\":1,\"command\":\"tran\",\"request_id\":null,\"status\":\"failed\",\"result\":null,\"diagnostic_count\":1}\n"
    );
    assert_eq!(
        String::from_utf8(duplicate.stderr).expect("duplicate stderr"),
        "{\"schema\":\"sipi.cli.diagnostic.v1\",\"sequence\":1,\"severity\":\"error\",\"code\":\"operational_failure\",\"command\":\"tran\",\"request_id\":null,\"location\":null,\"message\":\"command failed\"}\n"
    );
    assert_eq!(
        std::fs::read(root.join("rc-pulse-1").join("success.json")).expect("success"),
        success
    );
    assert_eq!(
        std::fs::read(root.join("rc-pulse-1").join("result.json")).expect("result"),
        result
    );
    assert_eq!(
        std::fs::read(root.join("rc-pulse-1").join("provenance.json")).expect("provenance"),
        provenance
    );
    let _ = std::fs::remove_dir_all(root);
}
