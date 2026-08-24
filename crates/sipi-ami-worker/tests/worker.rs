#![cfg(windows)]

use std::{
    fs,
    path::{Path, PathBuf},
    process::Command,
    sync::{Mutex, MutexGuard, OnceLock},
    time::Duration,
};

use sha2::{Digest, Sha256};
use sipi_ami_worker::{
    AmiWorkerJobV1, AmiWorkerJobV2, FileIdentityV1, SupervisorOutcomeV1, WorkerBundleManifestV1,
    WorkerBundleManifestV2, WorkerErrorV1, run_one_job, supervise_test_only, supervise_worker_v2,
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
fn mock_lock() -> MutexGuard<'static, ()> {
    static LOCK: OnceLock<Mutex<()>> = OnceLock::new();
    LOCK.get_or_init(|| Mutex::new(()))
        .lock()
        .expect("mock lock")
}
struct MockLogGuard(Option<std::ffi::OsString>);
impl Drop for MockLogGuard {
    fn drop(&mut self) {
        unsafe {
            if let Some(previous) = self.0.take() {
                std::env::set_var("SIPI_AMI_WORKER_MOCK_LOG", previous);
            } else {
                std::env::remove_var("SIPI_AMI_WORKER_MOCK_LOG");
            }
        }
    }
}
fn install_mock_log(path: &Path) -> MockLogGuard {
    let previous = std::env::var_os("SIPI_AMI_WORKER_MOCK_LOG");
    unsafe { std::env::set_var("SIPI_AMI_WORKER_MOCK_LOG", path) };
    MockLogGuard(previous)
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
fn job(root: &Path, mode: &str) -> AmiWorkerJobV2 {
    write_f64(&root.join("matrix.f64le"), &[0.0, 1.0]);
    write_f64(&root.join("wave.f64le"), &[0.0, 0.0]);
    fs::write(root.join("parameters.ami"), format!("(mode {mode})")).expect("params");
    AmiWorkerJobV2 {
        schema: "sipi.ami-worker.job.v2".into(),
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
        request_sha256: "0".repeat(64),
        root_sha256: hex(fs::canonicalize(root)
            .expect("canonical root")
            .to_string_lossy()
            .as_bytes()),
        getwave_bits_per_call: 1,
        samples_per_bit: 2,
        max_parameters_bytes: 65_536,
    }
}
fn worker_bundle() -> (PathBuf, WorkerBundleManifestV2) {
    let worker = PathBuf::from(env!("CARGO_BIN_EXE_sipi-ami-worker"))
        .canonicalize()
        .expect("worker");
    let bytes = fs::read(&worker).expect("worker bytes");
    (
        worker,
        WorkerBundleManifestV2 {
            schema: "sipi.ami-worker.bundle.v2".into(),
            worker_sha256: hex(&bytes),
            worker_bytes: bytes.len() as u64,
            abi_contract_revision: "p4b-ami-standard-abi-host.v1".into(),
        },
    )
}

#[test]
fn legacy_supervise_test_only_signature_remains_fail_closed_and_usable() {
    let root = root("legacy-api");
    let _ = fs::remove_dir_all(&root);
    fs::create_dir_all(&root).unwrap();
    build_mock(&root);
    let worker = PathBuf::from(env!("CARGO_BIN_EXE_sipi-ami-worker"));
    let value = job(&root, "success");
    let legacy = AmiWorkerJobV1 {
        schema: "sipi.ami-worker.job.v1".into(),
        job_id: value.job_id,
        abi_contract_revision: value.abi_contract_revision,
        dll: value.dll,
        closure: value.closure,
        init_matrix: value.init_matrix,
        parameters: value.parameters,
        waveform: value.waveform,
        rows: value.rows,
        aggressors: value.aggressors,
        sample_interval_s: value.sample_interval_s,
        bit_time_s: value.bit_time_s,
        clock_capacity: value.clock_capacity,
        deadline_ms: value.deadline_ms,
        cancel_file: value.cancel_file,
        artifact_id: value.artifact_id,
    };
    fs::write(root.join("job.json"), serde_json::to_vec(&legacy).unwrap()).unwrap();
    let bytes = fs::read(&worker).unwrap();
    let bundle = WorkerBundleManifestV1 {
        schema: "sipi.ami-worker.bundle.v1".into(),
        worker_sha256: hex(&bytes),
        abi_contract_revision: "p4b-ami-standard-abi-host.v1".into(),
    };
    assert_eq!(
        supervise_test_only(&bundle, &worker, &root, Duration::from_secs(1), true).unwrap(),
        SupervisorOutcomeV1::CancelledBeforeStart
    );
    let empty = std::env::temp_dir().join(format!(
        "sipi-ami-worker-legacy-no-job-{}",
        std::process::id()
    ));
    let _ = fs::remove_dir_all(&empty);
    assert_eq!(
        supervise_test_only(&bundle, &worker, &empty, Duration::from_secs(1), true).unwrap(),
        SupervisorOutcomeV1::CancelledBeforeStart
    );
    let _ = fs::remove_dir_all(empty);
    let _ = fs::remove_dir_all(root);
}

#[test]
fn legacy_run_is_single_getwave_and_v1_artifact_shape() {
    let _lock = mock_lock();
    let root = root("legacy-run");
    let _ = fs::remove_dir_all(&root);
    fs::create_dir_all(&root).unwrap();
    build_mock(&root);
    let value = job(&root, "success");
    let legacy = AmiWorkerJobV1 {
        schema: "sipi.ami-worker.job.v1".into(),
        job_id: value.job_id,
        abi_contract_revision: value.abi_contract_revision,
        dll: value.dll,
        closure: value.closure,
        init_matrix: value.init_matrix,
        parameters: value.parameters,
        waveform: value.waveform,
        rows: value.rows,
        aggressors: value.aggressors,
        sample_interval_s: value.sample_interval_s,
        bit_time_s: value.bit_time_s,
        clock_capacity: value.clock_capacity,
        deadline_ms: value.deadline_ms,
        cancel_file: value.cancel_file,
        artifact_id: value.artifact_id,
    };
    let log = root.join("legacy.log");
    let _guard = install_mock_log(&log);
    fs::write(root.join("job.json"), serde_json::to_vec(&legacy).unwrap()).unwrap();
    run_one_job(&root).unwrap();
    assert_eq!(fs::read_to_string(log).unwrap(), "IGC");
    let result: serde_json::Value =
        serde_json::from_slice(&fs::read(root.join("artifacts/result-1/result.json")).unwrap())
            .unwrap();
    assert_eq!(result["schema"], "sipi.ami-worker.result.v1");
    let provenance: serde_json::Value =
        serde_json::from_slice(&fs::read(root.join("artifacts/result-1/provenance.json")).unwrap())
            .unwrap();
    assert_eq!(provenance["schema"], "sipi.ami-worker.provenance.v1");
    assert!(!root.join("artifacts/result-1/waveform.f64le").exists());
    assert!(!root.join("artifacts/result-1/parameters_out.json").exists());
    let _ = fs::remove_dir_all(root);
}

#[test]
fn worker_supervisor_publishes_once_and_timeout_leaves_no_success_artifact() {
    let _lock = mock_lock();
    let success = root("success");
    let _ = fs::remove_dir_all(&success);
    fs::create_dir_all(&success).expect("root");
    build_mock(&success);
    let mut value = job(&success, "success");
    value.getwave_bits_per_call = 1;
    value.samples_per_bit = 1;
    let log = success.join("mock.log");
    let _log = install_mock_log(&log);
    fs::write(
        success.join("job.json"),
        serde_json::to_vec(&value).unwrap(),
    )
    .unwrap();
    let (worker, bundle) = worker_bundle();
    let receipt =
        supervise_worker_v2(&bundle, &worker, &success, Duration::from_secs(2), false).unwrap();
    assert_eq!(receipt.outcome, SupervisorOutcomeV1::Completed);
    assert_eq!(receipt.artifact_id, "result-1");
    assert!(
        receipt
            .manifest_sha256
            .as_ref()
            .is_some_and(|sha| sha.len() == 64)
    );
    assert!(success.join("artifacts/result-1/success.json").is_file());
    assert_eq!(fs::read_to_string(&log).unwrap(), "IGGC");
    let result: serde_json::Value =
        serde_json::from_slice(&fs::read(success.join("artifacts/result-1/result.json")).unwrap())
            .unwrap();
    assert_eq!(result["close_status"], 1);
    assert_eq!(result["clock_count"], 2);
    assert_eq!(result["parameters_out_count"], 2);
    let parameters: serde_json::Value = serde_json::from_slice(
        &fs::read(success.join("artifacts/result-1/parameters_out.json")).unwrap(),
    )
    .unwrap();
    assert_eq!(parameters["blocks"], serde_json::json!(["", ""]));
    assert_eq!(
        supervise_worker_v2(&bundle, &worker, &success, Duration::from_secs(2), true)
            .unwrap()
            .outcome,
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
        supervise_worker_v2(
            &bundle,
            &worker,
            &blocked,
            Duration::from_millis(100),
            false
        )
        .unwrap()
        .outcome,
        SupervisorOutcomeV1::TimedOut
    );
    assert!(!blocked.join("artifacts/result-1/success.json").exists());
    let _ = fs::remove_dir_all(success);
    let _ = fs::remove_dir_all(blocked);
}

#[test]
fn worker_rejects_hash_drift_path_escape_and_preexisting_cancel_without_publish() {
    let _lock = mock_lock();
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

#[test]
fn mock_fault_matrix_discards_partial_outputs_and_closes_after_init() {
    let _lock = mock_lock();
    for (mode, expected_log, expected_error) in [
        ("init_fail", "I", WorkerErrorV1::Host),
        ("partial_getwave_fail", "IGC", WorkerErrorV1::Host),
        ("bad_clock", "IGC", WorkerErrorV1::Host),
        ("close_fail", "IGC", WorkerErrorV1::Host),
        ("out_of_order", "IGGC", WorkerErrorV1::Host),
    ] {
        let root = root(mode);
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(&root).expect("root");
        build_mock(&root);
        let log = root.join("mock.log");
        let _log = install_mock_log(&log);
        let mut value = job(&root, mode);
        if mode == "out_of_order" {
            value.getwave_bits_per_call = 1;
            value.samples_per_bit = 1;
        }
        fs::write(root.join("job.json"), serde_json::to_vec(&value).unwrap()).unwrap();
        assert_eq!(run_one_job(&root), Err(expected_error), "{mode}");
        assert_eq!(
            fs::read_to_string(&log).expect("call log"),
            expected_log,
            "{mode}"
        );
        assert!(
            !root.join("artifacts/result-1/success.json").exists(),
            "{mode}"
        );
        drop(_log);
        let _ = fs::remove_dir_all(root);
    }
}

#[test]
fn worker_rejects_excessive_empty_parameter_blocks_before_reserve() {
    let _lock = mock_lock();
    let root = root("parameter-block-cap");
    let _ = fs::remove_dir_all(&root);
    fs::create_dir_all(&root).unwrap();
    build_mock(&root);
    let mut value = job(&root, "success");
    value.getwave_bits_per_call = 1;
    value.samples_per_bit = 1;
    write_f64(&root.join("wave.f64le"), &vec![0.0; 100_001]);
    value.waveform = identity(&root, "wave.f64le");
    fs::write(root.join("job.json"), serde_json::to_vec(&value).unwrap()).unwrap();
    assert_eq!(run_one_job(&root), Err(WorkerErrorV1::InvalidJob));
    assert!(!root.join("artifacts/result-1/success.json").exists());
    let _ = fs::remove_dir_all(root);
}

const MOCK: &str = r#"#![allow(unsafe_op_in_unsafe_fn)]
use std::{ffi::{c_char,c_long,c_void,CStr},fs,time::Duration};
static mut CALLS: usize = 0;
fn has(p:*const c_char,s:&str)->bool{unsafe{CStr::from_ptr(p).to_bytes().windows(s.len()).any(|w|w==s.as_bytes())}}
fn log(value:u8){if let Some(path)=std::env::var_os("SIPI_AMI_WORKER_MOCK_LOG"){let _=fs::OpenOptions::new().create(true).append(true).open(path).and_then(|mut f|std::io::Write::write_all(&mut f,&[value]));}}
#[unsafe(no_mangle)] pub unsafe extern "C" fn AMI_Init(_m:*mut f64,_r:c_long,_a:c_long,_dt:f64,_bt:f64,p:*mut c_char,_out:*mut *mut c_char,h:*mut *mut c_void,_msg:*mut *mut c_char)->c_long{log(b'I');if has(p,"init_fail"){return 0;}*h=if has(p,"block_getwave"){2usize as *mut c_void}else if has(p,"bad_clock"){3usize as *mut c_void}else if has(p,"close_fail"){4usize as *mut c_void}else if has(p,"partial_getwave_fail"){5usize as *mut c_void}else if has(p,"out_of_order"){7usize as *mut c_void}else{1usize as *mut c_void};1}
#[unsafe(no_mangle)] pub unsafe extern "C" fn AMI_GetWave(w:*mut f64,n:c_long,c:*mut f64,_out:*mut *mut c_char,h:*mut c_void)->c_long{log(b'G');if n>0{*w=2.0;}if h as usize==3{*c=f64::NAN;}else if h as usize==7{CALLS+=1;*c=if CALLS==1{2e-12}else{1e-12};}else{*c=1e-12;}if h as usize==2{std::thread::sleep(Duration::from_secs(3));}if h as usize==5{return 0;}if n>1{*w.add(1)=3.0;}*c.add(1)=-1.0;1}
#[unsafe(no_mangle)] pub unsafe extern "C" fn AMI_Close(h:*mut c_void)->c_long{log(b'C');if h as usize==4{0}else{1}}
"#;
