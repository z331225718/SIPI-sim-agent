//! Typed IBIS [Bus Label] complete block required keywords core (P4A-03ak).
//!
//! Lifts and validates IBIS [Bus Label] complete block required sub-keyword entries
//! (bus_label_declaration) into typed clean-room structures.
//! Fail-closed: invalid bus label declarations or missing required fields are strictly rejected.

use crate::bus_label_declaration_v1::TypedBusLabelDeclarationV1;

/// Scope policy for the typed bus label keywords core.
pub const BUS_LABEL_KEYWORDS_POLICY_V1: &str =
    "sipi.p4a-03ak.bus-label-keywords-v1.typed-bus-keywords";

/// Fail-closed errors during bus label keywords validation.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum BusLabelKeywordsErrorV1 {
    MissingBusLabelDeclaration,
}

/// A composite typed IBIS [Bus Label] complete block entry.
#[derive(Clone, Debug, PartialEq)]
pub struct TypedBusLabelBlockV1 {
    bus_label_declaration: TypedBusLabelDeclarationV1,
}

impl TypedBusLabelBlockV1 {
    pub fn try_new(
        bus_label_declaration: TypedBusLabelDeclarationV1,
    ) -> Result<Self, BusLabelKeywordsErrorV1> {
        Ok(Self {
            bus_label_declaration,
        })
    }

    pub fn bus_label_declaration(&self) -> &TypedBusLabelDeclarationV1 {
        &self.bus_label_declaration
    }
}

/// Lift one complete bus label block entry.
pub fn lift_bus_label_block_v1(
    bus_label_declaration: TypedBusLabelDeclarationV1,
) -> Result<TypedBusLabelBlockV1, BusLabelKeywordsErrorV1> {
    TypedBusLabelBlockV1::try_new(bus_label_declaration)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::bus_label_declaration_v1::lift_bus_label_declaration_v1;

    #[test]
    fn policy_fixed() {
        assert_eq!(
            BUS_LABEL_KEYWORDS_POLICY_V1,
            "sipi.p4a-03ak.bus-label-keywords-v1.typed-bus-keywords"
        );
    }

    #[test]
    fn valid_bus_label_block() {
        let bus = lift_bus_label_declaration_v1("DQ_BUS", vec!["DQ0".to_string(), "DQ1".to_string()]).unwrap();
        let block = lift_bus_label_block_v1(bus).expect("lift");

        assert_eq!(block.bus_label_declaration().bus_label_name(), "DQ_BUS");
        assert_eq!(block.bus_label_declaration().member_pins(), &["DQ0", "DQ1"]);
    }
}
