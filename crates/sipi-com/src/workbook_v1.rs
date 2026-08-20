//! R480 COM_Settings workbook importer (port of
//! `agent_com/config/excel.py`).
//!
//! Ported from agent-com (MIT source, P5-05a source map): strict
//! container validation, Strict/Transitional OOXML cell reading with
//! formula-cache rejection, typed cell values, and the r4.80 keyword
//! lookup semantics (`ComSettings.lookup_optional`/`lookup`). The
//! CSV/MAT reader paths are separate sub-slices.

use std::fs::File;
use std::io::{Cursor, Read};
use std::path::{Path, PathBuf};

use quick_xml::Reader;
use quick_xml::events::Event;
use zip::ZipArchive;

/// Explicit scope policy of the workbook importer stage.
pub const WORKBOOK_IMPORT_POLICY_V1: &str =
    "sipi.p5-05a.workbook-v1.xlsx-reader-lookup";

/// A typed cell value (port of the Python reader's object values).
#[derive(Clone, Debug, PartialEq)]
pub enum CellValueV1 {
    None,
    Integer(i64),
    Number(f64),
    Bool(bool),
    String(String),
    /// Multi-element numeric cell values (C-order flattening with the
    /// source's reshape(-1) semantics; MATLAB column-major payload is
    /// reordered).
    Array { dims: Vec<u32>, data: Vec<f64> },
}

/// One raw workbook cell (port of `RawCell`).
#[derive(Clone, Debug, PartialEq)]
pub struct RawCellV1 {
    sheet: String,
    coordinate: String,
    value: CellValueV1,
    formula: Option<String>,
}

impl RawCellV1 {
    pub(crate) fn new(
        sheet: String,
        coordinate: String,
        value: CellValueV1,
        formula: Option<String>,
    ) -> Self {
        Self { sheet, coordinate, value, formula }
    }

    pub fn sheet(&self) -> &str {
        &self.sheet
    }

    pub fn coordinate(&self) -> &str {
        &self.coordinate
    }

    pub fn value(&self) -> &CellValueV1 {
        &self.value
    }

    pub fn formula(&self) -> Option<&str> {
        self.formula.as_deref()
    }
}

/// Fail-closed workbook import errors.
#[derive(Clone, Debug, PartialEq)]
pub enum WorkbookErrorV1 {
    NotXlsx,
    InvalidContainer,
    MacroContentNotPermitted,
    ExternalLinksNotPermitted,
    NoComSettingsWorksheet,
    InvalidWorkbookXml,
    InvalidCoordinate,
    FormulaCacheMissing,
    UnsupportedFormulaCacheType,
    InvalidSharedStringIndex,
    InvalidCellValue,
    CalculationPolicyRequiresRecalc,
    InvalidCsvConfiguration,
    InvalidMatConfiguration,
    MissingParameterVariable,
    UnsupportedMatClass,
    DuplicateParameter(String),
    MissingParameter(String),
}

fn column_index(letters: &str) -> Option<usize> {
    let mut value = 0usize;
    for byte in letters.bytes() {
        let digit = (byte as usize).checked_sub(b'A' as usize)?;
        if digit >= 26 {
            return None;
        }
        value = value.checked_mul(26)?.checked_add(digit + 1)?;
    }
    if letters.is_empty() {
        None
    } else {
        Some(value)
    }
}

pub(crate) fn column_letter(index: usize) -> String {
    let mut letters = String::new();
    let mut value = index;
    while value > 0 {
        let remainder = (value - 1) % 26;
        letters.insert(0, (b'A' + remainder as u8) as char);
        value = (value - 1) / 26;
    }
    letters
}

fn split_coordinate(coordinate: &str) -> Option<(usize, usize)> {
    let split = coordinate
        .char_indices()
        .find(|(_, character)| character.is_ascii_digit())?;
    let (letter_end, _) = split;
    let (letters, digits) = coordinate.split_at(letter_end);
    if letters.is_empty() || digits.is_empty() {
        return None;
    }
    let column = column_index(letters)?;
    let row: usize = digits.parse().ok()?;
    Some((row, column))
}

fn local_name<'a>(name: quick_xml::name::QName<'a>) -> &'a [u8] {
    let bytes: &'a [u8] = name.0;
    match bytes.iter().position(|byte| *byte == b':') {
        Some(index) => &bytes[index + 1..],
        None => bytes,
    }
}

