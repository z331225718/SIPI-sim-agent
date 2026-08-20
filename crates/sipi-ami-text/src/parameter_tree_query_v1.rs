//! AMI parameter tree query core (P4B-02b8).
//!
//! Performs deterministic path-based queries (`query_parameter_tree_v1`)
//! over typed `AmiParameterTreeV1` hierarchies (P4B-02b7).
//! Fail-closed: empty path queries, empty node names, or path non-matches
//! are strictly rejected.

use crate::parameter_trees_v1::{AmiParameterTreeNodeV1, AmiParameterTreeV1};

/// Scope policy for the parameter tree query core.
pub const PARAMETER_TREE_QUERY_POLICY_V1: &str =
    "sipi.p4b-02b8.parameter-tree-query-v1.path-query-tree";

/// Fail-closed errors during AMI parameter tree query.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterTreeQueryErrorV1 {
    EmptyPath,
    RootMismatch,
    PathNotFound(String),
}

/// Query result node reference wrapper.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum QueryResultV1<'a> {
    Branch(&'a AmiParameterTreeNodeV1),
    Leaf(&'a AmiParameterTreeNodeV1),
}

fn query_node<'a>(
    node: &'a AmiParameterTreeNodeV1,
    segments: &[&str],
) -> Result<QueryResultV1<'a>, ParameterTreeQueryErrorV1> {
    if segments.is_empty() {
        return match node {
            AmiParameterTreeNodeV1::Branch { .. } => Ok(QueryResultV1::Branch(node)),
            AmiParameterTreeNodeV1::Leaf { .. } => Ok(QueryResultV1::Leaf(node)),
        };
    }
    match node {
        AmiParameterTreeNodeV1::Branch { children, .. } => {
            let next_segment = segments[0];
            let child = children
                .get(next_segment)
                .ok_or_else(|| ParameterTreeQueryErrorV1::PathNotFound(next_segment.to_string()))?;
            query_node(child, &segments[1..])
        }
        AmiParameterTreeNodeV1::Leaf { name, .. } => {
            Err(ParameterTreeQueryErrorV1::PathNotFound(name.clone()))
        }
    }
}

/// Query a parameter tree by path segments starting with the root node name.
pub fn query_parameter_tree_v1<'a>(
    tree: &'a AmiParameterTreeV1,
    path_segments: &[&str],
) -> Result<QueryResultV1<'a>, ParameterTreeQueryErrorV1> {
    if path_segments.is_empty() {
        return Err(ParameterTreeQueryErrorV1::EmptyPath);
    }
    if path_segments[0] != tree.root_name() {
        return Err(ParameterTreeQueryErrorV1::RootMismatch);
    }
    query_node(tree.root_node(), &path_segments[1..])
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
            PARAMETER_TREE_QUERY_POLICY_V1,
            "sipi.p4b-02b8.parameter-tree-query-v1.path-query-tree"
        );
    }

    #[test]
    fn queries_existing_branch_and_leaf() {
        let doc = parse_ami_text_v1(
            b"(Reserved_Parameters (tx_swing Float 0.5) (dfe (tap_1 Integer 2)))",
            limits(),
        )
        .expect("parse");
        let trees = build_parameter_trees_v1(&doc).expect("build");

        let res_root =
            query_parameter_tree_v1(&trees[0], &["Reserved_Parameters"]).expect("query root");
        assert!(matches!(res_root, QueryResultV1::Branch(_)));

        let res_leaf = query_parameter_tree_v1(&trees[0], &["Reserved_Parameters", "tx_swing"])
            .expect("query leaf");
        assert!(matches!(res_leaf, QueryResultV1::Leaf(_)));

        let res_nested =
            query_parameter_tree_v1(&trees[0], &["Reserved_Parameters", "dfe", "tap_1"])
                .expect("query nested");
        assert!(matches!(res_nested, QueryResultV1::Leaf(_)));
    }

    #[test]
    fn rejects_empty_path() {
        let doc = parse_ami_text_v1(b"(root (a 1))", limits()).expect("parse");
        let trees = build_parameter_trees_v1(&doc).expect("build");
        assert_eq!(
            query_parameter_tree_v1(&trees[0], &[]),
            Err(ParameterTreeQueryErrorV1::EmptyPath)
        );
    }

    #[test]
    fn rejects_root_mismatch() {
        let doc = parse_ami_text_v1(b"(root (a 1))", limits()).expect("parse");
        let trees = build_parameter_trees_v1(&doc).expect("build");
        assert_eq!(
            query_parameter_tree_v1(&trees[0], &["other_root"]),
            Err(ParameterTreeQueryErrorV1::RootMismatch)
        );
    }

    #[test]
    fn rejects_path_not_found() {
        let doc = parse_ami_text_v1(b"(root (a 1))", limits()).expect("parse");
        let trees = build_parameter_trees_v1(&doc).expect("build");
        assert_eq!(
            query_parameter_tree_v1(&trees[0], &["root", "nonexistent"]),
            Err(ParameterTreeQueryErrorV1::PathNotFound(
                "nonexistent".to_string()
            ))
        );
    }
}
