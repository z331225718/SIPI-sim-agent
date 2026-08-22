#![forbid(unsafe_code)]

//! AS-05 admission model plus the lane-local AS-01 `fit-sparam` direct port.
//!
//! This crate is intentionally lane-local and is not a product command yet.
//! It records the pinned `run-hspice` branch contract before a Rust solver is
//! promoted.  The model is executable for deck splitting, audit, conversion,
//! dependency admission, and artifact planning. The AS-01 module contains a
//! bounded native Rust fit route; neither lane claims product promotion or
//! numerical parity without the pinned differential gate.

pub mod fit_sparam;

use std::collections::{BTreeMap, BTreeSet};
use std::fmt::{Display, Formatter};
use std::path::{Path, PathBuf};

pub const UPSTREAM_REPOSITORY: &str = "agent-spice";
pub const UPSTREAM_COMMIT: &str = "2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5";
pub const UPSTREAM_TREE: &str = "b6bde97128030d6cea0d68b2f0a35d807be8c402";
pub const UPSTREAM_LICENSE: &str = "MIT";
pub const WORKFLOW_ID: &str = "AS-05";
pub const WORKFLOW_NAME: &str = "run-hspice";

const SUPPORTED_DIRECTIVES: &[&str] = &[
    ".ac", ".alter", ".dc", ".elif", ".else", ".elseif", ".endl", ".end", ".endif", ".ends",
    ".global", ".inc", ".include", ".if", ".lib", ".measure", ".meas", ".op", ".option",
    ".options", ".param", ".print", ".probe", ".subckt", ".temp", ".tran",
];

/// The four backend selectors accepted by the pinned CLI.
#[derive(Clone, Copy, Debug, Eq, Ord, PartialEq, PartialOrd)]
pub enum Backend {
    Native,
    Ngspice,
    Xyce,
    XyceXdm,
}

impl Backend {
    pub const ALL: [Self; 4] = [Self::Native, Self::Ngspice, Self::Xyce, Self::XyceXdm];

    pub const fn name(self) -> &'static str {
        match self {
            Self::Native => "native",
            Self::Ngspice => "ngspice",
            Self::Xyce => "xyce",
            Self::XyceXdm => "xyce-xdm",
        }
    }

    pub fn parse(value: &str) -> Result<Self, DirectPortError> {
        match value {
            "native" => Ok(Self::Native),
            "ngspice" => Ok(Self::Ngspice),
            "xyce" => Ok(Self::Xyce),
            "xyce-xdm" => Ok(Self::XyceXdm),
            other => Err(DirectPortError::UnsupportedBackend(other.to_owned())),
        }
    }
}

impl Display for Backend {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(self.name())
    }
}

/// Caller-visible options that affect the upstream branch graph.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RunHspiceRequest {
    pub backend: Backend,
    pub output_root: PathBuf,
    pub execute: bool,
    pub native_engine: Option<PathBuf>,
    pub rfm: Option<PathBuf>,
    pub rfm_subcircuit: String,
    pub dotnet_executable: String,
}

impl RunHspiceRequest {
    pub fn new(
        backend: &str,
        output_root: impl Into<PathBuf>,
        execute: bool,
    ) -> Result<Self, DirectPortError> {
        let output_root = output_root.into();
        if output_root.as_os_str().is_empty() {
            return Err(DirectPortError::EmptyOutputRoot);
        }
        Ok(Self {
            backend: Backend::parse(backend)?,
            output_root,
            execute,
            native_engine: None,
            rfm: None,
            rfm_subcircuit: "rfm_direct".to_owned(),
            dotnet_executable: "dotnet".to_owned(),
        })
    }

    pub fn with_native_engine(mut self, path: impl Into<PathBuf>) -> Self {
        self.native_engine = Some(path.into());
        self
    }

    pub fn with_rfm(mut self, path: impl Into<PathBuf>, subcircuit: impl Into<String>) -> Self {
        self.rfm = Some(path.into());
        self.rfm_subcircuit = subcircuit.into();
        self
    }

    pub fn with_dotnet(mut self, executable: impl Into<String>) -> Self {
        self.dotnet_executable = executable.into();
        self
    }
}

