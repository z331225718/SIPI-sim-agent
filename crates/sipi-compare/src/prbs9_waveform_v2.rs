//! Fixed P3C PRBS9-v2 waveform NRMSE profile.
//!
//! This module evaluates only caller-supplied, finite, strict-grid waveform
//! arrays. It does not read ADS output, bind an external reference, align
//! samples, or claim profile acceptance.

use std::{error::Error, fmt};

use sha2::{Digest, Sha256};

pub const PRBS9_METRIC_PROFILE_V2_SCHEMA: &str = "sipi.compare.prbs9-waveform-metric.v2";
pub const PRBS9_WAVEFORM_NRMSE_POLICY_V2: &str =
    "sipi.compare.prbs9-v2.third-period-strict-grid-nrmse.v1";
pub const PRBS9_CONTRACT_V2_SHA256: &str =
    "f47329b6ddda01cbcde1f24e21cb93e03f8ef6139ea2d43ff74cad9e2049d2b5";
pub const PRBS9_PERIOD_SHA256_V2: &str =
    "4437fb3beb2fa1ca99b4177673c53fc20089ac9cf68b1adaa1e0fad14d742127";
pub const PRBS9_TOTAL_SAMPLES_V2: usize = 49_056;
pub const PRBS9_THIRD_PERIOD_START_V2: usize = 32_704;
pub const PRBS9_THIRD_PERIOD_SAMPLES_V2: usize = 16_352;
pub const PRBS9_WAVEFORM_NRMSE_LIMIT_V2: f64 = 0.01;
pub const PRBS9_EYE_RELATIVE_ERROR_LIMIT_V2: f64 = 0.01;
pub const PRBS9_TIE_ERROR_LIMIT_SECONDS_V2: f64 = 3.125e-13;
const SAMPLES_PER_UI: usize = 32;
const PERIOD_UI: usize = 511;
const COMPARED_START_UI: usize = PRBS9_THIRD_PERIOD_START_V2 / SAMPLES_PER_UI;
const COMPARED_END_UI: usize = PRBS9_TOTAL_SAMPLES_V2 / SAMPLES_PER_UI;
const SAMPLE_INTERVAL_SECONDS: f64 = 9.765625e-13;
const UI_SECONDS: f64 = 3.125e-11;

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

    pub const fn eye_relative_error_limit(self) -> f64 {
        PRBS9_EYE_RELATIVE_ERROR_LIMIT_V2
    }
    pub const fn tie_error_limit_seconds(self) -> f64 {
        PRBS9_TIE_ERROR_LIMIT_SECONDS_V2
    }
}

/// Two full fixed-grid waveforms. Construction performs no alignment or transform.
#[derive(Clone, Debug, PartialEq)]
pub struct Prbs9WaveformPairV2 {
    reference: Vec<f64>,
    candidate: Vec<f64>,
}

