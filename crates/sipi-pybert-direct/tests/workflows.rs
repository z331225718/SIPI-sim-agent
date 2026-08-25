use std::{fs, io::Read, path::PathBuf};

use flate2::read::DeflateDecoder;
use serde_json::Value;
use sipi_pybert_direct::{
    SimulationOutputV1, compare_native_outputs, project_legacy_config_v1, run_sim_auto_file,
    run_sim_compare_file, run_sim_rust_file, simulate_portable_reference_v1,
};

fn fixture() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("fixtures")
        .join("pb-01-legacy-nrz.yaml")
}

fn temp_root(label: &str) -> PathBuf {
    let root = std::env::temp_dir().join(format!("sipi-pybert-{label}-{}", std::process::id()));
    let _ = fs::remove_dir_all(&root);
    fs::create_dir_all(&root).unwrap();
    root
}

#[test]
fn sim_rust_publishes_native_artifacts_but_auto_preserves_python_selection() {
    let root = temp_root("workflow-artifacts");
    let rust = run_sim_rust_file(&fixture(), &root.join("rust"), None).unwrap();
    assert_eq!(rust.metadata["schema"], "pybert.native-cli-result.v1");
    assert!(rust.meta_path.is_file());
    assert!(rust.arrays_path.is_file());

    let auto = run_sim_auto_file(&fixture(), &root.join("auto"), None).unwrap_err();
    let auto_payload: Value = serde_json::from_str(&auto.error_json()).unwrap();
    assert_eq!(auto_payload["code"], "auto_parity_blocked");
    assert_eq!(
        auto_payload["diagnostics"]["engine_selection"]["requested"],
        "auto"
    );
    assert_eq!(
        auto_payload["diagnostics"]["engine_selection"]["selected"],
        "python"
    );
    assert_eq!(
        auto_payload["diagnostics"]["engine_selection"]["parity_gate"]["version"],
        "pybert.native-auto-parity.v1"
    );
    assert_eq!(
        auto_payload["diagnostics"]["engine_selection"]["implementation"],
        "external_python_reference_required"
    );
    assert_eq!(
        auto_payload["diagnostics"]["engine_selection"]["rust_only"],
        Value::Bool(false)
    );
    assert_eq!(
        auto_payload["diagnostics"]["engine_selection"]["parity_gate"]["status"],
        "blocked"
    );
    assert!(!root.join("auto/meta.json").exists());
    let _ = fs::remove_dir_all(root);
}

#[test]
fn auto_external_projection_failure_is_structured_and_fail_closed() {
    let root = temp_root("workflow-auto-external");
    let config = root.join("ami.yaml");
    let fixture_text = fs::read_to_string(fixture()).unwrap();
    fs::write(&config, format!("{fixture_text}tx_use_ami: true\n")).unwrap();
    let error = run_sim_auto_file(&config, &root.join("auto"), None).unwrap_err();
    let payload: Value = serde_json::from_str(&error.error_json()).unwrap();
    assert_eq!(payload["code"], "auto_parity_blocked");
    assert_eq!(
        payload["diagnostics"]["engine_selection"]["selected"],
        "python"
    );
    assert_eq!(
        payload["diagnostics"]["engine_selection"]["implementation"],
        "external_python_reference_required"
    );
    assert!(!root.join("auto/meta.json").exists());
    let _ = fs::remove_dir_all(root);
}

#[test]
fn compare_checks_payload_and_rejects_waveform_mutation() {
    let root = temp_root("workflow-compare");
    let reference = run_sim_rust_file(&fixture(), &root.join("reference"), None)
        .unwrap()
        .output;
    let mut candidate = reference.clone();
    if let Some(value) = candidate
        .arrays
        .get_mut("rx_output_v")
        .expect("native fixture has rx output")
        .first_mut()
    {
        *value += 0.25;
    }
    let report = compare_native_outputs(&reference, &candidate);
    assert_eq!(report["passed"], Value::Bool(false));
    assert!(
        report["arrays"]["entries"]["rx_output_v"]["mismatch_count"]
            .as_u64()
            .unwrap_or(0)
            > 0
    );
    let _ = fs::remove_dir_all(root);
}

