//! Typed IBIS [Bus Label] declaration core (P4A-03t).
//!
//! Lifts and validates IBIS [Bus Label] bus grouping declarations
//! (bus_label_name, list of member pin names) into typed clean-room structures.
//! Fail-closed: empty bus label names, non-ASCII characters, invalid name spellings,
//! empty member pin lists, or duplicate member pins within a bus are strictly rejected.

use std::collections::BTreeSet;

/// Scope policy for the typed bus label declaration core.
pub const BUS_LABEL_DECLARATION_POLICY_V1: &str =
    "sipi.p4a-03t.bus-label-declaration-v1.typed-bus-label";

/// Fail-closed errors during bus label declaration lifting.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum BusLabelDeclarationErrorV1 {
    EmptyBusLabelName,
    NonAsciiName,
    InvalidName,
    EmptyMemberPins,
    DuplicateMemberPin(String),
}

/// A typed IBIS [Bus Label] declaration.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct TypedBusLabelDeclarationV1 {
    bus_label_name: String,
    member_pins: Vec<String>,
}

impl TypedBusLabelDeclarationV1 {
    pub fn try_new(
        bus_label_name: impl Into<String>,
        member_pins: Vec<String>,
    ) -> Result<Self, BusLabelDeclarationErrorV1> {
        let name = bus_label_name.into();
        let trimmed = name.trim();
        if trimmed.is_empty() {
            return Err(BusLabelDeclarationErrorV1::EmptyBusLabelName);
        }
        if !trimmed.is_ascii() {
            return Err(BusLabelDeclarationErrorV1::NonAsciiName);
        }
        if !trimmed
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-' || c == '.')
        {
            return Err(BusLabelDeclarationErrorV1::InvalidName);
        }

        if member_pins.is_empty() {
            return Err(BusLabelDeclarationErrorV1::EmptyMemberPins);
        }

        let mut seen = BTreeSet::new();
        let mut clean_pins = Vec::with_capacity(member_pins.len());

        for pin in &member_pins {
            let pt = pin.trim().to_string();
            if pt.is_empty() {
                return Err(BusLabelDeclarationErrorV1::EmptyBusLabelName);
            }
            if !pt.is_ascii() {
                return Err(BusLabelDeclarationErrorV1::NonAsciiName);
            }
            if !pt
                .chars()
                .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-' || c == '.')
            {
                return Err(BusLabelDeclarationErrorV1::InvalidName);
            }
            if !seen.insert(pt.clone()) {
                return Err(BusLabelDeclarationErrorV1::DuplicateMemberPin(pt));
            }
            clean_pins.push(pt);
        }

        Ok(Self {
            bus_label_name: trimmed.to_string(),
            member_pins: clean_pins,
        })
    }

    pub fn bus_label_name(&self) -> &str {
        &self.bus_label_name
    }

    pub fn member_pins(&self) -> &[String] {
        &self.member_pins
    }
}

/// Lift one bus label declaration.
pub fn lift_bus_label_declaration_v1(
    bus_label_name: &str,
    member_pins: Vec<String>,
) -> Result<TypedBusLabelDeclarationV1, BusLabelDeclarationErrorV1> {
    TypedBusLabelDeclarationV1::try_new(bus_label_name, member_pins)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn policy_fixed() {
        assert_eq!(
            BUS_LABEL_DECLARATION_POLICY_V1,
            "sipi.p4a-03t.bus-label-declaration-v1.typed-bus-label"
        );
    }

    #[test]
    fn valid_bus_label_declaration() {
        let bus = lift_bus_label_declaration_v1(
            "DQ_BUS",
            vec!["DQ0".to_string(), "DQ1".to_string(), "DQ2".to_string()],
        )
        .expect("lift");
        assert_eq!(bus.bus_label_name(), "DQ_BUS");
        assert_eq!(bus.member_pins(), &["DQ0", "DQ1", "DQ2"]);
    }

    #[test]
    fn rejects_empty_bus_label_name() {
        assert_eq!(
            lift_bus_label_declaration_v1("", vec!["DQ0".to_string()]),
            Err(BusLabelDeclarationErrorV1::EmptyBusLabelName)
        );
    }

    #[test]
    fn rejects_empty_member_pins() {
        assert_eq!(
            lift_bus_label_declaration_v1("DQ_BUS", vec![]),
            Err(BusLabelDeclarationErrorV1::EmptyMemberPins)
        );
    }

    #[test]
    fn rejects_duplicate_member_pin() {
        assert_eq!(
            lift_bus_label_declaration_v1("DQ_BUS", vec!["DQ0".to_string(), "DQ0".to_string()]),
            Err(BusLabelDeclarationErrorV1::DuplicateMemberPin("DQ0".to_string()))
        );
    }

    #[test]
    fn rejects_non_ascii_name() {
        assert_eq!(
            lift_bus_label_declaration_v1("数据总线", vec!["DQ0".to_string()]),
            Err(BusLabelDeclarationErrorV1::NonAsciiName)
        );
    }
}
