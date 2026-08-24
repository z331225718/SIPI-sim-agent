use std::{
    fs,
    path::{Path, PathBuf},
    process::Command,
    time::Duration,
};

use sipi_ami_worker::{SupervisorOutcomeV1, WorkerIdentityV1};
use sipi_pybert_direct::{
    PYBERT_AMI_ADAPTER_SCHEMA_V2, PybertAmiModeV1, PybertAmiRequestV1, PybertAmiWorkerErrorV1,
    Seconds, SupervisorReceiptV1, prepare_pybert_ami_launch,
    supervise_prepared_pybert_ami_job,
};

fn root(label: &str) -> PathBuf {
    let root = std::env::temp_dir().join(format!("sipi-pybert-ami-{label}-{}", std::process::id()));
    let _ = fs::remove_dir_all(&root);
    fs::create_dir_all(&root).unwrap();
    fs::write(root.join("model.ibs"), b"[IBIS Ver] 7.2\n").unwrap();
    fs::write(root.join("model.ami"), b"(mode success)").unwrap();
    fs::write(root.join("model.dll"), b"external-vendor-placeholder").unwrap();
    fs::write(root.join("matrix.f64le"), 0.0_f64.to_le_bytes()).unwrap();
    let mut waveform = Vec::new();
    waveform.extend_from_slice(&0.0_f64.to_le_bytes());
    waveform.extend_from_slice(&1.0_f64.to_le_bytes());
    fs::write(root.join("wave.f64le"), waveform).unwrap();
    root
}

fn build_mock_dll(root: &Path) -> PathBuf {
    let source = root.join("mock.rs");
    let dll = root.join("model.dll");
    fs::write(&source, MOCK_DLL).unwrap();
    let rustc = std::env::var("RUSTC").unwrap_or_else(|_| "rustc".into());
    assert!(
        Command::new(rustc)
            .args(["--crate-type", "cdylib", "--edition", "2024"])
            .arg(source)
            .arg("-o")
            .arg(&dll)
            .status()
            .unwrap()
            .success()
    );
    dll
}

fn worker_binary() -> PathBuf {
    let manifest = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let workspace = manifest
        .ancestors()
        .find(|candidate| {
            candidate
                .join("crates/sipi-ami-worker/Cargo.toml")
                .is_file()
        })
        .expect("workspace root");
    let cargo = std::env::var_os("CARGO").unwrap_or_else(|| "cargo.exe".into());
    assert!(
        Command::new(cargo)
            .current_dir(workspace)
            .args([
                "build",
                "--manifest-path",
                "crates/sipi-ami-worker/Cargo.toml",
                "--bin",
                "sipi-ami-worker",
            ])
            .status()
            .expect("cargo build sipi-ami-worker")
            .success()
    );
    let worker = workspace.join("target/debug/sipi-ami-worker.exe");
    assert!(worker.is_file(), "worker build output missing");
    worker
}

fn request(mode: PybertAmiModeV1) -> PybertAmiRequestV1 {
    PybertAmiRequestV1 {
        mode,
        ibis_path: "model.ibs".into(),
        ami_path: "model.ami".into(),
        runtime_parameters: "(mode success)".into(),
        dll_path: "model.dll".into(),
        init_matrix_path: "matrix.f64le".into(),
        waveform_path: "wave.f64le".into(),
        rows: 1,
        aggressors: 0,
        sample_interval: Seconds(1e-12),
        bit_time: Seconds(8e-12),
        samples_per_bit: 2,
        block_size_bits: 8,
        max_waveform_samples: 1024,
        clock_capacity: 8,
        max_parameters_bytes: 65_536,
        deadline_ms: 2_000,
        artifact_id: "artifact-1".into(),
        expected_worker_sha256: "0".repeat(64),
        expected_worker_bytes: 1,
    }
}

#[test]
fn adapter_binds_ibs_ami_dll_closure_and_fresh_request_identity() {
    let root = root("prepare");
    let first = prepare_pybert_ami_launch(&root, &request(PybertAmiModeV1::InitGetWave)).unwrap();
    let second = prepare_pybert_ami_launch(&root, &request(PybertAmiModeV1::InitGetWave)).unwrap();
    assert_eq!(first.schema, PYBERT_AMI_ADAPTER_SCHEMA_V2);
    assert_ne!(first.nonce, second.nonce);
    assert_ne!(first.request_sha256, second.request_sha256);
    assert_eq!(first.asset_bundle.ibis.path, "model.ibs");
    assert_eq!(first.asset_bundle.ami.path, "model.ami");
    assert_eq!(first.asset_bundle.dll.path, "model.dll");
    assert_eq!(first.job.closure.len(), 2);
    assert!(first.job.parameters.path.starts_with("runtime-"));
    assert_eq!(first.nonce.len(), 71);
    assert_eq!(first.job.getwave_bits_per_call, 8);
    assert_eq!(first.job.samples_per_bit, 2);
    let _ = fs::remove_dir_all(root);
}

