//! AMI parameter tree subtree compose core (P4B-02b26).
//!
//! Composes a subtree node into a typed `AmiParameterTreeV1` hierarchy at a dot-separated
//! canonical parent path (`compose_parameter_tree_subtree_v1`), returning a new tree with the
//! subtree attached. Fail-closed: empty paths, invalid node names, root-name mismatches,
//! missing parent path segments, or duplicate child names at the attachment point
//! are strictly rejected.

use crate::parameter_trees_v1::{AmiParameterTreeNodeV1, AmiParameterTreeV1};
use crate::parameter_tree_subtree_v1::{extract_parameter_tree_subtree_v1, ParameterTreeSubtreeErrorV1};

/// Scope policy for the parameter tree compose core.
pub const PARAMETER_TREE_COMPOSE_POLICY_V1: &str =
    "sipi.p4b-02b26.parameter-tree-compose-v1.tree-subtree-compose";

/// Fail-closed errors during AMI parameter tree subtree compose.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterTreeComposeErrorV1 {
    EmptyPath,
    EmptyNodeName,
    InvalidNodeName,
    RootMismatch { expected: String, actual: String },
    MissingPath(String),
    DuplicateChild(String),
    SubtreeError(String),
}

fn is_valid_identifier(name: &str) -> bool {
    let trimmed = name.trim();
    !trimmed.is_empty()
        && trimmed.is_ascii()
        && trimmed.chars().all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-' || c == '.')
}

fn compose_node(
    node: &AmiParameterTreeNodeV1,
    segments: &[&str],
    subtree: &AmiParameterTreeNodeV1,
    full_path: &str,
) -> Result<AmiParameterTreeNodeV1, ParameterTreeComposeErrorV1> {
    match node {
        AmiParameterTreeNodeV1::Branch { name, children } => {
            let mut new_children = children.clone();
            if segments.is_empty() {
                let child_name = subtree.name();
                if new_children.contains_key(child_name) {
                    return Err(ParameterTreeComposeErrorV1::DuplicateChild(child_name.to_string()));
                }
                new_children.insert(child_name.to_string(), subtree.clone());
            } else {
                let (head, rest) = (&segments[0], &segments[1..]);
                let child = new_children.get_mut(*head).ok_or_else(|| {
                    ParameterTreeComposeErrorV1::MissingPath(full_path.to_string())
                })?;
                let composed = compose_node(child, rest, subtree, full_path)?;
                new_children.insert((*head).to_string(), composed);
            }
            Ok(AmiParameterTreeNodeV1::Branch {
                name: name.clone(),
                children: new_children,
            })
        }
        AmiParameterTreeNodeV1::Leaf { .. } => {
            Err(ParameterTreeComposeErrorV1::MissingPath(full_path.to_string()))
        }
    }
}

/// Compose a subtree node into a parameter tree at the given dot-separated parent path.
///
/// The path starts with the tree root name (e.g. `root.a.b`) and names the PARENT branch
/// under which the subtree is attached. Composing at the root itself is forbidden
/// (`RootComposeForbidden`). Returns a new tree with the subtree attached.
/// Fails closed on empty paths, invalid node names, root-name mismatches,
/// missing parent path segments, or duplicate child names at the attachment point.
pub fn compose_parameter_tree_subtree_v1(
    tree: &AmiParameterTreeV1,
    path: &str,
    subtree: &AmiParameterTreeNodeV1,
) -> Result<AmiParameterTreeV1, ParameterTreeComposeErrorV1> {
    let trimmed_path = path.trim();
    if trimmed_path.is_empty() {
        return Err(ParameterTreeComposeErrorV1::EmptyPath);
    }
    let segments: Vec<&str> = trimmed_path.split('.').filter(|s| !s.is_empty()).collect();
    if segments.is_empty() {
        return Err(ParameterTreeComposeErrorV1::EmptyPath);
    }
    if segments[0] != tree.root_name() {
        return Err(ParameterTreeComposeErrorV1::RootMismatch {
            expected: tree.root_name().to_string(),
            actual: segments[0].to_string(),
        });
    }
    let node_name = subtree.name();
    if node_name.trim().is_empty() {
        return Err(ParameterTreeComposeErrorV1::EmptyNodeName);
    }
    if !is_valid_identifier(node_name) {
        return Err(ParameterTreeComposeErrorV1::InvalidNodeName);
    }

    // Validate the parent path exists first (fail closed with consistent error semantics).
    if let Err(e) = extract_parameter_tree_subtree_v1(tree, trimmed_path) {
        return Err(match e {
            ParameterTreeSubtreeErrorV1::EmptyPath => ParameterTreeComposeErrorV1::EmptyPath,
            ParameterTreeSubtreeErrorV1::RootMismatch { expected, actual } => {
                ParameterTreeComposeErrorV1::RootMismatch { expected, actual }
            }
            ParameterTreeSubtreeErrorV1::MissingPath(p) => ParameterTreeComposeErrorV1::MissingPath(p),
        });
    }

    let canonical = segments.join(".");
    let root = compose_node(tree.root_node(), &segments[1..], subtree, &canonical)?;
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
            PARAMETER_TREE_COMPOSE_POLICY_V1,
            "sipi.p4b-02b26.parameter-tree-compose-v1.tree-subtree-compose"
        );
    }

    #[test]
    fn composes_leaf_subtree_under_branch() {
        let tree = tree_of("(root (a 1))");
        let sub = node_of("(c 3)");
        let composed = compose_parameter_tree_subtree_v1(&tree, "root", &sub).expect("compose");
        let out = extract_parameter_tree_subtree_v1(&composed, "root.c").expect("extract");
        assert_eq!(out.name(), "c");
    }

    #[test]
    fn composes_subtree_under_nested_branch() {
        let tree = tree_of("(root (branch_a (leaf_1 10)))");
        let sub = node_of("(leaf_2 20)");
        let composed = compose_parameter_tree_subtree_v1(&tree, "root.branch_a", &sub).expect("compose");
        let out = extract_parameter_tree_subtree_v1(&composed, "root.branch_a.leaf_2").expect("extract");
        assert_eq!(out.name(), "leaf_2");
    }

    #[test]
    fn rejects_leaf_parent_path() {
        let tree = tree_of("(root (a 1))");
        let sub = node_of("(c 3)");
        assert_eq!(
            compose_parameter_tree_subtree_v1(&tree, "root.a", &sub),
            Err(ParameterTreeComposeErrorV1::MissingPath("root.a".to_string()))
        );
    }

    #[test]
    fn rejects_duplicate_child() {
        let tree = tree_of("(root (branch_a (leaf_1 10)))");
        let sub = node_of("(leaf_1 99)");
        assert_eq!(
            compose_parameter_tree_subtree_v1(&tree, "root.branch_a", &sub),
            Err(ParameterTreeComposeErrorV1::DuplicateChild("leaf_1".to_string()))
        );
    }

    #[test]
    fn rejects_missing_parent_path() {
        let tree = tree_of("(root (a 1))");
        let sub = node_of("(c 3)");
        assert_eq!(
            compose_parameter_tree_subtree_v1(&tree, "root.nope", &sub),
            Err(ParameterTreeComposeErrorV1::MissingPath("root.nope".to_string()))
        );
    }
}
