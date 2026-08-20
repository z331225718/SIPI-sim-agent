//! AMI parameter-catalog typed core (P4B-02b3).
//!
//! Compiles a caller-supplied parameter catalog (name, IBIS-AMI usage,
//! declared type, default token) and validates a candidate parameter value
//! set against it: unknown names rejected when strict, missing required
//! (Usage=In) names rejected, value type checked against the catalog type,
//! and a default token parsed to the declared type for fail-closed use.
//! Deliberately profile-agnostic: it carries no reserved-name catalog and
//! selects no AMI profile; the specific catalog is caller-supplied.

use crate::parameter_value_v1::{AmiParameterTypeV1, AmiParameterValueV1};

/// Stable scope policy of the P4B-02b3 catalog core.
pub const PARAMETER_CATALOG_POLICY_V1: &str = "sipi.p4b-02b3.parameter-catalog.v1.typed";

/// IBIS-AMI parameter usage role.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum AmiUsageV1 {
    In,
    Out,
    Info,
}

impl AmiUsageV1 {
    pub const fn token(self) -> &'static str {
        match self {
            Self::In => "In",
            Self::Out => "Out",
            Self::Info => "Info",
        }
    }

    pub fn from_token(token: &str) -> Option<Self> {
        match token {
            "In" => Some(Self::In),
            "Out" => Some(Self::Out),
            "Info" => Some(Self::Info),
            _ => None,
        }
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum CatalogErrorV1 {
    EmptyCatalog,
    DuplicateEntry(String),
    UnknownUsage(String),
    InvalidDefault,
    UnknownParameter(String),
    MissingRequired(String),
    TypeMismatch {
        name: String,
        expected: &'static str,
        value: String,
    },
}

/// One catalog entry: name, usage, declared type, and an optional default token.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct CatalogEntryV1 {
    name: String,
    usage: AmiUsageV1,
    parameter_type: AmiParameterTypeV1,
    default_token: Option<String>,
}

impl CatalogEntryV1 {
    pub fn new(
        name: impl Into<String>,
        usage: AmiUsageV1,
        parameter_type: AmiParameterTypeV1,
        default_token: Option<String>,
    ) -> Self {
        Self {
            name: name.into(),
            usage,
            parameter_type,
            default_token,
        }
    }
    pub fn name(&self) -> &str {
        &self.name
    }
    pub const fn usage(&self) -> AmiUsageV1 {
        self.usage
    }
    pub const fn parameter_type(&self) -> AmiParameterTypeV1 {
        self.parameter_type
    }
    pub fn default_token(&self) -> Option<&str> {
        self.default_token.as_deref()
    }
    pub fn has_default(&self) -> bool {
        self.default_token.is_some()
    }
}

/// A compiled parameter catalog (a set of named entries).
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ParameterCatalogV1 {
    entries: std::collections::BTreeMap<String, CatalogEntryV1>,
}

impl ParameterCatalogV1 {
    pub fn compile(entries: Vec<CatalogEntryV1>) -> Result<Self, CatalogErrorV1> {
        if entries.is_empty() {
            return Err(CatalogErrorV1::EmptyCatalog);
        }
        let mut map = std::collections::BTreeMap::new();
        for entry in entries {
            let name = entry.name.clone();
            if map.insert(name.clone(), entry).is_some() {
                return Err(CatalogErrorV1::DuplicateEntry(name));
            }
        }
        Ok(Self { entries: map })
    }

    pub fn entry(&self, name: &str) -> Option<&CatalogEntryV1> {
        self.entries.get(name)
    }

    pub fn parameter_names(&self) -> Vec<String> {
        self.entries.keys().cloned().collect()
    }
}

