//! Native linear FFE stages; file parsing and AMI models remain host-owned.

use num_complex::Complex64;
use thiserror::Error;

use crate::{SignalError, convolve_truncated, inverse_real_spectrum, zero_pad};

#[derive(Debug, Error, PartialEq)]
pub enum EqualizationError {
    #[error("FFE weights must not be empty")]
    EmptyWeights,
    #[error("FFE weights must contain only finite values")]
    NonFiniteWeights,
    #[error("samples per UI must be greater than zero")]
    InvalidSamplesPerUi,
    #[error("CTLE parameters must be finite and greater than zero")]
    InvalidCtleParameters,
    #[error("CTLE frequencies must be finite and non-negative")]
    InvalidCtleFrequencies,
    #[error(transparent)]
    Signal(#[from] SignalError),
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct CtleConfig {
    pub rx_bandwidth_hz: f64,
    pub peak_frequency_hz: f64,
    pub peak_magnitude_db: f64,
}

/// Match PyBERT's normalized two-pole, one-zero CTLE response.
pub fn ctle_frequency_response(
    config: CtleConfig,
    frequencies_hz: &[f64],
) -> Result<Vec<Complex64>, EqualizationError> {
    if !config.rx_bandwidth_hz.is_finite()
        || config.rx_bandwidth_hz <= 0.0
        || !config.peak_frequency_hz.is_finite()
        || config.peak_frequency_hz <= 0.0
        || !config.peak_magnitude_db.is_finite()
    {
        return Err(EqualizationError::InvalidCtleParameters);
    }
    if frequencies_hz.is_empty()
        || frequencies_hz
            .iter()
            .any(|frequency| !frequency.is_finite() || *frequency < 0.0)
    {
        return Err(EqualizationError::InvalidCtleFrequencies);
    }
    let p2 = -std::f64::consts::TAU * config.rx_bandwidth_hz;
    let p1 = -std::f64::consts::TAU * config.peak_frequency_hz;
    let zero = p1 / 10_f64.powf(config.peak_magnitude_db / 20.0);
    let (residue1, residue2) = if p2 != p1 {
        let first = (zero - p1) / (p2 - p1);
        (first, 1.0 - first)
    } else {
        (-1.0, zero - p1)
    };
    let mut response = frequencies_hz
        .iter()
        .map(|frequency| {
            let s = Complex64::new(0.0, std::f64::consts::TAU * frequency);
            Complex64::new(residue1, 0.0) / (s - Complex64::new(p1, 0.0))
                + Complex64::new(residue2, 0.0) / (s - Complex64::new(p2, 0.0))
        })
        .collect::<Vec<_>>();
    let scale = response
        .iter()
        .map(|value| value.norm())
        .fold(0.0, f64::max);
    if !scale.is_finite() || scale <= 0.0 {
        return Err(EqualizationError::InvalidCtleParameters);
    }
    for value in &mut response {
        *value /= scale;
    }
    Ok(response)
}

/// Sample the normalized PyBERT CTLE on an `rfft` grid and return its real
/// time-domain impulse response. This is the native equivalent of
/// `make_ctle(...); irfft(H)` when the requested time grid is uniform.
pub fn ctle_impulse_response(
    config: CtleConfig,
    fft_size: usize,
    sample_interval_s: f64,
) -> Result<Vec<f64>, EqualizationError> {
    if fft_size < 2 || !sample_interval_s.is_finite() || sample_interval_s <= 0.0 {
        return Err(EqualizationError::InvalidCtleParameters);
    }
    let frequencies = (0..=(fft_size / 2))
        .map(|index| index as f64 / (fft_size as f64 * sample_interval_s))
        .collect::<Vec<_>>();
    let response = ctle_frequency_response(config, &frequencies)?;
    let real = response.iter().map(|value| value.re).collect::<Vec<_>>();
    let imag = response.iter().map(|value| value.im).collect::<Vec<_>>();
    Ok(inverse_real_spectrum(&real, &imag, fft_size)?)
}

pub fn ffe_impulse_response(
    weights: &[f64],
    samples_per_ui: usize,
    output_len: usize,
) -> Result<Vec<f64>, EqualizationError> {
    if weights.is_empty() {
        return Err(EqualizationError::EmptyWeights);
    }
    if weights.iter().any(|weight| !weight.is_finite()) {
        return Err(EqualizationError::NonFiniteWeights);
    }
    if samples_per_ui == 0 {
        return Err(EqualizationError::InvalidSamplesPerUi);
    }
    let mut impulse = vec![0.0; weights.len() * samples_per_ui];
    for (index, &weight) in weights.iter().enumerate() {
        impulse[index * samples_per_ui] = weight;
    }
    Ok(zero_pad(&impulse, output_len)?)
}

pub fn apply_ffe(
    samples: &[f64],
    weights: &[f64],
    samples_per_ui: usize,
) -> Result<Vec<f64>, EqualizationError> {
    let impulse = ffe_impulse_response(weights, samples_per_ui, weights.len() * samples_per_ui)?;
    Ok(convolve_truncated(samples, &impulse, samples.len())?)
}

pub fn apply_ffe_to_response(
    response: &[f64],
    weights: &[f64],
    samples_per_ui: usize,
) -> Result<Vec<f64>, EqualizationError> {
    let impulse = ffe_impulse_response(weights, samples_per_ui, response.len())?;
    Ok(convolve_truncated(response, &impulse, response.len())?)
}
