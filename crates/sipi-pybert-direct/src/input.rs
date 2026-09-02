use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};

use crate::{ContractError, Hertz, Ohms, SIMULATION_SCHEMA_V1, Seconds, Volts};

#[derive(Debug, Clone, Deserialize, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ModulationV1 {
    Nrz,
    Pam4,
    DuoBinary,
}

#[derive(Debug, Clone, Deserialize, PartialEq, Serialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum PatternV1 {
    Prbs {
        order: u8,
        seed: u64,
    },
    ExplicitBits {
        bit_count: u64,
        /// Optional host-owned bit stream for hybrid/external-model paths.
        /// An empty vector retains v1 control-only telemetry compatibility, but
        /// native execution requires actual values rather than inventing bits.
        #[serde(default)]
        bits: Vec<u8>,
    },
}

impl PatternV1 {
    fn validate(&self) -> Result<(), ContractError> {
        match self {
            Self::Prbs { order, .. } if (2..=63).contains(order) => Ok(()),
            Self::Prbs { .. } => Err(ContractError::InvalidPrbsOrder),
            Self::ExplicitBits { bit_count, bits }
                if *bit_count > 0
                    && (bits.is_empty()
                        || (u64::try_from(bits.len()).ok() == Some(*bit_count)
                            && bits.iter().all(|bit| *bit <= 1))) =>
            {
                Ok(())
            }
            Self::ExplicitBits { bit_count, .. } if *bit_count == 0 => {
                Err(ContractError::InvalidBitCount)
            }
            Self::ExplicitBits { .. } => Err(ContractError::InvalidExplicitBits),
        }
    }
}

#[derive(Debug, Clone, Deserialize, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct TimebaseV1 {
    pub sample_interval: Seconds,
    pub samples_per_ui: u32,
    pub data_rate: Hertz,
    pub nbits: u64,
}

impl TimebaseV1 {
    fn validate(&self) -> Result<(), ContractError> {
        if !self.sample_interval.is_finite_positive() {
            return Err(ContractError::InvalidSampleInterval);
        }
        if !self.data_rate.is_finite_positive() {
            return Err(ContractError::InvalidDataRate);
        }
        if self.samples_per_ui == 0 {
            return Err(ContractError::InvalidSamplesPerUi);
        }
        if self.nbits == 0 {
            return Err(ContractError::InvalidBitCount);
        }
        Ok(())
    }
}

#[derive(Debug, Clone, Deserialize, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ChannelResponseV1 {
    pub sample_interval: Seconds,
    /// Fixture/IPC representation. The PyO3 adapter supplies production arrays
    /// through validated contiguous buffers rather than JSON text.
    pub impulse_response_volts_per_second: Vec<f64>,
    pub source_impedance: Ohms,
    pub load_impedance: Ohms,
}

/// Typed parameters for PyBERT's analytic metallic transmission-line model.
/// All values use SI units; capacitive terminations are intentionally explicit
/// rather than inferred from host-side parasitic configuration.
#[derive(Debug, Clone, Deserialize, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct MetallicLineChannelV1 {
    pub sample_interval: Seconds,
    pub length_m: f64,
    pub skin_effect_resistance_ohm_per_m: f64,
    pub crossover_angular_frequency_rad_per_s: f64,
    pub dc_resistance_ohm_per_m: f64,
    pub characteristic_impedance: Ohms,
    pub propagation_velocity_m_per_s: f64,
    pub loss_tangent: f64,
    pub source_impedance: Ohms,
    pub source_capacitance_f: f64,
    pub load_impedance: Ohms,
    pub load_capacitance_f: f64,
    /// Apply PyBERT's one-sided raised-cosine frequency window before IFFT.
    #[serde(default)]
    pub apply_raised_cosine_window: bool,
    /// Optional legacy-compatible uniformly spaced frequency grid.
    ///
    /// When supplied, the analytic response is evaluated on this grid before
    /// cubic resampling to `sample_interval`; omitting both fields preserves
    /// the native FFT-grid path for low-level callers.
    #[serde(default)]
    pub frequency_step_hz: Option<Hertz>,
    #[serde(default)]
    pub frequency_max_hz: Option<Hertz>,
    /// Optional host-requested impulse-response duration after resampling.
    #[serde(default)]
    pub impulse_length: Option<Seconds>,
}

