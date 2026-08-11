#![forbid(unsafe_code)]

//! A deliberately narrow, in-memory Touchstone admission boundary.
//!
//! This crate accepts only the product's `Hz S RI R 50.0` two-port subset.
//! It does not perform file I/O, unit conversion, interpolation, or channel
//! resolution. The sole numeric resolver remains in `sipi-channel`.

use std::{error::Error, fmt, num::NonZeroUsize};

use sipi_channel::{MatchedTwoPortSpectrumV1, TwoPortS};
use sipi_types::{Complex64, Hertz, Ohms};

/// Bounded parsing limits supplied by the caller. They carry no file or
/// transport policy; the parser operates only on the bytes it receives.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct TouchstoneParseLimitsV1 {
    max_input_bytes: NonZeroUsize,
    max_line_bytes: NonZeroUsize,
    /// Exactly this many data rows are admitted; the next row is rejected.
    max_data_records: NonZeroUsize,
}

impl TouchstoneParseLimitsV1 {
    pub const fn new(
        max_input_bytes: NonZeroUsize,
        max_line_bytes: NonZeroUsize,
        max_data_records: NonZeroUsize,
    ) -> Self {
        Self {
            max_input_bytes,
            max_line_bytes,
            max_data_records,
        }
    }
}

/// One parsed data row in the public Touchstone two-port order.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct ParsedTwoPortRowV1 {
    frequency_hz: f64,
    s11: Complex64,
    s21: Complex64,
    s12: Complex64,
    s22: Complex64,
}

impl ParsedTwoPortRowV1 {
    pub fn frequency_hz(self) -> f64 {
        self.frequency_hz
    }
    pub fn s11(self) -> Complex64 {
        self.s11
    }
    pub fn s21(self) -> Complex64 {
        self.s21
    }
    pub fn s12(self) -> Complex64 {
        self.s12
    }
    pub fn s22(self) -> Complex64 {
        self.s22
    }
}

/// A parsed `Hz S RI R 50.0` document. It deliberately preserves no input
/// bytes, paths, comments, or source identity.
#[derive(Clone, Debug, PartialEq)]
pub struct ParsedTouchstoneTwoPortV1 {
    rows: Vec<ParsedTwoPortRowV1>,
}

impl ParsedTouchstoneTwoPortV1 {
    pub fn rows(&self) -> &[ParsedTwoPortRowV1] {
        &self.rows
    }
}

/// Closed, stable failures for the strict lexical and admission subset.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum TouchstoneError {
    InputLimitExceeded,
    NonAsciiInput,
    NulByte,
    InvalidLineEnding,
    LineLimitExceeded,
    RecordLimitExceeded,
    MissingOptionLine,
    DuplicateOptionLine,
    UnsupportedOptionLine,
    OptionLineAfterData,
    MalformedDataRow,
    NonFiniteNumber,
    TooFewRows,
    MissingDc,
    NonIncreasingFrequency,
    NonUniformFrequencyGrid,
    ChannelAdmission,
}

impl fmt::Display for TouchstoneError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "touchstone v1 input is invalid: {self:?}")
    }
}

impl Error for TouchstoneError {}

fn trim_ascii(bytes: &[u8]) -> &[u8] {
    let start = bytes
        .iter()
        .position(|byte| !matches!(byte, b' ' | b'\t'))
        .unwrap_or(bytes.len());
    let end = bytes
        .iter()
        .rposition(|byte| !matches!(byte, b' ' | b'\t'))
        .map_or(start, |index| index + 1);
    &bytes[start..end]
}

fn finite_number(token: &[u8]) -> Result<f64, TouchstoneError> {
    // The full input has already passed the ASCII gate before tokenization.
    let text = std::str::from_utf8(token).map_err(|_| TouchstoneError::NonAsciiInput)?;
    let number = text
        .parse::<f64>()
        .map_err(|_| TouchstoneError::MalformedDataRow)?;
    number
        .is_finite()
        .then_some(number)
        .ok_or(TouchstoneError::NonFiniteNumber)
}

fn split_fields(line: &[u8]) -> Vec<&[u8]> {
    line.split(|byte| matches!(byte, b' ' | b'\t'))
        .filter(|field| !field.is_empty())
        .collect()
}

