//! Bounded native execution for the fully typed, already-migrated v1 subset.
//!
//! This intentionally does not emulate the legacy `PyBERT` object. Requests
//! that require AMI are rejected before allocation instead of silently
//! changing physics. Native jitter metrics consume a typed trailing eye window
//! when the request supplies one.

use std::{
    collections::BTreeMap,
    sync::{
        Arc,
        atomic::{AtomicBool, Ordering},
    },
};

use num_complex::Complex;
use rustfft::FftPlanner;
use thiserror::Error;

use crate::{
    BathtubError, BerError, CdrConfig, ChannelError, ChannelInputV1, ContractError, CrossingError,
    CtleConfig, DfeConfig, DfeModulation, DfeRunError, DfeRunOptions, EngineCapabilitiesV1,
    EqualizationError, FecDecodeError, FecEncoder, IsiDecodeConfig, IsiDecodeError,
    LinearLinkError, MetallicLineChannelV1, MetallicLineConfig, ModulationV1, Pam4EyeError, PatternError,
    PatternV1, PeriodicNoiseV1, RunEventV1, RunStageV1, SIMULATION_SCHEMA_V1, SignalError,
    SimulationInputV1, SimulationOutputV1, StatisticalEyeError, StatisticalEyeInputV1,
    SymbolModulation, TerminationConfig, assemble_tie_track, calculate_ber,
    calculate_data_dependent_jitter, calculate_dual_dirac_jitter, calculate_metallic_line,
    calculate_spectral_jitter, calculate_statistical_contours, calculate_statistical_eye,
    causal_convolve_truncated, convolve_truncated, ctle_frequency_response, ctle_impulse_response,
    decode_fec, decode_isi, ffe_impulse_response, find_crossings, forward_real_spectrum,
    generate_prbs_bits, inverse_real_spectrum, make_bathtub, modulate_bits, pulse_response,
    run_dfe, run_linear_link_with_rx_filter, sparse_tapped_convolve_truncated, step_response,
};

