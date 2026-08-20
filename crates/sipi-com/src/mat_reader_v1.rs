//! MATLAB v5 configuration reader (port of
//! `agent_com/config/excel.py` `ComSettings.from_mat` /
//! `_matlab_cell_value`).
//!
//! Ported from agent-com (MIT source, P5-05c source map): MAT v5
//! container parsing (128-byte header, typed element stream, zlib
//! compressed elements), cell-array matrix decoding, and the legacy
//! `parameter` cell-array value classification. Struct/sparse/object/
//! complex/nested-cell surfaces are rejected fail-closed.

use std::fs;
use std::io::Read;
use std::path::Path;

use flate2::read::ZlibDecoder;

use crate::workbook_v1::{
    column_letter, CellValueV1, ComSettingsV1, RawCellV1, WorkbookErrorV1,
};

/// Explicit scope policy of the MATLAB reader stage.
pub const MAT_READER_POLICY_V1: &str = "sipi.p5-05c.mat-reader-v1.matv5-cell-parameter";

const MI_INT8: u32 = 1;
const MI_UINT8: u32 = 2;
const MI_INT16: u32 = 3;
const MI_UINT16: u32 = 4;
const MI_INT32: u32 = 5;
const MI_UINT32: u32 = 6;
const MI_SINGLE: u32 = 7;
const MI_DOUBLE: u32 = 9;
const MI_INT64: u32 = 12;
const MI_UINT64: u32 = 13;
const MI_MATRIX: u32 = 14;
const MI_COMPRESSED: u32 = 15;
// scipy's element constants (observed on MAT v5 fixtures): miUTF8 = 16,
// miUTF16 = 17, miUTF32 = 18. MATLAB string cells are written as
// miUTF8 (ASCII) payloads.
const MI_UTF8: u32 = 16;
const MI_UTF16: u32 = 17;
const MI_UTF32: u32 = 18;

const MX_CELL_CLASS: u32 = 1;
const MX_CHAR_CLASS: u32 = 4;
const MX_DOUBLE_CLASS: u32 = 6;
const MX_SINGLE_CLASS: u32 = 7;
const MX_INT8_CLASS: u32 = 8;
const MX_UINT8_CLASS: u32 = 9;
const MX_INT16_CLASS: u32 = 10;
const MX_UINT16_CLASS: u32 = 11;
const MX_INT32_CLASS: u32 = 12;
const MX_UINT32_CLASS: u32 = 13;
const MX_INT64_CLASS: u32 = 14;
const MX_UINT64_CLASS: u32 = 15;
const MX_STRUCT_CLASS: u32 = 2;
const MX_OBJECT_CLASS: u32 = 3;
const MX_SPARSE_CLASS: u32 = 5;

const FLAGS_LOGICAL: u32 = 0x0200;

fn le_u16(bytes: &[u8], offset: usize) -> u16 {
    u16::from_le_bytes([bytes[offset], bytes[offset + 1]])
}

fn le_u32(bytes: &[u8], offset: usize) -> u32 {
    u32::from_le_bytes([
        bytes[offset],
        bytes[offset + 1],
        bytes[offset + 2],
        bytes[offset + 3],
    ])
}

fn le_i32(bytes: &[u8], offset: usize) -> i32 {
    i32::from_le_bytes([
        bytes[offset],
        bytes[offset + 1],
        bytes[offset + 2],
        bytes[offset + 3],
    ])
}

fn le_f64(bytes: &[u8], offset: usize) -> f64 {
    f64::from_le_bytes([
        bytes[offset],
        bytes[offset + 1],
        bytes[offset + 2],
        bytes[offset + 3],
        bytes[offset + 4],
        bytes[offset + 5],
        bytes[offset + 6],
        bytes[offset + 7],
    ])
}

/// One typed data element (port of the MAT element stream).
struct MatElement {
    kind: u32,
    data: Vec<u8>,
}

