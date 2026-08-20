//! AMI parameter tree typed-leaf fingerprint core (P4B-02b97).
//!
//! Computes a deterministic 64-bit fingerprint of the typed-form leaf content
//! of an `AmiParameterTreeV1`: `fingerprint_parameter_tree_typed_leaves_v1`
//! walks every leaf, collects the canonical path -> (declared type token, raw
//! value token) of every typed-form leaf (exactly two value tokens whose first
//! token is a known type token Float/Integer/Boolean/String/List; value
//! validity is not checked — the declared content is fingerprinted as-is),
//! serializes the sorted map to compact JSON, and applies FNV-1a 64. This is
//! the tree-level change detection fingerprint over declared typed content
//! (paths, types, and raw values), the companion of 02b96's profile
//! fingerprint; non-typed leaves are skipped and do not affect the hash.
//!
//! Fail-closed: the fingerprint is total (no error path); FNV-1a 64 uses
//! wrapping arithmetic with the standard offset basis (14695981039346656037)
//! and prime (1099511628211); a tree with no typed-form leaves hashes the
//! empty object `{}`.

use std::collections::BTreeMap;

use serde_json::{Map, Value};

use crate::{AmiParameterTreeV1, AmiParameterTreeNodeV1, AmiParameterTypeV1};

/// Explicit scope policy of this slice: typed-leaf content fingerprint.
pub const PARAMETER_TREE_TYPED_LEAF_FINGERPRINT_POLICY_V1: &str =
    "sipi.p4b-02b97.parameter-tree-typed-leaf-fingerprint-v1.fnv1a64-typed-leaf-content";

const FNV1A64_OFFSET_BASIS: u64 = 14695981039346656037;
const FNV1A64_PRIME: u64 = 1099511628211;

/// FNV-1a 64-bit hash of a byte slice.
fn fnv1a64(bytes: &[u8]) -> u64 {
    let mut hash = FNV1A64_OFFSET_BASIS;
    for byte in bytes {
        hash ^= u64::from(*byte);
        hash = hash.wrapping_mul(FNV1A64_PRIME);
    }
    hash
}

/// Collect canonical path -> (type token, value token) of typed-form leaves.
fn collect_typed_leaves(
    node: &AmiParameterTreeNodeV1,
    prefix: &str,
    out: &mut BTreeMap<String, (String, String)>,
) {
    let current = if prefix.is_empty() {
        node.name().to_string()
    } else {
        format!("{prefix}.{}", node.name())
    };
    match node {
        AmiParameterTreeNodeV1::Branch { children, .. } => {
            for child in children.values() {
                collect_typed_leaves(child, &current, out);
            }
        }
        AmiParameterTreeNodeV1::Leaf { value_tokens, .. } => {
            if value_tokens.len() == 2 {
                if AmiParameterTypeV1::from_token(&value_tokens[0]).is_some() {
                    out.insert(
                        current,
                        (value_tokens[0].clone(), value_tokens[1].clone()),
                    );
                }
            }
        }
    }
}

/// 64-bit fingerprint of a tree's typed-form leaf content.
pub fn fingerprint_parameter_tree_typed_leaves_v1(tree: &AmiParameterTreeV1) -> u64 {
    let mut leaves = BTreeMap::new();
    collect_typed_leaves(tree.root_node(), "", &mut leaves);
    let mut object = Map::new();
    for (path, (type_token, value_token)) in leaves {
        let mut entry = Map::new();
        entry.insert("type".to_string(), Value::String(type_token));
        entry.insert("value".to_string(), Value::String(value_token));
        object.insert(path, Value::Object(entry));
    }
    let serialized =
        serde_json::to_string(&Value::Object(object)).expect("typed-leaf json serialization");
    fnv1a64(serialized.as_bytes())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{build_parameter_trees_v1, parse_ami_text_v1, ParseLimitsV1};

    fn tree(text: &str) -> AmiParameterTreeV1 {
        let limits = ParseLimitsV1::try_new(8 * 1024 * 1024, 64, 4096, 4096).expect("limits");
        let doc = parse_ami_text_v1(text.as_bytes(), limits).expect("parse");
        let trees = build_parameter_trees_v1(&doc).expect("build");
        trees.into_iter().next().expect("one tree")
    }

    #[test]
    fn fingerprint_is_deterministic() {
        let t = tree("(root (gain Float 0.5) (steps Integer 7))");
        assert_eq!(
            fingerprint_parameter_tree_typed_leaves_v1(&t),
            fingerprint_parameter_tree_typed_leaves_v1(&t)
        );
    }

    #[test]
    fn fingerprint_changes_with_value() {
        let a = tree("(root (gain Float 0.5))");
        let b = tree("(root (gain Float 0.5001))");
        assert_ne!(
            fingerprint_parameter_tree_typed_leaves_v1(&a),
            fingerprint_parameter_tree_typed_leaves_v1(&b)
        );
    }

    #[test]
    fn fingerprint_changes_with_type() {
        let a = tree("(root (gain Float 0.5))");
        let b = tree("(root (gain Integer 0))");
        assert_ne!(
            fingerprint_parameter_tree_typed_leaves_v1(&a),
            fingerprint_parameter_tree_typed_leaves_v1(&b)
        );
    }

    #[test]
    fn fingerprint_changes_with_path() {
        let a = tree("(root (sub (steps Integer 7)))");
        let b = tree("(root (steps Integer 7))");
        assert_ne!(
            fingerprint_parameter_tree_typed_leaves_v1(&a),
            fingerprint_parameter_tree_typed_leaves_v1(&b)
        );
    }

    #[test]
    fn skipped_leaves_do_not_affect_fingerprint() {
        let a = tree("(root (gain Float 0.5))");
        let b = tree("(root (gain Float 0.5) (plain 5))");
        assert_eq!(
            fingerprint_parameter_tree_typed_leaves_v1(&a),
            fingerprint_parameter_tree_typed_leaves_v1(&b)
        );
    }

    #[test]
    fn no_typed_leaves_hashes_empty_object() {
        let t = tree("(root (plain 5) (raw x y z))");
        assert_eq!(fingerprint_parameter_tree_typed_leaves_v1(&t), fnv1a64(b"{}"));
    }
}
