//! Typed IBIS [Submodel] & [Add Submodel] declaration core (P4A-03l).
//!
//! Lifts and validates IBIS [Submodel] declarations (submodel name,
//! Submodel_type, Submodel mode) and [Add Submodel] references into typed,
//! clean-room structures.
//! Fail-closed: empty submodel names, non-ASCII characters, invalid name spellings,
//! or unknown Submodel_type / mode tokens are strictly rejected.

/// Scope policy for the typed submodel declaration core.
pub const SUBMODEL_DECLARATION_POLICY_V1: &str =
    "sipi.p4a-03l.submodel-declaration-v1.typed-submodel";

/// Supported IBIS Submodel_type tokens.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum SubmodelTypeV1 {
    DynamicClamp,
    BusHold,
    FallClamp,
    RiseClamp,
}

impl SubmodelTypeV1 {
    pub const fn token(self) -> &'static str {
        match self {
            Self::DynamicClamp => "Dynamic_clamp",
            Self::BusHold => "Bus_hold",
            Self::FallClamp => "Fall_clamp",
            Self::RiseClamp => "Rise_clamp",
        }
    }

    pub fn from_token(token: &str) -> Option<Self> {
        match token.trim() {
            "Dynamic_clamp" => Some(Self::DynamicClamp),
            "Bus_hold" => Some(Self::BusHold),
            "Fall_clamp" => Some(Self::FallClamp),
            "Rise_clamp" => Some(Self::RiseClamp),
            _ => None,
        }
    }
}

/// Supported IBIS Submodel Mode tokens.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum SubmodelModeV1 {
    Driving,
    NonDriving,
    All,
}

impl SubmodelModeV1 {
    pub const fn token(self) -> &'static str {
        match self {
            Self::Driving => "Driving",
            Self::NonDriving => "Non-Driving",
            Self::All => "All",
        }
    }

    pub fn from_token(token: &str) -> Option<Self> {
        match token.trim() {
            "Driving" => Some(Self::Driving),
            "Non-Driving" => Some(Self::NonDriving),
            "All" => Some(Self::All),
            _ => None,
        }
    }
}

/// Fail-closed errors during submodel declaration lifting.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum SubmodelDeclarationErrorV1 {
    EmptyName,
    NonAsciiName,
    InvalidName,
    UnknownSubmodelType(String),
    UnknownSubmodelMode(String),
}

/// A typed IBIS [Submodel] declaration.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct TypedSubmodelDeclarationV1 {
    submodel_name: String,
    submodel_type: SubmodelTypeV1,
    mode: SubmodelModeV1,
}

impl TypedSubmodelDeclarationV1 {
    pub fn try_new(
        submodel_name: impl Into<String>,
        submodel_type_token: &str,
        mode_token: &str,
    ) -> Result<Self, SubmodelDeclarationErrorV1> {
        let name = submodel_name.into();
        let trimmed = name.trim();
        if trimmed.is_empty() {
            return Err(SubmodelDeclarationErrorV1::EmptyName);
        }
        if !trimmed.is_ascii() {
            return Err(SubmodelDeclarationErrorV1::NonAsciiName);
        }
        if !trimmed
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-' || c == '.')
        {
            return Err(SubmodelDeclarationErrorV1::InvalidName);
        }

        let stype = SubmodelTypeV1::from_token(submodel_type_token)
            .ok_or_else(|| SubmodelDeclarationErrorV1::UnknownSubmodelType(submodel_type_token.to_string()))?;
        let smode = SubmodelModeV1::from_token(mode_token)
            .ok_or_else(|| SubmodelDeclarationErrorV1::UnknownSubmodelMode(mode_token.to_string()))?;

        Ok(Self {
            submodel_name: trimmed.to_string(),
            submodel_type: stype,
            mode: smode,
        })
    }

    pub fn submodel_name(&self) -> &str {
        &self.submodel_name
    }