#[test]
fn sim_compare_without_reference_is_not_evaluated() {
    let root = temp_root("workflow-compare-artifact");
    let error = run_sim_compare_file(&fixture(), &root.join("compare"), None, None).unwrap_err();
    let payload: Value = serde_json::from_str(&error.error_json()).unwrap();
    assert_eq!(payload["code"], "reference_unavailable");
    assert_eq!(
        payload["diagnostics"]["comparison"]["status_only_comparison"],
        Value::Bool(false)
    );
    assert_eq!(
        payload["diagnostics"]["comparison"]["passed"],
        Value::Bool(false),
        "not-evaluated comparison must never claim parity"
    );
    assert_eq!(
        payload["diagnostics"]["comparison"]["reason"],
        "not_evaluated"
    );
    assert_eq!(
        payload["diagnostics"]["comparison"]["reference_required"],
        "external_python_reference_required"
    );
    assert!(!root.join("compare/meta.json").exists());
    let _ = fs::remove_dir_all(root);
}

#[test]
fn compare_shadow_populates_full_result_adapter_payload() {
    let root = temp_root("workflow-result-adapter");
    let reference = run_sim_rust_file(&fixture(), &root.join("reference"), None)
        .unwrap()
        .output;
    let reference_json = root.join("reference.json");
    let payload = serde_json::json!({
        "output": reference.clone(),
        "metadata": {
            "schema": reference.schema,
            "run_id": reference.run_id,
            "engine": {"backend": "rust", "native_simulation_v1": true},
            "metrics": reference.metrics,
            "aborted": false,
        },
        "diagnostics": {
            "pipeline": "typed_simulation_input_v1",
            "capabilities": reference.capabilities.stages,
            "events": reference.events,
            "cancellation": "checked_before_and_after_the_bounded_native_call",
        },
        "performance": {},
    });
    fs::write(&reference_json, serde_json::to_vec(&payload).unwrap()).unwrap();
    let report = run_sim_compare_file(
        &fixture(),
        &root.join("compare"),
        None,
        Some(&reference_json),
    )
    .unwrap();
    assert_eq!(
        report.metadata["diagnostics"]["comparison"]["metadata"]["passed"],
        Value::Bool(true)
    );
    assert_eq!(
        report.metadata["diagnostics"]["comparison"]["diagnostics"]["passed"],
        Value::Bool(true)
    );
    let _ = fs::remove_dir_all(root);
}

#[test]
fn compare_consumes_nested_output_and_rejects_flat_projection_drift() {
    let root = temp_root("workflow-nested-output-projection");
    let output = run_sim_rust_file(&fixture(), &root.join("source"), None)
        .unwrap()
        .output;
    let reference_json = root.join("reference.json");
    let payload = serde_json::json!({
        "output": output.clone(),
        "metrics": output.metrics,
        "arrays": output.arrays,
        "metadata": {
            "schema": output.schema,
            "run_id": output.run_id,
            "engine": {"backend": "rust", "native_simulation_v1": true},
            "metrics": output.metrics,
            "aborted": false,
        },
        "diagnostics": {
            "pipeline": "typed_simulation_input_v1",
            "capabilities": output.capabilities.stages,
            "events": output.events,
            "cancellation": "checked_before_and_after_the_bounded_native_call",
        },
        "performance": {},
    });
    fs::write(&reference_json, serde_json::to_vec(&payload).unwrap()).unwrap();
    let report =
        run_sim_compare_file(&fixture(), &root.join("valid"), None, Some(&reference_json)).unwrap();
    assert_eq!(
        report.metadata["diagnostics"]["comparison"]["nested_output_projection"]["passed"],
        Value::Bool(true)
    );

    let mut metric_drift = payload.clone();
    metric_drift["metrics"]["generated_bits"] = serde_json::json!(0.0);
    fs::write(&reference_json, serde_json::to_vec(&metric_drift).unwrap()).unwrap();
    let error = run_sim_compare_file(
        &fixture(),
        &root.join("metric-drift"),
        None,
        Some(&reference_json),
    )
    .unwrap_err();
    assert!(error.to_string().contains("metrics drift"), "{error}");

    let mut array_drift = payload;
    array_drift["arrays"]["rx_output_v"][0] = serde_json::json!(123.0);
    fs::write(&reference_json, serde_json::to_vec(&array_drift).unwrap()).unwrap();
    let error = run_sim_compare_file(
        &fixture(),
        &root.join("array-drift"),
        None,
        Some(&reference_json),
    )
    .unwrap_err();
    assert!(error.to_string().contains("arrays drift"), "{error}");
    let _ = fs::remove_dir_all(root);
}

