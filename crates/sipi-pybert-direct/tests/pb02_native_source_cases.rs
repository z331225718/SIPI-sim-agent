#![cfg(feature = "pinned-python-tests")]

use std::{fs, path::PathBuf, process::Command};

use serde_json::{Value, json};

const PINNED_PYBERT_COMMIT: &str = "5bf6d7ea0ace261891aaeb611ffc1c267e160afe";
const PINNED_NATIVE_SIMULATION_TEST_BLOB: &str = "dd06dc7f612ac32a2fd088611c27530ed25762b6";

fn source_root() -> PathBuf {
    PathBuf::from(
        std::env::var_os("SIPI_PYBERT_ORACLE_ROOT")
            .expect("pinned-python-tests requires SIPI_PYBERT_ORACLE_ROOT"),
    )
}

fn required_env(name: &str) -> std::ffi::OsString {
    std::env::var_os(name).unwrap_or_else(|| panic!("pinned-python-tests requires {name}"))
}

fn git_output(root: &PathBuf, args: &[&str]) -> String {
    let output = Command::new("git")
        .arg("-C")
        .arg(root)
        .args(args)
        .output()
        .expect("invoke git for pinned PyBERT custody");
    assert!(
        output.status.success(),
        "git {:?}: {}",
        args,
        String::from_utf8_lossy(&output.stderr)
    );
    String::from_utf8(output.stdout).unwrap()
}

fn assert_source_custody(root: &PathBuf) {
    assert_eq!(
        git_output(root, &["rev-parse", "HEAD^{commit}"]).trim(),
        PINNED_PYBERT_COMMIT
    );
    assert_eq!(
        git_output(
            root,
            &[
                "rev-parse",
                &format!("{PINNED_PYBERT_COMMIT}:native/pybert-core/tests/simulation.rs")
            ],
        )
        .trim(),
        PINNED_NATIVE_SIMULATION_TEST_BLOB
    );
    assert!(
        git_output(
            root,
            &[
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
                "--",
                "native"
            ]
        )
        .is_empty(),
        "the pinned native source must be clean"
    );
}

fn native_fixture() -> Value {
    serde_json::from_slice(
        &fs::read(
            PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                .join("fixtures")
                .join("pb-02-nrz.json"),
        )
        .expect("read base native fixture"),
    )
    .expect("parse base native fixture")
}

