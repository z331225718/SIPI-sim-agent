//! AMI parameter tree structure validator core (P4B-02b10).
//!
//! Validates typed `AmiParameterTreeV1` hierarchies (P4B-02b7) for structural invariants
//! (depth limits, maximum leaf token counts, and node name syntax constraints).
//! Fail-closed: exceeding depth limits, exceeding max leaf tokens, or invalid node names
//! are strictly rejected.

use crate::parameter_trees_v1::{AmiParameterTreeNodeV1, AmiParameterTreeV1};

/// Scope policy for the parameter tree validator core.
pub const PARAMETER_TREE_VALIDATOR_POLICY_V1: &str =
    "sipi.p4b-02b10.parameter-tree-validator-v1.tree-invariants-validation";

/// Fail-closed errors during AMI parameter tree validation.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterTreeValidatorErrorV1 {
    EmptyTreeList,
    ExceededMaxDepth { max_allowed: usize, actual: usize },
    ExceededMaxLeafTokens { max_allowed: usize, actual: usize },
    InvalidNodeName(String),
}

/// Structural limits for AMI parameter tree validation.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct TreeValidationLimitsV1 {
    max_depth: usize,
    max_leaf_tokens: usize,
}

impl TreeValidationLimitsV1 {
    pub fn try_new(max_depth: usize, max_leaf_tokens: usize) -> Option<Self> {
        if max_depth == 0 || max_leaf_tokens == 0 {
            None
        } else {
            Some(Self {
                max_depth,
                max_leaf_tokens,
            })
        }
    }

    pub const fn max_depth(self) -> usize {
        self.max_depth
    }

    pub const fn max_leaf_tokens(self) -> usize {
        self.max_leaf_tokens
    }
}

impl Default for TreeValidationLimitsV1 {
    fn default() -> Self {
        Self {
            max_depth: 32,
            max_leaf_tokens: 1024,
        }
    }
}

fn is_valid_identifier(name: &str) -> bool {
    let trimmed = name.trim();
    !trimmed.is_empty()
        && trimmed.is_ascii()
        && trimmed
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-' || c == '.')
}

fn validate_node(
    node: &AmiParameterTreeNodeV1,
    current_depth: usize,
    limits: TreeValidationLimitsV1,
) -> Result<(), ParameterTreeValidatorErrorV1> {
    if current_depth > limits.max_depth() {
        return Err(ParameterTreeValidatorErrorV1::ExceededMaxDepth {
            max_allowed: limits.max_depth(),
            actual: current_depth,
        });
    }

    if !is_valid_identifier(node.name()) {
        return Err(ParameterTreeValidatorErrorV1::InvalidNodeName(
            node.name().to_string(),
        ));
    }

    match node {
        AmiParameterTreeNodeV1::Branch { children, .. } => {
            for child in children.values() {
                validate_node(child, current_depth + 1, limits)?;
            }
        }
        AmiParameterTreeNodeV1::Leaf { value_tokens, .. } => {
            if value_tokens.len() > limits.max_leaf_tokens() {
                return Err(ParameterTreeValidatorErrorV1::ExceededMaxLeafTokens {
                    max_allowed: limits.max_leaf_tokens(),
                    actual: value_tokens.len(),
                });
            }
        }
    }
    Ok(())
}

/// Validate structural invariants over a list of parameter trees.
pub fn validate_parameter_trees_v1(
    trees: &[AmiParameterTreeV1],
    limits: TreeValidationLimitsV1,
) -> Result<(), ParameterTreeValidatorErrorV1> {
    if trees.is_empty() {
        return Err(ParameterTreeValidatorErrorV1::EmptyTreeList);
    }
    for tree in trees {
        validate_node(tree.root_node(), 1, limits)?;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::parameter_trees_v1::build_parameter_trees_v1;
    use crate::{ParseLimitsV1, parse_ami_text_v1};

    fn parse_limits() -> ParseLimitsV1 {
        ParseLimitsV1::try_new(1024, 16, 64, 128).unwrap()
    }

    #[test]
    fn policy_fixed() {
        assert_eq!(
            PARAMETER_TREE_VALIDATOR_POLICY_V1,
            "sipi.p4b-02b10.parameter-tree-validator-v1.tree-invariants-validation"
        );
    }

    #[test]
    fn validates_normal_tree() {
        let doc = parse_ami_text_v1(
            b"(Reserved_Parameters (tx_swing Float 0.5) (dfe (tap_1 Integer 2)))",
            parse_limits(),
        )
        .expect("parse");
        let trees = build_parameter_trees_v1(&doc).expect("build");
        assert!(validate_parameter_trees_v1(&trees, TreeValidationLimitsV1::default()).is_ok());
    }

    #[test]
    fn rejects_empty_tree_list() {
        assert_eq!(
            validate_parameter_trees_v1(&[], TreeValidationLimitsV1::default()),
            Err(ParameterTreeValidatorErrorV1::EmptyTreeList)
        );
    }

    #[test]
    fn rejects_exceeded_max_depth() {
        let doc =
            parse_ami_text_v1(b"(root (b1 (b2 (b3 (leaf 1)))))", parse_limits()).expect("parse");
        let trees = build_parameter_trees_v1(&doc).expect("build");
        let strict_limits = TreeValidationLimitsV1::try_new(2, 1024).unwrap();
        assert!(matches!(
            validate_parameter_trees_v1(&trees, strict_limits),
            Err(ParameterTreeValidatorErrorV1::ExceededMaxDepth { .. })
        ));
    }

    #[test]
    fn rejects_exceeded_max_leaf_tokens() {
        let doc = parse_ami_text_v1(b"(root (leaf 1 2 3 4 5))", parse_limits()).expect("parse");
        let trees = build_parameter_trees_v1(&doc).expect("build");
        let strict_limits = TreeValidationLimitsV1::try_new(10, 2).unwrap();
        assert!(matches!(
            validate_parameter_trees_v1(&trees, strict_limits),
            Err(ParameterTreeValidatorErrorV1::ExceededMaxLeafTokens { .. })
        ));
    }
}
