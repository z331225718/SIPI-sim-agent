use sipi_agent_spice_adapter::{
    AdapterError, AgentSpiceAdapter, Backend, CancellationToken, FitSparamCascadeRequest,
    FitSparamRequest, FitYparamRequest, ProcessLimits, ProcessOptions, ProcessStatus, Request,
    RunHspiceRequest, RunRfmRequest, TuneYparamTranRequest,
};
use std::ffi::OsString;
use std::fs;
#[cfg(unix)]
use std::os::unix::ffi::OsStringExt;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::thread;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

fn temp_root(label: &str) -> PathBuf {
    let nonce = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .expect("clock")
        .as_nanos();
    let root = std::env::temp_dir().join(format!("sipi-as-adapter-{label}-{nonce}"));
    fs::create_dir_all(&root).expect("temp root");
    root
}

fn fake_options(root: &PathBuf, mode: &str) -> ProcessOptions {
    let fake = PathBuf::from(env!("CARGO_BIN_EXE_sipi-agent-spice-fake-interpreter"));
    ProcessOptions::new(&fake, root, root)
        .with_invocation_prefix(vec![OsString::from("fixture-prefix")])
        .with_environment("SIPI_FAKE_MODE", mode)
}

trait TestOptionsExt {
    fn with_environment(self, key: &str, value: &str) -> Self;
}

impl TestOptionsExt for ProcessOptions {
    fn with_environment(mut self, key: &str, value: &str) -> Self {
        self.environment
            .push((OsString::from(key), OsString::from(value)));
        self
    }
}

fn args(values: &[&str]) -> Vec<OsString> {
    values.iter().map(OsString::from).collect()
}

#[derive(Clone, Copy, Debug)]
enum RequiredOutputCase {
    FitSparam,
    FitSparamCascade,
    FitYparam,
    TuneYparamTran,
    RunHspice,
    RunRfm,
}

impl RequiredOutputCase {
    const fn label(self) -> &'static str {
        match self {
            Self::FitSparam => "fit-sparam",
            Self::FitSparamCascade => "fit-sparam-cascade",
            Self::FitYparam => "fit-yparam",
            Self::TuneYparamTran => "tune-yparam-tran",
            Self::RunHspice => "run-hspice",
            Self::RunRfm => "run-rfm",
        }
    }

    fn request(self, options: ProcessOptions) -> Request {
        match self {
            Self::FitSparam => Request::FitSparam(FitSparamRequest::new(
                args(&["input.s2p", "--output", "fit.sp"]),
                options,
            )),
            Self::FitSparamCascade => Request::FitSparamCascade(FitSparamCascadeRequest::new(
                args(&["manifest.json", "--output-root", "cascade"]),
                options,
            )),
            Self::FitYparam => Request::FitYparam(FitYparamRequest::new(
                args(&["input.s2p", "--output", "fit-y.sp"]),
                options,
            )),
            Self::TuneYparamTran => Request::TuneYparamTran(TuneYparamTranRequest::new(
                args(&[
                    "input.s2p",
                    "input.rfm",
                    "deck.sp",
                    "--output-rfm",
                    "tuned.rfm",
                    "--work-dir",
                    "tune-work",
                ]),
                options,
            )),
            Self::RunHspice => Request::RunHspice(
                RunHspiceRequest::new(
                    args(&[
                        "deck.sp",
                        "--backend",
                        "native",
                        "--output-root",
                        "hspice-run",
                    ]),
                    options,
                )
                .expect("run-hspice request"),
            ),
            Self::RunRfm => Request::RunRfm(
                RunRfmRequest::new(
                    args(&[
                        "deck.sp",
                        "--rfm",
                        "model.rfm",
                        "--backend",
                        "native",
                        "--output-root",
                        "rfm-run",
                    ]),
                    options,
                )
                .expect("run-rfm request"),
            ),
        }
    }

    fn assert_outputs(self, root: &Path) {
        match self {
            Self::FitSparam => assert!(root.join("fit.sp").is_file()),
            Self::FitSparamCascade => assert!(root.join("cascade").is_dir()),
            Self::FitYparam => assert!(root.join("fit-y.sp").is_file()),
            Self::TuneYparamTran => {
                assert!(root.join("tuned.rfm").is_file());
                assert!(root.join("tune-work").is_dir());
            }
            Self::RunHspice => assert!(root.join("hspice-run").is_dir()),
            Self::RunRfm => assert!(root.join("rfm-run").is_dir()),
        }
    }
}