#[test]
fn compare_accepts_serialized_backend_run_result_shape() {
    let root = temp_root("workflow-result-adapter-flat");
    let reference = run_sim_rust_file(&fixture(), &root.join("reference"), None)
        .unwrap()
        .output;
    let reference_json = root.join("reference-flat.json");
    let payload = serde_json::json!({
        "metadata": {
            "schema": reference.schema,
            "run_id": reference.run_id,
            "engine": {"backend": "rust", "native_simulation_v1": true},
            "metrics": reference.metrics,
            "aborted": false,
        },
        "arrays": reference.arrays,
        "diagnostics": {
            "pipeline": "typed_simulation_input_v1",
            "capabilities": reference.capabilities.stages,
            "events": reference.events,
            "cancellation": "checked_before_and_after_the_bounded_native_call",
        },
        "performance": {},
    });
    fs::write(&reference_json, serde_json::to_vec(&payload).unwrap()).unwrap();
    let report = run_sim_compare_file(
        &fixture(),
        &root.join("compare"),
        None,
        Some(&reference_json),
    )
    .unwrap();
    assert_eq!(
        report.metadata["diagnostics"]["comparison"]["passed"],
        Value::Bool(false),
        "serialized BackendRunResult compare must retain strict decision semantics"
    );
    let _ = fs::remove_dir_all(root);
}

#[test]
fn compare_preserves_external_two_dimensional_eye_shape_in_npz() {
    let root = temp_root("workflow-2d-array");
    let reference_json = root.join("reference-2d.json");
    let payload = serde_json::json!({
        "metadata": {
            "schema": "pybert.simulation.v1",
            "run_id": "two-dimensional-reference",
            "engine": {"backend": "python"},
            "metrics": {}
        },
        "arrays": {
            "rx_output_v": {"shape": [2, 2], "data": [[0.0, 1.0], [2.0, 3.0]]}
        },
        "diagnostics": {"result_adapter": "upstream_backend_run_result"}
    });
    fs::write(&reference_json, serde_json::to_vec(&payload).unwrap()).unwrap();
    let report = run_sim_compare_file(
        &fixture(),
        &root.join("compare"),
        None,
        Some(&reference_json),
    )
    .unwrap();
    assert_eq!(
        report.metadata["diagnostics"]["comparison"]["arrays"]["entries"]["rx_output_v"]["reason"],
        "shape"
    );
    let bytes = fs::read(&report.arrays_path).unwrap();
    let filename_len = u16::from_le_bytes([bytes[26], bytes[27]]) as usize;
    let extra_len = u16::from_le_bytes([bytes[28], bytes[29]]) as usize;
    let compressed_size = u32::from_le_bytes(bytes[18..22].try_into().unwrap()) as usize;
    let payload_start = 30 + filename_len + extra_len;
    let mut decoder = DeflateDecoder::new(&bytes[payload_start..payload_start + compressed_size]);
    let mut npy = Vec::new();
    decoder.read_to_end(&mut npy).unwrap();
    assert!(
        npy.windows(b"'shape': (2, 2), ".len())
            .any(|window| { window == b"'shape': (2, 2), " })
    );
    let _ = fs::remove_dir_all(root);
}

