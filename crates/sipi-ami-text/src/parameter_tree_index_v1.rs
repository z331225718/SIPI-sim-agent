//! AMI parameter tree fast leaf path index core (P4B-02b16).
//!
//! Builds flat path-indexed lookup tables (`AmiParameterTreeIndexV1`) mapping full parameter paths
//! to value tokens from typed `AmiParameterTreeV1` hierarchies (P4B-02b7).
//! Fail-closed: empty tree lists or duplicate leaf paths are strictly rejected.

use std::collections::BTreeMap;

use crate::parameter_trees_v1::{AmiParameterTreeNodeV1, AmiParameterTreeV1};

/// Scope policy for the parameter tree index core.
pub const PARAMETER_TREE_INDEX_POLICY_V1: &str =
    "sipi.p4b-02b16.parameter-tree-index-v1.flat-path-index";

/// Fail-closed errors during AMI parameter tree indexing.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterTreeIndexErrorV1 {
    EmptyTreeList,
    DuplicateLeafPath(String),
}

/// A flat path-indexed lookup table for AMI parameter tree leaves.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct AmiParameterTreeIndexV1 {
    leaf_index: BTreeMap<String, Vec<String>>,
}

impl AmiParameterTreeIndexV1 {
    pub fn leaf_index(&self) -> &BTreeMap<String, Vec<String>> {
        &self.leaf_index
    }

    pub fn get_leaf_tokens(&self, path: &str) -> Option<&[String]> {
        self.leaf_index.get(path).map(|v| v.as_slice())
    }

    pub fn contains_path(&self, path: &str) -> bool {
        self.leaf_index.contains_key(path)
    }

    pub fn len(&self) -> usize {
        self.leaf_index.len()
    }

    pub fn is_empty(&self) -> bool {
        self.leaf_index.is_empty()
    }
}

fn index_node(
    node: &AmiParameterTreeNodeV1,
    path_prefix: &str,
    index: &mut BTreeMap<String, Vec<String>>,
) -> Result<(), ParameterTreeIndexErrorV1> {
    let current_path = if path_prefix.is_empty() {
        node.name().to_string()
    } else {
        format!("{path_prefix}.{}", node.name())
    };

    match node {
        AmiParameterTreeNodeV1::Branch { children, .. } => {
            for child in children.values() {
                index_node(child, &current_path, index)?;
            }
        }
        AmiParameterTreeNodeV1::Leaf { value_tokens, .. } => {
            if index
                .insert(current_path.clone(), value_tokens.clone())
                .is_some()
            {
                return Err(ParameterTreeIndexErrorV1::DuplicateLeafPath(current_path));
            }
        }
    }
    Ok(())
}

/// Build a flat path index from a list of parameter trees.
pub fn build_parameter_tree_index_v1(
    trees: &[AmiParameterTreeV1],
) -> Result<AmiParameterTreeIndexV1, ParameterTreeIndexErrorV1> {
    if trees.is_empty() {
        return Err(ParameterTreeIndexErrorV1::EmptyTreeList);
    }
    let mut index = BTreeMap::new();
    for tree in trees {
        index_node(tree.root_node(), "", &mut index)?;
    }
    Ok(AmiParameterTreeIndexV1 { leaf_index: index })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::parameter_trees_v1::build_parameter_trees_v1;
    use crate::{parse_ami_text_v1, ParseLimitsV1};

    fn limits() -> ParseLimitsV1 {
        ParseLimitsV1::try_new(1024, 16, 64, 128).unwrap()
    }

    #[test]
    fn policy_fixed() {
        assert_eq!(
            PARAMETER_TREE_INDEX_POLICY_V1,
            "sipi.p4b-02b16.parameter-tree-index-v1.flat-path-index"
        );
    }

    #[test]
    fn indexes_tree_leaves() {
        let doc = parse_ami_text_v1(
            b"(Reserved_Parameters (tx_swing Float 0.5) (dfe (tap_1 Integer 2)))",
            limits(),
        )
        .expect("parse");
        let trees = build_parameter_trees_v1(&doc).expect("build");
        let idx = build_parameter_tree_index_v1(&trees).expect("index");

        assert_eq!(idx.len(), 2);
        assert!(idx.contains_path("Reserved_Parameters.tx_swing"));
        assert_eq!(
            idx.get_leaf_tokens("Reserved_Parameters.tx_swing"),
            Some(["Float".to_string(), "0.5".to_string()].as_slice())
        );
        assert_eq!(
            idx.get_leaf_tokens("Reserved_Parameters.dfe.tap_1"),
            Some(["Integer".to_string(), "2".to_string()].as_slice())
        );
    }

    #[test]
    fn rejects_empty_tree_list() {
        assert_eq!(
            build_parameter_tree_index_v1(&[]),
            Err(ParameterTreeIndexErrorV1::EmptyTreeList)
        );
    }
}
