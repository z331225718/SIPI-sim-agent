//! AMI parameter profile canonicalization core (P4B-02b77).
//!
//! Produces the canonical form of an assembled parameter profile
//! (`BTreeMap<String, AmiParameterValueV1>`, e.g. produced by 02b44 assembly)
//! by applying `canonicalize_parameter_value_spelling_v1` (02b75) to every
//! entry: Integer spellings become the parsed i64 in decimal (`007` -> `7`),
//! List spellings get trimmed items joined with `", "` (`(a,b,c)` ->
//! `(a, b, c)`), and Boolean/Float/String stay raw. This is the
//! profile-map-level companion of 02b75: a stable spelling key for a whole
//! profile without float formatting.
//!
//! Fail-closed: canonical spellings are rebuilt through
//! `AmiParameterValueV1::try_new` (always valid for canonical Integer/List
//! forms); a defensive fallback keeps the original entry rather than
//! panicking. The canonicalized count reports how many entries changed.

use std::collections::BTreeMap;

use crate::{AmiParameterValueV1, canonicalize_parameter_value_spelling_v1};

/// Explicit scope policy of this slice: canonical spelling of a whole profile.
pub const PARAMETER_PROFILE_CANONICALIZATION_POLICY_V1: &str =
    "sipi.p4b-02b77.parameter-profile-canonicalization-v1.canonical-profile";

/// Outcome of canonicalizing one parameter profile.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ParameterProfileCanonicalizationV1 {
    entries: usize,
    canonicalized: usize,
    parameters: BTreeMap<String, AmiParameterValueV1>,
}

impl ParameterProfileCanonicalizationV1 {
    /// Total number of profile entries.
    pub fn entries(&self) -> usize {
        self.entries
    }

    /// Number of entries whose value spelling changed.
    pub fn canonicalized(&self) -> usize {
        self.canonicalized
    }

    /// The canonicalized profile.
    pub fn parameters(&self) -> &BTreeMap<String, AmiParameterValueV1> {
        &self.parameters
    }
}

/// Canonicalize every value spelling of an assembled parameter profile.
pub fn canonicalize_parameter_profile_v1(
    profile: &BTreeMap<String, AmiParameterValueV1>,
) -> ParameterProfileCanonicalizationV1 {
    let mut canonicalized = 0usize;
    let mut parameters = BTreeMap::new();
    for (name, value) in profile {
        let canonical = canonicalize_parameter_value_spelling_v1(value);
        if canonical != value.value_token() {
            canonicalized += 1;
        }
        match AmiParameterValueV1::try_new(name, value.parameter_type().token(), &canonical) {
            Ok(rebuild) => {
                parameters.insert(name.clone(), rebuild);
            }
            Err(_) => {
                parameters.insert(name.clone(), value.clone());
            }
        }
    }
    ParameterProfileCanonicalizationV1 {
        entries: profile.len(),
        canonicalized,
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
    fn integer_entries_are_canonicalized() {
        let p = profile(&[("steps", "Integer", "007"), ("other", "Integer", "-0")]);
        let result = canonicalize_parameter_profile_v1(&p);
        assert_eq!(result.entries(), 2);
        assert_eq!(result.canonicalized(), 2);
        assert_eq!(result.parameters()["steps"].value_token(), "7");
        assert_eq!(result.parameters()["other"].value_token(), "0");
    }

    #[test]
    fn list_entries_are_canonicalized() {
        let p = profile(&[("channels", "List", "( a , b , c )")]);
        let result = canonicalize_parameter_profile_v1(&p);
        assert_eq!(result.canonicalized(), 1);
        assert_eq!(result.parameters()["channels"].value_token(), "(a, b, c)");
    }

    #[test]
    fn float_string_boolean_stay_raw() {
        let p = profile(&[
            ("gain", "Float", "0.50"),
            ("mode", "String", "Linear "),
            ("on", "Boolean", "True"),
        ]);
        let result = canonicalize_parameter_profile_v1(&p);
        assert_eq!(result.canonicalized(), 0);
        assert_eq!(result.parameters()["gain"].value_token(), "0.50");
        assert_eq!(result.parameters()["mode"].value_token(), "Linear ");
        assert_eq!(result.parameters()["on"].value_token(), "True");
    }

    #[test]
    fn canonicalized_count_tracks_changes() {
        let p = profile(&[
            ("steps", "Integer", "007"),
            ("channels", "List", "(a,b)"),
            ("gain", "Float", "1.25"),
        ]);
        let result = canonicalize_parameter_profile_v1(&p);
        assert_eq!(result.entries(), 3);
        assert_eq!(result.canonicalized(), 2);
    }

    #[test]
    fn empty_profile_is_empty() {
        let p = BTreeMap::new();
        let result = canonicalize_parameter_profile_v1(&p);
        assert_eq!(result.entries(), 0);
        assert_eq!(result.canonicalized(), 0);
        assert!(result.parameters().is_empty());
    }

    #[test]
    fn canonicalization_is_idempotent() {
        let p = profile(&[
            ("steps", "Integer", "007"),
            ("channels", "List", "( a , b )"),
            ("gain", "Float", "0.50"),
        ]);
        let first = canonicalize_parameter_profile_v1(&p);
        let second = canonicalize_parameter_profile_v1(first.parameters());
        assert_eq!(first.parameters(), second.parameters());
        assert_eq!(second.canonicalized(), 0);
    }
}
