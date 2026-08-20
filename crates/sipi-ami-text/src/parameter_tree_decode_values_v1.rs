//! AMI parameter tree leaf value decoding core (P4B-02b37).
//!
//! Decodes validated leaf value tokens of an `AmiParameterTreeV1` into typed
//! Rust values (`DecodedLeafValueV1`) using a caller-supplied type map
//! (leaf name -> `AmiParameterTypeV1`), reusing the exact product-owned rules of
//! `AmiParameterValueV1::try_new` (P4B-02b1) for validation. Every decoded leaf
//! carries exactly one value token (the AMI parameter form `(name Type value)`).
//! Fail-closed: missing type, invalid leaf name, invalid value, empty value
//! tokens, multi-token leaves, and duplicate leaf names are strictly rejected.
//! Raw spellings are preserved: a quoted token decodes with its surrounding
//! quotes (no normalization, per the P4B-02b0 raw-byte binding principle).

use std::collections::BTreeMap;

use crate::{
    AmiParameterTreeNodeV1, AmiParameterTreeV1, AmiParameterTypeV1, AmiParameterValueErrorV1,
    AmiParameterValueV1,
};

/// Scope policy for the parameter tree leaf value decoding core.
pub const PARAMETER_TREE_LEAF_VALUE_DECODING_POLICY_V1: &str =
    "sipi.p4b-02b37.parameter-tree-leaf-value-decoding-v1.typed-value-decode";

/// Fail-closed errors while decoding leaf value tokens of a parameter tree.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterTreeLeafValueDecodingErrorV1 {
    /// A leaf has no declared type in the caller-supplied type map.
    MissingType(String),
    /// A leaf name is not a valid parameter name per the P4B-02b1 name rule.
    InvalidLeafName(String),
    /// The leaf's value token violates its declared type rule.
    InvalidValue {
        leaf: String,
        error: AmiParameterValueErrorV1,
    },
    /// A leaf carries no value tokens at all.
    EmptyValueTokens(String),
    /// A leaf carries more than one value token; decoding needs exactly one.
    MultiTokenValue { leaf: String, token_count: usize },
    /// Two leaves (possibly at different depths) share the same name.
    DuplicateLeafName(String),
}

/// One decoded typed value of a parameter tree leaf.
#[derive(Clone, Debug, PartialEq)]
pub enum DecodedLeafValueV1 {
    Float(f64),
    Integer(i64),
    Boolean(bool),
    String(String),
    List(Vec<String>),
}

/// Outcome of a fully successful leaf value decoding pass.
#[derive(Clone, Debug, PartialEq)]
pub struct ParameterTreeLeafValueDecodingV1 {
    leaves_decoded: usize,
    values: BTreeMap<String, DecodedLeafValueV1>,
}

impl ParameterTreeLeafValueDecodingV1 {
    pub fn leaves_decoded(&self) -> usize {
        self.leaves_decoded
    }

    pub fn values(&self) -> &BTreeMap<String, DecodedLeafValueV1> {
        &self.values
    }
}

fn decode_token(
    _leaf: &str,
    parameter_type: AmiParameterTypeV1,
    token: &str,
) -> Result<DecodedLeafValueV1, ParameterTreeLeafValueDecodingErrorV1> {
    match parameter_type {
        AmiParameterTypeV1::Float => {
            let value = token.parse::<f64>().expect("validated finite float token");
            Ok(DecodedLeafValueV1::Float(value))
        }
        AmiParameterTypeV1::Integer => {
            let value = token.parse::<i64>().expect("validated integer token");
            Ok(DecodedLeafValueV1::Integer(value))
        }
        AmiParameterTypeV1::Boolean => {
            let value = match token {
                "True" => true,
                "False" => false,
                _ => unreachable!("validated boolean token"),
            };
            Ok(DecodedLeafValueV1::Boolean(value))
        }
        AmiParameterTypeV1::String_ => Ok(DecodedLeafValueV1::String(token.to_string())),
        AmiParameterTypeV1::List => {
            let inner = &token[1..token.len() - 1];
            let items = inner
                .split(',')
                .map(|item| item.trim().to_string())
                .collect();
            Ok(DecodedLeafValueV1::List(items))
        }
    }
}