impl MetallicLineChannelV1 {
    fn validate(&self) -> Result<(), ContractError> {
        let valid_frequency_grid = match (self.frequency_step_hz, self.frequency_max_hz) {
            (None, None) => true,
            (Some(step), Some(maximum)) => {
                step.is_finite_positive() && maximum.is_finite_positive()
            }
            _ => false,
        };
        if !self.sample_interval.is_finite_positive()
            || !self.length_m.is_finite()
            || self.length_m < 0.0
            || !self.skin_effect_resistance_ohm_per_m.is_finite()
            || self.skin_effect_resistance_ohm_per_m < 0.0
            || !self.crossover_angular_frequency_rad_per_s.is_finite()
            || self.crossover_angular_frequency_rad_per_s <= 0.0
            || !self.dc_resistance_ohm_per_m.is_finite()
            || self.dc_resistance_ohm_per_m < 0.0
            || !self.characteristic_impedance.is_finite_positive()
            || !self.propagation_velocity_m_per_s.is_finite()
            || self.propagation_velocity_m_per_s <= 0.0
            || !self.loss_tangent.is_finite()
            || !self.source_impedance.is_finite_positive()
            || !self.source_capacitance_f.is_finite()
            || self.source_capacitance_f < 0.0
            || !self.load_impedance.is_finite_positive()
            || !self.load_capacitance_f.is_finite()
            || self.load_capacitance_f < 0.0
            || !valid_frequency_grid
            || self
                .impulse_length
                .is_some_and(|value| !value.is_finite_positive())
        {
            return Err(ContractError::InvalidChannelResponse);
        }
        Ok(())
    }
}

impl ChannelResponseV1 {
    fn validate(&self) -> Result<(), ContractError> {
        if !self.sample_interval.is_finite_positive() {
            return Err(ContractError::InvalidSampleInterval);
        }
        if !self.source_impedance.is_finite_positive() || !self.load_impedance.is_finite_positive()
        {
            return Err(ContractError::InvalidChannelImpedance);
        }
        if self.impulse_response_volts_per_second.is_empty()
            || self
                .impulse_response_volts_per_second
                .iter()
                .any(|sample| !sample.is_finite())
        {
            return Err(ContractError::InvalidChannelResponse);
        }
        Ok(())
    }
}

#[derive(Debug, Clone, Deserialize, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ExternalModelRefV1 {
    pub kind: String,
    pub capability: String,
}

impl ExternalModelRefV1 {
    fn validate(&self) -> Result<(), ContractError> {
        if self.kind.trim().is_empty() || self.capability.trim().is_empty() {
            return Err(ContractError::InvalidExternalModel);
        }
        Ok(())
    }
}

#[derive(Debug, Clone, Deserialize, PartialEq, Serialize)]
#[serde(tag = "kind", content = "value", rename_all = "snake_case")]
pub enum ChannelInputV1 {
    ImpulseResponse(ChannelResponseV1),
    MetallicLine(MetallicLineChannelV1),
    ExternalModel(ExternalModelRefV1),
}

impl ChannelInputV1 {
    fn validate(&self) -> Result<(), ContractError> {
        match self {
            Self::ImpulseResponse(response) => response.validate(),
            Self::MetallicLine(channel) => channel.validate(),
            Self::ExternalModel(model) => model.validate(),
        }
    }
}

#[derive(Debug, Clone, Default, Deserialize, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct FfeConfigV1 {
    pub enabled: bool,
    pub weights: Vec<f64>,
    pub cursor_position: usize,
}

impl FfeConfigV1 {
    fn validate(&self) -> Result<(), ContractError> {
        if !self.enabled {
            return Ok(());
        }
        if self.weights.is_empty()
            || self.cursor_position >= self.weights.len()
            || self.weights.iter().any(|weight| !weight.is_finite())
        {
            return Err(ContractError::InvalidFfe);
        }
        Ok(())
    }
}

