//! AMI parameter tree structural diff entry filtering core (P4B-02b21).
//!
//! Filters sequences of atomic structural diff entries (`TreeDiffEntryV1`, P4B-02b11)
//! by applying predicate closures over diff entry properties and node paths (`filter_parameter_tree_diffs_v1`).
//! Fail-closed: empty diff lists or empty filtered diff result are strictly rejected.

use crate::parameter_tree_diff_v1::TreeDiffEntryV1;

/// Scope policy for the parameter tree diff filter core.
pub const PARAMETER_TREE_DIFF_FILTER_POLICY_V1: &str =
    "sipi.p4b-02b21.parameter-tree-diff-filter-v1.diff-entry-filtering";

/// Fail-closed errors during AMI parameter tree diff entry filtering.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterTreeDiffFilterErrorV1 {
    EmptyDiffList,
    EmptyFilteredResult,
}

fn diff_path(entry: &TreeDiffEntryV1) -> &str {
    match entry {
        TreeDiffEntryV1::MissingNode { path }
        | TreeDiffEntryV1::ExtraNode { path }
        | TreeDiffEntryV1::KindMismatch { path }
        | TreeDiffEntryV1::ValueMismatch { path, .. } => path.as_str(),
    }
}

/// Filter a sequence of structural diff entries using a predicate closure over the entry and path.
pub fn filter_parameter_tree_diffs_v1<F>(
    diffs: &[TreeDiffEntryV1],
    predicate: F,
) -> Result<Vec<TreeDiffEntryV1>, ParameterTreeDiffFilterErrorV1>
where
    F: Fn(&str, &TreeDiffEntryV1) -> bool,
{
    if diffs.is_empty() {
        return Err(ParameterTreeDiffFilterErrorV1::EmptyDiffList);
    }

    let filtered: Vec<TreeDiffEntryV1> = diffs
        .iter()
        .filter(|diff| predicate(diff_path(diff), diff))
        .cloned()
        .collect();

    if filtered.is_empty() {
        return Err(ParameterTreeDiffFilterErrorV1::EmptyFilteredResult);
    }
    Ok(filtered)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn policy_fixed() {
        assert_eq!(
            PARAMETER_TREE_DIFF_FILTER_POLICY_V1,
            "sipi.p4b-02b21.parameter-tree-diff-filter-v1.diff-entry-filtering"
        );
    }

    #[test]
    fn filters_diffs_by_predicate() {
        let diffs = vec![
            TreeDiffEntryV1::MissingNode {
                path: "root.node_b".to_string(),
            },
            TreeDiffEntryV1::ExtraNode {
                path: "root.node_c".to_string(),
            },
        ];

        let filtered = filter_parameter_tree_diffs_v1(&diffs, |path, _| path != "root.node_b")
            .expect("filter");
        assert_eq!(filtered.len(), 1);
        assert_eq!(
            filtered[0],
            TreeDiffEntryV1::ExtraNode {
                path: "root.node_c".to_string()
            }
        );
    }

    #[test]
    fn rejects_empty_diff_list() {
        assert_eq!(
            filter_parameter_tree_diffs_v1(&[], |_, _| true),
            Err(ParameterTreeDiffFilterErrorV1::EmptyDiffList)
        );
    }

    #[test]
    fn rejects_empty_filtered_result() {
        let diffs = vec![TreeDiffEntryV1::MissingNode {
            path: "root.node_b".to_string(),
        }];
        assert_eq!(
            filter_parameter_tree_diffs_v1(&diffs, |_, _| false),
            Err(ParameterTreeDiffFilterErrorV1::EmptyFilteredResult)
        );
    }
}
