#![forbid(unsafe_code)]

//! Measured TX pulse response stimulus and symbol-response overlap-add modeling.
//!
//! This module replaces the ideal rectangular symbol-hold with a linear
//! overlap-add of an empirically measured or fitted single-pulse response p(t),
//! such as those produced by the TXF-01 linear fit workflow.
//!
//! Semantic contract:
//! - A one-hot symbol [1, 0, 0, ...] exactly reproduces the pulse response.
//! - Consecutive symbols linearly superpose with UI spacing:
//!   v_tx[n] = sum_k s[k] * p[n - k * samples_per_ui]
//! - Grid resampling is performed with linear interpolation when the measured
//!   pulse sampling interval dt_pulse differs from the simulation interval dt.

use serde::{Deserialize, Serialize};
use thiserror::Error;

#[derive(Debug, Error, PartialEq)]
pub enum MeasuredTxError {
    #[error("pulse response is empty or contains non-finite samples")]
    InvalidPulse,
    #[error("invalid sample interval: {0}")]
    InvalidSampleInterval(f64),
    #[error("invalid amplitude scale: {0}")]
    InvalidScale(f64),
    #[error("cursor index {cursor} exceeds pulse length {len}")]
    InvalidCursor { cursor: usize, len: usize },
}

/// Typed configuration for empirical or fitted TX single-pulse response stimulus.
#[derive(Debug, Clone, Deserialize, Serialize, PartialEq)]
#[serde(rename_all = "camelCase")]
pub struct MeasuredTxPulseConfigV1 {
    /// Time-domain samples of the pulse response p(t) in Volts
    pub pulse_response_v: Vec<f64>,
    /// Sample interval of the pulse response in seconds (defaults to simulation sampleInterval)
    #[serde(default)]
    pub sample_interval_s: Option<f64>,
    /// Cursor/peak sample index in the pulse response (defaults to argmax of |p|)
    #[serde(default)]
    pub cursor_index: Option<usize>,
    /// Amplitude scaling factor (defaults to 1.0)
    #[serde(default)]
    pub amplitude_scale: Option<f64>,
    /// Measurement reference plane description (e.g. "tp0", "tp0a", "dut_pin")
    #[serde(default)]
    pub reference_plane: Option<String>,
}

impl MeasuredTxPulseConfigV1 {
    pub fn validate(&self) -> Result<(), MeasuredTxError> {
        if self.pulse_response_v.is_empty() || self.pulse_response_v.iter().any(|&v| !v.is_finite()) {
            return Err(MeasuredTxError::InvalidPulse);
        }
        if let Some(dt) = self.sample_interval_s {
            if !dt.is_finite() || dt <= 0.0 {
                return Err(MeasuredTxError::InvalidSampleInterval(dt));
            }
        }
        if let Some(scale) = self.amplitude_scale {
            if !scale.is_finite() || scale <= 0.0 {
                return Err(MeasuredTxError::InvalidScale(scale));
            }
        }
        if let Some(cursor) = self.cursor_index {
            if cursor >= self.pulse_response_v.len() {
                return Err(MeasuredTxError::InvalidCursor {
                    cursor,
                    len: self.pulse_response_v.len(),
                });
            }
        }
        Ok(())
    }
}

/// Linearly resample a pulse response from source interval dt_src to destination interval dt_dst.
pub fn resample_pulse_linear(raw: &[f64], dt_src: f64, dt_dst: f64) -> Result<Vec<f64>, MeasuredTxError> {
    if raw.is_empty() || raw.iter().any(|&v| !v.is_finite()) {
        return Err(MeasuredTxError::InvalidPulse);
    }
    if !dt_src.is_finite() || dt_src <= 0.0 {
        return Err(MeasuredTxError::InvalidSampleInterval(dt_src));
    }
    if !dt_dst.is_finite() || dt_dst <= 0.0 {
        return Err(MeasuredTxError::InvalidSampleInterval(dt_dst));
    }

    if (dt_src - dt_dst).abs() < 1e-15 * dt_src {
        return Ok(raw.to_vec());
    }

    let total_duration = raw.len() as f64 * dt_src;
    let dst_len = (total_duration / dt_dst).ceil() as usize;
    let mut resampled = Vec::with_capacity(dst_len);

    for i in 0..dst_len {
        let t = i as f64 * dt_dst;
        let src_pos = t / dt_src;
        let idx0 = src_pos.floor() as usize;
        let frac = src_pos - idx0 as f64;

        if idx0 >= raw.len() {
            resampled.push(0.0);
        } else if idx0 == raw.len() - 1 {
            resampled.push(raw[idx0] * (1.0 - frac));
        } else {
            let val = raw[idx0] * (1.0 - frac) + raw[idx0 + 1] * frac;
            resampled.push(val);
        }
    }

    Ok(resampled)
}

