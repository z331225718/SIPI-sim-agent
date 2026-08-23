use std::{collections::BTreeMap, fs, path::PathBuf};

use serde::Deserialize;
use sipi_pybert_direct::{
    ChannelInputV1, LegacyRuntimeError, LegacySimRequestV1, ModulationV1, project_legacy_config_v1,
    run_legacy_sim_v1, simulate_native_v1,
};

const EXPECTED_ITEM_NAMES: [&str; 23] = [
    "chnl_h",
    "tx_out_h",
    "ctle_out_h",
    "dfe_out_h",
    "chnl_s",
    "tx_s",
    "ctle_s",
    "dfe_s",
    "tx_out_s",
    "ctle_out_s",
    "dfe_out_s",
    "chnl_p",
    "tx_out_p",
    "ctle_out_p",
    "dfe_out_p",
    "chnl_H",
    "tx_H",
    "ctle_H",
    "dfe_H",
    "tx_out_H",
    "ctle_out_H",
    "dfe_out_H",
    "tx_out",
];

#[derive(Deserialize)]
struct LegacyPickleProbe {
    schema: String,
    item_names: Vec<String>,
    arrays: BTreeMap<String, Vec<f64>>,
}

fn projection_yaml(extra: &str) -> String {
    format!(
        r#"!!python/object:pybert.configuration.PyBertCfg
bit_rate: 10.0
nbits: 1000
pattern: PRBS-7
seed: 17
nspui: 2
{}
"#,
        extra
    )
}

fn write_s2p(root: &std::path::Path, name: &str) -> std::path::PathBuf {
    let path = root.join(name);
    fs::write(
        &path,
        "# GHz S RI R 50\n0 0 0 1 0 0 0 0 0\n1 0 0 0.8 0.1 0 0 0 0\n2 0 0 0.5 0.2 0 0 0 0\n",
    )
    .unwrap();
    path
}

#[test]
fn pinned_legacy_fixture_runs_in_rust_and_writes_python_pickle_dict() {
    let fixture = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("fixtures")
        .join("pb-01-legacy-nrz.yaml");
    let root = std::env::temp_dir().join(format!("sipi-pb01-runtime-{}", std::process::id()));
    let _ = fs::remove_dir_all(&root);
    fs::create_dir_all(&root).unwrap();
    let result = root.join("fixture.pybert_data");
    let report = run_legacy_sim_v1(&LegacySimRequestV1 {
        config_file: fixture,
        results: Some(result.clone()),
    })
    .unwrap();
    assert_eq!(report.input.timebase.nbits, 1_000);
    assert!(report.output.arrays.contains_key("channel_impulse_v_per_v"));
    let bytes = fs::read(&result).unwrap();
    assert_eq!(&bytes[..2], b"\x80\x03");
    let payload: LegacyPickleProbe =
        serde_pickle::from_slice(&bytes, serde_pickle::DeOptions::default()).unwrap();
    assert_eq!(payload.schema, "sipi.pybert_data.v1");
    assert_eq!(payload.item_names, EXPECTED_ITEM_NAMES);
    assert_eq!(
        payload
            .arrays
            .keys()
            .map(String::as_str)
            .collect::<Vec<_>>(),
        EXPECTED_ITEM_NAMES
            .iter()
            .copied()
            .collect::<std::collections::BTreeSet<_>>()
            .into_iter()
            .collect::<Vec<_>>()
    );
    for name in EXPECTED_ITEM_NAMES.iter() {
        assert!(
            !payload.arrays[*name].is_empty(),
            "{name} must be populated"
        );
    }
    for name in EXPECTED_ITEM_NAMES
        .iter()
        .filter(|name| name.ends_with("_H"))
    {
        assert!(
            !payload.arrays[*name].is_empty(),
            "{name} must be populated"
        );
    }
    assert_ne!(
        payload.arrays["ctle_out_h"], payload.arrays["dfe_out_h"],
        "DFE output response must not alias CTLE output"
    );
    assert_ne!(
        payload.arrays["ctle_out_H"], payload.arrays["dfe_out_H"],
        "DFE frequency response must not alias CTLE frequency response"
    );
    let _ = fs::remove_dir_all(root);
}