fn attribute_value<'a>(
    attributes: &[quick_xml::events::attributes::Attribute<'a>],
    key: &[u8],
) -> Option<String> {
    for attribute in attributes {
        if local_name(attribute.key) == key {
            return Some(attribute.value.as_ref().to_vec().into_iter().map(|b| b as char).collect());
        }
    }
    None
}


fn classify_cell_value(
    kind: Option<&str>,
    raw_value: Option<&str>,
    strings: &[String],
    strict: bool,
) -> Result<CellValueV1, WorkbookErrorV1> {
    let Some(raw_value) = raw_value else {
        return Ok(CellValueV1::None);
    };
    match kind {
        Some("s") => {
            let index: usize = raw_value
                .trim()
                .parse()
                .map_err(|_| WorkbookErrorV1::InvalidSharedStringIndex)?;
            let value = strings
                .get(index)
                .ok_or(WorkbookErrorV1::InvalidSharedStringIndex)?;
            Ok(CellValueV1::String(value.clone()))
        }
        Some("b") => Ok(CellValueV1::Bool(raw_value != "0")),
        Some("str") => Ok(CellValueV1::String(raw_value.to_string())),
        Some("inlineStr") => {
            if strict {
                Ok(CellValueV1::String(raw_value.to_string()))
            } else {
                Err(WorkbookErrorV1::InvalidCellValue)
            }
        }
        Some("e") => Ok(CellValueV1::String(raw_value.to_string())),
        Some("d") => {
            if strict {
                Ok(CellValueV1::String(raw_value.to_string()))
            } else {
                Err(WorkbookErrorV1::UnsupportedFormulaCacheType)
            }
        }
        _ => {
            let Ok(numeric) = raw_value.trim().parse::<f64>() else {
                return Ok(CellValueV1::String(raw_value.to_string()));
            };
            if numeric.fract() == 0.0 {
                if numeric >= i64::MIN as f64 && numeric <= i64::MAX as f64 {
                    Ok(CellValueV1::Integer(numeric as i64))
                } else {
                    Err(WorkbookErrorV1::InvalidCellValue)
                }
            } else {
                Ok(CellValueV1::Number(numeric))
            }
        }
    }
}

fn read_shared_strings(archive: &mut ZipArchive<File>) -> Result<Vec<String>, WorkbookErrorV1> {
    let mut buffer = Vec::new();
    match archive.by_name("xl/sharedStrings.xml") {
        Ok(mut entry) => {
            entry
                .read_to_end(&mut buffer)
                .map_err(|_| WorkbookErrorV1::InvalidWorkbookXml)?;
        }
        Err(_) => return Ok(Vec::new()),
    }
    let mut reader = Reader::from_reader(Cursor::new(buffer));
    let mut event_buffer = Vec::new();
    reader.config_mut().trim_text(false);
    let mut strings = Vec::new();
    let mut current = String::new();
    let mut in_si = false;
    loop {
        match reader
            .read_event_into(&mut event_buffer)
            .map_err(|_| WorkbookErrorV1::InvalidWorkbookXml)?
        {
            Event::Start(event) => {
                if local_name(event.name()) == b"si" {
                    in_si = true;
                    current.clear();
                }
            }
            Event::Text(text) => {
                if in_si {
                    let value = text
                        .unescape()
                        .map_err(|_| WorkbookErrorV1::InvalidWorkbookXml)?;
                    current.push_str(&value);
                }
            }
            Event::End(event) => {
                if local_name(event.name()) == b"si" {
                    in_si = false;
                    strings.push(current.clone());
                }
            }
            Event::Eof => break,
            _ => {}
        }
    }
    Ok(strings)
}

struct SheetLocation {
    path: String,
}

