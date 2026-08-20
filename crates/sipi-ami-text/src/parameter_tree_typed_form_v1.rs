//! AMI parameter tree typed-form extraction core (P4B-02b34).
//!
//! Extracts typed `AmiParameterValueV1` entries from an `AmiParameterTreeV1`
//! whose leaves follow the AMI parameter form `(name Type value)`, i.e. exactly
//! two value tokens: a type token and one value token. This is the tree-level
//! counterpart of the AST scanner (P4B-02b6): the bridge from a typed parameter
//! tree to typed parameter values. Fail-closed: leaves with no value tokens, a
//! single token, more than two tokens, an unknown type token, a value violating
//! its type rule, an invalid parameter name, or a duplicate parameter name are
//! strictly rejected.

use std::collections::BTreeMap;

use crate::{
    AmiParameterTreeNodeV1, AmiParameterTreeV1, AmiParameterTypeV1, AmiParameterValueErrorV1,
    AmiParameterValueV1,
};

/// Scope policy for the parameter tree typed-form extraction core.
pub const PARAMETER_TREE_TYPED_FORM_POLICY_V1: &str =
    "sipi.p4b-02b34.parameter-tree-typed-form-v1.tree-leaves-to-values";

/// Fail-closed errors while extracting typed parameter forms from a tree.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterTreeTypedFormErrorV1 {
    /// A leaf carries no value tokens at all.
    EmptyValueTokens(String),
    /// A leaf has a single value token: neither type nor value is decidable.
    NotTypedForm { leaf: String },
    /// A leaf has more than two value tokens; the AMI parameter form is
    /// exactly `(name Type value)`.
    MultiTokenForm { leaf: String, token_count: usize },
    /// The leaf's first value token is not a known type token.
    UnknownTypeToken { leaf: String, token: String },
    /// The leaf's value token violates its declared type rule.
    InvalidValue {
        leaf: String,
        error: AmiParameterValueErrorV1,
    },
    /// A leaf name is not a valid parameter name per the P4B-02b1 name rule.
    InvalidParameterName(String),
    /// Two leaves (possibly at different depths) share the same name.
    DuplicateParameter(String),
}

/// Outcome of a fully successful typed-form extraction pass.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ParameterTreeTypedFormsV1 {
    leaves_consumed: usize,
    parameters: BTreeMap<String, AmiParameterValueV1>,
}

impl ParameterTreeTypedFormsV1 {
    pub fn leaves_consumed(&self) -> usize {
        self.leaves_consumed
    }

    pub fn parameters(&self) -> &BTreeMap<String, AmiParameterValueV1> {
        &self.parameters
    }
}

fn extract_node(
    node: &AmiParameterTreeNodeV1,
    out: &mut ParameterTreeTypedFormsV1,
) -> Result<(), ParameterTreeTypedFormErrorV1> {
    match node {
        AmiParameterTreeNodeV1::Branch { children, .. } => {
            for child in children.values() {
                extract_node(child, out)?;
            }
            Ok(())
        }
        AmiParameterTreeNodeV1::Leaf { name, value_tokens } => {
            if value_tokens.is_empty() {
                return Err(ParameterTreeTypedFormErrorV1::EmptyValueTokens(
                    name.clone(),
                ));
            }
            if value_tokens.len() == 1 {
                return Err(ParameterTreeTypedFormErrorV1::NotTypedForm { leaf: name.clone() });
            }
            if value_tokens.len() > 2 {
                return Err(ParameterTreeTypedFormErrorV1::MultiTokenForm {
                    leaf: name.clone(),
                    token_count: value_tokens.len(),
                });
            }
            let type_token = &value_tokens[0];
            let value_token = &value_tokens[1];
            if AmiParameterTypeV1::from_token(type_token).is_none() {
                return Err(ParameterTreeTypedFormErrorV1::UnknownTypeToken {
                    leaf: name.clone(),
                    token: type_token.clone(),
                });
            }
            let parameter = AmiParameterValueV1::try_new(name, type_token, value_token)
                .map_err(|error| match error {
                    AmiParameterValueErrorV1::EmptyName
                    | AmiParameterValueErrorV1::UnknownTypeToken => {
                        unreachable!(
                            "structurally impossible: tree names are non-empty and the                              type token was just parsed"
                        )
                    }
                    AmiParameterValueErrorV1::InvalidName => {
                        ParameterTreeTypedFormErrorV1::InvalidParameterName(name.clone())
                    }
                    other => ParameterTreeTypedFormErrorV1::InvalidValue {
                        leaf: name.clone(),
                        error: other,
                    },
                })?;
            if out
                .parameters
                .insert(parameter.name().to_string(), parameter)
                .is_some()
            {
                return Err(ParameterTreeTypedFormErrorV1::DuplicateParameter(
                    name.clone(),
                ));
            }
            out.leaves_consumed += 1;
            Ok(())
        }
    }
}

