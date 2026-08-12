//! Fixed P3C PRBS9-v2 waveform NRMSE profile.
//!
//! This module evaluates only caller-supplied, finite, strict-grid waveform
//! arrays. It does not read ADS output, bind an external reference, align
//! samples, or claim profile acceptance.

use std::{error::Error, fmt};

use sha2::{Digest, Sha256};

pub const PRBS9_METRIC_PROFILE_V2_SCHEMA: &str = "sipi.compare.prbs9-waveform-metric.v2";
pub const PRBS9_WAVEFORM_NRMSE_POLICY_V2: &str = "sipi.compare.prbs9-v2.third-period-strict-grid-nrmse.v1";
pub const PRBS9_CONTRACT_V2_SHA256: &str = "f47329b6ddda01cbcde1f24e21cb93e03f8ef6139ea2d43ff74cad9e2049d2b5";
pub const PRBS9_TOTAL_SAMPLES_V2: usize = 49_056;
pub const PRBS9_THIRD_PERIOD_START_V2: usize = 32_704;
pub const PRBS9_THIRD_PERIOD_SAMPLES_V2: usize = 16_352;
pub const PRBS9_WAVEFORM_NRMSE_LIMIT_V2: f64 = 0.01;

/// The immutable product profile; callers cannot supply a seed, axis, or tolerance.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct Prbs9WaveformMetricProfileV2;

impl Prbs9WaveformMetricProfileV2 {
    pub const fn contract_sha256(self) -> &'static str {
        PRBS9_CONTRACT_V2_SHA256
    }

    pub const fn total_samples(self) -> usize {
        PRBS9_TOTAL_SAMPLES_V2
    }

    pub const fn compared_start(self) -> usize {
        PRBS9_THIRD_PERIOD_START_V2
    }

    pub const fn compared_samples(self) -> usize {
        PRBS9_THIRD_PERIOD_SAMPLES_V2
    }

    pub const fn waveform_nrmse_limit(self) -> f64 {
        PRBS9_WAVEFORM_NRMSE_LIMIT_V2
    }
}

/// Two full fixed-grid waveforms. Construction performs no alignment or transform.
#[derive(Clone, Debug, PartialEq)]
pub struct Prbs9WaveformPairV2 {
    reference: Vec<f64>,
    candidate: Vec<f64>,
}

impl Prbs9WaveformPairV2 {
    pub fn try_new(reference: Vec<f64>, candidate: Vec<f64>) -> Result<Self, Prbs9WaveformMetricErrorV2> {
        validate_waveform("reference", &reference)?;
        validate_waveform("candidate", &candidate)?;
        Ok(Self { reference, candidate })
    }

    pub fn reference(&self) -> &[f64] {
        &self.reference
    }

    pub fn candidate(&self) -> &[f64] {
        &self.candidate
    }

    pub fn reference_digest(&self) -> String {
        waveform_digest(b"reference", &self.reference)
    }

    pub fn candidate_digest(&self) -> String {
        waveform_digest(b"candidate", &self.candidate)
    }
}

/// A narrow waveform-only report; eye and jitter remain intentionally unevaluated.
#[derive(Clone, Debug, PartialEq)]
pub struct Prbs9WaveformMetricReportV2 {
    schema: &'static str,
    policy: &'static str,
    contract_sha256: &'static str,
    reference_digest: String,
    candidate_digest: String,
    compared_start: usize,
    compared_samples: usize,
    waveform_nrmse: f64,
    waveform_nrmse_limit: f64,
    within_waveform_nrmse_limit: bool,
    within_metric_limits: bool,
    evaluation_scope: &'static str,
    external_reference_binding: &'static str,
    external_profile_acceptance: &'static str,
    eye_metrics: &'static str,
    jitter_metrics: &'static str,
}

