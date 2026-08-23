//! Mixed-mode S-parameter transform for the R480 network-ingest stage.
//!
//! Ported from agent-com `src/agent_com/network/mixed_mode.py` (MIT
//! source, P5-04a source map). The COM_T transform and sdd21 extraction
//! follow the MATLAB r4.80 convention used by the oracle. This module
//! performs the standard linear transform only; it does not read files,
//! apply port orders, or compute any COM metric.

use sipi_types::Complex64;

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum MixedModeErrorV1 {
    LengthMismatch,
    InvalidFrequency,
    InvalidDelay,
    EmptySpectrum,
}

fn c(real: f64, imaginary: f64) -> Complex64 {
    Complex64::try_new(real, imaginary).expect("finite transform constant")
}

/// The fixed mixed-mode transform matrix (COM_T).
pub fn com_t_v1() -> FourPortSMatrixV1 {
    [
        [c(1.0, 0.0), c(1.0, 0.0), c(0.0, 0.0), c(0.0, 0.0)],
        [c(1.0, 0.0), c(-1.0, 0.0), c(0.0, 0.0), c(0.0, 0.0)],
        [c(0.0, 0.0), c(0.0, 0.0), c(1.0, 0.0), c(1.0, 0.0)],
        [c(0.0, 0.0), c(0.0, 0.0), c(1.0, 0.0), c(-1.0, 0.0)],
    ]
}

/// One 4x4 complex S-matrix in the single-ended port order of the file.
pub type FourPortSMatrixV1 = [[Complex64; 4]; 4];

fn multiply(left: &FourPortSMatrixV1, right: &FourPortSMatrixV1) -> FourPortSMatrixV1 {
    let mut result = [[Complex64::try_new(0.0, 0.0).expect("zero"); 4]; 4];
    for row in 0..4 {
        for column in 0..4 {
            let mut sum = 0.0_f64;
            let mut imag = 0.0_f64;
            for index in 0..4 {
                let a = left[row][index];
                let b = right[index][column];
                sum += a.real() * b.real() - a.imaginary() * b.imaginary();
                imag += a.real() * b.imaginary() + a.imaginary() * b.real();
            }
            result[row][column] = Complex64::try_new(sum, imag).expect("finite");
        }
    }
    result
}

/// Apply the mixed-mode transform: `COM_T * s * COM_T^-1`.
pub fn com_mixed_mode_v1(s: &FourPortSMatrixV1) -> FourPortSMatrixV1 {
    // COM_T^-1 == 0.5 * COM_T since COM_T^2 = 2I.
    let half: FourPortSMatrixV1 = [
        [c(0.5, 0.0), c(0.5, 0.0), c(0.0, 0.0), c(0.0, 0.0)],
        [c(0.5, 0.0), c(-0.5, 0.0), c(0.0, 0.0), c(0.0, 0.0)],
        [c(0.0, 0.0), c(0.0, 0.0), c(0.5, 0.0), c(0.5, 0.0)],
        [c(0.0, 0.0), c(0.0, 0.0), c(0.5, 0.0), c(-0.5, 0.0)],
    ];
    multiply(&multiply(&com_t_v1(), s), &half)
}

/// Differential victim-path response: mixed-mode row 3, column 1.
pub fn sdd21_v1(s: &FourPortSMatrixV1) -> Complex64 {
    com_mixed_mode_v1(s)[3][1]
}

/// Apply the source-line R480 per-port P/N skew phase matrix.
///
/// The argument order is intentionally retained from `Sigfct(txp, txn, rxp,
/// rxn)`: internally the source calls these `(sigma2, sigma1, sigma4,
/// sigma3)`.  This is a frequency-domain phase operation only; it does not
/// fit, interpolate, or resolve a channel.
pub fn apply_r480_pn_skew_v1(
    frequency_hz: &[f64],
    samples: &[FourPortSMatrixV1],
    txp_ps: f64,
    txn_ps: f64,
    rxp_ps: f64,
    rxn_ps: f64,
) -> Result<Vec<FourPortSMatrixV1>, MixedModeErrorV1> {
    if frequency_hz.len() != samples.len() {
        return Err(MixedModeErrorV1::LengthMismatch);
    }
    if frequency_hz.is_empty() {
        return Err(MixedModeErrorV1::EmptySpectrum);
    }
    if frequency_hz
        .iter()
        .any(|value| !value.is_finite() || *value < 0.0)
    {
        return Err(MixedModeErrorV1::InvalidFrequency);
    }
    if [txp_ps, txn_ps, rxp_ps, rxn_ps]
        .iter()
        .any(|value| !value.is_finite())
    {
        return Err(MixedModeErrorV1::InvalidDelay);
    }
    samples
        .iter()
        .zip(frequency_hz)
        .map(|(sample, frequency)| {
            let sigma2 = phase_v1(*frequency, txp_ps);
            let sigma1 = phase_v1(*frequency, txn_ps);
            let sigma4 = phase_v1(*frequency, rxp_ps);
            let sigma3 = phase_v1(*frequency, rxn_ps);
            let phases = [
                [
                    complex_mul_v1(sigma1, sigma1),
                    complex_mul_v1(sigma1, sigma2),
                    complex_mul_v1(sigma1, sigma3),
                    complex_mul_v1(sigma1, sigma4),
                ],
                [
                    complex_mul_v1(sigma1, sigma2),
                    complex_mul_v1(sigma2, sigma2),
                    complex_mul_v1(sigma2, sigma3),
                    complex_mul_v1(sigma2, sigma4),
                ],
                [
                    complex_mul_v1(sigma1, sigma3),
                    complex_mul_v1(sigma2, sigma3),
                    complex_mul_v1(sigma3, sigma3),
                    complex_mul_v1(sigma3, sigma4),
                ],
                [
                    complex_mul_v1(sigma1, sigma4),
                    complex_mul_v1(sigma2, sigma4),
                    complex_mul_v1(sigma3, sigma4),
                    complex_mul_v1(sigma4, sigma4),
                ],
            ];
            let mut result = [[c(0.0, 0.0); 4]; 4];
            for row in 0..4 {
                for column in 0..4 {
                    result[row][column] = complex_mul_v1(phases[row][column], sample[row][column]);
                }
            }
            Ok(result)
        })
        .collect()
}