impl Prbs9WaveformPairV2 {
    pub fn try_new(
        reference: Vec<f64>,
        candidate: Vec<f64>,
    ) -> Result<Self, Prbs9WaveformMetricErrorV2> {
        validate_waveform("reference", &reference)?;
        validate_waveform("candidate", &candidate)?;
        Ok(Self {
            reference,
            candidate,
        })
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

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Prbs9EyeMetricV2 {
    height_volts: f64,
    width_seconds: f64,
}
impl Prbs9EyeMetricV2 {
    pub fn height_volts(&self) -> f64 {
        self.height_volts
    }
    pub fn width_seconds(&self) -> f64 {
        self.width_seconds
    }
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Prbs9TieMetricV2 {
    raw_rms_seconds: f64,
    crossing_count: usize,
}
impl Prbs9TieMetricV2 {
    pub fn raw_rms_seconds(&self) -> f64 {
        self.raw_rms_seconds
    }
    pub fn crossing_count(&self) -> usize {
        self.crossing_count
    }
}

/// A strict product-side metric report. It is not an external profile acceptance.
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
    reference_eye: Prbs9EyeMetricV2,
    candidate_eye: Prbs9EyeMetricV2,
    eye_height_relative_error: f64,
    eye_width_relative_error: f64,
    within_eye_limits: bool,
    reference_tie: Prbs9TieMetricV2,
    candidate_tie: Prbs9TieMetricV2,
    paired_tie_rmse_seconds: f64,
    within_tie_limit: bool,
}

impl Prbs9WaveformMetricReportV2 {
    pub fn schema(&self) -> &'static str {
        self.schema
    }
    pub fn policy(&self) -> &'static str {
        self.policy
    }
    pub fn contract_sha256(&self) -> &'static str {
        self.contract_sha256
    }
    pub fn reference_digest(&self) -> &str {
        &self.reference_digest
    }
    pub fn candidate_digest(&self) -> &str {
        &self.candidate_digest
    }
    pub fn compared_start(&self) -> usize {
        self.compared_start
    }
    pub fn compared_samples(&self) -> usize {
        self.compared_samples
    }
    pub fn waveform_nrmse(&self) -> f64 {
        self.waveform_nrmse
    }
    pub fn waveform_nrmse_limit(&self) -> f64 {
        self.waveform_nrmse_limit
    }
    pub fn within_waveform_nrmse_limit(&self) -> bool {
        self.within_waveform_nrmse_limit
    }
    pub fn within_metric_limits(&self) -> bool {
        self.within_metric_limits
    }
    pub fn evaluation_scope(&self) -> &'static str {
        self.evaluation_scope
    }
    pub fn external_reference_binding(&self) -> &'static str {
        self.external_reference_binding
    }
    pub fn external_profile_acceptance(&self) -> &'static str {
        self.external_profile_acceptance
    }
    pub fn reference_eye(&self) -> Prbs9EyeMetricV2 {
        self.reference_eye
    }
    pub fn candidate_eye(&self) -> Prbs9EyeMetricV2 {
        self.candidate_eye
    }
    pub fn eye_height_relative_error(&self) -> f64 {
        self.eye_height_relative_error
    }
    pub fn eye_width_relative_error(&self) -> f64 {
        self.eye_width_relative_error
    }
    pub fn within_eye_limits(&self) -> bool {
        self.within_eye_limits
    }
    pub fn reference_tie(&self) -> Prbs9TieMetricV2 {
        self.reference_tie
    }
    pub fn candidate_tie(&self) -> Prbs9TieMetricV2 {
        self.candidate_tie
    }
    pub fn paired_tie_rmse_seconds(&self) -> f64 {
        self.paired_tie_rmse_seconds
    }
    pub fn within_tie_limit(&self) -> bool {
        self.within_tie_limit
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum Prbs9WaveformMetricErrorV2 {
    LengthMismatch {
        waveform: &'static str,
        expected: usize,
        actual: usize,
    },
    NonFiniteValue {
        waveform: &'static str,
        index: usize,
    },
    NumericOverflow {
        index: usize,
    },
    ZeroReferenceNorm,
    ZeroReferenceEyeMetric {
        metric: &'static str,
    },
    ZeroPlateau {
        waveform: &'static str,
        transition_ui: usize,
        index: usize,
    },
    CrossingCount {
        waveform: &'static str,
        transition_ui: usize,
        actual: usize,
    },
}

impl fmt::Display for Prbs9WaveformMetricErrorV2 {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::LengthMismatch {
                waveform,
                expected,
                actual,
            } => write!(
                formatter,
                "{waveform} waveform must contain {expected} samples, got {actual}"
            ),
            Self::NonFiniteValue { waveform, index } => write!(
                formatter,
                "{waveform} waveform is non-finite at index {index}"
            ),
            Self::NumericOverflow { index } => write!(
                formatter,
                "waveform NRMSE arithmetic is non-finite at index {index}"
            ),
            Self::ZeroReferenceNorm => {
                write!(formatter, "third-period reference waveform norm is zero")
            }
            Self::ZeroReferenceEyeMetric { metric } => {
                write!(formatter, "reference eye {metric} is zero")
            }
            Self::ZeroPlateau {
                waveform,
                transition_ui,
                index,
            } => write!(
                formatter,
                "{waveform} waveform has a zero plateau near UI {transition_ui} at sample {index}"
            ),
            Self::CrossingCount {
                waveform,
                transition_ui,
                actual,
            } => write!(
                formatter,
                "{waveform} waveform has {actual} crossings near nominal UI {transition_ui}"
            ),
        }
    }
}

impl Error for Prbs9WaveformMetricErrorV2 {}

