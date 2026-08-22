//! Response derivation from uniformly sampled real impulse responses.

use num_complex::Complex64;
use thiserror::Error;

use crate::{SignalError, pulse_response, step_response, zero_pad};

#[derive(Debug, Error, PartialEq)]
pub enum ResponseError {
    #[error("time axis must contain at least two finite uniformly spaced samples")]
    InvalidTimeAxis,
    #[error(
        "frequency axis must contain at least two finite uniformly spaced samples beginning at zero"
    )]
    InvalidFrequencyAxis,
    #[error("unit interval must be finite and contain at least one sample")]
    InvalidUi,
    #[error("time axis must be at least as long as the impulse response")]
    TimeAxisTooShort,
    #[error(transparent)]
    Signal(#[from] SignalError),
}

#[derive(Debug, Clone, PartialEq)]
pub struct ResponseV1 {
    pub step: Vec<f64>,
    pub pulse: Vec<f64>,
    pub frequency: Vec<Complex64>,
}

pub fn calculate_responses(
    time_s: &[f64],
    impulse: &[f64],
    ui_s: f64,
    frequencies_hz: &[f64],
) -> Result<ResponseV1, ResponseError> {
    if time_s.len() < 2 || time_s.iter().any(|value| !value.is_finite()) {
        return Err(ResponseError::InvalidTimeAxis);
    }
    if frequencies_hz.len() < 2
        || frequencies_hz.iter().any(|value| !value.is_finite())
        || frequencies_hz[0].abs() > 1.0e-18
    {
        return Err(ResponseError::InvalidFrequencyAxis);
    }
    if time_s.len() < impulse.len() {
        return Err(ResponseError::TimeAxisTooShort);
    }
    let sample_interval = time_s[1] - time_s[0];
    let frequency_step = frequencies_hz[1] - frequencies_hz[0];
    if sample_interval <= 0.0 || !uniformly_spaced(time_s, sample_interval) {
        return Err(ResponseError::InvalidTimeAxis);
    }
    if frequency_step <= 0.0 || !uniformly_spaced(frequencies_hz, frequency_step) {
        return Err(ResponseError::InvalidFrequencyAxis);
    }
    if !ui_s.is_finite() || ui_s <= 0.0 {
        return Err(ResponseError::InvalidUi);
    }
    let samples_per_ui = (ui_s / sample_interval) as usize;
    if samples_per_ui == 0 {
        return Err(ResponseError::InvalidUi);
    }
    let fft_length = ((1.0 / frequency_step) / sample_interval + 0.5) as usize;
    if fft_length == 0 {
        return Err(ResponseError::InvalidFrequencyAxis);
    }
    let step = step_response(impulse)?;
    let pulse = pulse_response(&step, samples_per_ui)?;
    let padded_impulse = zero_pad(impulse, fft_length)?;
    let frequency = frequencies_hz
        .iter()
        .map(|&frequency_hz| {
            padded_impulse.iter().enumerate().fold(
                Complex64::new(0.0, 0.0),
                |sum, (index, &sample)| {
                    let phase =
                        -std::f64::consts::TAU * frequency_hz * index as f64 * sample_interval;
                    sum + Complex64::from_polar(sample, phase)
                },
            )
        })
        .collect();
    Ok(ResponseV1 {
        step,
        pulse,
        frequency,
    })
}

fn uniformly_spaced(values: &[f64], expected_step: f64) -> bool {
    let tolerance = 1.0e-18_f64.max(expected_step.abs() * 1.0e-12);
    values
        .windows(2)
        .all(|window| (window[1] - window[0] - expected_step).abs() <= tolerance)
}
