use sipi_pybert_adapter::{AdapterError, AdapterRequest, ProcessLimits, WorkflowInput, run};
use std::{fs, path::PathBuf, time::Duration};

fn temp_root(label: &str) -> PathBuf {
    let root = std::env::temp_dir().join(format!(
        "sipi-pybert-adapter-{label}-{}",
        std::process::id()
    ));
    let _ = fs::remove_dir_all(&root);
    fs::create_dir_all(&root).expect("temp root");
    root
}

fn executable() -> PathBuf {
    PathBuf::from(env!("CARGO_BIN_EXE_pb_fake_pybert"))
}

fn limits() -> ProcessLimits {
    ProcessLimits {
        timeout: Duration::from_secs(2),
        poll_interval: Duration::from_millis(2),
        ..ProcessLimits::default()
    }
}

#[test]
fn sim_auto_reports_actual_selected_backend_and_inventories_artifacts() {
    let root = temp_root("auto");
    let config = root.join("config.yaml");
    let output = root.join("output");
    fs::write(&config, b"config").expect("config");
    let result = run(&AdapterRequest {
        executable: executable(),
        working_directory: root.clone(),
        input: WorkflowInput::SimAuto {
            config_file: config,
            output_dir: output,
            statistical_time_points: Some(64),
        },
        limits: limits(),
        cancel_file: None,
    })
    .expect("run");
    assert_eq!(result.selected_backend.as_deref(), Some("python"));
    let selection = result.backend_selection.as_ref().expect("selection");
    assert_eq!(selection.requested.as_deref(), Some("auto"));
    assert_eq!(
        selection.fallback_reason.as_deref(),
        Some("native validation failed")
    );
    assert_eq!(result.artifacts.len(), 2);
    assert!(result.succeeded());
}

#[test]
fn sim_preserves_explicit_result_file_and_hashes_it() {
    let root = temp_root("sim-result");
    let config = root.join("config.yaml");
    let results = root.join("result.pybert_data");
    fs::write(&config, b"config").expect("config");
    let result = run(&AdapterRequest {
        executable: executable(),
        working_directory: root.clone(),
        input: WorkflowInput::Sim {
            config_file: config,
            results: Some(results),
        },
        limits: limits(),
        cancel_file: None,
    })
    .expect("run");
    assert_eq!(result.artifacts.len(), 1);
    assert_eq!(result.artifacts[0].relative_path, "result.pybert_data");
    assert_eq!(result.artifacts[0].bytes, 7);
}

#[test]
fn sim_binds_upstream_default_result_path_when_results_is_absent() {
    let root = temp_root("sim-default-result");
    let config = root.join("config.yaml");
    fs::write(&config, b"config").expect("config");
    let result = run(&AdapterRequest {
        executable: executable(),
        working_directory: root.clone(),
        input: WorkflowInput::Sim {
            config_file: config.clone(),
            results: None,
        },
        limits: limits(),
        cancel_file: None,
    })
    .expect("run");
    assert_eq!(result.artifacts.len(), 1);
    assert_eq!(result.artifacts[0].relative_path, "config.pybert_data");
    assert_eq!(result.artifacts[0].bytes, 7);
    assert!(config.with_extension("pybert_data").is_file());
}

#[test]
fn relative_paths_use_caller_working_directory_for_spawn_and_custody() {
    let root = temp_root("relative-working-directory");
    let input = root.join("input.json");
    fs::write(&input, b"{}").expect("input");
    let result = run(&AdapterRequest {
        executable: executable(),
        working_directory: root.clone(),
        input: WorkflowInput::SimNative {
            input_file: PathBuf::from("input.json"),
            output_dir: PathBuf::from("relative-output"),
        },
        limits: limits(),
        cancel_file: None,
    })
    .expect("run");
    assert!(result.succeeded());
    assert_eq!(result.artifacts.len(), 2);
    assert!(
        result
            .artifacts
            .iter()
            .any(|artifact| artifact.relative_path == "arrays.npz")
    );
    assert!(root.join("relative-output").is_dir());
    let _ = fs::remove_dir_all(root);
}