fn parse_data_row(line: &[u8]) -> Result<ParsedTwoPortRowV1, TouchstoneError> {
    let fields = split_fields(line);
    if fields.len() != 9 {
        return Err(TouchstoneError::MalformedDataRow);
    }
    let values = fields
        .iter()
        .map(|field| finite_number(field))
        .collect::<Result<Vec<_>, _>>()?;
    let complex = |real: f64, imaginary: f64| {
        Complex64::try_new(real, imaginary).map_err(|_| TouchstoneError::NonFiniteNumber)
    };
    Ok(ParsedTwoPortRowV1 {
        frequency_hz: values[0],
        s11: complex(values[1], values[2])?,
        s21: complex(values[3], values[4])?,
        s12: complex(values[5], values[6])?,
        s22: complex(values[7], values[8])?,
    })
}

fn parse_line(
    line: &[u8],
    limits: TouchstoneParseLimitsV1,
) -> Result<Option<&[u8]>, TouchstoneError> {
    if line.len() > limits.max_line_bytes.get() {
        return Err(TouchstoneError::LineLimitExceeded);
    }
    if line.contains(&b'\r') {
        return Err(TouchstoneError::InvalidLineEnding);
    }
    let without_comment = line.split(|byte| *byte == b'!').next().unwrap_or_default();
    let content = trim_ascii(without_comment);
    Ok((!content.is_empty()).then_some(content))
}

/// Parse exactly one public, two-port `# Hz S RI R 50.0` option subset.
pub fn parse_touchstone_hz_s_ri_50_two_port_v1(
    bytes: &[u8],
    limits: TouchstoneParseLimitsV1,
) -> Result<ParsedTouchstoneTwoPortV1, TouchstoneError> {
    if bytes.len() > limits.max_input_bytes.get() {
        return Err(TouchstoneError::InputLimitExceeded);
    }
    if bytes.contains(&0) {
        return Err(TouchstoneError::NulByte);
    }
    if !bytes.is_ascii() {
        return Err(TouchstoneError::NonAsciiInput);
    }
    if bytes.ends_with(b"\r") {
        return Err(TouchstoneError::InvalidLineEnding);
    }
    let mut saw_option = false;
    let mut saw_data = false;
    let mut rows = Vec::new();
    for raw_line in bytes.split(|byte| *byte == b'\n') {
        let line = raw_line.strip_suffix(b"\r").unwrap_or(raw_line);
        let Some(content) = parse_line(line, limits)? else {
            continue;
        };
        if content.starts_with(b"#") {
            if saw_data {
                return Err(TouchstoneError::OptionLineAfterData);
            }
            if saw_option {
                return Err(TouchstoneError::DuplicateOptionLine);
            }
            if content != b"# Hz S RI R 50.0" {
                return Err(TouchstoneError::UnsupportedOptionLine);
            }
            saw_option = true;
            continue;
        }
        if !saw_option {
            return Err(TouchstoneError::MissingOptionLine);
        }
        if rows.len() == limits.max_data_records.get() {
            return Err(TouchstoneError::RecordLimitExceeded);
        }
        rows.push(parse_data_row(content)?);
        saw_data = true;
    }
    if !saw_option {
        return Err(TouchstoneError::MissingOptionLine);
    }
    Ok(ParsedTouchstoneTwoPortV1 { rows })
}

/// Admit a parsed document only when it exactly matches the product's matched
/// one-sided, uniform Hz grid. This performs no S-parameter transformation.
pub fn admit_matched_two_port_spectrum_v1(
    parsed: &ParsedTouchstoneTwoPortV1,
) -> Result<MatchedTwoPortSpectrumV1, TouchstoneError> {
    let rows = parsed.rows();
    if rows.len() < 2 {
        return Err(TouchstoneError::TooFewRows);
    }
    if rows[0].frequency_hz.to_bits() != 0.0_f64.to_bits() {
        return Err(TouchstoneError::MissingDc);
    }
    let step = rows[1].frequency_hz;
    if step <= 0.0 {
        return Err(TouchstoneError::NonIncreasingFrequency);
    }
    for (index, row) in rows.iter().enumerate().skip(1) {
        if row.frequency_hz <= rows[index - 1].frequency_hz {
            return Err(TouchstoneError::NonIncreasingFrequency);
        }
        if row.frequency_hz.to_bits() != (index as f64 * step).to_bits() {
            return Err(TouchstoneError::NonUniformFrequencyGrid);
        }
    }
    let samples = rows
        .iter()
        .map(|row| TwoPortS {
            s11: row.s11,
            s12: row.s12,
            s21: row.s21,
            s22: row.s22,
        })
        .collect();
    MatchedTwoPortSpectrumV1::try_new(
        Ohms::try_new(50.0).map_err(|_| TouchstoneError::ChannelAdmission)?,
        Hertz::try_new(step).map_err(|_| TouchstoneError::ChannelAdmission)?,
        samples,
    )
    .map_err(|_| TouchstoneError::ChannelAdmission)
}

