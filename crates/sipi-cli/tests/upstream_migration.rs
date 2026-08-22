use std::{
    fs,
    io::Write,
    path::PathBuf,
    process::{Command, Output, Stdio},
    time::{SystemTime, UNIX_EPOCH},
};

fn root(label: &str) -> PathBuf {
    let nonce = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .expect("clock")
        .as_nanos();
    let root = std::env::temp_dir().join(format!("sipi-upstream-cli-{label}-{nonce}"));
    fs::create_dir_all(&root).expect("root");
    root
}

fn fake() -> PathBuf {
    option_env!("CARGO_BIN_EXE_sipi-upstream-fake")
        .map(PathBuf::from)
        .unwrap_or_else(|| {
            let mut path = std::env::current_exe().expect("test executable");
            path.pop();
            path.join("sipi-upstream-fake.exe")
        })
}

fn run(route: &[&str], request: serde_json::Value) -> Output {
    let mut child = Command::new(env!("CARGO_BIN_EXE_sipi"))
        .args(route)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .expect("sipi");
    child
        .stdin
        .take()
        .expect("stdin")
        .write_all(request.to_string().as_bytes())
        .expect("request");
    child.wait_with_output().expect("output")
}

fn envelope(output: &Output) -> String {
    String::from_utf8(output.stdout.clone()).expect("UTF-8 envelope")
}

fn base(root: &PathBuf, workflow: &str, backend: &str) -> serde_json::Value {
    let backend = if backend == "null" {
        serde_json::Value::Null
    } else {
        serde_json::json!(backend)
    };
    serde_json::json!({
        "schema": "sipi.upstream-migration-request.v1",
        "workflow": workflow,
        "working_directory": root,
        "artifact_root": root,
        "backend": backend,
    })
}

#[test]
fn manifest_has_fifteen_external_migration_routes() {
    let output = Command::new(env!("CARGO_BIN_EXE_sipi"))
        .args(["commands", "--json"])
        .output()
        .expect("commands");
    assert!(output.status.success());
    let value: serde_json::Value = serde_json::from_slice(&output.stdout).expect("manifest JSON");
    let commands = value["result"]["commands"]
        .as_array()
        .expect("commands array");
    let external = commands
        .iter()
        .filter(|command| command["transport"] == "external_migration_adapter")
        .collect::<Vec<_>>();
    assert_eq!(external.len(), 15);
    assert!(external.iter().all(|command| {
        command["request_schema"] == "sipi.upstream-migration-request.v1"
            && command["nonclaim"]
                == "external_upstream_transport_only_no_product_capability_or_acceptance"
    }));
}

#[test]
fn schema_and_protocol_catalog_match_repository_route_shapes() {
    let schema_output = Command::new(env!("CARGO_BIN_EXE_sipi"))
        .args([
            "schema",
            "show",
            "sipi.upstream-migration-request.v1",
            "--json",
        ])
        .output()
        .expect("schema");
    assert!(schema_output.status.success());
    let schema_envelope: serde_json::Value =
        serde_json::from_slice(&schema_output.stdout).expect("schema envelope");
    assert_eq!(
        schema_envelope["result"]["oneOf"].as_array().map(Vec::len),
        Some(3)
    );

    let catalog_output = Command::new(env!("CARGO_BIN_EXE_sipi"))
        .args(["protocols", "--json"])
        .output()
        .expect("protocol catalog");
    assert!(catalog_output.status.success());
    let catalog_envelope: serde_json::Value =
        serde_json::from_slice(&catalog_output.stdout).expect("catalog envelope");
    let profiles = catalog_envelope["result"]["profiles"]
        .as_array()
        .expect("profiles");
    for (prefix, required, forbidden) in [
        (
            "upstream.agent-spice.",
            ["/interpreter", "/args"],
            "/executable",
        ),
        (
            "upstream.pybert.",
            ["/executable", "/input"],
            "/interpreter",
        ),
        (
            "upstream.agent-com.",
            ["/executable", "/interpreter"],
            "/args",
        ),
    ] {
        let matched = profiles
            .iter()
            .filter(|profile| {
                profile["command_id"]
                    .as_str()
                    .is_some_and(|id| id.starts_with(prefix))
            })
            .collect::<Vec<_>>();
        assert_eq!(
            matched.len(),
            if prefix == "upstream.agent-spice." {
                6
            } else if prefix == "upstream.pybert." {
                5
            } else {
                4
            }
        );
        assert!(matched.iter().all(|profile| {
            let bindings = profile["caller_bindings"].as_array().expect("bindings");
            required.iter().all(|pointer| {
                bindings
                    .iter()
                    .any(|binding| binding["pointer"] == *pointer)
            }) && !bindings
                .iter()
                .any(|binding| binding["pointer"] == forbidden)
        }));
    }
}