#[test]
fn adapter_does_not_silently_turn_init_into_getwave() {
    let root = root("mode");
    let error = prepare_pybert_ami_launch(&root, &request(PybertAmiModeV1::Init)).unwrap_err();
    assert_eq!(error, PybertAmiWorkerErrorV1::UnsupportedMode);
    let _ = fs::remove_dir_all(root);
}

#[test]
fn adapter_rebinds_file_drift_and_digest_mutations_fail_closed() {
    let root_dir = root("mutation");
    let launch =
        prepare_pybert_ami_launch(&root_dir, &request(PybertAmiModeV1::InitGetWave)).unwrap();
    fs::write(
        root_dir.join("model.ami"),
        b"(Reserved_Parameters (GetWave_Exists (Value False)))",
    )
    .unwrap();
    let rebound =
        prepare_pybert_ami_launch(&root_dir, &request(PybertAmiModeV1::InitGetWave)).unwrap();
    assert_ne!(
        launch.asset_bundle.ami.sha256,
        rebound.asset_bundle.ami.sha256
    );
    let mut forged = launch;
    forged.block_size_bits += 1;
    let receipt = SupervisorReceiptV1 {
        outcome: SupervisorOutcomeV1::Completed,
        artifact_id: forged.job.artifact_id.clone(),
        manifest_sha256: Some("0".repeat(64)),
        worker_pre: WorkerIdentityV1 {
            sha256: "0".repeat(64),
            bytes: 0,
            modified_nanos: 0,
        },
        worker_post: WorkerIdentityV1 {
            sha256: "0".repeat(64),
            bytes: 0,
            modified_nanos: 0,
        },
    };
    assert_eq!(
        sipi_pybert_direct::consume_pybert_ami_result(&root_dir, &forged, &receipt).unwrap_err(),
        PybertAmiWorkerErrorV1::AssetIdentity
    );
    let other_root = root("other-root");
    let error = sipi_pybert_direct::supervise_prepared_pybert_ami_job(
        &other_root,
        &rebound,
        Path::new(r"C:\missing\sipi-ami-worker.exe"),
        &sipi_ami_worker::WorkerBundleManifestV2 {
            schema: "sipi.ami-worker.bundle.v2".into(),
            worker_sha256: "0".repeat(64),
            worker_bytes: 1,
            abi_contract_revision: "p4b-ami-standard-abi-host.v1".into(),
        },
        Duration::from_secs(1),
    )
    .unwrap_err();
    assert_eq!(error, PybertAmiWorkerErrorV1::AssetIdentity);
    let _ = fs::remove_dir_all(other_root);
    let _ = fs::remove_dir_all(root_dir);
}

#[test]
fn adapter_rejects_escape_and_invalid_input() {
    let root = root("reject");
    let mut req = request(PybertAmiModeV1::InitGetWave);
    req.ami_path = "../model.ami".into();
    assert_eq!(
        prepare_pybert_ami_launch(&root, &req).unwrap_err(),
        PybertAmiWorkerErrorV1::UnsafePath
    );
    let mut oversized = request(PybertAmiModeV1::InitGetWave);
    oversized.max_waveform_samples = 8_000_001;
    assert_eq!(
        prepare_pybert_ami_launch(&root, &oversized).unwrap_err(),
        PybertAmiWorkerErrorV1::InvalidInput
    );
    let mut short_matrix = request(PybertAmiModeV1::InitGetWave);
    short_matrix.rows = 2;
    assert_eq!(
        prepare_pybert_ami_launch(&root, &short_matrix).unwrap_err(),
        PybertAmiWorkerErrorV1::AssetIdentity
    );
    let mut huge_matrix = request(PybertAmiModeV1::InitGetWave);
    huge_matrix.rows = 4_000_001;
    assert_eq!(
        prepare_pybert_ami_launch(&root, &huge_matrix).unwrap_err(),
        PybertAmiWorkerErrorV1::InvalidInput
    );
    let mut bad_deadline = request(PybertAmiModeV1::InitGetWave);
    bad_deadline.deadline_ms = 300_001;
    assert_eq!(
        prepare_pybert_ami_launch(&root, &bad_deadline).unwrap_err(),
        PybertAmiWorkerErrorV1::InvalidInput
    );
    let mut bad_artifact = request(PybertAmiModeV1::InitGetWave);
    bad_artifact.artifact_id = "artifact/escape".into();
    assert_eq!(
        prepare_pybert_ami_launch(&root, &bad_artifact).unwrap_err(),
        PybertAmiWorkerErrorV1::InvalidInput
    );
    let mut too_many_blocks = request(PybertAmiModeV1::InitGetWave);
    too_many_blocks.block_size_bits = 1;
    too_many_blocks.samples_per_bit = 1;
    too_many_blocks.max_waveform_samples = 8_000_000;
    assert_eq!(
        prepare_pybert_ami_launch(&root, &too_many_blocks).unwrap_err(),
        PybertAmiWorkerErrorV1::InvalidInput
    );
    let mut bad_identity = request(PybertAmiModeV1::InitGetWave);
    bad_identity.expected_worker_sha256 = "A".repeat(64);
    assert_eq!(
        prepare_pybert_ami_launch(&root, &bad_identity).unwrap_err(),
        PybertAmiWorkerErrorV1::InvalidInput
    );
    let _ = fs::remove_dir_all(root);
}

