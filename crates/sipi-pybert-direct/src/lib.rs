//! Stable, Python-independent contracts for the PyBERT Rust migration.
//!
//! The crate contains only deterministic data models and numerical stages. The
//! Python adapter owns GUI, Redis, filesystem policy, and IBIS-AMI DLL calls.

mod analysis;
mod bathtub;
mod capabilities;
mod channel;
mod decoder;
mod equalization;
mod error;
mod event;
mod external_host;
mod input;
mod jitter;
mod legacy_runtime;
mod legacy_sim;
mod crosstalk;
mod numpy_normal;
mod measured_tx;
mod output;
mod pam4_eye;
mod pattern;
mod physical_channel;
mod touchstone_channel;
mod pipeline;
mod receiver;
mod reference_runtime;
mod response;
mod runner;
mod signal;
mod simulation;
mod statistical_eye;
mod touchstone;
mod units;
mod workflows;

pub use analysis::{BerError, BerResult, calculate_ber};
pub use bathtub::{BathtubError, make_bathtub};
pub use capabilities::{EngineCapabilitiesV1, RunStageV1};
pub use channel::{
    ChannelError, MetallicLineConfig, TerminationConfig, calculate_loaded_transfer,
    calculate_metallic_line,
};
pub use crosstalk::{
    AggressorConfigV1, AggressorRunSummary, CrosstalkError, CrosstalkMetrics,
    calculate_induced_crosstalk_noise, evaluate_crosstalk_metrics, generate_aggressor_waveform,
};
pub use decoder::{
    FecDecodeError, FecDecodeResult, FecEncoder, IsiDecodeConfig, IsiDecodeError, IsiDecodeResult,
    decode_fec, decode_isi,
};
pub use equalization::{
    CtleConfig, EqualizationError, apply_ffe, apply_ffe_to_response, ctle_frequency_response,
    ctle_impulse_response, ffe_impulse_response,
};
pub use measured_tx::{
    MeasuredTxError, MeasuredTxPulseConfigV1, generate_measured_tx_waveform,
    resample_pulse_linear,
};
pub use error::ContractError;
pub use event::RunEventV1;
pub use external_host::{
    PYBERT_AMI_ADAPTER_SCHEMA_V2, PybertAmiAssetBundleV1, PybertAmiHostResultV2, PybertAmiLaunchV2,
    PybertAmiModeV1, PybertAmiRequestV1, PybertAmiWorkerErrorV1, consume_pybert_ami_result,
    prepare_pybert_ami_launch, sha256_bytes, supervise_prepared_pybert_ami_job,
};
pub use input::{
    AdditiveNoiseV1, AnalysisConfigV1, ChannelInputV1, ChannelResponseV1, CtleConfigV1,
    DfeConfigV1, ExternalModelRefV1, FfeConfigV1, MetallicLineChannelV1, ModulationV1, PatternV1,
    PeriodicNoiseV1, ResourceLimitsV1, RxConfigV1, SimulationInputV1, StatisticalEyeConfigV1,
    TimebaseV1, TxConfigV1, ViterbiConfigV1,
};
pub use jitter::{
    CrossingConfig, CrossingError, DataDependentJitterResult, DualDiracJitterResult,
    SpectralJitterResult, TieTrackResult, assemble_tie_track, calculate_data_dependent_jitter,
    calculate_dual_dirac_jitter, calculate_spectral_jitter, find_crossing_times, find_crossings,
};
pub use legacy_runtime::{
    LegacyConfigProjectionV1, LegacyResultCodecV1, LegacyRuntimeError, LegacySimReportV1,
    parse_legacy_config_v1, project_legacy_config_v1, run_legacy_sim_v1,
    run_legacy_sim_with_codec_v1, write_legacy_result_v1,
};
pub use legacy_sim::{
    DEFAULT_RESULT_EXTENSION, LEGACY_CONFIG_EXTENSIONS, LegacySimCandidateStatus, LegacySimError,
    LegacySimRequestV1, NATIVE_CORE_ENTRYPOINT, OsStringLike, PB01_COMMAND, prepare_legacy_sim_v1,
    validate_legacy_sim_request,
};
pub use output::{ArtifactRefV1, SimulationOutputV1};
pub use pattern::{PatternError, SymbolModulation, generate_prbs_bits, modulate_bits};
pub use pam4_eye::{
    Pam4EyeError, Pam4EyeMetrics, Pam4Levels, Pam4Thresholds, calculate_pam4_eye_metrics,
};
pub use physical_channel::{PHYSICAL_CHANNEL_POLICY_V1, run_channel_physical_json};
pub use touchstone_channel::{
    TOUCHSTONE_CHANNEL_POLICY_V1, TOUCHSTONE_RESULT_SCHEMA_V1,
    run_channel_touchstone_network_json,
};
pub use pipeline::{
    LinearDfeLinkConfig, LinearDfeLinkResult, LinearLinkError, LinearLinkResult,
    PrbsLinearDfeLinkConfig, PrbsLinearDfeLinkResult, run_linear_dfe_link, run_linear_link,
    run_linear_link_with_rx_filter, run_prbs_linear_dfe_link,
};
pub use receiver::{
    CdrConfig, CdrError, CdrState, DfeConfig, DfeDecision, DfeError, DfeModulation, DfeRunError,
    DfeRunOptions, DfeRunResult, DfeState, run_dfe, run_dfe_with_external_clocks, run_ideal_dfe,
};
pub use reference_runtime::simulate_portable_reference_v1;
pub use response::{ResponseError, ResponseV1, calculate_responses};
pub use runner::{
    ArrayDTypeV1, DirectRunError, DirectRunReport, NumericArrayV1, TypedArrayV1, npz_bytes_nd,
    npz_bytes_typed_nd, run_sim_native_file, run_sim_native_input, run_sim_native_json,
    strict_simulation_input_json, write_simulation_artifacts,
    write_simulation_artifacts_with_schema_and_backend,
    write_simulation_artifacts_with_schema_and_backend_and_shapes,
    write_simulation_artifacts_with_schema_and_backend_and_shapes_and_typed_arrays,
};
pub use signal::{
    SignalError, causal_convolve_truncated, convolve_truncated, forward_real_spectrum,
    inverse_real_spectrum, linear_convolve, pulse_response, sparse_tapped_convolve_truncated,
    step_response, zero_pad,
};
pub use simulation::{
    NativeCancellationToken, NativeSimulationError, simulate_native_v1,
    simulate_native_v1_with_cancellation,
};
pub use sipi_ami_worker::{SupervisorReceiptV1, WorkerIdentityV1};
pub use statistical_eye::{
    StatisticalEyeContourV1, StatisticalEyeError, StatisticalEyeInputV1, StatisticalEyeResultV1,
    calculate_statistical_contours, calculate_statistical_eye,
};
pub use touchstone::{TouchstoneError, parse_s2p_response, parse_touchstone_response};
pub use units::{Hertz, Ohms, Seconds, Volts};
pub use workflows::{
    CompareReference, WorkflowError, compare_native_outputs, run_sim_auto_file,
    run_sim_compare_file, run_sim_rust_file,
};

pub const SIMULATION_SCHEMA_V1: &str = "pybert.simulation.v1";
