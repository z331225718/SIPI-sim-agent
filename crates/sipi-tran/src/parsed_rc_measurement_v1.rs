//! Exact-profile text consumer for the bounded one-node RC/PULSE solver.

use std::{error::Error, fmt, num::NonZeroUsize};

use sipi_types::{FiniteF64, Ohms, Seconds, TypeError, Volts};

use crate::{
    IdealPulseV1, OneNodeRcPulseLimitsV1, OneNodeRcPulseRequestV1, RcPulseTransientResultV1,
    TranError, simulate_one_node_rc_pulse,
};

pub const EXACT_RC_MEASUREMENT_DECK_POLICY_V1: &str = "sipi.p2-06.exact-rc-measurement-deck-v1";

/// Caller-owned parser and solver budgets for the exact seven-line deck.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct ExactRcMeasurementDeckLimitsV1 {
    max_input_bytes: NonZeroUsize,
    max_lines: NonZeroUsize,
    max_output_samples: NonZeroUsize,
    max_integration_breakpoints: NonZeroUsize,
}

impl ExactRcMeasurementDeckLimitsV1 {
    pub fn try_new(
        max_input_bytes: usize,
        max_lines: usize,
        max_output_samples: usize,
        max_integration_breakpoints: usize,
    ) -> Result<Self, ExactRcMeasurementDeckErrorV1> {
        Ok(Self {
            max_input_bytes: NonZeroUsize::new(max_input_bytes)
                .ok_or(ExactRcMeasurementDeckErrorV1::InvalidLimit)?,
            max_lines: NonZeroUsize::new(max_lines)
                .ok_or(ExactRcMeasurementDeckErrorV1::InvalidLimit)?,
            max_output_samples: NonZeroUsize::new(max_output_samples)
                .ok_or(ExactRcMeasurementDeckErrorV1::InvalidLimit)?,
            max_integration_breakpoints: NonZeroUsize::new(max_integration_breakpoints)
                .ok_or(ExactRcMeasurementDeckErrorV1::InvalidLimit)?,
        })
    }

    pub const fn max_input_bytes(self) -> NonZeroUsize {
        self.max_input_bytes
    }

    pub const fn max_lines(self) -> NonZeroUsize {
        self.max_lines
    }

    pub const fn max_output_samples(self) -> NonZeroUsize {
        self.max_output_samples
    }

    pub const fn max_integration_breakpoints(self) -> NonZeroUsize {
        self.max_integration_breakpoints
    }
}

/// Parsed form of the only admitted text topology and measurement.
#[derive(Clone, Debug, PartialEq)]
pub struct ExactRcMeasurementDeckV1 {
    title: String,
    resistance: Ohms,
    capacitance_farads: FiniteF64,
    pulse: IdealPulseV1,
    output_times: Vec<Seconds>,
    measurement_name: String,
}

impl ExactRcMeasurementDeckV1 {
    pub fn title(&self) -> &str {
        &self.title
    }

    pub const fn resistance(&self) -> Ohms {
        self.resistance
    }

    pub const fn capacitance_farads(&self) -> FiniteF64 {
        self.capacitance_farads
    }

    pub const fn pulse(&self) -> IdealPulseV1 {
        self.pulse
    }

    pub fn output_times(&self) -> &[Seconds] {
        &self.output_times
    }

    pub fn measurement_name(&self) -> &str {
        &self.measurement_name
    }
}

/// One finite `MAX V(out)` value evaluated only over emitted transient samples.
#[derive(Clone, Debug, PartialEq)]
pub struct ExactRcMeasurementResultV1 {
    name: String,
    value: Volts,
}

impl ExactRcMeasurementResultV1 {
    pub fn name(&self) -> &str {
        &self.name
    }

