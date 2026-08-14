//! Fixed selected-highloss PRBS9 waveform-only comparison profile.
//!
//! This is deliberately separate from the v2 waveform/eye/TIE profile. It
//! compares the exact raw post-channel selected profile only and never derives
//! an eye or crossing metric.

use std::{error::Error, fmt};

use sha2::{Digest, Sha256};

pub const SELECTED_HIGHLOSS_PRBS9_WAVEFORM_ONLY_V3_SCHEMA: &str =
    "sipi.compare.selected-highloss-prbs9-waveform-only.v3";
pub const SELECTED_HIGHLOSS_PRBS9_WAVEFORM_ONLY_CONTRACT_SHA256_V3: &str =
    "db0d9a663b311105be329d79060f05a5179f40fd7eccf448faf85d45b73da64a";
pub const SELECTED_HIGHLOSS_PRBS9_TOTAL_SAMPLES_V3: usize = 49_056;
pub const SELECTED_HIGHLOSS_PRBS9_THIRD_PERIOD_START_V3: usize = 32_704;
pub const SELECTED_HIGHLOSS_PRBS9_THIRD_PERIOD_SAMPLES_V3: usize = 16_352;
pub const SELECTED_HIGHLOSS_PRBS9_WAVEFORM_NRMSE_LIMIT_V3: f64 = 0.01;

#[derive(Clone, Debug, PartialEq)]
pub struct SelectedHighlossPrbs9WaveformPairV3 {
    reference: Vec<f64>,
    candidate: Vec<f64>,
}

impl SelectedHighlossPrbs9WaveformPairV3 {
    pub fn try_new(
        reference: Vec<f64>,
        candidate: Vec<f64>,
    ) -> Result<Self, SelectedHighlossPrbs9WaveformOnlyErrorV3> {
        validate("reference", &reference)?;
        validate("candidate", &candidate)?;
        Ok(Self {
            reference,
            candidate,
        })
    }

    pub fn reference_digest(&self) -> String {
        digest(b"reference", &self.reference)
    }
    pub fn candidate_digest(&self) -> String {
        digest(b"candidate", &self.candidate)
    }
    fn reference(&self) -> &[f64] {
        &self.reference
    }
    fn candidate(&self) -> &[f64] {
        &self.candidate
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct SelectedHighlossPrbs9WaveformOnlyReportV3 {
    reference_digest: String,
    candidate_digest: String,
    waveform_nrmse: f64,
    within_waveform_nrmse_limit: bool,
}

impl SelectedHighlossPrbs9WaveformOnlyReportV3 {
    pub fn schema(&self) -> &'static str {
        SELECTED_HIGHLOSS_PRBS9_WAVEFORM_ONLY_V3_SCHEMA
    }
    pub fn contract_sha256(&self) -> &'static str {
        SELECTED_HIGHLOSS_PRBS9_WAVEFORM_ONLY_CONTRACT_SHA256_V3
    }
    pub fn reference_digest(&self) -> &str {
        &self.reference_digest
    }
    pub fn candidate_digest(&self) -> &str {
        &self.candidate_digest
    }
    pub fn compared_start(&self) -> usize {
        SELECTED_HIGHLOSS_PRBS9_THIRD_PERIOD_START_V3
    }
    pub fn compared_samples(&self) -> usize {
        SELECTED_HIGHLOSS_PRBS9_THIRD_PERIOD_SAMPLES_V3
    }
    pub fn waveform_nrmse(&self) -> f64 {
        self.waveform_nrmse
    }
    pub fn waveform_nrmse_limit(&self) -> f64 {
        SELECTED_HIGHLOSS_PRBS9_WAVEFORM_NRMSE_LIMIT_V3
    }
    pub fn within_waveform_nrmse_limit(&self) -> bool {
        self.within_waveform_nrmse_limit
    }
    pub fn within_selected_waveform_only_profile(&self) -> bool {
        self.within_waveform_nrmse_limit
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum SelectedHighlossPrbs9WaveformOnlyErrorV3 {
    LengthMismatch {
        waveform: &'static str,
        expected: usize,
        actual: usize,
    },
    NonFiniteValue {
        waveform: &'static str,
        index: usize,
    },
    ZeroReferenceNorm,
    NumericOverflow {
        index: usize,
    },
}

impl fmt::Display for SelectedHighlossPrbs9WaveformOnlyErrorV3 {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            formatter,
            "selected highloss waveform-only comparison rejected: {self:?}"
        )
    }
}