fn decode_node(
    node: &AmiParameterTreeNodeV1,
    type_map: &BTreeMap<String, AmiParameterTypeV1>,
    out: &mut ParameterTreeLeafValueDecodingV1,
) -> Result<(), ParameterTreeLeafValueDecodingErrorV1> {
    match node {
        AmiParameterTreeNodeV1::Branch { children, .. } => {
            for child in children.values() {
                decode_node(child, type_map, out)?;
            }
            Ok(())
        }
        AmiParameterTreeNodeV1::Leaf { name, value_tokens } => {
            let parameter_type = type_map
                .get(name)
                .copied()
                .ok_or_else(|| ParameterTreeLeafValueDecodingErrorV1::MissingType(name.clone()))?;
            if value_tokens.is_empty() {
                return Err(ParameterTreeLeafValueDecodingErrorV1::EmptyValueTokens(
                    name.clone(),
                ));
            }
            if value_tokens.len() > 1 {
                return Err(ParameterTreeLeafValueDecodingErrorV1::MultiTokenValue {
                    leaf: name.clone(),
                    token_count: value_tokens.len(),
                });
            }
            let token = &value_tokens[0];
            AmiParameterValueV1::try_new(name, parameter_type.token(), token).map_err(
                |error| match error {
                    AmiParameterValueErrorV1::EmptyName
                    | AmiParameterValueErrorV1::UnknownTypeToken => {
                        unreachable!(
                            "structurally impossible: tree names are non-empty and the                              type comes from AmiParameterTypeV1"
                        )
                    }
                    AmiParameterValueErrorV1::InvalidName => {
                        ParameterTreeLeafValueDecodingErrorV1::InvalidLeafName(
                            name.clone(),
                        )
                    }
                    other => ParameterTreeLeafValueDecodingErrorV1::InvalidValue {
                        leaf: name.clone(),
                        error: other,
                    },
                },
            )?;
            let decoded = decode_token(name, parameter_type, token)?;
            if out.values.insert(name.clone(), decoded).is_some() {
                return Err(ParameterTreeLeafValueDecodingErrorV1::DuplicateLeafName(
                    name.clone(),
                ));
            }
            out.leaves_decoded += 1;
            Ok(())
        }
    }
}

