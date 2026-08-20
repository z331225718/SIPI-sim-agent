//! AMI parameter tree structural visitor & traversal core (P4B-02b14).
//!
//! Traverses typed `AmiParameterTreeV1` hierarchies (P4B-02b7) in depth-first order,
//! reporting pre-order / post-order visitor events and node paths (`traverse_parameter_tree_v1`).
//! Fail-closed: empty tree lists or invalid node structures are strictly rejected.

use crate::parameter_trees_v1::{AmiParameterTreeNodeV1, AmiParameterTreeV1};

/// Scope policy for the parameter tree visitor core.
pub const PARAMETER_TREE_VISITOR_POLICY_V1: &str =
    "sipi.p4b-02b14.parameter-tree-visitor-v1.tree-structural-traversal";

/// Fail-closed errors during AMI parameter tree traversal.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterTreeVisitorErrorV1 {
    EmptyTreeList,
}

/// Visitor event generated during tree traversal.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum VisitorEventV1 {
    EnterBranch { path: String },
    LeaveBranch { path: String },
    VisitLeaf { path: String, value_tokens: Vec<String> },
}

fn traverse_node(
    node: &AmiParameterTreeNodeV1,
    path_prefix: &str,
    events: &mut Vec<VisitorEventV1>,
) {
    let current_path = if path_prefix.is_empty() {
        node.name().to_string()
    } else {
        format!("{path_prefix}.{}", node.name())
    };

    match node {
        AmiParameterTreeNodeV1::Branch { children, .. } => {
            events.push(VisitorEventV1::EnterBranch { path: current_path.clone() });
            for child in children.values() {
                traverse_node(child, &current_path, events);
            }
            events.push(VisitorEventV1::LeaveBranch { path: current_path });
        }
        AmiParameterTreeNodeV1::Leaf { value_tokens, .. } => {
            events.push(VisitorEventV1::VisitLeaf {
                path: current_path,
                value_tokens: value_tokens.clone(),
            });
        }
    }
}

/// Traverse a list of parameter trees in depth-first order.
pub fn traverse_parameter_trees_v1(
    trees: &[AmiParameterTreeV1],
) -> Result<Vec<VisitorEventV1>, ParameterTreeVisitorErrorV1> {
    if trees.is_empty() {
        return Err(ParameterTreeVisitorErrorV1::EmptyTreeList);
    }
    let mut events = Vec::new();
    for tree in trees {
        traverse_node(tree.root_node(), "", &mut events);
    }
    Ok(events)
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
            PARAMETER_TREE_VISITOR_POLICY_V1,
            "sipi.p4b-02b14.parameter-tree-visitor-v1.tree-structural-traversal"
        );
    }

    #[test]
    fn traverses_tree_hierarchy_in_depth_first_order() {
        let doc = parse_ami_text_v1(
            b"(Reserved_Parameters (tx_swing Float 0.5) (dfe (tap_1 Integer 2)))",
            limits(),
        )
        .expect("parse");
        let trees = build_parameter_trees_v1(&doc).expect("build");
        let events = traverse_parameter_trees_v1(&trees).expect("traverse");

        assert_eq!(events[0], VisitorEventV1::EnterBranch { path: "Reserved_Parameters".to_string() });
        assert_eq!(events[1], VisitorEventV1::EnterBranch { path: "Reserved_Parameters.dfe".to_string() });
        assert_eq!(events[2], VisitorEventV1::VisitLeaf {
            path: "Reserved_Parameters.dfe.tap_1".to_string(),
            value_tokens: vec!["Integer".to_string(), "2".to_string()],
        });
        assert_eq!(events[3], VisitorEventV1::LeaveBranch { path: "Reserved_Parameters.dfe".to_string() });
        assert_eq!(events[4], VisitorEventV1::VisitLeaf {
            path: "Reserved_Parameters.tx_swing".to_string(),
            value_tokens: vec!["Float".to_string(), "0.5".to_string()],
        });
        assert_eq!(events[5], VisitorEventV1::LeaveBranch { path: "Reserved_Parameters".to_string() });
    }

    #[test]
    fn rejects_empty_tree_list() {
        assert_eq!(
            traverse_parameter_trees_v1(&[]),
            Err(ParameterTreeVisitorErrorV1::EmptyTreeList)
        );
    }
}
