//! AMI parameter tree token frequencies core (P4B-02b60).
//!
//! Computes the global value-token frequency landscape of an
//! `AmiParameterTreeV1`: every distinct leaf value token with its total
//! occurrence count across all leaves, plus the total token count. This
//! complements the per-leaf token statistics (P4B-02b31, which reports the
//! distinct token set without frequencies). Result-based: any tree can be
//! analyzed.

use std::collections::BTreeMap;

use crate::{AmiParameterTreeV1, AmiParameterTreeNodeV1};

/// Scope policy for the token frequencies core.
pub const PARAMETER_TREE_TOKEN_FREQUENCIES_POLICY_V1: &str =
    "sipi.p4b-02b60.parameter-tree-token-frequencies-v1.value-token-landscape";

/// Outcome of a token frequency pass.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ParameterTreeTokenFrequenciesV1 {
    total_tokens: usize,
    frequencies: BTreeMap<String, usize>,
}

impl ParameterTreeTokenFrequenciesV1 {
    pub fn total_tokens(&self) -> usize {
        self.total_tokens
    }

    pub fn frequencies(&self) -> &BTreeMap<String, usize> {
        &self.frequencies
    }
}

fn walk(
    node: &AmiParameterTreeNodeV1,
    frequencies: &mut BTreeMap<String, usize>,
    total: &mut usize,
) {
    match node {
        AmiParameterTreeNodeV1::Branch { children, .. } => {
            for child in children.values() {
                walk(child, frequencies, total);
            }
        }
        AmiParameterTreeNodeV1::Leaf {
            value_tokens, ..
        } => {
            for token in value_tokens {
                *total += 1;
                *frequencies.entry(token.clone()).or_insert(0) += 1;
            }
        }
    }
}

/// Compute the value-token frequency landscape of `tree`.
///
/// Returns the total leaf value-token count and the token -> count map
/// (byte-wise token order). Result-based: any tree can be analyzed.
pub fn compute_parameter_tree_token_frequencies_v1(
    tree: &AmiParameterTreeV1,
) -> ParameterTreeTokenFrequenciesV1 {
    let mut frequencies = BTreeMap::new();
    let mut total = 0usize;
    walk(tree.root_node(), &mut frequencies, &mut total);
    ParameterTreeTokenFrequenciesV1 {
        total_tokens: total,
        frequencies,
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
    fn shared_tokens_are_counted_across_leaves() {
        let t = tree(branch(
            "root",
            vec![leaf("x", &["1", "2"]), leaf("y", &["2", "3"])],
        ));
        let result = compute_parameter_tree_token_frequencies_v1(&t);
        assert_eq!(result.total_tokens(), 4);
        assert_eq!(result.frequencies().get("1"), Some(&1));
        assert_eq!(result.frequencies().get("2"), Some(&2));
        assert_eq!(result.frequencies().get("3"), Some(&1));
    }

    #[test]
    fn repeated_tokens_in_one_leaf_count_each() {
        let t = tree(branch("root", vec![leaf("x", &["1", "1"])]));
        let result = compute_parameter_tree_token_frequencies_v1(&t);
        assert_eq!(result.total_tokens(), 2);
        assert_eq!(result.frequencies().get("1"), Some(&2));
    }

    #[test]
    fn unique_tokens_count_once() {
        let t = tree(branch(
            "root",
            vec![leaf("a", &["1"]), leaf("b", &["2"])],
        ));
        let result = compute_parameter_tree_token_frequencies_v1(&t);
        assert_eq!(result.total_tokens(), 2);
        assert_eq!(result.frequencies().get("1"), Some(&1));
        assert_eq!(result.frequencies().get("2"), Some(&1));
    }

    #[test]
    fn root_leaf_without_tokens_is_empty() {
        let t = tree(leaf("root", &[]));
        let result = compute_parameter_tree_token_frequencies_v1(&t);
        assert_eq!(result.total_tokens(), 0);
        assert!(result.frequencies().is_empty());
    }
}
