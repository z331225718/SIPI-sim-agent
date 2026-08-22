//! Pure real-valued signal primitives shared by native link stages.

use rustfft::{FftPlanner, num_complex::Complex};
use thiserror::Error;

// Small filters are faster and bit-for-bit stable with direct accumulation.
// Long link impulses require FFT convolution to keep native end-to-end runs
// bounded as waveform lengths grow.
const FFT_CONVOLUTION_WORK_THRESHOLD: usize = 1 << 18;

#[derive(Debug, Error, PartialEq)]
pub enum SignalError {
    #[error("signal inputs must not be empty")]
    EmptyInput,
    #[error("signal inputs must contain only finite values")]
    NonFiniteInput,
    #[error("samples per UI must be greater than zero")]
    InvalidSamplesPerUi,
    #[error(
        "real spectrum must contain finite real/imaginary bins for the requested output length"
    )]
    InvalidSpectrum,
}

pub fn linear_convolve(left: &[f64], right: &[f64]) -> Result<Vec<f64>, SignalError> {
    validate_signal(left)?;
    validate_signal(right)?;
    if left.len().saturating_mul(right.len()) >= FFT_CONVOLUTION_WORK_THRESHOLD {
        return Ok(fft_linear_convolve(left, right));
    }
    Ok(direct_linear_convolve(left, right))
}

fn direct_linear_convolve(left: &[f64], right: &[f64]) -> Vec<f64> {
    let mut output = vec![0.0; left.len() + right.len() - 1];
    for (left_index, &left_value) in left.iter().enumerate() {
        for (right_index, &right_value) in right.iter().enumerate() {
            output[left_index + right_index] += left_value * right_value;
        }
    }
    output
}

fn fft_linear_convolve(left: &[f64], right: &[f64]) -> Vec<f64> {
    let output_len = left.len() + right.len() - 1;
    let fft_len = output_len.next_power_of_two();
    let mut left_spectrum = vec![Complex::new(0.0, 0.0); fft_len];
    let mut right_spectrum = vec![Complex::new(0.0, 0.0); fft_len];
    left_spectrum[..left.len()]
        .iter_mut()
        .zip(left)
        .for_each(|(value, &sample)| value.re = sample);
    right_spectrum[..right.len()]
        .iter_mut()
        .zip(right)
        .for_each(|(value, &sample)| value.re = sample);

    let mut planner = FftPlanner::<f64>::new();
    planner
        .plan_fft_forward(fft_len)
        .process(&mut left_spectrum);
    planner
        .plan_fft_forward(fft_len)
        .process(&mut right_spectrum);
    left_spectrum
        .iter_mut()
        .zip(&right_spectrum)
        .for_each(|(left_bin, right_bin)| *left_bin *= *right_bin);
    planner
        .plan_fft_inverse(fft_len)
        .process(&mut left_spectrum);
    let scale = 1.0 / fft_len as f64;
    left_spectrum[..output_len]
        .iter()
        .map(|value| value.re * scale)
        .collect()
}

pub fn convolve_truncated(
    left: &[f64],
    right: &[f64],
    output_len: usize,
) -> Result<Vec<f64>, SignalError> {
    let mut output = linear_convolve(left, right)?;
    output.truncate(output_len.min(output.len()));
    Ok(output)
}

/// Apply a sparse causal FIR without introducing FFT leakage into its
/// mathematically zero prefix. This is intentionally separate from the
/// general convolution API because it fixes the RX tapped-delay contract.
pub fn sparse_tapped_convolve_truncated(
    signal: &[f64],
    taps: &[f64],
    output_len: usize,
) -> Result<Vec<f64>, SignalError> {
    validate_signal(signal)?;
    validate_signal(taps)?;
    let full_length = signal.len() + taps.len() - 1;
    let bounded_length = output_len.min(full_length);
    let mut output = vec![0.0; bounded_length];
    for (tap_index, &tap) in taps.iter().enumerate().filter(|(_, tap)| **tap != 0.0) {
        let source_length = signal.len().min(bounded_length.saturating_sub(tap_index));
        for (sample_index, &sample) in signal.iter().take(source_length).enumerate() {
            output[tap_index + sample_index] += tap * sample;
        }
    }
    Ok(output)
}