fn assert_required_output_missing(case: RequiredOutputCase) {
    let root = temp_root(&format!("{}-missing", case.label()));
    let error = AgentSpiceAdapter::new()
        .execute(
            case.request(fake_options(&root, "success")),
            &CancellationToken::new(),
        )
        .expect_err("exit zero without required output");
    assert_eq!(error.code(), "required_artifact_missing");
    let _ = fs::remove_dir_all(root);
}

fn assert_required_output_present(case: RequiredOutputCase) {
    let root = temp_root(&format!("{}-present", case.label()));
    let result = AgentSpiceAdapter::new()
        .execute(
            case.request(fake_options(&root, "required-artifacts")),
            &CancellationToken::new(),
        )
        .expect("required output exists");
    assert!(result.status.success());
    case.assert_outputs(&root);
    let _ = fs::remove_dir_all(root);
}

macro_rules! required_output_tests {
    ($missing:ident, $present:ident, $case:expr) => {
        #[test]
        fn $missing() {
            assert_required_output_missing($case);
        }

        #[test]
        fn $present() {
            assert_required_output_present($case);
        }
    };
}

required_output_tests!(
    fit_sparam_missing_required_output_is_rejected,
    fit_sparam_required_output_is_accepted,
    RequiredOutputCase::FitSparam
);
required_output_tests!(
    fit_sparam_cascade_missing_required_output_is_rejected,
    fit_sparam_cascade_required_output_is_accepted,
    RequiredOutputCase::FitSparamCascade
);
required_output_tests!(
    fit_yparam_missing_required_output_is_rejected,
    fit_yparam_required_output_is_accepted,
    RequiredOutputCase::FitYparam
);
required_output_tests!(
    tune_yparam_tran_missing_required_output_is_rejected,
    tune_yparam_tran_required_output_is_accepted,
    RequiredOutputCase::TuneYparamTran
);
required_output_tests!(
    run_hspice_missing_required_output_is_rejected,
    run_hspice_required_output_is_accepted,
    RequiredOutputCase::RunHspice
);
required_output_tests!(
    run_rfm_missing_required_output_is_rejected,
    run_rfm_required_output_is_accepted,
    RequiredOutputCase::RunRfm
);

#[test]
fn tune_yparam_tran_missing_required_work_directory_is_rejected() {
    let root = temp_root("tune-yparam-work-dir-missing");
    let error = AgentSpiceAdapter::new()
        .execute(
            RequiredOutputCase::TuneYparamTran.request(fake_options(&root, "tune-output-only")),
            &CancellationToken::new(),
        )
        .expect_err("missing required work directory");
    assert_eq!(error.code(), "required_artifact_missing");
    match error {
        AdapterError::RequiredArtifactMissing { flag, expected, .. } => {
            assert_eq!(flag, "--work-dir");
            assert_eq!(expected, "directory");
        }
        other => panic!("unexpected error: {other}"),
    }
    let _ = fs::remove_dir_all(root);
}

#[test]
fn required_artifact_kind_is_checked() {
    let root = temp_root("required-file-kind");
    let error = AgentSpiceAdapter::new()
        .execute(
            RequiredOutputCase::FitSparam.request(fake_options(&root, "wrong-file-kind")),
            &CancellationToken::new(),
        )
        .expect_err("directory cannot satisfy required file");
    assert_eq!(error.code(), "required_artifact_missing");
    let _ = fs::remove_dir_all(root);

    let root = temp_root("required-directory-kind");
    let error = AgentSpiceAdapter::new()
        .execute(
            RequiredOutputCase::RunHspice.request(fake_options(&root, "wrong-directory-kind")),
            &CancellationToken::new(),
        )
        .expect_err("file cannot satisfy required directory");
    assert_eq!(error.code(), "required_artifact_missing");
    let _ = fs::remove_dir_all(root);
}

