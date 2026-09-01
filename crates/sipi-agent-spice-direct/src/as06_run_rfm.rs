//! AS-06 direct port for `run-rfm`.
//!
//! The parser and frequency-response preflight are portable and numerical.
//! Native/ngspice execution remains an explicit caller-selected process path;
//! no simulator result is invented when the executable is unavailable.

use std::fmt::{Display, Formatter};
use std::fs;
use std::io::Read;
use std::path::{Path, PathBuf};

use num_complex::Complex64 as Complex;
use rayon::prelude::*;
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
const PARALLEL_FREQUENCY_THRESHOLD: usize = 4_096;

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
        // Keep short calls serial so a caller paying for a few samples does
        // not pay for the global Rayon pool; large sweeps are independent by
        // frequency and retain the scalar evaluator's exact operation order.
        if frequencies_hz.len() >= PARALLEL_FREQUENCY_THRESHOLD {
            return Ok(frequencies_hz
                .par_iter()
                .map(|frequency| self.evaluate_s(*frequency))
                .collect());
        }
        let response_count = self.response_count();
        let mut output = frequencies_hz
            .iter()
            .map(|_| vec![Complex::new(0.0, 0.0); response_count])
            .collect::<Vec<_>>();
        for (frequency_index, frequency_hz) in frequencies_hz.iter().enumerate() {
            let s = Complex::new(0.0, 2.0 * std::f64::consts::PI * frequency_hz);
            let row = &mut output[frequency_index];
            for (response, output_value) in row.iter_mut().enumerate() {
                let mut sum = Complex::new(0.0, 0.0);
                for (residue, pole) in self.residues[response].iter().zip(&self.poles) {
                    let primary = *residue / (s - *pole);
                    sum += if pole.im != 0.0 {
                        primary + residue.conj() / (s - pole.conj())
                    } else {
                        primary
                    };
                }
                *output_value = self.constant[response] + sum;
            }
        }
        Ok(output)
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

/// Explicit caller custody for the existing upstream ngspice/XSPICE branch.
/// The code model is an external asset as well as the solver executable, so
/// both identities are required before the process is started.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RfmNgspiceCustody {
    pub executable: crate::NgspiceCustody,
    pub code_model_sha256: String,
}

/// Explicit caller custody for the existing native-engine branch. A DLL
/// engine additionally requires custody of the dotnet host; a native binary
/// does not use that field.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RfmNativeCustody {
    pub engine: crate::NgspiceCustody,
    pub dotnet: Option<crate::NgspiceCustody>,
}

impl RfmNativeCustody {
    pub fn new(engine: crate::NgspiceCustody) -> Self {
        Self {
            engine,
            dotnet: None,
        }
    }

    pub fn with_dotnet(mut self, dotnet: crate::NgspiceCustody) -> Self {
        self.dotnet = Some(dotnet);
        self
    }
}