#[derive(Debug, Error, PartialEq)]
pub enum NativeSimulationError {
    #[error("native simulation was cancelled")]
    Cancelled,
    #[error(transparent)]
    Contract(#[from] ContractError),
    #[error("native simulation v1 supports deterministic PRBS patterns only")]
    UnsupportedPattern,
    #[error("native simulation v1 requires a host-independent impulse-response channel")]
    UnsupportedChannel,
    #[error("native simulation v1 does not support external models")]
    UnsupportedExternalModel,
    #[error("native statistical-eye analysis currently supports NRZ only")]
    UnsupportedStatisticalEyeModulation,
    #[error("statistical-eye analysis requires data rate and sampled UI to agree")]
    InconsistentTimebase,
    #[error("native simulation v1 requires typed DFE controls when dfeTaps is nonzero")]
    MissingDfeConfiguration,
    #[error("native simulation v1 requires typed CTLE controls when native CTLE is enabled")]
    MissingCtleConfiguration,
    #[error("native simulation v1 requires typed Viterbi controls when Viterbi is enabled")]
    MissingViterbiConfiguration,
    #[error("native Viterbi requires the typed DFE/CDR stage")]
    MissingViterbiDfe,
    #[error("native Viterbi pulse response is too short for the requested trellis depth")]
    ViterbiPulseTooShort,
    #[error("native FEC Viterbi requires PAM-4 modulation")]
    UnsupportedFecModulation,
    #[error("native FEC Viterbi requires DFE output in complete binary pairs")]
    IncompleteFecObservations,
    #[error("native simulation v1 does not consume legacy options")]
    UnsupportedLegacyOptions,
    #[error("native simulation waveform exceeds the declared resource limits")]
    ResourceLimitExceeded,
    #[error("additive noise sample count must equal the native receiver waveform length")]
    AdditiveNoiseLengthMismatch,
    #[error("legacy stage spectra exceed the sampled Nyquist frequency")]
    LegacyStageFrequencyOutOfRange,
    #[error(transparent)]
    Pattern(#[from] PatternError),
    #[error(transparent)]
    Link(#[from] LinearLinkError),
    #[error(transparent)]
    Signal(#[from] SignalError),
    #[error(transparent)]
    StatisticalEye(#[from] StatisticalEyeError),
    #[error(transparent)]
    Dfe(#[from] DfeRunError),
    #[error(transparent)]
    Channel(#[from] ChannelError),
    #[error(transparent)]
    Equalization(#[from] EqualizationError),
    #[error(transparent)]
    Isi(#[from] IsiDecodeError),
    #[error(transparent)]
    Fec(#[from] FecDecodeError),
    #[error(transparent)]
    Ber(#[from] BerError),
    #[error(transparent)]
    Crossing(#[from] CrossingError),
    #[error(transparent)]
    Bathtub(#[from] BathtubError),
    #[error(transparent)]
    Pam4Eye(#[from] Pam4EyeError),
}

/// Thread-safe cancellation handle owned by the host adapter.
///
/// The v1 core observes cancellation at deterministic stage boundaries. It
/// does not borrow Python state, so a PyO3 caller can release the GIL while a
/// separate host thread requests cancellation.
#[derive(Clone, Debug, Default)]
pub struct NativeCancellationToken {
    cancelled: Arc<AtomicBool>,
}

impl NativeCancellationToken {
    pub fn cancel(&self) {
        self.cancelled.store(true, Ordering::Release);
    }

    pub fn is_cancelled(&self) -> bool {
        self.cancelled.load(Ordering::Acquire)
    }

    fn check(&self) -> Result<(), NativeSimulationError> {
        if self.is_cancelled() {
            Err(NativeSimulationError::Cancelled)
        } else {
            Ok(())
        }
    }
}

/// Execute the deterministic linear subset of `SimulationInputV1`.
///
/// The typed channel stores a continuous impulse in V/s.  It is converted to
/// its sampled V/V convolution kernel using the declared sample interval at
/// this boundary, so the core never guesses time units from a raw array.
pub fn simulate_native_v1(
    input: &SimulationInputV1,
) -> Result<SimulationOutputV1, NativeSimulationError> {
    simulate_native_v1_with_cancellation(input, &NativeCancellationToken::default())
}

/// Execute the typed v1 subset while observing a host-owned cancellation token.
pub fn simulate_native_v1_with_cancellation(
    input: &SimulationInputV1,
    cancellation: &NativeCancellationToken,
) -> Result<SimulationOutputV1, NativeSimulationError> {
    simulate_native_v1_inner(input, cancellation, input.tx.amplitude.0)
}

/// Execute the legacy adapter's existing native path with an explicitly
/// validated PyBERT crossing amplitude. The public typed v1 path remains
/// pinned to its native `tx.amplitude` crossing semantics.
pub(crate) fn simulate_native_v1_with_legacy_crossing_amplitude(
    input: &SimulationInputV1,
    cancellation: &NativeCancellationToken,
    crossing_amplitude_v: f64,
) -> Result<SimulationOutputV1, NativeSimulationError> {
    let dfe = input
        .rx
        .dfe
        .as_ref()
        .ok_or(NativeSimulationError::Contract(ContractError::InvalidDfe))?;
    if !crate::Volts(crossing_amplitude_v).is_finite_positive()
        || !dfe.decision_scaler.is_finite_positive()
        || dfe.decision_scaler.0.to_bits() != crossing_amplitude_v.to_bits()
    {
        return Err(NativeSimulationError::Contract(ContractError::InvalidDfe));
    }
    simulate_native_v1_inner(input, cancellation, crossing_amplitude_v)
}

fn simulate_native_v1_inner(
    input: &SimulationInputV1,
    cancellation: &NativeCancellationToken,
    crossing_amplitude_v: f64,
) -> Result<SimulationOutputV1, NativeSimulationError> {
    cancellation.check()?;
    input.validate()?;
    cancellation.check()?;
    if !input.external_models.is_empty() {
        return Err(NativeSimulationError::UnsupportedExternalModel);
    }
    if !input.legacy_options.is_empty() {
        return Err(NativeSimulationError::UnsupportedLegacyOptions);
    }
    if input.rx.dfe_taps != 0 && input.rx.dfe.is_none() {
        return Err(NativeSimulationError::MissingDfeConfiguration);
    }
    if input.rx.native_ctle_enabled && input.rx.ctle.is_none() {
        return Err(NativeSimulationError::MissingCtleConfiguration);
    }
    if input.rx.viterbi_enabled && input.rx.viterbi.is_none() {
        return Err(NativeSimulationError::MissingViterbiConfiguration);
    }
    if input.rx.viterbi_enabled && input.rx.dfe.is_none() {
        return Err(NativeSimulationError::MissingViterbiDfe);
    }
    if input.rx.viterbi.as_ref().is_some_and(|viterbi| viterbi.fec)
        && !matches!(input.modulation, ModulationV1::Pam4)
    {
        return Err(NativeSimulationError::UnsupportedFecModulation);
    }
    let channel_sample_interval = match &input.channel {
        ChannelInputV1::ImpulseResponse(response) => response.sample_interval,
        ChannelInputV1::MetallicLine(channel) => channel.sample_interval,
        ChannelInputV1::Touchstone(_) | ChannelInputV1::ExternalModel(_) => {
            return Err(NativeSimulationError::UnsupportedChannel);
        }
    };
    if channel_sample_interval != input.timebase.sample_interval {
        return Err(NativeSimulationError::UnsupportedChannel);
    }
    let bit_count = usize::try_from(input.timebase.nbits)
        .map_err(|_| NativeSimulationError::ResourceLimitExceeded)?;
    let samples_per_ui = input.timebase.samples_per_ui as usize;
    let prbs_order = match &input.pattern {
        PatternV1::Prbs { order, .. } => Some(*order),
        PatternV1::ExplicitBits { .. } => None,
    };
    let bits = match &input.pattern {
        PatternV1::Prbs { order, seed } => generate_prbs_bits(*order, *seed, bit_count)?,
        PatternV1::ExplicitBits { bits, .. } if !bits.is_empty() => {
            bits.iter().map(|&bit| i32::from(bit)).collect()
        }
        PatternV1::ExplicitBits { .. } => return Err(NativeSimulationError::UnsupportedPattern),
    };
    let modulation = match input.modulation {
        ModulationV1::Nrz => SymbolModulation::Nrz,
        ModulationV1::Pam4 => SymbolModulation::Pam4,
        ModulationV1::DuoBinary => SymbolModulation::DuoBinary,
    };
    let fec_encoded_bits = input
        .rx
        .viterbi
        .as_ref()
        .filter(|viterbi| input.rx.viterbi_enabled && viterbi.fec)
        .map(|_| {
            FecEncoder::new([0; 3])
                .encode(&bits)
                .into_iter()
                .flat_map(|(first, second)| [first, second])
                .collect::<Vec<_>>()
        });
    let symbols = modulate_bits(
        fec_encoded_bits.as_deref().unwrap_or(&bits),
        modulation,
        input.tx.amplitude.0,
    )?;
    cancellation.check()?;
    let sample_count = symbols
        .len()
        .checked_mul(samples_per_ui)
        .ok_or(NativeSimulationError::ResourceLimitExceeded)?;
    let max_total_samples = usize::try_from(input.limits.max_total_samples)
        .map_err(|_| NativeSimulationError::ResourceLimitExceeded)?;
    let legacy_frequency_telemetry_bytes = match &input.channel {
        ChannelInputV1::MetallicLine(channel) => {
            match (channel.frequency_step_hz, channel.frequency_max_hz) {
                (Some(step), Some(maximum)) => {
                    let (frequency_intervals, effective_maximum) =
                        legacy_arange_grid(step.0, maximum.0, max_total_samples)?;
                    let stage_fft_size = validate_legacy_stage_frequency_grid(
                        step.0,
                        effective_maximum,
                        input.timebase.sample_interval.0,
                        max_total_samples,
                    )?;
                    let frequency_bins = frequency_intervals
                        .checked_add(1)
                        .ok_or(NativeSimulationError::ResourceLimitExceeded)?;
                    legacy_frequency_telemetry_resource_bytes(stage_fft_size, frequency_bins)?
                }
                (None, None) => 0,
                _ => return Err(NativeSimulationError::UnsupportedChannel),
            }
        }
        ChannelInputV1::ImpulseResponse(_)
        | ChannelInputV1::Touchstone(_)
        | ChannelInputV1::ExternalModel(_) => 0,
    };
    // Bound both materialized result vectors and the largest per-stage
    // telemetry. DFE tap history can reach one row per sample, so count every
    // configured tap as a full waveform rather than underestimating it.
    let output_vector_count = 8_usize
        .checked_add(usize::from(input.tx.additive_noise.is_some()))
        .and_then(|count| count.checked_add(usize::from(input.tx.periodic_noise.is_some()) * 2))
        .and_then(|count| {
            count.checked_add(
                input
                    .rx
                    .dfe
                    .as_ref()
                    .map_or(0, |_| 9 + input.rx.dfe_taps as usize + 4),
            )
        })
        .and_then(|count| count.checked_add(usize::from(input.rx.viterbi_enabled) * 3))
        .and_then(|count| {
            count.checked_add(
                input
                    .analysis
                    .statistical_eye
                    .as_ref()
                    .map_or(0, |analysis| analysis.contour_ber_levels.len().max(1) * 4),
            )
        })
        .and_then(|count| {
            count.checked_add(
                usize::from(input.analysis.include_jitter || input.analysis.include_bathtub)
                    * (50 + usize::from(input.analysis.include_bathtub) * 5),
            )
        })
        .ok_or(NativeSimulationError::ResourceLimitExceeded)?;
    let estimated_bytes = sample_count
        .checked_mul(output_vector_count)
        .and_then(|values| values.checked_mul(std::mem::size_of::<f64>()))
        .and_then(|bytes| bytes.checked_add(legacy_frequency_telemetry_bytes))
        .ok_or(NativeSimulationError::ResourceLimitExceeded)?;
    let max_memory_bytes = usize::try_from(input.limits.max_memory_bytes).unwrap_or(usize::MAX);
    if sample_count > max_total_samples || estimated_bytes > max_memory_bytes {
        return Err(NativeSimulationError::ResourceLimitExceeded);
    }
    let explicit_impulse_sample_count = match &input.channel {
        ChannelInputV1::MetallicLine(channel) => channel.impulse_length.map(|value| {
            (value.0 / input.timebase.sample_interval.0)
                .floor()
                .max(1.0) as usize
        }),
        ChannelInputV1::ImpulseResponse(_)
        | ChannelInputV1::Touchstone(_)
        | ChannelInputV1::ExternalModel(_) => None,
    };
    let (channel_impulse, legacy_channel) = match &input.channel {
        ChannelInputV1::ImpulseResponse(response) => (
            response
                .impulse_response_volts_per_second
                .iter()
                .map(|sample| sample * input.timebase.sample_interval.0)
                .collect::<Vec<_>>(),
            None,
        ),
        ChannelInputV1::MetallicLine(channel) => {
            let response = metallic_line_impulse(
                channel,
                sample_count,
                input.timebase.sample_interval.0,
                samples_per_ui,
                max_total_samples,
            )?;
            (response.impulse, response.legacy)
        }
        ChannelInputV1::Touchstone(_) | ChannelInputV1::ExternalModel(_) => {
            return Err(NativeSimulationError::UnsupportedChannel);
        }
    };
    cancellation.check()?;
    let ffe_weights = if input.tx.ffe.enabled {
        input.tx.ffe.weights.as_slice()
    } else {
        &[]
    };
    let rx_filter = input
        .rx
        .ctle
        .as_ref()
        .filter(|_| input.rx.native_ctle_enabled)
        .map_or(Ok(vec![1.0]), |ctle| {
            if let Some(impulse) = &ctle.impulse_response_v_per_v {
                return Ok(impulse[..impulse.len().min(sample_count)].to_vec());
            }
            legacy_ctle_impulse(
                ctle,
                sample_count,
                input.timebase.sample_interval.0,
                samples_per_ui,
                max_total_samples,
                explicit_impulse_sample_count,
            )
        })?;
    cancellation.check()?;
    let mut linear = run_linear_link_with_rx_filter(
        &symbols,
        &channel_impulse,
        ffe_weights,
        &rx_filter,
        samples_per_ui,
        max_total_samples,
    )?;
    if let Some(pulse_cfg) = &input.tx.measured_pulse {
        let mut custom_tx = crate::generate_measured_tx_waveform(
            &symbols,
            samples_per_ui,
            input.timebase.sample_interval.0,
            pulse_cfg,
            sample_count,
        )
        .map_err(|_| NativeSimulationError::Contract(crate::ContractError::InvalidChannelResponse))?;

        if input.tx.ffe.enabled && !input.tx.ffe.weights.is_empty() {
            let ffe_impulse = ffe_impulse_response(
                &input.tx.ffe.weights,
                samples_per_ui,
                input.tx.ffe.weights.len() * samples_per_ui,
            )?;
            custom_tx = convolve_truncated(&custom_tx, &ffe_impulse, sample_count)?;
        }
        linear.tx_waveform = custom_tx;
        linear.rx_input = causal_convolve_truncated(&linear.tx_waveform, &channel_impulse, sample_count)?;
        linear.rx_output = causal_convolve_truncated(&linear.rx_input, &rx_filter, sample_count)?;
    }
    cancellation.check()?;
    let periodic_noise = input
        .tx
        .periodic_noise
        .as_ref()
        .map(|noise| generate_periodic_noise(noise, input.timebase.sample_interval.0, sample_count))
        .transpose()?;
    let mut receiver_input_noise = periodic_noise.clone().unwrap_or_default();
    if let Some(additive_noise) = &input.tx.additive_noise {
        if additive_noise.samples_v.len() != linear.rx_input.len() {
            return Err(NativeSimulationError::AdditiveNoiseLengthMismatch);
        }
        if receiver_input_noise.is_empty() {
            receiver_input_noise = additive_noise.samples_v.clone();
        } else {
            receiver_input_noise
                .iter_mut()
                .zip(&additive_noise.samples_v)
                .for_each(|(total, noise)| *total += noise);
        }
    }
    if !receiver_input_noise.is_empty() {
        linear
            .rx_input
            .iter_mut()
            .zip(&receiver_input_noise)
            .for_each(|(input, noise)| *input += noise);
        linear.rx_output = convolve_truncated(&linear.rx_input, &rx_filter, sample_count)?;
    }
    let ctle_output = linear.rx_output.clone();
    let rx_ffe_weights = if input.rx.ffe.enabled {
        input.rx.ffe.weights.as_slice()
    } else {
        &[1.0]
    };
    let rx_ffe_impulse = ffe_impulse_response(rx_ffe_weights, samples_per_ui, sample_count)?;
    linear.rx_output = if input.rx.ffe.enabled {
        sparse_tapped_convolve_truncated(&ctle_output, &rx_ffe_impulse, sample_count)?
    } else {
        convolve_truncated(&ctle_output, &rx_ffe_impulse, sample_count)?
    };
    let rx_peak_abs = linear
        .rx_output
        .iter()
        .fold(0.0_f64, |peak, value| peak.max(value.abs()));
    let rx_rms = (linear
        .rx_output
        .iter()
        .map(|value| value * value)
        .sum::<f64>()
        / linear.rx_output.len() as f64)
        .sqrt();
    let sampled_ui_seconds = input.timebase.sample_interval.0 * samples_per_ui as f64;
    let configured_ui_seconds = 1.0 / input.timebase.data_rate.0;
    let dfe_result = input
        .rx
        .dfe
        .as_ref()
        .map(|dfe| {
            if !approximately_equal(sampled_ui_seconds, configured_ui_seconds) {
                return Err(NativeSimulationError::InconsistentTimebase);
            }
            let sample_times = (0..linear.rx_output.len())
                .map(|index| index as f64 * input.timebase.sample_interval.0)
                .collect::<Vec<_>>();
            let modulation = match input.modulation {
                ModulationV1::Nrz => DfeModulation::Nrz,
                ModulationV1::Pam4 => DfeModulation::Pam4,
                ModulationV1::DuoBinary => DfeModulation::DuoBinary,
            };
            run_dfe(
                &sample_times,
                &linear.rx_output,
                DfeConfig {
                    n_taps: input.rx.dfe_taps as usize,
                    gain: dfe.gain,
                    decision_scaler: dfe.decision_scaler.0,
                    modulation,
                    n_ave: dfe.n_ave as usize,
                    limits: dfe.tap_limits.clone(),
                    initial_weights: dfe.initial_weights.clone(),
                    initial_values: dfe.initial_values.clone(),
                    initial_corrections: dfe.initial_corrections.clone(),
                    training_start_ui: dfe.training_start_ui.map(|u| u as usize),
                    training_end_ui: dfe.training_end_ui.map(|u| u as usize),
                },
                CdrConfig {
                    delta_t: dfe.delta_t.0,
                    alpha: dfe.alpha,
                    ui: configured_ui_seconds,
                    n_lock_ave: dfe.n_lock_ave as usize,
                    rel_lock_tol: dfe.rel_lock_tol,
                    lock_sustain: dfe.lock_sustain as usize,
                },
                DfeRunOptions {
                    samples_per_ui,
                    bandwidth_hz: dfe.bandwidth.0,
                    ideal: dfe.ideal,
                    use_agc: dfe.use_agc,
                    agc_n_ave: dfe.agc_n_ave as usize,
                },
            )
            .map_err(NativeSimulationError::from)
        })
        .transpose()?;
    cancellation.check()?;
    let legacy_stage_responses = legacy_channel
        .as_ref()
        .map(|legacy| {
            legacy_stage_frequency_responses(
                &linear.tx_impulse,
                &linear.tx_channel_impulse,
                &rx_filter,
                &rx_ffe_impulse,
                dfe_result
                    .as_ref()
                    .and_then(|result| result.tap_weights.last())
                    .map_or(&[], Vec::as_slice),
                samples_per_ui,
                &legacy.frequency_hz,
                input.timebase.sample_interval.0,
                max_total_samples,
            )
        })
        .transpose()?;
    let channel_output =
        causal_convolve_truncated(&linear.tx_waveform, &channel_impulse, sample_count)?;
    let mut metrics = BTreeMap::from([
        ("generated_bits".into(), bits.len() as f64),
        ("symbol_count".into(), symbols.len() as f64),
        ("tx_sample_count".into(), linear.tx_waveform.len() as f64),
        ("rx_sample_count".into(), linear.rx_output.len() as f64),
        ("rx_peak_abs_v".into(), rx_peak_abs),
        ("rx_rms_v".into(), rx_rms),
    ]);
    if let PatternV1::Prbs { seed, .. } = &input.pattern {
        metrics.insert("effective_prbs_seed".into(), *seed as f64);
    }
    if let Some(encoded_bits) = &fec_encoded_bits {
        metrics.insert("fec_encoded_bit_count".into(), encoded_bits.len() as f64);
    }
    if input.tx.measured_pulse.is_some() {
        metrics.insert("tx_measured_pulse_enabled".into(), 1.0);
    }
    let mut arrays = BTreeMap::from([
        (
            "time_s".into(),
            (0..linear.rx_output.len())
                .map(|index| index as f64 * input.timebase.sample_interval.0)
                .collect(),
        ),
        ("symbols_v".into(), symbols.clone()),
        ("tx_waveform_v".into(), linear.tx_waveform.clone()),
        ("tx_impulse_v_per_v".into(), linear.tx_impulse.clone()),
        ("channel_output_v".into(), channel_output.clone()),
        ("channel_impulse_v_per_v".into(), channel_impulse),
        (
            "tx_channel_impulse_v_per_v".into(),
            linear.tx_channel_impulse.clone(),
        ),
        ("rx_filter_impulse_v_per_v".into(), rx_filter.clone()),
        ("rx_input_v".into(), linear.rx_input.clone()),
        ("ctle_output_v".into(), ctle_output.clone()),
        ("rx_ffe_impulse_v_per_v".into(), rx_ffe_impulse.clone()),
        ("rx_output_v".into(), linear.rx_output.clone()),
    ]);
    if let Some(legacy) = legacy_channel {
        arrays.extend([
            ("legacy_channel_frequency_hz".into(), legacy.frequency_hz),
            (
                "legacy_channel_raw_re".into(),
                legacy.raw.iter().map(|value| value.re).collect(),
            ),
            (
                "legacy_channel_raw_im".into(),
                legacy.raw.iter().map(|value| value.im).collect(),
            ),
            (
                "legacy_channel_terminated_re".into(),
                legacy.terminated.iter().map(|value| value.re).collect(),
            ),
            (
                "legacy_channel_terminated_im".into(),
                legacy.terminated.iter().map(|value| value.im).collect(),
            ),
            (
                "legacy_channel_trimmed_re".into(),
                legacy.trimmed.iter().map(|value| value.re).collect(),
            ),
            (
                "legacy_channel_trimmed_im".into(),
                legacy.trimmed.iter().map(|value| value.im).collect(),
            ),
        ]);
    }
    if let Some(stages) = legacy_stage_responses {
        for (name, response) in [
            ("tx", stages.tx),
            ("tx_out", stages.tx_out),
            ("ctle", stages.ctle),
            ("ctle_out", stages.ctle_out),
            ("dfe", stages.dfe),
            ("dfe_out", stages.dfe_out),
        ] {
            arrays.insert(
                format!("legacy_stage_{name}_re"),
                response.iter().map(|value| value.re).collect(),
            );
            arrays.insert(
                format!("legacy_stage_{name}_im"),
                response.iter().map(|value| value.im).collect(),
            );
        }
    }
    let mut post_receiver_bits = None;
    if let Some(additive_noise) = &input.tx.additive_noise {
        arrays.insert("random_noise_v".into(), additive_noise.samples_v.clone());
        arrays.insert("additive_noise_v".into(), receiver_input_noise.clone());
        metrics.insert(
            "random_noise_sample_count".into(),
            additive_noise.samples_v.len() as f64,
        );
        if let Some(seed) = additive_noise.effective_seed {
            metrics.insert("effective_noise_seed".into(), seed as f64);
        }
    }
    if let Some(periodic_noise) = periodic_noise {
        arrays.insert("periodic_noise_v".into(), periodic_noise);
    }
    if !receiver_input_noise.is_empty() {
        arrays.insert("receiver_input_noise_v".into(), receiver_input_noise);
    }
    let mut stages = vec![
        RunStageV1::Validate,
        RunStageV1::ChannelResponse,
        RunStageV1::TxProcessing,
        RunStageV1::RxEqualization,
    ];
    if let Some(dfe) = dfe_result.as_ref() {
        metrics.extend([
            ("dfe_decision_count".into(), dfe.decisions.len() as f64),
            ("dfe_bit_count".into(), dfe.bits.len() as f64),
            ("dfe_tap_history_rows".into(), dfe.tap_weights.len() as f64),
            ("dfe_tap_history_columns".into(), input.rx.dfe_taps as f64),
            (
                "dfe_locked_sample_count".into(),
                dfe.lockeds.iter().filter(|&&locked| locked).count() as f64,
            ),
        ]);
        if let Some(final_taps) = dfe.tap_weights.last() {
            metrics.extend(
                final_taps
                    .iter()
                    .enumerate()
                    .map(|(index, tap)| (format!("dfe_final_tap_{index}_v"), *tap)),
            );
        }
        arrays.extend([
            ("dfe_output_v".into(), dfe.dfe_out.clone()),
            ("dfe_clock_times_s".into(), dfe.clock_times.clone()),
            (
                "dfe_bits".into(),
                dfe.bits.iter().map(|&bit| bit as f64).collect(),
            ),
            ("dfe_decisions".into(), dfe.decisions.clone()),
            ("dfe_signal_samples_v".into(), dfe.signal_samples.clone()),
            (
                "dfe_tap_weights_v".into(),
                dfe.tap_weights.iter().flatten().copied().collect(),
            ),
            ("dfe_ui_estimates_s".into(), dfe.ui_estimates.clone()),
            ("dfe_clocks".into(), dfe.clocks.clone()),
            ("dfe_slicer_inputs_v".into(), dfe.slicer_inputs.clone()),
            ("dfe_errors_v".into(), dfe.errors.clone()),
            (
                "dfe_update_enabled".into(),
                dfe.update_enableds.iter().map(|&u| f64::from(u)).collect(),
            ),
            (
                "dfe_bank_updated".into(),
                dfe.bank_updateds.iter().map(|&u| f64::from(u)).collect(),
            ),
            (
                "dfe_locked".into(),
                dfe.lockeds
                    .iter()
                    .map(|&locked| if locked { 1.0 } else { 0.0 })
                    .collect(),
            ),
            (
                "dfe_decision_scalers_v".into(),
                dfe.decision_scalers.clone(),
            ),
        ]);
        post_receiver_bits = Some(dfe.bits.clone());
        stages.push(RunStageV1::DfeAdaptation);
    }
    if input.rx.viterbi_enabled {
        let dfe = dfe_result
            .as_ref()
            .expect("typed DFE was required before native execution");
        let viterbi = input
            .rx
            .viterbi
            .as_ref()
            .expect("typed Viterbi configuration was required before native execution");
        if viterbi.fec {
            let chunks = dfe.bits.chunks_exact(2);
            if !chunks.remainder().is_empty() {
                return Err(NativeSimulationError::IncompleteFecObservations);
            }
            let observations = chunks.map(|bits| (bits[0], bits[1])).collect::<Vec<_>>();
            let decoded = decode_fec(&observations, viterbi.state_symbols as usize)?;
            metrics.extend([
                ("fec_observation_count".into(), observations.len() as f64),
                (
                    "viterbi_state_count".into(),
                    decoded.state_path.len() as f64,
                ),
                ("viterbi_bit_count".into(), decoded.bits.len() as f64),
            ]);
            arrays.extend([
                (
                    "viterbi_state_path".into(),
                    decoded
                        .state_path
                        .iter()
                        .map(|&state| state as f64)
                        .collect(),
                ),
                (
                    "viterbi_bits".into(),
                    decoded.bits.iter().map(|&bit| bit as f64).collect(),
                ),
            ]);
            post_receiver_bits = Some(decoded.bits);
        } else {
            let pulse = viterbi_pulse_response(
                &linear.tx_channel_impulse,
                &rx_filter,
                dfe.tap_weights.last().map_or(&[], Vec::as_slice),
                samples_per_ui,
                viterbi.state_symbols as usize,
            )?;
            let levels = match input.modulation {
                ModulationV1::Nrz => 2,
                ModulationV1::Pam4 => 4,
                ModulationV1::DuoBinary => 3,
            };
            let decoded = decode_isi(
                &dfe.signal_samples,
                &pulse,
                IsiDecodeConfig {
                    levels,
                    state_symbols: viterbi.state_symbols as usize,
                    sigma: viterbi
                        .noise_sigma_v
                        .expect("non-FEC Viterbi configuration was validated")
                        .0,
                    max_states: (viterbi.max_states.min(input.limits.max_distribution_states))
                        as usize,
                },
            )?;
            let decoded_bits = decoded
                .symbols
                .iter()
                .flat_map(|&symbol| viterbi_symbol_bits(symbol, &input.modulation))
                .collect::<Vec<_>>();
            metrics.extend([
                (
                    "viterbi_state_count".into(),
                    decoded.state_path.len() as f64,
                ),
                ("viterbi_symbol_count".into(), decoded.symbols.len() as f64),
                ("viterbi_bit_count".into(), decoded_bits.len() as f64),
            ]);
            arrays.extend([
                (
                    "viterbi_state_path".into(),
                    decoded
                        .state_path
                        .iter()
                        .map(|&state| state as f64)
                        .collect(),
                ),
                ("viterbi_symbols_v".into(), decoded.symbols),
                (
                    "viterbi_bits".into(),
                    decoded_bits.iter().map(|&bit| bit as f64).collect(),
                ),
            ]);
            post_receiver_bits = Some(decoded_bits);
        }
        stages.push(RunStageV1::ViterbiFec);
    }
    if let Some(observed_bits) = post_receiver_bits {
        if bits.iter().any(|&bit| bit != 0) && !observed_bits.is_empty() {
            let requested_eye_bits = input.analysis.ber_eye_bits.unwrap_or(input.timebase.nbits);
            let eye_bits = usize::try_from(requested_eye_bits)
                .map_err(|_| NativeSimulationError::ResourceLimitExceeded)?;
            let ber = calculate_ber(&bits, &observed_bits, eye_bits)?;
            metrics.extend([
                ("ber_available".into(), 1.0),
                ("ber_bit_delay".into(), ber.bit_delay as f64),
                ("ber_compared_bits".into(), ber.compared_bits as f64),
                ("ber_error_count".into(), ber.error_indices.len() as f64),
                (
                    "ber".into(),
                    ber.error_indices.len() as f64 / ber.compared_bits as f64,
                ),
            ]);
            arrays.extend([
                (
                    "ber_reference_bits".into(),
                    bits.iter().map(|&bit| bit as f64).collect(),
                ),
                (
                    "ber_observed_bits".into(),
                    observed_bits.iter().map(|&bit| bit as f64).collect(),
                ),
                (
                    "ber_error_indices".into(),
                    ber.error_indices
                        .iter()
                        .map(|&index| index as f64)
                        .collect(),
                ),
                ("ber_auto_correlation".into(), ber.auto_correlation),
            ]);
        } else {
            metrics.insert("ber_available".into(), 0.0);
        }
    }
    cancellation.check()?;
    if input.analysis.include_jitter || input.analysis.include_bathtub {
        // The pinned native core measures the same held TX waveform for every
        // modulation.  Do not re-convolve DuoBinary here: that changes the
        // crossing sequence (and therefore the complete jitter payload).
        let jitter = calculate_native_jitter_metrics(
            input,
            prbs_order.ok_or(NativeSimulationError::UnsupportedPattern)?,
            &linear.tx_waveform,
            [
                ("chnl", channel_output.as_slice()),
                ("tx", linear.rx_input.as_slice()),
                ("ctle", ctle_output.as_slice()),
                (
                    "dfe",
                    dfe_result
                        .as_ref()
                        .map_or(linear.rx_output.as_slice(), |dfe| dfe.dfe_out.as_slice()),
                ),
            ],
            crossing_amplitude_v,
            samples_per_ui,
            input.analysis.include_bathtub,
        );
        let jitter = jitter?;
        metrics.extend(jitter.metrics);
        arrays.extend(jitter.arrays);
        if input.analysis.include_bathtub {
            metrics.extend(jitter.bathtub_metrics);
        }
        stages.push(RunStageV1::JitterAnalysis);
    }
    cancellation.check()?;
    if let Some(analysis) = &input.analysis.statistical_eye {
        if !matches!(input.modulation, ModulationV1::Nrz) {
            return Err(NativeSimulationError::UnsupportedStatisticalEyeModulation);
        }
        if !approximately_equal(sampled_ui_seconds, configured_ui_seconds) {
            return Err(NativeSimulationError::InconsistentTimebase);
        }
        // The generic contract remains pre-DFE by default. The controlled Web
        // path opts in to its legacy-compatible post-receiver pulse so it does
        // not recompute the same statistical eye in Python during adaptation.
        let native_eye_impulse =
            convolve_truncated(&linear.tx_channel_impulse, &rx_filter, sample_count)?;
        let response_length = linear.tx_channel_impulse.len();
        let rx_ffe_eye_impulse =
            convolve_truncated(&native_eye_impulse, &rx_ffe_impulse, response_length)?;
        let final_dfe_taps = dfe_result
            .as_ref()
            .and_then(|dfe| dfe.tap_weights.last())
            .map_or(&[][..], Vec::as_slice);
        let mut dfe_eye_impulse = vec![0.0; samples_per_ui];
        dfe_eye_impulse[0] = 1.0;
        for &tap in final_dfe_taps {
            dfe_eye_impulse.push(-tap);
            dfe_eye_impulse.extend(std::iter::repeat_n(0.0, samples_per_ui - 1));
        }
        let web_eye_impulse =
            convolve_truncated(&rx_ffe_eye_impulse, &dfe_eye_impulse, response_length)?;
        let web_eye_pulse = pulse_response(&step_response(&web_eye_impulse)?, samples_per_ui)?;
        let native_eye_pulse =
            pulse_response(&step_response(&native_eye_impulse)?, samples_per_ui)?;
        let max_distribution_states = usize::try_from(
            analysis
                .max_distribution_states
                .min(input.limits.max_distribution_states),
        )
        .map_err(|_| NativeSimulationError::ResourceLimitExceeded)?;
        let eye_input = StatisticalEyeInputV1 {
            pulse_response: if analysis.post_receiver_output {
                &web_eye_pulse
            } else {
                &native_eye_pulse
            },
            ui: crate::Seconds(sampled_ui_seconds),
            nspui: samples_per_ui,
            target_ber: analysis.target_ber,
            noise_sigma_v: None,
            horizontal_rj_ui: None,
            horizontal_dj_ui: None,
            tx_rj_ui: analysis.tx_rj_ui,
            tx_dj_ui: analysis.tx_dj_ui,
            tx_dcd_ui: analysis.tx_dcd_ui,
            rx_rj_ui: analysis.rx_rj_ui,
            rx_dj_ui: analysis.rx_dj_ui,
            voltage_resolution: analysis.voltage_resolution,
            time_points: analysis.time_points as usize,
            max_distribution_states,
        };
        let eye = calculate_statistical_eye(eye_input)?;
        let contour_levels = if analysis.contour_ber_levels.is_empty() {
            vec![analysis.target_ber]
        } else {
            analysis.contour_ber_levels.clone()
        };
        let contours = calculate_statistical_contours(eye_input, &contour_levels)?;
        metrics.extend([
            (
                "eye_is_pre_dfe_linear".into(),
                f64::from(!analysis.post_receiver_output),
            ),
            ("eye_level0_v".into(), eye.level0_v),
            ("eye_level1_v".into(), eye.level1_v),
            ("eye_height_v".into(), eye.eye_height_v),
            ("eye_width_ps".into(), eye.eye_width_ps),
            ("eye_height_at_ber_v".into(), eye.height_at_ber_v),
            ("eye_width_at_ber_ps".into(), eye.width_at_ber_ps),
            (
                "eye_distribution_state_count".into(),
                eye.distribution_state_count as f64,
            ),
            ("eye_contour_count".into(), contours.len() as f64),
        ]);
        arrays.extend([
            ("statistical_eye_impulse_v_per_v".into(), web_eye_impulse),
            ("statistical_eye_pulse_v".into(), web_eye_pulse),
            (
                "eye_contour_ber".into(),
                contours.iter().map(|contour| contour.ber).collect(),
            ),
            (
                "eye_contour_height_v".into(),
                contours.iter().map(|contour| contour.height_v).collect(),
            ),
            (
                "eye_contour_width_ps".into(),
                contours.iter().map(|contour| contour.width_ps).collect(),
            ),
            (
                "eye_contour_point_count".into(),
                contours
                    .iter()
                    .map(|contour| contour.point_count as f64)
                    .collect(),
            ),
        ]);
        for (index, contour) in contours.iter().enumerate() {
            arrays.insert(format!("eye_contour_{index}_x_ui"), contour.x_ui.clone());
            arrays.insert(format!("eye_contour_{index}_y_v"), contour.y_v.clone());
        }
        stages.push(RunStageV1::StatisticalEye);
    }
    if matches!(input.modulation, ModulationV1::Pam4) {
        let pam4_waveform = dfe_result
            .as_ref()
            .map_or(linear.rx_output.as_slice(), |dfe| dfe.dfe_out.as_slice());
        let rx_bits = dfe_result.as_ref().map(|dfe| dfe.bits.as_slice());
        let pam4_eye = crate::pam4_eye::calculate_pam4_eye_metrics(
            pam4_waveform,
            samples_per_ui,
            input.timebase.sample_interval.0,
            &bits,
            rx_bits,
        )?;
        metrics.extend([
            ("pam4_level_0_v".into(), pam4_eye.levels.v0),
            ("pam4_level_1_v".into(), pam4_eye.levels.v1),
            ("pam4_level_2_v".into(), pam4_eye.levels.v2),
            ("pam4_level_3_v".into(), pam4_eye.levels.v3),
            ("pam4_threshold_lower_v".into(), pam4_eye.thresholds.lower),
            ("pam4_threshold_mid_v".into(), pam4_eye.thresholds.mid),
            ("pam4_threshold_upper_v".into(), pam4_eye.thresholds.upper),
            ("pam4_eye_height_lower_v".into(), pam4_eye.eye_height_lower_v),
            ("pam4_eye_height_mid_v".into(), pam4_eye.eye_height_mid_v),
            ("pam4_eye_height_upper_v".into(), pam4_eye.eye_height_upper_v),
            ("pam4_eye_height_worst_v".into(), pam4_eye.eye_height_worst_v),
            ("pam4_inner_eye_height_lower_v".into(), pam4_eye.inner_eye_height_lower_v),
            ("pam4_inner_eye_height_mid_v".into(), pam4_eye.inner_eye_height_mid_v),
            ("pam4_inner_eye_height_upper_v".into(), pam4_eye.inner_eye_height_upper_v),
            ("pam4_inner_eye_height_worst_v".into(), pam4_eye.inner_eye_height_worst_v),
            ("pam4_eye_width_lower_ps".into(), pam4_eye.eye_width_lower_ps),
            ("pam4_eye_width_mid_ps".into(), pam4_eye.eye_width_mid_ps),
            ("pam4_eye_width_upper_ps".into(), pam4_eye.eye_width_upper_ps),
            ("pam4_eye_width_worst_ps".into(), pam4_eye.eye_width_worst_ps),
            ("pam4_rlm".into(), pam4_eye.rlm),
            ("pam4_ser".into(), pam4_eye.ser),
            ("pam4_ber".into(), pam4_eye.ber),
            ("pam4_symbol_count".into(), pam4_eye.symbol_count as f64),
        ]);
    }
    cancellation.check()?;
    stages.push(RunStageV1::ResultAssembly);
    let events = stages
        .iter()
        .enumerate()
        .map(|(sequence, &stage)| RunEventV1 {
            run_id: input.run_id.clone(),
            sequence: sequence as u64,
            stage,
            stage_progress: 1.0,
            total_progress: (f64::from(stage.ordinal()) + 1.0) / 9.0,
            message: None,
        })
        .collect();
    let output = SimulationOutputV1 {
        schema: SIMULATION_SCHEMA_V1.into(),
        run_id: input.run_id.clone(),
        capabilities: EngineCapabilitiesV1 {
            stages,
            external_models: vec![],
        },
        metrics,
        events,
        arrays,
        artifacts: vec![],
    };
    output.validate()?;
    Ok(output)
}

struct NativeJitterMetrics {
    metrics: BTreeMap<String, f64>,
    bathtub_metrics: BTreeMap<String, f64>,
    arrays: BTreeMap<String, Vec<f64>>,
}

struct NativeJitterStage {
    alignment_offset_s: f64,
    tie_s: Vec<f64>,
    times_s: Vec<f64>,
    data_independent_tie_s: Vec<f64>,
    isi_s: f64,
    dcd_s: f64,
    periodic_s: f64,
    random_s: f64,
    dual_dirac_periodic_s: f64,
    dual_dirac_random_s: f64,
    spectrum: Vec<f64>,
    data_independent_spectrum: Vec<f64>,
    frequency_hz: Vec<f64>,
    threshold: Vec<f64>,
    histogram_per_s: Vec<f64>,
    data_independent_histogram_per_s: Vec<f64>,
    bin_centers_s: Vec<f64>,
    bathtub_ber: Option<Vec<f64>>,
}

struct NativeJitterStageInput<'a> {
    input: &'a SimulationInputV1,
    ideal_waveform: &'a [f64],
    waveform: &'a [f64],
    ideal_crossings: &'a [f64],
    crossing_amplitude_v: f64,
    window_start_s: f64,
    eye_uis: usize,
    pattern_len: usize,
    include_bathtub: bool,
}

/// Analyze the Web-visible Channel, TX, CTLE, and DFE waveforms with the
/// legacy correlation alignment and trailing-eye window semantics.
fn calculate_native_jitter_metrics(
    input: &SimulationInputV1,
    prbs_order: u8,
    ideal_waveform: &[f64],
    stages: [(&str, &[f64]); 4],
    crossing_amplitude_v: f64,
    samples_per_ui: usize,
    include_bathtub: bool,
) -> Result<NativeJitterMetrics, NativeSimulationError> {
    let sample_interval_s = input.timebase.sample_interval.0;
    let modulation = match input.modulation {
        ModulationV1::Nrz => 0,
        ModulationV1::DuoBinary => 1,
        ModulationV1::Pam4 => 2,
    };
    let ui_s = 1.0 / input.timebase.data_rate.0;
    let complete_uis = ideal_waveform.len() / samples_per_ui;
    let requested_eye_uis = input.analysis.jitter_eye_uis.map_or(complete_uis, |value| {
        usize::try_from(value).unwrap_or(usize::MAX)
    });
    let eye_uis = requested_eye_uis.min(complete_uis);
    let window_start_s = (complete_uis - eye_uis) as f64 * ui_s;
    let ideal_times_s = (0..ideal_waveform.len())
        .map(|index| index as f64 * sample_interval_s)
        .collect::<Vec<_>>();
    let ideal_crossings = find_crossings(
        &ideal_times_s,
        ideal_waveform,
        crossing_amplitude_v,
        0.0,
        true,
        0.1,
        modulation,
    )?;
    let legacy_pattern_len = ((1_usize << prbs_order) - 1)
        .checked_mul(2)
        .ok_or(NativeSimulationError::ResourceLimitExceeded)?;
    let ideal_crossings = crop_crossings(&ideal_crossings, 0.0, window_start_s);
    let mut metrics = BTreeMap::new();
    let mut bathtub_metrics = BTreeMap::new();
    let mut arrays = BTreeMap::new();
    for (stage_name, waveform) in stages {
        let stage = calculate_native_jitter_stage(NativeJitterStageInput {
            input,
            ideal_waveform,
            waveform,
            ideal_crossings: &ideal_crossings,
            crossing_amplitude_v,
            window_start_s,
            eye_uis,
            pattern_len: legacy_pattern_len,
            include_bathtub,
        })?;
        insert_jitter_stage(
            stage_name,
            &stage,
            &mut metrics,
            &mut bathtub_metrics,
            &mut arrays,
        );
        if stage_name == "dfe" {
            insert_legacy_jitter_aliases(&stage, &mut metrics, &mut bathtub_metrics, &mut arrays);
        }
    }
    Ok(NativeJitterMetrics {
        metrics,
        bathtub_metrics,
        arrays,
    })
}

fn calculate_native_jitter_stage(
    stage_input: NativeJitterStageInput<'_>,
) -> Result<NativeJitterStage, NativeSimulationError> {
    let NativeJitterStageInput {
        input,
        ideal_waveform,
        waveform,
        ideal_crossings,
        crossing_amplitude_v,
        window_start_s,
        eye_uis,
        pattern_len,
        include_bathtub,
    } = stage_input;
    let sample_interval_s = input.timebase.sample_interval.0;
    let ui_s = 1.0 / input.timebase.data_rate.0;
    let modulation = match input.modulation {
        ModulationV1::Nrz => 0,
        ModulationV1::DuoBinary => 1,
        ModulationV1::Pam4 => 2,
    };
    let times_s = (0..waveform.len())
        .map(|index| index as f64 * sample_interval_s)
        .collect::<Vec<_>>();
    let lag_samples = correlation_peak_lag(waveform, ideal_waveform)?;
    let alignment_offset_s = lag_samples as f64 * sample_interval_s;
    let actual_crossings = find_crossings(
        &times_s,
        waveform,
        crossing_amplitude_v,
        0.0,
        true,
        0.1,
        modulation,
    )?;
    let actual_crossings = crop_crossings(&actual_crossings, alignment_offset_s, window_start_s);
    let track = assemble_tie_track(ui_s, ideal_crossings, &actual_crossings, true)?;
    let data_dependent = calculate_data_dependent_jitter(
        ui_s,
        eye_uis,
        pattern_len,
        &track.ideal_times_s,
        &track.jitter_s,
        true,
    )?;
    let spectral = calculate_spectral_jitter(
        ui_s,
        eye_uis,
        &track.ideal_times_s,
        &track.jitter_s,
        &data_dependent.data_independent_tie_s,
        input.analysis.jitter_rel_thresh.unwrap_or(3.0),
    )?;
    let dual_dirac = calculate_dual_dirac_jitter(
        ui_s,
        &track.jitter_s,
        &data_dependent.data_independent_tie_s,
        101,
        5,
    )?;
    let bathtub_ber = include_bathtub
        .then(|| {
            make_bathtub(
                &dual_dirac.bin_centers_s,
                &dual_dirac.total_histogram,
                1.0e-13,
                dual_dirac.random_jitter_s,
                dual_dirac.positive_mean_s,
                dual_dirac.negative_mean_s,
                dual_dirac.random_jitter_s > 0.0,
            )
        })
        .transpose()?;
    Ok(NativeJitterStage {
        alignment_offset_s,
        tie_s: track.jitter_s,
        times_s: track.ideal_times_s,
        data_independent_tie_s: data_dependent.data_independent_tie_s,
        isi_s: data_dependent.isi_s,
        dcd_s: data_dependent.dcd_s,
        periodic_s: spectral.periodic_jitter_s,
        random_s: spectral.random_jitter_s,
        dual_dirac_periodic_s: dual_dirac.periodic_jitter_s,
        dual_dirac_random_s: dual_dirac.random_jitter_s,
        spectrum: spectral.total_spectrum,
        data_independent_spectrum: spectral.data_independent_spectrum,
        frequency_hz: spectral.frequencies_hz,
        threshold: spectral.periodic_threshold,
        histogram_per_s: dual_dirac.total_histogram,
        data_independent_histogram_per_s: dual_dirac.data_independent_histogram,
        bin_centers_s: dual_dirac.bin_centers_s,
        bathtub_ber,
    })
}

fn crop_crossings(crossings: &[f64], offset_s: f64, window_start_s: f64) -> Vec<f64> {
    crossings
        .iter()
        .map(|crossing| crossing - offset_s)
        .filter(|crossing| *crossing > window_start_s)
        .map(|crossing| crossing - window_start_s)
        .collect()
}

fn correlation_peak_lag(
    waveform: &[f64],
    reference: &[f64],
) -> Result<isize, NativeSimulationError> {
    if waveform.is_empty() || reference.is_empty() {
        return Err(CrossingError::InvalidCrossingTrack.into());
    }
    let correlation_len = waveform
        .len()
        .checked_add(reference.len())
        .and_then(|length| length.checked_sub(1))
        .ok_or(NativeSimulationError::ResourceLimitExceeded)?;
    let fft_len = correlation_len
        .checked_next_power_of_two()
        .ok_or(NativeSimulationError::ResourceLimitExceeded)?;
    let mut left = vec![Complex::new(0.0, 0.0); fft_len];
    let mut right = vec![Complex::new(0.0, 0.0); fft_len];
    left.iter_mut()
        .zip(waveform)
        .for_each(|(slot, &value)| slot.re = value);
    right
        .iter_mut()
        .zip(reference.iter().rev())
        .for_each(|(slot, &value)| slot.re = value);
    let mut planner = FftPlanner::<f64>::new();
    planner.plan_fft_forward(fft_len).process(&mut left);
    planner.plan_fft_forward(fft_len).process(&mut right);
    left.iter_mut()
        .zip(right)
        .for_each(|(value, other)| *value *= other);
    planner.plan_fft_inverse(fft_len).process(&mut left);
    let scale = 1.0 / fft_len as f64;
    let peak_index = left[..correlation_len]
        .iter()
        .enumerate()
        .max_by(|(_, left), (_, right)| (left.re * scale).total_cmp(&(right.re * scale)))
        .map(|(index, _)| index)
        .ok_or(CrossingError::InvalidCrossingTrack)?;
    Ok(peak_index as isize - (reference.len() as isize - 1))
}

fn insert_jitter_stage(
    stage_name: &str,
    stage: &NativeJitterStage,
    metrics: &mut BTreeMap<String, f64>,
    bathtub_metrics: &mut BTreeMap<String, f64>,
    arrays: &mut BTreeMap<String, Vec<f64>>,
) {
    metrics.extend([
        (
            format!("jitter_{stage_name}_tie_count"),
            stage.tie_s.len() as f64,
        ),
        (format!("jitter_{stage_name}_isi_s"), stage.isi_s),
        (format!("jitter_{stage_name}_dcd_s"), stage.dcd_s),
        (format!("jitter_{stage_name}_periodic_s"), stage.periodic_s),
        (format!("jitter_{stage_name}_random_s"), stage.random_s),
        (
            format!("jitter_{stage_name}_dual_dirac_periodic_s"),
            stage.dual_dirac_periodic_s,
        ),
        (
            format!("jitter_{stage_name}_dual_dirac_random_s"),
            stage.dual_dirac_random_s,
        ),
        (
            format!("jitter_{stage_name}_alignment_offset_s"),
            stage.alignment_offset_s,
        ),
    ]);
    arrays.extend([
        (
            format!("jitter_{stage_name}"),
            stage.histogram_per_s.clone(),
        ),
        (format!("jitter_{stage_name}_tie_s"), stage.tie_s.clone()),
        (
            format!("jitter_{stage_name}_times_s"),
            stage.times_s.clone(),
        ),
        (
            format!("jitter_{stage_name}_data_independent_tie_s"),
            stage.data_independent_tie_s.clone(),
        ),
        (
            format!("jitter_{stage_name}_spectrum"),
            stage.spectrum.clone(),
        ),
        (
            format!("jitter_{stage_name}_data_independent_spectrum"),
            stage.data_independent_spectrum.clone(),
        ),
        (
            format!("jitter_{stage_name}_frequency_hz"),
            stage.frequency_hz.clone(),
        ),
        (
            format!("jitter_{stage_name}_threshold"),
            stage.threshold.clone(),
        ),
        (
            format!("jitter_{stage_name}_data_independent_histogram_per_s"),
            stage.data_independent_histogram_per_s.clone(),
        ),
        (
            format!("jitter_{stage_name}_bin_centers_s"),
            stage.bin_centers_s.clone(),
        ),
    ]);
    if let Some(bathtub) = &stage.bathtub_ber {
        bathtub_metrics.extend([
            (
                format!("bathtub_{stage_name}_min_ber"),
                bathtub.iter().copied().fold(f64::INFINITY, f64::min),
            ),
            (
                format!("bathtub_{stage_name}_max_ber"),
                bathtub.iter().copied().fold(f64::NEG_INFINITY, f64::max),
            ),
        ]);
        arrays.insert(format!("bathtub_{stage_name}_ber"), bathtub.clone());
    }
}

fn insert_legacy_jitter_aliases(
    stage: &NativeJitterStage,
    metrics: &mut BTreeMap<String, f64>,
    bathtub_metrics: &mut BTreeMap<String, f64>,
    arrays: &mut BTreeMap<String, Vec<f64>>,
) {
    metrics.extend([
        ("jitter_tie_count".into(), stage.tie_s.len() as f64),
        ("jitter_isi_s".into(), stage.isi_s),
        ("jitter_dcd_s".into(), stage.dcd_s),
        ("jitter_periodic_s".into(), stage.periodic_s),
        ("jitter_random_s".into(), stage.random_s),
        (
            "jitter_dual_dirac_periodic_s".into(),
            stage.dual_dirac_periodic_s,
        ),
        (
            "jitter_dual_dirac_random_s".into(),
            stage.dual_dirac_random_s,
        ),
        ("jitter_alignment_offset_s".into(), stage.alignment_offset_s),
    ]);
    arrays.extend([
        ("jitter_tie_s".into(), stage.tie_s.clone()),
        ("jitter_times_s".into(), stage.times_s.clone()),
        (
            "jitter_data_independent_tie_s".into(),
            stage.data_independent_tie_s.clone(),
        ),
        ("jitter_spectrum".into(), stage.spectrum.clone()),
        (
            "jitter_data_independent_spectrum".into(),
            stage.data_independent_spectrum.clone(),
        ),
        ("jitter_frequency_hz".into(), stage.frequency_hz.clone()),
        ("jitter_threshold".into(), stage.threshold.clone()),
        (
            "jitter_histogram_per_s".into(),
            stage.histogram_per_s.clone(),
        ),
        (
            "jitter_data_independent_histogram_per_s".into(),
            stage.data_independent_histogram_per_s.clone(),
        ),
        ("jitter_bin_centers_s".into(), stage.bin_centers_s.clone()),
    ]);
    if let Some(bathtub) = &stage.bathtub_ber {
        bathtub_metrics.extend([
            (
                "bathtub_min_ber".into(),
                bathtub.iter().copied().fold(f64::INFINITY, f64::min),
            ),
            (
                "bathtub_max_ber".into(),
                bathtub.iter().copied().fold(f64::NEG_INFINITY, f64::max),
            ),
        ]);
        arrays.insert("bathtub_ber".into(), bathtub.clone());
    }
}

fn viterbi_pulse_response(
    tx_channel_impulse: &[f64],
    rx_filter: &[f64],
    dfe_taps: &[f64],
    samples_per_ui: usize,
    state_symbols: usize,
) -> Result<Vec<f64>, NativeSimulationError> {
    let rx_impulse = convolve_truncated(tx_channel_impulse, rx_filter, tx_channel_impulse.len())?;
    let mut dfe_impulse = vec![1.0];
    dfe_impulse.extend(std::iter::repeat_n(0.0, samples_per_ui.saturating_sub(1)));
    for &tap in dfe_taps {
        dfe_impulse.extend(std::iter::once(-tap));
        dfe_impulse.extend(std::iter::repeat_n(0.0, samples_per_ui.saturating_sub(1)));
    }
    let dfe_output_impulse = convolve_truncated(&rx_impulse, &dfe_impulse, rx_impulse.len())?;
    let pulse = pulse_response(&step_response(&dfe_output_impulse)?, samples_per_ui)?;
    let cursor = pulse
        .iter()
        .enumerate()
        .max_by(|(_, left), (_, right)| left.total_cmp(right))
        .map(|(index, _)| index)
        .ok_or(NativeSimulationError::ViterbiPulseTooShort)?;
    let mut samples = Vec::with_capacity(state_symbols);
    for offset in 0..state_symbols {
        let index = cursor
            .checked_add(
                offset
                    .checked_mul(samples_per_ui)
                    .ok_or(NativeSimulationError::ViterbiPulseTooShort)?,
            )
            .ok_or(NativeSimulationError::ViterbiPulseTooShort)?;
        samples.push(
            *pulse
                .get(index)
                .ok_or(NativeSimulationError::ViterbiPulseTooShort)?,
        );
    }
    Ok(samples)
}

fn viterbi_symbol_bits(symbol: f64, modulation: &ModulationV1) -> Vec<i32> {
    match modulation {
        ModulationV1::Nrz => vec![i32::from(symbol > 0.0)],
        ModulationV1::DuoBinary => vec![i32::from(symbol.abs() < f64::EPSILON)],
        ModulationV1::Pam4 => {
            if symbol > 2.0 / 3.0 {
                vec![1, 0]
            } else if symbol > 0.0 {
                vec![1, 1]
            } else if symbol > -2.0 / 3.0 {
                vec![0, 1]
            } else {
                vec![0, 0]
            }
        }
    }
}

fn approximately_equal(left: f64, right: f64) -> bool {
    (left - right).abs() <= 1.0e-12 * left.abs().max(right.abs()).max(f64::MIN_POSITIVE)
}

fn generate_periodic_noise(
    noise: &PeriodicNoiseV1,
    sample_interval_s: f64,
    sample_count: usize,
) -> Result<Vec<f64>, NativeSimulationError> {
    let sample_rate_hz = 1.0 / sample_interval_s;
    if !sample_rate_hz.is_finite() || noise.frequency.0 > sample_rate_hz * 0.5 || sample_count == 0
    {
        return Err(NativeSimulationError::Contract(
            ContractError::InvalidPeriodicNoise,
        ));
    }
    let period_samples = (sample_rate_hz / noise.frequency.0 + 0.5).floor() as usize;
    if period_samples == 0 {
        return Err(NativeSimulationError::Contract(
            ContractError::InvalidPeriodicNoise,
        ));
    }

    // `scipy.signal.iirfilter(2, 1 MHz / (fs / 2), btype="highpass")`
    // followed by zero-state `lfilter`, expanded here to keep this physical
    // source deterministic and independent from SciPy at the native boundary.
    let prewarp = (std::f64::consts::PI * 1.0e6 / sample_rate_hz).tan();
    let denominator = 1.0 + std::f64::consts::SQRT_2 * prewarp + prewarp * prewarp;
    let b0 = 1.0 / denominator;
    let b1 = -2.0 * b0;
    let b2 = b0;
    let a1 = 2.0 * (prewarp * prewarp - 1.0) / denominator;
    let a2 = (1.0 - std::f64::consts::SQRT_2 * prewarp + prewarp * prewarp) / denominator;
    let mut output = Vec::with_capacity(sample_count);
    let mut prior_input_1 = 0.0;
    let mut prior_input_2 = 0.0;
    let mut prior_output_1 = 0.0;
    let mut prior_output_2 = 0.0;
    for index in 0..sample_count {
        let input = if index % period_samples >= period_samples / 2 {
            noise.magnitude.0
        } else {
            0.0
        };
        let value = b0 * input + b1 * prior_input_1 + b2 * prior_input_2
            - a1 * prior_output_1
            - a2 * prior_output_2;
        output.push(value);
        prior_input_2 = prior_input_1;
        prior_input_1 = input;
        prior_output_2 = prior_output_1;
        prior_output_1 = value;
    }
    Ok(output)
}

fn legacy_ctle_impulse(
    ctle: &crate::CtleConfigV1,
    target_sample_count: usize,
    target_sample_interval_s: f64,
    samples_per_ui: usize,
    max_total_samples: usize,
    explicit_impulse_sample_count: Option<usize>,
) -> Result<Vec<f64>, NativeSimulationError> {
    let config = CtleConfig {
        rx_bandwidth_hz: ctle.bandwidth.0,
        peak_frequency_hz: ctle.peak_frequency.0,
        peak_magnitude_db: ctle.peak_magnitude_db,
    };
    let (Some(step), Some(maximum)) = (ctle.frequency_step_hz, ctle.frequency_max_hz) else {
        return Ok(ctle_impulse_response(
            config,
            target_sample_count,
            target_sample_interval_s,
        )?);
    };
    // Keep this analytic CTLE route byte-for-byte aligned with the pinned
    // native core.  The metallic-line path has a separately justified
    // `arange` grid, but using it here changes the CTLE IFFT timebase.
    let intervals = (maximum.0 / step.0).round() as usize;
    let fft_size = intervals
        .checked_mul(2)
        .ok_or(NativeSimulationError::ResourceLimitExceeded)?;
    if fft_size > max_total_samples {
        return Err(NativeSimulationError::ResourceLimitExceeded);
    }
    let frequencies = (0..=intervals)
        .map(|index| index as f64 * step.0)
        .collect::<Vec<_>>();
    let response = ctle_frequency_response(config, &frequencies)?;
    let source_impulse = inverse_real_spectrum(
        &response.iter().map(|value| value.re).collect::<Vec<_>>(),
        &response.iter().map(|value| value.im).collect::<Vec<_>>(),
        fft_size,
    )?;
    let source_sample_interval_s = 0.5 / maximum.0;
    let source_sum = source_impulse.iter().sum::<f64>();
    // PyBERT's CTLE path uses `interp1d` without an explicit kind, whose
    // default is linear. Channel impulse resampling below is intentionally
    // cubic, but applying that rule here changes the equalizer waveform.
    let mut resampled = pinned_ctle_linear_resample_uniform(
        &source_impulse,
        source_sample_interval_s,
        target_sample_interval_s,
        target_sample_count,
    );
    let resampled_sum = resampled.iter().sum::<f64>();
    if !source_sum.is_finite() || !resampled_sum.is_finite() || resampled_sum == 0.0 {
        return Err(NativeSimulationError::Equalization(
            EqualizationError::InvalidCtleParameters,
        ));
    }
    let normalization = source_sum / resampled_sum;
    for sample in &mut resampled {
        *sample *= normalization;
    }
    let min_length = explicit_impulse_sample_count.unwrap_or(30 * samples_per_ui);
    let max_length = explicit_impulse_sample_count.unwrap_or(100 * samples_per_ui);
    Ok(trim_legacy_impulse(&resampled, min_length, max_length, 0))
}

/// The pinned analytic-CTLE path accepts the fractional final source interval
/// before its `floor` reaches the end.  Channel resampling intentionally has
/// a different out-of-range boundary, so this stays CTLE-private.
fn pinned_ctle_linear_resample_uniform(
    source: &[f64],
    source_sample_interval_s: f64,
    target_sample_interval_s: f64,
    target_len: usize,
) -> Vec<f64> {
    (0..target_len)
        .map(|index| {
            let position = index as f64 * target_sample_interval_s / source_sample_interval_s;
            let lower = position.floor() as usize;
            if lower >= source.len() {
                return 0.0;
            }
            let fraction = position - lower as f64;
            source[lower] * (1.0 - fraction)
                + source.get(lower + 1).copied().unwrap_or(0.0) * fraction
        })
        .collect()
}

/// Reproduce NumPy's bounded stop-exclusive ``arange(0, f_max + f_step,
/// f_step)`` point generation without a ratio round/ceil approximation.
fn legacy_arange_grid(
    step: f64,
    maximum: f64,
    max_total_samples: usize,
) -> Result<(usize, f64), NativeSimulationError> {
    if !step.is_finite() || step <= 0.0 || !maximum.is_finite() || maximum <= 0.0 {
        return Err(NativeSimulationError::UnsupportedChannel);
    }
    let stop = maximum + step;
    if !stop.is_finite() {
        return Err(NativeSimulationError::ResourceLimitExceeded);
    }
    let max_points = max_total_samples.saturating_div(2).saturating_add(1);
    let mut points = 0usize;
    while (points as f64 * step) < stop {
        points = points
            .checked_add(1)
            .ok_or(NativeSimulationError::ResourceLimitExceeded)?;
        if points > max_points {
            return Err(NativeSimulationError::ResourceLimitExceeded);
        }
    }
    let intervals = points
        .checked_sub(1)
        .ok_or(NativeSimulationError::UnsupportedChannel)?;
    if intervals == 0 {
        return Err(NativeSimulationError::UnsupportedChannel);
    }
    let effective_maximum = intervals as f64 * step;
    if !effective_maximum.is_finite() {
        return Err(NativeSimulationError::ResourceLimitExceeded);
    }
    Ok((intervals, effective_maximum))
}

struct MetallicLineImpulse {
    impulse: Vec<f64>,
    legacy: Option<LegacyChannelFrequencyResponse>,
}

struct LegacyChannelFrequencyResponse {
    frequency_hz: Vec<f64>,
    raw: Vec<num_complex::Complex64>,
    terminated: Vec<num_complex::Complex64>,
    trimmed: Vec<num_complex::Complex64>,
}

struct LegacyStageFrequencyResponses {
    tx: Vec<num_complex::Complex64>,
    tx_out: Vec<num_complex::Complex64>,
    ctle: Vec<num_complex::Complex64>,
    ctle_out: Vec<num_complex::Complex64>,
    dfe: Vec<num_complex::Complex64>,
    dfe_out: Vec<num_complex::Complex64>,
}

fn legacy_stage_frequency_responses(
    tx_impulse: &[f64],
    tx_channel_impulse: &[f64],
    ctle_impulse: &[f64],
    rx_ffe_impulse: &[f64],
    dfe_taps: &[f64],
    samples_per_ui: usize,
    frequencies_hz: &[f64],
    sample_interval_s: f64,
    max_fft_size: usize,
) -> Result<LegacyStageFrequencyResponses, NativeSimulationError> {
    let response_length = tx_channel_impulse.len();
    let ctle_out_impulse =
        causal_convolve_truncated(tx_channel_impulse, ctle_impulse, response_length)?;
    let rx_ffe_out_impulse =
        causal_convolve_truncated(&ctle_out_impulse, rx_ffe_impulse, response_length)?;
    let mut dfe_impulse = vec![1.0];
    dfe_impulse.extend(std::iter::repeat_n(0.0, samples_per_ui.saturating_sub(1)));
    for &tap in dfe_taps {
        dfe_impulse.push(-tap);
        dfe_impulse.extend(std::iter::repeat_n(0.0, samples_per_ui.saturating_sub(1)));
    }
    let dfe_out_impulse =
        causal_convolve_truncated(&rx_ffe_out_impulse, &dfe_impulse, response_length)?;
    Ok(LegacyStageFrequencyResponses {
        tx: legacy_frequency_response_from_impulse(
            tx_impulse,
            frequencies_hz,
            sample_interval_s,
            max_fft_size,
        )?,
        tx_out: legacy_frequency_response_from_impulse(
            tx_channel_impulse,
            frequencies_hz,
            sample_interval_s,
            max_fft_size,
        )?,
        ctle: legacy_frequency_response_from_impulse(
            ctle_impulse,
            frequencies_hz,
            sample_interval_s,
            max_fft_size,
        )?,
        ctle_out: legacy_frequency_response_from_impulse(
            &ctle_out_impulse,
            frequencies_hz,
            sample_interval_s,
            max_fft_size,
        )?,
        dfe: legacy_frequency_response_from_impulse(
            &dfe_impulse,
            frequencies_hz,
            sample_interval_s,
            max_fft_size,
        )?,
        dfe_out: legacy_frequency_response_from_impulse(
            &dfe_out_impulse,
            frequencies_hz,
            sample_interval_s,
            max_fft_size,
        )?,
    })
}

fn legacy_frequency_response_from_impulse(
    impulse: &[f64],
    frequencies_hz: &[f64],
    sample_interval_s: f64,
    max_fft_size: usize,
) -> Result<Vec<num_complex::Complex64>, NativeSimulationError> {
    let frequency_step_hz = *frequencies_hz
        .get(1)
        .ok_or(NativeSimulationError::UnsupportedChannel)?;
    let fft_size = validate_legacy_stage_frequency_grid(
        frequency_step_hz,
        *frequencies_hz
            .last()
            .ok_or(NativeSimulationError::LegacyStageFrequencyOutOfRange)?,
        sample_interval_s,
        max_fft_size,
    )?;
    let mut padded = impulse[..impulse.len().min(fft_size)].to_vec();
    padded.resize(fft_size, 0.0);
    let (real, imaginary) = forward_real_spectrum(&padded)?;
    let source_frequency_step_hz = 1.0 / (fft_size as f64 * sample_interval_s);
    Ok(frequencies_hz
        .iter()
        .map(|&frequency_hz| {
            let position = frequency_hz / source_frequency_step_hz;
            let lower = position.floor() as usize;
            let fraction = position - lower as f64;
            let lower_value = num_complex::Complex64::new(real[lower], imaginary[lower]);
            let upper_value = real
                .get(lower + 1)
                .zip(imaginary.get(lower + 1))
                .map_or(lower_value, |(&re, &im)| {
                    num_complex::Complex64::new(re, im)
                });
            lower_value * (1.0 - fraction) + upper_value * fraction
        })
        .collect())
}

fn validate_legacy_stage_frequency_grid(
    frequency_step_hz: f64,
    maximum_frequency_hz: f64,
    sample_interval_s: f64,
    max_fft_size: usize,
) -> Result<usize, NativeSimulationError> {
    if maximum_frequency_hz > 0.5 / sample_interval_s {
        return Err(NativeSimulationError::LegacyStageFrequencyOutOfRange);
    }
    let fft_size = (1.0 / (frequency_step_hz * sample_interval_s) + 0.5) as usize;
    if fft_size > max_fft_size {
        return Err(NativeSimulationError::ResourceLimitExceeded);
    }
    Ok(fft_size)
}

fn legacy_frequency_telemetry_resource_bytes(
    stage_fft_size: usize,
    frequency_bins: usize,
) -> Result<usize, NativeSimulationError> {
    let f64_bytes = std::mem::size_of::<f64>();
    let complex_bytes = std::mem::size_of::<num_complex::Complex64>();
    // A stage transform temporarily holds the padded real waveform, an FFT
    // complex working buffer, split source bins, and planner scratch. The
    // persistent telemetry covers three channel responses, six stage
    // responses, their split output arrays, and the shared frequency vector.
    let stage_fft_working_bytes = stage_fft_size
        .checked_mul(f64_bytes * 5)
        .ok_or(NativeSimulationError::ResourceLimitExceeded)?;
    let channel_response_bytes = frequency_bins
        .checked_mul(3)
        .and_then(|count| count.checked_mul(complex_bytes + 2 * f64_bytes))
        .ok_or(NativeSimulationError::ResourceLimitExceeded)?;
    let stage_response_bytes = frequency_bins
        .checked_mul(6)
        .and_then(|count| count.checked_mul(complex_bytes + 2 * f64_bytes))
        .ok_or(NativeSimulationError::ResourceLimitExceeded)?;
    let frequency_bytes = frequency_bins
        .checked_mul(f64_bytes)
        .ok_or(NativeSimulationError::ResourceLimitExceeded)?;
    stage_fft_working_bytes
        .checked_add(channel_response_bytes)
        .and_then(|bytes| bytes.checked_add(stage_response_bytes))
        .and_then(|bytes| bytes.checked_add(frequency_bytes))
        .ok_or(NativeSimulationError::ResourceLimitExceeded)
}

fn metallic_line_impulse(
    channel: &MetallicLineChannelV1,
    target_sample_count: usize,
    target_sample_interval_s: f64,
    samples_per_ui: usize,
    max_total_samples: usize,
) -> Result<MetallicLineImpulse, NativeSimulationError> {
    let (fft_size, frequency_step_hz, source_sample_interval_s, trim_to_legacy_window) =
        match (channel.frequency_step_hz, channel.frequency_max_hz) {
            (Some(step), Some(maximum)) => {
                let (intervals, effective_maximum) =
                    legacy_arange_grid(step.0, maximum.0, max_total_samples)?;
                let fft_size = intervals
                    .checked_mul(2)
                    .ok_or(NativeSimulationError::ResourceLimitExceeded)?;
                // The actual last materialized bin, rather than the requested
                // endpoint, determines both the source time scale and this
                // native IFFT Nyquist safety check.
                if effective_maximum > 0.5 / target_sample_interval_s {
                    return Err(NativeSimulationError::LegacyStageFrequencyOutOfRange);
                }
                (fft_size, step.0, 0.5 / effective_maximum, true)
            }
            (None, None) => (
                target_sample_count,
                1.0 / (target_sample_count as f64 * target_sample_interval_s),
                target_sample_interval_s,
                false,
            ),
            _ => return Err(NativeSimulationError::UnsupportedChannel),
        };
    let frequency_bins = fft_size / 2 + 1;
    let angular_frequencies = (0..frequency_bins)
        .map(|index| std::f64::consts::TAU * index as f64 * frequency_step_hz)
        .collect::<Vec<_>>();
    let (gamma, characteristic_impedance) = calculate_metallic_line(
        MetallicLineConfig {
            skin_effect_resistance_ohm_per_m: channel.skin_effect_resistance_ohm_per_m,
            crossover_angular_frequency_rad_per_s: channel.crossover_angular_frequency_rad_per_s,
            dc_resistance_ohm_per_m: channel.dc_resistance_ohm_per_m,
            characteristic_impedance_ohm: channel.characteristic_impedance.0,
            propagation_velocity_m_per_s: channel.propagation_velocity_m_per_s,
            loss_tangent: channel.loss_tangent,
        },
        &angular_frequencies,
    )?;
    let raw = gamma
        .iter()
        .map(|value| (-value * channel.length_m).exp())
        .collect::<Vec<_>>();
    let terminated = calculate_legacy_s_parameter_transfer(
        &gamma,
        &characteristic_impedance,
        &angular_frequencies,
        channel.length_m,
        TerminationConfig {
            source_resistance_ohm: channel.source_impedance.0,
            source_capacitance_f: channel.source_capacitance_f,
            load_resistance_ohm: channel.load_impedance.0,
            load_capacitance_f: channel.load_capacitance_f,
        },
    );
    // The legacy terminated response is published before the optional window;
    // only the windowed copy is transformed into the time-domain impulse.
    let mut loaded = terminated.clone();
    if channel.apply_raised_cosine_window {
        let bin_count = loaded.len() as f64;
        for (index, value) in loaded.iter_mut().enumerate() {
            let weight = (std::f64::consts::PI * index as f64 / bin_count)
                .cos()
                .mul_add(0.5, 0.5);
            *value *= weight;
        }
    }
    let real = loaded.iter().map(|value| value.re).collect::<Vec<_>>();
    let imag = loaded.iter().map(|value| value.im).collect::<Vec<_>>();
    let impulse = inverse_real_spectrum(&real, &imag, fft_size)?;
    if !trim_to_legacy_window {
        return Ok(MetallicLineImpulse {
            impulse,
            legacy: None,
        });
    }

    let scale = target_sample_interval_s / source_sample_interval_s;
    let resampled = cubic_resample_uniform(
        &impulse,
        source_sample_interval_s,
        target_sample_interval_s,
        target_sample_count,
    )
    .into_iter()
    .map(|sample| sample * scale)
    .collect::<Vec<_>>();
    let explicit_length = channel
        .impulse_length
        .map(|value| (value.0 / target_sample_interval_s).floor().max(1.0) as usize);
    let min_length = explicit_length.unwrap_or_else(|| 20 * samples_per_ui);
    let max_length = explicit_length.unwrap_or_else(|| 100 * samples_per_ui);
    let impulse = trim_legacy_impulse(&resampled, min_length, max_length, 1);
    let source_grid = cubic_resample_uniform(
        &impulse,
        target_sample_interval_s,
        source_sample_interval_s,
        fft_size,
    );
    let (trimmed_re, trimmed_im) = forward_real_spectrum(&source_grid)?;
    let scale = source_sample_interval_s / target_sample_interval_s;
    let trimmed = trimmed_re
        .into_iter()
        .zip(trimmed_im)
        .map(|(re, im)| num_complex::Complex64::new(re * scale, im * scale))
        .collect();
    Ok(MetallicLineImpulse {
        impulse,
        legacy: Some(LegacyChannelFrequencyResponse {
            frequency_hz: (0..frequency_bins)
                .map(|index| index as f64 * frequency_step_hz)
                .collect(),
            raw,
            terminated,
            trimmed,
        }),
    })
}

/// Reproduce PyBERT's `skrf.Network(...).renormalize(...).s21` calculation
/// for the analytic line. The public `calculate_loaded_transfer` remains the
/// historical `calc_G` primitive; the full pipeline instead needs the
/// power-wave S-parameter normalization used by `calc_chnl_h`.
fn calculate_legacy_s_parameter_transfer(
    gamma: &[num_complex::Complex64],
    characteristic_impedance: &[num_complex::Complex64],
    angular_frequencies: &[f64],
    length_m: f64,
    termination: TerminationConfig,
) -> Vec<num_complex::Complex64> {
    gamma
        .iter()
        .zip(characteristic_impedance)
        .zip(angular_frequencies)
        .map(
            |((&gamma, &characteristic_impedance), &angular_frequency)| {
                let propagation = (-gamma * length_m).exp();
                let initial_scattering = [
                    num_complex::Complex64::new(0.0, 0.0),
                    propagation,
                    propagation,
                    num_complex::Complex64::new(0.0, 0.0),
                ];
                let line_impedance = s_to_z_power(
                    initial_scattering,
                    [characteristic_impedance, characteristic_impedance],
                );
                // PyBERT first normalizes the matched line to the real driver
                // impedance, then applies the complex source/load references.
                let source_reference =
                    num_complex::Complex64::new(termination.source_resistance_ohm, 0.0);
                let driver_normalized =
                    z_to_s_power(line_impedance, [source_reference, source_reference]);
                let driver_impedance =
                    s_to_z_power(driver_normalized, [source_reference, source_reference]);
                let source_impedance = parallel_rc_impedance(
                    termination.source_resistance_ohm,
                    termination.source_capacitance_f,
                    angular_frequency,
                );
                let load_impedance = parallel_rc_impedance(
                    termination.load_resistance_ohm,
                    termination.load_capacitance_f,
                    angular_frequency,
                );
                let terminated = z_to_s_power(driver_impedance, [source_impedance, load_impedance]);
                terminated[2] * (load_impedance / source_impedance).sqrt()
            },
        )
        .collect()
}

fn parallel_rc_impedance(
    resistance_ohm: f64,
    capacitance_f: f64,
    angular_frequency: f64,
) -> num_complex::Complex64 {
    let resistance = num_complex::Complex64::new(resistance_ohm, 0.0);
    resistance
        / (num_complex::Complex64::new(1.0, angular_frequency * resistance_ohm * capacitance_f))
}

type ComplexMatrix2 = [num_complex::Complex64; 4];

fn s_to_z_power(
    scattering: ComplexMatrix2,
    references: [num_complex::Complex64; 2],
) -> ComplexMatrix2 {
    let identity = complex_identity();
    let factors = power_wave_factors(references);
    let reference_matrix = complex_diagonal(references);
    let lhs = legacy_power_wave_nudge_v1(complex_multiply(
        complex_subtract(identity, scattering),
        factors,
    ));
    let rhs = complex_multiply(
        complex_add(
            complex_multiply(scattering, reference_matrix),
            complex_diagonal([references[0].conj(), references[1].conj()]),
        ),
        factors,
    );
    complex_solve(lhs, rhs)
}

/// Match scikit-rf's `nudge_eig` safeguard in the symmetric two-port
/// power-wave conversion used by PyBERT's legacy line path.
///
/// In this path both reference impedances are identical, so `(I - S) F` is
/// symmetric and its eigenvectors are the fixed even/odd modes. scikit-rf
/// floors a near-zero eigenvalue before solving; without that floor the DC
/// bin can grow enough to perturb the downstream DFE decisions.
fn legacy_power_wave_nudge_v1(matrix: ComplexMatrix2) -> ComplexMatrix2 {
    const EIGENVALUE_CONDITION: f64 = 1.0e-9;
    const MINIMUM_EIGENVALUE: f64 = 1.0e-12;

    let scale = matrix.iter().map(|value| value.norm()).fold(1.0, f64::max);
    let symmetry_tolerance = f64::EPSILON * scale * 16.0;
    if (matrix[0] - matrix[3]).norm() > symmetry_tolerance
        || (matrix[1] - matrix[2]).norm() > symmetry_tolerance
    {
        return matrix;
    }

    let eigenvalue_floor = (EIGENVALUE_CONDITION
        * (matrix[0] + matrix[1])
            .norm()
            .max((matrix[0] - matrix[1]).norm()))
    .max(MINIMUM_EIGENVALUE);
    let even_mode = nudge_legacy_power_wave_eigenvalue(matrix[0] + matrix[1], eigenvalue_floor);
    let odd_mode = nudge_legacy_power_wave_eigenvalue(matrix[0] - matrix[1], eigenvalue_floor);
    let half = num_complex::Complex64::new(0.5, 0.0);
    [
        (even_mode + odd_mode) * half,
        (even_mode - odd_mode) * half,
        (even_mode - odd_mode) * half,
        (even_mode + odd_mode) * half,
    ]
}

fn nudge_legacy_power_wave_eigenvalue(
    eigenvalue: num_complex::Complex64,
    floor: f64,
) -> num_complex::Complex64 {
    if eigenvalue.norm() < floor {
        num_complex::Complex64::new(floor, 0.0)
    } else {
        eigenvalue
    }
}

fn z_to_s_power(
    impedance: ComplexMatrix2,
    references: [num_complex::Complex64; 2],
) -> ComplexMatrix2 {
    let factors = power_wave_factors(references);
    let reference_matrix = complex_diagonal(references);
    let conjugate_reference = complex_diagonal([references[0].conj(), references[1].conj()]);
    let lhs = complex_multiply(factors, complex_add(impedance, reference_matrix));
    let rhs = complex_multiply(factors, complex_subtract(impedance, conjugate_reference));
    complex_right_solve(lhs, rhs)
}

fn power_wave_factors(references: [num_complex::Complex64; 2]) -> ComplexMatrix2 {
    complex_diagonal([
        num_complex::Complex64::new(1.0 / (2.0 * references[0].re.sqrt()), 0.0),
        num_complex::Complex64::new(1.0 / (2.0 * references[1].re.sqrt()), 0.0),
    ])
}

fn complex_identity() -> ComplexMatrix2 {
    complex_diagonal([
        num_complex::Complex64::new(1.0, 0.0),
        num_complex::Complex64::new(1.0, 0.0),
    ])
}

fn complex_diagonal(values: [num_complex::Complex64; 2]) -> ComplexMatrix2 {
    [
        values[0],
        num_complex::Complex64::new(0.0, 0.0),
        num_complex::Complex64::new(0.0, 0.0),
        values[1],
    ]
}

fn complex_add(left: ComplexMatrix2, right: ComplexMatrix2) -> ComplexMatrix2 {
    std::array::from_fn(|index| left[index] + right[index])
}

fn complex_subtract(left: ComplexMatrix2, right: ComplexMatrix2) -> ComplexMatrix2 {
    std::array::from_fn(|index| left[index] - right[index])
}

fn complex_multiply(left: ComplexMatrix2, right: ComplexMatrix2) -> ComplexMatrix2 {
    [
        left[0] * right[0] + left[1] * right[2],
        left[0] * right[1] + left[1] * right[3],
        left[2] * right[0] + left[3] * right[2],
        left[2] * right[1] + left[3] * right[3],
    ]
}

/// Solve `coefficients * result = constants` using a partial-pivot LU step.
/// This matches the solve ordering used by scikit-rf more closely than an
/// explicit determinant inverse on the deliberately nudged DC matrix.
fn complex_solve(coefficients: ComplexMatrix2, constants: ComplexMatrix2) -> ComplexMatrix2 {
    let (upper_left, upper_right, lower_left, lower_right, top_constants, bottom_constants) =
        if coefficients[0].norm() >= coefficients[2].norm() {
            (
                coefficients[0],
                coefficients[1],
                coefficients[2],
                coefficients[3],
                [constants[0], constants[1]],
                [constants[2], constants[3]],
            )
        } else {
            (
                coefficients[2],
                coefficients[3],
                coefficients[0],
                coefficients[1],
                [constants[2], constants[3]],
                [constants[0], constants[1]],
            )
        };
    let multiplier = lower_left / upper_left;
    let diagonal = lower_right - multiplier * upper_right;
    let reduced_constants = [
        bottom_constants[0] - multiplier * top_constants[0],
        bottom_constants[1] - multiplier * top_constants[1],
    ];
    let lower_solution = [
        reduced_constants[0] / diagonal,
        reduced_constants[1] / diagonal,
    ];
    [
        (top_constants[0] - upper_right * lower_solution[0]) / upper_left,
        (top_constants[1] - upper_right * lower_solution[1]) / upper_left,
        lower_solution[0],
        lower_solution[1],
    ]
}

/// Solve `result * coefficients = constants` by transposing the two-right-
/// hand-side partial-pivot solve. This is scikit-rf's `rsolve` ordering.
fn complex_right_solve(coefficients: ComplexMatrix2, constants: ComplexMatrix2) -> ComplexMatrix2 {
    complex_transpose_conjugate(complex_solve(
        complex_transpose_conjugate(coefficients),
        complex_transpose_conjugate(constants),
    ))
}

fn complex_transpose_conjugate(matrix: ComplexMatrix2) -> ComplexMatrix2 {
    [
        matrix[0].conj(),
        matrix[2].conj(),
        matrix[1].conj(),
        matrix[3].conj(),
    ]
}

/// Match PyBERT's uniformly-spaced cubic `interp1d` stage without borrowing a
/// Python/Scipy runtime. The not-a-knot spline keeps the same endpoint model.
pub(crate) fn cubic_resample_uniform(
    source: &[f64],
    source_sample_interval_s: f64,
    target_sample_interval_s: f64,
    target_len: usize,
) -> Vec<f64> {
    if source.len() < 4 {
        return linear_resample_uniform(
            source,
            source_sample_interval_s,
            target_sample_interval_s,
            target_len,
        );
    }
    let second_derivatives = not_a_knot_second_derivatives(source, source_sample_interval_s);
    (0..target_len)
        .map(|index| {
            let position = index as f64 * target_sample_interval_s / source_sample_interval_s;
            if position < 0.0 || position > (source.len() - 1) as f64 {
                return 0.0;
            }
            let interval = position.floor() as usize;
            if interval >= source.len() - 1 {
                return source[source.len() - 1];
            }
            let fraction = position - interval as f64;
            let left = 1.0 - fraction;
            left * source[interval]
                + fraction * source[interval + 1]
                + ((left.powi(3) - left) * second_derivatives[interval]
                    + (fraction.powi(3) - fraction) * second_derivatives[interval + 1])
                    * source_sample_interval_s.powi(2)
                    / 6.0
        })
        .collect()
}

fn linear_resample_uniform(
    source: &[f64],
    source_sample_interval_s: f64,
    target_sample_interval_s: f64,
    target_len: usize,
) -> Vec<f64> {
    if source.is_empty() {
        return vec![0.0; target_len];
    }
    (0..target_len)
        .map(|index| {
            let target_time = index as f64 * target_sample_interval_s;
            let source_end = (source.len() - 1) as f64 * source_sample_interval_s;
            if target_time < 0.0 || target_time > source_end {
                return 0.0;
            }
            let position = target_time / source_sample_interval_s;
            let lower = position.floor() as usize;
            let fraction = position - lower as f64;
            source[lower] * (1.0 - fraction)
                + source.get(lower + 1).copied().unwrap_or(0.0) * fraction
        })
        .collect()
}

fn not_a_knot_second_derivatives(values: &[f64], spacing: f64) -> Vec<f64> {
    let length = values.len();
    let slope_change = |index: usize| {
        (values[index + 1] - 2.0 * values[index] + values[index - 1]) / spacing.powi(2)
    };
    let mut result = vec![0.0; length];
    result[1] = slope_change(1);
    result[length - 2] = slope_change(length - 2);

    let unknown_count = length - 4;
    if unknown_count > 0 {
        let mut diagonal = vec![4.0; unknown_count];
        let upper = vec![1.0; unknown_count.saturating_sub(1)];
        let mut rhs = (2..length - 2)
            .map(|index| 6.0 * slope_change(index))
            .collect::<Vec<_>>();
        rhs[0] -= result[1];
        rhs[unknown_count - 1] -= result[length - 2];
        for index in 1..unknown_count {
            let factor = 1.0 / diagonal[index - 1];
            diagonal[index] -= factor * upper[index - 1];
            rhs[index] -= factor * rhs[index - 1];
        }
        result[length - 3] = rhs[unknown_count - 1] / diagonal[unknown_count - 1];
        for offset in (0..unknown_count - 1).rev() {
            result[offset + 2] =
                (rhs[offset] - upper[offset] * result[offset + 3]) / diagonal[offset];
        }
    }
    result[0] = 2.0 * result[1] - result[2];
    result[length - 1] = 2.0 * result[length - 2] - result[length - 3];
    result
}

fn trim_legacy_impulse(
    values: &[f64],
    min_length: usize,
    max_length: usize,
    front_porch: usize,
) -> Vec<f64> {
    trim_legacy_impulse_with_start(values, min_length, max_length, front_porch).0
}

/// Apply PyBERT's bounded impulse window and retain the selected source index
/// for callers that need to preserve the non-zero trim origin.
pub(crate) fn trim_legacy_impulse_with_start(
    values: &[f64],
    min_length: usize,
    max_length: usize,
    front_porch: usize,
) -> (Vec<f64>, isize) {
    let mut impulse = values.to_vec();
    let half_length = impulse.len() / 2;
    let maximum_index = first_maximum_index(&impulse);
    if maximum_index < impulse.len() / 4 {
        impulse.rotate_right(half_length);
    }
    let maximum_index = first_maximum_index(&impulse);
    let derivative_energy = impulse
        .windows(2)
        .map(|pair| (pair[1] - pair[0]).powi(2))
        .collect::<Vec<_>>();
    let total_energy = derivative_energy.iter().sum::<f64>();
    let beginning_energy = 0.0005 * total_energy;
    let ending_energy = 0.9995 * total_energy;
    let mut beginning = 0;
    let mut accumulated = 0.0;
    while beginning < derivative_energy.len() && accumulated < beginning_energy {
        accumulated += derivative_energy[beginning];
        beginning += 1;
    }
    let mut ending = beginning;
    while ending < derivative_energy.len() && accumulated < ending_energy {
        accumulated += derivative_energy[ending];
        ending += 1;
    }
    if maximum_index.saturating_sub(beginning) < front_porch {
        beginning = maximum_index.saturating_sub(front_porch);
    }
    if ending.saturating_sub(beginning) < min_length {
        ending = beginning.saturating_add(min_length).min(impulse.len());
    }
    if ending.saturating_sub(beginning) > max_length {
        ending = beginning.saturating_add(max_length).min(impulse.len());
    }
    let start = beginning.min(impulse.len());
    (
        impulse[start..ending.min(impulse.len())].to_vec(),
        start as isize - half_length as isize,
    )
}

fn first_maximum_index(values: &[f64]) -> usize {
    let mut maximum = 0;
    for index in 1..values.len() {
        if values[index] > values[maximum] {
            maximum = index;
        }
    }
    maximum
}

#[cfg(test)]
mod tests {
    use super::{
        ComplexMatrix2, complex_multiply, complex_right_solve, complex_solve, first_maximum_index,
        legacy_arange_grid, legacy_ctle_impulse, legacy_power_wave_nudge_v1,
        linear_resample_uniform, simulate_native_v1_with_legacy_crossing_amplitude,
        trim_legacy_impulse_with_start,
    };
    use crate::{
        AnalysisConfigV1, ChannelInputV1, ChannelResponseV1, ContractError, CtleConfigV1,
        DfeConfigV1, FfeConfigV1, Hertz, ModulationV1, NativeCancellationToken, PatternV1,
        ResourceLimitsV1, RxConfigV1, SIMULATION_SCHEMA_V1, Seconds, SimulationInputV1, TimebaseV1,
        TxConfigV1, Volts,
    };
    use num_complex::Complex64;

    fn valid_legacy_crossing_input() -> SimulationInputV1 {
        SimulationInputV1 {
            schema: SIMULATION_SCHEMA_V1.into(),
            run_id: "legacy-crossing-test".into(),
            modulation: ModulationV1::DuoBinary,
            pattern: PatternV1::Prbs { order: 7, seed: 17 },
            timebase: TimebaseV1 {
                sample_interval: Seconds(1.0e-12),
                samples_per_ui: 2,
                data_rate: Hertz(5.0e9),
                nbits: 1_000,
            },
            channel: ChannelInputV1::ImpulseResponse(ChannelResponseV1 {
                sample_interval: Seconds(1.0e-12),
                impulse_response_volts_per_second: vec![1.0e12],
                source_impedance: crate::Ohms(50.0),
                load_impedance: crate::Ohms(50.0),
            }),
            tx: TxConfigV1::default(),
            rx: RxConfigV1 {
                native_ctle_enabled: false,
                ctle: None,
                ffe: FfeConfigV1::default(),
                dfe_taps: 0,
                dfe: Some(DfeConfigV1 {
                    gain: 0.1,
                    decision_scaler: Volts(0.5),
                    n_ave: 4,
                    delta_t: Seconds(1.0e-13),
                    alpha: 0.01,
                    n_lock_ave: 4,
                    rel_lock_tol: 0.1,
                    lock_sustain: 2,
                    ideal: true,
                    bandwidth: Hertz(12.0e9),
                    use_agc: true,
                    agc_n_ave: 4,
                    tap_limits: None,
                }),
                viterbi_enabled: false,
                viterbi: None,
            },
            analysis: AnalysisConfigV1 {
                statistical_eye: None,
                include_jitter: true,
                include_bathtub: false,
                ber_eye_bits: None,
                jitter_eye_uis: None,
                jitter_rel_thresh: None,
            },
            limits: ResourceLimitsV1::default(),
            external_models: Vec::new(),
            legacy_options: Default::default(),
        }
    }

    #[test]
    fn legacy_crossing_amplitude_requires_a_verified_dfe_scaler() {
        let cancellation = NativeCancellationToken::default();
        let mut missing_dfe = valid_legacy_crossing_input();
        missing_dfe.rx.dfe = None;
        assert_eq!(
            simulate_native_v1_with_legacy_crossing_amplitude(&missing_dfe, &cancellation, 0.5,)
                .unwrap_err(),
            super::NativeSimulationError::Contract(ContractError::InvalidDfe)
        );

        let input = valid_legacy_crossing_input();
        for invalid_scaler in [0.0, f64::NAN] {
            assert_eq!(
                simulate_native_v1_with_legacy_crossing_amplitude(
                    &input,
                    &cancellation,
                    invalid_scaler,
                )
                .unwrap_err(),
                super::NativeSimulationError::Contract(ContractError::InvalidDfe)
            );
        }

        let mut mismatched_dfe = valid_legacy_crossing_input();
        mismatched_dfe
            .rx
            .dfe
            .as_mut()
            .expect("test DFE")
            .decision_scaler = Volts(0.75);
        assert_eq!(
            simulate_native_v1_with_legacy_crossing_amplitude(&mismatched_dfe, &cancellation, 0.5,)
                .unwrap_err(),
            super::NativeSimulationError::Contract(ContractError::InvalidDfe)
        );
    }

    #[test]
    fn linear_resample_uniform_has_bounded_endpoint_semantics() {
        assert_eq!(
            linear_resample_uniform(&[], 1.0, 1.0, 3),
            vec![0.0, 0.0, 0.0]
        );

        let exact = linear_resample_uniform(&[2.0, 6.0, 10.0], 1.0, 0.5, 6);
        assert_eq!(exact, vec![2.0, 4.0, 6.0, 8.0, 10.0, 0.0]);

        let just_before = linear_resample_uniform(&[0.0, 10.0, 20.0], 1.0, 1.0 - f64::EPSILON, 4);
        assert!(just_before[2] > 19.99999999999999);
        assert_eq!(just_before[3], 0.0);

        let source = vec![1.0; 8];
        let rounded_past_end = linear_resample_uniform(&source, 1.0e-15, 7.0e-15 / 13.0, 14);
        assert_eq!(rounded_past_end[13], 0.0);
    }

    #[test]
    fn legacy_power_wave_nudge_v1_floors_a_near_singular_odd_mode() {
        let matrix: ComplexMatrix2 = [
            Complex64::new(1.0, 0.0),
            Complex64::new(1.0 - 1.0e-15, 0.0),
            Complex64::new(1.0 - 1.0e-15, 0.0),
            Complex64::new(1.0, 0.0),
        ];

        let nudged = legacy_power_wave_nudge_v1(matrix);

        assert!(((nudged[0] + nudged[1]).re - 2.0).abs() < 1.0e-12);
        assert!(((nudged[0] - nudged[1]).re - 2.0e-9).abs() < 1.0e-15);
        assert_eq!(nudged[0], nudged[3]);
        assert_eq!(nudged[1], nudged[2]);
    }

    #[test]
    fn trim_legacy_impulse_uses_first_peak_for_ties_and_zero_inputs() {
        let tied = [0.0, 1.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0];
        let (trimmed, start) = trim_legacy_impulse_with_start(&tied, 2, 2, 1);
        assert_eq!(start, 0);
        assert_eq!(trimmed, vec![0.0, 1.0]);

        let flat = [0.0; 8];
        let (trimmed, start) = trim_legacy_impulse_with_start(&flat, 3, 3, 1);
        assert_eq!(start, -4);
        assert_eq!(trimmed, vec![0.0, 0.0, 0.0]);
        assert_eq!(first_maximum_index(&[-0.0, 0.0, 0.0]), 0);
    }

    #[test]
    fn legacy_ctle_grid_matches_pinned_round_endpoint_and_payload() {
        let config = CtleConfigV1 {
            bandwidth: Hertz(12.0e9),
            peak_frequency: Hertz(5.0e9),
            peak_magnitude_db: 1.7,
            frequency_step_hz: Some(Hertz(3.0e9)),
            frequency_max_hz: Some(Hertz(10.0e9)),
            impulse_response_v_per_v: None,
        };
        let impulse = legacy_ctle_impulse(&config, 16, Seconds(1.0e-12).0, 4, 1024, Some(8))
            .expect("non-integral PyBERT arange endpoint is portable");
        let expected = [
            0.05905512979846243,
            0.05796525968692895,
            0.05687538957539548,
            0.055785519463862,
            0.054695649352328526,
            0.05360577924079505,
            0.052515909129261566,
            0.0688639608022637,
        ];
        assert_eq!(impulse.len(), expected.len());
        for (actual, expected) in impulse.iter().zip(expected) {
            assert!(
                (actual - expected).abs() < 1.0e-12,
                "{actual} != {expected}"
            );
        }
    }

    #[test]
    fn legacy_ctle_resample_keeps_pinned_fractional_final_interval() {
        let config = CtleConfigV1 {
            bandwidth: Hertz(12.0e9),
            peak_frequency: Hertz(5.0e9),
            peak_magnitude_db: 1.7,
            frequency_step_hz: Some(Hertz(3.0e9)),
            frequency_max_hz: Some(Hertz(10.0e9)),
            impulse_response_v_per_v: None,
        };
        let impulse = legacy_ctle_impulse(&config, 320, Seconds(1.0e-12).0, 4, 1024, Some(8))
            .expect("legacy CTLE interpolation should remain bounded");
        let expected = [
            -0.0022800257079578124,
            -0.0022040248510258836,
            -0.002128023994093958,
            -0.002052023137162029,
            -0.001976022280230104,
            -0.0019000214232981786,
            -0.0018240205663662497,
            -0.0017480197094343244,
        ];
        assert_eq!(impulse.len(), expected.len());
        for (actual, expected) in impulse.iter().zip(expected) {
            assert!((actual - expected).abs() < 1.0e-8, "{actual} != {expected}");
        }
    }

    #[test]
    fn legacy_arange_grid_keeps_numpy_near_integral_stop_exclusive() {
        let step = 3.0e9;
        let maximum = step * (1.0 + 2.0e-16);
        assert_eq!(legacy_arange_grid(step, maximum, 1024).unwrap(), (1, step));
    }

    #[test]
    fn complex_solve_uses_a_stable_row_pivot_for_two_right_hand_sides() {
        let coefficients: ComplexMatrix2 = [
            Complex64::new(1.0, 0.0),
            Complex64::new(2.0, 0.0),
            Complex64::new(3.0, 0.0),
            Complex64::new(4.0, 0.0),
        ];
        let constants: ComplexMatrix2 = [
            Complex64::new(5.0, 0.0),
            Complex64::new(6.0, 0.0),
            Complex64::new(7.0, 0.0),
            Complex64::new(8.0, 0.0),
        ];

        let solution = complex_solve(coefficients, constants);
        let reconstructed = complex_multiply(coefficients, solution);

        for (actual, expected) in reconstructed.into_iter().zip(constants) {
            assert!((actual - expected).norm() < 1.0e-12);
        }
    }

    #[test]
    fn complex_right_solve_matches_the_scikit_rf_rsolve_contract() {
        let coefficients: ComplexMatrix2 = [
            Complex64::new(1.0, 0.0),
            Complex64::new(2.0, 1.0),
            Complex64::new(3.0, -1.0),
            Complex64::new(4.0, 0.0),
        ];
        let constants: ComplexMatrix2 = [
            Complex64::new(5.0, 0.0),
            Complex64::new(6.0, 0.0),
            Complex64::new(7.0, 0.0),
            Complex64::new(8.0, 0.0),
        ];

        let solution = complex_right_solve(coefficients, constants);
        let reconstructed = complex_multiply(solution, coefficients);

        for (actual, expected) in reconstructed.into_iter().zip(constants) {
            assert!((actual - expected).norm() < 1.0e-12);
        }
    }
}
