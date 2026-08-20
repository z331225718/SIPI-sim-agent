//! AMI parameter tree structural diff patch & application core (P4B-02b17).
//!
//! Applies atomic structural diff entries (`TreeDiffEntryV1`, P4B-02b11) to a typed `AmiParameterTreeV1`
//! hierarchy (`apply_parameter_tree_diff_patch_v1`), producing a patched tree.
//! Fail-closed: invalid target paths, node kind mismatches, or root name mismatch are strictly rejected.
use crate::parameter_tree_diff_v1::TreeDiffEntryV1;
use crate::parameter_tree_merge_v1::merge_parameter_trees_v1;
use crate::parameter_tree_pruning_v1::prune_parameter_tree_v1;
use crate::parameter_trees_v1::{AmiParameterTreeNodeV1, AmiParameterTreeV1};
/// Scope policy for the parameter tree diff patch core.
pub const PARAMETER_TREE_DIFF_PATCH_POLICY_V1: &str =
    "sipi.p4b-02b17.parameter-tree-diff-patch-v1.diff-patch-application";
/// Fail-closed errors during AMI parameter tree diff patch application.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterTreeDiffPatchErrorV1 {
    EmptyDiffList,
    InvalidPath(String),
    NodeKindMismatch(String),
}
fn apply_single_diff(
    tree: &AmiParameterTreeV1,
    diff: &TreeDiffEntryV1,
    right_tree: Option<&AmiParameterTreeV1>,
) -> Result<AmiParameterTreeV1, ParameterTreeDiffPatchErrorV1> {
    match diff {
        TreeDiffEntryV1::MissingNode { path } => {
            let segments: Vec<&str> = path.split('.').collect();
            prune_parameter_tree_v1(tree, &segments)
                .map_err(|_| ParameterTreeDiffPatchErrorV1::InvalidPath(path.clone()))
        }
        TreeDiffEntryV1::ExtraNode { path } => {
            if let Some(r_tree) = right_tree {
                let segments: Vec<&str> = path.split('.').collect();
                if let Ok(query_res) = crate::query_parameter_tree_v1(r_tree, &segments) {
                    let node_to_insert = match query_res {
                        crate::QueryResultV1::Branch(n) => n.clone(),
                        crate::QueryResultV1::Leaf(n) => n.clone(),
                    };
                    let synth_tree = path_to_tree(&segments, node_to_insert);
                    merge_parameter_trees_v1(tree, &synth_tree)
                        .map_err(|e| ParameterTreeDiffPatchErrorV1::InvalidPath(format!("{e:?}")))
                } else {
                    Err(ParameterTreeDiffPatchErrorV1::InvalidPath(path.clone()))
                }
            } else {
                Err(ParameterTreeDiffPatchErrorV1::InvalidPath(path.clone()))
            }
        }
        TreeDiffEntryV1::ValueMismatch { path, right, .. } => {
            let target_path = path.clone();
            let new_tokens = right.clone();
            crate::transform_parameter_trees_v1(std::slice::from_ref(tree), |p, node| {
                if p == target_path {
                    Some(AmiParameterTreeNodeV1::Leaf {
                        name: node.name().to_string(),
                        value_tokens: new_tokens.clone(),
                    })
                } else {
                    None
                }
            })
            .map(|mut v| v.remove(0))
            .map_err(|_| ParameterTreeDiffPatchErrorV1::InvalidPath(path.clone()))
        }
        TreeDiffEntryV1::KindMismatch { path } => Err(
            ParameterTreeDiffPatchErrorV1::NodeKindMismatch(path.clone()),
        ),
    }
}
fn path_to_tree(segments: &[&str], node: AmiParameterTreeNodeV1) -> AmiParameterTreeV1 {
    if segments.len() <= 1 {
        let nname = node.name().to_string();
        return AmiParameterTreeV1::new(nname, node);
    }
    let mut current = node;
    for &seg in segments[1..segments.len() - 1].iter().rev() {
        let mut children = std::collections::BTreeMap::new();
        children.insert(current.name().to_string(), current);
        current = AmiParameterTreeNodeV1::Branch {
            name: seg.to_string(),
            children,
        };
    }
    let mut root_children = std::collections::BTreeMap::new();
    root_children.insert(current.name().to_string(), current);
    AmiParameterTreeV1::new(
        segments[0],
        AmiParameterTreeNodeV1::Branch {
            name: segments[0].to_string(),
            children: root_children,
        },
    )
}
/// Apply a sequence of diff entries to a parameter tree.
pub fn apply_parameter_tree_diff_patch_v1(
    tree: &AmiParameterTreeV1,
    diffs: &[TreeDiffEntryV1],
) -> Result<AmiParameterTreeV1, ParameterTreeDiffPatchErrorV1> {
    if diffs.is_empty() {
        return Err(ParameterTreeDiffPatchErrorV1::EmptyDiffList);
    }
    let mut current = tree.clone();
    for diff in diffs {
        current = apply_single_diff(&current, diff, None)?;
    }
    Ok(current)
}
/// Apply a sequence of diff entries with right tree reference context.
pub fn apply_parameter_tree_diff_patch_with_context_v1(
    tree: &AmiParameterTreeV1,
    diffs: &[TreeDiffEntryV1],
    right_tree: &AmiParameterTreeV1,
) -> Result<AmiParameterTreeV1, ParameterTreeDiffPatchErrorV1> {
    if diffs.is_empty() {
        return Err(ParameterTreeDiffPatchErrorV1::EmptyDiffList);
    }
    let mut current = tree.clone();
    for diff in diffs {
        current = apply_single_diff(&current, diff, Some(right_tree))?;
    }
    Ok(current)
}
#[cfg(test)]
mod tests {
    use super::*;
    use crate::parameter_tree_diff_v1::diff_parameter_trees_v1;
    use crate::parameter_trees_v1::build_parameter_trees_v1;
    use crate::{ParseLimitsV1, parse_ami_text_v1};
    fn limits() -> ParseLimitsV1 {
        ParseLimitsV1::try_new(1024, 16, 64, 128).unwrap()
    }
    #[test]
    fn policy_fixed() {
        assert_eq!(
            PARAMETER_TREE_DIFF_PATCH_POLICY_V1,
            "sipi.p4b-02b17.parameter-tree-diff-patch-v1.diff-patch-application"
        );
    }
    #[test]
    fn applies_value_mismatch_patch() {
        let doc1 = parse_ami_text_v1(b"(root (val Float 0.5))", limits()).expect("parse");
        let doc2 = parse_ami_text_v1(b"(root (val Float 0.9))", limits()).expect("parse");
        let t1 = &build_parameter_trees_v1(&doc1).unwrap()[0];
        let t2 = &build_parameter_trees_v1(&doc2).unwrap()[0];
        let diffs = diff_parameter_trees_v1(t1, t2).unwrap();
        let patched = apply_parameter_tree_diff_patch_v1(t1, &diffs).expect("patch");
        assert_eq!(patched, *t2);
    }
    #[test]
    fn rejects_empty_diff_list() {
        let doc = parse_ami_text_v1(b"(root (a 1))", limits()).expect("parse");
        let t = &build_parameter_trees_v1(&doc).unwrap()[0];
        assert_eq!(
            apply_parameter_tree_diff_patch_v1(t, &[]),
            Err(ParameterTreeDiffPatchErrorV1::EmptyDiffList)
        );
    }
}
