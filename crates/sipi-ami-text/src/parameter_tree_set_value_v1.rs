//! AMI parameter tree leaf value set core (P4B-02b39).
//!
//! Sets the value tokens of one leaf of an `AmiParameterTreeV1` addressed by a
//! canonical path (`[root_name, ..., leaf_name]`), replacing them with a single
//! new value token validated against the leaf's declared type (caller-supplied
//! type map keyed by leaf name) via the exact P4B-02b1 `AmiParameterValueV1::try_new`
//! rules. Returns a new tree; the source tree is untouched. Fail-closed: empty
//! path, root mismatch, path not found, branch target, missing type, invalid
//! value, and invalid leaf name are strictly rejected.

use std::collections::BTreeMap;

use crate::{
    AmiParameterTreeNodeV1, AmiParameterTreeV1, AmiParameterTypeV1, AmiParameterValueErrorV1,
    AmiParameterValueV1,
};

/// Scope policy for the parameter tree leaf value set core.
pub const PARAMETER_TREE_LEAF_VALUE_SET_POLICY_V1: &str =
    "sipi.p4b-02b39.parameter-tree-leaf-value-set-v1.typed-value-set";

/// Fail-closed errors while setting a leaf value of a parameter tree.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterTreeValueSetErrorV1 {
    /// The path is empty.
    EmptyPath,
    /// The first path segment does not match the tree root name.
    RootMismatch,
    /// A path segment does not resolve to a child.
    PathNotFound(String),
    /// The path resolves to a branch; only leaves carry value tokens.
    TargetNotLeaf { name: String },
    /// The leaf has no declared type in the caller-supplied type map.
    MissingType(String),
    /// The new value token violates the leaf's declared type rule.
    InvalidValue {
        leaf: String,
        error: AmiParameterValueErrorV1,
    },
    /// The leaf name is not a valid parameter name per the P4B-02b1 rule.
    InvalidLeafName(String),
}

fn set_node(
    node: &AmiParameterTreeNodeV1,
    segments: &[&str],
    type_map: &BTreeMap<String, AmiParameterTypeV1>,
    value_token: &str,
) -> Result<AmiParameterTreeNodeV1, ParameterTreeValueSetErrorV1> {
    match node {
        AmiParameterTreeNodeV1::Branch { name, children } => {
            let target = segments[0];
            let child = children
                .get(target)
                .ok_or_else(|| ParameterTreeValueSetErrorV1::PathNotFound(target.to_string()))?;
            let new_child = if segments.len() == 1 {
                // The target child is the leaf to modify.
                match child {
                    AmiParameterTreeNodeV1::Leaf {
                        name: leaf_name,
                        value_tokens: _,
                    } => {
                        let parameter_type = type_map.get(leaf_name).copied().ok_or_else(|| {
                            ParameterTreeValueSetErrorV1::MissingType(leaf_name.clone())
                        })?;
                        AmiParameterValueV1::try_new(leaf_name, parameter_type.token(), value_token)
                            .map_err(|error| match error {
                                AmiParameterValueErrorV1::EmptyName
                                | AmiParameterValueErrorV1::UnknownTypeToken => {
                                    unreachable!(
                                        "structurally impossible: tree names are non-empty and                                          the type comes from AmiParameterTypeV1"
                                    )
                                }
                                AmiParameterValueErrorV1::InvalidName => {
                                    ParameterTreeValueSetErrorV1::InvalidLeafName(
                                        leaf_name.clone(),
                                    )
                                }
                                other => ParameterTreeValueSetErrorV1::InvalidValue {
                                    leaf: leaf_name.clone(),
                                    error: other,
                                },
                            })?;
                        AmiParameterTreeNodeV1::Leaf {
                            name: leaf_name.clone(),
                            value_tokens: vec![value_token.to_string()],
                        }
                    }
                    AmiParameterTreeNodeV1::Branch {
                        name: branch_name, ..
                    } => {
                        return Err(ParameterTreeValueSetErrorV1::TargetNotLeaf {
                            name: branch_name.clone(),
                        });
                    }
                }
            } else {
                set_node(child, &segments[1..], type_map, value_token)?
            };
            let mut new_children = children.clone();
            new_children.insert(target.to_string(), new_child);
            Ok(AmiParameterTreeNodeV1::Branch {
                name: name.clone(),
                children: new_children,
            })
        }
        AmiParameterTreeNodeV1::Leaf { name, .. } => {
            // Ran out of segments on a leaf: the path is longer than the tree.
            Err(ParameterTreeValueSetErrorV1::PathNotFound(name.clone()))
        }
    }
}