/// Decode every leaf value token of `tree` into a typed Rust value.
///
/// Returns the count of decoded leaves and the name -> value map, or fails
/// closed with the first violating leaf (canonical traversal order: branch
/// children in byte-wise name order, depth first).
pub fn decode_parameter_tree_leaf_values_v1(
    tree: &AmiParameterTreeV1,
    type_map: &BTreeMap<String, AmiParameterTypeV1>,
) -> Result<ParameterTreeLeafValueDecodingV1, ParameterTreeLeafValueDecodingErrorV1> {
    let mut result = ParameterTreeLeafValueDecodingV1 {
        leaves_decoded: 0,
        values: BTreeMap::new(),
    };
    decode_node(tree.root_node(), type_map, &mut result)?;
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
    fn decodes_mixed_types() {
        let t = tree(branch(
            "root",
            vec![
                leaf("gain", &["0.5"]),
                leaf("steps", &["7"]),
                leaf("enabled", &["True"]),
                leaf("mode", &["fast"]),
                leaf("l", &["(1, 2)"]),
            ],
        ));
        let types = type_map(&[
            ("gain", AmiParameterTypeV1::Float),
            ("steps", AmiParameterTypeV1::Integer),
            ("enabled", AmiParameterTypeV1::Boolean),
            ("mode", AmiParameterTypeV1::String_),
            ("l", AmiParameterTypeV1::List),
        ]);
        let result = decode_parameter_tree_leaf_values_v1(&t, &types).expect("decoded");
        assert_eq!(result.leaves_decoded(), 5);
        assert_eq!(
            result.values().get("gain"),
            Some(&DecodedLeafValueV1::Float(0.5))
        );
        assert_eq!(
            result.values().get("steps"),
            Some(&DecodedLeafValueV1::Integer(7))
        );
        assert_eq!(
            result.values().get("enabled"),
            Some(&DecodedLeafValueV1::Boolean(true))
        );
        assert_eq!(
            result.values().get("mode"),
            Some(&DecodedLeafValueV1::String("fast".to_string()))
        );
        assert_eq!(
            result.values().get("l"),
            Some(&DecodedLeafValueV1::List(vec![
                "1".to_string(),
                "2".to_string()
            ]))
        );
    }

    #[test]
    fn float_precision_is_exact() {
        let t = tree(branch("root", vec![leaf("gain", &["0.125"])]));
        let types = type_map(&[("gain", AmiParameterTypeV1::Float)]);
        let result = decode_parameter_tree_leaf_values_v1(&t, &types).expect("decoded");
        assert_eq!(
            result.values().get("gain"),
            Some(&DecodedLeafValueV1::Float(0.125))
        );
    }

    #[test]
    fn multi_token_leaf_is_rejected() {
        let t = tree(branch("root", vec![leaf("steps", &["7", "8"])]));
        let types = type_map(&[("steps", AmiParameterTypeV1::Integer)]);
        let error = decode_parameter_tree_leaf_values_v1(&t, &types).unwrap_err();
        assert_eq!(
            error,
            ParameterTreeLeafValueDecodingErrorV1::MultiTokenValue {
                leaf: "steps".to_string(),
                token_count: 2,
            }
        );
    }

    #[test]
    fn missing_type_fails_closed() {
        let t = tree(branch(
            "root",
            vec![leaf("gain", &["0.5"]), leaf("steps", &["7"])],
        ));
        let types = type_map(&[("gain", AmiParameterTypeV1::Float)]);
        let error = decode_parameter_tree_leaf_values_v1(&t, &types).unwrap_err();
        assert_eq!(
            error,
            ParameterTreeLeafValueDecodingErrorV1::MissingType("steps".to_string())
        );
    }

    #[test]
    fn invalid_value_fails_closed() {
        let t = tree(branch("root", vec![leaf("gain", &["x1"])]));
        let types = type_map(&[("gain", AmiParameterTypeV1::Float)]);
        let error = decode_parameter_tree_leaf_values_v1(&t, &types).unwrap_err();
        assert_eq!(
            error,
            ParameterTreeLeafValueDecodingErrorV1::InvalidValue {
                leaf: "gain".to_string(),
                error: AmiParameterValueErrorV1::InvalidFloat,
            }
        );
    }

    #[test]
    fn empty_value_tokens_fail_closed() {
        let t = tree(branch("root", vec![leaf("mode", &[])]));
        let types = type_map(&[("mode", AmiParameterTypeV1::String_)]);
        let error = decode_parameter_tree_leaf_values_v1(&t, &types).unwrap_err();
        assert_eq!(
            error,
            ParameterTreeLeafValueDecodingErrorV1::EmptyValueTokens("mode".to_string())
        );
    }

    #[test]
    fn duplicate_leaf_names_fail_closed() {
        let t = tree(branch(
            "root",
            vec![
                branch("sub", vec![leaf("gain", &["1.0"])]),
                leaf("gain", &["2.0"]),
            ],
        ));
        let types = type_map(&[("gain", AmiParameterTypeV1::Float)]);
        let error = decode_parameter_tree_leaf_values_v1(&t, &types).unwrap_err();
        assert_eq!(
            error,
            ParameterTreeLeafValueDecodingErrorV1::DuplicateLeafName("gain".to_string())
        );
    }
}
