//! AMI parameter tree S-expression formatter core (P4B-02b9).
//!
//! Formats typed `AmiParameterTreeV1` hierarchies (P4B-02b7) back into canonical
//! parenthesized S-expression string representations (`format_parameter_tree_v1`).
//! Fail-closed: empty tree lists or invalid node structures are strictly rejected.

use crate::parameter_trees_v1::{AmiParameterTreeNodeV1, AmiParameterTreeV1};

/// Scope policy for the parameter tree formatter core.
pub const PARAMETER_TREE_FORMATTER_POLICY_V1: &str =
    "sipi.p4b-02b9.parameter-tree-formatter-v1.tree-to-sexpr";

/// Fail-closed errors during AMI parameter tree formatting.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterTreeFormatterErrorV1 {
    EmptyTreeList,
}

fn format_node(node: &AmiParameterTreeNodeV1, indent: usize, out: &mut String) {
    let pad = " ".repeat(indent);
    match node {
        AmiParameterTreeNodeV1::Branch { name, children } => {
            out.push_str(&format!("{pad}({name}"));
            for child in children.values() {
                out.push('\n');
                format_node(child, indent + 2, out);
            }
            out.push(')');
        }
        AmiParameterTreeNodeV1::Leaf { name, value_tokens } => {
            if value_tokens.is_empty() {
                out.push_str(&format!("{pad}({name})"));
            } else {
                let vals = value_tokens.join(" ");
                out.push_str(&format!("{pad}({name} {vals})"));
            }
        }
    }
}

/// Format a list of parameter trees into a canonical parenthesized string.
pub fn format_parameter_trees_v1(
    trees: &[AmiParameterTreeV1],
) -> Result<String, ParameterTreeFormatterErrorV1> {
    if trees.is_empty() {
        return Err(ParameterTreeFormatterErrorV1::EmptyTreeList);
    }
    let mut out = String::new();
    for (i, tree) in trees.iter().enumerate() {
        if i > 0 {
            out.push('\n');
        }
        format_node(tree.root_node(), 0, &mut out);
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::parameter_trees_v1::build_parameter_trees_v1;
    use crate::{ParseLimitsV1, parse_ami_text_v1};

    fn limits() -> ParseLimitsV1 {
        ParseLimitsV1::try_new(1024, 16, 64, 128).unwrap()
    }

    #[test]
    fn policy_fixed() {
        assert_eq!(
            PARAMETER_TREE_FORMATTER_POLICY_V1,
            "sipi.p4b-02b9.parameter-tree-formatter-v1.tree-to-sexpr"
        );
    }

    #[test]
    fn formats_tree_hierarchy() {
        let doc = parse_ami_text_v1(
            b"(Reserved_Parameters (tx_swing Float 0.5) (dfe (tap_1 Integer 2)))",
            limits(),
        )
        .expect("parse");
        let trees = build_parameter_trees_v1(&doc).expect("build");
        let formatted = format_parameter_trees_v1(&trees).expect("format");
        assert!(formatted.contains("(Reserved_Parameters"));
        assert!(formatted.contains("  (tx_swing Float 0.5)"));
        assert!(formatted.contains("  (dfe"));
        assert!(formatted.contains("    (tap_1 Integer 2)"));
    }

    #[test]
    fn rejects_empty_tree_list() {
        assert_eq!(
            format_parameter_trees_v1(&[]),
            Err(ParameterTreeFormatterErrorV1::EmptyTreeList)
        );
    }
}
