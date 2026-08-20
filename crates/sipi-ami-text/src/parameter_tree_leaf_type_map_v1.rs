//! AMI parameter tree leaf declared-type map core (P4B-02b87).
//!
//! Extracts the declared-type inventory of an `AmiParameterTreeV1`:
//! `extract_parameter_tree_leaf_type_map_v1` walks every leaf and, for leaves
//! whose value tokens are a well-formed typed form (exactly two tokens whose
//! first token is a known type token Float/Integer/Boolean/String/List),
//! records leaf name -> declared type in a map. This is the declared-type
//! companion of 02b33 type inference (which guesses types from values) and
//! builds exactly the name -> type map that 02b37 leaf decoding consumes.
//! Leaves that are not typed forms (single-token, multi-token, unknown type
//! token) are counted as skipped, not rejected: the map carries only what the
//! document declares.
//!
//! Fail-closed: the extraction is total (no error path); traversal is
//! deterministic (sorted children, canonical order); a leaf name appearing at
//! multiple depths takes its last canonical occurrence (documented; duplicate
//! consistency is 02b54's concern).

use std::collections::BTreeMap;

use crate::{AmiParameterTreeV1, AmiParameterTreeNodeV1, AmiParameterTypeV1};

/// Explicit scope policy of this slice: declared-type map of tree leaves.
pub const PARAMETER_TREE_LEAF_TYPE_MAP_POLICY_V1: &str =
    "sipi.p4b-02b87.parameter-tree-leaf-type-map-v1.declared-type-map";

/// Outcome of extracting the declared-type map of a tree's leaves.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ParameterTreeLeafTypeMapV1 {
    type_map: BTreeMap<String, AmiParameterTypeV1>,
    leaves_total: usize,
    typed_leaves: usize,
    skipped: usize,
}

impl ParameterTreeLeafTypeMapV1 {
    /// Declared leaf name -> type map (last canonical occurrence wins).
    pub fn type_map(&self) -> &BTreeMap<String, AmiParameterTypeV1> {
        &self.type_map
    }

    /// Total number of leaves in the tree.
    pub fn leaves_total(&self) -> usize {
        self.leaves_total
    }

    /// Leaves recorded as typed forms.
    pub fn typed_leaves(&self) -> usize {
        self.typed_leaves
    }

    /// Leaves skipped (not typed forms).
    pub fn skipped(&self) -> usize {
        self.skipped
    }
}

fn collect(node: &AmiParameterTreeNodeV1, state: &mut ParameterTreeLeafTypeMapV1) {
    match node {
        AmiParameterTreeNodeV1::Branch { children, .. } => {
            for child in children.values() {
                collect(child, state);
            }
        }
        AmiParameterTreeNodeV1::Leaf { name, value_tokens } => {
            state.leaves_total += 1;
            if value_tokens.len() == 2 {
                if let Some(parameter_type) = AmiParameterTypeV1::from_token(&value_tokens[0]) {
                    state.type_map.insert(name.clone(), parameter_type);
                    state.typed_leaves += 1;
                    return;
                }
            }
            state.skipped += 1;
        }
    }
}

/// Extract the declared-type map of every leaf of a parameter tree.
pub fn extract_parameter_tree_leaf_type_map_v1(
    tree: &AmiParameterTreeV1,
) -> ParameterTreeLeafTypeMapV1 {
    let mut state = ParameterTreeLeafTypeMapV1 {
        type_map: BTreeMap::new(),
        leaves_total: 0,
        typed_leaves: 0,
        skipped: 0,
    };
    collect(tree.root_node(), &mut state);
    state
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
    fn extracts_typed_form_types() {
        let t = tree("(root (gain Float 0.5) (steps Integer 7) (on Boolean True))");
        let result = extract_parameter_tree_leaf_type_map_v1(&t);
        assert_eq!(result.leaves_total(), 3);
        assert_eq!(result.typed_leaves(), 3);
        assert_eq!(result.skipped(), 0);
        assert_eq!(result.type_map()["gain"], AmiParameterTypeV1::Float);
        assert_eq!(result.type_map()["steps"], AmiParameterTypeV1::Integer);
        assert_eq!(result.type_map()["on"], AmiParameterTypeV1::Boolean);
    }

    #[test]
    fn non_typed_leaves_are_skipped() {
        let t = tree("(root (plain 5) (raw x y z) (bad Nope 1.0))");
        let result = extract_parameter_tree_leaf_type_map_v1(&t);
        assert_eq!(result.leaves_total(), 3);
        assert_eq!(result.typed_leaves(), 0);
        assert_eq!(result.skipped(), 3);
        assert!(result.type_map().is_empty());
    }

    #[test]
    fn nested_leaves_are_extracted() {
        let t = tree("(root (sub (steps Integer 007)) (gain Float 0.5))");
        let result = extract_parameter_tree_leaf_type_map_v1(&t);
        assert_eq!(result.leaves_total(), 2);
        assert_eq!(result.typed_leaves(), 2);
        assert_eq!(result.type_map()["steps"], AmiParameterTypeV1::Integer);
        assert_eq!(result.type_map()["gain"], AmiParameterTypeV1::Float);
    }

    #[test]
    fn duplicate_names_take_last_canonical_occurrence() {
        let t = tree("(root (gain Float 0.5) (sub (gain Integer 7)))");
        let result = extract_parameter_tree_leaf_type_map_v1(&t);
        assert_eq!(result.leaves_total(), 2);
        assert_eq!(result.typed_leaves(), 2);
        assert_eq!(result.type_map()["gain"], AmiParameterTypeV1::Integer);
    }

    #[test]
    fn mixed_typed_and_skipped_counts() {
        let t = tree("(root (gain Float 0.5) (plain 5) (channels List \"(a)\") (raw x y))");
        let result = extract_parameter_tree_leaf_type_map_v1(&t);
        assert_eq!(result.leaves_total(), 4);
        assert_eq!(result.typed_leaves(), 2);
        assert_eq!(result.skipped(), 2);
        assert_eq!(result.type_map()["gain"], AmiParameterTypeV1::Float);
        assert_eq!(result.type_map()["channels"], AmiParameterTypeV1::List);
    }

    #[test]
    fn tree_without_typed_leaves_is_all_skipped() {
        let t = tree("(root (sub (plain 5)) (other 7))");
        let result = extract_parameter_tree_leaf_type_map_v1(&t);
        assert_eq!(result.leaves_total(), 2);
        assert_eq!(result.typed_leaves(), 0);
        assert_eq!(result.skipped(), 2);
    }
}