#[test]
fn projection_covers_portable_modulation_noise_and_viterbi_fields() {
    let root = std::env::temp_dir().join(format!("sipi-pb03-projection-{}", std::process::id()));
    let _ = fs::remove_dir_all(&root);
    fs::create_dir_all(&root).unwrap();
    let config_path = root.join("pam4.yaml");
    fs::write(
        &config_path,
        projection_yaml(
            "mod_type: PAM-4\npn_mag: 0.001\npn_freq: 1000.0\nrn: 0.001\nrx_use_viterbi: true\nrx_viterbi_symbols: 2\ndfe_tap_tuners:\n- !!python/tuple [true, -0.2, 0.2]",
        ),
    )
    .unwrap();
    let (_, input) = project_legacy_config_v1(&config_path, "portable-fields").unwrap();
    assert!(matches!(input.modulation, ModulationV1::Pam4));
    assert_eq!(input.timebase.data_rate.0, 5.0e9);
    assert_eq!(input.timebase.sample_interval.0, 100.0e-12);
    assert_eq!(input.analysis.jitter_eye_uis, Some(5_080));
    assert_eq!(
        input.tx.additive_noise.as_ref().unwrap().samples_v.len(),
        1000
    );
    assert!(input.tx.additive_noise.is_some());
    assert!(input.tx.periodic_noise.is_some());
    assert!(input.rx.viterbi_enabled);
    assert!(
        input
            .rx
            .viterbi
            .as_ref()
            .is_some_and(|viterbi| !viterbi.fec)
    );
    assert!(input.rx.dfe.is_some());
    assert_eq!(
        input
            .rx
            .dfe
            .as_ref()
            .and_then(|dfe| dfe.tap_limits.as_ref())
            .map(Vec::len),
        Some(1)
    );
    let fec_path = root.join("pam4-fec.yaml");
    fs::write(
        &fec_path,
        projection_yaml(
            "mod_type: PAM-4\nrx_use_viterbi: true\nrx_viterbi_fec: true\ndfe_tap_tuners:\n- !!python/tuple [true, -0.2, 0.2]",
        ),
    )
    .unwrap();
    let (_, fec_input) = project_legacy_config_v1(&fec_path, "portable-fec").unwrap();
    assert!(matches!(fec_input.modulation, ModulationV1::Pam4));
    assert_eq!(fec_input.timebase.data_rate.0, 10.0e9);
    assert_eq!(fec_input.timebase.sample_interval.0, 50.0e-12);
    assert_eq!(
        fec_input
            .tx
            .additive_noise
            .as_ref()
            .unwrap()
            .samples_v
            .len(),
        2000
    );
    assert!(
        fec_input
            .rx
            .viterbi
            .as_ref()
            .is_some_and(|viterbi| viterbi.fec && viterbi.noise_sigma_v.is_none())
    );
    for (name, value) in [("nrz", "NRZ"), ("duo", "Duo-binary")] {
        let path = root.join(format!("{name}.yaml"));
        fs::write(&path, projection_yaml(&format!("mod_type: {value}"))).unwrap();
        let (_, projected) = project_legacy_config_v1(&path, name).unwrap();
        assert!(matches!(
            (name, projected.modulation),
            ("nrz", ModulationV1::Nrz) | ("duo", ModulationV1::DuoBinary)
        ));
    }
    let _ = fs::remove_dir_all(root);
}

#[test]
fn legacy_thresh_is_projected_and_changes_native_jitter_threshold() {
    let root = std::env::temp_dir().join(format!("sipi-pb03-thresh-{}", std::process::id()));
    let _ = fs::remove_dir_all(&root);
    fs::create_dir_all(&root).unwrap();
    let default_path = root.join("default.yaml");
    let explicit_path = root.join("explicit.yaml");
    let fixture = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("fixtures")
        .join("pb-01-legacy-nrz.yaml");
    let fixture_text = fs::read_to_string(&fixture).unwrap();
    fs::write(&default_path, &fixture_text).unwrap();
    fs::write(&explicit_path, format!("{fixture_text}thresh: 7.5\n")).unwrap();
    let (default_projection, default_input) =
        project_legacy_config_v1(&default_path, "threshold-default").unwrap();
    let (explicit_projection, explicit_input) =
        project_legacy_config_v1(&explicit_path, "threshold-explicit").unwrap();
    assert_eq!(default_projection.jitter_rel_thresh, 3.0);
    assert_eq!(default_input.analysis.jitter_rel_thresh, Some(3.0));
    assert_eq!(explicit_projection.jitter_rel_thresh, 7.5);
    assert_eq!(explicit_input.analysis.jitter_rel_thresh, Some(7.5));
    let default_output = simulate_native_v1(&default_input).unwrap();
    let explicit_output = simulate_native_v1(&explicit_input).unwrap();
    assert_ne!(
        default_output.arrays["jitter_threshold"], explicit_output.arrays["jitter_threshold"],
        "legacy thresh must reach spectral jitter classification"
    );
    let _ = fs::remove_dir_all(root);
}

