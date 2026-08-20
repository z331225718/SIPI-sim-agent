//! Typed IBIS Component declaration core (P4A-03g).
//!
//! Lifts and validates IBIS [Component] headers, manufacturer strings,
//! and package model names into typed, clean-room structures.
//! Fail-closed: empty component names, non-ASCII characters, or
//! invalid component name spellings are strictly rejected.

/// Scope policy for the typed component declaration core.
pub const COMPONENT_DECLARATION_POLICY_V1: &str =
    "sipi.p4a-03g.component-declaration-v1.typed-component";

/// Fail-closed errors during component declaration lifting.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ComponentDeclarationErrorV1 {
    EmptyName,
    NonAsciiName,
    InvalidName,
}

/// A typed IBIS component declaration.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct IbisComponentV1 {
    name: String,
    manufacturer: Option<String>,
    package_name: Option<String>,
}

impl IbisComponentV1 {
    pub fn try_new(
        name: impl Into<String>,
        manufacturer: Option<String>,
        package_name: Option<String>,
    ) -> Result<Self, ComponentDeclarationErrorV1> {
        let name = name.into();
        let trimmed = name.trim();
        if trimmed.is_empty() {
            return Err(ComponentDeclarationErrorV1::EmptyName);
        }
        if !trimmed.is_ascii() {
            return Err(ComponentDeclarationErrorV1::NonAsciiName);
        }
        if !trimmed
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-' || c == '.')
        {
            return Err(ComponentDeclarationErrorV1::InvalidName);
        }
        let manufacturer = manufacturer.and_then(|m| {
            let t = m.trim().to_string();
            if t.is_empty() {
                None
            } else {
                Some(t)
            }
        });
        let package_name = package_name.and_then(|p| {
            let t = p.trim().to_string();
            if t.is_empty() {
                None
            } else {
                Some(t)
            }
        });
        Ok(Self {
            name: trimmed.to_string(),
            manufacturer,
            package_name,
        })
    }

    pub fn name(&self) -> &str {
        &self.name
    }

    pub fn manufacturer(&self) -> Option<&str> {
        self.manufacturer.as_deref()
    }

    pub fn package_name(&self) -> Option<&str> {
        self.package_name.as_deref()
    }
}

/// Lift one component declaration from raw string fields.
pub fn lift_component_declaration_v1(
    name: &str,
    manufacturer: Option<&str>,
    package_name: Option<&str>,
) -> Result<IbisComponentV1, ComponentDeclarationErrorV1> {
    IbisComponentV1::try_new(
        name,
        manufacturer.map(|s| s.to_string()),
        package_name.map(|s| s.to_string()),
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn policy_fixed() {
        assert_eq!(
            COMPONENT_DECLARATION_POLICY_V1,
            "sipi.p4a-03g.component-declaration-v1.typed-component"
        );
    }

    #[test]
    fn valid_full_component() {
        let comp = lift_component_declaration_v1(
            "AS4C512M8S1",
            Some("Alliance Memory"),
            Some("FBGA84"),
        )
        .expect("lift");
        assert_eq!(comp.name(), "AS4C512M8S1");
        assert_eq!(comp.manufacturer(), Some("Alliance Memory"));
        assert_eq!(comp.package_name(), Some("FBGA84"));
    }

    #[test]
    fn valid_minimal_component() {
        let comp = lift_component_declaration_v1("CHIP_V1.0", None, None).expect("lift");
        assert_eq!(comp.name(), "CHIP_V1.0");
        assert_eq!(comp.manufacturer(), None);
        assert_eq!(comp.package_name(), None);
    }

    #[test]
    fn rejects_empty_name() {
        assert_eq!(
            lift_component_declaration_v1("", None, None),
            Err(ComponentDeclarationErrorV1::EmptyName)
        );
        assert_eq!(
            lift_component_declaration_v1("   ", None, None),
            Err(ComponentDeclarationErrorV1::EmptyName)
        );
    }

    #[test]
    fn rejects_non_ascii_name() {
        assert_eq!(
            lift_component_declaration_v1("组件1", None, None),
            Err(ComponentDeclarationErrorV1::NonAsciiName)
        );
    }

    #[test]
    fn rejects_invalid_characters() {
        assert_eq!(
            lift_component_declaration_v1("CHIP @1", None, None),
            Err(ComponentDeclarationErrorV1::InvalidName)
        );
    }
}
