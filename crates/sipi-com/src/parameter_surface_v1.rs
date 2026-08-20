//! Parameter surface extraction and consumption classification
//! (P5-05d).
//!
//! Extracts every (key, value) pair from a workbook surface with the
//! r4.80 lookup semantics (a non-empty string cell whose right-hand
//! neighbor exists and is non-empty) and classifies each key against
//! the canonical consumption key set observed from the authorized
//! MATLAB r4.80 source (`p5-r480-canonical-parameter-reference.v1.yaml`,
//! 214 keys / 229 xls_parameter calls). Unconsumed workbook fields
//! remain in the report; nothing is dropped.

use std::collections::BTreeSet;

use crate::workbook_v1::{CellValueV1, ComSettingsV1, RawCellV1, WorkbookErrorV1};

/// Explicit scope policy of the parameter surface stage.
pub const PARAMETER_SURFACE_POLICY_V1: &str =
    "sipi.p5-05d.parameter-surface-v1.key-extract-classify";

/// One extracted parameter pair.
#[derive(Clone, Debug, PartialEq)]
pub struct ParameterPairV1 {
    key: String,
    left_coordinate: String,
    right_coordinate: String,
    value_kind: String,
}

impl ParameterPairV1 {
    pub fn key(&self) -> &str {
        &self.key
    }

    pub fn left_coordinate(&self) -> &str {
        &self.left_coordinate
    }

    pub fn right_coordinate(&self) -> &str {
        &self.right_coordinate
    }

    pub fn value_kind(&self) -> &str {
        &self.value_kind
    }
}

fn value_kind_name(value: &CellValueV1) -> &'static str {
    match value {
        CellValueV1::None => "None",
        CellValueV1::Integer(_) => "Integer",
        CellValueV1::Number(_) => "Number",
        CellValueV1::Bool(_) => "Bool",
        CellValueV1::String(_) => "String",
        CellValueV1::Array { .. } => "Array",
    }
}

/// Port of the lookup scan surface: a non-empty string cell whose
/// right-hand neighbor exists and is not empty is one parameter pair.
pub fn extract_parameter_pairs_v1(
    settings: &ComSettingsV1,
) -> Result<Vec<ParameterPairV1>, WorkbookErrorV1> {
    let mut pairs = Vec::new();
    for row in settings.rows() {
        for (index, cell) in row.iter().enumerate() {
            let CellValueV1::String(key) = cell.value() else {
                continue;
            };
            if key.trim().is_empty() {
                continue;
            }
            let Some(right) = row.get(index + 1) else {
                continue;
            };
            if right.value() == &CellValueV1::None {
                continue;
            }
            pairs.push(ParameterPairV1 {
                key: key.clone(),
                left_coordinate: cell.coordinate().to_string(),
                right_coordinate: right.coordinate().to_string(),
                value_kind: value_kind_name(right.value()).to_string(),
            });
        }
    }
    Ok(pairs)
}

/// The classification report: every workbook pair is retained and the
/// unique keys are split into consumed (in the canonical set) and
/// unconsumed (workbook fields the r4.80 source never reads).
#[derive(Clone, Debug, PartialEq)]
pub struct ParameterSurfaceReportV1 {
    pairs: Vec<ParameterPairV1>,
    consumed: Vec<String>,
    unconsumed: Vec<String>,
}

impl ParameterSurfaceReportV1 {
    pub fn pairs(&self) -> &[ParameterPairV1] {
        &self.pairs
    }

    pub fn consumed(&self) -> &[String] {
        &self.consumed
    }

    pub fn unconsumed(&self) -> &[String] {
        &self.unconsumed
    }
}

pub fn classify_parameter_surface_v1(
    settings: &ComSettingsV1,
    canonical: &BTreeSet<String>,
) -> Result<ParameterSurfaceReportV1, WorkbookErrorV1> {
    let pairs = extract_parameter_pairs_v1(settings)?;
    let keys: BTreeSet<String> = pairs.iter().map(|pair| pair.key.clone()).collect();
    let mut consumed: Vec<String> = Vec::new();
    let mut unconsumed: Vec<String> = Vec::new();
    for key in keys.iter() {
        if canonical.contains(key) {
            consumed.push(key.clone());
        } else {
            unconsumed.push(key.clone());
        }
    }
    Ok(ParameterSurfaceReportV1 {
        pairs,
        consumed,
        unconsumed,
    })
}

/// Raw cell accessor used by the extractor (coordinate/value).
pub fn pair_value_kind(cell: &RawCellV1) -> &'static str {
    value_kind_name(cell.value())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::workbook_v1::{column_letter, CellValueV1, RawCellV1};

    fn cell(row: usize, column: usize, value: CellValueV1) -> RawCellV1 {
        RawCellV1::new(
            "COM_Settings".to_string(),
            format!("{}{}", column_letter(column + 1), row + 1),
            value,
            None,
        )
    }

    fn settings() -> ComSettingsV1 {
        let rows = vec![
            vec![
                cell(0, 0, CellValueV1::String("f_b".to_string())),
                cell(0, 1, CellValueV1::Number(53.125)),
            ],
            vec![
                cell(1, 0, CellValueV1::String("A_ft".to_string())),
                cell(1, 1, CellValueV1::Number(0.6)),
            ],
            vec![
                cell(2, 0, CellValueV1::String("unused_key".to_string())),
                cell(2, 1, CellValueV1::String("value".to_string())),
            ],
            vec![
                cell(3, 0, CellValueV1::String("empty_right".to_string())),
                cell(3, 1, CellValueV1::None),
            ],
            vec![cell(4, 0, CellValueV1::Number(1.0))],
        ];
        ComSettingsV1::from_cells(rows, None)
    }

    #[test]
    fn extraction_keeps_all_fields() {
        let settings = settings();
        let pairs = extract_parameter_pairs_v1(&settings).expect("pairs");
        assert_eq!(pairs.len(), 3);
        assert_eq!(pairs[0].key(), "f_b");
        assert_eq!(pairs[0].left_coordinate(), "A1");
        assert_eq!(pairs[0].right_coordinate(), "B1");
        assert_eq!(pairs[0].value_kind(), "Number");
        assert_eq!(pairs[2].key(), "unused_key");
    }

    #[test]
    fn classification_splits_consumed_and_unconsumed() {
        let settings = settings();
        let canonical: BTreeSet<String> = ["f_b".to_string(), "A_ft".to_string()]
            .into_iter()
            .collect();
        let report = classify_parameter_surface_v1(&settings, &canonical).expect("report");
        assert_eq!(report.consumed(), &["A_ft", "f_b"]);
        assert_eq!(report.unconsumed(), &["unused_key"]);
        // empty-right pair is not dropped from the report surface: it is
        // simply not a key pair; the report retains all extracted pairs.
        assert_eq!(report.pairs().len(), 3);
    }

    #[test]
    fn policy_string_is_fixed() {
        assert_eq!(
            PARAMETER_SURFACE_POLICY_V1,
            "sipi.p5-05d.parameter-surface-v1.key-extract-classify",
        );
    }
}