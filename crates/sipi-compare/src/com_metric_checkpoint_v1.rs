//! Strict same-checkpoint COM/ERL/TD-ILN comparison (P3C-03).
//!
//! This is an additive product comparison boundary.  It accepts three
//! already-extracted finite dB scalars and an exact caller-supplied checkpoint
//! identity.  It performs no waveform alignment, interpolation, aliasing, or
//! oracle lookup.  The 0.1 dB values are the owner's comparison policy only;
//! this module does not turn them into Agent-COM authority or release
//! acceptance.

use crate::{
    COM_METRIC_BUNDLE_POLICY_V1, ComMetricBundleV1, ComMetricTolerancesV1, MetricCompareErrorV1,
    MetricCompareReportV1, ToleranceV1, compare_com_metric_bundle_v1,
};

pub const COM_METRIC_CHECKPOINT_POLICY_V1: &str =
    "sipi.p3c-03.com-metric-checkpoint-v1.strict-same-checkpoint-no-alignment";
pub const COM_OWNER_ABSOLUTE_TOLERANCE_DB_V1: f64 = 0.1;
pub const COM_CHECKPOINT_ALIGNMENT_POLICY_V1: &str = "strict_same_checkpoint_no_alignment";

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ComMetricCheckpointCompareErrorV1 {
    InvalidCheckpoint,
    CheckpointMismatch,
    NonOwnerTolerance,
    Metric(MetricCompareErrorV1),
}

impl From<MetricCompareErrorV1> for ComMetricCheckpointCompareErrorV1 {
    fn from(error: MetricCompareErrorV1) -> Self {
        Self::Metric(error)
    }
}

/// Product report for one same-checkpoint comparison.  `passed` is a
/// comparison-policy result, not an external oracle or acceptance result.
#[derive(Clone, Debug, PartialEq)]
pub struct ComMetricCheckpointCompareReportV1 {
    checkpoint: String,
    metrics: MetricCompareReportV1,
}

impl ComMetricCheckpointCompareReportV1 {
    pub fn checkpoint(&self) -> &str {
        &self.checkpoint
    }

    pub fn metrics(&self) -> &MetricCompareReportV1 {
        &self.metrics
    }

    pub fn passed(&self) -> bool {
        self.metrics.passed()
    }

    pub const fn alignment_policy(&self) -> &'static str {
        COM_CHECKPOINT_ALIGNMENT_POLICY_V1
    }

    pub const fn acceptance_status(&self) -> &'static str {
        "owner_policy_comparison_only_not_acceptance"
    }

    pub const fn external_oracle_status(&self) -> &'static str {
        "not_selected"
    }
}

/// Compare the exact COM/ERL/TD-ILN scalar bundle at one identical
/// checkpoint.  All three tolerances must be exactly the owner-selected
/// absolute 0.1 dB with zero relative tolerance.
pub fn compare_com_metric_checkpoint_v1(
    reference_checkpoint: &str,
    candidate_checkpoint: &str,
    reference: ComMetricBundleV1,
    candidate: ComMetricBundleV1,
    tolerances: ComMetricTolerancesV1,
) -> Result<ComMetricCheckpointCompareReportV1, ComMetricCheckpointCompareErrorV1> {
    if !valid_checkpoint(reference_checkpoint) || !valid_checkpoint(candidate_checkpoint) {
        return Err(ComMetricCheckpointCompareErrorV1::InvalidCheckpoint);
    }
    if reference_checkpoint != candidate_checkpoint {
        return Err(ComMetricCheckpointCompareErrorV1::CheckpointMismatch);
    }
    let expected = ToleranceV1::try_new(COM_OWNER_ABSOLUTE_TOLERANCE_DB_V1, 0.0)
        .map_err(|_| ComMetricCheckpointCompareErrorV1::NonOwnerTolerance)?;
    if tolerances.com_db() != expected
        || tolerances.erl_db() != expected
        || tolerances.td_iln_db() != expected
    {
        return Err(ComMetricCheckpointCompareErrorV1::NonOwnerTolerance);
    }
    let metrics = compare_com_metric_bundle_v1(reference, candidate, tolerances)?;
    Ok(ComMetricCheckpointCompareReportV1 {
        checkpoint: reference_checkpoint.to_owned(),
        metrics,
    })
}

fn valid_checkpoint(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 256
        && value.is_ascii()
        && !value.chars().any(char::is_whitespace)
}

const _: &str = COM_METRIC_BUNDLE_POLICY_V1;

#[cfg(test)]
mod tests {
    use super::*;

    fn bundle(com: f64, erl: f64, td_iln: f64) -> ComMetricBundleV1 {
        ComMetricBundleV1::try_new(com, erl, td_iln).expect("bundle")
    }

    fn owner_tolerances() -> ComMetricTolerancesV1 {
        let tolerance = ToleranceV1::try_new(COM_OWNER_ABSOLUTE_TOLERANCE_DB_V1, 0.0).unwrap();
        ComMetricTolerancesV1::new(tolerance, tolerance, tolerance)
    }

    #[test]
    fn exact_same_checkpoint_passes_without_alignment() {
        let report = compare_com_metric_checkpoint_v1(
            "case-0/checkpoint-17",
            "case-0/checkpoint-17",
            bundle(3.0, 8.0, 12.0),
            bundle(3.05, 7.95, 12.0),
            owner_tolerances(),
        )
        .unwrap();
        assert!(report.passed());
        assert_eq!(
            report.alignment_policy(),
            COM_CHECKPOINT_ALIGNMENT_POLICY_V1
        );
        assert_eq!(
            report.acceptance_status(),
            "owner_policy_comparison_only_not_acceptance"
        );
    }

    #[test]
    fn checkpoint_mismatch_is_rejected_before_metric_compare() {
        assert_eq!(
            compare_com_metric_checkpoint_v1(
                "case-0/checkpoint-17",
                "case-0/checkpoint-18",
                bundle(3.0, 8.0, 12.0),
                bundle(3.0, 8.0, 12.0),
                owner_tolerances(),
            ),
            Err(ComMetricCheckpointCompareErrorV1::CheckpointMismatch)
        );
    }

    #[test]
    fn non_owner_tolerance_is_rejected() {
        let zero = ToleranceV1::try_new(0.0, 0.0).unwrap();
        assert_eq!(
            compare_com_metric_checkpoint_v1(
                "checkpoint",
                "checkpoint",
                bundle(1.0, 2.0, 3.0),
                bundle(1.0, 2.0, 3.0),
                ComMetricTolerancesV1::new(zero, zero, zero),
            ),
            Err(ComMetricCheckpointCompareErrorV1::NonOwnerTolerance)
        );
    }

    #[test]
    fn td_iln_remains_an_explicit_scalar_not_icn_alias() {
        let bundle = bundle(1.0, 2.0, 3.0);
        assert_eq!(bundle.td_iln_db(), 3.0);
        assert!(!COM_METRIC_CHECKPOINT_POLICY_V1.contains("icn"));
    }

    #[test]
    fn malformed_checkpoint_is_rejected() {
        assert!(matches!(
            compare_com_metric_checkpoint_v1(
                "",
                "",
                bundle(1.0, 2.0, 3.0),
                bundle(1.0, 2.0, 3.0),
                owner_tolerances(),
            ),
            Err(ComMetricCheckpointCompareErrorV1::InvalidCheckpoint)
        ));
    }
}
