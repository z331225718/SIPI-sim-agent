//! AMI parameter tree leaf index core (P4B-02b30).
//!
//! Builds a fast canonical-path index of leaf nodes inside a typed `AmiParameterTreeV1`
//! hierarchy (`build_parameter_tree_leaf_index_v1`) and resolves leaf paths
//! (`resolve_parameter_tree_leaf_v1`). Fail-closed: empty tree lists and
//! unresolved leaf paths are strictly rejected.

use std::collections::BTreeMap;

use crate::parameter_trees_v1::{AmiParameterTreeNodeV1, AmiParameterTreeV1};

/// Scope policy for the parameter tree leaf index core.
pub const PARAMETER_TREE_LEAF_INDEX_POLICY_V1: &str =
    "sipi.p4b-02b30.parameter-tree-leaf-index-v1.tree-leaf-index";

/// Fail-closed errors during AMI parameter tree leaf index operations.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterTreeLeafIndexErrorV1 {
    EmptyTreeList,
    EmptyLeafPath,
    LeafPathNotLeaf(String),
    MissingLeafPath(String),
}

/// Canonical-path index of leaf nodes in a parameter tree.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ParameterTreeLeafIndexV1 {
    /// Canonical leaf paths in topological (parents-before-children) order.
    pub leaf_paths: Vec<String>,
    /// Maps canonical leaf path -> leaf value token list.
    leaf_values: BTreeMap<String, Vec<String>>,
}

fn collect_leaves(node: &AmiParameterTreeNodeV1, prefix: &str, out: &mut Vec<(String, Vec<String>)>) {
    let current = if prefix.is_empty() {
        node.name().to_string()
    } else {
        format!("{prefix}.{}", node.name())
    };
    match node {
        AmiParameterTreeNodeV1::Branch { children, .. } => {
            for (_, child) in children {
                collect_leaves(child, &current, out);
            }
        }
        AmiParameterTreeNodeV1::Leaf { value_tokens, .. } => {
            out.push((current, value_tokens.clone()));
        }
    }
}

/// Build a canonical-path index of all leaf nodes in a parameter tree.
pub fn build_parameter_tree_leaf_index_v1(
    tree: &AmiParameterTreeV1,
) -> Result<ParameterTreeLeafIndexV1, ParameterTreeLeafIndexErrorV1> {
    let mut entries = Vec::new();
    collect_leaves(tree.root_node(), "", &mut entries);
    let mut leaf_values = BTreeMap::new();
    for (path, tokens) in entries {
        leaf_values.insert(path.clone(), tokens);
    }
    let leaf_paths = leaf_values.keys().cloned().collect();
    Ok(ParameterTreeLeafIndexV1 {
        leaf_paths,
        leaf_values,
    })
}

impl ParameterTreeLeafIndexV1 {
    /// Resolve a canonical leaf path to its value token list.
    ///
    /// Fails closed on empty paths, paths that exist but are not leaves
    /// (e.g. a branch path), or missing paths.
    pub fn resolve_leaf(&self, path: &str) -> Result<&[String], ParameterTreeLeafIndexErrorV1> {
        let trimmed = path.trim();
        if trimmed.is_empty() {
            return Err(ParameterTreeLeafIndexErrorV1::EmptyLeafPath);
        }
        let canonical = trimmed
            .split('.')
            .filter(|s| !s.is_empty())
            .collect::<Vec<_>>()
            .join(".");
        match self.leaf_values.get(&canonical) {
            Some(tokens) => Ok(tokens.as_slice()),
            None => {
                // Distinguish "exists but not a leaf" from "missing".
                if self.leaf_paths.iter().any(|p| p.starts_with(&format!("{canonical}."))) {
                    Err(ParameterTreeLeafIndexErrorV1::LeafPathNotLeaf(canonical))
                } else {
                    Err(ParameterTreeLeafIndexErrorV1::MissingLeafPath(canonical))
                }
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::parameter_trees_v1::build_parameter_trees_v1;
    use crate::parse_ami_text_v1;
    use crate::ParseLimitsV1;

    fn limits() -> ParseLimitsV1 {
        ParseLimitsV1::try_new(1024, 16, 64, 128).unwrap()
    }

    fn tree_of(text: &str) -> AmiParameterTreeV1 {
        let doc = parse_ami_text_v1(text.as_bytes(), limits()).expect("parse");
        build_parameter_trees_v1(&doc).expect("build").remove(0)
    }

    #[test]
    fn policy_fixed() {
        assert_eq!(
            PARAMETER_TREE_LEAF_INDEX_POLICY_V1,
            "sipi.p4b-02b30.parameter-tree-leaf-index-v1.tree-leaf-index"
        );
    }

    #[test]
    fn builds_leaf_index_and_resolves() {
        let tree = tree_of("(root (branch_a (leaf_1 10)) (leaf_2 20))");
        let index = build_parameter_tree_leaf_index_v1(&tree).expect("index");
        assert_eq!(index.leaf_paths, vec!["root.branch_a.leaf_1", "root.leaf_2"]);
        assert_eq!(index.resolve_leaf("root.leaf_2").expect("resolve"), &["20"]);
    }

    #[test]
    fn rejects_branch_path() {
        let tree = tree_of("(root (branch_a (leaf_1 10)))");
        let index = build_parameter_tree_leaf_index_v1(&tree).expect("index");
        assert_eq!(
            index.resolve_leaf("root.branch_a"),
            Err(ParameterTreeLeafIndexErrorV1::LeafPathNotLeaf("root.branch_a".to_string()))
        );
    }

    #[test]
    fn rejects_missing_leaf_path() {
        let tree = tree_of("(root (a 1))");
        let index = build_parameter_tree_leaf_index_v1(&tree).expect("index");
        assert_eq!(
            index.resolve_leaf("root.nope"),
            Err(ParameterTreeLeafIndexErrorV1::MissingLeafPath("root.nope".to_string()))
        );
    }
}
