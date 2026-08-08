#![cfg(windows)]

use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::{SystemTime, UNIX_EPOCH};

use serde_json::{Value, json};
use sha2::{Digest, Sha256};

const REQUEST_SCHEMA: &str = "agent-spice.ami-host-request.v1";

struct TempDir(PathBuf);

impl TempDir {
    fn new(label: &str) -> Self {
        let nonce = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("system clock after epoch")
            .as_nanos();
        let path = std::env::temp_dir().join(format!(
            "sipi-ami-host-candidate-{label}-{}-{nonce}",
            std::process::id()
        ));
        fs::create_dir_all(&path).expect("temporary fixture directory");
        Self(path)
    }

    fn path(&self) -> &Path {
        &self.0
    }
}

impl Drop for TempDir {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

#[test]
fn candidate_host_transports_raw_abi_buffers_and_fails_closed() {
    let temp = TempDir::new("transport");
    let root = temp.path();
    let dll = build_stub(root);
    fs::copy(&dll, root.join("ami_stub.dll")).expect("copy stub DLL");
    fs::write(root.join("model.ibs"), "[IBIS Ver] 7.1\n").expect("write IBIS fixture");
    fs::write(
        root.join("model.ami"),
        "(stub\n  (Reserved_Parameters\n    (AMI_Version (Type String) (Value \"7.1\"))\n    (Init_Returns_Impulse (Type Boolean) (Value True))\n    (GetWave_Exists (Type Boolean) (Value True))\n  )\n)\n",
    )
    .expect("write AMI fixture");
    write_f64(&root.join("init.f64le"), &[0.0, 1.0]);
    write_f64(&root.join("wave.f64le"), &[1.0, 2.0]);

    let request = request_document(root, "init-get-wave");
    let request_path = root.join("request.json");
    fs::write(
        &request_path,
        serde_json::to_vec_pretty(&request).expect("serialize request"),
    )
    .expect("write request");

    let output_dir = root.join("output");
    let success = run_candidate(&request_path, &output_dir, None);
    assert!(
        success.status.success(),
        "candidate stderr: {}",
        String::from_utf8_lossy(&success.stderr)
    );
    let result: Value = serde_json::from_slice(
        &fs::read(output_dir.join("result.json")).expect("candidate result"),
    )
    .expect("valid result JSON");
    assert_eq!(result["schema"], "agent-spice.ami-host-result.v1");
    assert_eq!(result["candidate"]["mode"], "rust-host-candidate");
    assert_eq!(result["candidate"]["primaryColumn"], 0);
    assert_eq!(result["lifecycle"]["initSucceeded"], true);
    assert_eq!(result["lifecycle"]["getWaveAttempted"], true);
    assert_eq!(result["lifecycle"]["closeSucceeded"], true);
    assert_eq!(
        read_f64(&output_dir.join("init-impulse-response.f64le")),
        [0.5, 1.0]
    );
    assert_eq!(
        read_f64(&output_dir.join("get-wave-response.f64le")),
        [0.25, 2.0]
    );
    assert_eq!(read_f64(&output_dir.join("clock-times.f64le")), [2e-12]);

    let mut init_only = request.clone();
    init_only["mode"] = Value::String("init".into());
    init_only.as_object_mut().unwrap().remove("getWave");
    let init_only_path = root.join("init-only.json");
    fs::write(&init_only_path, serde_json::to_vec(&init_only).unwrap()).unwrap();
    let init_only_output = root.join("init-only-output");
    assert!(
        run_candidate(&init_only_path, &init_only_output, None)
            .status
            .success()
    );
    let init_only_result: Value =
        serde_json::from_slice(&fs::read(init_only_output.join("result.json")).unwrap()).unwrap();
    assert_eq!(init_only_result["getWave"], Value::Null);
    assert_eq!(
        read_f64(&init_only_output.join("init-impulse-response.f64le")),
        [0.5, 1.0]
    );

    let mut bad_hash = request.clone();
    bad_hash["initImpulse"]["sha256"] = Value::String("0".repeat(64));
    let bad_hash_path = root.join("bad-hash.json");
    fs::write(&bad_hash_path, serde_json::to_vec(&bad_hash).unwrap()).unwrap();
    let bad_output = root.join("bad-hash-output");
    assert!(
        !run_candidate(&bad_hash_path, &bad_output, None)
            .status
            .success()
    );
    assert!(!bad_output.exists());

    let mut unknown_field = request.clone();
    unknown_field["unexpected"] = Value::Bool(true);
    let unknown_path = root.join("unknown.json");
    fs::write(&unknown_path, serde_json::to_vec(&unknown_field).unwrap()).unwrap();
    let unknown_output = root.join("unknown-output");
    assert!(
        !run_candidate(&unknown_path, &unknown_output, None)
            .status
            .success()
    );
    assert!(!unknown_output.exists());

    let mut traversal = request.clone();
    traversal["model"]["dll"]["path"] = Value::String("../ami_stub.dll".into());
    let traversal_path = root.join("traversal.json");
    fs::write(&traversal_path, serde_json::to_vec(&traversal).unwrap()).unwrap();
    let traversal_output = root.join("traversal-output");
    assert!(
        !run_candidate(&traversal_path, &traversal_output, None)
            .status
            .success()
    );
    assert!(!traversal_output.exists());

    let mut wrong_metadata = request.clone();
    wrong_metadata["expectedMetadata"]["amiVersion"] = Value::String("6.1".into());
    let wrong_metadata_path = root.join("wrong-metadata.json");
    fs::write(
        &wrong_metadata_path,
        serde_json::to_vec(&wrong_metadata).unwrap(),
    )
    .unwrap();
    let wrong_metadata_output = root.join("wrong-metadata-output");
    assert!(
        !run_candidate(&wrong_metadata_path, &wrong_metadata_output, None)
            .status
            .success()
    );
    assert!(!wrong_metadata_output.exists());

    write_f64(&root.join("non-finite.f64le"), &[f64::NAN]);
    let mut non_finite = request.clone();
    non_finite["initImpulse"] = f64_descriptor(root, "non-finite.f64le", 1);
    let non_finite_path = root.join("non-finite.json");
    fs::write(&non_finite_path, serde_json::to_vec(&non_finite).unwrap()).unwrap();
    let non_finite_output = root.join("non-finite-output");
    assert!(
        !run_candidate(&non_finite_path, &non_finite_output, None)
            .status
            .success()
    );
    assert!(!non_finite_output.exists());

    let close_output = root.join("close-output");
    assert!(
        !run_candidate(&request_path, &close_output, Some("1"))
            .status
            .success()
    );
    assert!(!close_output.exists());
}

fn build_stub(root: &Path) -> PathBuf {
    let manifest = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixtures")
        .join("ami_host_stub")
        .join("Cargo.toml");
    let target = root.join("stub-target");
    let output = Command::new(env!("CARGO"))
        .args(["build", "--quiet", "--manifest-path"])
        .arg(manifest)
        .env("CARGO_TARGET_DIR", &target)
        .output()
        .expect("build AMI host stub");
    assert!(
        output.status.success(),
        "stub build stderr: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    target.join("debug").join("ami_host_stub.dll")
}

fn request_document(root: &Path, mode: &str) -> Value {
    json!({
        "schema": REQUEST_SCHEMA,
        "mode": mode,
        "model": {
            "ibis": file_descriptor(root, "model.ibs"),
            "ami": file_descriptor(root, "model.ami"),
            "dll": file_descriptor(root, "ami_stub.dll"),
        },
        "expectedMetadata": {
            "amiVersion": "7.1",
            "initReturnsImpulse": true,
            "getWaveExists": true,
        },
        "sampleIntervalSeconds": 1e-12,
        "bitTimeSeconds": 1e-10,
        "amiParametersIn": "(stub)",
        "initImpulse": f64_descriptor(root, "init.f64le", 2),
        "getWave": {
            "waveform": f64_descriptor(root, "wave.f64le", 2),
            "clockCapacity": 2,
        },
    })
}

fn file_descriptor(root: &Path, name: &str) -> Value {
    let bytes = fs::read(root.join(name)).expect("fixture file");
    json!({"path": name, "sha256": sha256(&bytes), "byteLength": bytes.len()})
}

fn f64_descriptor(root: &Path, name: &str, count: usize) -> Value {
    let bytes = fs::read(root.join(name)).expect("f64 fixture");
    json!({
        "path": name,
        "sha256": sha256(&bytes),
        "elementCount": count,
        "byteLength": bytes.len(),
        "encoding": "f64le",
        "endianness": "little",
    })
}

fn run_candidate(
    request: &Path,
    output_dir: &Path,
    close_failure: Option<&str>,
) -> std::process::Output {
    let mut command = Command::new(env!("CARGO_BIN_EXE_agent-spice-sim"));
    command
        .arg("ami-host-candidate")
        .arg("--request")
        .arg(request)
        .arg("--output-dir")
        .arg(output_dir);
    if let Some(value) = close_failure {
        command.env("AMI_HOST_STUB_CLOSE_FAIL", value);
    }
    command.output().expect("run candidate host")
}

fn write_f64(path: &Path, values: &[f64]) {
    let bytes: Vec<u8> = values
        .iter()
        .flat_map(|value| value.to_le_bytes())
        .collect();
    fs::write(path, bytes).expect("write f64 fixture");
}

fn read_f64(path: &Path) -> Vec<f64> {
    fs::read(path)
        .expect("read f64 output")
        .chunks_exact(8)
        .map(|bytes| f64::from_le_bytes(bytes.try_into().expect("f64 bytes")))
        .collect()
}

fn sha256(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