fn locate_com_settings(archive: &mut ZipArchive<File>) -> Result<SheetLocation, WorkbookErrorV1> {
    let mut workbook_buffer = Vec::new();
    archive
        .by_name("xl/workbook.xml")
        .map_err(|_| WorkbookErrorV1::InvalidWorkbookXml)?
        .read_to_end(&mut workbook_buffer)
        .map_err(|_| WorkbookErrorV1::InvalidWorkbookXml)?;
    let mut rels_buffer = Vec::new();
    archive
        .by_name("xl/_rels/workbook.xml.rels")
        .map_err(|_| WorkbookErrorV1::InvalidWorkbookXml)?
        .read_to_end(&mut rels_buffer)
        .map_err(|_| WorkbookErrorV1::InvalidWorkbookXml)?;
    let mut reader = Reader::from_reader(Cursor::new(workbook_buffer));
    let mut event_buffer = Vec::new();
    reader.config_mut().trim_text(false);
    let mut relationship_id: Option<String> = None;
    let mut sheet_path: Option<String> = None;
    let mut calc_mode: Option<String> = None;
    let mut full_calc_on_load: Option<String> = None;
    loop {
        match reader
            .read_event_into(&mut event_buffer)
            .map_err(|_| WorkbookErrorV1::InvalidWorkbookXml)?
        {
            Event::Start(event) | Event::Empty(event) => match local_name(event.name()) {
                b"sheet" => {
                    let attributes: Vec<_> = event
                        .attributes()
                        .collect::<Result<_, _>>()
                        .map_err(|_| WorkbookErrorV1::InvalidWorkbookXml)?;
                    let name = attribute_value(&attributes, b"name");
                    if name.as_deref() == Some("COM_Settings") {
                        relationship_id = attribute_value(&attributes, b"id");
                    }
                }
                b"calcPr" => {
                    let attributes: Vec<_> = event
                        .attributes()
                        .collect::<Result<_, _>>()
                        .map_err(|_| WorkbookErrorV1::InvalidWorkbookXml)?;
                    calc_mode = attribute_value(&attributes, b"calcMode");
                    full_calc_on_load =
                        attribute_value(&attributes, b"fullCalcOnLoad");
                }
                _ => {}
            },
            Event::Eof => break,
            _ => {}
        }
    }
    if let Some(mode) = calc_mode {
        if mode == "manual" {
            return Err(WorkbookErrorV1::CalculationPolicyRequiresRecalc);
        }
    }
    if full_calc_on_load.as_deref() == Some("1") {
        return Err(WorkbookErrorV1::CalculationPolicyRequiresRecalc);
    }
    let Some(relationship_id) = relationship_id else {
        return Err(WorkbookErrorV1::NoComSettingsWorksheet);
    };
    let mut rels_reader = Reader::from_reader(Cursor::new(rels_buffer));
    rels_reader.config_mut().trim_text(false);
    loop {
        match rels_reader
            .read_event_into(&mut event_buffer)
            .map_err(|_| WorkbookErrorV1::InvalidWorkbookXml)?
        {
            Event::Start(event) | Event::Empty(event) => {
                if local_name(event.name()) == b"Relationship" {
                    let attributes: Vec<_> = event
                        .attributes()
                        .collect::<Result<_, _>>()
                        .map_err(|_| WorkbookErrorV1::InvalidWorkbookXml)?;
                    let id = attribute_value(&attributes, b"Id");
                    if id.as_deref() == Some(relationship_id.as_str()) {
                        let target = attribute_value(&attributes, b"Target");
                        if let Some(target) = target {
                            let joined = format!("xl/{}", target);
                            let mut parts: Vec<&str> = joined.split('/').collect();
                            let mut normalized: Vec<String> = Vec::new();
                            for part in parts.drain(..) {
                                if part == ".." {
                                    normalized.pop();
                                } else if part != "." && !part.is_empty() {
                                    normalized.push(part.to_string());
                                }
                            }
                            sheet_path = Some(normalized.join("/"));
                            break;
                        }
                    }
                }
            }
            Event::Eof => break,
            _ => {}
        }
    }
    match sheet_path {
        Some(path) => Ok(SheetLocation { path }),
        None => Err(WorkbookErrorV1::NoComSettingsWorksheet),
    }
}

