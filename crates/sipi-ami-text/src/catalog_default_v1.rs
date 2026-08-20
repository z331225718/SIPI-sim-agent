//! AMI catalog default validity core (P4B-02b4).
//!
//! Validates that each compiled AMI parameter-catalog entry's default token
//! is a well-formed value for its declared type, and materializes a typed
//! default value (AmiParameterValueV1) from a catalog entry. Reuses the
//! per-type token rules from parameter_value_v1 (Float finite, Integer i64,
//! Boolean True/False, String non-empty, List parenthesized non-empty).
//! Like P4B-02b3, this is profile-agnostic: it carries no reserved-name
//! catalog and selects no AMI profile.

use crate::parameter_catalog_v1::ParameterCatalogV1;
use crate::parameter_value_v1::{AmiParameterTypeV1, AmiParameterValueV1};

/// Stable scope policy of the P4B-02b4 catalog-default core.
pub const CATALOG_DEFAULT_POLICY_V1: &str = "sipi.p4b-02b4.catalog-default.v1.validity";

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum CatalogDefaultErrorV1 {
    MissingDefault(String),
    InvalidDefault { name: String, kind: String },
    UnknownDefaultType(String),
}

/// Checks whether a raw value token is valid for an AMI parameter type.
/// Reuses the exact rules from parameter_value_v1::AmiParameterValueV1.
pub fn token_valid_for_type_v1(
    type_token: &str,
    value_token: &str,
) -> bool {
    let Some(parameter_type) = AmiParameterTypeV1::from_token(type_token) else {
        return false;
    };
    let rule_ok = match parameter_type {
        AmiParameterTypeV1::Float => value_token.parse::<f64>().map(|v| v.is_finite()).unwrap_or(false),
        AmiParameterTypeV1::Integer => value_token.parse::<i64>().is_ok(),
        AmiParameterTypeV1::Boolean => value_token == "True" || value_token == "False",
        AmiParameterTypeV1::String_ => !value_token.is_empty(),
        AmiParameterTypeV1::List => {
            value_token.starts_with('(')
                && value_token.ends_with(')')
                && !value_token[1..value_token.len() - 1].trim().is_empty()
        }
    };
    rule_ok
}

/// Validates the default token of every catalog entry that declares one.
/// Entries without a default are skipped (a default is optional); an
/// invalid default for a declared-typed entry is a hard error.
pub fn validate_catalog_defaults_v1(
    catalog: &ParameterCatalogV1,
) -> Result<(), CatalogDefaultErrorV1> {
    for name in catalog.parameter_names() {
        let entry = catalog.entry(&name).ok_or_else(|| CatalogDefaultErrorV1::MissingDefault(name.clone()))?;
        if let Some(default) = entry.default_token() {
            if !token_valid_for_type_v1(entry.parameter_type().token(), default) {
                return Err(CatalogDefaultErrorV1::InvalidDefault {
                    name,
                    kind: entry.parameter_type().token().to_string(),
                });
            }
        }
    }
    Ok(())
}

/// Materializes a typed default value from a catalog entry's default token.
/// The catalog entry must already have been validated (its default token
/// matches its declared type); returns the typed AmiParameterValueV1.
pub fn materialize_default_v1(
    catalog: &ParameterCatalogV1,
    name: &str,
) -> Result<AmiParameterValueV1, CatalogDefaultErrorV1> {
    let entry = catalog
        .entry(name)
        .ok_or_else(|| CatalogDefaultErrorV1::MissingDefault(name.to_string()))?;
    let default = entry
        .default_token()
        .ok_or_else(|| CatalogDefaultErrorV1::MissingDefault(name.to_string()))?;
    let parameter_type = entry.parameter_type();
    AmiParameterValueV1::try_new(name, parameter_type.token(), default).map_err(|e| {
        CatalogDefaultErrorV1::InvalidDefault {
            name: name.to_string(),
            kind: format!("{e:?}"),
        }
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::parameter_catalog_v1::{AmiUsageV1, CatalogEntryV1};

    fn catalog(entries: Vec<CatalogEntryV1>) -> ParameterCatalogV1 {
        ParameterCatalogV1::compile(entries).unwrap()
    }

    fn entry(name: &str, ty: AmiParameterTypeV1, default: Option<&str>) -> CatalogEntryV1 {
        CatalogEntryV1::new(name.to_string(), AmiUsageV1::In, ty, default.map(|s| s.to_string()))
    }

    #[test]
    fn policy_fixed() {
        assert_eq!(CATALOG_DEFAULT_POLICY_V1, "sipi.p4b-02b4.catalog-default.v1.validity");
    }

    #[test]
    fn valid_defaults_pass() {
        let c = catalog(vec![
            entry("swing", AmiParameterTypeV1::Float, Some("0.5")),
            entry("pre", AmiParameterTypeV1::Integer, Some("2")),
            entry("flag", AmiParameterTypeV1::Boolean, Some("True")),
        ]);
        validate_catalog_defaults_v1(&c).expect("valid");
    }

    #[test]
    fn float_bad_default_rejected() {
        let c = catalog(vec![entry("swing", AmiParameterTypeV1::Float, Some("not-a-float"))]);
        assert!(validate_catalog_defaults_v1(&c).is_err());
    }

    #[test]
    fn integer_non_numeric_rejected() {
        let c = catalog(vec![entry("pre", AmiParameterTypeV1::Integer, Some("abc"))]);
        assert!(validate_catalog_defaults_v1(&c).is_err());
    }

    #[test]
    fn boolean_typo_rejected() {
        let c = catalog(vec![entry("flag", AmiParameterTypeV1::Boolean, Some("true"))]);
        assert!(validate_catalog_defaults_v1(&c).is_err());
    }

    #[test]
    fn entries_without_default_skipped() {
        let c = catalog(vec![entry("swing", AmiParameterTypeV1::Float, None)]);
        validate_catalog_defaults_v1(&c).expect("ok");
    }

    #[test]
    fn materialize_returns_typed_value() {
        let c = catalog(vec![entry("swing", AmiParameterTypeV1::Float, Some("0.5"))]);
        let v = materialize_default_v1(&c, "swing").expect("v");
        assert_eq!(v.name(), "swing");
        assert_eq!(v.parameter_type(), AmiParameterTypeV1::Float);
        assert_eq!(v.value_token(), "0.5");
    }

    #[test]
    fn materialize_missing_default_rejected() {
        let c = catalog(vec![entry("swing", AmiParameterTypeV1::Float, None)]);
        assert!(materialize_default_v1(&c, "swing").is_err());
    }
}