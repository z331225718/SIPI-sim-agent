use std::collections::{HashMap, HashSet};
use std::f64::consts::PI;
use std::fs;
use std::ops::Deref;
use std::path::{Path, PathBuf};

use faer::c64;

use crate::error::{Error, Result};
use crate::expression;
use crate::logging;
use crate::rfm::RfmModel;

pub type Node = Option<usize>;

const HSPICE_DEFAULT_RESMIN: f64 = 1e-5;

#[derive(Debug, Clone)]
pub enum Waveform {
    Pulse {
        initial: f64,
        pulsed: f64,
        delay: f64,
        rise: f64,
        fall: f64,
        width: f64,
        period: f64,
    },
    Pwl {
        points: Vec<(f64, f64)>,
        hard_breakpoints: Vec<f64>,
        repeat_from: Option<f64>,
    },
}

impl Waveform {
    pub fn value(&self, time: f64) -> f64 {
        match self {
            Self::Pulse {
                initial,
                pulsed,
                delay,
                rise,
                fall,
                width,
                period,
            } => {
                if time < *delay {
                    return *initial;
                }
                let local = if *period > 0.0 {
                    (time - delay).rem_euclid(*period)
                } else {
                    time - delay
                };
                if *rise > 0.0 && local < *rise {
                    return initial + (pulsed - initial) * local / rise;
                }
                if local < rise + width {
                    return *pulsed;
                }
                if *fall > 0.0 && local < rise + width + fall {
                    return pulsed - (pulsed - initial) * (local - rise - width) / fall;
                }
                *initial
            }
            Self::Pwl {
                points,
                repeat_from,
                ..
            } => {
                let time = repeat_from.map_or(time, |repeat_from| {
                    let end = points.last().expect("PWL has at least one point").0;
                    if time > end {
                        repeat_from + (time - repeat_from).rem_euclid(end - repeat_from)
                    } else {
                        time
                    }
                });
                interpolate_pwl(points, time)
            }
        }
    }

    pub fn next_breakpoint_after(&self, time: f64, stop: f64) -> Option<f64> {
        let tolerance = 1e-15_f64.max(time.abs() * 1e-12);
        match self {
            Self::Pwl {
                hard_breakpoints,
                repeat_from,
                ..
            } => {
                let threshold = time + tolerance;
                let direct_index =
                    hard_breakpoints.partition_point(|point_time| *point_time <= threshold);
                let direct = hard_breakpoints
                    .get(direct_index)
                    .copied()
                    .filter(|point_time| *point_time <= stop);
                let repeated = repeat_from
                    .and_then(|repeat_from| {
                        next_repeated_pwl_breakpoint(hard_breakpoints, repeat_from, threshold)
                    })
                    .filter(|point_time| *point_time <= stop);
                direct.into_iter().chain(repeated).min_by(f64::total_cmp)
            }
            Self::Pulse {
                delay,
                rise,
                fall,
                width,
                period,
                ..
            } => {
                let offsets = [0.0, *rise, rise + width, rise + width + fall];
                let first_cycle = if period.is_finite() && *period > 0.0 && time > *delay {
                    ((time - delay) / period).floor().max(0.0) as usize
                } else {
                    0
                };
                let cycle_count = if period.is_finite() && *period > 0.0 {
                    3
                } else {
                    1
                };
                (first_cycle..first_cycle + cycle_count)
                    .flat_map(|cycle| {
                        offsets
                            .iter()
                            .map(move |offset| delay + cycle as f64 * period + offset)
                    })
                    .filter(|candidate| {
                        candidate.is_finite() && *candidate > time + tolerance && *candidate <= stop
                    })
                    .min_by(f64::total_cmp)
            }
        }
    }
}

fn interpolate_pwl(points: &[(f64, f64)], time: f64) -> f64 {
    let right = points.partition_point(|(point_time, _)| *point_time < time);
    if right == 0 {
        return points[0].1;
    }
    if right == points.len() {
        return points.last().expect("PWL has at least one point").1;
    }
    let (left_time, left_value) = points[right - 1];
    let (right_time, right_value) = points[right];
    let fraction = (time - left_time) / (right_time - left_time);
    left_value + fraction * (right_value - left_value)
}

fn next_repeated_pwl_breakpoint(
    hard_breakpoints: &[f64],
    repeat_from: f64,
    threshold: f64,
) -> Option<f64> {
    let end = *hard_breakpoints.last().expect("PWL has at least one point");
    let period = end - repeat_from;
    if !period.is_finite() || period <= 0.0 {
        return None;
    }
    let cycle = if threshold < repeat_from {
        0.0
    } else {
        ((threshold - repeat_from) / period).floor()
    };
    let offset = cycle * period;
    let local_threshold = threshold - offset;
    let first_repeated = hard_breakpoints.partition_point(|point_time| *point_time < repeat_from);
    let repeated = &hard_breakpoints[first_repeated..];
    let next = repeated.partition_point(|point_time| *point_time <= local_threshold);
    let candidate = repeated
        .get(next)
        .map_or(repeat_from + (cycle + 1.0) * period, |point_time| {
            point_time + offset
        });
    (candidate > threshold).then_some(candidate)
}

fn pwl_hard_breakpoints(points: &[(f64, f64)], repeat_from: Option<f64>) -> Vec<f64> {
    debug_assert!(!points.is_empty());
    let mut breakpoints = Vec::with_capacity(points.len());
    breakpoints.push(points[0].0);
    for window in points.windows(3) {
        let [(t0, v0), (t1, v1), (t2, v2)] = window else {
            unreachable!("PWL windows have exactly three points")
        };
        let left_slope = (v1 - v0) / (t1 - t0);
        let right_slope = (v2 - v1) / (t2 - t1);
        if left_slope.to_bits() != right_slope.to_bits() {
            breakpoints.push(*t1);
        }
    }
    breakpoints.push(points.last().expect("PWL has at least one point").0);
    if let Some(repeat_from) = repeat_from {
        breakpoints.push(repeat_from);
    }
    breakpoints.sort_by(f64::total_cmp);
    breakpoints.dedup_by(|left, right| left.to_bits() == right.to_bits());
    breakpoints
}

#[cfg(test)]
mod waveform_lookup_tests {
    use super::{Waveform, interpolate_pwl, pwl_hard_breakpoints};

    #[test]
    fn binary_pwl_interpolation_preserves_boundaries_and_segments() {
        let points = [(0.0, 1.0), (1.0, 3.0), (2.5, -1.0), (4.0, 2.0)];
        let expected = [
            (-1.0, 1.0),
            (0.0, 1.0),
            (0.25, 1.5),
            (1.0, 3.0),
            (2.0, 1.0 / 3.0),
            (2.5, -1.0),
            (3.0, 0.0),
            (4.0, 2.0),
            (5.0, 2.0),
        ];
        for (time, value) in expected {
            assert!((interpolate_pwl(&points, time) - value).abs() < 1e-12);
        }
    }

    #[test]
    fn binary_repeated_pwl_breakpoints_match_cycle_boundaries() {
        let waveform = Waveform::Pwl {
            points: vec![(0.0, 0.0), (1.0, 1.0), (2.5, 0.5), (4.0, 0.0)],
            hard_breakpoints: pwl_hard_breakpoints(
                &[(0.0, 0.0), (1.0, 1.0), (2.5, 0.5), (4.0, 0.0)],
                Some(1.0),
            ),
            repeat_from: Some(1.0),
        };
        let expected = [
            (0.0, 1.0),
            (1.0, 4.0),
            (2.5, 4.0),
            (4.0, 7.0),
            (5.5, 7.0),
            (7.0, 10.0),
        ];
        for (time, next) in expected {
            assert_eq!(waveform.next_breakpoint_after(time, 10.0), Some(next));
        }
    }

    #[test]
    fn exact_collinear_points_are_not_hard_breakpoints() {
        let points = [(0.0, 0.0), (1.0, 2.0), (2.0, 4.0), (3.0, 6.0)];
        let waveform = Waveform::Pwl {
            points: points.to_vec(),
            hard_breakpoints: pwl_hard_breakpoints(&points, None),
            repeat_from: None,
        };

        assert_eq!(waveform.next_breakpoint_after(0.0, 10.0), Some(3.0));
        for time in [-1.0, 0.0, 0.25, 1.0, 1.75, 2.0, 2.5, 3.0, 5.0] {
            assert_eq!(
                waveform.value(time).to_bits(),
                interpolate_pwl(&points, time).to_bits()
            );
        }
    }

    #[test]
    fn nearly_collinear_points_remain_hard_breakpoints() {
        let points = [
            (0.0, 0.0),
            (1.0, 2.0),
            (2.0, 4.0 + 8.0 * f64::EPSILON),
            (3.0, 6.0),
        ];
        assert_eq!(
            pwl_hard_breakpoints(&points, None),
            vec![0.0, 1.0, 2.0, 3.0]
        );
    }
}

#[derive(Debug, Clone)]
pub struct Source {
    pub dc: f64,
    pub ac: c64,
    pub waveform: Option<Waveform>,
}

struct ParsedPwlFileSource {
    points: Vec<(f64, f64)>,
    repeat_from: Option<f64>,
}

impl Source {
    pub fn transient_value(&self, time: f64) -> f64 {
        self.waveform
            .as_ref()
            .map_or(self.dc, |waveform| waveform.value(time))
    }
}

#[derive(Debug, Clone)]
pub enum Element {
    Resistor {
        name: String,
        positive: Node,
        negative: Node,
        resistance: f64,
    },
    Capacitor {
        name: String,
        positive: Node,
        negative: Node,
        capacitance: f64,
    },
    Inductor {
        name: String,
        positive: Node,
        negative: Node,
        inductance: f64,
        branch: usize,
    },
    Voltage {
        name: String,
        positive: Node,
        negative: Node,
        source: Source,
        branch: usize,
    },
    Current {
        name: String,
        positive: Node,
        negative: Node,
        source: Source,
    },
    Vcvs {
        name: String,
        positive: Node,
        negative: Node,
        control_positive: Node,
        control_negative: Node,
        gain: f64,
        branch: usize,
    },
    Vccs {
        name: String,
        positive: Node,
        negative: Node,
        control_positive: Node,
        control_negative: Node,
        transconductance: f64,
    },
    Cccs {
        name: String,
        positive: Node,
        negative: Node,
        control_branch: usize,
        gain: f64,
    },
    Ccvs {
        name: String,
        positive: Node,
        negative: Node,
        control_branch: usize,
        transresistance: f64,
        branch: usize,
    },
    Rfm {
        name: String,
        ports: Vec<Node>,
        references: Vec<Node>,
        model: Option<String>,
    },
}

impl Element {
    pub fn name(&self) -> &str {
        match self {
            Self::Resistor { name, .. }
            | Self::Capacitor { name, .. }
            | Self::Inductor { name, .. }
            | Self::Voltage { name, .. }
            | Self::Current { name, .. }
            | Self::Vcvs { name, .. }
            | Self::Vccs { name, .. }
            | Self::Cccs { name, .. }
            | Self::Ccvs { name, .. }
            | Self::Rfm { name, .. } => name,
        }
    }
}

#[derive(Debug, Clone)]
pub enum Analysis {
    Op,
    Dc {
        source: String,
        start: f64,
        stop: f64,
        step: f64,
    },
    Ac {
        scale: AcScale,
        points: usize,
        start: f64,
        stop: f64,
    },
    Tran {
        step: f64,
        stop: f64,
    },
}

#[derive(Debug, Clone, Copy)]
pub enum MeasurementQuantity {
    Value,
    Real,
    Imaginary,
    Magnitude,
    Phase,
}

