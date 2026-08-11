use std::{
    io::Write,
    path::Path,
    process::{Command, Output, Stdio},
};

fn sipi() -> Command {
    Command::new(env!("CARGO_BIN_EXE_sipi"))
}

const RC_PULSE_REQUEST: &[u8] = br#"{"schema":"sipi.tran.rc-pulse-request.v1","request_id":"rc-pulse-1","resistance_ohms":1000.0,"capacitance_farads":0.000001,"initial_voltage_out_volts":0.0,"output_times_seconds":[0.0,0.000001,0.000002,0.000003],"pulse":{"voltage_low_volts":0.0,"voltage_high_volts":1.0,"delay_seconds":0.000001,"rise_seconds":0.000000001,"fall_seconds":0.000000001,"width_seconds":0.00001,"period_seconds":0.00002}}"#;
const ONE_NODE_RC_PULSE_REQUEST: &[u8] = br#"{"schema":"sipi.tran.one-node-rc-pulse-request.v1","request_id":"one-node-1","resistance_ohms":1000.0,"capacitance_farads":0.000000002,"initial_voltage_out_volts":0.0,"output_times_seconds":[0.0,0.000000001,0.000000002,0.000000003],"pulse":{"voltage_low_volts":0.0,"voltage_high_volts":1.2,"delay_seconds":0.0000000005,"rise_seconds":0.0000000002,"fall_seconds":0.0000000002,"width_seconds":0.000000001,"period_seconds":0.000000004}}"#;
const LINK_REQUEST: &[u8] = br#"{"schema":"sipi.link.causal-fir-request.v1","request_id":"link-1","plan":{"schema":"sipi.link-plan.v1","timebase":{"start_seconds":0.0,"sample_interval_seconds":1.0,"sample_count":2},"tx":{"kind":"direct_launch"},"stimulus_volts":[1.0,2.0],"channel":{"kind":"causal_fir","sample_interval_seconds":1.0,"gain_v_per_v":[3.0,4.0]},"rx":{"ctle":{"kind":"bypass"},"ffe":{"kind":"bypass"}}},"limits":{"max_output_samples":8,"max_multiply_accumulates":8}}"#;
const FIXED_PROJECT_REQUEST: &[u8] = br#"{"schema":"sipi.project.fixed-tran-causal-fir-run-request.v1","plan":{"schema":"sipi.project.v1","project_id":"cli-fixed-project-1","seed_hex":"0000000000000000000000000000000000000000000000000000000000000000","resource_policy":{"timeout_millis":1000,"max_work_units":100,"max_accounted_bytes":2048},"inputs":[{"id":"binding","contract":"sipi.project.tran-rc-pulse-to-causal-fir-binding.v1"}],"nodes":[{"id":"run","kind":"project.tran-rc-pulse-to-causal-fir"}],"edges":[{"from":{"kind":"project_input","input_id":"binding"},"to":{"node_id":"run","port":"binding"},"contract":"sipi.project.tran-rc-pulse-to-causal-fir-binding.v1"}],"requested_outputs":[{"node_id":"run","port":"received","contract":"sipi.link.causal-fir-result.v1"}]},"consumer":{"sample_interval_seconds":0.000001,"gain_v_per_v":[1.0],"max_output_samples":8,"max_multiply_accumulates":16}}"#;

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

