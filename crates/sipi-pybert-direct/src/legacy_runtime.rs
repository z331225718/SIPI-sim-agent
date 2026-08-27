//! A bounded, executable leaf of the pinned PyBERT `sim` workflow.
//!
//! The upstream command loads a `PyBertCfg`, executes the native Python
//! simulation graph, and pickles a `PyBertData` object.  This module performs
//! the first real Rust projection of that path: it consumes the upstream YAML
//! object (including its Python object/tuple tags), maps the reachable NRZ
//! metallic-line profile into the already-portable native core, and writes a
//! Python-readable pickle dictionary under the legacy `.pybert_data` suffix.
//!
//! This is intentionally a leaf, not a claim that every PyBERT configuration
//! or the exact `PyBertData` class pickle has been migrated.  Unsupported
//! branches fail closed and the artifact records the bounded schema. It
//! supersedes `legacy_sim` only as the active implementation for this scoped
//! leaf; that predecessor still owns the full branch/default/error inventory.

use std::{
    borrow::Cow,
    collections::{BTreeMap, BTreeSet},
    fs::{self, File},
    io::{Read, Write},
    path::{Path, PathBuf},
    sync::atomic::{AtomicU64, Ordering},
    time::{SystemTime, UNIX_EPOCH},
};

use serde::{Deserialize, Serialize};
use serde_json::Value as JsonValue;
use serde_pickle::{
    DeOptions,
    value::{HashableValue, Value as PickleValue},
    value_from_slice,
};
use serde_pickle::{SerOptions, to_vec};
use serde_yaml::Value;
use sha2::{Digest, Sha256};
use thiserror::Error;
use yaml_rust2::parser::{Event, EventReceiver, Parser, Tag};

use crate::touchstone::{S2pImportOptions, parse_touchstone_response_with_options};
use crate::{
    AdditiveNoiseV1, AnalysisConfigV1, ChannelInputV1, ChannelResponseV1, CtleConfigV1,
    DfeConfigV1, FfeConfigV1, Hertz, LegacySimError, LegacySimRequestV1, MetallicLineChannelV1,
    ModulationV1, Ohms, PatternV1, PeriodicNoiseV1, ResourceLimitsV1, RxConfigV1,
    SIMULATION_SCHEMA_V1, Seconds, SimulationInputV1, SimulationOutputV1, TimebaseV1, TxConfigV1,
    ViterbiConfigV1, Volts, forward_real_spectrum, pulse_response, simulate_native_v1,
    step_response,
};

const DEFAULT_NBITS: u64 = 15_000;
const MIN_NBITS: u64 = 1_000;
const DEFAULT_NSPUI: u32 = 32;
const DEFAULT_EYE_BITS: u64 = 10_160;
const DEFAULT_BIT_RATE_GBPS: f64 = 10.0;
const DEFAULT_FMAX_GHZ: f64 = 40.0;
const DEFAULT_FSTEP_MHZ: f64 = 10.0;
const DEFAULT_VOD: f64 = 1.0;
const DEFAULT_RS: f64 = 100.0;
const DEFAULT_COUT_PF: f64 = 0.5;
const DEFAULT_PN_MAG_V: f64 = 0.01;
const DEFAULT_PN_FREQ_MHZ: f64 = 11.0;
const DEFAULT_RN_V: f64 = 0.01;
const DEFAULT_RIN: f64 = 100.0;
const DEFAULT_CIN_PF: f64 = 0.5;
const DEFAULT_RX_BW_GHZ: f64 = 12.0;
const DEFAULT_PEAK_FREQ_GHZ: f64 = 5.0;
const DEFAULT_PEAK_MAG_DB: f64 = 1.7;
const DEFAULT_RDC: f64 = 0.1876;
const DEFAULT_W0: f64 = 10.0e6;
const DEFAULT_R0: f64 = 1.452;
const DEFAULT_THETA0: f64 = 0.02;
const DEFAULT_Z0: f64 = 100.0;
const DEFAULT_V0: f64 = 0.67;
const DEFAULT_CHANNEL_LENGTH_M: f64 = 0.5;
const DEFAULT_N_TAPS: usize = 15;
const DEFAULT_N_PRE: usize = 5;
const MAX_CONFIG_BYTES: u64 = 1024 * 1024;
const MAX_YAML_DEPTH: usize = 64;
const MAX_PICKLE_VALUES: usize = 100_000;
const MAX_RX_TAPS: usize = 256;
const MAX_DFE_TAPS: usize = 64;
const MAX_TX_TUNERS: usize = 64;
const MAX_TOTAL_SAMPLES: u64 = 50_000_000;
const MAX_LEGACY_RESULT_BYTES: usize = 512 * 1024 * 1024;
const LEGACY_RESULT_VECTOR_UPPER_BOUND: u64 = 16;
const LEGACY_CLASS_PICKLE_PROTOCOL: u8 = 3;
const LEGACY_CLASS_DATE_CREATED: &str = "not-recorded";
const LEGACY_CLASS_VERSION: &str = "sipi-pybert-direct/0.1.0 class-pickle-v1 noncanonical";
const LEGACY_CLASS_SAFE_LOG10_MIN: f64 = 1e-20;
const LEGACY_F64_WRITE_CHUNK_VALUES: usize = 1024;
const LEGACY_READBACK_BUFFER_BYTES: usize = 64 * 1024;
const PYBERT_CONFIG_TAG: &str = "python/object:pybert.configuration.PyBertCfg";
const PYTHON_TUPLE_TAG: &str = "python/tuple";
const YAML_2002_TAG_HANDLE: &str = "tag:yaml.org,2002:";

const LEGACY_ITEM_NAMES: [&str; 23] = [
    "chnl_h",
    "tx_out_h",
    "ctle_out_h",
    "dfe_out_h",
    "chnl_s",
    "tx_s",
    "ctle_s",
    "dfe_s",
    "tx_out_s",
    "ctle_out_s",
    "dfe_out_s",
    "chnl_p",
    "tx_out_p",
    "ctle_out_p",
    "dfe_out_p",
    "chnl_H",
    "tx_H",
    "ctle_H",
    "dfe_H",
    "tx_out_H",
    "ctle_out_H",
    "dfe_out_H",
    "tx_out",
];

const CONSUMED_KEYS: &[&str] = &[
    "bit_rate",
    "nbits",
    "pattern",
    "seed",
    "random_noise_seed",
    "nspui",
    "eye_bits",
    "mod_type",
    "f_max",
    "f_step",
    "use_ch_file",
    "ch_file",
    "impulse_length",
    "Rdc",
    "w0",
    "R0",
    "Theta0",
    "Z0",
    "v0",
    "l_ch",
    "use_window",
    "vod",
    "rs",
    "cout",
    "pn_mag",
    "pn_freq",
    "rn",
    "tx_taps",
    "rin",
    "cin",
    "rx_bw",
    "peak_freq",
    "peak_mag",
    "ctle_enable",
    "rx_n_taps",
    "rx_n_pre",
    "sum_ideal",
    "decision_scaler",
    "gain",
    "n_ave",
    "sum_bw",
    "use_agc",
    "delta_t",
    "alpha",
    "n_lock_ave",
    "rel_lock_tol",
    "lock_sustain",
    "dfe_tap_tuners",
    "tx_tap_tuners",
    "tx_use_ami",
    "tx_use_ts4",
    "tx_use_getwave",
    "tx_ami_file",
    "tx_dll_file",
    "tx_ibis_file",
    "tx_use_ibis",
    "cin",
    "cac",
    "use_ctle_file",
    "ctle_file",
    "rx_use_ami",
    "rx_use_ts4",
    "rx_use_getwave",
    "rx_ami_file",
    "rx_dll_file",
    "rx_ibis_file",
    "rx_use_ibis",
    "rx_use_viterbi",
    "rx_viterbi_symbols",
    "rx_viterbi_fec",
    "thresh",
    "rx_bw_tune",
    "peak_freq_tune",
    "peak_mag_tune",
    "min_mag_tune",
    "max_mag_tune",
    "step_mag_tune",
    "ctle_enable_tune",
    "use_mmse",
];

// Pinned PyBERT serialization metadata and inert UI state present in the
// scoped fixture. Every other top-level field must be classified before the
// Rust leaf is allowed to execute it.
const IGNORED_INERT_KEYS: &[&str] = &["date_created", "version", "debug", "renumber"];

const UNSUPPORTED_ENABLED_KEYS: &[&str] =
    &["tx_use_ami", "rx_use_ami", "tx_use_ibis", "rx_use_ibis"];

static SEED_COUNTER: AtomicU64 = AtomicU64::new(1);

/// Explicit result selection for the bounded legacy `sim` adapter.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum LegacyResultCodecV1 {
    /// Existing SIPI-owned data-only dictionary (the default CLI format).
    SipiDictionary,
    /// Pinned PyBERT class-load-compatible object graph.
    ClassPickle,
}