#[derive(Debug, Clone)]
pub struct MeasurementTarget {
    pub positive: String,
    pub negative: Option<String>,
    pub branch_current: bool,
    pub quantity: MeasurementQuantity,
}

impl MeasurementTarget {
    pub fn references(&self, name: &str) -> bool {
        self.positive.eq_ignore_ascii_case(name)
            || self
                .negative
                .as_ref()
                .is_some_and(|negative| negative.eq_ignore_ascii_case(name))
    }
}

#[derive(Debug, Clone)]
pub enum MeasurementOperation {
    Find {
        at: Option<f64>,
        when: Option<MeasurementEvent>,
    },
    Min {
        from: Option<f64>,
        to: Option<f64>,
    },
    Max {
        from: Option<f64>,
        to: Option<f64>,
    },
    Average {
        from: Option<f64>,
        to: Option<f64>,
    },
    Rms {
        from: Option<f64>,
        to: Option<f64>,
    },
    Integral {
        from: Option<f64>,
        to: Option<f64>,
    },
    Derivative {
        at: Option<f64>,
        when: Option<MeasurementEvent>,
    },
    When {
        event: MeasurementEvent,
    },
    Delay {
        trigger: MeasurementTrigger,
        target: MeasurementEvent,
    },
    Parameter {
        expression: String,
    },
}

#[derive(Debug, Clone)]
pub enum MeasurementTrigger {
    Event(MeasurementEvent),
    At(f64),
}

#[derive(Debug, Clone, Copy)]
pub enum MeasurementEventDirection {
    Rise,
    Fall,
    Cross,
}

#[derive(Debug, Clone, Copy)]
pub enum MeasurementEventOccurrence {
    Index(usize),
    Last,
}

#[derive(Debug, Clone)]
pub struct MeasurementEvent {
    pub target: MeasurementTarget,
    pub value: f64,
    pub delay: Option<f64>,
    pub direction: MeasurementEventDirection,
    pub occurrence: MeasurementEventOccurrence,
}

#[derive(Debug, Clone)]
pub struct Measurement {
    pub analysis: String,
    pub name: String,
    pub target: Option<MeasurementTarget>,
    pub operation: MeasurementOperation,
}

impl Measurement {
    pub fn references(&self, name: &str) -> bool {
        if self
            .target
            .as_ref()
            .is_some_and(|target| target.references(name))
        {
            return true;
        }
        match &self.operation {
            MeasurementOperation::Find {
                when: Some(event), ..
            }
            | MeasurementOperation::Derivative {
                when: Some(event), ..
            }
            | MeasurementOperation::When { event } => event.target.references(name),
            MeasurementOperation::Delay { trigger, target } => {
                matches!(trigger, MeasurementTrigger::Event(event) if event.target.references(name))
                    || target.target.references(name)
            }
            _ => false,
        }
    }
}

#[derive(Debug, Clone, Copy)]
pub enum AcScale {
    Linear,
    Decade,
    Octave,
}

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub enum IntegrationMethod {
    #[default]
    Trap,
    Gear2,
}

#[derive(Debug, Clone)]
enum ParameterValue {
    Numeric(f64),
    String(String),
}

#[derive(Debug, Clone, Default)]
struct ParameterSet {
    numeric: HashMap<String, f64>,
    strings: HashMap<String, String>,
}

impl ParameterSet {
    fn evaluate(&self, text: &str) -> Result<ParameterValue> {
        let text = text.trim();
        if let Some(value) = self.strings.get(&text.to_ascii_lowercase()) {
            return Ok(ParameterValue::String(value.clone()));
        }
        if let Some(open) = text.find('(')
            && text[..open].trim().eq_ignore_ascii_case("str")
        {
            let close = text
                .rfind(')')
                .filter(|close| *close == text.len() - 1 && *close > open)
                .ok_or_else(|| {
                    Error::Parse(format!("invalid HSPICE string expression '{text}'"))
                })?;
            let argument = text[open + 1..close].trim();
            if argument.len() >= 2 {
                let first = argument.as_bytes()[0] as char;
                let last = argument.as_bytes()[argument.len() - 1] as char;
                if (first == '\'' || first == '"') && first == last {
                    return Ok(ParameterValue::String(
                        argument[1..argument.len() - 1].to_string(),
                    ));
                }
            }
            if let Some(value) = self.strings.get(&argument.to_ascii_lowercase()) {
                return Ok(ParameterValue::String(value.clone()));
            }
            return Err(Error::Parse(format!(
                "str() requires a quoted string or string parameter in '{text}'"
            )));
        }
        expression::evaluate(text, &self.numeric).map(ParameterValue::Numeric)
    }

    fn insert(&mut self, name: &str, value: ParameterValue) {
        let name = name.to_ascii_lowercase();
        match value {
            ParameterValue::Numeric(value) => {
                self.strings.remove(&name);
                self.numeric.insert(name, value);
            }
            ParameterValue::String(value) => {
                self.numeric.remove(&name);
                self.strings.insert(name, value);
            }
        }
    }

    fn assign(&mut self, name: &str, expression: &str) -> Result<()> {
        let value = self.evaluate(expression)?;
        self.insert(name, value);
        Ok(())
    }

    fn string(&self, name: &str) -> Option<&str> {
        self.strings
            .get(&name.to_ascii_lowercase())
            .map(String::as_str)
    }
}

impl Deref for ParameterSet {
    type Target = HashMap<String, f64>;

    fn deref(&self) -> &Self::Target {
        &self.numeric
    }
}

#[derive(Debug)]
pub struct Deck {
    pub nodes: Vec<String>,
    pub elements: Vec<Element>,
    pub analyses: Vec<Analysis>,
    pub unknown_count: usize,
    pub branch_names: Vec<(String, usize)>,
    pub integration_method: IntegrationMethod,
    pub relative_tolerance: f64,
    pub voltage_tolerance: f64,
    pub current_tolerance: f64,
    pub charge_tolerance: f64,
    pub truncation_tolerance: f64,
    pub probes: HashMap<String, Vec<String>>,
    pub parameters: HashMap<String, f64>,
    pub measurements: Vec<Measurement>,
    pub rfm_models: HashMap<String, RfmModel>,
}

impl Deck {
    pub fn parse_file(path: &Path, rfm_binding: Option<(&str, usize)>) -> Result<Self> {
        let path = path.canonicalize()?;
        let mut active = HashSet::new();
        let lines = expand_includes(&path, &mut active)?;
        let rfm_models = load_rfm_models(&lines)?;
        let rfm_model_ports = rfm_models
            .iter()
            .map(|(name, model)| (name.clone(), model.nports))
            .collect();
        let lines =
            flatten_subcircuits(lines, rfm_binding.map(|(name, _)| name), &rfm_model_ports)?;
        let mut deck = Self::parse(lines, rfm_binding, rfm_model_ports)?;
        deck.rfm_models = rfm_models;
        Ok(deck)
    }

    fn parse(
        lines: Vec<SourceLine>,
        rfm_binding: Option<(&str, usize)>,
        rfm_model_ports: HashMap<String, usize>,
    ) -> Result<Self> {
        let deck_source = lines.first().cloned();
        let mut parser = Parser {
            rfm_subcircuit: rfm_binding.map(|(name, _)| name.to_string()),
            rfm_nports: rfm_binding.map(|(_, nports)| nports),
            rfm_model_ports,
            relative_tolerance: 1e-3,
            voltage_tolerance: 1e-6,
            current_tolerance: 1e-12,
            charge_tolerance: 1e-14,
            truncation_tolerance: 7.0,
            minimum_resistance: HSPICE_DEFAULT_RESMIN,
            ..Parser::default()
        };
        for (line_index, line) in lines.iter().enumerate() {
            if line_index == 0 || line.text.is_empty() || line.text.starts_with('*') {
                continue;
            }
            parser.parse_line(line)?;
        }
        let result = parser.finish();
        match deck_source {
            Some(source) => source.wrap(result),
            None => result,
        }
    }
}

#[derive(Debug, Clone)]
struct SourceLine {
    path: PathBuf,
    line: usize,
    original: String,
    text: String,
}

impl SourceLine {
    fn new(path: &Path, line: usize, text: String) -> Self {
        Self {
            path: path.to_path_buf(),
            line,
            original: text.clone(),
            text,
        }
    }

    fn rewritten(&self, text: String) -> Self {
        Self {
            text,
            ..self.clone()
        }
    }

    fn locate(&self, error: Error) -> Error {
        error.at_source(&self.path, self.line, &self.original, &self.text)
    }

    fn wrap<T>(&self, result: Result<T>) -> Result<T> {
        result.map_err(|error| self.locate(error))
    }

    fn error(&self, message: impl Into<String>) -> Error {
        self.locate(Error::Parse(message.into()))
    }

    fn directory(&self) -> &Path {
        self.path.parent().unwrap_or_else(|| Path::new("."))
    }
}

fn expand_includes(path: &Path, active: &mut HashSet<PathBuf>) -> Result<Vec<SourceLine>> {
    let path = path.canonicalize()?;
    enter_dependency(&path, active)?;
    let text = fs::read_to_string(&path)?;
    let expanded = expand_dependency_lines(&path, logical_lines(&text, &path), active)?;
    active.remove(&path);
    Ok(expanded)
}

fn expand_dependency_lines(
    source: &Path,
    lines: Vec<SourceLine>,
    active: &mut HashSet<PathBuf>,
) -> Result<Vec<SourceLine>> {
    let mut expanded = Vec::new();
    for line in lines {
        let tokens = tokenize(&line.text);
        let include = tokens.first().is_some_and(|head| {
            head.eq_ignore_ascii_case(".inc") || head.eq_ignore_ascii_case(".include")
        });
        if include {
            let reference = tokens
                .get(1)
                .ok_or_else(|| line.error("include path is missing"))?
                .trim_matches(|character| character == '\'' || character == '"');
            let include_path = source
                .parent()
                .unwrap_or_else(|| Path::new("."))
                .join(reference);
            expanded.extend(line.wrap(expand_includes(&include_path, active))?);
        } else if tokens
            .first()
            .is_some_and(|head| head.eq_ignore_ascii_case(".lib"))
            && tokens.len() >= 3
        {
            let reference =
                tokens[1].trim_matches(|character| character == '\'' || character == '"');
            let library_path = source
                .parent()
                .unwrap_or_else(|| Path::new("."))
                .join(reference);
            expanded.extend(line.wrap(expand_library_section(
                &library_path,
                &tokens[2],
                active,
            ))?);
        } else {
            expanded.push(line);
        }
    }
    Ok(expanded)
}

fn expand_library_section(
    path: &Path,
    section: &str,
    active: &mut HashSet<PathBuf>,
) -> Result<Vec<SourceLine>> {
    let path = path.canonicalize()?;
    enter_dependency(&path, active)?;
    let text = fs::read_to_string(&path)?;
    let mut selected = Vec::new();
    let mut inside = false;
    let mut found = false;
    for line in logical_lines(&text, &path) {
        let values = tokenize(&line.text);
        if values
            .first()
            .is_some_and(|head| head.eq_ignore_ascii_case(".lib"))
            && values.len() == 2
        {
            if inside {
                active.remove(&path);
                return Err(line.error("nested .lib sections are not supported"));
            }
            inside = values[1].eq_ignore_ascii_case(section);
            found |= inside;
            continue;
        }
        if values
            .first()
            .is_some_and(|head| head.eq_ignore_ascii_case(".endl"))
        {
            if inside {
                break;
            }
            continue;
        }
        if inside {
            selected.push(line);
        }
    }
    if !found {
        active.remove(&path);
        return Err(Error::Parse(format!(
            "library section '{section}' was not found in '{}'",
            path.display()
        )));
    }
    let expanded = expand_dependency_lines(&path, selected, active)?;
    active.remove(&path);
    Ok(expanded)
}

