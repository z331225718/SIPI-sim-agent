//! Typed AMI parameter profile diff core (P4B-02b79).
//!
//! Diffs two assembled parameter profiles (`BTreeMap<String, AmiParameterValueV1>`,
//! e.g. produced by 02b44 assembly) under the typed value semantics of
//! `parameter_values_equivalent_v1` (02b70): shared names with
//! typed-equivalent values (`0.5` vs `0.50`) count as matched, shared names
//! with typed-inequivalent values are reported as changed (with both sides'
//! declared types and raw value tokens plus the typed reason), left-only names
//! are removed and right-only names are added. This is the typed companion of
//! 02b47 profile diff (raw token equality) and the report-level view over the
//! boolean 02b71 profile equivalence.
//!
//! Fail-closed: the diff is total (no error path), all lists come back in
//! deterministic sorted order, and every changed entry carries its typed
//! reason via `ParameterValueInequivalenceReasonV1`.

use std::collections::BTreeMap;

use crate::{
    parameter_values_equivalent_v1, AmiParameterValueV1, ParameterValueEquivalenceV1,
    ParameterValueInequivalenceReasonV1,
};

/// Explicit scope policy of this slice: typed diff of parameter profiles.
pub const PARAMETER_PROFILE_TYPED_DIFF_POLICY_V1: &str =
    "sipi.p4b-02b79.parameter-profile-typed-diff-v1.typed-profile-diff";

/// One typed change for a shared name with typed-inequivalent values.
#[derive(Clone, Debug, PartialEq)]
pub struct ParameterProfileTypedChangeV1 {
    name: String,
    old_type: String,
    old_value: String,
    new_type: String,
    new_value: String,
    reason: ParameterValueInequivalenceReasonV1,
}

impl ParameterProfileTypedChangeV1 {
    pub fn name(&self) -> &str {
        &self.name
    }

    pub fn old_type(&self) -> &str {
        &self.old_type
    }

    pub fn old_value(&self) -> &str {
        &self.old_value
    }

    pub fn new_type(&self) -> &str {
        &self.new_type
    }

    pub fn new_value(&self) -> &str {
        &self.new_value
    }

    pub fn reason(&self) -> &ParameterValueInequivalenceReasonV1 {
        &self.reason
    }
}

/// Outcome of a typed profile diff.
#[derive(Clone, Debug, PartialEq)]
pub struct ParameterProfileTypedDiffV1 {
    matched: usize,
    added: Vec<String>,
    removed: Vec<String>,
    changed: Vec<ParameterProfileTypedChangeV1>,
}

impl ParameterProfileTypedDiffV1 {
    /// Shared names with typed-equivalent values.
    pub fn matched(&self) -> usize {
        self.matched
    }

    /// Sorted names present in right but missing in left.
    pub fn added(&self) -> &[String] {
        &self.added
    }

    /// Sorted names present in left but missing in right.
    pub fn removed(&self) -> &[String] {
        &self.removed
    }

    /// Sorted (by name) typed changes for shared names.
    pub fn changed(&self) -> &[ParameterProfileTypedChangeV1] {
        &self.changed
    }
}