/// Validates a candidate value set against a compiled catalog.
///
/// Every Usage=In catalog entry must be present; every present value's
/// type must match the catalog entry type; unknown names are rejected.
pub fn validate_candidate_set_v1(
    catalog: &ParameterCatalogV1,
    values: &std::collections::BTreeMap<String, AmiParameterValueV1>,
) -> Result<(), CatalogErrorV1> {
    // Every Usage=In entry must be supplied.
    for (name, entry) in &catalog.entries {
        if entry.usage() == AmiUsageV1::In && !values.contains_key(name) {
            return Err(CatalogErrorV1::MissingRequired(name.clone()));
        }
    }
    // Every supplied value must be a known catalog parameter with matching type.
    for (name, value) in values {
        let entry = catalog
            .entry(name)
            .ok_or_else(|| CatalogErrorV1::UnknownParameter(name.clone()))?;
        if value.parameter_type() != entry.parameter_type() {
            return Err(CatalogErrorV1::TypeMismatch {
                name: name.clone(),
                expected: entry.parameter_type().token(),
                value: value.value_token().to_string(),
            });
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::parameter_value_v1::AmiParameterValueV1;

    fn value(name: &str, ty: AmiParameterTypeV1, tok: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, ty.token(), tok).unwrap()
    }

    #[test]
    fn policy_fixed() {
        assert_eq!(
            PARAMETER_CATALOG_POLICY_V1,
            "sipi.p4b-02b3.parameter-catalog.v1.typed"
        );
    }

    #[test]
    fn missing_required_rejected() {
        let catalog = ParameterCatalogV1::compile(vec![CatalogEntryV1::new(
            "swing",
            AmiUsageV1::In,
            AmiParameterTypeV1::Float,
            None,
        )])
        .expect("catalog");
        let vals = std::collections::BTreeMap::new();
        let err = validate_candidate_set_v1(&catalog, &vals).expect_err("err");
        assert_eq!(err, CatalogErrorV1::MissingRequired("swing".to_string()));
    }

    #[test]
    fn valid_in_set_passes() {
        let catalog = ParameterCatalogV1::compile(vec![CatalogEntryV1::new(
            "swing",
            AmiUsageV1::In,
            AmiParameterTypeV1::Float,
            None,
        )])
        .expect("catalog");
        let mut vals = std::collections::BTreeMap::new();
        vals.insert(
            "swing".to_string(),
            value("swing", AmiParameterTypeV1::Float, "0.5"),
        );
        validate_candidate_set_v1(&catalog, &vals).expect("ok");
    }

    #[test]
    fn unknown_parameter_rejected() {
        let catalog = ParameterCatalogV1::compile(vec![CatalogEntryV1::new(
            "swing",
            AmiUsageV1::In,
            AmiParameterTypeV1::Float,
            None,
        )])
        .expect("catalog");
        let mut vals = std::collections::BTreeMap::new();
        vals.insert(
            "swing".to_string(),
            value("swing", AmiParameterTypeV1::Float, "0.5"),
        );
        vals.insert(
            "bogus".to_string(),
            value("bogus", AmiParameterTypeV1::Float, "1.0"),
        );
        let err = validate_candidate_set_v1(&catalog, &vals).expect_err("err");
        assert!(matches!(err, CatalogErrorV1::UnknownParameter(_)));
    }

    #[test]
    fn type_mismatch_rejected() {
        let catalog = ParameterCatalogV1::compile(vec![CatalogEntryV1::new(
            "swing",
            AmiUsageV1::In,
            AmiParameterTypeV1::Float,
            None,
        )])
        .expect("catalog");
        let mut vals = std::collections::BTreeMap::new();
        vals.insert(
            "swing".to_string(),
            value("swing", AmiParameterTypeV1::Integer, "5"),
        );
        let err = validate_candidate_set_v1(&catalog, &vals).expect_err("err");
        assert!(matches!(err, CatalogErrorV1::TypeMismatch { .. }));
    }

    #[test]
    fn optional_info_param_not_required() {
        let catalog = ParameterCatalogV1::compile(vec![
            CatalogEntryV1::new("swing", AmiUsageV1::In, AmiParameterTypeV1::Float, None),
            CatalogEntryV1::new(
                "comment",
                AmiUsageV1::Info,
                AmiParameterTypeV1::String_,
                None,
            ),
        ])
        .expect("catalog");
        let mut vals = std::collections::BTreeMap::new();
        vals.insert(
            "swing".to_string(),
            value("swing", AmiParameterTypeV1::Float, "0.5"),
        );
        validate_candidate_set_v1(&catalog, &vals).expect("ok");
    }

    #[test]
    fn empty_catalog_rejected() {
        let err = ParameterCatalogV1::compile(vec![]).expect_err("err");
        assert_eq!(err, CatalogErrorV1::EmptyCatalog);
    }

    #[test]
    fn duplicate_rejected() {
        let err = ParameterCatalogV1::compile(vec![
            CatalogEntryV1::new("swing", AmiUsageV1::In, AmiParameterTypeV1::Float, None),
            CatalogEntryV1::new("swing", AmiUsageV1::In, AmiParameterTypeV1::Float, None),
        ])
        .expect_err("err");
        assert!(matches!(err, CatalogErrorV1::DuplicateEntry(_)));
    }
}
