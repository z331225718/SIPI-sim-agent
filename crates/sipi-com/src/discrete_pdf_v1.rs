//! Discrete PDF core for the R480 noise stage.
//!
//! Ported from agent-com `src/agent_com/noise/discrete_pdf.py` (MIT
//! source, P5-04d source map): normalized discrete PDF, normal_pdf
//! generation, CDF/quantile, and exact full convolution with the
//! single-bin shortcuts. The combined noise PDF composition
//! (combine_r480_noise_pdf) is a separate stage.

/// A normalized discrete probability density over uniform bins.
#[derive(Clone, Debug, PartialEq)]
pub struct DiscretePdfV1 {
    bin_size: f64,
    min_bin: i64,
    probability: Vec<f64>,
}

impl DiscretePdfV1 {
    pub fn try_new(
        bin_size: f64,
        min_bin: i64,
        probability: Vec<f64>,
    ) -> Result<Self, PdfErrorV1> {
        if !(bin_size > 0.0) || probability.is_empty()
            || probability.iter().any(|value| *value < 0.0 || !value.is_finite())
        {
            return Err(PdfErrorV1::InvalidPdf);
        }
        let total: f64 = probability.iter().sum();
        if !(total > 0.0) {
            return Err(PdfErrorV1::InvalidPdf);
        }
        let normalized = probability.iter().map(|value| value / total).collect();
        Ok(Self {
            bin_size,
            min_bin,
            probability: normalized,
        })
    }

    pub fn bin_size(&self) -> f64 {
        self.bin_size
    }

    /// Lowest support bin index.
    pub fn min_bin(&self) -> i64 {
        self.min_bin
    }

    pub fn probability(&self) -> &[f64] {
        &self.probability
    }

    /// Support point for bin index `i` (0-based): `(min_bin + i) * bin_size`.
    pub fn x(&self, index: usize) -> f64 {
        (self.min_bin as f64 + index as f64) * self.bin_size
    }

    /// Normalized cumulative distribution over the support.
    pub fn cdf(&self) -> Vec<f64> {
        let mut running = 0.0;
        self.probability
            .iter()
            .map(|value| {
                running += value;
                running
            })
            .collect()
    }

    /// First support point whose CDF reaches `probability`.
    pub fn first_quantile(&self, probability: f64) -> Result<f64, PdfErrorV1> {
        if !(0.0 <= probability && probability <= 1.0) {
            return Err(PdfErrorV1::InvalidQuantile);
        }
        let cdf = self.cdf();
        let index = cdf
            .iter()
            .position(|value| *value >= probability)
            .unwrap_or(self.probability.len() - 1);
        Ok(self.x(index))
    }
}

