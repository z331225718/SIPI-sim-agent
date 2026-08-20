//! AMI parameter tree subtree extraction core (P4B-02b23).
//!
//! Extracts the subtree rooted at a dot-separated canonical path inside a typed
//! `AmiParameterTreeV1` hierarchy (`extract_parameter_tree_subtree_v1`), returning an owned
//! clone of the subtree node. Fail-closed: empty paths or missing path segments
//! are strictly rejected.

use crate::parameter_trees_v1::{AmiParameterTreeNodeV1, AmiParameterTreeV1};

/// Scope policy for the parameter tree subtree core.
pub const PARAMETER_TREE_SUBTREE_POLICY_V1: &str =
    "sipi.p4b-02b23.parameter-tree-subtree-v1.tree-subtree-extraction";

/// Fail-closed errors during AMI parameter tree subtree extraction.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterTreeSubtreeErrorV1 {
    EmptyPath,
    RootMismatch { expected: String, actual: String },
    MissingPath(String),
}

fn extract_node<'a>(
    node: &'a AmiParameterTreeNodeV1,
    segments: &[&str],
    prefix: &str,
    full_path: &str,
) -> Result<&'a AmiParameterTreeNodeV1, ParameterTreeSubtreeErrorV1> {
    let current = if prefix.is_empty() {
        node.name().to_string()
    } else {
        format!("{prefix}.{}", node.name())
    };

    if segments.is_empty() {
        return Ok(node);
    }

    let (head, rest) = (&segments[0], &segments[1..]);
    if *head != node.name() {
        return Err(ParameterTreeSubtreeErrorV1::MissingPath(full_path.to_string()));
    }
    if rest.is_empty() {
        return Ok(node);
    }
    match node {
        AmiParameterTreeNodeV1::Branch { children, .. } => {
            let next = children.get(rest[0]).ok_or_else(|| {
                ParameterTreeSubtreeErrorV1::MissingPath(full_path.to_string())
            })?;
            extract_node(next, rest, &current, full_path)
        }
        AmiParameterTreeNodeV1::Leaf { .. } => {
            Err(ParameterTreeSubtreeErrorV1::MissingPath(full_path.to_string()))
        }
    }
}

/// Extract the subtree rooted at the given dot-separated path inside a parameter tree.
///
/// The path starts with the tree root name (e.g. `root.a.b`). Returns an owned clone
/// of the subtree node. Fails closed on empty paths, root-name mismatches, or missing
/// path segments.
pub fn extract_parameter_tree_subtree_v1(
    tree: &AmiParameterTreeV1,
    path: &str,
) -> Result<AmiParameterTreeNodeV1, ParameterTreeSubtreeErrorV1> {
    let trimmed = path.trim();
    if trimmed.is_empty() {
        return Err(ParameterTreeSubtreeErrorV1::EmptyPath);
    }
    let segments: Vec<&str> = trimmed.split('.').filter(|s| !s.is_empty()).collect();
    if segments.is_empty() {
        return Err(ParameterTreeSubtreeErrorV1::EmptyPath);
    }
    if segments[0] != tree.root_name() {
        return Err(ParameterTreeSubtreeErrorV1::RootMismatch {
            expected: tree.root_name().to_string(),
            actual: segments[0].to_string(),
        });
    }
    let canonical = segments.join(".");
    let node = extract_node(tree.root_node(), &segments, "", &canonical)?;
    Ok(node.clone())
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

    #[test]
    fn policy_fixed() {
        assert_eq!(
            PARAMETER_TREE_SUBTREE_POLICY_V1,
            "sipi.p4b-02b23.parameter-tree-subtree-v1.tree-subtree-extraction"
        );
    }

    #[test]
    fn extracts_root_subtree() {
        let tree = tree_of("(root (a 1) (b 2))");
        let sub = extract_parameter_tree_subtree_v1(&tree, "root").expect("extract");
        assert_eq!(sub.name(), "root");
    }

    #[test]
    fn extracts_nested_subtree() {
        let tree = tree_of("(root (branch_a (leaf_1 10)) (branch_b 20))");
        let sub = extract_parameter_tree_subtree_v1(&tree, "root.branch_a").expect("extract");
        assert_eq!(sub.name(), "branch_a");
    }

    #[test]
    fn rejects_empty_path() {
        let tree = tree_of("(root (a 1))");
        assert_eq!(
            extract_parameter_tree_subtree_v1(&tree, "  "),
            Err(ParameterTreeSubtreeErrorV1::EmptyPath)
        );
    }

    #[test]
    fn rejects_root_mismatch() {
        let tree = tree_of("(root (a 1))");
        assert_eq!(
            extract_parameter_tree_subtree_v1(&tree, "other"),
            Err(ParameterTreeSubtreeErrorV1::RootMismatch {
                expected: "root".to_string(),
                actual: "other".to_string(),
            })
        );
    }

    #[test]
    fn rejects_missing_path_segment() {
        let tree = tree_of("(root (a 1))");
        assert_eq!(
            extract_parameter_tree_subtree_v1(&tree, "root.a.nope"),
            Err(ParameterTreeSubtreeErrorV1::MissingPath("root.a.nope".to_string()))
        );
    }
}
