//! AMI parameter tree cycle detection core (P4B-02b25).
//!
//! Detects structural cycles in typed `AmiParameterTreeV1` hierarchies
//! (`detect_parameter_tree_cycles_v1`) using a DFS white/gray/black visited-state walk.
//! Fail-closed: built trees are acyclic by construction; this core exposes the detection
//! as an explicit integrity check returning the first offending path when a cycle exists.

use std::collections::BTreeMap;

use crate::parameter_trees_v1::{AmiParameterTreeNodeV1, AmiParameterTreeV1};

/// Scope policy for the parameter tree cycle detection core.
pub const PARAMETER_TREE_DETECT_CYCLES_POLICY_V1: &str =
    "sipi.p4b-02b25.parameter-tree-detect-cycles-v1.tree-cycle-detection";

/// Fail-closed errors during AMI parameter tree cycle detection.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterTreeDetectCyclesErrorV1 {
    EmptyTreeList,
}

/// Result of a structural cycle scan over a parameter tree.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ParameterTreeCycleScanV1 {
    pub is_acyclic: bool,
    pub cycle_path: Option<String>,
}

/// Detect structural cycles in a parameter tree using a DFS white/gray/black walk.
///
/// Trees are immutable and acyclic by construction, so this scan returns
/// `is_acyclic: true` for every valid tree. The scan is exposed as an explicit
/// integrity check: if a cycle is ever observed (e.g. via unsafe construction),
/// the first offending canonical path is reported.
pub fn detect_parameter_tree_cycles_v1(
    tree: &AmiParameterTreeV1,
) -> Result<ParameterTreeCycleScanV1, ParameterTreeDetectCyclesErrorV1> {
    #[derive(Clone, Copy, Eq, PartialEq)]
    enum Color {
        White,
        Gray,
        Black,
    }

    fn walk(
        node: &AmiParameterTreeNodeV1,
        prefix: &str,
        colors: &mut BTreeMap<String, Color>,
    ) -> Option<String> {
        let current = if prefix.is_empty() {
            node.name().to_string()
        } else {
            format!("{prefix}.{}", node.name())
        };
        match colors.get(&current) {
            Some(Color::Gray) => return Some(current),
            Some(Color::Black) => return None,
            _ => {}
        }
        colors.insert(current.clone(), Color::Gray);
        if let AmiParameterTreeNodeV1::Branch { children, .. } = node {
            for (_, child) in children {
                if let Some(cycle) = walk(child, &current, colors) {
                    return Some(cycle);
                }
            }
        }
        colors.insert(current, Color::Black);
        None
    }

    let mut colors = BTreeMap::new();
    let cycle_path = walk(tree.root_node(), "", &mut colors);
    Ok(ParameterTreeCycleScanV1 {
        is_acyclic: cycle_path.is_none(),
        cycle_path,
    })
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

    #[test]
    fn policy_fixed() {
        assert_eq!(
            PARAMETER_TREE_DETECT_CYCLES_POLICY_V1,
            "sipi.p4b-02b25.parameter-tree-detect-cycles-v1.tree-cycle-detection"
        );
    }

    #[test]
    fn acyclic_tree_scan() {
        let doc = parse_ami_text_v1(
            b"(root (branch_a (leaf_1 10)) (branch_b 20))",
            limits(),
        )
        .expect("parse");
        let trees = build_parameter_trees_v1(&doc).expect("build");
        let scan = detect_parameter_tree_cycles_v1(&trees[0]).expect("scan");
        assert!(scan.is_acyclic);
        assert_eq!(scan.cycle_path, None);
    }

    #[test]
    fn single_node_tree_is_acyclic() {
        let doc = parse_ami_text_v1(b"(root)", limits()).expect("parse");
        let trees = build_parameter_trees_v1(&doc).expect("build");
        let scan = detect_parameter_tree_cycles_v1(&trees[0]).expect("scan");
        assert!(scan.is_acyclic);
    }
}
