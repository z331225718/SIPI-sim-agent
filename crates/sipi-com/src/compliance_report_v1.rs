//! COM metric-profile compliance report core (P3C-03e).
//!
//! Combines the P3C-03d dB-tolerance check with a named metric profile into
//! an end-to-end compliance report: for each metric (name + dB reference +
//! tolerance, defaulting to the owner 0.1 dB) compare the candidate value
//! and emit a per-metric verdict plus an overall pass. This is the runnable
//! compare output that advances P3C-03 from the raw engine (03c/03d) to a
//! usable COM metric compliance report. The specific metric profile (C4) is
//! caller-supplied; no profile is selected or implied.

use std::collections::BTreeMap;

use crate::db_tolerance_v1::db_tolerance_check_v1;

/// Stable scope policy of the P3C-03e compliance report core.
pub const COMPLIANCE_REPORT_POLICY_V1: &str = "sipi.p3c-03e.compliance-report.v1.profile";

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ComplianceErrorV1 {
    EmptyProfile,
    MissingCandidate(String),
    NonFinite,
}

/// One metric specification in a compliance profile (dB reference + tolerance).
#[derive(Clone, Debug, PartialEq)]
pub struct ComplianceMetricSpecV1 {
    name: String,
    reference_db: f64,
    tolerance_db: f64,
    unit: String,
}

impl ComplianceMetricSpecV1 {
    pub fn new(name: impl Into<String>, reference_db: f64, tolerance_db: f64, unit: impl Into<String>) -> Self {
        Self { name: name.into(), reference_db, tolerance_db, unit: unit.into() }
    }
}

/// One per-metric compliance verdict.
#[derive(Clone, Debug, PartialEq)]
pub struct MetricComplianceV1 {
    name: String,
    reference_db: f64,
    candidate_db: f64,
    difference_db: f64,
    tolerance_db: f64,
    unit: String,
    passed: bool,
}

impl MetricComplianceV1 {
    pub fn name(&self) -> &str { &self.name }
    pub fn passed(&self) -> bool { self.passed }
    pub fn difference_db(&self) -> f64 { self.difference_db }
    pub fn candidate_db(&self) -> f64 { self.candidate_db }
}

#[derive(Clone, Debug, PartialEq)]
pub struct ComplianceReportV1 {
    passed: bool,
    metric_count: usize,
    results: Vec<MetricComplianceV1>,
}

impl ComplianceReportV1 {
    pub fn passed(&self) -> bool { self.passed }
    pub fn metric_count(&self) -> usize { self.metric_count }
    pub fn results(&self) -> &[MetricComplianceV1] { &self.results }
}

/// Builds an end-to-end compliance report for a named metric profile.
pub fn compliance_report_v1(
    profile: &[ComplianceMetricSpecV1],
    candidates: &BTreeMap<String, f64>,
) -> Result<ComplianceReportV1, ComplianceErrorV1> {
    if profile.is_empty() {
        return Err(ComplianceErrorV1::EmptyProfile);
    }
    let mut results = Vec::new();
    let mut passed = true;
    for spec in profile {
        let candidate = candidates
            .get(&spec.name)
            .copied()
            .ok_or_else(|| ComplianceErrorV1::MissingCandidate(spec.name.clone()))?;
        if !candidate.is_finite() || !spec.reference_db.is_finite() {
            return Err(ComplianceErrorV1::NonFinite);
        }
        let verdict = db_tolerance_check_v1(spec.reference_db, candidate, spec.tolerance_db)
            .map_err(|_| ComplianceErrorV1::NonFinite)?;
        if !verdict.passed() {
            passed = false;
        }
        results.push(MetricComplianceV1 {
            name: spec.name.clone(),
            reference_db: spec.reference_db,
            candidate_db: candidate,
            difference_db: verdict.difference_db(),
            tolerance_db: spec.tolerance_db,
            unit: spec.unit.clone(),
            passed: verdict.passed(),
        });
    }
    Ok(ComplianceReportV1 { passed, metric_count: results.len(), results })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn policy_fixed() {
        assert_eq!(COMPLIANCE_REPORT_POLICY_V1, "sipi.p3c-03e.compliance-report.v1.profile");
    }

    #[test]
    fn all_within_passes() {
        let profile = vec![
            ComplianceMetricSpecV1::new("fom", 53.426, 0.1, "db"),
            ComplianceMetricSpecV1::new("crossing", 90.0, 0.5, "deg"),
        ];
        let mut cand = BTreeMap::new();
        cand.insert("fom".to_string(), 53.45);
        cand.insert("crossing".to_string(), 90.2);
        let rpt = compliance_report_v1(&profile, &cand).expect("rpt");
        assert!(rpt.passed());
        assert_eq!(rpt.metric_count(), 2);
    }

    #[test]
    fn out_of_tolerance_fails() {
        let profile = vec![ComplianceMetricSpecV1::new("fom", 53.426, 0.1, "db")];
        let mut cand = BTreeMap::new();
        cand.insert("fom".to_string(), 54.0);
        let rpt = compliance_report_v1(&profile, &cand).expect("rpt");
        assert!(!rpt.passed());
        assert!(!rpt.results()[0].passed());
    }

    #[test]
    fn missing_candidate_rejected() {
        let profile = vec![ComplianceMetricSpecV1::new("fom", 53.426, 0.1, "db")];
        let err = compliance_report_v1(&profile, &BTreeMap::new()).err().expect("err");
        assert_eq!(err, ComplianceErrorV1::MissingCandidate("fom".to_string()));
    }

    #[test]
    fn empty_profile_rejected() {
        assert_eq!(compliance_report_v1(&[], &BTreeMap::new()).err(), Some(ComplianceErrorV1::EmptyProfile));
    }
}