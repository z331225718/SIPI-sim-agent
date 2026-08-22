use crate::config_validate_v1::ConfigValidateErrorV1;
use flate2::read::ZlibDecoder;
use quick_xml::Reader;
use quick_xml::events::Event;
use std::collections::BTreeMap;
use std::fs::{self, File};
use std::io::{Cursor, Read};
use std::path::Path;
use zip::ZipArchive;

pub(crate) const MAX_XLSX_ARCHIVE_ENTRIES: usize = 2_048;
pub(crate) const MAX_XLSX_ENTRY_BYTES: u64 = 16 * 1024 * 1024;
pub(crate) const MAX_XLSX_TOTAL_UNCOMPRESSED_BYTES: u64 = 64 * 1024 * 1024;
pub(crate) const MAX_XLSX_METADATA_XML_BYTES: usize = 1024 * 1024;
pub(crate) const MAX_XLSX_SHARED_STRINGS_BYTES: usize = 8 * 1024 * 1024;
pub(crate) const MAX_XLSX_SHEET_XML_BYTES: usize = 16 * 1024 * 1024;
pub(crate) const MAX_XLSX_GRID_CELLS: usize = 1_000_000;
pub(crate) const MAX_MAT_EXPANDED_BYTES: usize = 32 * 1024 * 1024;
pub(crate) const MAX_MAT_ELEMENTS: usize = 1_000_000;
pub(crate) const MAX_MAT_DEPTH: usize = 16;
pub(crate) const MAX_MAT_DIMENSIONS: usize = 16;
pub(crate) const MAX_MAT_MATRIX_ELEMENTS: usize = 1_000_000;

const MAX_CONFIG_FILE_BYTES: u64 = 16 * 1024 * 1024;
const MAX_XLSX_ROWS: usize = 1_048_576;
const MAX_XLSX_COLUMNS: usize = 16_384;
const MI_INT32: u32 = 5;
const MI_UINT32: u32 = 6;
const MI_MATRIX: u32 = 14;
const MI_COMPRESSED: u32 = 15;

pub(crate) fn preflight_config_source_v1(
    path: &Path,
    extension: &str,
) -> Result<(), ConfigValidateErrorV1> {
    match extension {
        "xlsx" => preflight_xlsx_v1(path),
        "mat" => preflight_mat_v1(path),
        "csv" => Ok(()),
        _ => Ok(()),
    }
}

fn reject(message: impl Into<String>) -> ConfigValidateErrorV1 {
    ConfigValidateErrorV1::Workbook(format!(
        "configuration preflight rejected input: {}",
        message.into()
    ))
}

fn preflight_xlsx_v1(path: &Path) -> Result<(), ConfigValidateErrorV1> {
    let file = File::open(path).map_err(|error| reject(error.to_string()))?;
    let mut archive = ZipArchive::new(file).map_err(|_| reject("invalid XLSX ZIP container"))?;
    if archive.len() > MAX_XLSX_ARCHIVE_ENTRIES {
        return Err(reject("XLSX archive entry budget exceeded"));
    }
    let mut inventory = BTreeMap::new();
    let mut total = 0_u64;
    for index in 0..archive.len() {
        let entry = archive
            .by_index(index)
            .map_err(|_| reject("invalid XLSX ZIP entry"))?;
        if entry.enclosed_name().is_none() {
            return Err(reject("XLSX archive contains an unsafe member path"));
        }
        admit_zip_entry(&mut inventory, &mut total, entry.name(), entry.size())?;
    }

    let workbook = read_zip_entry_bounded(
        &mut archive,
        &inventory,
        "xl/workbook.xml",
        MAX_XLSX_METADATA_XML_BYTES,
        false,
    )?;
    let rels = read_zip_entry_bounded(
        &mut archive,
        &inventory,
        "xl/_rels/workbook.xml.rels",
        MAX_XLSX_METADATA_XML_BYTES,
        false,
    )?;
    let sheet_path = locate_com_settings_sheet(&workbook, &rels)?;
    let sheet = read_zip_entry_bounded(
        &mut archive,
        &inventory,
        &sheet_path,
        MAX_XLSX_SHEET_XML_BYTES,
        false,
    )?;
    let _ = read_zip_entry_bounded(
        &mut archive,
        &inventory,
        "xl/sharedStrings.xml",
        MAX_XLSX_SHARED_STRINGS_BYTES,
        true,
    )?;
    preflight_sheet_grid(&sheet)
}

