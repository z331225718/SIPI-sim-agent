//! AMI parameter tree leaf value type inference core (P4B-02b33).
//!
//! Infers one `AmiParameterTypeV1` per leaf of an `AmiParameterTreeV1` from the
//! leaf's own value tokens, using the exact product-owned token rules of
//! `AmiParameterValueV1::try_new` (P4B-02b1) in reverse: Integer (i64), Float
//! (finite f64), Boolean (exactly `True`/`False`), List (`(item, ...)` form),
//! String (non-empty fallback). Deterministic precedence per token:
//! Integer > Float > Boolean > List > String. Fail-closed: empty value tokens,
//! multi-token leaves whose tokens disagree, and duplicate leaf names across the
//! tree are strictly rejected.

use std::collections::BTreeMap;

use crate::{AmiParameterTreeV1, AmiParameterTreeNodeV1, AmiParameterTypeV1};

/// Scope policy for the parameter tree value type inference core.
pub const PARAMETER_TREE_VALUE_TYPE_INFERENCE_POLICY_V1: &str =
    "sipi.p4b-02b33.parameter-tree-value-type-inference-v1.leaf-type-inference";

/// Fail-closed errors while inferring leaf value types of a parameter tree.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterTreeTypeInferenceErrorV1 {
    /// A leaf carries no value tokens, so no type can be inferred.
    EmptyValueTokens(String),
    /// A multi-token leaf has tokens that infer to different types.
    ConflictingTokenTypes {
        leaf: String,
        types: Vec<String>,
    },
    /// Two leaves at different depths share the same name (map key collision).
    DuplicateLeafName(String),
}

/// Outcome of a fully successful leaf value type inference pass.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ParameterTreeTypeInferenceV1 {
    leaves_inferred: usize,
    leaf_types: BTreeMap<String, AmiParameterTypeV1>,
}

impl ParameterTreeTypeInferenceV1 {
    pub fn leaves_inferred(&self) -> usize {
        self.leaves_inferred
    }

    pub fn leaf_types(&self) -> &BTreeMap<String, AmiParameterTypeV1> {
        &self.leaf_types
    }
}

/// Infer the type of one value token with deterministic precedence.
fn infer_token_type(token: &str) -> AmiParameterTypeV1 {
    if token.parse::<i64>().is_ok() {
        return AmiParameterTypeV1::Integer;
    }
    if let Ok(value) = token.parse::<f64>() {
        if value.is_finite() {
            return AmiParameterTypeV1::Float;
        }
    }
    if token == "True" || token == "False" {
        return AmiParameterTypeV1::Boolean;
    }
    if token.starts_with('(') && token.ends_with(')') {
        let inner = &token[1..token.len() - 1];
        if !inner.is_empty() && !inner.split(',').any(|item| item.trim().is_empty()) {
            return AmiParameterTypeV1::List;
        }
    }
    AmiParameterTypeV1::String_
}

fn infer_node(
    node: &AmiParameterTreeNodeV1,
    out: &mut ParameterTreeTypeInferenceV1,
) -> Result<(), ParameterTreeTypeInferenceErrorV1> {
    match node {
        AmiParameterTreeNodeV1::Branch { children, .. } => {
            for child in children.values() {
                infer_node(child, out)?;
            }
            Ok(())
        }
        AmiParameterTreeNodeV1::Leaf {
            name,
            value_tokens,
        } => {
            if value_tokens.is_empty() {
                return Err(ParameterTreeTypeInferenceErrorV1::EmptyValueTokens(
                    name.clone(),
                ));
            }
            let mut distinct = Vec::new();
            for token in value_tokens {
                let token_type = infer_token_type(token);
                if !distinct.contains(&token_type) {
                    distinct.push(token_type);
                }
            }
            if distinct.len() > 1 {
                let mut types: Vec<String> =
                    distinct.iter().map(|t| t.token().to_string()).collect();
                types.sort();
                return Err(ParameterTreeTypeInferenceErrorV1::ConflictingTokenTypes {
                    leaf: name.clone(),
                    types,
                });
            }
            let leaf_type = distinct[0];
            if out.leaf_types.insert(name.clone(), leaf_type).is_some() {
                return Err(ParameterTreeTypeInferenceErrorV1::DuplicateLeafName(
                    name.clone(),
                ));
            }
            out.leaves_inferred += 1;
            Ok(())
        }
    }
}

