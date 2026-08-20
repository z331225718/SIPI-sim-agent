//! Mixed-mode S-parameter transform for the R480 network-ingest stage.
//!
//! Ported from agent-com `src/agent_com/network/mixed_mode.py` (MIT
//! source, P5-04a source map). The COM_T transform and sdd21 extraction
//! follow the MATLAB r4.80 convention used by the oracle. This module
//! performs the standard linear transform only; it does not read files,
//! apply port orders, or compute any COM metric.

use sipi_types::Complex64;

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
}