fn read_elements(mut bytes: &[u8]) -> Result<Vec<MatElement>, WorkbookErrorV1> {
    let mut elements = Vec::new();
    loop {
        if bytes.is_empty() {
            break;
        }
        if bytes.len() < 8 {
            return Err(WorkbookErrorV1::InvalidMatConfiguration);
        }
        let packed = le_u32(bytes, 0);
        // Small data element format packs (byte_count << 16) | mdtype in
        // one u32 with a fixed 4-byte data slot; the full tag layout is
        // mdtype u32 + byte_count u32.  A non-zero high half selects the
        // small tag (MATLAB format; scipy write_smalldata_element).
        let (kind, size, data_start, total) = if packed >> 16 == 0 {
            let kind = packed;
            let size = le_u32(bytes, 4) as usize;
            let padded = size + ((8 - size % 8) % 8);
            (kind, size, 8usize, 8usize + padded)
        } else {
            let kind = packed & 0xFFFF;
            let size = (packed >> 16) as usize;
            // Small tag: packed u32 then a fixed 4-byte data slot.
            (kind, size, 4usize, 8usize)
        };
        if bytes.len() < total {
            return Err(WorkbookErrorV1::InvalidMatConfiguration);
        }
        let data = bytes[data_start..data_start + size].to_vec();
        if kind == MI_COMPRESSED {
            let mut decoder = ZlibDecoder::new(data.as_slice());
            let mut inflated = Vec::new();
            decoder
                .read_to_end(&mut inflated)
                .map_err(|_| WorkbookErrorV1::InvalidMatConfiguration)?;
            elements.extend(read_elements(&inflated)?);
        } else {
            elements.push(MatElement { kind, data });
        }
        bytes = &bytes[total..];
    }
    Ok(elements)
}

/// A decoded matrix (port of the miMATRIX surface used by the reader).
struct MatMatrix {
    class: u32,
    flags: u32,
    dims: Vec<u32>,
    name: String,
    data: Vec<MatElement>,
}

fn matrix_name(element: &MatElement) -> Result<MatMatrix, WorkbookErrorV1> {
    if element.kind != MI_MATRIX {
        return Err(WorkbookErrorV1::InvalidMatConfiguration);
    }
    let mut sub = read_elements(&element.data)?;
    // flags
    let flags = sub
        .first()
        .ok_or(WorkbookErrorV1::InvalidMatConfiguration)?;
    if flags.kind != MI_UINT32 || flags.data.len() < 8 {
        return Err(WorkbookErrorV1::InvalidMatConfiguration);
    }
    let class = le_u32(&flags.data, 0);
    let flag_bits = le_u32(&flags.data, 4);
    // dims
    let dims_element = sub
        .get(1)
        .ok_or(WorkbookErrorV1::InvalidMatConfiguration)?;
    if dims_element.kind != MI_INT32 {
        return Err(WorkbookErrorV1::InvalidMatConfiguration);
    }
    let mut dims = Vec::new();
    for index in (0..dims_element.data.len()).step_by(4) {
        let dim = le_i32(&dims_element.data, index);
        if dim < 0 {
            return Err(WorkbookErrorV1::InvalidMatConfiguration);
        }
        dims.push(dim as u32);
    }
    // name
    let name_element = sub
        .get(2)
        .ok_or(WorkbookErrorV1::InvalidMatConfiguration)?;
    let name = String::from_utf8_lossy(&name_element.data).to_string();
    // remaining elements are the data section
    let data = sub.split_off(3);
    Ok(MatMatrix {
        class,
        flags: flag_bits,
        dims,
        name,
        data,
    })
}

fn size_of(dims: &[u32]) -> usize {
    dims.iter().map(|dim| *dim as usize).product::<usize>()
}

/// Convert MATLAB column-major payload order to the source's C-order
/// flattening used by `np.reshape(-1)`.
fn to_c_order(dims: &[u32], column_major: &[f64]) -> Vec<f64> {
    let rows = dims.first().copied().unwrap_or(0) as usize;
    let columns = dims.get(1).copied().unwrap_or(1) as usize;
    let mut result = vec![0.0_f64; column_major.len()];
    for column in 0..columns {
        for row in 0..rows {
            let matlab_index = column * rows + row;
            if let Some(value) = column_major.get(matlab_index) {
                result[row * columns + column] = *value;
            }
        }
    }
    result
}

fn utf16_string(bytes: &[u8]) -> Result<String, WorkbookErrorV1> {
    let code_units: Vec<u16> = bytes
        .chunks_exact(2)
        .map(|pair| u16::from_le_bytes([pair[0], pair[1]]))
        .collect();
    char::decode_utf16(code_units.into_iter())
        .collect::<Result<String, _>>()
        .map_err(|_| WorkbookErrorV1::InvalidMatConfiguration)
}

