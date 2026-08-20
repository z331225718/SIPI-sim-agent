//! AMI parameter tree node rename core (P4B-02b24).
//!
//! Renames the node rooted at a dot-separated canonical path inside a typed
//! `AmiParameterTreeV1` hierarchy (`rename_parameter_tree_node_v1`), returning a new tree
//! with the renamed node. Fail-closed: empty paths, root renames, invalid new names,
//! root-name mismatches, or missing path segments are strictly rejected.

use crate::parameter_tree_subtree_v1::{
    ParameterTreeSubtreeErrorV1, extract_parameter_tree_subtree_v1,
};
use crate::parameter_trees_v1::{AmiParameterTreeNodeV1, AmiParameterTreeV1};

/// Scope policy for the parameter tree rename core.
pub const PARAMETER_TREE_RENAME_POLICY_V1: &str =
    "sipi.p4b-02b24.parameter-tree-rename-v1.tree-node-rename";

/// Fail-closed errors during AMI parameter tree node rename.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterTreeRenameErrorV1 {
    EmptyPath,
    EmptyNewName,
    InvalidNewName,
    RootRenameForbidden,
    RootMismatch { expected: String, actual: String },
    MissingPath(String),
    SubtreeError(String),
}

fn is_valid_identifier(name: &str) -> bool {
    let trimmed = name.trim();
    !trimmed.is_empty()
        && trimmed.is_ascii()
        && trimmed
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-' || c == '.')
}

fn rename_node(
    node: &AmiParameterTreeNodeV1,
    segments: &[&str],
    new_name: &str,
) -> Result<AmiParameterTreeNodeV1, ParameterTreeRenameErrorV1> {
    if segments.is_empty() {
        // target node reached: rename it
        return Ok(match node {
            AmiParameterTreeNodeV1::Branch { children, .. } => AmiParameterTreeNodeV1::Branch {
                name: new_name.to_string(),
                children: children.clone(),
            },
            AmiParameterTreeNodeV1::Leaf { value_tokens, .. } => AmiParameterTreeNodeV1::Leaf {
                name: new_name.to_string(),
                value_tokens: value_tokens.clone(),
            },
        });
    }

    let (head, rest) = (&segments[0], &segments[1..]);
    match node {
        AmiParameterTreeNodeV1::Branch { name, children } => {
            let mut new_children = children.clone();
            let child = new_children
                .get(*head)
                .ok_or_else(|| ParameterTreeRenameErrorV1::MissingPath(segments.join(".")))?;
            if rest.is_empty() {
                // target child is the node to rename: insert under the new name key
                let renamed = rename_node(child, &[], new_name)?;
                new_children.remove(*head);
                new_children.insert(new_name.to_string(), renamed);
            } else {
                let renamed = rename_node(child, rest, new_name)?;
                new_children.insert((*head).to_string(), renamed);
            }
            Ok(AmiParameterTreeNodeV1::Branch {
                name: name.clone(),
                children: new_children,
            })
        }
        AmiParameterTreeNodeV1::Leaf { .. } => {
            Err(ParameterTreeRenameErrorV1::MissingPath(segments.join(".")))
        }
    }
}

/// Rename the node at the given dot-separated canonical path inside a parameter tree.
///
/// The path starts with the tree root name (e.g. `root.a.b`). Renaming the root node
/// itself is forbidden (`RootRenameForbidden`). Returns a new tree with the renamed node.
/// Fails closed on empty paths, invalid new names, root-name mismatches, or missing path segments.
pub fn rename_parameter_tree_node_v1(
    tree: &AmiParameterTreeV1,
    path: &str,
    new_name: &str,
) -> Result<AmiParameterTreeV1, ParameterTreeRenameErrorV1> {
    let trimmed_path = path.trim();
    if trimmed_path.is_empty() {
        return Err(ParameterTreeRenameErrorV1::EmptyPath);
    }
    let segments: Vec<&str> = trimmed_path.split('.').filter(|s| !s.is_empty()).collect();
    if segments.is_empty() {
        return Err(ParameterTreeRenameErrorV1::EmptyPath);
    }
    if segments.len() == 1 {
        return Err(ParameterTreeRenameErrorV1::RootRenameForbidden);
    }
    if segments[0] != tree.root_name() {
        return Err(ParameterTreeRenameErrorV1::RootMismatch {
            expected: tree.root_name().to_string(),
            actual: segments[0].to_string(),
        });
    }
    let trimmed_new = new_name.trim();
    if trimmed_new.is_empty() {
        return Err(ParameterTreeRenameErrorV1::EmptyNewName);
    }
    if !is_valid_identifier(trimmed_new) {
        return Err(ParameterTreeRenameErrorV1::InvalidNewName);
    }

    // Validate the target path exists first (fail closed with consistent error semantics).
    if let Err(e) = extract_parameter_tree_subtree_v1(tree, trimmed_path) {
        return Err(match e {
            ParameterTreeSubtreeErrorV1::EmptyPath => ParameterTreeRenameErrorV1::EmptyPath,
            ParameterTreeSubtreeErrorV1::RootMismatch { expected, actual } => {
                ParameterTreeRenameErrorV1::RootMismatch { expected, actual }
            }
            ParameterTreeSubtreeErrorV1::MissingPath(p) => {
                ParameterTreeRenameErrorV1::MissingPath(p)
            }
        });
    }

    let root = rename_node(tree.root_node(), &segments[1..], trimmed_new)?;
    Ok(AmiParameterTreeV1::new(tree.root_name(), root))
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
            PARAMETER_TREE_RENAME_POLICY_V1,
            "sipi.p4b-02b24.parameter-tree-rename-v1.tree-node-rename"
        );
    }

    #[test]
    fn renames_leaf_node() {
        let tree = tree_of("(root (a 1) (b 2))");
        let renamed = rename_parameter_tree_node_v1(&tree, "root.a", "a_renamed").expect("rename");
        let out = extract_parameter_tree_subtree_v1(&renamed, "root.a_renamed").expect("extract");
        assert_eq!(out.name(), "a_renamed");
    }

    #[test]
    fn renames_branch_node() {
        let tree = tree_of("(root (branch_a (leaf_1 10)) (branch_b 20))");
        let renamed =
            rename_parameter_tree_node_v1(&tree, "root.branch_a", "branch_x").expect("rename");
        let out = extract_parameter_tree_subtree_v1(&renamed, "root.branch_x").expect("extract");
        assert_eq!(out.name(), "branch_x");
    }

    #[test]
    fn rejects_root_rename() {
        let tree = tree_of("(root (a 1))");
        assert_eq!(
            rename_parameter_tree_node_v1(&tree, "root", "other"),
            Err(ParameterTreeRenameErrorV1::RootRenameForbidden)
        );
    }

    #[test]
    fn rejects_invalid_new_name() {
        let tree = tree_of("(root (a 1))");
        assert_eq!(
            rename_parameter_tree_node_v1(&tree, "root.a", "bad name!"),
            Err(ParameterTreeRenameErrorV1::InvalidNewName)
        );
    }

    #[test]
    fn rejects_missing_path() {
        let tree = tree_of("(root (a 1))");
        assert_eq!(
            rename_parameter_tree_node_v1(&tree, "root.a.nope", "x"),
            Err(ParameterTreeRenameErrorV1::MissingPath(
                "root.a.nope".to_string()
            ))
        );
    }
}
