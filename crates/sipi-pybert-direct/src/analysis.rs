//! Deterministic BER and error-index calculation for native receiver stages.

use thiserror::Error;

#[derive(Debug, Error, PartialEq, Eq)]
pub enum BerError {
    #[error("reference bits, observed bits, and eye-bit count must be non-empty")]
    InvalidInput,
    #[error("reference window must contain at least one asserted bit for delay correlation")]
    ZeroReferenceEnergy,
}

#[derive(Debug, Clone, PartialEq)]
pub struct BerResult {
    pub bit_delay: usize,
    pub compared_bits: usize,
    pub error_indices: Vec<usize>,
    pub auto_correlation: Vec<f64>,
}

/// Match PyBERT's post-DFE BER alignment: zero-pad the front of a short
/// observed stream, select the first maximum non-negative correlation lag,
/// then return indices relative to the compared eye window.
pub fn calculate_ber(
    reference_bits: &[i32],
    observed_bits: &[i32],
    eye_bits: usize,
) -> Result<BerResult, BerError> {
    if reference_bits.is_empty() || observed_bits.is_empty() || eye_bits == 0 {
        return Err(BerError::InvalidInput);
    }
    let mut compared = eye_bits.min(reference_bits.len()).min(observed_bits.len());
    if compared == 0 {
        return Err(BerError::InvalidInput);
    }
    let mut padded_observed = vec![0; reference_bits.len()];
    let copied = observed_bits.len().min(reference_bits.len());
    padded_observed[reference_bits.len() - copied..]
        .copy_from_slice(&observed_bits[observed_bits.len() - copied..]);
    let mut tested = padded_observed[padded_observed.len() - compared..].to_vec();
    let mut reference = reference_bits[reference_bits.len() - compared..].to_vec();
    let mut auto_correlation = nonnegative_correlation(&tested, &reference);
    let reference_sum = reference.iter().sum::<i32>();
    if reference_sum == 0 {
        return Err(BerError::ZeroReferenceEnergy);
    }
    for value in &mut auto_correlation {
        *value /= reference_sum as f64;
    }
    // NumPy's `where(correlation == correlation.max())[0][0]` selects the
    // first maximum. Keep the earlier index on ties rather than relying on
    // Rust iterator tie behavior.
    let bit_delay = auto_correlation
        .iter()
        .enumerate()
        .fold((0, f64::NEG_INFINITY), |best, (index, &value)| {
            if value > best.1 { (index, value) } else { best }
        })
        .0;
    compared = compared.min(reference_bits.len() - bit_delay);
    tested = padded_observed[padded_observed.len() - compared..].to_vec();
    reference = reference_bits
        [reference_bits.len() - bit_delay - compared..reference_bits.len() - bit_delay]
        .to_vec();
    let error_indices = tested
        .iter()
        .zip(&reference)
        .enumerate()
        .filter_map(|(index, (actual, expected))| (actual != expected).then_some(index))
        .collect();
    Ok(BerResult {
        bit_delay,
        compared_bits: compared,
        error_indices,
        auto_correlation,
    })
}

fn nonnegative_correlation(observed: &[i32], reference: &[i32]) -> Vec<f64> {
    // NumPy's `correlate(..., mode="same")` takes the centered slice of the
    // full correlation; the subsequent PyBERT slice starts at lag zero.
    (0..observed.len().div_ceil(2))
        .map(|delay| {
            (0..observed.len() - delay)
                .map(|index| (observed[index + delay] * reference[index]) as f64)
                .sum()
        })
        .collect()
}
