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
    assert_eq!(names.len(), 140);
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
    assert!(report.output.arrays.contains_key("tx_impulse_v_per_v"));
    assert!(report.output.arrays.contains_key("receiver_input_noise_v"));
    assert!(report.metadata["output"]["arrays"]["chnl_p"].is_array());
    assert_eq!(report.metadata["schema"], "pybert.native-cli-result.v1");

    let _ = fs::remove_dir_all(root);
}