    pub const fn submodel_type(&self) -> SubmodelTypeV1 {
        self.submodel_type
    }

    pub const fn mode(&self) -> SubmodelModeV1 {
        self.mode
    }
}

/// A typed IBIS [Add Submodel] declaration.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct TypedAddSubmodelV1 {
    submodel_name: String,
    mode: SubmodelModeV1,
}

impl TypedAddSubmodelV1 {
    pub fn try_new(
        submodel_name: impl Into<String>,
        mode_token: &str,
    ) -> Result<Self, SubmodelDeclarationErrorV1> {
        let name = submodel_name.into();
        let trimmed = name.trim();
        if trimmed.is_empty() {
            return Err(SubmodelDeclarationErrorV1::EmptyName);
        }
        if !trimmed.is_ascii() {
            return Err(SubmodelDeclarationErrorV1::NonAsciiName);
        }
        if !trimmed
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-' || c == '.')
        {
            return Err(SubmodelDeclarationErrorV1::InvalidName);
        }

        let smode = SubmodelModeV1::from_token(mode_token)
            .ok_or_else(|| SubmodelDeclarationErrorV1::UnknownSubmodelMode(mode_token.to_string()))?;

        Ok(Self {
            submodel_name: trimmed.to_string(),
            mode: smode,
        })
    }

    pub fn submodel_name(&self) -> &str {
        &self.submodel_name
    }

    pub const fn mode(&self) -> SubmodelModeV1 {
        self.mode
    }
}

/// Lift one submodel declaration.
pub fn lift_submodel_declaration_v1(
    submodel_name: &str,
    submodel_type_token: &str,
    mode_token: &str,
) -> Result<TypedSubmodelDeclarationV1, SubmodelDeclarationErrorV1> {
    TypedSubmodelDeclarationV1::try_new(submodel_name, submodel_type_token, mode_token)
}

/// Lift one add submodel entry.
pub fn lift_add_submodel_v1(
    submodel_name: &str,
    mode_token: &str,
) -> Result<TypedAddSubmodelV1, SubmodelDeclarationErrorV1> {
    TypedAddSubmodelV1::try_new(submodel_name, mode_token)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn policy_fixed() {
        assert_eq!(
            SUBMODEL_DECLARATION_POLICY_V1,
            "sipi.p4a-03l.submodel-declaration-v1.typed-submodel"
        );
    }

    #[test]
    fn valid_submodel_declaration() {
        let sub = lift_submodel_declaration_v1("SUB_CLAMP", "Dynamic_clamp", "Driving").expect("lift");
        assert_eq!(sub.submodel_name(), "SUB_CLAMP");
        assert_eq!(sub.submodel_type(), SubmodelTypeV1::DynamicClamp);
        assert_eq!(sub.mode(), SubmodelModeV1::Driving);
    }

    #[test]
    fn valid_add_submodel() {
        let add = lift_add_submodel_v1("SUB_HOLD", "Non-Driving").expect("lift");
        assert_eq!(add.submodel_name(), "SUB_HOLD");
        assert_eq!(add.mode(), SubmodelModeV1::NonDriving);
    }

    #[test]
    fn rejects_empty_name() {
        assert_eq!(
            lift_submodel_declaration_v1("", "Bus_hold", "All"),
            Err(SubmodelDeclarationErrorV1::EmptyName)
        );
    }

    #[test]
    fn rejects_unknown_submodel_type() {
        assert_eq!(
            lift_submodel_declaration_v1("SUB", "UnknownType", "All"),
            Err(SubmodelDeclarationErrorV1::UnknownSubmodelType("UnknownType".to_string()))
        );
    }

    #[test]
    fn rejects_unknown_submodel_mode() {
        assert_eq!(
            lift_submodel_declaration_v1("SUB", "Bus_hold", "UnknownMode"),
            Err(SubmodelDeclarationErrorV1::UnknownSubmodelMode("UnknownMode".to_string()))
        );
    }
}
