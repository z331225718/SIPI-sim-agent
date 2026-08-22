//! Jitter-PDF to bathtub-curve conversion used by the native analysis path.
//!
//! This is deliberately a small pure stage.  The legacy Python orchestration
//! remains responsible for extracting and decomposing jitter crossings.

use thiserror::Error;

#[derive(Debug, Error, PartialEq)]
pub enum BathtubError {
    #[error("bathtub centers and jitter PDF must have the same length of at least three")]
    InvalidLength,
    #[error("bathtub centers, jitter PDF, and parameters must be finite")]
    NonFiniteInput,
    #[error("bathtub bin spacing must be non-zero")]
    InvalidBinSpacing,
    #[error("random-jitter sigma must be finite and greater than zero when extrapolating")]
    InvalidRandomJitter,
}

/// Match PyBERT's legacy `make_bathtub` transform without depending on NumPy.
///
/// `centers` are seconds and `jitter_pdf` is a density in inverse seconds.
/// When `extrapolate` is enabled, the two PDF tails are filled from the same
/// dual-Dirac Gaussian model as the Python reference.
pub fn make_bathtub(
    centers: &[f64],
    jitter_pdf: &[f64],
    min_value: f64,
    random_jitter_sigma: f64,
    right_mean: f64,
    left_mean: f64,
    extrapolate: bool,
) -> Result<Vec<f64>, BathtubError> {
    if centers.len() < 3 || centers.len() != jitter_pdf.len() {
        return Err(BathtubError::InvalidLength);
    }
    if centers
        .iter()
        .chain(jitter_pdf)
        .chain([min_value, random_jitter_sigma, right_mean, left_mean].iter())
        .any(|value| !value.is_finite())
    {
        return Err(BathtubError::NonFiniteInput);
    }
    let bin_width = centers[2] - centers[1];
    if bin_width == 0.0 {
        return Err(BathtubError::InvalidBinSpacing);
    }
    if extrapolate && random_jitter_sigma <= 0.0 {
        return Err(BathtubError::InvalidRandomJitter);
    }

    let half_length = jitter_pdf.len() / 2;
    let probability_mass = if jitter_pdf[0] != 0.0 || jitter_pdf[jitter_pdf.len() - 1] != 0.0 {
        let half_ui = centers[centers.len() - 1];
        let mut mass = Vec::with_capacity(jitter_pdf.len());
        mass.push((jitter_pdf[0] + jitter_pdf[jitter_pdf.len() - 1]) * half_ui);
        mass.extend(
            jitter_pdf[1..jitter_pdf.len() - 1]
                .iter()
                .map(|value| value * bin_width),
        );
        mass.push(0.0);
        mass
    } else {
        let density = if extrapolate {
            let mut gaussian = Vec::with_capacity(jitter_pdf.len());
            gaussian.extend(
                centers[..half_length]
                    .iter()
                    .map(|&center| gaussian_pdf(center, left_mean, random_jitter_sigma)),
            );
            gaussian.extend(
                centers[half_length..]
                    .iter()
                    .map(|&center| gaussian_pdf(center, right_mean, random_jitter_sigma)),
            );
            let replaced = jitter_pdf
                .iter()
                .zip(gaussian)
                .map(|(&pdf, fit)| if pdf == 0.0 { fit } else { pdf })
                .collect::<Vec<_>>();
            moving_average_protect_edges(&replaced, 5)
        } else {
            jitter_pdf.to_vec()
        };
        density.into_iter().map(|value| value * bin_width).collect()
    };

    let mut cdf = Vec::with_capacity(probability_mass.len());
    let mut sum = 0.0;
    for mass in probability_mass {
        sum += mass;
        cdf.push(sum * 2.0);
    }
    let correction = (cdf[0] + cdf[cdf.len() - 1]) / 2.0 - 1.0;
    for value in &mut cdf {
        *value -= correction;
    }
    for value in &mut cdf[half_length..] {
        *value -= 2.0 * (*value - 1.0);
    }
    // NumPy's fftshift moves the extra sample of an odd-length vector to the
    // front. This is identical to half-length rotation for even vectors.
    let shift = cdf.len().div_ceil(2);
    cdf.rotate_left(shift);
    Ok(cdf.into_iter().map(|value| value.max(min_value)).collect())
}

fn gaussian_pdf(value: f64, mean: f64, sigma: f64) -> f64 {
    // Mirror the legacy Python scale-to-ps calculation before evaluating the
    // Gaussian; algebraic cancellation alone is not bitwise equivalent at
    // the very low-probability tails used by bathtub extrapolation.
    let scale = 1.0e12;
    let scaled_value = value * scale;
    let scaled_mean = mean * scale;
    let scaled_sigma = sigma * scale;
    (-0.5 * ((scaled_value - scaled_mean) / scaled_sigma).powi(2)).exp()
        / (scaled_sigma * (2.0 * std::f64::consts::PI).sqrt())
        / scale
}

fn moving_average_protect_edges(values: &[f64], width: usize) -> Vec<f64> {
    let half = width.div_ceil(2);
    let mut kernel = vec![0.0; half * 2 - 1];
    for left in 0..half {
        for right in 0..half {
            kernel[left + right] += 1.0;
        }
    }
    let kernel_sum = kernel.iter().sum::<f64>();
    for value in &mut kernel {
        *value /= kernel_sum;
    }

    let interior = &values[1..values.len() - 1];
    let mut full = vec![0.0; interior.len() + kernel.len() - 1];
    for (left_index, &left) in interior.iter().enumerate() {
        for (right_index, &right) in kernel.iter().enumerate() {
            full[left_index + right_index] += left * right;
        }
    }
    let start = (kernel.len() - 1) / 2;
    let mut output = Vec::with_capacity(values.len());
    output.push(values[0]);
    output.extend_from_slice(&full[start..start + interior.len()]);
    output.push(values[values.len() - 1]);
    output
}