#[test]
fn required_output_target_missing_fails_closed() {
    let root = temp_root("required-output-missing");
    let result = run(&AdapterRequest {
        executable: executable(),
        working_directory: root.clone(),
        input: WorkflowInput::SimNative {
            input_file: PathBuf::from("--no-output"),
            output_dir: root.join("output"),
        },
        limits: limits(),
        cancel_file: None,
    });
    assert!(matches!(result, Err(AdapterError::RequiredArtifactMissing)));
}

#[test]
fn empty_or_unrelated_output_directory_fails_closed() {
    let root = temp_root("minimum-directory-artifacts");
    for mode in [
        "--empty-output",
        "--unrelated-output",
        "--wrong-case-output",
    ] {
        let result = run(&AdapterRequest {
            executable: executable(),
            working_directory: root.clone(),
            input: WorkflowInput::SimNative {
                input_file: PathBuf::from(mode),
                output_dir: root.join(mode.trim_start_matches('-')),
            },
            limits: limits(),
            cancel_file: None,
        });
        assert!(
            matches!(result, Err(AdapterError::RequiredArtifactMissing)),
            "{mode} must not satisfy the pinned output contract"
        );
    }
}

#[test]
fn every_directory_workflow_requires_meta_and_arrays() {
    let root = temp_root("route-minimum-artifacts");
    let cases = [
        (
            "sim-native missing meta.json",
            WorkflowInput::SimNative {
                input_file: PathBuf::from("--missing-meta"),
                output_dir: root.join("sim-native-missing-meta"),
            },
        ),
        (
            "sim-native missing arrays.npz",
            WorkflowInput::SimNative {
                input_file: PathBuf::from("--missing-arrays"),
                output_dir: root.join("sim-native-missing-arrays"),
            },
        ),
        (
            "sim-rust missing meta.json",
            WorkflowInput::SimRust {
                config_file: PathBuf::from("--missing-meta"),
                output_dir: root.join("sim-rust-missing-meta"),
                statistical_time_points: None,
            },
        ),
        (
            "sim-rust missing arrays.npz",
            WorkflowInput::SimRust {
                config_file: PathBuf::from("--missing-arrays"),
                output_dir: root.join("sim-rust-missing-arrays"),
                statistical_time_points: None,
            },
        ),
        (
            "sim-auto missing meta.json",
            WorkflowInput::SimAuto {
                config_file: PathBuf::from("--missing-meta"),
                output_dir: root.join("sim-auto-missing-meta"),
                statistical_time_points: None,
            },
        ),
        (
            "sim-auto missing arrays.npz",
            WorkflowInput::SimAuto {
                config_file: PathBuf::from("--missing-arrays"),
                output_dir: root.join("sim-auto-missing-arrays"),
                statistical_time_points: None,
            },
        ),
        (
            "sim-compare missing meta.json",
            WorkflowInput::SimCompare {
                config_file: PathBuf::from("--missing-meta"),
                output_dir: root.join("sim-compare-missing-meta"),
                statistical_time_points: None,
            },
        ),
        (
            "sim-compare missing arrays.npz",
            WorkflowInput::SimCompare {
                config_file: PathBuf::from("--missing-arrays"),
                output_dir: root.join("sim-compare-missing-arrays"),
                statistical_time_points: None,
            },
        ),
    ];
    for (label, input) in cases {
        let result = run(&AdapterRequest {
            executable: executable(),
            working_directory: root.clone(),
            input,
            limits: limits(),
            cancel_file: None,
        });
        assert!(
            matches!(result, Err(AdapterError::RequiredArtifactMissing)),
            "{label} must fail closed"
        );
    }
}

