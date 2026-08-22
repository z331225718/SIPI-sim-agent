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
    collections::{BTreeMap, BTreeSet},
    fs::{self, File},
    io::Read,
    path::{Path, PathBuf},
};

use serde::{Deserialize, Serialize};
use serde_pickle::{SerOptions, to_vec};
use serde_yaml::Value;
use thiserror::Error;
use yaml_rust2::parser::{Event, EventReceiver, Parser, Tag};

use crate::{
    AnalysisConfigV1, ChannelInputV1, CtleConfigV1, DfeConfigV1, FfeConfigV1, Hertz,
    LegacySimError, LegacySimRequestV1, MetallicLineChannelV1, ModulationV1, Ohms, PatternV1,
    ResourceLimitsV1, RxConfigV1, SIMULATION_SCHEMA_V1, Seconds, SimulationInputV1,
    SimulationOutputV1, TimebaseV1, TxConfigV1, Volts, simulate_native_v1,
};

const DEFAULT_NBITS: u64 = 1_000;
const DEFAULT_NSPUI: u32 = 32;
const DEFAULT_EYE_BITS: u64 = 1_000;
const DEFAULT_BIT_RATE_GBPS: f64 = 10.0;
const DEFAULT_FMAX_GHZ: f64 = 40.0;
const DEFAULT_FSTEP_MHZ: f64 = 10.0;
const DEFAULT_VOD: f64 = 1.0;
const DEFAULT_RS: f64 = 100.0;
const DEFAULT_COUT_PF: f64 = 0.5;
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
const MAX_RX_TAPS: usize = 256;
const MAX_DFE_TAPS: usize = 64;
const MAX_TOTAL_SAMPLES: u64 = 50_000_000;
const MAX_LEGACY_RESULT_BYTES: usize = 512 * 1024 * 1024;
const LEGACY_RESULT_VECTOR_UPPER_BOUND: u64 = 16;
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
];

// Pinned PyBERT serialization metadata and inert UI state present in the
// scoped fixture. Every other top-level field must be classified before the
// Rust leaf is allowed to execute it.
const IGNORED_INERT_KEYS: &[&str] = &["date_created", "version", "debug", "renumber"];

const UNSUPPORTED_ENABLED_KEYS: &[&str] = &[
    "use_ch_file",
    "use_ctle_file",
    "tx_use_ami",
    "rx_use_ami",
    "tx_use_ibis",
    "rx_use_ibis",
    "tx_use_ts4",
    "rx_use_ts4",
    "tx_use_getwave",
    "rx_use_getwave",
    "rx_use_viterbi",
    "rx_viterbi_fec",
];

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
}

#[derive(Clone, Debug, Deserialize, Default)]
#[serde(default)]
struct RawLegacyConfig {
    bit_rate: Option<f64>,
    nbits: Option<u64>,
    pattern: Option<String>,
    seed: Option<u64>,
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
}

/// Typed projection of the legacy configuration consumed by the migrated leaf.
#[derive(Clone, Debug, PartialEq)]
pub struct LegacyConfigProjectionV1 {
    pub bit_rate_gbps: f64,
    pub nbits: u64,
    pub pattern: String,
    pub seed: u64,
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
    pub unconsumed_keys: Vec<String>,
}

