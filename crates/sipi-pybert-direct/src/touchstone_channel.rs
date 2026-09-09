#![forbid(unsafe_code)]

//! Explicit Touchstone and cascaded S-parameter network channel boundary.
//!
//! This module accepts single or cascaded S-parameter networks (Touchstone files,
//! inline Touchstone content, or analytical network fixtures), applies typed
//! port mappings, runs grid and passivity/reciprocity diagnostics, computes the
//! exact frequency-domain loaded voltage transfer function with terminations,
//! executes a single final FD-to-TD IFFT, and feeds the resulting impulse response
//! into the native link stages.

use std::{
    fs,
    path::{Path, PathBuf},
};

use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sipi_channel::{
    PortMapV1, TerminationParamsV1, TwoPortSpectrumV1, assess_frequency_grid_coverage,
    calculate_loaded_voltage_transfer, cascade_network_stages, create_analytic_delay_network,
    create_analytic_mismatched_line_network, create_analytic_thru_network,
    evaluate_sampled_passivity, evaluate_sampled_reciprocity, four_port_to_differential_two_port,
    parse_touchstone_2port, parse_touchstone_4port, spectrum_to_discrete_kernel,
};
use sipi_types::{Hertz as SipiHertz, Ohms as SipiOhms, Seconds as SipiSeconds};

use crate::{
    ChannelInputV1, ChannelResponseV1, DirectRunError, DirectRunReport, ModulationV1,
    NativeSimulationError, Ohms, PatternV1, Seconds, SimulationInputV1, simulate_native_v1,
    strict_simulation_input_json, write_simulation_artifacts_with_schema_and_backend,
};

pub const TOUCHSTONE_CHANNEL_POLICY_V1: &str = "touchstone-network-v1";
pub const TOUCHSTONE_RESULT_SCHEMA_V1: &str = "sipi.channel.touchstone-result.v1";

fn invalid(message: impl Into<String>) -> DirectRunError {
    DirectRunError::Json(format!("touchstone network channel: {}", message.into()))
}

fn resource_limit() -> DirectRunError {
    NativeSimulationError::ResourceLimitExceeded.into()
}

/// Typed specification of a single network stage in a cascade.
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct TouchstoneStageSpecV1 {
    pub name: String,
    #[serde(default)]
    pub kind: Option<String>,
    #[serde(default)]
    pub file_path: Option<String>,
    #[serde(default)]
    pub file_content: Option<String>,
    #[serde(default)]
    pub port_map: Option<String>,
    #[serde(default)]
    pub delay_seconds: Option<f64>,
    #[serde(default)]
    pub line_impedance_ohms: Option<f64>,
    #[serde(default)]
    pub propagation_velocity_m_per_s: Option<f64>,
    #[serde(default)]
    pub length_m: Option<f64>,
}

/// Request parameters for the Touchstone network channel.
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct TouchstoneNetworkChannelConfigV1 {
    #[serde(default)]
    pub file_path: Option<String>,
    #[serde(default)]
    pub file_content: Option<String>,
    #[serde(default)]
    pub port_map: Option<String>,
    #[serde(default)]
    pub stages: Option<Vec<TouchstoneStageSpecV1>>,
    #[serde(default = "default_reference_impedance")]
    pub reference_impedance: f64,
    #[serde(default = "default_source_impedance")]
    pub source_impedance: f64,
    #[serde(default)]
    pub source_capacitance_f: f64,
    #[serde(default = "default_load_impedance")]
    pub load_impedance: f64,
    #[serde(default)]
    pub load_capacitance_f: f64,
    #[serde(default)]
    pub apply_raised_cosine_window: bool,
    #[serde(default)]
    pub frequency_step_hz: Option<f64>,
    #[serde(default)]
    pub frequency_max_hz: Option<f64>,
    #[serde(default)]
    pub impulse_length: Option<f64>,
}

