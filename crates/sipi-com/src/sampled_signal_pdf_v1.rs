//! Sampled-signal discrete PDF stage (port of `sampled_signal_pdf`).
//!
//! Ported from agent-com `src/agent_com/noise/discrete_pdf.py` (MIT
//! source, P5-04f source map). Builds the discrete voltage PDF from a
//! series of sampled signal values: MATLAB half-away-from-zero bin
//! quantization (`d_cpdf`/from_values), per-sample PAM symbol
//! convolution, and the sparse PAM4 acceleration used by the exhaustive
//! C2M equalizer-search scope.

use crate::discrete_pdf_v1::{convolve_v1, matlab_round, DiscretePdfV1, PdfErrorV1};

/// Explicit scope policy of the sampled-signal PDF stage.
pub const SAMPLED_SIGNAL_PDF_POLICY_V1: &str =
    "sipi.p5-04f.sampled-signal-pdf-v1.direct-and-sparse-pam";

/// Port of `_PAM4_SYMBOL_VALUES = 2 * np.arange(4) / 3 - 1`; the IEEE
/// f64 division/subtraction order reproduces NumPy's values exactly.
pub const PAM4_SYMBOL_VALUES: [f64; 4] = [-1.0, 2.0 / 3.0 - 1.0, 4.0 / 3.0 - 1.0, 1.0];

fn symbol_values(levels: u32) -> Vec<f64> {
    (0..levels as usize)
        .map(|index| (2.0 * index as f64) / (levels - 1) as f64 - 1.0)
        .collect()
}

/// Port of `DiscretePdf.from_values` (`d_cpdf`): MATLAB bin rounding,
/// coalesced masses, and first/last non-zero support trimming.
pub fn from_values_v1(
    bin_size: f64,
    values: &[f64],
    probabilities: &[f64],
) -> Result<DiscretePdfV1, PdfErrorV1> {
    if values.is_empty()
        || values.len() != probabilities.len()
        || probabilities.iter().any(|value| *value < 0.0)
    {
        return Err(PdfErrorV1::InvalidPdf);
    }
    if values.iter().all(|value| *value == 0.0) {
        return DiscretePdfV1::try_new(bin_size, 0, vec![1.0]);
    }
    let mut indexed: Vec<(f64, usize)> = values
        .iter()
        .copied()
        .enumerate()
        .map(|(index, value)| (value, index))
        .collect();
    indexed.sort_by(|a, b| a.0.total_cmp(&b.0));
    let bins: Vec<i64> = indexed
        .iter()
        .map(|(value, _)| matlab_round(value / bin_size))
        .collect();
    let minimum = bins[0];
    let maximum = bins[bins.len() - 1];
    let mut mass = vec![0.0_f64; (maximum - minimum + 1) as usize];
    for (offset, (_, probability_index)) in indexed.iter().enumerate() {
        mass[(bins[offset] - minimum) as usize] += probabilities[*probability_index];
    }
    let first = mass.iter().position(|value| *value != 0.0).expect("non-zero mass");
    let last = mass.iter().rposition(|value| *value != 0.0).expect("non-zero mass");
    DiscretePdfV1::try_new(bin_size, minimum + first as i64, mass[first..=last].to_vec())
}

fn is_unit_delta(pdf: &DiscretePdfV1) -> bool {
    pdf.probability().len() == 1 && pdf.probability()[0] == 1.0 && pdf.min_bin() == 0
}