impl Error for SelectedHighlossPrbs9WaveformOnlyErrorV3 {}

#[derive(Default)]
struct ScaledSumSquares {
    scale: f64,
    sum: f64,
}

impl ScaledSumSquares {
    fn add(&mut self, value: f64) {
        let magnitude = value.abs();
        if magnitude == 0.0 {
            return;
        }
        if self.scale < magnitude {
            let ratio = self.scale / magnitude;
            self.sum = 1.0 + self.sum * ratio * ratio;
            self.scale = magnitude;
        } else {
            let ratio = magnitude / self.scale;
            self.sum += ratio * ratio;
        }
    }
    fn is_zero(&self) -> bool {
        self.scale == 0.0
    }
    fn ratio_sqrt(&self, divisor: &Self) -> Option<f64> {
        if divisor.is_zero() {
            return None;
        }
        if self.is_zero() {
            return Some(0.0);
        }
        ((self.scale / divisor.scale) * (self.sum / divisor.sum).sqrt())
            .is_finite()
            .then_some((self.scale / divisor.scale) * (self.sum / divisor.sum).sqrt())
    }
}

/// Evaluates only strict third-period raw waveform NRMSE, with no transform.
pub fn compare_selected_highloss_prbs9_waveform_only_v3(
    pair: &SelectedHighlossPrbs9WaveformPairV3,
) -> Result<SelectedHighlossPrbs9WaveformOnlyReportV3, SelectedHighlossPrbs9WaveformOnlyErrorV3> {
    let range = SELECTED_HIGHLOSS_PRBS9_THIRD_PERIOD_START_V3
        ..SELECTED_HIGHLOSS_PRBS9_THIRD_PERIOD_START_V3
            + SELECTED_HIGHLOSS_PRBS9_THIRD_PERIOD_SAMPLES_V3;
    let mut reference_sum = ScaledSumSquares::default();
    let mut error_sum = ScaledSumSquares::default();
    for index in range {
        let difference = pair.candidate()[index] - pair.reference()[index];
        if !difference.is_finite() {
            return Err(SelectedHighlossPrbs9WaveformOnlyErrorV3::NumericOverflow { index });
        }
        reference_sum.add(pair.reference()[index]);
        error_sum.add(difference);
    }
    if reference_sum.is_zero() {
        return Err(SelectedHighlossPrbs9WaveformOnlyErrorV3::ZeroReferenceNorm);
    }
    let waveform_nrmse = error_sum.ratio_sqrt(&reference_sum).ok_or(
        SelectedHighlossPrbs9WaveformOnlyErrorV3::NumericOverflow {
            index: SELECTED_HIGHLOSS_PRBS9_THIRD_PERIOD_START_V3,
        },
    )?;
    Ok(SelectedHighlossPrbs9WaveformOnlyReportV3 {
        reference_digest: pair.reference_digest(),
        candidate_digest: pair.candidate_digest(),
        waveform_nrmse,
        within_waveform_nrmse_limit: waveform_nrmse
            <= SELECTED_HIGHLOSS_PRBS9_WAVEFORM_NRMSE_LIMIT_V3,
    })
}

fn validate(
    waveform: &'static str,
    values: &[f64],
) -> Result<(), SelectedHighlossPrbs9WaveformOnlyErrorV3> {
    if values.len() != SELECTED_HIGHLOSS_PRBS9_TOTAL_SAMPLES_V3 {
        return Err(SelectedHighlossPrbs9WaveformOnlyErrorV3::LengthMismatch {
            waveform,
            expected: SELECTED_HIGHLOSS_PRBS9_TOTAL_SAMPLES_V3,
            actual: values.len(),
        });
    }
    for (index, value) in values.iter().enumerate() {
        if !value.is_finite() {
            return Err(SelectedHighlossPrbs9WaveformOnlyErrorV3::NonFiniteValue {
                waveform,
                index,
            });
        }
    }
    Ok(())
}

