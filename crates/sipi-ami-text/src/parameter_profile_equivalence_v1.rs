//! Typed AMI parameter profile semantic equivalence core (P4B-02b71).
//!
//! Compares two assembled parameter profiles (`BTreeMap<String, AmiParameterValueV1>`,
//! e.g. produced by 02b44 assembly) by typed value semantics, not raw token
//! spelling: every shared name must hold values that are typed-equivalent via
//! `parameter_values_equivalent_v1` (02b70), and the name sets must match
//! exactly. This is the profile-map-level companion of 02b70 (value-level) and
//! sits above 02b47 profile diff, which reports added/removed/changed by raw
//! tokens.
//!
//! Fail-closed: a name present in exactly one profile (left_only/right_only)
//! and any typed value mismatch are strictly reported; both-empty profiles are
//! Equivalent; all lists come back in deterministic sorted order.

use std::collections::BTreeMap;

use crate::{
    AmiParameterValueV1, ParameterValueEquivalenceV1, ParameterValueInequivalenceReasonV1,
    parameter_values_equivalent_v1,
};

/// Explicit scope policy of this slice: typed profile-map equivalence only.
pub const PARAMETER_PROFILE_EQUIVALENCE_POLICY_V1: &str =
    "sipi.p4b-02b71.parameter-profile-equivalence-v1.typed-profile-equivalence";

/// Outcome of comparing two parameter profiles by typed value semantics.
#[derive(Clone, Debug, PartialEq)]
pub enum ParameterProfileEquivalenceV1 {
    Equivalent,
    NotEquivalent(ParameterProfileInequivalenceV1),
}

/// Why two parameter profiles are not typed-equivalent.
#[derive(Clone, Debug, PartialEq)]
pub struct ParameterProfileInequivalenceV1 {
    /// Sorted names present in left but missing in right.
    left_only: Vec<String>,
    /// Sorted names present in right but missing in left.
    right_only: Vec<String>,
    /// Sorted (by name) typed value mismatches for shared names.
    value_mismatches: Vec<ParameterProfileValueMismatchV1>,
}

impl ParameterProfileInequivalenceV1 {
    pub fn left_only(&self) -> &[String] {
        &self.left_only
    }

    pub fn right_only(&self) -> &[String] {
        &self.right_only
    }

    pub fn value_mismatches(&self) -> &[ParameterProfileValueMismatchV1] {
        &self.value_mismatches
    }
}

/// One shared-name value mismatch with its typed reason.
#[derive(Clone, Debug, PartialEq)]
pub struct ParameterProfileValueMismatchV1 {
    name: String,
    reason: ParameterValueInequivalenceReasonV1,
}

impl ParameterProfileValueMismatchV1 {
    pub fn name(&self) -> &str {
        &self.name
    }

    pub fn reason(&self) -> &ParameterValueInequivalenceReasonV1 {
        &self.reason
    }
}