/// Extract typed parameter values from every leaf of `tree`.
///
/// Returns the count of consumed leaves and the name -> value map, or fails
/// closed with the first non-conforming leaf (canonical traversal order:
/// branch children in byte-wise name order, depth first).
pub fn extract_typed_parameter_forms_v1(
    tree: &AmiParameterTreeV1,
) -> Result<ParameterTreeTypedFormsV1, ParameterTreeTypedFormErrorV1> {
    let mut result = ParameterTreeTypedFormsV1 {
        leaves_consumed: 0,
        parameters: BTreeMap::new(),
    };
    extract_node(tree.root_node(), &mut result)?;
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

    #[test]
    fn valid_typed_leaves_extract() {
        let t = tree(branch(
            "root",
            vec![
                leaf("gain", &["Float", "0.5"]),
                leaf("steps", &["Integer", "7"]),
                leaf("enabled", &["Boolean", "True"]),
                leaf("mode", &["String", "fast"]),
            ],
        ));
        let result = extract_typed_parameter_forms_v1(&t).expect("extracted");
        assert_eq!(result.leaves_consumed(), 4);
        assert_eq!(result.parameters().len(), 4);
        let gain = result.parameters().get("gain").expect("gain");
        assert_eq!(gain.name(), "gain");
        assert_eq!(gain.parameter_type(), AmiParameterTypeV1::Float);
        assert_eq!(gain.value_token(), "0.5");
        let steps = result.parameters().get("steps").expect("steps");
        assert_eq!(steps.parameter_type(), AmiParameterTypeV1::Integer);
        assert_eq!(steps.value_token(), "7");
    }

    #[test]
    fn multi_token_form_is_rejected() {
        let t = tree(branch("root", vec![leaf("gain", &["Float", "0.5", "1.0"])]));
        let error = extract_typed_parameter_forms_v1(&t).unwrap_err();
        assert_eq!(
            error,
            ParameterTreeTypedFormErrorV1::MultiTokenForm {
                leaf: "gain".to_string(),
                token_count: 3,
            }
        );
    }

    #[test]
    fn single_token_is_not_a_typed_form() {
        let t = tree(branch("root", vec![leaf("gain", &["0.5"])]));
        let error = extract_typed_parameter_forms_v1(&t).unwrap_err();
        assert_eq!(
            error,
            ParameterTreeTypedFormErrorV1::NotTypedForm {
                leaf: "gain".to_string(),
            }
        );
    }

    #[test]
    fn empty_value_tokens_are_rejected() {
        let t = tree(branch("root", vec![leaf("gain", &[])]));
        let error = extract_typed_parameter_forms_v1(&t).unwrap_err();
        assert_eq!(
            error,
            ParameterTreeTypedFormErrorV1::EmptyValueTokens("gain".to_string())
        );
    }

    #[test]
    fn unknown_type_token_is_rejected() {
        let t = tree(branch("root", vec![leaf("gain", &["Real", "0.5"])]));
        let error = extract_typed_parameter_forms_v1(&t).unwrap_err();
        assert_eq!(
            error,
            ParameterTreeTypedFormErrorV1::UnknownTypeToken {
                leaf: "gain".to_string(),
                token: "Real".to_string(),
            }
        );
    }

    #[test]
    fn invalid_value_for_type_is_rejected() {
        let t = tree(branch("root", vec![leaf("gain", &["Float", "x1"])]));
        let error = extract_typed_parameter_forms_v1(&t).unwrap_err();
        assert_eq!(
            error,
            ParameterTreeTypedFormErrorV1::InvalidValue {
                leaf: "gain".to_string(),
                error: AmiParameterValueErrorV1::InvalidFloat,
            }
        );
    }

    #[test]
    fn invalid_parameter_name_is_rejected() {
        let t = tree(branch("root", vec![leaf("my-gain", &["Float", "0.5"])]));
        let error = extract_typed_parameter_forms_v1(&t).unwrap_err();
        assert_eq!(
            error,
            ParameterTreeTypedFormErrorV1::InvalidParameterName("my-gain".to_string())
        );
    }

    #[test]
    fn duplicate_parameter_names_are_rejected() {
        let t = tree(branch(
            "root",
            vec![
                branch("sub", vec![leaf("gain", &["Float", "1.0"])]),
                leaf("gain", &["Float", "2.0"]),
            ],
        ));
        let error = extract_typed_parameter_forms_v1(&t).unwrap_err();
        assert_eq!(
            error,
            ParameterTreeTypedFormErrorV1::DuplicateParameter("gain".to_string())
        );
    }
}
