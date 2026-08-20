//! Typed AMI parameter profile merge core (P4B-02b74).
//!
//! Merges two assembled parameter profiles (`BTreeMap<String, AmiParameterValueV1>`,
//! e.g. produced by 02b44 assembly) using the typed value semantics of
//! `parameter_values_equivalent_v1` (02b70) instead of raw token equality:
//! shared names whose values are typed-equivalent (`0.5` vs `0.50`, `007` vs
//! `7`) merge as matched, shared names with typed-inequivalent values are a
//! conflict, and disjoint names carry over. This sits beside 02b48 profile
//! merge (raw `Eq` on tokens, so `0.5` vs `0.50` would conflict) as the
//! spelling-insensitive composition layer.
//!
//! Fail-closed: any typed-inequivalent shared name yields
//! `ConflictingValue` with the declared types and raw value tokens of both
//! sides; the merged map keeps the left profile's entry for matched names and
//! is deterministic (BTreeMap order).

use std::collections::BTreeMap;

use crate::{
    parameter_values_equivalent_v1, AmiParameterValueV1, ParameterValueEquivalenceV1,
};

/// Explicit scope policy of this slice: typed-value profile merge.
pub const PARAMETER_PROFILE_TYPED_MERGE_POLICY_V1: &str =
    "sipi.p4b-02b74.parameter-profile-typed-merge-v1.typed-value-merge";

/// Fail-closed error while merging two profiles under typed semantics.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterProfileTypedMergeErrorV1 {
    /// A shared name holds typed-inequivalent values (02b70 rules).
    ConflictingValue {
        name: String,
        old_type: String,
        old_value: String,
        new_type: String,
        new_value: String,
    },
}

/// Outcome of a fully successful typed profile merge.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ParameterProfileTypedMergeV1 {
    matched: usize,
    parameters: BTreeMap<String, AmiParameterValueV1>,
}

impl ParameterProfileTypedMergeV1 {
    /// Number of shared names merged as typed-equivalent.
    pub fn matched(&self) -> usize {
        self.matched
    }

    /// The merged profile (left entry kept for matched names).
    pub fn parameters(&self) -> &BTreeMap<String, AmiParameterValueV1> {
        &self.parameters
    }
}

/// Merge two parameter profiles under typed value semantics.
pub fn merge_parameter_profiles_typed_v1(
    left: &BTreeMap<String, AmiParameterValueV1>,
    right: &BTreeMap<String, AmiParameterValueV1>,
) -> Result<ParameterProfileTypedMergeV1, ParameterProfileTypedMergeErrorV1> {
    let mut parameters = BTreeMap::new();
    let mut matched = 0usize;
    for (name, old_value) in left {
        match right.get(name) {
            None => {
                parameters.insert(name.clone(), old_value.clone());
            }
            Some(new_value) => {
                match parameter_values_equivalent_v1(old_value, new_value) {
                    ParameterValueEquivalenceV1::Equivalent => {
                        parameters.insert(name.clone(), old_value.clone());
                        matched += 1;
                    }
                    ParameterValueEquivalenceV1::NotEquivalent(_) => {
                        return Err(ParameterProfileTypedMergeErrorV1::ConflictingValue {
                            name: name.clone(),
                            old_type: old_value.parameter_type().token().to_string(),
                            old_value: old_value.value_token().to_string(),
                            new_type: new_value.parameter_type().token().to_string(),
                            new_value: new_value.value_token().to_string(),
                        });
                    }
                }
            }
        }
    }
    for (name, new_value) in right {
        if !left.contains_key(name) {
            parameters.insert(name.clone(), new_value.clone());
        }
    }
    Ok(ParameterProfileTypedMergeV1 {
        matched,
        parameters,
    })
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
        let a = profile(&[("gain", "Float", "0.5")]);
        let b = profile(&[("steps", "Integer", "7")]);
        let result = merge_parameter_profiles_typed_v1(&a, &b).expect("merged");
        assert_eq!(result.matched(), 0);
        assert_eq!(result.parameters().len(), 2);
        assert!(result.parameters().contains_key("gain"));
        assert!(result.parameters().contains_key("steps"));
    }

    #[test]
    fn typed_equivalent_spellings_merge_as_matched() {
        let a = profile(&[("gain", "Float", "0.5")]);
        let b = profile(&[("gain", "Float", "0.50")]);
        let result = merge_parameter_profiles_typed_v1(&a, &b).expect("merged");
        assert_eq!(result.matched(), 1);
        assert_eq!(result.parameters().len(), 1);
        assert_eq!(result.parameters()["gain"].value_token(), "0.5");
    }

    #[test]
    fn integer_spelling_variants_merge_as_matched() {
        let a = profile(&[("steps", "Integer", "007")]);
        let b = profile(&[("steps", "Integer", "7")]);
        let result = merge_parameter_profiles_typed_v1(&a, &b).expect("merged");
        assert_eq!(result.matched(), 1);
        assert_eq!(result.parameters().len(), 1);
    }

    #[test]
    fn typed_conflict_is_reported() {
        let a = profile(&[("gain", "Float", "0.5")]);
        let b = profile(&[("gain", "Float", "0.5001")]);
        match merge_parameter_profiles_typed_v1(&a, &b) {
            Ok(_) => panic!("expected conflict"),
            Err(ParameterProfileTypedMergeErrorV1::ConflictingValue {
                name,
                old_type,
                old_value,
                new_type,
                new_value,
            }) => {
                assert_eq!(name, "gain");
                assert_eq!(old_type, "Float");
                assert_eq!(old_value, "0.5");
                assert_eq!(new_type, "Float");
                assert_eq!(new_value, "0.5001");
            }
        }
    }

    #[test]
    fn cross_type_conflict_is_reported() {
        let a = profile(&[("x", "Float", "1.0")]);
        let b = profile(&[("x", "Integer", "1")]);
        match merge_parameter_profiles_typed_v1(&a, &b) {
            Ok(_) => panic!("expected conflict"),
            Err(ParameterProfileTypedMergeErrorV1::ConflictingValue {
                name,
                old_type,
                new_type,
                ..
            }) => {
                assert_eq!(name, "x");
                assert_eq!(old_type, "Float");
                assert_eq!(new_type, "Integer");
            }
        }
    }

    #[test]
    fn empty_profiles_merge() {
        let a = BTreeMap::new();
        let b = BTreeMap::new();
        let result = merge_parameter_profiles_typed_v1(&a, &b).expect("merged");
        assert_eq!(result.matched(), 0);
        assert!(result.parameters().is_empty());
    }
}