#[test]
fn success_preserves_exact_args_and_records_artifact_provenance() {
    let root = temp_root("success");
    let artifact = root.join("result.json");
    let options = fake_options(&root, "artifact")
        .with_environment("SIPI_FAKE_ARTIFACT", artifact.to_string_lossy().as_ref());
    let request = Request::FitSparam(FitSparamRequest::new(
        args(&[
            "input.s2p",
            "--rms-target",
            "0.001",
            "--output",
            "result.json",
        ]),
        options,
    ));
    let result = AgentSpiceAdapter::new()
        .execute(request, &CancellationToken::new())
        .expect("adapter success");

    assert_eq!(result.command.cli_name(), "fit-sparam");
    assert!(result.status.success());
    assert_eq!(result.status.exit_code(), Some(0));
    assert_eq!(
        &result.invocation[2..],
        &[
            "fit-sparam",
            "input.s2p",
            "--rms-target",
            "0.001",
            "--output",
            "result.json"
        ]
    );
    assert_eq!(
        result.provenance.upstream_commit,
        "2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5"
    );
    assert!(!result.provenance.runtime_source_authenticated);
    assert_eq!(
        result.provenance.runtime_identity,
        "caller_supplied_unverified"
    );
    assert_eq!(result.artifacts.entries.len(), 1);
    assert_eq!(result.artifacts.entries[0].relative_path, "result.json");
    assert_eq!(result.artifacts.entries[0].byte_length, 17);
    assert_eq!(
        result.artifacts.sha256,
        result.provenance.artifact_manifest_sha256
    );
    let _ = fs::remove_dir_all(root);
}

#[test]
fn run_hspice_requires_explicit_backend_without_inserting_one() {
    let root = temp_root("backend");
    let options = fake_options(&root, "required-artifacts");
    let missing =
        RunHspiceRequest::new(args(&["deck.sp"]), options.clone()).expect_err("backend required");
    assert_eq!(missing.code(), "backend_required");

    let request = RunHspiceRequest::new(
        args(&["deck.sp", "--backend", "native", "--output-root", "runs"]),
        options,
    )
    .expect("explicit backend");
    assert_eq!(request.backend, Backend::Native);
    let result = AgentSpiceAdapter::new()
        .execute(Request::RunHspice(request), &CancellationToken::new())
        .expect("fake run");
    assert_eq!(result.backend, Some(Backend::Native));
    assert!(
        result
            .invocation
            .windows(2)
            .any(|pair| pair == ["--backend", "native"])
    );
    let _ = fs::remove_dir_all(root);
}

#[test]
fn execute_revalidates_public_run_request_backend_state() {
    let root = temp_root("backend-revalidation");
    let options = fake_options(&root, "required-artifacts");
    let missing = Request::RunHspice(RunHspiceRequest {
        args: args(&["deck.sp", "--output-root", "runs"]),
        options: options.clone(),
        backend: Backend::Native,
    });
    let error = AgentSpiceAdapter::new()
        .execute(missing, &CancellationToken::new())
        .expect_err("public fields cannot bypass explicit backend parsing");
    assert_eq!(error.code(), "backend_required");

    let mismatched = Request::RunRfm(RunRfmRequest {
        args: args(&["model.rfm", "--backend", "ngspice", "--output-root", "runs"]),
        options,
        backend: Backend::Native,
    });
    let error = AgentSpiceAdapter::new()
        .execute(mismatched, &CancellationToken::new())
        .expect_err("stored backend must match exact argv");
    assert_eq!(error.code(), "conflicting_backend");
    let _ = fs::remove_dir_all(root);
}