/// Set the value tokens of one leaf addressed by `path` to a single validated
/// `value_token`, returning a new tree.
///
/// The path is canonical: `[root_name, ..., leaf_name]`. Fails closed with the
/// first violating condition (canonical traversal order). The source tree is
/// never mutated.
pub fn set_parameter_tree_leaf_value_v1(
    tree: &AmiParameterTreeV1,
    path: &[&str],
    type_map: &BTreeMap<String, AmiParameterTypeV1>,
    value_token: &str,
) -> Result<AmiParameterTreeV1, ParameterTreeValueSetErrorV1> {
    if path.is_empty() {
        return Err(ParameterTreeValueSetErrorV1::EmptyPath);
    }
    if path[0] != tree.root_name() {
        return Err(ParameterTreeValueSetErrorV1::RootMismatch);
    }
    let new_root = set_node(tree.root_node(), &path[1..], type_map, value_token)?;
    Ok(AmiParameterTreeV1::new(tree.root_name(), new_root))
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

    fn type_map(pairs: &[(&str, AmiParameterTypeV1)]) -> BTreeMap<String, AmiParameterTypeV1> {
        pairs
            .iter()
            .map(|(name, ty)| (name.to_string(), *ty))
            .collect()
    }

    #[test]
    fn sets_root_level_leaf_value() {
        let t = tree(branch(
            "root",
            vec![
                leaf("gain", &["Float", "0.5"]),
                leaf("steps", &["Integer", "7"]),
            ],
        ));
        let types = type_map(&[
            ("gain", AmiParameterTypeV1::Float),
            ("steps", AmiParameterTypeV1::Integer),
        ]);
        let updated =
            set_parameter_tree_leaf_value_v1(&t, &["root", "gain"], &types, "1.25").expect("set");
        let root = updated.root_node();
        match root {
            AmiParameterTreeNodeV1::Branch { children, .. } => {
                let gain = children.get("gain").expect("gain");
                match gain {
                    AmiParameterTreeNodeV1::Leaf { value_tokens, .. } => {
                        assert_eq!(value_tokens, &vec!["1.25".to_string()]);
                    }
                    AmiParameterTreeNodeV1::Branch { .. } => panic!("expected leaf"),
                }
                let steps = children.get("steps").expect("steps");
                match steps {
                    AmiParameterTreeNodeV1::Leaf { value_tokens, .. } => {
                        assert_eq!(value_tokens, &vec!["Integer".to_string(), "7".to_string()]);
                    }
                    AmiParameterTreeNodeV1::Branch { .. } => panic!("expected leaf"),
                }
            }
            AmiParameterTreeNodeV1::Leaf { .. } => panic!("expected branch root"),
        }
        // source tree untouched
        let source_root = t.root_node();
        match source_root {
            AmiParameterTreeNodeV1::Branch { children, .. } => {
                let gain = children.get("gain").expect("gain");
                match gain {
                    AmiParameterTreeNodeV1::Leaf { value_tokens, .. } => {
                        assert_eq!(value_tokens, &vec!["Float".to_string(), "0.5".to_string()]);
                    }
                    AmiParameterTreeNodeV1::Branch { .. } => panic!("expected leaf"),
                }
            }
            AmiParameterTreeNodeV1::Leaf { .. } => panic!("expected branch root"),
        }
    }

    #[test]
    fn sets_nested_leaf_value() {
        let t = tree(branch(
            "root",
            vec![branch("sub", vec![leaf("deep", &["Float", "1.0"])])],
        ));
        let types = type_map(&[("deep", AmiParameterTypeV1::Float)]);
        let updated = set_parameter_tree_leaf_value_v1(&t, &["root", "sub", "deep"], &types, "2.5")
            .expect("set");
        match updated.root_node() {
            AmiParameterTreeNodeV1::Branch { children, .. } => {
                let sub = children.get("sub").expect("sub");
                match sub {
                    AmiParameterTreeNodeV1::Branch { children, .. } => {
                        let deep = children.get("deep").expect("deep");
                        match deep {
                            AmiParameterTreeNodeV1::Leaf { value_tokens, .. } => {
                                assert_eq!(value_tokens, &vec!["2.5".to_string()]);
                            }
                            AmiParameterTreeNodeV1::Branch { .. } => panic!("expected leaf"),
                        }
                    }
                    AmiParameterTreeNodeV1::Leaf { .. } => panic!("expected branch"),
                }
            }
            AmiParameterTreeNodeV1::Leaf { .. } => panic!("expected branch root"),
        }
    }

    #[test]
    fn empty_path_fails_closed() {
        let t = tree(branch("root", vec![leaf("gain", &["0.5"])]));
        let types = type_map(&[("gain", AmiParameterTypeV1::Float)]);
        let error = set_parameter_tree_leaf_value_v1(&t, &[], &types, "1.0").unwrap_err();
        assert_eq!(error, ParameterTreeValueSetErrorV1::EmptyPath);
    }

    #[test]
    fn root_mismatch_fails_closed() {
        let t = tree(branch("root", vec![leaf("gain", &["0.5"])]));
        let types = type_map(&[("gain", AmiParameterTypeV1::Float)]);
        let error =
            set_parameter_tree_leaf_value_v1(&t, &["other", "gain"], &types, "1.0").unwrap_err();
        assert_eq!(error, ParameterTreeValueSetErrorV1::RootMismatch);
    }

    #[test]
    fn path_not_found_fails_closed() {
        let t = tree(branch("root", vec![leaf("gain", &["0.5"])]));
        let types = type_map(&[("gain", AmiParameterTypeV1::Float)]);
        let error =
            set_parameter_tree_leaf_value_v1(&t, &["root", "nope"], &types, "1.0").unwrap_err();
        assert_eq!(
            error,
            ParameterTreeValueSetErrorV1::PathNotFound("nope".to_string())
        );
    }

    #[test]
    fn branch_target_fails_closed() {
        let t = tree(branch(
            "root",
            vec![branch("sub", vec![leaf("deep", &["1.0"])])],
        ));
        let types = type_map(&[("deep", AmiParameterTypeV1::Float)]);
        let error =
            set_parameter_tree_leaf_value_v1(&t, &["root", "sub"], &types, "1.0").unwrap_err();
        assert_eq!(
            error,
            ParameterTreeValueSetErrorV1::TargetNotLeaf {
                name: "sub".to_string()
            }
        );
    }

    #[test]
    fn missing_type_fails_closed() {
        let t = tree(branch("root", vec![leaf("gain", &["0.5"])]));
        let types = type_map(&[]);
        let error =
            set_parameter_tree_leaf_value_v1(&t, &["root", "gain"], &types, "1.0").unwrap_err();
        assert_eq!(
            error,
            ParameterTreeValueSetErrorV1::MissingType("gain".to_string())
        );
    }

    #[test]
    fn invalid_value_fails_closed() {
        let t = tree(branch("root", vec![leaf("gain", &["0.5"])]));
        let types = type_map(&[("gain", AmiParameterTypeV1::Float)]);
        let error =
            set_parameter_tree_leaf_value_v1(&t, &["root", "gain"], &types, "x1").unwrap_err();
        assert_eq!(
            error,
            ParameterTreeValueSetErrorV1::InvalidValue {
                leaf: "gain".to_string(),
                error: AmiParameterValueErrorV1::InvalidFloat,
            }
        );
    }

    #[test]
    fn invalid_leaf_name_fails_closed() {
        let t = tree(branch("root", vec![leaf("my-gain", &["0.5"])]));
        let types = type_map(&[("my-gain", AmiParameterTypeV1::Float)]);
        let error =
            set_parameter_tree_leaf_value_v1(&t, &["root", "my-gain"], &types, "1.0").unwrap_err();
        assert_eq!(
            error,
            ParameterTreeValueSetErrorV1::InvalidLeafName("my-gain".to_string())
        );
    }
}
