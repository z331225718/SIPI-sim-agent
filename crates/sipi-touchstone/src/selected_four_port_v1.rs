//! Strict lexical admission for the selected P3C four-port Touchstone input.
//!
//! Version 1 accepts only `# Hz S RI R 50.0`; version 2 additionally accepts
//! the separately allowlisted `# Hz S RI R 50` spelling. Neither version
//! normalizes option-line numeric tokens. Both produce no file identity,
//! time-domain model, interpolation, repair, or waveform. The fixed bench
//! reduction lives separately in `sipi-channel`.

use std::{error::Error, fmt};

use sipi_channel::{FourPortS, SELECTED_P3C_PORT_COUNT, SelectedP3cFourPortSpectrumV1};
use sipi_types::{Complex64, Hertz, Ohms};

use super::{TouchstoneParseLimitsV1, finite_number, parse_line, split_fields};

const VALUES_PER_RECORD: usize = 1 + 2 * SELECTED_P3C_PORT_COUNT * SELECTED_P3C_PORT_COUNT;

/// One parsed four-port record in public Touchstone column-major order.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct ParsedSelectedFourPortRowV1 {
    frequency_hz: f64,
    matrix: FourPortS,
}

impl ParsedSelectedFourPortRowV1 {
    pub fn frequency_hz(self) -> f64 {
        self.frequency_hz
    }