#[test]
fn output_limit_is_mapped_before_unbounded_capture() {
    let root = temp_root("output-limit");
    let mut options = fake_options(&root, "stdout");
    options.limits = ProcessLimits {
        stdout_bytes: 32,
        stderr_bytes: 1024,
        wall_time: Duration::from_secs(5),
        reader_drain_time: Duration::from_millis(200),
        artifact_bytes: 1024,
        artifact_files: 8,
        artifact_directories: 8,
        artifact_max_depth: 4,
        artifact_path_bytes: 256,
        argv_bytes: 4096,
        poll_interval: Duration::from_millis(2),
    };
    options
        .environment
        .push((OsString::from("SIPI_FAKE_COUNT"), OsString::from("4096")));
    let request = Request::FitSparam(FitSparamRequest::new(
        args(&["case.s2p", "--output", "out.sp"]),
        options,
    ));
    let error = AgentSpiceAdapter::new()
        .execute(request, &CancellationToken::new())
        .expect_err("output must be bounded");
    assert_eq!(error.code(), "output_limit_exceeded", "{error}");
    let _ = fs::remove_dir_all(root);
}

#[test]
fn timeout_and_cooperative_cancel_are_stable_errors() {
    let root = temp_root("timeout");
    let mut options = fake_options(&root, "sleep");
    options.limits.wall_time = Duration::from_millis(80);
    options.limits.poll_interval = Duration::from_millis(2);
    let error = AgentSpiceAdapter::new()
        .execute(
            Request::FitSparam(FitSparamRequest::new(
                args(&["case.s2p", "--output", "out.sp"]),
                options,
            )),
            &CancellationToken::new(),
        )
        .expect_err("timeout");
    assert_eq!(error.code(), "timed_out");

    let token = CancellationToken::new();
    let worker_token = token.clone();
    let options = fake_options(&root, "sleep");
    let worker = thread::spawn(move || {
        AgentSpiceAdapter::new().execute(
            Request::FitSparam(FitSparamRequest::new(
                args(&["case.s2p", "--output", "out.sp"]),
                options,
            )),
            &worker_token,
        )
    });
    thread::sleep(Duration::from_millis(30));
    token.cancel();
    let error = worker.join().expect("worker join").expect_err("cancel");
    assert_eq!(error.code(), "cancelled");
    let _ = fs::remove_dir_all(root);
}

#[test]
fn child_failure_is_a_result_not_a_hidden_fallback() {
    let root = temp_root("failure");
    let result = AgentSpiceAdapter::new()
        .execute(
            Request::FitSparam(FitSparamRequest::new(
                args(&["case.s2p", "--output", "out.sp"]),
                fake_options(&root, "fail"),
            )),
            &CancellationToken::new(),
        )
        .expect("process result");
    assert_eq!(result.status, ProcessStatus::Exited { code: Some(23) });
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr).contains("fake failure"));
    let _ = fs::remove_dir_all(root);
}

#[test]
fn invalid_options_are_rejected_before_process_spawn() {
    let root = temp_root("invalid");
    let mut options = fake_options(&root, "success");
    options.invocation_prefix.clear();
    let request = Request::FitSparam(FitSparamRequest::new(args(&["case.s2p"]), options));
    let error = AgentSpiceAdapter::new()
        .execute(request, &CancellationToken::new())
        .expect_err("empty prefix");
    assert!(matches!(error, AdapterError::InvalidArgument(_)));
    let _ = fs::remove_dir_all(root);
}

#[test]
fn output_path_outside_canonical_artifact_root_is_rejected() {
    let root = temp_root("output-boundary");
    let request = Request::FitSparam(FitSparamRequest::new(
        args(&["case.s2p", "--output", "../outside.sp"]),
        fake_options(&root, "success"),
    ));
    let error = AgentSpiceAdapter::new()
        .execute(request, &CancellationToken::new())
        .expect_err("outside output");
    assert_eq!(error.code(), "invalid_argument");
    let _ = fs::remove_dir_all(root);
}

#[test]
fn preexisting_required_output_is_rejected_before_spawn() {
    let root = temp_root("preexisting-required-output");
    fs::write(root.join("fit.sp"), b"stale\n").expect("stale output");
    let error = AgentSpiceAdapter::new()
        .execute(
            RequiredOutputCase::FitSparam.request(fake_options(&root, "required-artifacts")),
            &CancellationToken::new(),
        )
        .expect_err("stale output must not satisfy this run");
    assert_eq!(error.code(), "invalid_argument");
    assert_eq!(
        fs::read(root.join("fit.sp")).expect("stale output"),
        b"stale\n"
    );
    let _ = fs::remove_dir_all(root);
}