#[test]
fn adapter_bundle_mismatch_rejects_before_writing_job_or_launch() {
    let root = root("bundle-before-write");
    let launch = prepare_pybert_ami_launch(&root, &request(PybertAmiModeV1::InitGetWave)).unwrap();
    let bundle = sipi_ami_worker::WorkerBundleManifestV2 {
        schema: "sipi.ami-worker.bundle.v2".into(),
        worker_sha256: "1".repeat(64),
        worker_bytes: 1,
        abi_contract_revision: "p4b-ami-standard-abi-host.v1".into(),
    };
    let missing = Path::new(r"C:\missing\sipi-ami-worker.exe");
    assert_eq!(
        sipi_pybert_direct::supervise_prepared_pybert_ami_job(
            &root,
            &launch,
            missing,
            &bundle,
            Duration::from_secs(1),
        )
        .unwrap_err(),
        PybertAmiWorkerErrorV1::AssetIdentity
    );
    assert!(!root.join("job.json").exists());
    assert!(!root.join("pybert-ami-launch.json").exists());
    let _ = fs::remove_dir_all(root);
}

#[test]
fn adapter_nonce_escape_rejected_before_any_file_write() {
    let root = root("nonce-escape");
    let mut launch =
        prepare_pybert_ami_launch(&root, &request(PybertAmiModeV1::InitGetWave)).unwrap();
    launch.nonce = r"..\escape".into();
    launch.job.job_id = launch.nonce.clone();
    let bundle = sipi_ami_worker::WorkerBundleManifestV2 {
        schema: "sipi.ami-worker.bundle.v2".into(),
        worker_sha256: launch.expected_worker_sha256.clone(),
        worker_bytes: launch.expected_worker_bytes,
        abi_contract_revision: "p4b-ami-standard-abi-host.v1".into(),
    };
    let outside = root.parent().unwrap().join("escape");
    let _ = fs::remove_file(&outside);
    let result = supervise_prepared_pybert_ami_job(
        &root,
        &launch,
        &root.join("missing-worker.exe"),
        &bundle,
        Duration::from_secs(1),
    );
    assert!(result.is_err());
    assert!(!root.join("job.json").exists());
    assert!(!root.join("pybert-ami-launch.json").exists());
    assert!(!outside.exists());
    let _ = fs::remove_dir_all(root);
}

#[test]
fn adapter_coordinated_max_parameter_drift_and_zero_block_are_errors() {
    let root = root("coordinated-drift");
    let launch = prepare_pybert_ami_launch(&root, &request(PybertAmiModeV1::InitGetWave)).unwrap();
    let mut drift = launch.clone();
    drift.max_parameters_bytes += 1;
    let receipt = SupervisorReceiptV1 {
        outcome: SupervisorOutcomeV1::Completed,
        artifact_id: drift.job.artifact_id.clone(),
        manifest_sha256: Some("0".repeat(64)),
        worker_pre: WorkerIdentityV1 {
            sha256: drift.expected_worker_sha256.clone(),
            bytes: drift.expected_worker_bytes,
            modified_nanos: 0,
        },
        worker_post: WorkerIdentityV1 {
            sha256: drift.expected_worker_sha256.clone(),
            bytes: drift.expected_worker_bytes,
            modified_nanos: 0,
        },
    };
    assert_eq!(
        std::panic::catch_unwind(|| {
            sipi_pybert_direct::consume_pybert_ami_result(&root.join("artifacts"), &drift, &receipt)
        })
        .expect("no panic")
        .unwrap_err(),
        PybertAmiWorkerErrorV1::AssetIdentity
    );
    let mut zero = launch;
    zero.job.getwave_bits_per_call = 0;
    assert!(
        std::panic::catch_unwind(|| {
            sipi_pybert_direct::consume_pybert_ami_result(&root.join("artifacts"), &zero, &receipt)
        })
        .expect("no panic")
        .is_err()
    );
    let _ = fs::remove_dir_all(root);
}

