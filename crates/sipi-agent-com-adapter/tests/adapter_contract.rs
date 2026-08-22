use sipi_agent_com_adapter::{
    AdapterConfig, AdapterError, AdapterLimits, AgentComAdapter, BackendCommand, CancellationToken,
    CompareRequest, ConfigValidateRequest, PublicWorkflowRequest, RunRequest,
};
use std::collections::BTreeMap;
#[cfg(windows)]
use std::ffi::OsString;
use std::fs;
use std::path::PathBuf;
#[cfg(windows)]
use std::process::{Command, Stdio};
use std::time::Duration;
#[cfg(windows)]
use std::time::Instant;

#[cfg(unix)]
use std::os::unix::fs::symlink;

fn adapter() -> AgentComAdapter {
    let executable = PathBuf::from(env!("CARGO_BIN_EXE_fake-com-backend"));
    AgentComAdapter::new(AdapterConfig {
        cli: BackendCommand::new(&executable),
        python: BackendCommand::new(&executable),
        working_directory: std::env::current_dir().unwrap(),
        limits: AdapterLimits {
            timeout: Duration::from_secs(2),
            max_stdout_bytes: 1024 * 1024,
            max_stderr_bytes: 1024 * 1024,
            max_stdin_bytes: 64 * 1024,
            max_artifact_bytes: 1024 * 1024,
            max_artifact_entries: 1_000,
            poll_interval: Duration::from_millis(2),
        },
        cancellation: Default::default(),
    })
    .unwrap()
}

fn temp_dir(name: &str) -> PathBuf {
    let path = std::env::temp_dir().join(format!("sipi-agent-com-{name}-{}", std::process::id()));
    let _ = fs::remove_dir_all(&path);
    fs::create_dir_all(&path).unwrap();
    path
}

#[test]
fn config_validate_transports_profile_and_overrides() {
    let report = adapter()
        .config_validate(&ConfigValidateRequest {
            config: PathBuf::from("config.xlsx"),
            profile: Some("custom".to_owned()),
            reader: Some("r480".to_owned()),
            fix_ids: vec!["fix.example".to_owned()],
            overrides: vec!["f_b=53.125".to_owned()],
            json: true,
            materialized_json: false,
        })
        .unwrap();
    assert_eq!(report.report.unwrap()["profile"], "r480");
}

#[test]
fn working_directory_owns_relative_request_and_output_paths() {
    let root = temp_dir("working-directory");
    let canonical_root = fs::canonicalize(&root).unwrap();
    let executable = PathBuf::from(env!("CARGO_BIN_EXE_fake-com-backend"));
    let adapter = AgentComAdapter::new(AdapterConfig {
        cli: BackendCommand::new(&executable),
        python: BackendCommand::new(&executable),
        working_directory: root.clone(),
        limits: AdapterLimits::default(),
        cancellation: Default::default(),
    })
    .unwrap();

    let validation = adapter
        .config_validate(&ConfigValidateRequest {
            config: PathBuf::from("inputs/config.xlsx"),
            profile: None,
            reader: None,
            fix_ids: vec![],
            overrides: vec![],
            json: true,
            materialized_json: false,
        })
        .unwrap();
    let report = validation.report.unwrap();
    assert_eq!(
        fs::canonicalize(PathBuf::from(report["working_directory"].as_str().unwrap(),)).unwrap(),
        canonical_root
    );
    assert_eq!(
        PathBuf::from(report["config"].as_str().unwrap()),
        canonical_root.join("inputs/config.xlsx")
    );

    let run = adapter
        .run(&RunRequest {
            config: PathBuf::from("inputs/config.xlsx"),
            thru: PathBuf::from("inputs/thru.s4p"),
            fext: vec![],
            next: vec![],
            calibration_noise: None,
            profile: None,
            reader: None,
            fix_ids: vec![],
            overrides: vec![],
            output_dir: PathBuf::from("artifacts"),
            overwrite: false,
            log_file: Some(PathBuf::from("artifacts/com.log")),
            progress_jsonl: Some(PathBuf::from("artifacts/progress.jsonl")),
            diagnostics: None,
            legacy_csv: false,
        })
        .unwrap();
    assert_eq!(run.artifacts.output_dir, canonical_root.join("artifacts"));
    assert!(canonical_root.join("artifacts/result.json").is_file());
    let _ = fs::remove_dir_all(root);
}

