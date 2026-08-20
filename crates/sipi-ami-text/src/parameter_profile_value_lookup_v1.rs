//! AMI parameter profile value reverse lookup core (P4B-02b80).
//!
//! Finds every name in an assembled parameter profile (`BTreeMap<String,
//! AmiParameterValueV1>`, e.g. produced by 02b44 assembly) whose entry is
//! typed-equivalent to a caller-supplied query value under
//! `parameter_values_equivalent_v1` (02b70). This is the reverse direction of
//! 02b69 profile apply (name -> value): value -> names, useful for detecting
//! semantically duplicate entries regardless of spelling (`0.5` vs `0.50`).
//! The query name is identity-only and never matched (names are compared at
//! the map-key level elsewhere, as in 02b47/02b71).
//!
//! Fail-closed: a query that fails `AmiParameterValueV1::try_new` (02b1)
//! yields `InvalidQueryValue`; matches come back in deterministic sorted
//! order (BTreeMap iteration).

use std::collections::BTreeMap;

use crate::{
    parameter_values_equivalent_v1, AmiParameterValueErrorV1, AmiParameterValueV1,
    ParameterValueEquivalenceV1,
};

/// Explicit scope policy of this slice: typed reverse lookup in profiles.
pub const PARAMETER_PROFILE_VALUE_LOOKUP_POLICY_V1: &str =
    "sipi.p4b-02b80.parameter-profile-value-lookup-v1.typed-value-reverse-lookup";

/// Fail-closed error while building the query value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterProfileValueLookupErrorV1 {
    /// The query value violates the P4B-02b1 value rules.
    InvalidQueryValue(AmiParameterValueErrorV1),
}

/// Outcome of a typed reverse lookup over a profile.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ParameterProfileValueLookupV1 {
    matches: Vec<String>,
}

impl ParameterProfileValueLookupV1 {
    /// Sorted names whose entries are typed-equivalent to the query.
    pub fn matches(&self) -> &[String] {
        &self.matches
    }

    /// Number of matching names.
    pub fn match_count(&self) -> usize {
        self.matches.len()
    }
}

/// Find every profile name whose entry is typed-equivalent to the query.
pub fn find_parameter_profile_names_by_value_v1(
    profile: &BTreeMap<String, AmiParameterValueV1>,
    query_name: &str,
    query_type_token: &str,
    query_value_token: &str,
) -> Result<ParameterProfileValueLookupV1, ParameterProfileValueLookupErrorV1> {
    let query = AmiParameterValueV1::try_new(query_name, query_type_token, query_value_token)
        .map_err(ParameterProfileValueLookupErrorV1::InvalidQueryValue)?;
    let mut matches = Vec::new();
    for (entry_name, entry) in profile {
        if parameter_values_equivalent_v1(&query, entry)
            == ParameterValueEquivalenceV1::Equivalent
        {
            matches.push(entry_name.clone());
        }
    }
    Ok(ParameterProfileValueLookupV1 { matches })
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
    fn finds_matching_float_spelling() {
        let p = profile(&[("gain", "Float", "0.50"), ("steps", "Integer", "7")]);
        let result = find_parameter_profile_names_by_value_v1(&p, "q", "Float", "0.5")
            .expect("lookup");
        assert_eq!(result.matches(), &["gain".to_string()]);
        assert_eq!(result.match_count(), 1);
    }

    #[test]
    fn no_match_returns_empty() {
        let p = profile(&[("gain", "Float", "0.5")]);
        let result =
            find_parameter_profile_names_by_value_v1(&p, "q", "Float", "0.5001").expect("lookup");
        assert!(result.matches().is_empty());
        assert_eq!(result.match_count(), 0);
    }

    #[test]
    fn multiple_matches_come_back_sorted() {
        let p = profile(&[
            ("b", "Integer", "007"),
            ("a", "Integer", "7"),
            ("c", "Integer", "8"),
        ]);
        let result = find_parameter_profile_names_by_value_v1(&p, "q", "Integer", "7")
            .expect("lookup");
        assert_eq!(result.matches(), &["a".to_string(), "b".to_string()]);
    }

    #[test]
    fn cross_type_never_matches() {
        let p = profile(&[("x", "Float", "1.0")]);
        let result = find_parameter_profile_names_by_value_v1(&p, "q", "Integer", "1")
            .expect("lookup");
        assert!(result.matches().is_empty());
    }

    #[test]
    fn invalid_query_fails_closed() {
        let p = profile(&[("gain", "Float", "0.5")]);
        match find_parameter_profile_names_by_value_v1(&p, "q", "Float", "abc") {
            Ok(_) => panic!("expected InvalidQueryValue"),
            Err(ParameterProfileValueLookupErrorV1::InvalidQueryValue(error)) => {
                assert_eq!(error, AmiParameterValueErrorV1::InvalidFloat);
            }
        }
    }

    #[test]
    fn empty_profile_never_matches() {
        let p = BTreeMap::new();
        let result = find_parameter_profile_names_by_value_v1(&p, "q", "Float", "0.5")
            .expect("lookup");
        assert!(result.matches().is_empty());
    }
}