#[test]
fn sim_result_target_missing_fails_closed() {
    let root = temp_root("sim-result-missing");
    let result = run(&AdapterRequest {
        executable: executable(),
        working_directory: root.clone(),
        input: WorkflowInput::Sim {
            config_file: PathBuf::from("--no-output"),
            results: None,
        },
        limits: limits(),
        cancel_file: None,
    });
    assert!(matches!(result, Err(AdapterError::RequiredArtifactMissing)));
}

#[test]
fn preexisting_output_targets_fail_closed_before_spawn() {
    let root = temp_root("preexisting-output-targets");
    let output = root.join("output");
    fs::create_dir_all(&output).expect("stale output directory");
    fs::write(output.join("meta.json"), b"stale").expect("stale metadata");
    fs::write(output.join("arrays.npz"), b"stale").expect("stale array");
    let directory_result = run(&AdapterRequest {
        executable: executable(),
        working_directory: root.clone(),
        input: WorkflowInput::SimNative {
            input_file: PathBuf::from("input.json"),
            output_dir: output,
        },
        limits: limits(),
        cancel_file: None,
    });
    assert!(matches!(
        directory_result,
        Err(AdapterError::OutputTargetAlreadyExists)
    ));

    let result_file = root.join("result.pybert_data");
    fs::write(&result_file, b"stale").expect("stale result");
    let file_result = run(&AdapterRequest {
        executable: executable(),
        working_directory: root.clone(),
        input: WorkflowInput::Sim {
            config_file: PathBuf::from("config.yaml"),
            results: Some(result_file),
        },
        limits: limits(),
        cancel_file: None,
    });
    assert!(matches!(
        file_result,
        Err(AdapterError::OutputTargetAlreadyExists)
    ));
}

#[test]
fn artifact_directory_bound_fails_closed() {
    let root = temp_root("artifact-directory-bound");
    let result = run(&AdapterRequest {
        executable: executable(),
        working_directory: root.clone(),
        input: WorkflowInput::SimNative {
            input_file: PathBuf::from("--many-empty-dirs"),
            output_dir: root.join("output"),
        },
        limits: ProcessLimits {
            max_artifact_directories: 1,
            ..limits()
        },
        cancel_file: None,
    });
    assert!(matches!(result, Err(AdapterError::ArtifactLimitExceeded)));
}

#[cfg(windows)]
#[test]
fn nested_junction_artifact_is_rejected_before_escape_inventory() {
    let root = temp_root("nested-junction-artifact");
    let result = run(&AdapterRequest {
        executable: executable(),
        working_directory: root.clone(),
        input: WorkflowInput::SimNative {
            input_file: PathBuf::from("--nested-junction-output"),
            output_dir: root.join("output"),
        },
        limits: limits(),
        cancel_file: None,
    });
    assert!(matches!(result, Err(AdapterError::ArtifactSymlink)));
}

#[test]
fn deadline_overflow_is_rejected_before_spawn() {
    let root = temp_root("deadline-overflow");
    let result = run(&AdapterRequest {
        executable: executable(),
        working_directory: root,
        input: WorkflowInput::Sim {
            config_file: PathBuf::from("--sleep"),
            results: None,
        },
        limits: ProcessLimits {
            timeout: Duration::MAX,
            ..limits()
        },
        cancel_file: None,
    });
    assert!(matches!(result, Err(AdapterError::InvalidLimits)));
}

#[test]
fn statistical_time_points_match_pinned_click_range() {
    for value in [31, 10_001] {
        let result = sipi_pybert_adapter::command_manifest(&AdapterRequest {
            executable: executable(),
            working_directory: std::env::current_dir().expect("working directory"),
            input: WorkflowInput::SimRust {
                config_file: PathBuf::from("config.yaml"),
                output_dir: PathBuf::from("output"),
                statistical_time_points: Some(value),
            },
            limits: limits(),
            cancel_file: None,
        });
        assert!(matches!(
            result,
            Err(AdapterError::InvalidStatisticalTimePoints { actual }) if actual == value
        ));
    }
}

