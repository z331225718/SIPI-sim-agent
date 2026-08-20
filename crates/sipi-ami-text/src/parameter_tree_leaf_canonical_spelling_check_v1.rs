//! AMI parameter tree leaf canonical spelling check core (P4B-02b94).
//!
//! Checks whether every try_new-valid typed-form leaf of an
//! `AmiParameterTreeV1` already carries its canonical value spelling
//! (`canonicalize_parameter_value_spelling_v1`, 02b75):
//! `check_parameter_tree_leaf_spellings_canonical_v1` walks every leaf and,
//! for leaves whose value tokens are a well-formed typed form (exactly two
//! tokens whose first token is a known type token) whose value passes
//! `AmiParameterValueV1::try_new` (02b1), compares the raw value token to its
//! canonical spelling (Integer `007` -> `7`, List item spacing normalization)
//! and reports each non-canonical leaf with its path, declared type, raw value,
//! and canonical value. This is the pure check companion of 02b78 tree leaf
//! canonicalization (which rewrites) and the tree-level gate before
//! canonicalizing. Leaves that are not try_new-valid typed forms (non-typed
//! forms, quoted List spellings that fail raw try_new) are skipped.
//!
//! Fail-closed: the check is total (no error path); non-canonical entries come
//! back in deterministic sorted (path) order; `canonical()` is true exactly
//! when no non-canonical leaf was found.

use std::collections::BTreeMap;

use crate::{
    canonicalize_parameter_value_spelling_v1, AmiParameterTreeV1, AmiParameterTreeNodeV1,
    AmiParameterTypeV1, AmiParameterValueV1,
};

/// Explicit scope policy of this slice: canonical leaf spelling check.
pub const PARAMETER_TREE_LEAF_CANONICAL_SPELLING_CHECK_POLICY_V1: &str =
    "sipi.p4b-02b94.parameter-tree-leaf-canonical-spelling-check-v1.canonical-leaf-spelling-check";

/// One non-canonical typed-form leaf with its canonical value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ParameterTreeLeafCanonicalSpellingIssueV1 {
    path: String,
    type_token: String,
    value_token: String,
    canonical: String,
}

impl ParameterTreeLeafCanonicalSpellingIssueV1 {
    pub fn path(&self) -> &str {
        &self.path
    }

    pub fn type_token(&self) -> &str {
        &self.type_token
    }

    pub fn value_token(&self) -> &str {
        &self.value_token
    }

    pub fn canonical(&self) -> &str {
        &self.canonical
    }
}

/// Outcome of the canonical spelling check over a tree's typed-form leaves.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ParameterTreeLeafCanonicalSpellingCheckV1 {
    typed_leaves: usize,
    non_canonical: Vec<ParameterTreeLeafCanonicalSpellingIssueV1>,
}

impl ParameterTreeLeafCanonicalSpellingCheckV1 {
    /// try_new-valid typed-form leaves that were checked.
    pub fn typed_leaves(&self) -> usize {
        self.typed_leaves
    }

    /// Sorted (by path) non-canonical typed-form leaves.
    pub fn non_canonical(&self) -> &[ParameterTreeLeafCanonicalSpellingIssueV1] {
        &self.non_canonical
    }

    /// True when every checked leaf is canonical.
    pub fn canonical(&self) -> bool {
        self.non_canonical.is_empty()
    }
}

