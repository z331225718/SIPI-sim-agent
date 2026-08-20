//! Typed validation of all leaf value tokens in an AMI parameter tree (P4B-02b32).
//!
//! Walks an `AmiParameterTreeV1` hierarchy and validates every leaf's value tokens
//! against a caller-supplied type map (leaf name -> `AmiParameterTypeV1`), reusing
//! the exact product-owned value rules of `AmiParameterValueV1::try_new` (P4B-02b1).
//! Fail-closed: a leaf without a declared type, a leaf with no value tokens, or any
//! token violating its declared type rule is strictly rejected.

use std::collections::BTreeMap;

use crate::{
    AmiParameterTreeNodeV1, AmiParameterTreeV1, AmiParameterTypeV1, AmiParameterValueErrorV1,
    AmiParameterValueV1,
};

/// Scope policy for the parameter tree value validation core.
pub const PARAMETER_TREE_VALUE_VALIDATION_POLICY_V1: &str =
    "sipi.p4b-02b32.parameter-tree-value-validation-v1.typed-leaf-validation";

/// Fail-closed errors while validating leaf value tokens of a parameter tree.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterTreeValueValidationErrorV1 {
    /// A leaf has no declared type in the caller-supplied type map.
    MissingType(String),
    /// A leaf name is not a valid parameter name per the P4B-02b1 name rule.
    InvalidLeafName(String),
    /// A Float leaf has a token that does not parse as a finite f64.
    InvalidFloat { leaf: String, token: String },
    /// An Integer leaf has a token that does not parse as an i64.
    InvalidInteger { leaf: String, token: String },
    /// A Boolean leaf has a token other than exactly `True` or `False`.
    InvalidBoolean { leaf: String, token: String },
    /// A String leaf has a token that is empty.
    EmptyStringValue { leaf: String },
    /// A List leaf has a token that is not a non-empty `(item, item, ...)` list.
    InvalidList { leaf: String, token: String },
    /// A leaf name, value token, or List item count exceeds the fixed v1 capacity.
    CapacityExceeded { leaf: String },
    /// A leaf carries no value tokens at all.
    EmptyValueTokens(String),
}

/// Outcome of a fully successful typed leaf value validation pass.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ParameterTreeValueValidationV1 {
    leaves_checked: usize,
    tokens_checked: usize,
    leaf_types: BTreeMap<String, AmiParameterTypeV1>,
}

impl ParameterTreeValueValidationV1 {
    pub fn leaves_checked(&self) -> usize {
        self.leaves_checked
    }

    pub fn tokens_checked(&self) -> usize {
        self.tokens_checked
    }

    pub fn leaf_types(&self) -> &BTreeMap<String, AmiParameterTypeV1> {
        &self.leaf_types
    }
}

