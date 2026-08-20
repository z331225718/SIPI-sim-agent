//! AMI parameter tree flatten core (P4B-02b50).
//!
//! Flattens an `AmiParameterTreeV1` into a canonical preorder record list:
//! every node (root, branches, leaves) becomes a `ParameterTreeNodeRecordV1`
//! carrying its canonical path, kind, name, and (for leaves) value tokens. This
//! is the export/inspection primitive for trees. Flattening is total and
//! result-based: any tree flattens.

use crate::{AmiParameterTreeV1, AmiParameterTreeNodeV1};

/// Scope policy for the parameter tree flatten core.
pub const PARAMETER_TREE_FLATTEN_POLICY_V1: &str =
    "sipi.p4b-02b50.parameter-tree-flatten-v1.preorder-record-list";

/// Node kind of a flattened record.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ParameterTreeNodeKindV1 {
    Branch,
    Leaf,
}

/// One flattened tree node record.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ParameterTreeNodeRecordV1 {
    path: Vec<String>,
    kind: ParameterTreeNodeKindV1,
    name: String,
    value_tokens: Vec<String>,
}

impl ParameterTreeNodeRecordV1 {
    pub fn path(&self) -> &[String] {
        &self.path
    }

    pub fn kind(&self) -> ParameterTreeNodeKindV1 {
        self.kind
    }

    pub fn name(&self) -> &str {
        &self.name
    }

    pub fn value_tokens(&self) -> &[String] {
        &self.value_tokens
    }
}

fn flatten_node(
    node: &AmiParameterTreeNodeV1,
    path: &mut Vec<String>,
    out: &mut Vec<ParameterTreeNodeRecordV1>,
) {
    match node {
        AmiParameterTreeNodeV1::Branch { name, children } => {
            out.push(ParameterTreeNodeRecordV1 {
                path: path.clone(),
                kind: ParameterTreeNodeKindV1::Branch,
                name: name.clone(),
                value_tokens: Vec::new(),
            });
            for child in children.values() {
                path.push(child.name().to_string());
                flatten_node(child, path, out);
                path.pop();
            }
        }
        AmiParameterTreeNodeV1::Leaf {
            name,
            value_tokens,
        } => {
            out.push(ParameterTreeNodeRecordV1 {
                path: path.clone(),
                kind: ParameterTreeNodeKindV1::Leaf,
                name: name.clone(),
                value_tokens: value_tokens.clone(),
            });
        }
    }
}

/// Flatten `tree` into canonical preorder records (root first, then children
/// byte-wise, depth first). Result-based: any tree flattens.
pub fn flatten_parameter_tree_v1(
    tree: &AmiParameterTreeV1,
) -> Vec<ParameterTreeNodeRecordV1> {
    let mut out = Vec::new();
    let mut path = vec![tree.root_name().to_string()];
    flatten_node(tree.root_node(), &mut path, &mut out);
    out
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

    fn paths(records: &[ParameterTreeNodeRecordV1]) -> Vec<Vec<String>> {
        records.iter().map(|r| r.path().to_vec()).collect()
    }

    #[test]
    fn flattens_mixed_tree_in_canonical_order() {
        let t = tree(branch(
            "root",
            vec![leaf("gain", &["Float", "0.5"]), leaf("steps", &["Integer", "7"])],
        ));
        let records = flatten_parameter_tree_v1(&t);
        assert_eq!(records.len(), 3);
        assert_eq!(
            paths(&records),
            vec![
                vec!["root".to_string()],
                vec!["root".to_string(), "gain".to_string()],
                vec!["root".to_string(), "steps".to_string()],
            ]
        );
        assert_eq!(records[0].kind(), ParameterTreeNodeKindV1::Branch);
        assert_eq!(records[1].kind(), ParameterTreeNodeKindV1::Leaf);
        assert_eq!(
            records[1].value_tokens(),
            &["Float".to_string(), "0.5".to_string()]
        );
    }

    #[test]
    fn nested_paths_are_canonical() {
        let t = tree(branch(
            "root",
            vec![branch("sub", vec![leaf("deep", &["1.0"])])],
        ));
        let records = flatten_parameter_tree_v1(&t);
        assert_eq!(
            paths(&records),
            vec![
                vec!["root".to_string()],
                vec!["root".to_string(), "sub".to_string()],
                vec![
                    "root".to_string(),
                    "sub".to_string(),
                    "deep".to_string()
                ],
            ]
        );
    }

    #[test]
    fn root_leaf_tree_flattens_to_single_record() {
        let t = tree(leaf("root", &["1"]));
        let records = flatten_parameter_tree_v1(&t);
        assert_eq!(records.len(), 1);
        assert_eq!(records[0].kind(), ParameterTreeNodeKindV1::Leaf);
        assert_eq!(records[0].path(), &["root".to_string()]);
        assert_eq!(records[0].value_tokens(), &["1".to_string()]);
    }

    #[test]
    fn branch_records_carry_empty_value_tokens() {
        let t = tree(branch(
            "root",
            vec![branch("sub", vec![]), leaf("gain", &["0.5"])],
        ));
        let records = flatten_parameter_tree_v1(&t);
        let sub = records.iter().find(|r| r.name() == "sub").expect("sub");
        assert_eq!(sub.kind(), ParameterTreeNodeKindV1::Branch);
        assert!(sub.value_tokens().is_empty());
    }
}
