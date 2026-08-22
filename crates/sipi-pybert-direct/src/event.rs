use serde::{Deserialize, Serialize};

use crate::{ContractError, RunStageV1};

#[derive(Debug, Clone, Deserialize, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct RunEventV1 {
    pub run_id: String,
    pub sequence: u64,
    pub stage: RunStageV1,
    pub stage_progress: f64,
    pub total_progress: f64,
    pub message: Option<String>,
}

impl RunEventV1 {
    pub fn validate(&self) -> Result<(), ContractError> {
        if self.run_id.trim().is_empty() {
            return Err(ContractError::InvalidRunId);
        }
        if !self.stage_progress.is_finite()
            || !self.total_progress.is_finite()
            || !(0.0..=1.0).contains(&self.stage_progress)
            || !(0.0..=1.0).contains(&self.total_progress)
        {
            return Err(ContractError::InvalidProgress);
        }
        Ok(())
    }
}
