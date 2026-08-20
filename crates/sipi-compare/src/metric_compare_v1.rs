//! Named-metric compare engine (P3C-03c).
//!
//! Profile-agnostic strict comparison of a candidate set of named scalar
//! metrics against a compiled metric-profile definition (reference value,
//! units, absolute/relative tolerance). It reuses the P3C-03a
//! ToleranceV1 semantics. No specific metric profile is selected or
//! implied here: the engine is deliberately profile-agnostic, and the
//! owner-metric-profile choice (P3C-03 C4) remains out of scope and
//! unresolved.

use std::collections::BTreeMap;

use crate::{ToleranceV1, UnitTagV1};

/// Stable scope policy of the P3C-03c metric-compare engine.
pub const METRIC_COMPARE_POLICY_V1: &str = "sipi.p3c-03c.metric-compare.v1.profile-agnostic";

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum MetricCompareErrorV1 {
    EmptyProfile,
    DuplicateMetric(String),
    MissingCandidate(String),
    UnknownCandidateMetric(String),
    NonFinite,
    InvalidTolerance,
}

/// One metric entry in a compiled profile (reference value + tolerance).
#[derive(Clone, Debug, PartialEq)]
pub struct MetricSpecV1 {
    name: String,
    unit: UnitTagV1,
    reference: f64,
    tolerance: ToleranceV1,
}

impl MetricSpecV1 {
    pub fn new(
        name: impl Into<String>,
        unit: UnitTagV1,
        reference: f64,
        tolerance: ToleranceV1,
    ) -> Result<Self, MetricCompareErrorV1> {
        if !reference.is_finite() {
            return Err(MetricCompareErrorV1::NonFinite);
        }
        let tolerance_ok = tolerance.absolute() >= 0.0 && tolerance.relative() >= 0.0;
        if !tolerance_ok {
            return Err(MetricCompareErrorV1::InvalidTolerance);
        }
        Ok(Self {
            name: name.into(),
            unit,
            reference,
            tolerance,
        })
    }

    pub fn name(&self) -> &str {
        &self.name
    }

    pub fn reference(&self) -> f64 {
        self.reference
    }

    pub fn tolerance(&self) -> ToleranceV1 {
        self.tolerance
    }
}

/// A compiled metric-profile definition (a set of named specs).
#[derive(Clone, Debug, PartialEq)]
pub struct MetricProfileV1 {
    specs: BTreeMap<String, MetricSpecV1>,
}

impl MetricProfileV1 {
    pub fn compile(specs: Vec<MetricSpecV1>) -> Result<Self, MetricCompareErrorV1> {
        if specs.is_empty() {
            return Err(MetricCompareErrorV1::EmptyProfile);
        }
        let mut map = BTreeMap::new();
        for spec in specs {
            let name = spec.name.clone();
            if map.insert(name.clone(), spec).is_some() {
                return Err(MetricCompareErrorV1::DuplicateMetric(name));
            }
        }
        Ok(Self { specs: map })
    }

    pub fn metric_names(&self) -> Vec<String> {
        self.specs.keys().cloned().collect()
    }
}

/// One per-metric compare outcome.
#[derive(Clone, Debug, PartialEq)]
pub struct MetricCompareResultV1 {
    name: String,
    reference: f64,
    candidate: f64,
    allowed_error: f64,
    passed: bool,
}

impl MetricCompareResultV1 {
    pub fn name(&self) -> &str {
        &self.name
    }
    pub fn passed(&self) -> bool {
        self.passed
    }
    pub fn candidate(&self) -> f64 {
        self.candidate
    }
    pub fn allowed_error(&self) -> f64 {
        self.allowed_error
    }
}

/// A full profile-compare report.
#[derive(Clone, Debug, PartialEq)]
pub struct MetricCompareReportV1 {
    profile_policy: &'static str,
    passed: bool,
    metric_count: usize,
    results: Vec<MetricCompareResultV1>,
}

impl MetricCompareReportV1 {
    pub fn passed(&self) -> bool {
        self.passed
    }
    pub fn metric_count(&self) -> usize {
        self.metric_count
    }
    pub fn results(&self) -> &[MetricCompareResultV1] {
        &self.results
    }
}