impl Prbs9WaveformMetricReportV2 {
    pub fn schema(&self) -> &'static str { self.schema }
    pub fn policy(&self) -> &'static str { self.policy }
    pub fn contract_sha256(&self) -> &'static str { self.contract_sha256 }
    pub fn reference_digest(&self) -> &str { &self.reference_digest }
    pub fn candidate_digest(&self) -> &str { &self.candidate_digest }
    pub fn compared_start(&self) -> usize { self.compared_start }
    pub fn compared_samples(&self) -> usize { self.compared_samples }
    pub fn waveform_nrmse(&self) -> f64 { self.waveform_nrmse }
    pub fn waveform_nrmse_limit(&self) -> f64 { self.waveform_nrmse_limit }
    pub fn within_waveform_nrmse_limit(&self) -> bool { self.within_waveform_nrmse_limit }
    pub fn within_metric_limits(&self) -> bool { self.within_metric_limits }
    pub fn evaluation_scope(&self) -> &'static str { self.evaluation_scope }
    pub fn external_reference_binding(&self) -> &'static str { self.external_reference_binding }
    pub fn external_profile_acceptance(&self) -> &'static str { self.external_profile_acceptance }
    pub fn eye_metrics(&self) -> &'static str { self.eye_metrics }
    pub fn jitter_metrics(&self) -> &'static str { self.jitter_metrics }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum Prbs9WaveformMetricErrorV2 {
    LengthMismatch { waveform: &'static str, expected: usize, actual: usize },
    NonFiniteValue { waveform: &'static str, index: usize },
    NumericOverflow { index: usize },
    ZeroReferenceNorm,
}

impl fmt::Display for Prbs9WaveformMetricErrorV2 {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::LengthMismatch { waveform, expected, actual } => write!(formatter, "{waveform} waveform must contain {expected} samples, got {actual}"),
            Self::NonFiniteValue { waveform, index } => write!(formatter, "{waveform} waveform is non-finite at index {index}"),
            Self::NumericOverflow { index } => write!(formatter, "waveform NRMSE arithmetic is non-finite at index {index}"),
            Self::ZeroReferenceNorm => write!(formatter, "third-period reference waveform norm is zero"),
        }
    }
}

impl Error for Prbs9WaveformMetricErrorV2 {}

/// Calculates the frozen third-period waveform NRMSE without alignment or fitting.
pub fn compare_prbs9_waveform_nrmse_v2(
    pair: &Prbs9WaveformPairV2,
) -> Result<Prbs9WaveformMetricReportV2, Prbs9WaveformMetricErrorV2> {
    let range = PRBS9_THIRD_PERIOD_START_V2..PRBS9_THIRD_PERIOD_START_V2 + PRBS9_THIRD_PERIOD_SAMPLES_V2;
    let mut reference_sum = ScaledSumSquares::default();
    let mut error_sum = ScaledSumSquares::default();
    for index in range.clone() {
        let difference = pair.candidate[index] - pair.reference[index];
        if !difference.is_finite() {
            return Err(Prbs9WaveformMetricErrorV2::NumericOverflow { index });
        }
        reference_sum.add(pair.reference[index]);
        error_sum.add(difference);
    }
    if reference_sum.is_zero() {
        return Err(Prbs9WaveformMetricErrorV2::ZeroReferenceNorm);
    }
    let nrmse = error_sum.ratio_sqrt(reference_sum).ok_or(
        Prbs9WaveformMetricErrorV2::NumericOverflow { index: PRBS9_THIRD_PERIOD_START_V2 },
    )?;
    let within = nrmse <= PRBS9_WAVEFORM_NRMSE_LIMIT_V2;
    Ok(Prbs9WaveformMetricReportV2 {
        schema: PRBS9_METRIC_PROFILE_V2_SCHEMA,
        policy: PRBS9_WAVEFORM_NRMSE_POLICY_V2,
        contract_sha256: PRBS9_CONTRACT_V2_SHA256,
        reference_digest: pair.reference_digest(),
        candidate_digest: pair.candidate_digest(),
        compared_start: range.start,
        compared_samples: range.len(),
        waveform_nrmse: nrmse,
        waveform_nrmse_limit: PRBS9_WAVEFORM_NRMSE_LIMIT_V2,
        within_waveform_nrmse_limit: within,
        within_metric_limits: within,
        evaluation_scope: "caller_supplied_strict_grid_waveforms_only",
        external_reference_binding: "not_evaluated",
        external_profile_acceptance: "not_evaluated",
        eye_metrics: "not_implemented",
        jitter_metrics: "not_implemented",
    })
}

fn validate_waveform(waveform: &'static str, values: &[f64]) -> Result<(), Prbs9WaveformMetricErrorV2> {
    if values.len() != PRBS9_TOTAL_SAMPLES_V2 {
        return Err(Prbs9WaveformMetricErrorV2::LengthMismatch { waveform, expected: PRBS9_TOTAL_SAMPLES_V2, actual: values.len() });
    }
    for (index, value) in values.iter().enumerate() {
        if !value.is_finite() {
            return Err(Prbs9WaveformMetricErrorV2::NonFiniteValue { waveform, index });
        }
    }
    Ok(())
}

#[derive(Default)]
struct ScaledSumSquares {
    scale: f64,
    sum_squares: f64,
}

impl ScaledSumSquares {
    fn add(&mut self, value: f64) {
        let magnitude = value.abs();
        if magnitude == 0.0 {
            return;
        }
        if self.scale < magnitude {
            let ratio = self.scale / magnitude;
            self.sum_squares = 1.0 + self.sum_squares * ratio * ratio;
            self.scale = magnitude;
        } else {
            let ratio = magnitude / self.scale;
            self.sum_squares += ratio * ratio;
        }
    }

    fn is_zero(&self) -> bool {
        self.scale == 0.0
    }