/// Preserve the causal zero prefix while retaining the established convolution
/// implementation for the nonzero tails.
pub fn causal_convolve_truncated(
    left: &[f64],
    right: &[f64],
    output_len: usize,
) -> Result<Vec<f64>, SignalError> {
    validate_signal(left)?;
    validate_signal(right)?;
    let full_length = left.len() + right.len() - 1;
    let bounded_length = output_len.min(full_length);
    let mut output = vec![0.0; bounded_length];
    let Some(left_start) = left.iter().position(|value| *value != 0.0) else {
        return Ok(output);
    };
    let Some(right_start) = right.iter().position(|value| *value != 0.0) else {
        return Ok(output);
    };
    let prefix_length = left_start + right_start;
    let tail_length = bounded_length.saturating_sub(prefix_length);
    if tail_length == 0 {
        return Ok(output);
    }
    let tail = convolve_truncated(&left[left_start..], &right[right_start..], tail_length)?;
    output[prefix_length..prefix_length + tail.len()].copy_from_slice(&tail);
    Ok(output)
}

pub fn step_response(impulse: &[f64]) -> Result<Vec<f64>, SignalError> {
    validate_signal(impulse)?;
    let mut total = 0.0;
    Ok(impulse
        .iter()
        .map(|sample| {
            total += sample;
            total
        })
        .collect())
}

pub fn pulse_response(step: &[f64], samples_per_ui: usize) -> Result<Vec<f64>, SignalError> {
    validate_signal(step)?;
    if samples_per_ui == 0 {
        return Err(SignalError::InvalidSamplesPerUi);
    }
    Ok(step
        .iter()
        .enumerate()
        .map(|(index, &value)| {
            value
                - index
                    .checked_sub(samples_per_ui)
                    .map_or(0.0, |previous| step[previous])
        })
        .collect())
}

pub fn zero_pad(values: &[f64], output_len: usize) -> Result<Vec<f64>, SignalError> {
    validate_signal(values)?;
    let mut output = values[..values.len().min(output_len)].to_vec();
    output.resize(output_len, 0.0);
    Ok(output)
}

/// Build a NumPy-compatible one-sided real spectrum.
///
/// The returned real and imaginary bins follow `rfft`: DC through Nyquist
/// (for even lengths). Keeping the complex data split makes the FFI contract
/// explicit and lets Agent-Spice frequency responses remain ABI-independent.
pub fn forward_real_spectrum(values: &[f64]) -> Result<(Vec<f64>, Vec<f64>), SignalError> {
    validate_signal(values)?;
    let mut spectrum = values
        .iter()
        .map(|&value| Complex::new(value, 0.0))
        .collect::<Vec<_>>();
    FftPlanner::<f64>::new()
        .plan_fft_forward(values.len())
        .process(&mut spectrum);
    let bins = values.len() / 2 + 1;
    let real = spectrum[..bins].iter().map(|value| value.re).collect();
    let imag = spectrum[..bins].iter().map(|value| value.im).collect();
    Ok((real, imag))
}

/// Invert a NumPy-compatible one-sided real spectrum.
///
/// Input bins follow `rfft`: DC through Nyquist (for even lengths), with the
/// omitted negative-frequency bins restored by Hermitian symmetry. The output
/// has NumPy's normalized `irfft` scaling and is suitable for converting an
/// Agent-Spice impedance response into a current-to-voltage impulse response.
pub fn inverse_real_spectrum(
    real: &[f64],
    imag: &[f64],
    output_len: usize,
) -> Result<Vec<f64>, SignalError> {
    let expected_bins = output_len.checked_div(2).map_or(0, |half| half + 1);
    if output_len < 2
        || real.len() != expected_bins
        || imag.len() != expected_bins
        || real.iter().chain(imag).any(|value| !value.is_finite())
    {
        return Err(SignalError::InvalidSpectrum);
    }
    let mut spectrum = vec![Complex::new(0.0, 0.0); output_len];
    for (index, (&re, &im)) in real.iter().zip(imag).enumerate() {
        spectrum[index] = Complex::new(re, im);
    }
    for index in 1..expected_bins {
        let mirror = output_len - index;
        if mirror != index {
            spectrum[mirror] = spectrum[index].conj();
        }
    }
    FftPlanner::<f64>::new()
        .plan_fft_inverse(output_len)
        .process(&mut spectrum);
    Ok(spectrum
        .into_iter()
        .map(|value| value.re / output_len as f64)
        .collect())
}

fn validate_signal(values: &[f64]) -> Result<(), SignalError> {
    if values.is_empty() {
        return Err(SignalError::EmptyInput);
    }
    if values.iter().any(|value| !value.is_finite()) {
        return Err(SignalError::NonFiniteInput);
    }
    Ok(())
}
