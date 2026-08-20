//! AMI parameter tree leaf type resolution core (P4B-02b88).
//!
//! Resolves the declared type of a single leaf by canonical dot-separated path
//! (`root.gain`) inside an `AmiParameterTreeV1`:
//! `resolve_parameter_tree_leaf_type_v1` returns the leaf's declared type
//! token (Float/Integer/Boolean/String/List) when the leaf is a well-formed
//! typed form (exactly two value tokens whose first token is a known type
//! token). This is the single-path query companion of 02b87 leaf type map
//! extraction and the type-level companion of 02b30 leaf index resolution
//! (which returns value tokens, not types).
//!
//! Fail-closed: an empty path yields `EmptyPath`; a path that matches no node
//! yields `MissingPath`; a path that lands on a branch (i.e. is a strict
//! prefix of a leaf path) yields `PathNotLeaf`; a leaf that is not a typed
//! form yields `LeafNotTypedForm`. Paths are trimmed and empty segments
//! filtered, mirroring 02b30.

use crate::{AmiParameterTreeNodeV1, AmiParameterTreeV1, AmiParameterTypeV1};

/// Explicit scope policy of this slice: leaf type resolution by path.
pub const PARAMETER_TREE_LEAF_TYPE_RESOLUTION_POLICY_V1: &str =
    "sipi.p4b-02b88.parameter-tree-leaf-type-resolution-v1.leaf-type-resolution";

/// Fail-closed error while resolving a leaf's declared type by path.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterTreeLeafTypeResolutionErrorV1 {
    /// The path is empty after trimming.
    EmptyPath,
    /// The path matches no node.
    MissingPath(String),
    /// The path exists but lands on a branch, not a leaf.
    PathNotLeaf(String),
    /// The leaf exists but is not a typed form.
    LeafNotTypedForm(String),
}

