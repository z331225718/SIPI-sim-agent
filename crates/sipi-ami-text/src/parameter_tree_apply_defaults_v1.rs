//! AMI parameter tree defaults application core (P4B-02b38).
//!
//! Applies a caller-supplied defaults map (leaf name -> value tokens) to an
//! `AmiParameterTreeV1`: every default whose name is not already a leaf anywhere
//! in the tree is added as a new root-level leaf with the default tokens; a
//! default whose name already exists is skipped (defaults fill only missing
//! parameters). Fail-closed: an empty defaults map and a default with no value
//! tokens are strictly rejected.

use std::collections::{BTreeMap, BTreeSet};

use crate::{AmiParameterTreeV1, AmiParameterTreeNodeV1};

/// Scope policy for the parameter tree defaults application core.
pub const PARAMETER_TREE_APPLY_DEFAULTS_POLICY_V1: &str =
    "sipi.p4b-02b38.parameter-tree-apply-defaults-v1.default-fill-missing";

/// Fail-closed errors during parameter tree defaults application.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterTreeDefaultsErrorV1 {
    /// The defaults map is empty.
    EmptyDefaults,
    /// A default carries no value tokens; a leaf with no tokens is invalid.
    EmptyDefaultTokens(String),
    /// The tree root is a leaf; defaults cannot be attached (built trees
    /// always have a branch root).
    RootNotBranch,
}

/// Outcome of a successful defaults application pass.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ParameterTreeDefaultsAppliedV1 {
    added: usize,
    skipped: usize,
    tree: AmiParameterTreeV1,
}

impl ParameterTreeDefaultsAppliedV1 {
    pub fn added(&self) -> usize {
        self.added
    }

    pub fn skipped(&self) -> usize {
        self.skipped
    }

    pub fn tree(&self) -> &AmiParameterTreeV1 {
        &self.tree
    }
}

fn collect_leaf_names(node: &AmiParameterTreeNodeV1, out: &mut BTreeSet<String>) {
    match node {
        AmiParameterTreeNodeV1::Branch { children, .. } => {
            for child in children.values() {
                collect_leaf_names(child, out);
            }
        }
        AmiParameterTreeNodeV1::Leaf { name, .. } => {
            out.insert(name.clone());
        }
    }
}

