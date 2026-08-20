//! AMI parameter tree duplicate-name consistency check core (P4B-02b54).
//!
//! Checks every leaf name occurring at more than one depth of an
//! `AmiParameterTreeV1` for value-token consistency: a duplicated name is
//! consistent when all its occurrences carry identical value tokens, and
//! inconsistent otherwise. This is the inspection companion of the
//! duplicate-rejecting slices (P4B-02b33/02b34/02b37): it reports the situation
//! before those slices fail. The check reports in the result; an inconsistent
//! tree is not itself an error. Result-based: any tree can be checked.

use std::collections::BTreeMap;

use crate::{AmiParameterTreeNodeV1, AmiParameterTreeV1};

/// Scope policy for the duplicate-name consistency check core.
pub const PARAMETER_TREE_DUPLICATE_CHECK_POLICY_V1: &str =
    "sipi.p4b-02b54.parameter-tree-duplicate-consistency-check-v1.duplicate-name-check";

/// Outcome of a duplicate-name consistency check pass.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ParameterTreeDuplicateCheckV1 {
    /// Total leaf occurrences checked.
    leaves_checked: usize,
    /// Names with at least two occurrences.
    duplicated_names: usize,
    /// Duplicated names whose occurrences all carry identical tokens (sorted).
    consistent: Vec<String>,
    /// Duplicated names whose occurrences differ (sorted).
    inconsistent: Vec<String>,
}

impl ParameterTreeDuplicateCheckV1 {
    pub fn leaves_checked(&self) -> usize {
        self.leaves_checked
    }

    pub fn duplicated_names(&self) -> usize {
        self.duplicated_names
    }

    pub fn consistent(&self) -> &[String] {
        &self.consistent
    }

    pub fn inconsistent(&self) -> &[String] {
        &self.inconsistent
    }
}

fn collect_occurrences(
    node: &AmiParameterTreeNodeV1,
    out: &mut BTreeMap<String, Vec<Vec<String>>>,
    leaves: &mut usize,
) {
    match node {
        AmiParameterTreeNodeV1::Branch { children, .. } => {
            for child in children.values() {
                collect_occurrences(child, out, leaves);
            }
        }
        AmiParameterTreeNodeV1::Leaf { name, value_tokens } => {
            *leaves += 1;
            out.entry(name.clone())
                .or_default()
                .push(value_tokens.clone());
        }
    }
}

/// Check duplicated leaf names for value-token consistency.
///
/// Returns total leaf occurrences, the number of duplicated names, and the
/// sorted consistent/inconsistent name lists. Result-based: any tree can be
/// checked; inconsistent duplicates are reported, not errored.
pub fn check_parameter_tree_duplicate_consistency_v1(
    tree: &AmiParameterTreeV1,
) -> ParameterTreeDuplicateCheckV1 {
    let mut occurrences = BTreeMap::new();
    let mut leaves = 0usize;
    collect_occurrences(tree.root_node(), &mut occurrences, &mut leaves);

    let mut duplicated_names = 0usize;
    let mut consistent = Vec::new();
    let mut inconsistent = Vec::new();
    for (name, token_lists) in occurrences {
        if token_lists.len() < 2 {
            continue;
        }
        duplicated_names += 1;
        let first = &token_lists[0];
        let all_same = token_lists.iter().all(|tokens| tokens == first);
        if all_same {
            consistent.push(name);
        } else {
            inconsistent.push(name);
        }
    }
    ParameterTreeDuplicateCheckV1 {
        leaves_checked: leaves,
        duplicated_names,
        consistent,
        inconsistent,
    }
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

    #[test]
    fn consistent_duplicates_are_reported() {
        let t = tree(branch(
            "root",
            vec![
                branch("sub", vec![leaf("gain", &["Float", "1.0"])]),
                leaf("gain", &["Float", "1.0"]),
            ],
        ));
        let result = check_parameter_tree_duplicate_consistency_v1(&t);
        assert_eq!(result.leaves_checked(), 2);
        assert_eq!(result.duplicated_names(), 1);
        assert_eq!(result.consistent(), &["gain".to_string()]);
        assert!(result.inconsistent().is_empty());
    }

    #[test]
    fn inconsistent_duplicates_are_reported() {
        let t = tree(branch(
            "root",
            vec![
                branch("sub", vec![leaf("gain", &["Float", "1.0"])]),
                leaf("gain", &["Float", "2.0"]),
            ],
        ));
        let result = check_parameter_tree_duplicate_consistency_v1(&t);
        assert_eq!(result.duplicated_names(), 1);
        assert!(result.consistent().is_empty());
        assert_eq!(result.inconsistent(), &["gain".to_string()]);
    }

    #[test]
    fn unique_names_have_no_duplicates() {
        let t = tree(branch(
            "root",
            vec![
                leaf("gain", &["Float", "1.0"]),
                leaf("steps", &["Integer", "7"]),
            ],
        ));
        let result = check_parameter_tree_duplicate_consistency_v1(&t);
        assert_eq!(result.leaves_checked(), 2);
        assert_eq!(result.duplicated_names(), 0);
        assert!(result.consistent().is_empty());
        assert!(result.inconsistent().is_empty());
    }

    #[test]
    fn mixed_consistency_is_reported_separately() {
        let t = tree(branch(
            "root",
            vec![
                branch("sub", vec![leaf("a", &["1"]), leaf("b", &["2"])]),
                leaf("a", &["1"]),
                leaf("b", &["3"]),
            ],
        ));
        let result = check_parameter_tree_duplicate_consistency_v1(&t);
        assert_eq!(result.leaves_checked(), 4);
        assert_eq!(result.duplicated_names(), 2);
        assert_eq!(result.consistent(), &["a".to_string()]);
        assert_eq!(result.inconsistent(), &["b".to_string()]);
    }
}
