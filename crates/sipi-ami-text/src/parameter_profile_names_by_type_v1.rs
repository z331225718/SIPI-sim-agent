//! AMI parameter profile names-by-type core (P4B-02b86).
//!
//! Lists every name in an assembled parameter profile (`BTreeMap<String,
//! AmiParameterValueV1>`, e.g. produced by 02b44 assembly) whose entry carries
//! a given declared type token: `list_parameter_profile_names_by_type_v1`
//! returns the sorted names for Float, Integer, Boolean, String, or List. This
//! is the name-list companion of 02b73 type statistics (which counts entries
//! by type) and of 02b80 value lookup (which finds names by typed value).
//!
//! Fail-closed: a type token that is not one of the five product variants
//! yields `UnknownTypeToken`; names come back in deterministic sorted order
//! (BTreeMap iteration); an empty profile or a type with no matches yields an
//! empty list.

use std::collections::BTreeMap;

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: names by declared type in profiles.
pub const PARAMETER_PROFILE_NAMES_BY_TYPE_POLICY_V1: &str =
    "sipi.p4b-02b86.parameter-profile-names-by-type-v1.names-by-declared-type";

/// Fail-closed error while listing profile names by declared type.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterProfileNamesByTypeErrorV1 {
    /// The type token is not one of Float/Integer/Boolean/String/List.
    UnknownTypeToken,
}

/// Outcome of listing profile names by declared type.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ParameterProfileNamesByTypeV1 {
    names: Vec<String>,
}

impl ParameterProfileNamesByTypeV1 {
    /// Sorted names of entries with the requested declared type.
    pub fn names(&self) -> &[String] {
        &self.names
    }

    /// Number of matching names.
    pub fn count(&self) -> usize {
        self.names.len()
    }
}

/// List every profile name whose entry has the given declared type.
pub fn list_parameter_profile_names_by_type_v1(
    profile: &BTreeMap<String, AmiParameterValueV1>,
    type_token: &str,
) -> Result<ParameterProfileNamesByTypeV1, ParameterProfileNamesByTypeErrorV1> {
    let parameter_type = AmiParameterTypeV1::from_token(type_token)
        .ok_or(ParameterProfileNamesByTypeErrorV1::UnknownTypeToken)?;
    let mut names = Vec::new();
    for (name, parameter) in profile {
        if parameter.parameter_type() == parameter_type {
            names.push(name.clone());
        }
    }
    Ok(ParameterProfileNamesByTypeV1 { names })
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
    fn lists_float_names() {
        let p = profile(&[
            ("gain", "Float", "0.5"),
            ("steps", "Integer", "7"),
            ("offset", "Float", "1.25"),
        ]);
        let result = list_parameter_profile_names_by_type_v1(&p, "Float").expect("float");
        assert_eq!(result.names(), &["gain".to_string(), "offset".to_string()]);
        assert_eq!(result.count(), 2);
    }

    #[test]
    fn names_come_back_sorted() {
        let p = profile(&[
            ("zeta", "Integer", "3"),
            ("alpha", "Integer", "1"),
            ("beta", "Integer", "2"),
        ]);
        let result = list_parameter_profile_names_by_type_v1(&p, "Integer").expect("integer");
        assert_eq!(
            result.names(),
            &["alpha".to_string(), "beta".to_string(), "zeta".to_string()]
        );
    }

    #[test]
    fn no_matches_returns_empty() {
        let p = profile(&[("gain", "Float", "0.5")]);
        let result = list_parameter_profile_names_by_type_v1(&p, "Integer").expect("integer");
        assert!(result.names().is_empty());
        assert_eq!(result.count(), 0);
    }

    #[test]
    fn unknown_type_fails_closed() {
        let p = profile(&[("gain", "Float", "0.5")]);
        assert_eq!(
            list_parameter_profile_names_by_type_v1(&p, "Nope"),
            Err(ParameterProfileNamesByTypeErrorV1::UnknownTypeToken)
        );
        assert_eq!(
            list_parameter_profile_names_by_type_v1(&p, "float"),
            Err(ParameterProfileNamesByTypeErrorV1::UnknownTypeToken)
        );
    }

    #[test]
    fn boolean_string_list_names() {
        let p = profile(&[
            ("on", "Boolean", "True"),
            ("mode", "String", "Linear"),
            ("channels", "List", "(a, b)"),
        ]);
        assert_eq!(
            list_parameter_profile_names_by_type_v1(&p, "Boolean").expect("bool").names(),
            &["on".to_string()]
        );
        assert_eq!(
            list_parameter_profile_names_by_type_v1(&p, "String").expect("str").names(),
            &["mode".to_string()]
        );
        assert_eq!(
            list_parameter_profile_names_by_type_v1(&p, "List").expect("list").names(),
            &["channels".to_string()]
        );
    }

    #[test]
    fn empty_profile_returns_empty() {
        let p = BTreeMap::new();
        let result = list_parameter_profile_names_by_type_v1(&p, "Float").expect("float");
        assert!(result.names().is_empty());
    }
}
