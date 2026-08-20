//! AMI parameter tree structural comparison & diff core (P4B-02b11).
//!
//! Compares two typed `AmiParameterTreeV1` hierarchies (P4B-02b7) and reports
//! exact structural differences (`diff_parameter_trees_v1`).
//! Fail-closed: root node name mismatch or invalid tree input is strictly rejected.

use std::collections::BTreeSet;

use crate::parameter_trees_v1::{AmiParameterTreeNodeV1, AmiParameterTreeV1};

/// Scope policy for the parameter tree diff core.
pub const PARAMETER_TREE_DIFF_POLICY_V1: &str =
    "sipi.p4b-02b11.parameter-tree-diff-v1.tree-structural-diff";

/// Fail-closed errors during AMI parameter tree structural comparison.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterTreeDiffErrorV1 {
    RootMismatch { expected: String, actual: String },
}

/// One atomic structural difference between two parameter trees.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum TreeDiffEntryV1 {
    MissingNode { path: String },
    ExtraNode { path: String },
    KindMismatch { path: String },
    ValueMismatch { path: String, left: Vec<String>, right: Vec<String> },
}

fn diff_nodes(
    path_prefix: &str,
    left: &AmiParameterTreeNodeV1,
    right: &AmiParameterTreeNodeV1,
    diffs: &mut Vec<TreeDiffEntryV1>,
) {
    let current_path = if path_prefix.is_empty() {
        left.name().to_string()
    } else {
        format!("{path_prefix}.{}", left.name())
    };

    match (left, right) {
        (
            AmiParameterTreeNodeV1::Branch { children: l_children, .. },
            AmiParameterTreeNodeV1::Branch { children: r_children, .. },
        ) => {
            let all_keys: BTreeSet<&String> = l_children.keys().chain(r_children.keys()).collect();
            for key in all_keys {
                let l_child = l_children.get(key);
                let r_child = r_children.get(key);
                let child_path = format!("{current_path}.{key}");
                match (l_child, r_child) {
                    (Some(l), Some(r)) => diff_nodes(&current_path, l, r, diffs),
                    (Some(_), None) => diffs.push(TreeDiffEntryV1::MissingNode { path: child_path }),
                    (None, Some(_)) => diffs.push(TreeDiffEntryV1::ExtraNode { path: child_path }),
                    (None, None) => unreachable!(),
                }
            }
        }
        (
            AmiParameterTreeNodeV1::Leaf { value_tokens: l_vals, .. },
            AmiParameterTreeNodeV1::Leaf { value_tokens: r_vals, .. },
        ) => {
            if l_vals != r_vals {
                diffs.push(TreeDiffEntryV1::ValueMismatch {
                    path: current_path,
                    left: l_vals.clone(),
                    right: r_vals.clone(),
                });
            }
        }
        _ => {
            diffs.push(TreeDiffEntryV1::KindMismatch { path: current_path });
        }
    }
}

/// Compute structural differences between two parameter trees.
pub fn diff_parameter_trees_v1(
    left: &AmiParameterTreeV1,
    right: &AmiParameterTreeV1,
) -> Result<Vec<TreeDiffEntryV1>, ParameterTreeDiffErrorV1> {
    if left.root_name() != right.root_name() {
        return Err(ParameterTreeDiffErrorV1::RootMismatch {
            expected: left.root_name().to_string(),
            actual: right.root_name().to_string(),
        });
    }
    let mut diffs = Vec::new();
    diff_nodes("", left.root_node(), right.root_node(), &mut diffs);
    Ok(diffs)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::parameter_trees_v1::build_parameter_trees_v1;
    use crate::{parse_ami_text_v1, ParseLimitsV1};

    fn limits() -> ParseLimitsV1 {
        ParseLimitsV1::try_new(1024, 16, 64, 128).unwrap()
    }

    #[test]
    fn policy_fixed() {
        assert_eq!(
            PARAMETER_TREE_DIFF_POLICY_V1,
            "sipi.p4b-02b11.parameter-tree-diff-v1.tree-structural-diff"
        );
    }

    #[test]
    fn diffs_identical_trees_as_empty() {
        let doc = parse_ami_text_v1(
            b"(Reserved_Parameters (tx_swing Float 0.5))",
            limits(),
        )
        .expect("parse");
        let trees = build_parameter_trees_v1(&doc).expect("build");
        let diffs = diff_parameter_trees_v1(&trees[0], &trees[0]).expect("diff");
        assert!(diffs.is_empty());
    }

    #[test]
    fn detects_missing_and_extra_nodes() {
        let doc1 = parse_ami_text_v1(b"(root (node_a 1) (node_b 2))", limits()).expect("parse");
        let doc2 = parse_ami_text_v1(b"(root (node_a 1) (node_c 3))", limits()).expect("parse");
        let t1 = &build_parameter_trees_v1(&doc1).unwrap()[0];
        let t2 = &build_parameter_trees_v1(&doc2).unwrap()[0];
        let diffs = diff_parameter_trees_v1(t1, t2).unwrap();
        assert_eq!(diffs.len(), 2);
        assert!(diffs.contains(&TreeDiffEntryV1::MissingNode {
            path: "root.node_b".to_string()
        }));
        assert!(diffs.contains(&TreeDiffEntryV1::ExtraNode {
            path: "root.node_c".to_string()
        }));
    }

    #[test]
    fn detects_value_and_kind_mismatches() {
        let doc1 = parse_ami_text_v1(b"(root (val Float 0.5) (kind 10))", limits()).expect("parse");
        let doc2 = parse_ami_text_v1(b"(root (val Float 0.9) (kind (sub 10)))", limits()).expect("parse");
        let t1 = &build_parameter_trees_v1(&doc1).unwrap()[0];
        let t2 = &build_parameter_trees_v1(&doc2).unwrap()[0];
        let diffs = diff_parameter_trees_v1(t1, t2).unwrap();
        assert_eq!(diffs.len(), 2);
        assert!(diffs.contains(&TreeDiffEntryV1::ValueMismatch {
            path: "root.val".to_string(),
            left: vec!["Float".to_string(), "0.5".to_string()],
            right: vec!["Float".to_string(), "0.9".to_string()],
        }));
        assert!(diffs.contains(&TreeDiffEntryV1::KindMismatch {
            path: "root.kind".to_string()
        }));
    }

    #[test]
    fn rejects_root_mismatch() {
        let doc1 = parse_ami_text_v1(b"(root_a (a 1))", limits()).expect("parse");
        let doc2 = parse_ami_text_v1(b"(root_b (a 1))", limits()).expect("parse");
        let t1 = &build_parameter_trees_v1(&doc1).unwrap()[0];
        let t2 = &build_parameter_trees_v1(&doc2).unwrap()[0];
        assert!(matches!(
            diff_parameter_trees_v1(t1, t2),
            Err(ParameterTreeDiffErrorV1::RootMismatch { .. })
        ));
    }
}
