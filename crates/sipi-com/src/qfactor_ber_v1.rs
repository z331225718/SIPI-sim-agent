//! Q-factor / BER estimator core (P3C-02e).
//!
//! Implements the owner-decided bathtub estimator (A5 decision, ref
//! docs/baselines/owner-decision-checklist.v1.md): Q-factor method with a
//! 0.1 dB tolerance policy. Converts between Q-factor and bit-error rate
//! (BER) using the standard IEEE 802.3 relation ber = 0.5 * erfc(q /
//! sqrt(2)), reusing the P5-04h erf/erfcinv cores. The eye-folding/
//! bin boundary is owned by the P3C-02c sampled-eye/TIE core; this slice
//! only estimates Q/BER from supplied amplitude and noise.

use crate::erf_v1::{erfc_v1_general, erfcinv_v1};

/// Stable scope policy of the P3C-02e Q-factor/BER estimator.
pub const QFACTOR_BER_POLICY_V1: &str = "sipi.p3c-02e.qfactor-ber.v1.estimator";

/// The owner-decided tolerance policy ref (A5: 0.1 dB).
pub const OWNER_TOLERANCE_POLICY_V1: &str = "sipi.p3c-02e.qfactor-ber.v1.tolerance-0p1db";

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum QFactorBerErrorV1 {
    NonFinite,
    NonPositiveNoiseSigma,
    NonPositiveAmplitude,
    BerOutOfRange,
}

/// Converts a Q-factor to BER: ber = 0.5 * erfc(q / sqrt(2)).
pub fn q_factor_to_ber_v1(q: f64) -> Result<f64, QFactorBerErrorV1> {
    if !q.is_finite() {
        return Err(QFactorBerErrorV1::NonFinite);
    }
    // At exactly q=0 the A&S continued-fraction erfc is degenerate, so the
    // analytic 0.5*erfc(0) = 0.5 is returned directly.
    let arg = q / std::f64::consts::SQRT_2;
    let ber = if arg == 0.0 {
        0.5
    } else {
        0.5 * erfc_v1_general(arg)
    };
    if !ber.is_finite() {
        return Err(QFactorBerErrorV1::NonFinite);
    }
    Ok(ber)
}

/// Converts a BER to Q-factor: q = sqrt(2) * erfcinv(2 * ber).
pub fn ber_to_q_factor_v1(ber: f64) -> Result<f64, QFactorBerErrorV1> {
    if !ber.is_finite() || !(0.0 < ber && ber < 1.0) {
        return Err(QFactorBerErrorV1::BerOutOfRange);
    }
    let twice = 2.0 * ber;
    if !(0.0 < twice && twice < 2.0) {
        return Err(QFactorBerErrorV1::BerOutOfRange);
    }
    let q = std::f64::consts::SQRT_2 * erfcinv_v1(twice);
    if !q.is_finite() {
        return Err(QFactorBerErrorV1::NonFinite);
    }
    Ok(q)
}

/// Estimates Q-factor from a peak-to-peak vertical eye amplitude and a
/// one-sided noise standard deviation: Q = amplitude / (2 * sigma).
/// The 2 accounts for the two-level distance to the symmetric decision
/// boundary (single-ended amplitude to a mid-level threshold).
pub fn estimate_q_factor_v1(
    amplitude_pp_v: f64,
    noise_sigma_v: f64,
) -> Result<f64, QFactorBerErrorV1> {
    if !amplitude_pp_v.is_finite() || !noise_sigma_v.is_finite() {
        return Err(QFactorBerErrorV1::NonFinite);
    }
    if noise_sigma_v <= 0.0 {
        return Err(QFactorBerErrorV1::NonPositiveNoiseSigma);
    }
    if amplitude_pp_v <= 0.0 {
        return Err(QFactorBerErrorV1::NonPositiveAmplitude);
    }
    Ok(amplitude_pp_v / (2.0 * noise_sigma_v))
}

/// Estimates BER from a peak-to-peak amplitude and a one-sided noise sigma.
pub fn estimate_ber_v1(amplitude_pp_v: f64, noise_sigma_v: f64) -> Result<f64, QFactorBerErrorV1> {
    let q = estimate_q_factor_v1(amplitude_pp_v, noise_sigma_v)?;
    q_factor_to_ber_v1(q)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn policy_fixed() {
        assert_eq!(
            QFACTOR_BER_POLICY_V1,
            "sipi.p3c-02e.qfactor-ber.v1.estimator"
        );
        assert_eq!(
            OWNER_TOLERANCE_POLICY_V1,
            "sipi.p3c-02e.qfactor-ber.v1.tolerance-0p1db"
        );
    }

    #[test]
    fn q_to_ber_known_value() {
        // scipy: q=7 -> ber = 0.5*erfc(7/sqrt2) = 1.2798e-12
        let ber = q_factor_to_ber_v1(7.0).expect("ber");
        assert!((ber - 1.2798125438855354e-12).abs() < 1e-14);
    }

    #[test]
    fn q_zero_gives_half_ber() {
        // q=0: ber = 0.5*erfc(0) = 0.5
        let ber = q_factor_to_ber_v1(0.0).expect("ber");
        assert!((ber - 0.5).abs() < 1e-15);
    }

    #[test]
    fn ber_to_q_roundtrip() {
        for q in [3.5, 4.5, 6.0, 7.0] {
            let ber = q_factor_to_ber_v1(q).expect("ber");
            let q_back = ber_to_q_factor_v1(ber).expect("q");
            assert!((q_back - q).abs() < 1e-9, "q={q} roundtrip {q_back}");
        }
    }

    #[test]
    fn estimate_q_from_signal_noise() {
        let q = estimate_q_factor_v1(1.0, 0.1).expect("q");
        assert!((q - 5.0).abs() < 1e-12);
    }

    #[test]
    fn estimate_ber_end_to_end() {
        let ber = estimate_ber_v1(0.5, 0.05).expect("ber");
        let q = estimate_q_factor_v1(0.5, 0.05).expect("q");
        let ber_q = q_factor_to_ber_v1(q).expect("berq");
        assert!((ber - ber_q).abs() < 1e-20);
    }

    #[test]
    fn rejects_nonpositive_noise() {
        assert_eq!(
            estimate_q_factor_v1(1.0, 0.0).err(),
            Some(QFactorBerErrorV1::NonPositiveNoiseSigma),
        );
        assert_eq!(
            estimate_q_factor_v1(1.0, -0.1).err(),
            Some(QFactorBerErrorV1::NonPositiveNoiseSigma),
        );
    }

    #[test]
    fn rejects_bad_ber_range() {
        assert_eq!(
            ber_to_q_factor_v1(0.0).err(),
            Some(QFactorBerErrorV1::BerOutOfRange)
        );
        assert_eq!(
            ber_to_q_factor_v1(1.0).err(),
            Some(QFactorBerErrorV1::BerOutOfRange)
        );
    }
}
