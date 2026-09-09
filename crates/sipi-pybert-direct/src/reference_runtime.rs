//! Independent portable reference pipeline for PB-04/PB-05.
//!
//! This module intentionally does not call `simulate_native_v1` (or the
//! composable candidate pipeline).  It is a small, explicit transcription of
//! the pure Python native path: pattern generation, sampled FFE/channel/CTLE,
//! noise, and the optional DFE/CDR stage are assembled here so auto fallback
//! and compare have a second execution graph.

use std::collections::BTreeMap;

use num_complex::{Complex, Complex64};
use rustfft::FftPlanner;

use crate::{
    ChannelInputV1, DfeConfig, DfeModulation, DfeRunOptions, EngineCapabilitiesV1, FecEncoder,
    FfeConfigV1, IsiDecodeConfig, MetallicLineConfig, ModulationV1, PatternV1, RunEventV1,
    RunStageV1, SIMULATION_SCHEMA_V1, SimulationInputV1, SimulationOutputV1, StatisticalEyeInputV1,
    SymbolModulation, TerminationConfig, assemble_tie_track, calculate_ber,
    calculate_data_dependent_jitter, calculate_dual_dirac_jitter, calculate_metallic_line,
    calculate_spectral_jitter, calculate_statistical_contours, calculate_statistical_eye,
    causal_convolve_truncated, convolve_truncated, ctle_impulse_response, decode_fec, decode_isi,
    ffe_impulse_response, find_crossings, generate_prbs_bits, inverse_real_spectrum, make_bathtub,
    modulate_bits, pulse_response, run_dfe, step_response,
};

const MAX_REFERENCE_SAMPLES: usize = 50_000_000;

