//! AMI parameter tree required-name check core (P4B-02b62).
//!
//! Checks every caller-supplied required name against an `AmiParameterTreeV1`:
//! a required name is present when it occurs as a leaf anywhere in the tree;
//! the check reports the sorted missing names and a completeness flag. This is
//! the tree-level counterpart of the profile-level completeness check
//! (P4B-02b55) and completes the name-policy trio with the reserved blacklist
//! (P4B-02b43) and the allowed whitelist (P4B-02b49): forbidden / allowed /
//! required. The check reports in the result; an incomplete tree is not itself
//! an error. Fail-closed: an empty required-name set is strictly rejected.

use std::collections::{BTreeMap, BTreeSet};

use crate::{AmiParameterTreeV1, AmiParameterTreeNodeV1};

/// Scope policy for the required-name check core.
pub const PARAMETER_TREE_REQUIRED_NAME_CHECK_POLICY_V1: &str =
    "sipi.p4b-02b62.parameter-tree-required-name-check-v1.required-presence-check";

/// Fail-closed errors during the required-name check.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterTreeRequiredNameErrorV1 {
    /// The required-name set is empty; a check against nothing is a caller
    /// error.
    EmptyRequired,
}

/// Outcome of a required-name check pass.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ParameterTreeRequiredNameCheckV1 {
    /// Number of required names.
    required_count: usize,
    /// Number of required names present as leaves.
    present: usize,
    /// Required names missing from the tree (sorted).
    missing: Vec<String>,
    /// True when every required name is present.
    complete: bool,
}

impl ParameterTreeRequiredNameCheckV1 {
    pub fn required_count(&self) -> usize {
        self.required_count
    }

    pub fn present(&self) -> usize {
        self.present
    }

    pub fn missing(&self) -> &[String] {
        &self.missing
    }

    pub fn is_complete(&self) -> bool {
        self.complete
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

/// Check every required name against the leaves of `tree`.
///
/// Returns required/present counts plus the sorted missing names and a
/// completeness flag. Fails closed on an empty required-name set.
pub fn check_parameter_tree_required_names_v1(
    tree: &AmiParameterTreeV1,
    required: &BTreeSet<String>,
) -> Result<ParameterTreeRequiredNameCheckV1, ParameterTreeRequiredNameErrorV1> {
    if required.is_empty() {
        return Err(ParameterTreeRequiredNameErrorV1::EmptyRequired);
    }
    let mut leaf_names = BTreeSet::new();
    collect_leaf_names(tree.root_node(), &mut leaf_names);
    let mut present = 0usize;
    let mut missing = Vec::new();
    for name in required {
        if leaf_names.contains(name) {
            present += 1;
        } else {
            missing.push(name.clone());
        }
    }
    let complete = missing.is_empty();
    Ok(ParameterTreeRequiredNameCheckV1 {
        required_count: required.len(),
        present,
        missing,
        complete,
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

    fn required_of(names: &[&str]) -> BTreeSet<String> {
        names.iter().map(|s| s.to_string()).collect()
    }

    #[test]
    fn all_required_present_is_complete() {
        let t = tree(branch(
            "root",
            vec![leaf("gain", &["0.5"]), leaf("steps", &["7"])],
        ));
        let result = check_parameter_tree_required_names_v1(
            &t,
            &required_of(&["gain", "steps"]),
        )
        .expect("checked");
        assert_eq!(result.required_count(), 2);
        assert_eq!(result.present(), 2);
        assert!(result.missing().is_empty());
        assert!(result.is_complete());
    }

    #[test]
    fn missing_required_names_are_reported_sorted() {
        let t = tree(branch("root", vec![leaf("gain", &["0.5"])]));
        let result = check_parameter_tree_required_names_v1(
            &t,
            &required_of(&["mode", "gain", "steps"]),
        )
        .expect("checked");
        assert_eq!(result.present(), 1);
        assert_eq!(
            result.missing(),
            &["mode".to_string(), "steps".to_string()]
        );
        assert!(!result.is_complete());
    }

    #[test]
    fn nested_leaves_satisfy_required() {
        let t = tree(branch(
            "root",
            vec![branch("sub", vec![leaf("deep", &["1.0"])])],
        ));
        let result = check_parameter_tree_required_names_v1(
            &t,
            &required_of(&["deep"]),
        )
        .expect("checked");
        assert!(result.is_complete());
        assert_eq!(result.present(), 1);
    }

    #[test]
    fn empty_required_fails_closed() {
        let t = tree(branch("root", vec![leaf("gain", &["0.5"])]));
        let error = check_parameter_tree_required_names_v1(&t, &required_of(&[])).unwrap_err();
        assert_eq!(error, ParameterTreeRequiredNameErrorV1::EmptyRequired);
    }
}
