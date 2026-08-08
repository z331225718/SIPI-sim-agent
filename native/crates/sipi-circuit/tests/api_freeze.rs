use std::collections::{BTreeMap, BTreeSet};

use agent_spice_sim::result::{
    ComplexSample, MeasurementResult, SimulationPoint, SimulationResult, SimulationStatistics,
};
use agent_spice_sim::{CIRCUIT_API_VERSION, RESULT_SCHEMA};

#[test]
fn circuit_api_version_is_one() {
    assert_eq!(CIRCUIT_API_VERSION, 1);
}

#[test]
fn result_schema_string() {
    assert_eq!(RESULT_SCHEMA, "agent-spice.simulation-result.v1");
}

#[test]
fn simulation_result_top_level_keys() {
    let result = SimulationResult {
        schema: RESULT_SCHEMA.to_string(),
        circuit_api_version: CIRCUIT_API_VERSION,
        nodes: Vec::new(),
        points: Vec::new(),
        measurements: Vec::new(),
        statistics: SimulationStatistics::default(),
    };
    let json = serde_json::to_string(&result).expect("serialize");
    let parsed: serde_json::Value = serde_json::from_str(&json).expect("parse");
    let keys: BTreeSet<String> = parsed.as_object().unwrap().keys().cloned().collect();
    let expected: BTreeSet<String> = [
        "circuitApiVersion",
        "measurements",
        "nodes",
        "points",
        "schema",
        "statistics",
    ]
    .into_iter()
    .map(String::from)
    .collect();
    assert_eq!(keys, expected);
}

#[test]
fn statistics_keys_are_camel_case() {
    let json = serde_json::to_string(&SimulationStatistics::default()).expect("serialize");
    let parsed: serde_json::Value = serde_json::from_str(&json).expect("parse");
    let keys: BTreeSet<String> = parsed.as_object().unwrap().keys().cloned().collect();
    let expected: BTreeSet<String> = [
        "acceptedTransientSteps",
        "rejectedTransientSteps",
        "sparseSymbolicFactorizations",
        "sparseNumericRefactorizations",
        "transientMatrixCacheHits",
        "transientMatrixCacheMisses",
        "acMatrixAssemblyReplays",
        "fixedTransientSteps",
        "breakpointTransientSteps",
        "deviceTruncationEvaluations",
    ]
    .into_iter()
    .map(String::from)
    .collect();
    assert_eq!(keys, expected);
}

#[test]
fn simulation_point_keys() {
    let point = SimulationPoint {
        analysis: "op".into(),
        x: 0.0,
        values: BTreeMap::new(),
        complex: BTreeMap::new(),
    };
    let json = serde_json::to_string(&point).expect("serialize");
    let parsed: serde_json::Value = serde_json::from_str(&json).expect("parse");
    let keys: BTreeSet<String> = parsed.as_object().unwrap().keys().cloned().collect();
    let expected: BTreeSet<String> = ["analysis", "complex", "values", "x"]
        .into_iter()
        .map(String::from)
        .collect();
    assert_eq!(keys, expected);
}

#[test]
fn complex_sample_round_trips() {
    let sample = ComplexSample { re: 1.5, im: -2.25 };
    let json = serde_json::to_string(&sample).expect("serialize");
    let back: ComplexSample = serde_json::from_str(&json).expect("deserialize");
    assert_eq!(back.re, 1.5);
    assert_eq!(back.im, -2.25);
}

#[test]
fn measurement_result_round_trips() {
    let m = MeasurementResult {
        analysis: "tran".into(),
        name: "vload".into(),
        value: 0.8,
    };
    let json = serde_json::to_string(&m).expect("serialize");
    let back: MeasurementResult = serde_json::from_str(&json).expect("deserialize");
    assert_eq!(back.analysis, "tran");
    assert_eq!(back.name, "vload");
    assert_eq!(back.value, 0.8);
}

#[test]
fn simulation_result_default_fields_round_trip() {
    let result = SimulationResult {
        schema: RESULT_SCHEMA.to_string(),
        circuit_api_version: CIRCUIT_API_VERSION,
        nodes: vec!["n1".into()],
        points: Vec::new(),
        measurements: Vec::new(),
        statistics: SimulationStatistics::default(),
    };
    let json = serde_json::to_string(&result).expect("serialize");
    // Stripping the version fields must still deserialize (backward-compatible).
    let stripped = json.replace(
        "\"schema\":\"agent-spice.simulation-result.v1\",\"circuitApiVersion\":1,",
        "",
    );
    let back: SimulationResult = serde_json::from_str(&stripped).expect("deserialize");
    assert_eq!(back.schema, RESULT_SCHEMA);
    assert_eq!(back.circuit_api_version, CIRCUIT_API_VERSION);
    assert_eq!(back.nodes, vec!["n1".to_string()]);
}
