//! AMI parameter profile canonical spelling groups core (P4B-02b92).
//!
//! Groups the names of an assembled parameter profile (`BTreeMap<String,
//! AmiParameterValueV1>`, e.g. produced by 02b44 assembly) by the canonical
//! spelling of their values (`canonicalize_parameter_value_spelling_v1`, 02b75):
//! names whose values normalize to the same canonical spelling form one group
//! (e.g. Integer `007` and `7`, List `(a,b,c)` and `(a, b, c)`). Float and
//! String values stay raw, so only spelling-normalizable types can group.
//! This finds semantically redundant entries within a profile and is the
//! grouping companion of 02b80 value lookup (query direction) and of 02b54
//! tree duplicate consistency (tree level).
//!
//! Fail-closed: the grouping is total (no error path); groups come back in
//! deterministic sorted (spelling) order and each group's names in sorted
//! order; `covered_names()` sums the group name counts.

use std::collections::BTreeMap;

use crate::{canonicalize_parameter_value_spelling_v1, AmiParameterValueV1};

/// Explicit scope policy of this slice: canonical spelling groups of profiles.
pub const PARAMETER_PROFILE_CANONICAL_SPELLING_GROUPS_POLICY_V1: &str =
    "sipi.p4b-02b92.parameter-profile-canonical-spelling-groups-v1.canonical-spelling-groups";

/// One canonical spelling and the names whose values normalize to it.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ParameterProfileCanonicalSpellingGroupV1 {
    spelling: String,
    names: Vec<String>,
}

impl ParameterProfileCanonicalSpellingGroupV1 {
    pub fn spelling(&self) -> &str {
        &self.spelling
    }

    pub fn names(&self) -> &[String] {
        &self.names
    }

    pub fn name_count(&self) -> usize {
        self.names.len()
    }
}

/// Outcome of grouping a profile's names by canonical value spelling.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ParameterProfileCanonicalSpellingGroupsV1 {
    groups: Vec<ParameterProfileCanonicalSpellingGroupV1>,
}

impl ParameterProfileCanonicalSpellingGroupsV1 {
    /// Sorted (by spelling) groups with at least one name.
    pub fn groups(&self) -> &[ParameterProfileCanonicalSpellingGroupV1] {
        &self.groups
    }

    /// Number of groups.
    pub fn group_count(&self) -> usize {
        self.groups.len()
    }

    /// Number of groups with exactly one name.
    pub fn singleton_count(&self) -> usize {
        self.groups
            .iter()
            .filter(|group| group.name_count() == 1)
            .count()
    }

    /// Total number of names covered by all groups (equals profile size).
    pub fn covered_names(&self) -> usize {
        self.groups.iter().map(|group| group.name_count()).sum()
    }
}

/// Group a profile's names by the canonical spelling of their values.
pub fn group_parameter_profile_names_by_canonical_spelling_v1(
    profile: &BTreeMap<String, AmiParameterValueV1>,
) -> ParameterProfileCanonicalSpellingGroupsV1 {
    let mut by_spelling: BTreeMap<String, Vec<String>> = BTreeMap::new();
    for (name, parameter) in profile {
        let canonical = canonicalize_parameter_value_spelling_v1(parameter);
        by_spelling
            .entry(canonical)
            .or_default()
            .push(name.clone());
    }
    let groups = by_spelling
        .into_iter()
        .map(|(spelling, names)| ParameterProfileCanonicalSpellingGroupV1 { spelling, names })
        .collect();
    ParameterProfileCanonicalSpellingGroupsV1 { groups }
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
    fn integer_spellings_group_together() {
        let p = profile(&[
            ("a", "Integer", "007"),
            ("b", "Integer", "7"),
            ("c", "Integer", "8"),
        ]);
        let result = group_parameter_profile_names_by_canonical_spelling_v1(&p);
        assert_eq!(result.group_count(), 2);
        assert_eq!(result.groups()[0].spelling(), "7");
        assert_eq!(result.groups()[0].names(), &["a".to_string(), "b".to_string()]);
        assert_eq!(result.groups()[1].spelling(), "8");
        assert_eq!(result.covered_names(), 3);
    }

    #[test]
    fn list_spacing_groups_together() {
        let p = profile(&[
            ("x", "List", "(a,b,c)"),
            ("y", "List", "(a, b, c)"),
        ]);
        let result = group_parameter_profile_names_by_canonical_spelling_v1(&p);
        assert_eq!(result.group_count(), 1);
        assert_eq!(result.groups()[0].spelling(), "(a, b, c)");
        assert_eq!(result.groups()[0].names(), &["x".to_string(), "y".to_string()]);
    }

    #[test]
    fn float_spellings_stay_separate() {
        let p = profile(&[
            ("a", "Float", "0.5"),
            ("b", "Float", "0.50"),
        ]);
        let result = group_parameter_profile_names_by_canonical_spelling_v1(&p);
        assert_eq!(result.group_count(), 2);
        assert_eq!(result.singleton_count(), 2);
        assert_eq!(result.groups()[0].spelling(), "0.5");
        assert_eq!(result.groups()[1].spelling(), "0.50");
    }

    #[test]
    fn singleton_count_tracks_single_name_groups() {
        let p = profile(&[
            ("a", "Integer", "007"),
            ("b", "Integer", "7"),
            ("c", "Integer", "8"),
        ]);
        let result = group_parameter_profile_names_by_canonical_spelling_v1(&p);
        assert_eq!(result.group_count(), 2);
        assert_eq!(result.singleton_count(), 1);
    }

    #[test]
    fn empty_profile_has_no_groups() {
        let p = BTreeMap::new();
        let result = group_parameter_profile_names_by_canonical_spelling_v1(&p);
        assert_eq!(result.group_count(), 0);
        assert_eq!(result.singleton_count(), 0);
        assert_eq!(result.covered_names(), 0);
    }

    #[test]
    fn mixed_types_group_by_their_own_canonical() {
        let p = profile(&[
            ("a", "Integer", "007"),
            ("b", "Integer", "7"),
            ("c", "Float", "0.5"),
        ]);
        let result = group_parameter_profile_names_by_canonical_spelling_v1(&p);
        assert_eq!(result.group_count(), 2);
        assert_eq!(result.groups()[0].spelling(), "0.5");
        assert_eq!(result.groups()[0].names(), &["c".to_string()]);
        assert_eq!(result.groups()[1].spelling(), "7");
        assert_eq!(result.groups()[1].names(), &["a".to_string(), "b".to_string()]);
        assert_eq!(result.covered_names(), 3);
    }
}
