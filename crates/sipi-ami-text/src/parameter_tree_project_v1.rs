//! AMI parameter tree leaf projection core (P4B-02b35).
//!
//! Projects an `AmiParameterTreeV1` onto a caller-supplied set of leaf names:
//! the result keeps exactly the requested leaves (with their ancestor branches)
//! under the same root name. Fail-closed: an empty selection and any requested
//! name that is not a leaf in the tree are strictly rejected.

use std::collections::{BTreeMap, BTreeSet};

use crate::{AmiParameterTreeNodeV1, AmiParameterTreeV1};

/// Scope policy for the parameter tree leaf projection core.
pub const PARAMETER_TREE_LEAF_PROJECTION_POLICY_V1: &str =
    "sipi.p4b-02b35.parameter-tree-leaf-projection-v1.name-set-projection";

/// Fail-closed errors during parameter tree leaf projection.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterTreeProjectErrorV1 {
    /// The requested leaf name set is empty.
    EmptySelection,
    /// A requested name is not a leaf in the tree (absent, or only a branch).
    MissingLeaf(String),
}

fn collect_leaf_names(node: &AmiParameterTreeNodeV1, out: &mut BTreeSet<String>) {
    match node {
        AmiParameterTreeNodeV1::Branch { children, .. } => {
            for child in children.values() {
                collect_leaf_names(child, out);
            }
        }
        AmiParameterTreeNodeV1::Leaf { name, .. } => {
            out.insert(name.clone());
        }
    }
}

fn project_node(
    node: &AmiParameterTreeNodeV1,
    keep: &BTreeSet<String>,
) -> Option<AmiParameterTreeNodeV1> {
    match node {
        AmiParameterTreeNodeV1::Leaf { name, .. } => {
            if keep.contains(name) {
                Some(node.clone())
            } else {
                None
            }
        }
        AmiParameterTreeNodeV1::Branch { name, children } => {
            let mut projected = BTreeMap::new();
            for (key, child) in children {
                if let Some(kept_child) = project_node(child, keep) {
                    projected.insert(key.clone(), kept_child);
                }
            }
            if projected.is_empty() {
                None
            } else {
                Some(AmiParameterTreeNodeV1::Branch {
                    name: name.clone(),
                    children: projected,
                })
            }
        }
    }
}

/// Project `tree` onto `keep`: keep exactly the requested leaves with their
/// ancestor branches, under the same root name.
///
/// Fails closed on an empty selection or any requested name that is not a leaf
/// in the tree. Traversal order is canonical (branch children in byte-wise name
/// order, depth first); the projected tree preserves child ordering.
pub fn project_parameter_tree_leaves_v1(
    tree: &AmiParameterTreeV1,
    keep: &BTreeSet<String>,
) -> Result<AmiParameterTreeV1, ParameterTreeProjectErrorV1> {
    if keep.is_empty() {
        return Err(ParameterTreeProjectErrorV1::EmptySelection);
    }
    let mut leaf_names = BTreeSet::new();
    collect_leaf_names(tree.root_node(), &mut leaf_names);
    for name in keep {
        if !leaf_names.contains(name) {
            return Err(ParameterTreeProjectErrorV1::MissingLeaf(name.clone()));
        }
    }
    let projected_root = project_node(tree.root_node(), keep)
        .expect("non-empty keep of existing leaves yields a non-empty root");
    Ok(AmiParameterTreeV1::new(tree.root_name(), projected_root))
}

#[cfg(test)]
mod tests {
    use super::*;

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

    fn keep_of(names: &[&str]) -> BTreeSet<String> {
        names.iter().map(|s| s.to_string()).collect()
    }

    fn count_leaves(node: &AmiParameterTreeNodeV1) -> usize {
        match node {
            AmiParameterTreeNodeV1::Leaf { .. } => 1,
            AmiParameterTreeNodeV1::Branch { children, .. } => {
                children.values().map(count_leaves).sum()
            }
        }
    }

    #[test]
    fn projects_requested_subset() {
        let t = tree(branch(
            "root",
            vec![
                leaf("gain", &["Float", "0.5"]),
                leaf("steps", &["Integer", "7"]),
                leaf("enabled", &["Boolean", "True"]),
                leaf("mode", &["String", "fast"]),
            ],
        ));
        let projected =
            project_parameter_tree_leaves_v1(&t, &keep_of(&["gain", "mode"])).expect("projected");
        assert_eq!(projected.root_name(), "root");
        assert_eq!(count_leaves(projected.root_node()), 2);
        let root = projected.root_node();
        match root {
            AmiParameterTreeNodeV1::Branch { children, .. } => {
                assert_eq!(children.len(), 2);
                assert!(children.contains_key("gain"));
                assert!(children.contains_key("mode"));
                assert!(!children.contains_key("steps"));
            }
            AmiParameterTreeNodeV1::Leaf { .. } => panic!("expected branch root"),
        }
    }

    #[test]
    fn keeps_ancestor_branches_for_nested_leaf() {
        let t = tree(branch(
            "root",
            vec![
                branch(
                    "sub",
                    vec![
                        leaf("deep", &["Float", "1.0"]),
                        leaf("other", &["Integer", "2"]),
                    ],
                ),
                leaf("top", &["Boolean", "True"]),
            ],
        ));
        let projected =
            project_parameter_tree_leaves_v1(&t, &keep_of(&["deep"])).expect("projected");
        assert_eq!(count_leaves(projected.root_node()), 1);
        let root = projected.root_node();
        match root {
            AmiParameterTreeNodeV1::Branch { children, .. } => {
                assert_eq!(children.len(), 1);
                let sub = children.get("sub").expect("sub kept");
                match sub {
                    AmiParameterTreeNodeV1::Branch { children, .. } => {
                        assert_eq!(children.len(), 1);
                        assert!(children.contains_key("deep"));
                    }
                    AmiParameterTreeNodeV1::Leaf { .. } => panic!("expected branch"),
                }
            }
            AmiParameterTreeNodeV1::Leaf { .. } => panic!("expected branch root"),
        }
    }

    #[test]
    fn projecting_all_leaves_yields_identical_tree() {
        let t = tree(branch(
            "root",
            vec![leaf("gain", &["0.5"]), leaf("steps", &["7"])],
        ));
        let projected =
            project_parameter_tree_leaves_v1(&t, &keep_of(&["gain", "steps"])).expect("projected");
        assert_eq!(projected, t);
    }

    #[test]
    fn empty_selection_fails_closed() {
        let t = tree(branch("root", vec![leaf("gain", &["0.5"])]));
        let error = project_parameter_tree_leaves_v1(&t, &keep_of(&[])).unwrap_err();
        assert_eq!(error, ParameterTreeProjectErrorV1::EmptySelection);
    }

    #[test]
    fn missing_leaf_fails_closed() {
        let t = tree(branch("root", vec![leaf("gain", &["0.5"])]));
        let error = project_parameter_tree_leaves_v1(&t, &keep_of(&["nope"])).unwrap_err();
        assert_eq!(
            error,
            ParameterTreeProjectErrorV1::MissingLeaf("nope".to_string())
        );
    }

    #[test]
    fn branch_name_is_not_a_leaf() {
        let t = tree(branch(
            "root",
            vec![
                branch("sub", vec![leaf("gain", &["1.0"])]),
                leaf("other", &["2"]),
            ],
        ));
        let error = project_parameter_tree_leaves_v1(&t, &keep_of(&["sub"])).unwrap_err();
        assert_eq!(
            error,
            ParameterTreeProjectErrorV1::MissingLeaf("sub".to_string())
        );
    }
}