/// Calculates all currently owner-authorized P3C PRBS9-v2 metrics without alignment.
pub fn compare_prbs9_metrics_v2(
    pair: &Prbs9WaveformPairV2,
) -> Result<Prbs9WaveformMetricReportV2, Prbs9WaveformMetricErrorV2> {
    let range =
        PRBS9_THIRD_PERIOD_START_V2..PRBS9_THIRD_PERIOD_START_V2 + PRBS9_THIRD_PERIOD_SAMPLES_V2;
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
    let nrmse =
        error_sum
            .ratio_sqrt(reference_sum)
            .ok_or(Prbs9WaveformMetricErrorV2::NumericOverflow {
                index: PRBS9_THIRD_PERIOD_START_V2,
            })?;
    let within_waveform = nrmse <= PRBS9_WAVEFORM_NRMSE_LIMIT_V2;
    let bits = prbs9_bits();
    let reference_eye = eye_metric(&pair.reference, &bits)?;
    let candidate_eye = eye_metric(&pair.candidate, &bits)?;
    let eye_height_relative_error = relative_error(
        reference_eye.height_volts,
        candidate_eye.height_volts,
        "height",
    )?;
    let eye_width_relative_error = relative_error(
        reference_eye.width_seconds,
        candidate_eye.width_seconds,
        "width",
    )?;
    let within_eye = eye_height_relative_error <= PRBS9_EYE_RELATIVE_ERROR_LIMIT_V2
        && eye_width_relative_error <= PRBS9_EYE_RELATIVE_ERROR_LIMIT_V2;
    let reference_ties = ties(&pair.reference, &bits, "reference")?;
    let candidate_ties = ties(&pair.candidate, &bits, "candidate")?;
    let reference_tie = tie_metric(&reference_ties)?;
    let candidate_tie = tie_metric(&candidate_ties)?;
    let paired_tie_rmse_seconds = rms_difference(&reference_ties, &candidate_ties)?;
    let within_tie = paired_tie_rmse_seconds <= PRBS9_TIE_ERROR_LIMIT_SECONDS_V2;
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
        within_waveform_nrmse_limit: within_waveform,
        within_metric_limits: within_waveform && within_eye && within_tie,
        evaluation_scope: "caller_supplied_strict_grid_waveforms_only",
        external_reference_binding: "not_evaluated",
        external_profile_acceptance: "not_evaluated",
        reference_eye,
        candidate_eye,
        eye_height_relative_error,
        eye_width_relative_error,
        within_eye_limits: within_eye,
        reference_tie,
        candidate_tie,
        paired_tie_rmse_seconds,
        within_tie_limit: within_tie,
    })
}

/// Backwards-compatible name for the original NRMSE-only entrypoint.
///
/// The returned report now also contains the owner-approved sampled-eye and
/// crossing-TIE metrics; callers still receive no external binding or
/// acceptance decision.
pub fn compare_prbs9_waveform_nrmse_v2(
    pair: &Prbs9WaveformPairV2,
) -> Result<Prbs9WaveformMetricReportV2, Prbs9WaveformMetricErrorV2> {
    compare_prbs9_metrics_v2(pair)
}

fn prbs9_bits() -> [bool; PERIOD_UI] {
    let mut state = 0x1a5_u16;
    let mut bits = [false; PERIOD_UI];
    for bit in &mut bits {
        *bit = state & 0x100 != 0;
        let feedback = ((state >> 8) ^ (state >> 4)) & 1;
        state = ((state << 1) & 0x1ff) | feedback;
    }
    bits
}

fn eye_metric(
    values: &[f64],
    bits: &[bool; PERIOD_UI],
) -> Result<Prbs9EyeMetricV2, Prbs9WaveformMetricErrorV2> {
    let mut openings = [0.0; SAMPLES_PER_UI];
    for phase in 0..SAMPLES_PER_UI {
        let mut high_min = f64::INFINITY;
        let mut low_max = f64::NEG_INFINITY;
        for ui in COMPARED_START_UI..COMPARED_END_UI {
            let value = values[ui * SAMPLES_PER_UI + phase];
            if bits[ui % PERIOD_UI] {
                high_min = high_min.min(value);
            } else {
                low_max = low_max.max(value);
            }
        }
        openings[phase] = high_min - low_max;
        if !openings[phase].is_finite() {
            return Err(Prbs9WaveformMetricErrorV2::NumericOverflow {
                index: PRBS9_THIRD_PERIOD_START_V2 + phase,
            });
        }
    }
    let height = openings.into_iter().fold(f64::NEG_INFINITY, f64::max);
    let center = SAMPLES_PER_UI / 2;
    let width_bins = if openings[center] <= 0.0 {
        0
    } else {
        let mut first = center;
        let mut last = center;
        while first > 0 && openings[first - 1] > 0.0 {
            first -= 1;
        }
        while last + 1 < SAMPLES_PER_UI && openings[last + 1] > 0.0 {
            last += 1;
        }
        last - first + 1
    };
    Ok(Prbs9EyeMetricV2 {
        height_volts: height,
        width_seconds: width_bins as f64 * SAMPLE_INTERVAL_SECONDS,
    })
}

