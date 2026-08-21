//! COM parameter ingestion consumer (P5-05g).
//!
//! This is the first product-owned consumer that connects the workbook
//! surface reader to the typed COM parameter DTO.  It deliberately consumes
//! only the already-classified `ParameterSurfaceReportV1`; the caller also
//! supplies the canonical consumed-key list observed for its selected COM
//! profile.  The consumer does not invent that list, normalize workbook
//! spelling, or silently discard fields.  Every consumed key is looked up through the existing workbook
//! lookup contract, converted to the existing `ResolvedDefaultV1` envelope,
//! and then passed to `merge_com_parameters_v1`. The returned report keeps
//! the consumed, workbook-overridden, defaulted, and unconsumed sets
//! explicit for downstream execution/reporting.

use std::collections::{BTreeMap, BTreeSet};

use crate::com_parameters_v1::{ComParametersErrorV1, ComParametersV1, merge_com_parameters_v1};
use crate::parameter_surface_v1::ParameterSurfaceReportV1;
use crate::value_consumption_v1::ResolvedDefaultV1;
use crate::workbook_v1::{CellValueV1, ComSettingsV1, RawCellV1, WorkbookErrorV1};

/// Stable scope policy of the workbook-to-DTO ingestion consumer.
pub const COM_PARAMETER_INGESTION_POLICY_V1: &str =
    "sipi.p5-05g.com-parameter-ingestion-v1.workbook-to-dto-report";

/// Fail-closed errors at the product ingestion boundary.
#[derive(Clone, Debug, PartialEq)]
pub enum ComParameterIngestionErrorV1 {
    /// The caller supplied a surface report that is not self-consistent.
    SurfaceMismatch,
    /// The source workbook lookup failed or found an ambiguous value.
    Workbook(WorkbookErrorV1),
    /// A workbook value cannot be represented by the existing typed value
    /// envelope without guessing or losing information.
    UnsupportedWorkbookValue(String),
    /// A workbook number/array member was non-finite.
    NonFiniteWorkbookValue(String),
    /// An integer cannot be represented exactly by the DTO's `f64` scalar.
    InexactWorkbookInteger(String),
    /// An array shape is unsupported or inconsistent with its payload.
    UnsupportedWorkbookShape(String),
    /// The typed DTO merge rejected the assembled values.
    Parameters(ComParametersErrorV1),
}

impl From<WorkbookErrorV1> for ComParameterIngestionErrorV1 {
    fn from(error: WorkbookErrorV1) -> Self {
        Self::Workbook(error)
    }
}

impl From<ComParametersErrorV1> for ComParameterIngestionErrorV1 {
    fn from(error: ComParametersErrorV1) -> Self {
        Self::Parameters(error)
    }
}

/// Explicit report of how workbook values reached the DTO.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ComParameterConsumptionReportV1 {
    consumed_keys: Vec<String>,
    workbook_value_keys: Vec<String>,
    defaulted_keys: Vec<String>,
    unconsumed_keys: Vec<String>,
}

impl ComParameterConsumptionReportV1 {
    pub fn consumed_keys(&self) -> &[String] {
        &self.consumed_keys
    }

    pub fn workbook_value_keys(&self) -> &[String] {
        &self.workbook_value_keys
    }

    pub fn defaulted_keys(&self) -> &[String] {
        &self.defaulted_keys
    }

    pub fn unconsumed_keys(&self) -> &[String] {
        &self.unconsumed_keys
    }
}

/// Result of the product-owned workbook-to-DTO ingestion consumer.
#[derive(Clone, Debug, PartialEq)]
pub struct ComParameterIngestionV1 {
    dto: ComParametersV1,
    report: ComParameterConsumptionReportV1,
}

impl ComParameterIngestionV1 {
    pub fn dto(&self) -> &ComParametersV1 {
        &self.dto
    }

    pub fn report(&self) -> &ComParameterConsumptionReportV1 {
        &self.report
    }
}