/// Diff two parameter profiles under typed value semantics.
pub fn diff_parameter_profiles_typed_v1(
    left: &BTreeMap<String, AmiParameterValueV1>,
    right: &BTreeMap<String, AmiParameterValueV1>,
) -> ParameterProfileTypedDiffV1 {
    let mut matched = 0usize;
    let mut added = Vec::new();
    let mut removed = Vec::new();
    let mut changed = Vec::new();

    for name in left.keys() {
        if !right.contains_key(name) {
            removed.push(name.clone());
        }
    }
    for name in right.keys() {
        if !left.contains_key(name) {
            added.push(name.clone());
        }
    }
    for (name, old_value) in left {
        if let Some(new_value) = right.get(name) {
            match parameter_values_equivalent_v1(old_value, new_value) {
                ParameterValueEquivalenceV1::Equivalent => {
                    matched += 1;
                }
                ParameterValueEquivalenceV1::NotEquivalent(reason) => {
                    changed.push(ParameterProfileTypedChangeV1 {
                        name: name.clone(),
                        old_type: old_value.parameter_type().token().to_string(),
                        old_value: old_value.value_token().to_string(),
                        new_type: new_value.parameter_type().token().to_string(),
                        new_value: new_value.value_token().to_string(),
                        reason,
                    });
                }
            }
        }
    }
    ParameterProfileTypedDiffV1 {
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
    fn identical_profiles_are_all_matched() {
        let a = profile(&[("gain", "Float", "0.5"), ("steps", "Integer", "7")]);
        let b = profile(&[("gain", "Float", "0.5"), ("steps", "Integer", "7")]);
        let diff = diff_parameter_profiles_typed_v1(&a, &b);
        assert_eq!(diff.matched(), 2);
        assert!(diff.added().is_empty());
        assert!(diff.removed().is_empty());
        assert!(diff.changed().is_empty());
    }

    #[test]
    fn spelling_variants_count_as_matched() {
        let a = profile(&[("gain", "Float", "0.5")]);
        let b = profile(&[("gain", "Float", "0.50")]);
        let diff = diff_parameter_profiles_typed_v1(&a, &b);
        assert_eq!(diff.matched(), 1);
        assert!(diff.changed().is_empty());
    }

    #[test]
    fn added_and_removed_names_are_reported() {
        let a = profile(&[("gain", "Float", "0.5"), ("steps", "Integer", "7")]);
        let b = profile(&[("gain", "Float", "0.5"), ("mode", "String", "Linear")]);
        let diff = diff_parameter_profiles_typed_v1(&a, &b);
        assert_eq!(diff.matched(), 1);
        assert_eq!(diff.removed(), &["steps".to_string()]);
        assert_eq!(diff.added(), &["mode".to_string()]);
        assert!(diff.changed().is_empty());
    }

    #[test]
    fn typed_change_is_reported_with_reason() {
        let a = profile(&[("gain", "Float", "0.5")]);
        let b = profile(&[("gain", "Float", "0.5001")]);
        let diff = diff_parameter_profiles_typed_v1(&a, &b);
        assert_eq!(diff.matched(), 0);
        assert_eq!(diff.changed().len(), 1);
        let change = &diff.changed()[0];
        assert_eq!(change.name(), "gain");
        assert_eq!(change.old_type(), "Float");
        assert_eq!(change.old_value(), "0.5");
        assert_eq!(change.new_type(), "Float");
        assert_eq!(change.new_value(), "0.5001");
        assert_eq!(
            change.reason(),
            &ParameterValueInequivalenceReasonV1::FloatMismatch {
                left: 0.5,
                right: 0.5001,
            }
        );
    }

    #[test]
    fn cross_type_change_is_reported() {
        let a = profile(&[("x", "Float", "1.0")]);
        let b = profile(&[("x", "Integer", "1")]);
        let diff = diff_parameter_profiles_typed_v1(&a, &b);
        assert_eq!(diff.changed().len(), 1);
        let change = &diff.changed()[0];
        assert_eq!(change.old_type(), "Float");
        assert_eq!(change.new_type(), "Integer");
        assert_eq!(
            change.reason(),
            &ParameterValueInequivalenceReasonV1::TypeMismatch {
                left: AmiParameterTypeV1::Float,
                right: AmiParameterTypeV1::Integer,
            }
        );
    }

    #[test]
    fn empty_profiles_diff() {
        let a = BTreeMap::new();
        let b = BTreeMap::new();
        let diff = diff_parameter_profiles_typed_v1(&a, &b);
        assert_eq!(diff.matched(), 0);
        assert!(diff.added().is_empty());
        assert!(diff.removed().is_empty());
        assert!(diff.changed().is_empty());
    }
}
