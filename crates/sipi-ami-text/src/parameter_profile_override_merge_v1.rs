//! Typed AMI parameter profile override merge core (P4B-02b76).
//!
//! Merges two assembled parameter profiles (`BTreeMap<String, AmiParameterValueV1>`,
//! e.g. produced by 02b44 assembly) with override semantics under the typed
//! value rules of `parameter_values_equivalent_v1` (02b70): shared names whose
//! values are typed-equivalent (`0.5` vs `0.50`) keep the base entry and count
//! as matched; shared names with typed-inequivalent values are overridden by
//! the second profile and counted as overridden; disjoint names carry over.
//! This is the lenient companion of 02b74 strict typed merge (which fails
//! closed on conflict) and of 02b48 raw-token merge: the natural layering of
//! an explicit override profile over a defaults profile.
//!
//! Fail-closed by construction: the merge is total (no error path), typed
//! equivalence is computed by 02b70, and the resulting map is deterministic
//! (BTreeMap order; base entries kept for matched names).

use std::collections::BTreeMap;

use crate::{parameter_values_equivalent_v1, AmiParameterValueV1, ParameterValueEquivalenceV1};

/// Explicit scope policy of this slice: typed override merge of profiles.
pub const PARAMETER_PROFILE_OVERRIDE_MERGE_POLICY_V1: &str =
    "sipi.p4b-02b76.parameter-profile-override-merge-v1.typed-override-merge";

/// Outcome of a typed override merge.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ParameterProfileOverrideMergeV1 {
    matched: usize,
    overridden: usize,
    parameters: BTreeMap<String, AmiParameterValueV1>,
}

impl ParameterProfileOverrideMergeV1 {
    /// Shared names merged as typed-equivalent (base entry kept).
    pub fn matched(&self) -> usize {
        self.matched
    }

    /// Shared names overridden by the second profile (typed-inequivalent).
    pub fn overridden(&self) -> usize {
        self.overridden
    }

    /// The merged profile.
    pub fn parameters(&self) -> &BTreeMap<String, AmiParameterValueV1> {
        &self.parameters
    }
}

/// Merge `override_profile` over `base` under typed value semantics.
pub fn merge_parameter_profiles_with_override_v1(
    base: &BTreeMap<String, AmiParameterValueV1>,
    override_profile: &BTreeMap<String, AmiParameterValueV1>,
) -> ParameterProfileOverrideMergeV1 {
    let mut parameters = BTreeMap::new();
    let mut matched = 0usize;
    let mut overridden = 0usize;
    for (name, base_value) in base {
        match override_profile.get(name) {
            None => {
                parameters.insert(name.clone(), base_value.clone());
            }
            Some(override_value) => {
                match parameter_values_equivalent_v1(base_value, override_value) {
                    ParameterValueEquivalenceV1::Equivalent => {
                        parameters.insert(name.clone(), base_value.clone());
                        matched += 1;
                    }
                    ParameterValueEquivalenceV1::NotEquivalent(_) => {
                        parameters.insert(name.clone(), override_value.clone());
                        overridden += 1;
                    }
                }
            }
        }
    }
    for (name, override_value) in override_profile {
        if !base.contains_key(name) {
            parameters.insert(name.clone(), override_value.clone());
        }
    }
    ParameterProfileOverrideMergeV1 {
        matched,
        overridden,
        parameters,
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
    fn disjoint_profiles_merge() {
        let base = profile(&[("gain", "Float", "0.5")]);
        let override_profile = profile(&[("steps", "Integer", "7")]);
        let result = merge_parameter_profiles_with_override_v1(&base, &override_profile);
        assert_eq!(result.matched(), 0);
        assert_eq!(result.overridden(), 0);
        assert_eq!(result.parameters().len(), 2);
        assert!(result.parameters().contains_key("gain"));
        assert!(result.parameters().contains_key("steps"));
    }

    #[test]
    fn typed_equivalent_shared_names_keep_base() {
        let base = profile(&[("gain", "Float", "0.5")]);
        let override_profile = profile(&[("gain", "Float", "0.50")]);
        let result = merge_parameter_profiles_with_override_v1(&base, &override_profile);
        assert_eq!(result.matched(), 1);
        assert_eq!(result.overridden(), 0);
        assert_eq!(result.parameters().len(), 1);
        assert_eq!(result.parameters()["gain"].value_token(), "0.5");
    }

    #[test]
    fn typed_conflict_is_overridden() {
        let base = profile(&[("gain", "Float", "0.5")]);
        let override_profile = profile(&[("gain", "Float", "0.5001")]);
        let result = merge_parameter_profiles_with_override_v1(&base, &override_profile);
        assert_eq!(result.matched(), 0);
        assert_eq!(result.overridden(), 1);
        assert_eq!(result.parameters().len(), 1);
        assert_eq!(result.parameters()["gain"].value_token(), "0.5001");
    }

    #[test]
    fn cross_type_conflict_is_overridden() {
        let base = profile(&[("x", "Float", "1.0")]);
        let override_profile = profile(&[("x", "Integer", "1")]);
        let result = merge_parameter_profiles_with_override_v1(&base, &override_profile);
        assert_eq!(result.matched(), 0);
        assert_eq!(result.overridden(), 1);
        assert_eq!(result.parameters()["x"].parameter_type().token(), "Integer");
        assert_eq!(result.parameters()["x"].value_token(), "1");
    }

    #[test]
    fn empty_profiles_merge() {
        let base = BTreeMap::new();
        let override_profile = BTreeMap::new();
        let result = merge_parameter_profiles_with_override_v1(&base, &override_profile);
        assert_eq!(result.matched(), 0);
        assert_eq!(result.overridden(), 0);
        assert!(result.parameters().is_empty());
    }

    #[test]
    fn matched_plus_overridden_counts() {
        let base = profile(&[
            ("a", "Float", "0.5"),
            ("b", "Integer", "7"),
            ("c", "Boolean", "True"),
        ]);
        let override_profile = profile(&[
            ("a", "Float", "0.50"),
            ("b", "Integer", "8"),
            ("d", "String", "S"),
        ]);
        let result = merge_parameter_profiles_with_override_v1(&base, &override_profile);
        assert_eq!(result.matched(), 1);
        assert_eq!(result.overridden(), 1);
        assert_eq!(result.parameters().len(), 4);
        assert_eq!(result.parameters()["a"].value_token(), "0.5");
        assert_eq!(result.parameters()["b"].value_token(), "8");
        assert_eq!(result.parameters()["c"].value_token(), "True");
        assert_eq!(result.parameters()["d"].value_token(), "S");
        assert_eq!(result.matched() + result.overridden(), 2);
    }
}
