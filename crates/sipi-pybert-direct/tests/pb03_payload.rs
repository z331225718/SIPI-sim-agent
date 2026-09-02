use std::{collections::BTreeSet, fs, path::PathBuf};

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
