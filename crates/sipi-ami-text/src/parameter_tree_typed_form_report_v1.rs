//! AMI parameter tree typed-form conformance report core (P4B-02b58).
//!
//! Reports the typed-form conformance of EVERY leaf of an `AmiParameterTreeV1`
//! against the AMI parameter form `(name Type value)` (P4B-02b34 rules): a leaf
//! conforms when it carries exactly `[type, value]` tokens with a known type
//! token and a value valid per the P4B-02b1 `AmiParameterValueV1::try_new`
//! rules. Unlike extraction (P4B-02b34, fail-fast on the first violation), this
//! is the full inspection report: every non-conforming leaf is listed with its
//! violation reason, sorted by leaf name. Result-based: any tree can be
//! checked.

use std::collections::BTreeMap;

use crate::{
    AmiParameterTreeV1, AmiParameterTreeNodeV1, AmiParameterTypeV1,
    AmiParameterValueErrorV1, AmiParameterValueV1,
};

/// Scope policy for the typed-form conformance report core.
pub const PARAMETER_TREE_TYPED_FORM_CONFORMANCE_POLICY_V1: &str =
    "sipi.p4b-02b58.parameter-tree-typed-form-conformance-v1.full-report";

/// Violation reason of one non-conforming leaf.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum TypedFormViolationV1 {
    /// The leaf carries no value tokens.
    EmptyValueTokens,
    /// The leaf carries a single value token.
    NotTypedForm,
    /// The leaf carries more than two value tokens.
    MultiTokenForm { token_count: usize },
    /// The leaf's first value token is not a known type token.
    UnknownTypeToken { token: String },
    /// The leaf's value token violates its declared type rule.
    InvalidValue { error: AmiParameterValueErrorV1 },
    /// The leaf name is not a valid parameter name per the P4B-02b1 rule.
    InvalidParameterName,
}

/// One per-leaf conformance report entry.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ParameterTreeTypedFormReportEntryV1 {
    leaf: String,
    conforming: bool,
    violation: Option<TypedFormViolationV1>,
}

impl ParameterTreeTypedFormReportEntryV1 {
    pub fn leaf(&self) -> &str {
        &self.leaf
    }

    pub fn is_conforming(&self) -> bool {
        self.conforming
    }

    pub fn violation(&self) -> Option<&TypedFormViolationV1> {
        self.violation.as_ref()
    }
}

/// Full typed-form conformance report of a tree.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ParameterTreeTypedFormReportV1 {
    conforming_count: usize,
    non_conforming_count: usize,
    entries: Vec<ParameterTreeTypedFormReportEntryV1>,
}

impl ParameterTreeTypedFormReportV1 {
    pub fn conforming_count(&self) -> usize {
        self.conforming_count
    }

    pub fn non_conforming_count(&self) -> usize {
        self.non_conforming_count
    }

    pub fn entries(&self) -> &[ParameterTreeTypedFormReportEntryV1] {
        &self.entries
    }
}

fn classify_leaf(
    name: &str,
    value_tokens: &[String],
) -> (bool, Option<TypedFormViolationV1>) {
    if value_tokens.is_empty() {
        return (false, Some(TypedFormViolationV1::EmptyValueTokens));
    }
    if value_tokens.len() == 1 {
        return (false, Some(TypedFormViolationV1::NotTypedForm));
    }
    if value_tokens.len() > 2 {
        return (
            false,
            Some(TypedFormViolationV1::MultiTokenForm {
                token_count: value_tokens.len(),
            }),
        );
    }
    let type_token = &value_tokens[0];
    let value_token = &value_tokens[1];
    let Some(parameter_type) = AmiParameterTypeV1::from_token(type_token) else {
        return (
            false,
            Some(TypedFormViolationV1::UnknownTypeToken {
                token: type_token.clone(),
            }),
        );
    };
    match AmiParameterValueV1::try_new(name, parameter_type.token(), value_token) {
        Ok(_) => (true, None),
        Err(error) => {
            let violation = match error {
                AmiParameterValueErrorV1::EmptyName
                | AmiParameterValueErrorV1::UnknownTypeToken => {
                    unreachable!(
                        "structurally impossible: tree names are non-empty and the                          type token was just parsed"
                    )
                }
                AmiParameterValueErrorV1::InvalidName => {
                    TypedFormViolationV1::InvalidParameterName
                }
                other => TypedFormViolationV1::InvalidValue { error: other },
            };
            (false, Some(violation))
        }
    }
}

fn walk(
    node: &AmiParameterTreeNodeV1,
    entries: &mut BTreeMap<String, ParameterTreeTypedFormReportEntryV1>,
) {
    match node {
        AmiParameterTreeNodeV1::Branch { children, .. } => {
            for child in children.values() {
                walk(child, entries);
            }
        }
        AmiParameterTreeNodeV1::Leaf {
            name,
            value_tokens,
        } => {
            let (conforming, violation) = classify_leaf(name, value_tokens);
            entries.insert(
                name.clone(),
                ParameterTreeTypedFormReportEntryV1 {
                    leaf: name.clone(),
                    conforming,
                    violation,
                },
            );
        }
    }
}

