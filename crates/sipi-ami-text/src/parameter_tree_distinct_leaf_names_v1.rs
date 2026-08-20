//! AMI parameter tree distinct leaf names core (P4B-02b63).
//!
//! Enumerates the distinct leaf names of an `AmiParameterTreeV1` sorted
//! byte-wise, deduplicated across depths. This is the name-view companion of
//! the occurrence counts (P4B-02b59) and the direct input for the name-policy
//! checks (P4B-02b43/02b49/02b62). Result-based: any tree can be enumerated.

use std::collections::BTreeSet;

use crate::{AmiParameterTreeNodeV1, AmiParameterTreeV1};

/// Scope policy for the distinct leaf names core.
pub const PARAMETER_TREE_DISTINCT_LEAF_NAMES_POLICY_V1: &str =
    "sipi.p4b-02b63.parameter-tree-distinct-leaf-names-v1.name-enumeration";

/// Outcome of a distinct leaf names pass.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ParameterTreeDistinctLeafNamesV1 {
    /// Number of distinct leaf names.
    distinct_count: usize,
    /// Distinct leaf names, sorted byte-wise.
    names: Vec<String>,
}

impl ParameterTreeDistinctLeafNamesV1 {
    pub fn distinct_count(&self) -> usize {
        self.distinct_count
    }

    pub fn names(&self) -> &[String] {
        &self.names
    }
}

fn collect(node: &AmiParameterTreeNodeV1, out: &mut BTreeSet<String>) {
    match node {
        AmiParameterTreeNodeV1::Branch { children, .. } => {
            for child in children.values() {
                collect(child, out);
            }
        }
        AmiParameterTreeNodeV1::Leaf { name, .. } => {
            out.insert(name.clone());
        }
    }
}

/// Enumerate the distinct leaf names of `tree`, sorted byte-wise.
///
/// Result-based: any tree can be enumerated (including root-leaf trees).
pub fn list_parameter_tree_distinct_leaf_names_v1(
    tree: &AmiParameterTreeV1,
) -> ParameterTreeDistinctLeafNamesV1 {
    let mut names = BTreeSet::new();
    collect(tree.root_node(), &mut names);
    let names: Vec<String> = names.into_iter().collect();
    ParameterTreeDistinctLeafNamesV1 {
        distinct_count: names.len(),
        names,
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
    fn deduplicates_cross_depth_names() {
        let t = tree(branch(
            "root",
            vec![
                branch("sub", vec![leaf("gain", &["1"])]),
                leaf("gain", &["2"]),
                leaf("steps", &["3"]),
            ],
        ));
        let result = list_parameter_tree_distinct_leaf_names_v1(&t);
        assert_eq!(result.distinct_count(), 2);
        assert_eq!(result.names(), &["gain".to_string(), "steps".to_string()]);
    }

    #[test]
    fn names_are_sorted_byte_wise() {
        let t = tree(branch(
            "root",
            vec![leaf("beta", &["1"]), leaf("alpha", &["2"])],
        ));
        let result = list_parameter_tree_distinct_leaf_names_v1(&t);
        assert_eq!(result.names(), &["alpha".to_string(), "beta".to_string()]);
    }

    #[test]
    fn root_leaf_tree_has_one_name() {
        let t = tree(leaf("root", &["1"]));
        let result = list_parameter_tree_distinct_leaf_names_v1(&t);
        assert_eq!(result.distinct_count(), 1);
        assert_eq!(result.names(), &["root".to_string()]);
    }

    #[test]
    fn branch_only_tree_has_no_leaf_names() {
        let t = tree(branch("root", vec![branch("a", vec![])]));
        let result = list_parameter_tree_distinct_leaf_names_v1(&t);
        assert_eq!(result.distinct_count(), 0);
        assert!(result.names().is_empty());
    }
}