/// Compare two parameter profiles by typed value semantics.
pub fn parameter_profiles_equivalent_v1(
    left: &BTreeMap<String, AmiParameterValueV1>,
    right: &BTreeMap<String, AmiParameterValueV1>,
) -> ParameterProfileEquivalenceV1 {
    let mut left_only = Vec::new();
    let mut right_only = Vec::new();
    let mut value_mismatches = Vec::new();

    for name in left.keys() {
        if !right.contains_key(name) {
            left_only.push(name.clone());
        }
    }
    for name in right.keys() {
        if !left.contains_key(name) {
            right_only.push(name.clone());
        }
    }
    for (name, left_value) in left {
        if let Some(right_value) = right.get(name) {
            match parameter_values_equivalent_v1(left_value, right_value) {
                ParameterValueEquivalenceV1::Equivalent => {}
                ParameterValueEquivalenceV1::NotEquivalent(reason) => {
                    value_mismatches.push(ParameterProfileValueMismatchV1 {
                        name: name.clone(),
                        reason,
                    });
                }
            }
        }
    }

    if left_only.is_empty() && right_only.is_empty() && value_mismatches.is_empty() {
        ParameterProfileEquivalenceV1::Equivalent
    } else {
        ParameterProfileEquivalenceV1::NotEquivalent(ParameterProfileInequivalenceV1 {
            left_only,
            right_only,
            value_mismatches,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{AmiParameterTypeV1, AmiParameterValueV1};

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
    fn identical_profiles_are_equivalent() {
        let a = profile(&[("gain", "Float", "0.5"), ("steps", "Integer", "7")]);
        let b = profile(&[("gain", "Float", "0.5"), ("steps", "Integer", "7")]);
        assert_eq!(
            parameter_profiles_equivalent_v1(&a, &b),
            ParameterProfileEquivalenceV1::Equivalent
        );
    }

    #[test]
    fn spelling_variants_are_equivalent() {
        let a = profile(&[("gain", "Float", "0.5"), ("channels", "List", "(a, b, c)")]);
        let b = profile(&[("gain", "Float", "0.50"), ("channels", "List", "(a,b,c)")]);
        assert_eq!(
            parameter_profiles_equivalent_v1(&a, &b),
            ParameterProfileEquivalenceV1::Equivalent
        );
    }

    #[test]
    fn missing_names_are_reported() {
        let a = profile(&[("gain", "Float", "0.5"), ("steps", "Integer", "7")]);
        let b = profile(&[("gain", "Float", "0.5")]);
        match parameter_profiles_equivalent_v1(&a, &b) {
            ParameterProfileEquivalenceV1::Equivalent => panic!("expected NotEquivalent"),
            ParameterProfileEquivalenceV1::NotEquivalent(report) => {
                assert_eq!(report.left_only(), &["steps".to_string()]);
                assert!(report.right_only().is_empty());
                assert!(report.value_mismatches().is_empty());
            }
        }
        let c = profile(&[("extra", "Float", "1.0")]);
        match parameter_profiles_equivalent_v1(&b, &c) {
            ParameterProfileEquivalenceV1::Equivalent => panic!("expected NotEquivalent"),
            ParameterProfileEquivalenceV1::NotEquivalent(report) => {
                assert_eq!(report.left_only(), &["gain".to_string()]);
                assert_eq!(report.right_only(), &["extra".to_string()]);
                assert!(report.value_mismatches().is_empty());
            }
        }
    }

    #[test]
    fn typed_value_mismatch_is_reported() {
        let a = profile(&[("gain", "Float", "0.5")]);
        let b = profile(&[("gain", "Float", "0.5001")]);
        match parameter_profiles_equivalent_v1(&a, &b) {
            ParameterProfileEquivalenceV1::Equivalent => panic!("expected NotEquivalent"),
            ParameterProfileEquivalenceV1::NotEquivalent(report) => {
                assert!(report.left_only().is_empty());
                assert!(report.right_only().is_empty());
                assert_eq!(report.value_mismatches().len(), 1);
                let mismatch = &report.value_mismatches()[0];
                assert_eq!(mismatch.name(), "gain");
                assert_eq!(
                    mismatch.reason(),
                    &ParameterValueInequivalenceReasonV1::FloatMismatch {
                        left: 0.5,
                        right: 0.5001,
                    }
                );
            }
        }
    }

    #[test]
    fn cross_type_mismatch_is_reported() {
        let a = profile(&[("x", "Float", "1.0")]);
        let b = profile(&[("x", "Integer", "1")]);
        match parameter_profiles_equivalent_v1(&a, &b) {
            ParameterProfileEquivalenceV1::Equivalent => panic!("expected NotEquivalent"),
            ParameterProfileEquivalenceV1::NotEquivalent(report) => {
                assert_eq!(report.value_mismatches().len(), 1);
                assert_eq!(
                    report.value_mismatches()[0].reason(),
                    &ParameterValueInequivalenceReasonV1::TypeMismatch {
                        left: AmiParameterTypeV1::Float,
                        right: AmiParameterTypeV1::Integer,
                    }
                );
            }
        }
    }

    #[test]
    fn empty_profiles_are_equivalent() {
        let a = BTreeMap::new();
        let b = BTreeMap::new();
        assert_eq!(
            parameter_profiles_equivalent_v1(&a, &b),
            ParameterProfileEquivalenceV1::Equivalent
        );
    }
}
