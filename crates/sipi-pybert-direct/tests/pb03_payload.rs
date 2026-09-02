use std::{fs, path::PathBuf};

#[cfg(feature = "pinned-python-tests")]
use std::process::Command;

use sipi_pybert_direct::run_sim_rust_file;

fn fixture() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("fixtures")
        .join("pb-03-legacy-nrz.yaml")
}

#[test]
fn sim_rust_rejects_controls_that_the_source_web_request_cannot_validate() {
    let root = std::env::temp_dir().join(format!("sipi-pb03-invalid-{}", std::process::id()));
    let _ = fs::remove_dir_all(&root);
    fs::create_dir_all(&root).unwrap();
    let config = root.join("gain-out-of-range.yaml");
    let source = fs::read_to_string(fixture()).unwrap();
    fs::write(&config, source.replacen("gain: 0.1", "gain: 1.1", 1)).unwrap();

    let error = run_sim_rust_file(&config, &root.join("output"), None).unwrap_err();
    assert!(error.to_string().contains("rx.gain outside 0..=1"));
    assert!(!root.join("output/meta.json").exists());

    let _ = fs::remove_dir_all(root);
}

#[cfg(feature = "pinned-python-tests")]
#[test]
fn pinned_pybert_sim_rust_matches_the_full_web_array_payload() {
    const PINNED_PYBERT_COMMIT: &str = "5bf6d7ea0ace261891aaeb611ffc1c267e160afe";
    let python = std::env::var_os("SIPI_PYBERT_PINNED_PYTHON")
        .expect("pinned-python-tests requires SIPI_PYBERT_PINNED_PYTHON");
    let oracle_cli = std::env::var_os("SIPI_PYBERT_ORACLE_CLI")
        .expect("pinned-python-tests requires SIPI_PYBERT_ORACLE_CLI");
    let candidate_cli = std::env::var_os("SIPI_PYBERT_CANDIDATE_CLI")
        .expect("pinned-python-tests requires SIPI_PYBERT_CANDIDATE_CLI (a release binary)");
    let oracle_root = PathBuf::from(
        std::env::var_os("SIPI_PYBERT_ORACLE_ROOT")
            .expect("pinned-python-tests requires SIPI_PYBERT_ORACLE_ROOT"),
    );
    let revision = Command::new("git")
        .args(["-C"])
        .arg(&oracle_root)
        .args(["rev-parse", "HEAD^{commit}"])
        .output()
        .expect("read pinned PyBERT revision");
    assert!(revision.status.success());
    assert_eq!(
        String::from_utf8(revision.stdout).unwrap().trim(),
        PINNED_PYBERT_COMMIT
    );
    let source_status = Command::new("git")
        .args(["-C"])
        .arg(&oracle_root)
        .args([
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--",
            "src",
        ])
        .output()
        .expect("check pinned PyBERT source custody");
    assert!(source_status.status.success());
    assert!(source_status.stdout.is_empty());

    let root =
        std::env::temp_dir().join(format!("sipi-pb03-source-compare-{}", std::process::id()));
    let _ = fs::remove_dir_all(&root);
    let oracle_dir = root.join("oracle");
    let candidate_dir = root.join("candidate");
    let oracle = Command::new(oracle_cli)
        .arg("sim-rust")
        .arg(fixture())
        .arg("--output-dir")
        .arg(&oracle_dir)
        .output()
        .unwrap();
    assert!(
        oracle.status.success(),
        "stdout={} stderr={}",
        String::from_utf8_lossy(&oracle.stdout),
        String::from_utf8_lossy(&oracle.stderr)
    );
    let candidate = Command::new(candidate_cli)
        .arg("sim-rust")
        .arg(fixture())
        .arg("--output-dir")
        .arg(&candidate_dir)
        .output()
        .unwrap();
    assert!(
        candidate.status.success(),
        "stdout={} stderr={}",
        String::from_utf8_lossy(&candidate.stdout),
        String::from_utf8_lossy(&candidate.stderr)
    );

    const PROBE: &str = r#"
import copy, json, sys
import numpy as np

oracle_dir, candidate_dir = sys.argv[1:]
with open(oracle_dir + "/meta.json", "r", encoding="utf-8") as stream:
    oracle_meta = json.load(stream)
with open(candidate_dir + "/meta.json", "r", encoding="utf-8") as stream:
    candidate_meta = json.load(stream)
assert set(oracle_meta) == set(candidate_meta) == {
    "schema", "input_file", "effective_input", "backend_metadata", "diagnostics", "arrays_file"
}
assert oracle_meta["schema"] == candidate_meta["schema"] == "pybert.native-cli-result.v1"
assert oracle_meta["input_file"] == candidate_meta["input_file"]
assert oracle_meta["effective_input"] == candidate_meta["effective_input"]
assert oracle_meta["arrays_file"] == candidate_meta["arrays_file"] == "arrays.npz"

oracle_backend = copy.deepcopy(oracle_meta["backend_metadata"])
candidate_backend = copy.deepcopy(candidate_meta["backend_metadata"])
oracle_backend["run_id"] = candidate_backend["run_id"] = "<runtime-provenance>"
oracle_backend["engine"].pop("build")
candidate_backend["engine"].pop("build")
def assert_equivalent(left, right, path=()):
    if isinstance(left, dict) and isinstance(right, dict):
        assert set(left) == set(right), path
        for key in left:
            assert_equivalent(left[key], right[key], path + (key,))
    elif isinstance(left, list) and isinstance(right, list):
        assert len(left) == len(right), path
        for index, (left_item, right_item) in enumerate(zip(left, right, strict=True)):
            assert_equivalent(left_item, right_item, path + (index,))
    elif isinstance(left, (int, float)) and isinstance(right, (int, float)):
        assert np.isclose(left, right, rtol=1.0e-9, atol=1.0e-12), path
    else:
        assert left == right, path

assert_equivalent(oracle_backend, candidate_backend)

oracle_diagnostics = copy.deepcopy(oracle_meta["diagnostics"])
candidate_diagnostics = copy.deepcopy(candidate_meta["diagnostics"])
for diagnostics in (oracle_diagnostics, candidate_diagnostics):
    for event in diagnostics["events"]:
        event["runId"] = "<runtime-provenance>"
assert oracle_diagnostics == candidate_diagnostics

with np.load(oracle_dir + "/arrays.npz", allow_pickle=False) as oracle, np.load(candidate_dir + "/arrays.npz", allow_pickle=False) as candidate:
    assert set(oracle.files) == set(candidate.files)
    assert len(oracle.files) == 150
    for name in oracle.files:
        left, right = oracle[name], candidate[name]
        assert left.dtype == right.dtype, name
        assert left.shape == right.shape, name
        if left.dtype.kind in "fc":
            assert np.allclose(left, right, rtol=1.0e-9, atol=1.0e-12), name
        else:
            assert np.array_equal(left, right), name
print("complete-web-payload-compare-ok")
"#;
    let compared = Command::new(python)
        .args(["-c", PROBE])
        .arg(&oracle_dir)
        .arg(&candidate_dir)
        .output()
        .unwrap();
    assert!(
        compared.status.success(),
        "stdout={} stderr={}",
        String::from_utf8_lossy(&compared.stdout),
        String::from_utf8_lossy(&compared.stderr)
    );
    assert_eq!(
        String::from_utf8_lossy(&compared.stdout).trim(),
        "complete-web-payload-compare-ok"
    );
    let _ = fs::remove_dir_all(root);
}