#[test]
fn compare_preserves_result_adapter_bool_int_float_dtypes() {
    let root = temp_root("workflow-typed-arrays");
    let reference_json = root.join("reference-typed.json");
    let payload = serde_json::json!({
        "metadata": {
            "schema": "pybert.simulation.v1",
            "run_id": "typed-reference",
            "engine": {"backend": "python"},
            "metrics": {}
        },
        "arrays": {
            "bool_decisions": {"dtype": "bool", "shape": [2, 2], "data": [[true, false], [false, true]]},
            "int_indices": [3, 8],
            "bare_bool_eye": [[true, false], [false, true]],
            "eye": {"dtype": "float64", "shape": [2, 2], "data": [[0.0, 0.25], [0.5, 0.75]]}
        },
        "array_dtypes": {"int_indices": "int64", "bare_bool_eye": "bool"},
        "diagnostics": {"result_adapter": "upstream_backend_run_result"}
    });
    fs::write(&reference_json, serde_json::to_vec(&payload).unwrap()).unwrap();
    let report = run_sim_compare_file(
        &fixture(),
        &root.join("compare"),
        None,
        Some(&reference_json),
    )
    .unwrap();
    assert_eq!(report.metadata["array_dtypes"]["bool_decisions"], "bool");
    assert_eq!(report.metadata["array_dtypes"]["int_indices"], "int64");
    assert_eq!(report.metadata["array_dtypes"]["bare_bool_eye"], "bool");
    assert_eq!(report.metadata["array_dtypes"]["eye"], "float64");
    assert_eq!(
        report.metadata["diagnostics"]["comparison"]["arrays"]["entries"]["bool_decisions"]["reason"],
        "missing_from_candidate"
    );
    let _ = fs::remove_dir_all(root);
}

#[test]
fn compare_output_schema_is_validated_before_use() {
    let output = serde_json::from_str::<SimulationOutputV1>(
        r#"{
          "schema":"pybert.simulation.v1",
          "runId":"r",
          "capabilities":{"stages":[],"externalModels":[]},
          "metrics":{"m":1.0},"events":[],"arrays":{"a":[1.0]},"artifacts":[]
        }"#,
    )
    .unwrap();
    let mut candidate = output.clone();
    candidate.metrics.insert("m".into(), 2.0);
    assert!(
        !compare_native_outputs(&output, &candidate)["passed"]
            .as_bool()
            .unwrap()
    );
}

