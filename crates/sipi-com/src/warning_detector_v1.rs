//! Deterministic R480-class warning detector core (P5-02m).
//!
//! Implements product-side, mechanically-detectable warnings that mirror the
//! observed R480 warning classes (P5-02i) WITHOUT requiring the MATLAB
//! oracle: (1) anti-causal response detection from pre-cursor energy, and
//! (2) high-frequency non-decay (extrapolation-risk) detection. Both are
//! deterministic signal-characteristic checks on caller-supplied arrays,
//! profile-agnostic, and fail-closed. They are NOT the full warning
//! contract (which needs the oracle golden); they form the deterministic
//! subset that the product can assert independently.

/// Stable scope policy of the P5-02m warning detector core.
pub const WARNING_DETECTOR_POLICY_V1: &str = "sipi.p5-02m.warning-detector.v1.deterministic";

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum WarningDetectorErrorV1 {
    EmptyInput,
    NonFinite,
    InvalidThreshold,
}

/// Detects anti-causality from pre-cursor energy in a time impulse h[n].
///
/// A causal channel has negligible energy before its main peak. We locate
/// the peak index, then compute the energy fraction in the `peak_exclusion`
/// samples immediately before the peak (excluding numerical warm-up). A
/// non-negligible fraction flags anti-causality (mirrors R480 line 6337).
pub fn anti_causal_precursor_fraction_v1(
    impulse: &[f64],
    peak_exclusion: usize,
) -> Result<f64, WarningDetectorErrorV1> {
    if impulse.is_empty() {
        return Err(WarningDetectorErrorV1::EmptyInput);
    }
    let total_energy: f64 = impulse.iter().map(|v| v * v).sum();
    if !total_energy.is_finite() || total_energy <= 0.0 {
        return Err(WarningDetectorErrorV1::NonFinite);
    }
    let n = impulse.len();
    if n <= 2 * peak_exclusion {
        return Ok(0.0);
    }
    let mut peak_idx = 0usize;
    let mut peak_val = f64::NEG_INFINITY;
    for i in 0..n {
        if impulse[i] > peak_val { peak_val = impulse[i]; peak_idx = i; }
    }
    if peak_idx < peak_exclusion {
        return Ok(0.0);
    }
    let precursor: f64 = impulse[peak_idx - peak_exclusion..peak_idx].iter().map(|v| v * v).sum();
    Ok(precursor / total_energy)
}

/// Flags anti-causality when the pre-cursor energy fraction exceeds a threshold.
pub fn detect_anti_causal_v1(
    impulse: &[f64],
    peak_exclusion: usize,
    threshold: f64,
) -> Result<bool, WarningDetectorErrorV1> {
    if !threshold.is_finite() || !(0.0 <= threshold && threshold <= 1.0) {
        return Err(WarningDetectorErrorV1::InvalidThreshold);
    }
    let fraction = anti_causal_precursor_fraction_v1(impulse, peak_exclusion)?;
    Ok(fraction > threshold)
}

/// Detects high-frequency non-decay (extrapolation risk) from a magnitude
/// spectrum (positive frequencies, ascending). Flagged if the avg tail does
/// not fall below the bin just before it (mirrors R480 line 6327).
pub fn detect_high_freq_non_decay_v1(
    magnitude_db: &[f64],
    tail_bins: usize,
) -> Result<bool, WarningDetectorErrorV1> {
    let n = magnitude_db.len();
    if n < 2 || tail_bins == 0 { return Err(WarningDetectorErrorV1::EmptyInput); }
    let start = n.saturating_sub(tail_bins);
    if start < 1 { return Err(WarningDetectorErrorV1::EmptyInput); }
    let tail_avg: f64 = magnitude_db[start..].iter().map(|v| *v).sum::<f64>() / tail_bins as f64;
    let head_avg = magnitude_db[start - 1];
    if !tail_avg.is_finite() || !head_avg.is_finite() { return Err(WarningDetectorErrorV1::NonFinite); }
    Ok(tail_avg >= head_avg)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn policy_fixed() {
        assert_eq!(WARNING_DETECTOR_POLICY_V1, "sipi.p5-02m.warning-detector.v1.deterministic");
    }

    #[test]
    fn causal_impulse_low_precursor() {
        let impulse = vec![0.0, 0.0, 0.0, 0.0, 1.0, 0.05, 0.02];
        let f = anti_causal_precursor_fraction_v1(&impulse, 2).expect("f");
        assert!(f < 1e-9);
        assert!(!detect_anti_causal_v1(&impulse, 2, 0.05).expect("ok"));
    }

    #[test]
    fn anti_causal_impulse_high_precursor() {
        let impulse = vec![0.0, 0.0, 0.4, 1.0, 0.1];
        let f = anti_causal_precursor_fraction_v1(&impulse, 2).expect("f");
        assert!(f > 0.1, "fraction={f}");
        assert!(detect_anti_causal_v1(&impulse, 2, 0.05).expect("ok"));
    }

    #[test]
    fn rejects_empty() {
        assert_eq!(anti_causal_precursor_fraction_v1(&[], 2).err(), Some(WarningDetectorErrorV1::EmptyInput));
    }

    #[test]
    fn rejects_bad_threshold() {
        let impulse = vec![0.0, 1.0];
        assert_eq!(detect_anti_causal_v1(&impulse, 2, 1.5).err(), Some(WarningDetectorErrorV1::InvalidThreshold));
    }

    #[test]
    fn high_freq_decay_ok() {
        let mag = vec![-10.0, -15.0, -20.0, -25.0, -30.0];
        assert!(!detect_high_freq_non_decay_v1(&mag, 2).expect("ok"));
    }

    #[test]
    fn high_freq_rise_flagged() {
        let mag = vec![-30.0, -25.0, -20.0, -15.0, -10.0];
        assert!(detect_high_freq_non_decay_v1(&mag, 2).expect("ok"));
    }
    
}