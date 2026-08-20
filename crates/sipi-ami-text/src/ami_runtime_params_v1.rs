//! AMI runtime parameter table core (P4B-02b5).
//!
//! Merges a compiled AMI parameter catalog with a validated candidate value
//! set into an ordered, typed runtime parameter table. Per catalog entry:
//!
//! - Usage=In: the runtime value is the candidate value when one is supplied,
//!   otherwise the catalog entry's validated typed default; a Usage=In entry
//!   with neither a candidate nor a default is a hard error (the runtime has
//!   no value to run with, and silently leaving it out would drift from the
//!   call that expects a concrete value).
//! - Usage=Out / Usage=Info: not required at runtime; carried through only
//!   when a candidate value is supplied (these roles are model-populated).
//!
//! The table is emitted in catalog order (a compiled catalog is a sorted map,
//! so the order is deterministic). Like the other P4B-02b* cores this slice is
//! profile-agnostic: it selects no AMI profile and carries no reserved-name
//! catalog; the caller supplies the catalog and the validated values.

use crate::catalog_default_v1::materialize_default_v1;
use crate::parameter_catalog_v1::{AmiUsageV1, CatalogEntryV1, ParameterCatalogV1};
use crate::parameter_value_v1::{AmiParameterTypeV1, AmiParameterValueV1};

/// Stable scope policy of the P4B-02b5 runtime-parameter-table core.
pub const AMI_RUNTIME_PARAMS_POLICY_V1: &str = "sipi.p4b-02b5.ami-runtime-params.v1.typed";

/// Fail-closed errors when building the runtime parameter table.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum RuntimeParamsErrorV1 {
    /// A Usage=In entry has neither a candidate value nor a usable default.
    MissingRuntimeValue(String),
    /// A catalog entry looked up for a default could not be found (invariant).
    CatalogLookup(String),
    /// The candidate value's type does not match the catalog entry type.
    TypeMismatch {
        name: String,
        expected: &'static str,
        value: String,
    },
}

/// One resolved runtime parameter in catalog (sorted-name) order.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RuntimeParamV1 {
    name: String,
    usage: AmiUsageV1,
    parameter_type: AmiParameterTypeV1,
    value: AmiParameterValueV1,
}

impl RuntimeParamV1 {
    pub fn name(&self) -> &str {
        &self.name
    }
    pub const fn usage(&self) -> AmiUsageV1 {
        self.usage
    }
    pub const fn parameter_type(&self) -> AmiParameterTypeV1 {
        self.parameter_type
    }
    pub fn value(&self) -> &AmiParameterValueV1 {
        &self.value
    }
}

/// An ordered typed runtime parameter table.
#[derive(Clone, Debug, Default, Eq, PartialEq)]
pub struct AmiRuntimeParamsV1 {
    params: Vec<RuntimeParamV1>,
}

impl AmiRuntimeParamsV1 {
    pub fn params(&self) -> &[RuntimeParamV1] {
        &self.params
    }

    /// Look up a resolved runtime parameter by name.
    pub fn get(&self, name: &str) -> Option<&RuntimeParamV1> {
        self.params.iter().find(|p| p.name == name)
    }
}

/// Builds the ordered runtime parameter table.
///
/// The candidate value set must already have passed
/// `validate_candidate_set_v1`; this function additionally requires every
/// Usage=In entry to resolve to a concrete value (candidate or catalog
/// default) and every supplied candidate to match the catalog entry type.
pub fn build_ami_runtime_params_v1(
    catalog: &ParameterCatalogV1,
    candidate_values: &std::collections::BTreeMap<String, AmiParameterValueV1>,
) -> Result<AmiRuntimeParamsV1, RuntimeParamsErrorV1> {
    let mut params = Vec::new();
    for name in catalog.parameter_names() {
        let entry = catalog
            .entry(&name)
            .ok_or_else(|| RuntimeParamsErrorV1::CatalogLookup(name.clone()))?;
        let candidate = candidate_values.get(&name);
        if let Some(value) = candidate {
            if value.parameter_type() != entry.parameter_type() {
                return Err(RuntimeParamsErrorV1::TypeMismatch {
                    name,
                    expected: entry.parameter_type().token(),
                    value: value.value_token().to_string(),
                });
            }
            params.push(runtime_param(entry, value.clone()));
            continue;
        }
        match entry.usage() {
            AmiUsageV1::In => {
                let default = materialize_default_v1(catalog, &name)
                    .map_err(|_| RuntimeParamsErrorV1::MissingRuntimeValue(name.clone()))?;
                params.push(runtime_param(entry, default));
            }
            AmiUsageV1::Out | AmiUsageV1::Info => {
                continue;
            }
        }
    }
    Ok(AmiRuntimeParamsV1 { params })
}