#[derive(Debug, Clone, Deserialize, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct TxConfigV1 {
    pub amplitude: Volts,
    pub ffe: FfeConfigV1,
    /// Host-generated physical additive noise in volts at the receiver input,
    /// before any native CTLE filter. This matches the reference native-TX
    /// path, where channel crosstalk/noise is equalized together with signal.
    /// Rust deliberately consumes samples instead of choosing an RNG so a
    /// Python/Rust comparison can replay identical noise exactly.
    #[serde(default)]
    pub additive_noise: Option<AdditiveNoiseV1>,
    /// Optional deterministic periodic aggressor applied at the pre-CTLE
    /// receiver input. Host-provided random noise remains separate above.
    #[serde(default)]
    pub periodic_noise: Option<PeriodicNoiseV1>,
}

#[derive(Debug, Clone, Deserialize, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct AdditiveNoiseV1 {
    pub samples_v: Vec<f64>,
    /// Seed used to resolve the legacy random-noise waveform. This is
    /// provenance only; the native core consumes the materialized samples.
    #[serde(default)]
    pub effective_seed: Option<u64>,
}

impl AdditiveNoiseV1 {
    fn validate(&self) -> Result<(), ContractError> {
        if self.samples_v.iter().any(|sample| !sample.is_finite()) {
            return Err(ContractError::InvalidAdditiveNoise);
        }
        Ok(())
    }
}

/// Deterministic capacitive-coupled aggressor noise, matching the legacy
/// native-TX periodic-noise control without introducing an RNG dependency.
#[derive(Debug, Clone, Deserialize, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct PeriodicNoiseV1 {
    pub magnitude: Volts,
    pub frequency: Hertz,
}

impl PeriodicNoiseV1 {
    fn validate(&self) -> Result<(), ContractError> {
        if !self.magnitude.0.is_finite()
            || self.magnitude.0 < 0.0
            || !self.frequency.is_finite_positive()
        {
            return Err(ContractError::InvalidPeriodicNoise);
        }
        Ok(())
    }
}

impl Default for TxConfigV1 {
    fn default() -> Self {
        Self {
            amplitude: Volts(1.0),
            ffe: FfeConfigV1::default(),
            additive_noise: None,
            periodic_noise: None,
        }
    }
}

impl TxConfigV1 {
    fn validate(&self) -> Result<(), ContractError> {
        if !self.amplitude.is_finite_positive() {
            return Err(ContractError::InvalidTxAmplitude);
        }
        self.ffe.validate()?;
        if let Some(additive_noise) = &self.additive_noise {
            additive_noise.validate()?;
        }
        if let Some(periodic_noise) = &self.periodic_noise {
            periodic_noise.validate()?;
        }
        Ok(())
    }
}

#[derive(Debug, Clone, Deserialize, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct RxConfigV1 {
    pub native_ctle_enabled: bool,
    #[serde(default)]
    pub ctle: Option<CtleConfigV1>,
    /// Optional linear receive FFE after the CTLE and before DFE/CDR.
    ///
    /// This is distinct from the transmitter FFE: legacy PyBERT applies the
    /// receive FIR to the CTLE output, and its default cursor is intentionally
    /// delayed by several UIs.
    #[serde(default)]
    pub ffe: FfeConfigV1,
    pub dfe_taps: u32,
    #[serde(default)]
    pub dfe: Option<DfeConfigV1>,
    pub viterbi_enabled: bool,
    #[serde(default)]
    pub viterbi: Option<ViterbiConfigV1>,
}

impl Default for RxConfigV1 {
    fn default() -> Self {
        Self {
            native_ctle_enabled: true,
            ctle: None,
            ffe: FfeConfigV1::default(),
            dfe_taps: 0,
            dfe: None,
            viterbi_enabled: false,
            viterbi: None,
        }
    }
}