fn admit_zip_entry(
    inventory: &mut BTreeMap<String, u64>,
    total: &mut u64,
    name: &str,
    size: u64,
) -> Result<(), ConfigValidateErrorV1> {
    if size > MAX_XLSX_ENTRY_BYTES {
        return Err(reject(
            "XLSX archive member exceeds uncompressed byte budget",
        ));
    }
    *total = total
        .checked_add(size)
        .ok_or_else(|| reject("XLSX uncompressed byte count overflow"))?;
    if *total > MAX_XLSX_TOTAL_UNCOMPRESSED_BYTES {
        return Err(reject("XLSX total uncompressed byte budget exceeded"));
    }
    if inventory.insert(name.to_owned(), size).is_some() {
        return Err(reject("XLSX archive contains duplicate member names"));
    }
    Ok(())
}

fn read_zip_entry_bounded(
    archive: &mut ZipArchive<File>,
    inventory: &BTreeMap<String, u64>,
    name: &str,
    limit: usize,
    optional: bool,
) -> Result<Vec<u8>, ConfigValidateErrorV1> {
    let Some(size) = inventory.get(name).copied() else {
        return if optional {
            Ok(Vec::new())
        } else {
            Err(reject(format!("required XLSX member is missing: {name}")))
        };
    };
    if size > limit as u64 {
        return Err(reject(format!("XLSX member exceeds byte budget: {name}")));
    }
    let entry = archive
        .by_name(name)
        .map_err(|_| reject(format!("cannot open XLSX member: {name}")))?;
    let mut bytes = Vec::new();
    entry
        .take(limit as u64 + 1)
        .read_to_end(&mut bytes)
        .map_err(|_| reject(format!("cannot read XLSX member: {name}")))?;
    if bytes.len() > limit {
        return Err(reject(format!(
            "XLSX member expanded beyond byte budget: {name}"
        )));
    }
    Ok(bytes)
}

fn local_name(name: quick_xml::name::QName<'_>) -> &[u8] {
    let bytes = name.0;
    bytes
        .iter()
        .position(|byte| *byte == b':')
        .map_or(bytes, |index| &bytes[index + 1..])
}

