//! AMI parameter profile type statistics core (P4B-02b73).
//!
//! Counts the entries of an assembled parameter profile (`BTreeMap<String,
//! AmiParameterValueV1>`, e.g. produced by 02b44 assembly) by declared type:
//! Float, Integer, Boolean, String, List, plus the total entry count. This is
//! the profile-level companion of tree token statistics (02b31) and form-head
//! counting (02b61); it is the deterministic inventory a caller uses before
//! feeding a profile onward (e.g. deciding whether a profile carries only
//! numeric parameters). Fail-closed: counts are derived exclusively from the
//! validated `parameter_type()` of each entry (types are closed under the
//! five product variants), and the per-type counts always sum to the total.

use std::collections::BTreeMap;

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: profile type inventory only.
pub const PARAMETER_PROFILE_TYPE_STATS_POLICY_V1: &str =
    "sipi.p4b-02b73.parameter-profile-type-stats-v1.profile-type-stats";

/// Declared-type inventory of one parameter profile.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ParameterProfileTypeStatsV1 {
    total: usize,
    float_count: usize,
    integer_count: usize,
    boolean_count: usize,
    string_count: usize,
    list_count: usize,
}

impl ParameterProfileTypeStatsV1 {
    /// Total number of profile entries.
    pub fn total(&self) -> usize {
        self.total
    }

    /// Entries declared Float.
    pub fn float_count(&self) -> usize {
        self.float_count
    }

    /// Entries declared Integer.
    pub fn integer_count(&self) -> usize {
        self.integer_count
    }

    /// Entries declared Boolean.
    pub fn boolean_count(&self) -> usize {
        self.boolean_count
    }

    /// Entries declared String.
    pub fn string_count(&self) -> usize {
        self.string_count
    }

    /// Entries declared List.
    pub fn list_count(&self) -> usize {
        self.list_count
    }

    /// Per-type counts sum to the total (invariant, checked in tests).
    pub fn sum_of_type_counts(&self) -> usize {
        self.float_count
            + self.integer_count
            + self.boolean_count
            + self.string_count
            + self.list_count
    }
}

/// Count an assembled parameter profile's entries by declared type.
pub fn compute_parameter_profile_type_stats_v1(
    profile: &BTreeMap<String, AmiParameterValueV1>,
) -> ParameterProfileTypeStatsV1 {
    let mut float_count = 0usize;
    let mut integer_count = 0usize;
    let mut boolean_count = 0usize;
    let mut string_count = 0usize;
    let mut list_count = 0usize;
    for value in profile.values() {
        match value.parameter_type() {
            AmiParameterTypeV1::Float => float_count += 1,
            AmiParameterTypeV1::Integer => integer_count += 1,
            AmiParameterTypeV1::Boolean => boolean_count += 1,
            AmiParameterTypeV1::String_ => string_count += 1,
            AmiParameterTypeV1::List => list_count += 1,
        }
    }
    ParameterProfileTypeStatsV1 {
        total: profile.len(),
        float_count,
        integer_count,
        boolean_count,
        string_count,
        list_count,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    fn profile(pairs: &[(&str, &str, &str)]) -> BTreeMap<String, AmiParameterValueV1> {
        pairs
            .iter()
            .map(|(name, type_token, value_token)| {
                ((*name).to_string(), value(name, type_token, value_token))
            })
            .collect()
    }

    #[test]
    fn counts_each_declared_type() {
        let p = profile(&[
            ("gain", "Float", "0.5"),
            ("steps", "Integer", "7"),
            ("on", "Boolean", "True"),
            ("mode", "String", "Linear"),
            ("channels", "List", "(a, b)"),
        ]);
        let stats = compute_parameter_profile_type_stats_v1(&p);
        assert_eq!(stats.total(), 5);
        assert_eq!(stats.float_count(), 1);
        assert_eq!(stats.integer_count(), 1);
        assert_eq!(stats.boolean_count(), 1);
        assert_eq!(stats.string_count(), 1);
        assert_eq!(stats.list_count(), 1);
        assert_eq!(stats.sum_of_type_counts(), stats.total());
    }

    #[test]
    fn total_matches_profile_len() {
        let p = profile(&[
            ("a", "Float", "0.5"),
            ("b", "Float", "1.25"),
            ("c", "Integer", "7"),
        ]);
        let stats = compute_parameter_profile_type_stats_v1(&p);
        assert_eq!(stats.total(), 3);
        assert_eq!(stats.float_count(), 2);
        assert_eq!(stats.integer_count(), 1);
        assert_eq!(stats.sum_of_type_counts(), stats.total());
    }

    #[test]
    fn empty_profile_is_all_zero() {
        let p = BTreeMap::new();
        let stats = compute_parameter_profile_type_stats_v1(&p);
        assert_eq!(stats.total(), 0);
        assert_eq!(stats.float_count(), 0);
        assert_eq!(stats.integer_count(), 0);
        assert_eq!(stats.boolean_count(), 0);
        assert_eq!(stats.string_count(), 0);
        assert_eq!(stats.list_count(), 0);
    }

    #[test]
    fn mixed_counts_are_deterministic() {
        let p = profile(&[
            ("a", "Float", "0.5"),
            ("b", "Integer", "1"),
            ("c", "Integer", "2"),
            ("d", "Boolean", "False"),
            ("e", "String", "S"),
            ("f", "List", "(x)"),
            ("g", "List", "(y, z)"),
        ]);
        let stats = compute_parameter_profile_type_stats_v1(&p);
        assert_eq!(stats.total(), 7);
        assert_eq!(stats.float_count(), 1);
        assert_eq!(stats.integer_count(), 2);
        assert_eq!(stats.boolean_count(), 1);
        assert_eq!(stats.string_count(), 1);
        assert_eq!(stats.list_count(), 2);
        assert_eq!(stats.sum_of_type_counts(), stats.total());
    }

    #[test]
    fn only_float_profile() {
        let p = profile(&[
            ("a", "Float", "0.5"),
            ("b", "Float", "1.0"),
            ("c", "Float", "2.5"),
        ]);
        let stats = compute_parameter_profile_type_stats_v1(&p);
        assert_eq!(stats.total(), 3);
        assert_eq!(stats.float_count(), 3);
        assert_eq!(stats.integer_count(), 0);
        assert_eq!(stats.boolean_count(), 0);
        assert_eq!(stats.string_count(), 0);
        assert_eq!(stats.list_count(), 0);
    }

    #[test]
    fn type_counts_sum_invariant() {
        let p = profile(&[
            ("gain", "Float", "0.5"),
            ("steps", "Integer", "7"),
            ("on", "Boolean", "True"),
            ("mode", "String", "Linear"),
            ("channels", "List", "(a, b)"),
            ("extra", "Float", "9.9"),
        ]);
        let stats = compute_parameter_profile_type_stats_v1(&p);
        assert_eq!(stats.total(), 6);
        assert_eq!(stats.sum_of_type_counts(), 6);
    }
}