/// Consume a classified workbook surface into the typed COM DTO.
///
/// `surface` must have been produced for `settings` by
/// `classify_parameter_surface_v1`, and `consumed_keys` must be the selected
/// profile's canonical consumed-key list.  The function checks the report's
/// key partition before reading values, then uses the workbook's existing
/// case-insensitive lookup semantics.  A missing workbook key is not an
/// error when a resolved default exists; `merge_com_parameters_v1` retains
/// the existing workbook-priority/default-fallback contract.
pub fn ingest_com_parameters_v1(
    settings: &ComSettingsV1,
    surface: &ParameterSurfaceReportV1,
    consumed_keys: &[String],
    resolved_defaults: &BTreeMap<String, ResolvedDefaultV1>,
) -> Result<ComParameterIngestionV1, ComParameterIngestionErrorV1> {
    validate_surface_partition(settings, surface, consumed_keys)?;
    let consumed_keys = consumed_keys.to_vec();
    let canonical_identities: BTreeSet<String> =
        consumed_keys.iter().map(|key| fold_key(key)).collect();

    let mut workbook_values = BTreeMap::new();
    for key in &consumed_keys {
        if let Some(cell) = settings.lookup_optional_v1(key)? {
            workbook_values.insert(key.clone(), cell_value_to_resolved(key, &cell)?);
        }
    }

    let unconsumed_keys: Vec<String> = surface
        .pairs()
        .iter()
        .map(|pair| pair.key())
        .filter(|key| !canonical_identities.contains(&fold_key(key)))
        .map(str::to_owned)
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect();
    let dto = merge_com_parameters_v1(
        &consumed_keys,
        &workbook_values,
        resolved_defaults,
        &unconsumed_keys,
    )?;

    let workbook_value_keys: Vec<String> = consumed_keys
        .iter()
        .filter(|key| workbook_values.contains_key(*key))
        .cloned()
        .collect();
    let defaulted_keys: Vec<String> = consumed_keys
        .iter()
        .filter(|key| !workbook_values.contains_key(*key) && resolved_defaults.contains_key(*key))
        .cloned()
        .collect();

    Ok(ComParameterIngestionV1 {
        dto,
        report: ComParameterConsumptionReportV1 {
            consumed_keys,
            workbook_value_keys,
            defaulted_keys,
            unconsumed_keys,
        },
    })
}

fn validate_surface_partition(
    settings: &ComSettingsV1,
    surface: &ParameterSurfaceReportV1,
    consumed_keys: &[String],
) -> Result<(), ComParameterIngestionErrorV1> {
    let surface_keys: BTreeSet<&str> = surface.pairs().iter().map(|pair| pair.key()).collect();
    let consumed: BTreeSet<&str> = surface.consumed().iter().map(String::as_str).collect();
    let unconsumed: BTreeSet<&str> = surface.unconsumed().iter().map(String::as_str).collect();
    let canonical: BTreeSet<&str> = consumed_keys.iter().map(String::as_str).collect();
    if canonical.len() != consumed_keys.len()
        || consumed.intersection(&unconsumed).next().is_some()
        || consumed
            .union(&unconsumed)
            .copied()
            .collect::<BTreeSet<_>>()
            != surface_keys
        || !consumed.is_subset(&canonical)
    {
        return Err(ComParameterIngestionErrorV1::SurfaceMismatch);
    }

    let canonical_identities: BTreeSet<String> =
        consumed_keys.iter().map(|key| fold_key(key)).collect();
    if canonical_identities.len() != consumed_keys.len() {
        return Err(ComParameterIngestionErrorV1::SurfaceMismatch);
    }

    // A surface report must describe the same row/column lookup surface.  A
    // key-set-only report from another workbook must not be accepted merely
    // because its names happen to match.
    let observed_pairs = crate::parameter_surface_v1::extract_parameter_pairs_v1(settings)?;
    if observed_pairs != surface.pairs() {
        return Err(ComParameterIngestionErrorV1::SurfaceMismatch);
    }
    let observed_identities: BTreeSet<String> = observed_pairs
        .iter()
        .map(|pair| fold_key(pair.key()))
        .collect();
    if observed_identities.len() != observed_pairs.len() {
        return Err(ComParameterIngestionErrorV1::SurfaceMismatch);
    }
    let observed_keys: BTreeSet<String> = observed_pairs
        .iter()
        .map(|pair| pair.key().to_owned())
        .collect();
    if observed_keys != surface_keys.into_iter().map(str::to_owned).collect() {
        return Err(ComParameterIngestionErrorV1::SurfaceMismatch);
    }
    let observed_consumed: BTreeSet<&str> = observed_keys
        .iter()
        .map(String::as_str)
        .filter(|key| canonical.contains(key))
        .collect();
    let observed_unconsumed: BTreeSet<&str> = observed_keys
        .iter()
        .map(String::as_str)
        .filter(|key| !canonical.contains(key))
        .collect();
    if observed_consumed != consumed || observed_unconsumed != unconsumed {
        return Err(ComParameterIngestionErrorV1::SurfaceMismatch);
    }
    Ok(())
}