impl RxConfigV1 {
    fn validate(&self) -> Result<(), ContractError> {
        if self
            .dfe
            .as_ref()
            .and_then(|dfe| dfe.tap_limits.as_ref())
            .is_some_and(|limits| limits.len() != self.dfe_taps as usize)
        {
            return Err(ContractError::InvalidDfe);
        }
        if let Some(ctle) = &self.ctle {
            ctle.validate()?;
        }
        self.ffe.validate()?;
        if let Some(dfe) = &self.dfe {
            dfe.validate()?;
        }
        if let Some(viterbi) = &self.viterbi {
            viterbi.validate()?;
        }
        Ok(())
    }
}

/// Typed controls for the normalized native CTLE frequency response.
#[derive(Debug, Clone, Deserialize, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct CtleConfigV1 {
    pub bandwidth: Hertz,
    pub peak_frequency: Hertz,
    pub peak_magnitude_db: f64,
    /// Optional legacy PyBERT frequency grid. Both values are required to
    /// reproduce its `make_ctle -> irfft -> cubic resample` path.
    #[serde(default)]
    pub frequency_step_hz: Option<Hertz>,
    #[serde(default)]
    pub frequency_max_hz: Option<Hertz>,
    /// Optional impulse response imported from a portable legacy Touchstone
    /// file. Values are dimensionless V/V samples at the request timebase;
    /// analytic fields above remain populated as the legacy metadata surface.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub impulse_response_v_per_v: Option<Vec<f64>>,
}

impl CtleConfigV1 {
    fn validate(&self) -> Result<(), ContractError> {
        if !self.bandwidth.is_finite_positive()
            || !self.peak_frequency.is_finite_positive()
            || !self.peak_magnitude_db.is_finite()
        {
            return Err(ContractError::InvalidCtle);
        }
        match (self.frequency_step_hz, self.frequency_max_hz) {
            (None, None) if self.valid_imported_impulse() => Ok(()),
            (Some(step), Some(maximum))
                if step.is_finite_positive() && maximum.is_finite_positive() =>
            {
                if self.valid_imported_impulse() {
                    Ok(())
                } else {
                    Err(ContractError::InvalidCtle)
                }
            }
            (None, None) => Err(ContractError::InvalidCtle),
            _ => Err(ContractError::InvalidCtle),
        }
    }

    fn valid_imported_impulse(&self) -> bool {
        self.impulse_response_v_per_v
            .as_ref()
            .is_none_or(|impulse| {
                !impulse.is_empty()
                    && impulse.len() <= 16 * 1024 * 1024
                    && impulse.iter().all(|sample| sample.is_finite())
            })
    }
}

/// Typed controls for the bounded native DFE/CDR stage.
///
/// The tap count remains in `RxConfigV1` for wire compatibility with earlier
/// v1 requests.  Legacy tuner limits are optional because the older typed
/// callers did not carry them; the admitted PyBERT projection populates them
/// so the Rust DFE can enforce the same bounded update interval.
#[derive(Debug, Clone, Deserialize, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct DfeConfigV1 {
    pub gain: f64,
    pub decision_scaler: Volts,
    pub n_ave: u32,
    pub delta_t: Seconds,
    pub alpha: f64,
    pub n_lock_ave: u32,
    pub rel_lock_tol: f64,
    pub lock_sustain: u32,
    pub ideal: bool,
    pub bandwidth: Hertz,
    pub use_agc: bool,
    pub agc_n_ave: u32,
    #[serde(default)]
    pub tap_limits: Option<Vec<(f64, f64)>>,
}

impl DfeConfigV1 {
    fn validate(&self) -> Result<(), ContractError> {
        if !self.gain.is_finite()
            || !self.decision_scaler.0.is_finite()
            || self.n_ave == 0
            || !self.delta_t.is_finite_positive()
            || !self.alpha.is_finite()
            || self.n_lock_ave == 0
            || !self.rel_lock_tol.is_finite()
            || self.rel_lock_tol < 0.0
            || !self.bandwidth.0.is_finite()
            || self.bandwidth.0 < 0.0
            || self.agc_n_ave == 0
            || self.tap_limits.as_ref().is_some_and(|limits| {
                limits
                    .iter()
                    .any(|(lower, upper)| !lower.is_finite() || !upper.is_finite() || lower > upper)
            })
        {
            return Err(ContractError::InvalidDfe);
        }
        if !self.ideal && self.bandwidth.0 <= 0.0 {
            return Err(ContractError::InvalidDfe);
        }
        Ok(())
    }
}