fn attribute_value(
    attributes: &[quick_xml::events::attributes::Attribute<'_>],
    key: &[u8],
) -> Option<String> {
    attributes.iter().find_map(|attribute| {
        (local_name(attribute.key) == key)
            .then(|| String::from_utf8_lossy(attribute.value.as_ref()).into_owned())
    })
}

fn locate_com_settings_sheet(
    workbook: &[u8],
    rels: &[u8],
) -> Result<String, ConfigValidateErrorV1> {
    let mut reader = Reader::from_reader(Cursor::new(workbook));
    let mut buffer = Vec::new();
    let mut relationship_id = None;
    loop {
        match reader
            .read_event_into(&mut buffer)
            .map_err(|_| reject("invalid workbook XML"))?
        {
            Event::Start(event) | Event::Empty(event) if local_name(event.name()) == b"sheet" => {
                let attributes = event
                    .attributes()
                    .collect::<Result<Vec<_>, _>>()
                    .map_err(|_| reject("invalid workbook sheet attributes"))?;
                if attribute_value(&attributes, b"name").as_deref() == Some("COM_Settings") {
                    relationship_id = attribute_value(&attributes, b"id");
                    break;
                }
            }
            Event::Eof => break,
            _ => {}
        }
        buffer.clear();
    }
    let relationship_id = relationship_id.ok_or_else(|| reject("COM_Settings sheet is missing"))?;
    let mut reader = Reader::from_reader(Cursor::new(rels));
    buffer.clear();
    loop {
        match reader
            .read_event_into(&mut buffer)
            .map_err(|_| reject("invalid workbook relationships XML"))?
        {
            Event::Start(event) | Event::Empty(event)
                if local_name(event.name()) == b"Relationship" =>
            {
                let attributes = event
                    .attributes()
                    .collect::<Result<Vec<_>, _>>()
                    .map_err(|_| reject("invalid workbook relationship attributes"))?;
                if attribute_value(&attributes, b"Id").as_deref() == Some(&relationship_id) {
                    let target = attribute_value(&attributes, b"Target")
                        .ok_or_else(|| reject("COM_Settings relationship target is missing"))?;
                    return normalize_sheet_target(&target);
                }
            }
            Event::Eof => break,
            _ => {}
        }
        buffer.clear();
    }
    Err(reject("COM_Settings relationship is missing"))
}

fn normalize_sheet_target(target: &str) -> Result<String, ConfigValidateErrorV1> {
    if target.contains(':') || target.contains('\\') {
        return Err(reject("unsafe COM_Settings relationship target"));
    }
    let joined = if target.starts_with('/') {
        target.trim_start_matches('/').to_owned()
    } else {
        format!("xl/{target}")
    };
    let mut normalized = Vec::new();
    for part in joined.split('/') {
        match part {
            "" | "." => {}
            ".." => {
                if normalized.pop().is_none() {
                    return Err(reject("COM_Settings relationship escapes archive root"));
                }
            }
            value => normalized.push(value),
        }
    }
    let path = normalized.join("/");
    if !path.starts_with("xl/") {
        return Err(reject("COM_Settings relationship is outside xl/"));
    }
    Ok(path)
}

fn preflight_sheet_grid(sheet: &[u8]) -> Result<(), ConfigValidateErrorV1> {
    let mut reader = Reader::from_reader(Cursor::new(sheet));
    let mut buffer = Vec::new();
    let mut max_row = 0_usize;
    let mut max_column = 0_usize;
    let mut explicit_cells = 0_usize;
    loop {
        match reader
            .read_event_into(&mut buffer)
            .map_err(|_| reject("invalid COM_Settings worksheet XML"))?
        {
            Event::Start(event) | Event::Empty(event) => {
                let name = local_name(event.name());
                if name == b"c" || name == b"dimension" {
                    let attributes = event
                        .attributes()
                        .collect::<Result<Vec<_>, _>>()
                        .map_err(|_| reject("invalid worksheet attributes"))?;
                    let reference =
                        attribute_value(&attributes, if name == b"c" { b"r" } else { b"ref" });
                    if let Some(reference) = reference {
                        let coordinate = reference.rsplit(':').next().unwrap_or(&reference);
                        let (row, column) = split_coordinate(coordinate)?;
                        max_row = max_row.max(row);
                        max_column = max_column.max(column);
                        checked_grid_extent(max_row, max_column)?;
                    }
                    if name == b"c" {
                        explicit_cells = explicit_cells
                            .checked_add(1)
                            .ok_or_else(|| reject("worksheet cell count overflow"))?;
                        if explicit_cells > MAX_XLSX_GRID_CELLS {
                            return Err(reject("worksheet explicit-cell budget exceeded"));
                        }
                    }
                }
            }
            Event::Eof => break,
            _ => {}
        }
        buffer.clear();
    }
    checked_grid_extent(max_row, max_column)
}

fn split_coordinate(coordinate: &str) -> Result<(usize, usize), ConfigValidateErrorV1> {
    let coordinate = coordinate.replace('$', "");
    let split = coordinate
        .char_indices()
        .find(|(_, character)| character.is_ascii_digit())
        .ok_or_else(|| reject("invalid worksheet coordinate"))?
        .0;
    let (letters, digits) = coordinate.split_at(split);
    if letters.is_empty()
        || digits.is_empty()
        || !letters.bytes().all(|byte| byte.is_ascii_alphabetic())
        || !digits.bytes().all(|byte| byte.is_ascii_digit())
    {
        return Err(reject("invalid worksheet coordinate"));
    }
    let column = letters.bytes().try_fold(0_usize, |value, byte| {
        value
            .checked_mul(26)?
            .checked_add((byte.to_ascii_uppercase() - b'A' + 1) as usize)
    });
    let row = digits
        .parse::<usize>()
        .map_err(|_| reject("worksheet row overflow"))?;
    let column = column.ok_or_else(|| reject("worksheet column overflow"))?;
    if row == 0 || row > MAX_XLSX_ROWS || column == 0 || column > MAX_XLSX_COLUMNS {
        return Err(reject("worksheet coordinate exceeds XLSX bounds"));
    }
    Ok((row, column))
}

fn checked_grid_extent(row: usize, column: usize) -> Result<(), ConfigValidateErrorV1> {
    let cells = row
        .checked_mul(column)
        .ok_or_else(|| reject("worksheet grid extent overflow"))?;
    if cells > MAX_XLSX_GRID_CELLS {
        return Err(reject("worksheet rectangular grid budget exceeded"));
    }
    Ok(())
}

#[derive(Default)]
struct MatBudget {
    expanded_bytes: usize,
    elements: usize,
    parameter_seen: bool,
}

fn preflight_mat_v1(path: &Path) -> Result<(), ConfigValidateErrorV1> {
    let bytes = fs::read(path).map_err(|error| reject(error.to_string()))?;
    if bytes.len() as u64 > MAX_CONFIG_FILE_BYTES
        || bytes.len() < 128
        || !bytes[..124].starts_with(b"MATLAB 5.0 MAT-file")
        || &bytes[126..128] != b"IM"
    {
        return Err(reject("invalid or oversized MAT v5 container"));
    }
    let mut budget = MatBudget::default();
    scan_mat_elements(&bytes[128..], 0, &mut budget)?;
    if !budget.parameter_seen {
        return Err(reject("MAT parameter cell array is missing"));
    }
    Ok(())
}

fn scan_mat_elements(
    mut bytes: &[u8],
    depth: usize,
    budget: &mut MatBudget,
) -> Result<(), ConfigValidateErrorV1> {
    if depth > MAX_MAT_DEPTH {
        return Err(reject("MAT element nesting budget exceeded"));
    }
    while !bytes.is_empty() {
        budget.elements = budget
            .elements
            .checked_add(1)
            .ok_or_else(|| reject("MAT element count overflow"))?;
        if budget.elements > MAX_MAT_ELEMENTS {
            return Err(reject("MAT element count budget exceeded"));
        }
        let (kind, data, total) = mat_element(bytes)?;
        if kind == MI_COMPRESSED {
            let remaining = MAX_MAT_EXPANDED_BYTES
                .checked_sub(budget.expanded_bytes)
                .ok_or_else(|| reject("MAT expanded byte budget exceeded"))?;
            let mut inflated = Vec::new();
            ZlibDecoder::new(data)
                .take(remaining as u64 + 1)
                .read_to_end(&mut inflated)
                .map_err(|_| reject("invalid MAT compressed element"))?;
            if inflated.len() > remaining {
                return Err(reject("MAT expanded byte budget exceeded"));
            }
            budget.expanded_bytes += inflated.len();
            scan_mat_elements(&inflated, depth + 1, budget)?;
        } else if kind == MI_MATRIX {
            scan_mat_matrix(data, depth + 1, budget)?;
        }
        bytes = &bytes[total..];
    }
    Ok(())
}

fn mat_element(bytes: &[u8]) -> Result<(u32, &[u8], usize), ConfigValidateErrorV1> {
    if bytes.len() < 8 {
        return Err(reject("truncated MAT element tag"));
    }
    let packed = u32::from_le_bytes(bytes[..4].try_into().expect("four bytes"));
    let (kind, size, data_start, total) = if packed >> 16 == 0 {
        let size = u32::from_le_bytes(bytes[4..8].try_into().expect("four bytes")) as usize;
        let padded = size
            .checked_add((8 - size % 8) % 8)
            .ok_or_else(|| reject("MAT element size overflow"))?;
        let total = 8_usize
            .checked_add(padded)
            .ok_or_else(|| reject("MAT element extent overflow"))?;
        (packed, size, 8_usize, total)
    } else {
        let size = (packed >> 16) as usize;
        if size > 4 {
            return Err(reject("invalid MAT small element size"));
        }
        (packed & 0xffff, size, 4_usize, 8_usize)
    };
    let data_end = data_start
        .checked_add(size)
        .ok_or_else(|| reject("MAT element data extent overflow"))?;
    if total > bytes.len() || data_end > total {
        return Err(reject("truncated MAT element payload"));
    }
    Ok((kind, &bytes[data_start..data_end], total))
}

fn scan_mat_matrix(
    data: &[u8],
    depth: usize,
    budget: &mut MatBudget,
) -> Result<(), ConfigValidateErrorV1> {
    let mut offset = 0_usize;
    let (flags_kind, flags, total) = mat_element(&data[offset..])?;
    budget.elements += 1;
    offset = offset
        .checked_add(total)
        .ok_or_else(|| reject("MAT matrix metadata extent overflow"))?;
    if flags_kind != MI_UINT32 || flags.len() < 8 {
        return Err(reject("invalid MAT matrix flags"));
    }
    let (dims_kind, dims_bytes, total) = mat_element(&data[offset..])?;
    budget.elements += 1;
    offset = offset
        .checked_add(total)
        .ok_or_else(|| reject("MAT matrix dimensions extent overflow"))?;
    if dims_kind != MI_INT32 || dims_bytes.is_empty() || dims_bytes.len() % 4 != 0 {
        return Err(reject("invalid MAT matrix dimensions"));
    }
    if dims_bytes.len() / 4 > MAX_MAT_DIMENSIONS {
        return Err(reject("MAT matrix dimension-count budget exceeded"));
    }
    let mut dimensions = Vec::with_capacity(dims_bytes.len() / 4);
    let mut element_count = 1_usize;
    for chunk in dims_bytes.chunks_exact(4) {
        let dimension = i32::from_le_bytes(chunk.try_into().expect("four bytes"));
        if dimension < 0 {
            return Err(reject("negative MAT matrix dimension"));
        }
        let dimension = dimension as usize;
        element_count = element_count
            .checked_mul(dimension)
            .ok_or_else(|| reject("MAT matrix dimension product overflow"))?;
        dimensions.push(dimension);
    }
    if element_count > MAX_MAT_MATRIX_ELEMENTS {
        return Err(reject("MAT matrix element budget exceeded"));
    }
    let (_, name, total) = mat_element(&data[offset..])?;
    budget.elements += 1;
    offset = offset
        .checked_add(total)
        .ok_or_else(|| reject("MAT matrix name extent overflow"))?;
    if budget.elements > MAX_MAT_ELEMENTS {
        return Err(reject("MAT element count budget exceeded"));
    }
    if name == b"parameter" {
        if dimensions.len() != 2 || element_count > MAX_XLSX_GRID_CELLS {
            return Err(reject("MAT parameter grid dimensions exceed budget"));
        }
        budget.parameter_seen = true;
    }
    scan_mat_elements(&data[offset..], depth, budget)
}

#[cfg(test)]
mod tests {
    use super::*;
    use flate2::Compression;
    use flate2::write::ZlibEncoder;
    use std::io::Write;
    use std::time::{SystemTime, UNIX_EPOCH};
    use zip::ZipWriter;
    use zip::write::SimpleFileOptions;

    fn temp_path(extension: &str) -> std::path::PathBuf {
        let nonce = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("clock")
            .as_nanos();
        std::env::temp_dir().join(format!("sipi-com-preflight-{nonce}.{extension}"))
    }

    fn write_xlsx(sheet: &str, shared_strings: Option<&[u8]>) -> std::path::PathBuf {
        let path = temp_path("xlsx");
        let file = File::create(&path).expect("xlsx fixture");
        let mut archive = ZipWriter::new(file);
        let options = SimpleFileOptions::default();
        for (name, bytes) in [
            (
                "xl/workbook.xml",
                br#"<workbook xmlns:r="r"><sheets><sheet name="COM_Settings" r:id="rId1"/></sheets></workbook>"#.as_slice(),
            ),
            (
                "xl/_rels/workbook.xml.rels",
                br#"<Relationships><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>"#.as_slice(),
            ),
            ("xl/worksheets/sheet1.xml", sheet.as_bytes()),
        ] {
            archive.start_file(name, options).expect("zip entry");
            archive.write_all(bytes).expect("zip bytes");
        }
        if let Some(bytes) = shared_strings {
            archive
                .start_file("xl/sharedStrings.xml", options)
                .expect("shared strings entry");
            archive.write_all(bytes).expect("shared strings");
        }
        archive.finish().expect("finish zip");
        path
    }

    fn mat_element_bytes(kind: u32, data: &[u8]) -> Vec<u8> {
        let mut result = Vec::new();
        result.extend_from_slice(&kind.to_le_bytes());
        result.extend_from_slice(&(data.len() as u32).to_le_bytes());
        result.extend_from_slice(data);
        result.resize(result.len().next_multiple_of(8), 0);
        result
    }

    fn matrix_bytes(name: &[u8], dimensions: &[i32], data: &[u8]) -> Vec<u8> {
        let mut body = Vec::new();
        body.extend(mat_element_bytes(MI_UINT32, &[1, 0, 0, 0, 0, 0, 0, 0]));
        let dims = dimensions
            .iter()
            .flat_map(|value| value.to_le_bytes())
            .collect::<Vec<_>>();
        body.extend(mat_element_bytes(MI_INT32, &dims));
        body.extend(mat_element_bytes(1, name));
        body.extend_from_slice(data);
        mat_element_bytes(MI_MATRIX, &body)
    }

    fn write_mat(payload: &[u8]) -> std::path::PathBuf {
        let path = temp_path("mat");
        let mut bytes = vec![b' '; 128];
        bytes[..19].copy_from_slice(b"MATLAB 5.0 MAT-file");
        bytes[126..128].copy_from_slice(b"IM");
        bytes.extend_from_slice(payload);
        fs::write(&path, bytes).expect("MAT fixture");
        path
    }

    #[test]
    fn rejects_remote_xlsx_coordinate_before_reader_allocation() {
        let path = write_xlsx(
            r#"<worksheet><sheetData><row><c r="XFD1048576"><v>1</v></c></row></sheetData></worksheet>"#,
            None,
        );
        let error = preflight_xlsx_v1(&path).expect_err("remote coordinate");
        assert!(error.to_string().contains("grid budget"));
        fs::remove_file(path).expect("cleanup");
    }

    #[test]
    fn rejects_oversized_shared_strings_from_zip_inventory() {
        let shared = vec![b'x'; MAX_XLSX_SHARED_STRINGS_BYTES + 1];
        let path = write_xlsx(r#"<worksheet><sheetData/></worksheet>"#, Some(&shared));
        let error = preflight_xlsx_v1(&path).expect_err("shared strings budget");
        assert!(error.to_string().contains("sharedStrings.xml"));
        fs::remove_file(path).expect("cleanup");
    }

    #[test]
    fn accepts_small_bounded_xlsx_grid() {
        let path = write_xlsx(
            r#"<worksheet><dimension ref="A1:B2"/><sheetData><row><c r="B2"><v>1</v></c></row></sheetData></worksheet>"#,
            None,
        );
        preflight_xlsx_v1(&path).expect("bounded worksheet");
        fs::remove_file(path).expect("cleanup");
    }

    #[test]
    fn zip_inventory_rejects_per_member_and_total_uncompressed_budgets() {
        let mut inventory = BTreeMap::new();
        let mut total = 0;
        assert!(
            admit_zip_entry(
                &mut inventory,
                &mut total,
                "oversized",
                MAX_XLSX_ENTRY_BYTES + 1,
            )
            .is_err()
        );
        for index in 0..4 {
            admit_zip_entry(
                &mut inventory,
                &mut total,
                &format!("entry-{index}"),
                MAX_XLSX_ENTRY_BYTES,
            )
            .expect("within total budget");
        }
        assert!(admit_zip_entry(&mut inventory, &mut total, "one-more", 1).is_err());
    }

    #[test]
    fn rejects_mat_dimension_product_before_shared_reader() {
        let path = write_mat(&matrix_bytes(b"parameter", &[i32::MAX, i32::MAX], &[]));
        let error = preflight_mat_v1(&path).expect_err("dimension product");
        assert!(error.to_string().contains("element budget"));
        fs::remove_file(path).expect("cleanup");
    }

    #[test]
    fn rejects_mat_dimension_count_before_preflight_allocation() {
        let dimensions = vec![1; MAX_MAT_DIMENSIONS + 1];
        let path = write_mat(&matrix_bytes(b"parameter", &dimensions, &[]));
        let error = preflight_mat_v1(&path).expect_err("dimension count");
        assert!(error.to_string().contains("dimension-count budget"));
        fs::remove_file(path).expect("cleanup");
    }

    #[test]
    fn accepts_bounded_mat_parameter_grid() {
        let path = write_mat(&matrix_bytes(b"parameter", &[1, 1], &[]));
        preflight_mat_v1(&path).expect("bounded MAT parameter grid");
        fs::remove_file(path).expect("cleanup");
    }

    #[test]
    fn rejects_mat_inflate_bomb_with_bounded_decoder() {
        let expanded = vec![0_u8; MAX_MAT_EXPANDED_BYTES + 1];
        let mut encoder = ZlibEncoder::new(Vec::new(), Compression::best());
        encoder.write_all(&expanded).expect("compress");
        let compressed = encoder.finish().expect("compressed payload");
        let path = write_mat(&mat_element_bytes(MI_COMPRESSED, &compressed));
        let error = preflight_mat_v1(&path).expect_err("inflate budget");
        assert!(error.to_string().contains("expanded byte budget"));
        fs::remove_file(path).expect("cleanup");
    }
}