fn enter_dependency(path: &Path, active: &mut HashSet<PathBuf>) -> Result<()> {
    if !active.insert(path.to_path_buf()) {
        return Err(Error::Parse(format!(
            "recursive include detected at '{}'",
            path.display()
        )));
    }
    Ok(())
}

fn load_rfm_models(lines: &[SourceLine]) -> Result<HashMap<String, RfmModel>> {
    let mut models = HashMap::new();
    for line in lines {
        let text = strip_hspice_comment(&line.text).trim();
        let tokens = tokenize(text);
        if tokens.len() < 3
            || !tokens[0].eq_ignore_ascii_case(".model")
            || !tokens[2].eq_ignore_ascii_case("s")
        {
            continue;
        }
        let name = tokens[1].to_ascii_lowercase();
        let mut rfm_file = None;
        let mut touchstone_file = None;
        let mut declared_ports = None;
        let mut rational_func_for_ac = false;
        let mut rational_func = false;
        for (option, value) in
            line.wrap(parse_assignments(&tokens[3..], ".model S option", false))?
        {
            match option.to_ascii_lowercase().as_str() {
                "rfmfile" => rfm_file = Some(value),
                "tstonefile" => touchstone_file = Some(value),
                "n" => {
                    let value = line.wrap(parse_number(&value, &HashMap::new()))?;
                    if value < 1.0 || value.fract() != 0.0 || value > usize::MAX as f64 {
                        return Err(line.error(".model S N must be a positive integer"));
                    }
                    declared_ports = Some(value as usize);
                }
                "rational_func_reuse" => {
                    let value = line.wrap(parse_number(&value, &HashMap::new()))?;
                    if value != 0.0 && value != 1.0 {
                        return Err(line.error(".model S RATIONAL_FUNC_REUSE must be 0 or 1"));
                    }
                }
                "rational_func_for_ac" => {
                    let value = line.wrap(parse_number(&value, &HashMap::new()))?;
                    if value != 0.0 && value != 1.0 {
                        return Err(line.error(".model S RATIONAL_FUNC_FOR_AC must be 0 or 1"));
                    }
                    rational_func_for_ac = value != 0.0;
                }
                "rational_func" => {
                    let value = line.wrap(parse_number(&value, &HashMap::new()))?;
                    if value != 0.0 && value != 1.0 {
                        return Err(line.error(".model S RATIONAL_FUNC must be 0 or 1"));
                    }
                    rational_func = value != 0.0;
                }
                _ => {
                    return Err(line.error(format!("unsupported .model S option '{option}'")));
                }
            }
        }
        if rfm_file.is_some() && touchstone_file.is_some() {
            return Err(line.error(format!(
                ".model '{}' cannot specify both RFMFILE and TSTONEFILE",
                tokens[1]
            )));
        }
        if rational_func_for_ac && !rational_func {
            return Err(line.error(".model S RATIONAL_FUNC_FOR_AC=1 requires RATIONAL_FUNC=1"));
        }
        let (file, is_touchstone) = if let Some(file) = rfm_file {
            (file, false)
        } else if let Some(file) = touchstone_file {
            (file, true)
        } else {
            return Err(line.error(format!(
                ".model '{}' requires RFMFILE or TSTONEFILE",
                tokens[1]
            )));
        };
        let file = line.wrap(resolve_string_value(&file, &ParameterSet::default()))?;
        let path = PathBuf::from(file);
        let path = if path.is_absolute() {
            path
        } else {
            let deck_relative = line.directory().join(&path);
            if deck_relative.is_file() {
                deck_relative
            } else if path.is_file() {
                path
            } else {
                deck_relative
            }
        };
        let model = if is_touchstone {
            if rational_func {
                logging::line(format_args!(
                    "[agent-spice-sim] fitting TSTONEFILE model {}: {}",
                    tokens[1],
                    path.display()
                ));
                line.wrap(RfmModel::fit_touchstone_file(&path, rational_func))?
            } else {
                logging::line(format_args!(
                    "[agent-spice-sim] loading direct-AC TSTONEFILE model {}: {}",
                    tokens[1],
                    path.display()
                ));
                line.wrap(RfmModel::load_touchstone_file(&path))?
            }
        } else {
            line.wrap(RfmModel::parse_file(&path))?
        };
        if declared_ports.is_some_and(|ports| ports != model.nports) {
            return Err(line.error(format!(
                ".model '{}' declares N={}, but model data has {} port(s)",
                tokens[1],
                declared_ports.expect("declared port count exists"),
                model.nports
            )));
        }
        if models.insert(name, model).is_some() {
            return Err(line.error(format!("duplicate .model definition '{}'", tokens[1])));
        }
    }
    Ok(models)
}

#[derive(Debug, Clone)]
struct Subcircuit {
    pins: Vec<String>,
    defaults: Vec<(String, String)>,
    body: Vec<SourceLine>,
    declaration: SourceLine,
}

struct Scope {
    path: String,
    pins: HashMap<String, String>,
    parameters: ParameterSet,
}

struct ConditionalFrame {
    parent_active: bool,
    branch_taken: bool,
    active: bool,
    else_seen: bool,
    opening: SourceLine,
}

#[derive(Default)]
struct ConditionalState {
    frames: Vec<ConditionalFrame>,
}

impl ConditionalState {
    fn is_active(&self) -> bool {
        self.frames.last().is_none_or(|frame| frame.active)
    }

    fn handle(
        &mut self,
        line: &SourceLine,
        tokens: &[String],
        parameters: &ParameterSet,
    ) -> Result<bool> {
        line.wrap(self.handle_inner(line, tokens, parameters))
    }

    fn handle_inner(
        &mut self,
        line: &SourceLine,
        tokens: &[String],
        parameters: &ParameterSet,
    ) -> Result<bool> {
        let Some(head) = tokens.first().map(|token| token.to_ascii_lowercase()) else {
            return Ok(false);
        };
        match head.as_str() {
            ".if" => {
                let parent_active = self.is_active();
                let condition =
                    parent_active && evaluate_condition(&line.text, &tokens[0], parameters)?;
                self.frames.push(ConditionalFrame {
                    parent_active,
                    branch_taken: condition,
                    active: condition,
                    else_seen: false,
                    opening: line.clone(),
                });
                Ok(true)
            }
            ".elseif" | ".elif" => {
                let frame = self
                    .frames
                    .last_mut()
                    .ok_or_else(|| Error::Parse(format!("{} has no matching .if", tokens[0])))?;
                if frame.else_seen {
                    return Err(Error::Parse(format!("{} cannot follow .else", tokens[0])));
                }
                let condition = frame.parent_active
                    && !frame.branch_taken
                    && evaluate_condition(&line.text, &tokens[0], parameters)?;
                frame.active = condition;
                frame.branch_taken |= condition;
                Ok(true)
            }
            ".else" => {
                let frame = self
                    .frames
                    .last_mut()
                    .ok_or_else(|| Error::Parse(".else has no matching .if".into()))?;
                if frame.else_seen {
                    return Err(Error::Parse("duplicate .else for the same .if".into()));
                }
                frame.else_seen = true;
                frame.active = frame.parent_active && !frame.branch_taken;
                frame.branch_taken = true;
                Ok(true)
            }
            ".endif" => {
                self.frames
                    .pop()
                    .ok_or_else(|| Error::Parse(".endif has no matching .if".into()))?;
                Ok(true)
            }
            _ => Ok(false),
        }
    }

    fn finish(&self, context: &str) -> Result<()> {
        if let Some(frame) = self.frames.last() {
            Err(frame
                .opening
                .error(format!("unterminated .if in {context}")))
        } else {
            Ok(())
        }
    }
}

fn evaluate_condition(line: &str, head: &str, parameters: &ParameterSet) -> Result<bool> {
    let condition = line[head.len()..].trim();
    if condition.is_empty() {
        return Err(Error::Parse(format!("{head} condition is missing")));
    }
    expression::evaluate(condition, parameters).map(|value| value != 0.0)
}

fn preprocess_top_level_conditionals(lines: Vec<SourceLine>) -> Result<Vec<SourceLine>> {
    if lines.is_empty() {
        return Ok(lines);
    }
    let mut output = vec![lines[0].clone()];
    let mut parameters = ParameterSet::default();
    let mut conditionals = ConditionalState::default();
    let mut subcircuit_selected = None;
    for line in lines.into_iter().skip(1) {
        let tokens = tokenize(&line.text);
        let head = tokens
            .first()
            .map(|token| token.to_ascii_lowercase())
            .unwrap_or_default();
        if let Some(selected) = subcircuit_selected {
            if selected {
                output.push(line);
            }
            if head == ".ends" {
                subcircuit_selected = None;
            }
            continue;
        }
        if head == ".subckt" {
            let selected = conditionals.is_active();
            subcircuit_selected = Some(selected);
            if selected {
                output.push(line);
            }
            continue;
        }
        if conditionals.handle(&line, &tokens, &parameters)? {
            continue;
        }
        if !conditionals.is_active() {
            continue;
        }
        if head == ".param" {
            line.wrap(update_parameters(&tokens[1..], &mut parameters))?;
        }
        output.push(line);
    }
    conditionals.finish("top-level netlist")?;
    Ok(output)
}

fn flatten_subcircuits(
    lines: Vec<SourceLine>,
    rfm_subcircuit: Option<&str>,
    rfm_model_ports: &HashMap<String, usize>,
) -> Result<Vec<SourceLine>> {
    let lines = preprocess_top_level_conditionals(lines)?;
    if lines.is_empty() {
        return Ok(Vec::new());
    }
    let mut definitions = HashMap::new();
    let mut top_level = vec![lines[0].clone()];
    let mut active: Option<(String, Subcircuit, bool)> = None;
    for line in lines.into_iter().skip(1) {
        let values = tokenize(&line.text);
        let head = values
            .first()
            .map(|value| value.to_ascii_lowercase())
            .unwrap_or_default();
        if head == ".subckt" {
            if active.is_some() {
                return Err(line.error("nested .subckt definitions are not supported"));
            }
            let name = values
                .get(1)
                .ok_or_else(|| line.error(".subckt name is missing"))?
                .clone();
            let parameter_start = (2..values.len())
                .find(|index| {
                    let value = &values[*index];
                    value.eq_ignore_ascii_case("params:")
                        || value.eq_ignore_ascii_case("params")
                        || value.contains('=')
                        || values
                            .get(*index + 1)
                            .is_some_and(|next| next == "=" || next.starts_with('='))
                })
                .unwrap_or(values.len());
            let pins = values[2..parameter_start].to_vec();
            let defaults = line
                .wrap(parse_assignments(
                    &values[parameter_start..],
                    ".subckt parameter declaration",
                    true,
                ))?
                .into_iter()
                .map(|(parameter, default)| (parameter.to_ascii_lowercase(), default))
                .collect();
            let ignored = rfm_subcircuit.is_some_and(|rfm| name.eq_ignore_ascii_case(rfm));
            active = Some((
                name,
                Subcircuit {
                    pins,
                    defaults,
                    body: Vec::new(),
                    declaration: line.clone(),
                },
                ignored,
            ));
            continue;
        }
        if head == ".ends" {
            let (name, definition, ignored) = active
                .take()
                .ok_or_else(|| line.error(".ends has no matching .subckt"))?;
            if !ignored
                && definitions
                    .insert(name.to_ascii_lowercase(), definition)
                    .is_some()
            {
                return Err(line.error(format!("duplicate subcircuit definition '{name}'")));
            }
            continue;
        }
        if let Some((_, definition, _)) = active.as_mut() {
            definition.body.push(line);
        } else {
            top_level.push(line);
        }
    }
    if let Some((name, definition, _)) = active {
        return Err(definition
            .declaration
            .error(format!("subcircuit '{name}' has no matching .ends")));
    }
    let mut global_nodes = HashSet::new();
    for line in &top_level {
        let values = tokenize(&line.text);
        if values
            .first()
            .is_some_and(|value| value.eq_ignore_ascii_case(".global"))
        {
            global_nodes.extend(values[1..].iter().map(|value| value.to_ascii_lowercase()));
        }
    }
    let mut flattener = Flattener {
        definitions: &definitions,
        global_nodes: &global_nodes,
        rfm_subcircuit,
        rfm_model_ports,
        active: Vec::new(),
    };
    let mut output = vec![top_level[0].clone()];
    let mut top_parameters = ParameterSet::default();
    for line in top_level.iter().skip(1) {
        let values = tokenize(&line.text);
        if values
            .first()
            .is_some_and(|value| value.eq_ignore_ascii_case(".param"))
        {
            line.wrap(update_parameters(&values[1..], &mut top_parameters))?;
        }
    }
    for line in top_level.into_iter().skip(1) {
        let values = tokenize(&line.text);
        if values.is_empty() {
            continue;
        }
        if values[0].eq_ignore_ascii_case(".global") {
            continue;
        }
        if values[0].eq_ignore_ascii_case(".param") {
            output.push(line);
            continue;
        }
        let scope = Scope {
            path: String::new(),
            pins: HashMap::new(),
            parameters: top_parameters.clone(),
        };
        flattener.expand_line(&line, &scope, &mut output)?;
    }
    Ok(output)
}

