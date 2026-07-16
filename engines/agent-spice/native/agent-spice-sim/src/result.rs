use std::collections::BTreeMap;

use serde::Serialize;

#[derive(Debug, Serialize)]
pub struct ComplexSample {
    pub re: f64,
    pub im: f64,
}

#[derive(Debug, Serialize)]
pub struct SimulationPoint {
    pub analysis: String,
    pub x: f64,
    pub values: BTreeMap<String, f64>,
    pub complex: BTreeMap<String, ComplexSample>,
}

#[derive(Debug, Serialize)]
pub struct MeasurementResult {
    pub analysis: String,
    pub name: String,
    pub value: f64,
}

#[derive(Debug, Default, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SimulationStatistics {
    pub accepted_transient_steps: usize,
    pub rejected_transient_steps: usize,
    pub sparse_symbolic_factorizations: usize,
    pub sparse_numeric_refactorizations: usize,
    pub ac_matrix_assembly_replays: usize,
    pub fixed_transient_steps: usize,
    pub breakpoint_transient_steps: usize,
    pub device_truncation_evaluations: usize,
}

#[derive(Debug, Serialize)]
pub struct SimulationResult {
    pub nodes: Vec<String>,
    pub points: Vec<SimulationPoint>,
    pub measurements: Vec<MeasurementResult>,
    pub statistics: SimulationStatistics,
}