fn parse_sheet_cells(
    sheet_xml: &[u8],
    strings: &[String],
    strict: bool,
) -> Result<Vec<Vec<RawCellV1>>, WorkbookErrorV1> {
    let mut reader = Reader::from_reader(Cursor::new(sheet_xml));
    let mut event_buffer = Vec::new();
    reader.config_mut().trim_text(false);
    let mut cells: std::collections::HashMap<(usize, usize), RawCellV1> = Default::default();
    let mut max_row = 0usize;
    let mut max_column = 0usize;
    let mut current_coordinate: Option<String> = None;
    let mut current_kind: Option<String> = None;
    let mut current_formula: Option<String> = None;
    let mut current_raw: Option<String> = None;
    let mut current_inline: String = String::new();
    let mut in_is = false;
    let mut in_inline_str = false;
    let mut in_formula = false;
    let mut in_value = false;
    loop {
        match reader
            .read_event_into(&mut event_buffer)
            .map_err(|_| WorkbookErrorV1::InvalidWorkbookXml)?
        {
            Event::Start(event) => match local_name(event.name()) {
                b"c" => {
                    current_formula = None;
                    current_raw = None;
                    current_inline.clear();
                    let attributes: Vec<_> = event
                        .attributes()
                        .collect::<Result<_, _>>()
                        .map_err(|_| WorkbookErrorV1::InvalidWorkbookXml)?;
                    current_coordinate = attribute_value(&attributes, b"r");
                    current_kind = attribute_value(&attributes, b"t");
                }
                b"f" => {
                    current_formula = Some(String::new());
                    in_formula = true;
                }
                b"v" => {
                    current_raw = Some(String::new());
                    in_value = true;
                }
                b"is" => {
                    in_is = true;
                    in_inline_str = true;
                }
                _ => {}
            },
            Event::Empty(event) => match local_name(event.name()) {
                b"c" => {
                    current_formula = None;
                    current_raw = None;
                    current_inline.clear();
                    let attributes: Vec<_> = event
                        .attributes()
                        .collect::<Result<_, _>>()
                        .map_err(|_| WorkbookErrorV1::InvalidWorkbookXml)?;
                    current_coordinate = attribute_value(&attributes, b"r");
                    current_kind = attribute_value(&attributes, b"t");
                    flush_cell(
                        &mut cells,
                        &mut max_row,
                        &mut max_column,
                        &current_coordinate,
                        &current_kind,
                        &current_formula,
                        &current_raw,
                        &current_inline,
                        in_inline_str,
                        strict,
                        strings,
                    )?;
                }
                b"f" => {
                    // Empty formula element.
                }
                b"v" => {}
                _ => {}
            },
            Event::Text(text) => {
                let value = text
                    .unescape()
                    .map_err(|_| WorkbookErrorV1::InvalidWorkbookXml)?;
                if in_is {
                    current_inline.push_str(&value);
                } else if in_formula {
                    if let Some(formula) = current_formula.as_mut() {
                        formula.push_str(&value);
                    }
                } else if in_value {
                    if let Some(raw) = current_raw.as_mut() {
                        raw.push_str(&value);
                    }
                }
            }
            Event::End(event) => match local_name(event.name()) {
                b"c" => {
                    flush_cell(
                        &mut cells,
                        &mut max_row,
                        &mut max_column,
                        &current_coordinate,
                        &current_kind,
                        &current_formula,
                        &current_raw,
                        &current_inline,
                        in_inline_str,
                        strict,
                        strings,
                    )?;
                    current_coordinate = None;
                    current_formula = None;
                    current_raw = None;
                    current_inline.clear();
                    in_inline_str = false;
                }
                b"f" => {
                    in_formula = false;
                }
                b"v" => {
                    in_value = false;
                }
                b"is" => {
                    in_is = false;
                }
                _ => {}
            },
            Event::Eof => break,
            _ => {}
        }
    }
    Ok((1..=max_row)
        .map(|row| {
            (1..=max_column)
                .map(|column| {
                    cells
                        .get(&(row, column))
                        .cloned()
                        .unwrap_or_else(|| RawCellV1 {
                            sheet: "COM_Settings".to_string(),
                            coordinate: format!("{}{}", column_letter(column), row),
                            value: CellValueV1::None,
                            formula: None,
                        })
                })
                .collect()
        })
        .collect())
}

