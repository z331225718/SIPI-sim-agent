#![forbid(unsafe_code)]

//! Multi-channel crosstalk (NEXT/FEXT) network modeling, asynchronous aggressor
//! waveform generation, and time-domain linear superposition.
//!
//! This module computes the induced crosstalk noise on a victim channel from one
//! or more aggressor channels. Aggressors can have independent PRBS patterns,
//! distinct modulation (NRZ or PAM4), arbitrary time/phase delays, and
//! asynchronous clock frequency offsets (ppm).

use serde::{Deserialize, Serialize};
use thiserror::Error;

use crate::{
    ModulationV1, SymbolModulation, causal_convolve_truncated, generate_prbs_bits,
    modulate_bits,
};

#[derive(Debug, Error, PartialEq)]
pub enum CrosstalkError {
    #[error("invalid aggressor configuration: {0}")]
    InvalidConfig(String),
    #[error("crosstalk impulse response is empty or non-finite")]
    InvalidImpulse,
    #[error("convolution failed: {0}")]
    ConvolutionFailed(String),
}

/// Specification for an individual aggressor channel in a crosstalk environment.
#[derive(Debug, Clone, Deserialize, Serialize, PartialEq)]
#[serde(rename_all = "camelCase")]
pub struct AggressorConfigV1 {
    pub name: String,
    #[serde(default = "default_aggressor_kind")]
    pub kind: String, // "fext" or "next"
    #[serde(default)]
    pub amplitude_v: Option<f64>,
    #[serde(default)]
    pub delay_seconds: Option<f64>,
    #[serde(default)]
    pub freq_offset_ppm: Option<f64>,
    #[serde(default)]
    pub modulation: Option<ModulationV1>,
    #[serde(default)]
    pub prbs_order: Option<u32>,
    #[serde(default)]
    pub prbs_seed: Option<u64>,
    #[serde(default)]
    pub coupling_coeff: Option<f64>,
    #[serde(default)]
    pub channel_file: Option<String>,
    #[serde(default)]
    pub channel_content: Option<String>,
    #[serde(default)]
    pub port_indices: Option<[usize; 4]>,
}

fn default_aggressor_kind() -> String {
    "fext".into()
}

/// Individual summary metrics for a single aggressor's contribution.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct AggressorRunSummary {
    pub name: String,
    pub kind: String,
    pub rms_voltage_v: f64,
    pub peak_to_peak_v: f64,
}

/// Overall crosstalk analysis and noise metrics.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct CrosstalkMetrics {
    pub total_rms_v: f64,
    pub total_peak_to_peak_v: f64,
    pub signal_to_crosstalk_ratio_db: f64,
    pub aggressor_summaries: Vec<AggressorRunSummary>,
}

/// Generate an aggressor transmit waveform on the simulation time grid,
/// accounting for independent PRBS patterns, modulation, delay, and ppm frequency offset.
pub fn generate_aggressor_waveform(
    config: &AggressorConfigV1,
    nominal_ui_seconds: f64,
    sample_interval_seconds: f64,
    total_samples: usize,
    default_amplitude_v: f64,
) -> Result<Vec<f64>, CrosstalkError> {
    if total_samples == 0 || nominal_ui_seconds <= 0.0 || sample_interval_seconds <= 0.0 {
        return Err(CrosstalkError::InvalidConfig("invalid time parameters".into()));
    }

    let amplitude = config.amplitude_v.unwrap_or(default_amplitude_v);
    if !amplitude.is_finite() || amplitude <= 0.0 {
        return Err(CrosstalkError::InvalidConfig("amplitude must be positive and finite".into()));
    }

    let order = config.prbs_order.unwrap_or(7);
    let seed = config.prbs_seed.unwrap_or_else(|| {
        // Deterministic hash of the aggressor name to avoid identical seed with victim
        config.name.bytes().fold(0x1234_5678_9ABC_DEF0_u64, |acc, b| {
            acc.wrapping_mul(31).wrapping_add(b as u64)
        })
    });

    let modulation = match config.modulation.clone().unwrap_or(ModulationV1::Nrz) {
        ModulationV1::Nrz => SymbolModulation::Nrz,
        ModulationV1::Pam4 => SymbolModulation::Pam4,
        ModulationV1::DuoBinary => SymbolModulation::DuoBinary,
    };

    // Calculate effective aggressor UI period with ppm offset
    let ppm = config.freq_offset_ppm.unwrap_or(0.0);
    if !ppm.is_finite() || ppm.abs() > 10_000.0 {
        return Err(CrosstalkError::InvalidConfig("ppm offset must be within +/- 10000".into()));
    }
    let effective_ui = nominal_ui_seconds / (1.0 + ppm * 1.0e-6);

    let total_duration = total_samples as f64 * sample_interval_seconds;
    let required_symbols = ((total_duration / effective_ui).ceil() as usize + 64).max(128);
    let bit_count = match modulation {
        SymbolModulation::Pam4 => required_symbols * 2,
        _ => required_symbols,
    };

    let bits = generate_prbs_bits(order as u8, seed, bit_count)
        .map_err(|e| CrosstalkError::InvalidConfig(e.to_string()))?;
    let symbols = modulate_bits(&bits, modulation, amplitude)
        .map_err(|e| CrosstalkError::InvalidConfig(e.to_string()))?;

    let delay = config.delay_seconds.unwrap_or(0.0);

    let mut waveform = Vec::with_capacity(total_samples);
    for n in 0..total_samples {
        let t = n as f64 * sample_interval_seconds;
        if t < delay {
            waveform.push(0.0);
        } else {
            let symbol_idx = (((t - delay) / effective_ui).floor() as usize) % symbols.len();
            waveform.push(symbols[symbol_idx]);
        }
    }

    Ok(waveform)
}

