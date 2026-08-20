//! AMI parameter tree multi-tree typed-form extraction core (P4B-02b42).
//!
//! Extracts typed `AmiParameterValueV1` entries from every tree of a tree list
//! (each tree in `(name Type value)` leaf form, per the P4B-02b34 rules) and
//! merges them into one name-keyed map. This is the profile-shaped consumption
//! path: an AMI profile consists of multiple parameter trees. Fail-closed: an
//! empty tree list, any per-tree typed-form violation (wrapped with the tree
//! index), and a parameter name appearing in more than one tree are strictly
//! rejected.

use std::collections::BTreeMap;

use crate::{
    AmiParameterTreeV1, AmiParameterValueV1, ParameterTreeTypedFormErrorV1,
    extract_typed_parameter_forms_v1,
};

/// Outcome of a successful multi-tree typed-form extraction pass.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ParameterTreeMultiTypedFormsV1 {
    leaves_consumed: usize,
    parameters: BTreeMap<String, AmiParameterValueV1>,
}

impl ParameterTreeMultiTypedFormsV1 {
    pub fn leaves_consumed(&self) -> usize {
        self.leaves_consumed
    }

    pub fn parameters(&self) -> &BTreeMap<String, AmiParameterValueV1> {
        &self.parameters
    }
}

/// Scope policy for the multi-tree typed-form extraction core.
pub const PARAMETER_TREE_TYPED_FORM_MULTI_POLICY_V1: &str =
    "sipi.p4b-02b42.parameter-tree-typed-form-multi-v1.multi-tree-extraction";

/// Fail-closed errors during multi-tree typed-form extraction.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterTreeMultiFormErrorV1 {
    /// The tree list is empty.
    EmptyTreeList,
    /// One tree failed its typed-form extraction, with its index.
    TreeError(usize, ParameterTreeTypedFormErrorV1),
    /// A parameter name appears in more than one tree.
    DuplicateAcrossTrees(String),
}

/// Extract typed parameter values from every tree of `trees`, merged by name.
///
/// Returns the total consumed leaves and the merged name -> value map, or fails
/// closed with the first violation (trees in list order, canonical traversal
/// order within each tree). Per-tree errors are wrapped with the tree index.
pub fn extract_typed_parameter_forms_multi_v1(
    trees: &[AmiParameterTreeV1],
) -> Result<ParameterTreeMultiTypedFormsV1, ParameterTreeMultiFormErrorV1> {
    if trees.is_empty() {
        return Err(ParameterTreeMultiFormErrorV1::EmptyTreeList);
    }
    let mut parameters = BTreeMap::new();
    let mut leaves_consumed = 0usize;
    let mut seen_names = BTreeMap::new();
    for (index, tree) in trees.iter().enumerate() {
        let extracted = extract_typed_parameter_forms_v1(tree)
            .map_err(|error| ParameterTreeMultiFormErrorV1::TreeError(index, error))?;
        leaves_consumed += extracted.leaves_consumed();
        for (name, parameter) in extracted.parameters() {
            if seen_names.contains_key(name) {
                return Err(ParameterTreeMultiFormErrorV1::DuplicateAcrossTrees(
                    name.clone(),
                ));
            }
            seen_names.insert(name.clone(), ());
            parameters.insert(name.clone(), parameter.clone());
        }
    }
    Ok(ParameterTreeMultiTypedFormsV1 {
        leaves_consumed,
        parameters,
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

    #[test]
    fn extracts_and_merges_across_trees() {
        let t1 = tree(branch("root", vec![leaf("gain", &["Float", "0.5"])]));
        let t2 = tree(branch(
            "root",
            vec![
                leaf("steps", &["Integer", "7"]),
                leaf("enabled", &["Boolean", "True"]),
            ],
        ));
        let result = extract_typed_parameter_forms_multi_v1(&[t1, t2]).expect("extracted");
        assert_eq!(result.leaves_consumed(), 3);
        assert_eq!(result.parameters().len(), 3);
        assert!(result.parameters().contains_key("gain"));
        assert!(result.parameters().contains_key("steps"));
        assert!(result.parameters().contains_key("enabled"));
    }

    #[test]
    fn duplicate_across_trees_fails_closed() {
        let t1 = tree(branch("root", vec![leaf("gain", &["Float", "0.5"])]));
        let t2 = tree(branch("root", vec![leaf("gain", &["Float", "1.0"])]));
        let error = extract_typed_parameter_forms_multi_v1(&[t1, t2]).unwrap_err();
        assert_eq!(
            error,
            ParameterTreeMultiFormErrorV1::DuplicateAcrossTrees("gain".to_string())
        );
    }

    #[test]
    fn empty_tree_list_fails_closed() {
        let error = extract_typed_parameter_forms_multi_v1(&[]).unwrap_err();
        assert_eq!(error, ParameterTreeMultiFormErrorV1::EmptyTreeList);
    }

    #[test]
    fn per_tree_error_is_wrapped_with_index() {
        let t1 = tree(branch("root", vec![leaf("gain", &["Float", "0.5"])]));
        let t2 = tree(branch("root", vec![leaf("steps", &["Real", "7"])]));
        let error = extract_typed_parameter_forms_multi_v1(&[t1, t2]).unwrap_err();
        assert_eq!(
            error,
            ParameterTreeMultiFormErrorV1::TreeError(
                1,
                ParameterTreeTypedFormErrorV1::UnknownTypeToken {
                    leaf: "steps".to_string(),
                    token: "Real".to_string(),
                }
            )
        );
    }

    #[test]
    fn nested_leaves_in_later_trees_are_extracted() {
        let t1 = tree(branch("root", vec![leaf("gain", &["Float", "0.5"])]));
        let t2 = tree(branch(
            "root",
            vec![branch("sub", vec![leaf("deep", &["Integer", "2"])])],
        ));
        let result = extract_typed_parameter_forms_multi_v1(&[t1, t2]).expect("extracted");
        assert_eq!(result.leaves_consumed(), 2);
        assert!(result.parameters().contains_key("deep"));
    }
}
