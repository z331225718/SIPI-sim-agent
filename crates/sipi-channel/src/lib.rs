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
    value.im.abs() <= 1e-12 + 1e-10 * value.re.abs()
}

pub fn resolve_matched_kernel_v1(
    input: &MatchedTwoPortSpectrumV1,
    limits: ChannelLimitsV1,
) -> Result<MatchedChannelKernelV1, ChannelError> {
    let m = input.samples.len();
    if m > limits.max_one_sided_samples.get() {
        return Err(ChannelError::SampleLimitExceeded);
    }
    let n = m
        .checked_sub(1)
        .and_then(|x| x.checked_mul(2))
        .ok_or(ChannelError::LengthOverflow)?;
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
    let max_re = spectrum
        .iter()
        .map(|v| (v.re * scale).abs())
        .fold(0.0_f64, f64::max);
    let gain = spectrum
        .into_iter()
        .map(|v| {
            let real = v.re * scale;
            if !real.is_finite() {
                return Err(ChannelError::NonFiniteOutput);
            }
            if (v.im * scale).abs() > 1e-10 + 1e-8 * max_re {
                return Err(ChannelError::InverseImaginaryResidue);
            }
            FiniteF64::try_new(real, "matched channel gain")
                .map_err(|_| ChannelError::NonFiniteOutput)
        })
        .collect::<Result<Vec<_>, _>>()?;
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
}
