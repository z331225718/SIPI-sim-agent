use std::{collections::BTreeMap, fs, io::Read};

use flate2::read::DeflateDecoder;
use serde_json::json;

use sipi_pybert_direct::{
    AdditiveNoiseV1, AnalysisConfigV1, ArrayDTypeV1, ArtifactRefV1, ChannelInputV1,
    ChannelResponseV1, FfeConfigV1, Hertz, ModulationV1, NumericArrayV1, Ohms, PatternV1,
    ResourceLimitsV1, RxConfigV1, SIMULATION_SCHEMA_V1, Seconds, SimulationInputV1,
    SimulationOutputV1, TxConfigV1, TypedArrayV1, Volts, npz_bytes_nd, npz_bytes_typed_nd,
    run_sim_native_json, sha256_bytes, simulate_native_v1, strict_simulation_input_json,
    write_simulation_artifacts, write_simulation_artifacts_with_schema_and_backend,
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
    assert_eq!(
        report
            .metadata
            .as_object()
            .expect("upstream metadata object")
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
    assert_eq!(report.metadata["arrays_file"], "arrays.npz");
    assert_eq!(
        report.metadata["backend_metadata"]["engine"]["backend"],
        "rust"
    );
    assert_eq!(
        report.metadata["backend_metadata"]["schema"],
        report.output.schema
    );
    assert_eq!(
        report.metadata["backend_metadata"]["run_id"],
        report.output.run_id
    );
    assert_eq!(
        report.metadata["backend_metadata"]["metrics"],
        serde_json::to_value(&report.output.metrics).expect("metrics")
    );
    assert_eq!(
        report.metadata["diagnostics"]["capabilities"],
        serde_json::to_value(&report.output.capabilities.stages).expect("stages")
    );
    assert_eq!(
        report.metadata["diagnostics"]["events"],
        serde_json::to_value(&report.output.events).expect("events")
    );
    assert!(
        report.metadata["backend_metadata"]["metrics"]
            .get("effective_prbs_seed")
            .is_none()
    );
    assert_eq!(
        report.metadata["backend_metadata"]["engine"]["name"],
        "pybert-python"
    );
    assert_eq!(
        report.metadata["backend_metadata"]["engine"]["build"]["profile"],
        "debug"
    );
    assert!(
        report.metadata["effective_input"]["analysis"]
            .get("jitterRelThresh")
            .is_none()
    );
    assert!(
        report.metadata["input_file"]
            .as_str()
            .expect("source path")
            .ends_with("input.json")
    );
    assert!(!report.output.arrays.contains_key("tx_impulse_v_per_v"));
    assert_eq!(report.diagnostics["pipeline"], "typed_simulation_input_v1");
    assert!(output_path.join("meta.json").is_file());
    assert!(output_path.join("arrays.npz").is_file());
    assert!(fs::metadata(output_path.join("arrays.npz")).unwrap().len() > 22);
    let _ = fs::remove_dir_all(root);
}

#[test]
fn reserved_workflow_extras_cannot_shadow_nested_or_flat_output() {
    let root = std::env::temp_dir().join(format!(
        "sipi-pybert-direct-reserved-extra-{}",
        std::process::id()
    ));
    let _ = fs::remove_dir_all(&root);
    fs::create_dir_all(&root).expect("root");
    let input_path = root.join("input.json");
    let output_path = root.join("out");
    let request = input();
    let input_json = serde_json::to_vec(&request).expect("serialize input");
    fs::write(&input_path, &input_json).expect("input");
    let baseline = run_sim_native_json(&input_json, &input_path, &output_path).expect("run");
    let safe_output_path = root.join("safe-out");
    let report = write_simulation_artifacts_with_schema_and_backend(
        request,
        &input_path,
        &safe_output_path,
        baseline.output.clone(),
        Some(json!({
            "pipeline": "evil-pipeline",
            "capabilities": ["evil-capability"],
            "events": [{"stage": "evil-event"}],
            "comparison": {"marker": true}
        })),
        "pybert.native-cli-result.v1",
        "rust",
        Some(json!({
            "schema": "evil-schema",
            "output": {"schema": "evil-output"},
            "backend_metadata": {"engine": {"backend": "evil-backend"}},
            "safe_marker": true
        })),
    )
    .expect("reserved extras are isolated");

    let nested = serde_json::from_value::<SimulationOutputV1>(report.metadata["output"].clone())
        .expect("nested output");
    assert_eq!(nested, baseline.output);
    assert_eq!(
        report.metadata["backend_metadata"]["metrics"],
        report.metadata["output"]["metrics"]
    );
    assert_eq!(
        report.metadata["diagnostics"]["capabilities"],
        report.metadata["output"]["capabilities"]["stages"]
    );
    assert_eq!(
        report.metadata["diagnostics"]["events"],
        report.metadata["output"]["events"]
    );
    assert_eq!(
        report.metadata["diagnostics"]["pipeline"],
        "typed_simulation_input_v1"
    );
    assert_eq!(report.metadata["diagnostics"]["comparison"]["marker"], true);
    assert_eq!(report.metadata["safe_marker"], true);
    assert_eq!(
        report.metadata["workflow_metadata"]["output"]["schema"],
        "evil-output"
    );
    assert_eq!(
        report.metadata["workflow_metadata"]["backend_metadata"]["engine"]["backend"],
        "evil-backend"
    );
    assert_eq!(
        report.metadata["workflow_diagnostics"]["pipeline"],
        "evil-pipeline"
    );
    assert_eq!(
        report.metadata["workflow_diagnostics"]["capabilities"],
        json!(["evil-capability"])
    );
    assert_eq!(
        report.metadata["workflow_diagnostics"]["events"],
        json!([{"stage": "evil-event"}])
    );
    let _ = fs::remove_dir_all(root);
}

#[test]
fn non_empty_artifact_refs_round_trip_and_native_arrays_match_npz() {
    let root = std::env::temp_dir().join(format!(
        "sipi-pybert-direct-artifact-ref-{}",
        std::process::id()
    ));
    let _ = fs::remove_dir_all(&root);
    fs::create_dir_all(&root).expect("root");
    let input_path = root.join("input.json");
    let output_path = root.join("out");
    let request = input();
    let input_json = serde_json::to_vec(&request).expect("serialize input");
    fs::write(&input_path, &input_json).expect("input");
    let baseline =
        run_sim_native_json(&input_json, &input_path, &root.join("baseline")).expect("run");
    fs::create_dir_all(&output_path).expect("output");
    let payload = b"artifact-ref-payload-v1";
    let payload_path = output_path.join("payload.bin");
    fs::write(&payload_path, payload).expect("payload");
    let mut output = baseline.output.clone();
    output.artifacts.push(ArtifactRefV1 {
        name: "payload".into(),
        schema: "pybert.payload.v1".into(),
        relative_path: "payload.bin".into(),
        mime_type: "application/octet-stream".into(),
        sha256: sha256_bytes(payload),
        byte_length: payload.len() as u64,
    });
    let report =
        write_simulation_artifacts(request, &input_path, &output_path, output.clone(), None)
            .expect("artifact ref output");
    let disk_metadata: serde_json::Value =
        serde_json::from_slice(&fs::read(&report.meta_path).expect("meta on disk"))
            .expect("valid metadata");
    let disk_output = serde_json::from_value::<SimulationOutputV1>(disk_metadata["output"].clone())
        .expect("typed output on disk");
    assert_eq!(disk_output, output);
    let artifact = &disk_output.artifacts[0];
    assert_eq!(artifact.name, "payload");
    assert_eq!(artifact.schema, "pybert.payload.v1");
    assert_eq!(artifact.relative_path, "payload.bin");
    assert_eq!(artifact.mime_type, "application/octet-stream");
    assert_eq!(artifact.sha256, sha256_bytes(payload));
    assert_eq!(artifact.byte_length, payload.len() as u64);
    assert_eq!(
        fs::metadata(&payload_path).expect("payload metadata").len(),
        artifact.byte_length
    );
    assert_eq!(
        sha256_bytes(&fs::read(&payload_path).expect("payload bytes")),
        artifact.sha256
    );

    let expected_arrays = output
        .arrays
        .iter()
        .map(|(name, values)| {
            (
                name.clone(),
                NumericArrayV1 {
                    shape: vec![values.len()],
                    values: values.clone(),
                },
            )
        })
        .collect::<BTreeMap<_, _>>();
    assert_eq!(
        fs::read(&report.arrays_path).expect("arrays on disk"),
        npz_bytes_nd(&expected_arrays).expect("expected native NPZ")
    );
    let _ = fs::remove_dir_all(root);
}

#[test]
fn metadata_preflight_rejects_large_nested_arrays_before_materialization() {
    let root = std::env::temp_dir().join(format!(
        "sipi-pybert-direct-metadata-preflight-{}",
        std::process::id()
    ));
    let _ = fs::remove_dir_all(&root);
    fs::create_dir_all(&root).expect("root");
    let input_path = root.join("input.json");
    let output_path = root.join("out");
    let request = input();
    fs::write(
        &input_path,
        serde_json::to_vec(&request).expect("input json"),
    )
    .expect("input");
    let output = SimulationOutputV1 {
        schema: SIMULATION_SCHEMA_V1.into(),
        run_id: "oversized-output".into(),
        capabilities: sipi_pybert_direct::EngineCapabilitiesV1 {
            stages: Vec::new(),
            external_models: Vec::new(),
        },
        metrics: BTreeMap::new(),
        events: Vec::new(),
        arrays: BTreeMap::from([("huge".into(), vec![0.0; 5_000_000])]),
        artifacts: Vec::new(),
    };
    let error = write_simulation_artifacts(request, &input_path, &output_path, output, None)
        .expect_err("large nested output must fail closed");
    assert!(error.to_string().contains("preflight"));
    assert!(
        !output_path.exists(),
        "preflight runs before output allocation"
    );
    let _ = fs::remove_dir_all(root);
}

#[test]
fn metadata_preflight_counts_metrics_projection_before_materialization() {
    let root = std::env::temp_dir().join(format!(
        "sipi-pybert-direct-metadata-metrics-preflight-{}",
        std::process::id()
    ));
    let _ = fs::remove_dir_all(&root);
    fs::create_dir_all(&root).expect("root");
    let input_path = root.join("input.json");
    let output_path = root.join("out");
    let request = input();
    fs::write(
        &input_path,
        serde_json::to_vec(&request).expect("input json"),
    )
    .expect("input");
    let metrics = (0..300_000)
        .map(|index| (format!("metric_{index:06}"), 1.0))
        .collect::<BTreeMap<_, _>>();
    let output = SimulationOutputV1 {
        schema: SIMULATION_SCHEMA_V1.into(),
        run_id: "oversized-metrics".into(),
        capabilities: sipi_pybert_direct::EngineCapabilitiesV1 {
            stages: Vec::new(),
            external_models: Vec::new(),
        },
        metrics,
        events: Vec::new(),
        arrays: BTreeMap::new(),
        artifacts: Vec::new(),
    };
    let error = write_simulation_artifacts(request, &input_path, &output_path, output, None)
        .expect_err("large duplicated metrics must fail closed");
    assert!(error.to_string().contains("preflight"));
    assert!(
        !output_path.exists(),
        "preflight runs before output allocation"
    );
    let _ = fs::remove_dir_all(root);
}

#[test]
fn metadata_preflight_counts_capabilities_and_events_projection_before_materialization() {
    let root = std::env::temp_dir().join(format!(
        "sipi-pybert-direct-metadata-events-preflight-{}",
        std::process::id()
    ));
    let _ = fs::remove_dir_all(&root);
    fs::create_dir_all(&root).expect("root");
    let input_path = root.join("input.json");
    let output_path = root.join("out");
    let request = input();
    fs::write(
        &input_path,
        serde_json::to_vec(&request).expect("input json"),
    )
    .expect("input");
    let stages = vec![
        sipi_pybert_direct::RunStageV1::Validate,
        sipi_pybert_direct::RunStageV1::ChannelResponse,
        sipi_pybert_direct::RunStageV1::TxProcessing,
        sipi_pybert_direct::RunStageV1::RxEqualization,
        sipi_pybert_direct::RunStageV1::DfeAdaptation,
        sipi_pybert_direct::RunStageV1::ViterbiFec,
        sipi_pybert_direct::RunStageV1::JitterAnalysis,
        sipi_pybert_direct::RunStageV1::StatisticalEye,
        sipi_pybert_direct::RunStageV1::ResultAssembly,
    ];
    let message = "e".repeat(1_000_000);
    let events = stages
        .iter()
        .enumerate()
        .map(|(sequence, stage)| sipi_pybert_direct::RunEventV1 {
            run_id: "oversized-events".into(),
            sequence: sequence as u64,
            stage: *stage,
            stage_progress: 1.0,
            total_progress: (sequence + 1) as f64 / stages.len() as f64,
            message: Some(message.clone()),
        })
        .collect();
    let output = SimulationOutputV1 {
        schema: SIMULATION_SCHEMA_V1.into(),
        run_id: "oversized-events".into(),
        capabilities: sipi_pybert_direct::EngineCapabilitiesV1 {
            stages,
            external_models: vec!["capability-".repeat(200_000)],
        },
        metrics: BTreeMap::new(),
        events,
        arrays: BTreeMap::new(),
        artifacts: Vec::new(),
    };
    let error = write_simulation_artifacts(request, &input_path, &output_path, output, None)
        .expect_err("large duplicated capability/event payload must fail closed");
    assert!(error.to_string().contains("preflight"));
    assert!(
        !output_path.exists(),
        "preflight runs before output allocation"
    );
    let _ = fs::remove_dir_all(root);
}

#[test]
fn metadata_preflight_counts_schema_and_backend_labels_before_materialization() {
    let root = std::env::temp_dir().join(format!(
        "sipi-pybert-direct-metadata-label-preflight-{}",
        std::process::id()
    ));
    let _ = fs::remove_dir_all(&root);
    fs::create_dir_all(&root).expect("root");
    let input_path = root.join("input.json");
    let output_path = root.join("out");
    let request = input();
    fs::write(
        &input_path,
        serde_json::to_vec(&request).expect("input json"),
    )
    .expect("input");
    let artifact_schema = "s".repeat(9 * 1024 * 1024);
    let backend_label = "b".repeat(9 * 1024 * 1024);
    let output = SimulationOutputV1 {
        schema: SIMULATION_SCHEMA_V1.into(),
        run_id: "oversized-labels".into(),
        capabilities: sipi_pybert_direct::EngineCapabilitiesV1 {
            stages: Vec::new(),
            external_models: Vec::new(),
        },
        metrics: BTreeMap::new(),
        events: Vec::new(),
        arrays: BTreeMap::new(),
        artifacts: Vec::new(),
    };
    let error = write_simulation_artifacts_with_schema_and_backend(
        request,
        &input_path,
        &output_path,
        output,
        None,
        &artifact_schema,
        &backend_label,
        None,
    )
    .expect_err("large schema/backend labels must fail closed");
    assert!(error.to_string().contains("preflight"));
    assert!(
        !output_path.exists(),
        "preflight runs before output allocation"
    );
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
    let parsed = strict_simulation_input_json(&json).expect("strict native input");
    let output = simulate_native_v1(&parsed).expect("native output");
    let report = write_simulation_artifacts(parsed, &input_path, &output_path, output, None)
        .expect("rich SIPI artifact");
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