#[cfg(any(unix, windows))]
#[test]
fn output_target_and_ancestor_symlink_are_rejected() {
    let root = temp_root("output-symlink");
    let real = root.join("real");
    let link = root.join("link");
    fs::create_dir_all(&real).expect("real");
    #[cfg(unix)]
    let linked = std::os::unix::fs::symlink(&real, &link);
    #[cfg(windows)]
    let linked = std::os::windows::fs::symlink_dir(&real, &link);
    if linked.is_err() {
        return;
    }
    let result = sipi_pybert_adapter::command_manifest(&AdapterRequest {
        executable: executable(),
        working_directory: root.clone(),
        input: WorkflowInput::SimNative {
            input_file: root.join("input.json"),
            output_dir: link.join("nested"),
        },
        limits: limits(),
        cancel_file: None,
    });
    assert!(matches!(result, Err(AdapterError::OutputPathSymlink)));
}

#[cfg(any(unix, windows))]
#[test]
fn working_directory_must_be_a_real_non_symlink_directory() {
    let root = temp_root("working-directory-symlink");
    let real = root.join("real");
    let link = root.join("link");
    fs::create_dir_all(&real).expect("real");
    #[cfg(unix)]
    let linked = std::os::unix::fs::symlink(&real, &link);
    #[cfg(windows)]
    let linked = std::os::windows::fs::symlink_dir(&real, &link);
    if linked.is_err() {
        return;
    }
    let result = sipi_pybert_adapter::command_manifest(&AdapterRequest {
        executable: executable(),
        working_directory: link,
        input: WorkflowInput::SimNative {
            input_file: PathBuf::from("input.json"),
            output_dir: PathBuf::from("output"),
        },
        limits: limits(),
        cancel_file: None,
    });
    assert!(matches!(result, Err(AdapterError::WorkingDirectorySymlink)));
}

#[cfg(unix)]
#[test]
fn non_utf8_path_is_rejected_instead_of_lossy_manifest_conversion() {
    use std::ffi::OsString;
    use std::os::unix::ffi::OsStringExt;

    let invalid = PathBuf::from(OsString::from_vec(vec![0xff, b'c', b'f']));
    let result = sipi_pybert_adapter::command_manifest(&AdapterRequest {
        executable: executable(),
        working_directory: std::env::current_dir().expect("working directory"),
        input: WorkflowInput::Sim {
            config_file: invalid,
            results: None,
        },
        limits: limits(),
        cancel_file: None,
    });
    assert!(matches!(result, Err(AdapterError::InvalidPathEncoding)));
}

#[cfg(windows)]
#[test]
fn non_utf16_path_is_rejected_instead_of_lossy_manifest_conversion() {
    use std::ffi::OsString;
    use std::os::windows::ffi::OsStringExt;

    let invalid = PathBuf::from(OsString::from_wide(&[0xd800, b'c' as u16, b'f' as u16]));
    let result = sipi_pybert_adapter::command_manifest(&AdapterRequest {
        executable: executable(),
        working_directory: std::env::current_dir().expect("working directory"),
        input: WorkflowInput::Sim {
            config_file: invalid,
            results: None,
        },
        limits: limits(),
        cancel_file: None,
    });
    assert!(matches!(result, Err(AdapterError::InvalidPathEncoding)));
}

#[test]
fn sim_rust_and_sim_compare_use_their_named_subcommands() {
    let root = temp_root("rust-compare");
    let config = root.join("config.yaml");
    fs::write(&config, b"config").expect("config");
    for (output_name, input) in [
        (
            "rust",
            WorkflowInput::SimRust {
                config_file: config.clone(),
                output_dir: root.join("rust-output"),
                statistical_time_points: None,
            },
        ),
        (
            "compare",
            WorkflowInput::SimCompare {
                config_file: config.clone(),
                output_dir: root.join("compare-output"),
                statistical_time_points: Some(128),
            },
        ),
    ] {
        let result = run(&AdapterRequest {
            executable: executable(),
            working_directory: root.clone(),
            input,
            limits: limits(),
            cancel_file: None,
        })
        .expect("run");
        assert_eq!(result.workflow.command_name(), format!("sim-{output_name}"));
        assert!(result.exit.success);
    }
}