#[derive(Debug, Error)]
pub enum LegacyRuntimeError {
    #[error("PB-01 legacy configuration could not be read: {0}")]
    Io(#[from] std::io::Error),
    #[error("PB-01 legacy YAML could not be parsed: {0}")]
    Yaml(#[from] serde_yaml::Error),
    #[error("PB-01 legacy configuration must be a mapping")]
    ConfigNotMapping,
    #[error("PB-01 legacy configuration is invalid: {0}")]
    InvalidConfig(String),
    #[error("PB-01 legacy configuration branch is not in the migrated leaf: {0}")]
    Unsupported(String),
    #[error("PB-01 legacy resource budget exceeded: {0}")]
    ResourceLimit(String),
    #[error("PB-01 native simulation failed: {0}")]
    Native(#[from] crate::NativeSimulationError),
    #[error("PB-01 legacy result pickle failed: {0}")]
    Pickle(#[from] serde_pickle::Error),
    #[error("PB-01 legacy result publication is indeterminate: {0}")]
    PublishIndeterminate(String),
}

#[derive(Clone, Debug, Deserialize, Default)]
#[serde(default)]
struct RawLegacyConfig {
    bit_rate: Option<f64>,
    nbits: Option<u64>,
    pattern: Option<String>,
    seed: Option<u64>,
    random_noise_seed: Option<u64>,
    nspui: Option<u32>,
    eye_bits: Option<u64>,
    mod_type: Option<String>,
    f_max: Option<f64>,
    f_step: Option<f64>,
    use_ch_file: Option<bool>,
    ch_file: Option<String>,
    impulse_length: Option<f64>,
    #[serde(rename = "Rdc")]
    rdc: Option<f64>,
    w0: Option<f64>,
    #[serde(rename = "R0")]
    r0: Option<f64>,
    #[serde(rename = "Theta0")]
    theta0: Option<f64>,
    #[serde(rename = "Z0")]
    z0: Option<f64>,
    v0: Option<f64>,
    l_ch: Option<f64>,
    use_window: Option<bool>,
    renumber: Option<bool>,
    vod: Option<f64>,
    rs: Option<f64>,
    cout: Option<f64>,
    pn_mag: Option<f64>,
    pn_freq: Option<f64>,
    rn: Option<f64>,
    tx_taps: Option<Vec<(bool, f64, f64, f64)>>,
    rin: Option<f64>,
    cin: Option<f64>,
    rx_bw: Option<f64>,
    peak_freq: Option<f64>,
    peak_mag: Option<f64>,
    ctle_enable: Option<bool>,
    rx_n_taps: Option<u32>,
    rx_n_pre: Option<u32>,
    sum_ideal: Option<bool>,
    decision_scaler: Option<f64>,
    gain: Option<f64>,
    n_ave: Option<f64>,
    sum_bw: Option<f64>,
    use_agc: Option<bool>,
    delta_t: Option<f64>,
    alpha: Option<f64>,
    n_lock_ave: Option<u32>,
    rel_lock_tol: Option<f64>,
    lock_sustain: Option<u32>,
    dfe_tap_tuners: Option<Vec<(bool, f64, f64)>>,
    tx_tap_tuners: Option<Vec<Value>>,
    tx_use_ami: Option<bool>,
    tx_use_ts4: Option<bool>,
    tx_use_getwave: Option<bool>,
    tx_ami_file: Option<String>,
    tx_dll_file: Option<String>,
    tx_ibis_file: Option<String>,
    tx_use_ibis: Option<bool>,
    cac: Option<f64>,
    use_ctle_file: Option<bool>,
    ctle_file: Option<String>,
    rx_use_ami: Option<bool>,
    rx_use_ts4: Option<bool>,
    rx_use_getwave: Option<bool>,
    rx_ami_file: Option<String>,
    rx_dll_file: Option<String>,
    rx_ibis_file: Option<String>,
    rx_use_ibis: Option<bool>,
    rx_use_viterbi: Option<bool>,
    rx_viterbi_symbols: Option<u32>,
    rx_viterbi_fec: Option<bool>,
    thresh: Option<f64>,
    rx_bw_tune: Option<Value>,
    peak_freq_tune: Option<Value>,
    peak_mag_tune: Option<Value>,
    min_mag_tune: Option<Value>,
    max_mag_tune: Option<Value>,
    step_mag_tune: Option<Value>,
    ctle_enable_tune: Option<bool>,
    use_mmse: Option<bool>,
}

/// Typed projection of the legacy configuration consumed by the migrated leaf.
#[derive(Clone, Debug, PartialEq)]
pub struct LegacyConfigProjectionV1 {
    pub bit_rate_gbps: f64,
    pub nbits: u64,
    pub pattern: String,
    /// The value supplied by the legacy caller.  A zero request is intentionally
    /// non-reproducible, matching PyBERT's ``randint(128)`` branch.
    pub requested_seed: u64,
    /// The non-zero value actually consumed by the PRBS and noise generators.
    pub effective_seed: u64,
    pub seed: u64,
    /// Optional explicit random-noise seed. When absent, PyBERT uses the
    /// completed PRBS seed as the noise seed.
    pub random_noise_seed: Option<u64>,
    pub nspui: u32,
    pub eye_bits: u64,
    pub mod_type: String,
    pub f_max_ghz: f64,
    pub f_step_mhz: f64,
    pub impulse_length_ns: f64,
    pub use_window: bool,
    pub channel_length_m: f64,
    pub rdc_ohm_per_m: f64,
    pub w0_rad_per_s: f64,
    pub r0_ohm_per_m: f64,
    pub theta0: f64,
    pub z0_ohm: f64,
    pub v0_relative: f64,
    pub vod_v: f64,
    pub rs_ohm: f64,
    pub cout_pf: f64,
    pub pn_mag_v: f64,
    pub pn_freq_mhz: f64,
    pub rn_v: f64,
    pub rin_ohm: f64,
    pub cin_pf: f64,
    pub rx_bw_ghz: f64,
    pub peak_freq_ghz: f64,
    pub peak_mag_db: f64,
    pub ctle_enable: bool,
    pub tx_taps: Vec<(bool, f64, f64, f64)>,
    pub rx_n_taps: usize,
    pub rx_n_pre: usize,
    pub sum_ideal: bool,
    pub decision_scaler_v: f64,
    pub gain: f64,
    pub n_ave: u32,
    pub sum_bw_ghz: f64,
    pub use_agc: bool,
    pub delta_t_ps: f64,
    pub alpha: f64,
    pub n_lock_ave: u32,
    pub rel_lock_tol: f64,
    pub lock_sustain: u32,
    pub dfe_tap_tuners: Vec<(bool, f64, f64)>,
    pub viterbi_enabled: bool,
    pub viterbi_symbols: u32,
    pub viterbi_fec: bool,
    /// PyBERT's spectral periodic-component threshold (``thresh``).
    pub jitter_rel_thresh: f64,
    pub channel_response: Option<ChannelResponseV1>,
    pub ctle_impulse_response_v_per_v: Option<Vec<f64>>,
    pub unconsumed_keys: Vec<String>,
}

impl LegacyConfigProjectionV1 {
    pub(crate) fn simulation_input(
        &self,
        run_id: String,
    ) -> Result<SimulationInputV1, LegacyRuntimeError> {
        let modulation = match self.mod_type.as_str() {
            "NRZ" => ModulationV1::Nrz,
            "PAM-4" | "PAM4" => ModulationV1::Pam4,
            "DUO-BINARY" | "DUOBINARY" => ModulationV1::DuoBinary,
            _ => {
                return Err(LegacyRuntimeError::Unsupported(format!(
                    "mod_type={} (supported: NRZ, PAM-4, Duo-binary)",
                    self.mod_type
                )));
            }
        };
        let is_nrz = matches!(modulation, ModulationV1::Nrz);
        let pam4_symbol_ui =
            matches!(modulation, ModulationV1::Pam4) && !(self.viterbi_enabled && self.viterbi_fec);
        let order = self
            .pattern
            .strip_prefix("PRBS-")
            .ok_or_else(|| {
                LegacyRuntimeError::Unsupported("only PRBS patterns are migrated".into())
            })?
            .parse::<u8>()
            .map_err(|_| LegacyRuntimeError::InvalidConfig("pattern PRBS order".into()))?;
        if !(2..=63).contains(&order) {
            return Err(LegacyRuntimeError::InvalidConfig(
                "PRBS order is outside 2..=63".into(),
            ));
        }
        if !matches!(order, 7 | 9 | 11 | 13 | 15 | 19 | 20 | 23 | 31) {
            return Err(LegacyRuntimeError::Unsupported(
                "legacy CLI PRBS mapping supports orders 7, 9, 11, 13, 15, 19, 20, 23, and 31"
                    .into(),
            ));
        }
        // Match PyBERT's cached properties: non-FEC PAM-4 symbols occupy two
        // bit-rate UIs, while FEC PAM-4 keeps one UI per encoded bit.
        let ui = if pam4_symbol_ui {
            2.0 / (self.bit_rate_gbps * 1.0e9)
        } else {
            1.0 / (self.bit_rate_gbps * 1.0e9)
        };
        let sample_interval = ui / f64::from(self.nspui);
        let tx_weights = tx_weights(&self.tx_taps)?;
        let rx_weights = rx_weights(self.rx_n_taps, self.rx_n_pre)?;
        let dfe_taps = contiguous_dfe_count(&self.dfe_tap_tuners)?;
        // PyBERT always constructs a dummy DFE/CDR, even when all tap tuners
        // are disabled.  Keeping the typed configuration present preserves
        // clock/decision telemetry and the default BER branch.
        let dfe = Some(DfeConfigV1 {
            gain: self.gain,
            decision_scaler: Volts(self.decision_scaler_v),
            n_ave: self.n_ave,
            delta_t: Seconds(self.delta_t_ps * 1.0e-12),
            alpha: self.alpha,
            n_lock_ave: self.n_lock_ave,
            rel_lock_tol: self.rel_lock_tol,
            lock_sustain: self.lock_sustain,
            ideal: self.sum_ideal,
            bandwidth: Hertz(self.sum_bw_ghz * 1.0e9),
            use_agc: self.use_agc,
            agc_n_ave: self.n_ave,
            tap_limits: (dfe_taps > 0).then(|| {
                self.dfe_tap_tuners
                    .iter()
                    .take(dfe_taps)
                    .map(|(_, lower, upper)| (*lower, *upper))
                    .collect()
            }),
        });
        let ctle = (self.ctle_enable || self.ctle_impulse_response_v_per_v.is_some()).then_some(
            CtleConfigV1 {
                bandwidth: Hertz(self.rx_bw_ghz * 1.0e9),
                peak_frequency: Hertz(self.peak_freq_ghz * 1.0e9),
                peak_magnitude_db: self.peak_mag_db,
                frequency_step_hz: Some(Hertz(self.f_step_mhz * 1.0e6)),
                frequency_max_hz: Some(Hertz(self.f_max_ghz * 1.0e9)),
                impulse_response_v_per_v: self.ctle_impulse_response_v_per_v.clone(),
            },
        );
        let impulse_length =
            (self.impulse_length_ns > 0.0).then_some(Seconds(self.impulse_length_ns * 1.0e-9));
        let sample_count = usize::try_from(self.nbits)
            .ok()
            .and_then(|bits| {
                let symbols = if pam4_symbol_ui { bits / 2 } else { bits };
                symbols.checked_mul(self.nspui as usize)
            })
            .ok_or_else(|| LegacyRuntimeError::ResourceLimit("nbits*nspui overflow".into()))?;
        Ok(SimulationInputV1 {
            schema: SIMULATION_SCHEMA_V1.into(),
            run_id,
            modulation,
            pattern: PatternV1::Prbs {
                order,
                seed: self.seed,
            },
            timebase: TimebaseV1 {
                sample_interval: Seconds(sample_interval),
                samples_per_ui: self.nspui,
                data_rate: Hertz(1.0 / ui),
                nbits: self.nbits,
            },
            channel: self
                .channel_response
                .clone()
                .map(ChannelInputV1::ImpulseResponse)
                .unwrap_or_else(|| {
                    ChannelInputV1::MetallicLine(MetallicLineChannelV1 {
                        sample_interval: Seconds(sample_interval),
                        length_m: self.channel_length_m,
                        skin_effect_resistance_ohm_per_m: self.r0_ohm_per_m,
                        crossover_angular_frequency_rad_per_s: self.w0_rad_per_s,
                        dc_resistance_ohm_per_m: self.rdc_ohm_per_m,
                        characteristic_impedance: Ohms(self.z0_ohm),
                        propagation_velocity_m_per_s: self.v0_relative * 3.0e8,
                        loss_tangent: self.theta0,
                        source_impedance: Ohms(self.rs_ohm),
                        source_capacitance_f: self.cout_pf * 1.0e-12,
                        load_impedance: Ohms(self.rin_ohm),
                        load_capacitance_f: self.cin_pf * 1.0e-12,
                        apply_raised_cosine_window: self.use_window,
                        frequency_step_hz: Some(Hertz(self.f_step_mhz * 1.0e6)),
                        frequency_max_hz: Some(Hertz(self.f_max_ghz * 1.0e9)),
                        impulse_length,
                    })
                }),
            tx: TxConfigV1 {
                amplitude: Volts(self.vod_v),
                ffe: FfeConfigV1 {
                    enabled: true,
                    weights: tx_weights,
                    cursor_position: 3,
                },
                // PyBERT materializes ``random_noise`` even for rn=0.  Keep a
                // zero waveform in the typed request so the legacy result
                // adapter has a real, replayable array in every branch.
                additive_noise: Some(AdditiveNoiseV1 {
                    samples_v: if self.rn_v > 0.0 {
                        legacy_noise_samples(
                            self.rn_v,
                            self.random_noise_seed.unwrap_or(self.effective_seed),
                            sample_count,
                        )
                    } else {
                        vec![0.0; sample_count]
                    },
                    effective_seed: Some(self.random_noise_seed.unwrap_or(self.effective_seed)),
                }),
                periodic_noise: (self.pn_mag_v > 0.0).then_some(PeriodicNoiseV1 {
                    magnitude: Volts(self.pn_mag_v),
                    frequency: Hertz(self.pn_freq_mhz * 1.0e6),
                }),
            },
            rx: RxConfigV1 {
                native_ctle_enabled: self.ctle_enable
                    || self.ctle_impulse_response_v_per_v.is_some(),
                ctle,
                ffe: FfeConfigV1 {
                    enabled: self.rx_n_taps > 0,
                    weights: rx_weights,
                    cursor_position: self.rx_n_pre,
                },
                dfe_taps: dfe_taps as u32,
                dfe,
                viterbi_enabled: self.viterbi_enabled,
                viterbi: self.viterbi_enabled.then_some(ViterbiConfigV1 {
                    state_symbols: self.viterbi_symbols,
                    fec: self.viterbi_fec,
                    noise_sigma_v: (!self.viterbi_fec).then_some(Volts(self.rn_v)),
                    max_states: ResourceLimitsV1::default().max_distribution_states,
                }),
            },
            analysis: AnalysisConfigV1 {
                statistical_eye: is_nrz.then_some(crate::StatisticalEyeConfigV1 {
                    target_ber: 1.0e-5,
                    // PyBERT's statistical BER list includes the target
                    // contour itself before the two additional display
                    // levels.  The contour implementation already accepts
                    // this list; keep the legacy projection's defaults
                    // aligned without adding another eye algorithm.
                    contour_ber_levels: vec![1.0e-5, 1.0e-4, 1.0e-3],
                    rx_rj_ui: None,
                    rx_dj_ui: None,
                    tx_rj_ui: None,
                    tx_dj_ui: None,
                    tx_dcd_ui: None,
                    voltage_resolution: Some(Volts(1.0e-3)),
                    time_points: 400,
                    max_distribution_states: ResourceLimitsV1::default().max_distribution_states,
                    post_receiver_output: true,
                }),
                include_jitter: true,
                include_bathtub: true,
                ber_eye_bits: Some(self.eye_bits),
                jitter_eye_uis: Some(if pam4_symbol_ui {
                    (self.eye_bits / 2).max(1)
                } else {
                    self.eye_bits
                }),
                jitter_rel_thresh: Some(self.jitter_rel_thresh),
            },
            limits: ResourceLimitsV1::default(),
            external_models: Vec::new(),
            legacy_options: BTreeMap::new(),
        })
    }
}

/// Project one admitted legacy YAML document into the typed native request.
///
/// Keeping this helper beside the existing PB-01 parser lets PB-03/PB-04/PB-05
/// share the exact same bounded projection without duplicating defaults or
/// silently widening the accepted legacy surface.
pub fn project_legacy_config_v1(
    path: &Path,
    run_id: impl Into<String>,
) -> Result<(LegacyConfigProjectionV1, SimulationInputV1), LegacyRuntimeError> {
    let config = parse_legacy_config_v1(path)?;
    let input = config.simulation_input(run_id.into())?;
    Ok((config, input))
}

/// Result of running the migrated legacy leaf.
#[derive(Clone, Debug)]
pub struct LegacySimReportV1 {
    pub config: LegacyConfigProjectionV1,
    pub input: SimulationInputV1,
    pub output: SimulationOutputV1,
    pub result_path: PathBuf,
}

/// Parse and project a pinned PyBERT YAML configuration.
pub fn parse_legacy_config_v1(path: &Path) -> Result<LegacyConfigProjectionV1, LegacyRuntimeError> {
    let bytes = read_bounded_config(path)?;
    let value = if path.extension().and_then(|value| value.to_str()) == Some("pybert_cfg") {
        parse_legacy_pickle_config(&bytes)?
    } else {
        validate_yaml_tag_policy(&bytes)?;
        let value: Value = serde_yaml::from_slice(&bytes)?;
        strip_validated_yaml_tags(value, 0)?
    };
    let mapping = value
        .as_mapping()
        .ok_or(LegacyRuntimeError::ConfigNotMapping)?;
    validate_sequence_budget(mapping, "tx_taps", 6)?;
    validate_sequence_budget(mapping, "tx_tap_tuners", MAX_TX_TUNERS)?;
    validate_sequence_budget(mapping, "dfe_tap_tuners", MAX_DFE_TAPS)?;
    let tx_external_parent = mapping
        .get(Value::String("tx_use_ami".into()))
        .and_then(Value::as_bool)
        .unwrap_or(false)
        || mapping
            .get(Value::String("tx_use_ibis".into()))
            .and_then(Value::as_bool)
            .unwrap_or(false);
    let rx_external_parent = mapping
        .get(Value::String("rx_use_ami".into()))
        .and_then(Value::as_bool)
        .unwrap_or(false)
        || mapping
            .get(Value::String("rx_use_ibis".into()))
            .and_then(Value::as_bool)
            .unwrap_or(false);
    for key in UNSUPPORTED_ENABLED_KEYS {
        if mapping
            .get(Value::String((*key).into()))
            .and_then(Value::as_bool)
            .unwrap_or(false)
        {
            return Err(LegacyRuntimeError::Unsupported(format!("{key}=true")));
        }
    }
    for (key, parent_enabled) in [
        ("tx_use_ts4", tx_external_parent),
        ("tx_use_getwave", tx_external_parent),
        ("rx_use_ts4", rx_external_parent),
        ("rx_use_getwave", rx_external_parent),
    ] {
        if mapping
            .get(Value::String(key.into()))
            .and_then(Value::as_bool)
            .unwrap_or(false)
            && parent_enabled
        {
            return Err(LegacyRuntimeError::Unsupported(format!(
                "{key}=true requires AMI/IBIS"
            )));
        }
    }
    let unconsumed_keys = mapping
        .keys()
        .filter_map(Value::as_str)
        .filter(|key| !CONSUMED_KEYS.contains(key) && !IGNORED_INERT_KEYS.contains(key))
        .map(ToOwned::to_owned)
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect::<Vec<_>>();
    if !unconsumed_keys.is_empty() {
        return Err(LegacyRuntimeError::Unsupported(format!(
            "unclassified top-level keys: {}",
            unconsumed_keys.join(", ")
        )));
    }
    let raw: RawLegacyConfig = serde_yaml::from_value(value)?;
    let requested_seed = raw.seed.unwrap_or(1);
    let effective_seed = nonzero_seed(requested_seed);
    let mut config = LegacyConfigProjectionV1 {
        bit_rate_gbps: finite_positive(raw.bit_rate.unwrap_or(DEFAULT_BIT_RATE_GBPS), "bit_rate")?,
        nbits: raw.nbits.unwrap_or(DEFAULT_NBITS),
        pattern: raw.pattern.unwrap_or_else(|| "PRBS-7".into()),
        requested_seed,
        effective_seed,
        seed: effective_seed,
        random_noise_seed: raw.random_noise_seed,
        nspui: raw.nspui.unwrap_or(DEFAULT_NSPUI),
        eye_bits: raw.eye_bits.unwrap_or(DEFAULT_EYE_BITS),
        mod_type: canonical_modulation(raw.mod_type.unwrap_or_else(|| "NRZ".into()))?,
        f_max_ghz: finite_positive(raw.f_max.unwrap_or(DEFAULT_FMAX_GHZ), "f_max")?,
        f_step_mhz: finite_positive(raw.f_step.unwrap_or(DEFAULT_FSTEP_MHZ), "f_step")?,
        impulse_length_ns: finite_non_negative(
            raw.impulse_length.unwrap_or(0.0),
            "impulse_length",
        )?,
        use_window: raw.use_window.unwrap_or(false),
        channel_length_m: finite_non_negative(
            raw.l_ch.unwrap_or(DEFAULT_CHANNEL_LENGTH_M),
            "l_ch",
        )?,
        rdc_ohm_per_m: finite_non_negative(raw.rdc.unwrap_or(DEFAULT_RDC), "Rdc")?,
        w0_rad_per_s: finite_positive(raw.w0.unwrap_or(DEFAULT_W0), "w0")?,
        r0_ohm_per_m: finite_non_negative(raw.r0.unwrap_or(DEFAULT_R0), "R0")?,
        theta0: finite_non_negative(raw.theta0.unwrap_or(DEFAULT_THETA0), "Theta0")?,
        z0_ohm: finite_positive(raw.z0.unwrap_or(DEFAULT_Z0), "Z0")?,
        v0_relative: finite_positive(raw.v0.unwrap_or(DEFAULT_V0), "v0")?,
        vod_v: finite_positive(raw.vod.unwrap_or(DEFAULT_VOD), "vod")?,
        rs_ohm: finite_positive(raw.rs.unwrap_or(DEFAULT_RS), "rs")?,
        cout_pf: finite_non_negative(raw.cout.unwrap_or(DEFAULT_COUT_PF), "cout")?,
        pn_mag_v: finite_non_negative(raw.pn_mag.unwrap_or(DEFAULT_PN_MAG_V), "pn_mag")?,
        pn_freq_mhz: finite_positive(raw.pn_freq.unwrap_or(DEFAULT_PN_FREQ_MHZ), "pn_freq")?,
        rn_v: finite_non_negative(raw.rn.unwrap_or(DEFAULT_RN_V), "rn")?,
        rin_ohm: finite_positive(raw.rin.unwrap_or(DEFAULT_RIN), "rin")?,
        cin_pf: finite_non_negative(raw.cin.unwrap_or(DEFAULT_CIN_PF), "cin")?,
        rx_bw_ghz: finite_positive(raw.rx_bw.unwrap_or(DEFAULT_RX_BW_GHZ), "rx_bw")?,
        peak_freq_ghz: finite_positive(
            raw.peak_freq.unwrap_or(DEFAULT_PEAK_FREQ_GHZ),
            "peak_freq",
        )?,
        peak_mag_db: finite_non_negative(raw.peak_mag.unwrap_or(DEFAULT_PEAK_MAG_DB), "peak_mag")?,
        ctle_enable: raw.ctle_enable.unwrap_or(true),
        tx_taps: raw.tx_taps.unwrap_or_else(default_tx_taps),
        rx_n_taps: usize::try_from(raw.rx_n_taps.unwrap_or(DEFAULT_N_TAPS as u32))
            .map_err(|_| LegacyRuntimeError::InvalidConfig("rx_n_taps".into()))?,
        rx_n_pre: usize::try_from(raw.rx_n_pre.unwrap_or(DEFAULT_N_PRE as u32))
            .map_err(|_| LegacyRuntimeError::InvalidConfig("rx_n_pre".into()))?,
        sum_ideal: raw.sum_ideal.unwrap_or(true),
        decision_scaler_v: finite_positive(raw.decision_scaler.unwrap_or(0.5), "decision_scaler")?,
        gain: finite_non_negative(raw.gain.unwrap_or(0.1), "gain")?,
        n_ave: finite_u32(raw.n_ave.unwrap_or(100.0), "n_ave")?,
        sum_bw_ghz: finite_non_negative(raw.sum_bw.unwrap_or(12.0), "sum_bw")?,
        use_agc: raw.use_agc.unwrap_or(true),
        delta_t_ps: finite_positive(raw.delta_t.unwrap_or(0.1), "delta_t")?,
        alpha: finite_non_negative(raw.alpha.unwrap_or(0.01), "alpha")?,
        n_lock_ave: raw.n_lock_ave.unwrap_or(500),
        rel_lock_tol: finite_non_negative(raw.rel_lock_tol.unwrap_or(0.1), "rel_lock_tol")?,
        lock_sustain: raw.lock_sustain.unwrap_or(500),
        dfe_tap_tuners: raw.dfe_tap_tuners.unwrap_or_else(default_dfe_tap_tuners),
        viterbi_enabled: raw.rx_use_viterbi.unwrap_or(false),
        viterbi_symbols: raw.rx_viterbi_symbols.unwrap_or(4),
        viterbi_fec: raw.rx_viterbi_fec.unwrap_or(false),
        jitter_rel_thresh: finite_positive(raw.thresh.unwrap_or(3.0), "thresh")?,
        channel_response: None,
        ctle_impulse_response_v_per_v: None,
        unconsumed_keys,
    };
    if config.viterbi_enabled && !config.viterbi_fec && config.rn_v <= 0.0 {
        return Err(LegacyRuntimeError::Unsupported(
            "rx_use_viterbi=true requires rn>0 for the native ISI decoder".into(),
        ));
    }
    if config.pn_mag_v == 0.0 && raw.pn_freq.is_some() {
        // Preserve an explicitly configured frequency as metadata, but do not
        // manufacture a periodic waveform when its magnitude is disabled.
        config.pn_freq_mhz = finite_positive(raw.pn_freq.unwrap_or(1.0), "pn_freq")?;
    }
    if config.nbits < MIN_NBITS {
        return Err(LegacyRuntimeError::InvalidConfig(
            "nbits must satisfy pinned PyBERT minimum 1000".into(),
        ));
    }
    if config.nspui < 2 {
        return Err(LegacyRuntimeError::InvalidConfig(
            "nspui must satisfy the Nyquist minimum of 2".into(),
        ));
    }
    if config.use_window && config.f_max_ghz <= 0.0 {
        return Err(LegacyRuntimeError::InvalidConfig("use_window/f_max".into()));
    }
    contiguous_dfe_count(&config.dfe_tap_tuners)?;
    if config.rx_n_taps > 0 && config.rx_n_pre >= config.rx_n_taps {
        return Err(LegacyRuntimeError::InvalidConfig(
            "rx_n_pre must be less than rx_n_taps".into(),
        ));
    }
    // Keep file-backed channel/CTLE sampling on the same UI as the projected
    // native request.  Non-FEC PAM-4 consumes two bit-rate UIs per symbol.
    let ui = if config.mod_type == "PAM-4" && !(config.viterbi_enabled && config.viterbi_fec) {
        2.0 / (config.bit_rate_gbps * 1.0e9)
    } else {
        1.0 / (config.bit_rate_gbps * 1.0e9)
    };
    let sample_interval = ui / f64::from(config.nspui);
    let sample_count = usize::try_from(config.nbits)
        .ok()
        .and_then(|bits| {
            let symbols =
                if config.mod_type == "PAM-4" && !(config.viterbi_enabled && config.viterbi_fec) {
                    bits / 2
                } else {
                    bits
                };
            symbols.checked_mul(config.nspui as usize)
        })
        .ok_or_else(|| LegacyRuntimeError::ResourceLimit("nbits*nspui overflow".into()))?;
    if raw.use_ch_file.unwrap_or(false) {
        let path = resolve_legacy_data_path(path, raw.ch_file.as_deref())?;
        let frequency_max_hz = config.f_max_ghz * 1.0e9;
        let frequency_step_hz = config.f_step_mhz * 1.0e6;
        let grid_is_supported = frequency_max_hz <= 0.5 / sample_interval;
        if is_touchstone_path(&path) && !grid_is_supported {
            return Err(LegacyRuntimeError::Unsupported(
                "S2P frequency grid exceeds the sample Nyquist limit".into(),
            ));
        }
        let output_len = if config.impulse_length_ns > 0.0 {
            let requested = config.impulse_length_ns * 1.0e-9 / sample_interval;
            if !requested.is_finite() || requested < 2.0 || requested > usize::MAX as f64 {
                return Err(LegacyRuntimeError::ResourceLimit(
                    "impulse_length exceeds the bounded sample budget".into(),
                ));
            }
            Some(requested.floor() as usize)
        } else {
            None
        };
        let (trim_min_len, trim_max_len) = if let Some(length) = output_len {
            (length, length)
        } else {
            let nspui = config.nspui as usize;
            let minimum = 20usize.checked_mul(nspui).ok_or_else(|| {
                LegacyRuntimeError::ResourceLimit("S2P trim length overflow".into())
            })?;
            let maximum = 100usize.checked_mul(nspui).ok_or_else(|| {
                LegacyRuntimeError::ResourceLimit("S2P trim length overflow".into())
            })?;
            (minimum, maximum)
        };
        config.channel_response = Some(
            parse_touchstone_response_with_options(
                &path,
                Seconds(sample_interval),
                sample_count,
                Ohms(config.rs_ohm),
                Ohms(config.rin_ohm),
                raw.renumber.unwrap_or(false),
                S2pImportOptions {
                    frequency_step_hz: grid_is_supported.then_some(frequency_step_hz),
                    frequency_max_hz: grid_is_supported.then_some(frequency_max_hz),
                    source_capacitance_pf: config.cout_pf,
                    load_capacitance_pf: config.cin_pf,
                    output_len,
                    trim_min_len: Some(trim_min_len),
                    trim_max_len: Some(trim_max_len),
                    trim_front_porch: 1,
                },
            )
            .map_err(|error| LegacyRuntimeError::Unsupported(format!("S2P channel: {error}")))?,
        );
    }
    if raw.use_ctle_file.unwrap_or(false) {
        let path = resolve_legacy_data_path(path, raw.ctle_file.as_deref())?;
        let frequency_max_hz = config.f_max_ghz * 1.0e9;
        let frequency_step_hz = config.f_step_mhz * 1.0e6;
        let grid_is_supported = frequency_max_hz <= 0.5 / sample_interval;
        if is_touchstone_path(&path) && !grid_is_supported {
            return Err(LegacyRuntimeError::Unsupported(
                "CTLE S2P frequency grid exceeds the sample Nyquist limit".into(),
            ));
        }
        let response = parse_touchstone_response_with_options(
            &path,
            Seconds(sample_interval),
            sample_count,
            Ohms(50.0),
            Ohms(50.0),
            raw.renumber.unwrap_or(false),
            S2pImportOptions {
                frequency_step_hz: grid_is_supported.then_some(frequency_step_hz),
                frequency_max_hz: grid_is_supported.then_some(frequency_max_hz),
                source_capacitance_pf: 0.0,
                load_capacitance_pf: 0.0,
                output_len: Some(sample_count),
                trim_min_len: None,
                trim_max_len: None,
                trim_front_porch: 0,
            },
        )
        .map_err(|error| LegacyRuntimeError::Unsupported(format!("CTLE S2P file: {error}")))?;
        config.ctle_impulse_response_v_per_v = Some(
            response
                .impulse_response_volts_per_second
                .into_iter()
                .map(|sample| sample * sample_interval)
                .collect(),
        );
    }
    validate_projection_budgets(&config)?;
    Ok(config)
}

fn is_touchstone_path(path: &Path) -> bool {
    matches!(
        path.extension()
            .and_then(|value| value.to_str())
            .map(|value| value.to_ascii_lowercase())
            .as_deref(),
        Some("s1p" | "s2p" | "s4p")
    )
}

/// Decode only the state mapping emitted by PyBERT's `PyBertCfg` pickle.
///
/// `serde-pickle` is used as a data parser with unresolved globals replaced by
/// inert values; it is never allowed to restore Python classes or invoke a
/// host runtime.  The class marker and bounded, string-keyed mapping checks
/// keep this compatibility path fail-closed for arbitrary pickle payloads.
fn parse_legacy_pickle_config(bytes: &[u8]) -> Result<Value, LegacyRuntimeError> {
    const PYBERT_CFG_MARKER: &[u8] = b"pybert.configuration\nPyBertCfg\n";
    // A marker buried in a dict/string is not proof that the pickle root is a
    // PyBertCfg.  PyBERT historically emitted protocol 3, while current
    // Python emits protocol 4/5 with FRAME + STACK_GLOBAL.  Recognize only
    // those exact root opcode layouts; unresolved class state is still parsed
    // as inert data below and never restored through Python.
    let root_global = if bytes.len() >= 4 && bytes[0] == 0x80 {
        match bytes[1] {
            3 => bytes[2..].starts_with(b"c") && bytes[3..].starts_with(PYBERT_CFG_MARKER),
            4 | 5 => pickle_protocol45_root_is_pybert_cfg(bytes),
            _ => false,
        }
    } else {
        false
    };
    if !root_global {
        return Err(LegacyRuntimeError::Unsupported(
            "pickle root is not the pinned PyBertCfg global".into(),
        ));
    }
    let pickle = value_from_slice(
        bytes,
        DeOptions::new()
            .keep_restore_state()
            .replace_unresolved_globals(),
    )
    .map_err(|error| LegacyRuntimeError::InvalidConfig(format!("PyBertCfg pickle: {error}")))?;
    let mut value_budget = 0;
    let json = pickle_value_to_json(pickle, 0, &mut value_budget)?;
    if !json.is_object() {
        return Err(LegacyRuntimeError::InvalidConfig(
            "PyBertCfg pickle state must be a mapping".into(),
        ));
    }
    serde_yaml::to_value(json)
        .map_err(|error| LegacyRuntimeError::InvalidConfig(format!("PyBertCfg mapping: {error}")))
}

fn pickle_protocol45_root_is_pybert_cfg(bytes: &[u8]) -> bool {
    const MODULE: &[u8] = b"pybert.configuration";
    const CLASS: &[u8] = b"PyBertCfg";
    let mut cursor = 2;
    // A protocol-4/5 PyBertCfg root starts with PROTO, an optional FRAME,
    // two memoized SHORT_BINUNICODE names, and STACK_GLOBAL. Walking this
    // prefix instead of searching the payload prevents a nested global from
    // being mistaken for the root class identity.
    if bytes.get(cursor) == Some(&0x95) {
        cursor = match cursor.checked_add(9) {
            Some(cursor) => cursor,
            None => return false,
        };
    }
    if read_pickle_short_unicode(bytes, &mut cursor) != Some(MODULE)
        || bytes.get(cursor) != Some(&0x94)
    {
        return false;
    }
    cursor += 1;
    if read_pickle_short_unicode(bytes, &mut cursor) != Some(CLASS)
        || bytes.get(cursor) != Some(&0x94)
    {
        return false;
    }
    cursor += 1;
    bytes.get(cursor) == Some(&0x93)
}

fn read_pickle_short_unicode<'a>(bytes: &'a [u8], cursor: &mut usize) -> Option<&'a [u8]> {
    if bytes.get(*cursor) != Some(&0x8c) {
        return None;
    }
    let length = usize::from(*bytes.get(cursor.checked_add(1)?)?);
    let start = cursor.checked_add(2)?;
    let end = start.checked_add(length)?;
    let value = bytes.get(start..end)?;
    *cursor = end;
    Some(value)
}

fn pickle_value_to_json(
    value: PickleValue,
    depth: usize,
    value_budget: &mut usize,
) -> Result<JsonValue, LegacyRuntimeError> {
    if depth > MAX_YAML_DEPTH {
        return Err(LegacyRuntimeError::ResourceLimit(
            "PyBertCfg pickle nesting exceeds 64 levels".into(),
        ));
    }
    *value_budget = value_budget.checked_add(1).ok_or_else(|| {
        LegacyRuntimeError::ResourceLimit("PyBertCfg pickle value overflow".into())
    })?;
    if *value_budget > MAX_PICKLE_VALUES {
        return Err(LegacyRuntimeError::ResourceLimit(
            "PyBertCfg pickle contains too many values".into(),
        ));
    }
    match value {
        PickleValue::None => Ok(JsonValue::Null),
        PickleValue::Bool(value) => Ok(JsonValue::Bool(value)),
        PickleValue::I64(value) => Ok(JsonValue::Number(value.into())),
        PickleValue::Int(value) => {
            let value = value.to_string().parse::<i64>().map_err(|_| {
                LegacyRuntimeError::InvalidConfig("PyBertCfg integer is outside i64".into())
            })?;
            Ok(JsonValue::Number(value.into()))
        }
        PickleValue::F64(value) if value.is_finite() => {
            let number = serde_json::Number::from_f64(value).ok_or_else(|| {
                LegacyRuntimeError::InvalidConfig("PyBertCfg float is not JSON-safe".into())
            })?;
            Ok(JsonValue::Number(number))
        }
        PickleValue::F64(_) => Err(LegacyRuntimeError::InvalidConfig(
            "PyBertCfg float must be finite".into(),
        )),
        PickleValue::String(value) => Ok(JsonValue::String(value)),
        PickleValue::Bytes(_) => Err(LegacyRuntimeError::Unsupported(
            "PyBertCfg byte strings are not in the portable configuration subset".into(),
        )),
        PickleValue::List(values) | PickleValue::Tuple(values) => values
            .into_iter()
            .map(|value| pickle_value_to_json(value, depth + 1, value_budget))
            .collect::<Result<Vec<_>, _>>()
            .map(JsonValue::Array),
        PickleValue::Set(values) | PickleValue::FrozenSet(values) => values
            .into_iter()
            .map(HashableValue::into_value)
            .map(|value| pickle_value_to_json(value, depth + 1, value_budget))
            .collect::<Result<Vec<_>, _>>()
            .map(JsonValue::Array),
        PickleValue::Dict(values) => values
            .into_iter()
            .map(|(key, value)| {
                let key = pickle_key_to_string(key)?;
                Ok((key, pickle_value_to_json(value, depth + 1, value_budget)?))
            })
            .collect::<Result<serde_json::Map<_, _>, LegacyRuntimeError>>()
            .map(JsonValue::Object),
    }
}

fn pickle_key_to_string(key: HashableValue) -> Result<String, LegacyRuntimeError> {
    match key {
        HashableValue::String(value) => Ok(value),
        HashableValue::Bytes(_) => Err(LegacyRuntimeError::InvalidConfig(
            "PyBertCfg mapping keys must be strings".into(),
        )),
        _ => Err(LegacyRuntimeError::InvalidConfig(
            "PyBertCfg mapping keys must be strings".into(),
        )),
    }
}

/// Execute the migrated leaf and write the bounded Python-readable artifact.
pub fn run_legacy_sim_v1(
    request: &LegacySimRequestV1,
) -> Result<LegacySimReportV1, LegacyRuntimeError> {
    run_legacy_sim_with_codec_v1(request, LegacyResultCodecV1::SipiDictionary)
}

/// Execute the migrated leaf with an explicit result codec.
///
/// Both codecs share the same `SimulationInputV1 -> simulate_native_v1`
/// path; this dispatcher changes serialization only.
pub fn run_legacy_sim_with_codec_v1(
    request: &LegacySimRequestV1,
    codec: LegacyResultCodecV1,
) -> Result<LegacySimReportV1, LegacyRuntimeError> {
    crate::validate_legacy_sim_request(request).map_err(|error| match error {
        LegacySimError::ConfigIo(error) => LegacyRuntimeError::Io(error),
        other => LegacyRuntimeError::InvalidConfig(other.to_string()),
    })?;
    let config = parse_legacy_config_v1(&request.config_file)?;
    let run_id = request
        .config_file
        .file_stem()
        .and_then(|value| value.to_str())
        .filter(|value| !value.is_empty())
        .unwrap_or("pb-01-legacy")
        .to_owned();
    let input = config.simulation_input(run_id)?;
    let mut output = simulate_native_v1(&input)?;
    output
        .metrics
        .insert("requested_seed".into(), config.requested_seed as f64);
    output
        .metrics
        .insert("effective_seed".into(), config.effective_seed as f64);
    output.metrics.insert(
        "effective_noise_seed".into(),
        config.random_noise_seed.unwrap_or(config.effective_seed) as f64,
    );
    let result_path = request
        .resolved_results_path()
        .map_err(|error| LegacyRuntimeError::InvalidConfig(error.to_string()))?;
    match codec {
        LegacyResultCodecV1::SipiDictionary => write_legacy_result_v1(&result_path, &output)?,
        LegacyResultCodecV1::ClassPickle => write_legacy_class_result_v1(&result_path, &output)?,
    }
    Ok(LegacySimReportV1 {
        config,
        input,
        output,
        result_path,
    })
}

/// Write a Python pickle dictionary under the legacy result suffix.
///
/// The payload intentionally uses canonical PyBERT item names and f64 arrays,
/// while identifying itself as `sipi.pybert_data.v1`. The explicit class-load
/// compatible codec is selected through [`run_legacy_sim_with_codec_v1`]; this
/// established default remains data-only.
pub fn write_legacy_result_v1(
    path: &Path,
    output: &SimulationOutputV1,
) -> Result<(), LegacyRuntimeError> {
    validate_legacy_result_budget(output)?;
    let arrays = legacy_arrays(output)?;
    let payload = LegacyPicklePayload {
        schema: "sipi.pybert_data.v1",
        artifact_kind: "legacy_item_name_pickle_dict",
        item_names: LEGACY_ITEM_NAMES.to_vec(),
        arrays,
        metrics: output.metrics.clone(),
        source: "pinned_pybert_native_core_scoped_leaf",
    };
    if let Some(parent) = path
        .parent()
        .filter(|parent| !parent.as_os_str().is_empty())
    {
        fs::create_dir_all(parent)?;
    }
    let bytes = to_vec(&payload, SerOptions::new())?;
    if bytes.len() > MAX_LEGACY_RESULT_BYTES {
        return Err(LegacyRuntimeError::ResourceLimit(
            "serialized .pybert_data exceeds 512 MiB".into(),
        ));
    }
    fs::write(path, bytes)?;
    Ok(())
}

fn write_legacy_class_result_v1(
    path: &Path,
    output: &SimulationOutputV1,
) -> Result<(), LegacyRuntimeError> {
    output
        .validate()
        .map_err(|error| LegacyRuntimeError::InvalidConfig(error.to_string()))?;
    let layout = LegacyArrayLayout::from_output(output)?;
    layout.validate_class_codec_peak()?;
    publish_legacy_class_result(path, |file| {
        let projection = LegacyArrayProjection::new(output)?;
        let mut pickle = LegacyClassPickleWriter::new(file, MAX_LEGACY_RESULT_BYTES);
        write_legacy_class_pickle(&mut pickle, &projection)?;
        pickle.finish()
    })
}

fn write_legacy_class_pickle<W: Write>(
    pickle: &mut LegacyClassPickleWriter<W>,
    arrays: &LegacyArrayProjection<'_>,
) -> Result<(), LegacyRuntimeError> {
    pickle.protocol(LEGACY_CLASS_PICKLE_PROTOCOL)?;
    pickle.global("pybert.results", "PyBertData")?;
    pickle.empty_tuple()?;
    pickle.new_object()?;
    pickle.empty_dict()?;
    pickle.mark()?;
    pickle.bin_unicode("the_data")?;
    pickle.global("chaco.array_plot_data", "ArrayPlotData")?;
    pickle.empty_tuple()?;
    pickle.new_object()?;
    pickle.empty_dict()?;
    pickle.mark()?;
    pickle.bin_unicode("arrays")?;
    write_legacy_trait_dict(pickle, arrays)?;
    pickle.bin_unicode("writable")?;
    pickle.new_true()?;
    pickle.bin_unicode("selectable")?;
    pickle.new_true()?;
    pickle.bin_unicode("__traits_version__")?;
    pickle.bin_unicode("7.1.0")?;
    pickle.set_items()?;
    pickle.build()?;
    pickle.bin_unicode("date_created")?;
    pickle.bin_unicode(LEGACY_CLASS_DATE_CREATED)?;
    pickle.bin_unicode("version")?;
    pickle.bin_unicode(LEGACY_CLASS_VERSION)?;
    pickle.set_items()?;
    pickle.build()?;
    pickle.stop()
}

fn write_legacy_trait_dict<W: Write>(
    pickle: &mut LegacyClassPickleWriter<W>,
    arrays: &LegacyArrayProjection<'_>,
) -> Result<(), LegacyRuntimeError> {
    pickle.global("traits.trait_dict_object", "TraitDictObject")?;
    pickle.empty_tuple()?;
    pickle.new_object()?;
    let memo = pickle.memo()?;
    arrays.visit(response_spectrum_db, |name, values| {
        pickle.bin_unicode(name)?;
        pickle.numpy_f64_array(values)?;
        pickle.set_item()
    })?;

    // Traits stores these validators and bookkeeping fields in the state
    // mapping.  Keeping the same state shape lets the pinned ArrayPlotData
    // loader reconstruct a real TraitDictObject instead of a plain dict.
    pickle.empty_dict()?;
    pickle.mark()?;
    pickle.bin_unicode("key_validator")?;
    pickle.getattr(memo, "_key_validator")?;
    pickle.bin_unicode("value_validator")?;
    pickle.getattr(memo, "_value_validator")?;
    pickle.bin_unicode("name")?;
    pickle.bin_unicode("arrays")?;
    pickle.bin_unicode("name_items")?;
    pickle.bin_unicode("arrays_items")?;
    pickle.set_items()?;
    pickle.build()?;
    Ok(())
}

struct LegacyClassPickleWriter<W> {
    sink: W,
    digest: Sha256,
    byte_count: usize,
    max_bytes: usize,
    next_memo: u16,
}

impl<W: Write> LegacyClassPickleWriter<W> {
    fn new(sink: W, max_bytes: usize) -> Self {
        Self {
            sink,
            digest: Sha256::new(),
            byte_count: 0,
            max_bytes,
            next_memo: 0,
        }
    }

    fn append(&mut self, bytes: &[u8]) -> Result<(), LegacyRuntimeError> {
        let next = self.byte_count.checked_add(bytes.len()).ok_or_else(|| {
            LegacyRuntimeError::ResourceLimit("class pickle byte count overflow".into())
        })?;
        if next > self.max_bytes {
            return Err(LegacyRuntimeError::ResourceLimit(
                "class-compatible .pybert_data exceeds 512 MiB".into(),
            ));
        }
        self.sink.write_all(bytes)?;
        self.digest.update(bytes);
        self.byte_count = next;
        Ok(())
    }

    fn byte(&mut self, byte: u8) -> Result<(), LegacyRuntimeError> {
        self.append(&[byte])
    }

    fn u8(&mut self, value: u8) -> Result<(), LegacyRuntimeError> {
        self.byte(value)
    }

    fn u32(&mut self, value: u32) -> Result<(), LegacyRuntimeError> {
        self.append(&value.to_le_bytes())
    }

    fn i32(&mut self, value: i32) -> Result<(), LegacyRuntimeError> {
        self.append(&value.to_le_bytes())
    }

    fn protocol(&mut self, protocol: u8) -> Result<(), LegacyRuntimeError> {
        self.byte(0x80)?;
        self.u8(protocol)
    }

    fn global(&mut self, module: &str, name: &str) -> Result<(), LegacyRuntimeError> {
        self.byte(b'c')?;
        self.append(module.as_bytes())?;
        self.byte(b'\n')?;
        self.append(name.as_bytes())?;
        self.byte(b'\n')
    }

    fn empty_tuple(&mut self) -> Result<(), LegacyRuntimeError> {
        self.byte(b')')
    }

    fn empty_dict(&mut self) -> Result<(), LegacyRuntimeError> {
        self.byte(b'}')
    }

    fn mark(&mut self) -> Result<(), LegacyRuntimeError> {
        self.byte(b'(')
    }

    fn bin_unicode(&mut self, value: &str) -> Result<(), LegacyRuntimeError> {
        let bytes = value.as_bytes();
        let length = u32::try_from(bytes.len()).map_err(|_| {
            LegacyRuntimeError::ResourceLimit("class pickle string length overflow".into())
        })?;
        self.byte(b'X')?;
        self.u32(length)?;
        self.append(bytes)
    }

    fn short_bin_bytes(&mut self, bytes: &[u8]) -> Result<(), LegacyRuntimeError> {
        let length = u8::try_from(bytes.len()).map_err(|_| {
            LegacyRuntimeError::ResourceLimit("class pickle short bytes length overflow".into())
        })?;
        self.byte(b'C')?;
        self.u8(length)?;
        self.append(bytes)
    }

    fn bin_f64_values(&mut self, values: &[f64]) -> Result<(), LegacyRuntimeError> {
        let length = values
            .len()
            .checked_mul(std::mem::size_of::<f64>())
            .and_then(|length| u32::try_from(length).ok())
            .ok_or_else(|| {
                LegacyRuntimeError::ResourceLimit("class pickle f64 byte length overflow".into())
            })?;
        self.byte(b'B')?;
        self.u32(length)?;
        let mut encoded = [0_u8; LEGACY_F64_WRITE_CHUNK_VALUES * std::mem::size_of::<f64>()];
        for chunk in values.chunks(LEGACY_F64_WRITE_CHUNK_VALUES) {
            for (index, value) in chunk.iter().enumerate() {
                let start = index * std::mem::size_of::<f64>();
                encoded[start..start + std::mem::size_of::<f64>()]
                    .copy_from_slice(&value.to_le_bytes());
            }
            self.append(&encoded[..std::mem::size_of_val(chunk)])?;
        }
        Ok(())
    }

    fn new_object(&mut self) -> Result<(), LegacyRuntimeError> {
        self.byte(0x81)
    }

    fn new_true(&mut self) -> Result<(), LegacyRuntimeError> {
        self.byte(0x88)
    }

    fn memo(&mut self) -> Result<u8, LegacyRuntimeError> {
        let memo = u8::try_from(self.next_memo).map_err(|_| {
            LegacyRuntimeError::ResourceLimit("class pickle memo table overflow".into())
        })?;
        self.next_memo = self.next_memo.checked_add(1).ok_or_else(|| {
            LegacyRuntimeError::ResourceLimit("class pickle memo table overflow".into())
        })?;
        self.byte(b'q')?;
        self.u8(memo)?;
        Ok(memo)
    }

    fn get_memo(&mut self, memo: u8) -> Result<(), LegacyRuntimeError> {
        self.byte(b'h')?;
        self.u8(memo)
    }

    fn tuple2(&mut self) -> Result<(), LegacyRuntimeError> {
        self.byte(0x86)
    }

    fn tuple3(&mut self) -> Result<(), LegacyRuntimeError> {
        self.byte(0x87)
    }

    fn tuple1(&mut self) -> Result<(), LegacyRuntimeError> {
        self.byte(0x85)
    }

    fn tuple(&mut self) -> Result<(), LegacyRuntimeError> {
        self.byte(b't')
    }

    fn reduce(&mut self) -> Result<(), LegacyRuntimeError> {
        self.byte(b'R')
    }

    fn set_item(&mut self) -> Result<(), LegacyRuntimeError> {
        self.byte(b's')
    }

    fn set_items(&mut self) -> Result<(), LegacyRuntimeError> {
        self.byte(b'u')
    }

    fn build(&mut self) -> Result<(), LegacyRuntimeError> {
        self.byte(b'b')
    }

    fn stop(&mut self) -> Result<(), LegacyRuntimeError> {
        self.byte(b'.')
    }

    fn getattr(&mut self, object_memo: u8, name: &str) -> Result<(), LegacyRuntimeError> {
        self.global("builtins", "getattr")?;
        self.get_memo(object_memo)?;
        self.bin_unicode(name)?;
        self.tuple2()?;
        self.reduce()
    }

    fn pickle_int(&mut self, value: usize) -> Result<(), LegacyRuntimeError> {
        if value <= u8::MAX as usize {
            self.byte(b'K')?;
            self.u8(value as u8)
        } else if value <= u16::MAX as usize {
            self.byte(b'M')?;
            self.append(&(value as u16).to_le_bytes())
        } else {
            let value = i32::try_from(value).map_err(|_| {
                LegacyRuntimeError::ResourceLimit("class pickle shape exceeds int32".into())
            })?;
            self.byte(b'J')?;
            self.i32(value)
        }
    }

    fn numpy_f64_array(&mut self, values: &[f64]) -> Result<(), LegacyRuntimeError> {
        self.global("numpy._core.multiarray", "_reconstruct")?;
        self.global("numpy", "ndarray")?;
        self.byte(b'K')?;
        self.u8(0)?;
        self.tuple1()?;
        self.short_bin_bytes(b"b")?;
        self.tuple3()?;
        self.reduce()?;
        self.mark()?;
        self.pickle_int(1)?;
        self.pickle_int(values.len())?;
        self.tuple1()?;
        self.global("numpy", "dtype")?;
        self.bin_unicode("f8")?;
        self.byte(0x89)?;
        self.new_true()?;
        self.tuple3()?;
        self.reduce()?;
        self.mark()?;
        self.pickle_int(3)?;
        self.bin_unicode("<")?;
        self.byte(b'N')?;
        self.byte(b'N')?;
        self.byte(b'N')?;
        self.byte(b'J')?;
        self.i32(-1)?;
        self.byte(b'J')?;
        self.i32(-1)?;
        self.pickle_int(0)?;
        self.tuple()?;
        self.build()?;
        self.byte(0x89)?;
        self.bin_f64_values(values)?;
        self.tuple()?;
        self.build()
    }

    fn finish(self) -> Result<(W, usize, [u8; 32]), LegacyRuntimeError> {
        Ok((self.sink, self.byte_count, self.digest.finalize().into()))
    }
}

#[derive(Debug, Serialize)]
struct LegacyPicklePayload {
    schema: &'static str,
    artifact_kind: &'static str,
    item_names: Vec<&'static str>,
    arrays: BTreeMap<String, Vec<f64>>,
    metrics: BTreeMap<String, f64>,
    source: &'static str,
}

struct TemporaryResult {
    path: PathBuf,
}

impl Drop for TemporaryResult {
    fn drop(&mut self) {
        let _ = fs::remove_file(&self.path);
    }
}

fn publish_legacy_class_result(
    path: &Path,
    encode: impl FnOnce(File) -> Result<(File, usize, [u8; 32]), LegacyRuntimeError>,
) -> Result<(), LegacyRuntimeError> {
    let parent = path
        .parent()
        .filter(|parent| !parent.as_os_str().is_empty())
        .unwrap_or_else(|| Path::new("."));
    fs::create_dir_all(parent)?;
    match fs::symlink_metadata(path) {
        Ok(_) => {
            return Err(LegacyRuntimeError::InvalidConfig(
                "class-pickle result target already exists".into(),
            ));
        }
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
        Err(error) => return Err(error.into()),
    }

    let mut created = None;
    for _ in 0..16 {
        let mut nonce = [0_u8; 16];
        getrandom::getrandom(&mut nonce).map_err(|error| {
            LegacyRuntimeError::InvalidConfig(format!(
                "class-pickle temporary nonce generation failed: {error}"
            ))
        })?;
        let nonce = nonce
            .iter()
            .map(|byte| format!("{byte:02x}"))
            .collect::<String>();
        let candidate = parent.join(format!(
            ".sipi-pb01-result-{}-{nonce}.tmp",
            std::process::id()
        ));
        match fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&candidate)
        {
            Ok(file) => {
                created = Some((TemporaryResult { path: candidate }, file));
                break;
            }
            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => continue,
            Err(error) => return Err(error.into()),
        }
    }
    let (temporary, file) = created.ok_or_else(|| {
        LegacyRuntimeError::Io(std::io::Error::new(
            std::io::ErrorKind::AlreadyExists,
            "could not create a fresh class-pickle temporary file",
        ))
    })?;
    let (mut file, expected_length, expected_sha256) = encode(file)?;
    file.flush()?;
    file.sync_all()?;
    drop(file);

    let mut readback = File::open(&temporary.path)?;
    let mut buffer = vec![0_u8; LEGACY_READBACK_BUFFER_BYTES];
    let mut digest = Sha256::new();
    let mut actual_length = 0_usize;
    loop {
        let count = readback.read(&mut buffer)?;
        if count == 0 {
            break;
        }
        actual_length = actual_length.checked_add(count).ok_or_else(|| {
            LegacyRuntimeError::ResourceLimit("class-pickle readback length overflow".into())
        })?;
        if actual_length > MAX_LEGACY_RESULT_BYTES {
            return Err(LegacyRuntimeError::ResourceLimit(
                "class-compatible .pybert_data exceeds 512 MiB".into(),
            ));
        }
        digest.update(&buffer[..count]);
    }
    let actual_sha256: [u8; 32] = digest.finalize().into();
    if actual_length != expected_length || actual_sha256 != expected_sha256 {
        return Err(LegacyRuntimeError::InvalidConfig(
            "class-pickle readback identity mismatch".into(),
        ));
    }
    fs::hard_link(&temporary.path, path).map_err(|error| {
        LegacyRuntimeError::Io(std::io::Error::new(
            error.kind(),
            format!("class-pickle no-clobber publication failed: {error}"),
        ))
    })?;
    fs::remove_file(&temporary.path).map_err(|error| {
        LegacyRuntimeError::PublishIndeterminate(format!(
            "class-pickle was published but temporary cleanup failed: {error}"
        ))
    })?;
    std::mem::forget(temporary);
    Ok(())
}

struct LegacyArrayProjection<'a> {
    channel: &'a [f64],
    tx_out_h: &'a [f64],
    tx_h: &'a [f64],
    ctle_h: Cow<'a, [f64]>,
    ctle_out_h: Vec<f64>,
    dfe_h: Vec<f64>,
    dfe_out_h: Vec<f64>,
    tx_out: &'a [f64],
    samples_per_ui: usize,
}

