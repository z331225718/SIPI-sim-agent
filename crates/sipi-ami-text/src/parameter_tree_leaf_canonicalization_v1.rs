//! AMI parameter tree leaf spelling canonicalization core (P4B-02b78).
//!
//! Produces the canonical form of an `AmiParameterTreeV1` by applying
//! `canonicalize_parameter_value_spelling_v1` (02b75) to every leaf that is a
//! well-formed typed parameter form: value token lists of exactly two tokens
//! whose first token is a known type token (Float/Integer/Boolean/String/List)
//! and whose value passes `AmiParameterValueV1::try_new` (02b1). Integer
//! spellings become the parsed i64 in decimal (`007` -> `7`), List spellings
//! get trimmed items joined with `", "` (`(a,b,c)` -> `(a, b, c)`), and
//! Boolean/Float/String stay raw. List values in tree text are quoted tokens
//! (per the P4B-02b0 raw-byte binding: quotes are structural, the inner
//! spelling is the value); the canonical List spelling keeps the quotes.
//! All other leaves (non-typed forms, multi-token leaves, invalid values) are
//! left untouched. This is the tree-level companion of 02b75 (value) and
//! 02b77 (profile): the canonical spelling of the document tree itself.
//!
//! Fail-closed: canonicalization is total (no error path); only leaves that
//! are valid typed forms are rewritten, everything else is preserved as-is;
//! the canonicalized count reports how many leaves changed.

use std::collections::BTreeMap;

use crate::{
    canonicalize_parameter_value_spelling_v1, AmiParameterTreeV1, AmiParameterTreeNodeV1,
    AmiParameterTypeV1, AmiParameterValueV1,
};

/// Explicit scope policy of this slice: canonical leaf spellings of a tree.
pub const PARAMETER_TREE_LEAF_CANONICALIZATION_POLICY_V1: &str =
    "sipi.p4b-02b78.parameter-tree-leaf-canonicalization-v1.canonical-leaf-spellings";

/// Outcome of canonicalizing one parameter tree's leaf spellings.
#[derive(Clone, Debug, PartialEq)]
pub struct ParameterTreeLeafCanonicalizationV1 {
    leaves: usize,
    canonicalized: usize,
    tree: AmiParameterTreeV1,
}

impl ParameterTreeLeafCanonicalizationV1 {
    /// Total number of leaves in the tree.
    pub fn leaves(&self) -> usize {
        self.leaves
    }

    /// Number of leaves whose value token changed.
    pub fn canonicalized(&self) -> usize {
        self.canonicalized
    }

    /// The canonicalized tree.
    pub fn tree(&self) -> &AmiParameterTreeV1 {
        &self.tree
    }
}

/// Strip surrounding quotes from a token when present. Quoted tokens are the
/// tree-text spelling for List values and quoted strings (raw-byte binding).
fn unwrap_quoted(token: &str) -> (String, bool) {
    if token.len() >= 2 && token.starts_with('"') && token.ends_with('"') {
        (token[1..token.len() - 1].to_string(), true)
    } else {
        (token.to_string(), false)
    }
}

fn canonicalize_node(
    node: &AmiParameterTreeNodeV1,
    leaves: &mut usize,
    canonicalized: &mut usize,
) -> AmiParameterTreeNodeV1 {
    match node {
        AmiParameterTreeNodeV1::Branch { name, children } => {
            let mut new_children = BTreeMap::new();
            for (child_name, child) in children {
                new_children.insert(
                    child_name.clone(),
                    canonicalize_node(child, leaves, canonicalized),
                );
            }
            AmiParameterTreeNodeV1::Branch {
                name: name.clone(),
                children: new_children,
            }
        }
        AmiParameterTreeNodeV1::Leaf { name, value_tokens } => {
            *leaves += 1;
            if value_tokens.len() == 2 {
                let type_token = &value_tokens[0];
                if let Some(_parameter_type) = AmiParameterTypeV1::from_token(type_token) {
                    let (value_token, quoted) = unwrap_quoted(&value_tokens[1]);
                    if let Ok(parameter) =
                        AmiParameterValueV1::try_new(name, type_token, &value_token)
                    {
                        let canonical =
                            canonicalize_parameter_value_spelling_v1(&parameter);
                        let emitted = if quoted {
                            format!("\"{}\"", canonical)
                        } else {
                            canonical
                        };
                        if emitted != value_tokens[1] {
                            *canonicalized += 1;
                            return AmiParameterTreeNodeV1::Leaf {
                                name: name.clone(),
                                value_tokens: vec![type_token.clone(), emitted],
                            };
                        }
                    }
                }
            }
            AmiParameterTreeNodeV1::Leaf {
                name: name.clone(),
                value_tokens: value_tokens.clone(),
            }
        }
    }
}

