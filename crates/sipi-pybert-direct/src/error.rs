use thiserror::Error;

#[derive(Debug, Error, PartialEq)]
pub enum ContractError {
    #[error("unsupported simulation schema: {0}")]
    UnsupportedSchema(String),
    #[error("run ID must not be empty")]
    InvalidRunId,
    #[error("sample interval must be finite and greater than zero")]
    InvalidSampleInterval,
    #[error("data rate must be finite and greater than zero")]
    InvalidDataRate,
    #[error("samples per UI must be greater than zero")]
    InvalidSamplesPerUi,
    #[error(
        "sample interval, samples per UI, and data rate must describe one consistent symbol clock"
    )]
    InconsistentTimebase,
    #[error("bit count must be greater than zero")]
    InvalidBitCount,
    #[error("PRBS order must be between 2 and 63")]
    InvalidPrbsOrder,
    #[error("explicit bits must contain exactly bitCount binary values when supplied")]
    InvalidExplicitBits,
    #[error("channel response must contain at least one finite sample")]
    InvalidChannelResponse,
    #[error("channel impedances must be finite and greater than zero")]
    InvalidChannelImpedance,
    #[error("external model kind and capability must not be empty")]
    InvalidExternalModel,
    #[error("TX amplitude must be finite and greater than zero")]
    InvalidTxAmplitude,
    #[error("additive noise samples must be finite")]
    InvalidAdditiveNoise,
    #[error("periodic noise configuration is invalid or above the sample Nyquist limit")]
    InvalidPeriodicNoise,
    #[error("enabled FFE requires finite weights and a valid cursor position")]
    InvalidFfe,
    #[error("DFE configuration is invalid or does not match the configured tap count")]
    InvalidDfe,
    #[error("CTLE configuration is invalid")]
    InvalidCtle,
    #[error("Viterbi configuration is invalid")]
    InvalidViterbi,
    #[error("statistical eye target BER must be between 0 and 0.5")]
    InvalidTargetBer,
    #[error("statistical eye voltage resolution must be finite and greater than zero")]
    InvalidVoltageResolution,
    #[error("statistical eye receiver jitter must be finite and non-negative")]
    InvalidReceiverJitter,
    #[error("statistical eye time points must be greater than zero")]
    InvalidTimePoints,
    #[error("statistical eye maximum distribution states must be at least 8")]
    InvalidDistributionStateLimit,
    #[error("BER eye-bit count must be greater than zero when supplied")]
    InvalidBerEyeBits,
    #[error("jitter eye-UI count must be greater than zero when supplied")]
    InvalidJitterEyeUis,
    #[error("jitter relative threshold must be finite and greater than zero when supplied")]
    InvalidJitterRelThresh,
    #[error("resource limits must be greater than zero")]
    InvalidResourceLimit,
    #[error("progress values must be finite and within [0, 1]")]
    InvalidProgress,
    #[error("output metrics must be finite")]
    InvalidOutputMetric,
    #[error(
        "artifact references must have a safe relative path, schema, MIME type, SHA-256, and positive byte length"
    )]
    InvalidArtifactReference,
}
