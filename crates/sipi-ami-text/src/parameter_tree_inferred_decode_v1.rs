//! AMI parameter tree inferred decoding core (P4B-02b41).
//!
//! Composes the leaf value type inference core (P4B-02b33) and the leaf value
//! decoding core (P4B-02b37) into one fail-closed pass:
//! `decode_parameter_tree_with_inferred_types_v1` infers one
//! `AmiParameterTypeV1` per leaf from its own value tokens, then decodes the
//! single value token of every leaf into a typed Rust value. This is the
//! end-to-end consumption path for an untyped AMI parameter tree: parse ->
//! tree -> infer -> decode, with no caller-supplied type map. Both underlying
//! cores are reused verbatim; errors are reported wrapped by stage
//! (Inference vs Decoding).

use std::collections::BTreeMap;

use crate::{
    decode_parameter_tree_leaf_values_v1, infer_parameter_tree_leaf_types_v1,
    AmiParameterTreeV1, AmiParameterTypeV1, DecodedLeafValueV1,
    ParameterTreeLeafValueDecodingErrorV1, ParameterTreeTypeInferenceErrorV1,
};

/// Scope policy for the parameter tree inferred decoding core.
pub const PARAMETER_TREE_INFERRED_DECODE_POLICY_V1: &str =
    "sipi.p4b-02b41.parameter-tree-inferred-decode-v1.infer-then-decode";

/// Fail-closed errors while inferring and decoding leaf values of a tree.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterTreeInferredDecodingErrorV1 {
    /// The inference stage (P4B-02b33) failed.
    Inference(ParameterTreeTypeInferenceErrorV1),
    /// The decoding stage (P4B-02b37) failed.
    Decoding(ParameterTreeLeafValueDecodingErrorV1),
}

/// Outcome of a successful inferred decoding pass.
#[derive(Clone, Debug, PartialEq)]
pub struct ParameterTreeInferredDecodingV1 {
    leaves_decoded: usize,
    leaf_types: BTreeMap<String, AmiParameterTypeV1>,
    values: BTreeMap<String, DecodedLeafValueV1>,
}

impl ParameterTreeInferredDecodingV1 {
    pub fn leaves_decoded(&self) -> usize {
        self.leaves_decoded
    }

    pub fn leaf_types(&self) -> &BTreeMap<String, AmiParameterTypeV1> {
        &self.leaf_types
    }

    pub fn values(&self) -> &BTreeMap<String, DecodedLeafValueV1> {
        &self.values
    }
}

/// Infer one type per leaf, then decode every leaf's single value token.
///
/// Returns the decoded count, the inferred type map, and the typed values, or
/// fails closed at the first violating leaf. Inference errors surface as
/// `Inference(...)`; decoding errors (only possible for multi-token leaves,
/// since inference already guarantees single-token type validity) surface as
/// `Decoding(...)`. Traversal order is canonical (branch children byte-wise,
/// depth first).
pub fn decode_parameter_tree_with_inferred_types_v1(
    tree: &AmiParameterTreeV1,
) -> Result<ParameterTreeInferredDecodingV1, ParameterTreeInferredDecodingErrorV1> {
    let inference = infer_parameter_tree_leaf_types_v1(tree)
        .map_err(ParameterTreeInferredDecodingErrorV1::Inference)?;
    let decoding = decode_parameter_tree_leaf_values_v1(tree, inference.leaf_types())
        .map_err(ParameterTreeInferredDecodingErrorV1::Decoding)?;
    Ok(ParameterTreeInferredDecodingV1 {
        leaves_decoded: decoding.leaves_decoded(),
        leaf_types: inference.leaf_types().clone(),
        values: decoding.values().clone(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::AmiParameterTreeNodeV1;

    fn leaf(name: &str, tokens: &[&str]) -> AmiParameterTreeNodeV1 {
        crate::AmiParameterTreeNodeV1::Leaf {
            name: name.to_string(),
            value_tokens: tokens.iter().map(|s| s.to_string()).collect(),
        }
    }

    fn branch(name: &str, children: Vec<AmiParameterTreeNodeV1>) -> AmiParameterTreeNodeV1 {
        crate::AmiParameterTreeNodeV1::Branch {
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
    fn infers_and_decodes_mixed_types() {
        let t = tree(branch(
            "root",
            vec![
                leaf("gain", &["0.5"]),
                leaf("steps", &["7"]),
                leaf("enabled", &["True"]),
                leaf("mode", &["fast"]),
            ],
        ));
        let result = decode_parameter_tree_with_inferred_types_v1(&t).expect("decoded");
        assert_eq!(result.leaves_decoded(), 4);
        assert_eq!(
            result.leaf_types().get("gain"),
            Some(&AmiParameterTypeV1::Float)
        );
        assert_eq!(
            result.leaf_types().get("steps"),
            Some(&AmiParameterTypeV1::Integer)
        );
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
    }

    #[test]
    fn multi_token_leaf_fails_at_decoding_stage() {
        let t = tree(branch("root", vec![leaf("a", &["1", "2"])]));
        let error = decode_parameter_tree_with_inferred_types_v1(&t).unwrap_err();
        assert_eq!(
            error,
            ParameterTreeInferredDecodingErrorV1::Decoding(
                ParameterTreeLeafValueDecodingErrorV1::MultiTokenValue {
                    leaf: "a".to_string(),
                    token_count: 2,
                }
            )
        );
    }

    #[test]
    fn conflicting_tokens_fail_at_inference_stage() {
        let t = tree(branch("root", vec![leaf("mix", &["1", "2.5"])]));
        let error = decode_parameter_tree_with_inferred_types_v1(&t).unwrap_err();
        assert_eq!(
            error,
            ParameterTreeInferredDecodingErrorV1::Inference(
                ParameterTreeTypeInferenceErrorV1::ConflictingTokenTypes {
                    leaf: "mix".to_string(),
                    types: vec!["Float".to_string(), "Integer".to_string()],
                }
            )
        );
    }

    #[test]
    fn empty_tokens_fail_at_inference_stage() {
        let t = tree(branch("root", vec![leaf("mode", &[])]));
        let error = decode_parameter_tree_with_inferred_types_v1(&t).unwrap_err();
        assert_eq!(
            error,
            ParameterTreeInferredDecodingErrorV1::Inference(
                ParameterTreeTypeInferenceErrorV1::EmptyValueTokens("mode".to_string())
            )
        );
    }

    #[test]
    fn duplicate_leaf_names_fail_at_inference_stage() {
        let t = tree(branch(
            "root",
            vec![
                branch("sub", vec![leaf("gain", &["1"])]),
                leaf("gain", &["2"]),
            ],
        ));
        let error = decode_parameter_tree_with_inferred_types_v1(&t).unwrap_err();
        assert_eq!(
            error,
            ParameterTreeInferredDecodingErrorV1::Inference(
                ParameterTreeTypeInferenceErrorV1::DuplicateLeafName("gain".to_string())
            )
        );
    }

    #[test]
    fn list_token_infers_and_decodes() {
        let t = tree(branch("root", vec![leaf("l", &["(1, 2)"])]));
        let result = decode_parameter_tree_with_inferred_types_v1(&t).expect("decoded");
        assert_eq!(
            result.leaf_types().get("l"),
            Some(&AmiParameterTypeV1::List)
        );
        assert_eq!(
            result.values().get("l"),
            Some(&DecodedLeafValueV1::List(vec!["1".to_string(), "2".to_string()]))
        );
    }
}