    fn ratio_sqrt(&self, denominator: Self) -> Option<f64> {
        let scale_ratio = self.scale / denominator.scale;
        let sum_ratio = self.sum_squares / denominator.sum_squares;
        let result = scale_ratio * sum_ratio.sqrt();
        result.is_finite().then_some(result)
    }
}

fn waveform_digest(kind: &[u8], values: &[f64]) -> String {
    let mut hash = Sha256::new();
    hash.update(b"sipi.compare.prbs9-waveform-v2");
    hash.update((kind.len() as u64).to_le_bytes());
    hash.update(kind);
    hash.update((values.len() as u64).to_le_bytes());
    for value in values {
        hash.update(value.to_bits().to_le_bytes());
    }
    format!("{:x}", hash.finalize())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn waveform(value: f64) -> Vec<f64> {
        vec![value; PRBS9_TOTAL_SAMPLES_V2]
    }

    #[test]
    fn exact_pair_is_strict_grid_waveform_only_and_within_limit() {
        let pair = Prbs9WaveformPairV2::try_new(waveform(1.0), waveform(1.0)).unwrap();
        let report = compare_prbs9_waveform_nrmse_v2(&pair).unwrap();
        assert_eq!(report.contract_sha256(), PRBS9_CONTRACT_V2_SHA256);
        assert_eq!(report.compared_start(), PRBS9_THIRD_PERIOD_START_V2);
        assert_eq!(report.compared_samples(), PRBS9_THIRD_PERIOD_SAMPLES_V2);
        assert_eq!(report.waveform_nrmse(), 0.0);
        assert!(report.within_metric_limits());
        assert_eq!(report.evaluation_scope(), "caller_supplied_strict_grid_waveforms_only");
        assert_eq!(report.external_reference_binding(), "not_evaluated");
        assert_eq!(report.external_profile_acceptance(), "not_evaluated");
        assert_eq!(report.eye_metrics(), "not_implemented");
        assert_eq!(report.jitter_metrics(), "not_implemented");
    }

    #[test]
    fn only_the_frozen_third_period_contributes() {
        let reference = waveform(1.0);
        let mut candidate = waveform(1.0);
        candidate[0] = -1.0;
        let pair = Prbs9WaveformPairV2::try_new(reference.clone(), candidate).unwrap();
        assert_eq!(compare_prbs9_waveform_nrmse_v2(&pair).unwrap().waveform_nrmse(), 0.0);
        let mut third_period_candidate = reference;
        third_period_candidate[PRBS9_THIRD_PERIOD_START_V2] = -1.0;
        let pair = Prbs9WaveformPairV2::try_new(waveform(1.0), third_period_candidate).unwrap();
        assert!(compare_prbs9_waveform_nrmse_v2(&pair).unwrap().waveform_nrmse() > PRBS9_WAVEFORM_NRMSE_LIMIT_V2);
    }

    #[test]
    fn no_shift_gain_offset_or_polarity_is_hidden() {
        let reference = (0..PRBS9_TOTAL_SAMPLES_V2).map(|index| if index % 2 == 0 { -1.0 } else { 1.0 }).collect::<Vec<_>>();
        let mut shifted = reference.clone();
        shifted.rotate_right(1);
        for candidate in [shifted, reference.iter().map(|value| value + 0.1).collect(), reference.iter().map(|value| value * 1.1).collect(), reference.iter().map(|value| -value).collect()] {
            let pair = Prbs9WaveformPairV2::try_new(reference.clone(), candidate).unwrap();
            assert!(!compare_prbs9_waveform_nrmse_v2(&pair).unwrap().within_waveform_nrmse_limit());
        }
    }

    #[test]
    fn malformed_or_numerically_unsafe_inputs_fail_closed() {
        assert_eq!(Prbs9WaveformPairV2::try_new(vec![], waveform(1.0)), Err(Prbs9WaveformMetricErrorV2::LengthMismatch { waveform: "reference", expected: PRBS9_TOTAL_SAMPLES_V2, actual: 0 }));
        let mut non_finite = waveform(1.0);
        non_finite[11] = f64::NAN;
        assert_eq!(Prbs9WaveformPairV2::try_new(waveform(1.0), non_finite), Err(Prbs9WaveformMetricErrorV2::NonFiniteValue { waveform: "candidate", index: 11 }));
        let pair = Prbs9WaveformPairV2::try_new(waveform(0.0), waveform(0.0)).unwrap();
        assert_eq!(compare_prbs9_waveform_nrmse_v2(&pair), Err(Prbs9WaveformMetricErrorV2::ZeroReferenceNorm));
        let pair = Prbs9WaveformPairV2::try_new(waveform(f64::MAX), waveform(-f64::MAX)).unwrap();
        assert_eq!(compare_prbs9_waveform_nrmse_v2(&pair), Err(Prbs9WaveformMetricErrorV2::NumericOverflow { index: PRBS9_THIRD_PERIOD_START_V2 }));
    }
}