fn fold_key(key: &str) -> String {
    key.to_ascii_lowercase()
}

fn cell_value_to_resolved(
    key: &str,
    cell: &RawCellV1,
) -> Result<ResolvedDefaultV1, ComParameterIngestionErrorV1> {
    match cell.value() {
        CellValueV1::None => Err(ComParameterIngestionErrorV1::UnsupportedWorkbookValue(
            key.to_owned(),
        )),
        CellValueV1::Integer(value) => {
            const MAX_EXACT_F64_INTEGER: i64 = 1_i64 << 53;
            if !(-MAX_EXACT_F64_INTEGER..=MAX_EXACT_F64_INTEGER).contains(value) {
                return Err(ComParameterIngestionErrorV1::InexactWorkbookInteger(
                    key.to_owned(),
                ));
            }
            Ok(ResolvedDefaultV1::Scalar(*value as f64))
        }
        CellValueV1::Number(value) => {
            if value.is_finite() {
                Ok(ResolvedDefaultV1::Scalar(*value))
            } else {
                Err(ComParameterIngestionErrorV1::NonFiniteWorkbookValue(
                    key.to_owned(),
                ))
            }
        }
        CellValueV1::Bool(value) => Ok(ResolvedDefaultV1::Boolean(*value)),
        CellValueV1::String(value) => Ok(ResolvedDefaultV1::String(value.clone())),
        CellValueV1::Array { dims, data } => {
            if data.iter().any(|value| !value.is_finite()) {
                return Err(ComParameterIngestionErrorV1::NonFiniteWorkbookValue(
                    key.to_owned(),
                ));
            }
            let expected_len = dims.iter().try_fold(1_usize, |product, dimension| {
                product.checked_mul(*dimension as usize)
            });
            if expected_len != Some(data.len()) || dims.is_empty() || dims.len() > 2 {
                return Err(ComParameterIngestionErrorV1::UnsupportedWorkbookShape(
                    key.to_owned(),
                ));
            }
            match dims.as_slice() {
                [_] if data.is_empty() => Ok(ResolvedDefaultV1::Empty),
                [_] if data.len() == 1 => Ok(ResolvedDefaultV1::Scalar(data[0])),
                [_] => Ok(ResolvedDefaultV1::Vector(data.clone())),
                [_, _] if data.is_empty() => Ok(ResolvedDefaultV1::Empty),
                [_, _] if data.len() == 1 => Ok(ResolvedDefaultV1::Scalar(data[0])),
                [rows, columns] if *rows == 1 || *columns == 1 => {
                    Ok(ResolvedDefaultV1::Vector(data.clone()))
                }
                [_, columns] => {
                    let columns = *columns as usize;
                    Ok(ResolvedDefaultV1::Matrix(
                        data.chunks_exact(columns).map(<[f64]>::to_vec).collect(),
                    ))
                }
                _ => Err(ComParameterIngestionErrorV1::UnsupportedWorkbookShape(
                    key.to_owned(),
                )),
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::parameter_surface_v1::classify_parameter_surface_v1;
    use crate::workbook_v1::{CellValueV1, RawCellV1};

    fn cell(row: usize, column: usize, value: CellValueV1) -> RawCellV1 {
        RawCellV1::new(
            "COM_Settings".to_owned(),
            format!("{}{}", (b'A' + column as u8) as char, row + 1),
            value,
            None,
        )
    }

    fn settings() -> ComSettingsV1 {
        ComSettingsV1::from_cells(
            vec![
                vec![
                    cell(0, 0, CellValueV1::String("fb".to_owned())),
                    cell(0, 1, CellValueV1::Number(53.125e9)),
                ],
                vec![
                    cell(1, 0, CellValueV1::String("unused".to_owned())),
                    cell(1, 1, CellValueV1::String("kept".to_owned())),
                ],
            ],
            None,
        )
    }

    #[test]
    fn consumes_workbook_value_and_default_without_dropping_unconsumed() {
        let settings = settings();
        let canonical = BTreeSet::from(["fb".to_owned(), "a_fext".to_owned()]);
        let surface = classify_parameter_surface_v1(&settings, &canonical).expect("surface");
        let consumed_keys = vec!["fb".to_owned(), "a_fext".to_owned()];
        let defaults = BTreeMap::from([("a_fext".to_owned(), ResolvedDefaultV1::Scalar(0.5))]);
        let result = ingest_com_parameters_v1(&settings, &surface, &consumed_keys, &defaults)
            .expect("ingest");
        assert_eq!(result.report().workbook_value_keys(), &["fb"]);
        assert_eq!(result.report().defaulted_keys(), &["a_fext"]);
        assert_eq!(result.report().unconsumed_keys(), &["unused"]);
        assert_eq!(result.dto().unconsumed(), &["unused"]);
        assert_eq!(
            result.dto().consumed().get("fb"),
            Some(&ResolvedDefaultV1::Scalar(53.125e9))
        );
        assert_eq!(
            result.dto().consumed().get("a_fext"),
            Some(&ResolvedDefaultV1::Scalar(0.5))
        );
    }

    #[test]
    fn rejects_missing_default_after_workbook_none() {
        let settings = settings();
        let canonical = BTreeSet::from(["fb".to_owned(), "a_fext".to_owned()]);
        let surface = classify_parameter_surface_v1(&settings, &canonical).expect("surface");
        let consumed_keys = vec!["fb".to_owned(), "a_fext".to_owned()];
        let error = ingest_com_parameters_v1(&settings, &surface, &consumed_keys, &BTreeMap::new())
            .expect_err("missing value");
        assert_eq!(
            error,
            ComParameterIngestionErrorV1::Parameters(ComParametersErrorV1::MissingValue(
                "a_fext".to_owned()
            ))
        );
    }

    #[test]
    fn rejects_surface_from_another_workbook() {
        let first = settings();
        let second = ComSettingsV1::from_cells(
            vec![
                vec![
                    cell(0, 0, CellValueV1::String("fb".to_owned())),
                    cell(0, 1, CellValueV1::String("53.125e9".to_owned())),
                ],
                vec![
                    cell(1, 0, CellValueV1::String("unused".to_owned())),
                    cell(1, 1, CellValueV1::String("kept".to_owned())),
                ],
            ],
            None,
        );
        let canonical = BTreeSet::from(["fb".to_owned(), "a_fext".to_owned()]);
        let surface = classify_parameter_surface_v1(&first, &canonical).expect("surface");
        let consumed_keys = vec!["fb".to_owned(), "a_fext".to_owned()];
        assert_eq!(
            ingest_com_parameters_v1(&second, &surface, &consumed_keys, &BTreeMap::new())
                .expect_err("mismatch"),
            ComParameterIngestionErrorV1::SurfaceMismatch
        );
    }

    #[test]
    fn converts_typed_workbook_values_without_string_guessing() {
        let settings = ComSettingsV1::from_cells(
            vec![
                vec![
                    cell(0, 0, CellValueV1::String("flag".to_owned())),
                    cell(0, 1, CellValueV1::Bool(true)),
                ],
                vec![
                    cell(1, 0, CellValueV1::String("mode".to_owned())),
                    cell(1, 1, CellValueV1::String("MM".to_owned())),
                ],
                vec![
                    cell(2, 0, CellValueV1::String("taps".to_owned())),
                    cell(
                        2,
                        1,
                        CellValueV1::Array {
                            dims: vec![2],
                            data: vec![1.0, 2.0],
                        },
                    ),
                ],
            ],
            None,
        );
        let canonical = BTreeSet::from(["flag".to_owned(), "mode".to_owned(), "taps".to_owned()]);
        let surface = classify_parameter_surface_v1(&settings, &canonical).expect("surface");
        let consumed_keys = vec!["flag".to_owned(), "mode".to_owned(), "taps".to_owned()];
        let result =
            ingest_com_parameters_v1(&settings, &surface, &consumed_keys, &BTreeMap::new())
                .expect("ingest");
        assert_eq!(
            result.dto().consumed().get("flag"),
            Some(&ResolvedDefaultV1::Boolean(true))
        );
        assert_eq!(
            result.dto().consumed().get("mode"),
            Some(&ResolvedDefaultV1::String("MM".to_owned()))
        );
        assert_eq!(
            result.dto().consumed().get("taps"),
            Some(&ResolvedDefaultV1::Vector(vec![1.0, 2.0]))
        );
    }

    #[test]
    fn preserves_matrix_shape_and_rejects_inconsistent_dimensions() {
        let matrix_settings = ComSettingsV1::from_cells(
            vec![vec![
                cell(0, 0, CellValueV1::String("matrix".to_owned())),
                cell(
                    0,
                    1,
                    CellValueV1::Array {
                        dims: vec![2, 2],
                        data: vec![1.0, 2.0, 3.0, 4.0],
                    },
                ),
            ]],
            None,
        );
        let canonical = BTreeSet::from(["matrix".to_owned()]);
        let surface = classify_parameter_surface_v1(&matrix_settings, &canonical).expect("surface");
        let result = ingest_com_parameters_v1(
            &matrix_settings,
            &surface,
            &["matrix".to_owned()],
            &BTreeMap::new(),
        )
        .expect("matrix ingest");
        assert_eq!(
            result.dto().consumed().get("matrix"),
            Some(&ResolvedDefaultV1::Matrix(vec![
                vec![1.0, 2.0],
                vec![3.0, 4.0]
            ]))
        );

        let malformed = ComSettingsV1::from_cells(
            vec![vec![
                cell(0, 0, CellValueV1::String("matrix".to_owned())),
                cell(
                    0,
                    1,
                    CellValueV1::Array {
                        dims: vec![2, 2],
                        data: vec![1.0, 2.0, 3.0],
                    },
                ),
            ]],
            None,
        );
        let surface = classify_parameter_surface_v1(&malformed, &canonical).expect("surface");
        assert_eq!(
            ingest_com_parameters_v1(
                &malformed,
                &surface,
                &["matrix".to_owned()],
                &BTreeMap::new(),
            ),
            Err(ComParameterIngestionErrorV1::UnsupportedWorkbookShape(
                "matrix".to_owned()
            ))
        );
    }

    #[test]
    fn rejects_integer_that_cannot_be_represented_exactly() {
        let settings = ComSettingsV1::from_cells(
            vec![vec![
                cell(0, 0, CellValueV1::String("count".to_owned())),
                cell(0, 1, CellValueV1::Integer((1_i64 << 53) + 1)),
            ]],
            None,
        );
        let canonical = BTreeSet::from(["count".to_owned()]);
        let surface = classify_parameter_surface_v1(&settings, &canonical).expect("surface");
        assert_eq!(
            ingest_com_parameters_v1(&settings, &surface, &["count".to_owned()], &BTreeMap::new(),),
            Err(ComParameterIngestionErrorV1::InexactWorkbookInteger(
                "count".to_owned()
            ))
        );
    }

    #[test]
    fn case_insensitive_lookup_and_report_share_one_identity() {
        let settings = ComSettingsV1::from_cells(
            vec![vec![
                cell(0, 0, CellValueV1::String("FB".to_owned())),
                cell(0, 1, CellValueV1::Number(53.125e9)),
            ]],
            None,
        );
        let canonical = BTreeSet::from(["fb".to_owned()]);
        let surface = classify_parameter_surface_v1(&settings, &canonical).expect("surface");
        let result =
            ingest_com_parameters_v1(&settings, &surface, &["fb".to_owned()], &BTreeMap::new())
                .expect("case-insensitive ingest");
        assert_eq!(result.report().consumed_keys(), &["fb"]);
        assert_eq!(result.report().workbook_value_keys(), &["fb"]);
        assert!(result.report().unconsumed_keys().is_empty());
    }

    #[test]
    fn rejects_case_folded_duplicate_workbook_keys() {
        let settings = ComSettingsV1::from_cells(
            vec![
                vec![
                    cell(0, 0, CellValueV1::String("fb".to_owned())),
                    cell(0, 1, CellValueV1::Number(1.0)),
                ],
                vec![
                    cell(1, 0, CellValueV1::String("FB".to_owned())),
                    cell(1, 1, CellValueV1::Number(2.0)),
                ],
            ],
            None,
        );
        let canonical = BTreeSet::from(["fb".to_owned()]);
        let surface = classify_parameter_surface_v1(&settings, &canonical).expect("surface");
        assert_eq!(
            ingest_com_parameters_v1(&settings, &surface, &["fb".to_owned()], &BTreeMap::new(),),
            Err(ComParameterIngestionErrorV1::SurfaceMismatch)
        );
    }
}
