//! AMI parameter tree leaf search core (P4B-02b40).
//!
//! Searches an `AmiParameterTreeV1` for leaves whose value tokens contain an
//! exact search token, returning every matching canonical path
//! (`[root_name, ..., leaf_name]`) in canonical traversal order (branch
//! children byte-wise, depth first). Zero matches is a valid result. Fail-closed:
//! an empty search token is strictly rejected.

use crate::{AmiParameterTreeNodeV1, AmiParameterTreeV1};

/// Scope policy for the parameter tree leaf search core.
pub const PARAMETER_TREE_LEAF_SEARCH_POLICY_V1: &str =
    "sipi.p4b-02b40.parameter-tree-leaf-search-v1.token-search";

/// Fail-closed errors during parameter tree leaf search.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterTreeSearchErrorV1 {
    /// The search token is empty; no leaf token can be empty, so an empty
    /// search is always a caller error.
    EmptyToken,
}

fn search_node(
    node: &AmiParameterTreeNodeV1,
    path: &mut Vec<String>,
    token: &str,
    out: &mut Vec<Vec<String>>,
) {
    match node {
        AmiParameterTreeNodeV1::Branch { children, .. } => {
            for child in children.values() {
                path.push(child.name().to_string());
                search_node(child, path, token, out);
                path.pop();
            }
        }
        AmiParameterTreeNodeV1::Leaf { value_tokens, .. } => {
            if value_tokens.iter().any(|t| t == token) {
                out.push(path.clone());
            }
        }
    }
}

/// Find every canonical path of a leaf whose value tokens contain `token`.
///
/// Returns paths in canonical traversal order (branch children byte-wise, depth
/// first), each `[root_name, ..., leaf_name]`. Zero matches returns an empty
/// vector (a valid result). Fails closed on an empty search token.
pub fn find_parameter_tree_leaves_by_token_v1(
    tree: &AmiParameterTreeV1,
    token: &str,
) -> Result<Vec<Vec<String>>, ParameterTreeSearchErrorV1> {
    if token.is_empty() {
        return Err(ParameterTreeSearchErrorV1::EmptyToken);
    }
    let mut out = Vec::new();
    let mut path = vec![tree.root_name().to_string()];
    search_node(tree.root_node(), &mut path, token, &mut out);
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

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
    fn finds_single_matching_leaf() {
        let t = tree(branch(
            "root",
            vec![
                leaf("gain", &["Float", "0.5"]),
                leaf("steps", &["Integer", "7"]),
                leaf("enabled", &["Boolean", "True"]),
            ],
        ));
        let paths = find_parameter_tree_leaves_by_token_v1(&t, "0.5").expect("searched");
        assert_eq!(paths, vec![vec!["root".to_string(), "gain".to_string()]]);
    }

    #[test]
    fn finds_multiple_matches_in_canonical_order() {
        let t = tree(branch(
            "root",
            vec![leaf("x", &["1", "2"]), leaf("y", &["2", "3"])],
        ));
        let paths = find_parameter_tree_leaves_by_token_v1(&t, "2").expect("searched");
        assert_eq!(
            paths,
            vec![
                vec!["root".to_string(), "x".to_string()],
                vec!["root".to_string(), "y".to_string()],
            ]
        );
    }

    #[test]
    fn finds_nested_leaf() {
        let t = tree(branch(
            "root",
            vec![branch("sub", vec![leaf("deep", &["1.0"])])],
        ));
        let paths = find_parameter_tree_leaves_by_token_v1(&t, "1.0").expect("searched");
        assert_eq!(
            paths,
            vec![vec![
                "root".to_string(),
                "sub".to_string(),
                "deep".to_string()
            ]]
        );
    }

    #[test]
    fn no_match_returns_empty_result() {
        let t = tree(branch(
            "root",
            vec![leaf("gain", &["0.5"]), leaf("steps", &["7"])],
        ));
        let paths = find_parameter_tree_leaves_by_token_v1(&t, "zzz").expect("searched");
        assert!(paths.is_empty());
    }

    #[test]
    fn empty_token_fails_closed() {
        let t = tree(branch("root", vec![leaf("gain", &["0.5"])]));
        let error = find_parameter_tree_leaves_by_token_v1(&t, "").unwrap_err();
        assert_eq!(error, ParameterTreeSearchErrorV1::EmptyToken);
    }
}
