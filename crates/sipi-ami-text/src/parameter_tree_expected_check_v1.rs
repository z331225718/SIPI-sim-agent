//! AMI parameter tree expected-value check core (P4B-02b46).
//!
//! Checks an `AmiParameterTreeV1` against a caller-supplied expected map
//! (leaf name -> expected value tokens), the golden/regression check for trees:
//! reports expected names missing from the tree and names whose value tokens
//! differ. Extra tree leaves not in the expected map are ignored (the check is
//! one-directional: does the tree match the expectation). Fail-closed: an empty
//! expected map and a leaf name occurring at more than one depth (uncheckable
//! unambiguously) are strictly rejected.

use std::collections::BTreeMap;

use crate::{AmiParameterTreeV1, AmiParameterTreeNodeV1};

/// Scope policy for the parameter tree expected-value check core.
pub const PARAMETER_TREE_EXPECTED_CHECK_POLICY_V1: &str =
    "sipi.p4b-02b46.parameter-tree-expected-check-v1.golden-value-check";

/// Fail-closed errors during the expected-value check.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterTreeExpectedCheckErrorV1 {
    /// The expected map is empty; a check against nothing is a caller error.
    EmptyExpected,
    /// A leaf name occurs at more than one depth, so the expected tokens cannot
    /// be compared unambiguously.
    DuplicateLeaf(String),
}

/// One leaf whose value tokens differ from the expectation.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ParameterTreeValueMismatchV1 {
    name: String,
    expected: Vec<String>,
    actual: Vec<String>,
}

impl ParameterTreeValueMismatchV1 {
    pub fn name(&self) -> &str {
        &self.name
    }

    pub fn expected(&self) -> &[String] {
        &self.expected
    }

    pub fn actual(&self) -> &[String] {
        &self.actual
    }
}

/// Outcome of an expected-value check pass.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ParameterTreeExpectedCheckV1 {
    expected_count: usize,
    matched: usize,
    missing: Vec<String>,
    mismatched: Vec<ParameterTreeValueMismatchV1>,
}

impl ParameterTreeExpectedCheckV1 {
    pub fn expected_count(&self) -> usize {
        self.expected_count
    }

    pub fn matched(&self) -> usize {
        self.matched
    }

    pub fn missing(&self) -> &[String] {
        &self.missing
    }

    pub fn mismatched(&self) -> &[ParameterTreeValueMismatchV1] {
        &self.mismatched
    }
}

fn collect_leaf_tokens(
    node: &AmiParameterTreeNodeV1,
    out: &mut BTreeMap<String, Vec<String>>,
) -> Result<(), ParameterTreeExpectedCheckErrorV1> {
    match node {
        AmiParameterTreeNodeV1::Branch { children, .. } => {
            for child in children.values() {
                collect_leaf_tokens(child, out)?;
            }
            Ok(())
        }
        AmiParameterTreeNodeV1::Leaf {
            name,
            value_tokens,
        } => {
            if out.contains_key(name) {
                return Err(ParameterTreeExpectedCheckErrorV1::DuplicateLeaf(
                    name.clone(),
                ));
            }
            out.insert(name.clone(), value_tokens.clone());
            Ok(())
        }
    }
}