impl RfmNgspiceCustody {
    pub fn new(executable: crate::NgspiceCustody, code_model_sha256: impl Into<String>) -> Self {
        Self {
            executable,
            code_model_sha256: code_model_sha256.into(),
        }
    }
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
        "VERSION {}\nNPORT {}\nMATRIX_TYPE {}\nZ0 {}\n",
        model.version,
        model.nports,
        model.matrix_type,
        rfm_float(model.z0)
    );
    for row in 0..model.nports {
        for column in 0..model.nports {
            let response = row * model.nports + column;
            text.push_str(&format!(
                "BEGIN {} {}\nConst {}\n",
                row + 1,
                column + 1,
                rfm_float(model.constant[response].re)
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
                    "  {}  {}\n",
                    rfm_float(-pole.re),
                    rfm_float(model.residues[response][index].re)
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
                    "  {}  {}  {}  {}\n",
                    rfm_float(-pole.re),
                    rfm_float(-pole.im),
                    rfm_float(residue.re),
                    rfm_float(residue.im)
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

/// Write the expanded SPICE equivalent exposed by the pinned RFM importer.
/// This is a solver-free artifact path; it does not refit or invoke a backend.
pub fn write_spice_subcircuit(
    model: &RfmModel,
    path: impl AsRef<Path>,
    subcircuit_name: Option<&str>,
    create_reference_pins: bool,
) -> Result<(), RfmError> {
    if model.version != 200600
        || model.matrix_type != "S"
        || model.nports == 0
        || model.nports > MAX_PORTS
        || model.constant.len() != model.response_count()
    {
        return Err(RfmError::InvalidOption(
            "RFM model dimensions are outside the bounded range".to_owned(),
        ));
    }
    if model.z0 <= 0.0 || !model.z0.is_finite() {
        return Err(RfmError::InvalidOption(
            "RFM reference impedance must be finite and positive".to_owned(),
        ));
    }
    if model.residues.len() != model.response_count()
        || model
            .residues
            .iter()
            .any(|row| row.len() != model.poles.len())
    {
        return Err(RfmError::InvalidOption(
            "RFM residue dimensions do not match the model".to_owned(),
        ));
    }
    let name = subcircuit_name.unwrap_or("rfm_imported");
    if !valid_spice_token(name) {
        return Err(RfmError::InvalidOption(
            "subcircuit_name is not a valid SPICE token".to_owned(),
        ));
    }
    let estimated_bytes = estimate_spice_subcircuit_bytes(
        model.nports,
        model.poles.len(),
        create_reference_pins,
        name.len(),
    )
    .ok_or_else(|| RfmError::Output("SPICE artifact size estimate overflowed".to_owned()))?;
    if estimated_bytes > MAX_ARTIFACT_BYTES {
        return Err(RfmError::Output(
            "SPICE subcircuit exceeds byte budget".to_owned(),
        ));
    }
    let path = path.as_ref();
    if model.poles.iter().any(|pole| pole.im < 0.0) {
        return Err(RfmError::Unsupported(
            "RFM complex poles must use the positive-imaginary representative".to_owned(),
        ));
    }
    let sqrt_z0 = model.z0.sqrt();
    let gain_vccs = 1.0 / (2.0 * sqrt_z0);
    let gain_cccs = sqrt_z0 / 2.0;
    let gain_b = 2.0 / sqrt_z0;
    let mut text = String::from(
        "* EQUIVALENT CIRCUIT FOR NATIVE VECTOR FITTED S-MATRIX\n* Created using agent-spice native vector fitting\n*\n",
    );
    let input_nodes = (1..=model.nports)
        .map(|index| {
            if create_reference_pins {
                format!("p{index} p{index}_ref")
            } else {
                format!("p{index}")
            }
        })
        .collect::<Vec<_>>()
        .join(" ");
    text.push_str(&format!(".SUBCKT {name} {input_nodes}\n"));
    for row in 0..model.nports {
        let row_node = format!("p{}", row + 1);
        let row_ref = if create_reference_pins {
            format!("p{}_ref", row + 1)
        } else {
            "0".to_owned()
        };
        let state_node = format!("s{}", row + 1);
        text.push_str("*\n");
        text.push_str(&format!("* Port network for port {}\n", row + 1));
        text.push_str(&format!("V{} {row_node} {state_node} 0\n", row + 1));
        text.push_str(&format!(
            "R{} {state_node} {row_ref} {:.17e}\n",
            row + 1,
            model.z0
        ));
        for column in 0..model.nports {
            let response = row * model.nports + column;
            let column_ref = if create_reference_pins {
                format!("p{}_ref", column + 1)
            } else {
                "0".to_owned()
            };
            let d = model.constant[response].re;
            if !d.is_finite()
                || !model.constant[response].im.is_finite()
                || model.constant[response].im.abs() > 1e-8 * d.abs().max(1.0)
            {
                return Err(RfmError::Unsupported(
                    "RFM constant coefficients must be real".to_owned(),
                ));
            }
            if d != 0.0 {
                let g = gain_b * d * gain_vccs;
                let f = gain_b * d * gain_cccs;
                text.push_str(&format!(
                    "Gd{}_{} {row_ref} {state_node} p{} {column_ref} {:.17e}\n",
                    row + 1,
                    column + 1,
                    column + 1,
                    g
                ));
                text.push_str(&format!(
                    "Fd{}_{} {row_ref} {state_node} V{} {:.17e}\n",
                    row + 1,
                    column + 1,
                    column + 1,
                    f
                ));
            }
            for (pole_index, pole) in model.poles.iter().enumerate() {
                if !pole.re.is_finite() || !pole.im.is_finite() || pole.re >= 0.0 {
                    return Err(RfmError::Unsupported(
                        "RFM poles must be finite and stable".to_owned(),
                    ));
                }
                let residue = model.residues[response][pole_index];
                if !residue.re.is_finite() || !residue.im.is_finite() {
                    return Err(RfmError::Unsupported(
                        "RFM residues must be finite".to_owned(),
                    ));
                }
                let g_re = gain_b * residue.re;
                let g_im = gain_b * residue.im;
                if pole.im == 0.0 {
                    text.push_str(&format!(
                        "Gr{}_{}_{} {row_ref} {state_node} x{}_a{} 0 {:.17e}\n",
                        pole_index + 1,
                        row + 1,
                        column + 1,
                        pole_index + 1,
                        column + 1,
                        g_re
                    ));
                } else if pole.im > 0.0 {
                    text.push_str(&format!(
                        "Gr{}_re_{}_{} {row_ref} {state_node} x{}_re_a{} 0 {:.17e}\n",
                        pole_index + 1,
                        row + 1,
                        column + 1,
                        pole_index + 1,
                        column + 1,
                        g_re
                    ));
                    text.push_str(&format!(
                        "Gr{}_im_{}_{} {row_ref} {state_node} x{}_im_a{} 0 {:.17e}\n",
                        pole_index + 1,
                        row + 1,
                        column + 1,
                        pole_index + 1,
                        column + 1,
                        g_im
                    ));
                }
            }
        }
        text.push_str("*\n");
        text.push_str(&format!("* State networks driven by port {}\n", row + 1));
        for (pole_index, pole) in model.poles.iter().enumerate() {
            if pole.im == 0.0 {
                let state = format!("x{}_a{}", pole_index + 1, row + 1);
                text.push_str(&format!(
                    "Cx{}_a{} {state} 0 1.0\nGx{}_a{} 0 {state} {row_node} {row_ref} {:.17e}\nFx{}_a{} 0 {state} V{} {:.17e}\nRp{}_a{} 0 {state} {:.17e}\n",
                    pole_index + 1, row + 1, pole_index + 1, row + 1, gain_vccs,
                    pole_index + 1, row + 1, row + 1, gain_cccs, pole_index + 1, row + 1, -1.0 / pole.re
                ));
            } else if pole.im > 0.0 {
                let real = format!("x{}_re_a{}", pole_index + 1, row + 1);
                let imag = format!("x{}_im_a{}", pole_index + 1, row + 1);
                text.push_str(&format!(
                    "Cx{}_re_a{} {real} 0 1.0\nGx{}_re_a{} 0 {real} {row_node} {row_ref} {:.17e}\nFx{}_re_a{} 0 {real} V{} {:.17e}\nRp{}_re_re_a{} 0 {real} {:.17e}\nGp{}_re_im_a{} 0 {real} {imag} 0 {:.17e}\nCx{}_im_a{} {imag} 0 1.0\nGp{}_im_re_a{} 0 {imag} {real} 0 {:.17e}\nRp{}_im_im_a{} 0 {imag} {:.17e}\n",
                    pole_index + 1, row + 1, pole_index + 1, row + 1, 2.0 * gain_vccs,
                    pole_index + 1, row + 1, row + 1, 2.0 * gain_cccs,
                    pole_index + 1, row + 1, -1.0 / pole.re,
                    pole_index + 1, row + 1, pole.im,
                    pole_index + 1, row + 1, pole_index + 1, row + 1, -pole.im,
                    pole_index + 1, row + 1, -1.0 / pole.re
                ));
            }
        }
    }
    text.push_str(&format!(".ENDS {name}\n"));
    if text.len() > MAX_ARTIFACT_BYTES {
        return Err(RfmError::Output(
            "SPICE subcircuit exceeds byte budget".to_owned(),
        ));
    }
    write_text(path, &text)
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

fn reconstruction_errors(original: &RfmModel, normalized: &RfmModel) -> (f64, f64) {
    let mut maximum = 0.0_f64;
    let mut squared_sum = 0.0_f64;
    let mut count = 0_usize;
    for frequency in response_frequencies(original) {
        let left = original.evaluate_s(frequency);
        let right = normalized.evaluate_s(frequency);
        for (a, b) in left.iter().zip(right) {
            let magnitude = (*a - b).norm();
            maximum = maximum.max(magnitude);
            squared_sum += magnitude * magnitude;
            count += 1;
        }
    }
    let rms = if count == 0 {
        f64::NAN
    } else {
        (squared_sum / count as f64).sqrt()
    };
    (maximum, rms)
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

fn create_fresh_output_dir(path: &Path) -> Result<(), RfmError> {
    let parent = path
        .parent()
        .ok_or_else(|| RfmError::Output("run-rfm output has no parent directory".to_owned()))?;
    reject_reparse_ancestors(parent)?;
    fs::create_dir_all(parent).map_err(|error| RfmError::Output(error.to_string()))?;
    reject_reparse_ancestors(parent)?;
    let parent_metadata =
        fs::symlink_metadata(parent).map_err(|error| RfmError::Output(error.to_string()))?;
    if parent_metadata.file_type().is_symlink() || !parent_metadata.is_dir() {
        return Err(RfmError::Output(
            "run-rfm output parent must be a regular directory".to_owned(),
        ));
    }
    fs::create_dir(path).map_err(|error| {
        RfmError::Output(format!(
            "run-rfm output directory must be fresh and create-new: {error}"
        ))
    })?;
    let metadata =
        fs::symlink_metadata(path).map_err(|error| RfmError::Output(error.to_string()))?;
    if metadata.file_type().is_symlink() || !metadata.is_dir() {
        return Err(RfmError::Output(
            "run-rfm output directory must be a regular directory".to_owned(),
        ));
    }
    reject_reparse_ancestors(path)?;
    let parent_resolved = parent
        .canonicalize()
        .map_err(|error| RfmError::Output(error.to_string()))?;
    let output_resolved = path
        .canonicalize()
        .map_err(|error| RfmError::Output(error.to_string()))?;
    if !output_resolved.starts_with(&parent_resolved) {
        return Err(RfmError::Output(
            "run-rfm output directory escaped its validated parent".to_owned(),
        ));
    }
    Ok(())
}

fn reject_reparse_ancestors(path: &Path) -> Result<(), RfmError> {
    let mut cursor = Some(path);
    while let Some(current) = cursor {
        match fs::symlink_metadata(current) {
            Ok(metadata) if metadata.file_type().is_symlink() => {
                return Err(RfmError::Output(
                    "run-rfm output path contains a symlink/reparse component".to_owned(),
                ));
            }
            Ok(_) => {}
            Err(error) if error.kind() != std::io::ErrorKind::NotFound => {
                return Err(RfmError::Output(error.to_string()));
            }
            Err(_) => {}
        }
        cursor = current.parent();
    }
    Ok(())
}

// Each emitted SPICE line is bounded by the fixed token and f64 formatting
// widths below. Check the worst-case topology before allocating the artifact.
fn estimate_spice_subcircuit_bytes(
    nports: usize,
    pole_count: usize,
    references: bool,
    name_len: usize,
) -> Option<usize> {
    const LINE_BUDGET: usize = 192;
    let response_lines = 2usize.checked_add(pole_count.checked_mul(2)?)?;
    let state_lines = pole_count.checked_mul(8)?;
    let response_count = nports.checked_mul(nports)?;
    let line_count = nports
        .checked_mul(4)?
        .checked_add(response_count.checked_mul(response_lines)?)?
        .checked_add(nports.checked_mul(state_lines)?)?
        .checked_add(1)?;
    let header_budget = 4096usize
        .checked_add(nports.checked_mul(if references { 24 } else { 8 })?)?
        .checked_add(name_len.checked_mul(2)?)?;
    line_count
        .checked_mul(LINE_BUDGET)?
        .checked_add(header_budget)
}

fn rfm_float(value: f64) -> String {
    let mut text = format!("{value:.12e}");
    if let Some(exponent) = text.find('e') {
        let suffix_len = text.len().saturating_sub(exponent + 1);
        let signed = matches!(text.as_bytes().get(exponent + 1), Some(b'+' | b'-'));
        if !signed {
            text.insert(exponent + 1, '+');
            if suffix_len == 1 {
                text.insert(exponent + 2, '0');
            }
        } else if suffix_len == 2 {
            text.insert(exponent + 2, '0');
        }
    }
    text
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

#[derive(Clone, Debug, PartialEq)]
struct ExternalArtifactReceipt {
    bytes: usize,
    sha256: String,
}

fn read_bounded_external_artifact(
    path: &Path,
    role: &str,
) -> Result<(Vec<u8>, ExternalArtifactReceipt), RfmError> {
    let metadata = fs::symlink_metadata(path)
        .map_err(|error| RfmError::Execution(format!("{role} artifact is unavailable: {error}")))?;
    if metadata.file_type().is_symlink() || !metadata.is_file() {
        return Err(RfmError::Execution(format!(
            "{role} artifact must be a regular non-symlink file"
        )));
    }
    if metadata.len() > MAX_ARTIFACT_BYTES as u64 {
        return Err(RfmError::Execution(format!(
            "{role} artifact exceeds the bounded byte budget"
        )));
    }
    let mut file = fs::File::open(path).map_err(|error| {
        RfmError::Execution(format!("{role} artifact cannot be opened: {error}"))
    })?;
    let mut bytes = Vec::new();
    Read::by_ref(&mut file)
        .take((MAX_ARTIFACT_BYTES + 1) as u64)
        .read_to_end(&mut bytes)
        .map_err(|error| RfmError::Execution(format!("{role} artifact cannot be read: {error}")))?;
    if bytes.len() > MAX_ARTIFACT_BYTES {
        return Err(RfmError::Execution(format!(
            "{role} artifact exceeds the bounded byte budget"
        )));
    }
    let bytes_len = bytes.len();
    let sha256 = format!("{:x}", Sha256::digest(&bytes));
    Ok((
        bytes,
        ExternalArtifactReceipt {
            bytes: bytes_len,
            sha256,
        },
    ))
}

fn inspect_native_waveform(text: &str) -> Result<(usize, String, f64), RfmError> {
    let mut lines = text.lines().filter(|line| !line.trim().is_empty());
    let header = lines
        .next()
        .ok_or_else(|| RfmError::Execution("native waveform header is missing".to_owned()))?;
    let columns = header.split(',').map(str::trim).collect::<Vec<_>>();
    if columns.len() < 2
        || !matches!(
            columns[0].to_ascii_lowercase().as_str(),
            "time" | "frequency" | "sweep"
        )
    {
        return Err(RfmError::Execution(
            "native waveform axis must be time, frequency, or sweep".to_owned(),
        ));
    }
    let probe_indices = columns[1..]
        .iter()
        .enumerate()
        .filter(|(_, name)| name.eq_ignore_ascii_case("v(out)"))
        .map(|(index, _)| index + 1)
        .collect::<Vec<_>>();
    if probe_indices.len() != 1 {
        return Err(RfmError::Execution(
            "native waveform must contain exactly one case-insensitive v(out) column".to_owned(),
        ));
    }
    let probe_index = probe_indices[0];
    let mut rows = 0usize;
    let mut probe_max_abs = 0.0_f64;
    for line in lines {
        let fields = line.split(',').map(str::trim).collect::<Vec<_>>();
        if fields.len() != columns.len() {
            return Err(RfmError::Execution(
                "native waveform row width differs from its header".to_owned(),
            ));
        }
        let values = fields
            .iter()
            .map(|field| field.parse::<f64>())
            .collect::<Result<Vec<_>, _>>()
            .map_err(|error| {
                RfmError::Execution(format!("native waveform value is invalid: {error}"))
            })?;
        if values.iter().any(|value| !value.is_finite()) {
            return Err(RfmError::Execution(
                "native waveform values must be finite".to_owned(),
            ));
        }
        probe_max_abs = probe_max_abs.max(values[probe_index].abs());
        rows += 1;
    }
    Ok((rows, columns[probe_index].to_owned(), probe_max_abs))
}

fn parse_native_execution_summary(stdout: &[u8]) -> Result<(bool, u64), RfmError> {
    let text = String::from_utf8(stdout.to_vec())
        .map_err(|error| RfmError::Execution(format!("native stdout is not UTF-8: {error}")))?;
    let lines = text
        .lines()
        .filter(|line| !line.trim().is_empty())
        .collect::<Vec<_>>();
    if lines.len() != 1 {
        return Err(RfmError::Execution(
            "native stdout must contain exactly one JSON execution summary".to_owned(),
        ));
    }
    let value: serde_json::Value = serde_json::from_str(lines[0]).map_err(|error| {
        RfmError::Execution(format!("native stdout summary is not JSON: {error}"))
    })?;
    let object = value.as_object().ok_or_else(|| {
        RfmError::Execution("native stdout summary must be a JSON object".to_owned())
    })?;
    if object.len() != 2 || !object.contains_key("ok") || !object.contains_key("waveformRows") {
        return Err(RfmError::Execution(
            "native stdout summary must have exactly ok and waveformRows".to_owned(),
        ));
    }
    let ok = object
        .get("ok")
        .and_then(serde_json::Value::as_bool)
        .ok_or_else(|| RfmError::Execution("native stdout ok must be boolean".to_owned()))?;
    let rows = object
        .get("waveformRows")
        .and_then(serde_json::Value::as_u64)
        .ok_or_else(|| {
            RfmError::Execution("native stdout waveformRows must be integer".to_owned())
        })?;
    Ok((ok, rows))
}

fn validate_native_simulation_result(value: &serde_json::Value) -> Result<(), RfmError> {
    let object = value.as_object().ok_or_else(|| {
        RfmError::Execution("native result must be a SimulationResult object".to_owned())
    })?;
    if !object.get("nodes").is_some_and(serde_json::Value::is_array)
        || !object
            .get("points")
            .is_some_and(serde_json::Value::is_array)
        || !object
            .get("statistics")
            .is_some_and(serde_json::Value::is_object)
    {
        return Err(RfmError::Execution(
            "native result must contain nodes, points, and statistics".to_owned(),
        ));
    }
    if let Some(measurements) = object.get("measurements")
        && !measurements.is_array()
    {
        return Err(RfmError::Execution(
            "native result measurements must be an array".to_owned(),
        ));
    }
    Ok(())
}

fn native_arguments(
    prepared_deck: &Path,
    subckt_name: &str,
    staged_rfm: &Path,
    native_json: &Path,
    waveform: &Path,
) -> Vec<PathBuf> {
    vec![
        prepared_deck.to_path_buf(),
        PathBuf::from("--rfm-subckt"),
        PathBuf::from(subckt_name),
        PathBuf::from("--rfm"),
        staged_rfm.to_path_buf(),
        PathBuf::from("--output-json"),
        native_json.to_path_buf(),
        PathBuf::from("--waveform-csv"),
        waveform.to_path_buf(),
    ]
}

fn write_ngspice_waveform_csv(text: &str, path: &Path) -> Result<(usize, String, f64), RfmError> {
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
        if values.iter().any(|value| !value.is_finite()) {
            continue;
        }
        rows.push(values);
    }
    let Some(columns) = columns else {
        return Ok((0, String::new(), 0.0));
    };
    if rows.is_empty() {
        return Ok((0, String::new(), 0.0));
    }
    let probe_indices = columns
        .iter()
        .enumerate()
        .filter(|(_, name)| name.trim().eq_ignore_ascii_case("v(out)"))
        .map(|(index, _)| index)
        .collect::<Vec<_>>();
    if probe_indices.len() != 1 {
        return Err(RfmError::Execution(
            "ngspice waveform must contain exactly one case-insensitive v(out) probe column"
                .to_owned(),
        ));
    }
    let probe_index = probe_indices[0];
    let probe_name = columns[probe_index].trim();
    let probe_max_abs = rows
        .iter()
        .map(|row| row[probe_index].abs())
        .fold(0.0, f64::max);
    let probe_name = probe_name.to_owned();
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
    Ok((rows.len(), probe_name, probe_max_abs))
}

fn ngspice_model_error(text: &str) -> bool {
    let lower = text.to_ascii_lowercase();
    lower.contains("nport_rfm")
        && ["error", "invalid", "failed", "failure"]
            .iter()
            .any(|needle| lower.contains(needle))
}

fn sha256_file(path: &Path) -> Result<String, RfmError> {
    let metadata =
        fs::symlink_metadata(path).map_err(|error| RfmError::Input(error.to_string()))?;
    if metadata.file_type().is_symlink() || !metadata.is_file() {
        return Err(RfmError::Input(
            "hashed artifact must be a regular non-symlink file".to_owned(),
        ));
    }
    if metadata.len() > MAX_ARTIFACT_BYTES as u64 {
        return Err(RfmError::Input(
            "hashed artifact exceeds the bounded 8 MiB budget".to_owned(),
        ));
    }
    let mut file = fs::File::open(path).map_err(|error| RfmError::Input(error.to_string()))?;
    let mut digest = Sha256::new();
    let mut buffer = [0_u8; 64 * 1024];
    let mut total = 0_u64;
    loop {
        let count = file
            .read(&mut buffer)
            .map_err(|error| RfmError::Input(error.to_string()))?;
        if count == 0 {
            break;
        }
        total = total
            .checked_add(count as u64)
            .ok_or_else(|| RfmError::Input("hashed artifact size overflow".to_owned()))?;
        if total > MAX_ARTIFACT_BYTES as u64 {
            return Err(RfmError::Input(
                "hashed artifact exceeds the bounded 8 MiB budget".to_owned(),
            ));
        }
        digest.update(&buffer[..count]);
    }
    let after = fs::symlink_metadata(path).map_err(|error| RfmError::Input(error.to_string()))?;
    if after.file_type().is_symlink() || !after.is_file() || after.len() != metadata.len() {
        return Err(RfmError::Input(
            "hashed artifact changed during bounded read".to_owned(),
        ));
    }
    Ok(format!("{:x}", digest.finalize()))
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
    run_rfm_internal(request, None, None)
}

/// Execute the pinned ngspice/XSPICE branch with explicit caller custody.
/// `run_rfm` remains preparation-only when execution is requested without
/// this additive custody object.
pub fn run_rfm_with_ngspice_custody(
    request: &RunRfmRequest,
    custody: &RfmNgspiceCustody,
) -> Result<RunRfmResult, RfmError> {
    run_rfm_internal(request, Some(custody), None)
}

/// Execute the pinned native-engine branch with explicit caller custody.
/// `run_rfm` remains preparation-only when native execution is requested
/// without this additive custody object.
pub fn run_rfm_with_native_custody(
    request: &RunRfmRequest,
    custody: &RfmNativeCustody,
) -> Result<RunRfmResult, RfmError> {
    run_rfm_internal(request, None, Some(custody))
}

fn run_rfm_internal(
    request: &RunRfmRequest,
    ngspice_custody: Option<&RfmNgspiceCustody>,
    native_custody: Option<&RfmNativeCustody>,
) -> Result<RunRfmResult, RfmError> {
    if request.execute
        && ((request.backend == RfmBackend::Ngspice && ngspice_custody.is_none())
            || (request.backend == RfmBackend::Native && native_custody.is_none()))
    {
        return Err(RfmError::Execution(
            "external simulator execution is fail-closed: explicit backend custody is required"
                .to_owned(),
        ));
    }
    if request.execute {
        match request.backend {
            RfmBackend::Ngspice => {
                let custody = ngspice_custody.expect("ngspice custody admission was checked above");
                let requested_solver = crate::absolute_path(Path::new(&request.ngspice))
                    .map_err(|error| RfmError::Execution(error.to_string()))?;
                let custody_solver = crate::absolute_path(&custody.executable.executable)
                    .map_err(|error| RfmError::Execution(error.to_string()))?;
                if requested_solver != custody_solver {
                    return Err(RfmError::Execution(
                        "request.ngspice and custody executable must resolve to the same path"
                            .to_owned(),
                    ));
                }
            }
            RfmBackend::Native => {
                let custody = native_custody.expect("native custody admission was checked above");
                let requested_engine = request.native_engine.as_ref().ok_or_else(|| {
                    RfmError::Execution(
                        "native backend requires --native-engine; no fallback is attempted"
                            .to_owned(),
                    )
                })?;
                let requested_engine = crate::absolute_path(requested_engine)
                    .map_err(|error| RfmError::Execution(error.to_string()))?;
                let custody_engine = crate::absolute_path(&custody.engine.executable)
                    .map_err(|error| RfmError::Execution(error.to_string()))?;
                if requested_engine != custody_engine {
                    return Err(RfmError::Execution(
                        "request.native_engine and custody engine must resolve to the same path"
                            .to_owned(),
                    ));
                }
                let is_dll = requested_engine
                    .extension()
                    .is_some_and(|value| value.eq_ignore_ascii_case("dll"));
                if is_dll != custody.dotnet.is_some() {
                    return Err(RfmError::Execution(
                        "native DLL execution requires exactly one attested dotnet custody"
                            .to_owned(),
                    ));
                }
                if let Some(dotnet) = &custody.dotnet {
                    let requested_dotnet = crate::absolute_path(Path::new(&request.dotnet))
                        .map_err(|error| RfmError::Execution(error.to_string()))?;
                    let custody_dotnet = crate::absolute_path(&dotnet.executable)
                        .map_err(|error| RfmError::Execution(error.to_string()))?;
                    if requested_dotnet != custody_dotnet {
                        return Err(RfmError::Execution(
                            "request.dotnet and custody dotnet must resolve to the same path"
                                .to_owned(),
                        ));
                    }
                }
            }
        }
    }
    let native_identity = if request.execute && request.backend == RfmBackend::Native {
        let custody = native_custody.expect("native custody admission was checked above");
        let engine = crate::attest_external_executable(
            &custody.engine.executable,
            Some(&custody.engine.sha256),
            "native engine",
        )
        .map_err(|error| RfmError::Execution(error.to_string()))?;
        let dotnet = custody
            .dotnet
            .as_ref()
            .map(|value| {
                crate::attest_external_executable(
                    &value.executable,
                    Some(&value.sha256),
                    "dotnet host",
                )
                .map_err(|error| RfmError::Execution(error.to_string()))
            })
            .transpose()?;
        Some((engine, dotnet))
    } else {
        None
    };
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
    create_fresh_output_dir(&output_root)?;
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
    let (response_max_error, response_rms_error) = reconstruction_errors(&model, &normalized);
    let mut delivered_response_max = max_response_abs(&model);
    if !response_max_error.is_finite()
        || !response_rms_error.is_finite()
        || response_max_error > 1e-11
    {
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
            "reconstruction_rms": response_rms_error,
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
        let mut code_model_source_identity = None;
        let mut code_model_staged_identity = None;
        let mut code_model_staged_post_sha = None;
        let mut code_model_source_post_sha = None;
        let mut ngspice_post_sha = None;
        let mut ngspice_identity = None;
        let mut native_engine_path = None;
        let mut native_engine_sha = None;
        let mut native_engine_post_sha = None;
        let mut native_dotnet_identity = None;
        let mut native_dotnet_post_sha = None;
        let (program, arguments) = match request.backend {
            RfmBackend::Native => {
                let (engine, dotnet) = native_identity.clone().ok_or_else(|| {
                    RfmError::Execution("native engine custody was not recorded".to_owned())
                })?;
                let executable = engine.0;
                native_engine_path = Some(executable.clone());
                native_engine_sha = Some(engine.1);
                native_dotnet_identity = dotnet.clone();
                let (program, mut native_args) = if executable
                    .extension()
                    .is_some_and(|value| value.eq_ignore_ascii_case("dll"))
                {
                    let dotnet = dotnet.ok_or_else(|| {
                        RfmError::Execution(
                            "native DLL execution requires attested dotnet custody".to_owned(),
                        )
                    })?;
                    (dotnet.0, vec![executable.clone()])
                } else {
                    (executable.clone(), Vec::new())
                };
                native_args.extend(native_arguments(
                    &prepared_deck,
                    &request.subckt_name,
                    &staged_rfm,
                    &native_json,
                    &waveform,
                ));
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
                let code_model_metadata = fs::symlink_metadata(&code_model).map_err(|error| {
                    RfmError::Execution(format!("ngspice code-model is unavailable: {error}"))
                })?;
                if code_model_metadata.file_type().is_symlink() || !code_model_metadata.is_file() {
                    return Err(RfmError::Execution(
                        "ngspice code-model must be a regular non-symlink file".to_owned(),
                    ));
                }
                if code_model_metadata.len() > MAX_ARTIFACT_BYTES as u64 {
                    return Err(RfmError::Execution(
                        "ngspice code-model exceeds the 8 MiB byte budget".to_owned(),
                    ));
                }
                let custody = ngspice_custody.ok_or_else(|| {
                    RfmError::Execution(
                        "ngspice backend requires explicit caller custody".to_owned(),
                    )
                })?;
                let code_model_sha = crate::file_sha256(&code_model)
                    .map_err(|error| RfmError::Execution(error.to_string()))?;
                if code_model_sha != custody.code_model_sha256.to_ascii_lowercase() {
                    return Err(RfmError::Execution(
                        "ngspice code-model SHA-256 does not match caller custody".to_owned(),
                    ));
                }
                code_model_source_identity = Some((code_model.clone(), code_model_sha));
                let (ngspice_path, ngspice_sha) = crate::attest_external_executable(
                    &custody.executable.executable,
                    Some(&custody.executable.sha256),
                    "ngspice",
                )
                .map_err(|error| RfmError::Execution(error.to_string()))?;
                ngspice_identity = Some((ngspice_path.clone(), ngspice_sha));
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
                let staged_metadata = fs::symlink_metadata(&staged_model).map_err(|error| {
                    RfmError::Execution(format!(
                        "staged ngspice code model is unavailable: {error}"
                    ))
                })?;
                if staged_metadata.file_type().is_symlink() || !staged_metadata.is_file() {
                    return Err(RfmError::Execution(
                        "staged ngspice code model must be a regular non-symlink file".to_owned(),
                    ));
                }
                if staged_metadata.len() > MAX_ARTIFACT_BYTES as u64 {
                    return Err(RfmError::Execution(
                        "staged ngspice code model exceeds the 8 MiB byte budget".to_owned(),
                    ));
                }
                let staged_sha = sha256_file(&staged_model)
                    .map_err(|error| RfmError::Execution(error.to_string()))?;
                let source_sha = custody.code_model_sha256.to_ascii_lowercase();
                if staged_sha != source_sha {
                    return Err(RfmError::Execution(
                        "staged ngspice code-model SHA-256 does not match caller custody"
                            .to_owned(),
                    ));
                }
                code_model_staged_identity = Some((staged_model.clone(), staged_sha));
                // Windows `canonicalize` can return an extended `\\?\\` path
                // which ngspice does not accept in `spinit`; the output root
                // is already absolute and freshly created, so retain it.
                let staged_model_path = staged_model.clone();
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
                    ngspice_path,
                    vec![PathBuf::from("-b"), prepared_deck.clone()],
                )
            }
        };
        let result = if request.backend == RfmBackend::Ngspice {
            let scripts = ngspice_scripts.as_deref().ok_or_else(|| {
                RfmError::Execution("ngspice SPICE_SCRIPTS staging is missing".to_owned())
            })?;
            let output = crate::run_external_process_with_spice_scripts(
                &program,
                &arguments,
                &output_root,
                scripts,
            )
            .map_err(|error| RfmError::Execution(error.to_string()))?;
            if let Some((path, before_sha)) = &ngspice_identity {
                let after_sha = crate::file_sha256(path)
                    .map_err(|error| RfmError::Execution(error.to_string()))?;
                if &after_sha != before_sha {
                    return Err(RfmError::Execution(
                        "ngspice executable changed during execution".to_owned(),
                    ));
                }
                ngspice_post_sha = Some(after_sha);
            }
            if let Some((path, before_sha)) = &code_model_source_identity {
                let after_sha =
                    sha256_file(path).map_err(|error| RfmError::Execution(error.to_string()))?;
                if &after_sha != before_sha {
                    return Err(RfmError::Execution(
                        "ngspice code-model changed during execution".to_owned(),
                    ));
                }
                code_model_source_post_sha = Some(after_sha);
            }
            if let Some((path, before_sha)) = &code_model_staged_identity {
                let after_sha =
                    sha256_file(path).map_err(|error| RfmError::Execution(error.to_string()))?;
                if &after_sha != before_sha {
                    return Err(RfmError::Execution(
                        "staged ngspice code-model changed during execution".to_owned(),
                    ));
                }
                code_model_staged_post_sha = Some(after_sha);
            }
            output
        } else {
            let output = crate::run_native_external_process(&program, &arguments, &output_root)
                .map_err(|error| RfmError::Execution(error.to_string()))?;
            if let Some((path, before_sha)) = native_identity.as_ref().map(|value| &value.0) {
                let after_sha = crate::file_sha256(path)
                    .map_err(|error| RfmError::Execution(error.to_string()))?;
                if &after_sha != before_sha {
                    return Err(RfmError::Execution(
                        "native engine changed during execution".to_owned(),
                    ));
                }
                native_engine_post_sha = Some(after_sha);
            }
            if let Some((path, before_sha)) = &native_dotnet_identity {
                let after_sha = crate::file_sha256(path)
                    .map_err(|error| RfmError::Execution(error.to_string()))?;
                if &after_sha != before_sha {
                    return Err(RfmError::Execution(
                        "dotnet host changed during execution".to_owned(),
                    ));
                }
                native_dotnet_post_sha = Some(after_sha);
            }
            output
        };
        write_text(
            &output_root.join("stdout.log"),
            &String::from_utf8_lossy(&result.stdout),
        )?;
        write_text(
            &output_root.join("stderr.log"),
            &String::from_utf8_lossy(&result.stderr),
        )?;
        let ngspice_model_failed = request.backend == RfmBackend::Ngspice
            && (ngspice_model_error(&String::from_utf8_lossy(&result.stdout))
                || ngspice_model_error(&String::from_utf8_lossy(&result.stderr)));
        let mut backend_ok = result.status.success() && !ngspice_model_failed;
        let mut native_waveform_rows = 0u64;
        let mut native_waveform_probe = String::new();
        let mut native_waveform_max_abs = 0.0;
        let mut native_result_receipt = None;
        let mut native_waveform_receipt = None;
        let mut native_result_error = None;
        let mut native_summary_rows = None;
        if request.backend == RfmBackend::Native && backend_ok {
            match parse_native_execution_summary(&result.stdout) {
                Err(error) => {
                    backend_ok = false;
                    native_result_error = Some(error.to_string());
                }
                Ok((ok, rows)) if !ok => {
                    backend_ok = false;
                    native_result_error =
                        Some("native stdout execution summary reported ok=false".to_owned());
                    native_summary_rows = Some(rows);
                }
                Ok((_ok, rows)) => native_summary_rows = Some(rows),
            }
            match read_bounded_external_artifact(&native_json, "native result") {
                Err(error) => {
                    backend_ok = false;
                    native_result_error = Some(error.to_string());
                }
                Ok((bytes, receipt)) => match serde_json::from_slice::<serde_json::Value>(&bytes) {
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
                        if let Err(error) = validate_native_simulation_result(&value) {
                            backend_ok = false;
                            native_result_error = Some(error.to_string());
                        } else if let Some(rows) = native_summary_rows {
                            native_result_receipt = Some(receipt);
                            match read_bounded_external_artifact(&waveform, "native waveform") {
                                Err(error) => {
                                    backend_ok = false;
                                    native_result_error = Some(error.to_string());
                                }
                                Ok((waveform_bytes, waveform_receipt)) => {
                                    let waveform_text =
                                        String::from_utf8(waveform_bytes).map_err(|error| {
                                            RfmError::Execution(format!(
                                                "native waveform is not UTF-8: {error}"
                                            ))
                                        })?;
                                    match inspect_native_waveform(&waveform_text) {
                                        Err(error) => {
                                            backend_ok = false;
                                            native_result_error = Some(error.to_string());
                                        }
                                        Ok((parsed_rows, probe, probe_max_abs)) => {
                                            native_waveform_rows = parsed_rows as u64;
                                            if parsed_rows as u64 != rows
                                                || !probe_max_abs.is_finite()
                                                || probe_max_abs <= 0.0
                                            {
                                                backend_ok = false;
                                                native_result_error = Some(
                                                    "native waveform rows/probe receipt mismatch"
                                                        .to_owned(),
                                                );
                                            } else {
                                                native_waveform_probe = probe;
                                                native_waveform_max_abs = probe_max_abs;
                                                native_waveform_receipt = Some(waveform_receipt);
                                            }
                                        }
                                    }
                                }
                            }
                        } else {
                            backend_ok = false;
                            native_result_error =
                                Some("native stdout summary rows were unavailable".to_owned());
                        }
                    }
                },
            }
        }
        execution = json!({"requested": true, "backend": request.backend.as_str(), "status": if backend_ok { "EXECUTED" } else { "FAIL" }, "returncode": result.status.code(), "stdout_bytes": result.stdout.len(), "stderr_bytes": result.stderr.len(), "logs": {"stdout": "stdout.log", "stderr": "stderr.log"}});
        if let Some((_, before_sha)) = &ngspice_identity {
            execution["solver_identity"] = json!({
                "path": "caller-attested-executable",
                "path_redacted": true,
                "sha256_before": before_sha,
                "sha256_after": ngspice_post_sha,
            });
        }
        if request.backend == RfmBackend::Native {
            execution["solver_identity"] = json!({
                "path": "caller-attested-engine",
                "path_redacted": true,
                "sha256_before": native_engine_sha.clone(),
                "sha256_after": native_engine_post_sha.clone(),
            });
            if let Some((_, before_sha)) = &native_dotnet_identity {
                execution["dotnet_identity"] = json!({
                    "path": "caller-attested-dotnet",
                    "path_redacted": true,
                    "sha256_before": before_sha,
                    "sha256_after": native_dotnet_post_sha.clone(),
                });
            }
        }
        if let Some(error) = native_result_error {
            execution["result_error"] = json!(error);
        }
        if let Some(receipt) = &native_result_receipt {
            execution["native_result"] = json!({
                "path": "native_result.json",
                "bytes": receipt.bytes,
                "sha256": receipt.sha256,
            });
        }
        if let Some(receipt) = &native_waveform_receipt {
            execution["waveform"] = json!({
                "path": "waveform.csv",
                "bytes": receipt.bytes,
                "sha256": receipt.sha256,
                "rows": native_waveform_rows,
                "probe": native_waveform_probe,
                "probe_max_abs": native_waveform_max_abs,
            });
        }
        if let Some((_source, _staged)) = ngspice_code_model {
            let staged_sha = code_model_staged_post_sha.clone().ok_or_else(|| {
                RfmError::Execution(
                    "staged ngspice code-model identity was not finalized".to_owned(),
                )
            })?;
            execution["code_model"] = json!({
                "source": "caller-code-model",
                "staged": "staged/.ngspice-code-models/000-code-model",
                "path_redacted": true,
                "source_sha256_before": code_model_source_identity.as_ref().map(|(_, sha)| sha),
                "source_sha256_after": code_model_source_post_sha,
                "staged_sha256_before": code_model_staged_identity.as_ref().map(|(_, sha)| sha),
                "staged_sha256_after": staged_sha,
            });
        }
        if request.backend == RfmBackend::Ngspice {
            let stdout = String::from_utf8_lossy(&result.stdout);
            let (waveform_rows, waveform_probe, waveform_probe_max_abs) =
                write_ngspice_waveform_csv(&stdout, &output_root.join("waveform.csv"))?;
            let measurements = parse_ngspice_measurements(&stdout);
            if waveform_rows == 0
                || waveform_probe.is_empty()
                || !waveform_probe_max_abs.is_finite()
                || waveform_probe_max_abs <= 0.0
            {
                backend_ok = false;
            }
            delivered_response_max = waveform_probe_max_abs;
            execution["waveform"] = json!({
                "path": "waveform.csv",
                "format": "csv",
                "rows": waveform_rows,
                "probe": waveform_probe,
                "probe_max_abs": waveform_probe_max_abs,
                "exists": output_root.join("waveform.csv").is_file(),
            });
            execution["measurements"] = json!(measurements);
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
            let _engine = native_engine_path.ok_or_else(|| {
                RfmError::Execution("native engine path was not recorded".to_owned())
            })?;
            let mut summary = json!({
                "schema_version": 1,
                "backend": "agent-spice-native-rfm",
                "ok": backend_ok,
                "returncode": result.status.code(),
                "engine": {
                    "path": "caller-attested-engine",
                    "path_redacted": true,
                "sha256_before": native_engine_sha.clone(),
                "sha256_after": native_engine_post_sha.clone(),
                },
                "logs": {"stdout": "stdout.log", "stderr": "stderr.log"},
                "result": if backend_ok && native_json.is_file() { serde_json::Value::String("native_result.json".to_owned()) } else { serde_json::Value::Null },
                "waveform": if native_waveform_rows > 0 && waveform.is_file() { serde_json::Value::String("waveform.csv".to_owned()) } else { serde_json::Value::Null },
                "waveform_rows": native_waveform_rows,
                "artifacts": {
                    "native_result": execution.get("native_result").cloned().unwrap_or(serde_json::Value::Null),
                    "waveform": execution.get("waveform").cloned().unwrap_or(serde_json::Value::Null),
                },
            });
            if let Some((_, before_sha)) = &native_dotnet_identity {
                summary["dotnet"] = json!({
                    "path": "caller-attested-dotnet",
                    "path_redacted": true,
                    "sha256_before": before_sha,
                    "sha256_after": native_dotnet_post_sha.clone(),
                });
            }
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
        "response_max_abs": delivered_response_max,
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
        let written = root.join("written.rfm");
        write_cadence_rfm(&written, &model).unwrap();
        let written_text = fs::read_to_string(&written).unwrap();
        assert!(written_text.contains("Const 0.000000000000e+00"));
        assert!(!written_text.contains("CONST"));
        assert!(!written_text.contains("C 0"));
        assert!(parse_cadence_rfm(&written).is_ok());
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
    fn batch_kernel_is_bitwise_equal_to_scalar_kernel_on_65536_point_fixture() {
        let path = Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../examples/circuit/rfm-deck/models/channel.rfm");
        let model = parse_cadence_rfm(&path).unwrap();
        let frequency_count = 65_536_usize;
        let frequencies = (0..frequency_count)
            .map(|index| 200.0e9 * (index as f64) / ((frequency_count - 1) as f64))
            .collect::<Vec<_>>();
        let batch = model.evaluate_s_many(&frequencies).unwrap();
        assert_eq!(batch.len(), frequencies.len());
        for (frequency_index, (frequency, row)) in frequencies.iter().zip(&batch).enumerate() {
            let scalar = model.evaluate_s(*frequency);
            assert_eq!(row.len(), scalar.len());
            for (response_index, (actual, expected)) in row.iter().zip(&scalar).enumerate() {
                assert_eq!(
                    actual.re.to_bits(),
                    expected.re.to_bits(),
                    "real mismatch at frequency {frequency_index}, response {response_index}"
                );
                assert_eq!(
                    actual.im.to_bits(),
                    expected.im.to_bits(),
                    "imag mismatch at frequency {frequency_index}, response {response_index}"
                );
            }
        }
    }

    #[test]
    fn serial_batch_kernel_is_bitwise_equal_to_scalar_kernel_below_parallel_threshold() {
        let path = Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../examples/circuit/rfm-deck/models/channel.rfm");
        let model = parse_cadence_rfm(&path).unwrap();
        let frequency_count = PARALLEL_FREQUENCY_THRESHOLD - 1;
        let frequencies = (0..frequency_count)
            .map(|index| 200.0e9 * (index as f64) / ((frequency_count - 1) as f64))
            .collect::<Vec<_>>();
        let batch = model.evaluate_s_many(&frequencies).unwrap();
        for (frequency_index, (frequency, row)) in frequencies.iter().zip(&batch).enumerate() {
            for (response_index, (actual, expected)) in row
                .iter()
                .zip(model.evaluate_s(*frequency).iter())
                .enumerate()
            {
                assert_eq!(
                    actual.re.to_bits(),
                    expected.re.to_bits(),
                    "real mismatch at frequency {frequency_index}, response {response_index}"
                );
                assert_eq!(
                    actual.im.to_bits(),
                    expected.im.to_bits(),
                    "imaginary mismatch at frequency {frequency_index}, response {response_index}"
                );
            }
        }
    }

    #[test]
    fn expanded_spice_subcircuit_matches_native_vf_artifact_shape() {
        let root = std::env::temp_dir().join(format!("sipi-as06-spice-{}", std::process::id()));
        fs::create_dir_all(&root).unwrap();
        let path = root.join("rfm_imported.sp");
        let model = RfmModel {
            version: 200600,
            nports: 1,
            matrix_type: "S".to_owned(),
            z0: 50.0,
            poles: vec![Complex::new(-1.0, 0.0), Complex::new(-2.0, 3.0)],
            residues: vec![vec![Complex::new(0.5, 0.0), Complex::new(0.25, -0.125)]],
            constant: vec![Complex::new(0.1, 0.0)],
        };
        write_spice_subcircuit(&model, &path, Some("rfm_test"), true).unwrap();
        let text = fs::read_to_string(&path).unwrap();
        assert!(text.contains("* EQUIVALENT CIRCUIT FOR NATIVE VECTOR FITTED S-MATRIX"));
        assert!(text.contains(".SUBCKT rfm_test p1 p1_ref"));
        assert!(text.contains("V1 p1 s1 0"));
        assert!(text.contains("R1 s1 p1_ref"));
        assert!(text.contains("Gd1_1 p1_ref s1 p1 p1_ref"));
        assert!(text.contains("Gr1_1_1 p1_ref s1 x1_a1"));
        assert!(text.contains("Gr2_re_1_1 p1_ref s1 x2_re_a1"));
        assert!(text.contains("Gr2_im_1_1 p1_ref s1 x2_im_a1"));
        assert!(text.contains("Cx1_a1 x1_a1 0 1.0"));
        assert!(text.contains("Cx2_re_a1 x2_re_a1 0 1.0"));
        assert!(text.contains(".ENDS rfm_test"));
        let invalid = RfmModel {
            poles: vec![Complex::new(-2.0, -3.0)],
            residues: vec![vec![Complex::new(0.25, 0.0)]],
            ..model
        };
        assert!(matches!(
            write_spice_subcircuit(&invalid, root.join("invalid.sp"), None, false),
            Err(RfmError::Unsupported(message)) if message.contains("positive-imaginary")
        ));
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn expanded_spice_subcircuit_rejects_over_budget_topology_before_write() {
        let root =
            std::env::temp_dir().join(format!("sipi-as06-spice-budget-{}", std::process::id()));
        fs::create_dir_all(&root).unwrap();
        let path = root.join("too-large.sp");
        let model = RfmModel {
            version: 200600,
            nports: 1,
            matrix_type: "S".to_owned(),
            z0: 50.0,
            poles: (0..5_000)
                .map(|index| Complex::new(-(index as f64 + 1.0), 0.0))
                .collect(),
            residues: vec![vec![Complex::new(0.0, 0.0); 5_000]],
            constant: vec![Complex::new(0.0, 0.0)],
        };
        assert!(matches!(
            write_spice_subcircuit(&model, &path, None, false),
            Err(RfmError::Output(message)) if message.contains("byte budget")
        ));
        assert!(!path.exists());
        let _ = fs::remove_dir_all(root);
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
        let manifest: serde_json::Value =
            serde_json::from_slice(&fs::read(run_root.join("rfm_run_manifest.json")).unwrap())
                .unwrap();
        assert_eq!(manifest["runtime_rfm"]["reconstruction_rms"], 0.0);
        assert_eq!(report["conversion"]["backend"], "ngspice");
        assert!(
            !report["conversion"]["actions"]
                .as_array()
                .unwrap()
                .is_empty()
        );
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
    fn native_execution_requires_explicit_custody() {
        let root =
            std::env::temp_dir().join(format!("sipi-as06-native-custody-{}", std::process::id()));
        let request = RunRfmRequest::new(
            root.join("deck.sp"),
            root.join("model.rfm"),
            "native",
            root.join("out"),
        )
        .unwrap()
        .with_native_engine(std::env::current_exe().unwrap())
        .execute(true);
        assert!(matches!(
            run_rfm(&request),
            Err(RfmError::Execution(message)) if message.contains("custody")
        ));
        assert!(!root.join("out").exists());
    }

    #[test]
    fn native_custody_attests_engine_before_input_consumption() {
        let root =
            std::env::temp_dir().join(format!("sipi-as06-native-attest-{}", std::process::id()));
        let engine = std::env::current_exe().unwrap();
        let request = RunRfmRequest::new(
            root.join("deck.sp"),
            root.join("model.rfm"),
            "native",
            root.join("out"),
        )
        .unwrap()
        .with_native_engine(engine.clone())
        .execute(true);
        let custody = RfmNativeCustody::new(crate::NgspiceCustody::new(engine, "0".repeat(64)));
        assert!(matches!(
            run_rfm_with_native_custody(&request, &custody),
            Err(RfmError::Execution(message)) if message.contains("SHA-256")
        ));
        assert!(!root.join("out").exists());
    }

    #[test]
    fn explicit_ngspice_custody_rejects_wrong_solver_or_model_digest() {
        let root =
            std::env::temp_dir().join(format!("sipi-as06-explicit-custody-{}", std::process::id()));
        fs::create_dir_all(&root).unwrap();
        let deck = root.join("deck.sp");
        let rfm = root.join("model.rfm");
        let code_model = root.join("rfm.cm");
        fs::write(&deck, ".tran 1p 1n\n.end\n").unwrap();
        fs::write(
            &rfm,
            "VERSION 200600\nNPORT 1\nMATRIX_TYPE S\nZ0 50\nBEGIN 1 1\nCONST 0\nC 0\nDELAY 0\nBEGIN_REAL 0\nBEGIN_COMPLEX 0\nEND\n",
        )
        .unwrap();
        fs::write(&code_model, b"caller-owned code model").unwrap();
        let mut request = RunRfmRequest::new(&deck, &rfm, "ngspice", root.join("out"))
            .unwrap()
            .with_code_model(&code_model)
            .execute(true);
        request.ngspice = std::env::current_exe()
            .unwrap()
            .to_string_lossy()
            .into_owned();
        let custody = RfmNgspiceCustody::new(
            crate::NgspiceCustody::new(std::env::current_exe().unwrap(), "0".repeat(64)),
            "0".repeat(64),
        );
        let result = run_rfm_with_ngspice_custody(&request, &custody);
        assert!(matches!(result, Err(RfmError::Execution(message)) if message.contains("SHA-256")));
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn ngspice_model_diagnostics_are_case_insensitive_and_fail_closed() {
        assert!(ngspice_model_error("nport_rfm: invalid Const"));
        assert!(ngspice_model_error("NPORT_RFM ERROR: failed to load model"));
        assert!(ngspice_model_error("nPoRt_RfM: FAILURE"));
        assert!(!ngspice_model_error("nport_rfm: model loaded"));
    }

    #[test]
    fn ngspice_request_and_custody_path_mismatch_is_rejected() {
        let root = std::env::temp_dir().join(format!(
            "sipi-as06-solver-path-mismatch-{}",
            std::process::id()
        ));
        fs::create_dir_all(&root).unwrap();
        let deck = root.join("deck.sp");
        let rfm = root.join("model.rfm");
        let code_model = root.join("rfm.cm");
        fs::write(&deck, ".tran 1p 1n\n.end\n").unwrap();
        fs::write(
            &rfm,
            "VERSION 200600\nNPORT 1\nMATRIX_TYPE S\nZ0 50\nBEGIN 1 1\nCONST 0\nBEGIN_REAL 0\nBEGIN_COMPLEX 0\nEND\n",
        )
        .unwrap();
        fs::write(&code_model, b"caller-owned code model").unwrap();
        let request = RunRfmRequest::new(&deck, &rfm, "ngspice", root.join("out"))
            .unwrap()
            .with_code_model(&code_model)
            .execute(true);
        let custody = RfmNgspiceCustody::new(
            crate::NgspiceCustody::new(std::env::current_exe().unwrap(), "0".repeat(64)),
            "0".repeat(64),
        );
        assert!(matches!(
            run_rfm_with_ngspice_custody(&request, &custody),
            Err(RfmError::Execution(message)) if message.contains("same path")
        ));
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn zero_rfm_waveform_does_not_admit_source_or_time_as_output() {
        let root =
            std::env::temp_dir().join(format!("sipi-as06-zero-waveform-{}", std::process::id()));
        fs::create_dir_all(&root).unwrap();
        let (rows, probe, probe_max_abs) = write_ngspice_waveform_csv(
            "Index time v(src) v(out)\n0 0 1 0\n1 1 2 0\n",
            &root.join("waveform.csv"),
        )
        .unwrap();
        assert_eq!(rows, 2);
        assert_eq!(probe.to_ascii_lowercase(), "v(out)");
        assert_eq!(probe_max_abs, 0.0);
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn waveform_without_exact_vout_probe_is_rejected() {
        let root =
            std::env::temp_dir().join(format!("sipi-as06-only-p1-waveform-{}", std::process::id()));
        fs::create_dir_all(&root).unwrap();
        assert!(matches!(
            write_ngspice_waveform_csv(
                "Index time v(src) v(p1)\n0 0 1 0.2\n1 1 2 0.3\n",
                &root.join("waveform.csv"),
            ),
            Err(RfmError::Execution(message)) if message.contains("exactly one")
        ));
        assert!(matches!(
            write_ngspice_waveform_csv(
                "Index time v(out) V(OUT)\n0 0 1 0.2\n1 1 2 0.3\n",
                &root.join("duplicate.csv"),
            ),
            Err(RfmError::Execution(message)) if message.contains("exactly one")
        ));
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn native_arguments_bind_subcircuit_and_all_result_artifacts() {
        let args = native_arguments(
            Path::new("case.cir"),
            "rfm_direct",
            Path::new("model.rfm"),
            Path::new("native_result.json"),
            Path::new("waveform.csv"),
        );
        assert_eq!(
            args,
            vec![
                PathBuf::from("case.cir"),
                PathBuf::from("--rfm-subckt"),
                PathBuf::from("rfm_direct"),
                PathBuf::from("--rfm"),
                PathBuf::from("model.rfm"),
                PathBuf::from("--output-json"),
                PathBuf::from("native_result.json"),
                PathBuf::from("--waveform-csv"),
                PathBuf::from("waveform.csv"),
            ]
        );
        assert_eq!(
            parse_native_execution_summary(br#"{"ok":true,"waveformRows":2}"#).unwrap(),
            (true, 2)
        );
        assert!(
            validate_native_simulation_result(&serde_json::json!({
                "nodes": [],
                "points": [],
                "statistics": {}
            }))
            .is_ok()
        );
        assert!(
            validate_native_simulation_result(&serde_json::json!({
                "waveformRows": 2
            }))
            .is_err()
        );
        assert!(
            parse_native_execution_summary(br#"{"ok":true,"waveformRows":2,"extra":false}"#)
                .is_err()
        );
    }

    #[test]
    fn native_waveform_receipt_requires_nonzero_vout_and_matching_rows() {
        let root =
            std::env::temp_dir().join(format!("sipi-as06-native-waveform-{}", std::process::id()));
        fs::create_dir_all(&root).unwrap();
        let (rows, probe, max_abs) =
            inspect_native_waveform("time,V(OUT)\n0,0.25\n1,-0.5\n").unwrap();
        assert_eq!(rows, 2);
        assert_eq!(probe, "V(OUT)");
        assert_eq!(max_abs, 0.5);
        assert!(matches!(
            inspect_native_waveform("time,v(p1)\n0,1\n"),
            Err(RfmError::Execution(message)) if message.contains("exactly one")
        ));
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn native_artifact_receipt_is_bounded_and_non_symlink() {
        let root =
            std::env::temp_dir().join(format!("sipi-as06-native-artifact-{}", std::process::id()));
        fs::create_dir_all(&root).unwrap();
        let result = root.join("native_result.json");
        fs::write(&result, b"{\"waveformRows\":1}").unwrap();
        let (bytes, receipt) = read_bounded_external_artifact(&result, "native result").unwrap();
        assert_eq!(bytes.len(), receipt.bytes);
        assert_eq!(receipt.sha256, format!("{:x}", Sha256::digest(&bytes)));
        let oversized = root.join("oversized.json");
        let file = fs::File::create(&oversized).unwrap();
        file.set_len((MAX_ARTIFACT_BYTES + 1) as u64).unwrap();
        assert!(matches!(
            read_bounded_external_artifact(&oversized, "native result"),
            Err(RfmError::Execution(message)) if message.contains("bounded")
        ));
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    #[cfg(windows)]
    fn ngspice_process_gets_fresh_user_init_root_and_only_explicit_scripts() {
        let root =
            std::env::temp_dir().join(format!("sipi-as06-env-isolation-{}", std::process::id()));
        fs::create_dir_all(root.join("scripts")).unwrap();
        let comspec = std::env::var_os("COMSPEC").unwrap();
        let program = crate::absolute_path(Path::new(&comspec)).unwrap();
        let result = crate::run_external_process_with_spice_scripts(
            &program,
            &[PathBuf::from("/C"), PathBuf::from("set")],
            &root,
            &root.join("scripts"),
        )
        .unwrap();
        assert!(result.status.success());
        let stdout = String::from_utf8_lossy(&result.stdout).to_ascii_lowercase();
        assert!(stdout.contains(".sipi-spice-user-init"));
        assert!(!stdout.contains("dotnet_startup_hooks="));
        assert!(!stdout.contains("dotnet_additional_deps="));
        assert!(!stdout.contains("dotnet_shared_store="));
        assert!(!stdout.contains("corehost_tracefile="));
        assert!(!root.join(".sipi-spice-user-init/.spiceinit").exists());
        assert!(root.join(".sipi-spice-user-init").is_dir());
        let _ = fs::remove_dir_all(root);
    }

    #[cfg(windows)]
    #[test]
    fn native_process_gets_loader_injection_boundary() {
        let root =
            std::env::temp_dir().join(format!("sipi-as06-native-env-{}", std::process::id()));
        fs::create_dir_all(&root).unwrap();
        let comspec = std::env::var_os("COMSPEC").unwrap();
        let program = crate::absolute_path(Path::new(&comspec)).unwrap();
        let result = crate::run_native_external_process(
            &program,
            &[PathBuf::from("/C"), PathBuf::from("set")],
            &root,
        )
        .unwrap();
        assert!(result.status.success());
        let stdout = String::from_utf8_lossy(&result.stdout).to_ascii_lowercase();
        assert!(!stdout.contains("coreclr_enable_profiling="));
        assert!(!stdout.contains("coreclr_profiler="));
        assert!(!stdout.contains("coreclr_profiler_path="));
        assert!(!stdout.contains("ld_preload="));
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn explicit_ngspice_custody_rejects_oversized_code_model() {
        let root =
            std::env::temp_dir().join(format!("sipi-as06-oversized-model-{}", std::process::id()));
        fs::create_dir_all(&root).unwrap();
        let deck = root.join("deck.sp");
        let rfm = root.join("model.rfm");
        let code_model = root.join("rfm.cm");
        fs::write(&deck, ".tran 1p 1n\n.end\n").unwrap();
        fs::write(
            &rfm,
            "VERSION 200600\nNPORT 1\nMATRIX_TYPE S\nZ0 50\nBEGIN 1 1\nCONST 0\nC 0\nDELAY 0\nBEGIN_REAL 0\nBEGIN_COMPLEX 0\nEND\n",
        )
        .unwrap();
        let file = fs::File::create(&code_model).unwrap();
        file.set_len((MAX_ARTIFACT_BYTES + 1) as u64).unwrap();
        let mut request = RunRfmRequest::new(&deck, &rfm, "ngspice", root.join("out"))
            .unwrap()
            .with_code_model(&code_model)
            .execute(true);
        request.ngspice = std::env::current_exe()
            .unwrap()
            .to_string_lossy()
            .into_owned();
        let custody = RfmNgspiceCustody::new(
            crate::NgspiceCustody::new(std::env::current_exe().unwrap(), "0".repeat(64)),
            "0".repeat(64),
        );
        let result = run_rfm_with_ngspice_custody(&request, &custody);
        assert!(matches!(result, Err(RfmError::Execution(message)) if message.contains("budget")));
        let _ = fs::remove_dir_all(root);
    }

    #[cfg(unix)]
    #[test]
    fn explicit_ngspice_custody_rejects_symlink_code_model() {
        use std::os::unix::fs::symlink;
        let root =
            std::env::temp_dir().join(format!("sipi-as06-symlink-model-{}", std::process::id()));
        fs::create_dir_all(&root).unwrap();
        let target = root.join("target.cm");
        let code_model = root.join("rfm.cm");
        fs::write(&target, b"code model").unwrap();
        symlink(&target, &code_model).unwrap();
        let deck = root.join("deck.sp");
        let rfm = root.join("model.rfm");
        fs::write(&deck, ".tran 1p 1n\n.end\n").unwrap();
        fs::write(
            &rfm,
            "VERSION 200600\nNPORT 1\nMATRIX_TYPE S\nZ0 50\nBEGIN 1 1\nCONST 0\nC 0\nDELAY 0\nBEGIN_REAL 0\nBEGIN_COMPLEX 0\nEND\n",
        )
        .unwrap();
        let request = RunRfmRequest::new(&deck, &rfm, "ngspice", root.join("out"))
            .unwrap()
            .with_code_model(&code_model)
            .execute(true);
        let custody = RfmNgspiceCustody::new(
            crate::NgspiceCustody::new(std::env::current_exe().unwrap(), "0".repeat(64)),
            "0".repeat(64),
        );
        let result = run_rfm_with_ngspice_custody(&request, &custody);
        assert!(
            matches!(result, Err(RfmError::Execution(message)) if message.contains("regular non-symlink"))
        );
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn prepared_rfm_run_rejects_stale_output_directory() {
        let root =
            std::env::temp_dir().join(format!("sipi-as06-stale-output-{}", std::process::id()));
        fs::create_dir_all(root.join("out/deck/rfm_direct")).unwrap();
        let deck = root.join("deck.sp");
        let rfm = root.join("model.rfm");
        fs::write(&deck, ".tran 1p 1n\n.end\n").unwrap();
        fs::write(
            &rfm,
            "VERSION 200600\nNPORT 1\nMATRIX_TYPE S\nZ0 50\nBEGIN 1 1\nCONST 0\nC 0\nDELAY 0\nBEGIN_REAL 0\nBEGIN_COMPLEX 0\nEND\n",
        )
        .unwrap();
        let request = RunRfmRequest::new(&deck, &rfm, "ngspice", root.join("out")).unwrap();
        assert!(
            matches!(run_rfm(&request), Err(RfmError::Output(message)) if message.contains("fresh"))
        );
        let _ = fs::remove_dir_all(root);
    }

    #[cfg(unix)]
    #[test]
    fn prepared_rfm_run_rejects_reparse_output_parent() {
        use std::os::unix::fs::symlink;
        let root =
            std::env::temp_dir().join(format!("sipi-as06-reparse-output-{}", std::process::id()));
        fs::create_dir_all(root.join("real")).unwrap();
        symlink(root.join("real"), root.join("alias")).unwrap();
        let deck = root.join("deck.sp");
        let rfm = root.join("model.rfm");
        fs::write(&deck, ".tran 1p 1n\n.end\n").unwrap();
        fs::write(
            &rfm,
            "VERSION 200600\nNPORT 1\nMATRIX_TYPE S\nZ0 50\nBEGIN 1 1\nCONST 0\nC 0\nDELAY 0\nBEGIN_REAL 0\nBEGIN_COMPLEX 0\nEND\n",
        )
        .unwrap();
        let request = RunRfmRequest::new(&deck, &rfm, "ngspice", root.join("alias")).unwrap();
        assert!(matches!(
            run_rfm(&request),
            Err(RfmError::Output(message)) if message.contains("symlink/reparse")
        ));
        let _ = fs::remove_dir_all(root);
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
