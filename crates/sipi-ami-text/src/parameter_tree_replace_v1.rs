//! AMI parameter tree node replace core (P4B-02b27).
//!
//! Replaces the node rooted at a dot-separated canonical path inside a typed
//! `AmiParameterTreeV1` hierarchy with a replacement subtree node
//! (`replace_parameter_tree_node_v1`), returning a new tree. Fail-closed:
//! empty paths, root replacement, invalid replacement names, root-name mismatches,
//! missing path segments, or replacement-name collisions with a sibling
//! are strictly rejected.

use crate::parameter_trees_v1::{AmiParameterTreeNodeV1, AmiParameterTreeV1};
use crate::parameter_tree_subtree_v1::{extract_parameter_tree_subtree_v1, ParameterTreeSubtreeErrorV1};

/// Scope policy for the parameter tree replace core.
pub const PARAMETER_TREE_REPLACE_POLICY_V1: &str =
    "sipi.p4b-02b27.parameter-tree-replace-v1.tree-node-replace";

/// Fail-closed errors during AMI parameter tree node replace.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterTreeReplaceErrorV1 {
    EmptyPath,
    EmptyNodeName,
    InvalidNodeName,
    RootReplaceForbidden,
    RootMismatch { expected: String, actual: String },
    MissingPath(String),
    SiblingNameCollision(String),
    SubtreeError(String),
}

fn is_valid_identifier(name: &str) -> bool {
    let trimmed = name.trim();
    !trimmed.is_empty()
        && trimmed.is_ascii()
        && trimmed.chars().all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-' || c == '.')
}

fn replace_node(
    node: &AmiParameterTreeNodeV1,
    segments: &[&str],
    replacement: &AmiParameterTreeNodeV1,
    full_path: &str,
) -> Result<AmiParameterTreeNodeV1, ParameterTreeReplaceErrorV1> {
    match node {
        AmiParameterTreeNodeV1::Branch { name, children } => {
            let mut new_children = children.clone();
            if segments.is_empty() {
                return Ok(replacement.clone());
            }
            let (head, rest) = (&segments[0], &segments[1..]);
            let child = new_children.get_mut(*head).ok_or_else(|| {
                ParameterTreeReplaceErrorV1::MissingPath(full_path.to_string())
            })?;
            if rest.is_empty() {
                let replacement_name = replacement.name();
                // Replacing the last child: the replacement name must not collide with a sibling.
                if new_children.contains_key(replacement_name) && replacement_name != *head {
                    return Err(ParameterTreeReplaceErrorV1::SiblingNameCollision(
                        replacement_name.to_string(),
                    ));
                }
                new_children.remove(*head);
                new_children.insert(replacement_name.to_string(), replacement.clone());
                return Ok(AmiParameterTreeNodeV1::Branch {
                    name: name.clone(),
                    children: new_children,
                });
            }
            let replaced = replace_node(child, rest, replacement, full_path)?;
            new_children.insert((*head).to_string(), replaced);
            Ok(AmiParameterTreeNodeV1::Branch {
                name: name.clone(),
                children: new_children,
            })
        }
        AmiParameterTreeNodeV1::Leaf { .. } => {
            Err(ParameterTreeReplaceErrorV1::MissingPath(full_path.to_string()))
        }
    }
}

