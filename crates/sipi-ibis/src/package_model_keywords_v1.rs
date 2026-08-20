//! Typed IBIS [Package Model] required keywords validation core (P4A-03ae).
//!
//! Lifts and validates IBIS [Package Model] required keywords and sections
//! (package model name, [Number Of Pins], [Pin Numbers]) into typed clean-room structures.
//! Fail-closed: empty package model names, non-ASCII characters, invalid pin count (0),
//! or empty pin number lists are strictly rejected.

use std::collections::BTreeSet;

/// Scope policy for the typed package model keywords core.
pub const PACKAGE_MODEL_KEYWORDS_POLICY_V1: &str =
    "sipi.p4a-03ae.package-model-keywords-v1.typed-package-keywords";

/// Fail-closed errors during package model keyword lifting.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum PackageModelKeywordsErrorV1 {
    EmptyPackageModelName,
    NonAsciiName,
    InvalidName,
    InvalidNumberOfPins,
    EmptyPinNumbers,
    DuplicatePinNumber(String),
}

/// A typed IBIS [Package Model] required keywords declaration.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct TypedPackageModelKeywordsV1 {
    package_model_name: String,
    number_of_pins: usize,
    pin_numbers: Vec<String>,
}

impl TypedPackageModelKeywordsV1 {
    pub fn try_new(
        package_model_name: impl Into<String>,
        number_of_pins: usize,
        pin_numbers: Vec<String>,
    ) -> Result<Self, PackageModelKeywordsErrorV1> {
        let name = package_model_name.into();
        let trimmed = name.trim();
        if trimmed.is_empty() {
            return Err(PackageModelKeywordsErrorV1::EmptyPackageModelName);
        }
        if !trimmed.is_ascii() {
            return Err(PackageModelKeywordsErrorV1::NonAsciiName);
        }
        if !trimmed
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-' || c == '.')
        {
            return Err(PackageModelKeywordsErrorV1::InvalidName);
        }

        if number_of_pins == 0 {
            return Err(PackageModelKeywordsErrorV1::InvalidNumberOfPins);
        }
        if pin_numbers.is_empty() {
            return Err(PackageModelKeywordsErrorV1::EmptyPinNumbers);
        }

        let mut seen = BTreeSet::new();
        let mut clean_pins = Vec::with_capacity(pin_numbers.len());

        for pin in &pin_numbers {
            let pt = pin.trim().to_string();
            if pt.is_empty() {
                return Err(PackageModelKeywordsErrorV1::EmptyPackageModelName);
            }
            if !pt.is_ascii() {
                return Err(PackageModelKeywordsErrorV1::NonAsciiName);
            }
            if !pt
                .chars()
                .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-' || c == '.')
            {
                return Err(PackageModelKeywordsErrorV1::InvalidName);
            }
            if !seen.insert(pt.clone()) {
                return Err(PackageModelKeywordsErrorV1::DuplicatePinNumber(pt));
            }
            clean_pins.push(pt);
        }

        Ok(Self {
            package_model_name: trimmed.to_string(),
            number_of_pins,
            pin_numbers: clean_pins,
        })
    }

    pub fn package_model_name(&self) -> &str {
        &self.package_model_name
    }

    pub const fn number_of_pins(&self) -> usize {
        self.number_of_pins
    }

    pub fn pin_numbers(&self) -> &[String] {
        &self.pin_numbers
    }
}

/// Lift one package model keywords declaration.
pub fn lift_package_model_keywords_v1(
    package_model_name: &str,
    number_of_pins: usize,
    pin_numbers: Vec<String>,
) -> Result<TypedPackageModelKeywordsV1, PackageModelKeywordsErrorV1> {
    TypedPackageModelKeywordsV1::try_new(package_model_name, number_of_pins, pin_numbers)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn policy_fixed() {
        assert_eq!(
            PACKAGE_MODEL_KEYWORDS_POLICY_V1,
            "sipi.p4a-03ae.package-model-keywords-v1.typed-package-keywords"
        );
    }

    #[test]
    fn valid_package_model_keywords() {
        let pkg = lift_package_model_keywords_v1(
            "PKG_BGA_100",
            2,
            vec!["A1".to_string(), "A2".to_string()],
        )
        .expect("lift");
        assert_eq!(pkg.package_model_name(), "PKG_BGA_100");
        assert_eq!(pkg.number_of_pins(), 2);
        assert_eq!(pkg.pin_numbers(), &["A1", "A2"]);
    }

    #[test]
    fn rejects_empty_package_model_name() {
        assert_eq!(
            lift_package_model_keywords_v1("", 2, vec!["A1".to_string()]),
            Err(PackageModelKeywordsErrorV1::EmptyPackageModelName)
        );
    }

    #[test]
    fn rejects_zero_number_of_pins() {
        assert_eq!(
            lift_package_model_keywords_v1("PKG_BGA", 0, vec!["A1".to_string()]),
            Err(PackageModelKeywordsErrorV1::InvalidNumberOfPins)
        );
    }

    #[test]
    fn rejects_empty_pin_numbers() {
        assert_eq!(
            lift_package_model_keywords_v1("PKG_BGA", 10, vec![]),
            Err(PackageModelKeywordsErrorV1::EmptyPinNumbers)
        );
    }

    #[test]
    fn rejects_duplicate_pin_number() {
        assert_eq!(
            lift_package_model_keywords_v1("PKG_BGA", 2, vec!["A1".to_string(), "A1".to_string()]),
            Err(PackageModelKeywordsErrorV1::DuplicatePinNumber("A1".to_string()))
        );
    }
}
