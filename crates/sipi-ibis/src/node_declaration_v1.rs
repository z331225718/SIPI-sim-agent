//! Typed IBIS [Node Declarations] core (P4A-03n).
//!
//! Lifts and validates IBIS [Node Declarations] entries (internal node name
//! and optional signal name association) into typed, clean-room structures.
//! Fail-closed: empty node names, non-ASCII characters, or invalid name spellings
//! are strictly rejected.

/// Scope policy for the typed node declaration core.
pub const NODE_DECLARATION_POLICY_V1: &str =
    "sipi.p4a-03n.node-declaration-v1.typed-node";

/// Fail-closed errors during node declaration lifting.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum NodeDeclarationErrorV1 {
    EmptyNodeName,
    NonAsciiNodeName,
    InvalidNodeName,
}

/// A typed IBIS [Node Declarations] entry.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct TypedNodeDeclarationV1 {
    node_name: String,
    signal_name: Option<String>,
}

impl TypedNodeDeclarationV1 {
    pub fn try_new(
        node_name: impl Into<String>,
        signal_name: Option<impl Into<String>>,
    ) -> Result<Self, NodeDeclarationErrorV1> {
        let name = node_name.into();
        let trimmed = name.trim();
        if trimmed.is_empty() {
            return Err(NodeDeclarationErrorV1::EmptyNodeName);
        }
        if !trimmed.is_ascii() {
            return Err(NodeDeclarationErrorV1::NonAsciiNodeName);
        }
        if !trimmed
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-' || c == '.')
        {
            return Err(NodeDeclarationErrorV1::InvalidNodeName);
        }

        let sig = signal_name.and_then(|s| {
            let t = s.into().trim().to_string();
            if t.is_empty() {
                None
            } else {
                Some(t)
            }
        });

        if let Some(ref s) = sig {
            if !s.is_ascii() {
                return Err(NodeDeclarationErrorV1::NonAsciiNodeName);
            }
        }

        Ok(Self {
            node_name: trimmed.to_string(),
            signal_name: sig,
        })
    }

    pub fn node_name(&self) -> &str {
        &self.node_name
    }

    pub fn signal_name(&self) -> Option<&str> {
        self.signal_name.as_deref()
    }
}

/// Lift one node declaration entry.
pub fn lift_node_declaration_v1(
    node_name: &str,
    signal_name: Option<&str>,
) -> Result<TypedNodeDeclarationV1, NodeDeclarationErrorV1> {
    TypedNodeDeclarationV1::try_new(node_name, signal_name)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn policy_fixed() {
        assert_eq!(
            NODE_DECLARATION_POLICY_V1,
            "sipi.p4a-03n.node-declaration-v1.typed-node"
        );
    }

    #[test]
    fn valid_full_node_declaration() {
        let node = lift_node_declaration_v1("INT_NODE_1", Some("SIG_CLK")).expect("lift");
        assert_eq!(node.node_name(), "INT_NODE_1");
        assert_eq!(node.signal_name(), Some("SIG_CLK"));
    }

    #[test]
    fn valid_minimal_node_declaration() {
        let node = lift_node_declaration_v1("NODE_A", None).expect("lift");
        assert_eq!(node.node_name(), "NODE_A");
        assert_eq!(node.signal_name(), None);
    }

    #[test]
    fn rejects_empty_node_name() {
        assert_eq!(
            lift_node_declaration_v1("", Some("SIG")),
            Err(NodeDeclarationErrorV1::EmptyNodeName)
        );
        assert_eq!(
            lift_node_declaration_v1("   ", None),
            Err(NodeDeclarationErrorV1::EmptyNodeName)
        );
    }

    #[test]
    fn rejects_non_ascii_name() {
        assert_eq!(
            lift_node_declaration_v1("节点1", None),
            Err(NodeDeclarationErrorV1::NonAsciiNodeName)
        );
    }

    #[test]
    fn rejects_invalid_name_characters() {
        assert_eq!(
            lift_node_declaration_v1("NODE #1", None),
            Err(NodeDeclarationErrorV1::InvalidNodeName)
        );
    }
}
