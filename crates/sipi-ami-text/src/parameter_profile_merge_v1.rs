//! AMI parameter profile merge core (P4B-02b48).
//!
//! Merges two assembled parameter maps (leaf name -> `AmiParameterValueV1`)
//! into one conflict-free map: names present in only one map are taken from it;
//! names present in both with identical values are taken once (matched); names
//! present in both with different values are a conflict and fail closed. This
//! is the combination primitive for assembled profiles (P4B-02b44), e.g. a base
//! profile plus an override map.

use std::collections::BTreeMap;

use crate::AmiParameterValueV1;

/// Scope policy for the parameter profile merge core.
pub const PARAMETER_PROFILE_MERGE_POLICY_V1: &str =
    "sipi.p4b-02b48.parameter-profile-merge-v1.conflict-free-merge";

/// Fail-closed errors during parameter profile merge.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterProfileMergeErrorV1 {
    /// A name exists in both maps with different values (type or value token).
    ConflictingValue {
        name: String,
        old_type: String,
        old_value: String,
        new_type: String,
        new_value: String,
    },
}

/// Outcome of a successful profile merge pass.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ParameterProfileMergeV1 {
    matched: usize,
    parameters: BTreeMap<String, AmiParameterValueV1>,
}

impl ParameterProfileMergeV1 {
    pub fn matched(&self) -> usize {
        self.matched
    }

    pub fn parameters(&self) -> &BTreeMap<String, AmiParameterValueV1> {
        &self.parameters
    }
}

/// Merge `a` and `b` into one conflict-free parameter map.
///
/// Names in only one map are taken from it; identical same-name entries are
/// taken once (counted as matched); different same-name entries fail closed
/// with the old (a) and new (b) type/value records.
pub fn merge_parameter_profiles_v1(
    a: &BTreeMap<String, AmiParameterValueV1>,
    b: &BTreeMap<String, AmiParameterValueV1>,
) -> Result<ParameterProfileMergeV1, ParameterProfileMergeErrorV1> {
    let mut parameters = BTreeMap::new();
    let mut matched = 0usize;
    for (name, old_value) in a {
        match b.get(name) {
            None => {
                parameters.insert(name.clone(), old_value.clone());
            }
            Some(new_value) if new_value == old_value => {
                parameters.insert(name.clone(), old_value.clone());
                matched += 1;
            }
            Some(new_value) => {
                return Err(ParameterProfileMergeErrorV1::ConflictingValue {
                    name: name.clone(),
                    old_type: old_value.parameter_type().token().to_string(),
                    old_value: old_value.value_token().to_string(),
                    new_type: new_value.parameter_type().token().to_string(),
                    new_value: new_value.value_token().to_string(),
                });
            }
        }
    }
    for (name, new_value) in b {
        if !a.contains_key(name) {
            parameters.insert(name.clone(), new_value.clone());
        }
    }
    Ok(ParameterProfileMergeV1 {
        matched,
        parameters,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

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
    fn disjoint_maps_merge() {
        let a = profile(&[("gain", "Float", "0.5")]);
        let b = profile(&[("steps", "Integer", "7")]);
        let result = merge_parameter_profiles_v1(&a, &b).expect("merged");
        assert_eq!(result.matched(), 0);
        assert_eq!(result.parameters().len(), 2);
        assert!(result.parameters().contains_key("gain"));
        assert!(result.parameters().contains_key("steps"));
    }

    #[test]
    fn identical_overlap_counts_as_matched() {
        let a = profile(&[("gain", "Float", "0.5")]);
        let b = profile(&[("gain", "Float", "0.5")]);
        let result = merge_parameter_profiles_v1(&a, &b).expect("merged");
        assert_eq!(result.matched(), 1);
        assert_eq!(result.parameters().len(), 1);
        assert_eq!(result.parameters().get("gain").expect("gain").value_token(), "0.5");
    }

    #[test]
    fn value_conflict_fails_closed() {
        let a = profile(&[("gain", "Float", "0.5")]);
        let b = profile(&[("gain", "Float", "1.25")]);
        let error = merge_parameter_profiles_v1(&a, &b).unwrap_err();
        assert_eq!(
            error,
            ParameterProfileMergeErrorV1::ConflictingValue {
                name: "gain".to_string(),
                old_type: "Float".to_string(),
                old_value: "0.5".to_string(),
                new_type: "Float".to_string(),
                new_value: "1.25".to_string(),
            }
        );
    }

    #[test]
    fn type_conflict_fails_closed() {
        let a = profile(&[("gain", "Float", "0.5")]);
        let b = profile(&[("gain", "String", "0.5")]);
        let error = merge_parameter_profiles_v1(&a, &b).unwrap_err();
        assert_eq!(
            error,
            ParameterProfileMergeErrorV1::ConflictingValue {
                name: "gain".to_string(),
                old_type: "Float".to_string(),
                old_value: "0.5".to_string(),
                new_type: "String".to_string(),
                new_value: "0.5".to_string(),
            }
        );
    }

    #[test]
    fn empty_a_takes_all_of_b() {
        let a = profile(&[]);
        let b = profile(&[("gain", "Float", "0.5"), ("steps", "Integer", "7")]);
        let result = merge_parameter_profiles_v1(&a, &b).expect("merged");
        assert_eq!(result.parameters().len(), 2);
        assert_eq!(result.matched(), 0);
    }

    #[test]
    fn mixed_merge_reports_correct_counts() {
        let a = profile(&[
            ("gain", "Float", "0.5"),
            ("steps", "Integer", "7"),
            ("mode", "String", "fast"),
        ]);
        let b = profile(&[
            ("gain", "Float", "0.5"),
            ("enabled", "Boolean", "True"),
        ]);
        let result = merge_parameter_profiles_v1(&a, &b).expect("merged");
        assert_eq!(result.matched(), 1);
        assert_eq!(result.parameters().len(), 4);
    }
}