fn digest(role: &[u8], values: &[f64]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(role);
    hasher.update((values.len() as u64).to_be_bytes());
    for value in values {
        hasher.update(value.to_bits().to_be_bytes());
    }
    format!("{:x}", hasher.finalize())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::prbs9_waveform_v2::{
        compare_prbs9_metrics_v2, Prbs9WaveformMetricErrorV2, Prbs9WaveformPairV2,
    };

    fn closed_eye_waveform() -> Vec<f64> {
        vec![0.1; SELECTED_HIGHLOSS_PRBS9_TOTAL_SAMPLES_V3]
    }

    #[test]
    fn closed_eye_identical_pair_is_waveform_only_success_but_v2_rejects() {
        let values = closed_eye_waveform();
        let pair =
            SelectedHighlossPrbs9WaveformPairV3::try_new(values.clone(), values.clone()).unwrap();
        let report = compare_selected_highloss_prbs9_waveform_only_v3(&pair).unwrap();
        assert_eq!(report.waveform_nrmse(), 0.0);
        assert!(report.within_selected_waveform_only_profile());
        assert!(matches!(
            compare_prbs9_metrics_v2(
                &Prbs9WaveformPairV2::try_new(values.clone(), values).unwrap()
            ),
            Err(Prbs9WaveformMetricErrorV2::ZeroReferenceEyeMetric {
                metric: "height" | "width"
            })
        ));
    }

    #[test]
    fn exact_one_percent_is_inclusive_and_shift_is_not_hidden() {
        let reference = vec![100.0; SELECTED_HIGHLOSS_PRBS9_TOTAL_SAMPLES_V3];
        let mut candidate = reference.clone();
        for value in &mut candidate[SELECTED_HIGHLOSS_PRBS9_THIRD_PERIOD_START_V3..] {
            *value = 101.0;
        }
        let report = compare_selected_highloss_prbs9_waveform_only_v3(
            &SelectedHighlossPrbs9WaveformPairV3::try_new(reference.clone(), candidate).unwrap(),
        )
        .unwrap();
        assert!(report.within_waveform_nrmse_limit());
        let strict_reference: Vec<f64> = (0..SELECTED_HIGHLOSS_PRBS9_TOTAL_SAMPLES_V3)
            .map(|index| if index % 2 == 0 { -1.0 } else { 1.0 })
            .collect();
        let mut shifted = strict_reference.clone();
        shifted.rotate_right(1);
        assert!(
            compare_selected_highloss_prbs9_waveform_only_v3(
                &SelectedHighlossPrbs9WaveformPairV3::try_new(strict_reference, shifted).unwrap(),
            )
            .unwrap()
            .waveform_nrmse()
                > 0.01
        );
    }

    #[test]
    fn invalid_inputs_reject() {
        let values = vec![1.0; SELECTED_HIGHLOSS_PRBS9_TOTAL_SAMPLES_V3];
        assert!(matches!(
            SelectedHighlossPrbs9WaveformPairV3::try_new(values[..10].to_vec(), values.clone()),
            Err(SelectedHighlossPrbs9WaveformOnlyErrorV3::LengthMismatch { .. })
        ));
        let mut nonfinite = values.clone();
        nonfinite[0] = f64::NAN;
        assert!(matches!(
            SelectedHighlossPrbs9WaveformPairV3::try_new(nonfinite, values.clone()),
            Err(SelectedHighlossPrbs9WaveformOnlyErrorV3::NonFiniteValue { .. })
        ));
        assert!(matches!(
            compare_selected_highloss_prbs9_waveform_only_v3(
                &SelectedHighlossPrbs9WaveformPairV3::try_new(
                    vec![0.0; SELECTED_HIGHLOSS_PRBS9_TOTAL_SAMPLES_V3],
                    values
                )
                .unwrap()
            ),
            Err(SelectedHighlossPrbs9WaveformOnlyErrorV3::ZeroReferenceNorm)
        ));
    }
}
