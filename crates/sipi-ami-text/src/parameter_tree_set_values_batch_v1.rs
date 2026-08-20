//! AMI parameter tree batch value set core (P4B-02b53).
//!
//! Sets the value tokens of every leaf addressed by name per a caller-supplied
//! updates map (leaf name -> single value token), each token validated against
//! the leaf's declared type (caller-supplied type map) via the exact P4B-02b1
//! `AmiParameterValueV1::try_new` rules. Returns a new tree and the number of
//! leaf occurrences updated. Fail-closed: empty updates, a name with no leaf,
//! a name matching leaves at multiple depths (ambiguous), a missing type, an
//! invalid value, and an invalid leaf name are strictly rejected.

use std::collections::BTreeMap;

use crate::{
    AmiParameterTreeV1, AmiParameterTreeNodeV1, AmiParameterTypeV1,
    AmiParameterValueErrorV1, AmiParameterValueV1,
};

/// Scope policy for the parameter tree batch value set core.
pub const PARAMETER_TREE_BATCH_VALUE_SET_POLICY_V1: &str =
    "sipi.p4b-02b53.parameter-tree-batch-value-set-v1.name-addressed-batch-set";

/// Fail-closed errors during batch value set.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterTreeBatchValueSetErrorV1 {
    /// The updates map is empty.
    EmptyUpdates,
    /// An update name matches no leaf in the tree.
    MissingLeaf(String),
    /// An update name matches leaves at more than one depth.
    AmbiguousName(String),
    /// An updated leaf has no declared type in the caller-supplied type map.
    MissingType(String),
    /// An update value token violates the leaf's declared type rule.
    InvalidValue {
        leaf: String,
        error: AmiParameterValueErrorV1,
    },
    /// An updated leaf name is not a valid parameter name per the P4B-02b1
    /// name rule.
    InvalidLeafName(String),
}

/// Outcome of a successful batch value set pass.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ParameterTreeValueSetBatchV1 {
    updated: usize,
    tree: AmiParameterTreeV1,
}

impl ParameterTreeValueSetBatchV1 {
    pub fn updated(&self) -> usize {
        self.updated
    }

    pub fn tree(&self) -> &AmiParameterTreeV1 {
        &self.tree
    }
}