#[test]
fn adapter_failed_prepare_cleans_runtime_temp_file() {
    let root = root("runtime-cleanup");
    fs::write(root.join("matrix.f64le"), 0.0_f64.to_le_bytes()).unwrap();
    let mut request = request(PybertAmiModeV1::InitGetWave);
    request.rows = 2;
    let error = prepare_pybert_ami_launch(&root, &request);
    assert_eq!(error.unwrap_err(), PybertAmiWorkerErrorV1::AssetIdentity);
    assert!(
        !fs::read_dir(&root)
            .unwrap()
            .flatten()
            .any(|entry| entry.file_name().to_string_lossy().starts_with("runtime-"))
    );
    let _ = fs::remove_dir_all(root);
}

#[test]
fn adapter_prepare_supervise_receipt_and_consume_is_one_real_process_chain() {
    let root = root("e2e");
    build_mock_dll(&root);
    let mut request = request(PybertAmiModeV1::InitGetWave);
    request.samples_per_bit = 1;
    request.block_size_bits = 1;
    let worker = worker_binary();
    assert!(
        worker.is_file(),
        "worker binary must be available from the explicit worker build"
    );
    let bytes = fs::read(&worker).unwrap();
    request.expected_worker_sha256 = sipi_pybert_direct::sha256_bytes(&bytes);
    request.expected_worker_bytes = bytes.len() as u64;
    let launch = prepare_pybert_ami_launch(&root, &request).unwrap();
    let bundle = sipi_ami_worker::WorkerBundleManifestV2 {
        schema: "sipi.ami-worker.bundle.v2".into(),
        worker_sha256: sipi_pybert_direct::sha256_bytes(&bytes),
        worker_bytes: bytes.len() as u64,
        abi_contract_revision: "p4b-ami-standard-abi-host.v1".into(),
    };
    let receipt = sipi_pybert_direct::supervise_prepared_pybert_ami_job(
        &root,
        &launch,
        &worker,
        &bundle,
        Duration::from_secs(10),
    )
    .unwrap();
    assert_eq!(
        receipt.outcome,
        sipi_ami_worker::SupervisorOutcomeV1::Completed
    );
    assert_eq!(receipt.worker_pre, receipt.worker_post);
    let result =
        sipi_pybert_direct::consume_pybert_ami_result(&root.join("artifacts"), &launch, &receipt)
            .unwrap();
    assert_eq!(result.waveform, vec![7.0, 8.0]);
    assert_eq!(result.clocks_s, vec![1e-12, 2e-12]);
    assert_eq!(result.parameters_out, vec!["block-1", "block-2"]);
    let _ = fs::remove_dir_all(root);
}

const MOCK_DLL: &str = r#"
#![allow(unsafe_op_in_unsafe_fn)]
use std::ffi::{c_char,c_long,c_void,CStr};
static INIT: &[u8] = b"init\0";
static BLOCK_ONE: &[u8] = b"block-1\0";
static BLOCK_TWO: &[u8] = b"block-2\0";
static mut CALLS: usize = 0;
#[unsafe(no_mangle)] pub unsafe extern "C" fn AMI_Init(matrix:*mut f64,_rows:c_long,_aggressors:c_long,_dt:f64,_bit:f64,parameters:*mut c_char,out:*mut *mut c_char,handle:*mut *mut c_void,_message:*mut *mut c_char)->c_long { if CStr::from_ptr(parameters).to_bytes() != b"(mode success)" { return 0; } *matrix=42.0; *out=INIT.as_ptr() as *mut c_char; *handle=1usize as *mut c_void; 1 }
#[unsafe(no_mangle)] pub unsafe extern "C" fn AMI_GetWave(wave:*mut f64,_size:c_long,clocks:*mut f64,out:*mut *mut c_char,_handle:*mut c_void)->c_long { CALLS+=1; *wave=if CALLS==1{7.0}else{8.0}; *clocks=if CALLS==1{1e-12}else{2e-12}; *out=if CALLS==1{BLOCK_ONE.as_ptr()}else{BLOCK_TWO.as_ptr()} as *mut c_char; *clocks.add(1)=-1.0; 1 }
#[unsafe(no_mangle)] pub unsafe extern "C" fn AMI_Close(_handle:*mut c_void)->c_long { 1 }
"#;