/// Port of `_sparse_pam_component`: the sorted, coalesced bins of one
/// PAM component (PAM4 scalar path plus the generic unique/count path).
pub fn sparse_pam_component_v1(value: f64, levels: u32, bin_size: f64) -> (Vec<i64>, Vec<f64>) {
    let mass = 1.0 / levels as f64;
    if levels != 4 {
        let mut bins: Vec<i64> = symbol_values(levels)
            .iter()
            .map(|symbol| matlab_round(value * symbol / bin_size))
            .collect();
        bins.sort_unstable();
        let mut unique: Vec<i64> = Vec::new();
        let mut counts: Vec<u32> = Vec::new();
        for bin in bins {
            if let Some(last) = unique.last_mut() {
                if *last == bin {
                    *counts.last_mut().expect("count") += 1;
                    continue;
                }
            }
            unique.push(bin);
            counts.push(1);
        }
        let probabilities: Vec<f64> = counts
            .iter()
            .map(|count| *count as f64 * mass)
            .collect();
        (unique, probabilities)
    } else {
        let bins: Vec<i64> = PAM4_SYMBOL_VALUES
            .iter()
            .map(|symbol| matlab_round(value * symbol / bin_size))
            .collect();
        let mut unique: Vec<i64> = Vec::new();
        let mut probabilities: Vec<f64> = Vec::new();
        for bin in bins {
            if let Some(last) = unique.last() {
                if *last == bin {
                    *probabilities.last_mut().expect("probability") += mass;
                    continue;
                }
            }
            unique.push(bin);
            probabilities.push(mass);
        }
        (unique, probabilities)
    }
}

/// Port of `_accelerated_sampled_signal_pdf`: sparse PAM PDF without
/// materializing empty component bins; normalizes after every addition.
pub fn accelerated_sampled_signal_pdf_v1(
    values: &[f64],
    levels: u32,
    bin_size: f64,
) -> Result<DiscretePdfV1, PdfErrorV1> {
    let mut probability = vec![1.0_f64];
    let mut minimum: i64 = 0;
    for value in values {
        let (component_bins, component_probability) =
            sparse_pam_component_v1(value.abs(), levels, bin_size);
        let next_minimum = minimum + component_bins[0];
        let next_maximum = minimum + probability.len() as i64 - 1
            + component_bins[component_bins.len() - 1];
        let mut next_probability =
            vec![0.0_f64; (next_maximum - next_minimum + 1) as usize];
        for (component_bin, mass) in component_bins.iter().zip(component_probability.iter()) {
            let start = (minimum + component_bin - next_minimum) as usize;
            for (offset, entry) in
                next_probability[start..start + probability.len()].iter_mut().enumerate()
            {
                *entry += mass * probability[offset];
            }
        }
        let total: f64 = next_probability.iter().sum();
        for entry in next_probability.iter_mut() {
            *entry /= total;
        }
        probability = next_probability;
        minimum = next_minimum;
    }
    DiscretePdfV1::try_new(bin_size, minimum, probability)
}