#[test]
fn unknown_upstream_workflow_fails_closed() {
    let root = root("unknown");
    let output = run(
        &["upstream", "pybert", "not-a-workflow", "--stdin"],
        base(&root, "pybert.not-a-workflow", "auto"),
    );
    assert_eq!(output.status.code(), Some(64));
    assert!(envelope(&output).contains("\"result\":null"));
    assert!(String::from_utf8_lossy(&output.stderr).contains("\"code\":\"usage\""));
    let _ = fs::remove_dir_all(root);
}

#[test]
fn agent_spice_path_is_callable_and_does_not_publish_child_payload() {
    let root = root("agent-spice");
    let mut request = base(&root, "agent-spice.fit-sparam", "null");
    request["interpreter"] = serde_json::json!(fake());
    request["args"] = serde_json::json!(["--output", "result.sp"]);
    let output = run(
        &["upstream", "agent-spice", "fit-sparam", "--stdin"],
        request,
    );
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    let body = envelope(&output);
    assert!(body.contains("sipi.upstream-migration-result.v1"));
    assert!(body.contains("external_migration_adapter"));
    assert!(body.contains("\"contract_source\""));
    assert!(body.contains("\"attestation\":\"not_performed\""));
    assert!(!body.contains("\"source\":"));
    assert!(!body.contains("fixture success"));
    assert!(output.stderr.is_empty());
    let _ = fs::remove_dir_all(root);
}

#[test]
fn agent_spice_fixture_satisfies_each_required_output_contract() {
    let root = root("agent-spice-all");
    let cases = [
        (
            "agent-spice.fit-sparam-cascade",
            serde_json::Value::Null,
            vec!["--output-root", "cascade"],
        ),
        (
            "agent-spice.fit-yparam",
            serde_json::Value::Null,
            vec!["--output", "yparam.rfm"],
        ),
        (
            "agent-spice.tune-yparam-tran",
            serde_json::Value::Null,
            vec!["--output-rfm", "tuned.rfm", "--work-dir", "tune-work"],
        ),
        (
            "agent-spice.run-hspice",
            serde_json::json!("native"),
            vec!["--backend=native", "--output-root", "hspice"],
        ),
        (
            "agent-spice.run-rfm",
            serde_json::json!("native"),
            vec!["--backend=native", "--output-root", "rfm"],
        ),
    ];
    for (workflow, backend, args) in cases {
        let mut request = base(&root, workflow, "null");
        request["backend"] = backend;
        request["interpreter"] = serde_json::json!(fake());
        request["args"] = serde_json::json!(args);
        let (_, command) = workflow.split_once('.').expect("agent-spice route");
        let output = run(&["upstream", "agent-spice", command, "--stdin"], request);
        assert!(
            output.status.success(),
            "{workflow}: {}",
            String::from_utf8_lossy(&output.stderr)
        );
    }
    let _ = fs::remove_dir_all(root);
}

#[test]
fn pybert_sim_auto_exposes_actual_backend_selection() {
    let root = root("pybert-auto");
    let config = root.join("config.yaml");
    fs::write(&config, b"fixture").expect("config");
    let mut request = base(&root, "pybert.sim-auto", "auto");
    request["executable"] = serde_json::json!(fake());
    request["artifact_root"] = serde_json::json!(root);
    request["input"] = serde_json::json!({
        "config_file": "config.yaml",
        "output_dir": "output",
        "statistical_time_points": null,
    });
    let output = run(&["upstream", "pybert", "sim-auto", "--stdin"], request);
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    let body = envelope(&output);
    assert!(body.contains("\"selected_backend\":\"python\""));
    assert!(body.contains("\"requested\":\"auto\""));
    assert!(body.contains("\"contract_source\""));
    assert!(body.contains("\"attestation\":\"not_performed\""));
    let _ = fs::remove_dir_all(root);
}