fn run_and_compare(case: &str, input: Value) {
    let root = std::env::temp_dir().join(format!("sipi-pb02-native-{case}-{}", std::process::id()));
    let _ = fs::remove_dir_all(&root);
    fs::create_dir_all(&root).unwrap();
    let config = root.join("input.json");
    fs::write(&config, serde_json::to_vec_pretty(&input).unwrap()).unwrap();
    let oracle_dir = root.join("oracle");
    let candidate_dir = root.join("candidate");
    let oracle = Command::new(required_env("SIPI_PYBERT_ORACLE_CLI"))
        .arg("sim-native")
        .arg(&config)
        .arg("--output-dir")
        .arg(&oracle_dir)
        .output()
        .unwrap();
    assert!(
        oracle.status.success(),
        "{case}: oracle stdout={} stderr={}",
        String::from_utf8_lossy(&oracle.stdout),
        String::from_utf8_lossy(&oracle.stderr)
    );
    let candidate = Command::new(required_env("SIPI_PYBERT_CANDIDATE_CLI"))
        .arg("sim-native")
        .arg(&config)
        .arg("--output-dir")
        .arg(&candidate_dir)
        .output()
        .unwrap();
    assert!(
        candidate.status.success(),
        "{case}: candidate stdout={} stderr={}",
        String::from_utf8_lossy(&candidate.stdout),
        String::from_utf8_lossy(&candidate.stderr)
    );
    const PROBE: &str = r#"
import copy, json, sys
import numpy as np

oracle_dir, candidate_dir = sys.argv[1:]
with open(oracle_dir + "/meta.json", encoding="utf-8") as stream:
    oracle_meta = json.load(stream)
with open(candidate_dir + "/meta.json", encoding="utf-8") as stream:
    candidate_meta = json.load(stream)

def compare(left, right, path=(), key=None):
    if key in {"input_file", "source_file"}:
        assert isinstance(left, str) and isinstance(right, str), path
        return
    if isinstance(left, dict) and isinstance(right, dict):
        assert set(left) == set(right), path
        for name in left:
            compare(left[name], right[name], path + (name,), name)
    elif isinstance(left, list) and isinstance(right, list):
        assert len(left) == len(right), path
        for index, (a, b) in enumerate(zip(left, right, strict=True)):
            compare(a, b, path + (index,))
    elif isinstance(left, (int, float)) and isinstance(right, (int, float)):
        assert np.isclose(left, right, rtol=1.0e-9, atol=1.0e-12), path
    else:
        assert left == right, path

oracle_backend = copy.deepcopy(oracle_meta["backend_metadata"])
candidate_backend = copy.deepcopy(candidate_meta["backend_metadata"])
oracle_backend["engine"].pop("build")
candidate_backend["engine"].pop("build")
compare(oracle_backend, candidate_backend, ("backend_metadata",))
compare(oracle_meta["effective_input"], candidate_meta["effective_input"], ("effective_input",))
compare(oracle_meta["diagnostics"], candidate_meta["diagnostics"], ("diagnostics",))
assert oracle_meta["schema"] == candidate_meta["schema"] == "pybert.native-cli-result.v1"
assert oracle_meta["arrays_file"] == candidate_meta["arrays_file"] == "arrays.npz"
with np.load(oracle_dir + "/arrays.npz", allow_pickle=False) as oracle, np.load(candidate_dir + "/arrays.npz", allow_pickle=False) as candidate:
    assert set(oracle.files) == set(candidate.files)
    for name in oracle.files:
        left, right = oracle[name], candidate[name]
        assert left.dtype == right.dtype, name
        assert left.shape == right.shape, name
        if left.dtype.kind in "fc":
            assert np.allclose(left, right, rtol=1.0e-9, atol=1.0e-12), name
        else:
            assert np.array_equal(left, right), name
print("native-source-case-compare-ok")
"#;
    let compared = Command::new(required_env("SIPI_PYBERT_PINNED_PYTHON"))
        .args(["-c", PROBE])
        .arg(&oracle_dir)
        .arg(&candidate_dir)
        .output()
        .unwrap();
    assert!(
        compared.status.success(),
        "{case}: stdout={} stderr={}",
        String::from_utf8_lossy(&compared.stdout),
        String::from_utf8_lossy(&compared.stderr)
    );
    assert_eq!(
        String::from_utf8_lossy(&compared.stdout).trim(),
        "native-source-case-compare-ok"
    );
    let _ = fs::remove_dir_all(root);
}

#[test]
fn pinned_native_ctle_case_matches_the_complete_artifact() {
    let root = source_root();
    assert_source_custody(&root);
    let mut input = native_fixture();
    input["rx"]["nativeCtleEnabled"] = Value::Bool(true);
    input["rx"]["ctle"] = json!({
        "bandwidth": 12.0e9,
        "peakFrequency": 5.0e9,
        "peakMagnitudeDb": 4.0,
        "frequencyStepHz": null,
        "frequencyMaxHz": null
    });
    run_and_compare("ctle", input);
}

#[test]
fn pinned_native_full_prbs_jitter_bathtub_case_matches_the_complete_artifact() {
    let root = source_root();
    assert_source_custody(&root);
    let mut input = native_fixture();
    input["timebase"]["nbits"] = Value::from(254_u64);
    input["analysis"]["includeJitter"] = Value::Bool(true);
    input["analysis"]["includeBathtub"] = Value::Bool(true);
    run_and_compare("jitter-bathtub", input);
}