impl<'a> LegacyArrayProjection<'a> {
    fn new(output: &'a SimulationOutputV1) -> Result<Self, LegacyRuntimeError> {
        let source = &output.arrays;
        let required = |name: &str| {
            source
                .get(name)
                .filter(|values| !values.is_empty())
                .map(Vec::as_slice)
                .ok_or_else(|| {
                    LegacyRuntimeError::InvalidConfig(format!(
                        "legacy result source array {name} is empty or missing"
                    ))
                })
        };
        let channel = required("channel_impulse_v_per_v")?;
        let tx_out_h = required("tx_channel_impulse_v_per_v")?;
        let tx_h = source
            .get("tx_impulse_v_per_v")
            .filter(|values| !values.is_empty())
            .or_else(|| {
                source
                    .get("legacy_stage_tx_re")
                    .filter(|values| !values.is_empty())
            })
            .map(Vec::as_slice)
            .ok_or_else(|| {
                LegacyRuntimeError::InvalidConfig(
                    "legacy result TX impulse source is empty or missing".into(),
                )
            })?;
        let ctle_h = source
            .get("rx_filter_impulse_v_per_v")
            .filter(|values| !values.is_empty())
            .map_or_else(
                || Cow::Owned(vec![1.0]),
                |values| Cow::Borrowed(values.as_slice()),
            );
        let ctle_out_h = causal_convolve(tx_out_h, ctle_h.as_ref(), tx_out_h.len())?;
        let ffe_out_h = match source
            .get("rx_ffe_impulse_v_per_v")
            .filter(|values| !values.is_empty())
        {
            Some(rx_ffe) => causal_convolve(&ctle_out_h, rx_ffe, tx_out_h.len())?,
            None => ctle_out_h.clone(),
        };
        let samples_per_ui = inferred_samples_per_ui(source);
        let final_taps = source
            .get("dfe_tap_weights_v")
            .map_or(&[][..], Vec::as_slice);
        let dfe_h = dfe_impulse_from_history(final_taps, samples_per_ui);
        let dfe_out_h = causal_convolve(&ffe_out_h, &dfe_h, tx_out_h.len())?;
        let tx_out = required("tx_waveform_v")?;
        Ok(Self {
            channel,
            tx_out_h,
            tx_h,
            ctle_h,
            ctle_out_h,
            dfe_h,
            dfe_out_h,
            tx_out,
            samples_per_ui,
        })
    }