#[test]
fn agent_com_path_is_callable_with_typed_output_root() {
    let root = root("agent-com");
    let output_dir = root.join("output");
    fs::create_dir_all(&output_dir).expect("output root");
    let config = root.join("config.xlsx");
    let thru = root.join("thru.s2p");
    fs::write(&config, b"fixture").expect("config");
    fs::write(&thru, b"fixture").expect("thru");
    let mut request = base(&root, "agent-com.run", "cli");
    request["executable"] = serde_json::json!(fake());
    request["interpreter"] = serde_json::json!(fake());
    request["artifact_root"] = serde_json::json!(output_dir);
    request["input"] = serde_json::json!({
        "config": "config.xlsx",
        "thru": "thru.s2p",
        "fext": [],
        "next": [],
        "calibration_noise": null,
        "profile": null,
        "reader": null,
        "fix_ids": [],
        "overrides": [],
        "output_dir": "output",
        "overwrite": false,
        "log_file": null,
        "progress_jsonl": null,
        "diagnostics": null,
        "legacy_csv": false,
    });
    let output = run(&["upstream", "agent-com", "run", "--stdin"], request);
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    let body = envelope(&output);
    assert!(body.contains("sipi.upstream-migration-result.v1"));
    assert!(body.contains("\"contract_source\""));
    assert!(body.contains("\"attestation\":\"not_performed\""));
    let _ = fs::remove_dir_all(root);
}

#[test]
fn output_target_must_be_inside_declared_artifact_root() {
    let root = root("artifact-boundary");
    let output_dir = root.join("output");
    fs::create_dir_all(&output_dir).expect("output root");
    let config = root.join("config.yaml");
    fs::write(&config, b"fixture").expect("config");

    let mut escapes = base(&root, "pybert.sim-auto", "auto");
    escapes["executable"] = serde_json::json!(fake());
    escapes["artifact_root"] = serde_json::json!(output_dir);
    escapes["input"] = serde_json::json!({
        "config_file": "config.yaml",
        "output_dir": ".",
        "statistical_time_points": null,
    });
    let output = run(&["upstream", "pybert", "sim-auto", "--stdin"], escapes);
    assert_eq!(output.status.code(), Some(3));

    let nested = root.join("nested-artifact");
    fs::create_dir_all(&nested).expect("nested artifact root");
    let mut ancestor = base(&root, "pybert.sim-auto", "auto");
    ancestor["executable"] = serde_json::json!(fake());
    ancestor["artifact_root"] = serde_json::json!(nested);
    ancestor["input"] = serde_json::json!({
        "config_file": "config.yaml",
        "output_dir": ".",
        "statistical_time_points": null,
    });
    let output = run(&["upstream", "pybert", "sim-auto", "--stdin"], ancestor);
    assert_eq!(output.status.code(), Some(3));
    let _ = fs::remove_dir_all(root);
}

#[test]
fn external_limits_are_bounded_and_route_specific() {
    let root = root("limit-boundary");
    let mut oversized = base(&root, "agent-spice.fit-sparam", "null");
    oversized["interpreter"] = serde_json::json!(fake());
    oversized["args"] = serde_json::json!(["--output", "result.sp"]);
    oversized["limits"] = serde_json::json!({"artifact_bytes": u64::MAX});
    let output = run(
        &["upstream", "agent-spice", "fit-sparam", "--stdin"],
        oversized,
    );
    assert_eq!(output.status.code(), Some(3));

    let mut unknown = base(&root, "agent-spice.fit-sparam", "null");
    unknown["interpreter"] = serde_json::json!(fake());
    unknown["args"] = serde_json::json!(["--output", "result.sp"]);
    unknown["limits"] = serde_json::json!({"not_a_limit": 1});
    let output = run(
        &["upstream", "agent-spice", "fit-sparam", "--stdin"],
        unknown,
    );
    assert_eq!(output.status.code(), Some(3));

    let mut unsupported_cancel = base(&root, "agent-spice.fit-sparam", "null");
    unsupported_cancel["interpreter"] = serde_json::json!(fake());
    unsupported_cancel["args"] = serde_json::json!(["--output", "result.sp"]);
    unsupported_cancel["cancel_file"] = serde_json::json!("cancel.flag");
    let output = run(
        &["upstream", "agent-spice", "fit-sparam", "--stdin"],
        unsupported_cancel,
    );
    assert_eq!(output.status.code(), Some(3));

    let mut unknown_top_level = base(&root, "agent-spice.fit-sparam", "null");
    unknown_top_level["interpreter"] = serde_json::json!(fake());
    unknown_top_level["args"] = serde_json::json!(["--output", "result.sp"]);
    unknown_top_level["unknown_top"] = serde_json::json!(true);
    let output = run(
        &["upstream", "agent-spice", "fit-sparam", "--stdin"],
        unknown_top_level,
    );
    assert_eq!(output.status.code(), Some(3));

    let mut wrong_route_field = base(&root, "agent-spice.fit-sparam", "null");
    wrong_route_field["interpreter"] = serde_json::json!(fake());
    wrong_route_field["args"] = serde_json::json!(["--output", "result.sp"]);
    wrong_route_field["input"] = serde_json::json!({"config_file": "config.yaml"});
    let output = run(
        &["upstream", "agent-spice", "fit-sparam", "--stdin"],
        wrong_route_field,
    );
    assert_eq!(output.status.code(), Some(3));
    let _ = fs::remove_dir_all(root);
}

