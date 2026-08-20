//! AMI parameter tree token remap core (P4B-02b52).
//!
//! Remaps leaf value tokens of an `AmiParameterTreeV1` per a caller-supplied
//! substitution map (old token -> new token), returning a new tree with the
//! number of replacements. Only leaf value tokens are remapped; node names are
//! never touched. Fail-closed: an empty remap map, a remap key that does not
//! occur as a leaf token, and a remap value that is empty (invalid as a leaf
//! token downstream) are strictly rejected.

use std::collections::{BTreeMap, BTreeSet};

use crate::{AmiParameterTreeV1, AmiParameterTreeNodeV1};

/// Scope policy for the parameter tree token remap core.
pub const PARAMETER_TREE_TOKEN_REMAP_POLICY_V1: &str =
    "sipi.p4b-02b52.parameter-tree-token-remap-v1.value-token-substitution";

/// Fail-closed errors during token remap.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterTreeTokenRemapErrorV1 {
    /// The remap map is empty.
    EmptyRemap,
    /// A remap key does not occur as any leaf value token.
    MissingToken(String),
    /// A remap value is empty; an empty leaf token is invalid downstream.
    InvalidRemapValue(String),
}

/// Outcome of a successful token remap pass.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ParameterTreeTokenRemapV1 {
    replacements: usize,
    tree: AmiParameterTreeV1,
}

impl ParameterTreeTokenRemapV1 {
    pub fn replacements(&self) -> usize {
        self.replacements
    }

    pub fn tree(&self) -> &AmiParameterTreeV1 {
        &self.tree
    }
}

fn collect_leaf_tokens(node: &AmiParameterTreeNodeV1, out: &mut BTreeSet<String>) {
    match node {
        AmiParameterTreeNodeV1::Branch { children, .. } => {
            for child in children.values() {
                collect_leaf_tokens(child, out);
            }
        }
        AmiParameterTreeNodeV1::Leaf {
            value_tokens, ..
        } => {
            out.extend(value_tokens.iter().cloned());
        }
    }
}

fn remap_node(
    node: &AmiParameterTreeNodeV1,
    remap: &BTreeMap<String, String>,
    replacements: &mut usize,
) -> AmiParameterTreeNodeV1 {
    match node {
        AmiParameterTreeNodeV1::Branch { name, children } => {
            let new_children = children
                .iter()
                .map(|(key, child)| {
                    (key.clone(), remap_node(child, remap, replacements))
                })
                .collect();
            AmiParameterTreeNodeV1::Branch {
                name: name.clone(),
                children: new_children,
            }
        }
        AmiParameterTreeNodeV1::Leaf {
            name,
            value_tokens,
        } => {
            let mut new_tokens = Vec::with_capacity(value_tokens.len());
            for token in value_tokens {
                match remap.get(token) {
                    Some(new_token) => {
                        new_tokens.push(new_token.clone());
                        *replacements += 1;
                    }
                    None => new_tokens.push(token.clone()),
                }
            }
            AmiParameterTreeNodeV1::Leaf {
                name: name.clone(),
                value_tokens: new_tokens,
            }
        }
    }
}

