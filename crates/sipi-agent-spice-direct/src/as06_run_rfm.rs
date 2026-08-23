//! AS-06 direct port for `run-rfm`.
//!
//! The parser and frequency-response preflight are portable and numerical.
//! Native/ngspice execution remains an explicit caller-selected process path;
//! no simulator result is invented when the executable is unavailable.

use std::fmt::{Display, Formatter};
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

use num_complex::Complex64 as Complex;
use serde_json::json;
use sha2::{Digest, Sha256};

pub const UPSTREAM_COMMIT: &str = "2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5";
pub const UPSTREAM_TREE: &str = "b6bde97128030d6cea0d68b2f0a35d807be8c402";
pub const WORKFLOW_ID: &str = "AS-06";
pub const WORKFLOW_NAME: &str = "run-rfm";
const MAX_RFM_BYTES: usize = 16 * 1024 * 1024;
const MAX_PORTS: usize = 64;
const RESPONSE_SAMPLES: usize = 65;
const MAX_ARTIFACT_BYTES: usize = 8 * 1024 * 1024;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum RfmBackend {
    Native,
    Ngspice,
}

impl RfmBackend {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Native => "native",
            Self::Ngspice => "ngspice",
        }
    }

    pub fn parse(value: &str) -> Result<Self, RfmError> {
        match value {
            "native" => Ok(Self::Native),
            "ngspice" => Ok(Self::Ngspice),
            other => Err(RfmError::InvalidOption(format!(
                "unsupported backend '{other}'"
            ))),
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct RfmModel {
    pub version: i64,
    pub nports: usize,
    pub matrix_type: String,
    pub z0: f64,
    pub poles: Vec<Complex>,
    pub residues: Vec<Vec<Complex>>, // response-major, union pole basis
    pub constant: Vec<Complex>,
}

impl RfmModel {
    pub fn response_count(&self) -> usize {
        self.nports * self.nports
    }

    /// Match the pinned importer’s effective order: a conjugate pair counts
    /// as two state poles even though RFM stores its positive-imaginary
    /// representative once.
    pub fn effective_order(&self) -> usize {
        self.poles
            .iter()
            .map(|pole| if pole.im != 0.0 { 2 } else { 1 })
            .sum()
    }

    /// RFM has no proportional term; expose the importer’s zero-valued
    /// coefficient contract for callers that inspect the canonical model.
    pub fn proportional_coeff(&self) -> Vec<f64> {
        vec![0.0; self.response_count()]
    }

    pub fn evaluate_s(&self, frequency_hz: f64) -> Vec<Complex> {
        let s = Complex::new(0.0, 2.0 * std::f64::consts::PI * frequency_hz);
        (0..self.response_count())
            .map(|response| {
                self.constant[response]
                    + self.residues[response]
                        .iter()
                        .zip(&self.poles)
                        .map(|(residue, pole)| {
                            let primary = *residue / (s - *pole);
                            if pole.im != 0.0 {
                                primary + residue.conj() / (s - pole.conj())
                            } else {
                                primary
                            }
                        })
                        .sum::<Complex>()
            })
            .collect()
    }

    /// Evaluate every requested frequency using the same response-major
    /// ordering as the upstream numpy implementation.
    pub fn evaluate_s_many(&self, frequencies_hz: &[f64]) -> Result<Vec<Vec<Complex>>, RfmError> {
        if frequencies_hz.is_empty() {
            return Err(RfmError::InvalidOption(
                "frequency vector must be non-empty".to_owned(),
            ));
        }
        if frequencies_hz
            .iter()
            .any(|frequency| !frequency.is_finite())
        {
            return Err(RfmError::InvalidOption(
                "frequency vector values must be finite".to_owned(),
            ));
        }
        Ok(frequencies_hz
            .iter()
            .map(|frequency| self.evaluate_s(*frequency))
            .collect())
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct RunRfmRequest {
    pub deck: PathBuf,
    pub rfm: PathBuf,
    pub output_root: PathBuf,
    pub backend: RfmBackend,
    pub subckt_name: String,
    pub ngspice: String,
    pub code_model: Option<PathBuf>,
    pub native_engine: Option<PathBuf>,
    pub dotnet: String,
    pub execute: bool,
}

impl RunRfmRequest {
    pub fn new(
        deck: impl Into<PathBuf>,
        rfm: impl Into<PathBuf>,
        backend: &str,
        output_root: impl Into<PathBuf>,
    ) -> Result<Self, RfmError> {
        let deck = deck.into();
        let rfm = rfm.into();
        let output_root = output_root.into();
        if deck.as_os_str().is_empty()
            || rfm.as_os_str().is_empty()
            || output_root.as_os_str().is_empty()
        {
            return Err(RfmError::InvalidOption(
                "deck, rfm, and output_root are required".to_owned(),
            ));
        }
        Ok(Self {
            deck,
            rfm,
            output_root,
            backend: RfmBackend::parse(backend)?,
            subckt_name: "rfm_direct".to_owned(),
            ngspice: "ngspice".to_owned(),
            code_model: None,
            native_engine: None,
            dotnet: "dotnet".to_owned(),
            execute: false,
        })
    }

    pub fn with_subckt_name(mut self, value: impl Into<String>) -> Self {
        self.subckt_name = value.into();
        self
    }

    pub fn with_native_engine(mut self, path: impl Into<PathBuf>) -> Self {
        self.native_engine = Some(path.into());
        self
    }

    pub fn with_code_model(mut self, path: impl Into<PathBuf>) -> Self {
        self.code_model = Some(path.into());
        self
    }

    pub fn execute(mut self, value: bool) -> Self {
        self.execute = value;
        self
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum RfmError {
    InvalidOption(String),
    Input(String),
    Parse(String),
    Unsupported(String),
    Execution(String),
    Output(String),
}

impl Display for RfmError {
    fn fmt(&self, f: &mut Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::InvalidOption(value) => write!(f, "invalid run-rfm option: {value}"),
            Self::Input(value) => write!(f, "run-rfm input error: {value}"),
            Self::Parse(value) => write!(f, "run-rfm RFM parse error: {value}"),
            Self::Unsupported(value) => write!(f, "unsupported run-rfm path: {value}"),
            Self::Execution(value) => write!(f, "run-rfm execution error: {value}"),
            Self::Output(value) => write!(f, "run-rfm output error: {value}"),
        }
    }
}

impl std::error::Error for RfmError {}

#[derive(Clone, Debug, PartialEq)]
pub struct RunRfmResult {
    pub status: String,
    pub report: PathBuf,
    pub output_root: PathBuf,
    pub response_max_error: f64,
    pub response_samples: usize,
    pub model: RfmModel,
}

fn finite(value: f64, label: &str) -> Result<f64, RfmError> {
    if value.is_finite() {
        Ok(value)
    } else {
        Err(RfmError::Parse(format!("{label} must be finite")))
    }
}

fn read_lines(path: &Path) -> Result<Vec<(usize, String)>, RfmError> {
    let bytes = fs::read(path).map_err(|error| RfmError::Input(error.to_string()))?;
    if bytes.len() > MAX_RFM_BYTES {
        return Err(RfmError::Parse("RFM input exceeds byte budget".to_owned()));
    }
    let text = std::str::from_utf8(&bytes).map_err(|error| RfmError::Parse(error.to_string()))?;
    let lines = text
        .lines()
        .enumerate()
        .filter_map(|(index, raw)| {
            let value = raw.trim();
            if value.is_empty()
                || value.starts_with('*')
                || value.starts_with('!')
                || value.starts_with('#')
            {
                None
            } else {
                Some((index + 1, value.to_owned()))
            }
        })
        .collect::<Vec<_>>();
    if lines.is_empty() {
        return Err(RfmError::Parse("RFM file is empty".to_owned()));
    }
    Ok(lines)
}

fn expect(
    lines: &[(usize, String)],
    index: &mut usize,
    keyword: &str,
    count: usize,
    path: &Path,
) -> Result<(usize, Vec<String>), RfmError> {
    let (line_number, text) = lines.get(*index).ok_or_else(|| {
        RfmError::Parse(format!(
            "{}: expected {keyword}, reached EOF",
            path.display()
        ))
    })?;
    let tokens = text
        .split_whitespace()
        .map(str::to_owned)
        .collect::<Vec<_>>();
    if tokens.len() != count || !tokens[0].eq_ignore_ascii_case(keyword) {
        return Err(RfmError::Parse(format!(
            "{}:{line_number}: expected {keyword} with {} value(s)",
            path.display(),
            count.saturating_sub(1)
        )));
    }
    *index += 1;
    Ok((*line_number, tokens))
}

fn parse_float(token: &str, path: &Path, line: usize, label: &str) -> Result<f64, RfmError> {
    let value = token.replace(['d', 'D'], "e").parse::<f64>().map_err(|_| {
        RfmError::Parse(format!(
            "{}:{line}: invalid {label} '{token}'",
            path.display()
        ))
    })?;
    finite(value, label)
}

/// Parse the pinned Cadence Broadband SPICE `VERSION 200600`, S-matrix RFM.
pub fn parse_cadence_rfm(path: impl AsRef<Path>) -> Result<RfmModel, RfmError> {
    let path = path.as_ref();
    let lines = read_lines(path)?;
    let required = ["VERSION", "NPORT", "MATRIX_TYPE", "Z0"];
    let mut headers = std::collections::BTreeMap::new();
    let mut index = 0usize;
    while index < lines.len()
        && !lines[index]
            .1
            .split_whitespace()
            .next()
            .is_some_and(|value| value.eq_ignore_ascii_case("BEGIN"))
    {
        let (line, text) = &lines[index];
        let tokens = text.split_whitespace().collect::<Vec<_>>();
        if tokens.len() != 2
            || !required
                .iter()
                .any(|key| key.eq_ignore_ascii_case(tokens[0]))
        {
            return Err(RfmError::Parse(format!(
                "{}:{line}: unsupported RFM header",
                path.display()
            )));
        }
        let key = tokens[0].to_ascii_uppercase();
        if headers
            .insert(key.clone(), (*line, tokens[1].to_owned()))
            .is_some()
        {
            return Err(RfmError::Parse(format!(
                "{}:{line}: duplicate RFM header {key}",
                path.display()
            )));
        }
        index += 1;
    }
    for key in required {
        if !headers.contains_key(key) {
            return Err(RfmError::Parse(format!(
                "{}: missing RFM header {key}",
                path.display()
            )));
        }
    }
    let version = headers["VERSION"]
        .1
        .parse::<i64>()
        .map_err(|_| RfmError::Parse("VERSION must be an integer".to_owned()))?;
    if version != 200600 {
        return Err(RfmError::Unsupported(format!("RFM VERSION {version}")));
    }
    let nports = headers["NPORT"]
        .1
        .parse::<usize>()
        .map_err(|_| RfmError::Parse("NPORT must be an integer".to_owned()))?;
    if nports == 0 || nports > MAX_PORTS {
        return Err(RfmError::Parse(
            "NPORT is outside the bounded range".to_owned(),
        ));
    }
    let matrix_type = headers["MATRIX_TYPE"].1.to_ascii_uppercase();
    if matrix_type != "S" {
        return Err(RfmError::Unsupported(format!("MATRIX_TYPE {matrix_type}")));
    }
    let z0 = parse_float(&headers["Z0"].1, path, headers["Z0"].0, "Z0")?;
    if z0 <= 0.0 {
        return Err(RfmError::Parse("Z0 must be positive".to_owned()));
    }
    let response_count = nports * nports;
    let mut constants = vec![Complex::new(0.0, 0.0); response_count];
    let mut terms: Vec<Option<Vec<(Complex, Complex)>>> = vec![None; response_count];
    let mut poles = Vec::<Complex>::new();
    while index < lines.len() {
        let (line, begin) = expect(&lines, &mut index, "BEGIN", 3, path)?;
        let row = begin[1].parse::<usize>().map_err(|_| {
            RfmError::Parse(format!("{}:{line}: invalid BEGIN row", path.display()))
        })?;
        let column = begin[2].parse::<usize>().map_err(|_| {
            RfmError::Parse(format!("{}:{line}: invalid BEGIN column", path.display()))
        })?;
        if row == 0 || row > nports || column == 0 || column > nports {
            return Err(RfmError::Parse(format!(
                "{}:{line}: BEGIN indices out of range",
                path.display()
            )));
        }
        let response = (row - 1) * nports + column - 1;
        if terms[response].is_some() {
            return Err(RfmError::Parse(format!(
                "{}:{line}: duplicate response block",
                path.display()
            )));
        }
        let (const_line, const_tokens) = expect(&lines, &mut index, "CONST", 2, path)?;
        constants[response] = Complex::new(
            parse_float(&const_tokens[1], path, const_line, "CONST")?,
            0.0,
        );
        if lines.get(index).is_some_and(|(_, value)| {
            value
                .split_whitespace()
                .next()
                .is_some_and(|token| token.eq_ignore_ascii_case("C"))
        }) {
            let (line, tokens) = expect(&lines, &mut index, "C", 2, path)?;
            if parse_float(&tokens[1], path, line, "C")? != 0.0 {
                return Err(RfmError::Unsupported(
                    "non-zero proportional C term".to_owned(),
                ));
            }
        }
        if lines.get(index).is_some_and(|(_, value)| {
            value
                .split_whitespace()
                .next()
                .is_some_and(|token| token.eq_ignore_ascii_case("DELAY"))
        }) {
            let (line, tokens) = expect(&lines, &mut index, "DELAY", 2, path)?;
            if parse_float(&tokens[1], path, line, "DELAY")? != 0.0 {
                return Err(RfmError::Unsupported("non-zero delay".to_owned()));
            }
        }
        let (line, real_header) = expect(&lines, &mut index, "BEGIN_REAL", 2, path)?;
        let real_count = real_header[1].parse::<usize>().map_err(|_| {
            RfmError::Parse(format!(
                "{}:{line}: invalid real-pole count",
                path.display()
            ))
        })?;
        let mut response_terms = Vec::new();
        for _ in 0..real_count {
            let (line, row) = lines
                .get(index)
                .ok_or_else(|| RfmError::Parse("truncated real-pole block".to_owned()))?;
            let fields = row.split_whitespace().collect::<Vec<_>>();
            if fields.len() != 2 {
                return Err(RfmError::Parse(format!(
                    "{}:{line}: real-pole row requires two values",
                    path.display()
                )));
            }
            let damping = parse_float(fields[0], path, *line, "real damping")?;
            let residue = parse_float(fields[1], path, *line, "real residue")?;
            if damping <= 0.0 {
                return Err(RfmError::Parse(format!(
                    "{}:{line}: real damping must be positive",
                    path.display()
                )));
            }
            response_terms.push((Complex::new(-damping, 0.0), Complex::new(residue, 0.0)));
            index += 1;
        }
        let (line, complex_header) = expect(&lines, &mut index, "BEGIN_COMPLEX", 2, path)?;
        let complex_count = complex_header[1].parse::<usize>().map_err(|_| {
            RfmError::Parse(format!(
                "{}:{line}: invalid complex-pole count",
                path.display()
            ))
        })?;
        for _ in 0..complex_count {
            let (line, row) = lines
                .get(index)
                .ok_or_else(|| RfmError::Parse("truncated complex-pole block".to_owned()))?;
            let fields = row.split_whitespace().collect::<Vec<_>>();
            if fields.len() != 4 {
                return Err(RfmError::Parse(format!(
                    "{}:{line}: complex-pole row requires four values",
                    path.display()
                )));
            }
            let damping = parse_float(fields[0], path, *line, "complex damping")?;
            let omega = parse_float(fields[1], path, *line, "complex omega")?;
            let real = parse_float(fields[2], path, *line, "complex residue real")?;
            let imag = parse_float(fields[3], path, *line, "complex residue imag")?;
            if damping <= 0.0 || omega == 0.0 {
                return Err(RfmError::Parse(format!(
                    "{}:{line}: complex damping must be positive and omega non-zero",
                    path.display()
                )));
            }
            let mut pole = Complex::new(-damping, -omega);
            let mut residue = Complex::new(real, imag);
            if pole.im < 0.0 {
                pole = pole.conj();
                residue = residue.conj();
            }
            response_terms.push((pole, residue));
            index += 1;
        }
        let _ = expect(&lines, &mut index, "END", 1, path)?;
        for (pole, _) in &response_terms {
            if !poles.contains(pole) {
                poles.push(*pole);
            }
        }
        terms[response] = Some(response_terms);
    }
    if terms.iter().any(Option::is_none) {
        return Err(RfmError::Parse(
            "one or more response blocks are missing".to_owned(),
        ));
    }
    let residues = terms
        .into_iter()
        .map(|entry| {
            let mut row = vec![Complex::new(0.0, 0.0); poles.len()];
            for (pole, residue) in entry.expect("missing terms was checked") {
                let index = poles
                    .iter()
                    .position(|candidate| *candidate == pole)
                    .expect("pole union contains response pole");
                row[index] += residue;
            }
            row
        })
        .collect::<Vec<_>>();
    Ok(RfmModel {
        version,
        nports,
        matrix_type,
        z0,
        poles,
        residues,
        constant: constants,
    })
}

pub fn write_cadence_rfm(path: impl AsRef<Path>, model: &RfmModel) -> Result<(), RfmError> {
    let path = path.as_ref();
    if model.version != 200600
        || model.nports == 0
        || model.nports > MAX_PORTS
        || model.matrix_type != "S"
        || !model.z0.is_finite()
        || model.z0 <= 0.0
        || model.poles.iter().any(|pole| {
            !pole.re.is_finite() || !pole.im.is_finite() || pole.re >= 0.0 || pole.im < 0.0
        })
        || model.constant.len() != model.response_count()
        || model.residues.len() != model.response_count()
        || model
            .residues
            .iter()
            .any(|row| row.len() != model.poles.len())
    {
        return Err(RfmError::Output(
            "RFM model dimensions, stability, or header fields are invalid".to_owned(),
        ));
    }
    if model.constant.iter().any(|value| {
        !value.re.is_finite()
            || !value.im.is_finite()
            || value.im.abs() > 1e-8 * value.re.abs().max(1.0)
    }) {
        return Err(RfmError::Unsupported(
            "RFM constant coefficients must be real".to_owned(),
        ));
    }
    for (pole_index, pole) in model.poles.iter().enumerate() {
        if pole.im == 0.0
            && model.residues.iter().any(|row| {
                let value = row[pole_index];
                !value.re.is_finite()
                    || !value.im.is_finite()
                    || value.im.abs() > 1e-8 * value.re.abs().max(1.0)
            })
        {
            return Err(RfmError::Unsupported(
                "RFM real-pole residues must be real".to_owned(),
            ));
        }
    }
    let mut text = format!(
        "VERSION {}\nNPORT {}\nMATRIX_TYPE {}\nZ0 {:.17e}\n",
        model.version, model.nports, model.matrix_type, model.z0
    );
    for row in 0..model.nports {
        for column in 0..model.nports {
            let response = row * model.nports + column;
            text.push_str(&format!(
                "BEGIN {} {}\nCONST {:.17e}\nC 0\nDELAY 0\n",
                row + 1,
                column + 1,
                model.constant[response].re
            ));
            let real = model
                .poles
                .iter()
                .enumerate()
                .filter(|(_, pole)| pole.im == 0.0)
                .collect::<Vec<_>>();
            text.push_str(&format!("BEGIN_REAL {}\n", real.len()));
            for (index, pole) in real {
                text.push_str(&format!(
                    "{:.17e} {:.17e}\n",
                    -pole.re, model.residues[response][index].re
                ));
            }
            let complex = model
                .poles
                .iter()
                .enumerate()
                .filter(|(_, pole)| pole.im > 0.0)
                .collect::<Vec<_>>();
            text.push_str(&format!("BEGIN_COMPLEX {}\n", complex.len()));
            for (index, pole) in complex {
                let residue = model.residues[response][index];
                text.push_str(&format!(
                    "{:.17e} {:.17e} {:.17e} {:.17e}\n",
                    -pole.re, -pole.im, residue.re, residue.im
                ));
            }
            text.push_str("END\n");
        }
    }
    if text.len() > MAX_ARTIFACT_BYTES {
        return Err(RfmError::Output(
            "RFM artifact exceeds byte budget".to_owned(),
        ));
    }
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|error| RfmError::Output(error.to_string()))?;
    }
    fs::write(path, text).map_err(|error| RfmError::Output(error.to_string()))
}

/// Write the portable wrapper used by the upstream `run-rfm`/HSPICE path.
/// The wrapper keeps positive/negative node pairs for every port; collapsing
/// them to one shared reference silently changes an N-port S-element.
pub fn write_cadence_rfm_wrapper(
    path: impl AsRef<Path>,
    rfm_path: impl AsRef<Path>,
    nports: usize,
    subcircuit_name: Option<&str>,
) -> Result<(), RfmError> {
    let path = path.as_ref();
    if nports == 0 || nports > MAX_PORTS {
        return Err(RfmError::InvalidOption(
            "nports is outside the bounded range".to_owned(),
        ));
    }
    let name = subcircuit_name.unwrap_or_else(|| {
        path.file_stem()
            .and_then(|v| v.to_str())
            .unwrap_or("rfm_wrapper")
    });
    if name.is_empty() || name.chars().any(char::is_whitespace) {
        return Err(RfmError::InvalidOption(
            "subcircuit_name must be a non-empty SPICE token".to_owned(),
        ));
    }
    let relative = pathdiff(
        rfm_path.as_ref(),
        path.parent().unwrap_or_else(|| Path::new(".")),
    )?;
    if relative.contains('\'') {
        return Err(RfmError::InvalidOption(
            "rfm path cannot contain a single quote".to_owned(),
        ));
    }
    let pairs = (1..=nports)
        .map(|index| format!("n{index} n{index}_ref"))
        .collect::<Vec<_>>();
    let mut lines = vec![format!(".subckt {name}")];
    for pair in &pairs {
        lines.push(format!("+ {pair}"));
    }
    lines.push("S1".to_owned());
    for pair in &pairs {
        lines.push(format!("+ {pair}"));
    }
    lines.extend([
        "+ mname=s_model".to_owned(),
        format!(".model s_model S n={nports}"),
        format!("+ rfmfile='{relative}'"),
        ".ends".to_owned(),
    ]);
    write_text(path, &(lines.join("\n") + "\n"))
}

/// Write the common-ground wrapper used when an HSPICE S-element exposes one
/// node per port.  The direct RFM device itself is differential, so every
/// positive node is paired with global ground without pretending that the
/// two-node wrapper is interchangeable with this contract.
pub fn write_cadence_rfm_common_ground_wrapper(
    path: impl AsRef<Path>,
    rfm_path: impl AsRef<Path>,
    nports: usize,
    subcircuit_name: Option<&str>,
) -> Result<(), RfmError> {
    let path = path.as_ref();
    if nports == 0 || nports > MAX_PORTS {
        return Err(RfmError::InvalidOption(
            "nports is outside the bounded range".to_owned(),
        ));
    }
    let name = subcircuit_name.unwrap_or_else(|| {
        path.file_stem()
            .and_then(|v| v.to_str())
            .unwrap_or("rfm_common_ground_wrapper")
    });
    if name.is_empty() || name.chars().any(char::is_whitespace) {
        return Err(RfmError::InvalidOption(
            "subcircuit_name must be a non-empty SPICE token".to_owned(),
        ));
    }
    let relative = pathdiff(
        rfm_path.as_ref(),
        path.parent().unwrap_or_else(|| Path::new(".")),
    )?;
    if relative.contains('\'') {
        return Err(RfmError::InvalidOption(
            "rfm path cannot contain a single quote".to_owned(),
        ));
    }
    let nodes = (1..=nports)
        .map(|index| format!("p{index}"))
        .collect::<Vec<_>>();
    let pairs = nodes
        .iter()
        .flat_map(|node| [node.clone(), "0".to_owned()])
        .collect::<Vec<_>>();
    let mut lines = vec![format!(".subckt {name} {}", nodes.join(" "))];
    lines.push(format!("S1 {} mname=s_model", pairs.join(" ")));
    lines.extend([
        format!(".model s_model S n={nports}"),
        format!("+ rfmfile='{relative}'"),
        ".ends".to_owned(),
    ]);
    write_text(path, &(lines.join("\n") + "\n"))
}

fn valid_spice_token(value: &str) -> bool {
    let mut chars = value.chars();
    chars
        .next()
        .is_some_and(|first| first.is_ascii_alphabetic() || first == '_')
        && chars.all(|character| character.is_ascii_alphanumeric() || "_.$".contains(character))
}

/// Write the XSPICE wrapper used by the pinned ngspice `run-rfm` branch.
/// Unlike the HSPICE S-element wrapper above, this is a vector code-model
/// instance with one common reference pin and one signal pin per port.
pub fn write_xspice_rfm_wrapper(
    path: impl AsRef<Path>,
    rfm_path: impl AsRef<Path>,
    nports: usize,
    subcircuit_name: &str,
) -> Result<(), RfmError> {
    let path = path.as_ref();
    if nports == 0 || nports > MAX_PORTS {
        return Err(RfmError::InvalidOption(
            "nports is outside the bounded range".to_owned(),
        ));
    }
    if !valid_spice_token(subcircuit_name) {
        return Err(RfmError::InvalidOption(
            "subcircuit_name is not a valid SPICE token".to_owned(),
        ));
    }
    let relative = pathdiff(
        rfm_path.as_ref(),
        path.parent().unwrap_or_else(|| Path::new(".")),
    )?;
    if relative
        .chars()
        .any(|character| matches!(character, '"' | '\n' | '\r'))
    {
        return Err(RfmError::InvalidOption(
            "rfm path contains unsupported characters".to_owned(),
        ));
    }
    let pins = (1..=nports)
        .map(|index| format!("p{index}"))
        .collect::<Vec<_>>();
    let vector = pins
        .iter()
        .map(|pin| format!("{pin} ref"))
        .collect::<Vec<_>>()
        .join(" ");
    let model = format!("{subcircuit_name}_rfm_model");
    let text = format!(
        "* Agent-Spice direct RFM XSPICE wrapper\n.subckt {subcircuit_name} {} ref\nArfm %gd[{vector}] {model}\n.model {model} nport_rfm(rfm_file=\"{relative}\")\n.ends {subcircuit_name}\n",
        pins.join(" ")
    );
    write_text(path, &text)
}

fn pathdiff(target: &Path, base: &Path) -> Result<String, RfmError> {
    let target = if target.is_absolute() {
        target.to_path_buf()
    } else {
        std::env::current_dir()
            .map_err(|e| RfmError::Output(e.to_string()))?
            .join(target)
    };
    let base = if base.is_absolute() {
        base.to_path_buf()
    } else {
        std::env::current_dir()
            .map_err(|e| RfmError::Output(e.to_string()))?
            .join(base)
    };
    let target = target.components().collect::<Vec<_>>();
    let base = base.components().collect::<Vec<_>>();
    let common = target.iter().zip(&base).take_while(|(a, b)| a == b).count();
    let mut parts = Vec::new();
    for _ in common..base.len() {
        parts.push("..".to_owned());
    }
    for component in &target[common..] {
        parts.push(component.as_os_str().to_string_lossy().into_owned());
    }
    Ok(if parts.is_empty() {
        ".".to_owned()
    } else {
        parts.join("/")
    })
}

fn response_frequencies(model: &RfmModel) -> Vec<f64> {
    // Match the upstream verification envelope: probe two decades beyond the
    // smallest/largest dynamic pole instead of imposing a fixed Hz range.
    // The zero-pole model still receives a finite, deterministic probe pair.
    let positive = model
        .poles
        .iter()
        .map(|pole| pole.norm())
        .filter(|magnitude| *magnitude > 0.0)
        .map(|magnitude| magnitude / (2.0 * std::f64::consts::PI))
        .collect::<Vec<_>>();
    if positive.is_empty() {
        return vec![0.0, 1.0];
    }
    let low =
        (positive.iter().copied().fold(f64::INFINITY, f64::min) / 100.0).max(f64::MIN_POSITIVE);
    let high = (positive.iter().copied().fold(0.0, f64::max) * 100.0).max(low * 10.0);
    std::iter::once(0.0)
        .chain(
            (0..RESPONSE_SAMPLES - 1)
                .map(|index| low * (high / low).powf(index as f64 / (RESPONSE_SAMPLES - 2) as f64)),
        )
        .collect::<Vec<_>>()
}

fn max_response_abs(model: &RfmModel) -> f64 {
    let mut maximum: f64 = 0.0;
    for frequency in response_frequencies(model) {
        let value = model.evaluate_s(frequency);
        if value
            .iter()
            .any(|entry| !entry.re.is_finite() || !entry.im.is_finite())
        {
            return f64::INFINITY;
        }
        maximum = maximum.max(value.iter().map(|entry| entry.norm()).fold(0.0, f64::max));
    }
    maximum
}

fn reconstruction_max_error(original: &RfmModel, normalized: &RfmModel) -> f64 {
    response_frequencies(original)
        .into_iter()
        .map(|frequency| {
            let left = original.evaluate_s(frequency);
            let right = normalized.evaluate_s(frequency);
            left.iter()
                .zip(right)
                .map(|(a, b)| (*a - b).norm())
                .fold(0.0, f64::max)
        })
        .fold(0.0, f64::max)
}

fn write_text(path: &Path, text: &str) -> Result<(), RfmError> {
    if text.len() > MAX_ARTIFACT_BYTES {
        return Err(RfmError::Output("artifact exceeds byte budget".to_owned()));
    }
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|error| RfmError::Output(error.to_string()))?;
    }
    fs::write(path, text).map_err(|error| RfmError::Output(error.to_string()))
}

fn parse_ngspice_measurements(text: &str) -> Vec<serde_json::Value> {
    let mut measurements = Vec::new();
    for line in text.lines() {
        let fields = line.split_whitespace().collect::<Vec<_>>();
        let Some(first) = fields.first() else {
            continue;
        };
        let (name, value, suffix_start) = if let Some((name, value)) = first.split_once('=') {
            (name, value, 1usize)
        } else if fields.get(1).is_some_and(|field| *field == "=") {
            let Some(value) = fields.get(2) else {
                continue;
            };
            (*first, *value, 3usize)
        } else {
            continue;
        };
        let Ok(value) = value.parse::<f64>() else {
            continue;
        };
        let mut entry = json!({"name": name, "value": value});
        let at = fields[suffix_start..]
            .iter()
            .enumerate()
            .find_map(|(index, field)| {
                let lower = field.to_ascii_lowercase();
                if let Some(value) = lower.strip_prefix("at=") {
                    return value.parse::<f64>().ok();
                }
                if lower == "at=" {
                    return fields.get(suffix_start + index + 1)?.parse::<f64>().ok();
                }
                None
            });
        if let Some(at) = at {
            entry["at"] = json!(at);
        }
        measurements.push(entry);
    }
    measurements
}

fn write_ngspice_waveform_csv(text: &str, path: &Path) -> Result<usize, RfmError> {
    let mut columns: Option<Vec<&str>> = None;
    let mut rows = Vec::<Vec<f64>>::new();
    for line in text.lines() {
        let fields = line.split_whitespace().collect::<Vec<_>>();
        if fields.first() == Some(&"Index") && fields.len() >= 3 {
            let candidate = fields[1..].to_vec();
            if columns.as_ref().is_none_or(|value| *value != candidate) {
                columns = Some(candidate);
                rows.clear();
            }
            continue;
        }
        let Some(header) = columns.as_ref() else {
            continue;
        };
        if fields.len() != header.len() + 1
            || fields
                .first()
                .is_none_or(|value| !value.chars().all(|c| c.is_ascii_digit()))
        {
            continue;
        }
        let Ok(values) = fields[1..]
            .iter()
            .map(|value| value.parse::<f64>())
            .collect::<Result<Vec<_>, _>>()
        else {
            continue;
        };
        rows.push(values);
    }
    let Some(columns) = columns else {
        return Ok(0);
    };
    if rows.is_empty() {
        return Ok(0);
    }
    let mut csv = columns.join(",");
    csv.push('\n');
    for row in &rows {
        csv.push_str(
            &row.iter()
                .map(|value| format!("{value:.17e}"))
                .collect::<Vec<_>>()
                .join(","),
        );
        csv.push('\n');
    }
    write_text(path, &csv)?;
    Ok(rows.len())
}

fn sha256_file(path: &Path) -> Result<String, RfmError> {
    let bytes = fs::read(path).map_err(|e| RfmError::Input(e.to_string()))?;
    Ok(format!("{:x}", Sha256::digest(bytes)))
}

fn dependency_references(text: &str) -> Vec<String> {
    let audit = crate::audit_deck(text);
    audit
        .includes
        .into_iter()
        .chain(audit.libraries.into_iter().map(|library| library.path))
        .collect()
}

type StagedDependencies = (
    Vec<String>,
    Vec<crate::ConversionAction>,
    Vec<crate::UnsupportedIssue>,
);

fn stage_dependencies(
    source_root: &Path,
    run_root: &Path,
    text: &str,
    _backend: RfmBackend,
) -> Result<StagedDependencies, RfmError> {
    const MAX_FILES: usize = 4096;
    const MAX_BYTES: u64 = 64 * 1024 * 1024;
    let root = source_root
        .canonicalize()
        .map_err(|e| RfmError::Input(e.to_string()))?;
    let mut queue = dependency_references(text)
        .into_iter()
        .map(|reference| (root.clone(), reference))
        .collect::<Vec<_>>();
    let mut seen = std::collections::BTreeSet::new();
    let mut staged = Vec::new();
    let mut actions = Vec::new();
    let mut unsupported = Vec::new();
    let mut total = 0u64;
    while let Some((parent, reference)) = queue.pop() {
        let path = Path::new(&reference);
        if path.is_absolute() {
            return Err(RfmError::Unsupported(format!(
                "absolute dependency is not staged: {reference}"
            )));
        }
        let source = parent.join(path).canonicalize().map_err(|e| {
            RfmError::Unsupported(format!("dependency {reference} is unavailable: {e}"))
        })?;
        let relative = source.strip_prefix(&root).map_err(|_| {
            RfmError::Unsupported(format!("dependency escapes deck root: {reference}"))
        })?;
        if !seen.insert(source.clone()) {
            continue;
        }
        if seen.len() > MAX_FILES {
            return Err(RfmError::Unsupported(
                "dependency file budget exceeded".to_owned(),
            ));
        }
        let metadata = fs::metadata(&source).map_err(|e| RfmError::Unsupported(e.to_string()))?;
        total = total.saturating_add(metadata.len());
        if total > MAX_BYTES {
            return Err(RfmError::Unsupported(
                "dependency byte budget exceeded".to_owned(),
            ));
        }
        let target = run_root.join(relative);
        if let Some(parent) = target.parent() {
            fs::create_dir_all(parent).map_err(|e| RfmError::Output(e.to_string()))?;
        }
        let nested = fs::read_to_string(&source).map_err(|e| RfmError::Input(e.to_string()))?;
        // The pinned prepare path writes all staged dependencies through the
        // deterministic HSPICE-to-ngspice converter, even when the eventual
        // native engine is selected.  Preserve that artifact contract here;
        // the solver remains an external runtime boundary.
        let (staged_text, nested_actions, nested_unsupported) =
            crate::convert_deck(&nested, crate::Backend::Ngspice);
        actions.extend(nested_actions);
        unsupported.extend(nested_unsupported);
        for directive in crate::audit_deck(&nested).unsupported_directives {
            unsupported.push(crate::UnsupportedIssue {
                line: directive,
                reason: "unsupported_directive_in_dependency".to_owned(),
            });
        }
        fs::write(&target, staged_text).map_err(|e| RfmError::Output(e.to_string()))?;
        staged.push(relative.to_string_lossy().replace('\\', "/"));
        for child in dependency_references(&nested) {
            queue.push((source.parent().unwrap_or(&root).to_path_buf(), child));
        }
    }
    staged.sort();
    Ok((staged, actions, unsupported))
}

fn is_end_marker(value: &str) -> bool {
    let lower = value.trim().to_ascii_lowercase();
    if lower == ".end" || lower.starts_with(".endcomment") {
        return true;
    }
    lower
        .strip_prefix(".end")
        .is_some_and(|suffix| suffix.trim_start().starts_with('*'))
}

fn inject_wrapper(text: &str, wrapper_name: &str) -> String {
    let directive = format!(".include '{wrapper_name}'\n");
    let mut last_end = None;
    for (index, _) in text.match_indices('\n') {
        let start = text[..index].rfind('\n').map_or(0, |value| value + 1);
        let value = text[start..index].trim();
        let lower = value.to_ascii_lowercase();
        if is_end_marker(&lower) {
            last_end = Some(start);
        }
    }
    // `str::match_indices('\n')` does not visit a final unterminated line.
    // Treat a terminal `.end*` comment on that line exactly like its newline-
    // terminated form, otherwise the wrapper would be injected after the
    // source terminator and never be seen by the simulator.
    if !text.ends_with('\n') {
        let start = text.rfind('\n').map_or(0, |value| value + 1);
        let value = text[start..].trim();
        let lower = value.to_ascii_lowercase();
        if is_end_marker(&lower) {
            last_end = Some(start);
        }
    }
    if let Some(index) = last_end {
        format!("{}{}{}", &text[..index], directive, &text[index..])
    } else {
        format!("{}\n{}.end\n", text.trim_end(), directive)
    }
}

/// Prepare an RFM run and optionally invoke the explicitly selected simulator.
pub fn run_rfm(request: &RunRfmRequest) -> Result<RunRfmResult, RfmError> {
    if request.execute && !external_execution_available() {
        return Err(RfmError::Execution(
            "external simulator execution is fail-closed: executable custody is required"
                .to_owned(),
        ));
    }
    let deck =
        crate::absolute_path(&request.deck).map_err(|error| RfmError::Input(error.to_string()))?;
    let rfm =
        crate::absolute_path(&request.rfm).map_err(|error| RfmError::Input(error.to_string()))?;
    if !deck.is_file() || !rfm.is_file() {
        return Err(RfmError::Input("deck and RFM must exist".to_owned()));
    }
    if deck
        .metadata()
        .map(|metadata| metadata.len() > MAX_ARTIFACT_BYTES as u64)
        .unwrap_or(false)
    {
        return Err(RfmError::Input(
            "deck exceeds the bounded input budget".to_owned(),
        ));
    }
    if request.subckt_name.is_empty() || request.subckt_name.chars().any(char::is_whitespace) {
        return Err(RfmError::InvalidOption(
            "subckt_name must be non-empty and whitespace-free".to_owned(),
        ));
    }
    let model = parse_cadence_rfm(&rfm)?;
    let deck_text =
        fs::read_to_string(&deck).map_err(|error| RfmError::Input(error.to_string()))?;
    if deck_text.is_empty() {
        return Err(RfmError::Input("deck is empty".to_owned()));
    }
    let requested_output_root = crate::absolute_path(&request.output_root)
        .map_err(|error| RfmError::Output(error.to_string()))?;
    let deck_stem = deck
        .file_stem()
        .and_then(|value| value.to_str())
        .filter(|value| !value.is_empty())
        .ok_or_else(|| RfmError::Input("deck file stem is empty".to_owned()))?;
    // Keep the same project/case layout as upstream prepare_rfm_run: callers
    // provide the run root, while this leaf owns <deck>/rfm_direct.
    let output_root = requested_output_root.join(deck_stem).join("rfm_direct");
    fs::create_dir_all(&output_root).map_err(|error| RfmError::Output(error.to_string()))?;
    // Match prepare_rfm_run's stable runtime filename.  The input copy is
    // retained separately so replay manifests distinguish source and runtime.
    let staged_rfm = output_root.join("model.runtime.rfm");
    let source_deck = output_root.join("case.source.sp");
    let source_rfm = output_root.join("model.input.rfm");
    let prepared_deck = output_root.join("case.cir");
    let wrapper = output_root.join("rfm_direct_wrapper.sp");
    write_cadence_rfm(&staged_rfm, &model)?;
    fs::copy(&rfm, &source_rfm).map_err(|error| RfmError::Output(error.to_string()))?;
    let normalized = parse_cadence_rfm(&staged_rfm)?;
    let response_max_error = reconstruction_max_error(&model, &normalized);
    if !response_max_error.is_finite() || response_max_error > 1e-11 {
        return Err(RfmError::Parse(format!(
            "RFM normalization changed the response (max error {response_max_error:.3e})"
        )));
    }
    write_text(&source_deck, &deck_text)?;
    let (staged_dependencies, dependency_actions, dependency_unsupported) = stage_dependencies(
        deck.parent().unwrap_or_else(|| Path::new(".")),
        &output_root,
        &deck_text,
        request.backend,
    )?;
    if request.backend == RfmBackend::Ngspice {
        write_xspice_rfm_wrapper(&wrapper, &staged_rfm, model.nports, &request.subckt_name)?;
    } else {
        write_cadence_rfm_wrapper(
            &wrapper,
            &staged_rfm,
            model.nports,
            Some(&request.subckt_name),
        )?;
    }
    let injected_deck = inject_wrapper(
        &deck_text,
        wrapper
            .file_name()
            .and_then(|v| v.to_str())
            .unwrap_or("rfm_direct_wrapper.sp"),
    );
    // `prepare_rfm_run` uses the same deterministic deck conversion for the
    // native and ngspice dispatch branches.  Keep unsupported root directives
    // visible before any external process is considered.
    let root_audit = crate::audit_deck(&injected_deck);
    let (prepared_text, mut conversion_actions, mut conversion_unsupported) =
        crate::convert_deck(&injected_deck, crate::Backend::Ngspice);
    conversion_unsupported.extend(root_audit.unsupported_directives.into_iter().map(|line| {
        crate::UnsupportedIssue {
            line,
            reason: "unsupported_directive".to_owned(),
        }
    }));
    conversion_actions.extend(dependency_actions);
    conversion_unsupported.extend(dependency_unsupported);
    write_text(&prepared_deck, &prepared_text)?;
    let waveform = output_root.join("waveform.csv");
    let native_json = output_root.join("native_result.json");
    let manifest_path = output_root.join("rfm_run_manifest.json");
    let source_sha = sha256_file(&source_deck)?;
    let source_rfm_sha = sha256_file(&source_rfm)?;
    let staged_rfm_sha = sha256_file(&staged_rfm)?;
    let verification_samples = response_frequencies(&model).len();
    let manifest = json!({
        "schema_version": 1,
        "execution_path": "xspice-nport-rational",
        "refit_performed": false,
        "reference_mode": "common-reference-pin",
        "subcircuit_name": request.subckt_name,
        "model": {
            "nports": model.nports,
            "z0_ohm": model.z0,
            "stored_poles": model.poles.len(),
            "effective_order": model.effective_order(),
        },
        "inputs": {
            "deck": {"path": "case.source.sp", "sha256": source_sha},
            "rfm": {"path": "model.input.rfm", "sha256": source_rfm_sha},
        },
        "runtime_rfm": {
            "path": "model.runtime.rfm",
            "sha256": staged_rfm_sha,
            "normalization": "shared-pole union with zero residues; no vector fitting",
            "verification_samples": verification_samples,
            "reconstruction_max": response_max_error,
        },
        "artifacts": {
            "deck": "case.cir",
            "wrapper": "rfm_direct_wrapper.sp",
            "staged_dependencies": staged_dependencies,
        },
    });
    write_text(
        &manifest_path,
        &(serde_json::to_string_pretty(&manifest)
            .map_err(|error| RfmError::Output(error.to_string()))?
            + "\n"),
    )?;
    let conversion_actions_json = conversion_actions
        .iter()
        .map(|action| {
            json!({
                "kind": action.kind,
                "source": action.source,
                "target": action.target,
            })
        })
        .collect::<Vec<_>>();
    let conversion_unsupported_json = conversion_unsupported
        .iter()
        .map(|issue| json!({"line": issue.line, "reason": issue.reason}))
        .collect::<Vec<_>>();
    let conversion_blocked = !conversion_unsupported.is_empty();
    let conversion = json!({
        "backend": request.backend.as_str(),
        "actions": conversion_actions_json,
        "unsupported": conversion_unsupported_json,
    });
    let mut execution = json!({
        "requested": request.execute,
        "backend": request.backend.as_str(),
        "status": if conversion_blocked { "BLOCKED" } else { "PREPARED" },
        "conversion": conversion.clone(),
    });
    if request.execute && !conversion_blocked {
        let mut ngspice_scripts = None;
        let mut ngspice_code_model = None;
        let mut native_engine_path = None;
        let (program, arguments) = match request.backend {
            RfmBackend::Native => {
                let executable = request
                    .native_engine
                    .as_ref()
                    .map(|path| crate::absolute_path(path))
                    .transpose()
                    .map_err(|error| RfmError::Execution(error.to_string()))?
                    .ok_or_else(|| {
                        RfmError::Execution(
                            "native backend requires --native-engine; no fallback is attempted"
                                .to_owned(),
                        )
                    })?;
                native_engine_path = Some(executable.clone());
                let (program, mut native_args) = if executable
                    .extension()
                    .is_some_and(|value| value.eq_ignore_ascii_case("dll"))
                {
                    (PathBuf::from(&request.dotnet), vec![executable.clone()])
                } else {
                    (executable.clone(), Vec::new())
                };
                native_args.extend([
                    prepared_deck.clone(),
                    PathBuf::from("--rfm"),
                    staged_rfm.clone(),
                    PathBuf::from("--output-json"),
                    native_json.clone(),
                    PathBuf::from("--waveform-csv"),
                    waveform.clone(),
                ]);
                (program, native_args)
            }
            RfmBackend::Ngspice => {
                let source_model = request.code_model.as_ref().ok_or_else(|| {
                    RfmError::Execution(
                        "ngspice backend requires an explicit --code-model".to_owned(),
                    )
                })?;
                let code_model = crate::absolute_path(source_model)
                    .map_err(|error| RfmError::Execution(error.to_string()))?;
                if !code_model.is_file() {
                    return Err(RfmError::Execution(
                        "ngspice backend requires an explicit --code-model".to_owned(),
                    ));
                }
                let scripts = output_root.join(".ngspice-scripts");
                let staged_models = output_root.join(".ngspice-code-models");
                fs::create_dir_all(&scripts).map_err(|error| {
                    RfmError::Execution(format!("cannot create ngspice script directory: {error}"))
                })?;
                fs::create_dir_all(&staged_models).map_err(|error| {
                    RfmError::Execution(format!(
                        "cannot create ngspice code-model directory: {error}"
                    ))
                })?;
                let file_name = code_model.file_name().ok_or_else(|| {
                    RfmError::Execution("ngspice code-model has no file name".to_owned())
                })?;
                let staged_model =
                    staged_models.join(format!("000-{}", file_name.to_string_lossy()));
                if staged_model
                    .to_string_lossy()
                    .chars()
                    .any(char::is_whitespace)
                {
                    return Err(RfmError::Execution(
                        "ngspice code-model paths cannot contain whitespace".to_owned(),
                    ));
                }
                fs::copy(&code_model, &staged_model).map_err(|error| {
                    RfmError::Execution(format!("cannot stage ngspice code model: {error}"))
                })?;
                let staged_model_path = staged_model
                    .canonicalize()
                    .map_err(|error| RfmError::Execution(error.to_string()))?;
                let spinit = format!(
                    "* Generated by SIPI; isolated ngspice code-model search path.\nalias exit quit\nset filetype=ascii\nset num_threads=1\nunset osdi_enabled\nif $?xspice_enabled\n codemodel {}\nend\n",
                    staged_model_path.to_string_lossy().replace('\\', "/")
                );
                fs::write(scripts.join("spinit"), spinit).map_err(|error| {
                    RfmError::Execution(format!("cannot write ngspice spinit: {error}"))
                })?;
                ngspice_scripts = Some(scripts);
                ngspice_code_model = Some((code_model, staged_model));
                (
                    PathBuf::from(&request.ngspice),
                    vec![PathBuf::from("-b"), prepared_deck.clone()],
                )
            }
        };
        let mut command = Command::new(&program);
        command
            .args(arguments.iter().map(|value| value.as_os_str()))
            .current_dir(&output_root);
        if let Some(scripts) = ngspice_scripts {
            command.env("SPICE_SCRIPTS", scripts);
        }
        let result = command
            .output()
            .map_err(|error| RfmError::Execution(error.to_string()))?;
        write_text(
            &output_root.join("stdout.log"),
            &String::from_utf8_lossy(&result.stdout),
        )?;
        write_text(
            &output_root.join("stderr.log"),
            &String::from_utf8_lossy(&result.stderr),
        )?;
        let ngspice_model_error = request.backend == RfmBackend::Ngspice
            && (String::from_utf8_lossy(&result.stdout).contains("nport_rfm ERROR:")
                || String::from_utf8_lossy(&result.stderr).contains("nport_rfm ERROR:"));
        let mut backend_ok = result.status.success() && !ngspice_model_error;
        let mut native_waveform_rows = 0u64;
        let mut native_result_error = None;
        if request.backend == RfmBackend::Native && backend_ok {
            match fs::read(&native_json) {
                Err(_) => {
                    backend_ok = false;
                    native_result_error = Some(
                        "native engine returned success without native_result.json".to_owned(),
                    );
                }
                Ok(bytes) => match serde_json::from_slice::<serde_json::Value>(&bytes) {
                    Err(error) => {
                        backend_ok = false;
                        native_result_error = Some(format!("native result is not JSON: {error}"));
                    }
                    Ok(value) if !value.is_object() => {
                        backend_ok = false;
                        native_result_error =
                            Some("native result must be a JSON object".to_owned());
                    }
                    Ok(value) => {
                        native_waveform_rows = value
                            .get("waveformRows")
                            .and_then(serde_json::Value::as_u64)
                            .unwrap_or(0);
                    }
                },
            }
        }
        execution = json!({"requested": true, "backend": request.backend.as_str(), "status": if backend_ok { "EXECUTED" } else { "FAIL" }, "returncode": result.status.code(), "stdout_bytes": result.stdout.len(), "stderr_bytes": result.stderr.len(), "logs": {"stdout": "stdout.log", "stderr": "stderr.log"}});
        if let Some(error) = native_result_error {
            execution["result_error"] = json!(error);
        }
        if let Some((source, staged)) = ngspice_code_model {
            execution["code_model"] = json!({
                "source": source,
                "staged": staged,
                "sha256": sha256_file(&staged)?,
            });
        }
        if request.backend == RfmBackend::Ngspice {
            let stdout = String::from_utf8_lossy(&result.stdout);
            let waveform_rows =
                write_ngspice_waveform_csv(&stdout, &output_root.join("waveform.csv"))?;
            execution["waveform"] = json!({
                "path": "waveform.csv",
                "format": "csv",
                "rows": waveform_rows,
                "exists": output_root.join("waveform.csv").is_file(),
            });
            execution["measurements"] = json!(parse_ngspice_measurements(&stdout));
            let summary = json!({
                "schema_version": 1,
                "backend": "ngspice-xspice-rfm",
                "ok": backend_ok,
                "returncode": result.status.code(),
                "code_model": execution.get("code_model").cloned().unwrap_or(serde_json::Value::Null),
                "logs": {"stdout": "stdout.log", "stderr": "stderr.log"},
                "waveform": if waveform_rows > 0 { serde_json::Value::String("waveform.csv".to_owned()) } else { serde_json::Value::Null },
                "waveform_rows": waveform_rows,
                "measurements": execution["measurements"].clone(),
            });
            write_text(
                &output_root.join("run_summary.json"),
                &(serde_json::to_string_pretty(&summary)
                    .map_err(|error| RfmError::Output(error.to_string()))?
                    + "\n"),
            )?;
        }
        if request.backend == RfmBackend::Native {
            let engine = native_engine_path.ok_or_else(|| {
                RfmError::Execution("native engine path was not recorded".to_owned())
            })?;
            let engine_sha = if engine.is_file() {
                Some(sha256_file(&engine)?)
            } else {
                None
            };
            let summary = json!({
                "schema_version": 1,
                "backend": "agent-spice-native-rfm",
                "ok": backend_ok,
                "returncode": result.status.code(),
                "engine": {"path": engine, "sha256": engine_sha},
                "logs": {"stdout": "stdout.log", "stderr": "stderr.log"},
                "result": if backend_ok && native_json.is_file() { serde_json::Value::String("native_result.json".to_owned()) } else { serde_json::Value::Null },
                "waveform": if native_waveform_rows > 0 && waveform.is_file() { serde_json::Value::String("waveform.csv".to_owned()) } else { serde_json::Value::Null },
                "waveform_rows": native_waveform_rows,
            });
            write_text(
                &output_root.join("run_summary.json"),
                &(serde_json::to_string_pretty(&summary)
                    .map_err(|error| RfmError::Output(error.to_string()))?
                    + "\n"),
            )?;
        }
        if !backend_ok {
            return Err(RfmError::Execution(format!(
                "{} returned {:?}",
                program.display(),
                result.status.code()
            )));
        }
    }
    // Keep conversion evidence alongside the backend result.  The external
    // branch replaces `execution` with its process contract, so restore this
    // portable input transformation record before publishing the report.
    execution["conversion"] = conversion.clone();
    let report = output_root.join("run_report.json");
    let rfm_sha = source_rfm_sha.clone();
    let status = if conversion_blocked {
        "BLOCKED"
    } else if request.execute {
        "PASS"
    } else {
        "PREPARED"
    };
    let payload = json!({
        "schema": "sipi.agent-spice-as-06-run-rfm-result.v2",
        "schema_version": 2,
        "workflow": WORKFLOW_NAME,
        "upstream_commit": UPSTREAM_COMMIT,
        "upstream_tree": UPSTREAM_TREE,
        "status": status,
        "backend": request.backend.as_str(),
        "deck": deck,
        "rfm": rfm,
        "nports": model.nports,
        "response_samples": verification_samples,
        "response_max_abs": max_response_abs(&model),
        "response_reconstruction_max": response_max_error,
        "execution": execution,
        "conversion": conversion,
        "inputs": {"deck": {"path": source_deck, "sha256": source_sha}, "rfm": {"path": source_rfm, "sha256": rfm_sha}},
        "runtime_rfm": {"path": staged_rfm, "sha256": staged_rfm_sha, "normalization": "shared-pole union; no refit", "reconstruction_max": response_max_error},
        "artifacts": {
            "source_deck": source_deck,
            "source_rfm": source_rfm,
            "prepared_deck": prepared_deck,
        "runtime_rfm": staged_rfm,
            "wrapper": wrapper,
            "staged_dependencies": staged_dependencies,
            "manifest": manifest_path,
            "report": report,
            "run_summary": output_root.join("run_summary.json"),
            "external_outputs_expected": {"waveform": waveform, "native_result": native_json, "ngspice_run_summary": output_root.join("run_summary.json")},
            "external_outputs_produced_by_prepare": false,
        },
        "portable_branches": ["nport-rfm-parse", "union-pole-normalization", "wrapper-injection", "ngspice-deck-conversion", "dependency-staging", "measure-waveform-result-contract", "content-addressed-manifest"],
        "external_runtime_boundary": ["native-engine", "ngspice-xspice-code-model"],
    });
    write_text(
        &report,
        &(serde_json::to_string_pretty(&payload)
            .map_err(|error| RfmError::Output(error.to_string()))?
            + "\n"),
    )?;
    Ok(RunRfmResult {
        status: status.to_owned(),
        report,
        output_root,
        response_max_error,
        response_samples: verification_samples,
        model,
    })
}

fn external_execution_available() -> bool {
    false
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parser_promotes_union_poles_and_rejects_nonzero_delay() {
        let root = std::env::temp_dir().join(format!("sipi-as06-{}", std::process::id()));
        fs::create_dir_all(&root).unwrap();
        let path = root.join("model.rfm");
        fs::write(&path, "VERSION 200600\nNPORT 1\nMATRIX_TYPE S\nZ0 50\nBEGIN 1 1\nCONST 0\nC 0\nDELAY 0\nBEGIN_REAL 1\n1 0.5\nBEGIN_COMPLEX 0\nEND\n").unwrap();
        let model = parse_cadence_rfm(&path).unwrap();
        assert_eq!(model.poles.len(), 1);
        assert_eq!(model.effective_order(), 1);
        assert_eq!(model.proportional_coeff(), vec![0.0]);
        assert!(model.evaluate_s(1.0)[0].re.is_finite());
        assert_eq!(
            model.evaluate_s_many(&[0.0, 1.0]).unwrap(),
            vec![model.evaluate_s(0.0), model.evaluate_s(1.0)]
        );
        assert!(matches!(
            model.evaluate_s_many(&[]),
            Err(RfmError::InvalidOption(message)) if message.contains("non-empty")
        ));
        assert!(matches!(
            model.evaluate_s_many(&[f64::NAN]),
            Err(RfmError::InvalidOption(message)) if message.contains("finite")
        ));
        assert!(matches!(
            model.evaluate_s_many(&[f64::INFINITY]),
            Err(RfmError::InvalidOption(message)) if message.contains("finite")
        ));
        fs::write(&path, "VERSION 200600\nNPORT 1\nMATRIX_TYPE S\nZ0 50\nBEGIN 1 1\nCONST 0\nC 0\nDELAY 1\nBEGIN_REAL 0\nBEGIN_COMPLEX 0\nEND\n").unwrap();
        assert!(matches!(
            parse_cadence_rfm(&path),
            Err(RfmError::Unsupported(_))
        ));
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn effective_order_and_response_major_batch_match_upstream_model_contract() {
        let model = RfmModel {
            version: 200600,
            nports: 2,
            matrix_type: "S".to_owned(),
            z0: 50.0,
            poles: vec![Complex::new(-1.0, 2.0)],
            residues: vec![
                vec![Complex::new(0.0, 0.0)],
                vec![Complex::new(0.0, 0.0)],
                vec![Complex::new(0.0, 0.0)],
                vec![Complex::new(0.0, 0.0)],
            ],
            constant: vec![
                Complex::new(1.0, 0.0),
                Complex::new(2.0, 0.0),
                Complex::new(3.0, 0.0),
                Complex::new(4.0, 0.0),
            ],
        };
        assert_eq!(model.effective_order(), 2);
        let samples = model.evaluate_s_many(&[0.0, 1.0]).unwrap();
        assert_eq!(samples.len(), 2);
        assert_eq!(samples[0].len(), 4);
        assert_eq!(samples[0], model.constant);
        assert_eq!(model.proportional_coeff(), vec![0.0; 4]);
    }

    #[test]
    fn wrapper_and_injection_preserve_nport_pairs() {
        let root = std::env::temp_dir().join(format!("sipi-as06-wrapper-{}", std::process::id()));
        fs::create_dir_all(&root).unwrap();
        let rfm = root.join("model.rfm");
        let wrapper = root.join("wrapper.sp");
        fs::write(&rfm, "VERSION 200600\nNPORT 2\nMATRIX_TYPE S\nZ0 50\nBEGIN 1 1\nCONST 0\nC 0\nDELAY 0\nBEGIN_REAL 0\nBEGIN_COMPLEX 0\nEND\nBEGIN 1 2\nCONST 0\nC 0\nDELAY 0\nBEGIN_REAL 0\nBEGIN_COMPLEX 0\nEND\nBEGIN 2 1\nCONST 0\nC 0\nDELAY 0\nBEGIN_REAL 0\nBEGIN_COMPLEX 0\nEND\nBEGIN 2 2\nCONST 0\nC 0\nDELAY 0\nBEGIN_REAL 0\nBEGIN_COMPLEX 0\nEND\n").unwrap();
        write_cadence_rfm_wrapper(&wrapper, &rfm, 2, Some("rfm_direct")).unwrap();
        let text = fs::read_to_string(&wrapper).unwrap();
        assert!(text.contains("n1 n1_ref") && text.contains("n2 n2_ref"));
        assert!(
            inject_wrapper(".tran 1p 1n\n.end\n", "wrapper.sp").contains(".include 'wrapper.sp'")
        );
        assert!(
            inject_wrapper(".tran 1p 1n\n.endcomment preserved\n", "wrapper.sp")
                .contains(".include 'wrapper.sp'\n.endcomment preserved\n")
        );
        assert_eq!(
            inject_wrapper(".tran 1p 1n\n.endcomment preserved", "wrapper.sp"),
            ".tran 1p 1n\n.include 'wrapper.sp'\n.endcomment preserved"
        );
        assert_eq!(
            inject_wrapper(".tran 1p 1n\n.end*comment preserved\n", "wrapper.sp"),
            ".tran 1p 1n\n.include 'wrapper.sp'\n.end*comment preserved\n"
        );
        assert_eq!(
            inject_wrapper(".tran 1p 1n\n.end*comment preserved", "wrapper.sp"),
            ".tran 1p 1n\n.include 'wrapper.sp'\n.end*comment preserved"
        );
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn xspice_wrapper_uses_common_reference_vector_and_relative_rfm() {
        let root = std::env::temp_dir().join(format!("sipi-as06-xspice-{}", std::process::id()));
        fs::create_dir_all(&root).unwrap();
        let rfm = root.join("nested").join("model.rfm");
        let wrapper = root.join("run").join("wrapper.sp");
        fs::create_dir_all(rfm.parent().unwrap()).unwrap();
        fs::create_dir_all(wrapper.parent().unwrap()).unwrap();
        fs::write(&rfm, b"VERSION 200600\n").unwrap();
        write_xspice_rfm_wrapper(&wrapper, &rfm, 3, "rfm_direct").unwrap();
        let text = fs::read_to_string(&wrapper).unwrap();
        assert!(text.contains(".subckt rfm_direct p1 p2 p3 ref"));
        assert!(text.contains("Arfm %gd[p1 ref p2 ref p3 ref] rfm_direct_rfm_model"));
        assert!(text.contains("rfm_file=\"../nested/model.rfm\""));
        assert!(text.contains(".ends rfm_direct"));
        assert!(matches!(
            write_xspice_rfm_wrapper(&wrapper, &rfm, 1, "bad name"),
            Err(RfmError::InvalidOption(_))
        ));
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn run_layout_and_ngspice_conversion_are_explicit() {
        let root = std::env::temp_dir().join(format!("sipi-as06-run-{}", std::process::id()));
        fs::create_dir_all(root.join("models")).unwrap();
        fs::write(root.join("models/top.inc"), ".include 'nested.inc'\n").unwrap();
        fs::write(root.join("models/nested.inc"), ".param r=50\n").unwrap();
        let deck = root.join("deck.sp");
        fs::write(
            &deck,
            ".inc 'models/top.inc'\n.probe tran v(out)\n.option post=2\nXrfm p1 rfm_direct\n.end\n",
        )
        .unwrap();
        let rfm = root.join("model.rfm");
        fs::write(
            &rfm,
            "VERSION 200600\nNPORT 1\nMATRIX_TYPE S\nZ0 50\nBEGIN 1 1\nCONST 0\nC 0\nDELAY 0\nBEGIN_REAL 1\n1 0.5\nBEGIN_COMPLEX 0\nEND\n",
        )
        .unwrap();
        let request = RunRfmRequest::new(&deck, &rfm, "ngspice", root.join("out")).unwrap();
        let result = run_rfm(&request).unwrap();
        let run_root = root.join("out/deck/rfm_direct");
        assert_eq!(result.status, "PREPARED");
        assert_eq!(result.output_root, run_root);
        assert!(run_root.join("models/top.inc").is_file());
        assert!(run_root.join("models/nested.inc").is_file());
        let staged_top = fs::read_to_string(run_root.join("models/top.inc")).unwrap();
        assert!(staged_top.contains(".include 'nested.inc'"));
        let prepared = fs::read_to_string(run_root.join("case.cir")).unwrap();
        assert!(prepared.contains(".include 'models/top.inc'"));
        assert!(prepared.contains(".print tran v(out)"));
        assert!(!prepared.contains("post=2"));
        let report: serde_json::Value =
            serde_json::from_slice(&fs::read(run_root.join("run_report.json")).unwrap()).unwrap();
        assert_eq!(report["conversion"]["backend"], "ngspice");
        assert!(!report["conversion"]["actions"]
            .as_array()
            .unwrap()
            .is_empty());
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn execute_never_resolves_fake_path_ngspice() {
        let root = std::env::temp_dir().join(format!("sipi-as06-custody-{}", std::process::id()));
        let request = RunRfmRequest::new(
            root.join("deck.sp"),
            root.join("model.rfm"),
            "ngspice",
            root.join("out"),
        )
        .unwrap()
        .execute(true);
        let result = run_rfm(&request);
        assert!(matches!(result, Err(RfmError::Execution(message)) if message.contains("custody")));
        assert!(!root.join("out").exists());
    }

    #[test]
    fn writer_rejects_nonreal_residue_on_real_pole_and_common_ground_wrapper_is_explicit() {
        let root = std::env::temp_dir().join(format!("sipi-as06-writer-{}", std::process::id()));
        fs::create_dir_all(&root).unwrap();
        let rfm = root.join("model.rfm");
        let invalid = RfmModel {
            version: 200600,
            nports: 1,
            matrix_type: "S".to_owned(),
            z0: 50.0,
            poles: vec![Complex::new(-1.0, 0.0)],
            residues: vec![vec![Complex::new(1.0, 0.25)]],
            constant: vec![Complex::new(0.0, 0.0)],
        };
        assert!(matches!(
            write_cadence_rfm(&rfm, &invalid),
            Err(RfmError::Unsupported(_))
        ));
        let wrapper = root.join("common.sp");
        write_cadence_rfm_common_ground_wrapper(&wrapper, &rfm, 2, Some("common")).unwrap();
        let text = fs::read_to_string(wrapper).unwrap();
        assert!(text.contains(".subckt common p1 p2"));
        assert!(text.contains("S1 p1 0 p2 0 mname=s_model"));
        let _ = fs::remove_dir_all(root);
    }
}