#[test]
fn argv_budget_is_enforced_before_spawn() {
    let root = temp_root("argv-limit");
    let mut options = fake_options(&root, "success");
    options.limits.argv_bytes = 16;
    let request = Request::FitSparam(FitSparamRequest::new(
        args(&["case.s2p", "--output", "out.sp"]),
        options,
    ));
    let error = AgentSpiceAdapter::new()
        .execute(request, &CancellationToken::new())
        .expect_err("argv limit");
    assert_eq!(error.code(), "argv_limit_exceeded");
    let _ = fs::remove_dir_all(root);
}

#[test]
fn artifact_directory_depth_and_path_budgets_are_enforced() {
    let root = temp_root("artifact-structure");
    let nested = root.join("a").join("b");
    fs::create_dir_all(&nested).expect("nested directory");
    fs::write(nested.join("artifact.txt"), b"x").expect("artifact");
    let mut options = fake_options(&root, "success");
    options.limits.artifact_max_depth = 1;
    let request = Request::FitSparam(FitSparamRequest::new(
        args(&["case.s2p", "--output", "out.sp"]),
        options,
    ));
    let error = AgentSpiceAdapter::new()
        .execute(request, &CancellationToken::new())
        .expect_err("depth limit");
    assert_eq!(error.code(), "artifact_depth_limit_exceeded");
    let _ = fs::remove_dir_all(root);

    let root = temp_root("artifact-directory-limit");
    fs::create_dir(root.join("child")).expect("child directory");
    let mut options = fake_options(&root, "success");
    options.limits.artifact_directories = 1;
    let request = Request::FitSparam(FitSparamRequest::new(
        args(&["case.s2p", "--output", "out.sp"]),
        options,
    ));
    let error = AgentSpiceAdapter::new()
        .execute(request, &CancellationToken::new())
        .expect_err("directory limit");
    assert_eq!(error.code(), "artifact_directory_limit_exceeded");
    let _ = fs::remove_dir_all(root);

    let root = temp_root("artifact-path-limit");
    fs::write(root.join("long-name.txt"), b"x").expect("long path artifact");
    let mut options = fake_options(&root, "success");
    options.limits.artifact_path_bytes = 4;
    let request = Request::FitSparam(FitSparamRequest::new(
        args(&["case.s2p", "--output", "out.sp"]),
        options,
    ));
    let error = AgentSpiceAdapter::new()
        .execute(request, &CancellationToken::new())
        .expect_err("path limit");
    assert_eq!(error.code(), "artifact_path_limit_exceeded");
    let _ = fs::remove_dir_all(root);

    let root = temp_root("artifact-empty-directory-path-limit");
    fs::create_dir(root.join("long-empty-directory")).expect("long empty directory");
    let mut options = fake_options(&root, "success");
    options.limits.artifact_path_bytes = 4;
    let request = Request::FitSparam(FitSparamRequest::new(
        args(&["case.s2p", "--output", "out.sp"]),
        options,
    ));
    let error = AgentSpiceAdapter::new()
        .execute(request, &CancellationToken::new())
        .expect_err("empty directory path limit");
    assert_eq!(error.code(), "artifact_path_limit_exceeded");
    let _ = fs::remove_dir_all(root);
}

#[cfg(unix)]
#[test]
fn non_utf8_invocation_is_rejected_before_hashing() {
    let root = temp_root("non-utf8");
    let mut bad = vec![0xff, b'.', b's', b'2', b'p'];
    bad.shrink_to_fit();
    let mut request_args = vec![OsString::from("--output"), OsString::from("out.sp")];
    request_args.insert(0, OsString::from_vec(bad));
    let request = Request::FitSparam(FitSparamRequest::new(
        request_args,
        fake_options(&root, "success"),
    ));
    let error = AgentSpiceAdapter::new()
        .execute(request, &CancellationToken::new())
        .expect_err("non-utf8 invocation");
    assert_eq!(error.code(), "invalid_argument");
    let _ = fs::remove_dir_all(root);
}