struct Flattener<'a> {
    definitions: &'a HashMap<String, Subcircuit>,
    global_nodes: &'a HashSet<String>,
    rfm_subcircuit: Option<&'a str>,
    rfm_model_ports: &'a HashMap<String, usize>,
    active: Vec<String>,
}

impl Flattener<'_> {
    fn expand_line(
        &mut self,
        line: &SourceLine,
        scope: &Scope,
        output: &mut Vec<SourceLine>,
    ) -> Result<()> {
        line.wrap(self.expand_line_inner(line, scope, output))
    }

    fn expand_line_inner(
        &mut self,
        line: &SourceLine,
        scope: &Scope,
        output: &mut Vec<SourceLine>,
    ) -> Result<()> {
        let substituted = substitute_braced_expressions(&line.text, &scope.parameters)?;
        let mut values = tokenize(&substituted);
        let parameter_start = values.first().map_or(values.len(), |head| {
            if head.starts_with('.') {
                1
            } else {
                match head.as_bytes()[0].to_ascii_uppercase() {
                    b'R' | b'C' | b'L' | b'V' | b'I' => 3,
                    b'E' | b'G' => 5,
                    b'F' | b'H' => 4,
                    _ => values.len(),
                }
            }
        });
        for index in parameter_start..values.len() {
            let is_assignment_name = values
                .get(index + 1)
                .is_some_and(|next| next == "=" || next.starts_with('='));
            if is_assignment_name {
                continue;
            }
            let value = &mut values[index];
            let quoted_expression = value.len() >= 2
                && ((value.starts_with('\'') && value.ends_with('\''))
                    || (value.starts_with('"') && value.ends_with('"')));
            if quoted_expression {
                let inner = &value[1..value.len() - 1];
                if let Some(parameter) = scope.parameters.string(inner) {
                    *value = quote_parameter_string(parameter);
                } else if let Ok(parameter) = expression::evaluate(value, &scope.parameters) {
                    *value = format!("{parameter:.17e}");
                }
            } else if let Some(parameter) = substitute_parameter_token(value, &scope.parameters) {
                *value = parameter;
            }
        }
        if values.is_empty() || values[0].starts_with('*') {
            return Ok(());
        }
        if values[0].starts_with('.') {
            output.push(line.rewritten(values.join(" ")));
            return Ok(());
        }
        let kind = values[0].as_bytes()[0].to_ascii_uppercase();
        if kind == b'X' {
            return self.expand_instance(&values, line, scope, output);
        }
        if !scope.path.is_empty() {
            values[0] = qualify_element(&scope.path, &values[0]);
        }
        if kind == b'S' {
            let (model, node_end) = parse_s_instance_model(&values)?;
            if !self.rfm_model_ports.contains_key(&model) {
                return Err(Error::Parse(format!(
                    "S-parameter model '{model}' was not found"
                )));
            }
            for value in &mut values[1..node_end] {
                *value = self.map_node(value, scope);
            }
        } else {
            let node_indices: &[usize] = match kind {
                b'R' | b'C' | b'L' | b'V' | b'I' | b'F' | b'H' => &[1, 2],
                b'E' | b'G' => &[1, 2, 3, 4],
                _ => &[],
            };
            for index in node_indices {
                if *index < values.len() {
                    values[*index] = self.map_node(&values[*index], scope);
                }
            }
        }
        if matches!(kind, b'F' | b'H') && !scope.path.is_empty() && values.len() > 3 {
            values[3] = qualify_element(&scope.path, &values[3]);
        }
        output.push(line.rewritten(values.join(" ")));
        Ok(())
    }

    fn expand_instance(
        &mut self,
        values: &[String],
        line: &SourceLine,
        scope: &Scope,
        output: &mut Vec<SourceLine>,
    ) -> Result<()> {
        if self.rfm_subcircuit.is_some_and(|rfm| {
            values
                .last()
                .is_some_and(|model| model.eq_ignore_ascii_case(rfm))
        }) {
            let mut rewritten = values.to_vec();
            if !scope.path.is_empty() {
                rewritten[0] = qualify_element(&scope.path, &rewritten[0]);
            }
            let node_end = rewritten.len() - 1;
            for value in &mut rewritten[1..node_end] {
                *value = self.map_node(value, scope);
            }
            output.push(line.rewritten(rewritten.join(" ")));
            return Ok(());
        }
        let definition_index = (1..values.len())
            .rev()
            .find(|index| {
                !values[*index].contains('=')
                    && self
                        .definitions
                        .contains_key(&values[*index].to_ascii_lowercase())
            })
            .ok_or_else(|| {
                Error::Parse(format!(
                    "subcircuit '{}' was not found",
                    values.last().map_or("", String::as_str)
                ))
            })?;
        let definition_name = values[definition_index].to_ascii_lowercase();
        if self.active.contains(&definition_name) {
            return Err(Error::Parse(format!(
                "recursive subcircuit expansion detected at '{}'",
                values[definition_index]
            )));
        }
        let definition = self.definitions[&definition_name].clone();
        let actual_nodes = &values[1..definition_index];
        if actual_nodes.len() != definition.pins.len() {
            return Err(Error::Parse(format!(
                "instance '{}' supplies {} node(s), but '{}' requires {}",
                values[0],
                actual_nodes.len(),
                values[definition_index],
                definition.pins.len()
            )));
        }
        let path = if scope.path.is_empty() {
            values[0].clone()
        } else {
            qualify(&scope.path, &values[0])
        };
        let pins = definition
            .pins
            .iter()
            .zip(actual_nodes)
            .map(|(pin, node)| (pin.to_ascii_lowercase(), self.map_node(node, scope)))
            .collect();
        let mut parameters = scope.parameters.clone();
        for (name, default) in &definition.defaults {
            let value = definition.declaration.wrap(parameters.evaluate(default))?;
            parameters.insert(name, value);
        }
        for (name, value) in parse_assignments(
            &values[definition_index + 1..],
            "instance parameter override",
            true,
        )? {
            let value = scope.parameters.evaluate(&value)?;
            parameters.insert(&name, value);
        }
        let mut child = Scope {
            path,
            pins,
            parameters,
        };
        self.active.push(definition_name);
        let mut conditionals = ConditionalState::default();
        let mut active_lines = Vec::new();
        for line in &definition.body {
            let body_values = tokenize(&line.text);
            if conditionals.handle(line, &body_values, &child.parameters)? {
                continue;
            }
            if !conditionals.is_active() {
                continue;
            }
            if body_values
                .first()
                .is_some_and(|value| value.eq_ignore_ascii_case(".param"))
            {
                let assignments: Vec<String> = line.wrap(
                    body_values[1..]
                        .iter()
                        .map(|value| substitute_braced_expressions(value, &child.parameters))
                        .collect::<Result<_>>(),
                )?;
                line.wrap(update_parameters(&assignments, &mut child.parameters))?;
                continue;
            }
            active_lines.push(line);
        }
        conditionals.finish(&format!("subcircuit '{}'", values[definition_index]))?;
        for line in active_lines {
            self.expand_line(line, &child, output)?;
        }
        self.active.pop();
        Ok(())
    }

    fn map_node(&self, node: &str, scope: &Scope) -> String {
        if node == "0"
            || node.eq_ignore_ascii_case("gnd")
            || self.global_nodes.contains(&node.to_ascii_lowercase())
        {
            return node.to_string();
        }
        if let Some(actual) = scope.pins.get(&node.to_ascii_lowercase()) {
            return actual.clone();
        }
        if scope.path.is_empty() {
            node.to_string()
        } else {
            qualify(&scope.path, node)
        }
    }
}

fn parse_assignments(
    tokens: &[String],
    context: &str,
    allow_params_marker: bool,
) -> Result<Vec<(String, String)>> {
    let invalid = |token: &str| Error::Parse(format!("invalid {context} '{token}'"));
    let mut assignments = Vec::new();
    let mut index = 0usize;
    while index < tokens.len() {
        let token = &tokens[index];
        if allow_params_marker
            && (token.eq_ignore_ascii_case("params:") || token.eq_ignore_ascii_case("params"))
        {
            index += 1;
            continue;
        }
        let (name, value, consumed) = if let Some((name, value)) = token.split_once('=') {
            if value.is_empty() {
                let value = tokens.get(index + 1).ok_or_else(|| invalid(token))?;
                (name, value.as_str(), 2)
            } else {
                (name, value, 1)
            }
        } else if tokens.get(index + 1).is_some_and(|next| next == "=") {
            let value = tokens.get(index + 2).ok_or_else(|| invalid(token))?;
            (token.as_str(), value.as_str(), 3)
        } else if let Some(value) = tokens
            .get(index + 1)
            .and_then(|next| next.strip_prefix('='))
            .filter(|value| !value.is_empty())
        {
            (token.as_str(), value, 2)
        } else {
            return Err(invalid(token));
        };
        if name.is_empty() || value.is_empty() || value == "=" {
            return Err(invalid(token));
        }
        assignments.push((name.to_string(), value.to_string()));
        index += consumed;
    }
    Ok(assignments)
}

fn parse_s_instance_model(tokens: &[String]) -> Result<(String, usize)> {
    let option_start = (1..tokens.len())
        .find(|index| {
            tokens[*index].eq_ignore_ascii_case("mname")
                || tokens[*index]
                    .split_once('=')
                    .is_some_and(|(name, _)| name.eq_ignore_ascii_case("mname"))
        })
        .ok_or_else(|| Error::Parse("S-parameter instance requires MNAME=<model>".into()))?;
    let assignments = parse_assignments(
        &tokens[option_start..],
        "S-parameter instance option",
        false,
    )?;
    if assignments.len() != 1 || !assignments[0].0.eq_ignore_ascii_case("mname") {
        return Err(Error::Parse(
            "S-parameter instance supports only MNAME=<model>".into(),
        ));
    }
    Ok((assignments[0].1.to_ascii_lowercase(), option_start))
}

fn update_parameters(tokens: &[String], parameters: &mut ParameterSet) -> Result<()> {
    for (name, expression_text) in parse_assignments(tokens, ".param assignment", false)? {
        parameters.assign(&name, &expression_text)?;
    }
    Ok(())
}