    fn visit(
        &self,
        spectrum: fn(&[f64]) -> Result<Vec<f64>, LegacyRuntimeError>,
        mut emit: impl FnMut(&str, &[f64]) -> Result<(), LegacyRuntimeError>,
    ) -> Result<(), LegacyRuntimeError> {
        emit("chnl_h", self.channel)?;
        emit("tx_out_h", self.tx_out_h)?;
        emit("ctle_out_h", &self.ctle_out_h)?;
        emit("dfe_out_h", &self.dfe_out_h)?;
        for (name, source) in [
            ("chnl_s", self.channel),
            ("tx_s", self.tx_h),
            ("ctle_s", self.ctle_h.as_ref()),
            ("dfe_s", self.dfe_h.as_slice()),
            ("tx_out_s", self.tx_out_h),
            ("ctle_out_s", self.ctle_out_h.as_slice()),
            ("dfe_out_s", self.dfe_out_h.as_slice()),
        ] {
            let values = step_from(source);
            emit(name, &values)?;
        }
        for (name, source) in [
            ("chnl_p", self.channel),
            ("tx_out_p", self.tx_out_h),
            ("ctle_out_p", self.ctle_out_h.as_slice()),
            ("dfe_out_p", self.dfe_out_h.as_slice()),
        ] {
            let values = pulse_from(source, self.samples_per_ui);
            emit(name, &values)?;
        }
        for (name, source) in [
            ("chnl_H", self.channel),
            ("tx_H", self.tx_h),
            ("ctle_H", self.ctle_h.as_ref()),
            ("dfe_H", self.dfe_h.as_slice()),
            ("tx_out_H", self.tx_out_h),
            ("ctle_out_H", self.ctle_out_h.as_slice()),
            ("dfe_out_H", self.dfe_out_h.as_slice()),
        ] {
            let values = spectrum(source)?;
            emit(name, &values)?;
        }
        emit("tx_out", self.tx_out)
    }
}