fn default_reference_impedance() -> f64 {
    50.0
}
fn default_source_impedance() -> f64 {
    50.0
}
fn default_load_impedance() -> f64 {
    50.0
}

fn parse_port_map(value: Option<&str>) -> PortMapV1 {
    match value {
        Some("adjacent") | Some("tx_plus_tx_minus_rx_plus_rx_minus") => {
            PortMapV1::TxPlusTxMinusRxPlusRxMinus
        }
        _ => PortMapV1::TxPlusRxPlusTxMinusRxMinus,
    }
}

fn resolve_stage_network(
    stage: &TouchstoneStageSpecV1,
    base_dir: &Path,
    ref_z: SipiOhms,
    simulation_grid: &[SipiHertz],
) -> Result<TwoPortSpectrumV1, DirectRunError> {
    let kind = stage.kind.as_deref().unwrap_or("touchstone_file");
    let net = match kind {
        "analytic_thru" => create_analytic_thru_network(simulation_grid, ref_z)
            .map_err(|e| invalid(format!("thru generation failed: {e:?}")))?,
        "analytic_delay" => {
            let delay = stage.delay_seconds.ok_or_else(|| {
                invalid("analytic_delay stage requires delaySeconds")
            })?;
            create_analytic_delay_network(simulation_grid, ref_z, delay)
                .map_err(|e| invalid(format!("delay generation failed: {e:?}")))?
        }
        "analytic_mismatched_line" => {
            let zc = stage.line_impedance_ohms.ok_or_else(|| {
                invalid("analytic_mismatched_line stage requires lineImpedanceOhms")
            })?;
            let v = stage.propagation_velocity_m_per_s.ok_or_else(|| {
                invalid("analytic_mismatched_line stage requires propagationVelocityMPerS")
            })?;
            let length = stage.length_m.ok_or_else(|| {
                invalid("analytic_mismatched_line stage requires lengthM")
            })?;
            create_analytic_mismatched_line_network(simulation_grid, ref_z, zc, v, length)
                .map_err(|e| invalid(format!("mismatched line generation failed: {e:?}")))?
        }
        "touchstone_file" | "touchstone" => {
            let content = if let Some(text) = &stage.file_content {
                text.clone()
            } else if let Some(file_path) = &stage.file_path {
                let full_path = if Path::new(file_path).is_absolute() {
                    PathBuf::from(file_path)
                } else {
                    base_dir.join(file_path)
                };
                fs::read_to_string(&full_path).map_err(|e| {
                    invalid(format!(
                        "cannot read Touchstone file '{}': {e}",
                        full_path.display()
                    ))
                })?
            } else {
                return Err(invalid(format!(
                    "stage '{}' requires either filePath or fileContent",
                    stage.name
                )));
            };

            // Detect if 2-port or 4-port by file path extension or parsing
            let is_s4p = stage
                .file_path
                .as_deref()
                .is_some_and(|p| p.to_ascii_lowercase().ends_with(".s4p"));

            if is_s4p {
                let (file_ref_z, freqs, s4p_samples) = parse_touchstone_4port(&content)
                    .map_err(|e| invalid(format!("parsing S4P failed: {e:?}")))?;
                let port_map = parse_port_map(stage.port_map.as_deref());
                let mut two_port_samples = Vec::with_capacity(s4p_samples.len());
                for s4p in s4p_samples {
                    let sdd = four_port_to_differential_two_port(s4p, port_map)
                        .map_err(|e| invalid(format!("port mapping failed: {e:?}")))?;
                    two_port_samples.push(sdd);
                }
                TwoPortSpectrumV1::try_new(&stage.name, file_ref_z, freqs, two_port_samples)
                    .map_err(|e| invalid(format!("creating TwoPortSpectrum failed: {e:?}")))?
            } else {
                // Default to 2-port
                parse_touchstone_2port(&content, &stage.name)
                    .map_err(|e| invalid(format!("parsing S2P failed: {e:?}")))?
            }
        }
        unknown => return Err(invalid(format!("unknown stage kind: {unknown}"))),
    };

    if net.name() != stage.name {
        TwoPortSpectrumV1::try_new(
            &stage.name,
            net.reference_impedance(),
            net.frequencies().to_vec(),
            net.samples().to_vec(),
        )
        .map_err(|e| invalid(format!("naming stage failed: {e:?}")))
    } else {
        Ok(net)
    }
}

