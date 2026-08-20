//! AMI parameter tree structural diff metrics & statistics core (P4B-02b20).
//!
//! Computes summary statistics (`AmiParameterTreeDiffStatsV1`) over atomic structural diff entry sequences
//! (`TreeDiffEntryV1`, P4B-02b11) generated between parameter trees (`compute_parameter_tree_diff_stats_v1`).
//! Fail-closed: empty diff lists produce zero counts without failing.

use crate::parameter_tree_diff_v1::TreeDiffEntryV1;

/// Scope policy for the parameter tree diff stats core.
pub const PARAMETER_TREE_DIFF_STATS_POLICY_V1: &str =
    "sipi.p4b-02b20.parameter-tree-diff-stats-v1.tree-diff-statistics";

/// Fail-closed errors during AMI parameter tree diff stats computation.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterTreeDiffStatsErrorV1 {
    InvalidDiffSequence(String),
}

/// Summary statistics for structural diff entries between two parameter trees.
#[derive(Clone, Debug, Default, Eq, PartialEq)]
pub struct AmiParameterTreeDiffStatsV1 {
    pub total_diffs: usize,
    pub missing_nodes_count: usize,
    pub extra_nodes_count: usize,
    pub kind_mismatches_count: usize,
    pub value_mismatches_count: usize,
}

impl AmiParameterTreeDiffStatsV1 {
    pub const fn is_identical(&self) -> bool {
        self.total_diffs == 0
    }
}

/// Compute summary statistics over a sequence of diff entries.
pub fn compute_parameter_tree_diff_stats_v1(
    diffs: &[TreeDiffEntryV1],
) -> Result<AmiParameterTreeDiffStatsV1, ParameterTreeDiffStatsErrorV1> {
    let mut stats = AmiParameterTreeDiffStatsV1::default();
    stats.total_diffs = diffs.len();

    for diff in diffs {
        match diff {
            TreeDiffEntryV1::MissingNode { .. } => stats.missing_nodes_count += 1,
            TreeDiffEntryV1::ExtraNode { .. } => stats.extra_nodes_count += 1,
            TreeDiffEntryV1::KindMismatch { .. } => stats.kind_mismatches_count += 1,
            TreeDiffEntryV1::ValueMismatch { .. } => stats.value_mismatches_count += 1,
        }
    }

    Ok(stats)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn policy_fixed() {
        assert_eq!(
            PARAMETER_TREE_DIFF_STATS_POLICY_V1,
            "sipi.p4b-02b20.parameter-tree-diff-stats-v1.tree-diff-statistics"
        );
    }

    #[test]
    fn computes_stats_correctly() {
        let diffs = vec![
            TreeDiffEntryV1::MissingNode { path: "root.a".to_string() },
            TreeDiffEntryV1::ExtraNode { path: "root.b".to_string() },
            TreeDiffEntryV1::KindMismatch { path: "root.c".to_string() },
            TreeDiffEntryV1::ValueMismatch {
                path: "root.d".to_string(),
                left: vec!["0.5".to_string()],
                right: vec!["0.9".to_string()],
            },
        ];

        let stats = compute_parameter_tree_diff_stats_v1(&diffs).expect("stats");
        assert_eq!(stats.total_diffs, 4);
        assert_eq!(stats.missing_nodes_count, 1);
        assert_eq!(stats.extra_nodes_count, 1);
        assert_eq!(stats.kind_mismatches_count, 1);
        assert_eq!(stats.value_mismatches_count, 1);
        assert!(!stats.is_identical());
    }

    #[test]
    fn empty_diffs_produce_zero_stats() {
        let stats = compute_parameter_tree_diff_stats_v1(&[]).expect("stats");
        assert_eq!(stats.total_diffs, 0);
        assert!(stats.is_identical());
    }
}
