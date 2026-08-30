//! Discrete PDF core for the R480 noise stage.
//!
//! Ported from agent-com `src/agent_com/noise/discrete_pdf.py` (MIT
//! source, P5-04d source map): normalized discrete PDF, normal_pdf
//! generation, CDF/quantile, and exact full convolution with the
//! single-bin shortcuts. The combined noise PDF composition
//! (combine_r480_noise_pdf) is a separate stage.

use std::cell::RefCell;

use rustfft::FftPlanner;
use rustfft::num_complex::Complex;

thread_local! {
    // The exhaustive C2M search repeatedly uses only a handful of support
    // lengths.  Retaining RustFFT's per-thread plan cache avoids rebuilding
    // twiddle tables for every viable TX-FFE candidate without introducing
    // cross-run mutable state.
    static C2M_FFT_PLANNER: RefCell<FftPlanner<f64>> = RefCell::new(FftPlanner::new());
}

/// A normalized discrete probability density over uniform bins.
#[derive(Clone, Debug, PartialEq)]
pub struct DiscretePdfV1 {
    bin_size: f64,
    min_bin: i64,
    probability: Vec<f64>,
}

impl DiscretePdfV1 {
    pub fn try_new(bin_size: f64, min_bin: i64, probability: Vec<f64>) -> Result<Self, PdfErrorV1> {
        if !(bin_size > 0.0)
            || probability.is_empty()
            || probability
                .iter()
                .any(|value| *value < 0.0 || !value.is_finite())
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
        if !(0.0..=1.0).contains(&probability) {
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
    let left_single =
        left.probability.len() == 1 && left.probability[0] == 1.0 && left.min_bin == 0;
    let right_single =
        right.probability.len() == 1 && right.probability[0] == 1.0 && right.min_bin == 0;
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

/// Bounded C2M-search convolution backend.
///
/// R4.80 switches its exhaustive candidate evaluation to a sparse/FFT full
/// convolution path.  Keep the public report-PDF primitive above on its
/// direct, source-order implementation; this helper is deliberately only for
/// the private C2M candidate loop, where dense O(n*m) work dominates runtime.
pub(crate) fn convolve_c2m_accelerated_v1(
    left: &DiscretePdfV1,
    right: &DiscretePdfV1,
) -> Result<DiscretePdfV1, PdfErrorV1> {
    if left.bin_size != right.bin_size {
        return Err(PdfErrorV1::ConvolveBinMismatch);
    }
    let left_single =
        left.probability.len() == 1 && left.probability[0] == 1.0 && left.min_bin == 0;
    let right_single =
        right.probability.len() == 1 && right.probability[0] == 1.0 && right.min_bin == 0;
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
    let result = if let Some(indices) = sparse_indices_at_most_four(&right.probability) {
        if indices.len()
            <= sparse_indices_at_most_four(&left.probability).map_or(usize::MAX, |v| v.len())
        {
            sparse_full_convolution(&left.probability, &right.probability, indices.as_slice())
        } else if let Some(indices) = sparse_indices_at_most_four(&left.probability) {
            sparse_full_convolution(&right.probability, &left.probability, indices.as_slice())
        } else {
            fft_full_convolution(&left.probability, &right.probability)?
        }
    } else if let Some(indices) = sparse_indices_at_most_four(&left.probability) {
        sparse_full_convolution(&right.probability, &left.probability, indices.as_slice())
    } else {
        fft_full_convolution(&left.probability, &right.probability)?
    };
    DiscretePdfV1::try_new(
        left.bin_size,
        matlab_round(left.min_bin as f64 + right.min_bin as f64),
        result,
    )
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct SparseIndicesAtMostFour {
    indices: [usize; 4],
    len: usize,
}

impl SparseIndicesAtMostFour {
    fn len(self) -> usize {
        self.len
    }

    fn as_slice(&self) -> &[usize] {
        &self.indices[..self.len]
    }
}

fn sparse_indices_at_most_four(values: &[f64]) -> Option<SparseIndicesAtMostFour> {
    let mut sparse = SparseIndicesAtMostFour {
        indices: [0; 4],
        len: 0,
    };
    for (index, value) in values.iter().enumerate() {
        // Preserve the source backend's exact `value != 0.0` classification:
        // notably, -0.0 is a zero-mass bin.  Dense PDFs stop at the fifth
        // nonzero rather than allocating and scanning their whole support.
        if *value != 0.0 {
            if sparse.len == sparse.indices.len() {
                return None;
            }
            sparse.indices[sparse.len] = index;
            sparse.len += 1;
        }
    }
    Some(sparse)
}

fn sparse_full_convolution(dense: &[f64], sparse: &[f64], indices: &[usize]) -> Vec<f64> {
    let mut result = vec![0.0; dense.len() + sparse.len() - 1];
    for &index in indices {
        let mass = sparse[index];
        for (out, value) in result[index..index + dense.len()].iter_mut().zip(dense) {
            *out += mass * value;
        }
    }
    result
}

fn fft_full_convolution(left: &[f64], right: &[f64]) -> Result<Vec<f64>, PdfErrorV1> {
    let output_len = left
        .len()
        .checked_add(right.len())
        .and_then(|size| size.checked_sub(1))
        .ok_or(PdfErrorV1::InvalidPdf)?;
    let fft_len = output_len
        .checked_next_power_of_two()
        .ok_or(PdfErrorV1::InvalidPdf)?;
    let mut left_fft = vec![Complex::new(0.0, 0.0); fft_len];
    let mut right_fft = vec![Complex::new(0.0, 0.0); fft_len];
    for (target, value) in left_fft.iter_mut().zip(left) {
        target.re = *value;
    }
    for (target, value) in right_fft.iter_mut().zip(right) {
        target.re = *value;
    }
    let (forward, inverse) = C2M_FFT_PLANNER.with(|planner| {
        let mut planner = planner.borrow_mut();
        (
            planner.plan_fft_forward(fft_len),
            planner.plan_fft_inverse(fft_len),
        )
    });
    forward.process(&mut left_fft);
    forward.process(&mut right_fft);
    for (left_value, right_value) in left_fft.iter_mut().zip(right_fft) {
        *left_value *= right_value;
    }
    inverse.process(&mut left_fft);
    let scale = 1.0 / fft_len as f64;
    let mut negative_mass = 0.0;
    let mut result = Vec::with_capacity(output_len);
    for value in left_fft.into_iter().take(output_len) {
        let real = value.re * scale;
        if !real.is_finite() {
            return Err(PdfErrorV1::InvalidPdf);
        }
        if real < 0.0 {
            negative_mass -= real;
            result.push(0.0);
        } else {
            result.push(real);
        }
    }
    // Match the pinned sparse/FFT path: a material negative lobe is not a
    // valid PDF, while sub-ULP roundoff is clamped before normalization.
    if negative_mass > 1e-12 {
        return Err(PdfErrorV1::InvalidPdf);
    }
    Ok(result)
}

/// Explicit scope policy of the discrete PDF stage core.
pub const DISCRETE_PDF_POLICY_V1: &str = "sipi.p5-04d.discrete-pdf-v1.normal-convolve-quantile";

#[cfg(test)]
mod tests {
    use super::*;

    fn legacy_sparse_indices(values: &[f64]) -> Option<Vec<usize>> {
        let indices: Vec<usize> = values
            .iter()
            .enumerate()
            .filter_map(|(index, value)| (*value != 0.0).then_some(index))
            .collect();
        (indices.len() <= 4).then_some(indices)
    }

    fn legacy_accelerated_convolution(
        left: &DiscretePdfV1,
        right: &DiscretePdfV1,
    ) -> Result<DiscretePdfV1, PdfErrorV1> {
        let result = if let Some(indices) = legacy_sparse_indices(&right.probability) {
            if indices.len()
                <= legacy_sparse_indices(&left.probability).map_or(usize::MAX, |v| v.len())
            {
                sparse_full_convolution(&left.probability, &right.probability, &indices)
            } else if let Some(indices) = legacy_sparse_indices(&left.probability) {
                sparse_full_convolution(&right.probability, &left.probability, &indices)
            } else {
                fft_full_convolution(&left.probability, &right.probability)?
            }
        } else if let Some(indices) = legacy_sparse_indices(&left.probability) {
            sparse_full_convolution(&right.probability, &left.probability, &indices)
        } else {
            fft_full_convolution(&left.probability, &right.probability)?
        };
        DiscretePdfV1::try_new(
            left.bin_size,
            matlab_round(left.min_bin as f64 + right.min_bin as f64),
            result,
        )
    }

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
        for (left, right) in result
            .probability()
            .iter()
            .zip(gaussian.probability().iter())
        {
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
    fn c2m_accelerated_sparse_and_fft_backends_match_direct_pdf() {
        let dense =
            DiscretePdfV1::try_new(1.0, -2, vec![0.05, 0.2, 0.3, 0.25, 0.2]).expect("dense");
        let sparse =
            DiscretePdfV1::try_new(1.0, -1, vec![0.5, 0.0, 0.25, 0.0, 0.25]).expect("sparse");
        let direct = convolve_v1(&dense, &sparse).expect("direct sparse");
        let accelerated = convolve_c2m_accelerated_v1(&dense, &sparse).expect("accelerated sparse");
        assert_eq!(direct.min_bin(), accelerated.min_bin());
        for (expected, actual) in direct.probability().iter().zip(accelerated.probability()) {
            assert!((expected - actual).abs() < 1e-15);
        }

        let other = DiscretePdfV1::try_new(1.0, 1, vec![0.1, 0.15, 0.2, 0.25, 0.3]).expect("other");
        let direct = convolve_v1(&dense, &other).expect("direct fft");
        let accelerated = convolve_c2m_accelerated_v1(&dense, &other).expect("accelerated fft");
        assert_eq!(direct.min_bin(), accelerated.min_bin());
        for (expected, actual) in direct.probability().iter().zip(accelerated.probability()) {
            assert!((expected - actual).abs() < 1e-12);
        }
    }

    #[test]
    fn sparse_classifier_preserves_zero_limit_order_and_negative_zero() {
        for (values, expected) in [
            (vec![0.0], Some(Vec::new())),
            (vec![1.0], Some(vec![0])),
            (
                vec![1.0, 0.0, 2.0, 0.0, 3.0, 0.0, 4.0],
                Some(vec![0, 2, 4, 6]),
            ),
            (vec![0.0, 1.0, 0.0, 2.0, 0.0, 3.0, 0.0, 4.0, 5.0], None),
            (vec![-0.0, 0.0, 1.0, -0.0, 2.0], Some(vec![2, 4])),
        ] {
            let actual =
                sparse_indices_at_most_four(&values).map(|indices| indices.as_slice().to_vec());
            assert_eq!(actual, expected, "classification drift for {values:?}");
        }
    }

    #[test]
    fn c2m_sparse_classifier_fast_path_is_bitwise_legacy_equivalent() {
        let cases = [
            (
                DiscretePdfV1::try_new(1.0, -3, vec![0.1, 0.2, 0.3, 0.4]).expect("dense"),
                DiscretePdfV1::try_new(1.0, 1, vec![0.25, 0.0, 0.25, 0.0, 0.5]).expect("sparse"),
            ),
            (
                DiscretePdfV1::try_new(1.0, 0, vec![0.4, 0.0, 0.0, 0.6]).expect("left sparse"),
                DiscretePdfV1::try_new(1.0, 0, vec![0.1, 0.2, 0.3, 0.25, 0.15])
                    .expect("right dense"),
            ),
            (
                DiscretePdfV1::try_new(1.0, -1, vec![0.5, 0.0, 0.5]).expect("left equal sparse"),
                DiscretePdfV1::try_new(1.0, 2, vec![0.0, 0.5, 0.0, 0.5])
                    .expect("right equal sparse"),
            ),
        ];
        for (left, right) in cases {
            let legacy = legacy_accelerated_convolution(&left, &right).expect("legacy result");
            let actual = convolve_c2m_accelerated_v1(&left, &right).expect("fast result");
            assert_eq!(legacy.min_bin(), actual.min_bin());
            assert_eq!(
                legacy
                    .probability()
                    .iter()
                    .map(|value| value.to_bits())
                    .collect::<Vec<_>>(),
                actual
                    .probability()
                    .iter()
                    .map(|value| value.to_bits())
                    .collect::<Vec<_>>(),
            );
        }
    }

    #[test]
    fn policy_string_is_fixed() {
        assert_eq!(
            DISCRETE_PDF_POLICY_V1,
            "sipi.p5-04d.discrete-pdf-v1.normal-convolve-quantile",
        );
    }
}
