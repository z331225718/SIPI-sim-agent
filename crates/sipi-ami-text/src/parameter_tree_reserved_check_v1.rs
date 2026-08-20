//! AMI parameter tree reserved-name check core (P4B-02b43).
//!
//! Checks every distinct leaf name of an `AmiParameterTreeV1` against a
//! caller-supplied reserved-name set and reports the violations. This is the
//! mechanism the future reserved-name catalog will drive (the catalog itself
//! remains profile-owned data, not part of this slice). The check reports
//! violations in the result; a tree with reserved names is not itself an error.
//! Fail-closed: an empty reserved-name set is strictly rejected.

use std::collections::BTreeSet;

use crate::{AmiParameterTreeNodeV1, AmiParameterTreeV1};

/// Scope policy for the parameter tree reserved-name check core.
pub const PARAMETER_TREE_RESERVED_NAME_CHECK_POLICY_V1: &str =
    "sipi.p4b-02b43.parameter-tree-reserved-name-check-v1.reserved-set-check";

/// Fail-closed errors during the reserved-name check.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterTreeReservedNameErrorV1 {
    /// The reserved-name set is empty; a check against nothing is a caller
    /// error.
    EmptyReservedSet,
}

/// Outcome of a reserved-name check pass.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ParameterTreeReservedNameCheckV1 {
    /// Number of distinct leaf names checked.
    leaves_checked: usize,
    /// Reserved leaf names found, sorted byte-wise, deduplicated.
    violations: Vec<String>,
    /// True when no leaf name is reserved.
    clean: bool,
}

impl ParameterTreeReservedNameCheckV1 {
    pub fn leaves_checked(&self) -> usize {
        self.leaves_checked
    }

    pub fn violations(&self) -> &[String] {
        &self.violations
    }

    pub fn is_clean(&self) -> bool {
        self.clean
    }
}

fn collect_leaf_names(node: &AmiParameterTreeNodeV1, out: &mut BTreeSet<String>) {
    match node {
        AmiParameterTreeNodeV1::Branch { children, .. } => {
            for child in children.values() {
                collect_leaf_names(child, out);
            }
        }
        AmiParameterTreeNodeV1::Leaf { name, .. } => {
            out.insert(name.clone());
        }
    }
}

/// Check every distinct leaf name of `tree` against `reserved`.
///
/// Returns the count of distinct leaf names checked, the sorted deduplicated
/// violations, and a clean flag. Fails closed on an empty reserved-name set.
pub fn check_parameter_tree_reserved_names_v1(
    tree: &AmiParameterTreeV1,
    reserved: &BTreeSet<String>,
) -> Result<ParameterTreeReservedNameCheckV1, ParameterTreeReservedNameErrorV1> {
    if reserved.is_empty() {
        return Err(ParameterTreeReservedNameErrorV1::EmptyReservedSet);
    }
    let mut leaf_names = BTreeSet::new();
    collect_leaf_names(tree.root_node(), &mut leaf_names);
    let mut violations = Vec::new();
    for name in &leaf_names {
        if reserved.contains(name) {
            violations.push(name.clone());
        }
    }
    Ok(ParameterTreeReservedNameCheckV1 {
        leaves_checked: leaf_names.len(),
        clean: violations.is_empty(),
        violations,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::AmiParameterTreeNodeV1;

    fn leaf(name: &str, tokens: &[&str]) -> AmiParameterTreeNodeV1 {
        AmiParameterTreeNodeV1::Leaf {
            name: name.to_string(),
            value_tokens: tokens.iter().map(|s| s.to_string()).collect(),
        }
    }

    fn branch(name: &str, children: Vec<AmiParameterTreeNodeV1>) -> AmiParameterTreeNodeV1 {
        AmiParameterTreeNodeV1::Branch {
            name: name.to_string(),
            children: children
                .into_iter()
                .map(|c| (c.name().to_string(), c))
                .collect(),
        }
    }

    fn tree(node: AmiParameterTreeNodeV1) -> AmiParameterTreeV1 {
        AmiParameterTreeV1::new("root", node)
    }

    fn reserved_of(names: &[&str]) -> BTreeSet<String> {
        names.iter().map(|s| s.to_string()).collect()
    }

    #[test]
    fn clean_tree_has_no_violations() {
        let t = tree(branch(
            "root",
            vec![leaf("gain", &["0.5"]), leaf("steps", &["7"])],
        ));
        let result =
            check_parameter_tree_reserved_names_v1(&t, &reserved_of(&["Reserved_Parameters"]))
                .expect("checked");
        assert_eq!(result.leaves_checked(), 2);
        assert!(result.violations().is_empty());
        assert!(result.is_clean());
    }

    #[test]
    fn reserved_leaf_is_reported() {
        let t = tree(branch(
            "root",
            vec![leaf("gain", &["0.5"]), leaf("Reserved_Parameters", &["1"])],
        ));
        let result =
            check_parameter_tree_reserved_names_v1(&t, &reserved_of(&["Reserved_Parameters"]))
                .expect("checked");
        assert_eq!(result.violations(), &["Reserved_Parameters".to_string()]);
        assert!(!result.is_clean());
    }

    #[test]
    fn violations_are_sorted_and_deduplicated() {
        let t = tree(branch(
            "root",
            vec![
                leaf("beta", &["1"]),
                leaf("alpha", &["2"]),
                leaf("gain", &["3"]),
            ],
        ));
        let result = check_parameter_tree_reserved_names_v1(&t, &reserved_of(&["alpha", "beta"]))
            .expect("checked");
        assert_eq!(
            result.violations(),
            &["alpha".to_string(), "beta".to_string()]
        );
        assert_eq!(result.leaves_checked(), 3);
    }

    #[test]
    fn duplicate_depth_names_deduplicate_in_violations() {
        let t = tree(branch(
            "root",
            vec![
                branch("sub", vec![leaf("gain", &["1"])]),
                leaf("gain", &["2"]),
            ],
        ));
        let result =
            check_parameter_tree_reserved_names_v1(&t, &reserved_of(&["gain"])).expect("checked");
        assert_eq!(result.violations(), &["gain".to_string()]);
        assert_eq!(result.leaves_checked(), 1);
    }

    #[test]
    fn empty_reserved_set_fails_closed() {
        let t = tree(branch("root", vec![leaf("gain", &["0.5"])]));
        let error = check_parameter_tree_reserved_names_v1(&t, &reserved_of(&[])).unwrap_err();
        assert_eq!(error, ParameterTreeReservedNameErrorV1::EmptyReservedSet);
    }
}