fn relative_error(
    reference: f64,
    candidate: f64,
    metric: &'static str,
) -> Result<f64, Prbs9WaveformMetricErrorV2> {
    if reference == 0.0 {
        return Err(Prbs9WaveformMetricErrorV2::ZeroReferenceEyeMetric { metric });
    }
    let result = (candidate - reference).abs() / reference.abs();
    result
        .is_finite()
        .then_some(result)
        .ok_or(Prbs9WaveformMetricErrorV2::NumericOverflow {
            index: PRBS9_THIRD_PERIOD_START_V2,
        })
}

fn ties(
    values: &[f64],
    bits: &[bool; PERIOD_UI],
    waveform: &'static str,
) -> Result<Vec<f64>, Prbs9WaveformMetricErrorV2> {
    let mut result = Vec::new();
    for transition_ui in COMPARED_START_UI..COMPARED_END_UI {
        let previous = bits[(transition_ui - 1) % PERIOD_UI];
        let next = bits[transition_ui % PERIOD_UI];
        if previous == next {
            continue;
        }
        let rising = !previous && next;
        let center = transition_ui * SAMPLES_PER_UI;
        let mut matches = Vec::new();
        for index in center - SAMPLES_PER_UI / 2 - 1..center + SAMPLES_PER_UI / 2 {
            let left = values[index];
            let right = values[index + 1];
            if left == 0.0 && right == 0.0 {
                return Err(Prbs9WaveformMetricErrorV2::ZeroPlateau {
                    waveform,
                    transition_ui,
                    index,
                });
            }
            let crosses = if rising {
                left < 0.0 && right >= 0.0
            } else {
                left > 0.0 && right <= 0.0
            };
            if crosses {
                let fraction = -left / (right - left);
                let time = (index as f64 + fraction) * SAMPLE_INTERVAL_SECONDS;
                let nominal = transition_ui as f64 * UI_SECONDS;
                if time >= nominal - UI_SECONDS / 2.0 && time < nominal + UI_SECONDS / 2.0 {
                    matches.push(time - nominal);
                }
            }
        }
        if matches.len() != 1 {
            return Err(Prbs9WaveformMetricErrorV2::CrossingCount {
                waveform,
                transition_ui,
                actual: matches.len(),
            });
        }
        result.push(matches[0]);
    }
    Ok(result)
}

fn tie_metric(values: &[f64]) -> Result<Prbs9TieMetricV2, Prbs9WaveformMetricErrorV2> {
    let rms = rms(values)?;
    Ok(Prbs9TieMetricV2 {
        raw_rms_seconds: rms,
        crossing_count: values.len(),
    })
}

fn rms_difference(reference: &[f64], candidate: &[f64]) -> Result<f64, Prbs9WaveformMetricErrorV2> {
    if reference.len() != candidate.len() {
        return Err(Prbs9WaveformMetricErrorV2::NumericOverflow {
            index: PRBS9_THIRD_PERIOD_START_V2,
        });
    }
    let differences = reference
        .iter()
        .zip(candidate)
        .map(|(left, right)| right - left)
        .collect::<Vec<_>>();
    rms(&differences)
}

fn rms(values: &[f64]) -> Result<f64, Prbs9WaveformMetricErrorV2> {
    if values.is_empty() {
        return Err(Prbs9WaveformMetricErrorV2::NumericOverflow {
            index: PRBS9_THIRD_PERIOD_START_V2,
        });
    }
    let mut sum = ScaledSumSquares::default();
    for value in values {
        sum.add(*value);
    }
    let result = sum.scale * (sum.sum_squares / values.len() as f64).sqrt();
    result
        .is_finite()
        .then_some(result)
        .ok_or(Prbs9WaveformMetricErrorV2::NumericOverflow {
            index: PRBS9_THIRD_PERIOD_START_V2,
        })
}

