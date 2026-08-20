//! Owner C4 metric-profile definition core (P3C-03, C4).
//!
//! Freezes the owner-decided COM metric profile (owner-decision-checklist
//! C4) as a real, named configuration that the P3C-03c profile-agnostic
//! compare engine can consume: metrics COM_dB / ICN_mV / ERL with a 1%
//! relative tolerance each (< 1%). The per-metric reference values are NOT
//! hard-coded here (the owner supplied the profile structure and tolerance,
//! not per-metric references): they are supplied by the caller at compare
//! time and must be finite. This is fail-closed: a missing, unknown, or
//! non-finite reference for any of the three metrics is a hard error, and
//! nothing is guessed.

use std::collections::BTreeMap;

use crate::{MetricSpecV1, ToleranceV1, UnitTagV1};

/// Stable scope policy of the C4 COM metric-profile core.
pub const C4_PROFILE_POLICY_V1: &str = "sipi.p3c-03c.c4-profile.v1.com-icn-erl-1pct";

/// The owner-decided relative tolerance for every C4 metric (< 1%).
pub const C4_RELATIVE_TOLERANCE_V1: f64 = 0.01;

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum C4ProfileErrorV1 {
    MissingReference(String),
    NonFiniteReference(String),
}

/// The fixed C4 metric list: (name, unit token, relative tolerance).
pub const C4_METRICS: [(&str, &str); 3] = [("COM_dB", "db"), ("ICN_mV", "mv"), ("ERL", "db")];

/// Builds the C4 metric specs for the P3C-03c compare engine from a
/// caller-supplied finite reference map.
///
/// Each of the three C4 metrics must have a finite reference; the returned
/// specs carry the fixed 1% relative tolerance. The result is intended to be
/// fed to MetricProfileV1::compile (P3C-03c).
pub fn c4_metric_specs_v1(
    references: &BTreeMap<String, f64>,
) -> Result<Vec<MetricSpecV1>, C4ProfileErrorV1> {
    let mut specs = Vec::with_capacity(C4_METRICS.len());
    for (name, unit) in C4_METRICS {
        let reference = references
            .get(name)
            .copied()
            .ok_or_else(|| C4ProfileErrorV1::MissingReference(name.to_string()))?;
        if !reference.is_finite() {
            return Err(C4ProfileErrorV1::NonFiniteReference(name.to_string()));
        }
        let unit_tag = UnitTagV1::try_new(unit.to_string()).expect("static unit");
        let tolerance =
            ToleranceV1::try_new(0.0, C4_RELATIVE_TOLERANCE_V1).expect("static tolerance");
        specs.push(
            MetricSpecV1::new(name.to_string(), unit_tag, reference, tolerance)
                .expect("valid spec"),
        );
    }
    Ok(specs)
}

/// Convenience: the fixed C4 metric names in profile order.
pub fn c4_metric_names() -> Vec<String> {
    C4_METRICS
        .iter()
        .map(|(name, _)| name.to_string())
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn refs_with(values: &[(&str, f64)]) -> std::collections::BTreeMap<String, f64> {
        values.iter().map(|(k, v)| (k.to_string(), *v)).collect()
    }

    #[test]
    fn policy_and_units_fixed() {
        assert_eq!(
            C4_PROFILE_POLICY_V1,
            "sipi.p3c-03c.c4-profile.v1.com-icn-erl-1pct"
        );
        assert!((C4_RELATIVE_TOLERANCE_V1 - 0.01).abs() < 1e-15);
        assert_eq!(c4_metric_names(), vec!["COM_dB", "ICN_mV", "ERL"]);
    }

    #[test]
    fn builds_three_specs_with_1pct_relative() {
        let refs = refs_with(&[("COM_dB", 3.5), ("ICN_mV", 12.0), ("ERL", 8.0)]);
        let specs = c4_metric_specs_v1(&refs).expect("specs");
        assert_eq!(specs.len(), 3);
        assert_eq!(specs[0].name(), "COM_dB");
        assert!((specs[0].reference() - 3.5).abs() < 1e-12);
        assert!((specs[0].tolerance().relative() - 0.01).abs() < 1e-15);
        assert_eq!(specs[1].name(), "ICN_mV");
        assert_eq!(specs[2].name(), "ERL");
    }

    #[test]
    fn missing_reference_rejected() {
        let refs = refs_with(&[("COM_dB", 3.5), ("ICN_mV", 12.0)]);
        assert_eq!(
            c4_metric_specs_v1(&refs).err(),
            Some(C4ProfileErrorV1::MissingReference("ERL".to_string()))
        );
    }

    #[test]
    fn unknown_extra_reference_ignored_but_missing_still_rejected() {
        let refs = refs_with(&[("COM_dB", 3.5), ("FOM", 53.0), ("ICN_mV", 12.0)]);
        assert_eq!(
            c4_metric_specs_v1(&refs).err(),
            Some(C4ProfileErrorV1::MissingReference("ERL".to_string()))
        );
    }

    #[test]
    fn non_finite_reference_rejected() {
        let refs = refs_with(&[("COM_dB", f64::NAN), ("ICN_mV", 12.0), ("ERL", 8.0)]);
        assert_eq!(
            c4_metric_specs_v1(&refs).err(),
            Some(C4ProfileErrorV1::NonFiniteReference("COM_dB".to_string()))
        );
    }
}