/// Canonicalize every typed-form leaf spelling of a parameter tree.
pub fn canonicalize_parameter_tree_leaf_spellings_v1(
    tree: &AmiParameterTreeV1,
) -> ParameterTreeLeafCanonicalizationV1 {
    let mut leaves = 0usize;
    let mut canonicalized = 0usize;
    let root = canonicalize_node(tree.root_node(), &mut leaves, &mut canonicalized);
    ParameterTreeLeafCanonicalizationV1 {
        leaves,
        canonicalized,
        tree: AmiParameterTreeV1::new(tree.root_name(), root),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{build_parameter_trees_v1, parse_ami_text_v1, ParseLimitsV1};

    fn tree(text: &str) -> AmiParameterTreeV1 {
        let limits = ParseLimitsV1::try_new(8 * 1024 * 1024, 64, 4096, 4096).expect("limits");
        let doc = parse_ami_text_v1(text.as_bytes(), limits).expect("parse");
        let trees = build_parameter_trees_v1(&doc).expect("build");
        trees.into_iter().next().expect("one tree")
    }

    fn leaf_tokens(result: &ParameterTreeLeafCanonicalizationV1, path: &str) -> Vec<String> {
        let mut current = result.tree().root_node();
        for segment in path.split('/') {
            match current {
                AmiParameterTreeNodeV1::Branch { children, .. } => {
                    current = &children[segment];
                }
                AmiParameterTreeNodeV1::Leaf { .. } => panic!("not a branch"),
            }
        }
        match current {
            AmiParameterTreeNodeV1::Leaf { value_tokens, .. } => value_tokens.clone(),
            AmiParameterTreeNodeV1::Branch { .. } => panic!("not a leaf"),
        }
    }

    #[test]
    fn typed_integer_leaf_is_canonicalized() {
        let t = tree("(root (steps Integer 007))");
        let result = canonicalize_parameter_tree_leaf_spellings_v1(&t);
        assert_eq!(result.leaves(), 1);
        assert_eq!(result.canonicalized(), 1);
        assert_eq!(
            leaf_tokens(&result, "steps"),
            vec!["Integer".to_string(), "7".to_string()]
        );
    }

    #[test]
    fn typed_list_leaf_is_canonicalized() {
        let t = tree("(root (channels List \"(a,b,c)\"))");
        let result = canonicalize_parameter_tree_leaf_spellings_v1(&t);
        assert_eq!(result.canonicalized(), 1);
        assert_eq!(
            leaf_tokens(&result, "channels"),
            vec!["List".to_string(), "\"(a, b, c)\"".to_string()]
        );
    }

    #[test]
    fn float_string_boolean_leaves_stay_raw() {
        let t = tree("(root (gain Float 0.50) (mode String Linear) (on Boolean True))");
        let result = canonicalize_parameter_tree_leaf_spellings_v1(&t);
        assert_eq!(result.leaves(), 3);
        assert_eq!(result.canonicalized(), 0);
        assert_eq!(
            leaf_tokens(&result, "gain"),
            vec!["Float".to_string(), "0.50".to_string()]
        );
        assert_eq!(
            leaf_tokens(&result, "mode"),
            vec!["String".to_string(), "Linear".to_string()]
        );
        assert_eq!(
            leaf_tokens(&result, "on"),
            vec!["Boolean".to_string(), "True".to_string()]
        );
    }

    #[test]
    fn non_typed_and_invalid_leaves_are_untouched() {
        let t = tree("(root (plain 5) (raw x y z) (bad Integer abc))");
        let result = canonicalize_parameter_tree_leaf_spellings_v1(&t);
        assert_eq!(result.leaves(), 3);
        assert_eq!(result.canonicalized(), 0);
        assert_eq!(leaf_tokens(&result, "plain"), vec!["5".to_string()]);
        assert_eq!(
            leaf_tokens(&result, "raw"),
            vec!["x".to_string(), "y".to_string(), "z".to_string()]
        );
        assert_eq!(
            leaf_tokens(&result, "bad"),
            vec!["Integer".to_string(), "abc".to_string()]
        );
    }

    #[test]
    fn nested_leaves_are_canonicalized_across_levels() {
        let t = tree("(root (sub (steps Integer 007)) (gain Float 0.5))");
        let result = canonicalize_parameter_tree_leaf_spellings_v1(&t);
        assert_eq!(result.leaves(), 2);
        assert_eq!(result.canonicalized(), 1);
        assert_eq!(
            leaf_tokens(&result, "sub/steps"),
            vec!["Integer".to_string(), "7".to_string()]
        );
        assert_eq!(
            leaf_tokens(&result, "gain"),
            vec!["Float".to_string(), "0.5".to_string()]
        );
    }

    #[test]
    fn canonicalization_preserves_structure() {
        let t = tree("(root (sub (steps Integer 007) (channels List \"(a,b)\")) (on Boolean True))");
        let result = canonicalize_parameter_tree_leaf_spellings_v1(&t);
        assert_eq!(result.leaves(), 3);
        assert_eq!(result.canonicalized(), 2);
        assert_eq!(
            leaf_tokens(&result, "sub/channels"),
            vec!["List".to_string(), "\"(a, b)\"".to_string()]
        );
        assert_eq!(
            leaf_tokens(&result, "on"),
            vec!["Boolean".to_string(), "True".to_string()]
        );
    }
}
