//! AMI parameter tree batch rename core (P4B-02b36).
//!
//! Renames leaves of an `AmiParameterTreeV1` in one pass from a caller-supplied
//! old-name -> new-name map, returning a new tree. Renaming is two-phase per
//! branch (remove all renamed leaves, then insert them under their new names),
//! so sibling swaps are supported. Fail-closed: an empty rename map, an old name
//! that is not a leaf in the tree, a new name that is not a valid tree node
//! identifier, or a rename that collides with a sibling in the same branch are
//! strictly rejected. New names follow the tree identifier rule (the typed-form
//! gate P4B-02b34 enforces the stricter parameter-name rule downstream).

use std::collections::{BTreeMap, BTreeSet};

use crate::{AmiParameterTreeNodeV1, AmiParameterTreeV1};

/// Scope policy for the parameter tree batch rename core.
pub const PARAMETER_TREE_BATCH_RENAME_POLICY_V1: &str =
    "sipi.p4b-02b36.parameter-tree-batch-rename-v1.leaf-map-rename";

/// Fail-closed errors during parameter tree batch rename.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterTreeBatchRenameErrorV1 {
    /// The rename map is empty.
    EmptyRenameMap,
    /// An old name in the rename map is not a leaf in the tree.
    MissingLeaf(String),
    /// A new name is not a valid tree node identifier.
    InvalidNewName(String),
    /// A rename would create two same-named children in the same branch.
    SiblingNameCollision(String),
}

