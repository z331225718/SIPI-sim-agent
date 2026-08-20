//! AMI parameter tree structural merge core (P4B-02b12).
//!
//! Merges two typed `AmiParameterTreeV1` hierarchies (P4B-02b7) into a unified tree
//! (`merge_parameter_trees_v1`), where right-side nodes override or augment left-side nodes.
//! Fail-closed: root node name mismatch or node kind conflict (Branch vs Leaf) is strictly rejected.

use std::collections::BTreeMap;

use crate::parameter_trees_v1::{AmiParameterTreeNodeV1, AmiParameterTreeV1};

/// Scope policy for the parameter tree merge core.
pub const PARAMETER_TREE_MERGE_POLICY_V1: &str =
    "sipi.p4b-02b12.parameter-tree-merge-v1.tree-structural-merge";

/// Fail-closed errors during AMI parameter tree structural merging.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterTreeMergeErrorV1 {
    RootMismatch { expected: String, actual: String },
    KindConflict { path: String },
}

fn merge_nodes(
    path_prefix: &str,
    left: &AmiParameterTreeNodeV1,
    right: &AmiParameterTreeNodeV1,
) -> Result<AmiParameterTreeNodeV1, ParameterTreeMergeErrorV1> {
    let current_path = if path_prefix.is_empty() {
        left.name().to_string()
    } else {
        format!("{path_prefix}.{}", left.name())
    };

    match (left, right) {
        (
            AmiParameterTreeNodeV1::Branch { name, children: l_children },
            AmiParameterTreeNodeV1::Branch { children: r_children, .. },
        ) => {
            let mut merged_children = BTreeMap::new();
            for (key, l_child) in l_children {
                if let Some(r_child) = r_children.get(key) {
                    let merged_child = merge_nodes(&current_path, l_child, r_child)?;
                    merged_children.insert(key.clone(), merged_child);
                } else {
                    merged_children.insert(key.clone(), l_child.clone());
                }
            }
            for (key, r_child) in r_children {
                if !l_children.contains_key(key) {
                    merged_children.insert(key.clone(), r_child.clone());
                }
            }
            Ok(AmiParameterTreeNodeV1::Branch {
                name: name.clone(),
                children: merged_children,
            })
        }
        (
            AmiParameterTreeNodeV1::Leaf { .. },
            AmiParameterTreeNodeV1::Leaf { .. },
        ) => {
            // Right-side leaf overrides left-side leaf
            Ok(right.clone())
        }
        _ => Err(ParameterTreeMergeErrorV1::KindConflict { path: current_path }),
    }
}

/// Merge right parameter tree into left parameter tree.
pub fn merge_parameter_trees_v1(
    left: &AmiParameterTreeV1,
    right: &AmiParameterTreeV1,
) -> Result<AmiParameterTreeV1, ParameterTreeMergeErrorV1> {
    if left.root_name() != right.root_name() {
        return Err(ParameterTreeMergeErrorV1::RootMismatch {
            expected: left.root_name().to_string(),
            actual: right.root_name().to_string(),
        });
    }
    let merged_node = merge_nodes("", left.root_node(), right.root_node())?;
    Ok(AmiParameterTreeV1::new(left.root_name(), merged_node))
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
            PARAMETER_TREE_MERGE_POLICY_V1,
            "sipi.p4b-02b12.parameter-tree-merge-v1.tree-structural-merge"
        );
    }

    #[test]
    fn merges_complementary_branches_and_overrides_leaves() {
        let doc1 = parse_ami_text_v1(b"(root (node_a 1) (val Float 0.5))", limits()).expect("parse");
        let doc2 = parse_ami_text_v1(b"(root (node_b 2) (val Float 0.9))", limits()).expect("parse");
        let t1 = &build_parameter_trees_v1(&doc1).unwrap()[0];
        let t2 = &build_parameter_trees_v1(&doc2).unwrap()[0];
        let merged = merge_parameter_trees_v1(t1, t2).expect("merge");

        assert_eq!(merged.root_name(), "root");
        if let AmiParameterTreeNodeV1::Branch { children, .. } = merged.root_node() {
            assert_eq!(children.len(), 3);
            assert!(children.contains_key("node_a"));
            assert!(children.contains_key("node_b"));
            if let AmiParameterTreeNodeV1::Leaf { value_tokens, .. } = &children["val"] {
                assert_eq!(value_tokens, &["Float", "0.9"]);
            } else {
                panic!("expected leaf for val");
            }
        } else {
            panic!("expected branch root");
        }
    }

    #[test]
    fn rejects_kind_conflict() {
        let doc1 = parse_ami_text_v1(b"(root (node 1))", limits()).expect("parse");
        let doc2 = parse_ami_text_v1(b"(root (node (sub 2)))", limits()).expect("parse");
        let t1 = &build_parameter_trees_v1(&doc1).unwrap()[0];
        let t2 = &build_parameter_trees_v1(&doc2).unwrap()[0];
        assert!(matches!(
            merge_parameter_trees_v1(t1, t2),
            Err(ParameterTreeMergeErrorV1::KindConflict { .. })
        ));
    }

    #[test]
    fn rejects_root_mismatch() {
        let doc1 = parse_ami_text_v1(b"(root_a (a 1))", limits()).expect("parse");
        let doc2 = parse_ami_text_v1(b"(root_b (a 1))", limits()).expect("parse");
        let t1 = &build_parameter_trees_v1(&doc1).unwrap()[0];
        let t2 = &build_parameter_trees_v1(&doc2).unwrap()[0];
        assert!(matches!(
            merge_parameter_trees_v1(t1, t2),
            Err(ParameterTreeMergeErrorV1::RootMismatch { .. })
        ));
    }
}
