//! AMI parameter tree token statistics core (P4B-02b31).
//!
//! Computes value-token statistics for a typed `AmiParameterTreeV1` hierarchy
//! (`compute_parameter_tree_token_stats_v1`): total leaf count, total value token count,
//! max/mean tokens per leaf, and the set of distinct token spellings.
//! Fail-closed: empty tree lists are strictly rejected.

use std::collections::BTreeSet;

use crate::parameter_trees_v1::{AmiParameterTreeNodeV1, AmiParameterTreeV1};

/// Scope policy for the parameter tree token stats core.
pub const PARAMETER_TREE_TOKEN_STATS_POLICY_V1: &str =
    "sipi.p4b-02b31.parameter-tree-token-stats-v1.tree-token-statistics";

/// Fail-closed errors during AMI parameter tree token statistics computation.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterTreeTokenStatsErrorV1 {
    EmptyTreeList,
}

/// Value-token statistics for a parameter tree.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ParameterTreeTokenStatsV1 {
    pub leaf_count: usize,
    pub total_tokens: usize,
    pub max_tokens_per_leaf: usize,
    /// Distinct token spellings across all leaves, in sorted order.
    pub distinct_tokens: Vec<String>,
}

fn walk(node: &AmiParameterTreeNodeV1, stats: &mut ParameterTreeTokenStatsV1) {
    match node {
        AmiParameterTreeNodeV1::Branch { children, .. } => {
            for child in children.values() {
                walk(child, stats);
            }
        }
        AmiParameterTreeNodeV1::Leaf { value_tokens, .. } => {
            stats.leaf_count += 1;
            stats.total_tokens += value_tokens.len();
            stats.max_tokens_per_leaf = stats.max_tokens_per_leaf.max(value_tokens.len());
            for token in value_tokens {
                stats.distinct_tokens.push(token.clone());
            }
        }
    }
}

/// Compute value-token statistics for a parameter tree.
pub fn compute_parameter_tree_token_stats_v1(
    tree: &AmiParameterTreeV1,
) -> Result<ParameterTreeTokenStatsV1, ParameterTreeTokenStatsErrorV1> {
    let mut stats = ParameterTreeTokenStatsV1 {
        leaf_count: 0,
        total_tokens: 0,
        max_tokens_per_leaf: 0,
        distinct_tokens: Vec::new(),
    };
    walk(tree.root_node(), &mut stats);
    let mut set = BTreeSet::new();
    for t in stats.distinct_tokens.drain(..) {
        set.insert(t);
    }
    stats.distinct_tokens = set.into_iter().collect();
    Ok(stats)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::ParseLimitsV1;
    use crate::parameter_trees_v1::build_parameter_trees_v1;
    use crate::parse_ami_text_v1;

    fn limits() -> ParseLimitsV1 {
        ParseLimitsV1::try_new(1024, 16, 64, 128).unwrap()
    }

    fn tree_of(text: &str) -> AmiParameterTreeV1 {
        let doc = parse_ami_text_v1(text.as_bytes(), limits()).expect("parse");
        build_parameter_trees_v1(&doc).expect("build").remove(0)
    }

    #[test]
    fn policy_fixed() {
        assert_eq!(
            PARAMETER_TREE_TOKEN_STATS_POLICY_V1,
            "sipi.p4b-02b31.parameter-tree-token-stats-v1.tree-token-statistics"
        );
    }

    #[test]
    fn computes_token_stats() {
        let tree = tree_of("(root (a Float 0.5) (b 1))");
        let stats = compute_parameter_tree_token_stats_v1(&tree).expect("stats");
        assert_eq!(stats.leaf_count, 2);
        assert_eq!(stats.total_tokens, 3);
        assert_eq!(stats.max_tokens_per_leaf, 2);
        assert_eq!(stats.distinct_tokens, vec!["0.5", "1", "Float"]);
    }

    #[test]
    fn single_leaf_token_stats() {
        let tree = tree_of("(root (a 1))");
        let stats = compute_parameter_tree_token_stats_v1(&tree).expect("stats");
        assert_eq!(stats.leaf_count, 1);
        assert_eq!(stats.total_tokens, 1);
        assert_eq!(stats.max_tokens_per_leaf, 1);
        assert_eq!(stats.distinct_tokens, vec!["1"]);
    }
}
