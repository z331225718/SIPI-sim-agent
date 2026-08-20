//! AMI parameter tree topological path ordering core (P4B-02b28).
//!
//! Produces a deterministic topological ordering of canonical node paths inside a typed
//! `AmiParameterTreeV1` hierarchy (`toposort_parameter_tree_paths_v1`), parents before children,
//! siblings in sorted key order. Fail-closed: empty tree lists are strictly rejected.

use crate::parameter_trees_v1::{AmiParameterTreeNodeV1, AmiParameterTreeV1};

/// Scope policy for the parameter tree toposort core.
pub const PARAMETER_TREE_TOPOSORT_POLICY_V1: &str =
    "sipi.p4b-02b28.parameter-tree-toposort-v1.tree-path-toposort";

/// Fail-closed errors during AMI parameter tree topological path ordering.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterTreeToposortErrorV1 {
    EmptyTreeList,
}

/// Collect canonical node paths in topological (parents-before-children) order.
fn collect_paths(node: &AmiParameterTreeNodeV1, prefix: &str, out: &mut Vec<String>) {
    let current = if prefix.is_empty() {
        node.name().to_string()
    } else {
        format!("{prefix}.{}", node.name())
    };
    out.push(current.clone());
    if let AmiParameterTreeNodeV1::Branch { children, .. } = node {
        for child in children.values() {
            collect_paths(child, &current, out);
        }
    }
}

/// Produce a deterministic topological ordering of canonical node paths in a parameter tree.
///
/// Parents always precede their children; siblings are visited in sorted key order
/// (BTreeMap iteration order). Returns the ordered path list.
pub fn toposort_parameter_tree_paths_v1(
    tree: &AmiParameterTreeV1,
) -> Result<Vec<String>, ParameterTreeToposortErrorV1> {
    let mut paths = Vec::new();
    collect_paths(tree.root_node(), "", &mut paths);
    Ok(paths)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::ParseLimitsV1;
    use crate::parameter_trees_v1::build_parameter_trees_v1;
    use crate::parse_ami_text_v1;

    fn limits() -> ParseLimitsV1 {
        ParseLimitsV1::try_new(1024, 16, 64, 128).unwrap()
    }

    #[test]
    fn policy_fixed() {
        assert_eq!(
            PARAMETER_TREE_TOPOSORT_POLICY_V1,
            "sipi.p4b-02b28.parameter-tree-toposort-v1.tree-path-toposort"
        );
    }

    #[test]
    fn parents_precede_children() {
        let doc = parse_ami_text_v1(
            b"(root (branch_a (leaf_1 10)) (branch_b (leaf_2 20)))",
            limits(),
        )
        .expect("parse");
        let trees = build_parameter_trees_v1(&doc).expect("build");
        let paths = toposort_parameter_tree_paths_v1(&trees[0]).expect("toposort");
        let expected = vec![
            "root".to_string(),
            "root.branch_a".to_string(),
            "root.branch_a.leaf_1".to_string(),
            "root.branch_b".to_string(),
            "root.branch_b.leaf_2".to_string(),
        ];
        assert_eq!(paths, expected);
    }

    #[test]
    fn single_node_paths() {
        let doc = parse_ami_text_v1(b"(root)", limits()).expect("parse");
        let trees = build_parameter_trees_v1(&doc).expect("build");
        let paths = toposort_parameter_tree_paths_v1(&trees[0]).expect("toposort");
        assert_eq!(paths, vec!["root".to_string()]);
    }
}