#[test]
fn designated_log_and_progress_outputs_cannot_escape_output_dir() {
    let root = temp_dir("designated-output-containment");
    let executable = PathBuf::from(env!("CARGO_BIN_EXE_fake-com-backend"));
    let adapter = AgentComAdapter::new(AdapterConfig {
        cli: BackendCommand::new(&executable),
        python: BackendCommand::new(&executable),
        working_directory: root.clone(),
        limits: AdapterLimits::default(),
        cancellation: Default::default(),
    })
    .unwrap();
    for (log_file, progress_jsonl) in [
        (Some(PathBuf::from("outside.log")), None),
        (None, Some(PathBuf::from("../outside.jsonl"))),
    ] {
        let result = adapter.run(&RunRequest {
            config: PathBuf::from("config.xlsx"),
            thru: PathBuf::from("thru.s4p"),
            fext: vec![],
            next: vec![],
            calibration_noise: None,
            profile: None,
            reader: None,
            fix_ids: vec![],
            overrides: vec![],
            output_dir: PathBuf::from("out"),
            overwrite: false,
            log_file,
            progress_jsonl,
            diagnostics: None,
            legacy_csv: false,
        });
        assert!(matches!(result, Err(AdapterError::InvalidRequest(_))));
        assert!(!root.join("out").exists());
    }
    let _ = fs::remove_dir_all(root);
}

#[test]
fn working_directory_must_be_an_existing_directory() {
    let root = temp_dir("working-directory-invalid");
    let executable = PathBuf::from(env!("CARGO_BIN_EXE_fake-com-backend"));
    let missing = AgentComAdapter::new(AdapterConfig {
        cli: BackendCommand::new(&executable),
        python: BackendCommand::new(&executable),
        working_directory: root.join("missing"),
        limits: AdapterLimits::default(),
        cancellation: Default::default(),
    });
    assert!(matches!(missing, Err(AdapterError::Artifact { .. })));

    let file = root.join("file");
    fs::write(&file, b"not a directory").unwrap();
    let regular_file = AgentComAdapter::new(AdapterConfig {
        cli: BackendCommand::new(&executable),
        python: BackendCommand::new(&executable),
        working_directory: file,
        limits: AdapterLimits::default(),
        cancellation: Default::default(),
    });
    assert!(matches!(regular_file, Err(AdapterError::Artifact { .. })));
    let _ = fs::remove_dir_all(root);
}

#[cfg(unix)]
#[test]
fn working_directory_symlink_is_rejected() {
    let root = temp_dir("working-directory-symlink");
    let target = root.join("target");
    let link = root.join("link");
    fs::create_dir_all(&target).unwrap();
    symlink(&target, &link).unwrap();
    let executable = PathBuf::from(env!("CARGO_BIN_EXE_fake-com-backend"));
    let adapter = AgentComAdapter::new(AdapterConfig {
        cli: BackendCommand::new(&executable),
        python: BackendCommand::new(&executable),
        working_directory: link,
        limits: AdapterLimits::default(),
        cancellation: Default::default(),
    });
    assert!(matches!(adapter, Err(AdapterError::Artifact { .. })));
    let _ = fs::remove_dir_all(root);
}

#[test]
fn run_validates_and_bounds_artifacts() {
    let root = temp_dir("run");
    let response = adapter()
        .run(&RunRequest {
            config: root.join("config.xlsx"),
            thru: root.join("thru.s4p"),
            fext: vec![root.join("fext.s4p")],
            next: vec![],
            calibration_noise: None,
            profile: None,
            reader: None,
            fix_ids: vec![],
            overrides: vec!["N_f=10".to_owned()],
            output_dir: root.join("out"),
            overwrite: false,
            log_file: None,
            progress_jsonl: None,
            diagnostics: None,
            legacy_csv: false,
        })
        .unwrap();
    assert!(response.artifacts.result.ends_with("result.json"));
    assert!(response.artifacts.total_bytes > 0);
    let _ = fs::remove_dir_all(root);
}

#[test]
fn run_enforces_artifact_entry_limit() {
    let root = temp_dir("artifact-entry-limit");
    let executable = PathBuf::from(env!("CARGO_BIN_EXE_fake-com-backend"));
    let adapter = AgentComAdapter::new(AdapterConfig {
        cli: BackendCommand::new(&executable),
        python: BackendCommand::new(&executable),
        working_directory: root.clone(),
        limits: AdapterLimits {
            max_artifact_entries: 1,
            ..AdapterLimits::default()
        },
        cancellation: Default::default(),
    })
    .unwrap();
    let result = adapter.run(&RunRequest {
        config: PathBuf::from("config.xlsx"),
        thru: PathBuf::from("thru.s4p"),
        fext: vec![],
        next: vec![],
        calibration_noise: None,
        profile: None,
        reader: None,
        fix_ids: vec![],
        overrides: vec![],
        output_dir: PathBuf::from("out"),
        overwrite: false,
        log_file: None,
        progress_jsonl: None,
        diagnostics: None,
        legacy_csv: false,
    });
    assert!(matches!(
        result,
        Err(AdapterError::ArtifactEntryLimit { .. })
    ));
    let _ = fs::remove_dir_all(root);
}