/// Matlab-style scalar half-away-from-zero rounding.
pub(crate) fn matlab_round(value: f64) -> i64 {
    if value >= 0.0 {
        (value + 0.5).floor() as i64
    } else {
        (value - 0.5).ceil() as i64
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum PdfErrorV1 {
    InvalidGaussianControls,
    InvalidSampledControls,
    InvalidResidualControls,
    InvalidNoisePdfControls,
    InvalidDfeCancellationCount,
    DfeSpanExceedsPulse,
    InvalidDfeBounds,
    DfeWindowExceedsPulse,
    PulseTooShort,
    PhaseOutsideCandidates,
    InvalidPdf,
    InvalidQuantile,
    ConvolveBinMismatch,
}

/// Port `normal_pdf` including the r4.80 +/- 2Q support rule.
pub fn normal_pdf_v1(
    sigma_v: f64,
    nsigma: f64,
    bin_size: f64,
) -> Result<DiscretePdfV1, PdfErrorV1> {
    if sigma_v < 0.0 || nsigma < 0.0 || !(bin_size > 0.0) {
        return Err(PdfErrorV1::InvalidGaussianControls);
    }
    let minimum = matlab_round(-2.0 * nsigma * sigma_v / bin_size);
    let count = (-minimum - minimum + 1) as usize;
    let denominator = 2.0 * sigma_v * sigma_v + f64::EPSILON;
    let probability = (0..count)
        .map(|index| {
            let bin = minimum + index as i64;
            let x = bin as f64 * bin_size;
            (-(x * x) / denominator).exp()
        })
        .collect();
    DiscretePdfV1::try_new(bin_size, minimum, probability)
}

/// Exact full convolution with the single-bin shortcuts (port of
/// `DiscretePdf.convolve`).
pub fn convolve_v1(
    left: &DiscretePdfV1,
    right: &DiscretePdfV1,
) -> Result<DiscretePdfV1, PdfErrorV1> {
    if left.bin_size != right.bin_size {
        return Err(PdfErrorV1::ConvolveBinMismatch);
    }
    let left_single = left.probability.len() == 1 && left.probability[0] == 1.0 && left.min_bin == 0;
    let right_single = right.probability.len() == 1 && right.probability[0] == 1.0 && right.min_bin == 0;
    if left_single || right_single {
        let (other, single_min) = if left_single {
            (right, left.min_bin)
        } else {
            (left, right.min_bin)
        };
        return DiscretePdfV1::try_new(
            other.bin_size,
            matlab_round(other.min_bin as f64 + single_min as f64),
            other.probability.clone(),
        );
    }
    let size = left.probability.len() + right.probability.len() - 1;
    let mut result = vec![0.0_f64; size];
    for (left_index, left_value) in left.probability.iter().enumerate() {
        for (right_index, right_value) in right.probability.iter().enumerate() {
            result[left_index + right_index] += left_value * right_value;
        }
    }
    DiscretePdfV1::try_new(
        left.bin_size,
        matlab_round(left.min_bin as f64 + right.min_bin as f64),
        result,
    )
}

/// Explicit scope policy of the discrete PDF stage core.
pub const DISCRETE_PDF_POLICY_V1: &str =
    "sipi.p5-04d.discrete-pdf-v1.normal-convolve-quantile";

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn normal_pdf_is_symmetric_and_normalized() {
        let pdf = normal_pdf_v1(0.01, 3.0, 1e-4).expect("pdf");
        let probabilities = pdf.probability();
        let half = probabilities.len() / 2;
        for index in 0..half {
            let left = probabilities[index];
            let right = probabilities[probabilities.len() - 1 - index];
            assert!((left - right).abs() < 1e-12);
        }
        let total: f64 = probabilities.iter().sum();
        assert!((total - 1.0).abs() < 1e-12);
    }

    #[test]
    fn quantile_returns_support_point() {
        let pdf = DiscretePdfV1::try_new(1.0, 0, vec![0.1, 0.2, 0.4, 0.3]).expect("pdf");
        let quantile = pdf.first_quantile(0.75).expect("quantile");
        assert!((quantile - 3.0).abs() < 1e-12);
    }

    #[test]
    fn delta_convolves_as_identity() {
        let delta = DiscretePdfV1::try_new(1e-4, 0, vec![1.0]).expect("delta");
        let gaussian = normal_pdf_v1(0.01, 3.0, 1e-4).expect("gaussian");
        let result = convolve_v1(&gaussian, &delta).expect("convolution");
        // Normalization re-entry may leave ~1e-16 relative differences.
        for (left, right) in result.probability().iter().zip(gaussian.probability().iter()) {
            assert!((left - right).abs() < 1e-14, "delta identity drift");
        }
    }

    #[test]
    fn two_pulses_convolve_to_two_mass_points() {
        let a = DiscretePdfV1::try_new(1.0, 0, vec![1.0]).expect("a");
        let b = DiscretePdfV1::try_new(1.0, 5, vec![1.0]).expect("b");
        let result = convolve_v1(&a, &b).expect("convolution");
        assert_eq!(result.probability().len(), 1);
        assert!((result.x(0) - 5.0).abs() < 1e-12);
    }

    #[test]
    fn policy_string_is_fixed() {
        assert_eq!(
            DISCRETE_PDF_POLICY_V1,
            "sipi.p5-04d.discrete-pdf-v1.normal-convolve-quantile",
        );
    }
}