#[allow(clippy::too_many_arguments)]
fn flush_cell(
    cells: &mut std::collections::HashMap<(usize, usize), RawCellV1>,
    max_row: &mut usize,
    max_column: &mut usize,
    coordinate: &Option<String>,
    kind: &Option<String>,
    formula: &Option<String>,
    raw: &Option<String>,
    inline: &String,
    in_inline_str: bool,
    strict: bool,
    strings: &[String],
) -> Result<(), WorkbookErrorV1> {
    let Some(coordinate) = coordinate else {
        return Ok(());
    };
    let (row, column) =
        split_coordinate(coordinate).ok_or(WorkbookErrorV1::InvalidCoordinate)?;
    let kind_value = kind.as_deref();
    let raw_value = raw.as_deref();
    let value = if kind_value == Some("inlineStr") && in_inline_str && !strict {
        CellValueV1::String(inline.clone())
    } else {
        classify_cell_value(kind_value, raw_value, strings, strict)?
    };
    if formula.is_some() {
        match &value {
            CellValueV1::None => return Err(WorkbookErrorV1::FormulaCacheMissing),
            CellValueV1::Integer(_)
            | CellValueV1::Number(_)
            | CellValueV1::Bool(_)
            | CellValueV1::String(_)
            | CellValueV1::Array { .. } => {}
        }
    }
    *max_row = (*max_row).max(row);
    *max_column = (*max_column).max(column);
    cells.insert(
        (row, column),
        RawCellV1 {
            sheet: "COM_Settings".to_string(),
            coordinate: coordinate.clone(),
            value,
            formula: formula.as_ref().map(|text| format!("={text}")),
        },
    );
    Ok(())
}

/// Port of `_validate_xlsx_container`: .xlsx suffix, zip container,
/// no macro content, no external links.
pub fn validate_xlsx_container_v1(path: &Path) -> Result<(), WorkbookErrorV1> {
    if path.extension().map(|ext| ext.to_string_lossy().to_lowercase()) != Some("xlsx".to_string()) {
        return Err(WorkbookErrorV1::NotXlsx);
    }
    let file = File::open(path).map_err(|_| WorkbookErrorV1::InvalidContainer)?;
    let archive = ZipArchive::new(file).map_err(|_| WorkbookErrorV1::InvalidContainer)?;
    let names: Vec<String> = archive
        .file_names()
        .map(|name| name.to_string())
        .collect();
    if names
        .iter()
        .any(|name| name.eq_ignore_ascii_case("xl/vbaproject.bin"))
    {
        return Err(WorkbookErrorV1::MacroContentNotPermitted);
    }
    if names
        .iter()
        .any(|name| name.to_ascii_lowercase().starts_with("xl/externallinks/"))
    {
        return Err(WorkbookErrorV1::ExternalLinksNotPermitted);
    }
    Ok(())
}

/// Port of `_is_strict_ooxml`: Strict namespace or conformance flag.
pub fn is_strict_ooxml_v1(path: &Path) -> Result<bool, WorkbookErrorV1> {
    validate_xlsx_container_v1(path)?;
    let file = File::open(path).map_err(|_| WorkbookErrorV1::InvalidContainer)?;
    let mut archive = ZipArchive::new(file).map_err(|_| WorkbookErrorV1::InvalidContainer)?;
    let mut buffer = Vec::new();
    archive
        .by_name("xl/workbook.xml")
        .map_err(|_| WorkbookErrorV1::InvalidWorkbookXml)?
        .read_to_end(&mut buffer)
        .map_err(|_| WorkbookErrorV1::InvalidWorkbookXml)?;
    let text = String::from_utf8_lossy(&buffer);
    Ok(text.contains("{http://purl.oclc.org/ooxml/")
        || text.contains("conformance='strict'"))
}

/// Read the COM_Settings worksheet into the raw cell grid (port of
/// `ComSettings.from_xlsx`).
pub fn read_com_settings_xlsx_v1(path: &Path) -> Result<ComSettingsV1, WorkbookErrorV1> {
    validate_xlsx_container_v1(path)?;
    let strict = is_strict_ooxml_v1(path)?;
    let file = File::open(path).map_err(|_| WorkbookErrorV1::InvalidContainer)?;
    let mut archive = ZipArchive::new(file).map_err(|_| WorkbookErrorV1::InvalidContainer)?;
    let location = locate_com_settings(&mut archive)?;
    let strings = read_shared_strings(&mut archive)?;
    let mut sheet_buffer = Vec::new();
    archive
        .by_name(&location.path)
        .map_err(|_| WorkbookErrorV1::InvalidWorkbookXml)?
        .read_to_end(&mut sheet_buffer)
        .map_err(|_| WorkbookErrorV1::InvalidWorkbookXml)?;
    let cells = parse_sheet_cells(&sheet_buffer, &strings, strict)?;
    Ok(ComSettingsV1 {
        cells,
        source: Some(path.to_path_buf()),
    })
}

/// The COM_Settings workbook surface (port of `ComSettings`).
#[derive(Clone, Debug)]
pub struct ComSettingsV1 {
    cells: Vec<Vec<RawCellV1>>,
    source: Option<PathBuf>,
}