    pub fn matrix(self) -> FourPortS {
        self.matrix
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct ParsedSelectedFourPortV1 {
    rows: Vec<ParsedSelectedFourPortRowV1>,
}

impl ParsedSelectedFourPortV1 {
    pub fn rows(&self) -> &[ParsedSelectedFourPortRowV1] {
        &self.rows
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum SelectedFourPortTouchstoneErrorV1 {
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
    UnsupportedKeyword,
    MalformedRecord,
    NonFiniteNumber,
    EmptyDocument,
    ChannelAdmission,
}

impl fmt::Display for SelectedFourPortTouchstoneErrorV1 {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            formatter,
            "selected four-port Touchstone v1 input is invalid: {self:?}"
        )
    }
}

impl Error for SelectedFourPortTouchstoneErrorV1 {}

fn map_common_error(error: super::TouchstoneError) -> SelectedFourPortTouchstoneErrorV1 {
    match error {
        super::TouchstoneError::InputLimitExceeded => {
            SelectedFourPortTouchstoneErrorV1::InputLimitExceeded
        }
        super::TouchstoneError::NonAsciiInput => SelectedFourPortTouchstoneErrorV1::NonAsciiInput,
        super::TouchstoneError::NulByte => SelectedFourPortTouchstoneErrorV1::NulByte,
        super::TouchstoneError::InvalidLineEnding => {
            SelectedFourPortTouchstoneErrorV1::InvalidLineEnding
        }
        super::TouchstoneError::LineLimitExceeded => {
            SelectedFourPortTouchstoneErrorV1::LineLimitExceeded
        }
        super::TouchstoneError::NonFiniteNumber => {
            SelectedFourPortTouchstoneErrorV1::NonFiniteNumber
        }
        _ => SelectedFourPortTouchstoneErrorV1::MalformedRecord,
    }
}

fn parse_record(
    tokens: &[&[u8]],
) -> Result<ParsedSelectedFourPortRowV1, SelectedFourPortTouchstoneErrorV1> {
    debug_assert_eq!(tokens.len(), VALUES_PER_RECORD);
    let values = tokens
        .iter()
        .map(|token| finite_number(token).map_err(map_common_error))
        .collect::<Result<Vec<_>, _>>()?;
    let mut matrix = [[Complex64::try_new(0.0, 0.0).expect("finite zero"); SELECTED_P3C_PORT_COUNT];
        SELECTED_P3C_PORT_COUNT];
    for incident in 0..SELECTED_P3C_PORT_COUNT {
        for output in 0..SELECTED_P3C_PORT_COUNT {
            let public_index = 1 + 2 * (incident * SELECTED_P3C_PORT_COUNT + output);
            matrix[output][incident] =
                Complex64::try_new(values[public_index], values[public_index + 1])
                    .map_err(|_| SelectedFourPortTouchstoneErrorV1::NonFiniteNumber)?;
        }
    }
    Ok(ParsedSelectedFourPortRowV1 {
        frequency_hz: values[0],
        matrix: FourPortS::new(matrix),
    })
}

fn parse_selected_four_port_with_allowed_options(
    bytes: &[u8],
    limits: TouchstoneParseLimitsV1,
    allowed_options: &[&[u8]],
) -> Result<ParsedSelectedFourPortV1, SelectedFourPortTouchstoneErrorV1> {
    if bytes.len() > limits.max_input_bytes.get() {
        return Err(SelectedFourPortTouchstoneErrorV1::InputLimitExceeded);
    }
    if bytes.contains(&0) {
        return Err(SelectedFourPortTouchstoneErrorV1::NulByte);
    }
    if !bytes.is_ascii() {
        return Err(SelectedFourPortTouchstoneErrorV1::NonAsciiInput);
    }
    if bytes.ends_with(b"\r") {
        return Err(SelectedFourPortTouchstoneErrorV1::InvalidLineEnding);
    }
    let mut saw_option = false;
    let mut saw_data = false;
    let mut tokens = Vec::with_capacity(VALUES_PER_RECORD);
    let mut rows = Vec::new();
    for raw_line in bytes.split(|byte| *byte == b'\n') {
        let line = raw_line.strip_suffix(b"\r").unwrap_or(raw_line);
        let Some(content) = parse_line(line, limits).map_err(map_common_error)? else {
            continue;
        };
        if content.starts_with(b"#") {
            if saw_data || !tokens.is_empty() {
                return Err(SelectedFourPortTouchstoneErrorV1::OptionLineAfterData);
            }
            if saw_option {
                return Err(SelectedFourPortTouchstoneErrorV1::DuplicateOptionLine);
            }
            if !allowed_options.contains(&content) {
                return Err(SelectedFourPortTouchstoneErrorV1::UnsupportedOptionLine);
            }
            saw_option = true;
            continue;
        }
        if content.starts_with(b"[") {
            return Err(SelectedFourPortTouchstoneErrorV1::UnsupportedKeyword);
        }
        if !saw_option {
            return Err(SelectedFourPortTouchstoneErrorV1::MissingOptionLine);
        }
        saw_data = true;
        for token in split_fields(content) {
            finite_number(token).map_err(map_common_error)?;
            tokens.push(token);
            if tokens.len() == VALUES_PER_RECORD {
                if rows.len() == limits.max_data_records.get() {
                    return Err(SelectedFourPortTouchstoneErrorV1::RecordLimitExceeded);
                }
                rows.push(parse_record(&tokens)?);
                tokens.clear();
            }
        }
    }
    if !saw_option {
        return Err(SelectedFourPortTouchstoneErrorV1::MissingOptionLine);
    }
    if !tokens.is_empty() {
        return Err(SelectedFourPortTouchstoneErrorV1::MalformedRecord);
    }
    if rows.is_empty() {
        return Err(SelectedFourPortTouchstoneErrorV1::EmptyDocument);
    }
    Ok(ParsedSelectedFourPortV1 { rows })
}

/// Parse only the original selected four-port `Hz S RI R 50.0` lexical
/// subset. This frozen entry point never accepts the `R 50` spelling.
///
/// Data records may span data-only continuation lines, but option lines and
/// Touchstone keywords are never accepted after data begins.
pub fn parse_selected_four_port_hz_s_ri_50_v1(
    bytes: &[u8],
    limits: TouchstoneParseLimitsV1,
) -> Result<ParsedSelectedFourPortV1, SelectedFourPortTouchstoneErrorV1> {
    parse_selected_four_port_with_allowed_options(bytes, limits, &[b"# Hz S RI R 50.0"])
}

/// Parse the amended selected four-port lexical profile. It accepts exactly
/// the two approved option-line spellings and does not perform numeric token
/// normalization.
pub fn parse_selected_four_port_hz_s_ri_50_v2(
    bytes: &[u8],
    limits: TouchstoneParseLimitsV1,
) -> Result<ParsedSelectedFourPortV1, SelectedFourPortTouchstoneErrorV1> {
    parse_selected_four_port_with_allowed_options(
        bytes,
        limits,
        &[b"# Hz S RI R 50", b"# Hz S RI R 50.0"],
    )
}

/// Bind the parsed spectrum to the only product-side P3C static bench.
/// This admits neither a time-domain solver nor a candidate waveform.
pub fn admit_selected_p3c_fixed_four_port_v1(
    parsed: &ParsedSelectedFourPortV1,
) -> Result<SelectedP3cFourPortSpectrumV1, SelectedFourPortTouchstoneErrorV1> {
    let frequencies = parsed
        .rows()
        .iter()
        .map(|row| {
            Hertz::try_new(row.frequency_hz())
                .map_err(|_| SelectedFourPortTouchstoneErrorV1::ChannelAdmission)
        })
        .collect::<Result<Vec<_>, _>>()?;
    let samples = parsed.rows().iter().map(|row| row.matrix()).collect();
    SelectedP3cFourPortSpectrumV1::try_new(
        Ohms::try_new(50.0).expect("finite selected impedance"),
        frequencies,
        samples,
    )
    .map_err(|_| SelectedFourPortTouchstoneErrorV1::ChannelAdmission)
}

#[cfg(test)]
mod tests {
    use std::num::NonZeroUsize;

    use sipi_channel::reduce_selected_p3c_fixed_four_port_bench_v1;

    use super::*;

    fn limits() -> TouchstoneParseLimitsV1 {
        TouchstoneParseLimitsV1::new(
            NonZeroUsize::new(8_192).unwrap(),
            NonZeroUsize::new(512).unwrap(),
            NonZeroUsize::new(4).unwrap(),
        )
    }

    fn record(frequency: f64, values: &[(usize, usize, f64, f64)]) -> String {
        let mut matrix = [[(0.0, 0.0); SELECTED_P3C_PORT_COUNT]; SELECTED_P3C_PORT_COUNT];
        for &(output, incident, real, imaginary) in values {
            matrix[output][incident] = (real, imaginary);
        }
        let mut fields = vec![frequency.to_string()];
        for incident in 0..SELECTED_P3C_PORT_COUNT {
            for output in 0..SELECTED_P3C_PORT_COUNT {
                let (real, imaginary) = matrix[output][incident];
                fields.push(real.to_string());
                fields.push(imaginary.to_string());
            }
        }
        fields.join(" ")
    }

    #[test]
    fn public_column_major_order_flows_to_fixed_bench_reduction() {
        let row = record(
            0.0,
            &[
                (1, 0, 4.0, 8.0),
                (1, 2, 8.0, 4.0),
                (3, 0, 12.0, -4.0),
                (3, 2, 16.0, -8.0),
            ],
        );
        let source = format!("! synthetic only\r\n# Hz S RI R 50.0\r\n{row}\r\n");
        let parsed = parse_selected_four_port_hz_s_ri_50_v1(source.as_bytes(), limits()).unwrap();
        let matrix = parsed.rows()[0].matrix();
        assert_eq!(matrix.at(1, 0).unwrap().real(), 4.0);
        assert_eq!(matrix.at(3, 2).unwrap().imaginary(), -8.0);
        let transfer = reduce_selected_p3c_fixed_four_port_bench_v1(
            &admit_selected_p3c_fixed_four_port_v1(&parsed).unwrap(),
        )
        .unwrap();
        assert_eq!(transfer.transfer()[0].real(), 0.0);
        assert_eq!(transfer.transfer()[0].imaginary(), 0.0);
    }

    #[test]
    fn continuation_and_strict_record_shape_are_explicit() {
        let row = record(0.0, &[]);
        let split = row.find(' ').unwrap();
        let source = format!("# Hz S RI R 50.0\n{}\n{}", &row[..split], &row[split + 1..]);
        assert_eq!(
            parse_selected_four_port_hz_s_ri_50_v1(source.as_bytes(), limits())
                .unwrap()
                .rows()
                .len(),
            1
        );
        assert_eq!(
            parse_selected_four_port_hz_s_ri_50_v1(b"# Hz S RI R 50.0\n0 0", limits()).unwrap_err(),
            SelectedFourPortTouchstoneErrorV1::MalformedRecord
        );
    }

    #[test]
    fn v2_accepts_only_the_two_approved_reference_impedance_spellings() {
        let row = record(0.0, &[]);
        let with_integer = format!("# Hz S RI R 50\n{row}");
        let with_decimal = format!("# Hz S RI R 50.0\n{row}");
        assert_eq!(
            parse_selected_four_port_hz_s_ri_50_v2(with_integer.as_bytes(), limits()).unwrap(),
            parse_selected_four_port_hz_s_ri_50_v2(with_decimal.as_bytes(), limits()).unwrap(),
        );
        assert_eq!(
            parse_selected_four_port_hz_s_ri_50_v1(with_integer.as_bytes(), limits()).unwrap_err(),
            SelectedFourPortTouchstoneErrorV1::UnsupportedOptionLine,
        );
        for spelling in ["050", "50.", "50.00", "5e1", "+50", "49.999"] {
            let source = format!("# Hz S RI R {spelling}\n{row}");
            assert_eq!(
                parse_selected_four_port_hz_s_ri_50_v2(source.as_bytes(), limits()).unwrap_err(),
                SelectedFourPortTouchstoneErrorV1::UnsupportedOptionLine,
            );
        }
    }

    #[test]
    fn unsupported_formats_keywords_and_frequency_order_fail_closed() {
        assert_eq!(
            parse_selected_four_port_hz_s_ri_50_v1(b"# Hz S MA R 50.0", limits()).unwrap_err(),
            SelectedFourPortTouchstoneErrorV1::UnsupportedOptionLine
        );
        assert_eq!(
            parse_selected_four_port_hz_s_ri_50_v1(b"# Hz S RI R 50.0\n[Version] 2.0", limits(),)
                .unwrap_err(),
            SelectedFourPortTouchstoneErrorV1::UnsupportedKeyword
        );
        let source = format!(
            "# Hz S RI R 50.0\n{}\n{}",
            record(1.0, &[]),
            record(1.0, &[])
        );
        let parsed = parse_selected_four_port_hz_s_ri_50_v1(source.as_bytes(), limits()).unwrap();
        assert_eq!(
            admit_selected_p3c_fixed_four_port_v1(&parsed).unwrap_err(),
            SelectedFourPortTouchstoneErrorV1::ChannelAdmission
        );
    }

    #[test]
    fn bounds_and_nonfinite_values_fail_closed() {
        assert_eq!(
            parse_selected_four_port_hz_s_ri_50_v1(b"# Hz S RI R 50.0\n0 NaN 0", limits(),)
                .unwrap_err(),
            SelectedFourPortTouchstoneErrorV1::NonFiniteNumber
        );
        let short = TouchstoneParseLimitsV1::new(
            NonZeroUsize::new(8).unwrap(),
            NonZeroUsize::new(512).unwrap(),
            NonZeroUsize::new(4).unwrap(),
        );
        assert_eq!(
            parse_selected_four_port_hz_s_ri_50_v1(b"# Hz S RI R 50.0", short).unwrap_err(),
            SelectedFourPortTouchstoneErrorV1::InputLimitExceeded
        );
    }
}