#[test]
fn compare_returns_mismatch_as_typed_report() {
    let response = adapter()
        .compare(&CompareRequest {
            golden: PathBuf::from("golden.json"),
            result: PathBuf::from("result.json"),
            atol: None,
        })
        .unwrap();
    assert!(response.report.matched);
}

#[test]
fn public_workflow_executes_api_sequence_and_artifact_bound() {
    let root = temp_dir("api");
    let response = adapter()
        .public_workflow(&PublicWorkflowRequest {
            config: root.join("config.xlsx"),
            thru: root.join("thru.s4p"),
            fext: vec![],
            next: vec![],
            calibration_noise: None,
            profile: None,
            overrides: BTreeMap::new(),
            output_dir: root.join("out"),
            overwrite: false,
            diagnostics: false,
        })
        .unwrap();
    assert!(response.artifacts.report.ends_with("report.html"));
    let _ = fs::remove_dir_all(root);
}

#[test]
fn timeout_and_output_limit_are_fail_closed() {
    let executable = PathBuf::from(env!("CARGO_BIN_EXE_fake-com-backend"));
    let timeout_adapter = AgentComAdapter::new(AdapterConfig {
        cli: BackendCommand::new(&executable).with_fixed_args(["--sleep-ms", "200"]),
        python: BackendCommand::new(&executable),
        working_directory: std::env::current_dir().unwrap(),
        limits: AdapterLimits {
            timeout: Duration::from_millis(20),
            ..AdapterLimits::default()
        },
        cancellation: Default::default(),
    })
    .unwrap();
    let timeout = timeout_adapter.config_validate(&ConfigValidateRequest {
        config: PathBuf::from("config.xlsx"),
        profile: None,
        reader: None,
        fix_ids: vec![],
        overrides: vec![],
        json: false,
        materialized_json: false,
    });
    assert!(matches!(timeout, Err(AdapterError::Timeout { .. })));

    let output_adapter = AgentComAdapter::new(AdapterConfig {
        cli: BackendCommand::new(&executable).with_fixed_args(["--large-output"]),
        python: BackendCommand::new(&executable),
        working_directory: std::env::current_dir().unwrap(),
        limits: AdapterLimits {
            max_stdout_bytes: 1024,
            ..AdapterLimits::default()
        },
        cancellation: Default::default(),
    })
    .unwrap();
    let output = output_adapter.config_validate(&ConfigValidateRequest {
        config: PathBuf::from("config.xlsx"),
        profile: None,
        reader: None,
        fix_ids: vec![],
        overrides: vec![],
        json: false,
        materialized_json: false,
    });
    assert!(matches!(output, Err(AdapterError::OutputLimit { .. })));

    let cancellation = CancellationToken::new();
    cancellation.cancel();
    let cancelled_adapter = AgentComAdapter::new(AdapterConfig {
        cli: BackendCommand::new(&executable),
        python: BackendCommand::new(&executable),
        working_directory: std::env::current_dir().unwrap(),
        limits: AdapterLimits::default(),
        cancellation,
    })
    .unwrap();
    let cancelled = cancelled_adapter.config_validate(&ConfigValidateRequest {
        config: PathBuf::from("config.xlsx"),
        profile: None,
        reader: None,
        fix_ids: vec![],
        overrides: vec![],
        json: false,
        materialized_json: false,
    });
    assert!(matches!(cancelled, Err(AdapterError::Cancelled)));
}

#[test]
fn final_argv_budget_includes_fixed_args() {
    let executable = PathBuf::from(env!("CARGO_BIN_EXE_fake-com-backend"));
    let oversized = "x".repeat(1024 * 1024);
    let adapter = AgentComAdapter::new(AdapterConfig {
        cli: BackendCommand::new(&executable).with_fixed_args([oversized]),
        python: BackendCommand::new(&executable),
        working_directory: std::env::current_dir().unwrap(),
        limits: AdapterLimits::default(),
        cancellation: Default::default(),
    })
    .unwrap();
    let result = adapter.config_validate(&ConfigValidateRequest {
        config: PathBuf::from("config.xlsx"),
        profile: None,
        reader: None,
        fix_ids: vec![],
        overrides: vec!["override=value".to_owned()],
        json: false,
        materialized_json: false,
    });
    assert!(matches!(
        result,
        Err(AdapterError::InputLimit { stream: "argv", .. })
    ));
}