pub fn run_channel_touchstone_network_json(
    bytes: &[u8],
    input_file: &Path,
    output_dir: &Path,
) -> Result<DirectRunReport, DirectRunError> {
    let _: SimulationInputV1 =
        serde_json::from_slice(bytes).map_err(|error| DirectRunError::Json(error.to_string()))?;
    let input = strict_simulation_input_json(bytes)?;
    input.validate().map_err(NativeSimulationError::from)?;

    let base_dir = input_file.parent().unwrap_or_else(|| Path::new("."));

    // Extract configuration from raw Value to allow flexible channel payload
    let raw: Value = serde_json::from_slice(bytes).map_err(|e| DirectRunError::Json(e.to_string()))?;
    let channel_val = raw.get("channel").ok_or_else(|| invalid("missing channel object"))?;
    let channel_inner = channel_val.get("value").unwrap_or(channel_val);

    let config: TouchstoneNetworkChannelConfigV1 = serde_json::from_value(channel_inner.clone())
        .map_err(|e| invalid(format!("invalid touchstone channel config: {e}")))?;

    let dt = input.timebase.sample_interval.0;
    if dt <= 0.0 {
        return Err(invalid("sample interval must be positive"));
    }

    let bits = match &input.pattern {
        PatternV1::Prbs { .. } => {
            usize::try_from(input.timebase.nbits).map_err(|_| resource_limit())?
        }
        PatternV1::ExplicitBits { bits, .. } => {
            if bits.is_empty() || bits.len() as u64 != input.timebase.nbits {
                return Err(invalid("explicit bits must match the declared timebase"));
            }
            bits.len()
        }
    };
    let encoded_bits = if input.rx.viterbi_enabled && input.rx.viterbi.as_ref().is_some_and(|v| v.fec) {
        bits.checked_mul(2).ok_or_else(resource_limit)?
    } else {
        bits
    };
    let symbols = if matches!(input.modulation, ModulationV1::Pam4) {
        encoded_bits / 2
    } else {
        encoded_bits
    };
    let sample_count = symbols
        .checked_mul(input.timebase.samples_per_ui as usize)
        .ok_or_else(resource_limit)?;

    let ref_z = SipiOhms::try_new(config.reference_impedance)
        .map_err(|_| invalid("reference impedance must be positive"))?;

    // Determine simulation frequency grid parameters
    let df = config.frequency_step_hz.unwrap_or(1.0 / (sample_count as f64 * dt));
    let n_fft_float = 1.0 / (df * dt);
    let n_fft = n_fft_float.round() as usize;
    if (n_fft_float - n_fft as f64).abs() > 1e-6 || n_fft < 2 || n_fft % 2 != 0 {
        return Err(invalid("frequency step and dt must yield an even integer FFT length"));
    }
    let last_bin = match config.frequency_max_hz {
        Some(max_f) => {
            let bin = (max_f / df).round() as usize;
            bin.min(n_fft / 2)
        }
        None => n_fft / 2,
    };
    if last_bin == 0 {
        return Err(invalid("maximum frequency must be greater than zero"));
    }

    let simulation_grid = (0..=last_bin)
        .map(|i| SipiHertz::try_new(i as f64 * df).unwrap())
        .collect::<Vec<_>>();

    // Assemble stages: either explicitly given stages, or single touchstone file/content
    let stages = if let Some(stage_list) = &config.stages {
        if stage_list.is_empty() {
            return Err(invalid("stages list must not be empty"));
        }
        let mut built = Vec::with_capacity(stage_list.len());
        for stage_spec in stage_list {
            let net = resolve_stage_network(stage_spec, base_dir, ref_z, &simulation_grid)?;
            built.push(net);
        }
        built
    } else if config.file_path.is_some() || config.file_content.is_some() {
        let single_spec = TouchstoneStageSpecV1 {
            name: "primary_touchstone".into(),
            kind: Some("touchstone_file".into()),
            file_path: config.file_path.clone(),
            file_content: config.file_content.clone(),
            port_map: config.port_map.clone(),
            delay_seconds: None,
            line_impedance_ohms: None,
            propagation_velocity_m_per_s: None,
            length_m: None,
        };
        vec![resolve_stage_network(&single_spec, base_dir, ref_z, &simulation_grid)?]
    } else {
        return Err(invalid(
            "must specify either 'stages', 'filePath', or 'fileContent'",
        ));
    };

    // Cascade stages
    let cascaded_network = cascade_network_stages("total_cascaded_network", &stages)
        .map_err(|e| invalid(format!("cascading network stages failed: {e:?}")))?;

    // Diagnostics
    let grid_diag = assess_frequency_grid_coverage(
        cascaded_network.frequencies(),
        Some(SipiSeconds::try_new(dt).unwrap()),
    )
    .map_err(|e| invalid(format!("grid assessment failed: {e:?}")))?;

    let passivity_diag = evaluate_sampled_passivity(&cascaded_network)
        .map_err(|e| invalid(format!("passivity assessment failed: {e:?}")))?;

    let reciprocity_diag = evaluate_sampled_reciprocity(&cascaded_network)
        .map_err(|e| invalid(format!("reciprocity assessment failed: {e:?}")))?;

    // Terminations and loaded voltage transfer
    let source_term = TerminationParamsV1::new(
        SipiOhms::try_new(config.source_impedance)
            .map_err(|_| invalid("source impedance must be positive"))?,
        config.source_capacitance_f,
    )
    .map_err(|e| invalid(format!("invalid source termination: {e:?}")))?;

    let load_term = TerminationParamsV1::new(
        SipiOhms::try_new(config.load_impedance)
            .map_err(|_| invalid("load impedance must be positive"))?,
        config.load_capacitance_f,
    )
    .map_err(|e| invalid(format!("invalid load termination: {e:?}")))?;

    let loaded_transfer = calculate_loaded_voltage_transfer(&cascaded_network, source_term, load_term)
        .map_err(|e| invalid(format!("calculating loaded transfer failed: {e:?}")))?;

    // Single final FD-to-TD transformation
    let impulse_len = config.impulse_length.map(|l| SipiSeconds::try_new(l).unwrap());
    let (kernel, kernel_metrics) = spectrum_to_discrete_kernel(
        cascaded_network.frequencies(),
        &loaded_transfer,
        SipiSeconds::try_new(dt).unwrap(),
        config.apply_raised_cosine_window,
        impulse_len,
    )
    .map_err(|e| invalid(format!("spectrum to kernel IFFT failed: {e:?}")))?;

    let impulse_v_per_s = kernel.iter().map(|&v| v / dt).collect::<Vec<_>>();

    let channel_response = ChannelResponseV1 {
        sample_interval: Seconds(dt),
        impulse_response_volts_per_second: impulse_v_per_s,
        source_impedance: Ohms(config.source_impedance),
        load_impedance: Ohms(config.load_impedance),
    };

    let mut direct_input = input.clone();
    direct_input.channel = ChannelInputV1::ImpulseResponse(channel_response);

    // Run native link simulation (PRBS, TX FFE, RX CTLE, FFE, DFE/CDR)
    let mut output = simulate_native_v1(&direct_input).map_err(NativeSimulationError::from)?;

    // Prepare telemetry arrays
    let freqs_hz = cascaded_network.frequencies().iter().map(|f| f.get()).collect::<Vec<_>>();
    let s11_re = cascaded_network.samples().iter().map(|s| s.s11.real()).collect::<Vec<_>>();
    let s11_im = cascaded_network.samples().iter().map(|s| s.s11.imaginary()).collect::<Vec<_>>();
    let s21_re = cascaded_network.samples().iter().map(|s| s.s21.real()).collect::<Vec<_>>();
    let s21_im = cascaded_network.samples().iter().map(|s| s.s21.imaginary()).collect::<Vec<_>>();
    let s12_re = cascaded_network.samples().iter().map(|s| s.s12.real()).collect::<Vec<_>>();
    let s12_im = cascaded_network.samples().iter().map(|s| s.s12.imaginary()).collect::<Vec<_>>();
    let s22_re = cascaded_network.samples().iter().map(|s| s.s22.real()).collect::<Vec<_>>();
    let s22_im = cascaded_network.samples().iter().map(|s| s.s22.imaginary()).collect::<Vec<_>>();

    let loaded_h_re = loaded_transfer.iter().map(|c| c.re).collect::<Vec<_>>();
    let loaded_h_im = loaded_transfer.iter().map(|c| c.im).collect::<Vec<_>>();

    let max_f = freqs_hz[freqs_hz.len() - 1];
    let windowed_h_re = loaded_transfer
        .iter()
        .zip(&freqs_hz)
        .map(|(c, &f)| {
            let w = if config.apply_raised_cosine_window && max_f > 0.0 {
                0.5 * (1.0 + (std::f64::consts::PI * f / max_f).cos())
            } else {
                1.0
            };
            c.re * w
        })
        .collect::<Vec<_>>();
    let windowed_h_im = loaded_transfer
        .iter()
        .zip(&freqs_hz)
        .map(|(c, &f)| {
            let w = if config.apply_raised_cosine_window && max_f > 0.0 {
                0.5 * (1.0 + (std::f64::consts::PI * f / max_f).cos())
            } else {
                1.0
            };
            c.im * w
        })
        .collect::<Vec<_>>();

    output.arrays.insert("touchstone_frequency_hz".into(), freqs_hz);
    output.arrays.insert("touchstone_s11_re".into(), s11_re);
    output.arrays.insert("touchstone_s11_im".into(), s11_im);
    output.arrays.insert("touchstone_s21_re".into(), s21_re);
    output.arrays.insert("touchstone_s21_im".into(), s21_im);
    output.arrays.insert("touchstone_s12_re".into(), s12_re);
    output.arrays.insert("touchstone_s12_im".into(), s12_im);
    output.arrays.insert("touchstone_s22_re".into(), s22_re);
    output.arrays.insert("touchstone_s22_im".into(), s22_im);
    output.arrays.insert("touchstone_loaded_h_re".into(), loaded_h_re);
    output.arrays.insert("touchstone_loaded_h_im".into(), loaded_h_im);
    output.arrays.insert("touchstone_windowed_h_re".into(), windowed_h_re);
    output.arrays.insert("touchstone_windowed_h_im".into(), windowed_h_im);

    // If multi-stage, export intermediate stage transmission
    if stages.len() > 1 {
        for (i, stage) in stages.iter().enumerate() {
            let s21_stage_re = stage.samples().iter().map(|s| s.s21.real()).collect::<Vec<_>>();
            let s21_stage_im = stage.samples().iter().map(|s| s.s21.imaginary()).collect::<Vec<_>>();
            output.arrays.insert(format!("touchstone_stage_{i}_{}_s21_re", stage.name()), s21_stage_re);
            output.arrays.insert(format!("touchstone_stage_{i}_{}_s21_im", stage.name()), s21_stage_im);
        }
    }

    let stage_metadata = stages
        .iter()
        .map(|s| {
            json!({
                "name": s.name(),
                "sampleCount": s.sample_count(),
                "referenceImpedance": s.reference_impedance().get(),
            })
        })
        .collect::<Vec<_>>();
    let dfe_invariance_diagnostic = if let Some(dfe_cfg) = &input.rx.dfe {
        if let Some(end_ui) = dfe_cfg.training_end_ui {
            if let (Some(weights_flat), Some(clock_times)) = (
                output.arrays.get("dfe_tap_weights_v"),
                output.arrays.get("dfe_clock_times_s"),
            ) {
                let n_taps = input.rx.dfe_taps as usize;
                let end_idx = (end_ui as usize).min(clock_times.len());
                let frozen_weights = (0..n_taps)
                    .map(|t| weights_flat.get(end_idx * n_taps + t).copied().unwrap_or(0.0))
                    .collect::<Vec<_>>();
                let mut max_drift = 0.0_f64;
                for k in end_idx..clock_times.len() {
                    for t in 0..n_taps {
                        let w = weights_flat.get(k * n_taps + t).copied().unwrap_or(0.0);
                        let drift = (w - frozen_weights[t]).abs();
                        if drift > max_drift {
                            max_drift = drift;
                        }
                    }
                }
                Some(json!({
                    "checked": true,
                    "training_end_ui": end_ui,
                    "passes_invariance": max_drift == 0.0,
                    "maximum_drift": max_drift,
                }))
            } else {
                None
            }
        } else {
            None
        }
    } else {
        None
    };


    let diagnostics_json = json!({
        "touchstone_network": {
            "policy": TOUCHSTONE_CHANNEL_POLICY_V1,
            "acceptance": false,
            "stage_count": stages.len(),
            "stages": stage_metadata,
            "frequency_grid_coverage": {
                "is_uniform": grid_diag.is_uniform,
                "frequency_step_hz": grid_diag.frequency_step_hz,
                "has_dc": grid_diag.has_dc,
                "min_frequency_hz": grid_diag.min_frequency_hz,
                "max_frequency_hz": grid_diag.max_frequency_hz,
                "nyquist_frequency_hz": grid_diag.nyquist_frequency_hz,
                "nyquist_coverage_ratio": grid_diag.nyquist_coverage_ratio,
                "nyquist_adequate": grid_diag.nyquist_adequate,
            },
            "passivity": {
                "passes_bound": passivity_diag.passes_bound,
                "maximum_singular_value": passivity_diag.maximum_singular_value,
                "worst_frequency_hz": passivity_diag.worst_frequency_hz,
                "worst_index": passivity_diag.worst_index,
            },
            "reciprocity": {
                "passes_bound": reciprocity_diag.passes_bound,
                "maximum_difference": reciprocity_diag.maximum_difference,
                "worst_frequency_hz": reciprocity_diag.worst_frequency_hz,
                "worst_index": reciprocity_diag.worst_index,
            },
            "causality": {
                "status": "NotAssessedFiniteBandPeriodicDft",
                "precursor_energy_ratio": kernel_metrics.precursor_energy_ratio,
                "tail_energy_ratio": kernel_metrics.tail_energy_ratio,
                "peak_index": kernel_metrics.peak_index,
                "peak_time_s": kernel_metrics.peak_time_s,
                "peak_value": kernel_metrics.peak_value,
                "diagnostic_only": true,
            },
            "terminations": {
                "source_resistance_ohms": config.source_impedance,
                "source_capacitance_f": config.source_capacitance_f,
                "load_resistance_ohms": config.load_impedance,
                "load_capacitance_f": config.load_capacitance_f,
            },
            "dfe_training_invariance": dfe_invariance_diagnostic,
        }
    });

    write_simulation_artifacts_with_schema_and_backend(
        crate::runner::upstream_native_input(direct_input),
        input_file,
        output_dir,
        output,
        Some(diagnostics_json),
        TOUCHSTONE_RESULT_SCHEMA_V1,
        "rust_channel_touchstone_network",
        None,
    )
}
