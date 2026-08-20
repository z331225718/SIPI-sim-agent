//! AMI parameter profile typed subset check core (P4B-02b90).
//!
//! Checks whether one assembled parameter profile (`BTreeMap<String,
//! AmiParameterValueV1>`, e.g. produced by 02b44 assembly) is a typed subset
//! of another under `parameter_values_equivalent_v1` (02b70):
//! `check_parameter_profile_typed_subset_v1` reports whether every entry of
//! the subset profile is present in the superset profile under the same name
//! with a typed-equivalent value (spelling-insensitive, `0.5` vs `0.50`).
//! This is the subset-direction companion of 02b71 exact profile equivalence
//! and of 02b79 typed diff: compatibility of a profile against a superset.
//!
//! Fail-closed: names present in the subset but missing in the superset are
//! reported sorted as `missing`; shared names with typed-inequivalent values
//! are reported sorted as `mismatched` (name + typed reason); `is_subset()`
//! is true exactly when both lists are empty; the check is total (no error
//! path) and deterministic.

use std::collections::BTreeMap;

use crate::{
    parameter_values_equivalent_v1, AmiParameterValueV1, ParameterValueEquivalenceV1,
    ParameterValueInequivalenceReasonV1,
};

/// Explicit scope policy of this slice: typed subset check of profiles.
pub const PARAMETER_PROFILE_TYPED_SUBSET_POLICY_V1: &str =
    "sipi.p4b-02b90.parameter-profile-typed-subset-v1.typed-subset-check";

/// One shared-name typed mismatch with its typed reason.
#[derive(Clone, Debug, PartialEq)]
pub struct ParameterProfileTypedSubsetMismatchV1 {
    name: String,
    reason: ParameterValueInequivalenceReasonV1,
}

impl ParameterProfileTypedSubsetMismatchV1 {
    pub fn name(&self) -> &str {
        &self.name
    }

    pub fn reason(&self) -> &ParameterValueInequivalenceReasonV1 {
        &self.reason
    }
}

/// Outcome of a typed subset check between two profiles.
#[derive(Clone, Debug, PartialEq)]
pub struct ParameterProfileTypedSubsetV1 {
    subset: bool,
    missing: Vec<String>,
    mismatched: Vec<ParameterProfileTypedSubsetMismatchV1>,
}

impl ParameterProfileTypedSubsetV1 {
    /// True when every subset entry is present and typed-equivalent.
    pub fn is_subset(&self) -> bool {
        self.subset
    }

    /// Sorted subset names missing from the superset.
    pub fn missing(&self) -> &[String] {
        &self.missing
    }

    /// Sorted (by name) shared names with typed-inequivalent values.
    pub fn mismatched(&self) -> &[ParameterProfileTypedSubsetMismatchV1] {
        &self.mismatched
    }
}

/// Check whether `subset` is a typed subset of `superset`.
pub fn check_parameter_profile_typed_subset_v1(
    subset: &BTreeMap<String, AmiParameterValueV1>,
    superset: &BTreeMap<String, AmiParameterValueV1>,
) -> ParameterProfileTypedSubsetV1 {
    let mut missing = Vec::new();
    let mut mismatched = Vec::new();
    for (name, subset_value) in subset {
        match superset.get(name) {
            None => {
                missing.push(name.clone());
            }
            Some(superset_value) => {
                match parameter_values_equivalent_v1(subset_value, superset_value) {
                    ParameterValueEquivalenceV1::Equivalent => {}
                    ParameterValueEquivalenceV1::NotEquivalent(reason) => {
                        mismatched.push(ParameterProfileTypedSubsetMismatchV1 {
                            name: name.clone(),
                            reason,
                        });
                    }
                }
            }
        }
    }
    let subset = missing.is_empty() && mismatched.is_empty();
    ParameterProfileTypedSubsetV1 {
        subset,
        missing,
        mismatched,
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
    fn true_subset_is_reported() {
        let subset = profile(&[("gain", "Float", "0.5")]);
        let superset = profile(&[
            ("gain", "Float", "0.5"),
            ("steps", "Integer", "7"),
        ]);
        let result = check_parameter_profile_typed_subset_v1(&subset, &superset);
        assert!(result.is_subset());
        assert!(result.missing().is_empty());
        assert!(result.mismatched().is_empty());
    }

    #[test]
    fn spelling_variants_still_subset() {
        let subset = profile(&[("gain", "Float", "0.5")]);
        let superset = profile(&[("gain", "Float", "0.50")]);
        let result = check_parameter_profile_typed_subset_v1(&subset, &superset);
        assert!(result.is_subset());
    }

    #[test]
    fn missing_name_breaks_subset() {
        let subset = profile(&[("gain", "Float", "0.5"), ("nope", "Float", "1.0")]);
        let superset = profile(&[("gain", "Float", "0.5")]);
        let result = check_parameter_profile_typed_subset_v1(&subset, &superset);
        assert!(!result.is_subset());
        assert_eq!(result.missing(), &["nope".to_string()]);
        assert!(result.mismatched().is_empty());
    }

    #[test]
    fn mismatched_value_breaks_subset() {
        let subset = profile(&[("gain", "Float", "0.5")]);
        let superset = profile(&[("gain", "Float", "0.5001")]);
        let result = check_parameter_profile_typed_subset_v1(&subset, &superset);
        assert!(!result.is_subset());
        assert!(result.missing().is_empty());
        assert_eq!(result.mismatched().len(), 1);
        assert_eq!(result.mismatched()[0].name(), "gain");
    }

    #[test]
    fn empty_subset_is_subset() {
        let subset = BTreeMap::new();
        let superset = profile(&[("gain", "Float", "0.5")]);
        let result = check_parameter_profile_typed_subset_v1(&subset, &superset);
        assert!(result.is_subset());
    }

    #[test]
    fn cross_type_mismatch_is_reported() {
        let subset = profile(&[("x", "Float", "1.0")]);
        let superset = profile(&[("x", "Integer", "1")]);
        let result = check_parameter_profile_typed_subset_v1(&subset, &superset);
        assert!(!result.is_subset());
        assert_eq!(result.mismatched().len(), 1);
        assert_eq!(result.mismatched()[0].name(), "x");
    }
}