#[test]
fn projection_parses_portable_s2p_channel_and_ctle_files() {
    let root = std::env::temp_dir().join(format!("sipi-pb03-s2p-{}", std::process::id()));
    let _ = fs::remove_dir_all(&root);
    fs::create_dir_all(&root).unwrap();
    let _ = write_s2p(&root, "channel.s2p");
    let _ = write_s2p(&root, "ctle.s2p");
    let config_path = root.join("s2p.yaml");
    fs::write(
        &config_path,
        projection_yaml(
            "use_ch_file: true\nch_file: channel.s2p\nuse_ctle_file: true\nctle_file: ctle.s2p",
        ),
    )
    .unwrap();
    let (_, input) = project_legacy_config_v1(&config_path, "portable-s2p").unwrap();
    assert!(matches!(input.channel, ChannelInputV1::ImpulseResponse(_)));
    assert!(
        input
            .rx
            .ctle
            .as_ref()
            .and_then(|ctle| ctle.impulse_response_v_per_v.as_ref())
            .is_some_and(|impulse| !impulse.is_empty())
    );
    let _ = fs::remove_dir_all(root);
}

#[test]
fn projection_keeps_ami_external_boundary_fail_closed() {
    let root = std::env::temp_dir().join(format!("sipi-pb03-external-{}", std::process::id()));
    let _ = fs::remove_dir_all(&root);
    fs::create_dir_all(&root).unwrap();
    let config_path = root.join("ami.yaml");
    fs::write(
        &config_path,
        projection_yaml("tx_use_ami: true\ntx_ami_file: tx.ami"),
    )
    .unwrap();
    assert!(matches!(
        project_legacy_config_v1(&config_path, "external"),
        Err(LegacyRuntimeError::Unsupported(message)) if message.contains("tx_use_ami")
    ));
    let _ = fs::remove_dir_all(root);
}

#[test]
fn projection_decodes_bounded_pybert_cfg_pickle_state_without_python() {
    let root = std::env::temp_dir().join(format!("sipi-pb03-pickle-{}", std::process::id()));
    let _ = fs::remove_dir_all(&root);
    fs::create_dir_all(&root).unwrap();
    let config_path = root.join("portable.pybert_cfg");
    let pickle = [
        0x80, 0x03, 0x63, 0x70, 0x79, 0x62, 0x65, 0x72, 0x74, 0x2e, 0x63, 0x6f, 0x6e, 0x66, 0x69,
        0x67, 0x75, 0x72, 0x61, 0x74, 0x69, 0x6f, 0x6e, 0x0a, 0x50, 0x79, 0x42, 0x65, 0x72, 0x74,
        0x43, 0x66, 0x67, 0x0a, 0x71, 0x00, 0x29, 0x81, 0x71, 0x01, 0x7d, 0x71, 0x02, 0x28, 0x58,
        0x08, 0x00, 0x00, 0x00, 0x62, 0x69, 0x74, 0x5f, 0x72, 0x61, 0x74, 0x65, 0x71, 0x03, 0x47,
        0x40, 0x24, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x58, 0x05, 0x00, 0x00, 0x00, 0x6e, 0x62,
        0x69, 0x74, 0x73, 0x71, 0x04, 0x4d, 0xe8, 0x03, 0x58, 0x07, 0x00, 0x00, 0x00, 0x70, 0x61,
        0x74, 0x74, 0x65, 0x72, 0x6e, 0x71, 0x05, 0x58, 0x06, 0x00, 0x00, 0x00, 0x50, 0x52, 0x42,
        0x53, 0x2d, 0x37, 0x71, 0x06, 0x58, 0x04, 0x00, 0x00, 0x00, 0x73, 0x65, 0x65, 0x64, 0x71,
        0x07, 0x4b, 0x11, 0x58, 0x05, 0x00, 0x00, 0x00, 0x6e, 0x73, 0x70, 0x75, 0x69, 0x71, 0x08,
        0x4b, 0x02, 0x75, 0x62, 0x2e,
    ];
    fs::write(&config_path, pickle).unwrap();
    let (_, input) = project_legacy_config_v1(&config_path, "pickle-config").unwrap();
    assert_eq!(input.timebase.nbits, 1_000);
    assert!(matches!(input.modulation, ModulationV1::Nrz));
    assert_eq!(input.tx.ffe.weights.len(), 7);
    let _ = fs::remove_dir_all(root);
}
