//! AMI parameter tree leaf value validity report core (P4B-02b91).
//!
//! Reports the value validity of every typed-form leaf of an
//! `AmiParameterTreeV1` using the document's own declared types:
//! `check_parameter_tree_leaf_value_validity_v1` walks every leaf and, for
//! leaves whose value tokens are a well-formed typed form (exactly two tokens
//! whose first token is a known type token Float/Integer/Boolean/String/List),
//! validates the value token via `AmiParameterValueV1::try_new` (02b1) and
//! reports each invalid leaf with its canonical path, declared type token,
//! value token, and typed error. This is the declared-type companion of 02b32
//! value validation (which needs an external name -> type map) and the
//! value-semantics complement of 02b58 typed-form conformance (form shape).
//! Leaves that are not typed forms are skipped (no declared type to validate
//! against) and counted separately.
//!
//! Fail-closed: the report is total (no error path); issues come back in
//! deterministic sorted (path) order; `valid()` is true exactly when no
//! invalid leaf was found.

use crate::{
    AmiParameterTreeNodeV1, AmiParameterTreeV1, AmiParameterTypeV1, AmiParameterValueErrorV1,
    AmiParameterValueV1,
};

/// Explicit scope policy of this slice: declared-type value validity report.
pub const PARAMETER_TREE_LEAF_VALUE_VALIDITY_POLICY_V1: &str =
    "sipi.p4b-02b91.parameter-tree-leaf-value-validity-v1.declared-type-value-validity";

/// One invalid typed-form leaf with its typed error.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ParameterTreeLeafValueValidityIssueV1 {
    path: String,
    type_token: String,
    value_token: String,
    error: AmiParameterValueErrorV1,
}

impl ParameterTreeLeafValueValidityIssueV1 {
    pub fn path(&self) -> &str {
        &self.path
    }

    pub fn type_token(&self) -> &str {
        &self.type_token
    }

    pub fn value_token(&self) -> &str {
        &self.value_token
    }

    pub fn error(&self) -> &AmiParameterValueErrorV1 {
        &self.error
    }
}

/// Outcome of the value validity report over a tree's typed-form leaves.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ParameterTreeLeafValueValidityReportV1 {
    leaves_total: usize,
    typed_leaves: usize,
    valid_leaves: usize,
    invalid: Vec<ParameterTreeLeafValueValidityIssueV1>,
}

impl ParameterTreeLeafValueValidityReportV1 {
    /// Total number of leaves in the tree.
    pub fn leaves_total(&self) -> usize {
        self.leaves_total
    }

    /// Leaves that are well-formed typed forms.
    pub fn typed_leaves(&self) -> usize {
        self.typed_leaves
    }

    /// Typed-form leaves with valid values.
    pub fn valid_leaves(&self) -> usize {
        self.valid_leaves
    }

    /// Sorted (by path) invalid typed-form leaves.
    pub fn invalid(&self) -> &[ParameterTreeLeafValueValidityIssueV1] {
        &self.invalid
    }

    /// True when every typed-form leaf has a valid value.
    pub fn valid(&self) -> bool {
        self.invalid.is_empty()
    }
}

fn collect(
    node: &AmiParameterTreeNodeV1,
    prefix: &str,
    report: &mut ParameterTreeLeafValueValidityReportV1,
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
            report.leaves_total += 1;
            if value_tokens.len() == 2
                && let Some(_parameter_type) = AmiParameterTypeV1::from_token(&value_tokens[0])
            {
                report.typed_leaves += 1;
                match AmiParameterValueV1::try_new(name, &value_tokens[0], &value_tokens[1]) {
                    Ok(_) => {
                        report.valid_leaves += 1;
                    }
                    Err(error) => {
                        report.invalid.push(ParameterTreeLeafValueValidityIssueV1 {
                            path: current,
                            type_token: value_tokens[0].clone(),
                            value_token: value_tokens[1].clone(),
                            error,
                        });
                    }
                }
            }
        }
    }
}

/// Report the value validity of every typed-form leaf of a parameter tree.
pub fn check_parameter_tree_leaf_value_validity_v1(
    tree: &AmiParameterTreeV1,
) -> ParameterTreeLeafValueValidityReportV1 {
    let mut report = ParameterTreeLeafValueValidityReportV1 {
        leaves_total: 0,
        typed_leaves: 0,
        valid_leaves: 0,
        invalid: Vec::new(),
    };
    collect(tree.root_node(), "", &mut report);
    report
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
    fn all_valid_typed_leaves() {
        let t = tree("(root (gain Float 0.5) (steps Integer 7) (on Boolean True))");
        let report = check_parameter_tree_leaf_value_validity_v1(&t);
        assert_eq!(report.leaves_total(), 3);
        assert_eq!(report.typed_leaves(), 3);
        assert_eq!(report.valid_leaves(), 3);
        assert!(report.invalid().is_empty());
        assert!(report.valid());
    }

    #[test]
    fn invalid_value_is_reported_with_error() {
        let t = tree("(root (gain Float abc) (steps Integer 7))");
        let report = check_parameter_tree_leaf_value_validity_v1(&t);
        assert_eq!(report.typed_leaves(), 2);
        assert_eq!(report.valid_leaves(), 1);
        assert_eq!(report.invalid().len(), 1);
        let issue = &report.invalid()[0];
        assert_eq!(issue.path(), "root.gain");
        assert_eq!(issue.type_token(), "Float");
        assert_eq!(issue.value_token(), "abc");
        assert_eq!(issue.error(), &AmiParameterValueErrorV1::InvalidFloat);
        assert!(!report.valid());
    }

    #[test]
    fn non_typed_leaves_are_skipped() {
        let t = tree("(root (plain 5) (raw x y z) (bad Nope 1.0))");
        let report = check_parameter_tree_leaf_value_validity_v1(&t);
        assert_eq!(report.leaves_total(), 3);
        assert_eq!(report.typed_leaves(), 0);
        assert_eq!(report.valid_leaves(), 0);
        assert!(report.invalid().is_empty());
        assert!(report.valid());
    }

    #[test]
    fn nested_paths_in_report() {
        let t = tree("(root (sub (steps Integer abc)) (gain Float 0.5))");
        let report = check_parameter_tree_leaf_value_validity_v1(&t);
        assert_eq!(report.invalid().len(), 1);
        assert_eq!(report.invalid()[0].path(), "root.sub.steps");
        assert_eq!(
            report.invalid()[0].error(),
            &AmiParameterValueErrorV1::InvalidInteger
        );
    }

    #[test]
    fn mixed_valid_and_invalid() {
        let t = tree("(root (gain Float 0.5) (on Boolean nope) (channels List \"(a, b)\"))");
        let report = check_parameter_tree_leaf_value_validity_v1(&t);
        assert_eq!(report.typed_leaves(), 3);
        assert_eq!(report.valid_leaves(), 1);
        assert_eq!(report.invalid().len(), 2);
        assert_eq!(report.invalid()[0].path(), "root.channels");
        assert_eq!(
            report.invalid()[0].error(),
            &AmiParameterValueErrorV1::InvalidList
        );
        assert_eq!(report.invalid()[1].path(), "root.on");
        assert_eq!(
            report.invalid()[1].error(),
            &AmiParameterValueErrorV1::InvalidBoolean
        );
    }

    #[test]
    fn unknown_type_token_is_not_typed() {
        let t = tree("(root (weird Nope 1.0))");
        let report = check_parameter_tree_leaf_value_validity_v1(&t);
        assert_eq!(report.leaves_total(), 1);
        assert_eq!(report.typed_leaves(), 0);
        assert!(report.invalid().is_empty());
    }
}
