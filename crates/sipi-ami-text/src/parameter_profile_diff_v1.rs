//! AMI parameter profile diff core (P4B-02b47).
//!
//! Compares two assembled parameter maps (leaf name -> `AmiParameterValueV1`)
//! and reports added, removed, and changed entries plus a matched count. This is
//! the regression-comparison primitive for assembled profiles (P4B-02b44).
//! The diff is total and result-based: empty maps are valid inputs and an empty
//! diff is a valid result.

use std::collections::BTreeMap;

use crate::AmiParameterValueV1;

/// Scope policy for the parameter profile diff core.
pub const PARAMETER_PROFILE_DIFF_POLICY_V1: &str =
    "sipi.p4b-02b47.parameter-profile-diff-v1.profile-comparison";

/// One parameter whose value changed between two profiles.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ParameterValueChangeV1 {
    name: String,
    old: AmiParameterValueV1,
    new: AmiParameterValueV1,
}

impl ParameterValueChangeV1 {
    pub fn name(&self) -> &str {
        &self.name
    }

    pub fn old(&self) -> &AmiParameterValueV1 {
        &self.old
    }

    pub fn new(&self) -> &AmiParameterValueV1 {
        &self.new
    }
}

/// Outcome of a profile diff pass.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ParameterProfileDiffV1 {
    matched: usize,
    added: Vec<String>,
    removed: Vec<String>,
    changed: Vec<ParameterValueChangeV1>,
}

impl ParameterProfileDiffV1 {
    pub fn matched(&self) -> usize {
        self.matched
    }

    pub fn added(&self) -> &[String] {
        &self.added
    }

    pub fn removed(&self) -> &[String] {
        &self.removed
    }

    pub fn changed(&self) -> &[ParameterValueChangeV1] {
        &self.changed
    }
}

/// Diff `a` (old) against `b` (new) by parameter name.
///
/// - matched: names present in both with identical values;
/// - added: names only in `b` (sorted);
/// - removed: names only in `a` (sorted);
/// - changed: names in both with different values (sorted by name), carrying
///   the old and new `AmiParameterValueV1` records.
pub fn diff_parameter_profiles_v1(
    a: &BTreeMap<String, AmiParameterValueV1>,
    b: &BTreeMap<String, AmiParameterValueV1>,
) -> ParameterProfileDiffV1 {
    let mut matched = 0usize;
    let mut added = Vec::new();
    let mut removed = Vec::new();
    let mut changed = Vec::new();
    for (name, old_value) in a {
        match b.get(name) {
            None => removed.push(name.clone()),
            Some(new_value) if new_value == old_value => matched += 1,
            Some(new_value) => changed.push(ParameterValueChangeV1 {
                name: name.clone(),
                old: old_value.clone(),
                new: new_value.clone(),
            }),
        }
    }
    for name in b.keys() {
        if !a.contains_key(name) {
            added.push(name.clone());
        }
    }
    ParameterProfileDiffV1 {
        matched,
        added,
        removed,
        changed,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::AmiParameterTypeV1;

    fn parameter(name: &str, type_token: &str, value: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value).expect("valid parameter")
    }

    fn profile(pairs: &[(&str, &str, &str)]) -> BTreeMap<String, AmiParameterValueV1> {
        pairs
            .iter()
            .map(|(name, type_token, value)| {
                (
                    name.to_string(),
                    parameter(name, type_token, value),
                )
            })
            .collect()
    }

    #[test]
    fn identical_profiles_match() {
        let a = profile(&[("gain", "Float", "0.5"), ("steps", "Integer", "7")]);
        let b = profile(&[("gain", "Float", "0.5"), ("steps", "Integer", "7")]);
        let diff = diff_parameter_profiles_v1(&a, &b);
        assert_eq!(diff.matched(), 2);
        assert!(diff.added().is_empty());
        assert!(diff.removed().is_empty());
        assert!(diff.changed().is_empty());
    }

    #[test]
    fn added_and_removed_are_reported() {
        let a = profile(&[("gain", "Float", "0.5"), ("steps", "Integer", "7")]);
        let b = profile(&[("gain", "Float", "0.5"), ("enabled", "Boolean", "True")]);
        let diff = diff_parameter_profiles_v1(&a, &b);
        assert_eq!(diff.matched(), 1);
        assert_eq!(diff.added(), &["enabled".to_string()]);
        assert_eq!(diff.removed(), &["steps".to_string()]);
        assert!(diff.changed().is_empty());
    }

    #[test]
    fn value_change_is_reported() {
        let a = profile(&[("gain", "Float", "0.5")]);
        let b = profile(&[("gain", "Float", "1.25")]);
        let diff = diff_parameter_profiles_v1(&a, &b);
        assert_eq!(diff.matched(), 0);
        assert_eq!(diff.changed().len(), 1);
        let change = &diff.changed()[0];
        assert_eq!(change.name(), "gain");
        assert_eq!(change.old().value_token(), "0.5");
        assert_eq!(change.new().value_token(), "1.25");
    }

    #[test]
    fn type_change_is_reported() {
        let a = profile(&[("gain", "Float", "0.5")]);
        let b = profile(&[("gain", "String", "0.5")]);
        let diff = diff_parameter_profiles_v1(&a, &b);
        assert_eq!(diff.changed().len(), 1);
        let change = &diff.changed()[0];
        assert_eq!(change.old().parameter_type(), AmiParameterTypeV1::Float);
        assert_eq!(change.new().parameter_type(), AmiParameterTypeV1::String_);
    }

    #[test]
    fn empty_against_full_reports_all_added() {
        let a = profile(&[]);
        let b = profile(&[("gain", "Float", "0.5")]);
        let diff = diff_parameter_profiles_v1(&a, &b);
        assert_eq!(diff.matched(), 0);
        assert_eq!(diff.added(), &["gain".to_string()]);
        assert!(diff.removed().is_empty());
        assert!(diff.changed().is_empty());
    }

    #[test]
    fn mixed_diff_reports_all_categories() {
        let a = profile(&[
            ("gain", "Float", "0.5"),
            ("steps", "Integer", "7"),
            ("mode", "String", "fast"),
        ]);
        let b = profile(&[
            ("gain", "Float", "1.25"),
            ("enabled", "Boolean", "True"),
            ("mode", "String", "fast"),
        ]);
        let diff = diff_parameter_profiles_v1(&a, &b);
        assert_eq!(diff.matched(), 1);
        assert_eq!(diff.added(), &["enabled".to_string()]);
        assert_eq!(diff.removed(), &["steps".to_string()]);
        assert_eq!(diff.changed().len(), 1);
        assert_eq!(diff.changed()[0].name(), "gain");
    }
}