/// Resolve the declared type of the leaf at `path` (canonical dot-separated).
pub fn resolve_parameter_tree_leaf_type_v1(
    tree: &AmiParameterTreeV1,
    path: &str,
) -> Result<AmiParameterTypeV1, ParameterTreeLeafTypeResolutionErrorV1> {
    let trimmed = path.trim();
    let segments: Vec<&str> = trimmed.split('.').filter(|s| !s.is_empty()).collect();
    if segments.is_empty() {
        return Err(ParameterTreeLeafTypeResolutionErrorV1::EmptyPath);
    }
    let canonical = segments.join(".");
    let mut current = tree.root_node();
    for (index, segment) in segments.iter().enumerate() {
        match current {
            AmiParameterTreeNodeV1::Branch { children, .. } => {
                if index == 0 {
                    // First segment is the root name itself; root is current.
                    if *segment != tree.root_name() {
                        return Err(ParameterTreeLeafTypeResolutionErrorV1::MissingPath(
                            canonical,
                        ));
                    }
                    continue;
                }
                match children.get(*segment) {
                    Some(child) => current = child,
                    None => {
                        return Err(ParameterTreeLeafTypeResolutionErrorV1::MissingPath(
                            canonical,
                        ));
                    }
                }
            }
            AmiParameterTreeNodeV1::Leaf { .. } => {
                return Err(ParameterTreeLeafTypeResolutionErrorV1::PathNotLeaf(
                    canonical,
                ));
            }
        }
    }
    match current {
        AmiParameterTreeNodeV1::Branch { .. } => Err(
            ParameterTreeLeafTypeResolutionErrorV1::PathNotLeaf(canonical),
        ),
        AmiParameterTreeNodeV1::Leaf { value_tokens, .. } => {
            if value_tokens.len() == 2
                && let Some(parameter_type) = AmiParameterTypeV1::from_token(&value_tokens[0])
            {
                return Ok(parameter_type);
            }
            Err(ParameterTreeLeafTypeResolutionErrorV1::LeafNotTypedForm(
                canonical,
            ))
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{ParseLimitsV1, build_parameter_trees_v1, parse_ami_text_v1};

    fn tree(text: &str) -> AmiParameterTreeV1 {
        let limits = ParseLimitsV1::try_new(8 * 1024 * 1024, 64, 4096, 4096).expect("limits");
        let doc = parse_ami_text_v1(text.as_bytes(), limits).expect("parse");
        let trees = build_parameter_trees_v1(&doc).expect("build");
        trees.into_iter().next().expect("one tree")
    }

    #[test]
    fn resolves_typed_form_type() {
        let t = tree("(root (gain Float 0.5) (steps Integer 7))");
        assert_eq!(
            resolve_parameter_tree_leaf_type_v1(&t, "root.gain"),
            Ok(AmiParameterTypeV1::Float)
        );
        assert_eq!(
            resolve_parameter_tree_leaf_type_v1(&t, "root.steps"),
            Ok(AmiParameterTypeV1::Integer)
        );
    }

    #[test]
    fn nested_path_resolves() {
        let t = tree("(root (sub (steps Integer 007)) (gain Float 0.5))");
        assert_eq!(
            resolve_parameter_tree_leaf_type_v1(&t, "root.sub.steps"),
            Ok(AmiParameterTypeV1::Integer)
        );
        assert_eq!(
            resolve_parameter_tree_leaf_type_v1(&t, "root.gain"),
            Ok(AmiParameterTypeV1::Float)
        );
    }

    #[test]
    fn empty_path_fails_closed() {
        let t = tree("(root (gain Float 0.5))");
        assert_eq!(
            resolve_parameter_tree_leaf_type_v1(&t, ""),
            Err(ParameterTreeLeafTypeResolutionErrorV1::EmptyPath)
        );
        assert_eq!(
            resolve_parameter_tree_leaf_type_v1(&t, "   "),
            Err(ParameterTreeLeafTypeResolutionErrorV1::EmptyPath)
        );
    }

    #[test]
    fn missing_path_fails_closed() {
        let t = tree("(root (gain Float 0.5))");
        assert_eq!(
            resolve_parameter_tree_leaf_type_v1(&t, "root.nope"),
            Err(ParameterTreeLeafTypeResolutionErrorV1::MissingPath(
                "root.nope".to_string()
            ))
        );
        assert_eq!(
            resolve_parameter_tree_leaf_type_v1(&t, "other.gain"),
            Err(ParameterTreeLeafTypeResolutionErrorV1::MissingPath(
                "other.gain".to_string()
            ))
        );
    }

    #[test]
    fn branch_path_is_not_a_leaf() {
        let t = tree("(root (sub (steps Integer 7)))");
        assert_eq!(
            resolve_parameter_tree_leaf_type_v1(&t, "root.sub"),
            Err(ParameterTreeLeafTypeResolutionErrorV1::PathNotLeaf(
                "root.sub".to_string()
            ))
        );
        assert_eq!(
            resolve_parameter_tree_leaf_type_v1(&t, "root"),
            Err(ParameterTreeLeafTypeResolutionErrorV1::PathNotLeaf(
                "root".to_string()
            ))
        );
    }

    #[test]
    fn non_typed_leaf_fails_closed() {
        let t = tree("(root (plain 5) (raw x y z))");
        assert_eq!(
            resolve_parameter_tree_leaf_type_v1(&t, "root.plain"),
            Err(ParameterTreeLeafTypeResolutionErrorV1::LeafNotTypedForm(
                "root.plain".to_string()
            ))
        );
        assert_eq!(
            resolve_parameter_tree_leaf_type_v1(&t, "root.raw"),
            Err(ParameterTreeLeafTypeResolutionErrorV1::LeafNotTypedForm(
                "root.raw".to_string()
            ))
        );
    }

    #[test]
    fn dotted_path_variants_canonicalize() {
        let t = tree("(root (gain Float 0.5))");
        assert_eq!(
            resolve_parameter_tree_leaf_type_v1(&t, " root..gain "),
            Ok(AmiParameterTypeV1::Float)
        );
    }
}