#[test]
fn compare_mismatch_is_a_typed_result_not_a_transport_failure() {
    let root = root("compare-mismatch");
    let mut request = base(&root, "agent-com.compare", "cli");
    request["executable"] = serde_json::json!(fake());
    request["interpreter"] = serde_json::json!(fake());
    request["input"] = serde_json::json!({
        "golden": "golden.json",
        "result": "mismatch",
        "atol": null,
    });
    let output = run(&["upstream", "agent-com", "compare", "--stdin"], request);
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    assert!(output.stderr.is_empty());
    let body = envelope(&output);
    assert!(body.contains("\"matched\":false"));
    assert!(body.contains("\"mismatch_count\":1"));
    assert!(body.contains("\"code\":3"));
    assert!(body.contains("\"success\":false"));
    assert!(!body.contains("external_adapter_nonzero_exit"));
    let _ = fs::remove_dir_all(root);
}

#[test]
fn compare_protocol_and_upstream_failures_remain_transport_errors() {
    let root = root("compare-failures");
    for (result, expected) in [
        ("malformed", "external_adapter_failure"),
        ("exit3-no-report", "external_adapter_failure"),
        ("exit4", "external_adapter_nonzero_exit"),
    ] {
        let mut request = base(&root, "agent-com.compare", "cli");
        request["executable"] = serde_json::json!(fake());
        request["interpreter"] = serde_json::json!(fake());
        request["input"] = serde_json::json!({
            "golden": "golden.json",
            "result": result,
            "atol": null,
        });
        let output = run(&["upstream", "agent-com", "compare", "--stdin"], request);
        assert_eq!(output.status.code(), Some(3), "{result}");
        assert!(
            String::from_utf8_lossy(&output.stderr).contains(expected),
            "{result}: {}",
            String::from_utf8_lossy(&output.stderr)
        );
        let body = String::from_utf8_lossy(&output.stdout);
        assert!(body.contains("\"status\":\"invalid\""), "{result}: {body}");
        assert!(body.contains("\"result\":null"), "{result}: {body}");
    }
    let _ = fs::remove_dir_all(root);
}

#[test]
fn nonzero_and_timeout_are_machine_diagnostics_without_child_text() {
    let root = root("diagnostics");
    let mut failure = base(&root, "agent-spice.fit-sparam", "null");
    failure["interpreter"] = serde_json::json!(fake());
    failure["args"] = serde_json::json!(["--output", "result.sp", "--fail"]);
    let output = run(
        &["upstream", "agent-spice", "fit-sparam", "--stdin"],
        failure,
    );
    assert_eq!(output.status.code(), Some(3));
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(stderr.contains("external_adapter_nonzero_exit"));
    assert!(!stderr.contains("fixture failure"));

    let mut timeout = base(&root, "agent-spice.fit-sparam", "null");
    timeout["interpreter"] = serde_json::json!(fake());
    timeout["args"] = serde_json::json!(["--output", "result.sp", "--sleep"]);
    timeout["limits"] = serde_json::json!({"timeout_millis": 20});
    let output = run(
        &["upstream", "agent-spice", "fit-sparam", "--stdin"],
        timeout,
    );
    assert_eq!(output.status.code(), Some(3));
    assert!(String::from_utf8_lossy(&output.stderr).contains("external_adapter_timeout"));
    let _ = fs::remove_dir_all(root);
}
