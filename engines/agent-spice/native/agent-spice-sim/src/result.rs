use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};

use crate::{CIRCUIT_API_VERSION, RESULT_SCHEMA};

fn default_schema() -> String {
    RESULT_SCHEMA.to_string()
}

fn default_circuit_api_version() -> u32 {
    CIRCUIT_API_VERSION
}

#[derive(Debug, Serialize, Deserialize)]
pub struct ComplexSample {
    pub re: f64,
    pub im: f64,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct SimulationPoint {
    pub analysis: String,
    pub x: f64,
    pub values: BTreeMap<String, f64>,
    pub complex: BTreeMap<String, ComplexSample>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct MeasurementResult {
    pub analysis: String,
    pub name: String,
    pub value: f64,
}

#[derive(Debug, Default, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SimulationStatistics {
    pub accepted_transient_steps: usize,
    pub rejected_transient_steps: usize,
    pub sparse_symbolic_factorizations: usize,
    pub sparse_numeric_refactorizations: usize,
    pub transient_matrix_cache_hits: usize,
    pub transient_matrix_cache_misses: usize,
    pub ac_matrix_assembly_replays: usize,
    pub fixed_transient_steps: usize,
    pub breakpoint_transient_steps: usize,
    pub device_truncation_evaluations: usize,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct SimulationResult {
    #[serde(default = "default_schema")]
    pub schema: String,
    #[serde(rename = "circuitApiVersion", default = "default_circuit_api_version")]
    pub circuit_api_version: u32,
    pub nodes: Vec<String>,
    pub points: Vec<SimulationPoint>,
    pub measurements: Vec<MeasurementResult>,
    pub statistics: SimulationStatistics,
}