/// Report the typed-form conformance of every leaf of `tree`.
///
/// Entries are sorted by leaf name; a duplicated leaf name at different depths
/// keeps the last occurrence (the report is name-addressed). Result-based.
pub fn check_parameter_tree_typed_form_conformance_v1(
    tree: &AmiParameterTreeV1,
) -> ParameterTreeTypedFormReportV1 {
    let mut entries = BTreeMap::new();
    walk(tree.root_node(), &mut entries);
    let conforming_count = entries
        .values()
        .filter(|entry| entry.is_conforming())
        .count();
    let non_conforming_count = entries.len() - conforming_count;
    ParameterTreeTypedFormReportV1 {
        conforming_count,
        non_conforming_count,
        entries: entries.into_values().collect(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::AmiParameterTreeNodeV1;

    fn leaf(name: &str, tokens: &[&str]) -> AmiParameterTreeNodeV1 {
        AmiParameterTreeNodeV1::Leaf {
            name: name.to_string(),
            value_tokens: tokens.iter().map(|s| s.to_string()).collect(),
        }
    }

    fn branch(name: &str, children: Vec<AmiParameterTreeNodeV1>) -> AmiParameterTreeNodeV1 {
        AmiParameterTreeNodeV1::Branch {
            name: name.to_string(),
            children: children
                .into_iter()
                .map(|c| (c.name().to_string(), c))
                .collect(),
        }
    }

    fn tree(node: AmiParameterTreeNodeV1) -> AmiParameterTreeV1 {
        AmiParameterTreeV1::new("root", node)
    }

    #[test]
    fn all_conforming_leaves_are_reported() {
        let t = tree(branch(
            "root",
            vec![leaf("gain", &["Float", "0.5"]), leaf("steps", &["Integer", "7"])],
        ));
        let report = check_parameter_tree_typed_form_conformance_v1(&t);
        assert_eq!(report.conforming_count(), 2);
        assert_eq!(report.non_conforming_count(), 0);
        assert!(report.entries().iter().all(|e| e.is_conforming()));
    }

    #[test]
    fn mixed_violations_are_all_reported_sorted() {
        let t = tree(branch(
            "root",
            vec![
                leaf("a", &["Real", "1"]),
                leaf("b", &["1", "2", "3"]),
                leaf("c", &["1"]),
                leaf("d", &["Float", "x1"]),
            ],
        ));
        let report = check_parameter_tree_typed_form_conformance_v1(&t);
        assert_eq!(report.conforming_count(), 0);
        assert_eq!(report.non_conforming_count(), 4);
        let names: Vec<&str> = report.entries().iter().map(|e| e.leaf()).collect();
        assert_eq!(names, vec!["a", "b", "c", "d"]);
        assert_eq!(
            report.entries()[0].violation(),
            Some(&TypedFormViolationV1::UnknownTypeToken {
                token: "Real".to_string()
            })
        );
        assert_eq!(
            report.entries()[1].violation(),
            Some(&TypedFormViolationV1::MultiTokenForm { token_count: 3 })
        );
        assert_eq!(
            report.entries()[2].violation(),
            Some(&TypedFormViolationV1::NotTypedForm)
        );
        assert_eq!(
            report.entries()[3].violation(),
            Some(&TypedFormViolationV1::InvalidValue {
                error: AmiParameterValueErrorV1::InvalidFloat
            })
        );
    }

    #[test]
    fn empty_leaf_is_empty_value_tokens() {
        let t = tree(branch("root", vec![leaf("a", &[])]));
        let report = check_parameter_tree_typed_form_conformance_v1(&t);
        assert_eq!(report.non_conforming_count(), 1);
        assert_eq!(
            report.entries()[0].violation(),
            Some(&TypedFormViolationV1::EmptyValueTokens)
        );
    }

    #[test]
    fn invalid_parameter_name_is_reported() {
        let t = tree(branch("root", vec![leaf("my-gain", &["Float", "0.5"])]));
        let report = check_parameter_tree_typed_form_conformance_v1(&t);
        assert_eq!(report.non_conforming_count(), 1);
        assert_eq!(
            report.entries()[0].violation(),
            Some(&TypedFormViolationV1::InvalidParameterName)
        );
    }

    #[test]
    fn nested_conforming_leaves_count() {
        let t = tree(branch(
            "root",
            vec![
                branch("sub", vec![leaf("deep", &["Float", "1.0"])]),
                leaf("gain", &["Float", "0.5"]),
            ],
        ));
        let report = check_parameter_tree_typed_form_conformance_v1(&t);
        assert_eq!(report.conforming_count(), 2);
        assert_eq!(report.non_conforming_count(), 0);
    }
}
