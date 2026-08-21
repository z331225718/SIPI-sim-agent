//! Product-owned parameter partition for the specified COM artifact route.
//!
//! This additive module leaves the workbook consumer and its historical
//! evidence untouched. The caller supplies the canonical consumed set,
//! provided values, resolved defaults, and retained unconsumed keys; no COM
//! profile is inferred and no workbook provenance is claimed.

use std::collections::{BTreeMap, BTreeSet};

use crate::{ComParametersErrorV1, ComParametersV1, ResolvedDefaultV1, merge_com_parameters_v1};

pub const COM_SPECIFIED_PARAMETER_INGESTION_POLICY_V1: &str =
    "sipi.p5-08f.com-specified-parameter-partition-v1.product-owned";

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ComSpecifiedParameterIngestionErrorV1 {
    Parameters(ComParametersErrorV1),
    ValueOutsideConsumed(String),
    ProvidedAndDefaultOverlap(String),
    DuplicateUnconsumed(String),
}

impl From<ComParametersErrorV1> for ComSpecifiedParameterIngestionErrorV1 {
    fn from(error: ComParametersErrorV1) -> Self {
        Self::Parameters(error)
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ComSpecifiedParameterConsumptionReportV1 {
    consumed_keys: Vec<String>,
    provided_value_keys: Vec<String>,
    defaulted_keys: Vec<String>,
    unconsumed_keys: Vec<String>,
}

impl ComSpecifiedParameterConsumptionReportV1 {
    pub fn consumed_keys(&self) -> &[String] {
        &self.consumed_keys
    }

    pub fn provided_value_keys(&self) -> &[String] {
        &self.provided_value_keys
    }

    pub fn defaulted_keys(&self) -> &[String] {
        &self.defaulted_keys
    }

    pub fn unconsumed_keys(&self) -> &[String] {
        &self.unconsumed_keys
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct ComSpecifiedParameterIngestionV1 {
    dto: ComParametersV1,
    report: ComSpecifiedParameterConsumptionReportV1,
}

impl ComSpecifiedParameterIngestionV1 {
    pub fn dto(&self) -> &ComParametersV1 {
        &self.dto
    }

    pub fn report(&self) -> &ComSpecifiedParameterConsumptionReportV1 {
        &self.report
    }
}

/// Build the typed DTO and explicit partition for the non-oracle route.
pub fn ingest_com_specified_parameters_v1(
    consumed_keys: &[String],
    provided_values: &BTreeMap<String, ResolvedDefaultV1>,
    resolved_defaults: &BTreeMap<String, ResolvedDefaultV1>,
    unconsumed_keys: &[String],
) -> Result<ComSpecifiedParameterIngestionV1, ComSpecifiedParameterIngestionErrorV1> {
    let consumed: BTreeSet<&str> = consumed_keys.iter().map(String::as_str).collect();
    if let Some(key) = provided_values
        .keys()
        .chain(resolved_defaults.keys())
        .find(|key| !consumed.contains(key.as_str()))
    {
        return Err(ComSpecifiedParameterIngestionErrorV1::ValueOutsideConsumed(
            key.clone(),
        ));
    }
    if let Some(key) = provided_values
        .keys()
        .find(|key| resolved_defaults.contains_key(*key))
    {
        return Err(ComSpecifiedParameterIngestionErrorV1::ProvidedAndDefaultOverlap(key.clone()));
    }
    let mut seen_unconsumed = BTreeSet::new();
    if let Some(key) = unconsumed_keys
        .iter()
        .find(|key| !seen_unconsumed.insert(key.as_str()))
    {
        return Err(ComSpecifiedParameterIngestionErrorV1::DuplicateUnconsumed(
            key.clone(),
        ));
    }
    let dto = merge_com_parameters_v1(
        consumed_keys,
        provided_values,
        resolved_defaults,
        unconsumed_keys,
    )?;
    let provided_value_keys = consumed_keys
        .iter()
        .filter(|key| provided_values.contains_key(*key))
        .cloned()
        .collect();
    let defaulted_keys = consumed_keys
        .iter()
        .filter(|key| !provided_values.contains_key(*key) && resolved_defaults.contains_key(*key))
        .cloned()
        .collect();
    Ok(ComSpecifiedParameterIngestionV1 {
        dto,
        report: ComSpecifiedParameterConsumptionReportV1 {
            consumed_keys: consumed_keys.to_vec(),
            provided_value_keys,
            defaulted_keys,
            unconsumed_keys: unconsumed_keys.to_vec(),
        },
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn scalar(value: f64) -> ResolvedDefaultV1 {
        ResolvedDefaultV1::Scalar(value)
    }

    #[test]
    fn reports_provided_defaulted_and_unconsumed_without_workbook_claim() {
        let mut provided = BTreeMap::new();
        provided.insert("A_v".to_owned(), scalar(0.5));
        let mut defaults = BTreeMap::new();
        defaults.insert("samples_per_ui".to_owned(), scalar(8.0));
        let result = ingest_com_specified_parameters_v1(
            &["A_v".to_owned(), "samples_per_ui".to_owned()],
            &provided,
            &defaults,
            &["extra".to_owned()],
        )
        .expect("partition");
        assert_eq!(result.report().provided_value_keys(), ["A_v"]);
        assert_eq!(result.report().defaulted_keys(), ["samples_per_ui"]);
        assert_eq!(result.report().unconsumed_keys(), ["extra"]);
        assert_eq!(result.dto().consumed().len(), 2);
    }

    #[test]
    fn rejects_values_outside_partition() {
        let mut provided = BTreeMap::new();
        provided.insert("other".to_owned(), scalar(1.0));
        assert!(matches!(
            ingest_com_specified_parameters_v1(
                &["A_v".to_owned()],
                &provided,
                &BTreeMap::new(),
                &[],
            ),
            Err(ComSpecifiedParameterIngestionErrorV1::ValueOutsideConsumed(
                _
            ))
        ));
    }

    #[test]
    fn rejects_provided_default_overlap() {
        let mut provided = BTreeMap::new();
        provided.insert("A_v".to_owned(), scalar(1.0));
        let mut defaults = BTreeMap::new();
        defaults.insert("A_v".to_owned(), scalar(0.5));
        assert!(matches!(
            ingest_com_specified_parameters_v1(&["A_v".to_owned()], &provided, &defaults, &[]),
            Err(ComSpecifiedParameterIngestionErrorV1::ProvidedAndDefaultOverlap(_))
        ));
    }
}