fn legacy_arrays(
    output: &SimulationOutputV1,
) -> Result<BTreeMap<String, Vec<f64>>, LegacyRuntimeError> {
    let projection = LegacyArrayProjection::new(output)?;
    let mut arrays = BTreeMap::new();
    projection.visit(response_spectrum_interleaved, |name, values| {
        arrays.insert(name.into(), values.to_vec());
        Ok(())
    })?;
    Ok(arrays)
}

/// Add the result-adapter fields that the pinned `sim-rust` Web path publishes
/// from the already materialized native output.
///
/// This is deliberately a serializer projection, not another simulation
/// stage: aliases copy typed arrays, response fields take magnitudes of the
/// typed complex telemetry, and the bathtub fields apply the pinned adapter's
/// log presentation.  The legacy frequency/stage telemetry is optional for an
/// impulse-response channel; in that case the upstream adapter publishes its
/// channel FFT fields and empty stage-response fields.
pub(crate) fn augment_sim_rust_result_arrays_v1(
    input: &SimulationInputV1,
    output: &mut SimulationOutputV1,
) -> Result<(), LegacyRuntimeError> {
    let source = &output.arrays;
    let channel = source.get("channel_impulse_v_per_v").ok_or_else(|| {
        LegacyRuntimeError::InvalidConfig(
            "PB-03 sim-rust payload projection requires channel_impulse_v_per_v".into(),
        )
    })?;
    if channel.is_empty() {
        return Err(LegacyRuntimeError::InvalidConfig(
            "PB-03 sim-rust payload projection requires a non-empty channel impulse".into(),
        ));
    }
    let sample_interval = input.timebase.sample_interval.0;
    let samples_per_ui = usize::try_from(input.timebase.samples_per_ui).map_err(|_| {
        LegacyRuntimeError::InvalidConfig(
            "PB-03 sim-rust payload projection samples_per_ui overflows usize".into(),
        )
    })?;
    if !sample_interval.is_finite() || sample_interval <= 0.0 || samples_per_ui == 0 {
        return Err(LegacyRuntimeError::InvalidConfig(
            "PB-03 sim-rust payload projection has an invalid timebase".into(),
        ));
    }

    let legacy_frequency = match &input.channel {
        ChannelInputV1::MetallicLine(channel_input) => {
            Some(validate_pb03_legacy_frequency_v1(source, channel_input)?)
        }
        ChannelInputV1::ImpulseResponse(_) | ChannelInputV1::ExternalModel(_) => None,
    };
    validate_pb03_projection_budget_v1(input, source, channel.len(), legacy_frequency)?;

    let mut projected = BTreeMap::new();
    let channel_step = step_response(channel).map_err(|error| {
        LegacyRuntimeError::InvalidConfig(format!(
            "PB-03 sim-rust channel step projection failed: {error}"
        ))
    })?;
    let channel_pulse = pulse_response(&channel_step, samples_per_ui).map_err(|error| {
        LegacyRuntimeError::InvalidConfig(format!(
            "PB-03 sim-rust channel pulse projection failed: {error}"
        ))
    })?;
    let peak_index = first_abs_argmax(channel).ok_or_else(|| {
        LegacyRuntimeError::InvalidConfig(
            "PB-03 sim-rust payload projection could not locate channel peak".into(),
        )
    })?;
    let channel_time_ns = (0..channel.len())
        .map(|index| (index as f64 - peak_index as f64) * sample_interval * 1.0e9)
        .collect::<Vec<_>>();
    add_projected_array(source, &mut projected, "t_ns_chnl", channel_time_ns)?;
    add_projected_array(source, &mut projected, "chnl_h", channel.clone())?;
    add_projected_array(source, &mut projected, "chnl_s", channel_step)?;
    add_projected_array(source, &mut projected, "chnl_p", channel_pulse)?;

    if let Some(frequency_len) = legacy_frequency {
        let frequency = &source["legacy_channel_frequency_hz"];
        debug_assert_eq!(frequency.len(), frequency_len);
        add_projected_array(
            source,
            &mut projected,
            "f_GHz",
            frequency.iter().map(|value| *value / 1.0e9).collect(),
        )?;
        for (alias, stage) in [
            (
                "chnl_H_raw",
                ("legacy_channel_raw_re", "legacy_channel_raw_im"),
            ),
            (
                "chnl_H",
                (
                    "legacy_channel_terminated_re",
                    "legacy_channel_terminated_im",
                ),
            ),
            (
                "chnl_trimmed_H",
                ("legacy_channel_trimmed_re", "legacy_channel_trimmed_im"),
            ),
        ] {
            add_projected_array(
                source,
                &mut projected,
                alias,
                source[stage.0]
                    .iter()
                    .zip(&source[stage.1])
                    .map(|(real, imag)| real.hypot(*imag))
                    .collect(),
            )?;
        }

        for (alias, stage) in [
            ("tx_H", "tx"),
            ("tx_out_H", "tx_out"),
            ("ctle_H", "ctle"),
            ("ctle_out_H", "ctle_out"),
            ("dfe_H", "dfe"),
            ("dfe_out_H", "dfe_out"),
        ] {
            let real_name = format!("legacy_stage_{stage}_re");
            let imag_name = format!("legacy_stage_{stage}_im");
            let (Some(real), Some(imag)) = (source.get(&real_name), source.get(&imag_name)) else {
                return Err(LegacyRuntimeError::InvalidConfig(format!(
                    "PB-03 sim-rust payload projection is missing {real_name}/{imag_name}"
                )));
            };
            if real.len() != frequency.len() || imag.len() != frequency.len() {
                return Err(LegacyRuntimeError::InvalidConfig(format!(
                    "PB-03 sim-rust payload projection length mismatch for {stage} response"
                )));
            }
            add_projected_array(
                source,
                &mut projected,
                alias,
                real.iter()
                    .zip(imag)
                    .map(|(real, imag)| real.hypot(*imag))
                    .collect(),
            )?;
        }
        let rx_out_h = projected.get("dfe_out_H").cloned().ok_or_else(|| {
            LegacyRuntimeError::InvalidConfig(
                "PB-03 sim-rust payload projection did not produce dfe_out_H".into(),
            )
        })?;
        add_projected_array(source, &mut projected, "rx_out_H", rx_out_h)?;
    } else {
        // The pinned adapter uses an rFFT fallback when legacy RLGC frequency
        // telemetry is unavailable.  Reuse the crate's existing real-spectrum
        // helper rather than introducing a second transform implementation.
        let (real, imag) = forward_real_spectrum(channel).map_err(|error| {
            LegacyRuntimeError::InvalidConfig(format!(
                "PB-03 sim-rust fallback channel spectrum failed: {error}"
            ))
        })?;
        let frequency_step_hz = 1.0 / (channel.len() as f64 * sample_interval);
        add_projected_array(
            source,
            &mut projected,
            "f_GHz",
            (0..real.len())
                .map(|index| index as f64 * frequency_step_hz / 1.0e9)
                .collect(),
        )?;
        let transfer = real
            .iter()
            .zip(&imag)
            .map(|(real, imag)| real.hypot(*imag))
            .collect::<Vec<_>>();
        for name in ["chnl_H_raw", "chnl_H", "chnl_trimmed_H"] {
            add_projected_array(source, &mut projected, name, transfer.clone())?;
        }
        for name in [
            "tx_H",
            "tx_out_H",
            "ctle_H",
            "ctle_out_H",
            "dfe_H",
            "dfe_out_H",
            "rx_out_H",
        ] {
            add_projected_array(source, &mut projected, name, Vec::new())?;
        }
    }

    for (alias, source_name) in [
        ("parity_channel_impulse_v_per_v", "channel_impulse_v_per_v"),
        ("parity_ctle_output_v", "ctle_output_v"),
        ("parity_rx_output_v", "rx_output_v"),
        ("parity_dfe_output_v", "dfe_output_v"),
        ("parity_dfe_decisions", "dfe_decisions"),
        ("parity_dfe_clock_times_s", "dfe_clock_times_s"),
    ] {
        if let Some(values) = source.get(source_name) {
            add_projected_array(source, &mut projected, alias, values.clone())?;
        }
    }
    add_projected_array(
        source,
        &mut projected,
        "jitter_bins",
        source
            .get("jitter_bin_centers_s")
            .cloned()
            .unwrap_or_default(),
    )?;
    for (alias, source_name) in [
        ("bathtub_chnl", "bathtub_chnl_ber"),
        ("bathtub_tx", "bathtub_tx_ber"),
        ("bathtub_ctle", "bathtub_ctle_ber"),
        ("bathtub_dfe", "bathtub_dfe_ber"),
    ] {
        let values = source.get(source_name);
        add_projected_array(
            source,
            &mut projected,
            alias,
            values
                .into_iter()
                .flatten()
                .map(|value| value.max(1.0e-13).log10())
                .collect(),
        )?;
    }
    let bathtub_rx = projected["bathtub_dfe"].clone();
    add_projected_array(source, &mut projected, "bathtub_rx", bathtub_rx)?;
    output.arrays.extend(projected);
    Ok(())
}

fn first_abs_argmax(values: &[f64]) -> Option<usize> {
    let mut peak_index = 0;
    let mut peak_magnitude = values.first()?.abs();
    for (index, value) in values.iter().enumerate().skip(1) {
        let magnitude = value.abs();
        if magnitude > peak_magnitude {
            peak_index = index;
            peak_magnitude = magnitude;
        }
    }
    Some(peak_index)
}

fn validate_pb03_legacy_frequency_v1(
    source: &BTreeMap<String, Vec<f64>>,
    channel: &MetallicLineChannelV1,
) -> Result<usize, LegacyRuntimeError> {
    let frequency_names = [
        "legacy_channel_frequency_hz",
        "legacy_channel_raw_re",
        "legacy_channel_raw_im",
        "legacy_channel_terminated_re",
        "legacy_channel_terminated_im",
        "legacy_channel_trimmed_re",
        "legacy_channel_trimmed_im",
    ];
    for name in frequency_names {
        if !source.contains_key(name) {
            return Err(LegacyRuntimeError::InvalidConfig(format!(
                "PB-03 native_typed_rlgc requires {name}"
            )));
        }
    }
    let step = channel.frequency_step_hz.as_ref().map(|value| value.0);
    let maximum = channel.frequency_max_hz.as_ref().map(|value| value.0);
    let (Some(step), Some(maximum)) = (step, maximum) else {
        return Err(LegacyRuntimeError::InvalidConfig(
            "PB-03 native_typed_rlgc requires an explicit legacy frequency grid".into(),
        ));
    };
    let ratio = maximum / step;
    if !step.is_finite()
        || step <= 0.0
        || !maximum.is_finite()
        || maximum < 0.0
        || !ratio.is_finite()
        || ratio.round() > (usize::MAX - 1) as f64
    {
        return Err(LegacyRuntimeError::InvalidConfig(
            "PB-03 native_typed_rlgc has an invalid expected frequency grid".into(),
        ));
    }
    let expected = (ratio.round() as usize).checked_add(1).ok_or_else(|| {
        LegacyRuntimeError::ResourceLimit("PB-03 frequency count overflow".into())
    })?;
    let frequency = &source["legacy_channel_frequency_hz"];
    if frequency.len() != expected
        || frequency.iter().any(|value| !value.is_finite())
        || frequency.first().is_none_or(|value| value.abs() > 1.0e-8)
        || frequency.windows(2).any(|pair| {
            let delta = pair[1] - pair[0];
            (delta - step).abs() > 1.0e-6 + 1.0e-12 * step.abs()
        })
    {
        return Err(LegacyRuntimeError::InvalidConfig(
            "PB-03 native_typed_rlgc emitted an invalid legacy frequency grid".into(),
        ));
    }
    for name in frequency_names.into_iter().skip(1) {
        let values = &source[name];
        if values.len() != expected || values.iter().any(|value| !value.is_finite()) {
            return Err(LegacyRuntimeError::InvalidConfig(format!(
                "PB-03 native_typed_rlgc emitted invalid {name}"
            )));
        }
    }
    for stage in ["tx", "tx_out", "ctle", "ctle_out", "dfe", "dfe_out"] {
        for component in ["re", "im"] {
            let name = format!("legacy_stage_{stage}_{component}");
            let Some(values) = source.get(&name) else {
                return Err(LegacyRuntimeError::InvalidConfig(format!(
                    "PB-03 native_typed_rlgc requires {name}"
                )));
            };
            if values.len() != expected || values.iter().any(|value| !value.is_finite()) {
                return Err(LegacyRuntimeError::InvalidConfig(format!(
                    "PB-03 native_typed_rlgc emitted invalid {name}"
                )));
            }
        }
    }
    Ok(expected)
}

fn validate_pb03_projection_budget_v1(
    input: &SimulationInputV1,
    source: &BTreeMap<String, Vec<f64>>,
    channel_len: usize,
    legacy_frequency_len: Option<usize>,
) -> Result<(), LegacyRuntimeError> {
    let add = |left: usize, right: usize| {
        left.checked_add(right).ok_or_else(|| {
            LegacyRuntimeError::ResourceLimit("PB-03 projection count overflow".into())
        })
    };
    let multiply = |left: usize, right: usize| {
        left.checked_mul(right).ok_or_else(|| {
            LegacyRuntimeError::ResourceLimit("PB-03 projection count overflow".into())
        })
    };
    let existing = source
        .values()
        .try_fold(0_usize, |total, values| add(total, values.len()))?;
    let mut retained = multiply(channel_len, 4)?;
    let fallback_bins = channel_len / 2 + 1;
    retained = add(
        retained,
        multiply(
            legacy_frequency_len.unwrap_or(fallback_bins),
            if legacy_frequency_len.is_some() {
                11
            } else {
                4
            },
        )?,
    )?;
    for name in [
        "channel_impulse_v_per_v",
        "ctle_output_v",
        "rx_output_v",
        "dfe_output_v",
        "dfe_decisions",
        "dfe_clock_times_s",
        "jitter_bin_centers_s",
        "bathtub_chnl_ber",
        "bathtub_tx_ber",
        "bathtub_ctle_ber",
        "bathtub_dfe_ber",
        "bathtub_dfe_ber",
    ] {
        retained = add(retained, source.get(name).map_or(0, Vec::len))?;
    }
    let fallback_allocation = if legacy_frequency_len.is_none() {
        add(multiply(channel_len, 2)?, multiply(fallback_bins, 3)?)?
    } else {
        0
    };
    let transient_peak = if legacy_frequency_len.is_none() {
        add(multiply(channel_len, 2)?, multiply(fallback_bins, 2)?)?
            .max(multiply(fallback_bins, 3)?)
    } else {
        0
    };
    let allocated = add(retained, fallback_allocation)?;
    let peak = add(add(existing, retained)?, transient_peak)?;
    let allocated_bytes = multiply(allocated, std::mem::size_of::<f64>())?;
    let peak_bytes = multiply(peak, std::mem::size_of::<f64>())?;
    let limit = usize::try_from(input.limits.max_memory_bytes).unwrap_or(usize::MAX);
    if allocated_bytes > limit || peak_bytes > limit {
        return Err(LegacyRuntimeError::ResourceLimit(format!(
            "PB-03 projection requires {allocated} allocated f64 values ({allocated_bytes} bytes) and a {peak}-value peak ({peak_bytes} bytes), limit is {} bytes",
            input.limits.max_memory_bytes
        )));
    }
    Ok(())
}

fn add_projected_array(
    source: &BTreeMap<String, Vec<f64>>,
    projected: &mut BTreeMap<String, Vec<f64>>,
    name: &str,
    values: Vec<f64>,
) -> Result<(), LegacyRuntimeError> {
    if let Some(existing) = source.get(name)
        && existing != &values
    {
        return Err(LegacyRuntimeError::InvalidConfig(format!(
            "PB-03 sim-rust payload projection would overwrite {name}"
        )));
    }
    if let Some(existing) = projected.get(name)
        && existing != &values
    {
        return Err(LegacyRuntimeError::InvalidConfig(format!(
            "PB-03 sim-rust payload projection produced conflicting {name}"
        )));
    }
    projected.entry(name.into()).or_insert(values);
    Ok(())
}

