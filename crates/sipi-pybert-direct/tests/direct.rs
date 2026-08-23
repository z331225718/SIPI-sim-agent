use std::{collections::BTreeMap, fs, io::Read};

use flate2::read::DeflateDecoder;

use sipi_pybert_direct::{
    AdditiveNoiseV1, AnalysisConfigV1, ArrayDTypeV1, ChannelInputV1, ChannelResponseV1,
    FfeConfigV1, Hertz, ModulationV1, NumericArrayV1, Ohms, PatternV1, ResourceLimitsV1,
    RxConfigV1, SIMULATION_SCHEMA_V1, Seconds, SimulationInputV1, TxConfigV1, TypedArrayV1, Volts,
    npz_bytes_nd, npz_bytes_typed_nd, run_sim_native_json, strict_simulation_input_json,
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
            jitter_rel_thresh: None,
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
fn artifact_keeps_explicit_noise_distinct_from_seeded_noise() {
    let root = std::env::temp_dir().join(format!(
        "sipi-pybert-direct-explicit-noise-{}",
        std::process::id()
    ));
    let _ = fs::remove_dir_all(&root);
    fs::create_dir_all(&root).expect("root");
    let input_path = root.join("input.json");
    let output_path = root.join("out");
    let mut request = input();
    request.tx.additive_noise = Some(AdditiveNoiseV1 {
        samples_v: vec![1.0e-3; 32],
        effective_seed: None,
    });
    let json = serde_json::to_vec(&request).expect("serialize");
    fs::write(&input_path, &json).expect("input");
    let report = run_sim_native_json(&json, &input_path, &output_path).expect("run");
    assert_eq!(
        report.metadata["effective_randomness"]["noise"]["source"],
        "explicit_samples"
    );
    assert!(report.metadata["effective_randomness"]["noise"]["effective_seed"].is_null());
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

#[test]
fn npz_artifact_uses_deflate_and_preserves_two_dimensional_shape() {
    let arrays = BTreeMap::from([(
        "eye_dfe".into(),
        NumericArrayV1 {
            shape: vec![2, 3],
            values: vec![0.0, 1.0, 2.0, 3.0, 4.0, 5.0],
        },
    )]);
    let bytes = npz_bytes_nd(&arrays).expect("valid 2-D NPZ");
    assert_eq!(&bytes[..4], b"PK\x03\x04");
    assert_eq!(
        u16::from_le_bytes([bytes[8], bytes[9]]),
        8,
        "deflate method"
    );
    let compressed_size =
        u32::from_le_bytes(bytes[18..22].try_into().expect("local compressed size")) as usize;
    let name_len = u16::from_le_bytes([bytes[26], bytes[27]]) as usize;
    let extra_len = u16::from_le_bytes([bytes[28], bytes[29]]) as usize;
    let payload_start = 30 + name_len + extra_len;
    let mut decoder = DeflateDecoder::new(&bytes[payload_start..payload_start + compressed_size]);
    let mut npy = Vec::new();
    decoder
        .read_to_end(&mut npy)
        .expect("decompress NPY member");
    let marker = b"'shape': (2, 3), ";
    assert!(npy.windows(marker.len()).any(|window| window == marker));
}

#[test]
fn typed_npz_artifact_preserves_bool_int_float_dtypes_and_shapes() {
    let arrays = BTreeMap::from([
        (
            "bool_decisions".into(),
            TypedArrayV1 {
                shape: vec![2, 2],
                values: vec![1.0, 0.0, 0.0, 1.0],
                dtype: ArrayDTypeV1::Bool,
            },
        ),
        (
            "int_indices".into(),
            TypedArrayV1 {
                shape: vec![2],
                values: vec![2.0, 7.0],
                dtype: ArrayDTypeV1::Int64,
            },
        ),
        (
            "eye".into(),
            TypedArrayV1 {
                shape: vec![2, 2],
                values: vec![0.0, 0.25, 0.5, 0.75],
                dtype: ArrayDTypeV1::Float64,
            },
        ),
    ]);
    let bytes = npz_bytes_typed_nd(&arrays).expect("valid typed NPZ");
    assert_eq!(&bytes[..4], b"PK\x03\x04");
    let mut offset = 0usize;
    let mut npy_members = Vec::new();
    while offset + 30 <= bytes.len() && &bytes[offset..offset + 4] == b"PK\x03\x04" {
        let compressed_size =
            u32::from_le_bytes(bytes[offset + 18..offset + 22].try_into().unwrap()) as usize;
        let name_len = u16::from_le_bytes([bytes[offset + 26], bytes[offset + 27]]) as usize;
        let extra_len = u16::from_le_bytes([bytes[offset + 28], bytes[offset + 29]]) as usize;
        let payload_start = offset + 30 + name_len + extra_len;
        let mut decoder =
            DeflateDecoder::new(&bytes[payload_start..payload_start + compressed_size]);
        let mut npy = Vec::new();
        decoder.read_to_end(&mut npy).unwrap();
        npy_members.push(npy);
        offset = payload_start + compressed_size;
    }
    assert_eq!(npy_members.len(), 3);
    assert!(npy_members.iter().any(|npy| {
        npy.windows(b"'descr': '|b1'".len())
            .any(|w| w == b"'descr': '|b1'")
    }));
    assert!(npy_members.iter().any(|npy| {
        npy.windows(b"'descr': '<i8'".len())
            .any(|w| w == b"'descr': '<i8'")
    }));
    assert!(npy_members.iter().any(|npy| {
        npy.windows(b"'descr': '<f8'".len())
            .any(|w| w == b"'descr': '<f8'")
    }));
    assert!(npy_members.iter().any(|npy| {
        npy.windows(b"'shape': (2, 2), ".len())
            .any(|w| w == b"'shape': (2, 2), ")
    }));
}