pub fn simulate_portable_reference_v1(
    input: &SimulationInputV1,
) -> Result<SimulationOutputV1, String> {
    input.validate().map_err(|error| error.to_string())?;
    if !input.external_models.is_empty() || !input.legacy_options.is_empty() {
        return Err("portable reference does not consume external/legacy options".into());
    }
    let bits = match &input.pattern {
        PatternV1::Prbs { order, seed } => {
            let count = usize::try_from(input.timebase.nbits)
                .map_err(|_| "bit count exceeds reference budget")?;
            generate_prbs_bits(*order, *seed, count).map_err(|error| error.to_string())?
        }
        PatternV1::ExplicitBits { bits, .. } if !bits.is_empty() => {
            bits.iter().map(|bit| i32::from(*bit)).collect()
        }
        PatternV1::ExplicitBits { .. } => {
            return Err("portable reference requires explicit bits or PRBS values".into());
        }
    };
    let modulation = match input.modulation {
        ModulationV1::Nrz => (SymbolModulation::Nrz, DfeModulation::Nrz),
        ModulationV1::Pam4 => (SymbolModulation::Pam4, DfeModulation::Pam4),
        ModulationV1::DuoBinary => (SymbolModulation::DuoBinary, DfeModulation::DuoBinary),
    };
    let fec_enabled = input
        .rx
        .viterbi
        .as_ref()
        .is_some_and(|viterbi| input.rx.viterbi_enabled && viterbi.fec);
    let fec_encoded_bits = fec_enabled.then(|| {
        FecEncoder::new([0; 3])
            .encode(&bits)
            .into_iter()
            .flat_map(|(first, second)| [first, second])
            .collect::<Vec<_>>()
    });
    let modulation_bits = fec_encoded_bits.as_deref().unwrap_or(&bits);
    let symbols = modulate_bits(modulation_bits, modulation.0, input.tx.amplitude.0)
        .map_err(|error| error.to_string())?;
    let samples_per_ui = input.timebase.samples_per_ui as usize;
    let sample_count = symbols
        .len()
        .checked_mul(samples_per_ui)
        .ok_or("reference sample count overflow")?;
    if sample_count == 0 || sample_count > MAX_REFERENCE_SAMPLES {
        return Err("portable reference sample budget exceeded".into());
    }

    let channel = reference_channel(input, sample_count, samples_per_ui)?;
    let tx_weights = enabled_weights(&input.tx.ffe);
    let tx_impulse = ffe_impulse_response(&tx_weights, samples_per_ui, channel.len())
        .map_err(|error| error.to_string())?;
    let tx_channel_impulse = causal_convolve_truncated(&tx_impulse, &channel, channel.len())
        .map_err(|error| error.to_string())?;
    let tx_waveform = hold_symbols(&symbols, samples_per_ui);
    let mut rx_input = causal_convolve_truncated(&tx_waveform, &tx_channel_impulse, sample_count)
        .map_err(|error| error.to_string())?;

    let ctle_impulse = reference_ctle(input, sample_count)?;
    let mut receiver_noise = vec![0.0; sample_count];
    if let Some(noise) = &input.tx.additive_noise {
        if noise.samples_v.len() != sample_count {
            return Err("reference additive noise length does not match waveform".into());
        }
        receiver_noise.clone_from(&noise.samples_v);
    }
    if let Some(noise) = &input.tx.periodic_noise {
        let period = (1.0 / input.timebase.sample_interval.0 / noise.frequency.0)
            .round()
            .max(1.0) as usize;
        for (index, value) in receiver_noise.iter_mut().enumerate() {
            if index % period >= period / 2 {
                *value += noise.magnitude.0;
            }
        }
    }
    for (sample, noise) in rx_input.iter_mut().zip(&receiver_noise) {
        *sample += noise;
    }
    let ctle_output = causal_convolve_truncated(&rx_input, &ctle_impulse, sample_count)
        .map_err(|error| error.to_string())?;
    let rx_ffe_weights = enabled_weights(&input.rx.ffe);
    let rx_ffe_impulse = ffe_impulse_response(&rx_ffe_weights, samples_per_ui, sample_count)
        .map_err(|error| error.to_string())?;
    let rx_output = causal_convolve_truncated(&ctle_output, &rx_ffe_impulse, sample_count)
        .map_err(|error| error.to_string())?;

    let channel_output = causal_convolve_truncated(&tx_waveform, &channel, sample_count)
        .map_err(|error| error.to_string())?;
    let mut arrays = BTreeMap::from([
        (
            "time_s".into(),
            sample_times(sample_count, input.timebase.sample_interval.0),
        ),
        ("symbols_v".into(), symbols.clone()),
        ("tx_waveform_v".into(), tx_waveform.clone()),
        ("tx_impulse_v_per_v".into(), tx_impulse.clone()),
        ("channel_output_v".into(), channel_output.clone()),
        ("channel_impulse_v_per_v".into(), channel.clone()),
        (
            "tx_channel_impulse_v_per_v".into(),
            tx_channel_impulse.clone(),
        ),
        ("rx_filter_impulse_v_per_v".into(), ctle_impulse.clone()),
        ("rx_input_v".into(), rx_input.clone()),
        ("ctle_output_v".into(), ctle_output.clone()),
        ("rx_ffe_impulse_v_per_v".into(), rx_ffe_impulse.clone()),
        ("rx_output_v".into(), rx_output.clone()),
    ]);
    let rx_peak_abs = rx_output
        .iter()
        .fold(0.0_f64, |peak, value| peak.max(value.abs()));
    let rx_rms =
        (rx_output.iter().map(|value| value * value).sum::<f64>() / rx_output.len() as f64).sqrt();
    let mut metrics = BTreeMap::from([
        ("generated_bits".into(), bits.len() as f64),
        ("symbol_count".into(), symbols.len() as f64),
        ("tx_sample_count".into(), tx_waveform.len() as f64),
        ("rx_sample_count".into(), rx_output.len() as f64),
        ("rx_peak_abs_v".into(), rx_peak_abs),
        ("rx_rms_v".into(), rx_rms),
    ]);
    if let PatternV1::Prbs { seed, .. } = &input.pattern {
        metrics.insert("effective_prbs_seed".into(), *seed as f64);
    }
    if let Some(noise) = &input.tx.additive_noise {
        // Mirror the upstream BackendRunResult result_adapter: random_noise
        // remains a first-class array and additive_noise includes periodic
        // noise after its composition at the receiver input.
        arrays.insert("random_noise_v".into(), noise.samples_v.clone());
        arrays.insert("additive_noise_v".into(), receiver_noise.clone());
        metrics.insert(
            "random_noise_sample_count".into(),
            noise.samples_v.len() as f64,
        );
        if let Some(seed) = noise.effective_seed {
            metrics.insert("effective_noise_seed".into(), seed as f64);
        }
    }
    if let Some(noise) = &input.tx.periodic_noise {
        let periodic = reference_periodic_noise(
            noise.magnitude.0,
            noise.frequency.0,
            input.timebase.sample_interval.0,
            sample_count,
        )?;
        arrays.insert("periodic_noise_v".into(), periodic);
    }
    if input.tx.additive_noise.is_some() || input.tx.periodic_noise.is_some() {
        arrays.insert("receiver_input_noise_v".into(), receiver_noise.clone());
    }
    if let Some(encoded_bits) = &fec_encoded_bits {
        metrics.insert("fec_encoded_bit_count".into(), encoded_bits.len() as f64);
    }

    let dfe_result = if let Some(dfe) = input.rx.dfe.as_ref() {
        let times = sample_times(sample_count, input.timebase.sample_interval.0);
        let result = run_dfe(
            &times,
            &rx_output,
            DfeConfig {
                n_taps: input.rx.dfe_taps as usize,
                gain: dfe.gain,
                decision_scaler: dfe.decision_scaler.0,
                modulation: modulation.1,
                n_ave: dfe.n_ave as usize,
                limits: dfe.tap_limits.clone(),
            },
            crate::CdrConfig {
                delta_t: dfe.delta_t.0,
                alpha: dfe.alpha,
                ui: 1.0 / input.timebase.data_rate.0,
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
        .map_err(|error| error.to_string())?;
        metrics.extend([
            ("dfe_decision_count".into(), result.decisions.len() as f64),
            ("dfe_bit_count".into(), result.bits.len() as f64),
            (
                "dfe_tap_history_rows".into(),
                result.tap_weights.len() as f64,
            ),
            ("dfe_tap_history_columns".into(), input.rx.dfe_taps as f64),
            (
                "dfe_locked_sample_count".into(),
                result.lockeds.iter().filter(|locked| **locked).count() as f64,
            ),
        ]);
        if let Some(final_taps) = result.tap_weights.last() {
            for (index, tap) in final_taps.iter().enumerate() {
                metrics.insert(format!("dfe_final_tap_{index}_v"), *tap);
            }
        }
        arrays.extend([
            ("dfe_output_v".into(), result.dfe_out.clone()),
            ("dfe_clock_times_s".into(), result.clock_times.clone()),
            (
                "dfe_bits".into(),
                result.bits.iter().map(|bit| *bit as f64).collect(),
            ),
            ("dfe_decisions".into(), result.decisions.clone()),
            ("dfe_signal_samples_v".into(), result.signal_samples.clone()),
            ("dfe_ui_estimates_s".into(), result.ui_estimates.clone()),
            ("dfe_clocks".into(), result.clocks.clone()),
            (
                "dfe_locked".into(),
                result
                    .lockeds
                    .iter()
                    .map(|locked| f64::from(*locked))
                    .collect(),
            ),
            (
                "dfe_decision_scalers_v".into(),
                result.decision_scalers.clone(),
            ),
            (
                "dfe_tap_weights_v".into(),
                result.tap_weights.iter().flatten().copied().collect(),
            ),
        ]);
        Some(result)
    } else {
        None
    };
    let dfe_output = dfe_result
        .as_ref()
        .map_or_else(|| rx_output.clone(), |result| result.dfe_out.clone());

    let mut post_receiver_bits = dfe_result.as_ref().map(|result| result.bits.clone());
    if input.rx.viterbi_enabled {
        let dfe = dfe_result
            .as_ref()
            .ok_or("portable Viterbi requires the reference DFE stage")?;
        let viterbi = input
            .rx
            .viterbi
            .as_ref()
            .ok_or("portable Viterbi configuration is missing")?;
        if viterbi.fec {
            let chunks = dfe.bits.chunks_exact(2);
            if !chunks.remainder().is_empty() {
                return Err("portable FEC observations are incomplete".into());
            }
            let observations = chunks.map(|pair| (pair[0], pair[1])).collect::<Vec<_>>();
            let decoded = decode_fec(&observations, viterbi.state_symbols as usize)
                .map_err(|error| error.to_string())?;
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
                        .map(|state| *state as f64)
                        .collect(),
                ),
                (
                    "viterbi_bits".into(),
                    decoded.bits.iter().map(|bit| *bit as f64).collect(),
                ),
            ]);
            post_receiver_bits = Some(decoded.bits);
        } else {
            let pulse = reference_viterbi_pulse_response(
                &tx_channel_impulse,
                &ctle_impulse,
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
                        .ok_or("portable non-FEC Viterbi noise sigma is missing")?
                        .0,
                    max_states: (viterbi.max_states.min(input.limits.max_distribution_states))
                        as usize,
                },
            )
            .map_err(|error| error.to_string())?;
            let decoded_bits = decoded
                .symbols
                .iter()
                .flat_map(|symbol| reference_viterbi_symbol_bits(*symbol, &input.modulation))
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
                        .map(|state| *state as f64)
                        .collect(),
                ),
                ("viterbi_symbols_v".into(), decoded.symbols),
                (
                    "viterbi_bits".into(),
                    decoded_bits.iter().map(|bit| *bit as f64).collect(),
                ),
            ]);
            post_receiver_bits = Some(decoded_bits);
        }
    }

    if let Some(observed_bits) = post_receiver_bits.as_ref()
        && !observed_bits.is_empty()
    {
        let eye_bits = input.analysis.ber_eye_bits.unwrap_or(input.timebase.nbits);
        let eye_bits =
            usize::try_from(eye_bits).map_err(|_| "BER eye-bit count exceeds reference budget")?;
        if bits.iter().any(|bit| *bit != 0) {
            let ber =
                calculate_ber(&bits, observed_bits, eye_bits).map_err(|error| error.to_string())?;
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
                    bits.iter().map(|bit| *bit as f64).collect(),
                ),
                (
                    "ber_observed_bits".into(),
                    observed_bits.iter().map(|bit| *bit as f64).collect(),
                ),
                (
                    "ber_error_indices".into(),
                    ber.error_indices
                        .iter()
                        .map(|index| *index as f64)
                        .collect(),
                ),
                ("ber_auto_correlation".into(), ber.auto_correlation),
            ]);
        } else {
            metrics.insert("ber_available".into(), 0.0);
        }
    }

    if (input.analysis.include_jitter || input.analysis.include_bathtub)
        && let PatternV1::Prbs { order, .. } = &input.pattern
    {
        // The legacy Python model builds a two-tap duobinary ideal pulse for
        // crossing analysis.  Comparing against the held symbols loses the
        // zero crossings for otherwise valid Duo-binary requests.
        let jitter_ideal_waveform = if matches!(input.modulation, ModulationV1::DuoBinary) {
            let mut duobinary_impulse = vec![0.0; samples_per_ui.saturating_mul(2)];
            duobinary_impulse[0] = 0.5;
            duobinary_impulse[samples_per_ui] = 0.5;
            causal_convolve_truncated(&tx_waveform, &duobinary_impulse, sample_count)
                .map_err(|error| error.to_string())?
        } else {
            tx_waveform.clone()
        };
        reference_jitter(
            input,
            *order,
            &jitter_ideal_waveform,
            [
                ("chnl", channel_output.as_slice()),
                ("tx", rx_input.as_slice()),
                ("ctle", ctle_output.as_slice()),
                ("dfe", dfe_output.as_slice()),
            ],
            samples_per_ui,
            input.analysis.include_bathtub,
            &mut metrics,
            &mut arrays,
        )?;
    }

    if let Some(telemetry) =
        reference_legacy_channel(input, &channel, sample_count, samples_per_ui)?
    {
        arrays.extend([
            (
                "legacy_channel_frequency_hz".into(),
                telemetry.frequency_hz.clone(),
            ),
            (
                "legacy_channel_raw_re".into(),
                telemetry.raw.iter().map(|value| value.re).collect(),
            ),
            (
                "legacy_channel_raw_im".into(),
                telemetry.raw.iter().map(|value| value.im).collect(),
            ),
            (
                "legacy_channel_terminated_re".into(),
                telemetry.terminated.iter().map(|value| value.re).collect(),
            ),
            (
                "legacy_channel_terminated_im".into(),
                telemetry.terminated.iter().map(|value| value.im).collect(),
            ),
            (
                "legacy_channel_trimmed_re".into(),
                telemetry.trimmed.iter().map(|value| value.re).collect(),
            ),
            (
                "legacy_channel_trimmed_im".into(),
                telemetry.trimmed.iter().map(|value| value.im).collect(),
            ),
        ]);
        let final_taps = dfe_result
            .as_ref()
            .and_then(|result| result.tap_weights.last())
            .map_or(&[][..], Vec::as_slice);
        let dfe_impulse = reference_dfe_impulse(final_taps, samples_per_ui);
        let ctle_out_impulse =
            causal_convolve_truncated(&tx_channel_impulse, &ctle_impulse, tx_channel_impulse.len())
                .map_err(|error| error.to_string())?;
        let rx_ffe_out_impulse =
            causal_convolve_truncated(&ctle_out_impulse, &rx_ffe_impulse, tx_channel_impulse.len())
                .map_err(|error| error.to_string())?;
        let dfe_out_impulse =
            causal_convolve_truncated(&rx_ffe_out_impulse, &dfe_impulse, tx_channel_impulse.len())
                .map_err(|error| error.to_string())?;
        for (name, impulse) in [
            ("tx", tx_impulse.as_slice()),
            ("tx_out", tx_channel_impulse.as_slice()),
            ("ctle", ctle_impulse.as_slice()),
            ("ctle_out", ctle_out_impulse.as_slice()),
            ("dfe", dfe_impulse.as_slice()),
            ("dfe_out", dfe_out_impulse.as_slice()),
        ] {
            let response = reference_frequency_response_from_impulse(
                impulse,
                &telemetry.frequency_hz,
                input.timebase.sample_interval.0,
            )?;
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

    if let Some(analysis) = &input.analysis.statistical_eye {
        if !matches!(input.modulation, ModulationV1::Nrz) {
            return Err("portable statistical eye only supports NRZ".into());
        }
        let response_length = tx_channel_impulse.len();
        let native_eye_impulse =
            convolve_truncated(&tx_channel_impulse, &ctle_impulse, sample_count)
                .map_err(|error| error.to_string())?;
        let rx_ffe_eye_impulse =
            convolve_truncated(&native_eye_impulse, &rx_ffe_impulse, response_length)
                .map_err(|error| error.to_string())?;
        let final_taps = dfe_result
            .as_ref()
            .and_then(|result| result.tap_weights.last())
            .map_or(&[][..], Vec::as_slice);
        let dfe_eye_impulse = reference_dfe_impulse(final_taps, samples_per_ui);
        let web_eye_impulse =
            convolve_truncated(&rx_ffe_eye_impulse, &dfe_eye_impulse, response_length)
                .map_err(|error| error.to_string())?;
        let native_eye_pulse = pulse_response(
            &step_response(&native_eye_impulse).map_err(|error| error.to_string())?,
            samples_per_ui,
        )
        .map_err(|error| error.to_string())?;
        let web_eye_pulse = pulse_response(
            &step_response(&web_eye_impulse).map_err(|error| error.to_string())?,
            samples_per_ui,
        )
        .map_err(|error| error.to_string())?;
        let max_states = usize::try_from(
            analysis
                .max_distribution_states
                .min(input.limits.max_distribution_states),
        )
        .map_err(|_| "statistical eye state limit exceeds reference budget")?;
        let eye_input = StatisticalEyeInputV1 {
            pulse_response: if analysis.post_receiver_output {
                &web_eye_pulse
            } else {
                &native_eye_pulse
            },
            // The native path derives UI from the sampled timebase here.  It
            // is mathematically equivalent to 1/data_rate, but retaining the
            // operation order keeps statistical-state quantization identical.
            ui: crate::Seconds(input.timebase.sample_interval.0 * samples_per_ui as f64),
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
            max_distribution_states: max_states,
        };
        let eye = calculate_statistical_eye(eye_input).map_err(|error| error.to_string())?;
        let contour_levels = if analysis.contour_ber_levels.is_empty() {
            vec![analysis.target_ber]
        } else {
            analysis.contour_ber_levels.clone()
        };
        let contours = calculate_statistical_contours(eye_input, &contour_levels)
            .map_err(|error| error.to_string())?;
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
    }

    let mut stages = vec![
        RunStageV1::Validate,
        RunStageV1::ChannelResponse,
        RunStageV1::TxProcessing,
        RunStageV1::RxEqualization,
    ];
    if dfe_result.is_some() {
        stages.push(RunStageV1::DfeAdaptation);
    }
    if input.rx.viterbi_enabled {
        stages.push(RunStageV1::ViterbiFec);
    }
    if (input.analysis.include_jitter || input.analysis.include_bathtub)
        && matches!(input.pattern, PatternV1::Prbs { .. })
    {
        stages.push(RunStageV1::JitterAnalysis);
    }
    if input.analysis.statistical_eye.is_some() {
        stages.push(RunStageV1::StatisticalEye);
    }
    stages.push(RunStageV1::ResultAssembly);
    let events = stages
        .iter()
        .enumerate()
        .map(|(sequence, stage)| RunEventV1 {
            run_id: input.run_id.clone(),
            sequence: sequence as u64,
            stage: *stage,
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
            external_models: Vec::new(),
        },
        metrics,
        events,
        arrays,
        artifacts: Vec::new(),
    };
    output.validate().map_err(|error| error.to_string())?;
    Ok(output)
}

fn enabled_weights(config: &FfeConfigV1) -> Vec<f64> {
    if config.enabled && !config.weights.is_empty() {
        config.weights.clone()
    } else {
        vec![1.0]
    }
}

fn reference_periodic_noise(
    magnitude: f64,
    frequency: f64,
    sample_interval_s: f64,
    sample_count: usize,
) -> Result<Vec<f64>, String> {
    let sample_rate_hz = 1.0 / sample_interval_s;
    if !sample_rate_hz.is_finite() || frequency > sample_rate_hz * 0.5 || sample_count == 0 {
        return Err("reference periodic-noise input is invalid".into());
    }
    let period_samples = (sample_rate_hz / frequency + 0.5).floor() as usize;
    if period_samples == 0 {
        return Err("reference periodic-noise period is invalid".into());
    }
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
            magnitude
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

fn reference_viterbi_pulse_response(
    tx_channel_impulse: &[f64],
    rx_filter: &[f64],
    dfe_taps: &[f64],
    samples_per_ui: usize,
    state_symbols: usize,
) -> Result<Vec<f64>, String> {
    let rx_impulse = convolve_truncated(tx_channel_impulse, rx_filter, tx_channel_impulse.len())
        .map_err(|error| error.to_string())?;
    let mut dfe_impulse = vec![1.0];
    dfe_impulse.extend(std::iter::repeat_n(0.0, samples_per_ui.saturating_sub(1)));
    for &tap in dfe_taps {
        dfe_impulse.push(-tap);
        dfe_impulse.extend(std::iter::repeat_n(0.0, samples_per_ui.saturating_sub(1)));
    }
    let dfe_output_impulse = convolve_truncated(&rx_impulse, &dfe_impulse, rx_impulse.len())
        .map_err(|error| error.to_string())?;
    let pulse = pulse_response(
        &step_response(&dfe_output_impulse).map_err(|error| error.to_string())?,
        samples_per_ui,
    )
    .map_err(|error| error.to_string())?;
    let cursor = pulse
        .iter()
        .enumerate()
        .max_by(|(_, left), (_, right)| left.total_cmp(right))
        .map(|(index, _)| index)
        .ok_or("portable Viterbi pulse is empty")?;
    (0..state_symbols)
        .map(|offset| {
            let index = cursor
                .checked_add(
                    offset
                        .checked_mul(samples_per_ui)
                        .ok_or("portable Viterbi pulse index overflow")?,
                )
                .ok_or("portable Viterbi pulse index overflow")?;
            pulse
                .get(index)
                .copied()
                .ok_or_else(|| "portable Viterbi pulse is too short".to_owned())
        })
        .collect()
}

fn reference_viterbi_symbol_bits(symbol: f64, modulation: &ModulationV1) -> Vec<i32> {
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

fn reference_jitter(
    input: &SimulationInputV1,
    prbs_order: u8,
    ideal_waveform: &[f64],
    stages: [(&str, &[f64]); 4],
    samples_per_ui: usize,
    include_bathtub: bool,
    metrics: &mut BTreeMap<String, f64>,
    arrays: &mut BTreeMap<String, Vec<f64>>,
) -> Result<(), String> {
    let modulation = match input.modulation {
        ModulationV1::Nrz => 0,
        ModulationV1::DuoBinary => 1,
        ModulationV1::Pam4 => 2,
    };
    let ui_s = 1.0 / input.timebase.data_rate.0;
    let complete_uis = ideal_waveform.len() / samples_per_ui;
    let requested_eye_uis = input
        .analysis
        .jitter_eye_uis
        .and_then(|value| usize::try_from(value).ok())
        .unwrap_or(complete_uis);
    let eye_uis = requested_eye_uis.min(complete_uis);
    let window_start_s = (complete_uis.saturating_sub(eye_uis)) as f64 * ui_s;
    let ideal_times = sample_times(ideal_waveform.len(), input.timebase.sample_interval.0);
    let ideal_crossings = find_crossings(
        &ideal_times,
        ideal_waveform,
        input.tx.amplitude.0,
        0.0,
        true,
        0.1,
        modulation,
    )
    .map_err(|error| error.to_string())?;
    let pattern_len = (1usize
        .checked_shl(u32::from(prbs_order).min(usize::BITS - 1))
        .unwrap_or(usize::MAX)
        .saturating_sub(1))
    .saturating_mul(2);
    let ideal_crossings = crop_crossings(&ideal_crossings, 0.0, window_start_s);
    for (stage_name, waveform) in stages {
        let times = sample_times(waveform.len(), input.timebase.sample_interval.0);
        let lag = correlation_peak_lag(waveform, ideal_waveform)?;
        let offset_s = lag as f64 * input.timebase.sample_interval.0;
        let actual = find_crossings(
            &times,
            waveform,
            input.tx.amplitude.0,
            0.0,
            true,
            0.1,
            modulation,
        )
        .map_err(|error| error.to_string())?;
        let actual = crop_crossings(&actual, offset_s, window_start_s);
        let track = assemble_tie_track(ui_s, &ideal_crossings, &actual, true)
            .map_err(|error| error.to_string())?;
        let data = calculate_data_dependent_jitter(
            ui_s,
            eye_uis,
            pattern_len,
            &track.ideal_times_s,
            &track.jitter_s,
            true,
        )
        .map_err(|error| error.to_string())?;
        let spectral = calculate_spectral_jitter(
            ui_s,
            eye_uis,
            &track.ideal_times_s,
            &track.jitter_s,
            &data.data_independent_tie_s,
            input.analysis.jitter_rel_thresh.unwrap_or(3.0),
        )
        .map_err(|error| error.to_string())?;
        let dual = calculate_dual_dirac_jitter(
            ui_s,
            &track.jitter_s,
            &data.data_independent_tie_s,
            101,
            5,
        )
        .map_err(|error| error.to_string())?;
        let bathtub = if include_bathtub {
            Some(
                make_bathtub(
                    &dual.bin_centers_s,
                    &dual.total_histogram,
                    1.0e-13,
                    dual.random_jitter_s,
                    dual.positive_mean_s,
                    dual.negative_mean_s,
                    dual.random_jitter_s > 0.0,
                )
                .map_err(|error| error.to_string())?,
            )
        } else {
            None
        };
        metrics.extend([
            (
                format!("jitter_{stage_name}_tie_count"),
                track.jitter_s.len() as f64,
            ),
            (format!("jitter_{stage_name}_isi_s"), data.isi_s),
            (format!("jitter_{stage_name}_dcd_s"), data.dcd_s),
            (
                format!("jitter_{stage_name}_periodic_s"),
                spectral.periodic_jitter_s,
            ),
            (
                format!("jitter_{stage_name}_random_s"),
                spectral.random_jitter_s,
            ),
            (
                format!("jitter_{stage_name}_dual_dirac_periodic_s"),
                dual.periodic_jitter_s,
            ),
            (
                format!("jitter_{stage_name}_dual_dirac_random_s"),
                dual.random_jitter_s,
            ),
            (format!("jitter_{stage_name}_alignment_offset_s"), offset_s),
        ]);
        arrays.extend([
            (format!("jitter_{stage_name}"), dual.total_histogram.clone()),
            (format!("jitter_{stage_name}_tie_s"), track.jitter_s.clone()),
            (
                format!("jitter_{stage_name}_times_s"),
                track.ideal_times_s.clone(),
            ),
            (
                format!("jitter_{stage_name}_data_independent_tie_s"),
                data.data_independent_tie_s.clone(),
            ),
            (
                format!("jitter_{stage_name}_spectrum"),
                spectral.total_spectrum.clone(),
            ),
            (
                format!("jitter_{stage_name}_data_independent_spectrum"),
                spectral.data_independent_spectrum.clone(),
            ),
            (
                format!("jitter_{stage_name}_frequency_hz"),
                spectral.frequencies_hz.clone(),
            ),
            (
                format!("jitter_{stage_name}_threshold"),
                spectral.periodic_threshold.clone(),
            ),
            (
                format!("jitter_{stage_name}_data_independent_histogram_per_s"),
                dual.data_independent_histogram.clone(),
            ),
            (
                format!("jitter_{stage_name}_bin_centers_s"),
                dual.bin_centers_s.clone(),
            ),
        ]);
        if let Some(bathtub) = bathtub {
            metrics.extend([
                (
                    format!("bathtub_{stage_name}_min_ber"),
                    bathtub.iter().copied().fold(f64::INFINITY, f64::min),
                ),
                (
                    format!("bathtub_{stage_name}_max_ber"),
                    bathtub.iter().copied().fold(f64::NEG_INFINITY, f64::max),
                ),
            ]);
            arrays.insert(format!("bathtub_{stage_name}_ber"), bathtub);
        }
        if stage_name == "dfe" {
            metrics.extend([
                ("jitter_tie_count".into(), track.jitter_s.len() as f64),
                ("jitter_isi_s".into(), data.isi_s),
                ("jitter_dcd_s".into(), data.dcd_s),
                ("jitter_periodic_s".into(), spectral.periodic_jitter_s),
                ("jitter_random_s".into(), spectral.random_jitter_s),
                (
                    "jitter_dual_dirac_periodic_s".into(),
                    dual.periodic_jitter_s,
                ),
                ("jitter_dual_dirac_random_s".into(), dual.random_jitter_s),
                ("jitter_alignment_offset_s".into(), offset_s),
            ]);
            arrays.extend([
                ("jitter_tie_s".into(), track.jitter_s.clone()),
                ("jitter_times_s".into(), track.ideal_times_s.clone()),
                (
                    "jitter_data_independent_tie_s".into(),
                    data.data_independent_tie_s.clone(),
                ),
                ("jitter_spectrum".into(), spectral.total_spectrum.clone()),
                (
                    "jitter_data_independent_spectrum".into(),
                    spectral.data_independent_spectrum.clone(),
                ),
                (
                    "jitter_frequency_hz".into(),
                    spectral.frequencies_hz.clone(),
                ),
                (
                    "jitter_threshold".into(),
                    spectral.periodic_threshold.clone(),
                ),
                (
                    "jitter_histogram_per_s".into(),
                    dual.total_histogram.clone(),
                ),
                (
                    "jitter_data_independent_histogram_per_s".into(),
                    dual.data_independent_histogram.clone(),
                ),
                ("jitter_bin_centers_s".into(), dual.bin_centers_s.clone()),
            ]);
            if include_bathtub && let Some(bathtub) = arrays.get("bathtub_dfe_ber").cloned() {
                metrics.extend([
                    (
                        "bathtub_min_ber".into(),
                        bathtub.iter().copied().fold(f64::INFINITY, f64::min),
                    ),
                    (
                        "bathtub_max_ber".into(),
                        bathtub.iter().copied().fold(f64::NEG_INFINITY, f64::max),
                    ),
                ]);
                arrays.insert("bathtub_ber".into(), bathtub);
            }
        }
    }
    Ok(())
}

fn crop_crossings(crossings: &[f64], offset_s: f64, window_start_s: f64) -> Vec<f64> {
    crossings
        .iter()
        .map(|crossing| crossing - offset_s)
        .filter(|crossing| *crossing > window_start_s)
        .map(|crossing| crossing - window_start_s)
        .collect()
}

fn correlation_peak_lag(waveform: &[f64], reference: &[f64]) -> Result<isize, String> {
    if waveform.is_empty() || reference.is_empty() {
        return Err("jitter correlation requires non-empty waveforms".into());
    }
    let correlation_len = waveform
        .len()
        .checked_add(reference.len())
        .and_then(|length| length.checked_sub(1))
        .ok_or("jitter correlation length overflow")?;
    let fft_len = correlation_len
        .checked_next_power_of_two()
        .ok_or("jitter correlation FFT length overflow")?;
    let mut left = vec![Complex::new(0.0, 0.0); fft_len];
    let mut right = vec![Complex::new(0.0, 0.0); fft_len];
    left.iter_mut()
        .zip(waveform)
        .for_each(|(slot, value)| slot.re = *value);
    right
        .iter_mut()
        .zip(reference.iter().rev())
        .for_each(|(slot, value)| slot.re = *value);
    let mut planner = FftPlanner::<f64>::new();
    planner.plan_fft_forward(fft_len).process(&mut left);
    planner.plan_fft_forward(fft_len).process(&mut right);
    left.iter_mut()
        .zip(right)
        .for_each(|(value, other)| *value *= other);
    planner.plan_fft_inverse(fft_len).process(&mut left);
    let scale = 1.0 / fft_len as f64;
    let peak = left[..correlation_len]
        .iter()
        .enumerate()
        .max_by(|(_, left), (_, right)| (left.re * scale).total_cmp(&(right.re * scale)))
        .map(|(index, _)| index)
        .ok_or("jitter correlation peak is unavailable")?;
    Ok(peak as isize - (reference.len() as isize - 1))
}

fn hold_symbols(symbols: &[f64], samples_per_ui: usize) -> Vec<f64> {
    symbols
        .iter()
        .flat_map(|symbol| std::iter::repeat_n(*symbol, samples_per_ui))
        .collect()
}

fn sample_times(count: usize, interval: f64) -> Vec<f64> {
    (0..count).map(|index| index as f64 * interval).collect()
}

fn reference_ctle(input: &SimulationInputV1, sample_count: usize) -> Result<Vec<f64>, String> {
    if !input.rx.native_ctle_enabled {
        return Ok(vec![1.0]);
    }
    let config = input
        .rx
        .ctle
        .as_ref()
        .ok_or("native CTLE is enabled without a typed configuration")?;
    if let Some(impulse) = &config.impulse_response_v_per_v {
        let mut values = impulse.clone();
        values.resize(sample_count.max(1), 0.0);
        values.truncate(sample_count.max(1));
        return Ok(values);
    }
    ctle_impulse_response(
        crate::CtleConfig {
            rx_bandwidth_hz: config.bandwidth.0,
            peak_frequency_hz: config.peak_frequency.0,
            peak_magnitude_db: config.peak_magnitude_db,
        },
        sample_count.max(2),
        input.timebase.sample_interval.0,
    )
    .map_err(|error| error.to_string())
}

fn reference_dfe_impulse(taps: &[f64], samples_per_ui: usize) -> Vec<f64> {
    let mut impulse = vec![1.0];
    impulse.extend(std::iter::repeat_n(0.0, samples_per_ui.saturating_sub(1)));
    for &tap in taps {
        impulse.push(-tap);
        impulse.extend(std::iter::repeat_n(0.0, samples_per_ui.saturating_sub(1)));
    }
    impulse
}

struct ReferenceLegacyChannel {
    frequency_hz: Vec<f64>,
    raw: Vec<Complex64>,
    terminated: Vec<Complex64>,
    trimmed: Vec<Complex64>,
}

fn reference_legacy_channel(
    input: &SimulationInputV1,
    channel_impulse: &[f64],
    _target_count: usize,
    _samples_per_ui: usize,
) -> Result<Option<ReferenceLegacyChannel>, String> {
    let ChannelInputV1::MetallicLine(channel) = &input.channel else {
        return Ok(None);
    };
    let (Some(step), Some(maximum)) = (channel.frequency_step_hz, channel.frequency_max_hz) else {
        return Ok(None);
    };
    let intervals = (maximum.0 / step.0).round() as usize;
    let fft_size = intervals
        .checked_mul(2)
        .ok_or("reference legacy channel FFT size overflow")?;
    let bins = fft_size / 2 + 1;
    let frequencies = (0..bins)
        .map(|index| index as f64 * step.0)
        .collect::<Vec<_>>();
    // Keep the same multiplication order as the native metallic-line leaf;
    // this avoids magnifying ulp drift during the complex termination solve.
    let angular = (0..bins)
        .map(|index| std::f64::consts::TAU * index as f64 * step.0)
        .collect::<Vec<_>>();
    let (gamma, impedance) = calculate_metallic_line(
        MetallicLineConfig {
            skin_effect_resistance_ohm_per_m: channel.skin_effect_resistance_ohm_per_m,
            crossover_angular_frequency_rad_per_s: channel.crossover_angular_frequency_rad_per_s,
            dc_resistance_ohm_per_m: channel.dc_resistance_ohm_per_m,
            characteristic_impedance_ohm: channel.characteristic_impedance.0,
            propagation_velocity_m_per_s: channel.propagation_velocity_m_per_s,
            loss_tangent: channel.loss_tangent,
        },
        &angular,
    )
    .map_err(|error| error.to_string())?;
    let raw = gamma
        .iter()
        .map(|value| (-value * channel.length_m).exp())
        .collect::<Vec<_>>();
    let terminated = reference_s_parameter_transfer(
        &gamma,
        &impedance,
        &angular,
        channel.length_m,
        TerminationConfig {
            source_resistance_ohm: channel.source_impedance.0,
            source_capacitance_f: channel.source_capacitance_f,
            load_resistance_ohm: channel.load_impedance.0,
            load_capacitance_f: channel.load_capacitance_f,
        },
    );
    let source_interval = 0.5 / maximum.0;
    let source_grid = reference_cubic_resample(
        channel_impulse,
        input.timebase.sample_interval.0,
        source_interval,
        fft_size,
    );
    let (real, imag) = inverse_spectrum_parts(&source_grid)?;
    let scale = source_interval / input.timebase.sample_interval.0;
    let trimmed = real
        .into_iter()
        .zip(imag)
        .map(|(real, imag)| Complex64::new(real * scale, imag * scale))
        .collect::<Vec<_>>();
    Ok(Some(ReferenceLegacyChannel {
        frequency_hz: frequencies,
        raw,
        terminated,
        trimmed,
    }))
}

fn inverse_spectrum_parts(values: &[f64]) -> Result<(Vec<f64>, Vec<f64>), String> {
    let (real, imag) = crate::forward_real_spectrum(values).map_err(|error| error.to_string())?;
    Ok((real, imag))
}

fn reference_frequency_response_from_impulse(
    impulse: &[f64],
    frequencies_hz: &[f64],
    sample_interval_s: f64,
) -> Result<Vec<Complex64>, String> {
    let frequency_step_hz = *frequencies_hz
        .get(1)
        .ok_or("reference legacy response frequency grid is empty")?;
    let maximum_frequency_hz = *frequencies_hz
        .last()
        .ok_or("reference legacy response frequency grid is empty")?;
    let fft_size = (1.0 / (frequency_step_hz * sample_interval_s) + 0.5) as usize;
    if fft_size < 2 || maximum_frequency_hz > 0.5 / sample_interval_s {
        return Err("reference legacy response frequency grid is invalid".into());
    }
    let mut padded = impulse[..impulse.len().min(fft_size)].to_vec();
    padded.resize(fft_size, 0.0);
    let (real, imag) = inverse_spectrum_parts(&padded)?;
    let source_step = 1.0 / (fft_size as f64 * sample_interval_s);
    frequencies_hz
        .iter()
        .map(|frequency| {
            let position = *frequency / source_step;
            let lower = position.floor() as usize;
            let fraction = position - lower as f64;
            let lower = lower.min(real.len().saturating_sub(1));
            let upper = (lower + 1).min(real.len().saturating_sub(1));
            Ok(Complex64::new(
                real[lower] * (1.0 - fraction) + real[upper] * fraction,
                imag[lower] * (1.0 - fraction) + imag[upper] * fraction,
            ))
        })
        .collect()
}

fn reference_channel(
    input: &SimulationInputV1,
    target_count: usize,
    samples_per_ui: usize,
) -> Result<Vec<f64>, String> {
    match &input.channel {
        ChannelInputV1::ImpulseResponse(response) => {
            let mut values = response
                .impulse_response_volts_per_second
                .iter()
                .map(|value| *value * input.timebase.sample_interval.0)
                .collect::<Vec<_>>();
            values.resize(target_count.max(1), 0.0);
            values.truncate(target_count.max(1));
            Ok(values)
        }
        ChannelInputV1::MetallicLine(channel) => {
            let (fft_size, frequency_step, source_interval) =
                match (channel.frequency_step_hz, channel.frequency_max_hz) {
                    (Some(step), Some(maximum)) => (
                        ((maximum.0 / step.0).round() as usize)
                            .saturating_mul(2)
                            .max(2),
                        step.0,
                        0.5 / maximum.0,
                    ),
                    (None, None) => (
                        target_count.next_power_of_two().max(2),
                        1.0 / (target_count as f64 * input.timebase.sample_interval.0),
                        input.timebase.sample_interval.0,
                    ),
                    _ => return Err("metallic channel frequency grid is incomplete".into()),
                };
            let bins = fft_size / 2 + 1;
            let frequencies = (0..bins)
                .map(|index| std::f64::consts::TAU * index as f64 * frequency_step)
                .collect::<Vec<_>>();
            let (gamma, impedance) = calculate_metallic_line(
                MetallicLineConfig {
                    skin_effect_resistance_ohm_per_m: channel.skin_effect_resistance_ohm_per_m,
                    crossover_angular_frequency_rad_per_s: channel
                        .crossover_angular_frequency_rad_per_s,
                    dc_resistance_ohm_per_m: channel.dc_resistance_ohm_per_m,
                    characteristic_impedance_ohm: channel.characteristic_impedance.0,
                    propagation_velocity_m_per_s: channel.propagation_velocity_m_per_s,
                    loss_tangent: channel.loss_tangent,
                },
                &frequencies,
            )
            .map_err(|error| error.to_string())?;
            let loaded = reference_s_parameter_transfer(
                &gamma,
                &impedance,
                &frequencies,
                channel.length_m,
                TerminationConfig {
                    source_resistance_ohm: channel.source_impedance.0,
                    source_capacitance_f: channel.source_capacitance_f,
                    load_resistance_ohm: channel.load_impedance.0,
                    load_capacitance_f: channel.load_capacitance_f,
                },
            );
            let (real, imag): (Vec<_>, Vec<_>) =
                loaded.iter().map(|value| (value.re, value.im)).unzip();
            let mut impulse =
                inverse_real_spectrum(&real, &imag, fft_size).map_err(|error| error.to_string())?;
            if channel.apply_raised_cosine_window {
                for (index, value) in impulse.iter_mut().enumerate() {
                    let weight = (std::f64::consts::PI * index as f64 / bins as f64)
                        .cos()
                        .mul_add(0.5, 0.5);
                    *value *= weight;
                }
            }
            let values = reference_cubic_resample(
                &impulse,
                source_interval,
                input.timebase.sample_interval.0,
                target_count.max(1),
            )
            .into_iter()
            .map(|value| value * input.timebase.sample_interval.0 / source_interval)
            .collect::<Vec<_>>();
            let explicit = channel
                .impulse_length
                .map(|length| (length.0 / input.timebase.sample_interval.0).floor() as usize)
                .filter(|length| *length > 0)
                .unwrap_or_else(|| (20 * samples_per_ui).min(target_count));
            let max_length = channel
                .impulse_length
                .map(|length| (length.0 / input.timebase.sample_interval.0).floor() as usize)
                .filter(|length| *length > 0)
                .unwrap_or_else(|| (100 * samples_per_ui).min(target_count));
            let length = explicit.max(1).min(max_length.max(1)).min(values.len());
            Ok(reference_trim_impulse(
                &values,
                length,
                max_length.max(1),
                1,
            ))
        }
        ChannelInputV1::Touchstone(_) => {
            Err("touchstone channels are evaluated through the native workflow".into())
        }
        ChannelInputV1::ExternalModel(_) => Err("external channel models are not portable".into()),
    }
}

fn reference_cubic_resample(
    source: &[f64],
    source_interval: f64,
    target_interval: f64,
    target_len: usize,
) -> Vec<f64> {
    if source.len() < 4 {
        return (0..target_len)
            .map(|index| {
                let position = index as f64 * target_interval / source_interval;
                let lower = position.floor() as usize;
                if lower >= source.len() {
                    0.0
                } else {
                    let fraction = position - lower as f64;
                    source[lower] * (1.0 - fraction)
                        + source.get(lower + 1).copied().unwrap_or(0.0) * fraction
                }
            })
            .collect();
    }
    let second = reference_not_a_knot_second_derivatives(source, source_interval);
    (0..target_len)
        .map(|index| {
            let position = index as f64 * target_interval / source_interval;
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
                + ((left.powi(3) - left) * second[interval]
                    + (fraction.powi(3) - fraction) * second[interval + 1])
                    * source_interval.powi(2)
                    / 6.0
        })
        .collect()
}

fn reference_not_a_knot_second_derivatives(values: &[f64], spacing: f64) -> Vec<f64> {
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

fn reference_trim_impulse(
    values: &[f64],
    min_length: usize,
    max_length: usize,
    front_porch: usize,
) -> Vec<f64> {
    let mut impulse = values.to_vec();
    let half_length = impulse.len() / 2;
    let maximum_index = reference_first_maximum_index(&impulse);
    if maximum_index < impulse.len() / 4 {
        impulse.rotate_right(half_length);
    }
    let maximum_index = reference_first_maximum_index(&impulse);
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
    impulse[beginning.min(impulse.len())..ending.min(impulse.len())].to_vec()
}

fn reference_first_maximum_index(values: &[f64]) -> usize {
    let mut maximum = 0;
    for index in 1..values.len() {
        if values[index] > values[maximum] {
            maximum = index;
        }
    }
    maximum
}

// The following small matrix implementation is kept local to the reference
// graph.  It mirrors the legacy power-wave termination algebra without
// calling the candidate simulation's private stage helper.
type ComplexMatrix2 = [Complex64; 4];

fn reference_s_parameter_transfer(
    gamma: &[Complex64],
    characteristic_impedance: &[Complex64],
    angular_frequencies: &[f64],
    length_m: f64,
    termination: TerminationConfig,
) -> Vec<Complex64> {
    gamma
        .iter()
        .zip(characteristic_impedance)
        .zip(angular_frequencies)
        .map(|((&gamma, &impedance), &frequency)| {
            let propagation = (-gamma * length_m).exp();
            let initial = [
                Complex64::new(0.0, 0.0),
                propagation,
                propagation,
                Complex64::new(0.0, 0.0),
            ];
            let line_z = reference_s_to_z(initial, [impedance, impedance]);
            let source_reference = Complex64::new(termination.source_resistance_ohm, 0.0);
            let normalized = reference_z_to_s(line_z, [source_reference, source_reference]);
            let driver_z = reference_s_to_z(normalized, [source_reference, source_reference]);
            let source_z = reference_parallel_rc(
                termination.source_resistance_ohm,
                termination.source_capacitance_f,
                frequency,
            );
            let load_z = reference_parallel_rc(
                termination.load_resistance_ohm,
                termination.load_capacitance_f,
                frequency,
            );
            let terminated = reference_z_to_s(driver_z, [source_z, load_z]);
            terminated[2] * (load_z / source_z).sqrt()
        })
        .collect()
}

fn reference_parallel_rc(resistance: f64, capacitance: f64, angular_frequency: f64) -> Complex64 {
    let resistance = Complex64::new(resistance, 0.0);
    resistance / Complex64::new(1.0, angular_frequency * resistance.re * capacitance)
}

fn reference_s_to_z(scattering: ComplexMatrix2, references: [Complex64; 2]) -> ComplexMatrix2 {
    let identity = reference_identity();
    let factors = reference_factors(references);
    let reference_matrix = reference_diagonal(references);
    let lhs = reference_nudge(reference_multiply(
        reference_subtract(identity, scattering),
        factors,
    ));
    let rhs = reference_multiply(
        reference_add(
            reference_multiply(scattering, reference_matrix),
            reference_diagonal([references[0].conj(), references[1].conj()]),
        ),
        factors,
    );
    reference_solve(lhs, rhs)
}

fn reference_z_to_s(impedance: ComplexMatrix2, references: [Complex64; 2]) -> ComplexMatrix2 {
    let factors = reference_factors(references);
    let reference_matrix = reference_diagonal(references);
    let conjugates = reference_diagonal([references[0].conj(), references[1].conj()]);
    let lhs = reference_multiply(factors, reference_add(impedance, reference_matrix));
    let rhs = reference_multiply(factors, reference_subtract(impedance, conjugates));
    reference_right_solve(lhs, rhs)
}

fn reference_factors(references: [Complex64; 2]) -> ComplexMatrix2 {
    reference_diagonal([
        Complex64::new(1.0 / (2.0 * references[0].re.sqrt()), 0.0),
        Complex64::new(1.0 / (2.0 * references[1].re.sqrt()), 0.0),
    ])
}

fn reference_identity() -> ComplexMatrix2 {
    reference_diagonal([Complex64::new(1.0, 0.0), Complex64::new(1.0, 0.0)])
}

fn reference_diagonal(values: [Complex64; 2]) -> ComplexMatrix2 {
    [
        values[0],
        Complex64::new(0.0, 0.0),
        Complex64::new(0.0, 0.0),
        values[1],
    ]
}

fn reference_add(left: ComplexMatrix2, right: ComplexMatrix2) -> ComplexMatrix2 {
    std::array::from_fn(|index| left[index] + right[index])
}

fn reference_subtract(left: ComplexMatrix2, right: ComplexMatrix2) -> ComplexMatrix2 {
    std::array::from_fn(|index| left[index] - right[index])
}

fn reference_multiply(left: ComplexMatrix2, right: ComplexMatrix2) -> ComplexMatrix2 {
    [
        left[0] * right[0] + left[1] * right[2],
        left[0] * right[1] + left[1] * right[3],
        left[2] * right[0] + left[3] * right[2],
        left[2] * right[1] + left[3] * right[3],
    ]
}

fn reference_nudge(matrix: ComplexMatrix2) -> ComplexMatrix2 {
    const CONDITION: f64 = 1.0e-9;
    const MINIMUM: f64 = 1.0e-12;
    let scale = matrix.iter().map(|value| value.norm()).fold(1.0, f64::max);
    let tolerance = f64::EPSILON * scale * 16.0;
    if (matrix[0] - matrix[3]).norm() > tolerance || (matrix[1] - matrix[2]).norm() > tolerance {
        return matrix;
    }
    let floor = (CONDITION
        * (matrix[0] + matrix[1])
            .norm()
            .max((matrix[0] - matrix[1]).norm()))
    .max(MINIMUM);
    let even = reference_nudge_value(matrix[0] + matrix[1], floor);
    let odd = reference_nudge_value(matrix[0] - matrix[1], floor);
    let half = Complex64::new(0.5, 0.0);
    [
        (even + odd) * half,
        (even - odd) * half,
        (even - odd) * half,
        (even + odd) * half,
    ]
}

fn reference_nudge_value(value: Complex64, floor: f64) -> Complex64 {
    if value.norm() < floor {
        Complex64::new(floor, 0.0)
    } else {
        value
    }
}

fn reference_solve(coefficients: ComplexMatrix2, constants: ComplexMatrix2) -> ComplexMatrix2 {
    let (a, b, c, d, top, bottom) = if coefficients[0].norm() >= coefficients[2].norm() {
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
    let multiplier = c / a;
    let diagonal = d - multiplier * b;
    let lower = [
        bottom[0] - multiplier * top[0],
        bottom[1] - multiplier * top[1],
    ];
    let solution = [lower[0] / diagonal, lower[1] / diagonal];
    [
        (top[0] - b * solution[0]) / a,
        (top[1] - b * solution[1]) / a,
        solution[0],
        solution[1],
    ]
}

fn reference_right_solve(
    coefficients: ComplexMatrix2,
    constants: ComplexMatrix2,
) -> ComplexMatrix2 {
    reference_transpose_conjugate(reference_solve(
        reference_transpose_conjugate(coefficients),
        reference_transpose_conjugate(constants),
    ))
}

fn reference_transpose_conjugate(matrix: ComplexMatrix2) -> ComplexMatrix2 {
    [
        matrix[0].conj(),
        matrix[2].conj(),
        matrix[1].conj(),
        matrix[3].conj(),
    ]
}

#[cfg(test)]
mod tests {
    use super::reference_first_maximum_index;

    #[test]
    fn reference_argmax_keeps_first_signed_zero() {
        assert_eq!(reference_first_maximum_index(&[-0.0, 0.0, 0.0]), 0);
    }
}