/// Typed limits for the bounded ISI Viterbi stage.
///
/// `noise_sigma_v` is deliberately required when the stage is enabled: the
/// native decoder must not invent a noise floor for a zero-noise request.
#[derive(Debug, Clone, Deserialize, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ViterbiConfigV1 {
    pub state_symbols: u32,
    #[serde(default)]
    pub fec: bool,
    #[serde(default)]
    pub noise_sigma_v: Option<Volts>,
    pub max_states: u32,
}

impl ViterbiConfigV1 {
    fn validate(&self) -> Result<(), ContractError> {
        if self.state_symbols < 2 || self.max_states < 4 {
            return Err(ContractError::InvalidViterbi);
        }
        if !self.fec
            && self
                .noise_sigma_v
                .is_none_or(|noise_sigma_v| !noise_sigma_v.is_finite_positive())
        {
            return Err(ContractError::InvalidViterbi);
        }
        Ok(())
    }
}

#[derive(Debug, Clone, Deserialize, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct StatisticalEyeConfigV1 {
    pub target_ber: f64,
    /// Additional BER thresholds for the same typed eye surface. The target
    /// BER remains the source for the primary scalar eye metrics.
    #[serde(default)]
    pub contour_ber_levels: Vec<f64>,
    /// Receiver sampling jitter is applied as a horizontal periodic BER-surface
    /// convolution. TX edge jitter below uses its own conditioned-distribution
    /// state propagation model.
    #[serde(default)]
    pub rx_rj_ui: Option<f64>,
    #[serde(default)]
    pub rx_dj_ui: Option<f64>,
    #[serde(default)]
    pub tx_rj_ui: Option<f64>,
    #[serde(default)]
    pub tx_dj_ui: Option<f64>,
    #[serde(default)]
    pub tx_dcd_ui: Option<f64>,
    pub voltage_resolution: Option<Volts>,
    pub time_points: u32,
    pub max_distribution_states: u32,
    /// Opt in to the post-receiver pulse used by the legacy Web result
    /// contract. The generic v1 contract remains pre-DFE by default.
    #[serde(default)]
    pub post_receiver_output: bool,
}

impl StatisticalEyeConfigV1 {
    fn validate(&self) -> Result<(), ContractError> {
        if !self.target_ber.is_finite() || !(0.0..0.5).contains(&self.target_ber) {
            return Err(ContractError::InvalidTargetBer);
        }
        if self
            .contour_ber_levels
            .iter()
            .any(|level| !level.is_finite() || !(0.0..0.5).contains(level))
            || self
                .contour_ber_levels
                .iter()
                .enumerate()
                .any(|(index, level)| self.contour_ber_levels[index + 1..].contains(level))
            || self.contour_ber_levels.len() > 32
        {
            return Err(ContractError::InvalidTargetBer);
        }
        if self
            .voltage_resolution
            .is_some_and(|resolution| !resolution.is_finite_positive())
        {
            return Err(ContractError::InvalidVoltageResolution);
        }
        if [
            self.rx_rj_ui,
            self.rx_dj_ui,
            self.tx_rj_ui,
            self.tx_dj_ui,
            self.tx_dcd_ui,
        ]
        .into_iter()
        .flatten()
        .any(|value| !value.is_finite() || value < 0.0)
        {
            return Err(ContractError::InvalidReceiverJitter);
        }
        if self.time_points == 0 {
            return Err(ContractError::InvalidTimePoints);
        }
        if self.max_distribution_states < 8 {
            return Err(ContractError::InvalidDistributionStateLimit);
        }
        Ok(())
    }
}