/// Convolve an aggressor transmit waveform with a crosstalk channel impulse response
/// (scaled by dt) to produce the induced crosstalk voltage on the victim receiver.
pub fn calculate_induced_crosstalk_noise(
    tx_waveform: &[f64],
    xtalk_impulse_v_per_s: &[f64],
    sample_interval_seconds: f64,
) -> Result<Vec<f64>, CrosstalkError> {
    if tx_waveform.is_empty() || xtalk_impulse_v_per_s.is_empty() {
        return Err(CrosstalkError::InvalidImpulse);
    }
    if xtalk_impulse_v_per_s.iter().any(|&v| !v.is_finite()) {
        return Err(CrosstalkError::InvalidImpulse);
    }

    // Scale impulse response by sample interval dt to get dimensionless discrete convolution
    let scaled_impulse: Vec<f64> = xtalk_impulse_v_per_s
        .iter()
        .map(|&h| h * sample_interval_seconds)
        .collect();

    causal_convolve_truncated(tx_waveform, &scaled_impulse, tx_waveform.len())
        .map_err(|e| CrosstalkError::ConvolutionFailed(e.to_string()))
}

/// Compute overall crosstalk metrics from individual aggressor noise waveforms
/// and the clean victim received signal.
pub fn evaluate_crosstalk_metrics(
    aggressor_noises: &[(&AggressorConfigV1, Vec<f64>)],
    victim_rx_waveform: &[f64],
) -> (Vec<f64>, CrosstalkMetrics) {
    let sample_count = victim_rx_waveform.len();
    let mut total_xtalk_waveform = vec![0.0; sample_count];
    let mut summaries = Vec::with_capacity(aggressor_noises.len());

    for (config, noise) in aggressor_noises {
        let mut sum_sq = 0.0;
        let mut min_val = f64::INFINITY;
        let mut max_val = f64::NEG_INFINITY;

        for (i, &val) in noise.iter().take(sample_count).enumerate() {
            total_xtalk_waveform[i] += val;
            sum_sq += val * val;
            if val < min_val {
                min_val = val;
            }
            if val > max_val {
                max_val = val;
            }
        }

        let n = noise.len().max(1) as f64;
        let rms = (sum_sq / n).sqrt();
        let p2p = if max_val >= min_val { max_val - min_val } else { 0.0 };

        summaries.push(AggressorRunSummary {
            name: config.name.clone(),
            kind: config.kind.clone(),
            rms_voltage_v: rms,
            peak_to_peak_v: p2p,
        });
    }

    // Compute total metrics
    let mut tot_sum = 0.0;
    let mut tot_sum_sq = 0.0;
    let mut tot_min = f64::INFINITY;
    let mut tot_max = f64::NEG_INFINITY;

    for &val in &total_xtalk_waveform {
        tot_sum += val;
        tot_sum_sq += val * val;
        if val < tot_min {
            tot_min = val;
        }
        if val > tot_max {
            tot_max = val;
        }
    }

    let n = sample_count.max(1) as f64;
    let mean = tot_sum / n;
    let variance = (tot_sum_sq / n - mean * mean).max(0.0);
    let total_rms = variance.sqrt();
    let total_p2p = if tot_max >= tot_min { tot_max - tot_min } else { 0.0 };

    let victim_min = victim_rx_waveform.iter().copied().fold(f64::INFINITY, f64::min);
    let victim_max = victim_rx_waveform.iter().copied().fold(f64::NEG_INFINITY, f64::max);
    let victim_p2p = (victim_max - victim_min).max(1.0e-6);

    let scr_db = 20.0 * (victim_p2p / (total_p2p + 1.0e-12)).log10();

    let metrics = CrosstalkMetrics {
        total_rms_v: total_rms,
        total_peak_to_peak_v: total_p2p,
        signal_to_crosstalk_ratio_db: scr_db,
        aggressor_summaries: summaries,
    };

    (total_xtalk_waveform, metrics)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_aggressor_waveform_generation_nrz_and_pam4() {
        let nrz_config = AggressorConfigV1 {
            name: "agg1".into(),
            kind: "fext".into(),
            amplitude_v: Some(0.8),
            delay_seconds: Some(0.0),
            freq_offset_ppm: Some(0.0),
            modulation: Some(ModulationV1::Nrz),
            prbs_order: Some(7),
            prbs_seed: Some(42),
            coupling_coeff: None,
            channel_file: None,
            channel_content: None,
            port_indices: None,
        };

        let dt = 1.0e-12;
        let ui = 32.0e-12; // 32 samples per UI
        let samples = 320; // 10 UI

        let wave_nrz = generate_aggressor_waveform(&nrz_config, ui, dt, samples, 0.5).unwrap();
        assert_eq!(wave_nrz.len(), samples);
        for &v in &wave_nrz {
            assert!((v.abs() - 0.4).abs() < 1e-6);
        }

        let pam4_config = AggressorConfigV1 {
            modulation: Some(ModulationV1::Pam4),
            ..nrz_config
        };
        let wave_pam4 = generate_aggressor_waveform(&pam4_config, ui, dt, samples, 0.5).unwrap();
        assert_eq!(wave_pam4.len(), samples);
    }

    #[test]
    fn test_induced_crosstalk_linearity_and_metrics() {
        let config = AggressorConfigV1 {
            name: "fext1".into(),
            kind: "fext".into(),
            amplitude_v: Some(1.0),
            delay_seconds: None,
            freq_offset_ppm: None,
            modulation: None,
            prbs_order: Some(7),
            prbs_seed: Some(123),
            coupling_coeff: None,
            channel_file: None,
            channel_content: None,
            port_indices: None,
        };

        let dt = 1.0e-12;
        let ui = 20.0e-12;
        let samples = 200;
        let tx = generate_aggressor_waveform(&config, ui, dt, samples, 1.0).unwrap();

        // Simple impulse response representing capacitive/inductive crosstalk: high-pass spike
        let mut impulse = vec![0.0; 32];
        impulse[1] = 0.05 / dt;
        impulse[2] = -0.05 / dt;

        let noise = calculate_induced_crosstalk_noise(&tx, &impulse, dt).unwrap();
        assert_eq!(noise.len(), samples);

        // Verify linearity: doubling impulse doubles noise
        let mut double_impulse = impulse.clone();
        for v in &mut double_impulse {
            *v *= 2.0;
        }
        let double_noise = calculate_induced_crosstalk_noise(&tx, &double_impulse, dt).unwrap();
        for (a, b) in noise.iter().zip(&double_noise) {
            assert!((a * 2.0 - b).abs() < 1e-12);
        }

        let victim_wave = vec![0.5; samples];
        let (tot_noise, metrics) = evaluate_crosstalk_metrics(&[(&config, noise)], &victim_wave);
        assert_eq!(tot_noise.len(), samples);
        assert!(metrics.total_rms_v > 0.0);
        assert!(metrics.total_peak_to_peak_v > 0.0);
        assert!(metrics.signal_to_crosstalk_ratio_db.is_finite());
    }
}
