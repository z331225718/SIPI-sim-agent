//! AMI parameter tree profile apply core (P4B-02b69).
//!
//! Applies an assembled parameter profile (leaf name -> `AmiParameterValueV1`,
//! e.g. produced by P4B-02b44) onto an `AmiParameterTreeV1`: every leaf
//! addressed by a profile name gets its value tokens replaced by the profile
//! value token. The profile values are already validated, so no re-validation
//! or type map is needed — this is the final consumption composition (assemble
//! -> apply). Fail-closed: an empty profile, a profile name with no leaf, and a
//! profile name matching leaves at multiple depths are strictly rejected.

use std::collections::BTreeMap;

use crate::{AmiParameterTreeNodeV1, AmiParameterTreeV1, AmiParameterValueV1};

/// Scope policy for the profile apply core.
pub const PARAMETER_TREE_PROFILE_APPLY_POLICY_V1: &str =
    "sipi.p4b-02b69.parameter-tree-profile-apply-v1.profile-to-tree-apply";

/// Fail-closed errors during profile application.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterTreeProfileApplyErrorV1 {
    /// The profile is empty.
    EmptyProfile,
    /// A profile name matches no leaf in the tree.
    MissingLeaf(String),
    /// A profile name matches leaves at more than one depth.
    AmbiguousName(String),
}

/// Outcome of a successful profile application pass.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ParameterTreeProfileApplyV1 {
    applied: usize,
    tree: AmiParameterTreeV1,
}

impl ParameterTreeProfileApplyV1 {
    pub fn applied(&self) -> usize {
        self.applied
    }

    pub fn tree(&self) -> &AmiParameterTreeV1 {
        &self.tree
    }
}

fn count_leaf_occurrences(node: &AmiParameterTreeNodeV1, counts: &mut BTreeMap<String, usize>) {
    match node {
        AmiParameterTreeNodeV1::Branch { children, .. } => {
            for child in children.values() {
                count_leaf_occurrences(child, counts);
            }
        }
        AmiParameterTreeNodeV1::Leaf { name, .. } => {
            *counts.entry(name.clone()).or_insert(0) += 1;
        }
    }
}

fn apply_profile(
    node: &AmiParameterTreeNodeV1,
    profile: &BTreeMap<String, AmiParameterValueV1>,
    applied: &mut usize,
) -> AmiParameterTreeNodeV1 {
    match node {
        AmiParameterTreeNodeV1::Branch { name, children } => {
            let new_children = children
                .iter()
                .map(|(key, child)| (key.clone(), apply_profile(child, profile, applied)))
                .collect();
            AmiParameterTreeNodeV1::Branch {
                name: name.clone(),
                children: new_children,
            }
        }
        AmiParameterTreeNodeV1::Leaf {
            name,
            value_tokens: _,
        } => {
            if let Some(parameter) = profile.get(name) {
                *applied += 1;
                AmiParameterTreeNodeV1::Leaf {
                    name: name.clone(),
                    value_tokens: vec![parameter.value_token().to_string()],
                }
            } else {
                node.clone()
            }
        }
    }
}

