//! Typed IBIS [Package Model] declaration core (P4A-03h).
//!
//! Lifts and validates IBIS [Package Model] declarations, global typical
//! resistance (R_pkg), inductance (L_pkg), and capacitance (C_pkg) into
//! typed, clean-room structures.
//! Fail-closed: empty names, non-ASCII characters, invalid name spellings,
//! or negative/non-finite RLC values are strictly rejected.

use sipi_types::FiniteF64;

/// Scope policy for the typed package model declaration core.
pub const PACKAGE_MODEL_DECLARATION_POLICY_V1: &str =
    "sipi.p4a-03h.package-model-declaration-v1.typed-package-model";

/// Fail-closed errors during package model declaration lifting.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum PackageModelDeclarationErrorV1 {
    EmptyName,
    NonAsciiName,
    InvalidName,
    NonFiniteValue,
    NegativeValue,
}

/// A typed IBIS package model declaration.
#[derive(Clone, Debug, PartialEq)]
pub struct TypedPackageModelDeclarationV1 {
    name: String,
    r_pkg_ohm: Option<FiniteF64>,
    l_pkg_henry: Option<FiniteF64>,
    c_pkg_farad: Option<FiniteF64>,
}

impl TypedPackageModelDeclarationV1 {
    pub fn try_new(
        name: impl Into<String>,
        r_pkg_ohm: Option<f64>,
        l_pkg_henry: Option<f64>,
        c_pkg_farad: Option<f64>,
    ) -> Result<Self, PackageModelDeclarationErrorV1> {
        let name = name.into();
        let trimmed = name.trim();
        if trimmed.is_empty() {
            return Err(PackageModelDeclarationErrorV1::EmptyName);
        }
        if !trimmed.is_ascii() {
            return Err(PackageModelDeclarationErrorV1::NonAsciiName);
        }
        if !trimmed
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-' || c == '.')
        {
            return Err(PackageModelDeclarationErrorV1::InvalidName);
        }

        let validate_rlc = |val: Option<f64>, kind: &'static str| -> Result<Option<FiniteF64>, PackageModelDeclarationErrorV1> {
            match val {
                None => Ok(None),
                Some(v) => {
                    if !v.is_finite() {
                        return Err(PackageModelDeclarationErrorV1::NonFiniteValue);
                    }
                    if v < 0.0 {
                        return Err(PackageModelDeclarationErrorV1::NegativeValue);
                    }
                    let finite = FiniteF64::try_new(v, kind)
                        .map_err(|_| PackageModelDeclarationErrorV1::NonFiniteValue)?;
                    Ok(Some(finite))
                }
            }
        };

        let r_pkg_ohm = validate_rlc(r_pkg_ohm, "r_pkg_ohm")?;
        let l_pkg_henry = validate_rlc(l_pkg_henry, "l_pkg_henry")?;
        let c_pkg_farad = validate_rlc(c_pkg_farad, "c_pkg_farad")?;

        Ok(Self {
            name: trimmed.to_string(),
            r_pkg_ohm,
            l_pkg_henry,
            c_pkg_farad,
        })
    }

    pub fn name(&self) -> &str {
        &self.name
    }

    pub fn r_pkg_ohm(&self) -> Option<FiniteF64> {
        self.r_pkg_ohm
    }

    pub fn l_pkg_henry(&self) -> Option<FiniteF64> {
        self.l_pkg_henry
    }

    pub fn c_pkg_farad(&self) -> Option<FiniteF64> {
        self.c_pkg_farad
    }
}

/// Lift one package model declaration from raw parameters.
pub fn lift_package_model_declaration_v1(
    name: &str,
    r_pkg_ohm: Option<f64>,
    l_pkg_henry: Option<f64>,
    c_pkg_farad: Option<f64>,
) -> Result<TypedPackageModelDeclarationV1, PackageModelDeclarationErrorV1> {
    TypedPackageModelDeclarationV1::try_new(name, r_pkg_ohm, l_pkg_henry, c_pkg_farad)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn policy_fixed() {
        assert_eq!(
            PACKAGE_MODEL_DECLARATION_POLICY_V1,
            "sipi.p4a-03h.package-model-declaration-v1.typed-package-model"
        );
    }

    #[test]
    fn valid_full_package_model() {
        let pkg = lift_package_model_declaration_v1(
            "FBGA84_PKG",
            Some(0.1),
            Some(1e-9),
            Some(1e-12),
        )
        .expect("lift");
        assert_eq!(pkg.name(), "FBGA84_PKG");
        assert_eq!(pkg.r_pkg_ohm().unwrap().get(), 0.1);
        assert_eq!(pkg.l_pkg_henry().unwrap().get(), 1e-9);
        assert_eq!(pkg.c_pkg_farad().unwrap().get(), 1e-12);
    }

    #[test]
    fn valid_minimal_package_model() {
        let pkg = lift_package_model_declaration_v1("PKG_MIN", None, None, None).expect("lift");
        assert_eq!(pkg.name(), "PKG_MIN");
        assert_eq!(pkg.r_pkg_ohm(), None);
        assert_eq!(pkg.l_pkg_henry(), None);
        assert_eq!(pkg.c_pkg_farad(), None);
    }

    #[test]
    fn rejects_empty_name() {
        assert_eq!(
            lift_package_model_declaration_v1("", Some(0.1), None, None),
            Err(PackageModelDeclarationErrorV1::EmptyName)
        );
    }

    #[test]
    fn rejects_non_ascii_name() {
        assert_eq!(
            lift_package_model_declaration_v1("封装1", Some(0.1), None, None),
            Err(PackageModelDeclarationErrorV1::NonAsciiName)
        );
    }

    #[test]
    fn rejects_negative_or_non_finite_values() {
        assert_eq!(
            lift_package_model_declaration_v1("PKG", Some(-0.1), None, None),
            Err(PackageModelDeclarationErrorV1::NegativeValue)
        );
        assert_eq!(
            lift_package_model_declaration_v1("PKG", Some(f64::NAN), None, None),
            Err(PackageModelDeclarationErrorV1::NonFiniteValue)
        );
    }
}