/// Apply the mixed-mode transform to each sample in a frequency trace.
pub fn com_mixed_mode_spectrum_v1(samples: &[FourPortSMatrixV1]) -> Vec<FourPortSMatrixV1> {
    samples.iter().map(com_mixed_mode_v1).collect()
}

fn phase_v1(frequency_hz: f64, delay_ps: f64) -> Complex64 {
    let angle = 2.0 * std::f64::consts::PI * frequency_hz * delay_ps * 1.0e-12;
    c(angle.cos(), angle.sin())
}

fn complex_mul_v1(left: Complex64, right: Complex64) -> Complex64 {
    c(
        left.real() * right.real() - left.imaginary() * right.imaginary(),
        left.real() * right.imaginary() + left.imaginary() * right.real(),
    )
}

/// Explicit scope policy of this ported stage.
pub const NETWORK_INGEST_POLICY_V1: &str =
    "sipi.p5-04a.network-ingest-v1.mixed-mode-transform-only";

#[cfg(test)]
mod tests {
    use super::*;

    fn cm(real: f64, imaginary: f64) -> Complex64 {
        Complex64::try_new(real, imaginary).expect("complex")
    }

    #[test]
    fn identity_transforms_to_identity() {
        let identity: FourPortSMatrixV1 = [
            [cm(1.0, 0.0), cm(0.0, 0.0), cm(0.0, 0.0), cm(0.0, 0.0)],
            [cm(0.0, 0.0), cm(1.0, 0.0), cm(0.0, 0.0), cm(0.0, 0.0)],
            [cm(0.0, 0.0), cm(0.0, 0.0), cm(1.0, 0.0), cm(0.0, 0.0)],
            [cm(0.0, 0.0), cm(0.0, 0.0), cm(0.0, 0.0), cm(1.0, 0.0)],
        ];
        let mixed = com_mixed_mode_v1(&identity);
        assert!((mixed[0][0].real() - 1.0).abs() < 1e-12);
        assert!((mixed[1][1].real() - 1.0).abs() < 1e-12);
        assert!((mixed[2][2].real() - 1.0).abs() < 1e-12);
        assert!((mixed[3][3].real() - 1.0).abs() < 1e-12);
        // sdd21 is mixed[3][1]; for the identity network it is zero.
        assert!(sdd21_v1(&identity).real().abs() < 1e-12);
    }

    #[test]
    fn differential_only_network_yields_sdd21_one() {
        // s31=1, s42=1, s41=0, s32=0 -> differential gain 1.
        let s: FourPortSMatrixV1 = [
            [cm(0.0, 0.0), cm(0.0, 0.0), cm(0.0, 0.0), cm(0.0, 0.0)],
            [cm(0.0, 0.0), cm(0.0, 0.0), cm(0.0, 0.0), cm(0.0, 0.0)],
            [cm(1.0, 0.0), cm(0.0, 0.0), cm(0.0, 0.0), cm(0.0, 0.0)],
            [cm(0.0, 0.0), cm(1.0, 0.0), cm(0.0, 0.0), cm(0.0, 0.0)],
        ];
        assert!((sdd21_v1(&s).real() - 1.0).abs() < 1e-12);
    }

    #[test]
    fn common_mode_is_rejected_by_sdd21() {
        // s31=1, s32=1 -> common-mode only, differential gain 0.
        let s: FourPortSMatrixV1 = [
            [cm(0.0, 0.0), cm(0.0, 0.0), cm(0.0, 0.0), cm(0.0, 0.0)],
            [cm(0.0, 0.0), cm(0.0, 0.0), cm(0.0, 0.0), cm(0.0, 0.0)],
            [cm(1.0, 0.0), cm(1.0, 0.0), cm(0.0, 0.0), cm(0.0, 0.0)],
            [cm(0.0, 0.0), cm(0.0, 0.0), cm(0.0, 0.0), cm(0.0, 0.0)],
        ];
        assert!(sdd21_v1(&s).real().abs() < 1e-12);
    }

    #[test]
    fn policy_string_is_fixed() {
        assert_eq!(
            NETWORK_INGEST_POLICY_V1,
            "sipi.p5-04a.network-ingest-v1.mixed-mode-transform-only",
        );
    }

    #[test]
    fn pn_skew_applies_source_argument_order_and_preserves_zero_delay() {
        let frequencies = [1.0e9, 2.0e9];
        let mut samples = [[cm(0.0, 0.0); 4]; 4];
        samples[0][1] = cm(1.0, 0.0);
        let result = apply_r480_pn_skew_v1(&frequencies, &[samples, samples], 0.0, 10.0, 0.0, 0.0)
            .expect("skew");
        let expected = 2.0 * std::f64::consts::PI * 1.0e9 * 10.0e-12;
        assert!((result[0][0][1].real() - expected.cos()).abs() < 1.0e-12);
        assert!((result[0][0][1].imaginary() - expected.sin()).abs() < 1.0e-12);
        let unchanged =
            apply_r480_pn_skew_v1(&frequencies, &[samples, samples], 0.0, 0.0, 0.0, 0.0)
                .expect("zero skew");
        assert_eq!(unchanged[1][0][1], cm(1.0, 0.0));
    }
}