fn substitute_braced_expressions(line: &str, parameters: &ParameterSet) -> Result<String> {
    let mut output = String::with_capacity(line.len());
    let mut cursor = 0usize;
    while let Some(relative_start) = line[cursor..].find('{') {
        let start = cursor + relative_start;
        output.push_str(&line[cursor..start]);
        let mut depth = 0usize;
        let mut end = None;
        for (offset, character) in line[start..].char_indices() {
            if character == '{' {
                depth += 1;
            } else if character == '}' {
                depth -= 1;
                if depth == 0 {
                    end = Some(start + offset);
                    break;
                }
            }
        }
        let end = end.ok_or_else(|| Error::Parse(format!("unclosed '{{' in '{line}'")))?;
        let expression_text = line[start + 1..end].trim();
        if let Some(value) = parameters.string(expression_text) {
            output.push_str(&quote_parameter_string(value));
        } else {
            let value = expression::evaluate(expression_text, parameters)?;
            output.push_str(&format!("{value:.17e}"));
        }
        cursor = end + 1;
    }
    output.push_str(&line[cursor..]);
    Ok(output)
}

fn substitute_parameter_token(token: &str, parameters: &ParameterSet) -> Option<String> {
    if let Some(value) = parameters.get(&token.to_ascii_lowercase()) {
        return Some(format!("{value:.17e}"));
    }
    if let Some(value) = parameters.string(token) {
        return Some(quote_parameter_string(value));
    }
    let (prefix, value) = token.split_once('=')?;
    match parameters.evaluate(value).ok()? {
        ParameterValue::Numeric(parameter) => Some(format!("{prefix}={parameter:.17e}")),
        ParameterValue::String(parameter) => {
            Some(format!("{prefix}={}", quote_parameter_string(&parameter)))
        }
    }
}

fn quote_parameter_string(value: &str) -> String {
    if value.contains('\'') && !value.contains('"') {
        format!("\"{value}\"")
    } else {
        format!("'{value}'")
    }
}

fn qualify(path: &str, name: &str) -> String {
    format!("{path}:{name}")
}

fn qualify_element(path: &str, name: &str) -> String {
    format!("{name}:{path}")
}

#[derive(Default)]
struct Parser {
    nodes: Vec<String>,
    node_lookup: HashMap<String, usize>,
    elements: Vec<PendingElement>,
    element_sources: Vec<SourceLine>,
    analyses: Vec<Analysis>,
    parameters: ParameterSet,
    rfm_subcircuit: Option<String>,
    rfm_nports: Option<usize>,
    rfm_model_ports: HashMap<String, usize>,
    skipping_rfm_wrapper: bool,
    integration_method: IntegrationMethod,
    relative_tolerance: f64,
    voltage_tolerance: f64,
    current_tolerance: f64,
    charge_tolerance: f64,
    truncation_tolerance: f64,
    minimum_resistance: f64,
    probes: HashMap<String, Vec<String>>,
    measurements: Vec<Measurement>,
}

enum PendingElement {
    Resistor(String, Node, Node, f64),
    Capacitor(String, Node, Node, f64),
    Inductor(String, Node, Node, f64),
    Voltage(String, Node, Node, Source),
    Current(String, Node, Node, Source),
    Vcvs(String, Node, Node, Node, Node, f64),
    Vccs(String, Node, Node, Node, Node, f64),
    Cccs(String, Node, Node, String, f64),
    Ccvs(String, Node, Node, String, f64),
    Rfm(String, Vec<Node>, Vec<Node>, Option<String>),
}

impl Parser {
    fn parse_line(&mut self, source: &SourceLine) -> Result<()> {
        let previous_elements = self.elements.len();
        let result = self.parse_line_inner(&source.text, source.directory());
        if result.is_ok() {
            self.element_sources.extend(std::iter::repeat_n(
                source.clone(),
                self.elements.len() - previous_elements,
            ));
        }
        source.wrap(result)
    }

    fn parse_line_inner(&mut self, line: &str, source_directory: &Path) -> Result<()> {
        let line = strip_hspice_comment(line).trim();
        if line.is_empty() {
            return Ok(());
        }
        let tokens = tokenize(line);
        if tokens.is_empty() {
            return Ok(());
        }
        let head = tokens[0].to_ascii_lowercase();
        if self.skipping_rfm_wrapper {
            if head == ".ends" {
                self.skipping_rfm_wrapper = false;
            }
            return Ok(());
        }
        if head == ".subckt"
            && tokens.get(1).is_some_and(|name| {
                self.rfm_subcircuit
                    .as_ref()
                    .is_some_and(|rfm| name.eq_ignore_ascii_case(rfm))
            })
        {
            self.skipping_rfm_wrapper = true;
            return Ok(());
        }
        if head.starts_with('.') {
            return self.parse_directive(&head, &tokens[1..]);
        }
        if tokens.len() < 4 {
            return Err(Error::Parse(format!("invalid element line '{line}'")));
        }
        let name = tokens[0].clone();
        let positive = self.node(&tokens[1]);
        let negative = self.node(&tokens[2]);
        let kind = name.as_bytes()[0].to_ascii_uppercase();
        match kind {
            b'R' => {
                let value = parse_passive_value(&tokens[3..], "r", &self.parameters)?;
                if value < 0.0 {
                    return Err(Error::Parse(format!(
                        "resistance must be non-negative on '{name}'"
                    )));
                }
                let value = value.max(self.minimum_resistance);
                self.elements
                    .push(PendingElement::Resistor(name, positive, negative, value));
            }
            b'C' => {
                let value = parse_passive_value(&tokens[3..], "c", &self.parameters)?;
                if value <= 0.0 {
                    return Err(Error::Parse(format!(
                        "capacitance must be positive on '{name}'"
                    )));
                }
                self.elements
                    .push(PendingElement::Capacitor(name, positive, negative, value));
            }
            b'L' => {
                let value = parse_passive_value(&tokens[3..], "l", &self.parameters)?;
                if value <= 0.0 {
                    return Err(Error::Parse(format!(
                        "inductance must be positive on '{name}'"
                    )));
                }
                self.elements
                    .push(PendingElement::Inductor(name, positive, negative, value));
            }
            b'V' => {
                let source = parse_source(&tokens[3..], &self.parameters, source_directory)?;
                self.elements
                    .push(PendingElement::Voltage(name, positive, negative, source));
            }
            b'I' => {
                let source = parse_source(&tokens[3..], &self.parameters, source_directory)?;
                self.elements
                    .push(PendingElement::Current(name, positive, negative, source));
            }
            b'E' | b'G' => {
                if tokens.len() < 6 {
                    return Err(Error::Parse(format!(
                        "{} source '{name}' requires two control nodes and a gain",
                        kind as char
                    )));
                }
                let control_positive = self.node(&tokens[3]);
                let control_negative = self.node(&tokens[4]);
                let gain = parse_number(&tokens[5], &self.parameters)?;
                let element = if kind == b'E' {
                    PendingElement::Vcvs(
                        name,
                        positive,
                        negative,
                        control_positive,
                        control_negative,
                        gain,
                    )
                } else {
                    PendingElement::Vccs(
                        name,
                        positive,
                        negative,
                        control_positive,
                        control_negative,
                        gain,
                    )
                };
                self.elements.push(element);
            }
            b'F' | b'H' => {
                if tokens.len() < 5 {
                    return Err(Error::Parse(format!(
                        "{} source '{name}' requires a controlling branch and gain",
                        kind as char
                    )));
                }
                let control = tokens[3].clone();
                let gain = parse_number(&tokens[4], &self.parameters)?;
                let element = if kind == b'F' {
                    PendingElement::Cccs(name, positive, negative, control, gain)
                } else {
                    PendingElement::Ccvs(name, positive, negative, control, gain)
                };
                self.elements.push(element);
            }
            b'S' => {
                let (model, node_end) = parse_s_instance_model(&tokens)?;
                let nports = self.rfm_model_ports.get(&model).copied().ok_or_else(|| {
                    Error::Parse(format!(
                        "S-parameter model '{model}' was not found for '{name}'"
                    ))
                })?;
                let node_tokens = &tokens[1..node_end];
                let (ports, references) = if node_tokens.len() == nports * 2 {
                    let mut ports = Vec::with_capacity(nports);
                    let mut references = Vec::with_capacity(nports);
                    for pair in node_tokens.chunks_exact(2) {
                        ports.push(self.node(&pair[0]));
                        references.push(self.node(&pair[1]));
                    }
                    (ports, references)
                } else if node_tokens.len() == nports + 1 {
                    let ports = node_tokens[..nports]
                        .iter()
                        .map(|token| self.node(token))
                        .collect();
                    let reference = self.node(&node_tokens[nports]);
                    (ports, vec![reference; nports])
                } else {
                    return Err(Error::Parse(format!(
                        "S-parameter instance '{name}' requires either {nports} positive/negative node pair(s), or {nports} port nodes plus one common reference, before MNAME"
                    )));
                };
                self.elements
                    .push(PendingElement::Rfm(name, ports, references, Some(model)));
            }
            b'X' => {
                let subcircuit = self.rfm_subcircuit.as_ref().ok_or_else(|| {
                    Error::Parse(format!(
                        "unsupported subcircuit instance '{name}'; pass --rfm for an RFM instance"
                    ))
                })?;
                let nports = self.rfm_nports.expect("RFM binding includes a port count");
                let expected = nports + 3;
                if tokens.len() != expected
                    || !tokens[expected - 1].eq_ignore_ascii_case(subcircuit)
                {
                    return Err(Error::Parse(format!(
                        "RFM instance '{name}' requires {nports} port node(s), one reference node, and model '{subcircuit}'"
                    )));
                }
                let ports = tokens[1..=nports]
                    .iter()
                    .map(|token| self.node(token))
                    .collect();
                let reference = self.node(&tokens[nports + 1]);
                self.elements.push(PendingElement::Rfm(
                    name,
                    ports,
                    vec![reference; nports],
                    None,
                ));
            }
            kind => {
                return Err(Error::Parse(format!(
                    "unsupported element '{}' on line '{line}'",
                    kind as char
                )));
            }
        }
        Ok(())
    }

