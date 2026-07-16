use std::collections::{HashMap, HashSet};
use std::f64::consts::PI;
use std::fs;
use std::path::{Path, PathBuf};

use faer::c64;

use crate::error::{Error, Result};
use crate::expression;

pub type Node = Option<usize>;

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
    Pwl(Vec<(f64, f64)>),
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
            Self::Pwl(points) => {
                if time <= points[0].0 {
                    return points[0].1;
                }
                for pair in points.windows(2) {
                    let (left_time, left_value) = pair[0];
                    let (right_time, right_value) = pair[1];
                    if time <= right_time {
                        let fraction = (time - left_time) / (right_time - left_time);
                        return left_value + fraction * (right_value - left_value);
                    }
                }
                points.last().expect("PWL has at least one point").1
            }
        }
    }

    pub fn next_breakpoint_after(&self, time: f64, stop: f64) -> Option<f64> {
        let tolerance = 1e-15_f64.max(time.abs() * 1e-12);
        match self {
            Self::Pwl(points) => points
                .iter()
                .map(|(point_time, _)| *point_time)
                .find(|point_time| *point_time > time + tolerance && *point_time <= stop),
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

#[derive(Debug, Clone)]
pub struct Source {
    pub dc: f64,
    pub ac: c64,
    pub waveform: Option<Waveform>,
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
        reference: Node,
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
}

impl Deck {
    pub fn parse_file(path: &Path, rfm_binding: Option<(&str, usize)>) -> Result<Self> {
        let mut active = HashSet::new();
        let text = expand_includes(path, &mut active)?;
        let text = flatten_subcircuits(&text, rfm_binding.map(|(name, _)| name))?;
        Self::parse(&text, rfm_binding)
    }

    fn parse(text: &str, rfm_binding: Option<(&str, usize)>) -> Result<Self> {
        let mut parser = Parser {
            rfm_subcircuit: rfm_binding.map(|(name, _)| name.to_string()),
            rfm_nports: rfm_binding.map(|(_, nports)| nports),
            relative_tolerance: 1e-3,
            voltage_tolerance: 1e-6,
            current_tolerance: 1e-12,
            charge_tolerance: 1e-14,
            truncation_tolerance: 7.0,
            ..Parser::default()
        };
        let lines = logical_lines(text);
        for (line_index, line) in lines.iter().enumerate() {
            if line_index == 0 || line.is_empty() || line.starts_with('*') {
                continue;
            }
            parser.parse_line(line)?;
        }
        parser.finish()
    }
}

fn expand_includes(path: &Path, active: &mut HashSet<PathBuf>) -> Result<String> {
    let path = path.canonicalize()?;
    enter_dependency(&path, active)?;
    let text = fs::read_to_string(&path)?;
    let expanded = expand_dependency_lines(&path, logical_lines(&text), active)?;
    active.remove(&path);
    Ok(expanded)
}

fn expand_dependency_lines(
    source: &Path,
    lines: Vec<String>,
    active: &mut HashSet<PathBuf>,
) -> Result<String> {
    let mut expanded = String::new();
    for line in lines {
        let tokens = tokenize(&line);
        let include = tokens.first().is_some_and(|head| {
            head.eq_ignore_ascii_case(".inc") || head.eq_ignore_ascii_case(".include")
        });
        if include {
            let reference = tokens
                .get(1)
                .ok_or_else(|| Error::Parse(format!("include path is missing in '{line}'")))?
                .trim_matches(|character| character == '\'' || character == '"');
            let include_path = source
                .parent()
                .unwrap_or_else(|| Path::new("."))
                .join(reference);
            expanded.push_str(&expand_includes(&include_path, active)?);
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
            expanded.push_str(&expand_library_section(&library_path, &tokens[2], active)?);
        } else {
            expanded.push_str(&line);
            expanded.push('\n');
        }
    }
    Ok(expanded)
}

fn expand_library_section(
    path: &Path,
    section: &str,
    active: &mut HashSet<PathBuf>,
) -> Result<String> {
    let path = path.canonicalize()?;
    enter_dependency(&path, active)?;
    let text = fs::read_to_string(&path)?;
    let mut selected = Vec::new();
    let mut inside = false;
    let mut found = false;
    for line in logical_lines(&text) {
        let values = tokenize(&line);
        if values
            .first()
            .is_some_and(|head| head.eq_ignore_ascii_case(".lib"))
            && values.len() == 2
        {
            if inside {
                active.remove(&path);
                return Err(Error::Parse(format!(
                    "nested .lib section in '{}'",
                    path.display()
                )));
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

#[derive(Debug, Clone)]
struct Subcircuit {
    pins: Vec<String>,
    defaults: Vec<(String, String)>,
    body: Vec<String>,
}

struct Scope {
    path: String,
    pins: HashMap<String, String>,
    parameters: HashMap<String, f64>,
}

fn flatten_subcircuits(text: &str, rfm_subcircuit: Option<&str>) -> Result<String> {
    let lines = logical_lines(text);
    if lines.is_empty() {
        return Ok(String::new());
    }
    let mut definitions = HashMap::new();
    let mut top_level = vec![lines[0].clone()];
    let mut active: Option<(String, Subcircuit, bool)> = None;
    for line in lines.into_iter().skip(1) {
        let values = tokenize(&line);
        let head = values
            .first()
            .map(|value| value.to_ascii_lowercase())
            .unwrap_or_default();
        if head == ".subckt" {
            if active.is_some() {
                return Err(Error::Parse(
                    "nested .subckt definitions are not supported".into(),
                ));
            }
            let name = values
                .get(1)
                .ok_or_else(|| Error::Parse(".subckt name is missing".into()))?
                .clone();
            let parameter_start = values[2..]
                .iter()
                .position(|value| {
                    value.eq_ignore_ascii_case("params:")
                        || value.eq_ignore_ascii_case("params")
                        || value.contains('=')
                })
                .map(|index| index + 2)
                .unwrap_or(values.len());
            let pins = values[2..parameter_start].to_vec();
            let mut defaults = Vec::new();
            for value in &values[parameter_start..] {
                if value.eq_ignore_ascii_case("params:") || value.eq_ignore_ascii_case("params") {
                    continue;
                }
                let (parameter, default) = value.split_once('=').ok_or_else(|| {
                    Error::Parse(format!("invalid .subckt parameter declaration '{value}'"))
                })?;
                defaults.push((parameter.to_ascii_lowercase(), default.to_string()));
            }
            let ignored = rfm_subcircuit.is_some_and(|rfm| name.eq_ignore_ascii_case(rfm));
            active = Some((
                name,
                Subcircuit {
                    pins,
                    defaults,
                    body: Vec::new(),
                },
                ignored,
            ));
            continue;
        }
        if head == ".ends" {
            let (name, definition, ignored) = active
                .take()
                .ok_or_else(|| Error::Parse(".ends has no matching .subckt".into()))?;
            if !ignored
                && definitions
                    .insert(name.to_ascii_lowercase(), definition)
                    .is_some()
            {
                return Err(Error::Parse(format!(
                    "duplicate subcircuit definition '{name}'"
                )));
            }
            continue;
        }
        if let Some((_, definition, _)) = active.as_mut() {
            definition.body.push(line);
        } else {
            top_level.push(line);
        }
    }
    if let Some((name, _, _)) = active {
        return Err(Error::Parse(format!(
            "subcircuit '{name}' has no matching .ends"
        )));
    }
    if definitions.is_empty() {
        return Ok(top_level.join("\n") + "\n");
    }

    let mut global_nodes = HashSet::new();
    for line in &top_level {
        let values = tokenize(line);
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
        active: Vec::new(),
    };
    let mut output = vec![top_level[0].clone()];
    let mut top_parameters = HashMap::new();
    for line in top_level.into_iter().skip(1) {
        let values = tokenize(&line);
        if values.is_empty() {
            continue;
        }
        if values[0].eq_ignore_ascii_case(".global") {
            continue;
        }
        if values[0].eq_ignore_ascii_case(".param") {
            update_parameters(&values[1..], &mut top_parameters)?;
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
    Ok(output.join("\n") + "\n")
}

struct Flattener<'a> {
    definitions: &'a HashMap<String, Subcircuit>,
    global_nodes: &'a HashSet<String>,
    rfm_subcircuit: Option<&'a str>,
    active: Vec<String>,
}

impl Flattener<'_> {
    fn expand_line(&mut self, line: &str, scope: &Scope, output: &mut Vec<String>) -> Result<()> {
        let substituted = substitute_braced_expressions(line, &scope.parameters)?;
        let mut values = tokenize(&substituted);
        for value in &mut values {
            let quoted_expression = value.len() >= 2
                && ((value.starts_with('\'') && value.ends_with('\''))
                    || (value.starts_with('"') && value.ends_with('"')));
            if quoted_expression {
                if let Ok(parameter) = expression::evaluate(value, &scope.parameters) {
                    *value = format!("{parameter:.17e}");
                }
            } else if let Some(parameter) = scope.parameters.get(&value.to_ascii_lowercase()) {
                *value = format!("{parameter:.17e}");
            }
        }
        if values.is_empty() || values[0].starts_with('*') {
            return Ok(());
        }
        if values[0].starts_with('.') {
            output.push(values.join(" "));
            return Ok(());
        }
        let kind = values[0].as_bytes()[0].to_ascii_uppercase();
        if kind == b'X' {
            return self.expand_instance(&values, scope, output);
        }
        if !scope.path.is_empty() {
            values[0] = qualify_element(&scope.path, &values[0]);
        }
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
        if matches!(kind, b'F' | b'H') && !scope.path.is_empty() && values.len() > 3 {
            values[3] = qualify_element(&scope.path, &values[3]);
        }
        output.push(values.join(" "));
        Ok(())
    }

    fn expand_instance(
        &mut self,
        values: &[String],
        scope: &Scope,
        output: &mut Vec<String>,
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
            output.push(rewritten.join(" "));
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
            let value = expression::evaluate(default, &parameters)?;
            parameters.insert(name.clone(), value);
        }
        for assignment in &values[definition_index + 1..] {
            let (name, value) = assignment.split_once('=').ok_or_else(|| {
                Error::Parse(format!(
                    "invalid instance parameter override '{assignment}'"
                ))
            })?;
            let value = expression::evaluate(value, &scope.parameters)?;
            parameters.insert(name.to_ascii_lowercase(), value);
        }
        let mut child = Scope {
            path,
            pins,
            parameters,
        };
        self.active.push(definition_name);
        for line in &definition.body {
            let body_values = tokenize(line);
            if body_values
                .first()
                .is_some_and(|value| value.eq_ignore_ascii_case(".param"))
            {
                let assignments: Vec<String> = body_values[1..]
                    .iter()
                    .map(|value| substitute_braced_expressions(value, &child.parameters))
                    .collect::<Result<_>>()?;
                update_parameters(&assignments, &mut child.parameters)?;
                continue;
            }
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

fn update_parameters(tokens: &[String], parameters: &mut HashMap<String, f64>) -> Result<()> {
    for token in tokens {
        let (name, expression_text) = token
            .split_once('=')
            .ok_or_else(|| Error::Parse(format!("invalid .param assignment '{token}'")))?;
        let value = expression::evaluate(expression_text, parameters)?;
        parameters.insert(name.to_ascii_lowercase(), value);
    }
    Ok(())
}

fn substitute_braced_expressions(line: &str, parameters: &HashMap<String, f64>) -> Result<String> {
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
        let value = expression::evaluate(&line[start + 1..end], parameters)?;
        output.push_str(&format!("{value:.17e}"));
        cursor = end + 1;
    }
    output.push_str(&line[cursor..]);
    Ok(output)
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
    analyses: Vec<Analysis>,
    parameters: HashMap<String, f64>,
    rfm_subcircuit: Option<String>,
    rfm_nports: Option<usize>,
    skipping_rfm_wrapper: bool,
    integration_method: IntegrationMethod,
    relative_tolerance: f64,
    voltage_tolerance: f64,
    current_tolerance: f64,
    charge_tolerance: f64,
    truncation_tolerance: f64,
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
    Rfm(String, Vec<Node>, Node),
}

impl Parser {
    fn parse_line(&mut self, line: &str) -> Result<()> {
        let line = line.split('$').next().unwrap_or("").trim();
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
                let value = parse_number(&tokens[3], &self.parameters)?;
                if value <= 0.0 {
                    return Err(Error::Parse(format!(
                        "resistance must be positive on '{name}'"
                    )));
                }
                self.elements
                    .push(PendingElement::Resistor(name, positive, negative, value));
            }
            b'C' => {
                let value = parse_number(&tokens[3], &self.parameters)?;
                if value <= 0.0 {
                    return Err(Error::Parse(format!(
                        "capacitance must be positive on '{name}'"
                    )));
                }
                self.elements
                    .push(PendingElement::Capacitor(name, positive, negative, value));
            }
            b'L' => {
                let value = parse_number(&tokens[3], &self.parameters)?;
                if value <= 0.0 {
                    return Err(Error::Parse(format!(
                        "inductance must be positive on '{name}'"
                    )));
                }
                self.elements
                    .push(PendingElement::Inductor(name, positive, negative, value));
            }
            b'V' => {
                let source = parse_source(&tokens[3..], &self.parameters)?;
                self.elements
                    .push(PendingElement::Voltage(name, positive, negative, source));
            }
            b'I' => {
                let source = parse_source(&tokens[3..], &self.parameters)?;
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
                self.elements
                    .push(PendingElement::Rfm(name, ports, reference));
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
                for token in tokens {
                    let (name, value) = token.split_once('=').ok_or_else(|| {
                        Error::Parse(format!("invalid .param assignment '{token}'"))
                    })?;
                    let value = parse_number(value, &self.parameters)?;
                    self.parameters.insert(name.to_ascii_lowercase(), value);
                }
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
                        _ => {}
                    }
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
                            Error::Parse(format!("controlling branch '{control}' was not found"))
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
                                Error::Parse(format!(
                                    "controlling branch '{control}' was not found"
                                ))
                            })?,
                        transresistance,
                        branch: branch_by_element[&index],
                    }
                }
                PendingElement::Rfm(name, ports, reference) => Element::Rfm {
                    name,
                    ports,
                    reference,
                },
            };
            elements.push(element);
        }
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
            parameters: self.parameters,
            measurements: self.measurements,
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

fn logical_lines(text: &str) -> Vec<String> {
    let mut lines: Vec<String> = Vec::new();
    for raw in text.lines() {
        let trimmed = raw.trim();
        if let Some(continuation) = trimmed.strip_prefix('+') {
            if let Some(previous) = lines.last_mut() {
                previous.push(' ');
                previous.push_str(continuation.trim());
            }
        } else {
            lines.push(trimmed.to_string());
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

fn parse_source(tokens: &[String], parameters: &HashMap<String, f64>) -> Result<Source> {
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
            waveform = Some(Waveform::Pwl(points));
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

fn is_source_keyword(token: &str) -> bool {
    token.eq_ignore_ascii_case("dc") || token.eq_ignore_ascii_case("ac") || token.contains('(')
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