/// Apply `profile` onto `tree`: matching leaves get the profile value token.
///
/// Returns the number of leaves updated and the new tree. Fails closed on an
/// empty profile, a profile name with no leaf, or an ambiguous (multi-depth)
/// name.
pub fn apply_parameter_profile_to_tree_v1(
    tree: &AmiParameterTreeV1,
    profile: &BTreeMap<String, AmiParameterValueV1>,
) -> Result<ParameterTreeProfileApplyV1, ParameterTreeProfileApplyErrorV1> {
    if profile.is_empty() {
        return Err(ParameterTreeProfileApplyErrorV1::EmptyProfile);
    }
    let mut counts = BTreeMap::new();
    count_leaf_occurrences(tree.root_node(), &mut counts);
    for name in profile.keys() {
        match counts.get(name) {
            None => {
                return Err(ParameterTreeProfileApplyErrorV1::MissingLeaf(name.clone()));
            }
            Some(&count) if count > 1 => {
                return Err(ParameterTreeProfileApplyErrorV1::AmbiguousName(
                    name.clone(),
                ));
            }
            Some(_) => {}
        }
    }
    let mut applied = 0usize;
    let new_root = apply_profile(tree.root_node(), profile, &mut applied);
    Ok(ParameterTreeProfileApplyV1 {
        applied,
        tree: AmiParameterTreeV1::new(tree.root_name(), new_root),
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

    fn parameter(name: &str, type_token: &str, value: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value).expect("valid parameter")
    }

    fn profile_of(pairs: &[(&str, &str, &str)]) -> BTreeMap<String, AmiParameterValueV1> {
        pairs
            .iter()
            .map(|(name, type_token, value)| (name.to_string(), parameter(name, type_token, value)))
            .collect()
    }

    fn find_leaf<'a>(
        node: &'a AmiParameterTreeNodeV1,
        name: &str,
    ) -> Option<&'a AmiParameterTreeNodeV1> {
        match node {
            AmiParameterTreeNodeV1::Leaf { name: n, .. } if n == name => Some(node),
            AmiParameterTreeNodeV1::Leaf { .. } => None,
            AmiParameterTreeNodeV1::Branch { children, .. } => {
                children.values().find_map(|c| find_leaf(c, name))
            }
        }
    }

    #[test]
    fn applies_profile_values_to_leaves() {
        let t = tree(branch(
            "root",
            vec![
                leaf("gain", &["Float", "0.5"]),
                leaf("steps", &["Integer", "7"]),
            ],
        ));
        let profile = profile_of(&[("gain", "Float", "1.25"), ("steps", "Integer", "8")]);
        let result = apply_parameter_profile_to_tree_v1(&t, &profile).expect("applied");
        assert_eq!(result.applied(), 2);
        match find_leaf(result.tree().root_node(), "gain").expect("gain") {
            AmiParameterTreeNodeV1::Leaf { value_tokens, .. } => {
                assert_eq!(value_tokens, &vec!["1.25".to_string()]);
            }
            AmiParameterTreeNodeV1::Branch { .. } => panic!("expected leaf"),
        }
        match find_leaf(result.tree().root_node(), "steps").expect("steps") {
            AmiParameterTreeNodeV1::Leaf { value_tokens, .. } => {
                assert_eq!(value_tokens, &vec!["8".to_string()]);
            }
            AmiParameterTreeNodeV1::Branch { .. } => panic!("expected leaf"),
        }
    }

    #[test]
    fn unlisted_leaves_are_unchanged() {
        let t = tree(branch(
            "root",
            vec![
                leaf("gain", &["Float", "0.5"]),
                leaf("steps", &["Integer", "7"]),
            ],
        ));
        let profile = profile_of(&[("gain", "Float", "1.25")]);
        let result = apply_parameter_profile_to_tree_v1(&t, &profile).expect("applied");
        assert_eq!(result.applied(), 1);
        match find_leaf(result.tree().root_node(), "steps").expect("steps") {
            AmiParameterTreeNodeV1::Leaf { value_tokens, .. } => {
                assert_eq!(value_tokens, &vec!["Integer".to_string(), "7".to_string()]);
            }
            AmiParameterTreeNodeV1::Branch { .. } => panic!("expected leaf"),
        }
    }

    #[test]
    fn missing_leaf_fails_closed() {
        let t = tree(branch("root", vec![leaf("gain", &["0.5"])]));
        let profile = profile_of(&[("nope", "Float", "1.0")]);
        let error = apply_parameter_profile_to_tree_v1(&t, &profile).unwrap_err();
        assert_eq!(
            error,
            ParameterTreeProfileApplyErrorV1::MissingLeaf("nope".to_string())
        );
    }

    #[test]
    fn ambiguous_name_fails_closed() {
        let t = tree(branch(
            "root",
            vec![
                branch("sub", vec![leaf("gain", &["1.0"])]),
                leaf("gain", &["2.0"]),
            ],
        ));
        let profile = profile_of(&[("gain", "Float", "3.0")]);
        let error = apply_parameter_profile_to_tree_v1(&t, &profile).unwrap_err();
        assert_eq!(
            error,
            ParameterTreeProfileApplyErrorV1::AmbiguousName("gain".to_string())
        );
    }

    #[test]
    fn empty_profile_fails_closed() {
        let t = tree(branch("root", vec![leaf("gain", &["0.5"])]));
        let error = apply_parameter_profile_to_tree_v1(&t, &profile_of(&[])).unwrap_err();
        assert_eq!(error, ParameterTreeProfileApplyErrorV1::EmptyProfile);
    }
}