    fn parse_directive(&mut self, head: &str, tokens: &[String]) -> Result<()> {
        match head {
            ".param" => {
                update_parameters(tokens, &mut self.parameters)?;
            }
            ".op" => self.analyses.push(Analysis::Op),
            ".dc" => {
                if tokens.len() < 4 {
                    return Err(Error::Parse(".dc requires source start stop step".into()));
                }
                let start = parse_number(&tokens[1], &self.parameters)?;
                let stop = parse_number(&tokens[2], &self.parameters)?;
                let step = parse_number(&tokens[3], &self.parameters)?;
                if step == 0.0 || (stop - start).signum() != step.signum() {
                    return Err(Error::Parse(".dc step must move toward stop".into()));
                }
                self.analyses.push(Analysis::Dc {
                    source: tokens[0].clone(),
                    start,
                    stop,
                    step,
                });
            }
            ".ac" => {
                if tokens.len() < 4 {
                    return Err(Error::Parse(".ac requires scale points start stop".into()));
                }
                let scale = match tokens[0].to_ascii_lowercase().as_str() {
                    "lin" => AcScale::Linear,
                    "dec" => AcScale::Decade,
                    "oct" => AcScale::Octave,
                    value => return Err(Error::Parse(format!("unsupported .ac scale '{value}'"))),
                };
                let points = tokens[1].parse::<usize>().map_err(|_| {
                    Error::Parse(format!("invalid .ac point count '{}'", tokens[1]))
                })?;
                let start = parse_number(&tokens[2], &self.parameters)?;
                let stop = parse_number(&tokens[3], &self.parameters)?;
                if points == 0 || start <= 0.0 || stop < start {
                    return Err(Error::Parse("invalid .ac range".into()));
                }
                self.analyses.push(Analysis::Ac {
                    scale,
                    points,
                    start,
                    stop,
                });
            }
            ".tran" => {
                if tokens.len() < 2 {
                    return Err(Error::Parse(".tran requires step and stop".into()));
                }
                let step = parse_number(&tokens[0], &self.parameters)?;
                let stop = parse_number(&tokens[1], &self.parameters)?;
                if step <= 0.0 || stop <= 0.0 {
                    return Err(Error::Parse(".tran step and stop must be positive".into()));
                }
                self.analyses.push(Analysis::Tran { step, stop });
            }
            ".option" | ".options" => {
                for token in tokens {
                    let Some((name, value)) = token.split_once('=') else {
                        continue;
                    };
                    if name.eq_ignore_ascii_case("method") {
                        self.integration_method = match value.to_ascii_lowercase().as_str() {
                            "trap" | "trapezoidal" => IntegrationMethod::Trap,
                            "gear" | "gear2" | "bdf2" => IntegrationMethod::Gear2,
                            method => {
                                return Err(Error::Parse(format!(
                                    "unsupported transient integration method '{method}'"
                                )));
                            }
                        };
                        continue;
                    }
                    let value = parse_number(value, &self.parameters)?;
                    if value <= 0.0 || !value.is_finite() {
                        return Err(Error::Parse(format!(".options {name} must be positive")));
                    }
                    match name.to_ascii_lowercase().as_str() {
                        "reltol" => self.relative_tolerance = value,
                        "vntol" | "vabstol" => self.voltage_tolerance = value,
                        "abstol" | "iabstol" => self.current_tolerance = value,
                        "chgtol" => self.charge_tolerance = value,
                        "trtol" => self.truncation_tolerance = value,
                        "resmin" => self.minimum_resistance = value,
                        _ => {}
                    }
                }
            }
            ".model" => {
                if tokens.len() < 2 || !tokens[1].eq_ignore_ascii_case("s") {
                    return Err(Error::Parse("only .model <name> S is supported".into()));
                }
                if !self
                    .rfm_model_ports
                    .contains_key(&tokens[0].to_ascii_lowercase())
                {
                    return Err(Error::Parse(format!(
                        ".model '{}' requires a valid RFMFILE",
                        tokens[0]
                    )));
                }
            }
            ".print" | ".probe" => self.parse_probes(tokens),
            ".measure" | ".meas" => self.parse_measurement(tokens)?,
            ".end" | ".global" | ".temp" => {}
            _ => return Err(Error::Parse(format!("unsupported directive '{head}'"))),
        }
        Ok(())
    }

    fn node(&mut self, token: &str) -> Node {
        if token == "0" || token.eq_ignore_ascii_case("gnd") {
            return None;
        }
        let key = token.to_ascii_lowercase();
        if let Some(index) = self.node_lookup.get(&key) {
            return Some(*index);
        }
        let index = self.nodes.len();
        self.nodes.push(token.to_string());
        self.node_lookup.insert(key, index);
        Some(index)
    }

    fn parse_probes(&mut self, tokens: &[String]) {
        let Some(analysis) = tokens.first() else {
            return;
        };
        let analysis = analysis.to_ascii_lowercase();
        if !matches!(analysis.as_str(), "op" | "dc" | "ac" | "tran") {
            return;
        }
        let probes = self.probes.entry(analysis).or_default();
        for token in &tokens[1..] {
            let Some(name) = probe_name(token) else {
                continue;
            };
            if !probes
                .iter()
                .any(|existing| existing.eq_ignore_ascii_case(&name))
            {
                probes.push(name);
            }
        }
    }

    fn parse_measurement(&mut self, tokens: &[String]) -> Result<()> {
        if tokens.len() < 3 {
            return Err(Error::Parse(
                ".measure requires analysis, name, and operation".into(),
            ));
        }
        let analysis = tokens[0].to_ascii_lowercase();
        if !matches!(analysis.as_str(), "op" | "dc" | "ac" | "tran") {
            return Err(Error::Parse(format!(
                "unsupported .measure analysis '{}'",
                tokens[0]
            )));
        }
        let name = tokens[1].clone();
        if self
            .measurements
            .iter()
            .any(|measurement| measurement.name.eq_ignore_ascii_case(&name))
        {
            return Err(Error::Parse(format!("duplicate .measure name '{name}'")));
        }
        let mut operation = tokens[2].to_ascii_lowercase();
        let mut inline_parameter = None;
        if let Some((candidate, expression)) = tokens[2].split_once('=')
            && candidate.eq_ignore_ascii_case("param")
        {
            operation = "param".into();
            inline_parameter = Some(expression.to_string());
        }
        if operation != "param" && tokens.len() < 4 {
            return Err(Error::Parse(format!(
                ".measure '{name}' operation '{}' requires a target",
                tokens[2]
            )));
        }
        let (target, operation) = match operation.as_str() {
            "param" => {
                let expression = if let Some(expression) = inline_parameter {
                    if expression.is_empty() || tokens.len() != 3 {
                        return Err(Error::Parse(format!(
                            "invalid .measure '{name}' PARAM expression"
                        )));
                    }
                    expression
                } else {
                    parse_measurement_parameter_expression(&tokens[3..], &name)?
                };
                (None, MeasurementOperation::Parameter { expression })
            }
            "find" => {
                let target = parse_measurement_target(&tokens[3])?;
                let at = measurement_option(tokens, "at", &self.parameters)?;
                let when_index = tokens
                    .iter()
                    .position(|token| token.eq_ignore_ascii_case("when"));
                let when = when_index
                    .map(|index| parse_measurement_event(&tokens[index + 1..], &self.parameters))
                    .transpose()?;
                if at.is_some() && when.is_some() {
                    return Err(Error::Parse(format!(
                        ".measure '{name}' FIND cannot use both AT and WHEN"
                    )));
                }
                (Some(target), MeasurementOperation::Find { at, when })
            }
            "deriv" | "derivative" => {
                let target = parse_measurement_target(&tokens[3])?;
                let at = measurement_option(tokens, "at", &self.parameters)?;
                let when_index = tokens
                    .iter()
                    .position(|token| token.eq_ignore_ascii_case("when"));
                let when = when_index
                    .map(|index| parse_measurement_event(&tokens[index + 1..], &self.parameters))
                    .transpose()?;
                if at.is_some() && when.is_some() {
                    return Err(Error::Parse(format!(
                        ".measure '{name}' DERIV cannot use both AT and WHEN"
                    )));
                }
                (Some(target), MeasurementOperation::Derivative { at, when })
            }
            "min" | "max" | "avg" | "average" | "rms" | "integ" | "integral" => {
                let target = parse_measurement_target(&tokens[3])?;
                let from = measurement_option(tokens, "from", &self.parameters)?;
                let to = measurement_option(tokens, "to", &self.parameters)?;
                let operation = match operation.as_str() {
                    "min" => MeasurementOperation::Min { from, to },
                    "max" => MeasurementOperation::Max { from, to },
                    "avg" | "average" => MeasurementOperation::Average { from, to },
                    "rms" => MeasurementOperation::Rms { from, to },
                    "integ" | "integral" => MeasurementOperation::Integral { from, to },
                    _ => unreachable!(),
                };
                (Some(target), operation)
            }
            "when" => {
                let event = parse_measurement_event(&tokens[3..], &self.parameters)?;
                (
                    Some(event.target.clone()),
                    MeasurementOperation::When { event },
                )
            }
            "trig" => {
                let target_index = tokens
                    .iter()
                    .enumerate()
                    .skip(4)
                    .find(|(_, token)| token.eq_ignore_ascii_case("targ"))
                    .map(|(index, _)| index)
                    .ok_or_else(|| {
                        Error::Parse(format!(".measure '{name}' TRIG requires a TARG event"))
                    })?;
                let trigger =
                    parse_measurement_trigger(&tokens[3..target_index], &self.parameters)?;
                let target =
                    parse_measurement_event(&tokens[target_index + 1..], &self.parameters)?;
                let measurement_target = match &trigger {
                    MeasurementTrigger::Event(event) => event.target.clone(),
                    MeasurementTrigger::At(_) => target.target.clone(),
                };
                (
                    Some(measurement_target),
                    MeasurementOperation::Delay { trigger, target },
                )
            }
            _ => {
                return Err(Error::Parse(format!(
                    "unsupported .measure operation '{}'",
                    tokens[2]
                )));
            }
        };
        self.measurements.push(Measurement {
            analysis,
            name,
            target,
            operation,
        });
        Ok(())
    }

    fn finish(self) -> Result<Deck> {
        if self.analyses.is_empty() {
            return Err(Error::Parse(
                "deck has no OP, DC, AC, or TRAN analysis".into(),
            ));
        }
        let mut next_branch = self.nodes.len();
        let mut branch_names = Vec::new();
        let mut branch_by_element = HashMap::new();
        let mut branch_by_name = HashMap::new();
        for (index, pending) in self.elements.iter().enumerate() {
            let name = match pending {
                PendingElement::Inductor(name, ..)
                | PendingElement::Voltage(name, ..)
                | PendingElement::Vcvs(name, ..)
                | PendingElement::Ccvs(name, ..) => Some(name),
                _ => None,
            };
            if let Some(name) = name {
                let branch = next_branch;
                next_branch += 1;
                branch_names.push((name.clone(), branch));
                branch_by_element.insert(index, branch);
                branch_by_name.insert(name.to_ascii_lowercase(), branch);
            }
        }
        let mut elements = Vec::with_capacity(self.elements.len());
        let element_sources = self.element_sources;
        for (index, pending) in self.elements.into_iter().enumerate() {
            let element = match pending {
                PendingElement::Resistor(name, positive, negative, resistance) => {
                    Element::Resistor {
                        name,
                        positive,
                        negative,
                        resistance,
                    }
                }
                PendingElement::Capacitor(name, positive, negative, capacitance) => {
                    Element::Capacitor {
                        name,
                        positive,
                        negative,
                        capacitance,
                    }
                }
                PendingElement::Inductor(name, positive, negative, inductance) => {
                    Element::Inductor {
                        name,
                        positive,
                        negative,
                        inductance,
                        branch: branch_by_element[&index],
                    }
                }
                PendingElement::Voltage(name, positive, negative, source) => Element::Voltage {
                    name,
                    positive,
                    negative,
                    source,
                    branch: branch_by_element[&index],
                },
                PendingElement::Current(name, positive, negative, source) => Element::Current {
                    name,
                    positive,
                    negative,
                    source,
                },
                PendingElement::Vcvs(
                    name,
                    positive,
                    negative,
                    control_positive,
                    control_negative,
                    gain,
                ) => Element::Vcvs {
                    name,
                    positive,
                    negative,
                    control_positive,
                    control_negative,
                    gain,
                    branch: branch_by_element[&index],
                },
                PendingElement::Vccs(
                    name,
                    positive,
                    negative,
                    control_positive,
                    control_negative,
                    transconductance,
                ) => Element::Vccs {
                    name,
                    positive,
                    negative,
                    control_positive,
                    control_negative,
                    transconductance,
                },
                PendingElement::Cccs(name, positive, negative, control, gain) => Element::Cccs {
                    name,
                    positive,
                    negative,
                    control_branch: branch_by_name
                        .get(&control.to_ascii_lowercase())
                        .copied()
                        .ok_or_else(|| {
                            element_sources[index]
                                .error(format!("controlling branch '{control}' was not found"))
                        })?,
                    gain,
                },
                PendingElement::Ccvs(name, positive, negative, control, transresistance) => {
                    Element::Ccvs {
                        name,
                        positive,
                        negative,
                        control_branch: branch_by_name
                            .get(&control.to_ascii_lowercase())
                            .copied()
                            .ok_or_else(|| {
                                element_sources[index]
                                    .error(format!("controlling branch '{control}' was not found"))
                            })?,
                        transresistance,
                        branch: branch_by_element[&index],
                    }
                }
                PendingElement::Rfm(name, ports, references, model) => Element::Rfm {
                    name,
                    ports,
                    references,
                    model,
                },
            };
            elements.push(element);
        }
        let ParameterSet { numeric, .. } = self.parameters;
        Ok(Deck {
            nodes: self.nodes,
            elements,
            analyses: self.analyses,
            unknown_count: next_branch,
            branch_names,
            integration_method: self.integration_method,
            relative_tolerance: self.relative_tolerance,
            voltage_tolerance: self.voltage_tolerance,
            current_tolerance: self.current_tolerance,
            charge_tolerance: self.charge_tolerance,
            truncation_tolerance: self.truncation_tolerance,
            probes: self.probes,
            parameters: numeric,
            measurements: self.measurements,
            rfm_models: HashMap::new(),
        })
    }
}