fn collect(
    node: &AmiParameterTreeNodeV1,
    prefix: &str,
    report: &mut ParameterTreeLeafCanonicalSpellingCheckV1,
) {
    let current = if prefix.is_empty() {
        node.name().to_string()
    } else {
        format!("{prefix}.{}", node.name())
    };
    match node {
        AmiParameterTreeNodeV1::Branch { children, .. } => {
            for child in children.values() {
                collect(child, &current, report);
            }
        }
        AmiParameterTreeNodeV1::Leaf { name, value_tokens } => {
            if value_tokens.len() == 2 {
                if AmiParameterTypeV1::from_token(&value_tokens[0]).is_some() {
                    if let Ok(parameter) =
                        AmiParameterValueV1::try_new(name, &value_tokens[0], &value_tokens[1])
                    {
                        report.typed_leaves += 1;
                        let canonical =
                            canonicalize_parameter_value_spelling_v1(&parameter);
                        if canonical != value_tokens[1] {
                            report.non_canonical.push(
                                ParameterTreeLeafCanonicalSpellingIssueV1 {
                                    path: current,
                                    type_token: value_tokens[0].clone(),
                                    value_token: value_tokens[1].clone(),
                                    canonical,
                                },
                            );
                        }
                    }
                }
            }
        }
    }
}

/// Check the canonical spelling of every try_new-valid typed-form leaf.
pub fn check_parameter_tree_leaf_spellings_canonical_v1(
    tree: &AmiParameterTreeV1,
) -> ParameterTreeLeafCanonicalSpellingCheckV1 {
    let mut report = ParameterTreeLeafCanonicalSpellingCheckV1 {
        typed_leaves: 0,
        non_canonical: Vec::new(),
    };
    collect(tree.root_node(), "", &mut report);
    report
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
    fn canonical_tree_is_canonical() {
        let t = tree("(root (gain Float 0.5) (steps Integer 7) (on Boolean True))");
        let report = check_parameter_tree_leaf_spellings_canonical_v1(&t);
        assert_eq!(report.typed_leaves(), 3);
        assert!(report.non_canonical().is_empty());
        assert!(report.canonical());
    }

    #[test]
    fn non_canonical_integer_is_reported() {
        let t = tree("(root (steps Integer 007) (gain Float 0.5))");
        let report = check_parameter_tree_leaf_spellings_canonical_v1(&t);
        assert_eq!(report.typed_leaves(), 2);
        assert_eq!(report.non_canonical().len(), 1);
        let issue = &report.non_canonical()[0];
        assert_eq!(issue.path(), "root.steps");
        assert_eq!(issue.type_token(), "Integer");
        assert_eq!(issue.value_token(), "007");
        assert_eq!(issue.canonical(), "7");
        assert!(!report.canonical());
    }

    #[test]
    fn nested_non_canonical_is_reported() {
        let t = tree("(root (sub (steps Integer 007)) (gain Float 0.5))");
        let report = check_parameter_tree_leaf_spellings_canonical_v1(&t);
        assert_eq!(report.non_canonical().len(), 1);
        assert_eq!(report.non_canonical()[0].path(), "root.sub.steps");
    }

    #[test]
    fn quoted_list_is_skipped() {
        // Quoted List spellings fail raw try_new (02b1), so they are skipped
        // by the check, consistent with 02b91's raw rule.
        let t = tree("(root (channels List \"(a,b,c)\") (steps Integer 7))");
        let report = check_parameter_tree_leaf_spellings_canonical_v1(&t);
        assert_eq!(report.typed_leaves(), 1);
        assert!(report.non_canonical().is_empty());
        assert!(report.canonical());
    }

    #[test]
    fn invalid_value_is_skipped() {
        let t = tree("(root (gain Float abc))");
        let report = check_parameter_tree_leaf_spellings_canonical_v1(&t);
        assert_eq!(report.typed_leaves(), 0);
        assert!(report.canonical());
    }

    #[test]
    fn mixed_canonical_and_non_canonical() {
        let t = tree("(root (a Integer 007) (b Integer 7) (c Float 0.5))");
        let report = check_parameter_tree_leaf_spellings_canonical_v1(&t);
        assert_eq!(report.typed_leaves(), 3);
        assert_eq!(report.non_canonical().len(), 1);
        assert_eq!(report.non_canonical()[0].path(), "root.a");
        assert_eq!(report.non_canonical()[0].canonical(), "7");
    }
}