#[test]
fn sim_native_keeps_requested_rust_backend_explicit() {
    let root = temp_root("native");
    let input = root.join("input.json");
    let output = root.join("output");
    fs::write(&input, b"{}").expect("input");
    let result = run(&AdapterRequest {
        executable: executable(),
        working_directory: root.clone(),
        input: WorkflowInput::SimNative {
            input_file: input,
            output_dir: output,
        },
        limits: limits(),
        cancel_file: None,
    })
    .expect("run");
    assert_eq!(result.requested_backend, "rust");
    assert_eq!(result.selected_backend, None);
    assert!(result.exit.success);
}

#[test]
fn stdout_limit_fails_closed() {
    let error = run(&AdapterRequest {
        executable: executable(),
        working_directory: std::env::current_dir().expect("working directory"),
        input: WorkflowInput::Sim {
            config_file: PathBuf::from("--spam"),
            results: None,
        },
        limits: ProcessLimits {
            max_stdout_bytes: 8,
            ..limits()
        },
        cancel_file: None,
    })
    .expect_err("spam must be rejected");
    assert!(matches!(
        error,
        AdapterError::OutputLimitExceeded { stream: "stdout" }
    ));
}

#[cfg(windows)]
#[test]
fn output_limit_kills_descendant_that_holds_inherited_pipes() {
    let started = std::time::Instant::now();
    let error = run(&AdapterRequest {
        executable: executable(),
        working_directory: std::env::current_dir().expect("working directory"),
        input: WorkflowInput::Sim {
            config_file: PathBuf::from("--spam-hold-pipe"),
            results: None,
        },
        limits: ProcessLimits {
            max_stdout_bytes: 8,
            stream_drain_timeout: Duration::from_millis(100),
            ..limits()
        },
        cancel_file: None,
    })
    .expect_err("output overflow must terminate the process tree");
    assert!(matches!(
        error,
        AdapterError::OutputLimitExceeded { stream: "stdout" }
    ));
    assert!(started.elapsed() < Duration::from_secs(2));
}

#[test]
fn timeout_kills_child_and_reports_typed_error() {
    let error = run(&AdapterRequest {
        executable: executable(),
        working_directory: std::env::current_dir().expect("working directory"),
        input: WorkflowInput::Sim {
            config_file: PathBuf::from("--sleep"),
            results: None,
        },
        limits: ProcessLimits {
            timeout: Duration::from_millis(20),
            ..limits()
        },
        cancel_file: None,
    })
    .expect_err("sleep must time out");
    assert!(matches!(error, AdapterError::TimedOut));
}

#[cfg(windows)]
#[test]
fn timeout_kills_descendant_that_holds_inherited_pipes() {
    let started = std::time::Instant::now();
    let error = run(&AdapterRequest {
        executable: executable(),
        working_directory: std::env::current_dir().expect("working directory"),
        input: WorkflowInput::Sim {
            config_file: PathBuf::from("--hold-pipe"),
            results: None,
        },
        limits: ProcessLimits {
            timeout: Duration::from_millis(40),
            stream_drain_timeout: Duration::from_millis(100),
            ..limits()
        },
        cancel_file: None,
    })
    .expect_err("descendant must not keep adapter blocked");
    assert!(matches!(error, AdapterError::TimedOut));
    assert!(started.elapsed() < Duration::from_secs(2));
}