fn validate_node(
    node: &AmiParameterTreeNodeV1,
    type_map: &BTreeMap<String, AmiParameterTypeV1>,
    out: &mut ParameterTreeValueValidationV1,
) -> Result<(), ParameterTreeValueValidationErrorV1> {
    match node {
        AmiParameterTreeNodeV1::Branch { children, .. } => {
            for child in children.values() {
                validate_node(child, type_map, out)?;
            }
            Ok(())
        }
        AmiParameterTreeNodeV1::Leaf { name, value_tokens } => {
            let parameter_type = type_map
                .get(name)
                .copied()
                .ok_or_else(|| ParameterTreeValueValidationErrorV1::MissingType(name.clone()))?;
            if value_tokens.is_empty() {
                return Err(ParameterTreeValueValidationErrorV1::EmptyValueTokens(
                    name.clone(),
                ));
            }
            for token in value_tokens {
                AmiParameterValueV1::try_new(name, parameter_type.token(), token).map_err(
                    |error| match error {
                        AmiParameterValueErrorV1::EmptyName
                        | AmiParameterValueErrorV1::UnknownTypeToken => {
                            unreachable!(
                                "structurally impossible: tree names are non-empty and the                                  type comes from AmiParameterTypeV1"
                            )
                        }
                        AmiParameterValueErrorV1::InvalidName
                        | AmiParameterValueErrorV1::NameTooLong => {
                            ParameterTreeValueValidationErrorV1::InvalidLeafName(
                                name.clone(),
                            )
                        }
                        AmiParameterValueErrorV1::InvalidFloat => {
                            ParameterTreeValueValidationErrorV1::InvalidFloat {
                                leaf: name.clone(),
                                token: token.clone(),
                            }
                        }
                        AmiParameterValueErrorV1::InvalidInteger => {
                            ParameterTreeValueValidationErrorV1::InvalidInteger {
                                leaf: name.clone(),
                                token: token.clone(),
                            }
                        }
                        AmiParameterValueErrorV1::InvalidBoolean => {
                            ParameterTreeValueValidationErrorV1::InvalidBoolean {
                                leaf: name.clone(),
                                token: token.clone(),
                            }
                        }
                        AmiParameterValueErrorV1::EmptyStringValue => {
                            ParameterTreeValueValidationErrorV1::EmptyStringValue {
                                leaf: name.clone(),
                            }
                        }
                        AmiParameterValueErrorV1::InvalidList => {
                            ParameterTreeValueValidationErrorV1::InvalidList {
                                leaf: name.clone(),
                                token: token.clone(),
                            }
                        }
                        AmiParameterValueErrorV1::ValueTokenTooLong
                        | AmiParameterValueErrorV1::ListTooLong => {
                            ParameterTreeValueValidationErrorV1::CapacityExceeded {
                                leaf: name.clone(),
                            }
                        }
                    },
                )?;
                out.tokens_checked += 1;
            }
            out.leaf_types.insert(name.clone(), parameter_type);
            out.leaves_checked += 1;
            Ok(())
        }
    }
}