#[cfg(unix)]
#[test]
fn dangling_output_symlink_is_rejected_before_spawn() {
    use std::os::unix::fs::symlink;

    let root = temp_root("dangling-output-symlink");
    symlink(
        root.join("outside").join("result.sp"),
        root.join("result.sp"),
    )
    .expect("dangling output symlink");
    let request = Request::FitSparam(FitSparamRequest::new(
        args(&["case.s2p", "--output", "result.sp"]),
        fake_options(&root, "success"),
    ));
    let error = AgentSpiceAdapter::new()
        .execute(request, &CancellationToken::new())
        .expect_err("dangling output symlink");
    assert_eq!(error.code(), "invalid_argument");
    assert!(!root.join("outside").join("result.sp").exists());
    let _ = fs::remove_dir_all(root);
}

#[cfg(windows)]
fn descendant_pid(pid_file: &PathBuf) -> u32 {
    let deadline = std::time::Instant::now() + Duration::from_secs(2);
    loop {
        if let Ok(value) = fs::read_to_string(pid_file)
            && let Ok(pid) = value.trim().parse::<u32>()
        {
            return pid;
        }
        assert!(
            std::time::Instant::now() < deadline,
            "descendant pid missing"
        );
        thread::sleep(Duration::from_millis(10));
    }
}

#[cfg(windows)]
fn create_junction(target: &Path, junction: &Path) {
    let system_root =
        std::env::var_os("SystemRoot").unwrap_or_else(|| OsString::from("C:\\Windows"));
    let cmd = PathBuf::from(system_root).join("System32").join("cmd.exe");
    let output = Command::new(cmd)
        .args(["/D", "/C", "mklink", "/J"])
        .arg(junction)
        .arg(target)
        .output()
        .expect("create junction");
    assert!(output.status.success(), "mklink /J failed");
}

#[cfg(windows)]
#[test]
fn nested_artifact_junction_is_rejected() {
    let root = temp_root("artifact-junction");
    let outside = temp_root("artifact-junction-outside");
    fs::write(outside.join("outside.txt"), b"outside\n").expect("outside artifact");
    let junction = root.join("nested-junction");
    create_junction(&outside, &junction);
    let request = RequiredOutputCase::FitSparam.request(fake_options(&root, "required-artifacts"));
    let error = AgentSpiceAdapter::new()
        .execute(request, &CancellationToken::new())
        .expect_err("junction must not escape artifact custody");
    assert_eq!(error.code(), "artifact_symlink");
    fs::remove_dir(&junction).expect("remove junction");
    let _ = fs::remove_dir_all(root);
    let _ = fs::remove_dir_all(outside);
}

#[cfg(windows)]
fn assert_process_gone(pid: u32) {
    let deadline = std::time::Instant::now() + Duration::from_secs(2);
    loop {
        let output = Command::new("tasklist")
            .args(["/FI", &format!("PID eq {pid}"), "/NH"])
            .output()
            .expect("tasklist");
        let text = String::from_utf8_lossy(&output.stdout);
        if !text.contains(&pid.to_string()) {
            break;
        }
        assert!(
            std::time::Instant::now() < deadline,
            "descendant survived job termination"
        );
        thread::sleep(Duration::from_millis(20));
    }
}

#[cfg(windows)]
#[test]
fn timeout_terminates_descendant_holding_output_pipe() {
    let root = temp_root("descendant");
    let pid_file = root.join("descendant.pid");
    let mut options = fake_options(&root, "descendant");
    options.limits.wall_time = Duration::from_millis(120);
    options.limits.reader_drain_time = Duration::from_millis(500);
    options.environment.push((
        OsString::from("SIPI_FAKE_PID_FILE"),
        OsString::from(pid_file.to_string_lossy().as_ref()),
    ));
    let request = Request::FitSparam(FitSparamRequest::new(
        args(&["case.s2p", "--output", "out.sp"]),
        options,
    ));
    let error = AgentSpiceAdapter::new()
        .execute(request, &CancellationToken::new())
        .expect_err("timeout");
    assert_eq!(error.code(), "timed_out");

    assert_process_gone(descendant_pid(&pid_file));
    let _ = fs::remove_dir_all(root);
}

