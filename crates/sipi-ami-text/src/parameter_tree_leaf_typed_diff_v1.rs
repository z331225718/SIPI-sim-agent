//! AMI parameter tree leaf typed diff core (P4B-02b89).
//!
//! Diffs the leaves of two `AmiParameterTreeV1` trees at matching canonical
//! dot-separated paths under typed value semantics: leaves at the same path
//! whose value tokens are typed-equivalent (02b70, both leaves well-formed
//! typed forms with valid values) count as matched; typed-inequivalent leaves
//! are reported as changed with both token lists and the typed reason; leaves
//! where either side is not a typed form fall back to raw token equality
//! (matched when tokens are byte-equal, changed with reason None otherwise);
//! left-only paths are removed and right-only paths are added. This is the
//! tree-pair typed companion of 02b11 raw tree diff and of 02b79 profile typed
//! diff, at leaf-path granularity.
//!
//! Fail-closed: the diff is total (no error path); all lists come back in
//! deterministic sorted (path) order.

use std::collections::BTreeMap;

use crate::{
    parameter_values_equivalent_v1, AmiParameterTreeV1, AmiParameterTreeNodeV1,
    AmiParameterTypeV1, AmiParameterValueV1, ParameterValueEquivalenceV1,
    ParameterValueInequivalenceReasonV1,
};

/// Explicit scope policy of this slice: typed leaf diff of two trees.
pub const PARAMETER_TREE_LEAF_TYPED_DIFF_POLICY_V1: &str =
    "sipi.p4b-02b89.parameter-tree-leaf-typed-diff-v1.typed-leaf-diff";

/// One typed or raw change for a shared leaf path.
#[derive(Clone, Debug, PartialEq)]
pub struct ParameterTreeLeafTypedChangeV1 {
    path: String,
    old_tokens: Vec<String>,
    new_tokens: Vec<String>,
    reason: Option<ParameterValueInequivalenceReasonV1>,
}

impl ParameterTreeLeafTypedChangeV1 {
    pub fn path(&self) -> &str {
        &self.path
    }

    pub fn old_tokens(&self) -> &[String] {
        &self.old_tokens
    }

    pub fn new_tokens(&self) -> &[String] {
        &self.new_tokens
    }

    /// The typed inequivalence reason, or None when the raw fallback applied.
    pub fn reason(&self) -> Option<&ParameterValueInequivalenceReasonV1> {
        self.reason.as_ref()
    }
}

/// Outcome of a typed leaf diff between two trees.
#[derive(Clone, Debug, PartialEq)]
pub struct ParameterTreeLeafTypedDiffV1 {
    matched: usize,
    added: Vec<String>,
    removed: Vec<String>,
    changed: Vec<ParameterTreeLeafTypedChangeV1>,
}

impl ParameterTreeLeafTypedDiffV1 {
    /// Shared paths with typed-equivalent (or raw-equal) leaves.
    pub fn matched(&self) -> usize {
        self.matched
    }

    /// Sorted paths present in right but missing in left.
    pub fn added(&self) -> &[String] {
        &self.added
    }

    /// Sorted paths present in left but missing in right.
    pub fn removed(&self) -> &[String] {
        &self.removed
    }

    /// Sorted (by path) changes for shared paths.
    pub fn changed(&self) -> &[ParameterTreeLeafTypedChangeV1] {
        &self.changed
    }
}

/// Collect canonical leaf paths -> value tokens for a tree.
fn collect_leaves(node: &AmiParameterTreeNodeV1, prefix: &str, out: &mut BTreeMap<String, Vec<String>>) {
    let current = if prefix.is_empty() {
        node.name().to_string()
    } else {
        format!("{prefix}.{}", node.name())
    };
    match node {
        AmiParameterTreeNodeV1::Branch { children, .. } => {
            for child in children.values() {
                collect_leaves(child, &current, out);
            }
        }
        AmiParameterTreeNodeV1::Leaf { value_tokens, .. } => {
            out.insert(current, value_tokens.clone());
        }
    }
}

/// Build a typed value from a leaf's tokens when it is a typed form.
fn typed_value(name: &str, tokens: &[String]) -> Option<AmiParameterValueV1> {
    if tokens.len() == 2 {
        if AmiParameterTypeV1::from_token(&tokens[0]).is_some() {
            if let Ok(parameter) = AmiParameterValueV1::try_new(name, &tokens[0], &tokens[1]) {
                return Some(parameter);
            }
        }
    }
    None
}

