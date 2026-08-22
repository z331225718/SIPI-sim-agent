use std::collections::BTreeMap;
use std::path::{Component, Path};

use serde::{Deserialize, Serialize};

use crate::{ContractError, EngineCapabilitiesV1, RunEventV1, SIMULATION_SCHEMA_V1};

/// A content-addressed large result produced outside the JSON control plane.
///
/// Paths are deliberately relative to a host-owned run directory. The core
/// never opens them; Agent-Spice and application adapters may use the stable
/// schema, MIME type, length, and SHA-256 to transfer or verify the artifact.
#[derive(Debug, Clone, Deserialize, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ArtifactRefV1 {
    pub name: String,
    pub schema: String,
    pub relative_path: String,
    pub mime_type: String,
    pub sha256: String,
    pub byte_length: u64,
}

impl ArtifactRefV1 {
    fn validate(&self) -> Result<(), ContractError> {
        let safe_relative_path = !self.relative_path.is_empty()
            && !self.relative_path.contains('\\')
            && Path::new(&self.relative_path)
                .components()
                .all(|component| matches!(component, Component::Normal(_) | Component::CurDir));
        let valid_sha256 = self.sha256.len() == 64
            && self
                .sha256
                .bytes()
                .all(|byte| byte.is_ascii_digit() || (byte as char).is_ascii_lowercase());
        if self.name.trim().is_empty()
            || self.schema.trim().is_empty()
            || self.mime_type.trim().is_empty()
            || !safe_relative_path
            || !valid_sha256
            || self.byte_length == 0
        {
            return Err(ContractError::InvalidArtifactReference);
        }
        Ok(())
    }
}

#[derive(Debug, Clone, Deserialize, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SimulationOutputV1 {
    pub schema: String,
    pub run_id: String,
    pub capabilities: EngineCapabilitiesV1,
    pub metrics: BTreeMap<String, f64>,
    /// Ordered, completed-stage events for replay/audit consumers. Live hosts
    /// can stream the same semantic events without changing this output schema.
    #[serde(default)]
    pub events: Vec<RunEventV1>,
    /// Small-to-medium numeric stage outputs for the JSON/native v1 boundary.
    ///
    /// The PyO3 production path can replace this transfer with zero-copy
    /// buffers without changing the semantic names. JSON callers retain this
    /// materialized form for fixtures and diagnostics.
    #[serde(default)]
    pub arrays: BTreeMap<String, Vec<f64>>,
    /// Host-owned large outputs, kept out of the JSON/numpy control payload.
    #[serde(default)]
    pub artifacts: Vec<ArtifactRefV1>,
}

impl SimulationOutputV1 {
    pub fn validate(&self) -> Result<(), ContractError> {
        if self.schema != SIMULATION_SCHEMA_V1 {
            return Err(ContractError::UnsupportedSchema(self.schema.clone()));
        }
        if self.run_id.trim().is_empty() {
            return Err(ContractError::InvalidRunId);
        }
        if self.metrics.values().any(|value| !value.is_finite()) {
            return Err(ContractError::InvalidOutputMetric);
        }
        if self.arrays.iter().any(|(name, values)| {
            name.trim().is_empty() || values.iter().any(|value| !value.is_finite())
        }) {
            return Err(ContractError::InvalidOutputMetric);
        }
        if self.artifacts.iter().enumerate().any(|(index, artifact)| {
            artifact.validate().is_err()
                || self.artifacts[index + 1..]
                    .iter()
                    .any(|other| other.name == artifact.name)
        }) {
            return Err(ContractError::InvalidArtifactReference);
        }
        let mut previous_stage = None;
        let mut previous_total_progress = 0.0;
        for (index, event) in self.events.iter().enumerate() {
            event.validate()?;
            if event.run_id != self.run_id
                || event.sequence != index as u64
                || previous_stage.is_some_and(|stage| event.stage.ordinal() < stage)
                || event.total_progress < previous_total_progress
            {
                return Err(ContractError::InvalidProgress);
            }
            previous_stage = Some(event.stage.ordinal());
            previous_total_progress = event.total_progress;
        }
        Ok(())
    }
}
