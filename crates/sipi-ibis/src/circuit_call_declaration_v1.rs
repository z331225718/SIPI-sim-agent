//! Typed IBIS [Circuit Call] & Port-Node Mapping core (P4A-03m).
//!
//! Lifts and validates IBIS [Circuit Call] declarations (external circuit name
//! and port-to-node mapping pairs) into typed, clean-room structures.
//! Fail-closed: empty circuit names, non-ASCII characters, invalid name spellings,
//! empty port mappings, or duplicate port names are strictly rejected.

use std::collections::BTreeSet;

/// Scope policy for the typed circuit call declaration core.
pub const CIRCUIT_CALL_DECLARATION_POLICY_V1: &str =
    "sipi.p4a-03m.circuit-call-declaration-v1.typed-circuit-call";

/// Fail-closed errors during circuit call declaration lifting.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum CircuitCallDeclarationErrorV1 {
    EmptyCircuitName,
    NonAsciiName,
    InvalidName,
    EmptyPortMappings,
    DuplicatePortName(String),
}

/// One port-to-node mapping pair inside a [Circuit Call] block.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct PortMapV1 {
    port_name: String,
    node_name: String,
}

impl PortMapV1 {
    pub fn new(port_name: impl Into<String>, node_name: impl Into<String>) -> Self {
        Self {
            port_name: port_name.into().trim().to_string(),
            node_name: node_name.into().trim().to_string(),
        }
    }

    pub fn port_name(&self) -> &str {
        &self.port_name
    }

    pub fn node_name(&self) -> &str {
        &self.node_name
    }
}

/// A typed IBIS [Circuit Call] declaration.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct TypedCircuitCallDeclarationV1 {
    circuit_name: String,
    port_mappings: Vec<PortMapV1>,
}

impl TypedCircuitCallDeclarationV1 {
    pub fn try_new(
        circuit_name: impl Into<String>,
        port_mappings: Vec<PortMapV1>,
    ) -> Result<Self, CircuitCallDeclarationErrorV1> {
        let name = circuit_name.into();
        let trimmed = name.trim();
        if trimmed.is_empty() {
            return Err(CircuitCallDeclarationErrorV1::EmptyCircuitName);
        }
        if !trimmed.is_ascii() {
            return Err(CircuitCallDeclarationErrorV1::NonAsciiName);
        }
        if !trimmed
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-' || c == '.')
        {
            return Err(CircuitCallDeclarationErrorV1::InvalidName);
        }
        if port_mappings.is_empty() {
            return Err(CircuitCallDeclarationErrorV1::EmptyPortMappings);
        }

        let mut seen = BTreeSet::new();
        for pm in &port_mappings {
            let p = pm.port_name();
            let n = pm.node_name();
            if p.is_empty() || n.is_empty() {
                return Err(CircuitCallDeclarationErrorV1::EmptyCircuitName);
            }
            if !p.is_ascii() || !n.is_ascii() {
                return Err(CircuitCallDeclarationErrorV1::NonAsciiName);
            }
            if !seen.insert(p.to_string()) {
                return Err(CircuitCallDeclarationErrorV1::DuplicatePortName(p.to_string()));
            }
        }

        Ok(Self {
            circuit_name: trimmed.to_string(),
            port_mappings,
        })
    }

    pub fn circuit_name(&self) -> &str {
        &self.circuit_name
    }

    pub fn port_mappings(&self) -> &[PortMapV1] {
        &self.port_mappings
    }
}

/// Lift one circuit call declaration.
pub fn lift_circuit_call_declaration_v1(
    circuit_name: &str,
    port_mappings: Vec<PortMapV1>,
) -> Result<TypedCircuitCallDeclarationV1, CircuitCallDeclarationErrorV1> {
    TypedCircuitCallDeclarationV1::try_new(circuit_name, port_mappings)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn policy_fixed() {
        assert_eq!(
            CIRCUIT_CALL_DECLARATION_POLICY_V1,
            "sipi.p4a-03m.circuit-call-declaration-v1.typed-circuit-call"
        );
    }

    #[test]
    fn valid_circuit_call() {
        let pm1 = PortMapV1::new("P1", "N1");
        let pm2 = PortMapV1::new("P2", "N2");
        let call = lift_circuit_call_declaration_v1("SUBCKT_DIFF", vec![pm1, pm2]).expect("lift");
        assert_eq!(call.circuit_name(), "SUBCKT_DIFF");
        assert_eq!(call.port_mappings().len(), 2);
        assert_eq!(call.port_mappings()[0].port_name(), "P1");
        assert_eq!(call.port_mappings()[0].node_name(), "N1");
    }

    #[test]
    fn rejects_empty_circuit_name() {
        let pm1 = PortMapV1::new("P1", "N1");
        assert_eq!(
            lift_circuit_call_declaration_v1("", vec![pm1]),
            Err(CircuitCallDeclarationErrorV1::EmptyCircuitName)
        );
    }

    #[test]
    fn rejects_empty_port_mappings() {
        assert_eq!(
            lift_circuit_call_declaration_v1("SUBCKT", vec![]),
            Err(CircuitCallDeclarationErrorV1::EmptyPortMappings)
        );
    }

    #[test]
    fn rejects_non_ascii_name() {
        let pm1 = PortMapV1::new("P1", "N1");
        assert_eq!(
            lift_circuit_call_declaration_v1("电路1", vec![pm1]),
            Err(CircuitCallDeclarationErrorV1::NonAsciiName)
        );
    }

    #[test]
    fn rejects_duplicate_port_name() {
        let pm1 = PortMapV1::new("P1", "N1");
        let pm2 = PortMapV1::new("P1", "N2");
        assert_eq!(
            lift_circuit_call_declaration_v1("SUBCKT_DUP", vec![pm1, pm2]),
            Err(CircuitCallDeclarationErrorV1::DuplicatePortName("P1".to_string()))
        );
    }
}
