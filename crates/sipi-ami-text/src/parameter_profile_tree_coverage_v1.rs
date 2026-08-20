//! AMI parameter profile tree coverage core (P4B-02b72).
//!
//! Reports how an assembled parameter profile (`BTreeMap<String, AmiParameterValueV1>`,
//! e.g. produced by 02b44 assembly) covers the leaves of an `AmiParameterTreeV1`:
//! for every profile name, whether the tree holds exactly one leaf
//! (covered), more than one leaf at possibly different depths (ambiguous),
//! or no leaf at all (missing). This is the pre-flight planning report ahead
//! of `apply_parameter_profile_to_tree_v1` (02b69), which fails closed on the
//! first missing or ambiguous name; this slice surfaces the complete picture
//! up front without failing. Fail-closed on tree shape: any node that is
//! neither a Branch nor a Leaf is rejected by the exhaustive match (the
//! product tree type has exactly these two variants).

use std::collections::BTreeMap;

use crate::{AmiParameterTreeV1, AmiParameterTreeNodeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: profile-to-tree leaf coverage report.
pub const PARAMETER_PROFILE_TREE_COVERAGE_POLICY_V1: &str =
    "sipi.p4b-02b72.parameter-profile-tree-coverage-v1.profile-leaf-coverage-report";

/// Coverage of one profile over one parameter tree's leaves.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ParameterProfileTreeCoverageV1 {
    profile_names: usize,
    covered: Vec<String>,
    ambiguous: Vec<String>,
    missing: Vec<String>,
}

impl ParameterProfileTreeCoverageV1 {
    /// Number of names in the profile map.
    pub fn profile_names(&self) -> usize {
        self.profile_names
    }

    /// Sorted profile names with exactly one leaf in the tree.
    pub fn covered(&self) -> &[String] {
        &self.covered
    }

    /// Sorted profile names with more than one leaf (different depths possible).
    pub fn ambiguous(&self) -> &[String] {
        &self.ambiguous
    }

    /// Sorted profile names with no leaf at all.
    pub fn missing(&self) -> &[String] {
        &self.missing
    }

    /// Every profile name has at least one leaf (no missing names).
    pub fn complete(&self) -> bool {
        self.missing.is_empty()
    }

    /// No ambiguous names (02b69 apply would not hit AmbiguousName).
    pub fn unambiguous(&self) -> bool {
        self.ambiguous.is_empty()
    }
}

/// Count leaf occurrences per name across the whole tree.
fn count_leaf_names(node: &AmiParameterTreeNodeV1, counts: &mut BTreeMap<String, usize>) {
    match node {
        AmiParameterTreeNodeV1::Branch { children, .. } => {
            for child in children.values() {
                count_leaf_names(child, counts);
            }
        }
        AmiParameterTreeNodeV1::Leaf { name, .. } => {
            *counts.entry(name.clone()).or_insert(0) += 1;
        }
    }
}