/// Diff two trees' leaves at matching canonical paths under typed semantics.
pub fn diff_parameter_tree_leaves_typed_v1(
    left: &AmiParameterTreeV1,
    right: &AmiParameterTreeV1,
) -> ParameterTreeLeafTypedDiffV1 {
    let mut left_leaves = BTreeMap::new();
    let mut right_leaves = BTreeMap::new();
    collect_leaves(left.root_node(), "", &mut left_leaves);
    collect_leaves(right.root_node(), "", &mut right_leaves);

    let mut matched = 0usize;
    let mut added = Vec::new();
    let mut removed = Vec::new();
    let mut changed = Vec::new();

    for path in left_leaves.keys() {
        if !right_leaves.contains_key(path) {
            removed.push(path.clone());
        }
    }
    for path in right_leaves.keys() {
        if !left_leaves.contains_key(path) {
            added.push(path.clone());
        }
    }
    for (path, left_tokens) in &left_leaves {
        if let Some(right_tokens) = right_leaves.get(path) {
            let leaf_name = path
                .rsplit('.')
                .next()
                .unwrap_or(path)
                .to_string();
            let equivalence = match (
                typed_value(&leaf_name, left_tokens),
                typed_value(&leaf_name, right_tokens),
            ) {
                (Some(left_value), Some(right_value)) => {
                    match parameter_values_equivalent_v1(&left_value, &right_value) {
                        ParameterValueEquivalenceV1::Equivalent => {
                            matched += 1;
                            continue;
                        }
                        ParameterValueEquivalenceV1::NotEquivalent(reason) => {
                            Some(reason)
                        }
                    }
                }
                _ => {
                    if left_tokens == right_tokens {
                        matched += 1;
                        continue;
                    }
                    None
                }
            };
            changed.push(ParameterTreeLeafTypedChangeV1 {
                path: path.clone(),
                old_tokens: left_tokens.clone(),
                new_tokens: right_tokens.clone(),
                reason: equivalence,
            });
        }
    }
    ParameterTreeLeafTypedDiffV1 {
        matched,
        added,
        removed,
        changed,
    }
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
    fn identical_trees_are_all_matched() {
        let a = tree("(root (gain Float 0.5) (steps Integer 7))");
        let b = tree("(root (gain Float 0.5) (steps Integer 7))");
        let diff = diff_parameter_tree_leaves_typed_v1(&a, &b);
        assert_eq!(diff.matched(), 2);
        assert!(diff.added().is_empty());
        assert!(diff.removed().is_empty());
        assert!(diff.changed().is_empty());
    }

    #[test]
    fn spelling_variants_count_as_matched() {
        let a = tree("(root (gain Float 0.5))");
        let b = tree("(root (gain Float 0.50))");
        let diff = diff_parameter_tree_leaves_typed_v1(&a, &b);
        assert_eq!(diff.matched(), 1);
        assert!(diff.changed().is_empty());
    }

    #[test]
    fn added_and_removed_paths_are_reported() {
        let a = tree("(root (gain Float 0.5) (steps Integer 7))");
        let b = tree("(root (gain Float 0.5) (mode String Linear))");
        let diff = diff_parameter_tree_leaves_typed_v1(&a, &b);
        assert_eq!(diff.matched(), 1);
        assert_eq!(diff.removed(), &["root.steps".to_string()]);
        assert_eq!(diff.added(), &["root.mode".to_string()]);
        assert!(diff.changed().is_empty());
    }

    #[test]
    fn typed_change_is_reported_with_reason() {
        let a = tree("(root (gain Float 0.5))");
        let b = tree("(root (gain Float 0.5001))");
        let diff = diff_parameter_tree_leaves_typed_v1(&a, &b);
        assert_eq!(diff.matched(), 0);
        assert_eq!(diff.changed().len(), 1);
        let change = &diff.changed()[0];
        assert_eq!(change.path(), "root.gain");
        assert_eq!(
            change.reason(),
            Some(&ParameterValueInequivalenceReasonV1::FloatMismatch {
                left: 0.5,
                right: 0.5001,
            })
        );
    }

    #[test]
    fn non_typed_leaves_use_raw_fallback() {
        let a = tree("(root (plain 5) (same x y))");
        let b = tree("(root (plain 6) (same x y))");
        let diff = diff_parameter_tree_leaves_typed_v1(&a, &b);
        assert_eq!(diff.matched(), 1);
        assert_eq!(diff.changed().len(), 1);
        let change = &diff.changed()[0];
        assert_eq!(change.path(), "root.plain");
        assert_eq!(change.reason(), None);
    }

    #[test]
    fn nested_changes_are_reported_by_path() {
        let a = tree("(root (sub (steps Integer 007)) (gain Float 0.5))");
        let b = tree("(root (sub (steps Integer 8)) (gain Float 0.5))");
        let diff = diff_parameter_tree_leaves_typed_v1(&a, &b);
        assert_eq!(diff.matched(), 1);
        assert_eq!(diff.changed().len(), 1);
        assert_eq!(diff.changed()[0].path(), "root.sub.steps");
    }
}