/// Generate a transmit waveform by linear overlap-add of the measured pulse response.
///
/// Each symbol s[k] contributes an instance of the pulse response p(t) delayed by
/// k * samples_per_ui:
///   v_tx[n] = sum_k s[k] * p[n - k * samples_per_ui]
pub fn generate_measured_tx_waveform(
    symbols: &[f64],
    samples_per_ui: usize,
    sim_dt: f64,
    config: &MeasuredTxPulseConfigV1,
    output_length: usize,
) -> Result<Vec<f64>, MeasuredTxError> {
    config.validate()?;
    if symbols.is_empty() || samples_per_ui == 0 || output_length == 0 {
        return Ok(vec![0.0; output_length]);
    }
    if !sim_dt.is_finite() || sim_dt <= 0.0 {
        return Err(MeasuredTxError::InvalidSampleInterval(sim_dt));
    }

    let pulse_dt = config.sample_interval_s.unwrap_or(sim_dt);
    let pulse_on_grid = resample_pulse_linear(&config.pulse_response_v, pulse_dt, sim_dt)?;

    let scale = config.amplitude_scale.unwrap_or(1.0);
    let mut wave = vec![0.0; output_length];

    for (k, &s) in symbols.iter().enumerate() {
        let n_k = k * samples_per_ui;
        if n_k >= output_length {
            break;
        }
        for (m, &p_val) in pulse_on_grid.iter().enumerate() {
            let idx = n_k + m;
            if idx < output_length {
                wave[idx] += s * p_val * scale;
            }
        }
    }

    Ok(wave)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_one_hot_symbol_reproduces_pulse() {
        let p = vec![0.0, 0.25, 0.90, 1.0, 0.70, 0.35, 0.10, 0.0];
        let config = MeasuredTxPulseConfigV1 {
            pulse_response_v: p.clone(),
            sample_interval_s: Some(1.0e-12),
            cursor_index: Some(3),
            amplitude_scale: Some(1.0),
            reference_plane: Some("tp0".into()),
        };

        let symbols = vec![1.0, 0.0, 0.0, 0.0];
        let spui = 16;
        let wave = generate_measured_tx_waveform(&symbols, spui, 1.0e-12, &config, 64).unwrap();

        assert_eq!(wave.len(), 64);
        for (w, expected) in wave.iter().take(p.len()).zip(&p) {
            assert!((w - expected).abs() < 1e-12);
        }
        for &w in wave.iter().skip(p.len()) {
            assert_eq!(w, 0.0);
        }
    }

    #[test]
    fn test_two_symbol_ui_shifted_superposition() {
        let p = vec![0.1, 0.5, 1.0, 0.5, 0.1];
        let config = MeasuredTxPulseConfigV1 {
            pulse_response_v: p.clone(),
            sample_interval_s: None,
            cursor_index: None,
            amplitude_scale: None,
            reference_plane: None,
        };

        let symbols = vec![1.0, 1.0, 0.0];
        let spui = 4;
        let wave = generate_measured_tx_waveform(&symbols, spui, 1.0e-12, &config, 32).unwrap();

        for i in 0..p.len() {
            let expected = p[i] + if i >= spui { p[i - spui] } else { 0.0 };
            assert!((wave[i] - expected).abs() < 1e-12);
        }
    }

    #[test]
    fn test_linear_resampling() {
        let raw = vec![0.0, 1.0, 0.0];
        // Resample from dt=2.0 to dt=1.0 (doubling samples)
        let resampled = resample_pulse_linear(&raw, 2.0, 1.0).unwrap();
        assert_eq!(resampled.len(), 6);
        assert!((resampled[0] - 0.0).abs() < 1e-12);
        assert!((resampled[1] - 0.5).abs() < 1e-12);
        assert!((resampled[2] - 1.0).abs() < 1e-12);
        assert!((resampled[3] - 0.5).abs() < 1e-12);
        assert!((resampled[4] - 0.0).abs() < 1e-12);
    }
}