fn run_one_node_tran(root: &Path, request: &[u8]) -> Output {
    let mut child = sipi()
        .args([
            "tran",
            "one-node-rc-pulse",
            "--stdin",
            "--artifact-root",
            root.to_string_lossy().as_ref(),
            "--artifact-id",
            "one-node-1",
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

fn run_fixed_project(root: &Path, request: &[u8]) -> Output {
    let mut child = sipi()
        .args([
            "project",
            "run",
            "--stdin",
            "--artifact-root",
            root.to_string_lossy().as_ref(),
            "--artifact-id",
            "project-1",
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

fn run_artifact_report(root: &Path, artifact_id: &str) -> Output {
    let root = root.to_string_lossy().replace('\\', "\\\\");
    let request = format!(
        "{{\"schema\":\"sipi.artifact-report-request.v1\",\"artifact_root\":\"{root}\",\"artifact_id\":\"{artifact_id}\"}}"
    );
    let mut child = sipi()
        .args(["report", "inspect", "--stdin"])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .expect("start sipi");
    child
        .stdin
        .take()
        .expect("stdin")
        .write_all(request.as_bytes())
        .expect("write request");
    child.wait_with_output().expect("wait sipi")
}

fn run_with_stdin(arguments: &[&str], request: &[u8]) -> Output {
    let mut child = sipi()
        .args(arguments)
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
        "{\"schema\":\"sipi.cli.response.v1\",\"protocol\":1,\"command\":\"capabilities\",\"request_id\":null,\"status\":\"ok\",\"result\":{\"schema\":\"sipi.capabilities.v1\",\"product\":{\"name\":\"sipi\",\"version\":\"0.1.0\"},\"platform\":{\"target\":\"x86_64-pc-windows-msvc\",\"certification\":\"uncertified\"},\"capabilities\":[{\"domain\":\"tran\",\"status\":\"limited\",\"reason\":\"fixed_rc_pulse_and_one_node_rc_pulse_only\"},{\"domain\":\"channel\",\"status\":\"limited\",\"reason\":\"matched_s21_periodic_kernel_only\"},{\"domain\":\"ibis-ami\",\"status\":\"unsupported\",\"reason\":\"not_implemented\"},{\"domain\":\"com\",\"status\":\"unsupported\",\"reason\":\"not_implemented\"}]},\"diagnostic_count\":0}\n"
    );
    assert!(output.stderr.is_empty());
}

#[test]
fn protocol_catalog_and_product_examples_are_machine_readable() {
    let catalog = sipi()
        .args(["protocols", "--json"])
        .output()
        .expect("run sipi protocols");
    assert!(catalog.status.success());
    let catalog_stdout = String::from_utf8(catalog.stdout).expect("UTF-8 stdout");
    assert!(catalog_stdout.contains("sipi.command-protocol-catalog.v1"));
    assert!(catalog_stdout.contains("\"command_id\":\"tran.run\""));
    assert!(catalog_stdout.contains("\"request_schema_sha256\":\""));
    assert!(catalog.stderr.is_empty());

    for (command, request_schema) in [
        ("validate", "sipi.validation-request.v1"),
        ("ibis.inspect", "sipi.ibis.inspect.request.v1"),
        (
            "ibis.dc-evaluate",
            "sipi.ibis.input-typ-dc-evaluate.request.v1",
        ),
        (
            "ibis.quasi-static-evaluate",
            "sipi.ibis.input-typ-quasi-static-evaluate.request.v1",
        ),
        (
            "rx-load.differential-rc-evaluate",
            "sipi.rx-load.selected-differential-rc-evaluate.request.v1",
        ),
        ("tran.run", "sipi.tran.rc-pulse-request.v1"),
        (
            "tran.one-node-rc-pulse",
            "sipi.tran.one-node-rc-pulse-request.v1",
        ),
        ("link.run", "sipi.link.causal-fir-request.v1"),
        (
            "channel.run",
            "sipi.channel.matched-two-port-kernel-run-request.v1",
        ),
        ("compare.run", "sipi.compare.aligned-arrays-request.v1"),
        (
            "project.run",
            "sipi.project.fixed-tran-causal-fir-run-request.v1",
        ),
    ] {
        let example = sipi()
            .args(["example", command, "--json"])
            .output()
            .expect("run sipi example");
        assert!(example.status.success(), "{command}");
        let example_stdout = String::from_utf8(example.stdout).expect("UTF-8 stdout");
        assert!(example_stdout.contains("sipi.command-example.v1"));
        assert!(example_stdout.contains(request_schema));
        assert!(example.stderr.is_empty());
    }

    let missing_id = sipi()
        .args(["example", "--json"])
        .output()
        .expect("run incomplete sipi example");
    assert_eq!(missing_id.status.code(), Some(4));
    assert!(
        String::from_utf8(missing_id.stderr)
            .expect("UTF-8 stderr")
            .contains("example_not_applicable")
    );
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
fn fixed_project_run_publishes_only_the_admitted_composite_artifact() {
    let root = std::env::temp_dir().join(format!("sipi-cli-project-{}", std::process::id()));
    let output = run_fixed_project(&root, FIXED_PROJECT_REQUEST);
    assert!(output.status.success());
    assert!(
        String::from_utf8(output.stdout)
            .expect("stdout")
            .contains("sipi.project.fixed-tran-causal-fir-run-result.v1")
    );
    let artifact = root.join("project-1");
    for entry in [
        "success.json",
        "request.json",
        "received-waveform.json",
        "edge-record.json",
        "provenance.json",
    ] {
        assert!(artifact.join(entry).is_file(), "{entry}");
    }
    assert_eq!(
        run_fixed_project(&root, FIXED_PROJECT_REQUEST)
            .status
            .code(),
        Some(5)
    );
    let rejected = run_fixed_project(
        &std::env::temp_dir().join(format!("sipi-cli-project-bad-{}", std::process::id())),
        br#"{"schema":"sipi.project.fixed-tran-causal-fir-run-request.v1","unexpected":true}"#,
    );
    assert_eq!(rejected.status.code(), Some(3));
    let _ = std::fs::remove_dir_all(root);
}

#[test]
fn link_noise_jitter_and_missing_stages_fail_closed() {
    let request = String::from_utf8(LINK_REQUEST.to_vec()).expect("link request UTF-8");
    let rejected = [
        request.replacen("\"plan\":", "\"seed\":7,\"plan\":", 1),
        request.replacen("\"rx\":", "\"noise\":{\"kind\":\"gaussian\"},\"rx\":", 1),
        request.replacen(
            "\"sample_count\":2",
            "\"jitter\":{\"kind\":\"random\"},\"sample_count\":2",
            1,
        ),
        request.replace("\"kind\":\"direct_launch\"", "\"kind\":\"prbs\""),
        request.replacen(
            "\"ffe\":",
            "\"dfe\":{\"kind\":\"decision_feedback\"},\"ffe\":",
            1,
        ),
        request.replacen("\"ffe\":", "\"cdr\":{\"kind\":\"tracking\"},\"ffe\":", 1),
        request.replacen("\"ffe\":", "\"ber\":{\"kind\":\"measure\"},\"ffe\":", 1),
        request.replace(
            "\"ctle\":{\"kind\":\"bypass\"}",
            "\"ctle\":{\"kind\":\"peaking\"}",
        ),
    ];
    for (index, request) in rejected.iter().enumerate() {
        let root = std::env::temp_dir().join(format!(
            "sipi-cli-process-link-stage-reject-{}-{index}",
            std::process::id()
        ));
        let output = run_link(&root, request.as_bytes());
        assert_eq!(output.status.code(), Some(3), "rejected request {index}");
        assert!(!root.join("link-1").join("success.json").exists());
        let _ = std::fs::remove_dir_all(root);
    }
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
    let diagnostic = String::from_utf8(output.stderr).expect("UTF-8 stderr");
    assert!(diagnostic.contains("\"code\":\"unsupported\""));
    assert!(diagnostic.contains("\"stage\":\"protocol\""));
    assert!(diagnostic.contains("\"rule_id\":\"cli.command-shape.v1\""));
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
fn ibis_inspect_stdin_reports_structure_without_electrical_claims() {
    let request = br#"{"schema":"sipi.ibis.inspect.request.v1","source":{"encoding":"utf-8","text":"[IBIS Ver] 7.1\n[Model] rx_0\n"}}"#;
    let mut child = sipi()
        .args(["ibis", "inspect", "--stdin"])
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
    let output = child.wait_with_output().expect("wait sipi");
    assert!(output.status.success());
    let stdout = String::from_utf8(output.stdout).expect("UTF-8 stdout");
    assert!(stdout.contains("\"command\":\"ibis\""));
    assert!(stdout.contains("\"structural_parse\":\"accepted\""));
    assert!(stdout.contains("\"electrical_behavior\":\"not_evaluated\""));
    assert!(stdout.contains("\"external_profile_acceptance\":\"not_evaluated\""));
    assert!(output.stderr.is_empty());

    let rejected = sipi()
        .args(["ibis", "inspect", "--file", "sample.ibs"])
        .output()
        .expect("run rejected command");
    assert_eq!(rejected.status.code(), Some(4));
}

#[test]
fn channel_run_stdin_resolves_only_the_bounded_matched_periodic_kernel() {
    let request = br##"{"schema":"sipi.channel.matched-two-port-kernel-run-request.v1","source":{"encoding":"utf-8","text":"# Hz S RI R 50.0\n0 0 0 1 0 0 0 0 0\n1000000 0 0 1 0 0 0 0 0\n"}}"##;
    let mut child = sipi()
        .args(["channel", "run", "--stdin"])
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
    let output = child.wait_with_output().expect("wait sipi");
    assert!(output.status.success());
    let stdout = String::from_utf8(output.stdout).expect("UTF-8 stdout");
    assert!(stdout.contains("sipi.channel.matched-two-port-kernel-run-result.v1"));
    assert!(stdout.contains("\"gain_v_per_v\":[1,0]"));
    assert!(stdout.contains("\"evaluation_scope\":\"matched_s21_periodic_kernel_only\""));
    assert!(stdout.contains("\"external_profile_acceptance\":\"caller_input_unattested\""));
    assert!(output.stderr.is_empty());

    let mut rejected = sipi()
        .args(["channel", "run", "--stdin"])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .expect("start rejected sipi");
    let mut rejected_stdin = rejected.stdin.take().expect("stdin");
    rejected_stdin
        .write_all(br##"{"schema":"sipi.channel.matched-two-port-kernel-run-request.v1","source":{"encoding":"utf-8","text":"# Hz S MA R 50.0\n"}}"##)
        .expect("write rejected request");
    drop(rejected_stdin);
    let output = rejected.wait_with_output().expect("wait rejected sipi");
    assert_eq!(output.status.code(), Some(3));
    assert!(
        String::from_utf8(output.stderr)
            .expect("stderr")
            .contains("contract_rejected")
    );

    let unsupported = sipi()
        .args(["channel", "run"])
        .output()
        .expect("run incomplete channel command");
    assert_eq!(unsupported.status.code(), Some(4));
    let stdout = String::from_utf8(unsupported.stdout).expect("UTF-8 stdout");
    assert!(stdout.contains("\"status\":\"unsupported\""));
    let stderr = String::from_utf8(unsupported.stderr).expect("UTF-8 stderr");
    assert!(stderr.contains("\"code\":\"unsupported\""));
    assert!(stderr.contains("\"rule_id\":\"cli.command-shape.v1\""));
}

#[test]
fn compare_run_stdin_compares_only_caller_aligned_arrays() {
    let request = br#"{"schema":"sipi.compare.aligned-arrays-request.v1","reference":{"shape":[2],"unit":"v","semantic_binding_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","values":[0.0,2.0]},"candidate":{"shape":[2],"unit":"v","semantic_binding_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","values":[0.0,2.01]},"tolerance":{"absolute":0.001,"relative":0.001}}"#;
    let output = run_with_stdin(&["compare", "run", "--stdin"], request);
    assert!(output.status.success());
    let stdout = String::from_utf8(output.stdout).expect("UTF-8 stdout");
    assert!(stdout.contains("sipi.compare.aligned-arrays-run-result.v1"));
    assert!(stdout.contains("\"passed\":false"));
    assert!(stdout.contains("\"mismatch_count\":1"));
    assert!(stdout.contains("\"evaluation_scope\":\"caller_aligned_arrays_only\""));
    assert!(!stdout.contains("\"values\""));
    assert!(output.stderr.is_empty());

    let rejected = run_with_stdin(
        &["compare", "run", "--stdin"],
        br#"{"schema":"sipi.compare.aligned-arrays-request.v1","reference":{"shape":[1],"unit":"v","semantic_binding_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","values":[0.0],"path":"outside"},"candidate":{"shape":[1],"unit":"v","semantic_binding_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","values":[0.0]},"tolerance":{"absolute":0.0,"relative":0.0}}"#,
    );
    assert_eq!(rejected.status.code(), Some(3));
    let rejected_stdout = String::from_utf8(rejected.stdout).expect("UTF-8 stdout");
    assert!(rejected_stdout.contains("\"status\":\"invalid\""));
    assert!(!rejected_stdout.contains("outside"));
    assert!(
        String::from_utf8(rejected.stderr)
            .expect("UTF-8 stderr")
            .contains("contract_rejected")
    );

    let unsupported = sipi().args(["compare", "run"]).output().expect("run sipi");
    assert_eq!(unsupported.status.code(), Some(4));
    assert!(
        String::from_utf8(unsupported.stdout)
            .expect("UTF-8 stdout")
            .contains("\"status\":\"unsupported\"")
    );
    assert!(
        String::from_utf8(unsupported.stderr)
            .expect("UTF-8 stderr")
            .contains("\"code\":\"unsupported\"")
    );
}

#[test]
fn ibis_dc_evaluate_stdin_evaluates_only_caller_supplied_static_clamps() {
    let request = br#"{"schema":"sipi.ibis.input-typ-dc-evaluate.request.v1","source":{"encoding":"utf-8","text":"[IBIS Ver] 7.1\n[Model] product_input\nModel_type Input\nC_comp 1pF\n[GND_clamp]\n-1V -1A\n1V 1A\n[POWER_clamp]\n-1V 1A\n1V -1A\n"},"selection":{"ibis_version":"7.1","model_selector":"product_input","corner":"typical"},"probe":{"gnd_clamp_drive_volts":0.5,"power_clamp_drive_volts":0.0}}"#;
    let mut child = sipi()
        .args(["ibis", "dc-evaluate", "--stdin"])
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
    let output = child.wait_with_output().expect("wait sipi");
    assert!(output.status.success());
    let stdout = String::from_utf8(output.stdout).expect("UTF-8 stdout");
    assert!(stdout.contains("sipi.ibis.input-typ-dc-evaluate.response.v1"));
    assert!(stdout.contains("\"gnd_clamp_current_amps\":0.5"));
    assert!(stdout.contains("\"power_clamp_current_amps\":0"));
    assert!(stdout.contains("\"total_shunt_current_amps\":0.5"));
    assert!(stdout.contains("\"external_profile_acceptance\":\"caller_input_unattested\""));
    assert!(!stdout.contains("[GND_clamp]"));
    assert!(output.stderr.is_empty());

    let mut malformed = sipi()
        .args(["ibis", "dc-evaluate", "--stdin"])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .expect("start sipi");
    let mut stdin = malformed.stdin.take().expect("stdin");
    stdin
        .write_all(br#"{"schema":"sipi.ibis.input-typ-dc-evaluate.request.v1","unexpected":true}"#)
        .expect("write malformed request");
    drop(stdin);
    let output = malformed.wait_with_output().expect("wait sipi");
    assert_eq!(output.status.code(), Some(3));
    assert!(
        String::from_utf8(output.stdout)
            .expect("stdout")
            .contains("\"status\":\"invalid\"")
    );
    assert!(
        String::from_utf8(output.stderr)
            .expect("stderr")
            .contains("\"code\":\"contract_rejected\"")
    );
}

#[test]
fn ibis_quasi_static_evaluate_stdin_requires_an_explicit_slope() {
    let request = br#"{"schema":"sipi.ibis.input-typ-quasi-static-evaluate.request.v1","source":{"encoding":"utf-8","text":"[IBIS Ver] 7.1\n[Model] product_input\nModel_type Input\nC_comp 1pF\n[GND_clamp]\n-1V -1A\n1V 1A\n[POWER_clamp]\n-1V 1A\n1V -1A\n"},"selection":{"ibis_version":"7.1","model_selector":"product_input","corner":"typical"},"probe":{"gnd_clamp_drive_volts":0.5,"power_clamp_drive_volts":0.0,"sig_to_ref_slope_volts_per_second":1000000000.0}}"#;
    let mut child = sipi()
        .args(["ibis", "quasi-static-evaluate", "--stdin"])
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
    let output = child.wait_with_output().expect("wait sipi");
    assert!(output.status.success());
    let stdout = String::from_utf8(output.stdout).expect("UTF-8 stdout");
    assert!(stdout.contains("sipi.ibis.input-typ-quasi-static-evaluate.response.v1"));
    assert!(stdout.contains("\"gnd_clamp_current_amps\":0.5"));
    assert!(stdout.contains("\"power_clamp_current_amps\":0"));
    assert!(stdout.contains("\"c_comp_current_amps\":0.001"));
    assert!(stdout.contains("\"total_shunt_current_amps\":0.501"));
    assert!(stdout.contains("\"external_profile_acceptance\":\"not_evaluated\""));
    assert!(!stdout.contains("[GND_clamp]"));
    assert!(output.stderr.is_empty());

    let mut malformed = sipi()
        .args(["ibis", "quasi-static-evaluate", "--stdin"])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .expect("start sipi");
    let mut stdin = malformed.stdin.take().expect("stdin");
    stdin
        .write_all(br#"{"schema":"sipi.ibis.input-typ-quasi-static-evaluate.request.v1","unexpected":true}"#)
        .expect("write malformed request");
    drop(stdin);
    let output = malformed.wait_with_output().expect("wait sipi");
    assert_eq!(output.status.code(), Some(3));
    assert!(
        String::from_utf8(output.stderr)
            .expect("stderr")
            .contains("\"code\":\"contract_rejected\"")
    );
}

#[test]
fn selected_differential_rc_load_evaluate_requires_explicit_p_n_ref_probe() {
    let request = br#"{"schema":"sipi.rx-load.selected-differential-rc-evaluate.request.v1","probe":{"p_to_ref_volts":0.5,"n_to_ref_volts":-0.5,"p_to_ref_slope_volts_per_second":1000000000.0,"n_to_ref_slope_volts_per_second":-1000000000.0}}"#;
    let mut child = sipi()
        .args(["rx-load", "differential-rc-evaluate", "--stdin"])
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
    let output = child.wait_with_output().expect("wait sipi");
    assert!(output.status.success());
    let stdout = String::from_utf8(output.stdout).expect("UTF-8 stdout");
    assert!(stdout.contains("sipi.rx-load.selected-differential-rc-evaluate.response.v1"));
    assert!(stdout.contains("\"reference_terminal\":\"ref\""));
    assert!(stdout.contains("\"differential_resistance_ohms\":100"));
    assert!(stdout.contains("\"p_to_ref_capacitance_farads\":0.000000000001"));
    assert!(stdout.contains("\"resistor_p_to_n_current_amps\":0.01"));
    assert!(stdout.contains("\"p_capacitor_to_ref_current_amps\":0.001"));
    assert!(stdout.contains("\"n_capacitor_to_ref_current_amps\":-0.001"));
    assert!(stdout.contains("\"p_terminal_current_amps\":0.011"));
    assert!(stdout.contains("\"n_terminal_current_amps\":-0.011"));
    assert!(stdout.contains("\"ref_terminal_current_amps\":-0"));
    assert!(stdout.contains("\"current_sign\":\"positive_into_load_terminal\""));
    assert!(stdout.contains("\"external_profile_acceptance\":\"not_evaluated\""));
    assert!(output.stderr.is_empty());

    let mut malformed = sipi()
        .args(["rx-load", "differential-rc-evaluate", "--stdin"])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .expect("start sipi");
    let mut stdin = malformed.stdin.take().expect("stdin");
    stdin
        .write_all(br#"{"schema":"sipi.rx-load.selected-differential-rc-evaluate.request.v1","probe":{"p_to_ref_volts":0.0,"n_to_ref_volts":0.0,"p_to_ref_slope_volts_per_second":0.0,"n_to_ref_slope_volts_per_second":0.0,"unexpected":true}}"#)
        .expect("write malformed request");
    drop(stdin);
    let output = malformed.wait_with_output().expect("wait sipi");
    assert_eq!(output.status.code(), Some(3));
    assert!(
        String::from_utf8(output.stderr)
            .expect("stderr")
            .contains("\"code\":\"contract_rejected\"")
    );
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
    let duplicate_diagnostic = String::from_utf8(duplicate.stderr).expect("duplicate stderr");
    assert!(duplicate_diagnostic.contains("\"code\":\"operational_failure\""));
    assert!(duplicate_diagnostic.contains("\"stage\":\"runtime\""));
    assert!(duplicate_diagnostic.contains("\"rule_id\":\"runtime.execution.v1\""));
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

#[test]
fn one_node_tran_stdin_run_publishes_a_bounded_three_file_artifact() {
    let root =
        std::env::temp_dir().join(format!("sipi-cli-process-one-node-{}", std::process::id()));
    let output = run_one_node_tran(&root, ONE_NODE_RC_PULSE_REQUEST);
    assert!(output.status.success());
    let stdout = String::from_utf8(output.stdout).expect("stdout");
    assert!(stdout.contains("sipi.tran.one-node-rc-pulse-run-result.v1"));
    assert!(stdout.contains("\"file_count\":3"));
    assert!(output.stderr.is_empty());
    let artifact = root.join("one-node-1");
    assert!(artifact.join("success.json").is_file());
    assert!(artifact.join("request.json").is_file());
    assert!(artifact.join("result.json").is_file());
    assert!(artifact.join("provenance.json").is_file());
    let result = std::fs::read_to_string(artifact.join("result.json")).expect("result");
    assert!(result.contains("ideal_pulse_series_r_capacitor_to_explicit_ref"));
    assert!(result.contains("\"time_seconds\":[0,0.000000001,0.000000002,0.000000003]"));

    let duplicate = run_one_node_tran(&root, ONE_NODE_RC_PULSE_REQUEST);
    assert_eq!(duplicate.status.code(), Some(5));
    assert!(
        String::from_utf8(duplicate.stdout)
            .expect("duplicate stdout")
            .contains("\"result\":null")
    );

    let malformed = br#"{"schema":"sipi.tran.one-node-rc-pulse-request.v1","request_id":"one-node-1","resistance_ohms":1000.0,"capacitance_farads":0.000000002,"initial_voltage_out_volts":0.0,"output_times_seconds":[0.0,0.000000001],"pulse":{"voltage_low_volts":0.0,"voltage_high_volts":1.2,"delay_seconds":0.0000000005,"rise_seconds":0.0000000002,"fall_seconds":0.0000000002,"width_seconds":0.000000001,"period_seconds":0.000000004},"netlist":"rc.cir"}"#;
    let rejected = run_one_node_tran(&root, malformed);
    assert_eq!(rejected.status.code(), Some(3));
    assert!(
        String::from_utf8(rejected.stderr)
            .expect("diagnostic")
            .contains("\"code\":\"contract_rejected\"")
    );
    let _ = std::fs::remove_dir_all(root);
}

#[test]
fn one_node_tran_breakpoint_budget_fails_before_publication() {
    let root =
        std::env::temp_dir().join(format!("sipi-cli-one-node-budget-{}", std::process::id()));
    let request = br#"{"schema":"sipi.tran.one-node-rc-pulse-request.v1","request_id":"budget-1","resistance_ohms":1000.0,"capacitance_farads":0.000000002,"initial_voltage_out_volts":0.0,"output_times_seconds":[0.0,0.001],"pulse":{"voltage_low_volts":0.0,"voltage_high_volts":1.2,"delay_seconds":0.00000001,"rise_seconds":0.00000001,"fall_seconds":0.00000001,"width_seconds":0.00000001,"period_seconds":0.0000001}}"#;
    let output = run_one_node_tran(&root, request);
    assert_eq!(output.status.code(), Some(5));
    assert!(
        String::from_utf8(output.stdout)
            .expect("failure envelope")
            .contains("\"result\":null")
    );
    assert!(!root.join("one-node-1").join("success.json").exists());
    let _ = std::fs::remove_dir_all(root);
}

#[test]
fn report_inspect_projects_only_verified_artifact_metadata() {
    let root = std::env::temp_dir().join(format!("sipi-cli-process-report-{}", std::process::id()));
    assert!(run_fixed_tran(&root).status.success());
    let report = run_artifact_report(&root, "rc-pulse-1");
    assert!(report.status.success());
    let stdout = String::from_utf8(report.stdout).expect("report stdout");
    assert!(stdout.contains("\"schema\":\"sipi.artifact-report.v1\""));
    assert!(stdout.contains("\"verified\":true"));
    assert!(stdout.contains("\"integrity_lineage\":\"unavailable\""));
    assert!(!stdout.contains(root.to_string_lossy().as_ref()));
    assert!(!stdout.contains("result.json"));
    assert!(report.stderr.is_empty());

    std::fs::write(root.join("rc-pulse-1").join("result.json"), b"tampered")
        .expect("tamper payload");
    let rejected = run_artifact_report(&root, "rc-pulse-1");
    assert_eq!(rejected.status.code(), Some(5));
    let rejected_stdout = String::from_utf8(rejected.stdout).expect("failure envelope");
    assert!(rejected_stdout.contains("\"result\":null"));
    assert!(!rejected_stdout.contains("sipi.artifact-report.v1"));
    let diagnostic = String::from_utf8(rejected.stderr).expect("diagnostic");
    assert!(diagnostic.contains("\"code\":\"operational_failure\""));
    assert!(diagnostic.contains("\"stage\":\"runtime\""));
    let _ = std::fs::remove_dir_all(root);
}
