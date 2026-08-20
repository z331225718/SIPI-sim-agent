//! AMI parameter tree sections listing core (P4B-02b57).
//!
//! Lists the top-level children (sections) of an `AmiParameterTreeV1`: every
//! root child as a `ParameterTreeSectionV1` (name plus branch/leaf kind), in
//! byte-wise name order. This is the profile structure view (e.g. section names
//! like `Reserved_Parameters`). Fail-closed: a root-leaf tree (no sections
//! possible) is strictly rejected; an empty section list is a valid result.

use crate::{AmiParameterTreeNodeV1, AmiParameterTreeV1};

/// Scope policy for the parameter tree sections listing core.
pub const PARAMETER_TREE_SECTIONS_POLICY_V1: &str =
    "sipi.p4b-02b57.parameter-tree-sections-v1.top-level-structure";

/// Fail-closed errors during sections listing.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterTreeSectionsErrorV1 {
    /// The tree root is a leaf; a root-leaf tree has no sections.
    RootNotBranch,
}

/// Kind of one top-level section.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ParameterTreeSectionKindV1 {
    Branch,
    Leaf,
}

/// One top-level section of a parameter tree.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ParameterTreeSectionV1 {
    name: String,
    kind: ParameterTreeSectionKindV1,
}

impl ParameterTreeSectionV1 {
    pub fn name(&self) -> &str {
        &self.name
    }

    pub fn kind(&self) -> ParameterTreeSectionKindV1 {
        self.kind
    }
}

/// List the top-level sections of `tree` in byte-wise name order.
///
/// Returns an empty list for a branch root with no children; fails closed on a
/// root-leaf tree.
pub fn list_parameter_tree_sections_v1(
    tree: &AmiParameterTreeV1,
) -> Result<Vec<ParameterTreeSectionV1>, ParameterTreeSectionsErrorV1> {
    match tree.root_node() {
        AmiParameterTreeNodeV1::Branch { children, .. } => Ok(children
            .values()
            .map(|child| ParameterTreeSectionV1 {
                name: child.name().to_string(),
                kind: match child {
                    AmiParameterTreeNodeV1::Branch { .. } => ParameterTreeSectionKindV1::Branch,
                    AmiParameterTreeNodeV1::Leaf { .. } => ParameterTreeSectionKindV1::Leaf,
                },
            })
            .collect()),
        AmiParameterTreeNodeV1::Leaf { .. } => Err(ParameterTreeSectionsErrorV1::RootNotBranch),
    }
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

    #[test]
    fn lists_mixed_sections_sorted() {
        let t = tree(branch(
            "root",
            vec![
                branch("sub", vec![leaf("deep", &["1.0"])]),
                leaf("gain", &["Float", "0.5"]),
            ],
        ));
        let sections = list_parameter_tree_sections_v1(&t).expect("sections");
        assert_eq!(sections.len(), 2);
        assert_eq!(sections[0].name(), "gain");
        assert_eq!(sections[0].kind(), ParameterTreeSectionKindV1::Leaf);
        assert_eq!(sections[1].name(), "sub");
        assert_eq!(sections[1].kind(), ParameterTreeSectionKindV1::Branch);
    }

    #[test]
    fn lists_leaf_only_sections() {
        let t = tree(branch(
            "root",
            vec![
                leaf("gain", &["Float", "0.5"]),
                leaf("steps", &["Integer", "7"]),
            ],
        ));
        let sections = list_parameter_tree_sections_v1(&t).expect("sections");
        assert_eq!(sections.len(), 2);
        assert!(
            sections
                .iter()
                .all(|s| s.kind() == ParameterTreeSectionKindV1::Leaf)
        );
    }

    #[test]
    fn empty_children_is_a_valid_empty_list() {
        let t = tree(branch("root", vec![]));
        let sections = list_parameter_tree_sections_v1(&t).expect("sections");
        assert!(sections.is_empty());
    }

    #[test]
    fn root_leaf_tree_fails_closed() {
        let t = tree(leaf("root", &["1"]));
        let error = list_parameter_tree_sections_v1(&t).unwrap_err();
        assert_eq!(error, ParameterTreeSectionsErrorV1::RootNotBranch);
    }
}