#[derive(Debug, Clone, Deserialize, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct AnalysisConfigV1 {
    pub statistical_eye: Option<StatisticalEyeConfigV1>,
    pub include_jitter: bool,
    pub include_bathtub: bool,
    /// Optional post-receiver BER correlation window. Omitted means use all
    /// configured input bits, preserving the original v1 request behavior.
    #[serde(default)]
    pub ber_eye_bits: Option<u64>,
    /// Optional trailing UI window used exclusively for jitter analysis.
    /// Omitted requests retain the original complete-waveform v1 behavior.
    #[serde(default)]
    pub jitter_eye_uis: Option<u64>,
    /// Relative spectral threshold used to classify periodic jitter.  The
    /// legacy PyBERT ``thresh`` setting projects here instead of being
    /// silently discarded; omission preserves PyBERT's 3-sigma default.
    #[serde(default)]
    pub jitter_rel_thresh: Option<f64>,
}

impl Default for AnalysisConfigV1 {
    fn default() -> Self {
        Self {
            statistical_eye: None,
            include_jitter: true,
            include_bathtub: true,
            ber_eye_bits: None,
            jitter_eye_uis: None,
            jitter_rel_thresh: None,
        }
    }
}

impl AnalysisConfigV1 {
    fn validate(&self) -> Result<(), ContractError> {
        if let Some(statistical_eye) = &self.statistical_eye {
            statistical_eye.validate()?;
        }
        if self.ber_eye_bits == Some(0) {
            return Err(ContractError::InvalidBerEyeBits);
        }
        if self.jitter_eye_uis == Some(0) {
            return Err(ContractError::InvalidJitterEyeUis);
        }
        if self
            .jitter_rel_thresh
            .is_some_and(|value| !value.is_finite() || value <= 0.0)
        {
            return Err(ContractError::InvalidJitterRelThresh);
        }
        Ok(())
    }
}

#[derive(Debug, Clone, Deserialize, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ResourceLimitsV1 {
    pub max_total_samples: u64,
    pub max_memory_bytes: u64,
    pub max_distribution_states: u32,
}

impl Default for ResourceLimitsV1 {
    fn default() -> Self {
        Self {
            max_total_samples: 50_000_000,
            max_memory_bytes: 2 * 1024 * 1024 * 1024,
            max_distribution_states: 200_000,
        }
    }
}

impl ResourceLimitsV1 {
    fn validate(&self) -> Result<(), ContractError> {
        if self.max_total_samples == 0
            || self.max_memory_bytes == 0
            || self.max_distribution_states < 8
        {
            return Err(ContractError::InvalidResourceLimit);
        }
        Ok(())
    }
}

#[derive(Debug, Clone, Deserialize, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SimulationInputV1 {
    pub schema: String,
    pub run_id: String,
    pub modulation: ModulationV1,
    pub pattern: PatternV1,
    pub timebase: TimebaseV1,
    pub channel: ChannelInputV1,
    pub tx: TxConfigV1,
    pub rx: RxConfigV1,
    pub analysis: AnalysisConfigV1,
    pub limits: ResourceLimitsV1,
    pub external_models: Vec<ExternalModelRefV1>,
    /// Compatibility-only data. A Rust stage must promote each consumed key to
    /// a typed field before this map can be removed in a future schema version.
    #[serde(default)]
    pub legacy_options: BTreeMap<String, serde_json::Value>,
}

impl SimulationInputV1 {
    pub fn validate(&self) -> Result<(), ContractError> {
        if self.schema != SIMULATION_SCHEMA_V1 {
            return Err(ContractError::UnsupportedSchema(self.schema.clone()));
        }
        if self.run_id.trim().is_empty() {
            return Err(ContractError::InvalidRunId);
        }
        self.pattern.validate()?;
        self.timebase.validate()?;
        self.channel.validate()?;
        self.tx.validate()?;
        if self
            .tx
            .periodic_noise
            .as_ref()
            .is_some_and(|periodic_noise| {
                periodic_noise.frequency.0 > 0.5 / self.timebase.sample_interval.0
            })
        {
            return Err(ContractError::InvalidPeriodicNoise);
        }
        self.rx.validate()?;
        self.analysis.validate()?;
        self.limits.validate()?;
        for model in &self.external_models {
            model.validate()?;
        }
        Ok(())
    }
}