/// Port of `sampled_signal_pdf` (non-Gaussian discrete path).
///
/// The product API does not expose the r4.80 `fast_noise_convolution`
/// option; that MATLAB/FFT backend path is not ported (charter admission).
pub fn sampled_signal_pdf_v1(
    samples: &[f64],
    levels: u32,
    bin_size: f64,
    sparse_pam: bool,
) -> Result<DiscretePdfV1, PdfErrorV1> {
    if levels < 2 || !(bin_size > 0.0) {
        return Err(PdfErrorV1::InvalidSampledControls);
    }
    let mut values = samples.to_vec();
    if values.is_empty() {
        return Err(PdfErrorV1::InvalidSampledControls);
    }
    let max = values.iter().copied().fold(f64::NEG_INFINITY, f64::max);
    if max > bin_size {
        values.retain(|value| value.abs() > bin_size);
    }
    for value in values.iter_mut() {
        if value.abs() < bin_size {
            *value = 0.0;
        }
    }
    values.sort_by(|a, b| b.abs().total_cmp(&a.abs()));
    if sparse_pam {
        return accelerated_sampled_signal_pdf_v1(&values, levels, bin_size);
    }
    let symbols = symbol_values(levels);
    let symbol_probability = vec![1.0 / levels as f64; levels as usize];
    let mut result = DiscretePdfV1::try_new(bin_size, 0, vec![1.0])?;
    for value in values {
        let component_values: Vec<f64> =
            symbols.iter().map(|symbol| value.abs() * symbol).collect();
        let component = from_values_v1(bin_size, &component_values, &symbol_probability)?;
        if is_unit_delta(&component) {
            // Source convolve short-circuits the unit impulse operand.
            continue;
        }
        result = convolve_v1(&result, &component)?;
    }
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn pam4_samples() -> Vec<f64> {
        vec![
            0.42, -0.15, 0.03, -0.42, 0.15, -0.03, 0.42, 0.42, -0.42, 0.15,
        ]
    }

    #[test]
    fn direct_and_sparse_pam4_agree() {
        let samples = pam4_samples();
        let direct = sampled_signal_pdf_v1(&samples, 4, 0.01, false).expect("direct");
        let sparse = sampled_signal_pdf_v1(&samples, 4, 0.01, true).expect("sparse");
        assert_eq!(direct.min_bin(), sparse.min_bin());
        assert_eq!(direct.probability().len(), sparse.probability().len());
        for (a, b) in direct.probability().iter().zip(sparse.probability().iter()) {
            assert!((a - b).abs() < 1e-12, "direct/sparse drift: {a} vs {b}");
        }
    }

    #[test]
    fn levels_two_and_three_are_supported() {
        for levels in [2u32, 3u32] {
            let samples = pam4_samples();
            let direct = sampled_signal_pdf_v1(&samples, levels, 0.01, false).expect("direct");
            let sparse = sampled_signal_pdf_v1(&samples, levels, 0.01, true).expect("sparse");
            assert_eq!(direct.min_bin(), sparse.min_bin());
            assert_eq!(direct.probability().len(), sparse.probability().len());
            for (a, b) in direct.probability().iter().zip(sparse.probability().iter()) {
                assert!((a - b).abs() < 1e-12);
            }
        }
    }

    #[test]
    fn all_zero_samples_yield_delta() {
        let pdf = sampled_signal_pdf_v1(&[0.0, 0.0, 0.0], 4, 0.01, false).expect("pdf");
        assert_eq!(pdf.probability().len(), 1);
        assert!((pdf.probability()[0] - 1.0).abs() < 1e-15);
        assert_eq!(pdf.min_bin(), 0);
    }

    #[test]
    fn out_of_range_samples_are_filtered_then_zeroed() {
        // max(|values|) <= bin_size -> no filter; |v| < bin_size zeroed.
        let small = sampled_signal_pdf_v1(&[0.005, -0.003, 0.0], 4, 0.01, false).expect("pdf");
        assert_eq!(small.probability().len(), 1);
        // A large sample triggers the |v| > bin_size retain path.
        let filtered = sampled_signal_pdf_v1(&[0.05, 0.004], 4, 0.01, false).expect("pdf");
        assert!(filtered.probability().len() > 1);
    }

    #[test]
    fn controls_and_empty_are_rejected() {
        assert_eq!(
            sampled_signal_pdf_v1(&[0.1], 1, 0.01, false).unwrap_err(),
            PdfErrorV1::InvalidSampledControls,
        );
        assert_eq!(
            sampled_signal_pdf_v1(&[0.1], 4, 0.0, false).unwrap_err(),
            PdfErrorV1::InvalidSampledControls,
        );
        assert_eq!(
            sampled_signal_pdf_v1(&[], 4, 0.01, false).unwrap_err(),
            PdfErrorV1::InvalidSampledControls,
        );
    }

    #[test]
    fn from_values_coalesces_and_trims() {
        let pdf = from_values_v1(1.0, &[-0.6, 0.6, 0.61, 2.4], &[0.25, 0.25, 0.25, 0.25])
            .expect("pdf");
        assert_eq!(pdf.min_bin(), -1);
        assert_eq!(pdf.probability().len(), 4);
        assert!((pdf.probability()[0] - 0.25).abs() < 1e-12);
        assert!((pdf.probability()[2] - 0.5).abs() < 1e-12);
        let delta = from_values_v1(1.0, &[0.0, 0.0], &[0.5, 0.5]).expect("delta");
        assert_eq!(delta.probability().len(), 1);
    }

    #[test]
    fn policy_string_is_fixed() {
        assert_eq!(
            SAMPLED_SIGNAL_PDF_POLICY_V1,
            "sipi.p5-04f.sampled-signal-pdf-v1.direct-and-sparse-pam",
        );
    }
}