#[cfg(test)]
mod tests {
    use super::*;
    use sipi_channel::{ChannelLimitsV1, resolve_matched_kernel_v1};

    fn limits() -> TouchstoneParseLimitsV1 {
        TouchstoneParseLimitsV1::new(
            NonZeroUsize::new(4_096).unwrap(),
            NonZeroUsize::new(256).unwrap(),
            NonZeroUsize::new(8).unwrap(),
        )
    }

    fn source(rows: &str) -> Vec<u8> {
        format!("! product-owned fixture\r\n# Hz S RI R 50.0\r\n{rows}\r\n").into_bytes()
    }

    #[test]
    fn parses_public_order_and_comments() {
        let parsed = parse_touchstone_hz_s_ri_50_two_port_v1(
            &source("0 1 2 3 4 5 6 7 8 ! inline\r\n1000000 9 10 11 12 13 14 15 16"),
            limits(),
        )
        .unwrap();
        assert_eq!(parsed.rows().len(), 2);
        let row = parsed.rows()[0];
        assert_eq!(row.s11().real(), 1.0);
        assert_eq!(row.s21().real(), 3.0);
        assert_eq!(row.s12().real(), 5.0);
        assert_eq!(row.s22().real(), 7.0);
    }

    #[test]
    fn admission_maps_s21_to_the_existing_kernel() {
        let parsed = parse_touchstone_hz_s_ri_50_two_port_v1(
            &source("0 9 0 1 0 8 0 7 0\r\n1000000 6 0 1 0 5 0 4 0"),
            limits(),
        )
        .unwrap();
        let spectrum = admit_matched_two_port_spectrum_v1(&parsed).unwrap();
        let kernel = resolve_matched_kernel_v1(
            &spectrum,
            ChannelLimitsV1::new(NonZeroUsize::new(8).unwrap()),
        )
        .unwrap();
        assert!((kernel.gain()[0].get() - 1.0).abs() < 1e-12);
        assert_eq!(kernel.gain().len(), 2);
    }