impl LegacyConfigProjectionV1 {
    fn simulation_input(&self, run_id: String) -> Result<SimulationInputV1, LegacyRuntimeError> {
        if self.mod_type != "NRZ" {
            return Err(LegacyRuntimeError::Unsupported(format!(
                "mod_type={} (only NRZ is migrated)",
                self.mod_type
            )));
        }
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
        let ui = 1.0 / (self.bit_rate_gbps * 1.0e9);
        let sample_interval = ui / f64::from(self.nspui);
        let tx_weights = tx_weights(&self.tx_taps)?;
        let rx_weights = rx_weights(self.rx_n_taps, self.rx_n_pre)?;
        let dfe_taps = self
            .dfe_tap_tuners
            .iter()
            .take_while(|(enabled, _, _)| *enabled)
            .count();
        let dfe = (dfe_taps > 0).then_some(DfeConfigV1 {
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
        });
        let ctle = self.ctle_enable.then_some(CtleConfigV1 {
            bandwidth: Hertz(self.rx_bw_ghz * 1.0e9),
            peak_frequency: Hertz(self.peak_freq_ghz * 1.0e9),
            peak_magnitude_db: self.peak_mag_db,
            frequency_step_hz: Some(Hertz(self.f_step_mhz * 1.0e6)),
            frequency_max_hz: Some(Hertz(self.f_max_ghz * 1.0e9)),
        });
        let impulse_length =
            (self.impulse_length_ns > 0.0).then_some(Seconds(self.impulse_length_ns * 1.0e-9));
        Ok(SimulationInputV1 {
            schema: SIMULATION_SCHEMA_V1.into(),
            run_id,
            modulation: ModulationV1::Nrz,
            pattern: PatternV1::Prbs {
                order,
                seed: self.seed,
            },
            timebase: TimebaseV1 {
                sample_interval: Seconds(sample_interval),
                samples_per_ui: self.nspui,
                data_rate: Hertz(self.bit_rate_gbps * 1.0e9),
                nbits: self.nbits,
            },
            channel: ChannelInputV1::MetallicLine(MetallicLineChannelV1 {
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
            }),
            tx: TxConfigV1 {
                amplitude: Volts(self.vod_v),
                ffe: FfeConfigV1 {
                    enabled: true,
                    weights: tx_weights,
                    cursor_position: 3,
                },
                additive_noise: None,
                periodic_noise: None,
            },
            rx: RxConfigV1 {
                native_ctle_enabled: self.ctle_enable,
                ctle,
                ffe: FfeConfigV1 {
                    enabled: true,
                    weights: rx_weights,
                    cursor_position: self.rx_n_pre,
                },
                dfe_taps: dfe_taps as u32,
                dfe,
                viterbi_enabled: false,
                viterbi: None,
            },
            analysis: AnalysisConfigV1 {
                statistical_eye: None,
                include_jitter: false,
                include_bathtub: false,
                ber_eye_bits: Some(self.eye_bits),
                jitter_eye_uis: None,
            },
            limits: ResourceLimitsV1::default(),
            external_models: Vec::new(),
            legacy_options: BTreeMap::new(),
        })
    }
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
    validate_yaml_tag_policy(&bytes)?;
    let value: Value = serde_yaml::from_slice(&bytes)?;
    let value = strip_validated_yaml_tags(value, 0)?;
    let mapping = value
        .as_mapping()
        .ok_or(LegacyRuntimeError::ConfigNotMapping)?;
    validate_sequence_budget(mapping, "tx_taps", 6)?;
    validate_sequence_budget(mapping, "dfe_tap_tuners", MAX_DFE_TAPS)?;
    for key in UNSUPPORTED_ENABLED_KEYS {
        if mapping
            .get(Value::String((*key).into()))
            .and_then(Value::as_bool)
            .unwrap_or(false)
        {
            return Err(LegacyRuntimeError::Unsupported(format!("{key}=true")));
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
    let config = LegacyConfigProjectionV1 {
        bit_rate_gbps: finite_positive(raw.bit_rate.unwrap_or(DEFAULT_BIT_RATE_GBPS), "bit_rate")?,
        nbits: raw.nbits.unwrap_or(DEFAULT_NBITS),
        pattern: raw.pattern.unwrap_or_else(|| "PRBS-7".into()),
        seed: raw.seed.unwrap_or(1),
        nspui: raw.nspui.unwrap_or(DEFAULT_NSPUI),
        eye_bits: raw.eye_bits.unwrap_or(DEFAULT_EYE_BITS),
        mod_type: raw.mod_type.unwrap_or_else(|| "NRZ".into()),
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
        unconsumed_keys,
    };
    if raw.pn_mag.unwrap_or(0.0) != 0.0 || raw.rn.unwrap_or(0.0) != 0.0 {
        return Err(LegacyRuntimeError::Unsupported(
            "periodic/random noise is not in the migrated leaf".into(),
        ));
    }
    if config.nbits < DEFAULT_NBITS {
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
    if config.rx_n_pre >= config.rx_n_taps || config.rx_n_taps == 0 {
        return Err(LegacyRuntimeError::InvalidConfig(
            "rx_n_pre must be less than a non-zero rx_n_taps".into(),
        ));
    }
    validate_projection_budgets(&config)?;
    Ok(config)
}

/// Execute the migrated leaf and write the bounded Python-readable artifact.
pub fn run_legacy_sim_v1(
    request: &LegacySimRequestV1,
) -> Result<LegacySimReportV1, LegacyRuntimeError> {
    crate::validate_legacy_sim_request(request).map_err(|error| match error {
        LegacySimError::ConfigIo(error) => LegacyRuntimeError::Io(error),
        other => LegacyRuntimeError::InvalidConfig(other.to_string()),
    })?;
    if request
        .config_file
        .extension()
        .and_then(|value| value.to_str())
        == Some("pybert_cfg")
    {
        return Err(LegacyRuntimeError::Unsupported(
            "pickle .pybert_cfg input is not in the migrated leaf".into(),
        ));
    }
    let config = parse_legacy_config_v1(&request.config_file)?;
    let run_id = request
        .config_file
        .file_stem()
        .and_then(|value| value.to_str())
        .filter(|value| !value.is_empty())
        .unwrap_or("pb-01-legacy")
        .to_owned();
    let input = config.simulation_input(run_id)?;
    let output = simulate_native_v1(&input)?;
    let result_path = request
        .resolved_results_path()
        .map_err(|error| LegacyRuntimeError::InvalidConfig(error.to_string()))?;
    write_legacy_result_v1(&result_path, &output)?;
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
/// while identifying itself as `sipi.pybert_data.v1`.  A future slice can
/// replace this dictionary with a class-compatible `PyBertData` pickle without
/// changing the Rust simulation leaf or the CLI default path.
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

#[derive(Debug, Serialize)]
struct LegacyPicklePayload {
    schema: &'static str,
    artifact_kind: &'static str,
    item_names: Vec<&'static str>,
    arrays: BTreeMap<String, Vec<f64>>,
    metrics: BTreeMap<String, f64>,
    source: &'static str,
}

fn legacy_arrays(
    output: &SimulationOutputV1,
) -> Result<BTreeMap<String, Vec<f64>>, LegacyRuntimeError> {
    let source = &output.arrays;
    let mut arrays = BTreeMap::new();
    let get = |name: &str| source.get(name).cloned().unwrap_or_default();
    let channel = get("channel_impulse_v_per_v");
    let tx_out_h = get("tx_channel_impulse_v_per_v");
    let ctle_out_h = tx_out_h.clone();
    // With adaptive DFE bypassed, PyBERT's dfe impulse is the preceding CTLE
    // output impulse passed through the configured RX FFE. Reuse the native
    // FFE impulse rather than baking a fixture-specific cursor delay here.
    let rx_ffe = get("rx_ffe_impulse_v_per_v");
    let dfe_out_h = if rx_ffe.is_empty() {
        tx_out_h.clone()
    } else {
        causal_convolve(&tx_out_h, &rx_ffe, tx_out_h.len())?
    };
    let tx_out = get("tx_waveform_v");
    for (name, values) in [
        ("chnl_h", channel.clone()),
        ("tx_out_h", tx_out_h.clone()),
        ("ctle_out_h", ctle_out_h.clone()),
        ("dfe_out_h", dfe_out_h.clone()),
        ("chnl_s", step_from(&channel)),
        ("tx_s", step_from(&tx_out_h)),
        ("ctle_s", step_from(&ctle_out_h)),
        ("dfe_s", step_from(&dfe_out_h)),
        ("tx_out_s", step_from(&tx_out_h)),
        ("ctle_out_s", step_from(&ctle_out_h)),
        ("dfe_out_s", step_from(&dfe_out_h)),
        (
            "chnl_p",
            pulse_from(&channel, inferred_samples_per_ui(source)),
        ),
        (
            "tx_out_p",
            pulse_from(&tx_out_h, inferred_samples_per_ui(source)),
        ),
        (
            "ctle_out_p",
            pulse_from(&ctle_out_h, inferred_samples_per_ui(source)),
        ),
        (
            "dfe_out_p",
            pulse_from(&dfe_out_h, inferred_samples_per_ui(source)),
        ),
        ("tx_out", tx_out),
    ] {
        arrays.insert(name.into(), values);
    }
    for name in LEGACY_ITEM_NAMES {
        arrays.entry(name.into()).or_default();
    }
    Ok(arrays)
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
    if n_taps == 0 || n_taps > MAX_RX_TAPS || n_pre >= n_taps {
        return Err(LegacyRuntimeError::InvalidConfig("rx_taps shape".into()));
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
    let sample_count = config
        .nbits
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
    vec![
        (true, -0.2, 0.4),
        (true, -0.15, 0.15),
        (true, -0.05, 0.1),
        (true, -0.05, 0.1),
        (true, -0.05, 0.1),
    ]
}

#[cfg(test)]
mod tests {
    use super::*;

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
    }
}