fn validate_waveform(
    waveform: &'static str,
    values: &[f64],
) -> Result<(), Prbs9WaveformMetricErrorV2> {
    if values.len() != PRBS9_TOTAL_SAMPLES_V2 {
        return Err(Prbs9WaveformMetricErrorV2::LengthMismatch {
            waveform,
            expected: PRBS9_TOTAL_SAMPLES_V2,
            actual: values.len(),
        });
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

    fn ideal_waveform() -> Vec<f64> {
        let bits = prbs9_bits();
        (0..PRBS9_TOTAL_SAMPLES_V2)
            .map(|index| {
                if bits[(index / SAMPLES_PER_UI) % PERIOD_UI] {
                    1.0
                } else {
                    -1.0
                }
            })
            .collect()
    }

    #[test]
    fn exact_pair_is_strict_grid_waveform_only_and_within_limit() {
        let ideal = ideal_waveform();
        let pair = Prbs9WaveformPairV2::try_new(ideal.clone(), ideal).unwrap();
        let report = compare_prbs9_metrics_v2(&pair).unwrap();
        assert_eq!(report.contract_sha256(), PRBS9_CONTRACT_V2_SHA256);
        assert_eq!(report.compared_start(), PRBS9_THIRD_PERIOD_START_V2);
        assert_eq!(report.compared_samples(), PRBS9_THIRD_PERIOD_SAMPLES_V2);
        assert_eq!(report.waveform_nrmse(), 0.0);
        assert!(report.within_metric_limits());
        assert_eq!(
            report.evaluation_scope(),
            "caller_supplied_strict_grid_waveforms_only"
        );
        assert_eq!(report.external_reference_binding(), "not_evaluated");
        assert_eq!(report.external_profile_acceptance(), "not_evaluated");
        assert_eq!(report.reference_eye().height_volts(), 2.0);
        assert_eq!(report.reference_eye().width_seconds(), UI_SECONDS);
        assert_eq!(
            report.reference_tie().crossing_count(),
            report.candidate_tie().crossing_count()
        );
    }

    #[test]
    fn frozen_prbs9_sequence_matches_the_contract_digest() {
        let serialized = prbs9_bits()
            .into_iter()
            .map(|bit| if bit { b'1' } else { b'0' })
            .collect::<Vec<_>>();
        assert_eq!(
            format!("{:x}", Sha256::digest(serialized)),
            PRBS9_PERIOD_SHA256_V2
        );
    }

    #[test]
    fn eye_and_tie_limits_are_directional_and_fixed() {
        assert!(
            (relative_error(2.0, 2.02, "height").unwrap() - PRBS9_EYE_RELATIVE_ERROR_LIMIT_V2)
                .abs()
                < 1.0e-15
        );
        assert!(relative_error(2.0, 2.021, "height").unwrap() > PRBS9_EYE_RELATIVE_ERROR_LIMIT_V2);
        assert_eq!(
            rms_difference(&[0.0], &[PRBS9_TIE_ERROR_LIMIT_SECONDS_V2]).unwrap(),
            PRBS9_TIE_ERROR_LIMIT_SECONDS_V2
        );
    }

    #[test]
    fn only_the_frozen_third_period_contributes() {
        let reference = ideal_waveform();
        let mut candidate = reference.clone();
        candidate[0] = -1.0;
        let pair = Prbs9WaveformPairV2::try_new(reference.clone(), candidate).unwrap();
        assert_eq!(
            compare_prbs9_waveform_nrmse_v2(&pair)
                .unwrap()
                .waveform_nrmse(),
            0.0
        );
        let mut third_period_candidate = reference;
        third_period_candidate[PRBS9_THIRD_PERIOD_START_V2] = -1.0;
        let pair = Prbs9WaveformPairV2::try_new(ideal_waveform(), third_period_candidate).unwrap();
        assert!(
            compare_prbs9_waveform_nrmse_v2(&pair)
                .unwrap()
                .waveform_nrmse()
                > PRBS9_WAVEFORM_NRMSE_LIMIT_V2
        );
    }

    #[test]
    fn no_shift_gain_offset_or_polarity_is_hidden() {
        let reference = ideal_waveform();
        let mut shifted = reference.clone();
        shifted.rotate_right(1);
        for candidate in [
            shifted,
            reference.iter().map(|value| value + 0.1).collect(),
            reference.iter().map(|value| value * 1.1).collect(),
            reference.iter().map(|value| -value).collect(),
        ] {
            let pair = Prbs9WaveformPairV2::try_new(reference.clone(), candidate).unwrap();
            match compare_prbs9_waveform_nrmse_v2(&pair) {
                Ok(report) => assert!(!report.within_waveform_nrmse_limit()),
                Err(Prbs9WaveformMetricErrorV2::CrossingCount { .. }) => {}
                Err(error) => panic!("unexpected transform rejection: {error}"),
            }
        }
    }

    #[test]
    fn malformed_or_numerically_unsafe_inputs_fail_closed() {
        assert_eq!(
            Prbs9WaveformPairV2::try_new(vec![], ideal_waveform()),
            Err(Prbs9WaveformMetricErrorV2::LengthMismatch {
                waveform: "reference",
                expected: PRBS9_TOTAL_SAMPLES_V2,
                actual: 0
            })
        );
        let mut non_finite = ideal_waveform();
        non_finite[11] = f64::NAN;
        assert_eq!(
            Prbs9WaveformPairV2::try_new(ideal_waveform(), non_finite),
            Err(Prbs9WaveformMetricErrorV2::NonFiniteValue {
                waveform: "candidate",
                index: 11
            })
        );
        let pair = Prbs9WaveformPairV2::try_new(
            vec![0.0; PRBS9_TOTAL_SAMPLES_V2],
            vec![0.0; PRBS9_TOTAL_SAMPLES_V2],
        )
        .unwrap();
        assert_eq!(
            compare_prbs9_waveform_nrmse_v2(&pair),
            Err(Prbs9WaveformMetricErrorV2::ZeroReferenceNorm)
        );
        let pair = Prbs9WaveformPairV2::try_new(
            vec![f64::MAX; PRBS9_TOTAL_SAMPLES_V2],
            vec![-f64::MAX; PRBS9_TOTAL_SAMPLES_V2],
        )
        .unwrap();
        assert_eq!(
            compare_prbs9_waveform_nrmse_v2(&pair),
            Err(Prbs9WaveformMetricErrorV2::NumericOverflow {
                index: PRBS9_THIRD_PERIOD_START_V2
            })
        );
    }

    #[test]
    fn sampled_eye_uses_phase_sixteen_without_wraparound() {
        let bits = prbs9_bits();
        let mut values = ideal_waveform();
        for ui in COMPARED_START_UI..COMPARED_END_UI {
            if bits[ui % PERIOD_UI] {
                values[ui * SAMPLES_PER_UI + SAMPLES_PER_UI / 2] = -1.0;
            }
        }
        let eye = eye_metric(&values, &bits).unwrap();
        assert_eq!(eye.height_volts(), 2.0);
        assert_eq!(eye.width_seconds(), 0.0);
    }

    #[test]
    fn tie_is_raw_and_rejects_zero_plateaus_or_multiple_crossings() {
        let bits = prbs9_bits();
        let ideal = ideal_waveform();
        let raw = ties(&ideal, &bits, "reference").unwrap();
        assert!(!raw.is_empty());
        assert!((raw[0] + SAMPLE_INTERVAL_SECONDS / 2.0).abs() < 2.0e-24);
        assert!(
            (tie_metric(&raw).unwrap().raw_rms_seconds() - SAMPLE_INTERVAL_SECONDS / 2.0).abs()
                < 2.0e-24
        );

        let transition_ui = (COMPARED_START_UI..COMPARED_END_UI)
            .find(|ui| bits[(ui - 1) % PERIOD_UI] != bits[ui % PERIOD_UI])
            .unwrap();
        let center = transition_ui * SAMPLES_PER_UI;
        let mut plateau = ideal.clone();
        plateau[center - 1] = 0.0;
        plateau[center] = 0.0;
        assert_eq!(
            ties(&plateau, &bits, "candidate"),
            Err(Prbs9WaveformMetricErrorV2::ZeroPlateau {
                waveform: "candidate",
                transition_ui,
                index: center - 1
            })
        );

        let mut multiple = ideal;
        if !bits[(transition_ui - 1) % PERIOD_UI] {
            multiple[center - 2] = -1.0;
            multiple[center - 1] = 1.0;
            multiple[center] = -1.0;
            multiple[center + 1] = 1.0;
        } else {
            multiple[center - 2] = 1.0;
            multiple[center - 1] = -1.0;
            multiple[center] = 1.0;
            multiple[center + 1] = -1.0;
        }
        assert_eq!(
            ties(&multiple, &bits, "candidate"),
            Err(Prbs9WaveformMetricErrorV2::CrossingCount {
                waveform: "candidate",
                transition_ui,
                actual: 2
            })
        );
    }
}