/// Report how a parameter profile covers a parameter tree's leaves.
pub fn check_parameter_profile_tree_coverage_v1(
    tree: &AmiParameterTreeV1,
    profile: &BTreeMap<String, AmiParameterValueV1>,
) -> ParameterProfileTreeCoverageV1 {
    let mut leaf_counts = BTreeMap::new();
    count_leaf_names(tree.root_node(), &mut leaf_counts);

    let mut covered = Vec::new();
    let mut ambiguous = Vec::new();
    let mut missing = Vec::new();
    for name in profile.keys() {
        match leaf_counts.get(name).copied().unwrap_or(0) {
            0 => missing.push(name.clone()),
            1 => covered.push(name.clone()),
            _ => ambiguous.push(name.clone()),
        }
    }
    ParameterProfileTreeCoverageV1 {
        profile_names: profile.len(),
        covered,
        ambiguous,
        missing,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{build_parameter_trees_v1, parse_ami_text_v1, ParseLimitsV1};

    fn tree(text: &str) -> AmiParameterTreeV1 {
        let limits = ParseLimitsV1::try_new(8 * 1024 * 1024, 64, 4096, 4096).expect("limits");
        let doc = parse_ami_text_v1(text.as_bytes(), limits).expect("parse");
        let trees = build_parameter_trees_v1(&doc).expect("build");
        trees.into_iter().next().expect("one tree")
    }

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
    fn full_coverage_is_complete_and_unambiguous() {
        let t = tree("(root (gain Float 0.5) (steps Integer 7))");
        let p = profile(&[("gain", "Float", "1.25"), ("steps", "Integer", "8")]);
        let report = check_parameter_profile_tree_coverage_v1(&t, &p);
        assert_eq!(report.profile_names(), 2);
        assert_eq!(report.covered(), &["gain".to_string(), "steps".to_string()]);
        assert!(report.ambiguous().is_empty());
        assert!(report.missing().is_empty());
        assert!(report.complete());
        assert!(report.unambiguous());
    }

    #[test]
    fn missing_names_are_reported() {
        let t = tree("(root (gain Float 0.5))");
        let p = profile(&[("gain", "Float", "1.25"), ("nope", "Float", "1.0")]);
        let report = check_parameter_profile_tree_coverage_v1(&t, &p);
        assert_eq!(report.profile_names(), 2);
        assert_eq!(report.covered(), &["gain".to_string()]);
        assert_eq!(report.missing(), &["nope".to_string()]);
        assert!(!report.complete());
        assert!(report.unambiguous());
    }

    #[test]
    fn ambiguous_names_are_reported() {
        let t = tree("(root (gain Float 0.5) (sub (gain Float 1.0)))");
        let p = profile(&[("gain", "Float", "1.25")]);
        let report = check_parameter_profile_tree_coverage_v1(&t, &p);
        assert_eq!(report.profile_names(), 1);
        assert!(report.covered().is_empty());
        assert_eq!(report.ambiguous(), &["gain".to_string()]);
        assert!(report.missing().is_empty());
        assert!(report.complete());
        assert!(!report.unambiguous());
    }

    #[test]
    fn empty_profile_is_complete_and_unambiguous() {
        let t = tree("(root (gain Float 0.5))");
        let p = BTreeMap::new();
        let report = check_parameter_profile_tree_coverage_v1(&t, &p);
        assert_eq!(report.profile_names(), 0);
        assert!(report.covered().is_empty());
        assert!(report.ambiguous().is_empty());
        assert!(report.missing().is_empty());
        assert!(report.complete());
        assert!(report.unambiguous());
    }

    #[test]
    fn tree_without_leaves_reports_all_missing() {
        let t = tree("(root (sub (leaf Float 0.5)) (other (leaf2 Integer 7)))");
        let p = profile(&[("gain", "Float", "1.25"), ("steps", "Integer", "8")]);
        let report = check_parameter_profile_tree_coverage_v1(&t, &p);
        assert_eq!(report.profile_names(), 2);
        assert_eq!(
            report.missing(),
            &["gain".to_string(), "steps".to_string()]
        );
        assert!(report.covered().is_empty());
        assert!(report.ambiguous().is_empty());
        assert!(!report.complete());
        assert!(report.unambiguous());
    }

    #[test]
    fn mixed_coverage_reports_each_class() {
        let t = tree("(root (gain Float 0.5) (sub (gain Float 1.0)) (steps Integer 7))");
        let p = profile(&[
            ("gain", "Float", "1.25"),
            ("steps", "Integer", "8"),
            ("nope", "Float", "1.0"),
        ]);
        let report = check_parameter_profile_tree_coverage_v1(&t, &p);
        assert_eq!(report.profile_names(), 3);
        assert_eq!(report.covered(), &["steps".to_string()]);
        assert_eq!(report.ambiguous(), &["gain".to_string()]);
        assert_eq!(report.missing(), &["nope".to_string()]);
        assert!(!report.complete());
        assert!(!report.unambiguous());
    }
}