#[test]
fn final_argv_budget_includes_config_validate_and_run_args() {
    let executable = PathBuf::from(env!("CARGO_BIN_EXE_fake-com-backend"));
    let oversized = "x".repeat(1024 * 1024);
    let adapter = AgentComAdapter::new(AdapterConfig {
        cli: BackendCommand::new(&executable),
        python: BackendCommand::new(&executable),
        working_directory: std::env::current_dir().unwrap(),
        limits: AdapterLimits::default(),
        cancellation: Default::default(),
    })
    .unwrap();

    let config_validate = adapter.config_validate(&ConfigValidateRequest {
        config: PathBuf::from("config.xlsx"),
        profile: None,
        reader: None,
        fix_ids: vec![],
        overrides: vec![oversized.clone()],
        json: false,
        materialized_json: false,
    });
    assert!(matches!(
        config_validate,
        Err(AdapterError::InputLimit { stream: "argv", .. })
    ));

    let root = temp_dir("argv-run");
    let run = adapter.run(&RunRequest {
        config: root.join("config.xlsx"),
        thru: root.join("thru.s4p"),
        fext: vec![],
        next: vec![],
        calibration_noise: None,
        profile: None,
        reader: None,
        fix_ids: vec![],
        overrides: vec![oversized],
        output_dir: root.join("out"),
        overwrite: false,
        log_file: None,
        progress_jsonl: None,
        diagnostics: None,
        legacy_csv: false,
    });
    assert!(matches!(
        run,
        Err(AdapterError::InputLimit { stream: "argv", .. })
    ));
    let _ = fs::remove_dir_all(root);
}

#[cfg(unix)]
#[test]
fn output_root_symlink_is_rejected() {
    let root = temp_dir("symlink-root");
    let target = root.join("target");
    let link = root.join("link");
    fs::create_dir_all(&target).unwrap();
    symlink(&target, &link).unwrap();
    let response = adapter().run(&RunRequest {
        config: root.join("config.xlsx"),
        thru: root.join("thru.s4p"),
        fext: vec![],
        next: vec![],
        calibration_noise: None,
        profile: None,
        reader: None,
        fix_ids: vec![],
        overrides: vec![],
        output_dir: link,
        overwrite: false,
        log_file: None,
        progress_jsonl: None,
        diagnostics: None,
        legacy_csv: false,
    });
    assert!(matches!(response, Err(AdapterError::Artifact { .. })));
    let _ = fs::remove_dir_all(root);
}

#[cfg(windows)]
#[test]
fn timeout_kills_descendant_and_closes_pipes() {
    let executable = PathBuf::from(env!("CARGO_BIN_EXE_fake-com-backend"));
    let adapter = AgentComAdapter::new(AdapterConfig {
        cli: BackendCommand::new(&executable).with_fixed_args(["--spawn-holder"]),
        python: BackendCommand::new(&executable),
        working_directory: std::env::current_dir().unwrap(),
        limits: AdapterLimits {
            timeout: Duration::from_millis(100),
            ..AdapterLimits::default()
        },
        cancellation: Default::default(),
    })
    .unwrap();
    let started = Instant::now();
    let result = adapter.config_validate(&ConfigValidateRequest {
        config: PathBuf::from("config.xlsx"),
        profile: None,
        reader: None,
        fix_ids: vec![],
        overrides: vec![],
        json: false,
        materialized_json: false,
    });
    assert!(matches!(result, Err(AdapterError::Timeout { .. })));
    assert!(started.elapsed() < Duration::from_secs(6));
}

#[cfg(windows)]
#[test]
fn parent_exit_drains_job_and_terminates_pipe_holding_descendant() {
    let root = temp_dir("parent-exit-job-drain");
    let pid_file = root.join("holder.pid");
    let executable = PathBuf::from(env!("CARGO_BIN_EXE_fake-com-backend"));
    let adapter = AgentComAdapter::new(AdapterConfig {
        cli: BackendCommand::new(&executable).with_fixed_args(vec![
            OsString::from("--spawn-holder-exit"),
            OsString::from("--holder-pid-file"),
            pid_file.as_os_str().to_owned(),
        ]),
        python: BackendCommand::new(&executable),
        working_directory: root.clone(),
        limits: AdapterLimits {
            timeout: Duration::from_secs(2),
            ..AdapterLimits::default()
        },
        cancellation: Default::default(),
    })
    .unwrap();
    let started = Instant::now();
    let result = adapter
        .config_validate(&ConfigValidateRequest {
            config: PathBuf::from("config.xlsx"),
            profile: None,
            reader: None,
            fix_ids: vec![],
            overrides: vec![],
            json: false,
            materialized_json: false,
        })
        .unwrap();
    assert_eq!(result.exit_code, 0);
    assert!(started.elapsed() < Duration::from_secs(6));
    let holder_pid = fs::read_to_string(&pid_file)
        .unwrap()
        .parse::<u32>()
        .unwrap();
    assert!(process_has_exited(holder_pid));
    let _ = fs::remove_dir_all(root);
}

#[cfg(windows)]
fn process_has_exited(pid: u32) -> bool {
    Command::new("powershell.exe")
        .args([
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "if (Get-Process -Id $args[0] -ErrorAction SilentlyContinue) { exit 1 } else { exit 0 }",
        ])
        .arg(pid.to_string())
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .is_ok_and(|status| status.success())
}
