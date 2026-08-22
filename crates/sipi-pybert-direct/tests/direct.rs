use std::{collections::BTreeMap, fs};

use sipi_pybert_direct::{
    AnalysisConfigV1, ChannelInputV1, ChannelResponseV1, FfeConfigV1, Hertz, ModulationV1, Ohms,
    PatternV1, ResourceLimitsV1, RxConfigV1, SIMULATION_SCHEMA_V1, Seconds, SimulationInputV1,
    TxConfigV1, Volts, run_sim_native_json, strict_simulation_input_json,
};

fn input() -> SimulationInputV1 {
    SimulationInputV1 {
        schema: SIMULATION_SCHEMA_V1.into(),
        run_id: "direct-pb-02-test".into(),
        modulation: ModulationV1::Nrz,
        pattern: PatternV1::Prbs { order: 7, seed: 17 },
        timebase: sipi_pybert_direct::TimebaseV1 {
            sample_interval: Seconds(1.0e-12),
            samples_per_ui: 2,
            data_rate: Hertz(500.0e9),
            nbits: 16,
        },
        channel: ChannelInputV1::ImpulseResponse(ChannelResponseV1 {
            sample_interval: Seconds(1.0e-12),
            impulse_response_volts_per_second: vec![1.0e12, 0.25e12],
            source_impedance: Ohms(50.0),
            load_impedance: Ohms(50.0),
        }),
        tx: TxConfigV1 {
            amplitude: Volts(0.5),
            ffe: FfeConfigV1::default(),
            additive_noise: None,
            periodic_noise: None,
        },
        rx: RxConfigV1 {
            native_ctle_enabled: false,
            ctle: None,
            ffe: FfeConfigV1::default(),
            dfe_taps: 0,
            dfe: None,
            viterbi_enabled: false,
            viterbi: None,
        },
        analysis: AnalysisConfigV1 {
            statistical_eye: None,
            include_jitter: false,
            include_bathtub: false,
            ber_eye_bits: None,
            jitter_eye_uis: None,
        },
        limits: ResourceLimitsV1::default(),
        external_models: vec![],
        legacy_options: BTreeMap::new(),
    }
}

#[test]
fn strict_boundary_rejects_unknown_top_level_field() {
    let mut value = serde_json::to_value(input()).expect("input json");
    value
        .as_object_mut()
        .expect("object")
        .insert("silentFallback".into(), true.into());
    let error = strict_simulation_input_json(serde_json::to_string(&value).unwrap().as_bytes())
        .expect_err("unknown field must be rejected");
    assert_eq!(error.code(), "invalid_input");
    assert!(error.to_string().contains("silentFallback"));
}

#[test]
fn direct_run_writes_upstream_artifact_names_and_metadata() {
    let root = std::env::temp_dir().join(format!("sipi-pybert-direct-{}", std::process::id()));
    let _ = fs::remove_dir_all(&root);
    fs::create_dir_all(&root).expect("root");
    let input_path = root.join("input.json");
    let output_path = root.join("out");
    let json = serde_json::to_vec(&input()).expect("serialize");
    fs::write(&input_path, &json).expect("input");
    let report = run_sim_native_json(&json, &input_path, &output_path).expect("run");
    assert_eq!(report.meta_path, output_path.join("meta.json"));
    assert_eq!(report.arrays_path, output_path.join("arrays.npz"));
    assert_eq!(report.metadata["arrays_file"], "arrays.npz");
    assert_eq!(
        report.metadata["backend_metadata"]["engine"]["backend"],
        "rust"
    );
    assert_eq!(report.diagnostics["pipeline"], "typed_simulation_input_v1");
    assert!(output_path.join("meta.json").is_file());
    assert!(output_path.join("arrays.npz").is_file());
    assert!(fs::metadata(output_path.join("arrays.npz")).unwrap().len() > 22);
    let _ = fs::remove_dir_all(root);
}

#[test]
fn strict_boundary_preserves_legacy_options_as_explicit_compatibility_map() {
    let mut value = serde_json::to_value(input()).expect("input json");
    value["legacyOptions"] = serde_json::json!({"caller_note": "not consumed"});
    let parsed = strict_simulation_input_json(serde_json::to_string(&value).unwrap().as_bytes())
        .expect("legacy options are a declared field");
    assert_eq!(parsed.legacy_options["caller_note"], "not consumed");
}

#[test]
fn strict_boundary_rejects_non_object_channel_value() {
    let mut value = serde_json::to_value(input()).expect("input json");
    value["channel"]["value"] = serde_json::Value::Null;
    let error = strict_simulation_input_json(serde_json::to_string(&value).unwrap().as_bytes())
        .expect_err("channel value must be an object");
    assert_eq!(error.code(), "invalid_input");
}
