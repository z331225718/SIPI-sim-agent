//! AMI parameter tree hierarchy core (P4B-02b7).
//!
//! Builds typed, clean-room AMI parameter hierarchy trees (`AmiParameterTreeV1`)
//! from a sequence of root `AmiTextListV1` AST forms.
//! Fail-closed: empty documents, invalid branch node spellings, or duplicate child branch
//! names under the same node are strictly rejected.

use std::collections::BTreeMap;

use crate::{AmiTextDocumentV1, AmiTextListV1, AmiTextNodeV1};

/// Scope policy for the parameter trees core.
pub const PARAMETER_TREES_POLICY_V1: &str =
    "sipi.p4b-02b7.parameter-trees-v1.ast-forms-to-tree";

/// Fail-closed errors during AMI parameter tree construction.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterTreesErrorV1 {
    EmptyDocument,
    InvalidNodeName,
    DuplicateChild(String),
    NoValidTrees,
}

/// A node in an AMI parameter tree hierarchy.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum AmiParameterTreeNodeV1 {
    Branch {
        name: String,
        children: BTreeMap<String, AmiParameterTreeNodeV1>,
    },
    Leaf {
        name: String,
        value_tokens: Vec<String>,
    },
}

impl AmiParameterTreeNodeV1 {
    pub fn name(&self) -> &str {
        match self {
            Self::Branch { name, .. } => name,
            Self::Leaf { name, .. } => name,
        }
    }
}

/// A typed AMI parameter tree root.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct AmiParameterTreeV1 {
    root_name: String,
    root_node: AmiParameterTreeNodeV1,
}

impl AmiParameterTreeV1 {
    pub fn new(root_name: impl Into<String>, root_node: AmiParameterTreeNodeV1) -> Self {
        Self {
            root_name: root_name.into(),
            root_node,
        }
    }

    pub fn root_name(&self) -> &str {
        &self.root_name
    }

    pub fn root_node(&self) -> &AmiParameterTreeNodeV1 {
        &self.root_node
    }
}

fn item_spelling(node: &AmiTextNodeV1) -> Option<&str> {
    match node {
        AmiTextNodeV1::Atom(token) | AmiTextNodeV1::Quoted(token) => Some(token.spelling()),
        AmiTextNodeV1::List(_) => None,
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

fn build_tree_node(list: &AmiTextListV1) -> Result<AmiParameterTreeNodeV1, ParameterTreesErrorV1> {
    let items = list.items();
    if items.is_empty() {
        return Err(ParameterTreesErrorV1::InvalidNodeName);
    }

    let head_spelling = item_spelling(&items[0]).ok_or(ParameterTreesErrorV1::InvalidNodeName)?;
    if !is_valid_identifier(head_spelling) {
        return Err(ParameterTreesErrorV1::InvalidNodeName);
    }

    let name = head_spelling.trim().to_string();

    // If remaining items are all atoms/quoted (no nested lists), treat as Leaf
    let has_sublist = items[1..].iter().any(|item| matches!(item, AmiTextNodeV1::List(_)));

    if !has_sublist {
        let mut tokens = Vec::new();
        for item in &items[1..] {
            let tok = item_spelling(item).ok_or(ParameterTreesErrorV1::InvalidNodeName)?;
            tokens.push(tok.to_string());
        }
        Ok(AmiParameterTreeNodeV1::Leaf {
            name,
            value_tokens: tokens,
        })
    } else {
        let mut children = BTreeMap::new();
        for item in &items[1..] {
            if let AmiTextNodeV1::List(sublist) = item {
                let child = build_tree_node(sublist)?;
                let cname = child.name().to_string();
                if children.insert(cname.clone(), child).is_some() {
                    return Err(ParameterTreesErrorV1::DuplicateChild(cname));
                }
            }
        }
        Ok(AmiParameterTreeNodeV1::Branch { name, children })
    }
}

/// Build typed AMI parameter trees from an AST document.
pub fn build_parameter_trees_v1(
    document: &AmiTextDocumentV1,
) -> Result<Vec<AmiParameterTreeV1>, ParameterTreesErrorV1> {
    if document.forms().is_empty() {
        return Err(ParameterTreesErrorV1::EmptyDocument);
    }
    let mut trees = Vec::new();
    for form in document.forms() {
        let node = build_tree_node(form)?;
        trees.push(AmiParameterTreeV1 {
            root_name: node.name().to_string(),
            root_node: node,
        });
    }
    if trees.is_empty() {
        return Err(ParameterTreesErrorV1::NoValidTrees);
    }
    Ok(trees)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{parse_ami_text_v1, ParseLimitsV1};

    fn limits() -> ParseLimitsV1 {
        ParseLimitsV1::try_new(1024, 16, 64, 128).unwrap()
    }

    #[test]
    fn policy_fixed() {
        assert_eq!(
            PARAMETER_TREES_POLICY_V1,
            "sipi.p4b-02b7.parameter-trees-v1.ast-forms-to-tree"
        );
    }

    #[test]
    fn builds_valid_tree_hierarchy() {
        let doc = parse_ami_text_v1(
            b"(Reserved_Parameters (tx_swing Float 0.5) (dfe (tap_1 Integer 2)))",
            limits(),
        )
        .expect("parse");
        let trees = build_parameter_trees_v1(&doc).expect("build");
        assert_eq!(trees.len(), 1);
        assert_eq!(trees[0].root_name(), "Reserved_Parameters");
    }

    #[test]
    fn rejects_empty_document() {
        let doc = AmiTextDocumentV1 { forms: Vec::new() };
        assert_eq!(
            build_parameter_trees_v1(&doc),
            Err(ParameterTreesErrorV1::EmptyDocument)
        );
    }

    #[test]
    fn rejects_duplicate_child_names() {
        let doc = parse_ami_text_v1(
            b"(root (child_a 1) (child_a 2))",
            limits(),
        )
        .expect("parse");
        assert_eq!(
            build_parameter_trees_v1(&doc),
            Err(ParameterTreesErrorV1::DuplicateChild("child_a".to_string()))
        );
    }
}
