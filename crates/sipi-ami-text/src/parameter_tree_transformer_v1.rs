//! AMI parameter tree structural transformation core (P4B-02b15).
//!
//! Transforms typed `AmiParameterTreeV1` hierarchies (P4B-02b7) by applying closure/mapping functions
//! over Branch and Leaf nodes (`transform_parameter_tree_v1`).
//! Fail-closed: empty tree lists or invalid node structures are strictly rejected.

use std::collections::BTreeMap;

use crate::parameter_trees_v1::{AmiParameterTreeNodeV1, AmiParameterTreeV1};

/// Scope policy for the parameter tree transformer core.
pub const PARAMETER_TREE_TRANSFORMER_POLICY_V1: &str =
    "sipi.p4b-02b15.parameter-tree-transformer-v1.tree-structural-transform";

/// Fail-closed errors during AMI parameter tree transformation.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterTreeTransformerErrorV1 {
    EmptyTreeList,
    InvalidNodeName(String),
}

fn is_valid_identifier(name: &str) -> bool {
    let trimmed = name.trim();
    !trimmed.is_empty()
        && trimmed.is_ascii()
        && trimmed
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-' || c == '.')
}

fn transform_node<F>(
    node: &AmiParameterTreeNodeV1,
    path_prefix: &str,
    transform_fn: &F,
) -> Result<AmiParameterTreeNodeV1, ParameterTreeTransformerErrorV1>
where
    F: Fn(&str, &AmiParameterTreeNodeV1) -> Option<AmiParameterTreeNodeV1>,
{
    let current_path = if path_prefix.is_empty() {
        node.name().to_string()
    } else {
        format!("{path_prefix}.{}", node.name())
    };

    // Apply custom transformation if closure returns Some(node)
    if let Some(custom) = transform_fn(&current_path, node) {
        if !is_valid_identifier(custom.name()) {
            return Err(ParameterTreeTransformerErrorV1::InvalidNodeName(
                custom.name().to_string(),
            ));
        }
        return Ok(custom);
    }

    match node {
        AmiParameterTreeNodeV1::Branch { name, children } => {
            let mut new_children = BTreeMap::new();
            for (key, child) in children {
                let transformed_child = transform_node(child, &current_path, transform_fn)?;
                new_children.insert(key.clone(), transformed_child);
            }
            Ok(AmiParameterTreeNodeV1::Branch {
                name: name.clone(),
                children: new_children,
            })
        }
        AmiParameterTreeNodeV1::Leaf { .. } => Ok(node.clone()),
    }
}

/// Transform a list of parameter trees using a node transformation closure.
pub fn transform_parameter_trees_v1<F>(
    trees: &[AmiParameterTreeV1],
    transform_fn: F,
) -> Result<Vec<AmiParameterTreeV1>, ParameterTreeTransformerErrorV1>
where
    F: Fn(&str, &AmiParameterTreeNodeV1) -> Option<AmiParameterTreeNodeV1>,
{
    if trees.is_empty() {
        return Err(ParameterTreeTransformerErrorV1::EmptyTreeList);
    }
    let mut transformed_trees = Vec::new();
    for tree in trees {
        let root = transform_node(tree.root_node(), "", &transform_fn)?;
        let rname = root.name().to_string();
        transformed_trees.push(AmiParameterTreeV1::new(rname, root));
    }
    Ok(transformed_trees)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::parameter_trees_v1::build_parameter_trees_v1;
    use crate::{ParseLimitsV1, parse_ami_text_v1};

    fn limits() -> ParseLimitsV1 {
        ParseLimitsV1::try_new(1024, 16, 64, 128).unwrap()
    }

    #[test]
    fn policy_fixed() {
        assert_eq!(
            PARAMETER_TREE_TRANSFORMER_POLICY_V1,
            "sipi.p4b-02b15.parameter-tree-transformer-v1.tree-structural-transform"
        );
    }

    #[test]
    fn transforms_leaf_values_and_preserves_tree_structure() {
        let doc = parse_ami_text_v1(
            b"(Reserved_Parameters (tx_swing Float 0.5) (dfe (tap_1 Integer 2)))",
            limits(),
        )
        .expect("parse");
        let trees = build_parameter_trees_v1(&doc).expect("build");

        // Transform tx_swing leaf value from 0.5 to 1.0
        let transformed = transform_parameter_trees_v1(&trees, |path, _node| {
            if path == "Reserved_Parameters.tx_swing" {
                Some(AmiParameterTreeNodeV1::Leaf {
                    name: "tx_swing".to_string(),
                    value_tokens: vec!["Float".to_string(), "1.0".to_string()],
                })
            } else {
                None
            }
        })
        .expect("transform");

        assert_eq!(transformed.len(), 1);
        if let AmiParameterTreeNodeV1::Branch { children, .. } = transformed[0].root_node() {
            if let AmiParameterTreeNodeV1::Leaf { value_tokens, .. } = &children["tx_swing"] {
                assert_eq!(value_tokens, &["Float", "1.0"]);
            } else {
                panic!("expected leaf");
            }
        } else {
            panic!("expected branch");
        }
    }

    #[test]
    fn rejects_empty_tree_list() {
        assert_eq!(
            transform_parameter_trees_v1(&[], |_, _| None),
            Err(ParameterTreeTransformerErrorV1::EmptyTreeList)
        );
    }
}
