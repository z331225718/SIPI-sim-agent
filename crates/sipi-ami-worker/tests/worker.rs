#![cfg(windows)]

use std::{
    fs,
    path::{Path, PathBuf},
    process::Command,
    time::Duration,
};

use sha2::{Digest, Sha256};
use sipi_ami_worker::{
    AmiWorkerJobV1, FileIdentityV1, SupervisorOutcomeV1, WorkerBundleManifestV1, WorkerErrorV1,
    run_one_job, supervise_test_only,
};

fn hex(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
fn identity(root: &Path, relative: &str) -> FileIdentityV1 {
    let bytes = fs::read(root.join(relative)).expect("sidecar");
    FileIdentityV1 {
        path: relative.into(),
        sha256: hex(&bytes),
        bytes: bytes.len() as u64,
    }
}
fn root(label: &str) -> PathBuf {
    std::env::temp_dir().join(format!("sipi-ami-worker-{label}-{}", std::process::id()))
}
fn write_f64(path: &Path, values: &[f64]) {
    let mut bytes = Vec::new();
    for value in values {
        bytes.extend(value.to_le_bytes());
    }
    fs::write(path, bytes).expect("write f64");
}

fn build_mock(root: &Path) -> PathBuf {
    let source = root.join("mock.rs");
    let output = root.join("model.dll");
    fs::write(&source, MOCK).expect("source");
    let rustc = std::env::var("RUSTC").unwrap_or_else(|_| "rustc".into());
    assert!(
        Command::new(rustc)
            .args(["--crate-type", "cdylib", "--edition", "2024"])
            .arg(&source)
            .arg("-o")
            .arg(&output)
            .status()
            .expect("rustc")
            .success()
    );
    output
}
fn job(root: &Path, mode: &str) -> AmiWorkerJobV1 {
    write_f64(&root.join("matrix.f64le"), &[0.0, 1.0]);
    write_f64(&root.join("wave.f64le"), &[0.0, 0.0]);
    fs::write(root.join("parameters.ami"), format!("(mode {mode})")).expect("params");
    AmiWorkerJobV1 {
        schema: "sipi.ami-worker.job.v1".into(),
        job_id: "job-1".into(),
        abi_contract_revision: "p4b-ami-standard-abi-host.v1".into(),
        dll: identity(root, "model.dll"),
        closure: vec![],
        init_matrix: identity(root, "matrix.f64le"),
        parameters: identity(root, "parameters.ami"),
        waveform: identity(root, "wave.f64le"),
        rows: 2,
        aggressors: 0,
        sample_interval_s: 1e-12,
        bit_time_s: 8e-12,
        clock_capacity: 4,
        deadline_ms: 5_000,
        cancel_file: "cancel.flag".into(),
        artifact_id: "result-1".into(),
    }
}
fn worker_bundle() -> (PathBuf, WorkerBundleManifestV1) {
    let worker = PathBuf::from(env!("CARGO_BIN_EXE_sipi-ami-worker"))
        .canonicalize()
        .expect("worker");
    let bytes = fs::read(&worker).expect("worker bytes");
    (
        worker,
        WorkerBundleManifestV1 {
            schema: "sipi.ami-worker.bundle.v1".into(),
            worker_sha256: hex(&bytes),
            abi_contract_revision: "p4b-ami-standard-abi-host.v1".into(),
        },
    )
}

#[test]
fn worker_supervisor_publishes_once_and_timeout_leaves_no_success_artifact() {
    let success = root("success");
    let _ = fs::remove_dir_all(&success);
    fs::create_dir_all(&success).expect("root");
    build_mock(&success);
    let value = job(&success, "success");
    fs::write(
        success.join("job.json"),
        serde_json::to_vec(&value).unwrap(),
    )
    .unwrap();
    let (worker, bundle) = worker_bundle();
    assert_eq!(
        supervise_test_only(&bundle, &worker, &success, Duration::from_secs(2), false).unwrap(),
        SupervisorOutcomeV1::Completed
    );
    assert!(success.join("artifacts/result-1/success.json").is_file());
    assert_eq!(
        supervise_test_only(&bundle, &worker, &success, Duration::from_secs(2), true).unwrap(),
        SupervisorOutcomeV1::CancelledBeforeStart
    );
    let blocked = root("blocked");
    let _ = fs::remove_dir_all(&blocked);
    fs::create_dir_all(&blocked).unwrap();
    build_mock(&blocked);
    let value = job(&blocked, "block_getwave");
    fs::write(
        blocked.join("job.json"),
        serde_json::to_vec(&value).unwrap(),
    )
    .unwrap();
    assert_eq!(
        supervise_test_only(
            &bundle,
            &worker,
            &blocked,
            Duration::from_millis(100),
            false
        )
        .unwrap(),
        SupervisorOutcomeV1::TimedOut
    );
    assert!(!blocked.join("artifacts/result-1/success.json").exists());
    let _ = fs::remove_dir_all(success);
    let _ = fs::remove_dir_all(blocked);
}

#[test]
fn worker_rejects_hash_drift_path_escape_and_preexisting_cancel_without_publish() {
    let root = root("rejection");
    let _ = fs::remove_dir_all(&root);
    fs::create_dir_all(&root).unwrap();
    build_mock(&root);
    let mut value = job(&root, "success");
    value.init_matrix.sha256 = "0".repeat(64);
    fs::write(root.join("job.json"), serde_json::to_vec(&value).unwrap()).unwrap();
    assert_eq!(run_one_job(&root), Err(WorkerErrorV1::IdentityMismatch));
    assert!(!root.join("artifacts/result-1/success.json").exists());
    let mut value = job(&root, "success");
    value.dll.path = "../model.dll".into();
    fs::write(root.join("job.json"), serde_json::to_vec(&value).unwrap()).unwrap();
    assert_eq!(run_one_job(&root), Err(WorkerErrorV1::InvalidJob));
    let value = job(&root, "success");
    fs::write(root.join("job.json"), serde_json::to_vec(&value).unwrap()).unwrap();
    fs::write(root.join("cancel.flag"), b"cancel").unwrap();
    assert_eq!(run_one_job(&root), Err(WorkerErrorV1::Cancelled));
    assert!(!root.join("artifacts/result-1/success.json").exists());
    let _ = fs::remove_dir_all(root);
}

const MOCK: &str = r#"#![allow(unsafe_op_in_unsafe_fn)]
use std::{ffi::{c_char,c_long,c_void,CStr},time::Duration};
fn has(p:*const c_char,s:&str)->bool{unsafe{CStr::from_ptr(p).to_bytes().windows(s.len()).any(|w|w==s.as_bytes())}}
#[unsafe(no_mangle)] pub unsafe extern "C" fn AMI_Init(_m:*mut f64,_r:c_long,_a:c_long,_dt:f64,_bt:f64,p:*mut c_char,_out:*mut *mut c_char,h:*mut *mut c_void,_msg:*mut *mut c_char)->c_long{*h=if has(p,"block_getwave"){2usize as *mut c_void}else{1usize as *mut c_void};1}
#[unsafe(no_mangle)] pub unsafe extern "C" fn AMI_GetWave(w:*mut f64,n:c_long,c:*mut f64,_out:*mut *mut c_char,h:*mut c_void)->c_long{if h as usize==2{std::thread::sleep(Duration::from_secs(3));}if n>0{*w=2.0;}if n>1{*w.add(1)=3.0;}*c=1e-12;*c.add(1)=-1.0;1}
#[unsafe(no_mangle)] pub unsafe extern "C" fn AMI_Close(_h:*mut c_void)->c_long{1}
"#;