fn response_spectrum_interleaved(values: &[f64]) -> Result<Vec<f64>, LegacyRuntimeError> {
    if values.is_empty() {
        return Ok(vec![0.0, 0.0]);
    }
    let fft_len = values.len().next_power_of_two().max(2);
    let mut padded = values.to_vec();
    padded.resize(fft_len, 0.0);
    let (real, imag) = forward_real_spectrum(&padded)
        .map_err(|error| LegacyRuntimeError::InvalidConfig(format!("response FFT: {error}")))?;
    let mut flattened = Vec::with_capacity(real.len() * 2);
    for (real, imag) in real.into_iter().zip(imag) {
        flattened.extend([real, imag]);
    }
    Ok(flattened)
}

fn dfe_impulse_from_history(history: &[f64], samples_per_ui: usize) -> Vec<f64> {
    let tap_count = if samples_per_ui == 0 {
        0
    } else {
        history.len() / samples_per_ui.max(1)
    };
    let taps = history
        .iter()
        .rev()
        .take(tap_count)
        .copied()
        .collect::<Vec<_>>();
    let mut impulse = vec![1.0];
    impulse.extend(std::iter::repeat_n(0.0, samples_per_ui.saturating_sub(1)));
    for tap in taps.into_iter().rev() {
        impulse.push(-tap);
        impulse.extend(std::iter::repeat_n(0.0, samples_per_ui.saturating_sub(1)));
    }
    impulse
}

fn response_spectrum_db(values: &[f64]) -> Result<Vec<f64>, LegacyRuntimeError> {
    if values.is_empty() {
        return Err(LegacyRuntimeError::InvalidConfig(
            "legacy response spectrum source is empty".into(),
        ));
    }
    let fft_len = values.len().next_power_of_two().max(2);
    let mut padded = values.to_vec();
    padded.resize(fft_len, 0.0);
    let (mut real, imag) = forward_real_spectrum(&padded)
        .map_err(|error| LegacyRuntimeError::InvalidConfig(format!("response FFT: {error}")))?;
    drop(padded);
    if real.len() != imag.len() || real.len() < 2 {
        return Err(LegacyRuntimeError::InvalidConfig(
            "response FFT returned an invalid real-spectrum shape".into(),
        ));
    }
    for index in 1..real.len() {
        let magnitude = real[index].hypot(imag[index]);
        real[index - 1] = 20.0 * magnitude.max(LEGACY_CLASS_SAFE_LOG10_MIN).log10();
    }
    real.truncate(real.len() - 1);
    Ok(real)
}

fn step_from(values: &[f64]) -> Vec<f64> {
    let mut total = 0.0;
    values
        .iter()
        .map(|value| {
            total += *value;
            total
        })
        .collect()
}

fn pulse_from(values: &[f64], samples_per_ui: usize) -> Vec<f64> {
    let step = step_from(values);
    step.iter()
        .enumerate()
        .map(|(index, &value)| {
            let delayed = index
                .checked_sub(samples_per_ui)
                .and_then(|delayed_index| step.get(delayed_index))
                .copied()
                .unwrap_or(0.0);
            value - delayed
        })
        .collect()
}

fn inferred_samples_per_ui(source: &BTreeMap<String, Vec<f64>>) -> usize {
    let samples = source.get("tx_waveform_v").map_or(0, Vec::len);
    let symbols = source.get("symbols_v").map_or(0, Vec::len);
    if symbols > 0 {
        samples
            .checked_div(symbols)
            .filter(|value| *value > 0)
            .unwrap_or(1)
    } else {
        1
    }
}

fn causal_convolve(
    left: &[f64],
    right: &[f64],
    output_length: usize,
) -> Result<Vec<f64>, LegacyRuntimeError> {
    let full_length = left
        .len()
        .checked_add(right.len().saturating_sub(1))
        .ok_or_else(|| LegacyRuntimeError::ResourceLimit("convolution length overflow".into()))?;
    let mut output = vec![0.0; output_length.min(full_length)];
    for (left_index, &left_value) in left.iter().enumerate() {
        for (right_index, &right_value) in right.iter().enumerate() {
            let index = left_index + right_index;
            if index >= output.len() {
                break;
            }
            output[index] += left_value * right_value;
        }
    }
    Ok(output)
}

fn tx_weights(taps: &[(bool, f64, f64, f64)]) -> Result<Vec<f64>, LegacyRuntimeError> {
    if taps.len() != 6 {
        return Err(LegacyRuntimeError::Unsupported(
            "tx_taps must contain the pinned six-tap legacy shape".into(),
        ));
    }
    let mut values = taps
        .iter()
        .map(|(enabled, value, _, _)| if *enabled { *value } else { 0.0 })
        .collect::<Vec<_>>();
    let cursor = 1.0 - values.iter().map(|value| value.abs()).sum::<f64>();
    values.insert(3, cursor);
    if values.iter().any(|value| !value.is_finite()) {
        return Err(LegacyRuntimeError::InvalidConfig("tx_taps".into()));
    }
    Ok(values)
}

fn rx_weights(n_taps: usize, n_pre: usize) -> Result<Vec<f64>, LegacyRuntimeError> {
    if n_taps > MAX_RX_TAPS || (n_taps > 0 && n_pre >= n_taps) {
        return Err(LegacyRuntimeError::InvalidConfig("rx_taps shape".into()));
    }
    if n_taps == 0 {
        return Ok(vec![1.0]);
    }
    let mut values = vec![0.0; n_taps];
    values[n_pre] = 1.0;
    Ok(values)
}

fn read_bounded_config(path: &Path) -> Result<Vec<u8>, LegacyRuntimeError> {
    let file = File::open(path)?;
    let byte_count = file.metadata()?.len();
    if byte_count > MAX_CONFIG_BYTES {
        return Err(LegacyRuntimeError::ResourceLimit(
            "configuration exceeds 1 MiB".into(),
        ));
    }
    let capacity = usize::try_from(byte_count)
        .map_err(|_| LegacyRuntimeError::ResourceLimit("configuration length overflow".into()))?;
    let mut bytes = Vec::with_capacity(capacity);
    file.take(MAX_CONFIG_BYTES + 1).read_to_end(&mut bytes)?;
    if bytes.len() as u64 > MAX_CONFIG_BYTES {
        return Err(LegacyRuntimeError::ResourceLimit(
            "configuration exceeds 1 MiB".into(),
        ));
    }
    Ok(bytes)
}

fn validate_sequence_budget(
    mapping: &serde_yaml::Mapping,
    key: &str,
    max_items: usize,
) -> Result<(), LegacyRuntimeError> {
    let Some(sequence) = mapping
        .get(Value::String(key.into()))
        .and_then(Value::as_sequence)
    else {
        return Ok(());
    };
    if sequence.len() > max_items {
        return Err(LegacyRuntimeError::ResourceLimit(format!(
            "{key} exceeds {max_items} entries"
        )));
    }
    Ok(())
}