fn numeric_values(data: &[MatElement]) -> Result<Vec<f64>, WorkbookErrorV1> {
    let element = data
        .first()
        .ok_or(WorkbookErrorV1::InvalidMatConfiguration)?;
    let payload = &element.data;
    let values = match element.kind {
        MI_DOUBLE => (0..payload.len())
            .step_by(8)
            .map(|offset| le_f64(payload, offset))
            .collect(),
        MI_SINGLE => (0..payload.len())
            .step_by(4)
            .map(|offset| f32::from_le_bytes([
                payload[offset],
                payload[offset + 1],
                payload[offset + 2],
                payload[offset + 3],
            ]) as f64)
            .collect(),
        MI_INT8 => payload.iter().map(|byte| *byte as i8 as f64).collect(),
        MI_UINT8 => payload.iter().map(|byte| *byte as f64).collect(),
        MI_INT16 => (0..payload.len())
            .step_by(2)
            .map(|offset| i16::from_le_bytes([payload[offset], payload[offset + 1]]) as f64)
            .collect(),
        MI_UINT16 => (0..payload.len())
            .step_by(2)
            .map(|offset| u16::from_le_bytes([payload[offset], payload[offset + 1]]) as f64)
            .collect(),
        MI_INT32 => (0..payload.len())
            .step_by(4)
            .map(|offset| le_i32(payload, offset) as f64)
            .collect(),
        MI_UINT32 => (0..payload.len())
            .step_by(4)
            .map(|offset| le_u32(payload, offset) as f64)
            .collect(),
        MI_INT64 => (0..payload.len())
            .step_by(8)
            .map(|offset| i64::from_le_bytes([
                payload[offset],
                payload[offset + 1],
                payload[offset + 2],
                payload[offset + 3],
                payload[offset + 4],
                payload[offset + 5],
                payload[offset + 6],
                payload[offset + 7],
            ]) as f64)
            .collect(),
        MI_UINT64 => (0..payload.len())
            .step_by(8)
            .map(|offset| u64::from_le_bytes([
                payload[offset],
                payload[offset + 1],
                payload[offset + 2],
                payload[offset + 3],
                payload[offset + 4],
                payload[offset + 5],
                payload[offset + 6],
                payload[offset + 7],
            ]) as f64)
            .collect(),
        _ => return Err(WorkbookErrorV1::UnsupportedMatClass),
    };
    Ok(values)
}

fn char_string(data: &[MatElement]) -> Result<String, WorkbookErrorV1> {
    let element = data
        .first()
        .ok_or(WorkbookErrorV1::InvalidMatConfiguration)?;
    match element.kind {
        MI_UTF16 | MI_UINT16 => utf16_string(&element.data),
        MI_UTF8 => String::from_utf8(element.data.clone())
            .map_err(|_| WorkbookErrorV1::InvalidMatConfiguration),
        _ => Err(WorkbookErrorV1::UnsupportedMatClass),
    }
}

/// Port of `_matlab_cell_value` over one decoded cell matrix.
fn mat_cell_value(matrix: &MatMatrix) -> Result<CellValueV1, WorkbookErrorV1> {
    // scipy packs the logical flag into the class word (class | 0x200).
    let base_class = matrix.class & !FLAGS_LOGICAL;
    let logical = matrix.class & FLAGS_LOGICAL != 0 || matrix.flags & FLAGS_LOGICAL != 0;
    match base_class {
        MX_CHAR_CLASS => {
            let text = char_string(&matrix.data)?;
            if text.is_empty() {
                Ok(CellValueV1::None)
            } else {
                // Source joins all characters in C order; the MATLAB
                // payload is UTF-16 in column-major order, which is
                // character-identical for the joined string.
                Ok(CellValueV1::String(text))
            }
        }
        MX_DOUBLE_CLASS | MX_SINGLE_CLASS | MX_INT8_CLASS | MX_UINT8_CLASS
        | MX_INT16_CLASS | MX_UINT16_CLASS | MX_INT32_CLASS | MX_UINT32_CLASS
        | MX_INT64_CLASS | MX_UINT64_CLASS => {
            let values = numeric_values(&matrix.data)?;
            let size = size_of(&matrix.dims);
            if size == 0 {
                return Ok(CellValueV1::None);
            }
            if size == 1 {
                let value = values.first().copied().unwrap_or(0.0);
                if logical {
                    // scipy loadmat yields an integer scalar for a
                    // logical cell, so the source's .item() is an int.
                    return Ok(CellValueV1::Integer(value as i64));
                }
                return if value.fract() == 0.0
                    && value >= i64::MIN as f64
                    && value <= i64::MAX as f64
                {
                    Ok(CellValueV1::Integer(value as i64))
                } else {
                    Ok(CellValueV1::Number(value))
                };
            }
            let ordered = if matrix.dims.len() >= 2 {
                to_c_order(&matrix.dims, &values)
            } else {
                values
            };
            Ok(CellValueV1::Array {
                dims: matrix.dims.clone(),
                data: ordered,
            })
        }
        MX_CELL_CLASS => Err(WorkbookErrorV1::UnsupportedMatClass),
        _ => Err(WorkbookErrorV1::UnsupportedMatClass),
    }
}

