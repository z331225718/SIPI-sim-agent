//! Fixed COM/ERL/TD-ILN scalar bundle for the required COM compare surface.
//!
//! This module fixes only metric identity and dB units. References, candidates,
//! and all three tolerances remain explicit caller inputs; no oracle, alignment,
//! alias conversion, or acceptance tolerance is selected here.

use std::collections::BTreeMap;

use crate::{
    MetricCompareErrorV1, MetricCompareReportV1, MetricProfileV1, MetricSpecV1, ToleranceV1,
    UnitTagV1, compare_metric_profile_v1,
};

pub const COM_METRIC_BUNDLE_POLICY_V1: &str =
    "sipi.p3c-03.com-metric-bundle.v1.com-erl-td-iln-explicit-tolerances";

const METRIC_NAMES: [&str; 3] = ["com_db", "erl_db", "td_iln_db"];

/// A complete, finite COM/ERL/TD-ILN scalar bundle in dB.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct ComMetricBundleV1 {
    com_db: f64,
    erl_db: f64,
    td_iln_db: f64,
}

impl ComMetricBundleV1 {
    pub fn try_new(com_db: f64, erl_db: f64, td_iln_db: f64) -> Result<Self, MetricCompareErrorV1> {
        if ![com_db, erl_db, td_iln_db].into_iter().all(f64::is_finite) {
            return Err(MetricCompareErrorV1::NonFinite);
        }
        Ok(Self {
            com_db,
            erl_db,
            td_iln_db,
        })
    }

    pub fn com_db(self) -> f64 {
        self.com_db
    }

    pub fn erl_db(self) -> f64 {
        self.erl_db
    }

    pub fn td_iln_db(self) -> f64 {
        self.td_iln_db
    }

    fn values(self) -> [f64; 3] {
        [self.com_db, self.erl_db, self.td_iln_db]
    }
}

/// Explicit per-metric tolerances. There is deliberately no default.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct ComMetricTolerancesV1 {
    com_db: ToleranceV1,
    erl_db: ToleranceV1,
    td_iln_db: ToleranceV1,
}

impl ComMetricTolerancesV1 {
    pub fn new(com_db: ToleranceV1, erl_db: ToleranceV1, td_iln_db: ToleranceV1) -> Self {
        Self {
            com_db,
            erl_db,
            td_iln_db,
        }
    }

    pub fn com_db(self) -> ToleranceV1 {
        self.com_db
    }

    pub fn erl_db(self) -> ToleranceV1 {
        self.erl_db
    }

    pub fn td_iln_db(self) -> ToleranceV1 {
        self.td_iln_db
    }

    fn values(self) -> [ToleranceV1; 3] {
        [self.com_db, self.erl_db, self.td_iln_db]
    }
}

