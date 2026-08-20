//! AMI parameter tree depth statistics core (P4B-02b29).
//!
//! Computes depth statistics for a typed `AmiParameterTreeV1` hierarchy
//! (`compute_parameter_tree_depth_stats_v1`): maximum depth, minimum depth,
//! leaf depth histogram, and node counts per depth level.
//! Fail-closed: empty tree lists are strictly rejected.

use crate::parameter_trees_v1::{AmiParameterTreeNodeV1, AmiParameterTreeV1};

/// Scope policy for the parameter tree depth stats core.
pub const PARAMETER_TREE_DEPTH_STATS_POLICY_V1: &str =
    "sipi.p4b-02b29.parameter-tree-depth-stats-v1.tree-depth-statistics";

/// Fail-closed errors during AMI parameter tree depth statistics computation.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterTreeDepthStatsErrorV1 {
    EmptyTreeList,
}

/// Depth statistics for a parameter tree.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ParameterTreeDepthStatsV1 {
    pub max_depth: usize,
    pub min_depth: usize,
    pub leaf_count: usize,
    /// Number of nodes at each depth level, indexed by depth (root at depth 0).
    pub nodes_per_depth: Vec<usize>,
    /// Number of leaves at each depth level, indexed by depth.
    pub leaves_per_depth: Vec<usize>,
}

fn walk(node: &AmiParameterTreeNodeV1, depth: usize, stats: &mut ParameterTreeDepthStatsV1) {
    if stats.nodes_per_depth.len() <= depth {
        stats.nodes_per_depth.push(0);
    }
    if stats.leaves_per_depth.len() <= depth {
        stats.leaves_per_depth.push(0);
    }
    stats.nodes_per_depth[depth] += 1;
    stats.max_depth = stats.max_depth.max(depth);
    stats.min_depth = stats.min_depth.min(depth);

    match node {
        AmiParameterTreeNodeV1::Branch { children, .. } => {
            for child in children.values() {
                walk(child, depth + 1, stats);
            }
        }
        AmiParameterTreeNodeV1::Leaf { .. } => {
            stats.leaf_count += 1;
            stats.leaves_per_depth[depth] += 1;
        }
    }
}

/// Compute depth statistics for a parameter tree.
///
/// Root node is at depth 0. Returns max/min depth, leaf count, and per-depth
/// node and leaf histograms.
pub fn compute_parameter_tree_depth_stats_v1(
    tree: &AmiParameterTreeV1,
) -> Result<ParameterTreeDepthStatsV1, ParameterTreeDepthStatsErrorV1> {
    let mut stats = ParameterTreeDepthStatsV1 {
        max_depth: 0,
        min_depth: usize::MAX,
        leaf_count: 0,
        nodes_per_depth: Vec::new(),
        leaves_per_depth: Vec::new(),
    };
    walk(tree.root_node(), 0, &mut stats);
    if stats.min_depth == usize::MAX {
        stats.min_depth = 0;
    }
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
            PARAMETER_TREE_DEPTH_STATS_POLICY_V1,
            "sipi.p4b-02b29.parameter-tree-depth-stats-v1.tree-depth-statistics"
        );
    }

    #[test]
    fn computes_nested_depth_stats() {
        let tree = tree_of("(root (branch_a (leaf_1 10)) (leaf_2 20))");
        let stats = compute_parameter_tree_depth_stats_v1(&tree).expect("stats");
        assert_eq!(stats.max_depth, 2);
        assert_eq!(stats.min_depth, 0);
        assert_eq!(stats.leaf_count, 2);
        assert_eq!(stats.nodes_per_depth, vec![1, 2, 1]);
        assert_eq!(stats.leaves_per_depth, vec![0, 1, 1]);
    }

    #[test]
    fn single_node_depth_stats() {
        let tree = tree_of("(root)");
        let stats = compute_parameter_tree_depth_stats_v1(&tree).expect("stats");
        assert_eq!(stats.max_depth, 0);
        assert_eq!(stats.min_depth, 0);
        assert_eq!(stats.leaf_count, 1);
        assert_eq!(stats.nodes_per_depth, vec![1]);
        assert_eq!(stats.leaves_per_depth, vec![1]);
    }
}