/// Stable rejection categories for this admission layer.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum DirectPortError {
    UnsupportedBackend(String),
    EmptyOutputRoot,
    EmptyDeckStem,
}

impl Display for DirectPortError {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::UnsupportedBackend(value) => write!(formatter, "unsupported backend '{value}'"),
            Self::EmptyOutputRoot => formatter.write_str("output root must not be empty"),
            Self::EmptyDeckStem => formatter.write_str("deck stem must not be empty"),
        }
    }
}

impl std::error::Error for DirectPortError {}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum CaseKind {
    Base,
    Alter,
    Other,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct DeckCase {
    pub name: String,
    pub text: String,
    pub kind: CaseKind,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct LibraryReference {
    pub path: String,
    pub section: Option<String>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct DeckAudit {
    pub directive_counts: BTreeMap<String, usize>,
    pub includes: Vec<String>,
    pub libraries: Vec<LibraryReference>,
    pub unsupported_directives: Vec<String>,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum DependencyAdmission {
    RelativeRequiresSourceRoot,
    AbsoluteNotStaged,
    LexicallyEscapesSourceRoot,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct DependencyReference {
    pub reference: String,
    pub admission: DependencyAdmission,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ConversionAction {
    pub kind: String,
    pub source: String,
    pub target: String,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct UnsupportedIssue {
    pub line: String,
    pub reason: String,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum PreparationStatus {
    Compatible,
    AutoConverted,
    Blocked,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct PreparedCase {
    pub case: DeckCase,
    pub deck_text: String,
    pub audit: DeckAudit,
    pub dependencies: Vec<DependencyReference>,
    pub actions: Vec<ConversionAction>,
    pub unsupported: Vec<UnsupportedIssue>,
    pub preparation_status: PreparationStatus,
    pub output_paths: Vec<String>,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ExecutionStage {
    NotExecuted,
    NativeEngine,
    Ngspice,
    Xyce,
    XdmThenXyce,
}

impl ExecutionStage {
    pub const fn for_request(request: &RunHspiceRequest) -> Self {
        if !request.execute {
            return Self::NotExecuted;
        }
        match request.backend {
            Backend::Native => Self::NativeEngine,
            Backend::Ngspice => Self::Ngspice,
            Backend::Xyce => Self::Xyce,
            Backend::XyceXdm => Self::XdmThenXyce,
        }
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RunHspiceAdmission {
    pub deck_id: String,
    pub backend: Backend,
    pub execute: bool,
    pub execution_stage: ExecutionStage,
    pub cases: Vec<PreparedCase>,
    pub external_solver_required: bool,
    pub numerical_parity: ParityStatus,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ParityStatus {
    NotEvaluated,
}

/// Build the AS-05 branch plan from the same deck text accepted by upstream.
/// No file is opened and no backend process is launched here.
pub fn admit_run_hspice(
    deck_stem: &str,
    deck_text: &str,
    request: RunHspiceRequest,
) -> Result<RunHspiceAdmission, DirectPortError> {
    if deck_stem.is_empty() {
        return Err(DirectPortError::EmptyDeckStem);
    }
    let cases = split_alter_cases(deck_text, deck_stem);
    let prepared = cases
        .into_iter()
        .map(|case| prepare_case(case, request.backend))
        .collect();
    Ok(RunHspiceAdmission {
        deck_id: deck_stem.to_owned(),
        backend: request.backend,
        execute: request.execute,
        execution_stage: ExecutionStage::for_request(&request),
        cases: prepared,
        external_solver_required: request.execute,
        numerical_parity: ParityStatus::NotEvaluated,
    })
}

fn prepare_case(case: DeckCase, backend: Backend) -> PreparedCase {
    let audit = audit_deck(&case.text);
    let dependencies = audit
        .includes
        .iter()
        .cloned()
        .chain(audit.libraries.iter().map(|library| library.path.clone()))
        .map(|reference| DependencyReference {
            admission: classify_dependency(&reference),
            reference,
        })
        .collect::<Vec<_>>();
    let (deck_text, actions, unsupported) = convert_deck(&case.text, backend);
    let mut output_paths = vec![
        format!("{}/case.cir", case.name),
        format!("{}/case.source.sp", case.name),
        format!("{}/compat_report.json", case.name),
    ];
    if backend == Backend::XyceXdm {
        output_paths.push(format!("{}/case.sp", case.name));
    }
    let status = if !audit.unsupported_directives.is_empty() || !unsupported.is_empty() {
        PreparationStatus::Blocked
    } else if actions.is_empty() {
        PreparationStatus::Compatible
    } else {
        PreparationStatus::AutoConverted
    };
    PreparedCase {
        case,
        deck_text,
        audit,
        dependencies,
        actions,
        unsupported,
        preparation_status: status,
        output_paths,
    }
}

/// Mirrors `split_alter_cases` from the pinned Python object, including its
/// permissive `.alter*` prefix and missing-`.end` behavior.
pub fn split_alter_cases(text: &str, stem: &str) -> Vec<DeckCase> {
    let mut base = Vec::<String>::new();
    let mut alters = Vec::<(String, Vec<String>)>::new();
    let mut current_header: Option<String> = None;
    let mut current_lines = Vec::<String>::new();
    let mut end_line: Option<String> = None;
    for line in text.lines() {
        let stripped = line.trim();
        if stripped.eq_ignore_ascii_case(".end") {
            end_line = Some(stripped.to_owned());
            continue;
        }
        if stripped.to_ascii_lowercase().starts_with(".alter") {
            if let Some(header) = current_header.take() {
                alters.push((header, std::mem::take(&mut current_lines)));
            }
            current_header = Some(stripped.to_owned());
            continue;
        }
        if current_header.is_none() {
            base.push(line.to_owned());
        } else {
            current_lines.push(line.to_owned());
        }
    }
    if let Some(header) = current_header {
        alters.push((header, current_lines));
    }
    let base_text = case_text(&base, end_line.as_deref());
    let mut cases = vec![DeckCase {
        name: format!("{stem}__base"),
        text: base_text.clone(),
        kind: CaseKind::Base,
    }];
    for (index, (header, body)) in alters.into_iter().enumerate() {
        let suffix = case_suffix(&header, index + 1);
        let name = format!("{stem}__{suffix}");
        cases.push(DeckCase {
            name,
            text: case_text(&[base.clone(), body].concat(), end_line.as_deref()),
            kind: CaseKind::Alter,
        });
    }
    cases
}

fn case_text(lines: &[String], end_line: Option<&str>) -> String {
    let body = lines.join("\n").trim().to_owned();
    let body = match end_line {
        Some(end) if body.is_empty() => end.to_owned(),
        Some(end) => format!("{body}\n{end}"),
        None => body,
    };
    format!("{body}\n")
}

fn case_suffix(header: &str, index: usize) -> String {
    let mut words = header.split_whitespace();
    let _directive = words.next();
    let label = words.collect::<Vec<_>>().join(" ");
    if label.is_empty() {
        return format!("alter_{index:03}");
    }
    let mut sanitized = label
        .chars()
        .map(|character| {
            if character.is_ascii_alphanumeric() || character == '_' {
                character.to_ascii_lowercase()
            } else {
                '_'
            }
        })
        .collect::<String>();
    while sanitized.starts_with('_') {
        sanitized.remove(0);
    }
    while sanitized.ends_with('_') {
        sanitized.pop();
    }
    if sanitized.is_empty() {
        format!("alter_{index:03}")
    } else {
        format!("alter_{index:03}_{sanitized}")
    }
}

fn strip_hspice_comment(line: &str) -> String {
    let mut quote = None;
    for (index, character) in line.char_indices() {
        if matches!(character, '\'' | '"') && quote.is_none() {
            quote = Some(character);
        } else if quote == Some(character) {
            quote = None;
        } else if character == '$' && quote.is_none() {
            return line[..index].to_owned();
        }
    }
    line.to_owned()
}

fn logical_lines(text: &str) -> Vec<String> {
    let mut lines = Vec::new();
    let mut current = String::new();
    for raw in text.lines() {
        let stripped = strip_hspice_comment(raw).trim().to_owned();
        if stripped.is_empty() || stripped.starts_with('*') {
            continue;
        }
        if let Some(rest) = stripped.strip_prefix('+') {
            current.push(' ');
            current.push_str(rest.trim());
        } else {
            if !current.is_empty() {
                lines.push(std::mem::take(&mut current));
            }
            current = stripped;
        }
    }
    if !current.is_empty() {
        lines.push(current);
    }
    lines
}

fn tokens(line: &str) -> Vec<String> {
    let characters = line.chars().collect::<Vec<_>>();
    let mut output = Vec::new();
    let mut cursor = 0;
    while cursor < characters.len() {
        while cursor < characters.len() && characters[cursor].is_whitespace() {
            cursor += 1;
        }
        if cursor == characters.len() {
            break;
        }
        let start = cursor;
        if matches!(characters[cursor], '\'' | '"') {
            let quote = characters[cursor];
            cursor += 1;
            while cursor < characters.len() {
                let character = characters[cursor];
                cursor += 1;
                if character == quote {
                    break;
                }
            }
        } else {
            while cursor < characters.len() && !characters[cursor].is_whitespace() {
                cursor += 1;
            }
        }
        output.push(characters[start..cursor].iter().collect());
    }
    output
}

fn clean_path(token: &str) -> String {
    token.trim_matches(['\'', '"']).to_owned()
}

/// Mirrors the upstream directive, include, library, and unsupported audit.
pub fn audit_deck(text: &str) -> DeckAudit {
    let supported = SUPPORTED_DIRECTIVES
        .iter()
        .copied()
        .collect::<BTreeSet<_>>();
    let mut directive_counts = BTreeMap::new();
    let mut includes = Vec::new();
    let mut libraries = Vec::new();
    let mut unsupported_directives = Vec::new();
    for line in logical_lines(text) {
        if !line.starts_with('.') {
            continue;
        }
        let fields = tokens(&line);
        let Some(directive) = fields.first().map(|field| field.to_ascii_lowercase()) else {
            continue;
        };
        *directive_counts.entry(directive.clone()).or_insert(0) += 1;
        if matches!(directive.as_str(), ".include" | ".inc") && fields.len() >= 2 {
            includes.push(clean_path(&fields[1]));
        }
        if directive == ".lib" && fields.len() >= 2 {
            libraries.push(LibraryReference {
                path: clean_path(&fields[1]),
                section: fields.get(2).map(|field| clean_path(field)),
            });
        }
        if !supported.contains(directive.as_str()) {
            unsupported_directives.push(directive);
        }
    }
    DeckAudit {
        directive_counts,
        includes,
        libraries,
        unsupported_directives,
    }
}

fn classify_dependency(reference: &str) -> DependencyAdmission {
    let path = Path::new(reference);
    if path.is_absolute() {
        return DependencyAdmission::AbsoluteNotStaged;
    }
    if path
        .components()
        .next()
        .is_some_and(|component| matches!(component, std::path::Component::ParentDir))
    {
        return DependencyAdmission::LexicallyEscapesSourceRoot;
    }
    DependencyAdmission::RelativeRequiresSourceRoot
}

fn has_post_option(line: &str) -> bool {
    let fields = tokens(line);
    fields
        .first()
        .is_some_and(|field| field.eq_ignore_ascii_case(".option"))
        && fields[1..].iter().any(|field| {
            field.eq_ignore_ascii_case("post") || field.to_ascii_lowercase().starts_with("post=")
        })
}

const PWL_TIME_UNITS: [(&str, f64); 6] = [
    ("fs", 1e-15),
    ("ps", 1e-12),
    ("ns", 1e-9),
    ("us", 1e-6),
    ("ms", 1e-3),
    ("s", 1.0),
];

fn parse_pwl_time(token: &str) -> Option<(f64, String)> {
    let lower = token.to_ascii_lowercase();
    for (unit, scale) in PWL_TIME_UNITS {
        if let Some(number) = lower.strip_suffix(unit) {
            if number.is_empty()
                || !number
                    .chars()
                    .all(|character| character.is_ascii_digit() || ".eE+-".contains(character))
            {
                continue;
            }
            let seconds = number.parse::<f64>().ok()? * scale;
            return Some((seconds, unit.to_owned()));
        }
    }
    None
}

fn is_pwl_value(token: &str) -> bool {
    !token.is_empty()
        && token
            .chars()
            .all(|character| character.is_ascii_digit() || ".eE+-".contains(character))
}

fn parse_pwl_points(text: &str) -> Vec<(f64, String)> {
    let fields = text.split_whitespace().collect::<Vec<_>>();
    let mut points = Vec::new();
    for pair in fields.windows(2) {
        let Some((seconds, _unit)) = parse_pwl_time(pair[0]) else {
            continue;
        };
        if is_pwl_value(pair[1]) {
            points.push((seconds, pair[1].to_owned()));
        }
    }
    points
}

fn parse_repeat_line(line: &str) -> Option<(f64, String, Option<String>)> {
    let trimmed = line.trim_start();
    let remainder = trimmed.strip_prefix('+')?.trim_start();
    let remainder_lower = remainder.to_ascii_lowercase();
    let mut cursor = 0;
    if !remainder_lower[cursor..].starts_with('r') {
        return None;
    }
    cursor += 1;
    while remainder
        .as_bytes()
        .get(cursor)
        .is_some_and(u8::is_ascii_whitespace)
    {
        cursor += 1;
    }
    if remainder.as_bytes().get(cursor) != Some(&b'=') {
        return None;
    }
    cursor += 1;
    while remainder
        .as_bytes()
        .get(cursor)
        .is_some_and(u8::is_ascii_whitespace)
    {
        cursor += 1;
    }
    let number_start = cursor;
    while remainder.as_bytes().get(cursor).is_some_and(|character| {
        character.is_ascii_digit() || matches!(character, b'.' | b'e' | b'E' | b'+' | b'-')
    }) {
        cursor += 1;
    }
    if cursor == number_start {
        return None;
    }
    let number_text = remainder.get(number_start..cursor)?.to_owned();
    let number = number_text.parse::<f64>().ok()?;
    let unit_start = cursor;
    while remainder
        .as_bytes()
        .get(cursor)
        .is_some_and(u8::is_ascii_alphabetic)
    {
        cursor += 1;
    }
    let unit = remainder.get(unit_start..cursor)?;
    let scale = PWL_TIME_UNITS
        .iter()
        .find(|(candidate, _)| candidate.eq_ignore_ascii_case(unit))
        .map(|(_, scale)| *scale)?;
    while remainder
        .as_bytes()
        .get(cursor)
        .is_some_and(u8::is_ascii_whitespace)
    {
        cursor += 1;
    }
    if remainder.as_bytes().get(cursor) != Some(&b')') {
        return None;
    }
    cursor += 1;
    while remainder
        .as_bytes()
        .get(cursor)
        .is_some_and(u8::is_ascii_whitespace)
    {
        cursor += 1;
    }
    let multiplicity = if remainder_lower[cursor..].starts_with('m') {
        cursor += 1;
        while remainder
            .as_bytes()
            .get(cursor)
            .is_some_and(u8::is_ascii_whitespace)
        {
            cursor += 1;
        }
        if remainder.as_bytes().get(cursor) != Some(&b'=') {
            return None;
        }
        cursor += 1;
        while remainder
            .as_bytes()
            .get(cursor)
            .is_some_and(u8::is_ascii_whitespace)
        {
            cursor += 1;
        }
        let value_start = cursor;
        while remainder
            .as_bytes()
            .get(cursor)
            .is_some_and(|character| !character.is_ascii_whitespace())
        {
            cursor += 1;
        }
        Some(remainder.get(value_start..cursor)?.to_owned())
    } else {
        None
    };
    if !remainder[cursor..].trim().is_empty() {
        return None;
    }
    Some((number * scale, format!("{number_text}{unit}"), multiplicity))
}

fn current_pwl_open(line: &str) -> Option<usize> {
    if !line.starts_with(['I', 'i']) {
        return None;
    }
    let first_space = line.find(char::is_whitespace)?;
    if first_space <= 1 {
        return None;
    }
    let lower = line.to_ascii_lowercase();
    let pwl = lower.rfind("pwl")?;
    if pwl > 0 && line.as_bytes()[pwl - 1].is_ascii_alphanumeric() {
        return None;
    }
    let mut open = pwl + 3;
    while line
        .as_bytes()
        .get(open)
        .is_some_and(u8::is_ascii_whitespace)
    {
        open += 1;
    }
    if line.as_bytes().get(open) != Some(&b'(') {
        return None;
    }
    Some(open)
}

fn format_pwl_number(value: f64) -> String {
    if value == 0.0 {
        return "0".to_owned();
    }
    let absolute = value.abs();
    if (1e-4..1e6).contains(&absolute) {
        let exponent = absolute.log10().floor() as i32;
        let decimals = (5 - exponent).max(0) as usize;
        let mut result = format!("{:.*}", decimals, value);
        while result.ends_with('0') {
            result.pop();
        }
        if result.ends_with('.') {
            result.pop();
        }
        return result;
    }
    let scientific = format!("{value:.5e}");
    let (mantissa, exponent) = scientific
        .split_once('e')
        .expect("Rust scientific formatting includes an exponent");
    let mut mantissa = mantissa
        .trim_end_matches('0')
        .trim_end_matches('.')
        .to_owned();
    if mantissa == "-0" {
        mantissa = "0".to_owned();
    }
    let exponent = exponent.parse::<i32>().expect("Rust exponent is numeric");
    format!("{mantissa}e{exponent:+03}")
}

fn rewrite_current_pwl_source(
    group: &str,
    repeat_start: f64,
    repeat_end: f64,
    points: &[(f64, String)],
    multiplicity: Option<&str>,
) -> String {
    let mut source = group.to_owned();
    source.replace_range(0..1, "B");
    let lower = source.to_ascii_lowercase();
    let open = source
        .rfind('(')
        .expect("current PWL group has an opening parenthesis");
    let pwl = lower[..open]
        .rfind("pwl")
        .expect("current PWL group has a PWL function");
    let multiplier = multiplicity.map_or_else(String::new, |value| format!("({value}) * "));
    source.replace_range(pwl..open + 1, &format!("I = {multiplier}pwl("));
    let start = format_pwl_number(repeat_start / 1e-12);
    let period = format_pwl_number((repeat_end - repeat_start) / 1e-12);
    let mut lines = vec![format!(
        "{source}(time <= {start}ps ? time : {start}ps + (time - {start}ps) - {period}ps * floor((time - {start}ps) / {period}ps)),"
    )];
    for (chunk_index, chunk) in points.chunks(4).enumerate() {
        let values = chunk
            .iter()
            .map(|(seconds, value)| format!("{}ps, {value}", format_pwl_number(seconds / 1e-12)))
            .collect::<Vec<_>>()
            .join(", ");
        let suffix = if (chunk_index + 1) * 4 >= points.len() {
            ""
        } else {
            ","
        };
        lines.push(format!("+ {values}{suffix}"));
    }
    lines.push("+ )".to_owned());
    lines.join("\n")
}

fn rewrite_current_pwl_repeats_for_ngspice(
    text: &str,
    actions: &mut Vec<ConversionAction>,
    unsupported: &mut Vec<UnsupportedIssue>,
) -> String {
    let lines = text.split_inclusive('\n').collect::<Vec<_>>();
    let mut output = String::new();
    let mut index = 0;
    while index < lines.len() {
        let raw_line = lines[index];
        let line = raw_line.trim_end_matches(['\r', '\n']);
        let Some(open) = current_pwl_open(line) else {
            output.push_str(raw_line);
            index += 1;
            continue;
        };
        let mut point_text = line[open + 1..].to_owned();
        let mut repeat = None;
        let mut end_index = index + 1;
        while end_index < lines.len() {
            let candidate = lines[end_index].trim_end_matches(['\r', '\n']);
            if let Some(parsed) = parse_repeat_line(candidate) {
                repeat = Some(parsed);
                break;
            }
            point_text.push(' ');
            point_text.push_str(candidate);
            end_index += 1;
        }
        let Some((repeat_start, repeat_text, multiplicity)) = repeat else {
            output.push_str(raw_line);
            index += 1;
            continue;
        };
        let points = parse_pwl_points(&point_text);
        let first_line = line.to_owned();
        let repeat_end = points.last().map(|(seconds, _)| *seconds);
        if !points
            .iter()
            .any(|(seconds, _)| (*seconds - repeat_start).abs() <= 1e-18)
        {
            unsupported.push(UnsupportedIssue {
                line: first_line,
                reason: "current_pwl_repeat_point_not_found".to_owned(),
            });
            output.push_str(raw_line);
            index += 1;
            continue;
        }
        let Some(repeat_end) = repeat_end else {
            unsupported.push(UnsupportedIssue {
                line: first_line,
                reason: "current_pwl_repeat_point_not_found".to_owned(),
            });
            output.push_str(raw_line);
            index += 1;
            continue;
        };
        if repeat_end <= repeat_start {
            unsupported.push(UnsupportedIssue {
                line: first_line,
                reason: "invalid_current_pwl_repeat_window".to_owned(),
            });
            output.push_str(raw_line);
            index += 1;
            continue;
        }
        let group = &line[..open + 1];
        let converted = rewrite_current_pwl_source(
            group,
            repeat_start,
            repeat_end,
            &points,
            multiplicity.as_deref(),
        );
        actions.push(ConversionAction {
            kind: "rewrite_current_pwl_repeat".to_owned(),
            source: format!("{}... R={repeat_text}", group.trim()),
            target: format!(
                "behavioral current PWL: repeat {}ps to {}ps{}",
                format_pwl_number(repeat_start / 1e-12),
                format_pwl_number(repeat_end / 1e-12),
                multiplicity
                    .as_deref()
                    .map_or(String::new(), |value| format!("; preserves M={value}"))
            ),
        });
        output.push_str(&converted);
        if lines[end_index].ends_with('\n') {
            output.push('\n');
        }
        index = end_index + 1;
    }
    output
}

/// Mirrors the deterministic text conversions in `convert_hspice_deck`.
fn convert_deck(
    text: &str,
    backend: Backend,
) -> (String, Vec<ConversionAction>, Vec<UnsupportedIssue>) {
    if backend != Backend::Ngspice {
        return (text.to_owned(), Vec::new(), Vec::new());
    }
    let mut actions = Vec::new();
    let mut unsupported = Vec::new();
    let source_text = rewrite_current_pwl_repeats_for_ngspice(text, &mut actions, &mut unsupported);
    let mut output = Vec::new();
    for raw in source_text.lines() {
        let stripped = raw.trim();
        let lower = stripped.to_ascii_lowercase();
        if lower.starts_with(".inc ") {
            let target = format!(
                ".include {}",
                stripped
                    .split_once(char::is_whitespace)
                    .map_or("", |(_, rest)| rest)
            );
            actions.push(ConversionAction {
                kind: "rewrite".to_owned(),
                source: stripped.to_owned(),
                target: target.clone(),
            });
            output.push(target);
        } else if lower.starts_with(".probe ") {
            let target = format!(
                ".print {}",
                stripped
                    .split_once(char::is_whitespace)
                    .map_or("", |(_, rest)| rest)
            );
            actions.push(ConversionAction {
                kind: "rewrite".to_owned(),
                source: stripped.to_owned(),
                target: target.clone(),
            });
            output.push(target);
        } else if has_post_option(stripped) {
            actions.push(ConversionAction {
                kind: "drop_option".to_owned(),
                source: stripped.to_owned(),
                target: String::new(),
            });
        } else {
            output.push(raw.to_owned());
        }
    }
    let deck_text = format!("{}\n", output.join("\n").trim());
    (deck_text, actions, unsupported)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn all_backend_and_execute_branches_are_explicit() {
        for backend in Backend::ALL {
            for execute in [false, true] {
                let request = RunHspiceRequest::new(backend.name(), "runs", execute).unwrap();
                let admission = admit_run_hspice("demo", ".tran 1p 1n\n.end\n", request).unwrap();
                assert_eq!(admission.backend, backend);
                assert_eq!(admission.execute, execute);
                assert_eq!(
                    admission.execution_stage,
                    match (backend, execute) {
                        (_, false) => ExecutionStage::NotExecuted,
                        (Backend::Native, true) => ExecutionStage::NativeEngine,
                        (Backend::Ngspice, true) => ExecutionStage::Ngspice,
                        (Backend::Xyce, true) => ExecutionStage::Xyce,
                        (Backend::XyceXdm, true) => ExecutionStage::XdmThenXyce,
                    }
                );
            }
        }
    }

    #[test]
    fn alter_split_matches_pinned_case_names_and_end_ownership() {
        let cases = split_alter_cases(
            ".param c=1u\n.tran 1p 1n\n.alter high decap\n.param c=2u\n.alter slow\n.param c=3u\n.end\n",
            "deck",
        );
        assert_eq!(
            cases
                .iter()
                .map(|case| case.name.as_str())
                .collect::<Vec<_>>(),
            [
                "deck__base",
                "deck__alter_001_high_decap",
                "deck__alter_002_slow"
            ]
        );
        assert!(cases.iter().all(|case| case.text.ends_with(".end\n")));
        assert!(cases[1].text.contains(".param c=2u"));
        assert!(!cases[1].text.contains(".param c=3u"));
    }

    #[test]
    fn audit_and_ngspice_conversion_cover_includes_libs_measure_and_actions() {
        let source = ".inc 'models.inc'\n.lib './corners.lib' tt\n.probe tran v(out)\n.measure tran m max v(out)\n.option post=2\n.end\n";
        let audit = audit_deck(source);
        assert_eq!(audit.includes, ["models.inc"]);
        assert_eq!(audit.libraries[0].path, "./corners.lib");
        assert_eq!(audit.directive_counts[".measure"], 1);
        let admission = admit_run_hspice(
            "deck",
            source,
            RunHspiceRequest::new("ngspice", "runs", false).unwrap(),
        )
        .unwrap();
        assert_eq!(
            admission.cases[0].preparation_status,
            PreparationStatus::AutoConverted
        );
        assert!(
            admission.cases[0]
                .deck_text
                .contains(".include 'models.inc'")
        );
        assert!(admission.cases[0].deck_text.contains(".print tran v(out)"));
        assert!(!admission.cases[0].deck_text.contains("post=2"));
    }

    #[test]
    fn unsupported_directive_is_reported_without_silent_deletion() {
        let admission = admit_run_hspice(
            "deck",
            ".fft v(out)\n.end\n",
            RunHspiceRequest::new("native", "runs", false).unwrap(),
        )
        .unwrap();
        assert_eq!(
            admission.cases[0].preparation_status,
            PreparationStatus::Blocked
        );
        assert_eq!(admission.cases[0].audit.unsupported_directives, [".fft"]);
        assert!(admission.cases[0].deck_text.contains(".fft v(out)"));
    }

    #[test]
    fn xdm_plan_contains_two_stage_case_artifact() {
        let admission = admit_run_hspice(
            "deck",
            ".end\n",
            RunHspiceRequest::new("xyce-xdm", "runs", true).unwrap(),
        )
        .unwrap();
        assert!(
            admission.cases[0]
                .output_paths
                .iter()
                .any(|path| path.ends_with("/case.sp"))
        );
        assert_eq!(admission.execution_stage, ExecutionStage::XdmThenXyce);
        assert!(admission.external_solver_required);
        assert_eq!(admission.numerical_parity, ParityStatus::NotEvaluated);
    }

    #[test]
    fn invalid_backend_and_empty_stem_fail_closed() {
        assert_eq!(
            RunHspiceRequest::new("hspice", "runs", false).unwrap_err(),
            DirectPortError::UnsupportedBackend("hspice".to_owned())
        );
        assert_eq!(
            admit_run_hspice(
                "",
                ".end\n",
                RunHspiceRequest::new("native", "runs", false).unwrap()
            )
            .unwrap_err(),
            DirectPortError::EmptyDeckStem
        );
    }
}