fn parse_measurement_target(token: &str) -> Result<MeasurementTarget> {
    let open = token
        .find('(')
        .ok_or_else(|| Error::Parse(format!("invalid .measure target '{token}'")))?;
    let close = token
        .rfind(')')
        .filter(|close| *close > open)
        .ok_or_else(|| Error::Parse(format!("invalid .measure target '{token}'")))?;
    let function = token[..open].to_ascii_lowercase();
    let nodes: Vec<_> = token[open + 1..close]
        .split(',')
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .collect();
    let (branch_current, quantity) = match function.as_str() {
        "v" | "i" => (function == "i", MeasurementQuantity::Value),
        "vr" | "ir" => (function == "ir", MeasurementQuantity::Real),
        "vi" | "ii" => (function == "ii", MeasurementQuantity::Imaginary),
        "vm" | "im" => (function == "im", MeasurementQuantity::Magnitude),
        "vp" | "ip" => (function == "ip", MeasurementQuantity::Phase),
        _ => {
            return Err(Error::Parse(format!(
                "unsupported .measure target function '{function}'"
            )));
        }
    };
    if nodes.is_empty() || nodes.len() > 2 || (branch_current && nodes.len() != 1) {
        return Err(Error::Parse(format!("invalid .measure target '{token}'")));
    }
    Ok(MeasurementTarget {
        positive: nodes[0].to_string(),
        negative: nodes.get(1).map(|node| (*node).to_string()),
        branch_current,
        quantity,
    })
}

fn parse_measurement_parameter_expression(tokens: &[String], name: &str) -> Result<String> {
    let expression = match tokens {
        [expression] => expression,
        [equals, expression] if equals == "=" => expression,
        _ => {
            return Err(Error::Parse(format!(
                "invalid .measure '{name}' PARAM expression"
            )));
        }
    };
    if expression.is_empty() {
        return Err(Error::Parse(format!(
            ".measure '{name}' PARAM expression is empty"
        )));
    }
    Ok(expression.clone())
}

fn parse_measurement_event(
    tokens: &[String],
    parameters: &HashMap<String, f64>,
) -> Result<MeasurementEvent> {
    let first = tokens
        .first()
        .ok_or_else(|| Error::Parse(".measure event target is missing".into()))?;
    let (target_token, inline_value) = first
        .split_once('=')
        .map_or((first.as_str(), None), |(target, value)| {
            (target, (!value.is_empty()).then_some(value))
        });
    let target = parse_measurement_target(target_token)?;
    let mut value = inline_value
        .map(|value| parse_number(value, parameters))
        .transpose()?;
    let mut delay = None;
    let mut selector = None;
    let mut index = 1usize;
    if value.is_none() && tokens.get(index).is_some_and(|token| token == "=") {
        let event_value = tokens
            .get(index + 1)
            .ok_or_else(|| Error::Parse(".measure event value is missing".into()))?;
        value = Some(parse_number(event_value, parameters)?);
        index += 2;
    }
    while index < tokens.len() {
        let token = &tokens[index];
        let (option, raw_value, consumed) = if let Some((option, raw_value)) = token.split_once('=')
        {
            if raw_value.is_empty() {
                return Err(Error::Parse(format!(
                    ".measure event option '{option}' has no value"
                )));
            }
            (option, raw_value, 1)
        } else if tokens.get(index + 1).is_some_and(|token| token == "=") {
            let raw_value = tokens.get(index + 2).ok_or_else(|| {
                Error::Parse(format!(".measure event option '{token}' has no value"))
            })?;
            (token.as_str(), raw_value.as_str(), 3)
        } else {
            return Err(Error::Parse(format!(
                "unsupported .measure event token '{token}'"
            )));
        };
        match option.to_ascii_lowercase().as_str() {
            "val" => value = Some(parse_number(raw_value, parameters)?),
            "td" => delay = Some(parse_number(raw_value, parameters)?),
            "rise" => {
                set_measurement_selector(
                    &mut selector,
                    MeasurementEventDirection::Rise,
                    raw_value,
                    parameters,
                )?;
            }
            "fall" => {
                set_measurement_selector(
                    &mut selector,
                    MeasurementEventDirection::Fall,
                    raw_value,
                    parameters,
                )?;
            }
            "cross" => {
                set_measurement_selector(
                    &mut selector,
                    MeasurementEventDirection::Cross,
                    raw_value,
                    parameters,
                )?;
            }
            _ => {
                return Err(Error::Parse(format!(
                    "unsupported .measure event option '{option}'"
                )));
            }
        }
        index += consumed;
    }
    let value = value.ok_or_else(|| Error::Parse(".measure event value is missing".into()))?;
    let (direction, occurrence) = selector.unwrap_or((
        MeasurementEventDirection::Cross,
        MeasurementEventOccurrence::Index(1),
    ));
    Ok(MeasurementEvent {
        target,
        value,
        delay,
        direction,
        occurrence,
    })
}

fn parse_measurement_trigger(
    tokens: &[String],
    parameters: &HashMap<String, f64>,
) -> Result<MeasurementTrigger> {
    let first = tokens
        .first()
        .ok_or_else(|| Error::Parse(".measure TRIG event is missing".into()))?;
    if let Some((option, value)) = first.split_once('=')
        && option.eq_ignore_ascii_case("at")
    {
        if tokens.len() != 1 || value.is_empty() {
            return Err(Error::Parse("invalid .measure TRIG AT syntax".into()));
        }
        return parse_number(value, parameters).map(MeasurementTrigger::At);
    }
    if first.eq_ignore_ascii_case("at") && tokens.get(1).is_some_and(|token| token == "=") {
        if tokens.len() != 3 {
            return Err(Error::Parse("invalid .measure TRIG AT syntax".into()));
        }
        return parse_number(&tokens[2], parameters).map(MeasurementTrigger::At);
    }
    parse_measurement_event(tokens, parameters).map(MeasurementTrigger::Event)
}

fn set_measurement_selector(
    selector: &mut Option<(MeasurementEventDirection, MeasurementEventOccurrence)>,
    direction: MeasurementEventDirection,
    raw_value: &str,
    parameters: &HashMap<String, f64>,
) -> Result<()> {
    if selector.is_some() {
        return Err(Error::Parse(
            ".measure event accepts only one of RISE, FALL, or CROSS".into(),
        ));
    }
    let occurrence = if raw_value.eq_ignore_ascii_case("last") {
        MeasurementEventOccurrence::Last
    } else {
        let value = parse_number(raw_value, parameters)?;
        if !value.is_finite() || value < 1.0 || value.fract() != 0.0 || value > usize::MAX as f64 {
            return Err(Error::Parse(format!(
                ".measure event occurrence must be a positive integer or LAST, got '{raw_value}'"
            )));
        }
        MeasurementEventOccurrence::Index(value as usize)
    };
    *selector = Some((direction, occurrence));
    Ok(())
}

fn measurement_option(
    tokens: &[String],
    option: &str,
    parameters: &HashMap<String, f64>,
) -> Result<Option<f64>> {
    for (index, token) in tokens.iter().enumerate().skip(4) {
        if let Some((name, value)) = token.split_once('=')
            && name.eq_ignore_ascii_case(option)
        {
            return parse_number(value, parameters).map(Some);
        }
        if token.eq_ignore_ascii_case(option)
            && tokens.get(index + 1).is_some_and(|token| token == "=")
        {
            let value = tokens
                .get(index + 2)
                .ok_or_else(|| Error::Parse(format!(".measure {option} value is missing")))?;
            return parse_number(value, parameters).map(Some);
        }
    }
    Ok(None)
}

fn probe_name(token: &str) -> Option<String> {
    let lower = token.to_ascii_lowercase();
    for marker in ["v(", "i(", "vr(", "vi(", "vm(", "vp("] {
        if let Some(start) = lower.find(marker) {
            let value_start = start + marker.len();
            let end = lower[value_start..].find(')')? + value_start;
            let name = token[value_start..end].split(',').next()?.trim();
            if !name.is_empty() {
                return Some(name.to_string());
            }
        }
    }
    (!token.contains('(') && !token.contains(')')).then(|| token.to_string())
}

fn strip_hspice_comment(line: &str) -> &str {
    let mut quote = None;
    for (index, character) in line.char_indices() {
        match character {
            '\'' | '"' if quote.is_none() => quote = Some(character),
            value if quote == Some(value) => quote = None,
            '$' if quote.is_none() => return &line[..index],
            _ => {}
        }
    }
    line
}

fn logical_lines(text: &str, path: &Path) -> Vec<SourceLine> {
    let mut lines: Vec<SourceLine> = Vec::new();
    for (physical_index, raw) in text.lines().enumerate() {
        let trimmed = strip_hspice_comment(raw).trim();
        if trimmed.is_empty() || trimmed.starts_with('*') {
            if physical_index == 0 {
                lines.push(SourceLine::new(
                    path,
                    physical_index + 1,
                    trimmed.to_string(),
                ));
            }
            continue;
        }
        if let Some(continuation) = trimmed.strip_prefix('+') {
            if let Some(previous) = lines
                .iter_mut()
                .rev()
                .find(|line| !line.text.is_empty() && !line.text.starts_with('*'))
            {
                previous.text.push(' ');
                previous.text.push_str(continuation.trim());
                previous.original.push(' ');
                previous.original.push_str(continuation.trim());
            }
        } else {
            lines.push(SourceLine::new(
                path,
                physical_index + 1,
                trimmed.to_string(),
            ));
        }
    }
    lines
}

fn tokenize(line: &str) -> Vec<String> {
    let mut tokens = Vec::new();
    let mut current = String::new();
    let mut depth = 0usize;
    let mut quote = None;
    for character in line.chars() {
        match character {
            '\'' | '"' if quote.is_none() => {
                quote = Some(character);
                current.push(character);
            }
            value if quote == Some(value) => {
                quote = None;
                current.push(value);
            }
            '(' | '{' if quote.is_none() => {
                depth += 1;
                current.push(character);
            }
            ')' | '}' if quote.is_none() => {
                depth = depth.saturating_sub(1);
                current.push(character);
            }
            value if value.is_whitespace() && depth == 0 && quote.is_none() => {
                if !current.is_empty() {
                    tokens.push(std::mem::take(&mut current));
                }
            }
            _ => current.push(character),
        }
    }
    if !current.is_empty() {
        tokens.push(current);
    }
    tokens
}

