//! AMI parameter tree typed-leaf type counts core (P4B-02b93).
//!
//! Counts the typed-form leaves of an `AmiParameterTreeV1` by declared type:
//! `count_parameter_tree_typed_leaves_by_type_v1` walks every leaf and counts
//! those whose value tokens are a well-formed typed form (exactly two tokens
//! whose first token is a known type token Float/Integer/Boolean/String/List)
//! per declared type, plus skipped leaves (not typed forms). This is the
//! tree-level companion of 02b73 profile type statistics and the count view
//! over 02b87's leaf type map.
//!
//! Fail-closed: the counting is total (no error path); traversal is
//! deterministic (sorted children, canonical order); the per-type counts sum
//! to `total_typed` and `total_typed + skipped` equals the total leaf count.

use crate::{AmiParameterTreeNodeV1, AmiParameterTreeV1, AmiParameterTypeV1};

/// Explicit scope policy of this slice: typed-leaf type counts of a tree.
pub const PARAMETER_TREE_TYPED_LEAF_TYPE_COUNTS_POLICY_V1: &str =
    "sipi.p4b-02b93.parameter-tree-typed-leaf-type-counts-v1.typed-leaf-type-counts";

/// Declared-type inventory of a tree's typed-form leaves.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ParameterTreeTypedLeafTypeCountsV1 {
    total_typed: usize,
    float_count: usize,
    integer_count: usize,
    boolean_count: usize,
    string_count: usize,
    list_count: usize,
    skipped: usize,
}

impl ParameterTreeTypedLeafTypeCountsV1 {
    /// Typed-form leaves in total.
    pub fn total_typed(&self) -> usize {
        self.total_typed
    }

    pub fn float_count(&self) -> usize {
        self.float_count
    }

    pub fn integer_count(&self) -> usize {
        self.integer_count
    }

    pub fn boolean_count(&self) -> usize {
        self.boolean_count
    }

    pub fn string_count(&self) -> usize {
        self.string_count
    }

    pub fn list_count(&self) -> usize {
        self.list_count
    }

    /// Leaves that are not typed forms.
    pub fn skipped(&self) -> usize {
        self.skipped
    }

    /// Per-type counts sum to total_typed (invariant, checked in tests).
    pub fn sum_of_type_counts(&self) -> usize {
        self.float_count
            + self.integer_count
            + self.boolean_count
            + self.string_count
            + self.list_count
    }
}

/// Count the typed-form leaves of a parameter tree by declared type.
pub fn count_parameter_tree_typed_leaves_by_type_v1(
    tree: &AmiParameterTreeV1,
) -> ParameterTreeTypedLeafTypeCountsV1 {
    let mut counts = ParameterTreeTypedLeafTypeCountsV1 {
        total_typed: 0,
        float_count: 0,
        integer_count: 0,
        boolean_count: 0,
        string_count: 0,
        list_count: 0,
        skipped: 0,
    };
    fn collect(node: &AmiParameterTreeNodeV1, counts: &mut ParameterTreeTypedLeafTypeCountsV1) {
        match node {
            AmiParameterTreeNodeV1::Branch { children, .. } => {
                for child in children.values() {
                    collect(child, counts);
                }
            }
            AmiParameterTreeNodeV1::Leaf { value_tokens, .. } => {
                if value_tokens.len() == 2 {
                    match AmiParameterTypeV1::from_token(&value_tokens[0]) {
                        Some(AmiParameterTypeV1::Float) => counts.float_count += 1,
                        Some(AmiParameterTypeV1::Integer) => counts.integer_count += 1,
                        Some(AmiParameterTypeV1::Boolean) => counts.boolean_count += 1,
                        Some(AmiParameterTypeV1::String_) => counts.string_count += 1,
                        Some(AmiParameterTypeV1::List) => counts.list_count += 1,
                        None => {
                            counts.skipped += 1;
                            return;
                        }
                    }
                    counts.total_typed += 1;
                } else {
                    counts.skipped += 1;
                }
            }
        }
    }
    collect(tree.root_node(), &mut counts);
    counts
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
    fn counts_each_declared_type() {
        let t = tree(
            "(root (gain Float 0.5) (steps Integer 7) (on Boolean True) (mode String Linear) (channels List \"(a, b)\"))",
        );
        let counts = count_parameter_tree_typed_leaves_by_type_v1(&t);
        assert_eq!(counts.total_typed(), 5);
        assert_eq!(counts.float_count(), 1);
        assert_eq!(counts.integer_count(), 1);
        assert_eq!(counts.boolean_count(), 1);
        assert_eq!(counts.string_count(), 1);
        assert_eq!(counts.list_count(), 1);
        assert_eq!(counts.skipped(), 0);
        assert_eq!(counts.sum_of_type_counts(), counts.total_typed());
    }

    #[test]
    fn non_typed_leaves_are_skipped() {
        let t = tree("(root (plain 5) (raw x y z) (bad Nope 1.0))");
        let counts = count_parameter_tree_typed_leaves_by_type_v1(&t);
        assert_eq!(counts.total_typed(), 0);
        assert_eq!(counts.skipped(), 3);
        assert_eq!(counts.sum_of_type_counts(), 0);
    }

    #[test]
    fn nested_leaves_are_counted() {
        let t = tree("(root (sub (steps Integer 007)) (gain Float 0.5))");
        let counts = count_parameter_tree_typed_leaves_by_type_v1(&t);
        assert_eq!(counts.total_typed(), 2);
        assert_eq!(counts.integer_count(), 1);
        assert_eq!(counts.float_count(), 1);
    }

    #[test]
    fn sum_invariant_holds() {
        let t = tree(
            "(root (gain Float 0.5) (a Integer 1) (b Integer 2) (on Boolean True) (mode String Linear) (plain 5))",
        );
        let counts = count_parameter_tree_typed_leaves_by_type_v1(&t);
        assert_eq!(counts.total_typed(), 5);
        assert_eq!(counts.skipped(), 1);
        assert_eq!(counts.sum_of_type_counts(), 5);
    }

    #[test]
    fn quoted_list_counts_as_list() {
        let t = tree("(root (channels List \"(a, b)\"))");
        let counts = count_parameter_tree_typed_leaves_by_type_v1(&t);
        assert_eq!(counts.total_typed(), 1);
        assert_eq!(counts.list_count(), 1);
    }

    #[test]
    fn tree_without_leaves_is_all_zero() {
        let t = tree("(root (sub (leaf 1)))");
        let counts = count_parameter_tree_typed_leaves_by_type_v1(&t);
        assert_eq!(counts.total_typed(), 0);
        assert_eq!(counts.skipped(), 1);
    }
}
