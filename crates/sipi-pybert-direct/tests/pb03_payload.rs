use std::{collections::BTreeSet, fs, path::PathBuf};

#[cfg(feature = "pinned-python-tests")]
use std::process::Command;

use sipi_pybert_direct::run_sim_rust_file;

fn fixture() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("fixtures")
        .join("pb-03-legacy-nrz.yaml")
}

#[test]
fn sim_rust_publishes_the_existing_web_payload_projection() {
    let root = std::env::temp_dir().join(format!("sipi-pb03-payload-{}", std::process::id()));
    let _ = fs::remove_dir_all(&root);
    let report = run_sim_rust_file(&fixture(), &root, None).unwrap();

    let expected = [
        "t_ns_chnl",
        "chnl_h",
        "chnl_s",
        "chnl_p",
        "f_GHz",
        "chnl_H_raw",
        "chnl_H",
        "chnl_trimmed_H",
        "tx_H",
        "tx_out_H",
        "ctle_H",
        "ctle_out_H",
        "dfe_H",
        "dfe_out_H",
        "rx_out_H",
        "parity_channel_impulse_v_per_v",
        "parity_ctle_output_v",
        "parity_rx_output_v",
        "parity_dfe_output_v",
        "parity_dfe_decisions",
        "parity_dfe_clock_times_s",
        "jitter_bins",
        "bathtub_chnl",
        "bathtub_tx",
        "bathtub_ctle",
        "bathtub_dfe",
        "bathtub_rx",
    ];
    let names = report
        .output
        .arrays
        .keys()
        .map(String::as_str)
        .collect::<BTreeSet<_>>();
    // The upstream `sim-rust` CLI keeps the full payload in arrays.npz; its
    // metadata is a six-key envelope rather than a second embedded array map.
    assert_eq!(names.len(), 150);
    for name in expected {
        assert!(names.contains(name), "missing projected array {name}");
    }
    assert_eq!(
        report.output.arrays["chnl_h"],
        report.output.arrays["channel_impulse_v_per_v"]
    );
    assert_eq!(
        report.output.arrays["parity_rx_output_v"],
        report.output.arrays["rx_output_v"]
    );
    assert_eq!(
        report.output.arrays["parity_dfe_decisions"],
        report.output.arrays["dfe_decisions"]
    );
    for name in [
        "native_eye_chnl",
        "native_eye_tx",
        "native_eye_ctle",
        "native_eye_dfe",
        "native_eye_rx",
        "eye_chnl",
        "eye_tx",
        "eye_ctle",
        "eye_dfe",
        "eye_rx",
    ] {
        assert!(names.contains(name), "missing Web eye presentation {name}");
    }
    assert!(!names.contains("tx_impulse_v_per_v"));
    assert!(!names.contains("receiver_input_noise_v"));
    assert_eq!(report.output.metrics["eye_contour_count"], 3.0);
    for source_only_metric in [
        "effective_prbs_seed",
        "effective_noise_seed",
        "random_noise_sample_count",
    ] {
        assert!(
            !report.output.metrics.contains_key(source_only_metric),
            "{source_only_metric} must not leak into the source-compatible Web result"
        );
    }
    assert_eq!(
        report.output.arrays["eye_contour_ber"].as_slice(),
        &[1.0e-5, 1.0e-4, 1.0e-3]
    );
    for index in 0..3 {
        assert!(
            report
                .output
                .arrays
                .contains_key(&format!("eye_contour_{index}_x_ui"))
        );
        assert!(
            report
                .output
                .arrays
                .contains_key(&format!("eye_contour_{index}_y_v"))
        );
    }
    assert!(report.output.arrays["eye_contour_2_x_ui"].is_empty());
    assert!(report.output.arrays["eye_contour_2_y_v"].is_empty());
    assert!(report.metadata.get("output").is_none());
    assert_eq!(
        report
            .metadata
            .as_object()
            .unwrap()
            .keys()
            .map(String::as_str)
            .collect::<Vec<_>>(),
        [
            "arrays_file",
            "backend_metadata",
            "diagnostics",
            "effective_input",
            "input_file",
            "schema",
        ]
    );
    assert_eq!(
        report.metadata["effective_input"]["tx"]["modulation"],
        "nrz"
    );
    assert_eq!(report.metadata["schema"], "pybert.native-cli-result.v1");

    let _ = fs::remove_dir_all(root);
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
    let candidate = Command::new(env!("CARGO_BIN_EXE_sipi-pybert-direct"))
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
for metric in ("eye_distribution_state_count", "eye_height_at_ber_v"):
    assert metric in oracle_backend["metrics"] and metric in candidate_backend["metrics"]
    oracle_backend["metrics"].pop(metric)
    candidate_backend["metrics"].pop(metric)

def assert_equivalent(left, right, path=()):
    # These two values are preserved in their native locations but are an
    # independently observed statistical-eye mismatch, not presentation
    # adapter data.  Do not generalize this exception to the complete result.
    if path == ("statistical_eye", "height_at_ber_v"):
        assert isinstance(left, (int, float)) and isinstance(right, (int, float))
        return
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