/// Compares two complete bundles without selecting tolerance or alignment policy.
pub fn compare_com_metric_bundle_v1(
    reference: ComMetricBundleV1,
    candidate: ComMetricBundleV1,
    tolerances: ComMetricTolerancesV1,
) -> Result<MetricCompareReportV1, MetricCompareErrorV1> {
    let references = reference.values();
    let candidates = candidate.values();
    let tolerances = tolerances.values();

    for index in 0..METRIC_NAMES.len() {
        let error = (candidates[index] - references[index]).abs();
        let allowed =
            tolerances[index].absolute() + tolerances[index].relative() * references[index].abs();
        if !error.is_finite() || !allowed.is_finite() {
            return Err(MetricCompareErrorV1::NonFinite);
        }
    }

    let unit = UnitTagV1::try_new("db").expect("static unit");
    let specs = METRIC_NAMES
        .into_iter()
        .zip(references)
        .zip(tolerances)
        .map(|((name, value), tolerance)| {
            MetricSpecV1::new(name, unit.clone(), value, tolerance).expect("validated fixed spec")
        })
        .collect();
    let profile = MetricProfileV1::compile(specs).expect("fixed unique non-empty profile");
    let candidate_map = METRIC_NAMES
        .into_iter()
        .zip(candidates)
        .map(|(name, value)| (name.to_string(), value))
        .collect::<BTreeMap<_, _>>();
    compare_metric_profile_v1(&profile, &candidate_map)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn tolerance(absolute: f64, relative: f64) -> ToleranceV1 {
        ToleranceV1::try_new(absolute, relative).unwrap()
    }

    fn tolerances(value: ToleranceV1) -> ComMetricTolerancesV1 {
        ComMetricTolerancesV1::new(value, value, value)
    }

    #[test]
    fn fixes_exact_com_erl_td_iln_surface_without_icn() {
        assert_eq!(METRIC_NAMES, ["com_db", "erl_db", "td_iln_db"]);
        assert!(!COM_METRIC_BUNDLE_POLICY_V1.contains("icn"));

        let values = ComMetricBundleV1::try_new(3.0, 8.0, 12.0).unwrap();
        assert_eq!(
            (values.com_db(), values.erl_db(), values.td_iln_db()),
            (3.0, 8.0, 12.0)
        );
    }

    #[test]
    fn exact_bundle_passes_with_explicit_zero_tolerances() {
        let bundle = ComMetricBundleV1::try_new(3.0, 8.0, 12.0).unwrap();
        let report =
            compare_com_metric_bundle_v1(bundle, bundle, tolerances(tolerance(0.0, 0.0))).unwrap();
        assert!(report.passed());
        assert_eq!(report.metric_count(), 3);
        assert_eq!(
            report
                .results()
                .iter()
                .map(|result| result.name())
                .collect::<Vec<_>>(),
            vec!["com_db", "erl_db", "td_iln_db"]
        );
    }

    #[test]
    fn each_metric_uses_its_explicit_tolerance_at_the_boundary() {
        let reference = ComMetricBundleV1::try_new(8.0, 16.0, 32.0).unwrap();
        let candidate = ComMetricBundleV1::try_new(8.125, 16.25, 32.5).unwrap();
        let report = compare_com_metric_bundle_v1(
            reference,
            candidate,
            ComMetricTolerancesV1::new(
                tolerance(0.125, 0.0),
                tolerance(0.0, 0.015_625),
                tolerance(0.5, 0.0),
            ),
        )
        .unwrap();
        assert!(report.passed());

        let outside = ComMetricBundleV1::try_new(8.125_001, 16.0, 32.0).unwrap();
        assert!(
            !compare_com_metric_bundle_v1(
                reference,
                outside,
                ComMetricTolerancesV1::new(
                    tolerance(0.125, 0.0),
                    tolerance(0.0, 0.015_625),
                    tolerance(0.5, 0.0),
                ),
            )
            .unwrap()
            .passed()
        );
    }

    #[test]
    fn non_finite_bundle_and_arithmetic_fail_closed() {
        assert_eq!(
            ComMetricBundleV1::try_new(f64::NAN, 1.0, 2.0),
            Err(MetricCompareErrorV1::NonFinite)
        );
        let positive = ComMetricBundleV1::try_new(f64::MAX, 1.0, 2.0).unwrap();
        let negative = ComMetricBundleV1::try_new(-f64::MAX, 1.0, 2.0).unwrap();
        assert_eq!(
            compare_com_metric_bundle_v1(positive, negative, tolerances(tolerance(0.0, 0.0)),),
            Err(MetricCompareErrorV1::NonFinite)
        );
    }

    #[test]
    fn negative_or_non_finite_tolerances_cannot_enter_the_bundle() {
        assert!(ToleranceV1::try_new(-0.1, 0.0).is_err());
        assert!(ToleranceV1::try_new(0.0, -0.1).is_err());
        assert!(ToleranceV1::try_new(f64::INFINITY, 0.0).is_err());
        assert!(ToleranceV1::try_new(0.0, f64::NAN).is_err());
    }
}
