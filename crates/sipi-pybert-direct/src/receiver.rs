//! Receiver timing-recovery primitives with explicit, bounded state.

use thiserror::Error;

#[derive(Debug, Error, PartialEq)]
pub enum CdrError {
    #[error("CDR timing parameters must be finite and delta_t/ui must be greater than zero")]
    InvalidTiming,
    #[error("CDR lock windows must be greater than zero")]
    InvalidLockWindow,
    #[error("CDR samples must contain exactly three finite values")]
    InvalidSamples,
}

#[derive(Debug, Error, PartialEq)]
pub enum DfeError {
    #[error("DFE configuration values must be finite and n_ave must be greater than zero")]
    InvalidConfiguration,
    #[error("DFE limits must have one finite lower/upper pair per tap")]
    InvalidLimits,
    #[error("DFE modulation must be NRZ (0), DuoBinary (1), or PAM4 (2)")]
    InvalidModulation,
}

#[derive(Debug, Error, PartialEq)]
pub enum DfeRunError {
    #[error("sample times and signal must have equal non-empty finite lengths")]
    InvalidInput,
    #[error("sample times must be monotonically non-decreasing")]
    NonMonotonicTime,
    #[error("external clock times must contain at least two finite, non-decreasing values")]
    InvalidExternalClocks,
    #[error("non-ideal DFE bandwidth/options are invalid for the sampling rate")]
    InvalidOptions,
    #[error(transparent)]
    Cdr(#[from] CdrError),
    #[error(transparent)]
    Dfe(#[from] DfeError),
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DfeModulation {
    Nrz,
    DuoBinary,
    Pam4,
}

impl TryFrom<u8> for DfeModulation {
    type Error = DfeError;

    fn try_from(value: u8) -> Result<Self, Self::Error> {
        match value {
            0 => Ok(Self::Nrz),
            1 => Ok(Self::DuoBinary),
            2 => Ok(Self::Pam4),
            _ => Err(DfeError::InvalidModulation),
        }
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct DfeConfig {
    pub n_taps: usize,
    pub gain: f64,
    pub decision_scaler: f64,
    pub modulation: DfeModulation,
    pub n_ave: usize,
    pub limits: Option<Vec<(f64, f64)>>,
    pub initial_weights: Option<Vec<f64>>,
    pub initial_values: Option<Vec<f64>>,
    pub initial_corrections: Option<Vec<f64>>,
    pub training_start_ui: Option<usize>,
    pub training_end_ui: Option<usize>,
}

impl DfeConfig {
    pub fn validate(&self) -> Result<(), DfeError> {
        if !self.gain.is_finite() || !self.decision_scaler.is_finite() || self.n_ave == 0 {
            return Err(DfeError::InvalidConfiguration);
        }
        if let Some(limits) = &self.limits
            && (limits.len() != self.n_taps
                || limits.iter().any(|(lower, upper)| {
                    !lower.is_finite() || !upper.is_finite() || lower > upper
                }))
        {
            return Err(DfeError::InvalidLimits);
        }
        if let Some(weights) = &self.initial_weights
            && (weights.len() != self.n_taps || weights.iter().any(|w| !w.is_finite()))
        {
            return Err(DfeError::InvalidConfiguration);
        }
        if let Some(values) = &self.initial_values
            && (values.len() != self.n_taps || values.iter().any(|v| !v.is_finite()))
        {
            return Err(DfeError::InvalidConfiguration);
        }
        if let Some(corrs) = &self.initial_corrections
            && (corrs.len() != self.n_taps || corrs.iter().any(|c| !c.is_finite()))
        {
            return Err(DfeError::InvalidConfiguration);
        }
        if let (Some(start), Some(end)) = (self.training_start_ui, self.training_end_ui)
            && start > end
        {
            return Err(DfeError::InvalidConfiguration);
        }
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct DfeDecision {
    pub decision: f64,
    pub bits: Vec<i32>,
}

/// Pure feedback-tap and slicer state; sample filtering and CDR scheduling stay separate.
#[derive(Debug, Clone)]
pub struct DfeState {
    config: DfeConfig,
    tap_weights: Vec<f64>,
    tap_values: Vec<f64>,
    corrections: Vec<f64>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct DfeRunResult {
    pub dfe_out: Vec<f64>,
    pub tap_weights: Vec<Vec<f64>>,
    pub ui_estimates: Vec<f64>,
    pub clocks: Vec<f64>,
    pub lockeds: Vec<bool>,
    pub clock_times: Vec<f64>,
    pub bits: Vec<i32>,
    pub signal_samples: Vec<f64>,
    pub decisions: Vec<f64>,
    pub decision_scalers: Vec<f64>,
    pub slicer_inputs: Vec<f64>,
    pub errors: Vec<f64>,
    pub update_enableds: Vec<bool>,
    pub bank_updateds: Vec<bool>,
    pub event_corrections: Vec<Vec<f64>>,
}
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct DfeRunOptions {
    pub samples_per_ui: usize,
    pub bandwidth_hz: f64,
    pub ideal: bool,
    pub use_agc: bool,
    pub agc_n_ave: usize,
}

/// Run the ideal summing-node form of PyBERT's DFE/CDR loop.
///
/// The non-ideal IIR summing filter and AGC are deliberately separate stages;
/// this stage freezes the timing schedule, slicer semantics, and tap update
/// ordering before those optional behaviors are introduced.
pub fn run_ideal_dfe(
    sample_times: &[f64],
    signal: &[f64],
    dfe_config: DfeConfig,
    cdr_config: CdrConfig,
) -> Result<DfeRunResult, DfeRunError> {
    run_dfe(
        sample_times,
        signal,
        dfe_config,
        cdr_config,
        DfeRunOptions {
            samples_per_ui: 1,
            bandwidth_hz: 0.0,
            ideal: true,
            use_agc: false,
            agc_n_ave: 1,
        },
    )
}

/// Run PyBERT's DFE/CDR loop, including its optional Butterworth summing
/// node and AGC state. `run_ideal_dfe()` remains the narrower parity API for
/// callers that do not need those optional behaviors.
pub fn run_dfe(
    sample_times: &[f64],
    signal: &[f64],
    dfe_config: DfeConfig,
    cdr_config: CdrConfig,
    options: DfeRunOptions,
) -> Result<DfeRunResult, DfeRunError> {
    if sample_times.is_empty()
        || sample_times.len() != signal.len()
        || sample_times.iter().any(|value| !value.is_finite())
        || signal.iter().any(|value| !value.is_finite())
    {
        return Err(DfeRunError::InvalidInput);
    }
    if sample_times.windows(2).any(|window| window[1] < window[0]) {
        return Err(DfeRunError::NonMonotonicTime);
    }
    if options.agc_n_ave == 0
        || (!options.ideal
            && (options.samples_per_ui == 0
                || !options.bandwidth_hz.is_finite()
                || options.bandwidth_hz <= 0.0
                || options.bandwidth_hz >= options.samples_per_ui as f64 / (2.0 * cdr_config.ui)))
    {
        return Err(DfeRunError::InvalidOptions);
    }

    let mut dfe = DfeState::new(dfe_config)?;
    let mut cdr = CdrState::new(cdr_config)?;
    let mut summing_filter = if options.ideal {
        None
    } else {
        Some(Butterworth2::lowpass(
            options.bandwidth_hz,
            options.samples_per_ui as f64 / cdr_config.ui,
        )?)
    };
    let mut ui = cdr.ui();
    let mut decision_scaler = dfe.decision_scaler();
    let mut clock_count = 0_usize;
    let mut filter_out = 0.0;
    let mut next_filter_out = 0.0;
    let mut last_clock_sample = 0.0;
    let mut next_boundary_time = 0.0;
    let mut next_clock_time = ui / 2.0;
    let mut locked = false;

    let mut dfe_out = Vec::with_capacity(signal.len());
    let mut tap_weights = vec![dfe.tap_weights().to_vec()];
    let mut ui_estimates = Vec::with_capacity(signal.len());
    let mut clocks = vec![0.0; signal.len()];
    let mut lockeds = Vec::with_capacity(signal.len());
    let mut clock_times = vec![next_clock_time];
    let mut bits = Vec::new();
    let mut signal_samples = Vec::new();
    let mut decisions = Vec::new();
    let mut boundary_sample = 0.0;
    let mut slicer_samples = vec![0.0; options.agc_n_ave];
    let mut average_samples = vec![0.0; options.agc_n_ave];
    let mut slicer_sample_count = 0_usize;
    let mut average_sample_count = 0_usize;
    let mut decision_scalers = vec![decision_scaler];
    let mut slicer_inputs = Vec::new();
    let mut errors = Vec::new();
    let mut update_enableds = Vec::new();
    let mut bank_updateds = Vec::new();
    let mut event_corrections = Vec::new();
    for (index, (&time, &input)) in sample_times.iter().zip(signal).enumerate() {
        let sum_out = summing_filter
            .as_mut()
            .map_or(input - filter_out, |filter| filter.step(input - filter_out));
        dfe_out.push(sum_out);
        if time_reached(time, next_boundary_time) {
            boundary_sample = sum_out;
            filter_out = next_filter_out;
            next_boundary_time += ui;
        }
        if time_reached(time, next_clock_time) {
            clock_count += 1;
            clocks[index] = 1.0;
            let mut cdr_samples = [last_clock_sample, boundary_sample, sum_out];
            if dfe.config.modulation == DfeModulation::DuoBinary {
                let threshold = if cdr_samples.iter().sum::<f64>() / 3.0 < 0.0 {
                    -decision_scaler / 2.0
                } else {
                    decision_scaler / 2.0
                };
                cdr_samples
                    .iter_mut()
                    .for_each(|sample| *sample -= threshold);
            }
            (ui, locked) = cdr.adapt(&cdr_samples)?;
            let decision = dfe.decide(sum_out)?;
            bits.extend(decision.bits.iter().copied());
            signal_samples.push(sum_out);
            decisions.push(decision.decision);
            let slicer_output = decision.decision * decision_scaler;
            let error = sum_out - slicer_output;
            let in_training = dfe.config.training_start_ui.map_or(true, |start| clock_count >= start)
                && dfe.config.training_end_ui.map_or(true, |end| clock_count < end);
            let update = locked && in_training && clock_count.is_multiple_of(dfe.config.n_ave);
            next_filter_out = dfe.step(slicer_output, if locked && in_training { error } else { 0.0 }, update)?;
            tap_weights.push(dfe.tap_weights().to_vec());
            slicer_inputs.push(sum_out);
            errors.push(error);
            update_enableds.push(locked && in_training);
            bank_updateds.push(update);
            event_corrections.push(dfe.corrections().to_vec());
            last_clock_sample = sum_out;
            next_boundary_time = next_clock_time + ui / 2.0;
            next_clock_time += ui;
            clock_times.push(next_clock_time);
            if options.use_agc {
                shift_append(&mut slicer_samples, sum_out);
                slicer_sample_count += 1;
                if slicer_sample_count >= options.agc_n_ave {
                    let average_slicer_sample =
                        slicer_samples.iter().map(|value| value.abs()).sum::<f64>()
                            / options.agc_n_ave as f64;
                    shift_append(&mut average_samples, average_slicer_sample);
                    average_sample_count += 1;
                    if average_sample_count >= options.agc_n_ave {
                        let average_average_sample =
                            average_samples.iter().sum::<f64>() / options.agc_n_ave as f64;
                        decision_scaler = match dfe.config.modulation {
                            DfeModulation::Nrz => average_average_sample,
                            DfeModulation::DuoBinary | DfeModulation::Pam4 => {
                                1.5 * average_average_sample
                            }
                        };
                        dfe.set_decision_scaler(decision_scaler)?;
                        decision_scalers.push(decision_scaler);
                    }
                }
            }
        }
        ui_estimates.push(ui);
        lockeds.push(locked);
    }

    Ok(DfeRunResult {
        dfe_out,
        tap_weights,
        ui_estimates,
        clocks,
        lockeds,
        clock_times,
        bits,
        signal_samples,
        decisions,
        decision_scalers,
        slicer_inputs,
        errors,
        update_enableds,
        bank_updateds,
        event_corrections,
    })
}

/// Run the slicer using clock edges supplied by an external AMI GetWave model.
///
/// IBIS-AMI clock times identify *edges*, while PyBERT samples each symbol half
/// a UI later.  The external model owns timing recovery in this mode, so this
/// deliberately uses a zero-tap, zero-gain DFE and does not run the native CDR
/// or adapt feedback taps.
pub fn run_dfe_with_external_clocks(
    sample_times: &[f64],
    signal: &[f64],
    clock_times: &[f64],
    ui: f64,
    decision_scaler: f64,
    modulation: DfeModulation,
    ignore_bits: usize,
) -> Result<DfeRunResult, DfeRunError> {
    if sample_times.is_empty()
        || sample_times.len() != signal.len()
        || sample_times.iter().any(|value| !value.is_finite())
        || signal.iter().any(|value| !value.is_finite())
    {
        return Err(DfeRunError::InvalidInput);
    }
    if sample_times.windows(2).any(|window| window[1] < window[0]) {
        return Err(DfeRunError::NonMonotonicTime);
    }
    if clock_times.len() < 2
        || clock_times.iter().any(|value| !value.is_finite())
        || clock_times
            .windows(2)
            .filter(|window| window[0] >= 0.0 && window[1] >= 0.0)
            .any(|window| window[1] < window[0])
        || !ui.is_finite()
        || ui <= 0.0
    {
        return Err(DfeRunError::InvalidExternalClocks);
    }

    let dfe_config = DfeConfig {
        n_taps: 0,
        gain: 0.0,
        decision_scaler,
        modulation,
        n_ave: 1,
        limits: None,
        initial_weights: None,
        initial_values: None,
        initial_corrections: None,
        training_start_ui: None,
        training_end_ui: None,
    };
    let dfe = DfeState::new(dfe_config)?;
    let mut sample_index = 0_usize;
    let mut ui_estimates = Vec::with_capacity(sample_times.len());
    let mut lockeds = Vec::with_capacity(sample_times.len());
    let mut clocks = vec![0.0; sample_times.len()];
    let mut bits = Vec::new();
    let mut signal_samples = Vec::new();
    let mut decisions = Vec::new();

    for (clock_index, window) in clock_times.windows(2).enumerate() {
        let clock_time = window[0];
        if clock_time < 0.0 {
            break;
        }
        let next_clock_time = window[1];
        if next_clock_time < 0.0 || next_clock_time < clock_time {
            return Err(DfeRunError::InvalidExternalClocks);
        }
        let sample_time = clock_time + ui / 2.0;
        let ui_estimate = next_clock_time - clock_time;
        let locked = clock_index >= ignore_bits;
        while sample_index < sample_times.len() && sample_times[sample_index] < sample_time {
            ui_estimates.push(ui_estimate);
            lockeds.push(locked);
            sample_index += 1;
        }
        if sample_index >= sample_times.len() {
            break;
        }
        let input = signal[sample_index];
        let decision = dfe.decide(input)?;
        bits.extend(decision.bits);
        signal_samples.push(input);
        decisions.push(decision.decision);
        clocks[sample_index] = 1.0;
    }

    Ok(DfeRunResult {
        dfe_out: signal.to_vec(),
        tap_weights: Vec::new(),
        ui_estimates,
        clocks,
        lockeds,
        clock_times: clock_times.to_vec(),
        bits,
        signal_samples,
        decisions,
        decision_scalers: Vec::new(),
        slicer_inputs: Vec::new(),
        errors: Vec::new(),
        update_enableds: Vec::new(),
        bank_updateds: Vec::new(),
        event_corrections: Vec::new(),
    })
}

impl DfeState {
    pub fn new(config: DfeConfig) -> Result<Self, DfeError> {
        config.validate()?;
        let tap_weights = config.initial_weights.clone().unwrap_or_else(|| vec![0.0; config.n_taps]);
        let tap_values = config.initial_values.clone().unwrap_or_else(|| vec![0.0; config.n_taps]);
        let corrections = config.initial_corrections.clone().unwrap_or_else(|| vec![0.0; config.n_taps]);
        Ok(Self {
            tap_weights,
            tap_values,
            corrections,
            config,
        })
    }

    pub fn corrections(&self) -> &[f64] {
        &self.corrections
    }

    pub fn tap_weights(&self) -> &[f64] {
        &self.tap_weights
    }

    pub fn decision_scaler(&self) -> f64 {
        self.config.decision_scaler
    }

    pub fn set_decision_scaler(&mut self, decision_scaler: f64) -> Result<(), DfeError> {
        if !decision_scaler.is_finite() {
            return Err(DfeError::InvalidConfiguration);
        }
        self.config.decision_scaler = decision_scaler;
        Ok(())
    }

    pub fn decide(&self, sample: f64) -> Result<DfeDecision, DfeError> {
        if !sample.is_finite() {
            return Err(DfeError::InvalidConfiguration);
        }
        let scaler = self.config.decision_scaler;
        let decision = match self.config.modulation {
            DfeModulation::Nrz => DfeDecision {
                decision: pybert_sign(sample),
                bits: vec![i32::from(sample > 0.0)],
            },
            DfeModulation::DuoBinary => {
                let lower = -scaler / 2.0;
                let upper = scaler / 2.0;
                if (sample > lower) ^ (sample > upper) {
                    DfeDecision {
                        decision: 0.0,
                        bits: vec![1],
                    }
                } else {
                    DfeDecision {
                        decision: pybert_sign(sample),
                        bits: vec![0],
                    }
                }
            }
            DfeModulation::Pam4 => {
                if sample > scaler * 2.0 / 3.0 {
                    DfeDecision {
                        decision: 1.0,
                        bits: vec![1, 0],
                    }
                } else if sample > 0.0 {
                    DfeDecision {
                        decision: 1.0 / 3.0,
                        bits: vec![1, 1],
                    }
                } else if sample > -scaler * 2.0 / 3.0 {
                    DfeDecision {
                        decision: -1.0 / 3.0,
                        bits: vec![0, 1],
                    }
                } else {
                    DfeDecision {
                        decision: -1.0,
                        bits: vec![0, 0],
                    }
                }
            }
        };
        Ok(decision)
    }

    /// Update tap adaptation and return the delayed feedback contribution.
    pub fn step(&mut self, decision: f64, error: f64, update: bool) -> Result<f64, DfeError> {
        if !decision.is_finite() || !error.is_finite() {
            return Err(DfeError::InvalidConfiguration);
        }
        for ((correction, tap_value), _) in self
            .corrections
            .iter_mut()
            .zip(&self.tap_values)
            .zip(&self.tap_weights)
        {
            *correction += tap_value * error * self.config.gain;
        }
        if update {
            for (index, weight) in self.tap_weights.iter_mut().enumerate() {
                let candidate = *weight + self.corrections[index] / self.config.n_ave as f64;
                *weight = self.config.limits.as_ref().map_or(candidate, |limits| {
                    candidate.clamp(limits[index].0, limits[index].1)
                });
            }
            self.corrections.fill(0.0);
        }
        if !self.tap_values.is_empty() {
            self.tap_values.rotate_right(1);
            self.tap_values[0] = decision;
        }
        Ok(self
            .tap_weights
            .iter()
            .zip(&self.tap_values)
            .map(|(weight, value)| weight * value)
            .sum())
    }
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct CdrConfig {
    pub delta_t: f64,
    pub alpha: f64,
    pub ui: f64,
    pub n_lock_ave: usize,
    pub rel_lock_tol: f64,
    pub lock_sustain: usize,
}

impl CdrConfig {
    pub fn validate(self) -> Result<(), CdrError> {
        if !self.delta_t.is_finite()
            || self.delta_t <= 0.0
            || !self.alpha.is_finite()
            || !self.ui.is_finite()
            || self.ui <= 0.0
            || !self.rel_lock_tol.is_finite()
            || self.rel_lock_tol < 0.0
        {
            return Err(CdrError::InvalidTiming);
        }
        if self.n_lock_ave == 0 || self.lock_sustain == 0 {
            return Err(CdrError::InvalidLockWindow);
        }
        Ok(())
    }
}

/// Stateful PyBERT-compatible bang-bang CDR adaptation kernel.
#[derive(Debug, Clone)]
pub struct CdrState {
    config: CdrConfig,
    ui: f64,
    locked: bool,
    integral_corrections: Vec<f64>,
    proportional_corrections: Vec<f64>,
    lockeds: Vec<bool>,
}

impl CdrState {
    pub fn new(config: CdrConfig) -> Result<Self, CdrError> {
        config.validate()?;
        Ok(Self {
            config,
            ui: config.ui,
            locked: false,
            integral_corrections: vec![0.0],
            proportional_corrections: Vec::new(),
            lockeds: Vec::new(),
        })
    }

    pub fn ui(&self) -> f64 {
        self.ui
    }

    pub fn locked(&self) -> bool {
        self.locked
    }

    /// Adapt the UI from samples at the prior clock, boundary, and current clock.
    pub fn adapt(&mut self, samples: &[f64]) -> Result<(f64, bool), CdrError> {
        if samples.len() != 3 || samples.iter().any(|value| !value.is_finite()) {
            return Err(CdrError::InvalidSamples);
        }

        let signs = [
            pybert_sign(samples[0]),
            pybert_sign(samples[1]),
            pybert_sign(samples[2]),
        ];
        let proportional_correction = if signs[0] == signs[2] {
            0.0
        } else if signs[0] == signs[1] {
            self.config.delta_t
        } else {
            -self.config.delta_t
        };
        let integral_correction = self.integral_corrections.last().copied().unwrap_or(0.0)
            + self.config.alpha * proportional_correction;
        self.ui = self.config.ui + integral_correction + proportional_correction;

        push_bounded(
            &mut self.integral_corrections,
            integral_correction,
            self.config.n_lock_ave,
        );
        push_bounded(
            &mut self.proportional_corrections,
            proportional_correction,
            self.config.n_lock_ave,
        );

        if self.proportional_corrections.len() == self.config.n_lock_ave {
            let average =
                self.proportional_corrections.iter().sum::<f64>() / self.config.n_lock_ave as f64;
            let variance = self
                .integral_corrections
                .iter()
                .map(|correction| correction * correction)
                .sum::<f64>()
                / self.config.n_lock_ave as f64;
            let lock = (average / self.config.delta_t).abs() < self.config.rel_lock_tol
                && (variance / self.config.delta_t) < self.config.rel_lock_tol;
            push_bounded(&mut self.lockeds, lock, self.config.lock_sustain);
            let locked_count = self.lockeds.iter().filter(|&&value| value).count();
            if self.locked {
                if (locked_count as f64) < 0.2 * self.config.lock_sustain as f64 {
                    self.locked = false;
                }
            } else if locked_count as f64 > 0.8 * self.config.lock_sustain as f64 {
                self.locked = true;
            }
        }

        Ok((self.ui, self.locked))
    }
}

fn push_bounded<T>(values: &mut Vec<T>, value: T, limit: usize) {
    values.push(value);
    if values.len() > limit {
        values.remove(0);
    }
}

fn pybert_sign(value: f64) -> f64 {
    if value > 0.0 {
        1.0
    } else if value < 0.0 {
        -1.0
    } else {
        0.0
    }
}

fn time_reached(time: f64, target: f64) -> bool {
    time >= target
}

#[derive(Debug, Clone)]
struct Butterworth2 {
    b: [f64; 3],
    a: [f64; 3],
    xs: [f64; 2],
    ys: [f64; 2],
}

impl Butterworth2 {
    fn lowpass(bandwidth_hz: f64, sample_rate_hz: f64) -> Result<Self, DfeRunError> {
        let normalized_frequency = bandwidth_hz / (sample_rate_hz / 2.0);
        if !normalized_frequency.is_finite() || !(0.0..1.0).contains(&normalized_frequency) {
            return Err(DfeRunError::InvalidOptions);
        }
        let k = (std::f64::consts::PI * normalized_frequency / 2.0).tan();
        let normalization = 1.0 / (1.0 + std::f64::consts::SQRT_2 * k + k * k);
        Ok(Self {
            b: [
                k * k * normalization,
                2.0 * k * k * normalization,
                k * k * normalization,
            ],
            a: [
                1.0,
                2.0 * (k * k - 1.0) * normalization,
                (1.0 - std::f64::consts::SQRT_2 * k + k * k) * normalization,
            ],
            xs: [0.0; 2],
            ys: [0.0; 2],
        })
    }

    fn step(&mut self, input: f64) -> f64 {
        let output = self.b[0] * input + self.b[1] * self.xs[0] + self.b[2] * self.xs[1]
            - self.a[1] * self.ys[0]
            - self.a[2] * self.ys[1];
        self.xs.rotate_right(1);
        self.xs[0] = input;
        self.ys.rotate_right(1);
        self.ys[0] = output;
        output
    }
}

fn shift_append(values: &mut [f64], value: f64) {
    values.rotate_left(1);
    if let Some(last) = values.last_mut() {
        *last = value;
    }
}