fn is_valid_identifier(name: &str) -> bool {
    let trimmed = name.trim();
    !trimmed.is_empty()
        && trimmed.is_ascii()
        && trimmed
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-' || c == '.')
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

fn rename_node(
    node: &AmiParameterTreeNodeV1,
    renames: &BTreeMap<String, String>,
) -> Result<AmiParameterTreeNodeV1, ParameterTreeBatchRenameErrorV1> {
    match node {
        AmiParameterTreeNodeV1::Leaf { name, value_tokens } => {
            let new_name = renames.get(name).cloned().unwrap_or_else(|| name.clone());
            Ok(AmiParameterTreeNodeV1::Leaf {
                name: new_name,
                value_tokens: value_tokens.clone(),
            })
        }
        AmiParameterTreeNodeV1::Branch { name, children } => {
            // Phase 1: recurse into children; renamed leaves are re-keyed.
            let mut new_children = BTreeMap::new();
            let mut renamed_entries: Vec<(String, AmiParameterTreeNodeV1)> = Vec::new();
            for (key, child) in children {
                let renamed_child = rename_node(child, renames)?;
                match child {
                    AmiParameterTreeNodeV1::Leaf { name: old_name, .. } => {
                        if renames.contains_key(old_name) {
                            let new_key = renamed_child.name().to_string();
                            renamed_entries.push((new_key, renamed_child));
                        } else {
                            new_children.insert(key.clone(), renamed_child);
                        }
                    }
                    AmiParameterTreeNodeV1::Branch { .. } => {
                        new_children.insert(key.clone(), renamed_child);
                    }
                }
            }
            // Phase 2: insert renamed leaves; a collision with any child (renamed
            // or pre-existing) is a sibling collision.
            for (new_key, renamed_child) in renamed_entries {
                if new_children
                    .insert(new_key.clone(), renamed_child)
                    .is_some()
                {
                    return Err(ParameterTreeBatchRenameErrorV1::SiblingNameCollision(
                        new_key,
                    ));
                }
            }
            Ok(AmiParameterTreeNodeV1::Branch {
                name: name.clone(),
                children: new_children,
            })
        }
    }
}

/// Rename leaves of `tree` in one pass per `renames` (old name -> new name).
///
/// Returns a new tree with the renamed leaves under the same root name, or
/// fails closed with the first violating rename (canonical traversal order:
/// branch children in byte-wise name order, depth first). Sibling swaps are
/// supported via two-phase re-keying.
pub fn rename_parameter_tree_leaves_v1(
    tree: &AmiParameterTreeV1,
    renames: &BTreeMap<String, String>,
) -> Result<AmiParameterTreeV1, ParameterTreeBatchRenameErrorV1> {
    if renames.is_empty() {
        return Err(ParameterTreeBatchRenameErrorV1::EmptyRenameMap);
    }
    let mut leaf_names = BTreeSet::new();
    collect_leaf_names(tree.root_node(), &mut leaf_names);
    for old_name in renames.keys() {
        if !leaf_names.contains(old_name) {
            return Err(ParameterTreeBatchRenameErrorV1::MissingLeaf(
                old_name.clone(),
            ));
        }
        let new_name = renames.get(old_name).expect("key present");
        if !is_valid_identifier(new_name) {
            return Err(ParameterTreeBatchRenameErrorV1::InvalidNewName(
                new_name.clone(),
            ));
        }
    }
    let new_root = rename_node(tree.root_node(), renames)?;
    Ok(AmiParameterTreeV1::new(tree.root_name(), new_root))
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

    fn renames_of(pairs: &[(&str, &str)]) -> BTreeMap<String, String> {
        pairs
            .iter()
            .map(|(a, b)| (a.to_string(), b.to_string()))
            .collect()
    }

    fn find_leaf<'a>(
        node: &'a AmiParameterTreeNodeV1,
        name: &str,
    ) -> Option<&'a AmiParameterTreeNodeV1> {
        match node {
            AmiParameterTreeNodeV1::Leaf { name: n, .. } if n == name => Some(node),
            AmiParameterTreeNodeV1::Leaf { .. } => None,
            AmiParameterTreeNodeV1::Branch { children, .. } => {
                children.values().find_map(|c| find_leaf(c, name))
            }
        }
    }

    #[test]
    fn batch_renames_requested_leaves() {
        let t = tree(branch(
            "root",
            vec![
                leaf("gain", &["Float", "0.5"]),
                leaf("steps", &["Integer", "7"]),
            ],
        ));
        let renamed = rename_parameter_tree_leaves_v1(
            &t,
            &renames_of(&[("gain", "amplitude"), ("steps", "count")]),
        )
        .expect("renamed");
        assert_eq!(renamed.root_name(), "root");
        assert!(find_leaf(renamed.root_node(), "amplitude").is_some());
        assert!(find_leaf(renamed.root_node(), "count").is_some());
        assert!(find_leaf(renamed.root_node(), "gain").is_none());
        match find_leaf(renamed.root_node(), "amplitude").expect("amplitude") {
            AmiParameterTreeNodeV1::Leaf { value_tokens, .. } => {
                assert_eq!(value_tokens, &vec!["Float".to_string(), "0.5".to_string()]);
            }
            AmiParameterTreeNodeV1::Branch { .. } => panic!("expected leaf"),
        }
    }

    #[test]
    fn unrequested_leaves_are_unchanged() {
        let t = tree(branch(
            "root",
            vec![leaf("gain", &["0.5"]), leaf("steps", &["7"])],
        ));
        let renamed = rename_parameter_tree_leaves_v1(&t, &renames_of(&[("gain", "amplitude")]))
            .expect("renamed");
        assert!(find_leaf(renamed.root_node(), "steps").is_some());
    }

    #[test]
    fn empty_rename_map_fails_closed() {
        let t = tree(branch("root", vec![leaf("gain", &["0.5"])]));
        let error = rename_parameter_tree_leaves_v1(&t, &renames_of(&[])).unwrap_err();
        assert_eq!(error, ParameterTreeBatchRenameErrorV1::EmptyRenameMap);
    }

    #[test]
    fn missing_old_name_fails_closed() {
        let t = tree(branch("root", vec![leaf("gain", &["0.5"])]));
        let error = rename_parameter_tree_leaves_v1(&t, &renames_of(&[("nope", "x")])).unwrap_err();
        assert_eq!(
            error,
            ParameterTreeBatchRenameErrorV1::MissingLeaf("nope".to_string())
        );
    }

    #[test]
    fn invalid_new_name_fails_closed() {
        let t = tree(branch("root", vec![leaf("gain", &["0.5"])]));
        let error =
            rename_parameter_tree_leaves_v1(&t, &renames_of(&[("gain", "my gain")])).unwrap_err();
        assert_eq!(
            error,
            ParameterTreeBatchRenameErrorV1::InvalidNewName("my gain".to_string())
        );
    }

    #[test]
    fn sibling_collision_fails_closed() {
        let t = tree(branch(
            "root",
            vec![leaf("gain", &["0.5"]), leaf("steps", &["7"])],
        ));
        let error =
            rename_parameter_tree_leaves_v1(&t, &renames_of(&[("gain", "steps")])).unwrap_err();
        assert_eq!(
            error,
            ParameterTreeBatchRenameErrorV1::SiblingNameCollision("steps".to_string())
        );
    }

    #[test]
    fn sibling_swap_is_supported() {
        let t = tree(branch("root", vec![leaf("a", &["0.5"]), leaf("b", &["7"])]));
        let renamed = rename_parameter_tree_leaves_v1(&t, &renames_of(&[("a", "b"), ("b", "a")]))
            .expect("swap");
        assert!(find_leaf(renamed.root_node(), "a").is_some());
        assert!(find_leaf(renamed.root_node(), "b").is_some());
        match find_leaf(renamed.root_node(), "a").expect("a") {
            AmiParameterTreeNodeV1::Leaf { value_tokens, .. } => {
                assert_eq!(value_tokens, &vec!["7".to_string()]);
            }
            AmiParameterTreeNodeV1::Branch { .. } => panic!("expected leaf"),
        }
    }

    #[test]
    fn same_name_at_other_depth_is_not_a_collision() {
        let t = tree(branch(
            "root",
            vec![
                branch("sub", vec![leaf("gain", &["1.0"])]),
                leaf("top", &["True"]),
            ],
        ));
        let renamed =
            rename_parameter_tree_leaves_v1(&t, &renames_of(&[("gain", "top")])).expect("renamed");
        // two "top" leaves at different depths are legal in the tree
        assert!(find_leaf(renamed.root_node(), "top").is_some());
        match renamed.root_node() {
            AmiParameterTreeNodeV1::Branch { children, .. } => {
                let sub = children.get("sub").expect("sub");
                match sub {
                    AmiParameterTreeNodeV1::Branch { children, .. } => {
                        assert!(children.contains_key("top"));
                    }
                    AmiParameterTreeNodeV1::Leaf { .. } => panic!("expected branch"),
                }
            }
            AmiParameterTreeNodeV1::Leaf { .. } => panic!("expected branch"),
        }
    }

    #[test]
    fn nested_leaf_rename_keeps_ancestor_branches() {
        let t = tree(branch(
            "root",
            vec![branch("sub", vec![leaf("deep", &["1.0"])])],
        ));
        let renamed = rename_parameter_tree_leaves_v1(&t, &renames_of(&[("deep", "shallow")]))
            .expect("renamed");
        assert!(find_leaf(renamed.root_node(), "shallow").is_some());
        assert!(find_leaf(renamed.root_node(), "deep").is_none());
    }
}
