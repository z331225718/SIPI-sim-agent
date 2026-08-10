#![forbid(unsafe_code)]

//! Matched two-port S21 to discrete V/V kernel conversion.
//! No Touchstone parsing, file I/O, reflection solving, or Link stages live here.

use std::{error::Error, fmt, num::NonZeroUsize};

use rustfft::{FftPlanner, num_complex::Complex};
use sipi_types::{Complex64, FiniteF64, Hertz, Ohms, Seconds};

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct TwoPortS {
    pub s11: Complex64,
    pub s12: Complex64,
    pub s21: Complex64,
    pub s22: Complex64,
}

#[derive(Clone, Debug, PartialEq)]
pub struct MatchedTwoPortSpectrumV1 {
    reference_impedance: Ohms,
    frequency_step: Hertz,
    samples: Vec<TwoPortS>,
}

impl MatchedTwoPortSpectrumV1 {
    pub fn try_new(
        reference_impedance: Ohms,
        frequency_step: Hertz,
        samples: Vec<TwoPortS>,
    ) -> Result<Self, ChannelError> {
        if reference_impedance.get() <= 0.0 {
            return Err(ChannelError::NonPositiveImpedance);
        }
        if frequency_step.get() <= 0.0 {
            return Err(ChannelError::NonPositiveFrequencyStep);
        }
        if samples.len() < 2 {
            return Err(ChannelError::TooFewSamples);
        }
        Ok(Self {
            reference_impedance,
            frequency_step,
            samples,
        })
    }
    pub fn sample_count(&self) -> usize {
        self.samples.len()
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct ChannelLimitsV1 {
    max_one_sided_samples: NonZeroUsize,
}
impl ChannelLimitsV1 {
    pub const fn new(max_one_sided_samples: NonZeroUsize) -> Self {
        Self {
            max_one_sided_samples,
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct MatchedChannelKernelV1 {
    sample_interval: Seconds,
    gain: Vec<FiniteF64>,
}

/// Result of a finite-grid diagnostic. It deliberately does not certify a
/// continuous-frequency network property.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum SampledDiagnosticStatusV1 {
    PassesSampledBound,
    ViolatesSampledBound,
    Indeterminate,
}

/// A bounded passivity observation over the supplied S-parameter samples.
#[derive(Clone, Debug, PartialEq)]
pub struct SampledPassivityV1 {
    status: SampledDiagnosticStatusV1,
    worst_index: usize,
    maximum_singular_value: Option<FiniteF64>,
}
impl SampledPassivityV1 {
    pub fn status(&self) -> SampledDiagnosticStatusV1 {
        self.status
    }
    pub fn worst_index(&self) -> usize {
        self.worst_index
    }
    pub fn maximum_singular_value(&self) -> Option<FiniteF64> {
        self.maximum_singular_value
    }
}

/// A bounded reciprocity observation over the supplied S-parameter samples.
#[derive(Clone, Debug, PartialEq)]
pub struct SampledReciprocityV1 {
    status: SampledDiagnosticStatusV1,
    worst_index: usize,
    maximum_difference: Option<FiniteF64>,
}
impl SampledReciprocityV1 {
    pub fn status(&self) -> SampledDiagnosticStatusV1 {
        self.status
    }
    pub fn worst_index(&self) -> usize {
        self.worst_index
    }
    pub fn maximum_difference(&self) -> Option<FiniteF64> {
        self.maximum_difference
    }
}

/// A bounded losslessness observation over the supplied S-parameter samples.
#[derive(Clone, Debug, PartialEq)]
pub struct SampledLosslessnessV1 {
    status: SampledDiagnosticStatusV1,
    worst_index: usize,
    maximum_residual: Option<FiniteF64>,
}
impl SampledLosslessnessV1 {
    pub fn status(&self) -> SampledDiagnosticStatusV1 {
        self.status
    }
    pub fn worst_index(&self) -> usize {
        self.worst_index
    }
    pub fn maximum_residual(&self) -> Option<FiniteF64> {
        self.maximum_residual
    }
}

/// Causality cannot be established from this finite, periodic DFT input.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum CausalityAssessmentV1 {
    NotAssessedFiniteBandPeriodicDft,
}

/// Informational diagnostics for a supplied finite frequency grid.
///
/// These observations neither modify the spectrum nor change resolver
/// admission. A sampled passivity result is not a continuous-band passivity
/// certificate; causality is intentionally not assessed.
#[derive(Clone, Debug, PartialEq)]
pub struct NetworkDiagnosticsV1 {
    sampled_passivity: SampledPassivityV1,
    sampled_reciprocity: SampledReciprocityV1,
    sampled_losslessness: SampledLosslessnessV1,
    causality: CausalityAssessmentV1,
}
impl NetworkDiagnosticsV1 {
    pub fn sampled_passivity(&self) -> &SampledPassivityV1 {
        &self.sampled_passivity
    }
    pub fn sampled_reciprocity(&self) -> &SampledReciprocityV1 {
        &self.sampled_reciprocity
    }
    pub fn sampled_losslessness(&self) -> &SampledLosslessnessV1 {
        &self.sampled_losslessness
    }
    pub fn causality(&self) -> CausalityAssessmentV1 {
        self.causality
    }
}
impl MatchedChannelKernelV1 {
    pub fn sample_interval(&self) -> Seconds {
        self.sample_interval
    }
    pub fn gain(&self) -> &[FiniteF64] {
        &self.gain
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ChannelError {
    TooFewSamples,
    SampleLimitExceeded,
    LengthOverflow,
    NonPositiveImpedance,
    NonPositiveFrequencyStep,
    EndpointImaginaryResidue,
    InverseImaginaryResidue,
    NonFiniteOutput,
}
impl fmt::Display for ChannelError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "channel input or transform is invalid: {self:?}")
    }
}
impl Error for ChannelError {}

fn complex(value: Complex64) -> Complex<f64> {
    Complex::new(value.real(), value.imaginary())
}
fn endpoint_is_real(value: Complex<f64>) -> bool {
    value.im.abs() <= 1e-12
}
fn fft_length(sample_count: usize) -> Result<usize, ChannelError> {
    sample_count
        .checked_sub(1)
        .and_then(|x| x.checked_mul(2))
        .ok_or(ChannelError::LengthOverflow)
}
fn finalize_gain(spectrum: Vec<Complex<f64>>, scale: f64) -> Result<Vec<FiniteF64>, ChannelError> {
    let max_re = spectrum
        .iter()
        .map(|v| (v.re * scale).abs())
        .fold(0.0_f64, f64::max);
    spectrum
        .into_iter()
        .map(|v| {
            let real = v.re * scale;
            if !real.is_finite() {
                return Err(ChannelError::NonFiniteOutput);
            }
            if (v.im * scale).abs() > 1e-12 + 1e-10 * max_re {
                return Err(ChannelError::InverseImaginaryResidue);
            }
            FiniteF64::try_new(real, "matched channel gain")
                .map_err(|_| ChannelError::NonFiniteOutput)
        })
        .collect()
}

const PASSIVITY_TOLERANCE: f64 = 1e-10;
const IDENTITY_ABSOLUTE_TOLERANCE: f64 = 1e-12;
const IDENTITY_RELATIVE_TOLERANCE: f64 = 1e-10;

fn magnitude(value: Complex<f64>) -> f64 {
    value.re.hypot(value.im)
}

fn finite_complex(value: Complex<f64>) -> Option<Complex<f64>> {
    (value.re.is_finite() && value.im.is_finite()).then_some(value)
}

fn product(left: Complex<f64>, right: Complex<f64>) -> Option<Complex<f64>> {
    finite_complex(Complex::new(
        left.re * right.re - left.im * right.im,
        left.re * right.im + left.im * right.re,
    ))
}

fn sum(left: Complex<f64>, right: Complex<f64>) -> Option<Complex<f64>> {
    finite_complex(Complex::new(left.re + right.re, left.im + right.im))
}

fn max_singular_value(sample: TwoPortS) -> Option<f64> {
    let entries = [sample.s11, sample.s12, sample.s21, sample.s22].map(complex);
    let scale = entries
        .iter()
        .map(|entry| magnitude(*entry))
        .fold(0.0, f64::max);
    if scale == 0.0 {
        return Some(0.0);
    }
    if !scale.is_finite() {
        return None;
    }
    let [a, b, c, d] = entries.map(|entry| entry / scale);
    let trace = [a, b, c, d]
        .iter()
        .map(|entry| entry.norm_sqr())
        .sum::<f64>();
    let determinant = a * d - b * c;
    let determinant_norm_squared = determinant.norm_sqr();
    let discriminant = (trace * trace - 4.0 * determinant_norm_squared).max(0.0);
    let normalized = ((trace + discriminant.sqrt()) / 2.0).sqrt();
    let value = scale * normalized;
    value.is_finite().then_some(value)
}

fn reciprocity_difference(sample: TwoPortS) -> Option<f64> {
    let difference = complex(sample.s12) - complex(sample.s21);
    let result = magnitude(difference);
    result.is_finite().then_some(result)
}

fn lossless_residual(sample: TwoPortS) -> Option<f64> {
    let s11 = complex(sample.s11);
    let s12 = complex(sample.s12);
    let s21 = complex(sample.s21);
    let s22 = complex(sample.s22);
    let h11 = sum(product(s11.conj(), s11)?, product(s21.conj(), s21)?)? - Complex::new(1.0, 0.0);
    let h12 = sum(product(s11.conj(), s12)?, product(s21.conj(), s22)?)?;
    let h21 = sum(product(s12.conj(), s11)?, product(s22.conj(), s21)?)?;
    let h22 = sum(product(s12.conj(), s12)?, product(s22.conj(), s22)?)? - Complex::new(1.0, 0.0);
    let result = [h11, h12, h21, h22]
        .iter()
        .map(|entry| magnitude(*entry))
        .fold(0.0, f64::max);
    result.is_finite().then_some(result)
}

fn classify(
    values: impl Iterator<Item = Option<(f64, f64)>>,
) -> (SampledDiagnosticStatusV1, usize, Option<FiniteF64>) {
    let mut worst = None;
    let mut indeterminate = false;
    for (index, value) in values.enumerate() {
        let Some((metric, limit)) = value else {
            indeterminate = true;
            continue;
        };
        if worst.is_none_or(|(_, current, _)| metric > current) {
            worst = Some((index, metric, limit));
        }
    }
    let Some((worst_index, maximum, limit)) = worst else {
        return (SampledDiagnosticStatusV1::Indeterminate, 0, None);
    };
    let status = if maximum > limit {
        SampledDiagnosticStatusV1::ViolatesSampledBound
    } else if indeterminate {
        SampledDiagnosticStatusV1::Indeterminate
    } else {
        SampledDiagnosticStatusV1::PassesSampledBound
    };
    (
        status,
        worst_index,
        FiniteF64::try_new(maximum, "channel diagnostic metric").ok(),
    )
}

/// Analyze only the supplied discrete samples without changing channel resolution.
pub fn analyze_matched_two_port_v1(input: &MatchedTwoPortSpectrumV1) -> NetworkDiagnosticsV1 {
    let (passivity_status, passivity_index, singular_value) =
        classify(input.samples.iter().copied().map(|sample| {
            max_singular_value(sample).map(|value| (value, 1.0 + PASSIVITY_TOLERANCE))
        }));
    let (reciprocity_status, reciprocity_index, difference) =
        classify(input.samples.iter().copied().map(|sample| {
            let scale = magnitude(complex(sample.s12)).max(magnitude(complex(sample.s21)));
            scale.is_finite().then(|| {
                reciprocity_difference(sample).map(|value| {
                    (
                        value,
                        IDENTITY_ABSOLUTE_TOLERANCE + IDENTITY_RELATIVE_TOLERANCE * scale,
                    )
                })
            })?
        }));
    let (losslessness_status, losslessness_index, residual) =
        classify(input.samples.iter().copied().map(|sample| {
            let scale = [sample.s11, sample.s12, sample.s21, sample.s22]
                .map(complex)
                .iter()
                .map(|entry| magnitude(*entry))
                .fold(1.0, f64::max);
            (scale * scale).is_finite().then(|| {
                lossless_residual(sample).map(|value| {
                    (
                        value,
                        IDENTITY_ABSOLUTE_TOLERANCE + IDENTITY_RELATIVE_TOLERANCE * scale * scale,
                    )
                })
            })?
        }));
    NetworkDiagnosticsV1 {
        sampled_passivity: SampledPassivityV1 {
            status: passivity_status,
            worst_index: passivity_index,
            maximum_singular_value: singular_value,
        },
        sampled_reciprocity: SampledReciprocityV1 {
            status: reciprocity_status,
            worst_index: reciprocity_index,
            maximum_difference: difference,
        },
        sampled_losslessness: SampledLosslessnessV1 {
            status: losslessness_status,
            worst_index: losslessness_index,
            maximum_residual: residual,
        },
        causality: CausalityAssessmentV1::NotAssessedFiniteBandPeriodicDft,
    }
}

pub fn resolve_matched_kernel_v1(
    input: &MatchedTwoPortSpectrumV1,
    limits: ChannelLimitsV1,
) -> Result<MatchedChannelKernelV1, ChannelError> {
    let m = input.samples.len();
    if m > limits.max_one_sided_samples.get() {
        return Err(ChannelError::SampleLimitExceeded);
    }
    let n = fft_length(m)?;
    let dc = complex(input.samples[0].s21);
    let nyquist = complex(input.samples[m - 1].s21);
    if !endpoint_is_real(dc) || !endpoint_is_real(nyquist) {
        return Err(ChannelError::EndpointImaginaryResidue);
    }
    let mut spectrum = vec![Complex::new(0.0, 0.0); n];
    for (k, sample) in input.samples.iter().enumerate() {
        spectrum[k] = complex(sample.s21);
    }
    for k in 1..m - 1 {
        spectrum[n - k] = spectrum[k].conj();
    }
    FftPlanner::<f64>::new()
        .plan_fft_inverse(n)
        .process(&mut spectrum);
    let scale = 1.0 / n as f64;
    let gain = finalize_gain(spectrum, scale)?;
    let dt = Seconds::try_new(1.0 / (n as f64 * input.frequency_step.get()))
        .map_err(|_| ChannelError::NonFiniteOutput)?;
    Ok(MatchedChannelKernelV1 {
        sample_interval: dt,
        gain,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    fn c(re: f64, im: f64) -> Complex64 {
        Complex64::try_new(re, im).unwrap()
    }
    fn input(values: Vec<Complex64>) -> MatchedTwoPortSpectrumV1 {
        MatchedTwoPortSpectrumV1::try_new(
            Ohms::try_new(50.0).unwrap(),
            Hertz::try_new(1.0).unwrap(),
            values
                .into_iter()
                .map(|s21| TwoPortS {
                    s11: c(0.0, 0.0),
                    s12: c(0.0, 0.0),
                    s21,
                    s22: c(0.0, 0.0),
                })
                .collect(),
        )
        .unwrap()
    }
    fn matrix(sample: TwoPortS) -> MatchedTwoPortSpectrumV1 {
        MatchedTwoPortSpectrumV1::try_new(
            Ohms::try_new(50.0).unwrap(),
            Hertz::try_new(1.0).unwrap(),
            vec![sample; 3],
        )
        .unwrap()
    }
    fn two_port(s11: Complex64, s12: Complex64, s21: Complex64, s22: Complex64) -> TwoPortS {
        TwoPortS { s11, s12, s21, s22 }
    }
    fn limits() -> ChannelLimitsV1 {
        ChannelLimitsV1::new(NonZeroUsize::new(16).unwrap())
    }
    #[test]
    fn identity_is_unit_at_zero() {
        let result = resolve_matched_kernel_v1(&input(vec![c(1.0, 0.0); 3]), limits()).unwrap();
        assert!((result.gain()[0].get() - 1.0).abs() < 1e-12);
        assert!(result.gain()[1..].iter().all(|v| v.get().abs() < 1e-12));
    }
    #[test]
    fn integer_delay_has_positive_index() {
        let n = 4.0;
        let values = (0..3)
            .map(|k| {
                let phase = -2.0 * std::f64::consts::PI * k as f64 / n;
                c(phase.cos(), phase.sin())
            })
            .collect();
        let result = resolve_matched_kernel_v1(&input(values), limits()).unwrap();
        assert!(result.gain()[1].get() > 1.0 - 1e-12);
        assert!(
            result
                .gain()
                .iter()
                .enumerate()
                .filter(|(i, _)| *i != 1)
                .all(|(_, v)| v.get().abs() < 1e-12)
        );
    }
    #[test]
    fn other_s_parameters_do_not_change_output() {
        let mut a = input(vec![c(1.0, 0.0); 3]);
        let baseline = resolve_matched_kernel_v1(&a, limits()).unwrap();
        a.samples[1].s11 = c(99.0, 2.0);
        a.samples[1].s12 = c(-3.0, 7.0);
        a.samples[1].s22 = c(8.0, -1.0);
        assert_eq!(
            baseline.gain(),
            resolve_matched_kernel_v1(&a, limits()).unwrap().gain()
        );
    }
    #[test]
    fn endpoints_and_limits_fail_closed() {
        assert_eq!(
            resolve_matched_kernel_v1(&input(vec![c(1.0, 1.0), c(1.0, 0.0)]), limits())
                .unwrap_err(),
            ChannelError::EndpointImaginaryResidue
        );
        assert_eq!(
            resolve_matched_kernel_v1(&input(vec![c(1.0e6, 2.0e-12), c(1.0, 0.0)]), limits())
                .unwrap_err(),
            ChannelError::EndpointImaginaryResidue
        );
    }
    #[test]
    fn scaling_is_linear_and_limit_rejects() {
        let base = resolve_matched_kernel_v1(&input(vec![c(0.5, 0.0); 3]), limits()).unwrap();
        let scaled = resolve_matched_kernel_v1(&input(vec![c(1.0, 0.0); 3]), limits()).unwrap();
        assert!((scaled.gain()[0].get() - 2.0 * base.gain()[0].get()).abs() < 1e-12);
        assert_eq!(
            resolve_matched_kernel_v1(
                &input(vec![c(1.0, 0.0); 3]),
                ChannelLimitsV1::new(NonZeroUsize::new(2).unwrap())
            )
            .unwrap_err(),
            ChannelError::SampleLimitExceeded
        );
    }
    #[test]
    fn internal_transform_failures_are_closed() {
        assert_eq!(
            fft_length(usize::MAX).unwrap_err(),
            ChannelError::LengthOverflow
        );
        assert_eq!(
            finalize_gain(vec![Complex::new(1.0, 1.0)], 1.0).unwrap_err(),
            ChannelError::InverseImaginaryResidue
        );
        assert_eq!(
            finalize_gain(vec![Complex::new(f64::INFINITY, 0.0)], 1.0).unwrap_err(),
            ChannelError::NonFiniteOutput
        );
    }
    #[test]
    fn sampled_network_identities_are_distinguished() {
        let zero = c(0.0, 0.0);
        let one = c(1.0, 0.0);
        let through = matrix(two_port(zero, one, one, zero));
        let diagnostics = analyze_matched_two_port_v1(&through);
        assert_eq!(
            diagnostics.sampled_passivity().status(),
            SampledDiagnosticStatusV1::PassesSampledBound
        );
        assert_eq!(
            diagnostics.sampled_reciprocity().status(),
            SampledDiagnosticStatusV1::PassesSampledBound
        );
        assert_eq!(
            diagnostics.sampled_losslessness().status(),
            SampledDiagnosticStatusV1::PassesSampledBound
        );
        assert_eq!(
            diagnostics.causality(),
            CausalityAssessmentV1::NotAssessedFiniteBandPeriodicDft
        );
        let attenuator = matrix(two_port(zero, c(0.5, 0.0), c(0.5, 0.0), zero));
        let diagnostics = analyze_matched_two_port_v1(&attenuator);
        assert_eq!(
            diagnostics.sampled_passivity().status(),
            SampledDiagnosticStatusV1::PassesSampledBound
        );
        assert_eq!(
            diagnostics.sampled_reciprocity().status(),
            SampledDiagnosticStatusV1::PassesSampledBound
        );
        assert_eq!(
            diagnostics.sampled_losslessness().status(),
            SampledDiagnosticStatusV1::ViolatesSampledBound
        );
    }
    #[test]
    fn sampled_active_and_nonreciprocal_networks_are_not_conflated() {
        let zero = c(0.0, 0.0);
        let one = c(1.0, 0.0);
        let active = matrix(two_port(zero, zero, c(1.1, 0.0), zero));
        assert_eq!(
            analyze_matched_two_port_v1(&active)
                .sampled_passivity()
                .status(),
            SampledDiagnosticStatusV1::ViolatesSampledBound
        );
        let nonreciprocal = matrix(two_port(zero, zero, one, zero));
        let diagnostics = analyze_matched_two_port_v1(&nonreciprocal);
        assert_eq!(
            diagnostics.sampled_passivity().status(),
            SampledDiagnosticStatusV1::PassesSampledBound
        );
        assert_eq!(
            diagnostics.sampled_reciprocity().status(),
            SampledDiagnosticStatusV1::ViolatesSampledBound
        );
    }
    #[test]
    fn diagnostics_do_not_change_resolution_or_claim_large_value_certainty() {
        let mut spectrum = input(vec![c(0.5, 0.0); 3]);
        let before = resolve_matched_kernel_v1(&spectrum, limits()).unwrap();
        assert_eq!(
            analyze_matched_two_port_v1(&spectrum).causality(),
            CausalityAssessmentV1::NotAssessedFiniteBandPeriodicDft
        );
        assert_eq!(
            before,
            resolve_matched_kernel_v1(&spectrum, limits()).unwrap()
        );
        spectrum.samples[0].s11 = c(f64::MAX, 0.0);
        spectrum.samples[0].s12 = c(f64::MAX, 0.0);
        assert_eq!(
            analyze_matched_two_port_v1(&spectrum)
                .sampled_passivity()
                .status(),
            SampledDiagnosticStatusV1::Indeterminate
        );
    }
    #[test]
    fn matched_kernel_obeys_parseval_on_product_owned_spectrum() {
        let spectrum = input(vec![c(0.5, 0.0), c(0.3, 0.2), c(0.25, 0.0)]);
        let kernel = resolve_matched_kernel_v1(&spectrum, limits()).unwrap();
        let kernel_energy = kernel
            .gain()
            .iter()
            .map(|gain| gain.get().powi(2))
            .sum::<f64>();
        let one_sided_energy =
            0.5_f64.powi(2) + 2.0 * (0.3_f64.powi(2) + 0.2_f64.powi(2)) + 0.25_f64.powi(2);
        assert!((kernel_energy - one_sided_energy / 4.0).abs() < 1e-12);
    }
}
