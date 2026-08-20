//! CSV configuration reader (port of
//! `agent_com/config/excel.py` `ComSettings.from_csv` / `_csv_value`).
//!
//! Ported from agent-com (MIT source, P5-05b source map): RFC 4180
//! row/field parsing aligned with Python's `csv.reader`, utf-8-sig
//! decoding, and the r4.80 numeric string classification. The MATLAB
//! .mat reader path (`from_mat`) is a separate sub-slice.

use std::fs;
use std::path::Path;

use crate::workbook_v1::{
    column_letter, CellValueV1, ComSettingsV1, RawCellV1, WorkbookErrorV1,
};

/// Explicit scope policy of the CSV reader stage.
pub const CSV_READER_POLICY_V1: &str = "sipi.p5-05b.csv-reader-v1.rfc4180-utf8sig";

/// Port of `_CSV_NUMBER`: `[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?`.
fn is_csv_number(value: &str) -> bool {
    let bytes = value.as_bytes();
    let mut index = 0usize;
    if index < bytes.len() && (bytes[index] == b'+' || bytes[index] == b'-') {
        index += 1;
    }
    let mut digits = 0usize;
    while index < bytes.len() && bytes[index].is_ascii_digit() {
        index += 1;
        digits += 1;
    }
    if index < bytes.len() && bytes[index] == b'.' {
        index += 1;
        while index < bytes.len() && bytes[index].is_ascii_digit() {
            index += 1;
            digits += 1;
        }
    }
    if digits == 0 {
        return false;
    }
    if index < bytes.len() && (bytes[index] == b'e' || bytes[index] == b'E') {
        index += 1;
        if index < bytes.len() && (bytes[index] == b'+' || bytes[index] == b'-') {
            index += 1;
        }
        let mut exponent_digits = 0usize;
        while index < bytes.len() && bytes[index].is_ascii_digit() {
            index += 1;
            exponent_digits += 1;
        }
        if exponent_digits == 0 {
            return false;
        }
    }
    index == bytes.len()
}

/// Port of `_csv_value`: empty -> None; numeric pattern -> float;
/// otherwise the raw string.
pub fn csv_value_v1(value: &str) -> CellValueV1 {
    if value.is_empty() {
        return CellValueV1::None;
    }
    if is_csv_number(value) {
        if let Ok(numeric) = value.parse::<f64>() {
            return CellValueV1::Number(numeric);
        }
    }
    CellValueV1::String(value.to_string())
}

/// Split one RFC 4180 logical record into fields (aligned with Python's
/// `csv.reader`: double-quote escapes inside quoted fields, quoted
/// fields may contain separators and line breaks).
fn parse_csv_record(record: &str) -> Result<Vec<String>, WorkbookErrorV1> {
    let mut fields = Vec::new();
    let mut current = String::new();
    let mut index = 0usize;
    let mut in_quotes = false;
    let mut field_quoted = false;
    let bytes: Vec<char> = record.chars().collect();
    while index < bytes.len() {
        let character = bytes[index];
        if in_quotes {
            if character == '"' {
                if index + 1 < bytes.len() && bytes[index + 1] == '"' {
                    current.push('"');
                    index += 2;
                    continue;
                }
                in_quotes = false;
                index += 1;
                continue;
            }
            current.push(character);
            index += 1;
            continue;
        }
        if character == '"' && current.is_empty() && !field_quoted {
            in_quotes = true;
            field_quoted = true;
            index += 1;
            continue;
        }
        if character == ',' {
            fields.push(current.clone());
            current.clear();
            field_quoted = false;
            index += 1;
            continue;
        }
        if character == '\n' || character == '\r' {
            break;
        }
        current.push(character);
        index += 1;
    }
    // Python's csv.reader tolerates an unterminated quote: the opening
    // quote is consumed and the field runs to the record end.
    fields.push(current);
    Ok(fields)
}

/// Read the `xlsread(... .csv)` compatibility input as raw cells
/// (port of `ComSettings.from_csv`).
pub fn read_com_settings_csv_v1(path: &Path) -> Result<ComSettingsV1, WorkbookErrorV1> {
    let bytes = fs::read(path).map_err(|_| WorkbookErrorV1::InvalidCsvConfiguration)?;
    let mut text = String::from_utf8(bytes)
        .map_err(|_| WorkbookErrorV1::InvalidCsvConfiguration)?;
    if let Some(rest) = text.strip_prefix('\u{feff}') {
        text = rest.to_string();
    }
    let mut rows = Vec::new();
    let mut records: Vec<&str> = text.split('\n').collect();
    if records.last().is_some_and(|record| record.is_empty()) {
        // A trailing line break does not produce a record in csv.reader.
        records.pop();
    }
    for record in records {
        let record = record.strip_suffix('\r').unwrap_or(record);
        if record.is_empty() {
            // Python csv.reader yields an empty row for a blank line.
            rows.push(Vec::new());
            continue;
        }
        let fields = parse_csv_record(record)?;
        let cells: Vec<RawCellV1> = fields
            .iter()
            .enumerate()
            .map(|(column, value)| {
                RawCellV1::new(
                    "COM_Settings".to_string(),
                    format!("{}{}", column_letter(column + 1), rows.len() + 1),
                    csv_value_v1(value),
                    None,
                )
            })
            .collect();
        rows.push(cells);
    }
    Ok(ComSettingsV1::from_cells(rows, Some(path.to_path_buf())))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn csv_number_pattern() {
        assert!(is_csv_number("53.125"));
        assert!(is_csv_number("5"));
        assert!(is_csv_number("-2.5"));
        assert!(is_csv_number("+1"));
        assert!(is_csv_number(".5"));
        assert!(is_csv_number("1."));
        assert!(is_csv_number("1e5"));
        assert!(is_csv_number("1E-5"));
        assert!(!is_csv_number(""));
        assert!(!is_csv_number("abc"));
        assert!(!is_csv_number("1a"));
        assert!(!is_csv_number("nan"));
        assert!(!is_csv_number("inf"));
        assert!(!is_csv_number("1e"));
    }

    #[test]
    fn csv_value_classification() {
        assert_eq!(csv_value_v1(""), CellValueV1::None);
        assert_eq!(csv_value_v1("5"), CellValueV1::Number(5.0));
        assert_eq!(csv_value_v1("53.125"), CellValueV1::Number(53.125));
        assert_eq!(csv_value_v1("-2.5"), CellValueV1::Number(-2.5));
        assert_eq!(csv_value_v1("1e5"), CellValueV1::Number(100000.0));
        assert_eq!(
            csv_value_v1("[ 1 3 2 4 ]"),
            CellValueV1::String("[ 1 3 2 4 ]".to_string())
        );
        assert_eq!(csv_value_v1("inf"), CellValueV1::String("inf".to_string()));
    }

    #[test]
    fn record_parsing_quotes_and_escapes() {
        let fields = parse_csv_record("a,\"b,c\",\"d\"\"e\"").expect("fields");
        assert_eq!(fields, vec!["a", "b,c", "d\"e"]);
        let bare = parse_csv_record("x\"y,z").expect("fields");
        assert_eq!(bare, vec!["x\"y", "z"]);
        // Python csv.reader tolerates an unterminated quote (stripped).
        let tolerated = parse_csv_record("\"unterminated").expect("fields");
        assert_eq!(tolerated, vec!["unterminated"]);
    }
}