/// Check `tree` against `expected` (name -> expected value tokens).
///
/// Returns expected/matched counts plus sorted missing names and sorted
/// mismatches (by name). Extra tree leaves are ignored. Fails closed on an
/// empty expected map or a duplicated leaf name.
pub fn check_parameter_tree_against_expected_v1(
    tree: &AmiParameterTreeV1,
    expected: &BTreeMap<String, Vec<String>>,
) -> Result<ParameterTreeExpectedCheckV1, ParameterTreeExpectedCheckErrorV1> {
    if expected.is_empty() {
        return Err(ParameterTreeExpectedCheckErrorV1::EmptyExpected);
    }
    let mut actual_tokens = BTreeMap::new();
    collect_leaf_tokens(tree.root_node(), &mut actual_tokens)?;

    let mut matched = 0usize;
    let mut missing = Vec::new();
    let mut mismatched = Vec::new();
    for (name, expected_tokens) in expected {
        match actual_tokens.get(name) {
            None => missing.push(name.clone()),
            Some(actual) if actual == expected_tokens => matched += 1,
            Some(actual) => mismatched.push(ParameterTreeValueMismatchV1 {
                name: name.clone(),
                expected: expected_tokens.clone(),
                actual: actual.clone(),
            }),
        }
    }
    Ok(ParameterTreeExpectedCheckV1 {
        expected_count: expected.len(),
        matched,
        missing,
        mismatched,
    })
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

    fn expected_of(pairs: &[(&str, &[&str])]) -> BTreeMap<String, Vec<String>> {
        pairs
            .iter()
            .map(|(name, tokens)| {
                (
                    name.to_string(),
                    tokens.iter().map(|s| s.to_string()).collect(),
                )
            })
            .collect()
    }

    #[test]
    fn full_match_reports_matched() {
        let t = tree(branch(
            "root",
            vec![leaf("gain", &["Float", "0.5"]), leaf("steps", &["Integer", "7"])],
        ));
        let result = check_parameter_tree_against_expected_v1(
            &t,
            &expected_of(&[
                ("gain", &["Float", "0.5"]),
                ("steps", &["Integer", "7"]),
            ]),
        )
        .expect("checked");
        assert_eq!(result.expected_count(), 2);
        assert_eq!(result.matched(), 2);
        assert!(result.missing().is_empty());
        assert!(result.mismatched().is_empty());
    }

    #[test]
    fn missing_names_are_reported() {
        let t = tree(branch("root", vec![leaf("gain", &["Float", "0.5"])]));
        let result = check_parameter_tree_against_expected_v1(
            &t,
            &expected_of(&[("gain", &["Float", "0.5"]), ("steps", &["Integer", "7"])]),
        )
        .expect("checked");
        assert_eq!(result.matched(), 1);
        assert_eq!(result.missing(), &["steps".to_string()]);
    }

    #[test]
    fn token_mismatch_is_reported() {
        let t = tree(branch("root", vec![leaf("gain", &["Float", "0.5"])]));
        let result = check_parameter_tree_against_expected_v1(
            &t,
            &expected_of(&[("gain", &["Float", "9.9"])]),
        )
        .expect("checked");
        assert_eq!(result.matched(), 0);
        assert_eq!(result.mismatched().len(), 1);
        let mismatch = &result.mismatched()[0];
        assert_eq!(mismatch.name(), "gain");
        assert_eq!(mismatch.expected(), &["Float".to_string(), "9.9".to_string()]);
        assert_eq!(mismatch.actual(), &["Float".to_string(), "0.5".to_string()]);
    }

    #[test]
    fn extra_tree_leaves_are_ignored() {
        let t = tree(branch(
            "root",
            vec![leaf("gain", &["0.5"]), leaf("extra", &["1"])],
        ));
        let result = check_parameter_tree_against_expected_v1(
            &t,
            &expected_of(&[("gain", &["0.5"])]),
        )
        .expect("checked");
        assert_eq!(result.matched(), 1);
        assert_eq!(result.expected_count(), 1);
    }

    #[test]
    fn empty_expected_fails_closed() {
        let t = tree(branch("root", vec![leaf("gain", &["0.5"])]));
        let error = check_parameter_tree_against_expected_v1(&t, &expected_of(&[])).unwrap_err();
        assert_eq!(error, ParameterTreeExpectedCheckErrorV1::EmptyExpected);
    }

    #[test]
    fn duplicate_leaf_name_fails_closed() {
        let t = tree(branch(
            "root",
            vec![
                branch("sub", vec![leaf("gain", &["1.0"])]),
                leaf("gain", &["2.0"]),
            ],
        ));
        let error = check_parameter_tree_against_expected_v1(
            &t,
            &expected_of(&[("gain", &["1.0"])]),
        )
        .unwrap_err();
        assert_eq!(
            error,
            ParameterTreeExpectedCheckErrorV1::DuplicateLeaf("gain".to_string())
        );
    }
}