/// Apply `defaults` to `tree`: add missing leaves at root level, skip names
/// that already exist anywhere in the tree.
///
/// Returns the added/skipped counts and the resulting tree (root children in
/// byte-wise name order). Fails closed on an empty defaults map or a default
/// with no value tokens.
pub fn apply_parameter_tree_defaults_v1(
    tree: &AmiParameterTreeV1,
    defaults: &BTreeMap<String, Vec<String>>,
) -> Result<ParameterTreeDefaultsAppliedV1, ParameterTreeDefaultsErrorV1> {
    if defaults.is_empty() {
        return Err(ParameterTreeDefaultsErrorV1::EmptyDefaults);
    }
    let mut leaf_names = BTreeSet::new();
    collect_leaf_names(tree.root_node(), &mut leaf_names);

    let mut added = 0usize;
    let mut skipped = 0usize;
    let mut extra_children = BTreeMap::new();
    for (name, tokens) in defaults {
        if leaf_names.contains(name) {
            skipped += 1;
            continue;
        }
        if tokens.is_empty() {
            return Err(ParameterTreeDefaultsErrorV1::EmptyDefaultTokens(
                name.clone(),
            ));
        }
        extra_children.insert(
            name.clone(),
            AmiParameterTreeNodeV1::Leaf {
                name: name.clone(),
                value_tokens: tokens.clone(),
            },
        );
        added += 1;
    }

    let new_root = match tree.root_node() {
        AmiParameterTreeNodeV1::Branch { name, children } => {
            let mut merged = children.clone();
            for (key, child) in extra_children {
                merged.insert(key, child);
            }
            AmiParameterTreeNodeV1::Branch {
                name: name.clone(),
                children: merged,
            }
        }
        AmiParameterTreeNodeV1::Leaf { .. } => {
            // Defaults cannot be attached to a root-leaf tree; fail closed.
            return Err(ParameterTreeDefaultsErrorV1::RootNotBranch);
        }
    };
    Ok(ParameterTreeDefaultsAppliedV1 {
        added,
        skipped,
        tree: AmiParameterTreeV1::new(tree.root_name(), new_root),
    })
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

    fn defaults_of(pairs: &[(&str, &[&str])]) -> BTreeMap<String, Vec<String>> {
        pairs
            .iter()
            .map(|(name, tokens)| {
                (
                    name.to_string(),
                    tokens.iter().map(|s| s.to_string()).collect(),
                )
            })
            .collect()
    }

    #[test]
    fn fills_missing_leaves_at_root() {
        let t = tree(branch("root", vec![leaf("gain", &["Float", "0.5"])]));
        let result = apply_parameter_tree_defaults_v1(
            &t,
            &defaults_of(&[("steps", &["Integer", "7"])]),
        )
        .expect("applied");
        assert_eq!(result.added(), 1);
        assert_eq!(result.skipped(), 0);
        let root = result.tree().root_node();
        match root {
            AmiParameterTreeNodeV1::Branch { children, .. } => {
                assert_eq!(children.len(), 2);
                let steps = children.get("steps").expect("steps");
                match steps {
                    AmiParameterTreeNodeV1::Leaf { value_tokens, .. } => {
                        assert_eq!(
                            value_tokens,
                            &vec!["Integer".to_string(), "7".to_string()]
                        );
                    }
                    AmiParameterTreeNodeV1::Branch { .. } => panic!("expected leaf"),
                }
            }
            AmiParameterTreeNodeV1::Leaf { .. } => panic!("expected branch root"),
        }
    }

    #[test]
    fn existing_leaf_is_skipped() {
        let t = tree(branch("root", vec![leaf("gain", &["Float", "0.5"])]));
        let result = apply_parameter_tree_defaults_v1(
            &t,
            &defaults_of(&[("gain", &["Float", "9.9"])]),
        )
        .expect("applied");
        assert_eq!(result.added(), 0);
        assert_eq!(result.skipped(), 1);
        assert_eq!(result.tree(), &t);
    }

    #[test]
    fn deeper_existing_leaf_is_skipped() {
        let t = tree(branch(
            "root",
            vec![branch("sub", vec![leaf("gain", &["1.0"])])],
        ));
        let result = apply_parameter_tree_defaults_v1(
            &t,
            &defaults_of(&[("gain", &["Float", "9.9"])]),
        )
        .expect("applied");
        assert_eq!(result.added(), 0);
        assert_eq!(result.skipped(), 1);
        assert_eq!(result.tree(), &t);
    }

    #[test]
    fn empty_defaults_fail_closed() {
        let t = tree(branch("root", vec![leaf("gain", &["0.5"])]));
        let error = apply_parameter_tree_defaults_v1(&t, &defaults_of(&[])).unwrap_err();
        assert_eq!(error, ParameterTreeDefaultsErrorV1::EmptyDefaults);
    }

    #[test]
    fn empty_default_tokens_fail_closed() {
        let t = tree(branch("root", vec![leaf("gain", &["0.5"])]));
        let error = apply_parameter_tree_defaults_v1(
            &t,
            &defaults_of(&[("steps", &[])]),
        )
        .unwrap_err();
        assert_eq!(
            error,
            ParameterTreeDefaultsErrorV1::EmptyDefaultTokens("steps".to_string())
        );
    }

    #[test]
    fn root_leaf_tree_fails_closed() {
        let t = tree(leaf("gain", &["0.5"]));
        let error = apply_parameter_tree_defaults_v1(
            &t,
            &defaults_of(&[("steps", &["Integer", "7"])]),
        )
        .unwrap_err();
        assert_eq!(error, ParameterTreeDefaultsErrorV1::RootNotBranch);
    }

    #[test]
    fn mixed_add_and_skip_counts() {
        let t = tree(branch(
            "root",
            vec![leaf("gain", &["Float", "0.5"]), leaf("mode", &["String", "fast"])],
        ));
        let result = apply_parameter_tree_defaults_v1(
            &t,
            &defaults_of(&[
                ("gain", &["Float", "9.9"]),
                ("steps", &["Integer", "7"]),
                ("enabled", &["Boolean", "True"]),
            ]),
        )
        .expect("applied");
        assert_eq!(result.added(), 2);
        assert_eq!(result.skipped(), 1);
        let root = result.tree().root_node();
        match root {
            AmiParameterTreeNodeV1::Branch { children, .. } => {
                assert_eq!(children.len(), 4);
                assert!(children.contains_key("enabled"));
                assert!(children.contains_key("steps"));
            }
            AmiParameterTreeNodeV1::Leaf { .. } => panic!("expected branch root"),
        }
    }
}