#[test]
fn compare_gates_complete_output_capabilities_and_events() {
    let output = output_for_complete_contract_test();
    let same = compare_native_outputs(&output, &output);
    assert_eq!(same["output"]["passed"], Value::Bool(true));

    let mut capability_mutation = output.clone();
    capability_mutation.capabilities.stages.pop();
    let capability_report = compare_native_outputs(&output, &capability_mutation);
    assert_eq!(capability_report["passed"], Value::Bool(false));
    assert_eq!(
        capability_report["output"]["capabilities"]["passed"],
        Value::Bool(false)
    );

    let mut event_mutation = output;
    event_mutation.events[1].total_progress = 0.9;
    let event_report =
        compare_native_outputs(&output_for_complete_contract_test(), &event_mutation);
    assert_eq!(event_report["passed"], Value::Bool(false));
    assert_eq!(
        event_report["output"]["events"]["passed"],
        Value::Bool(false)
    );

    let mut schema_mutation = output_for_complete_contract_test();
    schema_mutation.schema = "pybert.simulation.mutated.v1".into();
    let schema_report =
        compare_native_outputs(&output_for_complete_contract_test(), &schema_mutation);
    assert_eq!(
        schema_report["output"]["schema"]["passed"],
        Value::Bool(false)
    );

    let mut artifact_mutation = output_for_complete_contract_test();
    artifact_mutation.artifacts[0].sha256 = "f".repeat(64);
    let artifact_report =
        compare_native_outputs(&output_for_complete_contract_test(), &artifact_mutation);
    assert_eq!(
        artifact_report["output"]["artifacts"]["passed"],
        Value::Bool(false)
    );

    let mut byte_length_mutation = output_for_complete_contract_test();
    byte_length_mutation.artifacts[0].byte_length += 1;
    let byte_length_report =
        compare_native_outputs(&output_for_complete_contract_test(), &byte_length_mutation);
    assert_eq!(
        byte_length_report["output"]["artifacts"]["comparison"],
        "exact"
    );
    assert_eq!(
        byte_length_report["output"]["artifacts"]["passed"],
        Value::Bool(false)
    );

    let mut path_mutation = output_for_complete_contract_test();
    path_mutation.artifacts[0].relative_path = "other.bin".into();
    let path_report = compare_native_outputs(&output_for_complete_contract_test(), &path_mutation);
    assert_eq!(
        path_report["output"]["artifacts"]["passed"],
        Value::Bool(false)
    );
}

fn output_for_complete_contract_test() -> SimulationOutputV1 {
    serde_json::from_str(
        r#"{
          "schema":"pybert.simulation.v1",
          "runId":"r",
          "capabilities":{"stages":["validate","result_assembly"],"externalModels":[]},
          "metrics":{"m":1.0},
          "events":[
            {"runId":"r","sequence":0,"stage":"validate","stageProgress":1.0,"totalProgress":0.111111,"message":null},
            {"runId":"r","sequence":1,"stage":"result_assembly","stageProgress":1.0,"totalProgress":1.0,"message":null}
          ],
          "arrays":{"a":[1.0]},
          "artifacts":[{"name":"result","schema":"pybert.result.v1","relativePath":"result.bin","mimeType":"application/octet-stream","sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","byteLength":1}]
        }"#,
    )
    .unwrap()
}

#[test]
fn compare_treats_decision_names_as_strict_even_when_encoded_as_float64() {
    let output = serde_json::from_value::<SimulationOutputV1>(serde_json::json!({
        "schema": "pybert.simulation.v1",
        "runId": "decision-strict",
        "capabilities": {"stages": [], "externalModels": []},
        "metrics": {},
        "events": [],
        "arrays": {"floating_decisions": [1.0, 2.0]},
        "artifacts": []
    }))
    .unwrap();
    let mut candidate = output.clone();
    candidate.arrays.get_mut("floating_decisions").unwrap()[0] += 1.0e-9;
    let report = compare_native_outputs(&output, &candidate);
    assert_eq!(report["passed"], Value::Bool(false));
    assert_eq!(
        report["arrays"]["entries"]["floating_decisions"]["discrete"],
        Value::Bool(true)
    );
    assert_eq!(
        report["arrays"]["entries"]["floating_decisions"]["reference_dtype"],
        "float64"
    );
}

#[test]
fn compare_rejects_empty_payloads_instead_of_comparing_status_only() {
    let output = serde_json::from_str::<SimulationOutputV1>(
        r#"{
          "schema":"pybert.simulation.v1",
          "runId":"r",
          "capabilities":{"stages":[],"externalModels":[]},
          "metrics":{},"events":[],"arrays":{},"artifacts":[]
        }"#,
    )
    .unwrap();
    let report = compare_native_outputs(&output, &output);
    assert_eq!(report["passed"], Value::Bool(false));
    assert_eq!(report["arrays"]["reason"], "empty_payload");
}

