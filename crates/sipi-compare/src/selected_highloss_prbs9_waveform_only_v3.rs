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
pub const SELECTED_HIGHLOSS_PRBS9_PERIOD_SAMPLES_V3: usize = 16_352;
pub const SELECTED_HIGHLOSS_PRBS9_PERIOD_COUNT_V3: usize = 3;
pub const SELECTED_HIGHLOSS_PRBS9_UI_SAMPLES_V3: usize = 32;
pub const SELECTED_HIGHLOSS_PRBS9_UIS_PER_PERIOD_V3: usize = 511;
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

/// A fixed strict-index residual summary. This is diagnostic-only and has no
/// acceptance fields or transform controls.
#[derive(Clone, Debug, PartialEq)]
pub struct SelectedHighlossPrbs9ResidualPeriodV1 {
    reference_rms: f64,
    candidate_rms: f64,
    residual_rms: f64,
    residual_mean: f64,
    residual_nrmse: f64,
    residual_digest: String,
    maximum_absolute_residual: f64,
    maximum_absolute_residual_offset: usize,
}

impl SelectedHighlossPrbs9ResidualPeriodV1 {
    pub fn reference_rms(&self) -> f64 {
        self.reference_rms
    }
    pub fn candidate_rms(&self) -> f64 {
        self.candidate_rms
    }
    pub fn residual_rms(&self) -> f64 {
        self.residual_rms
    }
    pub fn residual_mean(&self) -> f64 {
        self.residual_mean
    }
    pub fn residual_nrmse(&self) -> f64 {
        self.residual_nrmse
    }
    pub fn residual_digest(&self) -> &str {
        &self.residual_digest
    }
    pub fn maximum_absolute_residual(&self) -> f64 {
        self.maximum_absolute_residual
    }
    pub fn maximum_absolute_residual_offset(&self) -> usize {
        self.maximum_absolute_residual_offset
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct SelectedHighlossPrbs9ResidualDiagnosticV1 {
    periods: [SelectedHighlossPrbs9ResidualPeriodV1; SELECTED_HIGHLOSS_PRBS9_PERIOD_COUNT_V3],
    third_period_ui_energy_digest: String,
    third_period_maximum_energy_ui_offset: usize,
}

impl SelectedHighlossPrbs9ResidualDiagnosticV1 {
    pub fn periods(
        &self,
    ) -> &[SelectedHighlossPrbs9ResidualPeriodV1; SELECTED_HIGHLOSS_PRBS9_PERIOD_COUNT_V3] {
        &self.periods
    }
    pub fn third_period_ui_energy_digest(&self) -> &str {
        &self.third_period_ui_energy_digest
    }
    pub fn third_period_maximum_energy_ui_offset(&self) -> usize {
        self.third_period_maximum_energy_ui_offset
    }
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
    fn rms(&self, count: usize) -> Option<f64> {
        if count == 0 {
            return None;
        }
        if self.is_zero() {
            return Some(0.0);
        }
        let value = self.scale * (self.sum / count as f64).sqrt();
        value.is_finite().then_some(value)
    }
    fn energy(&self) -> Option<f64> {
        if self.is_zero() {
            return Some(0.0);
        }
        let value = self.scale * self.scale * self.sum;
        value.is_finite().then_some(value)
    }
}

/// Evaluates only strict third-period raw waveform NRMSE, with no transform.
pub fn compare_selected_highloss_prbs9_waveform_only_v3(
    pair: &SelectedHighlossPrbs9WaveformPairV3,
) -> Result<SelectedHighlossPrbs9WaveformOnlyReportV3, SelectedHighlossPrbs9WaveformOnlyErrorV3> {
    let waveform_nrmse = nrmse_for_range(
        pair,
        SELECTED_HIGHLOSS_PRBS9_THIRD_PERIOD_START_V3,
        SELECTED_HIGHLOSS_PRBS9_THIRD_PERIOD_SAMPLES_V3,
    )?;
    Ok(SelectedHighlossPrbs9WaveformOnlyReportV3 {
        reference_digest: pair.reference_digest(),
        candidate_digest: pair.candidate_digest(),
        waveform_nrmse,
        within_waveform_nrmse_limit: waveform_nrmse
            <= SELECTED_HIGHLOSS_PRBS9_WAVEFORM_NRMSE_LIMIT_V3,
    })
}

/// Diagnoses fixed period partitions without changing the v3 comparison.
pub fn diagnose_selected_highloss_prbs9_residual_v1(
    pair: &SelectedHighlossPrbs9WaveformPairV3,
) -> Result<SelectedHighlossPrbs9ResidualDiagnosticV1, SelectedHighlossPrbs9WaveformOnlyErrorV3> {
    let periods = [
        residual_period(pair, 0)?,
        residual_period(pair, SELECTED_HIGHLOSS_PRBS9_PERIOD_SAMPLES_V3)?,
        residual_period(pair, SELECTED_HIGHLOSS_PRBS9_PERIOD_SAMPLES_V3 * 2)?,
    ];
    let mut energies = Vec::with_capacity(SELECTED_HIGHLOSS_PRBS9_UIS_PER_PERIOD_V3);
    let third_start = SELECTED_HIGHLOSS_PRBS9_THIRD_PERIOD_START_V3;
    for ui_offset in 0..SELECTED_HIGHLOSS_PRBS9_UIS_PER_PERIOD_V3 {
        let start = third_start + ui_offset * SELECTED_HIGHLOSS_PRBS9_UI_SAMPLES_V3;
        let mut sum = ScaledSumSquares::default();
        for index in start..start + SELECTED_HIGHLOSS_PRBS9_UI_SAMPLES_V3 {
            let difference = pair.candidate()[index] - pair.reference()[index];
            if !difference.is_finite() {
                return Err(SelectedHighlossPrbs9WaveformOnlyErrorV3::NumericOverflow { index });
            }
            sum.add(difference);
        }
        energies.push(
            sum.energy()
                .ok_or(SelectedHighlossPrbs9WaveformOnlyErrorV3::NumericOverflow {
                    index: start,
                })?,
        );
    }
    let (maximum_energy, maximum_energy_ui_offset) = energies.iter().copied().enumerate().fold(
        (f64::NEG_INFINITY, 0_usize),
        |current, (offset, energy)| {
            if energy > current.0 {
                (energy, offset)
            } else {
                current
            }
        },
    );
    if !maximum_energy.is_finite() {
        return Err(SelectedHighlossPrbs9WaveformOnlyErrorV3::NumericOverflow {
            index: third_start,
        });
    }
    let mut digest = Sha256::new();
    digest.update(b"sipi.compare.selected-highloss-prbs9-residual-ui-energy.v1\0");
    digest.update((energies.len() as u64).to_be_bytes());
    for energy in energies {
        digest.update(energy.to_bits().to_be_bytes());
    }
    Ok(SelectedHighlossPrbs9ResidualDiagnosticV1 {
        periods,
        third_period_ui_energy_digest: format!("{:x}", digest.finalize()),
        third_period_maximum_energy_ui_offset: maximum_energy_ui_offset,
    })
}

fn nrmse_for_range(
    pair: &SelectedHighlossPrbs9WaveformPairV3,
    start: usize,
    count: usize,
) -> Result<f64, SelectedHighlossPrbs9WaveformOnlyErrorV3> {
    let mut reference_sum = ScaledSumSquares::default();
    let mut error_sum = ScaledSumSquares::default();
    for index in start..start + count {
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
    let waveform_nrmse = error_sum
        .ratio_sqrt(&reference_sum)
        .ok_or(SelectedHighlossPrbs9WaveformOnlyErrorV3::NumericOverflow { index: start })?;
    Ok(waveform_nrmse)
}

fn residual_period(
    pair: &SelectedHighlossPrbs9WaveformPairV3,
    start: usize,
) -> Result<SelectedHighlossPrbs9ResidualPeriodV1, SelectedHighlossPrbs9WaveformOnlyErrorV3> {
    let mut reference_sum = ScaledSumSquares::default();
    let mut candidate_sum = ScaledSumSquares::default();
    let mut residual_sum = ScaledSumSquares::default();
    let mut residual_mean = 0.0;
    let mut maximum_absolute_residual = 0.0;
    let mut maximum_absolute_residual_offset = 0;
    let mut digest = Sha256::new();
    digest.update(b"sipi.compare.selected-highloss-prbs9-residual-period.v1\0");
    digest.update((SELECTED_HIGHLOSS_PRBS9_PERIOD_SAMPLES_V3 as u64).to_be_bytes());
    for offset in 0..SELECTED_HIGHLOSS_PRBS9_PERIOD_SAMPLES_V3 {
        let index = start + offset;
        let difference = pair.candidate()[index] - pair.reference()[index];
        if !difference.is_finite() {
            return Err(SelectedHighlossPrbs9WaveformOnlyErrorV3::NumericOverflow { index });
        }
        reference_sum.add(pair.reference()[index]);
        candidate_sum.add(pair.candidate()[index]);
        residual_sum.add(difference);
        let next_mean = residual_mean + (difference - residual_mean) / (offset + 1) as f64;
        if !next_mean.is_finite() {
            return Err(SelectedHighlossPrbs9WaveformOnlyErrorV3::NumericOverflow { index });
        }
        residual_mean = next_mean;
        let absolute = difference.abs();
        if absolute > maximum_absolute_residual {
            maximum_absolute_residual = absolute;
            maximum_absolute_residual_offset = offset;
        }
        digest.update(difference.to_bits().to_be_bytes());
    }
    let reference_rms = reference_sum
        .rms(SELECTED_HIGHLOSS_PRBS9_PERIOD_SAMPLES_V3)
        .ok_or(SelectedHighlossPrbs9WaveformOnlyErrorV3::NumericOverflow { index: start })?;
    let candidate_rms = candidate_sum
        .rms(SELECTED_HIGHLOSS_PRBS9_PERIOD_SAMPLES_V3)
        .ok_or(SelectedHighlossPrbs9WaveformOnlyErrorV3::NumericOverflow { index: start })?;
    let residual_rms = residual_sum
        .rms(SELECTED_HIGHLOSS_PRBS9_PERIOD_SAMPLES_V3)
        .ok_or(SelectedHighlossPrbs9WaveformOnlyErrorV3::NumericOverflow { index: start })?;
    let residual_nrmse = residual_sum
        .ratio_sqrt(&reference_sum)
        .ok_or(SelectedHighlossPrbs9WaveformOnlyErrorV3::ZeroReferenceNorm)?;
    Ok(SelectedHighlossPrbs9ResidualPeriodV1 {
        reference_rms,
        candidate_rms,
        residual_rms,
        residual_mean,
        residual_nrmse,
        residual_digest: format!("{:x}", digest.finalize()),
        maximum_absolute_residual,
        maximum_absolute_residual_offset,
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
        Prbs9WaveformMetricErrorV2, Prbs9WaveformPairV2, compare_prbs9_metrics_v2,
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

    #[test]
    fn residual_diagnostic_partitions_all_periods_without_changing_v3_nrmse() {
        let reference = vec![2.0; SELECTED_HIGHLOSS_PRBS9_TOTAL_SAMPLES_V3];
        let mut candidate = reference.clone();
        candidate[0] = 3.0;
        candidate[SELECTED_HIGHLOSS_PRBS9_PERIOD_SAMPLES_V3] = 0.0;
        candidate[SELECTED_HIGHLOSS_PRBS9_THIRD_PERIOD_START_V3 + 7] = 1.0;
        candidate[SELECTED_HIGHLOSS_PRBS9_THIRD_PERIOD_START_V3 + 9] = 1.0;
        let pair = SelectedHighlossPrbs9WaveformPairV3::try_new(reference, candidate).unwrap();
        let diagnostic = diagnose_selected_highloss_prbs9_residual_v1(&pair).unwrap();
        assert_eq!(
            diagnostic.periods().len(),
            SELECTED_HIGHLOSS_PRBS9_PERIOD_COUNT_V3
        );
        assert_eq!(
            diagnostic.periods()[0].maximum_absolute_residual_offset(),
            0
        );
        assert_eq!(
            diagnostic.periods()[1].maximum_absolute_residual_offset(),
            0
        );
        assert_eq!(
            diagnostic.periods()[2].maximum_absolute_residual_offset(),
            7
        );
        assert_eq!(diagnostic.third_period_maximum_energy_ui_offset(), 0);
        assert_eq!(
            diagnostic.periods()[2].residual_nrmse().to_bits(),
            compare_selected_highloss_prbs9_waveform_only_v3(&pair)
                .unwrap()
                .waveform_nrmse()
                .to_bits()
        );
        assert_ne!(
            diagnostic.periods()[0].residual_digest(),
            diagnostic.periods()[1].residual_digest()
        );
    }

    #[test]
    fn residual_diagnostic_rejects_zero_period_reference_energy() {
        let mut reference = vec![1.0; SELECTED_HIGHLOSS_PRBS9_TOTAL_SAMPLES_V3];
        reference[..SELECTED_HIGHLOSS_PRBS9_PERIOD_SAMPLES_V3].fill(0.0);
        let candidate = reference.clone();
        let pair = SelectedHighlossPrbs9WaveformPairV3::try_new(reference, candidate).unwrap();
        assert_eq!(
            diagnose_selected_highloss_prbs9_residual_v1(&pair),
            Err(SelectedHighlossPrbs9WaveformOnlyErrorV3::ZeroReferenceNorm)
        );
    }

    #[test]
    fn residual_diagnostic_is_directional_and_uses_lowest_index_ties() {
        let reference = vec![2.0; SELECTED_HIGHLOSS_PRBS9_TOTAL_SAMPLES_V3];
        let mut candidate = reference.clone();
        candidate[3] = 3.0;
        candidate[11] = 3.0;
        let forward = diagnose_selected_highloss_prbs9_residual_v1(
            &SelectedHighlossPrbs9WaveformPairV3::try_new(reference.clone(), candidate.clone())
                .unwrap(),
        )
        .unwrap();
        let reverse = diagnose_selected_highloss_prbs9_residual_v1(
            &SelectedHighlossPrbs9WaveformPairV3::try_new(candidate, reference).unwrap(),
        )
        .unwrap();
        assert_eq!(forward.periods()[0].maximum_absolute_residual_offset(), 3);
        assert_eq!(
            forward.periods()[0].residual_mean().to_bits(),
            (-reverse.periods()[0].residual_mean()).to_bits()
        );
        assert_ne!(
            forward.periods()[0].residual_digest(),
            reverse.periods()[0].residual_digest()
        );
    }
}