#[cfg(windows)]
#[test]
fn exited_parent_descendant_is_terminated_by_job_object() {
    fn windows_system_binary(name: &str) -> PathBuf {
        std::env::var_os("SystemRoot")
            .map(PathBuf::from)
            .filter(|path| path.is_absolute())
            .unwrap_or_else(|| PathBuf::from(r"C:\Windows"))
            .join("System32")
            .join(name)
    }

    fn process_is_running(pid: u32) -> bool {
        let output = std::process::Command::new(windows_system_binary("tasklist.exe"))
            .args(["/FI", &format!("PID eq {pid}"), "/FO", "CSV", "/NH"])
            .output()
            .expect("tasklist");
        String::from_utf8_lossy(&output.stdout).contains(&format!("\"{pid}\""))
    }

    let root = temp_root("exited-parent-job-object");
    let started = std::time::Instant::now();
    let error = run(&AdapterRequest {
        executable: executable(),
        working_directory: root.clone(),
        input: WorkflowInput::Sim {
            config_file: PathBuf::from("--exit-long-descendant"),
            results: None,
        },
        limits: ProcessLimits {
            timeout: Duration::from_secs(1),
            stream_drain_timeout: Duration::from_millis(500),
            ..limits()
        },
        cancel_file: None,
    })
    .expect_err("fixture intentionally omits the resolved result file");
    let pid: u32 = fs::read_to_string(root.join("descendant.pid"))
        .expect("descendant pid")
        .parse()
        .expect("numeric descendant pid");
    let deadline = std::time::Instant::now() + Duration::from_secs(2);
    while process_is_running(pid) && std::time::Instant::now() < deadline {
        std::thread::sleep(Duration::from_millis(20));
    }
    let survived = process_is_running(pid);
    if survived {
        let _ = std::process::Command::new(windows_system_binary("taskkill.exe"))
            .args(["/PID", &pid.to_string(), "/T", "/F"])
            .status();
    }
    assert!(matches!(error, AdapterError::RequiredArtifactMissing));
    assert!(!survived, "descendant PID {pid} survived adapter return");
    assert!(started.elapsed() < Duration::from_secs(2));
}

#[test]
fn preexisting_cancel_marker_prevents_spawn() {
    let root = temp_root("cancelled");
    let cancel = root.join("cancel");
    fs::write(&cancel, b"cancel").expect("cancel");
    let result = run(&AdapterRequest {
        executable: executable(),
        working_directory: root.clone(),
        input: WorkflowInput::Sim {
            config_file: root.join("config.yaml"),
            results: None,
        },
        limits: limits(),
        cancel_file: Some(cancel),
    });
    assert!(matches!(result, Err(AdapterError::Cancelled)));
}

#[cfg(windows)]
#[test]
fn cancellation_kills_descendant_that_holds_inherited_pipes() {
    let root = temp_root("cancel-tree");
    let cancel = root.join("cancel");
    let cancel_for_thread = cancel.clone();
    std::thread::spawn(move || {
        std::thread::sleep(Duration::from_millis(40));
        fs::write(cancel_for_thread, b"cancel").expect("cancel");
    });
    let started = std::time::Instant::now();
    let error = run(&AdapterRequest {
        executable: executable(),
        working_directory: root.clone(),
        input: WorkflowInput::Sim {
            config_file: PathBuf::from("--hold-pipe"),
            results: None,
        },
        limits: ProcessLimits {
            stream_drain_timeout: Duration::from_millis(100),
            ..limits()
        },
        cancel_file: Some(cancel),
    })
    .expect_err("cancellation must terminate the process tree");
    assert!(matches!(error, AdapterError::Cancelled));
    assert!(started.elapsed() < Duration::from_secs(2));
}

#[test]
fn auto_without_selection_is_not_claimed_successfully() {
    let root = temp_root("auto-missing");
    let config = root.join("--no-selection");
    let output = root.join("output");
    fs::write(&config, b"config").expect("config");
    let result = run(&AdapterRequest {
        executable: executable(),
        working_directory: root.clone(),
        input: WorkflowInput::SimAuto {
            config_file: config,
            output_dir: output,
            statistical_time_points: None,
        },
        limits: limits(),
        cancel_file: None,
    });
    assert!(matches!(result, Err(AdapterError::MissingAutoSelection)));
}
