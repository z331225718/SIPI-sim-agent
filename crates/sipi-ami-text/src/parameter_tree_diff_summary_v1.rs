//! AMI parameter tree structural diff textual summary report core (P4B-02b22).
//!
//! Generates structured human-readable text reports (`generate_parameter_tree_diff_summary_v1`)
//! summarizing atomic structural diff entries (`TreeDiffEntryV1`, P4B-02b11) and metrics (`AmiParameterTreeDiffStatsV1`, P4B-02b20).
//! Fail-closed: invalid diff inputs fail closed; empty diff lists produce an identical status summary.

use crate::parameter_tree_diff_stats_v1::{
    AmiParameterTreeDiffStatsV1, compute_parameter_tree_diff_stats_v1,
};
use crate::parameter_tree_diff_v1::TreeDiffEntryV1;

/// Scope policy for the parameter tree diff summary core.
pub const PARAMETER_TREE_DIFF_SUMMARY_POLICY_V1: &str =
    "sipi.p4b-02b22.parameter-tree-diff-summary-v1.diff-summary-report";

/// Fail-closed errors during AMI parameter tree diff summary generation.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterTreeDiffSummaryErrorV1 {
    InvalidDiffSequence(String),
}

/// A structured AMI parameter tree diff summary report.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct AmiParameterTreeDiffSummaryReportV1 {
    pub stats: AmiParameterTreeDiffStatsV1,
    pub summary_text: String,
}

/// Generate a structured diff summary report over a sequence of diff entries.
pub fn generate_parameter_tree_diff_summary_v1(
    diffs: &[TreeDiffEntryV1],
) -> Result<AmiParameterTreeDiffSummaryReportV1, ParameterTreeDiffSummaryErrorV1> {
    let stats = compute_parameter_tree_diff_stats_v1(diffs)
        .map_err(|e| ParameterTreeDiffSummaryErrorV1::InvalidDiffSequence(format!("{e:?}")))?;

    let mut lines = Vec::new();
    lines.push("AMI Parameter Tree Diff Summary Report".to_string());
    lines.push(format!("Policy: {}", PARAMETER_TREE_DIFF_SUMMARY_POLICY_V1));

    if stats.is_identical() {
        lines.push("Status: Identical (0 differences)".to_string());
    } else {
        lines.push(format!(
            "Status: Modified ({} differences)",
            stats.total_diffs
        ));
        lines.push(format!("  Missing Nodes: {}", stats.missing_nodes_count));
        lines.push(format!("  Extra Nodes: {}", stats.extra_nodes_count));
        lines.push(format!(
            "  Kind Mismatches: {}",
            stats.kind_mismatches_count
        ));
        lines.push(format!(
            "  Value Mismatches: {}",
            stats.value_mismatches_count
        ));

        lines.push("Diff Details:".to_string());
        for entry in diffs {
            match entry {
                TreeDiffEntryV1::MissingNode { path } => {
                    lines.push(format!("  - [Missing] {path}"));
                }
                TreeDiffEntryV1::ExtraNode { path } => {
                    lines.push(format!("  - [Extra] {path}"));
                }
                TreeDiffEntryV1::KindMismatch { path } => {
                    lines.push(format!("  - [Kind Mismatch] {path}"));
                }
                TreeDiffEntryV1::ValueMismatch { path, left, right } => {
                    lines.push(format!(
                        "  - [Value Mismatch] {path}: left=[{}] right=[{}]",
                        left.join(" "),
                        right.join(" ")
                    ));
                }
            }
        }
    }

    let summary_text = lines.join(
        "
",
    );
    Ok(AmiParameterTreeDiffSummaryReportV1 {
        stats,
        summary_text,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn policy_fixed() {
        assert_eq!(
            PARAMETER_TREE_DIFF_SUMMARY_POLICY_V1,
            "sipi.p4b-02b22.parameter-tree-diff-summary-v1.diff-summary-report"
        );
    }

    #[test]
    fn generates_identical_summary() {
        let report = generate_parameter_tree_diff_summary_v1(&[]).expect("report");
        assert!(report.stats.is_identical());
        assert!(
            report
                .summary_text
                .contains("Status: Identical (0 differences)")
        );
    }

    #[test]
    fn generates_modified_summary() {
        let diffs = vec![
            TreeDiffEntryV1::MissingNode {
                path: "root.node_b".to_string(),
            },
            TreeDiffEntryV1::ValueMismatch {
                path: "root.val".to_string(),
                left: vec!["0.5".to_string()],
                right: vec!["0.9".to_string()],
            },
        ];

        let report = generate_parameter_tree_diff_summary_v1(&diffs).expect("report");
        assert_eq!(report.stats.total_diffs, 2);
        assert!(
            report
                .summary_text
                .contains("Status: Modified (2 differences)")
        );
        assert!(report.summary_text.contains("- [Missing] root.node_b"));
        assert!(
            report
                .summary_text
                .contains("- [Value Mismatch] root.val: left=[0.5] right=[0.9]")
        );
    }
}