/// Replace the node at the given dot-separated canonical path inside a parameter tree.
///
/// The path starts with the tree root name (e.g. `root.a.b`). Replacing the root node
/// itself is forbidden (`RootReplaceForbidden`). Returns a new tree with the node replaced.
/// Fails closed on empty paths, invalid replacement names, root-name mismatches,
/// missing path segments, or replacement-name collisions with a sibling.
pub fn replace_parameter_tree_node_v1(
    tree: &AmiParameterTreeV1,
    path: &str,
    replacement: &AmiParameterTreeNodeV1,
) -> Result<AmiParameterTreeV1, ParameterTreeReplaceErrorV1> {
    let trimmed_path = path.trim();
    if trimmed_path.is_empty() {
        return Err(ParameterTreeReplaceErrorV1::EmptyPath);
    }
    let segments: Vec<&str> = trimmed_path.split('.').filter(|s| !s.is_empty()).collect();
    if segments.is_empty() {
        return Err(ParameterTreeReplaceErrorV1::EmptyPath);
    }
    if segments.len() == 1 {
        return Err(ParameterTreeReplaceErrorV1::RootReplaceForbidden);
    }
    if segments[0] != tree.root_name() {
        return Err(ParameterTreeReplaceErrorV1::RootMismatch {
            expected: tree.root_name().to_string(),
            actual: segments[0].to_string(),
        });
    }
    let node_name = replacement.name();
    if node_name.trim().is_empty() {
        return Err(ParameterTreeReplaceErrorV1::EmptyNodeName);
    }
    if !is_valid_identifier(node_name) {
        return Err(ParameterTreeReplaceErrorV1::InvalidNodeName);
    }

    // Validate the target path exists first (fail closed with consistent error semantics).
    if let Err(e) = extract_parameter_tree_subtree_v1(tree, trimmed_path) {
        return Err(match e {
            ParameterTreeSubtreeErrorV1::EmptyPath => ParameterTreeReplaceErrorV1::EmptyPath,
            ParameterTreeSubtreeErrorV1::RootMismatch { expected, actual } => {
                ParameterTreeReplaceErrorV1::RootMismatch { expected, actual }
            }
            ParameterTreeSubtreeErrorV1::MissingPath(p) => ParameterTreeReplaceErrorV1::MissingPath(p),
        });
    }

    let canonical = segments.join(".");
    let root = replace_node(tree.root_node(), &segments[1..], replacement, &canonical)?;
    Ok(AmiParameterTreeV1::new(tree.root_name(), root))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::parameter_trees_v1::build_parameter_trees_v1;
    use crate::parse_ami_text_v1;
    use crate::ParseLimitsV1;

    fn limits() -> ParseLimitsV1 {
        ParseLimitsV1::try_new(1024, 16, 64, 128).unwrap()
    }

    fn tree_of(text: &str) -> AmiParameterTreeV1 {
        let doc = parse_ami_text_v1(text.as_bytes(), limits()).expect("parse");
        build_parameter_trees_v1(&doc).expect("build").remove(0)
    }

    fn node_of(text: &str) -> AmiParameterTreeNodeV1 {
        let doc = parse_ami_text_v1(text.as_bytes(), limits()).expect("parse");
        build_parameter_trees_v1(&doc).expect("build").remove(0).root_node().clone()
    }

    #[test]
    fn policy_fixed() {
        assert_eq!(
            PARAMETER_TREE_REPLACE_POLICY_V1,
            "sipi.p4b-02b27.parameter-tree-replace-v1.tree-node-replace"
        );
    }

    #[test]
    fn replaces_leaf_node() {
        let tree = tree_of("(root (a 1) (b 2))");
        let repl = node_of("(a_new 9)");
        let replaced = replace_parameter_tree_node_v1(&tree, "root.a", &repl).expect("replace");
        let out = extract_parameter_tree_subtree_v1(&replaced, "root.a_new").expect("extract");
        assert_eq!(out.name(), "a_new");
    }

    #[test]
    fn replaces_branch_node() {
        let tree = tree_of("(root (branch_a (leaf_1 10)) (branch_b 20))");
        let repl = node_of("(branch_x (leaf_9 90))");
        let replaced = replace_parameter_tree_node_v1(&tree, "root.branch_a", &repl).expect("replace");
        let out = extract_parameter_tree_subtree_v1(&replaced, "root.branch_x.leaf_9").expect("extract");
        assert_eq!(out.name(), "leaf_9");
    }

    #[test]
    fn rejects_root_replace() {
        let tree = tree_of("(root (a 1))");
        let repl = node_of("(other 9)");
        let result = replace_parameter_tree_node_v1(&tree, "root", &repl);
        assert!(matches!(result, Err(ParameterTreeReplaceErrorV1::RootReplaceForbidden)));
    }

    #[test]
    fn rejects_sibling_name_collision() {
        let tree = tree_of("(root (a 1) (b 2))");
        let repl = node_of("(b 9)");
        assert_eq!(
            replace_parameter_tree_node_v1(&tree, "root.a", &repl),
            Err(ParameterTreeReplaceErrorV1::SiblingNameCollision("b".to_string()))
        );
    }

    #[test]
    fn rejects_missing_path() {
        let tree = tree_of("(root (a 1))");
        let repl = node_of("(x 9)");
        assert_eq!(
            replace_parameter_tree_node_v1(&tree, "root.a.nope", &repl),
            Err(ParameterTreeReplaceErrorV1::MissingPath("root.a.nope".to_string()))
        );
    }
}
