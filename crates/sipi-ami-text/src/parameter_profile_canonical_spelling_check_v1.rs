//! AMI parameter profile canonical spelling check core (P4B-02b95).
//!
//! Checks whether every entry of an assembled parameter profile (`BTreeMap<String,
//! AmiParameterValueV1>`, e.g. produced by 02b44 assembly) already carries its
//! canonical value spelling (`canonicalize_parameter_value_spelling_v1`, 02b75):
//! `check_parameter_profile_spellings_canonical_v1` compares each entry's raw
//! value token to its canonical spelling (Integer `007` -> `7`, List
//! `(a,b,c)` -> `(a, b, c)`; Float and String stay raw and are never flagged)
//! and reports each non-canonical entry with its name, declared type, raw
//! value, and canonical value. This is the profile-level companion of 02b77
//! profile canonicalization (which rewrites) and the parallel of 02b94's tree
//! leaf check: the gate before canonicalizing a profile.
//!
//! Fail-closed: the check is total (no error path); issues come back in
//! deterministic sorted (name) order; `canonical()` is true exactly when no
//! non-canonical entry was found.

use std::collections::BTreeMap;

use crate::{AmiParameterValueV1, canonicalize_parameter_value_spelling_v1};

/// Explicit scope policy of this slice: canonical profile spelling check.
pub const PARAMETER_PROFILE_CANONICAL_SPELLING_CHECK_POLICY_V1: &str =
    "sipi.p4b-02b95.parameter-profile-canonical-spelling-check-v1.canonical-profile-spelling-check";

/// One non-canonical profile entry with its canonical value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ParameterProfileCanonicalSpellingIssueV1 {
    name: String,
    type_token: String,
    value_token: String,
    canonical: String,
}

impl ParameterProfileCanonicalSpellingIssueV1 {
    pub fn name(&self) -> &str {
        &self.name
    }

    pub fn type_token(&self) -> &str {
        &self.type_token
    }

    pub fn value_token(&self) -> &str {
        &self.value_token
    }

    pub fn canonical(&self) -> &str {
        &self.canonical
    }
}

/// Outcome of the canonical spelling check over a profile.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ParameterProfileCanonicalSpellingCheckV1 {
    entries: usize,
    non_canonical: Vec<ParameterProfileCanonicalSpellingIssueV1>,
}

impl ParameterProfileCanonicalSpellingCheckV1 {
    /// Total number of profile entries.
    pub fn entries(&self) -> usize {
        self.entries
    }

    /// Sorted (by name) non-canonical entries.
    pub fn non_canonical(&self) -> &[ParameterProfileCanonicalSpellingIssueV1] {
        &self.non_canonical
    }

    /// True when every entry is canonical.
    pub fn canonical(&self) -> bool {
        self.non_canonical.is_empty()
    }
}

/// Check the canonical spelling of every profile entry's value.
pub fn check_parameter_profile_spellings_canonical_v1(
    profile: &BTreeMap<String, AmiParameterValueV1>,
) -> ParameterProfileCanonicalSpellingCheckV1 {
    let mut non_canonical = Vec::new();
    for (name, parameter) in profile {
        let canonical = canonicalize_parameter_value_spelling_v1(parameter);
        if canonical != parameter.value_token() {
            non_canonical.push(ParameterProfileCanonicalSpellingIssueV1 {
                name: name.clone(),
                type_token: parameter.parameter_type().token().to_string(),
                value_token: parameter.value_token().to_string(),
                canonical,
            });
        }
    }
    ParameterProfileCanonicalSpellingCheckV1 {
        entries: profile.len(),
        non_canonical,
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
    fn canonical_profile_is_canonical() {
        let p = profile(&[
            ("gain", "Float", "0.5"),
            ("steps", "Integer", "7"),
            ("on", "Boolean", "True"),
        ]);
        let report = check_parameter_profile_spellings_canonical_v1(&p);
        assert_eq!(report.entries(), 3);
        assert!(report.non_canonical().is_empty());
        assert!(report.canonical());
    }

    #[test]
    fn non_canonical_integer_is_reported() {
        let p = profile(&[("steps", "Integer", "007"), ("gain", "Float", "0.5")]);
        let report = check_parameter_profile_spellings_canonical_v1(&p);
        assert_eq!(report.entries(), 2);
        assert_eq!(report.non_canonical().len(), 1);
        let issue = &report.non_canonical()[0];
        assert_eq!(issue.name(), "steps");
        assert_eq!(issue.type_token(), "Integer");
        assert_eq!(issue.value_token(), "007");
        assert_eq!(issue.canonical(), "7");
        assert!(!report.canonical());
    }

    #[test]
    fn non_canonical_list_is_reported() {
        let p = profile(&[("channels", "List", "(a,b,c)")]);
        let report = check_parameter_profile_spellings_canonical_v1(&p);
        assert_eq!(report.non_canonical().len(), 1);
        assert_eq!(report.non_canonical()[0].canonical(), "(a, b, c)");
    }

    #[test]
    fn float_and_string_are_never_flagged() {
        let p = profile(&[("gain", "Float", "0.50"), ("mode", "String", "Linear ")]);
        let report = check_parameter_profile_spellings_canonical_v1(&p);
        assert!(report.non_canonical().is_empty());
        assert!(report.canonical());
    }

    #[test]
    fn empty_profile_is_canonical() {
        let p = BTreeMap::new();
        let report = check_parameter_profile_spellings_canonical_v1(&p);
        assert_eq!(report.entries(), 0);
        assert!(report.canonical());
    }

    #[test]
    fn mixed_canonical_and_non_canonical() {
        let p = profile(&[
            ("a", "Integer", "007"),
            ("b", "Integer", "7"),
            ("c", "Float", "0.5"),
        ]);
        let report = check_parameter_profile_spellings_canonical_v1(&p);
        assert_eq!(report.entries(), 3);
        assert_eq!(report.non_canonical().len(), 1);
        assert_eq!(report.non_canonical()[0].name(), "a");
        assert_eq!(report.non_canonical()[0].canonical(), "7");
    }
}