#[cfg(windows)]
#[test]
fn cancellation_terminates_descendant_job() {
    let root = temp_root("descendant-cancel");
    let pid_file = root.join("descendant.pid");
    let mut options = fake_options(&root, "descendant");
    options.limits.wall_time = Duration::from_secs(5);
    options.environment.push((
        OsString::from("SIPI_FAKE_PID_FILE"),
        OsString::from(pid_file.to_string_lossy().as_ref()),
    ));
    let request = Request::FitSparam(FitSparamRequest::new(
        args(&["case.s2p", "--output", "out.sp"]),
        options,
    ));
    let token = CancellationToken::new();
    let worker_token = token.clone();
    let worker = thread::spawn(move || AgentSpiceAdapter::new().execute(request, &worker_token));
    let pid = descendant_pid(&pid_file);
    token.cancel();
    let error = worker.join().expect("worker join").expect_err("cancelled");
    assert_eq!(error.code(), "cancelled");
    assert_process_gone(pid);
    let _ = fs::remove_dir_all(root);
}

#[cfg(windows)]
#[test]
fn clean_parent_exit_terminates_detached_descendant_job() {
    let root = temp_root("descendant-clean-exit");
    let pid_file = root.join("descendant.pid");
    let mut options = fake_options(&root, "descendant-clean-exit");
    options.environment.push((
        OsString::from("SIPI_FAKE_PID_FILE"),
        OsString::from(pid_file.to_string_lossy().as_ref()),
    ));
    let request = Request::FitSparam(FitSparamRequest::new(
        args(&["case.s2p", "--output", "out.sp"]),
        options,
    ));
    let result = AgentSpiceAdapter::new()
        .execute(request, &CancellationToken::new())
        .expect("parent success");
    assert!(result.status.success());
    assert_process_gone(descendant_pid(&pid_file));
    let _ = fs::remove_dir_all(root);
}

#[cfg(windows)]
#[test]
fn parent_exit_kills_job_before_reader_drain() {
    let root = temp_root("descendant-parent-exits");
    let pid_file = root.join("descendant.pid");
    let mut options = fake_options(&root, "descendant-exit");
    options.limits.wall_time = Duration::from_secs(5);
    options.limits.reader_drain_time = Duration::from_millis(120);
    options.environment.push((
        OsString::from("SIPI_FAKE_PID_FILE"),
        OsString::from(pid_file.to_string_lossy().as_ref()),
    ));
    let request = Request::FitSparam(FitSparamRequest::new(
        args(&["case.s2p", "--output", "out.sp"]),
        options,
    ));
    let result = AgentSpiceAdapter::new()
        .execute(request, &CancellationToken::new())
        .expect("parent exit closes the retained process scope before drain");
    assert!(result.status.success());

    assert_process_gone(descendant_pid(&pid_file));
    let _ = fs::remove_dir_all(root);
}

#[cfg(windows)]
#[test]
fn output_overflow_kills_descendant_job() {
    let root = temp_root("descendant-output-overflow");
    let pid_file = root.join("descendant.pid");
    let mut options = fake_options(&root, "descendant-output");
    options.limits.wall_time = Duration::from_secs(5);
    options.limits.stdout_bytes = 32;
    options.environment.push((
        OsString::from("SIPI_FAKE_PID_FILE"),
        OsString::from(pid_file.to_string_lossy().as_ref()),
    ));
    let request = Request::FitSparam(FitSparamRequest::new(
        args(&["case.s2p", "--output", "out.sp"]),
        options,
    ));
    let error = AgentSpiceAdapter::new()
        .execute(request, &CancellationToken::new())
        .expect_err("descendant output must remain bounded");
    assert_eq!(error.code(), "output_limit_exceeded", "{error}");

    assert_process_gone(descendant_pid(&pid_file));
    let _ = fs::remove_dir_all(root);
}
