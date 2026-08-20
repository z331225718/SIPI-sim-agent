//! AMI parameter tree leaf occurrence counts core (P4B-02b59).
//!
//! Counts the occurrences of every leaf name of an `AmiParameterTreeV1`,
//! producing the name -> count landscape (including cross-depth duplicates).
//! This is the direct input view for ambiguity-protected name-addressed
//! operations (P4B-02b53) and the duplicate-name landscape companion of the
//! consistency check (P4B-02b54). Result-based: any tree can be counted.

use std::collections::BTreeMap;

use crate::{AmiParameterTreeNodeV1, AmiParameterTreeV1};

/// Scope policy for the leaf occurrence counts core.
pub const PARAMETER_TREE_LEAF_OCCURRENCES_POLICY_V1: &str =
    "sipi.p4b-02b59.parameter-tree-leaf-occurrences-v1.name-counts";

/// Outcome of a leaf occurrence counting pass.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ParameterTreeLeafOccurrencesV1 {
    total_leaves: usize,
    occurrences: BTreeMap<String, usize>,
}

impl ParameterTreeLeafOccurrencesV1 {
    pub fn total_leaves(&self) -> usize {
        self.total_leaves
    }

    pub fn occurrences(&self) -> &BTreeMap<String, usize> {
        &self.occurrences
    }
}

fn count_node(
    node: &AmiParameterTreeNodeV1,
    occurrences: &mut BTreeMap<String, usize>,
    total: &mut usize,
) {
    match node {
        AmiParameterTreeNodeV1::Branch { children, .. } => {
            for child in children.values() {
                count_node(child, occurrences, total);
            }
        }
        AmiParameterTreeNodeV1::Leaf { name, .. } => {
            *total += 1;
            *occurrences.entry(name.clone()).or_insert(0) += 1;
        }
    }
}

/// Count the occurrences of every leaf name of `tree`.
///
/// Returns the total leaf count and the name -> count map (byte-wise name
/// order). Result-based: any tree can be counted.
pub fn count_parameter_tree_leaf_occurrences_v1(
    tree: &AmiParameterTreeV1,
) -> ParameterTreeLeafOccurrencesV1 {
    let mut occurrences = BTreeMap::new();
    let mut total = 0usize;
    count_node(tree.root_node(), &mut occurrences, &mut total);
    ParameterTreeLeafOccurrencesV1 {
        total_leaves: total,
        occurrences,
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
    fn counts_cross_depth_duplicates() {
        let t = tree(branch(
            "root",
            vec![
                branch("sub", vec![leaf("gain", &["1"])]),
                leaf("gain", &["2"]),
                leaf("steps", &["3"]),
            ],
        ));
        let result = count_parameter_tree_leaf_occurrences_v1(&t);
        assert_eq!(result.total_leaves(), 3);
        assert_eq!(result.occurrences().get("gain"), Some(&2));
        assert_eq!(result.occurrences().get("steps"), Some(&1));
    }

    #[test]
    fn unique_names_count_one() {
        let t = tree(branch(
            "root",
            vec![leaf("gain", &["1"]), leaf("steps", &["2"])],
        ));
        let result = count_parameter_tree_leaf_occurrences_v1(&t);
        assert_eq!(result.total_leaves(), 2);
        assert_eq!(result.occurrences().get("gain"), Some(&1));
        assert_eq!(result.occurrences().get("steps"), Some(&1));
    }

    #[test]
    fn root_leaf_tree_counts_one() {
        let t = tree(leaf("root", &["1"]));
        let result = count_parameter_tree_leaf_occurrences_v1(&t);
        assert_eq!(result.total_leaves(), 1);
        assert_eq!(result.occurrences().get("root"), Some(&1));
    }

    #[test]
    fn deep_nesting_counts_only_leaves() {
        let t = tree(branch(
            "root",
            vec![branch("a", vec![branch("b", vec![leaf("c", &["1"])])])],
        ));
        let result = count_parameter_tree_leaf_occurrences_v1(&t);
        assert_eq!(result.total_leaves(), 1);
        assert_eq!(result.occurrences().get("c"), Some(&1));
        assert_eq!(result.occurrences().len(), 1);
    }
}