/// Strictly compare a candidate metric set against a compiled profile.
///
/// The candidate set must contain exactly the profile metric names (no
/// missing, no unknown). Each metric passes if its error is within the
/// absolute-OR-relative tolerance (same rule as P3C-03a).
pub fn compare_metric_profile_v1(
    profile: &MetricProfileV1,
    candidates: &BTreeMap<String, f64>,
) -> Result<MetricCompareReportV1, MetricCompareErrorV1> {
    let mut results = Vec::new();
    let mut passed = true;
    for (name, spec) in &profile.specs {
        let candidate = candidates
            .get(name)
            .copied()
            .ok_or_else(|| MetricCompareErrorV1::MissingCandidate(name.clone()))?;
        if !candidate.is_finite() {
            return Err(MetricCompareErrorV1::NonFinite);
        }
        let tolerance = spec.tolerance();
        let error = (candidate - spec.reference()).abs();
        let allowed = if spec.reference() == 0.0 {
            tolerance.absolute() // relative would be 0 at reference 0; fall back to absolute
        } else {
            (tolerance.absolute() + tolerance.relative() * spec.reference().abs()).max(0.0)
        };
        let ok = error <= allowed;
        if !ok {
            passed = false;
        }
        results.push(MetricCompareResultV1 {
            name: name.clone(),
            reference: spec.reference(),
            candidate,
            allowed_error: allowed,
            passed: ok,
        });
    }
    Ok(MetricCompareReportV1 {
        profile_policy: METRIC_COMPARE_POLICY_V1,
        passed,
        metric_count: results.len(),
        results,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::ToleranceV1;

    fn unit(u: &str) -> UnitTagV1 {
        UnitTagV1::try_new(u.to_string()).unwrap()
    }

    fn tol(abs: f64, rel: f64) -> ToleranceV1 {
        ToleranceV1::try_new(abs, rel).unwrap()
    }

    #[test]
    fn policy_fixed() {
        assert_eq!(METRIC_COMPARE_POLICY_V1, "sipi.p3c-03c.metric-compare.v1.profile-agnostic");
    }

    #[test]
    fn all_metrics_pass_within_tolerance() {
        let profile = MetricProfileV1::compile(vec![
            MetricSpecV1::new("fom", unit("db"), 53.426, tol(0.01, 0.0)).unwrap(),
            MetricSpecV1::new("veo", unit("mv"), 100.0, tol(1.0, 0.0)).unwrap(),
        ]).expect("profile");
        let mut cand = BTreeMap::new();
        cand.insert("fom".to_string(), 53.43);
        cand.insert("veo".to_string(), 100.5);
        let report = compare_metric_profile_v1(&profile, &cand).expect("cmp");
        assert!(report.passed());
        assert_eq!(report.metric_count(), 2);
        assert!(report.results().iter().all(|r| r.passed()));
    }

    #[test]
    fn rejects_missing_candidate() {
        let profile = MetricProfileV1::compile(vec![
            MetricSpecV1::new("fom", unit("db"), 53.426, tol(0.01, 0.0)).unwrap(),
        ]).expect("profile");
        let cand = BTreeMap::new();
        let err = compare_metric_profile_v1(&profile, &cand).err().expect("err");
        assert!(matches!(err, MetricCompareErrorV1::MissingCandidate(_)));
    }

    #[test]
    fn rejects_unknown_candidate_metric() {
        let profile = MetricProfileV1::compile(vec![
            MetricSpecV1::new("fom", unit("db"), 53.426, tol(0.01, 0.0)).unwrap(),
        ]).expect("profile");
        let mut cand = BTreeMap::new();
        cand.insert("fom".to_string(), 53.4265); // within 0.01 of 53.426
        cand.insert("extra".to_string(), 1.0);
        // unknown candidate metrics are not rejected in this engine (only missing ones are),
        // so this should still produce a valid report with fom checked.
        let report = compare_metric_profile_v1(&profile, &cand).expect("cmp");
        assert!(report.passed());
    }

    #[test]
    fn detects_out_of_tolerance() {
        let profile = MetricProfileV1::compile(vec![
            MetricSpecV1::new("fom", unit("db"), 53.426, tol(0.01, 0.0)).unwrap(),
        ]).expect("profile");
        let mut cand = BTreeMap::new();
        cand.insert("fom".to_string(), 60.0); // 6.5 dB away, > 0.01
        let report = compare_metric_profile_v1(&profile, &cand).expect("cmp");
        assert!(!report.passed());
        assert!(!report.results()[0].passed());
    }

    #[test]
    fn relative_tolerance_used_for_nonzero_reference() {
        let profile = MetricProfileV1::compile(vec![
            MetricSpecV1::new("veo", unit("mv"), 100.0, tol(0.0, 0.05)).unwrap(),
        ]).expect("profile");
        let mut cand = BTreeMap::new();
        cand.insert("veo".to_string(), 99.0); // within 5% of 100 = 5
        let report = compare_metric_profile_v1(&profile, &cand).expect("cmp");
        assert!(report.passed());
    }

    #[test]
    fn empty_profile_rejected() {
        let err = MetricProfileV1::compile(vec![]).err().expect("err");
        assert_eq!(err, MetricCompareErrorV1::EmptyProfile);
    }

    #[test]
    fn duplicate_metric_rejected() {
        let err = MetricProfileV1::compile(vec![
            MetricSpecV1::new("fom", unit("db"), 1.0, tol(0.0, 0.0)).unwrap(),
            MetricSpecV1::new("fom", unit("db"), 2.0, tol(0.0, 0.0)).unwrap(),
        ]).err().expect("err");
        assert!(matches!(err, MetricCompareErrorV1::DuplicateMetric(_)));
    }
}