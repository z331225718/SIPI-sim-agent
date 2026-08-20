//! AMI parameter tree predicate filtering core (P4B-02b18).
//!
//! Filters typed `AmiParameterTreeV1` hierarchies (P4B-02b7) by applying predicate closures
//! over node path and node properties (`filter_parameter_trees_v1`).
//! Fail-closed: empty tree lists or empty result tree list are strictly rejected.

use std::collections::BTreeMap;

use crate::parameter_trees_v1::{AmiParameterTreeNodeV1, AmiParameterTreeV1};

/// Scope policy for the parameter tree filter core.
pub const PARAMETER_TREE_FILTER_POLICY_V1: &str =
    "sipi.p4b-02b18.parameter-tree-filter-v1.tree-predicate-filter";

/// Fail-closed errors during AMI parameter tree predicate filtering.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterTreeFilterErrorV1 {
    EmptyTreeList,
    EmptyFilteredResult,
}

fn filter_node<F>(
    node: &AmiParameterTreeNodeV1,
    path_prefix: &str,
    predicate: &F,
) -> Option<AmiParameterTreeNodeV1>
where
    F: Fn(&str, &AmiParameterTreeNodeV1) -> bool,
{
    let current_path = if path_prefix.is_empty() {
        node.name().to_string()
    } else {
        format!("{path_prefix}.{}", node.name())
    };

    // If predicate explicitly rejects node, prune node and sub-tree
    if !predicate(&current_path, node) {
        return None;
    }

    match node {
        AmiParameterTreeNodeV1::Branch { name, children } => {
            let mut filtered_children = BTreeMap::new();
            for (key, child) in children {
                if let Some(filtered_child) = filter_node(child, &current_path, predicate) {
                    filtered_children.insert(key.clone(), filtered_child);
                }
            }
            Some(AmiParameterTreeNodeV1::Branch {
                name: name.clone(),
                children: filtered_children,
            })
        }
        AmiParameterTreeNodeV1::Leaf { .. } => Some(node.clone()),
    }
}

/// Filter a list of parameter trees using a predicate closure over path and node.
pub fn filter_parameter_trees_v1<F>(
    trees: &[AmiParameterTreeV1],
    predicate: F,
) -> Result<Vec<AmiParameterTreeV1>, ParameterTreeFilterErrorV1>
where
    F: Fn(&str, &AmiParameterTreeNodeV1) -> bool,
{
    if trees.is_empty() {
        return Err(ParameterTreeFilterErrorV1::EmptyTreeList);
    }

    let mut filtered_trees = Vec::new();
    for tree in trees {
        if let Some(filtered_root) = filter_node(tree.root_node(), "", &predicate) {
            let rname = filtered_root.name().to_string();
            filtered_trees.push(AmiParameterTreeV1::new(rname, filtered_root));
        }
    }

    if filtered_trees.is_empty() {
        return Err(ParameterTreeFilterErrorV1::EmptyFilteredResult);
    }
    Ok(filtered_trees)
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
            PARAMETER_TREE_FILTER_POLICY_V1,
            "sipi.p4b-02b18.parameter-tree-filter-v1.tree-predicate-filter"
        );
    }

    #[test]
    fn filters_tree_by_path_predicate() {
        let doc = parse_ami_text_v1(
            b"(Reserved_Parameters (tx_swing Float 0.5) (dfe (tap_1 Integer 2)))",
            limits(),
        )
        .expect("parse");
        let trees = build_parameter_trees_v1(&doc).expect("build");

        // Filter out tx_swing leaf
        let filtered = filter_parameter_trees_v1(&trees, |path, _| {
            path != "Reserved_Parameters.tx_swing"
        })
        .expect("filter");

        assert_eq!(filtered.len(), 1);
        if let AmiParameterTreeNodeV1::Branch { children, .. } = filtered[0].root_node() {
            assert_eq!(children.len(), 1);
            assert!(!children.contains_key("tx_swing"));
            assert!(children.contains_key("dfe"));
        } else {
            panic!("expected branch");
        }
    }

    #[test]
    fn rejects_empty_tree_list() {
        assert_eq!(
            filter_parameter_trees_v1(&[], |_, _| true),
            Err(ParameterTreeFilterErrorV1::EmptyTreeList)
        );
    }

    #[test]
    fn rejects_empty_filtered_result() {
        let doc = parse_ami_text_v1(b"(root (a 1))", limits()).expect("parse");
        let trees = build_parameter_trees_v1(&doc).expect("build");
        assert_eq!(
            filter_parameter_trees_v1(&trees, |_, _| false),
            Err(ParameterTreeFilterErrorV1::EmptyFilteredResult)
        );
    }
}