/// Infer one `AmiParameterTypeV1` per leaf of `tree` from its value tokens.
///
/// Returns the count of leaves inferred and the name -> type map, or fails
/// closed on empty value tokens, conflicting multi-token leaves, or duplicate
/// leaf names (canonical traversal order: branch children in byte-wise name
/// order, depth first).
pub fn infer_parameter_tree_leaf_types_v1(
    tree: &AmiParameterTreeV1,
) -> Result<ParameterTreeTypeInferenceV1, ParameterTreeTypeInferenceErrorV1> {
    let mut result = ParameterTreeTypeInferenceV1 {
        leaves_inferred: 0,
        leaf_types: BTreeMap::new(),
    };
    infer_node(tree.root_node(), &mut result)?;
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::validate_parameter_tree_values_v1;

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
    fn single_token_types_infer() {
        let t = tree(branch(
            "root",
            vec![
                leaf("gain", &["0.5"]),
                leaf("steps", &["7"]),
                leaf("enabled", &["True"]),
                leaf("mode", &["fast"]),
            ],
        ));
        let result = infer_parameter_tree_leaf_types_v1(&t).expect("inferred");
        assert_eq!(result.leaves_inferred(), 4);
        assert_eq!(
            result.leaf_types().get("gain"),
            Some(&AmiParameterTypeV1::Float)
        );
        assert_eq!(
            result.leaf_types().get("steps"),
            Some(&AmiParameterTypeV1::Integer)
        );
        assert_eq!(
            result.leaf_types().get("enabled"),
            Some(&AmiParameterTypeV1::Boolean)
        );
        assert_eq!(
            result.leaf_types().get("mode"),
            Some(&AmiParameterTypeV1::String_)
        );
    }

    #[test]
    fn list_token_infers_list() {
        let t = tree(branch("root", vec![leaf("l", &["(1, 2)"])]));
        let result = infer_parameter_tree_leaf_types_v1(&t).expect("inferred");
        assert_eq!(
            result.leaf_types().get("l"),
            Some(&AmiParameterTypeV1::List)
        );
    }

    #[test]
    fn uniform_multi_token_leaf_infers() {
        let t = tree(branch("root", vec![leaf("a", &["1", "2", "3"])]));
        let result = infer_parameter_tree_leaf_types_v1(&t).expect("inferred");
        assert_eq!(
            result.leaf_types().get("a"),
            Some(&AmiParameterTypeV1::Integer)
        );
    }

    #[test]
    fn conflicting_tokens_fail_closed() {
        let t = tree(branch("root", vec![leaf("mix", &["1", "2.5"])]));
        let error = infer_parameter_tree_leaf_types_v1(&t).unwrap_err();
        assert_eq!(
            error,
            ParameterTreeTypeInferenceErrorV1::ConflictingTokenTypes {
                leaf: "mix".to_string(),
                types: vec!["Float".to_string(), "Integer".to_string()],
            }
        );
    }

    #[test]
    fn empty_value_tokens_fail_closed() {
        let t = tree(branch("root", vec![leaf("mode", &[])]));
        let error = infer_parameter_tree_leaf_types_v1(&t).unwrap_err();
        assert_eq!(
            error,
            ParameterTreeTypeInferenceErrorV1::EmptyValueTokens("mode".to_string())
        );
    }

    #[test]
    fn duplicate_leaf_names_fail_closed() {
        let t = tree(branch(
            "root",
            vec![branch("sub", vec![leaf("gain", &["1"])]), leaf("gain", &["2"])],
        ));
        let error = infer_parameter_tree_leaf_types_v1(&t).unwrap_err();
        assert_eq!(
            error,
            ParameterTreeTypeInferenceErrorV1::DuplicateLeafName("gain".to_string())
        );
    }

    #[test]
    fn string_fallback_and_numeric_tokens() {
        let t = tree(branch(
            "root",
            vec![leaf("name", &["x-y"]), leaf("code", &["007"])],
        ));
        let result = infer_parameter_tree_leaf_types_v1(&t).expect("inferred");
        assert_eq!(
            result.leaf_types().get("name"),
            Some(&AmiParameterTypeV1::String_)
        );
        assert_eq!(
            result.leaf_types().get("code"),
            Some(&AmiParameterTypeV1::Integer)
        );
    }

    #[test]
    fn inferred_types_round_trip_through_validation() {
        let t = tree(branch(
            "root",
            vec![
                leaf("gain", &["0.5"]),
                leaf("steps", &["7"]),
                leaf("enabled", &["True"]),
            ],
        ));
        let inference = infer_parameter_tree_leaf_types_v1(&t).expect("inferred");
        let validation =
            validate_parameter_tree_values_v1(&t, inference.leaf_types()).expect("valid");
        assert_eq!(validation.leaves_checked(), 3);
        assert_eq!(validation.tokens_checked(), 3);
    }
}