#[cfg(feature = "pinned-python-tests")]
#[test]
fn pinned_pybert_sim_rust_matches_the_analytic_ctle_payload() {
    const PINNED_PYBERT_COMMIT: &str = "5bf6d7ea0ace261891aaeb611ffc1c267e160afe";
    let python = std::env::var_os("SIPI_PYBERT_PINNED_PYTHON")
        .expect("pinned-python-tests requires SIPI_PYBERT_PINNED_PYTHON");
    let oracle_cli = std::env::var_os("SIPI_PYBERT_ORACLE_CLI")
        .expect("pinned-python-tests requires SIPI_PYBERT_ORACLE_CLI");
    let candidate_cli = std::env::var_os("SIPI_PYBERT_CANDIDATE_CLI")
        .expect("pinned-python-tests requires SIPI_PYBERT_CANDIDATE_CLI (a release binary)");
    let oracle_root = PathBuf::from(
        std::env::var_os("SIPI_PYBERT_ORACLE_ROOT")
            .expect("pinned-python-tests requires SIPI_PYBERT_ORACLE_ROOT"),
    );
    let revision = Command::new("git")
        .args(["-C"])
        .arg(&oracle_root)
        .args(["rev-parse", "HEAD^{commit}"])
        .output()
        .expect("read pinned PyBERT revision");
    assert!(revision.status.success());
    assert_eq!(
        String::from_utf8(revision.stdout).unwrap().trim(),
        PINNED_PYBERT_COMMIT
    );
    let source_status = Command::new("git")
        .args(["-C"])
        .arg(&oracle_root)
        .args([
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--",
            "src",
        ])
        .output()
        .expect("check pinned PyBERT source custody");
    assert!(source_status.status.success());
    assert!(source_status.stdout.is_empty());

    let root = std::env::temp_dir().join(format!("sipi-pb03-ctle-{}", std::process::id()));
    let _ = fs::remove_dir_all(&root);
    fs::create_dir_all(&root).unwrap();
    let config = root.join("analytic-ctle.yaml");
    let fixture_text = fs::read_to_string(fixture()).unwrap();
    let configured = fixture_text
        .replacen("ctle_enable: false", "ctle_enable: true", 1)
        .replacen("peak_mag: 1.7", "peak_mag: 4.0", 1);
    assert_ne!(configured, fixture_text, "CTLE fixture mutation must apply");
    fs::write(&config, configured).unwrap();
    let oracle_dir = root.join("oracle");
    let candidate_dir = root.join("candidate");
    let oracle = Command::new(oracle_cli)
        .args(["sim-rust"])
        .arg(&config)
        .args(["--output-dir"])
        .arg(&oracle_dir)
        .output()
        .unwrap();
    assert!(
        oracle.status.success(),
        "{}",
        String::from_utf8_lossy(&oracle.stderr)
    );
    let candidate = Command::new(candidate_cli)
        .args(["sim-rust"])
        .arg(&config)
        .args(["--output-dir"])
        .arg(&candidate_dir)
        .output()
        .unwrap();
    assert!(
        candidate.status.success(),
        "{}",
        String::from_utf8_lossy(&candidate.stderr)
    );
    const PROBE: &str = r#"
import numpy as np
import sys

oracle_dir, candidate_dir = sys.argv[1:]
with np.load(oracle_dir + "/arrays.npz", allow_pickle=False) as oracle, np.load(candidate_dir + "/arrays.npz", allow_pickle=False) as candidate:
    assert set(oracle.files) == set(candidate.files)
    assert len(oracle.files) == 150
    for name in oracle.files:
        left, right = oracle[name], candidate[name]
        assert left.dtype == right.dtype, name
        assert left.shape == right.shape, name
        if left.dtype.kind in "fc":
            assert np.allclose(left, right, rtol=1.0e-9, atol=1.0e-12), name
        else:
            assert np.array_equal(left, right), name
print("analytic-ctle-payload-compare-ok")
"#;
    let compared = Command::new(python)
        .args(["-c", PROBE])
        .arg(&oracle_dir)
        .arg(&candidate_dir)
        .output()
        .unwrap();
    assert!(
        compared.status.success(),
        "stdout={} stderr={}",
        String::from_utf8_lossy(&compared.stdout),
        String::from_utf8_lossy(&compared.stderr)
    );
    assert_eq!(
        String::from_utf8_lossy(&compared.stdout).trim(),
        "analytic-ctle-payload-compare-ok"
    );
    let _ = fs::remove_dir_all(root);
}