/// Read the legacy `parameter` MATLAB cell array as raw cells (port of
/// `ComSettings.from_mat`).
pub fn read_com_settings_mat_v1(path: &Path) -> Result<ComSettingsV1, WorkbookErrorV1> {
    let bytes = fs::read(path).map_err(|_| WorkbookErrorV1::InvalidMatConfiguration)?;
    if bytes.len() < 128 {
        return Err(WorkbookErrorV1::InvalidMatConfiguration);
    }
    if !bytes[..124].starts_with(b"MATLAB 5.0 MAT-file") {
        return Err(WorkbookErrorV1::InvalidMatConfiguration);
    }
    let elements = read_elements(&bytes[128..])?;
    let mut parameter: Option<MatMatrix> = None;
    for element in elements {
        if element.kind != MI_MATRIX {
            continue;
        }
        let matrix = matrix_name(&element)?;
        if matrix.name == "parameter" {
            parameter = Some(matrix);
        }
    }
    let Some(parameter) = parameter else {
        return Err(WorkbookErrorV1::MissingParameterVariable);
    };
    if parameter.class != MX_CELL_CLASS {
        return Err(WorkbookErrorV1::MissingParameterVariable);
    }
    if parameter.dims.len() != 2 {
        return Err(WorkbookErrorV1::InvalidMatConfiguration);
    }
    let rows = parameter.dims[0] as usize;
    let columns = parameter.dims[1] as usize;
    let mut cells: Vec<Vec<RawCellV1>> = Vec::with_capacity(rows);
    for row in 0..rows {
        let mut row_cells = Vec::with_capacity(columns);
        for column in 0..columns {
            let index = column * rows + row;
            let element = parameter
                .data
                .get(index)
                .ok_or(WorkbookErrorV1::InvalidMatConfiguration)?;
            let cell_matrix = matrix_name(element)?;
            if cell_matrix.class & !FLAGS_LOGICAL == MX_CELL_CLASS {
                return Err(WorkbookErrorV1::UnsupportedMatClass);
            }
            let value = mat_cell_value(&cell_matrix)?;
            row_cells.push(RawCellV1::new(
                "COM_Settings".to_string(),
                format!("{}{}", column_letter(column + 1), row + 1),
                value,
                None,
            ));
        }
        cells.push(row_cells);
    }
    Ok(ComSettingsV1::from_cells(cells, Some(path.to_path_buf())))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn c_order_reshapes_column_major() {
        let dims = [2u32, 2u32];
        let column_major = vec![1.0, 3.0, 2.0, 4.0];
        assert_eq!(to_c_order(&dims, &column_major), vec![1.0, 2.0, 3.0, 4.0]);
        let row = [1u32, 3u32];
        assert_eq!(to_c_order(&row, &[1.0, 2.0, 3.0]), vec![1.0, 2.0, 3.0]);
    }

    #[test]
    fn utf16_decoding() {
        assert_eq!(utf16_string(&[0x41, 0x00, 0x42, 0x00]).expect("s"), "AB");
        assert_eq!(utf16_string(&[0x48, 0x00]).expect("s"), "H");
    }

    #[test]
    fn policy_string_is_fixed() {
        assert_eq!(MAT_READER_POLICY_V1, "sipi.p5-05c.mat-reader-v1.matv5-cell-parameter");
    }
}