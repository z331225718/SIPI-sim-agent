#![cfg(feature = "pinned-python-tests")]

use std::{fs, path::PathBuf, process::Command};

use serde::Deserialize;
use sipi_pybert_direct::{Seconds, StatisticalEyeInputV1, Volts, calculate_statistical_eye};

const PINNED_PYBERT_COMMIT: &str = "5bf6d7ea0ace261891aaeb611ffc1c267e160afe";
const PINNED_GOLDEN_TREE: &str = "4de363247ca45a399d4dd0e69e8d7e71c4f2654e";
const GOLDEN_PATH: &str = "tests/golden/rust_migration/statistical_eye";

#[derive(Debug, Deserialize)]
struct GoldenCase {
    schema: String,
    name: String,
    input: GoldenInput,
    expected: GoldenExpected,
}

#[derive(Debug, Deserialize)]
struct GoldenInput {
    pulse_response: Vec<f64>,
    ui: f64,
    nspui: usize,
    target_ber: f64,
    noise_sigma_v: Option<f64>,
    horizontal_rj_ui: Option<f64>,
    horizontal_dj_ui: Option<f64>,
    tx_rj_ui: Option<f64>,
    tx_dj_ui: Option<f64>,
    tx_dcd_ui: Option<f64>,
    rx_rj_ui: Option<f64>,
    rx_dj_ui: Option<f64>,
    voltage_resolution_v: Option<f64>,
    time_points: usize,
    max_distribution_states: usize,
}

#[derive(Debug, Deserialize)]
struct GoldenExpected {
    level0_v: f64,
    level1_v: f64,
    eye_height_v: f64,
    eye_width_ps: f64,
    height_at_ber_v: f64,
    width_at_ber_ps: f64,
}

fn source_root() -> PathBuf {
    PathBuf::from(
        std::env::var_os("SIPI_PYBERT_ORACLE_ROOT")
            .expect("pinned-python-tests requires SIPI_PYBERT_ORACLE_ROOT"),
    )
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

fn assert_close(case: &str, field: &str, actual: f64, expected: f64) {
    // The pinned native tests allow a few nanovolts for the Gaussian/jitter
    // numerical integration path, while its deterministic scalar checks are
    // tighter. Keep that source-established integration envelope explicit.
    let tolerance = if field.ends_with("_v") {
        3.0e-9
    } else {
        1.0e-9
    };
    assert!(
        (actual - expected).abs() <= tolerance,
        "{case}.{field}: actual={actual:.17e}, expected={expected:.17e}, tolerance={tolerance:.17e}"
    );
}

#[test]
fn pinned_statistical_eye_goldens_match_the_reachable_rust_leaf() {
    let root = source_root();
    assert_eq!(
        git_output(&root, &["rev-parse", "HEAD^{commit}"]).trim(),
        PINNED_PYBERT_COMMIT
    );
    assert!(
        git_output(
            &root,
            &[
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
                "--",
                "src",
                GOLDEN_PATH
            ],
        )
        .is_empty(),
        "the pinned source and golden corpus must be clean"
    );
    assert_eq!(
        git_output(
            &root,
            &[
                "rev-parse",
                &format!("{PINNED_PYBERT_COMMIT}:{GOLDEN_PATH}")
            ],
        )
        .trim(),
        PINNED_GOLDEN_TREE
    );

    let corpus = root.join(GOLDEN_PATH);
    let mut paths = fs::read_dir(&corpus)
        .expect("read pinned golden corpus")
        .map(|entry| entry.expect("read golden entry").path())
        .filter(|path| {
            path.extension()
                .is_some_and(|extension| extension == "json")
        })
        .collect::<Vec<_>>();
    paths.sort();
    assert_eq!(paths.len(), 8, "unexpected golden corpus membership");

    for path in paths {
        let case: GoldenCase =
            serde_json::from_slice(&fs::read(&path).expect("read pinned statistical-eye golden"))
                .expect("parse pinned statistical-eye golden");
        assert_eq!(
            case.schema, "pybert.statistical-eye-golden.v1",
            "{:?}",
            path
        );
        assert_eq!(
            path.file_stem().and_then(|stem| stem.to_str()),
            Some(case.name.as_str()),
            "golden file name must bind its case name"
        );
        let input = &case.input;
        let actual = calculate_statistical_eye(StatisticalEyeInputV1 {
            pulse_response: &input.pulse_response,
            ui: Seconds(input.ui),
            nspui: input.nspui,
            target_ber: input.target_ber,
            noise_sigma_v: input.noise_sigma_v.map(Volts),
            horizontal_rj_ui: input.horizontal_rj_ui,
            horizontal_dj_ui: input.horizontal_dj_ui,
            tx_rj_ui: input.tx_rj_ui,
            tx_dj_ui: input.tx_dj_ui,
            tx_dcd_ui: input.tx_dcd_ui,
            rx_rj_ui: input.rx_rj_ui,
            rx_dj_ui: input.rx_dj_ui,
            voltage_resolution: input.voltage_resolution_v.map(Volts),
            time_points: input.time_points,
            max_distribution_states: input.max_distribution_states,
        })
        .unwrap_or_else(|error| panic!("{}: {error}", case.name));
        assert_close(
            &case.name,
            "level0_v",
            actual.level0_v,
            case.expected.level0_v,
        );
        assert_close(
            &case.name,
            "level1_v",
            actual.level1_v,
            case.expected.level1_v,
        );
        assert_close(
            &case.name,
            "eye_height_v",
            actual.eye_height_v,
            case.expected.eye_height_v,
        );
        assert_close(
            &case.name,
            "eye_width_ps",
            actual.eye_width_ps,
            case.expected.eye_width_ps,
        );
        assert_close(
            &case.name,
            "height_at_ber_v",
            actual.height_at_ber_v,
            case.expected.height_at_ber_v,
        );
        assert_close(
            &case.name,
            "width_at_ber_ps",
            actual.width_at_ber_ps,
            case.expected.width_at_ber_ps,
        );
    }
}