fn validate_projection_budgets(
    config: &LegacyConfigProjectionV1,
) -> Result<(), LegacyRuntimeError> {
    if config.rx_n_taps > MAX_RX_TAPS {
        return Err(LegacyRuntimeError::ResourceLimit(format!(
            "rx_n_taps exceeds {MAX_RX_TAPS}"
        )));
    }
    if config.dfe_tap_tuners.len() > MAX_DFE_TAPS {
        return Err(LegacyRuntimeError::ResourceLimit(format!(
            "dfe_tap_tuners exceeds {MAX_DFE_TAPS} entries"
        )));
    }
    let symbol_count =
        if config.mod_type == "PAM-4" && !(config.viterbi_enabled && config.viterbi_fec) {
            config.nbits / 2
        } else {
            config.nbits
        };
    let sample_count = symbol_count
        .checked_mul(u64::from(config.nspui))
        .ok_or_else(|| LegacyRuntimeError::ResourceLimit("nbits*nspui overflow".into()))?;
    if sample_count > MAX_TOTAL_SAMPLES {
        return Err(LegacyRuntimeError::ResourceLimit(format!(
            "sample count exceeds {MAX_TOTAL_SAMPLES}"
        )));
    }
    let rx_impulse_samples = u64::try_from(config.rx_n_taps)
        .ok()
        .and_then(|taps| taps.checked_mul(u64::from(config.nspui)))
        .ok_or_else(|| LegacyRuntimeError::ResourceLimit("RX FFE sample count overflow".into()))?;
    if rx_impulse_samples > MAX_TOTAL_SAMPLES {
        return Err(LegacyRuntimeError::ResourceLimit(
            "RX FFE sample count exceeds budget".into(),
        ));
    }
    let dfe_tap_count = u64::try_from(config.dfe_tap_tuners.len())
        .map_err(|_| LegacyRuntimeError::ResourceLimit("DFE tap count overflow".into()))?;
    let vector_count = LEGACY_RESULT_VECTOR_UPPER_BOUND
        .checked_add(dfe_tap_count)
        .ok_or_else(|| LegacyRuntimeError::ResourceLimit("output vector count overflow".into()))?;
    let output_bytes = sample_count
        .checked_mul(vector_count)
        .and_then(|values| values.checked_mul(std::mem::size_of::<f64>() as u64))
        .and_then(|bytes| bytes.checked_mul(2))
        .ok_or_else(|| LegacyRuntimeError::ResourceLimit("output byte count overflow".into()))?;
    if output_bytes > MAX_LEGACY_RESULT_BYTES as u64 {
        return Err(LegacyRuntimeError::ResourceLimit(
            "projected .pybert_data exceeds 512 MiB".into(),
        ));
    }
    Ok(())
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct LegacyArrayLayout {
    total_values: usize,
    construction_peak_values: usize,
    retained_projection_values: usize,
    transient_vector_peak_values: usize,
    spectrum_work_peak_values: usize,
}

impl LegacyArrayLayout {
    fn from_output(output: &SimulationOutputV1) -> Result<Self, LegacyRuntimeError> {
        let source = &output.arrays;
        let length = |name: &str| source.get(name).map_or(0, Vec::len);
        let required = |name: &str| {
            let value = length(name);
            if value == 0 {
                Err(LegacyRuntimeError::InvalidConfig(format!(
                    "legacy result source array {name} is empty or missing"
                )))
            } else {
                Ok(value)
            }
        };
        let channel = required("channel_impulse_v_per_v")?;
        let response = required("tx_channel_impulse_v_per_v")?;
        let tx = match length("tx_impulse_v_per_v") {
            0 => required("legacy_stage_tx_re")?,
            value => value,
        };
        let ctle_source = length("rx_filter_impulse_v_per_v");
        let ctle = ctle_source.max(1);
        let owned_ctle_identity = usize::from(ctle_source == 0);
        let tx_out = required("tx_waveform_v")?;
        let samples_per_ui = inferred_samples_per_ui(source);
        let dfe = length("dfe_tap_weights_v")
            .checked_div(samples_per_ui)
            .and_then(|taps| taps.checked_add(1))
            .and_then(|taps| taps.checked_mul(samples_per_ui))
            .ok_or_else(|| {
                LegacyRuntimeError::ResourceLimit("DFE result length overflow".into())
            })?;
        let spectrum = |value: usize| {
            value
                .checked_next_power_of_two()
                .map(|fft_length| fft_length.max(2) / 2)
                .ok_or_else(|| {
                    LegacyRuntimeError::ResourceLimit("response spectrum length overflow".into())
                })
        };
        let channel_spectrum = spectrum(channel)?;
        let tx_spectrum = spectrum(tx)?;
        let ctle_spectrum = spectrum(ctle)?;
        let dfe_spectrum = spectrum(dfe)?;
        let response_spectrum = spectrum(response)?;
        let lengths = [
            channel,
            response,
            response,
            response,
            channel,
            tx,
            ctle,
            dfe,
            response,
            response,
            response,
            channel,
            response,
            response,
            response,
            channel_spectrum,
            tx_spectrum,
            ctle_spectrum,
            dfe_spectrum,
            response_spectrum,
            response_spectrum,
            response_spectrum,
            tx_out,
        ];
        let total_values = lengths.into_iter().try_fold(0_usize, |total, value| {
            total.checked_add(value).ok_or_else(|| {
                LegacyRuntimeError::ResourceLimit("legacy array value count overflow".into())
            })
        })?;
        let retained_projection_values = response
            .checked_mul(2)
            .and_then(|value| value.checked_add(dfe))
            .and_then(|value| value.checked_add(owned_ctle_identity))
            .ok_or_else(|| {
                LegacyRuntimeError::ResourceLimit("legacy projection peak overflow".into())
            })?;
        let construction_peak_values = response
            .checked_mul(3)
            .and_then(|value| value.checked_add(dfe))
            .and_then(|value| value.checked_add(owned_ctle_identity))
            .ok_or_else(|| {
                LegacyRuntimeError::ResourceLimit("legacy projection peak overflow".into())
            })?;
        let transient_vector = [channel, tx, ctle, dfe, response]
            .into_iter()
            .max()
            .unwrap_or(0);
        let spectrum_scratch = [channel, tx, ctle, dfe, response]
            .into_iter()
            .map(|value| {
                let fft = value.checked_next_power_of_two()?.max(2);
                fft.checked_add((fft / 2 + 1).checked_mul(2)?)
            })
            .collect::<Option<Vec<_>>>()
            .and_then(|values| values.into_iter().max())
            .ok_or_else(|| {
                LegacyRuntimeError::ResourceLimit("response FFT scratch overflow".into())
            })?;
        Ok(Self {
            total_values,
            construction_peak_values,
            retained_projection_values,
            transient_vector_peak_values: transient_vector,
            spectrum_work_peak_values: spectrum_scratch,
        })
    }

    fn validate_class_codec_peak(self) -> Result<(), LegacyRuntimeError> {
        let array_bytes = self
            .total_values
            .checked_mul(std::mem::size_of::<f64>())
            .ok_or_else(|| {
                LegacyRuntimeError::ResourceLimit("legacy array byte count overflow".into())
            })?;
        let spectrum_peak = self
            .retained_projection_values
            .checked_add(self.spectrum_work_peak_values)
            .and_then(|values| values.checked_mul(std::mem::size_of::<f64>()))
            .ok_or_else(|| LegacyRuntimeError::ResourceLimit("class codec peak overflow".into()))?;
        let serialization_peak = self
            .retained_projection_values
            .checked_add(self.transient_vector_peak_values)
            .and_then(|values| values.checked_mul(std::mem::size_of::<f64>()))
            .and_then(|bytes| {
                bytes.checked_add(LEGACY_F64_WRITE_CHUNK_VALUES * std::mem::size_of::<f64>())
            })
            .ok_or_else(|| LegacyRuntimeError::ResourceLimit("class codec peak overflow".into()))?;
        let construction_peak = self
            .construction_peak_values
            .checked_mul(std::mem::size_of::<f64>())
            .ok_or_else(|| {
                LegacyRuntimeError::ResourceLimit("class codec peak byte count overflow".into())
            })?;
        let codec_peak = construction_peak
            .max(spectrum_peak)
            .max(serialization_peak)
            .max(LEGACY_READBACK_BUFFER_BYTES);
        if array_bytes > MAX_LEGACY_RESULT_BYTES || codec_peak > MAX_LEGACY_RESULT_BYTES {
            return Err(LegacyRuntimeError::ResourceLimit(
                "class-compatible .pybert_data exceeds 512 MiB logical payload or codec peak"
                    .into(),
            ));
        }
        Ok(())
    }
}

fn validate_legacy_result_budget(output: &SimulationOutputV1) -> Result<(), LegacyRuntimeError> {
    let length = |name: &str| output.arrays.get(name).map_or(0, Vec::len);
    validate_legacy_result_lengths(
        length("channel_impulse_v_per_v"),
        length("tx_channel_impulse_v_per_v"),
        length("tx_waveform_v"),
    )
}

fn validate_legacy_result_lengths(
    channel_length: usize,
    response_length: usize,
    tx_length: usize,
) -> Result<(), LegacyRuntimeError> {
    let channel_values = channel_length.checked_mul(3).ok_or_else(|| {
        LegacyRuntimeError::ResourceLimit("channel result length overflow".into())
    })?;
    let response_values = response_length.checked_mul(12).ok_or_else(|| {
        LegacyRuntimeError::ResourceLimit("response result length overflow".into())
    })?;
    let serialized_upper_bound = channel_values
        .checked_add(response_values)
        .and_then(|value| value.checked_add(tx_length))
        .and_then(|value| value.checked_mul(std::mem::size_of::<f64>()))
        .and_then(|bytes| bytes.checked_mul(2))
        .ok_or_else(|| LegacyRuntimeError::ResourceLimit("result byte count overflow".into()))?;
    if serialized_upper_bound > MAX_LEGACY_RESULT_BYTES {
        return Err(LegacyRuntimeError::ResourceLimit(
            "projected .pybert_data exceeds 512 MiB".into(),
        ));
    }
    Ok(())
}

fn validate_yaml_tag_policy(bytes: &[u8]) -> Result<(), LegacyRuntimeError> {
    let source = std::str::from_utf8(bytes)
        .map_err(|_| LegacyRuntimeError::InvalidConfig("YAML must be UTF-8".into()))?;
    let mut policy = YamlTagPolicy::default();
    Parser::new_from_str(source)
        .load(&mut policy, true)
        .map_err(|error| LegacyRuntimeError::InvalidConfig(format!("YAML scan: {error}")))?;
    if let Some(error) = policy.error {
        return Err(LegacyRuntimeError::Unsupported(error));
    }
    if policy.document_count != 1 || policy.expecting_root {
        return Err(LegacyRuntimeError::Unsupported(
            "YAML must contain exactly one tagged PyBertCfg document".into(),
        ));
    }
    Ok(())
}

#[derive(Default)]
struct YamlTagPolicy {
    document_count: usize,
    expecting_root: bool,
    error: Option<String>,
}

impl YamlTagPolicy {
    fn node(&mut self, kind: &str, tag: Option<Tag>) {
        if self.error.is_some() {
            return;
        }
        if self.expecting_root {
            self.expecting_root = false;
            if kind != "mapping" || !tag.as_ref().is_some_and(is_pybert_config_tag) {
                let actual = tag
                    .as_ref()
                    .map(|tag| format!("{tag:?}"))
                    .unwrap_or_else(|| "untagged".into());
                self.error = Some(format!(
                    "root YAML tag must be !!{PYBERT_CONFIG_TAG} on a mapping (got {actual})"
                ));
            }
            return;
        }
        if let Some(tag) = tag.filter(|tag| !is_python_tuple_tag(tag)) {
            self.error = Some(format!(
                "YAML tag {}{} is not allowed",
                tag.handle, tag.suffix
            ));
        }
    }
}

impl EventReceiver for YamlTagPolicy {
    fn on_event(&mut self, event: Event) {
        match event {
            Event::DocumentStart => {
                self.document_count += 1;
                if self.document_count == 1 {
                    self.expecting_root = true;
                } else if self.error.is_none() {
                    self.error = Some("multiple YAML documents are not allowed".into());
                }
            }
            Event::MappingStart(_, tag) => self.node("mapping", tag),
            Event::SequenceStart(_, tag) => self.node("sequence", tag),
            Event::Scalar(_, _, _, tag) => self.node("scalar", tag),
            Event::Alias(_) => self.node("alias", None),
            _ => {}
        }
    }
}

fn is_pybert_config_tag(tag: &Tag) -> bool {
    tag.handle == YAML_2002_TAG_HANDLE && tag.suffix == PYBERT_CONFIG_TAG
}

fn is_python_tuple_tag(tag: &Tag) -> bool {
    tag.handle == YAML_2002_TAG_HANDLE && tag.suffix == PYTHON_TUPLE_TAG
}

fn strip_validated_yaml_tags(value: Value, depth: usize) -> Result<Value, LegacyRuntimeError> {
    if depth > MAX_YAML_DEPTH {
        return Err(LegacyRuntimeError::ResourceLimit(
            "YAML nesting exceeds 64 levels".into(),
        ));
    }
    match value {
        Value::Tagged(tagged)
            if tagged.tag == PYTHON_TUPLE_TAG || tagged.tag == PYBERT_CONFIG_TAG =>
        {
            strip_validated_yaml_tags(tagged.value, depth + 1)
        }
        Value::Tagged(tagged) => Err(LegacyRuntimeError::Unsupported(format!(
            "YAML tag {} is not allowed",
            tagged.tag
        ))),
        Value::Sequence(values) => Ok(Value::Sequence(
            values
                .into_iter()
                .map(|value| strip_validated_yaml_tags(value, depth + 1))
                .collect::<Result<_, _>>()?,
        )),
        Value::Mapping(mapping) => Ok(Value::Mapping(
            mapping
                .into_iter()
                .map(|(key, value)| {
                    Ok((
                        strip_validated_yaml_tags(key, depth + 1)?,
                        strip_validated_yaml_tags(value, depth + 1)?,
                    ))
                })
                .collect::<Result<_, LegacyRuntimeError>>()?,
        )),
        scalar => Ok(scalar),
    }
}

fn finite_positive(value: f64, name: &str) -> Result<f64, LegacyRuntimeError> {
    if value.is_finite() && value > 0.0 {
        Ok(value)
    } else {
        Err(LegacyRuntimeError::InvalidConfig(name.into()))
    }
}

fn canonical_modulation(value: String) -> Result<String, LegacyRuntimeError> {
    let normalized = value.trim().to_ascii_uppercase();
    match normalized.as_str() {
        "NRZ" => Ok("NRZ".into()),
        "PAM-4" | "PAM4" => Ok("PAM-4".into()),
        "DUO-BINARY" | "DUOBINARY" => Ok("DUO-BINARY".into()),
        _ => Err(LegacyRuntimeError::Unsupported(format!(
            "mod_type={value} (supported: NRZ, PAM-4, Duo-binary)"
        ))),
    }
}

fn resolve_legacy_data_path(
    config_path: &Path,
    configured_path: Option<&str>,
) -> Result<PathBuf, LegacyRuntimeError> {
    let configured_path = configured_path
        .filter(|value| !value.trim().is_empty())
        .ok_or_else(|| {
            LegacyRuntimeError::InvalidConfig("enabled file branch requires a path".into())
        })?;
    let path = PathBuf::from(configured_path);
    Ok(if path.is_absolute() {
        path
    } else {
        config_path
            .parent()
            .unwrap_or_else(|| Path::new("."))
            .join(path)
    })
}

fn legacy_noise_samples(rms_v: f64, seed: u64, count: usize) -> Vec<f64> {
    if rms_v == 0.0 {
        return vec![0.0; count];
    }
    // NumPy's ``default_rng(seed).normal`` uses PCG XSL RR 128/64 plus the
    // double ziggurat distribution.  Keep the generator local and
    // deterministic instead of borrowing process-global entropy; explicit
    // injected samples remain replayable without consuming this stream.
    let (mut state, increment) = numpy_pcg64_seed(seed);
    let mut output = Vec::with_capacity(count);
    while output.len() < count {
        output.push(rms_v * crate::numpy_normal::standard_normal(&mut state, increment));
    }
    output
}

fn numpy_pcg64_seed(seed: u64) -> (u128, u128) {
    const INIT_A: u32 = 0x43b0_d7e5;
    const MULT_A: u32 = 0x931e_8875;
    const INIT_B: u32 = 0x8b51_f9dd;
    const MULT_B: u32 = 0x58f3_8ded;
    const MIX_MULT_L: u32 = 0xca01_f9dd;
    const MIX_MULT_R: u32 = 0x4973_f715;
    let mut entropy = vec![(seed & u64::from(u32::MAX)) as u32];
    if seed > u64::from(u32::MAX) {
        entropy.push((seed >> 32) as u32);
    }
    let mut hash_const = INIT_A;
    let mut pool = [0_u32; 4];
    for (index, slot) in pool.iter_mut().enumerate() {
        let value = entropy.get(index).copied().unwrap_or(0) ^ hash_const;
        hash_const = hash_const.wrapping_mul(MULT_A);
        let value = value.wrapping_mul(hash_const);
        *slot = value ^ (value >> 16);
    }
    for source in 0..pool.len() {
        for destination in 0..pool.len() {
            if source != destination {
                let value = pool[source] ^ hash_const;
                hash_const = hash_const.wrapping_mul(MULT_A);
                let value = value.wrapping_mul(hash_const);
                let hashed = value ^ (value >> 16);
                let mixed = MIX_MULT_L
                    .wrapping_mul(pool[destination])
                    .wrapping_sub(MIX_MULT_R.wrapping_mul(hashed));
                pool[destination] = mixed ^ (mixed >> 16);
            }
        }
    }
    let mut hash_const = INIT_B;
    let mut words = [0_u32; 8];
    for (index, word) in words.iter_mut().enumerate() {
        let value = pool[index % pool.len()] ^ hash_const;
        hash_const = hash_const.wrapping_mul(MULT_B);
        let value = value.wrapping_mul(hash_const);
        *word = value ^ (value >> 16);
    }
    let state_high = u64::from(words[0]) | (u64::from(words[1]) << 32);
    let state_low = u64::from(words[2]) | (u64::from(words[3]) << 32);
    let sequence_high = u64::from(words[4]) | (u64::from(words[5]) << 32);
    let sequence_low = u64::from(words[6]) | (u64::from(words[7]) << 32);
    let init_state = (u128::from(state_high) << 64) | u128::from(state_low);
    let init_sequence = (u128::from(sequence_high) << 64) | u128::from(sequence_low);
    let increment = (init_sequence << 1) | 1;
    let multiplier = (u128::from(2_549_297_995_355_413_924_u64) << 64)
        | u128::from(4_865_540_595_714_422_341_u64);
    let state = increment
        .wrapping_add(init_state)
        .wrapping_mul(multiplier)
        .wrapping_add(increment);
    (state, increment)
}

fn nonzero_seed(requested: u64) -> u64 {
    if requested != 0 {
        return requested;
    }
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_or(1, |duration| duration.as_nanos() as u64);
    let counter = SEED_COUNTER.fetch_add(1, Ordering::Relaxed);
    let mixed = nanos ^ counter.rotate_left(17) ^ 0x9e37_79b9_7f4a_7c15;
    // PyBERT's ``randint(128)`` branch draws a non-zero 7-bit LFSR seed.
    // Keep the entropy source process-local and preserve that effective range.
    mixed % 127 + 1
}

fn finite_non_negative(value: f64, name: &str) -> Result<f64, LegacyRuntimeError> {
    if value.is_finite() && value >= 0.0 {
        Ok(value)
    } else {
        Err(LegacyRuntimeError::InvalidConfig(name.into()))
    }
}

fn finite_u32(value: f64, name: &str) -> Result<u32, LegacyRuntimeError> {
    if value.is_finite() && value > 0.0 && value.fract() == 0.0 && value <= u32::MAX as f64 {
        Ok(value as u32)
    } else {
        Err(LegacyRuntimeError::InvalidConfig(name.into()))
    }
}

fn default_tx_taps() -> Vec<(bool, f64, f64, f64)> {
    vec![
        (false, 0.0, -0.05, 0.05),
        (true, 0.0, -0.1, 0.1),
        (true, 0.0, -0.2, 0.2),
        (false, 0.0, -0.2, 0.2),
        (false, 0.0, -0.1, 0.1),
        (false, 0.0, -0.05, 0.05),
    ]
}

fn default_dfe_tap_tuners() -> Vec<(bool, f64, f64)> {
    // Keep the complete PyBERT default tuner surface.  Only the first five
    // taps are enabled; retaining the disabled tail matters for config/result
    // parity and for the contiguous-enable validation branch.
    vec![
        (true, -0.2, 0.4),
        (true, -0.15, 0.15),
        (true, -0.05, 0.1),
        (true, -0.05, 0.1),
        (true, -0.05, 0.1),
        (false, -0.05, 0.1),
        (false, -0.05, 0.1),
        (false, -0.05, 0.1),
        (false, -0.05, 0.1),
        (false, -0.05, 0.1),
        (false, -0.05, 0.1),
        (false, -0.05, 0.1),
        (false, -0.05, 0.1),
        (false, -0.05, 0.1),
        (false, -0.05, 0.1),
        (false, -0.05, 0.1),
        (false, -0.05, 0.1),
        (false, -0.05, 0.1),
        (false, -0.05, 0.1),
        (false, -0.05, 0.1),
    ]
}

fn contiguous_dfe_count(tuners: &[(bool, f64, f64)]) -> Result<usize, LegacyRuntimeError> {
    let mut count = 0;
    let mut disabled = false;
    for (enabled, min_value, max_value) in tuners {
        if !min_value.is_finite() || !max_value.is_finite() || min_value > max_value {
            return Err(LegacyRuntimeError::InvalidConfig(
                "dfe_tap_tuners limits".into(),
            ));
        }
        if *enabled {
            if disabled {
                return Err(LegacyRuntimeError::Unsupported(
                    "dfe_tap_tuners must be enabled contiguously from tap zero".into(),
                ));
            }
            count += 1;
        } else {
            disabled = true;
        }
    }
    Ok(count)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn pb03_input_output() -> (SimulationInputV1, SimulationOutputV1) {
        let fixture = Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("fixtures")
            .join("pb-03-legacy-nrz.yaml");
        let (_, input) = project_legacy_config_v1(&fixture, "pb03-unit").unwrap();
        let output = simulate_native_v1(&input).unwrap();
        (input, output)
    }

    fn tagged_config() -> String {
        r#"!!python/object:pybert.configuration.PyBertCfg
bit_rate: 10.0
nbits: 1000
pattern: PRBS-7
seed: 1
nspui: 2
mod_type: NRZ
use_ch_file: false
ctle_enable: false
rn: 0.0
pn_mag: 0.0
dfe_tap_tuners:
- !!python/tuple [false, -0.2, 0.4]
"#
        .into()
    }

    #[test]
    fn pb03_argmax_keeps_the_first_equal_absolute_peak_and_signed_zero() {
        assert_eq!(first_abs_argmax(&[0.25, -1.0, 1.0, 0.5]), Some(1));
        assert_eq!(first_abs_argmax(&[0.0, -0.0]), Some(0));
        assert_eq!(first_abs_argmax(&[]), None);
    }

    #[test]
    fn pb03_rlgc_requires_complete_finite_uniform_frequency_telemetry() {
        let (input, output) = pb03_input_output();
        let mut missing = output.clone();
        missing.arrays.remove("legacy_channel_frequency_hz");
        assert!(matches!(
            augment_sim_rust_result_arrays_v1(&input, &mut missing),
            Err(LegacyRuntimeError::InvalidConfig(message))
                if message.contains("native_typed_rlgc requires legacy_channel_frequency_hz")
        ));

        let mut non_dc = output.clone();
        non_dc
            .arrays
            .get_mut("legacy_channel_frequency_hz")
            .unwrap()[0] = 1.0;
        assert!(matches!(
            augment_sim_rust_result_arrays_v1(&input, &mut non_dc),
            Err(LegacyRuntimeError::InvalidConfig(message))
                if message.contains("invalid legacy frequency grid")
        ));

        let mut non_uniform = output;
        non_uniform
            .arrays
            .get_mut("legacy_channel_frequency_hz")
            .unwrap()[2] += 1.0;
        assert!(matches!(
            augment_sim_rust_result_arrays_v1(&input, &mut non_uniform),
            Err(LegacyRuntimeError::InvalidConfig(message))
                if message.contains("invalid legacy frequency grid")
        ));
    }

    #[test]
    fn pb03_channel_intent_controls_frequency_projection_and_empty_presentations() {
        let (mut input, mut output) = pb03_input_output();
        let channel = output.arrays["channel_impulse_v_per_v"].clone();
        input.channel = ChannelInputV1::ImpulseResponse(ChannelResponseV1 {
            sample_interval: input.timebase.sample_interval,
            impulse_response_volts_per_second: channel
                .iter()
                .map(|value| value / input.timebase.sample_interval.0)
                .collect(),
            source_impedance: Ohms(100.0),
            load_impedance: Ohms(100.0),
        });
        for name in [
            "jitter_bin_centers_s",
            "bathtub_chnl_ber",
            "bathtub_tx_ber",
            "bathtub_ctle_ber",
            "bathtub_dfe_ber",
        ] {
            output.arrays.remove(name);
        }
        augment_sim_rust_result_arrays_v1(&input, &mut output).unwrap();
        assert_eq!(output.arrays["f_GHz"].len(), channel.len() / 2 + 1);
        for name in [
            "jitter_bins",
            "bathtub_chnl",
            "bathtub_tx",
            "bathtub_ctle",
            "bathtub_dfe",
            "bathtub_rx",
        ] {
            assert!(
                output.arrays[name].is_empty(),
                "{name} must be published empty"
            );
        }
    }

    #[test]
    fn pb03_projection_budget_fails_before_publishing_any_alias() {
        let (mut input, mut output) = pb03_input_output();
        input.limits.max_memory_bytes = 1;
        assert!(matches!(
            augment_sim_rust_result_arrays_v1(&input, &mut output),
            Err(LegacyRuntimeError::ResourceLimit(message))
                if message.contains("PB-03 projection requires")
        ));
        assert!(!output.arrays.contains_key("t_ns_chnl"));
    }

    #[test]
    fn default_dictionary_retains_interleaved_frequency_arrays_and_tx_out_p() {
        let tx_impulse = vec![1.0, 0.0, 0.0, 0.0];
        let tx_channel_impulse = vec![0.0, 1.0, 0.0, 0.0];
        let output = SimulationOutputV1 {
            schema: SIMULATION_SCHEMA_V1.into(),
            run_id: "tx-out-p-regression".into(),
            capabilities: crate::EngineCapabilitiesV1 {
                stages: Vec::new(),
                external_models: Vec::new(),
            },
            metrics: BTreeMap::new(),
            events: Vec::new(),
            arrays: BTreeMap::from([
                ("channel_impulse_v_per_v".into(), vec![1.0, 0.0, 0.0, 0.0]),
                ("tx_impulse_v_per_v".into(), tx_impulse.clone()),
                (
                    "tx_channel_impulse_v_per_v".into(),
                    tx_channel_impulse.clone(),
                ),
                ("rx_filter_impulse_v_per_v".into(), vec![1.0]),
                ("rx_ffe_impulse_v_per_v".into(), vec![1.0]),
                ("tx_waveform_v".into(), vec![1.0, 0.0, 1.0, 0.0]),
                ("symbols_v".into(), vec![1.0, -1.0]),
            ]),
            artifacts: Vec::new(),
        };

        let projection = LegacyArrayProjection::new(&output).unwrap();
        let arrays = legacy_arrays(&output).unwrap();
        let mut class_arrays = BTreeMap::new();
        projection
            .visit(response_spectrum_db, |name, values| {
                class_arrays.insert(name.to_owned(), values.to_vec());
                Ok(())
            })
            .unwrap();
        assert_eq!(
            LegacyArrayLayout::from_output(&output).unwrap(),
            LegacyArrayLayout {
                total_values: 71,
                construction_peak_values: 14,
                retained_projection_values: 10,
                transient_vector_peak_values: 4,
                spectrum_work_peak_values: 10,
            }
        );

        assert_eq!(arrays["tx_out_p"], pulse_from(&tx_channel_impulse, 2));
        assert_ne!(arrays["tx_out_p"], pulse_from(&tx_impulse, 2));
        for (name, source) in [
            ("chnl_H", projection.channel),
            ("tx_H", projection.tx_h),
            ("ctle_H", projection.ctle_h.as_ref()),
            ("dfe_H", projection.dfe_h.as_slice()),
            ("tx_out_H", projection.tx_out_h),
            ("ctle_out_H", projection.ctle_out_h.as_slice()),
            ("dfe_out_H", projection.dfe_out_h.as_slice()),
        ] {
            assert_eq!(
                arrays[name],
                response_spectrum_interleaved(source).unwrap(),
                "default dictionary {name}"
            );
            assert_eq!(
                class_arrays[name],
                response_spectrum_db(source).unwrap(),
                "class codec {name}"
            );
        }
    }

    #[test]
    fn legacy_frequency_arrays_are_f64_db_values_without_dc() {
        assert_eq!(response_spectrum_db(&[1.0, 0.0]).unwrap(), vec![0.0]);
        assert_eq!(response_spectrum_db(&[1.0, 1.0]).unwrap(), vec![-400.0]);

        let source = [1.0, -0.5, 0.25, 0.0];
        let actual = response_spectrum_db(&source).unwrap();
        let (real, imag) = forward_real_spectrum(&source).unwrap();
        let expected = real
            .iter()
            .zip(&imag)
            .skip(1)
            .map(|(real, imag)| 20.0 * real.hypot(*imag).max(LEGACY_CLASS_SAFE_LOG10_MIN).log10())
            .collect::<Vec<_>>();
        assert_eq!(actual.len(), source.len() / 2);
        assert_eq!(actual, expected);
    }

    #[test]
    fn parses_python_object_and_tuple_tags() {
        let path =
            std::env::temp_dir().join(format!("pb01-yaml-parse-{}.yaml", std::process::id()));
        fs::write(&path, tagged_config()).unwrap();
        let config = parse_legacy_config_v1(&path).unwrap();
        assert_eq!(config.nbits, 1000);
        assert_eq!(config.nspui, 2);
        assert_eq!(config.dfe_tap_tuners, vec![(false, -0.2, 0.4)]);
        let _ = fs::remove_file(path);
    }

    #[test]
    fn preserves_upstream_defaults_when_legacy_fields_are_omitted() {
        let path = std::env::temp_dir().join(format!("pb01-defaults-{}.yaml", std::process::id()));
        fs::write(&path, "!!python/object:pybert.configuration.PyBertCfg {}\n").unwrap();
        let config = parse_legacy_config_v1(&path).unwrap();
        assert_eq!(config.nbits, 15_000);
        assert_eq!(config.eye_bits, 10_160);
        assert_eq!(config.pn_mag_v, 0.01);
        assert_eq!(config.pn_freq_mhz, 11.0);
        assert_eq!(config.rn_v, 0.01);
        assert_eq!(config.viterbi_symbols, 4);
        assert_eq!(config.dfe_tap_tuners.len(), 20);
        let _ = fs::remove_file(path);
    }

    #[test]
    fn maps_cursor_and_rx_ffe_without_external_python() {
        let path = std::env::temp_dir().join(format!("pb01-yaml-map-{}.yaml", std::process::id()));
        fs::write(&path, tagged_config()).unwrap();
        let config = parse_legacy_config_v1(&path).unwrap();
        let input = config.simulation_input("run".into()).unwrap();
        assert!(matches!(input.channel, ChannelInputV1::MetallicLine(_)));
        assert_eq!(input.tx.ffe.cursor_position, 3);
        assert_eq!(input.rx.ffe.cursor_position, 5);
        assert_eq!(input.rx.dfe_taps, 0);
        let _ = fs::remove_file(path);
    }

    #[test]
    fn preserves_zero_seed_randomization_and_zero_tap_identity() {
        let path = std::env::temp_dir().join(format!("pb01-zero-seed-{}.yaml", std::process::id()));
        fs::write(
            &path,
            tagged_config()
                .replace("seed: 1", "seed: 0")
                .replace("nspui: 2", "nspui: 2\nrx_n_taps: 0\nrx_n_pre: 0"),
        )
        .unwrap();
        let config = parse_legacy_config_v1(&path).unwrap();
        assert_eq!(config.requested_seed, 0);
        assert!((1..=127).contains(&config.effective_seed));
        let input = config.simulation_input("zero-seed".into()).unwrap();
        assert!(!input.rx.ffe.enabled);
        assert_eq!(input.rx.ffe.weights, vec![1.0]);
        let noisy_path =
            std::env::temp_dir().join(format!("pb01-zero-seed-noise-{}.yaml", std::process::id()));
        fs::write(
            &noisy_path,
            tagged_config()
                .replace("seed: 1", "seed: 0")
                .replace("rn: 0.0", "rn: 0.01"),
        )
        .unwrap();
        let noisy_config = parse_legacy_config_v1(&noisy_path).unwrap();
        let noisy_input = noisy_config
            .simulation_input("zero-seed-noise".into())
            .unwrap();
        assert_eq!(
            noisy_input
                .tx
                .additive_noise
                .as_ref()
                .and_then(|noise| noise.effective_seed),
            Some(noisy_config.effective_seed)
        );
        assert!(
            noisy_input
                .tx
                .additive_noise
                .as_ref()
                .is_some_and(|noise| noise.samples_v.iter().any(|sample| *sample != 0.0))
        );
        let _ = fs::remove_file(noisy_path);
        let _ = fs::remove_file(path);
    }

    #[test]
    fn keeps_explicit_random_noise_seed_separate_from_prbs_seed() {
        let path =
            std::env::temp_dir().join(format!("pb01-noise-seed-{}.yaml", std::process::id()));
        fs::write(
            &path,
            tagged_config()
                .replace("seed: 1", "seed: 17\nrandom_noise_seed: 99")
                .replace("rn: 0.0", "rn: 0.01"),
        )
        .unwrap();
        let config = parse_legacy_config_v1(&path).unwrap();
        assert_eq!(config.random_noise_seed, Some(99));
        let input = config.simulation_input("noise-seed".into()).unwrap();
        let noise = input.tx.additive_noise.as_ref().unwrap();
        assert_eq!(noise.effective_seed, Some(99));
        assert!(noise.samples_v.iter().any(|sample| *sample != 0.0));
        let replay = config.simulation_input("noise-seed-replay".into()).unwrap();
        assert_eq!(noise.samples_v, replay.tx.additive_noise.unwrap().samples_v);
        let zero_noise_seed_path =
            std::env::temp_dir().join(format!("pb01-noise-seed-zero-{}.yaml", std::process::id()));
        fs::write(
            &zero_noise_seed_path,
            tagged_config()
                .replace("seed: 1", "seed: 17\nrandom_noise_seed: 0")
                .replace("rn: 0.0", "rn: 0.01"),
        )
        .unwrap();
        let zero_noise_config = parse_legacy_config_v1(&zero_noise_seed_path).unwrap();
        let zero_noise = zero_noise_config
            .simulation_input("noise-seed-zero".into())
            .unwrap()
            .tx
            .additive_noise
            .unwrap();
        assert_eq!(zero_noise.effective_seed, Some(0));
        assert!(zero_noise.samples_v.iter().any(|sample| *sample != 0.0));
        let _ = fs::remove_file(zero_noise_seed_path);
        let _ = fs::remove_file(path);
    }

    #[test]
    fn pcg64_seed_matches_numpy_raw_stream_for_scalar_seed() {
        let (mut state, increment) = numpy_pcg64_seed(1);
        let actual = (0..4)
            .map(|_| crate::numpy_normal::pcg64_raw(&mut state, increment))
            .collect::<Vec<_>>();
        assert_eq!(
            actual,
            vec![
                9_441_442_522_235_856_127,
                17_532_960_557_476_522_086,
                2_659_275_481_604_167_885,
                17_499_493_567_006_797_778,
            ]
        );
    }

    #[test]
    fn pcg64_seed_matches_numpy_for_zero_and_independent_noise_seeds() {
        for (seed, expected) in [
            (
                0,
                [
                    11_749_869_230_777_074_271,
                    4_976_686_463_289_251_617,
                    755_828_109_848_996_024,
                    304_881_062_738_325_533,
                ],
            ),
            (
                99,
                [
                    9_334_618_346_840_842_905,
                    10_424_100_709_723_369_767,
                    9_443_182_695_686_696_458,
                    17_933_673_198_744_876_582,
                ],
            ),
        ] {
            let (mut state, increment) = numpy_pcg64_seed(seed);
            let actual = (0..4)
                .map(|_| crate::numpy_normal::pcg64_raw(&mut state, increment))
                .collect::<Vec<_>>();
            assert_eq!(actual, expected, "seed {seed} raw stream");
        }
    }

    #[test]
    fn random_noise_matches_numpy_default_rng_normal_sequence() {
        let (mut state, increment) = numpy_pcg64_seed(1);
        let actual = (0..6)
            .map(|_| crate::numpy_normal::standard_normal(&mut state, increment))
            .collect::<Vec<_>>();
        assert_eq!(
            actual,
            vec![
                0.345584192064786,
                0.8216181435011584,
                0.33043707618338714,
                -1.303157231604361,
                0.9053558666731177,
                0.4463745723640113,
            ]
        );
        for (seed, expected) in [
            (
                0,
                [
                    0.1257302210933933,
                    -0.1321048632913019,
                    0.6404226504432821,
                    0.10490011715303971,
                    -0.535669373161111,
                    0.36159505490948474,
                ],
            ),
            (
                99,
                [
                    0.08249430428370294,
                    -0.46441841495421887,
                    0.05051506297463688,
                    0.6862308196812632,
                    -1.7567905055789348,
                    1.6844316011395088,
                ],
            ),
        ] {
            let (mut state, increment) = numpy_pcg64_seed(seed);
            let actual = (0..expected.len())
                .map(|_| crate::numpy_normal::standard_normal(&mut state, increment))
                .collect::<Vec<_>>();
            assert_eq!(actual, expected, "seed {seed} normal stream");
        }
    }

    #[test]
    fn accepts_protocol4_pybert_cfg_root_without_restoring_a_python_class() {
        let bytes = [
            0x80, 0x04, 0x95, 0x73, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x8c, 0x14, 0x70,
            0x79, 0x62, 0x65, 0x72, 0x74, 0x2e, 0x63, 0x6f, 0x6e, 0x66, 0x69, 0x67, 0x75, 0x72,
            0x61, 0x74, 0x69, 0x6f, 0x6e, 0x94, 0x8c, 0x09, 0x50, 0x79, 0x42, 0x65, 0x72, 0x74,
            0x43, 0x66, 0x67, 0x94, 0x93, 0x94, 0x29, 0x81, 0x94, 0x7d, 0x94, 0x28, 0x8c, 0x08,
            0x62, 0x69, 0x74, 0x5f, 0x72, 0x61, 0x74, 0x65, 0x94, 0x47, 0x40, 0x24, 0x00, 0x00,
            0x00, 0x00, 0x00, 0x00, 0x8c, 0x05, 0x6e, 0x62, 0x69, 0x74, 0x73, 0x94, 0x4d, 0xe8,
            0x03, 0x8c, 0x07, 0x70, 0x61, 0x74, 0x74, 0x65, 0x72, 0x6e, 0x94, 0x8c, 0x06, 0x50,
            0x52, 0x42, 0x53, 0x2d, 0x37, 0x94, 0x8c, 0x04, 0x73, 0x65, 0x65, 0x64, 0x94, 0x4b,
            0x11, 0x8c, 0x05, 0x6e, 0x73, 0x70, 0x75, 0x69, 0x94, 0x4b, 0x02, 0x75, 0x62, 0x2e,
        ];
        let value = parse_legacy_pickle_config(&bytes).expect("protocol 4 root is portable");
        assert_eq!(value["nbits"].as_u64(), Some(1000));
        assert_eq!(value["pattern"].as_str(), Some("PRBS-7"));
    }

    #[test]
    fn rejects_protocol45_pybert_cfg_global_when_it_is_nested() {
        let nested = [
            0x80, 0x04, 0x7d, 0x8c, 0x14, b'p', b'y', b'b', b'e', b'r', b't', b'.', b'c', b'o',
            b'n', b'f', b'i', b'g', b'u', b'r', b'a', b't', b'i', b'o', b'n', 0x94, 0x8c, 0x09,
            b'P', b'y', b'B', b'e', b'r', b't', b'C', b'f', b'g', 0x94, 0x93,
        ];
        assert!(!pickle_protocol45_root_is_pybert_cfg(&nested));
    }

    #[test]
    fn rejects_non_contiguous_dfe_taps_but_allows_ts4_without_external_parent() {
        let path = std::env::temp_dir().join(format!("pb01-dfe-gaps-{}.yaml", std::process::id()));
        fs::write(
            &path,
            tagged_config()
                .replace(
                    "- !!python/tuple [false, -0.2, 0.4]",
                    "- !!python/tuple [true, -0.2, 0.2]\n- !!python/tuple [false, -0.2, 0.2]\n- !!python/tuple [true, -0.2, 0.2]",
                )
                .replace("nspui: 2", "nspui: 2\ntx_use_ts4: true"),
        )
        .unwrap();
        assert!(matches!(
            parse_legacy_config_v1(&path),
            Err(LegacyRuntimeError::Unsupported(message)) if message.contains("contiguously")
        ));
        let _ = fs::remove_file(path);
    }

    #[test]
    fn rejects_unclassified_top_level_controls() {
        let path = std::env::temp_dir().join(format!("pb01-unknown-{}.yaml", std::process::id()));
        fs::write(
            &path,
            format!("{}future_equalizer_mode: enabled\n", tagged_config()),
        )
        .unwrap();
        let error = parse_legacy_config_v1(&path).unwrap_err();
        assert!(
            matches!(error, LegacyRuntimeError::Unsupported(message) if message.contains("future_equalizer_mode"))
        );
        let _ = fs::remove_file(path);
    }

    #[test]
    fn rejects_unapproved_or_missing_yaml_tags() {
        for (name, yaml) in [
            ("root", "!!python/object:builtins.dict\nnbits: 1000\n"),
            (
                "nested",
                "!!python/object:pybert.configuration.PyBertCfg\npattern: !future PRBS-7\n",
            ),
            ("missing", "nbits: 1000\n"),
        ] {
            let path =
                std::env::temp_dir().join(format!("pb01-tag-{name}-{}.yaml", std::process::id()));
            fs::write(&path, yaml).unwrap();
            assert!(matches!(
                parse_legacy_config_v1(&path),
                Err(LegacyRuntimeError::Unsupported(_))
            ));
            let _ = fs::remove_file(path);
        }
    }

    #[test]
    fn rejects_config_and_projection_budget_overflows() {
        let oversized =
            std::env::temp_dir().join(format!("pb01-config-budget-{}.yaml", std::process::id()));
        fs::write(&oversized, vec![b' '; MAX_CONFIG_BYTES as usize + 1]).unwrap();
        assert!(matches!(
            parse_legacy_config_v1(&oversized),
            Err(LegacyRuntimeError::ResourceLimit(message)) if message.contains("1 MiB")
        ));
        let _ = fs::remove_file(oversized);

        let samples =
            std::env::temp_dir().join(format!("pb01-sample-budget-{}.yaml", std::process::id()));
        fs::write(
            &samples,
            tagged_config().replace("nbits: 1000", "nbits: 18446744073709551615"),
        )
        .unwrap();
        assert!(matches!(
            parse_legacy_config_v1(&samples),
            Err(LegacyRuntimeError::ResourceLimit(message)) if message.contains("nbits*nspui")
        ));
        let _ = fs::remove_file(samples);
    }

    #[test]
    fn rejects_tap_and_result_length_budgets() {
        let rx = std::env::temp_dir().join(format!("pb01-rx-budget-{}.yaml", std::process::id()));
        fs::write(&rx, format!("{}rx_n_taps: 257\n", tagged_config())).unwrap();
        assert!(matches!(
            parse_legacy_config_v1(&rx),
            Err(LegacyRuntimeError::ResourceLimit(message)) if message.contains("rx_n_taps")
        ));
        let _ = fs::remove_file(rx);

        let dfe = std::env::temp_dir().join(format!("pb01-dfe-budget-{}.yaml", std::process::id()));
        let dfe_entries = (0..=MAX_DFE_TAPS)
            .map(|_| "- !!python/tuple [false, -0.2, 0.4]\n")
            .collect::<String>();
        fs::write(
            &dfe,
            format!(
                "!!python/object:pybert.configuration.PyBertCfg\nnbits: 1000\nnspui: 2\ndfe_tap_tuners:\n{dfe_entries}"
            ),
        )
        .unwrap();
        assert!(matches!(
            parse_legacy_config_v1(&dfe),
            Err(LegacyRuntimeError::ResourceLimit(message)) if message.contains("dfe_tap_tuners")
        ));
        let _ = fs::remove_file(dfe);

        assert!(matches!(
            validate_legacy_result_lengths(usize::MAX, 0, 0),
            Err(LegacyRuntimeError::ResourceLimit(message)) if message.contains("channel result length")
        ));

        let boundary = LegacyArrayLayout {
            total_values: MAX_LEGACY_RESULT_BYTES / std::mem::size_of::<f64>(),
            construction_peak_values: 0,
            retained_projection_values: 0,
            transient_vector_peak_values: 0,
            spectrum_work_peak_values: 0,
        };
        assert!(boundary.validate_class_codec_peak().is_ok());
        assert!(matches!(
            LegacyArrayLayout {
                total_values: boundary.total_values + 1,
                ..boundary
            }
            .validate_class_codec_peak(),
            Err(LegacyRuntimeError::ResourceLimit(message)) if message.contains("logical payload")
        ));
        assert!(matches!(
            LegacyArrayLayout {
                construction_peak_values: usize::MAX,
                ..boundary
            }
            .validate_class_codec_peak(),
            Err(LegacyRuntimeError::ResourceLimit(message)) if message.contains("peak byte count")
        ));
    }
}
