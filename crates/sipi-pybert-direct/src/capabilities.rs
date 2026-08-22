use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, Deserialize, Eq, Hash, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum RunStageV1 {
    Validate,
    ChannelResponse,
    TxProcessing,
    RxEqualization,
    DfeAdaptation,
    ViterbiFec,
    StatisticalEye,
    JitterAnalysis,
    ResultAssembly,
}

impl RunStageV1 {
    pub const fn ordinal(self) -> u8 {
        match self {
            Self::Validate => 0,
            Self::ChannelResponse => 1,
            Self::TxProcessing => 2,
            Self::RxEqualization => 3,
            Self::DfeAdaptation => 4,
            Self::ViterbiFec => 5,
            // The native pipeline performs waveform-derived jitter before the
            // optional analytical eye. Keep ordinals aligned with execution
            // so serialized event streams are strictly monotonic.
            Self::JitterAnalysis => 6,
            Self::StatisticalEye => 7,
            Self::ResultAssembly => 8,
        }
    }
}

#[derive(Debug, Clone, Deserialize, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct EngineCapabilitiesV1 {
    pub stages: Vec<RunStageV1>,
    pub external_models: Vec<String>,
}
