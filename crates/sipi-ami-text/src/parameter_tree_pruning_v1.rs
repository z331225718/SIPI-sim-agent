//! AMI parameter tree structural pruning core (P4B-02b13).
//!
//! Prunes target sub-trees or nodes from typed `AmiParameterTreeV1` hierarchies (P4B-02b7)
//! by path segments (`prune_parameter_tree_v1`).
//! Fail-closed: empty path queries, root node name mismatch, or target path not found
//! are strictly rejected.

use crate::parameter_trees_v1::{AmiParameterTreeNodeV1, AmiParameterTreeV1};

/// Scope policy for the parameter tree pruning core.
pub const PARAMETER_TREE_PRUNING_POLICY_V1: &str =
    "sipi.p4b-02b13.parameter-tree-pruning-v1.tree-structural-pruning";

/// Fail-closed errors during AMI parameter tree structural pruning.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterTreePruningErrorV1 {
    EmptyPath,
    RootMismatch,
    PathNotFound(String),
    CannotPruneRoot,
}

fn prune_node(
    node: &AmiParameterTreeNodeV1,
    segments: &[&str],
) -> Result<AmiParameterTreeNodeV1, ParameterTreePruningErrorV1> {
    if segments.is_empty() {
        return Err(ParameterTreePruningErrorV1::EmptyPath);
    }
    let target = segments[0];

    match node {
        AmiParameterTreeNodeV1::Branch { name, children } => {
            if !children.contains_key(target) {
                return Err(ParameterTreePruningErrorV1::PathNotFound(
                    target.to_string(),
                ));
            }

            if segments.len() == 1 {
                // Prune target child node from branch
                let mut new_children = children.clone();
                new_children.remove(target);
                Ok(AmiParameterTreeNodeV1::Branch {
                    name: name.clone(),
                    children: new_children,
                })
            } else {
                // Recurse into target child
                let child = &children[target];
                let pruned_child = prune_node(child, &segments[1..])?;
                let mut new_children = children.clone();
                new_children.insert(target.to_string(), pruned_child);
                Ok(AmiParameterTreeNodeV1::Branch {
                    name: name.clone(),
                    children: new_children,
                })
            }
        }
        AmiParameterTreeNodeV1::Leaf { name, .. } => {
            Err(ParameterTreePruningErrorV1::PathNotFound(name.clone()))
        }
    }
}

/// Prune a node or sub-tree at the specified path from a parameter tree.
pub fn prune_parameter_tree_v1(
    tree: &AmiParameterTreeV1,
    path_segments: &[&str],
) -> Result<AmiParameterTreeV1, ParameterTreePruningErrorV1> {
    if path_segments.is_empty() {
        return Err(ParameterTreePruningErrorV1::EmptyPath);
    }
    if path_segments[0] != tree.root_name() {
        return Err(ParameterTreePruningErrorV1::RootMismatch);
    }
    if path_segments.len() == 1 {
        return Err(ParameterTreePruningErrorV1::CannotPruneRoot);
    }

    let pruned_node = prune_node(tree.root_node(), &path_segments[1..])?;
    Ok(AmiParameterTreeV1::new(tree.root_name(), pruned_node))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::parameter_trees_v1::build_parameter_trees_v1;
    use crate::{ParseLimitsV1, parse_ami_text_v1};

    fn limits() -> ParseLimitsV1 {
        ParseLimitsV1::try_new(1024, 16, 64, 128).unwrap()
    }

    #[test]
    fn policy_fixed() {
        assert_eq!(
            PARAMETER_TREE_PRUNING_POLICY_V1,
            "sipi.p4b-02b13.parameter-tree-pruning-v1.tree-structural-pruning"
        );
    }

    #[test]
    fn prunes_branch_and_leaf_nodes() {
        let doc = parse_ami_text_v1(
            b"(Reserved_Parameters (tx_swing Float 0.5) (dfe (tap_1 Integer 2)))",
            limits(),
        )
        .expect("parse");
        let trees = build_parameter_trees_v1(&doc).expect("build");

        // Prune leaf node tx_swing
        let pruned_leaf = prune_parameter_tree_v1(&trees[0], &["Reserved_Parameters", "tx_swing"])
            .expect("prune leaf");
        if let AmiParameterTreeNodeV1::Branch { children, .. } = pruned_leaf.root_node() {
            assert_eq!(children.len(), 1);
            assert!(!children.contains_key("tx_swing"));
            assert!(children.contains_key("dfe"));
        } else {
            panic!("expected branch");
        }

        // Prune branch node dfe
        let pruned_branch = prune_parameter_tree_v1(&trees[0], &["Reserved_Parameters", "dfe"])
            .expect("prune branch");
        if let AmiParameterTreeNodeV1::Branch { children, .. } = pruned_branch.root_node() {
            assert_eq!(children.len(), 1);
            assert!(children.contains_key("tx_swing"));
            assert!(!children.contains_key("dfe"));
        } else {
            panic!("expected branch");
        }
    }

    #[test]
    fn rejects_cannot_prune_root() {
        let doc = parse_ami_text_v1(b"(root (a 1))", limits()).expect("parse");
        let trees = build_parameter_trees_v1(&doc).expect("build");
        assert_eq!(
            prune_parameter_tree_v1(&trees[0], &["root"]),
            Err(ParameterTreePruningErrorV1::CannotPruneRoot)
        );
    }

    #[test]
    fn rejects_root_mismatch() {
        let doc = parse_ami_text_v1(b"(root (a 1))", limits()).expect("parse");
        let trees = build_parameter_trees_v1(&doc).expect("build");
        assert_eq!(
            prune_parameter_tree_v1(&trees[0], &["other_root", "a"]),
            Err(ParameterTreePruningErrorV1::RootMismatch)
        );
    }

    #[test]
    fn rejects_path_not_found() {
        let doc = parse_ami_text_v1(b"(root (a 1))", limits()).expect("parse");
        let trees = build_parameter_trees_v1(&doc).expect("build");
        assert_eq!(
            prune_parameter_tree_v1(&trees[0], &["root", "nonexistent"]),
            Err(ParameterTreePruningErrorV1::PathNotFound(
                "nonexistent".to_string()
            ))
        );
    }
}