    pub const fn value(&self) -> Volts {
        self.value
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct ExactRcMeasurementRunV1 {
    transient: RcPulseTransientResultV1,
    measurement: ExactRcMeasurementResultV1,
}

impl ExactRcMeasurementRunV1 {
    pub fn transient(&self) -> &RcPulseTransientResultV1 {
        &self.transient
    }

    pub fn measurement(&self) -> &ExactRcMeasurementResultV1 {
        &self.measurement
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ExactRcMeasurementDeckErrorV1 {
    InvalidLimit,
    InputByteLimitExceeded,
    LineLimitExceeded,
    NonAsciiInput,
    InvalidDeckShape,
    UnsupportedAnalysis { line: usize },
    InvalidLine { line: usize },
    InvalidNumber { line: usize },
    OutputSampleLimitExceeded,
    OutputSampleCountOverflow,
    Invariant(TypeError),
    Transient(TranError),
}

impl fmt::Display for ExactRcMeasurementDeckErrorV1 {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::InvalidLimit => write!(formatter, "deck limits must be nonzero"),
            Self::InputByteLimitExceeded => write!(formatter, "deck input byte limit exceeded"),
            Self::LineLimitExceeded => write!(formatter, "deck line limit exceeded"),
            Self::NonAsciiInput => write!(formatter, "deck must contain printable ASCII only"),
            Self::InvalidDeckShape => write!(formatter, "deck must contain exactly seven lines"),
            Self::UnsupportedAnalysis { line } => {
                write!(formatter, "unsupported analysis on line {line}")
            }
            Self::InvalidLine { line } => write!(formatter, "invalid exact-profile line {line}"),
            Self::InvalidNumber { line } => {
                write!(formatter, "invalid numeric value on line {line}")
            }
            Self::OutputSampleLimitExceeded => write!(formatter, "output sample limit exceeded"),
            Self::OutputSampleCountOverflow => write!(formatter, "output sample count overflow"),
            Self::Invariant(error) => error.fmt(formatter),
            Self::Transient(error) => error.fmt(formatter),
        }
    }
}

impl Error for ExactRcMeasurementDeckErrorV1 {}

impl From<TypeError> for ExactRcMeasurementDeckErrorV1 {
    fn from(value: TypeError) -> Self {
        Self::Invariant(value)
    }
}

impl From<TranError> for ExactRcMeasurementDeckErrorV1 {
    fn from(value: TranError) -> Self {
        Self::Transient(value)
    }
}

/// Parses one title, V1/PULSE, R1, C1, `.tran`, one MAX measurement, and `.end`.
///
/// Element names, nodes, line order, arity, and measurement target are fixed.
/// `.op` and `.ac` are rejected instead of being accepted and ignored.
pub fn parse_exact_rc_measurement_deck_v1(
    text: &str,
    limits: ExactRcMeasurementDeckLimitsV1,
) -> Result<ExactRcMeasurementDeckV1, ExactRcMeasurementDeckErrorV1> {
    if text.len() > limits.max_input_bytes.get() {
        return Err(ExactRcMeasurementDeckErrorV1::InputByteLimitExceeded);
    }
    if text.bytes().any(|byte| {
        !byte.is_ascii() || (byte.is_ascii_control() && !matches!(byte, b'\r' | b'\n' | b'\t'))
    }) {
        return Err(ExactRcMeasurementDeckErrorV1::NonAsciiInput);
    }

    let lines = text.lines().collect::<Vec<_>>();
    if lines.len() > limits.max_lines.get() {
        return Err(ExactRcMeasurementDeckErrorV1::LineLimitExceeded);
    }
    if lines.len() != 7 || lines.iter().any(|line| line.trim().is_empty()) {
        return Err(ExactRcMeasurementDeckErrorV1::InvalidDeckShape);
    }
    for (index, line) in lines.iter().enumerate().skip(1) {
        let command = line.split_ascii_whitespace().next().unwrap_or_default();
        if command.eq_ignore_ascii_case(".op") || command.eq_ignore_ascii_case(".ac") {
            return Err(ExactRcMeasurementDeckErrorV1::UnsupportedAnalysis { line: index + 1 });
        }
    }

    let title = lines[0].trim();
    if title.starts_with('.') || title.bytes().any(|byte| byte.is_ascii_control()) {
        return Err(ExactRcMeasurementDeckErrorV1::InvalidLine { line: 1 });
    }
    let pulse = parse_source(lines[1], 2)?;
    let resistance = parse_resistor(lines[2], 3)?;
    let capacitance_farads = parse_capacitor(lines[3], 4)?;
    let output_times = parse_tran(lines[4], 5, limits)?;
    let measurement_name = parse_measurement(lines[5], 6)?;
    let end = lines[6].split_ascii_whitespace().collect::<Vec<_>>();
    if end.len() != 1 || !end[0].eq_ignore_ascii_case(".end") {
        return Err(ExactRcMeasurementDeckErrorV1::InvalidLine { line: 7 });
    }

    // Reuse the solver request constructor so every parsed deck is executable.
    let _ = OneNodeRcPulseRequestV1::try_new(
        output_times.clone(),
        resistance,
        capacitance_farads,
        Volts::try_new(0.0)?,
        pulse,
    )?;

    Ok(ExactRcMeasurementDeckV1 {
        title: title.to_owned(),
        resistance,
        capacitance_farads,
        pulse,
        output_times,
        measurement_name,
    })
}

pub fn simulate_exact_rc_measurement_deck_v1(
    deck: &ExactRcMeasurementDeckV1,
    limits: ExactRcMeasurementDeckLimitsV1,
) -> Result<ExactRcMeasurementRunV1, ExactRcMeasurementDeckErrorV1> {
    if deck.output_times.len() > limits.max_output_samples.get() {
        return Err(ExactRcMeasurementDeckErrorV1::OutputSampleLimitExceeded);
    }
    let request = OneNodeRcPulseRequestV1::try_new(
        deck.output_times.clone(),
        deck.resistance,
        deck.capacitance_farads,
        Volts::try_new(0.0)?,
        deck.pulse,
    )?;
    let transient = simulate_one_node_rc_pulse(
        &request,
        OneNodeRcPulseLimitsV1::new(
            limits.max_output_samples,
            limits.max_integration_breakpoints,
        ),
    )?;
    let maximum = transient
        .voltage_out()
        .samples()
        .iter()
        .map(|sample| sample.get())
        .reduce(f64::max)
        .ok_or(ExactRcMeasurementDeckErrorV1::OutputSampleCountOverflow)?;
    Ok(ExactRcMeasurementRunV1 {
        transient,
        measurement: ExactRcMeasurementResultV1 {
            name: deck.measurement_name.clone(),
            value: Volts::try_new(maximum)?,
        },
    })
}

pub fn parse_and_simulate_exact_rc_measurement_deck_v1(
    text: &str,
    limits: ExactRcMeasurementDeckLimitsV1,
) -> Result<ExactRcMeasurementRunV1, ExactRcMeasurementDeckErrorV1> {
    let deck = parse_exact_rc_measurement_deck_v1(text, limits)?;
    simulate_exact_rc_measurement_deck_v1(&deck, limits)
}

fn parse_source(
    line: &str,
    line_number: usize,
) -> Result<IdealPulseV1, ExactRcMeasurementDeckErrorV1> {
    let mut fields = line.split_ascii_whitespace();
    if !fields
        .next()
        .is_some_and(|field| field.eq_ignore_ascii_case("V1"))
        || !fields
            .next()
            .is_some_and(|field| field.eq_ignore_ascii_case("in"))
        || fields.next() != Some("0")
    {
        return Err(ExactRcMeasurementDeckErrorV1::InvalidLine { line: line_number });
    }
    let expression = fields.collect::<Vec<_>>().join(" ");
    if expression.len() < 8
        || !expression[..6].eq_ignore_ascii_case("PULSE(")
        || !expression.ends_with(')')
    {
        return Err(ExactRcMeasurementDeckErrorV1::InvalidLine { line: line_number });
    }
    let values = expression[6..expression.len() - 1]
        .split(|character: char| character == ',' || character.is_ascii_whitespace())
        .filter(|value| !value.is_empty())
        .collect::<Vec<_>>();
    if values.len() != 7 {
        return Err(ExactRcMeasurementDeckErrorV1::InvalidLine { line: line_number });
    }
    let parsed = values
        .into_iter()
        .map(|value| parse_si_number(value.trim(), line_number))
        .collect::<Result<Vec<_>, _>>()?;
    Ok(IdealPulseV1::try_new(
        Volts::try_new(parsed[0])?,
        Volts::try_new(parsed[1])?,
        Seconds::try_new(parsed[2])?,
        Seconds::try_new(parsed[3])?,
        Seconds::try_new(parsed[4])?,
        Seconds::try_new(parsed[5])?,
        Seconds::try_new(parsed[6])?,
    )?)
}

fn parse_resistor(line: &str, line_number: usize) -> Result<Ohms, ExactRcMeasurementDeckErrorV1> {
    let fields = line.split_ascii_whitespace().collect::<Vec<_>>();
    if fields.len() != 4
        || !fields[0].eq_ignore_ascii_case("R1")
        || !fields[1].eq_ignore_ascii_case("in")
        || !fields[2].eq_ignore_ascii_case("out")
    {
        return Err(ExactRcMeasurementDeckErrorV1::InvalidLine { line: line_number });
    }
    Ok(Ohms::try_new(parse_si_number(fields[3], line_number)?)?)
}

fn parse_capacitor(
    line: &str,
    line_number: usize,
) -> Result<FiniteF64, ExactRcMeasurementDeckErrorV1> {
    let fields = line.split_ascii_whitespace().collect::<Vec<_>>();
    if fields.len() != 4
        || !fields[0].eq_ignore_ascii_case("C1")
        || !fields[1].eq_ignore_ascii_case("out")
        || fields[2] != "0"
    {
        return Err(ExactRcMeasurementDeckErrorV1::InvalidLine { line: line_number });
    }
    Ok(FiniteF64::try_new(
        parse_si_number(fields[3], line_number)?,
        "capacitance farads",
    )?)
}

fn parse_tran(
    line: &str,
    line_number: usize,
    limits: ExactRcMeasurementDeckLimitsV1,
) -> Result<Vec<Seconds>, ExactRcMeasurementDeckErrorV1> {
    let fields = line.split_ascii_whitespace().collect::<Vec<_>>();
    if fields.len() != 3 || !fields[0].eq_ignore_ascii_case(".tran") {
        return Err(ExactRcMeasurementDeckErrorV1::InvalidLine { line: line_number });
    }
    let step = parse_si_number(fields[1], line_number)?;
    let stop = parse_si_number(fields[2], line_number)?;
    if step <= 0.0 || stop <= 0.0 {
        return Err(ExactRcMeasurementDeckErrorV1::InvalidNumber { line: line_number });
    }
    let ratio = stop / step;
    let rounded = ratio.round();
    let tolerance = ratio.abs().max(1.0) * 1.0e-12;
    if !ratio.is_finite()
        || (ratio - rounded).abs() > tolerance
        || rounded < 1.0
        || rounded > (usize::MAX - 1) as f64
    {
        return Err(ExactRcMeasurementDeckErrorV1::InvalidNumber { line: line_number });
    }
    let intervals = rounded as usize;
    let count = intervals
        .checked_add(1)
        .ok_or(ExactRcMeasurementDeckErrorV1::OutputSampleCountOverflow)?;
    if count > limits.max_output_samples.get() {
        return Err(ExactRcMeasurementDeckErrorV1::OutputSampleLimitExceeded);
    }
    (0..=intervals)
        .map(|index| {
            let value = if index == intervals {
                stop
            } else {
                index as f64 * step
            };
            Seconds::try_new(value).map_err(Into::into)
        })
        .collect()
}

fn parse_measurement(
    line: &str,
    line_number: usize,
) -> Result<String, ExactRcMeasurementDeckErrorV1> {
    let fields = line.split_ascii_whitespace().collect::<Vec<_>>();
    if fields.len() != 5
        || !fields[0].eq_ignore_ascii_case(".measure")
        || !fields[1].eq_ignore_ascii_case("tran")
        || !fields[3].eq_ignore_ascii_case("max")
        || !fields[4].eq_ignore_ascii_case("v(out)")
        || !is_identifier(fields[2])
    {
        return Err(ExactRcMeasurementDeckErrorV1::InvalidLine { line: line_number });
    }
    Ok(fields[2].to_owned())
}

fn is_identifier(value: &str) -> bool {
    let mut bytes = value.bytes();
    matches!(bytes.next(), Some(first) if first.is_ascii_alphabetic() || first == b'_')
        && bytes.all(|byte| byte.is_ascii_alphanumeric() || byte == b'_')
}

fn parse_si_number(token: &str, line: usize) -> Result<f64, ExactRcMeasurementDeckErrorV1> {
    let lower = token.to_ascii_lowercase();
    let (number, scale) = if let Some(number) = lower.strip_suffix("meg") {
        (number, 1.0e6)
    } else if let Some((suffix, scale)) = [
        ("t", 1.0e12),
        ("g", 1.0e9),
        ("k", 1.0e3),
        ("m", 1.0e-3),
        ("u", 1.0e-6),
        ("n", 1.0e-9),
        ("p", 1.0e-12),
        ("f", 1.0e-15),
    ]
    .into_iter()
    .find(|(suffix, _)| lower.ends_with(suffix))
    {
        (&lower[..lower.len() - suffix.len()], scale)
    } else {
        (lower.as_str(), 1.0)
    };
    let parsed = number
        .parse::<f64>()
        .map_err(|_| ExactRcMeasurementDeckErrorV1::InvalidNumber { line })?;
    let scaled = parsed * scale;
    if scaled.is_finite() {
        Ok(scaled)
    } else {
        Err(ExactRcMeasurementDeckErrorV1::InvalidNumber { line })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const DECK: &str = "Agent-Spice bounded RC measurement\n\
V1 in 0 PULSE(0 1 1u 1n 1n 10u 20u)\n\
R1 in out 1k\n\
C1 out 0 1u\n\
.tran 1u 3u\n\
.measure TRAN vmax MAX V(out)\n\
.end\n";

    fn limits() -> ExactRcMeasurementDeckLimitsV1 {
        ExactRcMeasurementDeckLimitsV1::try_new(4096, 7, 16, 32).unwrap()
    }

    #[test]
    fn exact_deck_runs_and_max_is_from_emitted_samples() {
        let deck = parse_exact_rc_measurement_deck_v1(DECK, limits()).unwrap();
        assert_eq!(deck.output_times().len(), 4);
        assert_eq!(deck.resistance().get(), 1.0e3);
        assert_eq!(deck.capacitance_farads().get(), 1.0e-6);

        let run = simulate_exact_rc_measurement_deck_v1(&deck, limits()).unwrap();
        let expected = run
            .transient()
            .voltage_out()
            .samples()
            .iter()
            .map(|sample| sample.get())
            .reduce(f64::max)
            .unwrap();
        assert_eq!(run.measurement().name(), "vmax");
        assert_eq!(run.measurement().value().get(), expected);
    }

    #[test]
    fn unsupported_analyses_and_shape_expansion_fail_closed() {
        let op = DECK.replace(".tran 1u 3u", ".op");
        assert_eq!(
            parse_exact_rc_measurement_deck_v1(&op, limits()),
            Err(ExactRcMeasurementDeckErrorV1::UnsupportedAnalysis { line: 5 })
        );
        let ac = DECK.replace(".tran 1u 3u", ".ac lin 3 1 3");
        assert_eq!(
            parse_exact_rc_measurement_deck_v1(&ac, limits()),
            Err(ExactRcMeasurementDeckErrorV1::UnsupportedAnalysis { line: 5 })
        );
        let duplicate = DECK.replace(".end\n", ".measure TRAN extra MAX V(out)\n.end\n");
        assert_eq!(
            parse_exact_rc_measurement_deck_v1(&duplicate, limits()),
            Err(ExactRcMeasurementDeckErrorV1::LineLimitExceeded)
        );
        let wrong_node = DECK.replace("C1 out 0", "C1 other 0");
        assert_eq!(
            parse_exact_rc_measurement_deck_v1(&wrong_node, limits()),
            Err(ExactRcMeasurementDeckErrorV1::InvalidLine { line: 4 })
        );
    }

    #[test]
    fn budgets_and_measurement_forms_fail_closed() {
        let tight = ExactRcMeasurementDeckLimitsV1::try_new(4096, 7, 3, 32).unwrap();
        assert_eq!(
            parse_exact_rc_measurement_deck_v1(DECK, tight),
            Err(ExactRcMeasurementDeckErrorV1::OutputSampleLimitExceeded)
        );
        let windowed = DECK.replace("V(out)", "V(out) FROM=1u");
        assert_eq!(
            parse_exact_rc_measurement_deck_v1(&windowed, limits()),
            Err(ExactRcMeasurementDeckErrorV1::InvalidLine { line: 6 })
        );
        let source_ac = DECK.replace(")\nR1", ") AC 1\nR1");
        assert_eq!(
            parse_exact_rc_measurement_deck_v1(&source_ac, limits()),
            Err(ExactRcMeasurementDeckErrorV1::InvalidLine { line: 2 })
        );
    }
}
