//! AMI parameter tree allowed-name check core (P4B-02b49).
//!
//! Checks every distinct leaf name of an `AmiParameterTreeV1` against a
//! caller-supplied allowed-name set and reports the violations (names NOT in the
//! allowed set). This is the mirror of the reserved-name check (P4B-02b43,
//! blacklist) — a whitelist mechanism the future reserved-name catalog will
//! drive. The check reports violations in the result; a tree with disallowed
//! names is not itself an error. Fail-closed: an empty allowed-name set is
//! strictly rejected.

use std::collections::BTreeSet;

use crate::{AmiParameterTreeNodeV1, AmiParameterTreeV1};

/// Scope policy for the parameter tree allowed-name check core.
pub const PARAMETER_TREE_ALLOWED_NAME_CHECK_POLICY_V1: &str =
    "sipi.p4b-02b49.parameter-tree-allowed-name-check-v1.allowed-set-check";

/// Fail-closed errors during the allowed-name check.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterTreeAllowedNameErrorV1 {
    /// The allowed-name set is empty; a whitelist with no names is a caller
    /// error.
    EmptyAllowedSet,
}

/// Outcome of an allowed-name check pass.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ParameterTreeAllowedNameCheckV1 {
    /// Number of distinct leaf names checked.
    leaves_checked: usize,
    /// Leaf names NOT in the allowed set, sorted byte-wise, deduplicated.
    violations: Vec<String>,
    /// True when every leaf name is allowed.
    clean: bool,
}

impl ParameterTreeAllowedNameCheckV1 {
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

/// Check every distinct leaf name of `tree` against `allowed`.
///
/// Returns the count of distinct leaf names checked, the sorted deduplicated
/// violations (names not allowed), and a clean flag. Fails closed on an empty
/// allowed-name set.
pub fn check_parameter_tree_allowed_names_v1(
    tree: &AmiParameterTreeV1,
    allowed: &BTreeSet<String>,
) -> Result<ParameterTreeAllowedNameCheckV1, ParameterTreeAllowedNameErrorV1> {
    if allowed.is_empty() {
        return Err(ParameterTreeAllowedNameErrorV1::EmptyAllowedSet);
    }
    let mut leaf_names = BTreeSet::new();
    collect_leaf_names(tree.root_node(), &mut leaf_names);
    let mut violations = Vec::new();
    for name in &leaf_names {
        if !allowed.contains(name) {
            violations.push(name.clone());
        }
    }
    Ok(ParameterTreeAllowedNameCheckV1 {
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

    fn allowed_of(names: &[&str]) -> BTreeSet<String> {
        names.iter().map(|s| s.to_string()).collect()
    }

    #[test]
    fn all_allowed_names_are_clean() {
        let t = tree(branch(
            "root",
            vec![leaf("gain", &["0.5"]), leaf("steps", &["7"])],
        ));
        let result = check_parameter_tree_allowed_names_v1(&t, &allowed_of(&["gain", "steps"]))
            .expect("checked");
        assert_eq!(result.leaves_checked(), 2);
        assert!(result.violations().is_empty());
        assert!(result.is_clean());
    }

    #[test]
    fn unknown_name_is_a_violation() {
        let t = tree(branch(
            "root",
            vec![leaf("gain", &["0.5"]), leaf("steps", &["7"])],
        ));
        let result =
            check_parameter_tree_allowed_names_v1(&t, &allowed_of(&["gain"])).expect("checked");
        assert_eq!(result.violations(), &["steps".to_string()]);
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
        let result =
            check_parameter_tree_allowed_names_v1(&t, &allowed_of(&["alpha"])).expect("checked");
        assert_eq!(
            result.violations(),
            &["beta".to_string(), "gain".to_string()]
        );
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
            check_parameter_tree_allowed_names_v1(&t, &allowed_of(&["steps"])).expect("checked");
        assert_eq!(result.violations(), &["gain".to_string()]);
        assert_eq!(result.leaves_checked(), 1);
    }

    #[test]
    fn empty_allowed_set_fails_closed() {
        let t = tree(branch("root", vec![leaf("gain", &["0.5"])]));
        let error = check_parameter_tree_allowed_names_v1(&t, &allowed_of(&[])).unwrap_err();
        assert_eq!(error, ParameterTreeAllowedNameErrorV1::EmptyAllowedSet);
    }
}