    #[test]
    fn lexical_and_bound_failures_are_closed() {
        assert_eq!(
            parse_touchstone_hz_s_ri_50_two_port_v1(
                b"# Hz S RI R 50.0\n0 0 0 0 0 0 0 0 0\0",
                limits()
            )
            .unwrap_err(),
            TouchstoneError::NulByte
        );
        assert_eq!(
            parse_touchstone_hz_s_ri_50_two_port_v1(b"# Hz S MA R 50.0", limits()).unwrap_err(),
            TouchstoneError::UnsupportedOptionLine
        );
        assert_eq!(
            parse_touchstone_hz_s_ri_50_two_port_v1(b"0 0 0 0 0 0 0 0 0", limits()).unwrap_err(),
            TouchstoneError::MissingOptionLine
        );
        assert_eq!(
            parse_touchstone_hz_s_ri_50_two_port_v1(b"# Hz S RI R 50.0\n0 0 0", limits())
                .unwrap_err(),
            TouchstoneError::MalformedDataRow
        );
        assert_eq!(
            parse_touchstone_hz_s_ri_50_two_port_v1(
                b"# Hz S RI R 50.0\n0 NaN 0 0 0 0 0 0 0",
                limits()
            )
            .unwrap_err(),
            TouchstoneError::NonFiniteNumber
        );
        assert_eq!(
            parse_touchstone_hz_s_ri_50_two_port_v1(b"# Hz S RI R 50.0\n\xFF", limits())
                .unwrap_err(),
            TouchstoneError::NonAsciiInput
        );
        assert_eq!(
            parse_touchstone_hz_s_ri_50_two_port_v1(
                b"# Hz S RI R 50.0\r0 0 0 0 0 0 0 0 0",
                limits()
            )
            .unwrap_err(),
            TouchstoneError::InvalidLineEnding
        );
        assert_eq!(
            parse_touchstone_hz_s_ri_50_two_port_v1(b"# Hz S RI R 50.0\r", limits()).unwrap_err(),
            TouchstoneError::InvalidLineEnding
        );
        let one_byte_input = TouchstoneParseLimitsV1::new(
            NonZeroUsize::new(1).unwrap(),
            NonZeroUsize::new(256).unwrap(),
            NonZeroUsize::new(8).unwrap(),
        );
        assert_eq!(
            parse_touchstone_hz_s_ri_50_two_port_v1(b"# Hz S RI R 50.0", one_byte_input)
                .unwrap_err(),
            TouchstoneError::InputLimitExceeded
        );
        let short_line = TouchstoneParseLimitsV1::new(
            NonZeroUsize::new(4_096).unwrap(),
            NonZeroUsize::new(3).unwrap(),
            NonZeroUsize::new(8).unwrap(),
        );
        assert_eq!(
            parse_touchstone_hz_s_ri_50_two_port_v1(b"# Hz S RI R 50.0", short_line).unwrap_err(),
            TouchstoneError::LineLimitExceeded
        );
        let two_records = TouchstoneParseLimitsV1::new(
            NonZeroUsize::new(4_096).unwrap(),
            NonZeroUsize::new(256).unwrap(),
            NonZeroUsize::new(2).unwrap(),
        );
        assert_eq!(
            parse_touchstone_hz_s_ri_50_two_port_v1(
                &source("0 0 0 1 0 0 0 0 0\r\n1 0 0 1 0 0 0 0 0\r\n2 0 0 1 0 0 0 0 0"),
                two_records
            )
            .unwrap_err(),
            TouchstoneError::RecordLimitExceeded
        );
    }

    #[test]
    fn option_and_field_boundaries_are_explicit() {
        assert_eq!(
            parse_touchstone_hz_s_ri_50_two_port_v1(
                b"# Hz S RI R 50.0\n# Hz S RI R 50.0",
                limits()
            )
            .unwrap_err(),
            TouchstoneError::DuplicateOptionLine
        );
        assert_eq!(
            parse_touchstone_hz_s_ri_50_two_port_v1(
                b"# Hz S RI R 50.0\n0 0 0 1 0 0 0 0 0\n# Hz S RI R 50.0",
                limits()
            )
            .unwrap_err(),
            TouchstoneError::OptionLineAfterData
        );
        let parsed = parse_touchstone_hz_s_ri_50_two_port_v1(
            b"# Hz S RI R 50.0\n0\t0\t0\t1\t0\t0\t0\t0\t0\n1\t0\t0\t1\t0\t0\t0\t0\t0",
            limits(),
        )
        .unwrap();
        assert_eq!(parsed.rows().len(), 2);
    }

    #[test]
    fn grid_and_record_admission_is_strict() {
        let nonuniform = parse_touchstone_hz_s_ri_50_two_port_v1(
            &source("0 0 0 1 0 0 0 0 0\r\n1 0 0 1 0 0 0 0 0\r\n3 0 0 1 0 0 0 0 0"),
            limits(),
        )
        .unwrap();
        assert_eq!(
            admit_matched_two_port_spectrum_v1(&nonuniform).unwrap_err(),
            TouchstoneError::NonUniformFrequencyGrid
        );
        let missing_dc = parse_touchstone_hz_s_ri_50_two_port_v1(
            &source("1 0 0 1 0 0 0 0 0\r\n2 0 0 1 0 0 0 0 0"),
            limits(),
        )
        .unwrap();
        assert_eq!(
            admit_matched_two_port_spectrum_v1(&missing_dc).unwrap_err(),
            TouchstoneError::MissingDc
        );
        let too_few =
            parse_touchstone_hz_s_ri_50_two_port_v1(&source("0 0 0 1 0 0 0 0 0"), limits())
                .unwrap();
        assert_eq!(
            admit_matched_two_port_spectrum_v1(&too_few).unwrap_err(),
            TouchstoneError::TooFewRows
        );
    }
}