impl ComSettingsV1 {
    pub(crate) fn from_cells(cells: Vec<Vec<RawCellV1>>, source: Option<PathBuf>) -> Self {
        Self { cells, source }
    }

    pub fn rows(&self) -> &[Vec<RawCellV1>] {
        &self.cells
    }

    pub fn source(&self) -> Option<&Path> {
        self.source.as_deref()
    }

    /// Port of `lookup_optional`: case-insensitive keyword scan of the
    /// left column values; the right-hand neighbor is the result.
    pub fn lookup_optional_v1(&self, keyword: &str) -> Result<Option<RawCellV1>, WorkbookErrorV1> {
        let folded = keyword.to_lowercase();
        let mut matches = Vec::new();
        for (row_index, row) in self.cells.iter().enumerate() {
            for (column_index, cell) in row.iter().enumerate() {
                if let CellValueV1::String(value) = &cell.value {
                    if value.to_lowercase() == folded {
                        matches.push((row_index, column_index));
                    }
                }
            }
        }
        if matches.is_empty() {
            return Ok(None);
        }
        if matches.len() != 1 {
            return Err(WorkbookErrorV1::DuplicateParameter(keyword.to_string()));
        }
        let (row_index, column_index) = matches[0];
        let row = &self.cells[row_index];
        if column_index + 1 >= row.len() {
            return Err(WorkbookErrorV1::MissingParameter(format!(
                "{keyword}: right-hand value"
            )));
        }
        let value = &row[column_index + 1];
        if value.value == CellValueV1::None {
            return Err(WorkbookErrorV1::MissingParameter(format!(
                "{keyword}: right-hand value"
            )));
        }
        Ok(Some(value.clone()))
    }

    pub fn lookup_v1(&self, keyword: &str) -> Result<RawCellV1, WorkbookErrorV1> {
        match self.lookup_optional_v1(keyword)? {
            Some(value) => Ok(value),
            None => Err(WorkbookErrorV1::MissingParameter(keyword.to_string())),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn column_helpers_round_trip() {
        assert_eq!(column_index("A"), Some(1));
        assert_eq!(column_index("Z"), Some(26));
        assert_eq!(column_index("AA"), Some(27));
        assert_eq!(column_letter(1), "A");
        assert_eq!(column_letter(26), "Z");
        assert_eq!(column_letter(27), "AA");
        assert_eq!(column_letter(column_index("BQ").expect("index")), "BQ");
    }

    #[test]
    fn coordinate_splitting() {
        assert_eq!(split_coordinate("A1"), Some((1, 1)));
        assert_eq!(split_coordinate("BQ32"), Some((32, 69)));
        assert_eq!(split_coordinate("1A"), None);
        assert_eq!(split_coordinate(""), None);
    }

    #[test]
    fn cell_value_classification() {
        assert_eq!(classify_cell_value(None, Some("3"), &[], false).unwrap(), CellValueV1::Integer(3));
        assert_eq!(classify_cell_value(None, Some("3.5"), &[], false).unwrap(), CellValueV1::Number(3.5));
        assert_eq!(classify_cell_value(None, Some("1e2"), &[], false).unwrap(), CellValueV1::Integer(100));
        assert_eq!(classify_cell_value(Some("b"), Some("0"), &[], false).unwrap(), CellValueV1::Bool(false));
        assert_eq!(classify_cell_value(Some("s"), Some("1"), &["a".to_string(), "b".to_string()], false).unwrap(), CellValueV1::String("b".to_string()));
        assert_eq!(classify_cell_value(Some("str"), Some("x"), &[], false).unwrap(), CellValueV1::String("x".to_string()));
        assert_eq!(classify_cell_value(Some("e"), Some("#DIV/0!"), &[], false).unwrap(), CellValueV1::String("#DIV/0!".to_string()));
        assert_eq!(classify_cell_value(None, Some("notnum"), &[], false).unwrap(), CellValueV1::String("notnum".to_string()));
        assert!(classify_cell_value(Some("s"), Some("9"), &["a".to_string()], false).is_err());
    }

    #[test]
    fn policy_string_is_fixed() {
        assert_eq!(
            WORKBOOK_IMPORT_POLICY_V1,
            "sipi.p5-05a.workbook-v1.xlsx-reader-lookup",
        );
    }
}