/// Remap leaf value tokens of `tree` per `remap` (old token -> new token).
///
/// Returns the replacement count and the new tree. Node names are never
/// remapped. Fails closed on an empty remap map, a key that does not occur as a
/// leaf token, or an empty remap value.
pub fn remap_parameter_tree_tokens_v1(
    tree: &AmiParameterTreeV1,
    remap: &BTreeMap<String, String>,
) -> Result<ParameterTreeTokenRemapV1, ParameterTreeTokenRemapErrorV1> {
    if remap.is_empty() {
        return Err(ParameterTreeTokenRemapErrorV1::EmptyRemap);
    }
    let mut leaf_tokens = BTreeSet::new();
    collect_leaf_tokens(tree.root_node(), &mut leaf_tokens);
    for (old_token, new_token) in remap {
        if !leaf_tokens.contains(old_token) {
            return Err(ParameterTreeTokenRemapErrorV1::MissingToken(
                old_token.clone(),
            ));
        }
        if new_token.is_empty() {
            return Err(ParameterTreeTokenRemapErrorV1::InvalidRemapValue(
                new_token.clone(),
            ));
        }
    }
    let mut replacements = 0usize;
    let new_root = remap_node(tree.root_node(), remap, &mut replacements);
    Ok(ParameterTreeTokenRemapV1 {
        replacements,
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

    fn remap_of(pairs: &[(&str, &str)]) -> BTreeMap<String, String> {
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
    fn remaps_leaf_value_tokens() {
        let t = tree(branch(
            "root",
            vec![leaf("gain", &["Float", "0.5"]), leaf("steps", &["Integer", "7"])],
        ));
        let result = remap_parameter_tree_tokens_v1(
            &t,
            &remap_of(&[("0.5", "0.55"), ("7", "8")]),
        )
        .expect("remapped");
        assert_eq!(result.replacements(), 2);
        match find_leaf(result.tree().root_node(), "gain").expect("gain") {
            AmiParameterTreeNodeV1::Leaf { value_tokens, .. } => {
                assert_eq!(
                    value_tokens,
                    &vec!["Float".to_string(), "0.55".to_string()]
                );
            }
            AmiParameterTreeNodeV1::Branch { .. } => panic!("expected leaf"),
        }
    }

    #[test]
    fn multi_occurrence_tokens_are_all_replaced() {
        let t = tree(branch(
            "root",
            vec![leaf("x", &["1", "2"]), leaf("y", &["2", "3"])],
        ));
        let result = remap_parameter_tree_tokens_v1(
            &t,
            &remap_of(&[("2", "9")]),
        )
        .expect("remapped");
        assert_eq!(result.replacements(), 2);
        match find_leaf(result.tree().root_node(), "x").expect("x") {
            AmiParameterTreeNodeV1::Leaf { value_tokens, .. } => {
                assert_eq!(value_tokens, &vec!["1".to_string(), "9".to_string()]);
            }
            AmiParameterTreeNodeV1::Branch { .. } => panic!("expected leaf"),
        }
    }

    #[test]
    fn empty_remap_fails_closed() {
        let t = tree(branch("root", vec![leaf("gain", &["0.5"])]));
        let error = remap_parameter_tree_tokens_v1(&t, &remap_of(&[])).unwrap_err();
        assert_eq!(error, ParameterTreeTokenRemapErrorV1::EmptyRemap);
    }

    #[test]
    fn missing_token_fails_closed() {
        let t = tree(branch("root", vec![leaf("gain", &["0.5"])]));
        let error =
            remap_parameter_tree_tokens_v1(&t, &remap_of(&[("zzz", "1")])).unwrap_err();
        assert_eq!(
            error,
            ParameterTreeTokenRemapErrorV1::MissingToken("zzz".to_string())
        );
    }

    #[test]
    fn empty_remap_value_fails_closed() {
        let t = tree(branch("root", vec![leaf("gain", &["0.5"])]));
        let error =
            remap_parameter_tree_tokens_v1(&t, &remap_of(&[("0.5", "")])).unwrap_err();
        assert_eq!(
            error,
            ParameterTreeTokenRemapErrorV1::InvalidRemapValue("".to_string())
        );
    }

    #[test]
    fn node_names_are_not_remapped() {
        let t = tree(branch("root", vec![leaf("gain", &["0.5"])]));
        // "gain" appears as a NAME, not as a leaf value token; a remap key that
        // only matches a name is a MissingToken error (names are never remapped).
        let error = remap_parameter_tree_tokens_v1(&t, &remap_of(&[("gain", "x")]))
            .unwrap_err();
        assert_eq!(
            error,
            ParameterTreeTokenRemapErrorV1::MissingToken("gain".to_string())
        );
    }
}