/// Validate every leaf value token of `tree` against `type_map`.
///
/// Returns the validated leaf/token counts and the echoed type map, or fails
/// closed with the first violating leaf and token (canonical traversal order:
/// branch children in byte-wise name order, depth first).
pub fn validate_parameter_tree_values_v1(
    tree: &AmiParameterTreeV1,
    type_map: &BTreeMap<String, AmiParameterTypeV1>,
) -> Result<ParameterTreeValueValidationV1, ParameterTreeValueValidationErrorV1> {
    let mut result = ParameterTreeValueValidationV1 {
        leaves_checked: 0,
        tokens_checked: 0,
        leaf_types: BTreeMap::new(),
    };
    validate_node(tree.root_node(), type_map, &mut result)?;
    Ok(result)
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
    fn mixed_types_validate() {
        let t = tree(branch(
            "root",
            vec![
                leaf("gain", &["0.5"]),
                leaf("steps", &["7"]),
                leaf("enabled", &["True"]),
                leaf("mode", &["fast"]),
            ],
        ));
        let types = type_map(&[
            ("gain", AmiParameterTypeV1::Float),
            ("steps", AmiParameterTypeV1::Integer),
            ("enabled", AmiParameterTypeV1::Boolean),
            ("mode", AmiParameterTypeV1::String_),
        ]);
        let result = validate_parameter_tree_values_v1(&t, &types).expect("valid");
        assert_eq!(result.leaves_checked(), 4);
        assert_eq!(result.tokens_checked(), 4);
        assert_eq!(result.leaf_types(), &types);
    }

    #[test]
    fn nested_branch_leaves_are_validated() {
        let t = tree(branch(
            "root",
            vec![branch(
                "sub",
                vec![leaf("deep", &["1.25"]), leaf("other", &["2.5"])],
            )],
        ));
        let types = type_map(&[
            ("deep", AmiParameterTypeV1::Float),
            ("other", AmiParameterTypeV1::Float),
        ]);
        let result = validate_parameter_tree_values_v1(&t, &types).expect("valid");
        assert_eq!(result.leaves_checked(), 2);
        assert_eq!(result.tokens_checked(), 2);
    }

    #[test]
    fn missing_type_fails_closed() {
        let t = tree(branch(
            "root",
            vec![leaf("gain", &["0.5"]), leaf("steps", &["7"])],
        ));
        let types = type_map(&[("gain", AmiParameterTypeV1::Float)]);
        let error = validate_parameter_tree_values_v1(&t, &types).unwrap_err();
        assert_eq!(
            error,
            ParameterTreeValueValidationErrorV1::MissingType("steps".to_string())
        );
    }

    #[test]
    fn invalid_float_token_is_rejected() {
        let t = tree(branch(
            "root",
            vec![leaf("gain", &["x1"]), leaf("steps", &["7"])],
        ));
        let types = type_map(&[
            ("gain", AmiParameterTypeV1::Float),
            ("steps", AmiParameterTypeV1::Integer),
        ]);
        let error = validate_parameter_tree_values_v1(&t, &types).unwrap_err();
        assert_eq!(
            error,
            ParameterTreeValueValidationErrorV1::InvalidFloat {
                leaf: "gain".to_string(),
                token: "x1".to_string(),
            }
        );
    }

    #[test]
    fn invalid_integer_token_is_rejected() {
        let t = tree(branch("root", vec![leaf("steps", &["7.5"])]));
        let types = type_map(&[("steps", AmiParameterTypeV1::Integer)]);
        let error = validate_parameter_tree_values_v1(&t, &types).unwrap_err();
        assert_eq!(
            error,
            ParameterTreeValueValidationErrorV1::InvalidInteger {
                leaf: "steps".to_string(),
                token: "7.5".to_string(),
            }
        );
    }

    #[test]
    fn invalid_boolean_token_is_rejected() {
        let t = tree(branch("root", vec![leaf("enabled", &["maybe"])]));
        let types = type_map(&[("enabled", AmiParameterTypeV1::Boolean)]);
        let error = validate_parameter_tree_values_v1(&t, &types).unwrap_err();
        assert_eq!(
            error,
            ParameterTreeValueValidationErrorV1::InvalidBoolean {
                leaf: "enabled".to_string(),
                token: "maybe".to_string(),
            }
        );
    }

    #[test]
    fn empty_value_tokens_are_rejected() {
        let t = tree(branch("root", vec![leaf("mode", &[])]));
        let types = type_map(&[("mode", AmiParameterTypeV1::String_)]);
        let error = validate_parameter_tree_values_v1(&t, &types).unwrap_err();
        assert_eq!(
            error,
            ParameterTreeValueValidationErrorV1::EmptyValueTokens("mode".to_string())
        );
    }

    #[test]
    fn list_tokens_follow_the_list_rule() {
        let t = tree(branch(
            "root",
            vec![leaf("lgood", &["(1, 2)"]), leaf("lbad", &["(1,,2)"])],
        ));
        let types = type_map(&[
            ("lgood", AmiParameterTypeV1::List),
            ("lbad", AmiParameterTypeV1::List),
        ]);
        let error = validate_parameter_tree_values_v1(&t, &types).unwrap_err();
        assert_eq!(
            error,
            ParameterTreeValueValidationErrorV1::InvalidList {
                leaf: "lbad".to_string(),
                token: "(1,,2)".to_string(),
            }
        );
        let t2 = tree(branch("root", vec![leaf("lgood", &["(1, 2)"])]));
        let result = validate_parameter_tree_values_v1(&t2, &types).expect("valid list");
        assert_eq!(result.leaves_checked(), 1);
        assert_eq!(result.tokens_checked(), 1);
    }

    #[test]
    fn invalid_leaf_name_is_rejected() {
        let t = tree(branch("root", vec![leaf("my-gain", &["0.5"])]));
        let types = type_map(&[("my-gain", AmiParameterTypeV1::Float)]);
        let error = validate_parameter_tree_values_v1(&t, &types).unwrap_err();
        assert_eq!(
            error,
            ParameterTreeValueValidationErrorV1::InvalidLeafName("my-gain".to_string())
        );
    }
}