#[test]
fn compare_consumes_full_metadata_and_diagnostics_payload() {
    let root = temp_root("workflow-full-compare");
    let reference = run_sim_rust_file(&fixture(), &root.join("reference"), None)
        .unwrap()
        .output;
    let reference_json = root.join("reference.json");
    let payload = serde_json::json!({
        "output": reference,
        "metadata": {"engine": {"backend": "python"}},
        "diagnostics": {"reference_marker": true},
        "performance": {"timing": {"run_seconds": 0.01}}
    });
    fs::write(&reference_json, serde_json::to_vec(&payload).unwrap()).unwrap();
    let report = run_sim_compare_file(
        &fixture(),
        &root.join("compare"),
        None,
        Some(&reference_json),
    )
    .unwrap();
    assert_eq!(
        report.metadata["diagnostics"]["comparison"]["schema"],
        "pybert.engine-compare.v1"
    );
    assert_eq!(
        report.metadata["diagnostics"]["comparison"]["metadata"]["passed"],
        Value::Bool(false)
    );
    assert_eq!(
        report.metadata["diagnostics"]["comparison"]["performance"]["available"],
        Value::Bool(false)
    );
    assert_eq!(
        report.metadata["backend_metadata"]["engine"]["backend"],
        "external_reference"
    );
    let _ = fs::remove_dir_all(root);
}

#[test]
fn compare_retains_reference_when_candidate_fails_after_projection() {
    let root = temp_root("workflow-candidate-failure");
    let config = root.join("fec-nrz.yaml");
    fs::write(
        &config,
        r#"!!python/object:pybert.configuration.PyBertCfg
bit_rate: 10.0
nbits: 1000
pattern: PRBS-7
seed: 17
nspui: 2
mod_type: NRZ
ctle_enable: false
rx_use_viterbi: true
rx_viterbi_symbols: 2
rx_viterbi_fec: true
dfe_tap_tuners:
- !!python/tuple [true, -0.2, 0.2]
"#,
    )
    .unwrap();
    let reference_json = root.join("reference.json");
    fs::write(
        &reference_json,
        r#"{
          "schema":"pybert.simulation.v1",
          "runId":"reference",
          "capabilities":{"stages":[],"externalModels":[]},
          "metrics":{"reference":1.0},
          "events":[],"arrays":{"reference":[1.0]},"artifacts":[]
        }"#,
    )
    .unwrap();
    let report =
        run_sim_compare_file(&config, &root.join("compare"), None, Some(&reference_json)).unwrap();
    assert_eq!(
        report.metadata["diagnostics"]["comparison"]["reason"],
        "candidate_error"
    );
    assert!(report.arrays_path.is_file());
    assert_eq!(report.output.arrays["reference"], vec![1.0]);
    assert_eq!(
        report.metadata["diagnostics"]["compare_reference"]["reference_retained_on_candidate_failure"],
        Value::Bool(true)
    );
    let _ = fs::remove_dir_all(root);
}

#[test]
fn portable_reference_covers_pam4_viterbi_isi_and_fec_payloads() {
    let root = temp_root("workflow-pam4-viterbi");
    let base = fs::read_to_string(fixture()).unwrap();
    for (label, fec) in [("isi", false), ("fec", true)] {
        let config = root.join(format!("{label}.yaml"));
        let text = format!(
            "{}mod_type: PAM-4\nrn: 0.02\nrx_use_viterbi: true\nrx_viterbi_symbols: 2\nrx_viterbi_fec: {}\n",
            base.replace("mod_type: NRZ\n", "")
                .replace("rn: 0.0\n", "")
                .replace("nspui: 32\n", "nspui: 4\n"),
            if fec { "true" } else { "false" }
        );
        fs::write(&config, text).unwrap();
        let (_, input) = project_legacy_config_v1(&config, label.to_string()).unwrap();
        let output = simulate_portable_reference_v1(&input).unwrap();
        assert!(output.arrays.contains_key("viterbi_state_path"));
        assert!(output.arrays.contains_key("viterbi_bits"));
    }
    let _ = fs::remove_dir_all(root);
}