fn runtime_param(entry: &CatalogEntryV1, value: AmiParameterValueV1) -> RuntimeParamV1 {
    RuntimeParamV1 {
        name: entry.name().to_string(),
        usage: entry.usage(),
        parameter_type: entry.parameter_type(),
        value,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::parameter_catalog_v1::{AmiUsageV1, CatalogEntryV1};
    use crate::parameter_value_v1::AmiParameterValueV1;

    fn val(name: &str, ty: AmiParameterTypeV1, tok: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, ty.token(), tok).unwrap()
    }

    fn catalog(entries: Vec<CatalogEntryV1>) -> ParameterCatalogV1 {
        ParameterCatalogV1::compile(entries).unwrap()
    }

    fn in_entry(name: &str, ty: AmiParameterTypeV1, default: Option<&str>) -> CatalogEntryV1 {
        CatalogEntryV1::new(
            name.to_string(),
            AmiUsageV1::In,
            ty,
            default.map(String::from),
        )
    }

    fn out_entry(name: &str, ty: AmiParameterTypeV1) -> CatalogEntryV1 {
        CatalogEntryV1::new(name.to_string(), AmiUsageV1::Out, ty, None)
    }

    #[test]
    fn policy_fixed() {
        assert_eq!(
            AMI_RUNTIME_PARAMS_POLICY_V1,
            "sipi.p4b-02b5.ami-runtime-params.v1.typed"
        );
    }

    #[test]
    fn candidate_wins_over_default_for_in() {
        let c = catalog(vec![in_entry(
            "swing",
            AmiParameterTypeV1::Float,
            Some("0.5"),
        )]);
        let mut cand = std::collections::BTreeMap::new();
        cand.insert(
            "swing".to_string(),
            val("swing", AmiParameterTypeV1::Float, "0.9"),
        );
        let table = build_ami_runtime_params_v1(&c, &cand).expect("ok");
        assert_eq!(table.params().len(), 1);
        assert_eq!(table.get("swing").unwrap().value().value_token(), "0.9");
    }

    #[test]
    fn default_used_when_no_candidate_for_in() {
        let c = catalog(vec![in_entry(
            "swing",
            AmiParameterTypeV1::Float,
            Some("0.5"),
        )]);
        let table =
            build_ami_runtime_params_v1(&c, &std::collections::BTreeMap::new()).expect("ok");
        assert_eq!(table.params().len(), 1);
        assert_eq!(table.get("swing").unwrap().value().value_token(), "0.5");
        assert_eq!(table.get("swing").unwrap().usage(), AmiUsageV1::In);
    }

    #[test]
    fn in_without_candidate_or_default_is_error() {
        let c = catalog(vec![in_entry("swing", AmiParameterTypeV1::Float, None)]);
        let err =
            build_ami_runtime_params_v1(&c, &std::collections::BTreeMap::new()).expect_err("err");
        assert_eq!(
            err,
            RuntimeParamsErrorV1::MissingRuntimeValue("swing".to_string())
        );
    }

    #[test]
    fn out_and_info_omitted_without_candidate() {
        let c = catalog(vec![out_entry("out_x", AmiParameterTypeV1::Float)]);
        let table =
            build_ami_runtime_params_v1(&c, &std::collections::BTreeMap::new()).expect("ok");
        assert_eq!(table.params().len(), 0);
    }

    #[test]
    fn out_carried_when_candidate_supplied() {
        let c = catalog(vec![out_entry("out_x", AmiParameterTypeV1::Float)]);
        let mut cand = std::collections::BTreeMap::new();
        cand.insert(
            "out_x".to_string(),
            val("out_x", AmiParameterTypeV1::Float, "3.0"),
        );
        let table = build_ami_runtime_params_v1(&c, &cand).expect("ok");
        assert_eq!(table.params().len(), 1);
        assert_eq!(table.get("out_x").unwrap().value().value_token(), "3.0");
        assert_eq!(table.get("out_x").unwrap().usage(), AmiUsageV1::Out);
    }

    #[test]
    fn order_is_sorted_catalog_name_order() {
        let c = catalog(vec![
            in_entry("zeta", AmiParameterTypeV1::Float, Some("1.0")),
            in_entry("alpha", AmiParameterTypeV1::Float, Some("2.0")),
        ]);
        let table =
            build_ami_runtime_params_v1(&c, &std::collections::BTreeMap::new()).expect("ok");
        let names: Vec<&str> = table.params().iter().map(|p| p.name()).collect();
        assert_eq!(names, vec!["alpha", "zeta"]);
    }

    #[test]
    fn nonempty_info_only_catalog_yields_empty_table() {
        // An empty catalog cannot be legally compiled (CatalogErrorV1::EmptyCatalog
        // is already covered in the catalog core). A catalog with only Out/Info
        // entries and no candidate values yields an empty runtime table without
        // error: these model-populated roles are simply not populated.
        let c = catalog(vec![
            out_entry("out_x", AmiParameterTypeV1::Float),
            CatalogEntryV1::new(
                "info_y",
                AmiUsageV1::Info,
                AmiParameterTypeV1::String_,
                None,
            ),
        ]);
        let table =
            build_ami_runtime_params_v1(&c, &std::collections::BTreeMap::new()).expect("ok");
        assert_eq!(table.params().len(), 0);
    }
}