fn count_leaf_occurrences(
    node: &AmiParameterTreeNodeV1,
    counts: &mut BTreeMap<String, usize>,
) {
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

fn apply_updates(
    node: &AmiParameterTreeNodeV1,
    updates: &BTreeMap<String, String>,
    updated: &mut usize,
) -> AmiParameterTreeNodeV1 {
    match node {
        AmiParameterTreeNodeV1::Branch { name, children } => {
            let new_children = children
                .iter()
                .map(|(key, child)| {
                    (key.clone(), apply_updates(child, updates, updated))
                })
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
            if let Some(new_token) = updates.get(name) {
                *updated += 1;
                AmiParameterTreeNodeV1::Leaf {
                    name: name.clone(),
                    value_tokens: vec![new_token.clone()],
                }
            } else {
                node.clone()
            }
        }
    }
}

/// Set the value tokens of every leaf addressed by name per `updates`.
///
/// Each update value token is validated against the leaf's declared type
/// (type map keyed by leaf name) before any mutation. Returns the number of
/// leaf occurrences updated and the new tree. Fails closed on the first
/// violating condition.
pub fn set_parameter_tree_leaf_values_v1(
    tree: &AmiParameterTreeV1,
    type_map: &BTreeMap<String, AmiParameterTypeV1>,
    updates: &BTreeMap<String, String>,
) -> Result<ParameterTreeValueSetBatchV1, ParameterTreeBatchValueSetErrorV1> {
    if updates.is_empty() {
        return Err(ParameterTreeBatchValueSetErrorV1::EmptyUpdates);
    }
    let mut counts = BTreeMap::new();
    count_leaf_occurrences(tree.root_node(), &mut counts);
    for (name, token) in updates {
        match counts.get(name) {
            None => {
                return Err(ParameterTreeBatchValueSetErrorV1::MissingLeaf(
                    name.clone(),
                ));
            }
            Some(&count) if count > 1 => {
                return Err(ParameterTreeBatchValueSetErrorV1::AmbiguousName(
                    name.clone(),
                ));
            }
            Some(_) => {}
        }
        let parameter_type = type_map
            .get(name)
            .copied()
            .ok_or_else(|| ParameterTreeBatchValueSetErrorV1::MissingType(name.clone()))?;
        AmiParameterValueV1::try_new(name, parameter_type.token(), token).map_err(|error| {
            match error {
                AmiParameterValueErrorV1::EmptyName
                | AmiParameterValueErrorV1::UnknownTypeToken => {
                    unreachable!(
                        "structurally impossible: tree names are non-empty and the                          type comes from AmiParameterTypeV1"
                    )
                }
                AmiParameterValueErrorV1::InvalidName => {
                    ParameterTreeBatchValueSetErrorV1::InvalidLeafName(name.clone())
                }
                other => ParameterTreeBatchValueSetErrorV1::InvalidValue {
                    leaf: name.clone(),
                    error: other,
                },
            }
        })?;
    }
    let mut updated = 0usize;
    let new_root = apply_updates(tree.root_node(), updates, &mut updated);
    Ok(ParameterTreeValueSetBatchV1 {
        updated,
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

    fn type_map(pairs: &[(&str, AmiParameterTypeV1)]) -> BTreeMap<String, AmiParameterTypeV1> {
        pairs
            .iter()
            .map(|(name, ty)| (name.to_string(), *ty))
            .collect()
    }

    fn updates_of(pairs: &[(&str, &str)]) -> BTreeMap<String, String> {
        pairs
            .iter()
            .map(|(a, b)| (a.to_string(), b.to_string()))
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
    fn batch_updates_leaf_values() {
        let t = tree(branch(
            "root",
            vec![leaf("gain", &["Float", "0.5"]), leaf("steps", &["Integer", "7"])],
        ));
        let types = type_map(&[
            ("gain", AmiParameterTypeV1::Float),
            ("steps", AmiParameterTypeV1::Integer),
        ]);
        let result = set_parameter_tree_leaf_values_v1(
            &t,
            &types,
            &updates_of(&[("gain", "1.25"), ("steps", "8")]),
        )
        .expect("updated");
        assert_eq!(result.updated(), 2);
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
    fn ambiguous_name_fails_closed() {
        let t = tree(branch(
            "root",
            vec![
                branch("sub", vec![leaf("gain", &["Float", "1.0"])]),
                leaf("gain", &["Float", "2.0"]),
            ],
        ));
        let types = type_map(&[("gain", AmiParameterTypeV1::Float)]);
        let error = set_parameter_tree_leaf_values_v1(
            &t,
            &types,
            &updates_of(&[("gain", "3.0")]),
        )
        .unwrap_err();
        assert_eq!(
            error,
            ParameterTreeBatchValueSetErrorV1::AmbiguousName("gain".to_string())
        );
    }

    #[test]
    fn missing_leaf_fails_closed() {
        let t = tree(branch("root", vec![leaf("gain", &["0.5"])]));
        let types = type_map(&[("gain", AmiParameterTypeV1::Float)]);
        let error = set_parameter_tree_leaf_values_v1(
            &t,
            &types,
            &updates_of(&[("nope", "1.0")]),
        )
        .unwrap_err();
        assert_eq!(
            error,
            ParameterTreeBatchValueSetErrorV1::MissingLeaf("nope".to_string())
        );
    }

    #[test]
    fn empty_updates_fails_closed() {
        let t = tree(branch("root", vec![leaf("gain", &["0.5"])]));
        let types = type_map(&[("gain", AmiParameterTypeV1::Float)]);
        let error =
            set_parameter_tree_leaf_values_v1(&t, &types, &updates_of(&[])).unwrap_err();
        assert_eq!(error, ParameterTreeBatchValueSetErrorV1::EmptyUpdates);
    }

    #[test]
    fn missing_type_fails_closed() {
        let t = tree(branch("root", vec![leaf("gain", &["0.5"])]));
        let types = type_map(&[]);
        let error = set_parameter_tree_leaf_values_v1(
            &t,
            &types,
            &updates_of(&[("gain", "1.0")]),
        )
        .unwrap_err();
        assert_eq!(
            error,
            ParameterTreeBatchValueSetErrorV1::MissingType("gain".to_string())
        );
    }

    #[test]
    fn invalid_value_fails_closed() {
        let t = tree(branch("root", vec![leaf("gain", &["0.5"])]));
        let types = type_map(&[("gain", AmiParameterTypeV1::Float)]);
        let error = set_parameter_tree_leaf_values_v1(
            &t,
            &types,
            &updates_of(&[("gain", "x1")]),
        )
        .unwrap_err();
        assert_eq!(
            error,
            ParameterTreeBatchValueSetErrorV1::InvalidValue {
                leaf: "gain".to_string(),
                error: AmiParameterValueErrorV1::InvalidFloat,
            }
        );
    }
}