fn parse_passive_value(
    tokens: &[String],
    parameter_name: &str,
    parameters: &HashMap<String, f64>,
) -> Result<f64> {
    let first = tokens
        .first()
        .ok_or_else(|| Error::Parse(format!("{parameter_name} value is missing")))?;
    let expression = if let Some((name, value)) = first.split_once('=')
        && name.eq_ignore_ascii_case(parameter_name)
    {
        if value.is_empty() {
            tokens
                .get(1)
                .filter(|value| value.as_str() != "=")
                .ok_or_else(|| Error::Parse(format!("{parameter_name} value is missing")))?
        } else {
            value
        }
    } else if first.eq_ignore_ascii_case(parameter_name)
        && tokens.get(1).is_some_and(|value| value == "=")
    {
        tokens
            .get(2)
            .ok_or_else(|| Error::Parse(format!("{parameter_name} value is missing")))?
    } else if first.eq_ignore_ascii_case(parameter_name)
        && tokens.get(1).is_some_and(|value| value.starts_with('='))
    {
        tokens[1]
            .strip_prefix('=')
            .filter(|value| !value.is_empty())
            .ok_or_else(|| Error::Parse(format!("{parameter_name} value is missing")))?
    } else {
        first
    };
    parse_number(expression, parameters)
}

fn parse_source(
    tokens: &[String],
    parameters: &ParameterSet,
    source_directory: &Path,
) -> Result<Source> {
    let mut dc = None;
    let mut ac = c64::new(0.0, 0.0);
    let mut waveform = None;
    let mut index = 0usize;
    while index < tokens.len() {
        let token = &tokens[index];
        if token.eq_ignore_ascii_case("dc") {
            index += 1;
            dc = Some(parse_number(
                tokens
                    .get(index)
                    .ok_or_else(|| Error::Parse("DC source value is missing".into()))?,
                parameters,
            )?);
        } else if token.eq_ignore_ascii_case("ac") {
            index += 1;
            let magnitude = parse_number(
                tokens
                    .get(index)
                    .ok_or_else(|| Error::Parse("AC source magnitude is missing".into()))?,
                parameters,
            )?;
            let phase = tokens
                .get(index + 1)
                .filter(|value| !is_source_keyword(value))
                .map(|value| parse_number(value, parameters))
                .transpose()?
                .unwrap_or(0.0);
            if phase != 0.0 {
                index += 1;
            }
            ac = c64::from_polar(magnitude, phase * PI / 180.0);
        } else if token.to_ascii_lowercase().starts_with("pulse(") {
            let values = waveform_values(token, "pulse", parameters)?;
            if values.len() < 2 {
                return Err(Error::Parse("PULSE requires at least two values".into()));
            }
            let initial = values[0];
            let pulsed = values[1];
            let delay = values.get(2).copied().unwrap_or(0.0);
            let rise = values.get(3).copied().unwrap_or(0.0);
            let fall = values.get(4).copied().unwrap_or(rise);
            let width = values.get(5).copied().unwrap_or(f64::INFINITY);
            let period = values.get(6).copied().unwrap_or(f64::INFINITY);
            dc.get_or_insert(initial);
            waveform = Some(Waveform::Pulse {
                initial,
                pulsed,
                delay,
                rise,
                fall,
                width,
                period,
            });
        } else if token.to_ascii_lowercase().starts_with("pwl(") {
            let values = waveform_values(token, "pwl", parameters)?;
            if values.len() < 2 || values.len() % 2 != 0 {
                return Err(Error::Parse("PWL requires time/value pairs".into()));
            }
            let points: Vec<(f64, f64)> = values
                .chunks_exact(2)
                .map(|pair| (pair[0], pair[1]))
                .collect();
            if points.windows(2).any(|pair| pair[1].0 <= pair[0].0) {
                return Err(Error::Parse("PWL times must be strictly increasing".into()));
            }
            dc.get_or_insert(points[0].1);
            waveform = Some(Waveform::Pwl {
                hard_breakpoints: pwl_hard_breakpoints(&points, None),
                points,
                repeat_from: None,
            });
        } else if token.eq_ignore_ascii_case("pwl") {
            let parsed = parse_pwl_file_source(&tokens[index + 1..], parameters, source_directory)?;
            let ParsedPwlFileSource {
                points,
                repeat_from,
            } = parsed;
            dc.get_or_insert(points[0].1);
            waveform = Some(Waveform::Pwl {
                hard_breakpoints: pwl_hard_breakpoints(&points, repeat_from),
                points,
                repeat_from,
            });
            break;
        } else if dc.is_none() {
            dc = Some(parse_number(token, parameters)?);
        } else {
            return Err(Error::Parse(format!("unsupported source token '{token}'")));
        }
        index += 1;
    }
    Ok(Source {
        dc: dc.unwrap_or(0.0),
        ac,
        waveform,
    })
}

fn parse_pwl_file_source(
    tokens: &[String],
    parameters: &ParameterSet,
    source_directory: &Path,
) -> Result<ParsedPwlFileSource> {
    let mut normalized = tokens.to_vec();
    for index in 0..normalized.len() {
        if normalized[index].eq_ignore_ascii_case("r")
            && normalized
                .get(index + 1)
                .is_none_or(|next| next != "=" && !next.starts_with('='))
        {
            normalized[index] = "r=0".into();
        }
    }
    let mut file = None;
    let mut multiplier = 1.0;
    let mut delay = 0.0;
    let mut repeat_from = None;
    for (name, value) in parse_assignments(&normalized, "PWL source option", false)? {
        match name.to_ascii_lowercase().as_str() {
            "pwlfile" => file = Some(resolve_string_value(&value, parameters)?),
            "m" => multiplier = parse_number(&value, parameters)?,
            "td" => delay = parse_number(&value, parameters)?,
            "r" => repeat_from = Some(parse_number(&value, parameters)?),
            _ => {
                return Err(Error::Parse(format!(
                    "unsupported PWL source option '{name}'"
                )));
            }
        }
    }
    if !multiplier.is_finite() {
        return Err(Error::Parse("PWL source M must be finite".into()));
    }
    if delay < 0.0 || !delay.is_finite() {
        return Err(Error::Parse("PWL source TD must be non-negative".into()));
    }
    if repeat_from.is_some_and(|value| value < 0.0 || !value.is_finite()) {
        return Err(Error::Parse("PWL source R must be non-negative".into()));
    }
    let file = file.ok_or_else(|| Error::Parse("PWL source requires PWLFILE".into()))?;
    let path = PathBuf::from(file);
    let path = if path.is_absolute() {
        path
    } else {
        let deck_relative = source_directory.join(&path);
        if deck_relative.is_file() {
            deck_relative
        } else if path.is_file() {
            path
        } else {
            deck_relative
        }
    };
    let mut points = read_pwl_file(&path)?;
    if let Some(repeat) = repeat_from {
        let end = points.last().expect("PWL file has at least two points").0;
        if repeat >= end {
            return Err(Error::Parse(format!(
                "PWL source R={repeat} must be less than the final time {end} in '{}'",
                path.display()
            )));
        }
        insert_pwl_point(&mut points, repeat);
    }
    for (time, value) in &mut points {
        *time += delay;
        *value *= multiplier;
    }
    Ok(ParsedPwlFileSource {
        points,
        repeat_from: repeat_from.map(|repeat| repeat + delay),
    })
}

fn resolve_string_value(value: &str, parameters: &ParameterSet) -> Result<String> {
    let value = value.trim();
    if value.len() >= 2 {
        let first = value.as_bytes()[0] as char;
        let last = value.as_bytes()[value.len() - 1] as char;
        if (first == '\'' || first == '"') && first == last {
            return Ok(value[1..value.len() - 1].to_string());
        }
    }
    if value.len() > 5 && value[..4].eq_ignore_ascii_case("str(") && value.ends_with(')') {
        let argument = value[4..value.len() - 1].trim();
        if let Some(parameter) = parameters.string(argument) {
            return Ok(parameter.to_string());
        }
        let unquoted = argument.trim_matches(|character| character == '\'' || character == '"');
        if unquoted != argument {
            return Ok(unquoted.to_string());
        }
        return Err(Error::Parse(format!(
            "unknown string parameter '{argument}' in PWLFILE"
        )));
    }
    Ok(parameters.string(value).unwrap_or(value).to_string())
}

fn read_pwl_file(path: &Path) -> Result<Vec<(f64, f64)>> {
    let text = fs::read_to_string(path).map_err(|error| {
        Error::Parse(format!(
            "failed to read PWLFILE '{}': {error}",
            path.display()
        ))
    })?;
    let empty = HashMap::new();
    let mut points = Vec::new();
    for (line_index, raw) in text.lines().enumerate() {
        let line = strip_hspice_comment(raw).trim();
        if line.is_empty() || line.starts_with('*') || line.starts_with('#') {
            continue;
        }
        let fields: Vec<_> = line
            .split(|character: char| character == ',' || character.is_whitespace())
            .filter(|field| !field.is_empty())
            .collect();
        if fields.len() < 2 {
            return Err(Error::Parse(format!(
                "PWLFILE '{}' line {} requires time and value columns",
                path.display(),
                line_index + 1
            )));
        }
        let time = parse_number(fields[0], &empty).map_err(|error| {
            Error::Parse(format!(
                "PWLFILE '{}' line {} has invalid time: {error}",
                path.display(),
                line_index + 1
            ))
        })?;
        let value = parse_number(fields[1], &empty).map_err(|error| {
            Error::Parse(format!(
                "PWLFILE '{}' line {} has invalid value: {error}",
                path.display(),
                line_index + 1
            ))
        })?;
        points.push((time, value));
    }
    if points.len() < 2 {
        return Err(Error::Parse(format!(
            "PWLFILE '{}' requires at least two time/value rows",
            path.display()
        )));
    }
    if points.windows(2).any(|pair| pair[1].0 <= pair[0].0) {
        return Err(Error::Parse(format!(
            "PWLFILE '{}' times must be strictly increasing",
            path.display()
        )));
    }
    Ok(points)
}

fn insert_pwl_point(points: &mut Vec<(f64, f64)>, time: f64) {
    if points
        .iter()
        .any(|(point_time, _)| (*point_time - time).abs() <= 1e-15)
    {
        return;
    }
    let value = if time <= points[0].0 {
        points[0].1
    } else {
        let pair = points
            .windows(2)
            .find(|pair| time < pair[1].0)
            .expect("repeat time is before the final PWL point");
        let fraction = (time - pair[0].0) / (pair[1].0 - pair[0].0);
        pair[0].1 + fraction * (pair[1].1 - pair[0].1)
    };
    let index = points.partition_point(|(point_time, _)| *point_time < time);
    points.insert(index, (time, value));
}

fn is_source_keyword(token: &str) -> bool {
    token.eq_ignore_ascii_case("dc")
        || token.eq_ignore_ascii_case("ac")
        || token.eq_ignore_ascii_case("pwl")
        || token.contains('(')
}

fn waveform_values(token: &str, name: &str, parameters: &HashMap<String, f64>) -> Result<Vec<f64>> {
    let open = token
        .find('(')
        .ok_or_else(|| Error::Parse(format!("invalid {name} waveform")))?;
    let close = token
        .rfind(')')
        .ok_or_else(|| Error::Parse(format!("invalid {name} waveform")))?;
    token[open + 1..close]
        .split(|character: char| character.is_whitespace() || character == ',')
        .filter(|value| !value.is_empty())
        .map(|value| parse_number(value, parameters))
        .collect()
}

pub fn parse_number(token: &str, parameters: &HashMap<String, f64>) -> Result<f64> {
    expression::evaluate(token.trim(), parameters)
}
