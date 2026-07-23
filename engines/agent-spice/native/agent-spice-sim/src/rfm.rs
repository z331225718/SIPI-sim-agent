use std::collections::HashMap;
use std::f64::consts::PI;
use std::fs;
use std::path::Path;
use std::sync::Arc;

use faer::linalg::matmul::matmul;
use faer::linalg::solvers::DenseSolveCore;
use faer::{Accum, Mat, MatMut, MatRef, Par, c64};
use vecfit::{Model as VectorFitModel, Options as VectorFitOptions, Shape, Touchstone, complex};

use crate::error::{Error, Result};

#[derive(Debug, Clone)]
struct SourceLine {
    number: usize,
    text: String,
}

#[derive(Debug, Clone)]
struct StepKernel {
    kind: KernelKind,
    parameter: f64,
    weights: Vec<f64>,
    inverse_starts: Vec<usize>,
    inverse_columns: Vec<usize>,
    inverse_values: Vec<f64>,
    conductance: Vec<f64>,
    dynamic_response: Vec<f64>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum KernelKind {
    Trapezoidal,
    Bdf,
}

#[derive(Debug, Clone, Copy)]
enum DerivativeFormula {
    Trapezoidal { step: f64 },
    Bdf { a0: f64, a1: f64, a2: f64 },
}

#[derive(Debug, Clone, Copy)]
struct DynamicMode {
    pole: c64,
    input: usize,
    state: usize,
}

#[derive(Debug, Clone, Copy)]
struct ResponseTerm {
    mode: usize,
    residue: c64,
}

#[derive(Debug, Clone, Copy)]
pub struct RfmStorageStats {
    pub unique_poles: usize,
    pub dynamic_modes: usize,
    pub state_scalars: usize,
    pub response_terms: usize,
    pub legacy_dense_state_scalars: usize,
    pub legacy_dense_history_bytes: usize,
    pub dense_history_bytes: usize,
}

#[derive(Debug)]
struct TouchstoneSamples {
    frequencies_hz: Vec<f64>,
    scattering: Vec<c64>,
}

#[derive(Debug)]
pub struct RfmModel {
    pub nports: usize,
    pub z0: f64,
    constant: Vec<f64>,
    modes: Vec<DynamicMode>,
    response_starts: Vec<usize>,
    response_terms: Vec<ResponseTerm>,
    state_width: usize,
    unique_poles: usize,
    legacy_state_width: usize,
    dense_history_coefficients: Option<Vec<f64>>,
    touchstone: Option<TouchstoneSamples>,
    transient_supported: bool,
}

impl RfmModel {
    /// Load an S-parameter Touchstone model for direct frequency-domain use.
    /// This deliberately does not synthesize a transient state-space model.
    pub fn load_touchstone_file(path: &Path) -> Result<Self> {
        let touchstone = Touchstone::from_path(path).map_err(|error| {
            Error::Parse(format!("{}: invalid Touchstone: {error}", path.display()))
        })?;
        if !matches!(touchstone.parameter_type(), vecfit::ParameterType::S) {
            return Err(Error::Parse(format!(
                "{}: TSTONEFILE must contain S-parameters",
                path.display()
            )));
        }
        let z0 = touchstone.reference_impedance();
        if !z0.is_finite() || z0 <= 0.0 {
            return Err(Error::Parse(format!(
                "{}: Touchstone reference impedance must be positive and finite",
                path.display()
            )));
        }
        let nports = touchstone.ports();
        let response_count = nports
            .checked_mul(nports)
            .ok_or_else(|| Error::Parse("Touchstone port count is too large".into()))?;
        if touchstone.len() < 2 {
            return Err(Error::Parse(format!(
                "{}: TSTONEFILE needs at least two frequency samples",
                path.display()
            )));
        }
        let frequencies_hz = touchstone.frequency_hz().to_vec();
        if frequencies_hz.windows(2).any(|pair| pair[0] >= pair[1]) {
            return Err(Error::Parse(format!(
                "{}: TSTONEFILE frequencies must be strictly increasing",
                path.display()
            )));
        }
        let mut scattering = vec![c64::new(0.0, 0.0); touchstone.len() * response_count];
        for sample in 0..touchstone.len() {
            let source = touchstone.samples().row(sample);
            for row in 0..nports {
                for column in 0..nports {
                    scattering[sample * response_count + row * nports + column] =
                        source[column * nports + row];
                }
            }
        }
        Ok(Self {
            nports,
            z0,
            constant: Vec::new(),
            modes: Vec::new(),
            response_starts: vec![0; response_count + 1],
            response_terms: Vec::new(),
            state_width: 0,
            unique_poles: 0,
            legacy_state_width: 0,
            dense_history_coefficients: None,
            touchstone: Some(TouchstoneSamples {
                frequencies_hz,
                scattering,
            }),
            transient_supported: false,
        })
    }

    /// Load a Touchstone S-parameter file and fit it into the same real, stable
    /// rational representation used by native AC and transient simulation.
    pub fn fit_touchstone_file(path: &Path, transient_supported: bool) -> Result<Self> {
        let touchstone = Touchstone::from_path(path).map_err(|error| {
            Error::Parse(format!("{}: invalid Touchstone: {error}", path.display()))
        })?;
        if !matches!(touchstone.parameter_type(), vecfit::ParameterType::S) {
            return Err(Error::Parse(format!(
                "{}: TSTONEFILE must contain S-parameters",
                path.display()
            )));
        }
        let z0 = touchstone.reference_impedance();
        if !z0.is_finite() || z0 <= 0.0 {
            return Err(Error::Parse(format!(
                "{}: Touchstone reference impedance must be positive and finite",
                path.display()
            )));
        }
        let nports = touchstone.ports();
        let response_count = nports
            .checked_mul(nports)
            .ok_or_else(|| Error::Parse("Touchstone port count is too large".into()))?;
        if touchstone.len() < 3 {
            return Err(Error::Parse(format!(
                "{}: TSTONEFILE needs at least three frequency samples",
                path.display()
            )));
        }

        // Touchstone stores each frequency matrix by column (S11, S21, ...),
        // while the native RFM is row-major. Keep the conversion here rather
        // than relying on a parser layout default.
        let mut samples = vec![c64::new(0.0, 0.0); touchstone.len() * response_count];
        for sample in 0..touchstone.len() {
            let source = touchstone.samples().row(sample);
            for row in 0..nports {
                for column in 0..nports {
                    samples[sample * response_count + row * nports + column] =
                        source[column * nports + row];
                }
            }
        }
        let poles = touchstone_fit_pole_count(touchstone.len());
        let shape = Shape::matrix(nports, nports).map_err(|error| {
            Error::Parse(format!(
                "{}: invalid Touchstone shape: {error}",
                path.display()
            ))
        })?;
        let fit = VectorFitModel::fit_samples(
            complex(touchstone.axis()),
            &samples,
            shape,
            VectorFitOptions::new()
                .poles(poles)
                .max_iterations(24)
                .fit_constant(true)
                .fit_proportional(false),
        )
        .map_err(|error| {
            Error::Parse(format!(
                "{}: native rational fit failed: {error}",
                path.display()
            ))
        })?;
        let mut model = Self::from_vector_fit(nports, z0, &fit)?;
        model.transient_supported = transient_supported;
        if !model.constant.iter().all(|value| value.is_finite()) {
            return Err(Error::Parse(format!(
                "{}: native rational fit produced non-finite constants",
                path.display()
            )));
        }
        Ok(model)
    }

    fn from_vector_fit(nports: usize, z0: f64, fit: &VectorFitModel) -> Result<Self> {
        let response_count = nports * nports;
        if fit.channels() != response_count {
            return Err(Error::Parse(
                "native rational fit returned an invalid response shape".into(),
            ));
        }
        let constants = fit
            .constant_terms()
            .iter()
            .enumerate()
            .map(|(index, value)| real_fit_value(*value, &format!("constant term {index}")))
            .collect::<Result<Vec<_>>>()?;
        if fit
            .proportional_terms()
            .iter()
            .any(|value| value.norm() > 1e-12)
        {
            return Err(Error::Parse(
                "native rational fit produced unsupported proportional terms".into(),
            ));
        }

        let mut terms = vec![Vec::<(c64, c64)>::new(); response_count];
        let poles = fit.poles();
        let mut used = vec![false; poles.len()];
        for (index, pole) in poles.iter().copied().enumerate() {
            if used[index] {
                continue;
            }
            if !pole.re.is_finite() || !pole.im.is_finite() || pole.re >= 0.0 {
                return Err(Error::Parse(
                    "native rational fit produced an unstable pole".into(),
                ));
            }
            let pole_scale = pole.norm().max(1.0);
            if pole.im.abs() <= 1e-10 * pole_scale {
                used[index] = true;
                for (response, response_terms) in terms.iter_mut().enumerate() {
                    let residue =
                        real_fit_value(fit.residue(index, response), "real-pole residue")?;
                    response_terms.push((c64::new(pole.re, 0.0), c64::new(residue, 0.0)));
                }
                continue;
            }
            let positive = if pole.im > 0.0 {
                index
            } else {
                poles
                    .iter()
                    .enumerate()
                    .find_map(|(candidate, other)| {
                        (!used[candidate] && other.im > 0.0 && pole_pair_matches(pole, *other))
                            .then_some(candidate)
                    })
                    .ok_or_else(|| {
                        Error::Parse(
                            "native rational fit returned an incomplete complex pole pair".into(),
                        )
                    })?
            };
            let negative = poles
                .iter()
                .enumerate()
                .find_map(|(candidate, other)| {
                    (!used[candidate]
                        && other.im < 0.0
                        && pole_pair_matches(poles[positive], *other))
                    .then_some(candidate)
                })
                .ok_or_else(|| {
                    Error::Parse(
                        "native rational fit returned an incomplete complex pole pair".into(),
                    )
                })?;
            used[positive] = true;
            used[negative] = true;
            for (response, response_terms) in terms.iter_mut().enumerate() {
                let residue = (fit.residue(positive, response)
                    + fit.residue(negative, response).conj())
                    * 0.5;
                response_terms.push((poles[positive], residue));
            }
        }
        Self::from_response_terms(nports, z0, constants, terms)
    }

    pub fn parse_file(path: &Path) -> Result<Self> {
        let lines: Vec<SourceLine> = fs::read_to_string(path)?
            .lines()
            .enumerate()
            .filter_map(|(index, text)| {
                let text = text.trim();
                (!text.is_empty()
                    && !text.starts_with('*')
                    && !text.starts_with('!')
                    && !text.starts_with('#'))
                .then(|| SourceLine {
                    number: index + 1,
                    text: text.to_string(),
                })
            })
            .collect();
        if lines.is_empty() {
            return Err(Error::Parse(format!(
                "RFM file '{}' is empty",
                path.display()
            )));
        }

        let mut cursor = 0usize;
        let mut headers = HashMap::new();
        while cursor < lines.len() && !keyword(&lines[cursor], "BEGIN") {
            let tokens = tokens(&lines[cursor]);
            if tokens.len() != 2 {
                return Err(line_error(
                    path,
                    &lines[cursor],
                    "expected a two-token RFM header",
                ));
            }
            let key = tokens[0].to_ascii_uppercase();
            if headers
                .insert(key.clone(), (lines[cursor].clone(), tokens[1].to_string()))
                .is_some()
            {
                return Err(line_error(
                    path,
                    &lines[cursor],
                    &format!("duplicate RFM header '{key}'"),
                ));
            }
            cursor += 1;
        }

        for required in ["VERSION", "NPORT", "MATRIX_TYPE", "Z0"] {
            if !headers.contains_key(required) {
                return Err(Error::Parse(format!(
                    "{}: missing RFM header {required}",
                    path.display()
                )));
            }
        }
        let (version_line, version_text) = &headers["VERSION"];
        let version = integer(version_text, path, version_line, "VERSION")?;
        if version != 200600 {
            return Err(line_error(
                path,
                version_line,
                &format!("unsupported RFM VERSION {version}"),
            ));
        }
        let (nport_line, nport_text) = &headers["NPORT"];
        let nports = integer(nport_text, path, nport_line, "NPORT")?;
        if nports <= 0 {
            return Err(line_error(path, nport_line, "NPORT must be positive"));
        }
        let nports = nports as usize;
        let (matrix_line, matrix_type) = &headers["MATRIX_TYPE"];
        if !matrix_type.eq_ignore_ascii_case("S") {
            return Err(line_error(
                path,
                matrix_line,
                "only MATRIX_TYPE S is supported",
            ));
        }
        let (z0_line, z0_text) = &headers["Z0"];
        let z0 = number(z0_text, path, z0_line, "Z0")?;
        if z0 <= 0.0 {
            return Err(line_error(path, z0_line, "Z0 must be positive"));
        }

        let response_count = nports
            .checked_mul(nports)
            .ok_or_else(|| Error::Parse("RFM port count is too large".into()))?;
        let mut constants = vec![0.0; response_count];
        let mut response_terms: Vec<Option<Vec<(c64, c64)>>> = vec![None; response_count];
        while cursor < lines.len() {
            let begin = expect(&lines, &mut cursor, path, "BEGIN", 3)?;
            let begin_tokens = tokens(begin);
            let row = integer(begin_tokens[1], path, begin, "BEGIN row")?;
            let column = integer(begin_tokens[2], path, begin, "BEGIN column")?;
            if row < 1 || row > nports as i32 || column < 1 || column > nports as i32 {
                return Err(line_error(
                    path,
                    begin,
                    &format!("BEGIN indices are outside 1..{nports}"),
                ));
            }
            let response = (row as usize - 1) * nports + column as usize - 1;
            if response_terms[response].is_some() {
                return Err(line_error(
                    path,
                    begin,
                    &format!("duplicate BEGIN {row} {column} block"),
                ));
            }

            let constant = expect(&lines, &mut cursor, path, "CONST", 2)?;
            constants[response] = number(tokens(constant)[1], path, constant, "CONST")?;
            if cursor < lines.len() && keyword(&lines[cursor], "C") {
                let proportional = expect(&lines, &mut cursor, path, "C", 2)?;
                if number(tokens(proportional)[1], path, proportional, "C")? != 0.0 {
                    return Err(line_error(
                        path,
                        proportional,
                        "non-zero C is not supported",
                    ));
                }
            }
            if cursor < lines.len() && keyword(&lines[cursor], "DELAY") {
                let delay = expect(&lines, &mut cursor, path, "DELAY", 2)?;
                if number(tokens(delay)[1], path, delay, "DELAY")? != 0.0 {
                    return Err(line_error(path, delay, "non-zero DELAY is not supported"));
                }
            }

            let mut terms = Vec::new();
            let real_header = expect(&lines, &mut cursor, path, "BEGIN_REAL", 2)?;
            let real_count = integer(
                tokens(real_header)[1],
                path,
                real_header,
                "BEGIN_REAL count",
            )?;
            if real_count < 0 {
                return Err(line_error(
                    path,
                    real_header,
                    "BEGIN_REAL count must be non-negative",
                ));
            }
            for _ in 0..real_count {
                let line = lines.get(cursor).ok_or_else(|| {
                    Error::Parse(format!("{}: truncated BEGIN_REAL block", path.display()))
                })?;
                cursor += 1;
                let row_tokens = tokens(line);
                if row_tokens.len() != 2 {
                    return Err(line_error(
                        path,
                        line,
                        "real pole row requires damping and residue",
                    ));
                }
                let damping = number(row_tokens[0], path, line, "real-pole damping")?;
                if damping <= 0.0 {
                    return Err(line_error(path, line, "real-pole damping must be positive"));
                }
                let residue = number(row_tokens[1], path, line, "real residue")?;
                terms.push((c64::new(-damping, 0.0), c64::new(residue, 0.0)));
            }

            let complex_header = expect(&lines, &mut cursor, path, "BEGIN_COMPLEX", 2)?;
            let complex_count = integer(
                tokens(complex_header)[1],
                path,
                complex_header,
                "BEGIN_COMPLEX count",
            )?;
            if complex_count < 0 {
                return Err(line_error(
                    path,
                    complex_header,
                    "BEGIN_COMPLEX count must be non-negative",
                ));
            }
            for _ in 0..complex_count {
                let line = lines.get(cursor).ok_or_else(|| {
                    Error::Parse(format!("{}: truncated BEGIN_COMPLEX block", path.display()))
                })?;
                cursor += 1;
                let row_tokens = tokens(line);
                if row_tokens.len() != 4 {
                    return Err(line_error(
                        path,
                        line,
                        "complex pole row requires damping, omega, residue real, and residue imag",
                    ));
                }
                let damping = number(row_tokens[0], path, line, "complex-pole damping")?;
                let omega = number(row_tokens[1], path, line, "complex-pole omega")?;
                if damping <= 0.0 || omega == 0.0 {
                    return Err(line_error(
                        path,
                        line,
                        "complex-pole damping must be positive and omega must be non-zero",
                    ));
                }
                let mut pole = c64::new(-damping, -omega);
                let mut residue = c64::new(
                    number(row_tokens[2], path, line, "complex residue real")?,
                    number(row_tokens[3], path, line, "complex residue imag")?,
                );
                if pole.im < 0.0 {
                    pole = pole.conj();
                    residue = residue.conj();
                }
                terms.push((pole, residue));
            }
            expect(&lines, &mut cursor, path, "END", 1)?;
            response_terms[response] = Some(terms);
        }

        let missing: Vec<String> = response_terms
            .iter()
            .enumerate()
            .filter(|(_, terms)| terms.is_none())
            .map(|(index, _)| format!("{},{}", index / nports + 1, index % nports + 1))
            .collect();
        if !missing.is_empty() {
            return Err(Error::Parse(format!(
                "{}: missing response block(s): {}",
                path.display(),
                missing.join(", ")
            )));
        }
        Self::from_response_terms(
            nports,
            z0,
            constants,
            response_terms
                .into_iter()
                .map(|terms| terms.expect("all RFM responses were checked"))
                .collect(),
        )
    }

    fn from_response_terms(
        nports: usize,
        z0: f64,
        constants: Vec<f64>,
        response_terms: Vec<Vec<(c64, c64)>>,
    ) -> Result<Self> {
        let response_count = nports * nports;
        if constants.len() != response_count || response_terms.len() != response_count {
            return Err(Error::Parse("invalid RFM response dimensions".into()));
        }
        let mut unique_poles = HashMap::new();
        for terms in &response_terms {
            for (pole, _) in terms {
                unique_poles
                    .entry((pole.re.to_bits(), pole.im.to_bits()))
                    .or_insert(if pole.im == 0.0 { 1usize } else { 2usize });
            }
        }
        let legacy_state_width = unique_poles.values().sum();
        let mut modes = Vec::new();
        let mut mode_lookup = HashMap::new();
        let mut flattened_terms = Vec::new();
        let mut response_starts = Vec::with_capacity(response_count + 1);
        let mut state_width = 0usize;
        for (response, terms) in response_terms.into_iter().enumerate() {
            response_starts.push(flattened_terms.len());
            let input = response % nports;
            let response_start = flattened_terms.len();
            for (pole, residue) in terms {
                let key = (pole.re.to_bits(), pole.im.to_bits(), input);
                let mode = *mode_lookup.entry(key).or_insert_with(|| {
                    let mode = modes.len();
                    modes.push(DynamicMode {
                        pole,
                        input,
                        state: state_width,
                    });
                    state_width += if pole.im == 0.0 { 1 } else { 2 };
                    mode
                });
                if let Some(existing) = flattened_terms[response_start..]
                    .iter_mut()
                    .find(|term: &&mut ResponseTerm| term.mode == mode)
                {
                    existing.residue += residue;
                } else {
                    flattened_terms.push(ResponseTerm { mode, residue });
                }
            }
        }
        response_starts.push(flattened_terms.len());
        let dense_history_len = nports.saturating_mul(state_width);
        let coefficient_scalars: usize = flattened_terms
            .iter()
            .map(|term| {
                if modes[term.mode].pole.im == 0.0 {
                    1
                } else {
                    2
                }
            })
            .sum();
        let dense_history_coefficients = (dense_history_len <= 8 * 1024 * 1024
            && coefficient_scalars.saturating_mul(4) >= dense_history_len)
            .then(|| {
                let mut coefficients = vec![0.0; dense_history_len];
                for output in 0..nports {
                    for input in 0..nports {
                        let response = output * nports + input;
                        for term in &flattened_terms
                            [response_starts[response]..response_starts[response + 1]]
                        {
                            let mode = modes[term.mode];
                            let row = output * state_width;
                            coefficients[row + mode.state] += term.residue.re;
                            if mode.pole.im != 0.0 {
                                coefficients[row + mode.state + 1] += term.residue.im;
                            }
                        }
                    }
                }
                coefficients
            });
        Ok(Self {
            nports,
            z0,
            constant: constants,
            modes,
            response_starts,
            response_terms: flattened_terms,
            state_width,
            unique_poles: unique_poles.len(),
            legacy_state_width,
            dense_history_coefficients,
            touchstone: None,
            transient_supported: true,
        })
    }

    pub fn storage_stats(&self) -> RfmStorageStats {
        let legacy_dense_state_scalars = self.nports.saturating_mul(self.legacy_state_width);
        RfmStorageStats {
            unique_poles: self.unique_poles,
            dynamic_modes: self.modes.len(),
            state_scalars: self.state_width,
            response_terms: self.response_terms.len(),
            legacy_dense_state_scalars,
            legacy_dense_history_bytes: self
                .nports
                .saturating_mul(legacy_dense_state_scalars)
                .saturating_mul(std::mem::size_of::<f64>()),
            dense_history_bytes: self
                .dense_history_coefficients
                .as_ref()
                .map_or(0, |values| {
                    values.len().saturating_mul(std::mem::size_of::<f64>())
                }),
        }
    }

    fn terms(&self, response: usize) -> &[ResponseTerm] {
        &self.response_terms[self.response_starts[response]..self.response_starts[response + 1]]
    }

    pub fn admittance(&self, s: c64) -> Result<Vec<c64>> {
        if let Some(touchstone) = &self.touchstone {
            return self.touchstone_admittance(touchstone, s);
        }
        let mut identity_plus_scattering = vec![c64::new(0.0, 0.0); self.nports * self.nports];
        for row in 0..self.nports {
            for column in 0..self.nports {
                let response = row * self.nports + column;
                let mut value = c64::new(self.constant[response], 0.0);
                for term in self.terms(response) {
                    let pole = self.modes[term.mode].pole;
                    let residue = term.residue;
                    value += residue / (s - pole);
                    if pole.im != 0.0 {
                        value += residue.conj() / (s - pole.conj());
                    }
                }
                identity_plus_scattering[response] = value
                    + if row == column {
                        c64::new(1.0, 0.0)
                    } else {
                        c64::new(0.0, 0.0)
                    };
            }
        }
        let inverse = invert_complex(&identity_plus_scattering, self.nports)?;
        let mut admittance = vec![c64::new(0.0, 0.0); inverse.len()];
        for row in 0..self.nports {
            for column in 0..self.nports {
                let index = row * self.nports + column;
                admittance[index] = 2.0 * inverse[index] / self.z0
                    - if row == column {
                        c64::new(1.0 / self.z0, 0.0)
                    } else {
                        c64::new(0.0, 0.0)
                    };
            }
        }
        Ok(admittance)
    }

    pub fn supports_transient(&self) -> bool {
        self.transient_supported
    }

    pub fn direct_touchstone_frequency_range(&self) -> Option<(f64, f64)> {
        self.touchstone.as_ref().map(|touchstone| {
            let last = touchstone.frequencies_hz.len() - 1;
            (
                touchstone.frequencies_hz[0],
                touchstone.frequencies_hz[last],
            )
        })
    }

    fn touchstone_admittance(&self, touchstone: &TouchstoneSamples, s: c64) -> Result<Vec<c64>> {
        if s.re != 0.0 || s.im <= 0.0 {
            return Err(Error::InvalidDeck(
                "direct TSTONEFILE evaluation only supports positive-frequency AC analysis; set RATIONAL_FUNC_FOR_AC=1 for a rational model".into(),
            ));
        }
        let frequency_hz = s.im / (2.0 * PI);
        let (left, right, fraction) =
            linear_frequency_bracket(&touchstone.frequencies_hz, frequency_hz);
        let response_count = self.nports * self.nports;
        let scattering = (0..response_count)
            .map(|index| {
                touchstone.scattering[left * response_count + index] * (1.0 - fraction)
                    + touchstone.scattering[right * response_count + index] * fraction
            })
            .collect::<Vec<_>>();
        scattering_to_admittance(&scattering, self.nports, self.z0)
    }

    pub fn dc_admittance_real(&self) -> Result<Vec<f64>> {
        self.admittance(c64::new(0.0, 0.0))?
            .into_iter()
            .map(|value| {
                if value.im.abs() > 1e-12 * (1.0 + value.re.abs()) {
                    Err(Error::InvalidDeck(
                        "RFM DC admittance unexpectedly became complex".into(),
                    ))
                } else {
                    Ok(value.re)
                }
            })
            .collect()
    }

    pub fn create_state(&self) -> RfmState {
        let value_count = self.state_width;
        RfmState {
            values: vec![0.0; value_count],
            previous_values: vec![0.0; value_count],
            older_values: vec![0.0; value_count],
            incident: vec![0.0; self.nports],
            x_base: vec![0.0; value_count],
            history: vec![0.0; self.nports],
            offset: vec![0.0; self.nports],
            dynamic_output: vec![0.0; self.nports],
            previous_dynamic_output: vec![0.0; self.nports],
            older_dynamic_output: vec![0.0; self.nports],
            dynamic_output_derivative: vec![0.0; self.nports],
            normalized_port_voltages: vec![0.0; self.nports],
            derivative_formula: None,
            kernel: None,
        }
    }

    pub fn initialize_dc(&self, state: &mut RfmState, port_voltages: &[f64]) -> Result<()> {
        let weights = self.dc_weights();
        let inverse = invert_real(&self.build_wave_matrix(&weights), self.nports)?;
        for input in 0..self.nports {
            let incident = (0..self.nports)
                .map(|column| {
                    inverse[input * self.nports + column] * port_voltages[column] / self.z0.sqrt()
                })
                .sum();
            state.incident[input] = incident;
        }
        for mode in &self.modes {
            state.values[mode.state] = weights[mode.state] * state.incident[mode.input];
            if mode.pole.im != 0.0 {
                state.values[mode.state + 1] = weights[mode.state + 1] * state.incident[mode.input];
            }
        }
        state.previous_values.copy_from_slice(&state.values);
        state.older_values.copy_from_slice(&state.values);
        self.fill_dynamic_output_voltage(&state.values, &mut state.dynamic_output);
        state
            .previous_dynamic_output
            .copy_from_slice(&state.dynamic_output);
        state
            .older_dynamic_output
            .copy_from_slice(&state.dynamic_output);
        Ok(())
    }

    pub fn prepare_trapezoidal(&self, state: &mut RfmState, step: f64) -> Result<()> {
        if step <= 0.0 {
            return Err(Error::InvalidDeck(
                "RFM transient step must be positive".into(),
            ));
        }
        if state
            .kernel
            .as_ref()
            .is_none_or(|kernel| kernel.kind != KernelKind::Trapezoidal || kernel.parameter != step)
        {
            state.kernel = Some(Arc::new(self.build_trapezoidal_kernel(step)?));
        }
        state.derivative_formula = Some(DerivativeFormula::Trapezoidal { step });

        let half = 0.5 * step;
        for mode in &self.modes {
            let pole = mode.pole;
            let base = mode.state;
            let old_incident = state.incident[mode.input];
            if pole.im == 0.0 {
                let denominator = 1.0 - half * pole.re;
                state.x_base[base] = ((1.0 + half * pole.re) * state.values[base]
                    + half * old_incident)
                    / denominator;
                continue;
            }
            let d = 1.0 - half * pole.re;
            let e = half * pole.im;
            let denominator = d * d + e * e;
            let old_real = state.values[base];
            let old_imaginary = state.values[base + 1];
            let q_real =
                (1.0 + half * pole.re) * old_real + e * old_imaginary + step * old_incident;
            let q_imaginary = -e * old_real + (1.0 + half * pole.re) * old_imaginary;
            state.x_base[base] = (d * q_real + e * q_imaginary) / denominator;
            state.x_base[base + 1] = (-e * q_real + d * q_imaginary) / denominator;
        }
        self.finish_companion(state);
        Ok(())
    }

    pub fn prepare_bdf(&self, state: &mut RfmState, a0: f64, a1: f64, a2: f64) -> Result<()> {
        if a0 <= 0.0 {
            return Err(Error::InvalidDeck(
                "RFM BDF leading coefficient must be positive".into(),
            ));
        }
        if state
            .kernel
            .as_ref()
            .is_none_or(|kernel| kernel.kind != KernelKind::Bdf || kernel.parameter != a0)
        {
            state.kernel = Some(Arc::new(self.build_bdf_kernel(a0)?));
        }
        state.derivative_formula = Some(DerivativeFormula::Bdf { a0, a1, a2 });
        for mode in &self.modes {
            let pole = mode.pole;
            let base = mode.state;
            let q_real = -a1 * state.values[base] - a2 * state.previous_values[base];
            if pole.im == 0.0 {
                state.x_base[base] = q_real / (a0 - pole.re);
                continue;
            }
            let q_imaginary = -a1 * state.values[base + 1] - a2 * state.previous_values[base + 1];
            let d = a0 - pole.re;
            let e = pole.im;
            let denominator = d * d + e * e;
            state.x_base[base] = (d * q_real + e * q_imaginary) / denominator;
            state.x_base[base + 1] = (-e * q_real + d * q_imaginary) / denominator;
        }
        self.finish_companion(state);
        Ok(())
    }

    fn finish_companion(&self, state: &mut RfmState) {
        self.fill_history(&state.x_base, &mut state.history);
        let kernel = state.kernel.as_ref().expect("RFM step kernel was built");
        for row in 0..self.nports {
            let transformed: f64 = (kernel.inverse_starts[row]..kernel.inverse_starts[row + 1])
                .map(|term| {
                    kernel.inverse_values[term] * state.history[kernel.inverse_columns[term]]
                })
                .sum();
            state.offset[row] = -2.0 * transformed / self.z0.sqrt();
        }
    }

    pub fn commit_candidate(
        &self,
        current: &mut RfmState,
        previous: &RfmState,
        port_voltages: &[f64],
    ) {
        current.kernel.clone_from(&previous.kernel);
        current.derivative_formula = previous.derivative_formula;
        current.x_base.copy_from_slice(&previous.x_base);
        current.history.copy_from_slice(&previous.history);
        current
            .older_values
            .copy_from_slice(&previous.previous_values);
        current.previous_values.copy_from_slice(&previous.values);
        current
            .older_dynamic_output
            .copy_from_slice(&previous.previous_dynamic_output);
        current
            .previous_dynamic_output
            .copy_from_slice(&previous.dynamic_output);
        let scale = self.z0.sqrt();
        for (normalized, voltage) in current
            .normalized_port_voltages
            .iter_mut()
            .zip(port_voltages)
        {
            *normalized = voltage / scale;
        }
        let kernel = current.kernel.as_ref().expect("RFM companion was prepared");
        for input in 0..self.nports {
            let incident: f64 = (kernel.inverse_starts[input]..kernel.inverse_starts[input + 1])
                .map(|term| {
                    let output = kernel.inverse_columns[term];
                    kernel.inverse_values[term]
                        * (current.normalized_port_voltages[output] - current.history[output])
                })
                .sum();
            current.incident[input] = incident;
        }
        for mode in &self.modes {
            current.values[mode.state] = current.x_base[mode.state]
                + kernel.weights[mode.state] * current.incident[mode.input];
            if mode.pole.im != 0.0 {
                current.values[mode.state + 1] = current.x_base[mode.state + 1]
                    + kernel.weights[mode.state + 1] * current.incident[mode.input];
            }
        }
        for row in 0..self.nports {
            let response = &kernel.dynamic_response[row * self.nports..(row + 1) * self.nports];
            current.dynamic_output[row] = scale
                * (current.history[row]
                    + response
                        .iter()
                        .zip(&current.incident)
                        .map(|(coefficient, incident)| coefficient * incident)
                        .sum::<f64>());
        }
        match current
            .derivative_formula
            .expect("RFM derivative formula was prepared")
        {
            DerivativeFormula::Trapezoidal { step } => {
                for port in 0..self.nports {
                    current.dynamic_output_derivative[port] =
                        2.0 * (current.dynamic_output[port] - previous.dynamic_output[port]) / step
                            - previous.dynamic_output_derivative[port];
                }
            }
            DerivativeFormula::Bdf { a0, a1, a2 } => {
                for port in 0..self.nports {
                    current.dynamic_output_derivative[port] = a0 * current.dynamic_output[port]
                        + a1 * previous.dynamic_output[port]
                        + a2 * previous.previous_dynamic_output[port];
                }
            }
        }
    }

    #[allow(clippy::too_many_arguments)]
    pub fn truncation_error_ratio(
        &self,
        current: &RfmState,
        previous: &RfmState,
        h0: f64,
        h1: f64,
        h2: f64,
        order: usize,
        second_order_factor: f64,
        voltage_tolerance: f64,
        relative_tolerance: f64,
        truncation_tolerance: f64,
        truncation_scale: f64,
    ) -> f64 {
        let mut maximum: f64 = 0.0;
        for port in 0..self.nports {
            maximum = maximum.max(charge_truncation_ratio(
                current.dynamic_output[port],
                previous.dynamic_output[port],
                previous.previous_dynamic_output[port],
                previous.older_dynamic_output[port],
                current.dynamic_output_derivative[port],
                previous.dynamic_output_derivative[port],
                h0,
                h1,
                h2,
                order,
                second_order_factor,
                voltage_tolerance / h0,
                relative_tolerance,
                voltage_tolerance,
                truncation_tolerance * truncation_scale,
            ));
        }
        maximum
    }

    fn build_trapezoidal_kernel(&self, step: f64) -> Result<StepKernel> {
        let half = 0.5 * step;
        let mut weights = vec![0.0; self.state_width];
        for mode in &self.modes {
            let pole = mode.pole;
            let state = mode.state;
            if pole.im == 0.0 {
                weights[state] = half / (1.0 - half * pole.re);
                continue;
            }
            let d = 1.0 - half * pole.re;
            let e = half * pole.im;
            let denominator = d * d + e * e;
            weights[state] = step * d / denominator;
            weights[state + 1] = -step * e / denominator;
        }
        let wave_matrix = self.build_wave_matrix(&weights);
        let inverse = invert_real(&wave_matrix, self.nports)?;
        let (inverse_starts, inverse_columns, inverse_values) =
            compress_real_rows(&inverse, self.nports);
        let mut conductance = vec![0.0; self.nports * self.nports];
        let mut dynamic_response = wave_matrix;
        for row in 0..self.nports {
            for column in 0..self.nports {
                let index = row * self.nports + column;
                dynamic_response[index] -=
                    self.constant[index] + if row == column { 1.0 } else { 0.0 };
                conductance[index] = 2.0 * inverse[index] / self.z0
                    - if row == column { 1.0 / self.z0 } else { 0.0 };
            }
        }
        Ok(StepKernel {
            kind: KernelKind::Trapezoidal,
            parameter: step,
            weights,
            inverse_starts,
            inverse_columns,
            inverse_values,
            conductance,
            dynamic_response,
        })
    }

    fn build_bdf_kernel(&self, a0: f64) -> Result<StepKernel> {
        let mut weights = vec![0.0; self.state_width];
        for mode in &self.modes {
            let pole = mode.pole;
            let state = mode.state;
            let d = a0 - pole.re;
            if pole.im == 0.0 {
                weights[state] = 1.0 / d;
                continue;
            }
            let e = pole.im;
            let denominator = d * d + e * e;
            weights[state] = 2.0 * d / denominator;
            weights[state + 1] = -2.0 * e / denominator;
        }
        let wave_matrix = self.build_wave_matrix(&weights);
        let inverse = invert_real(&wave_matrix, self.nports)?;
        let (inverse_starts, inverse_columns, inverse_values) =
            compress_real_rows(&inverse, self.nports);
        let mut conductance = vec![0.0; self.nports * self.nports];
        let mut dynamic_response = wave_matrix;
        for row in 0..self.nports {
            for column in 0..self.nports {
                let index = row * self.nports + column;
                dynamic_response[index] -=
                    self.constant[index] + if row == column { 1.0 } else { 0.0 };
                conductance[index] = 2.0 * inverse[index] / self.z0
                    - if row == column { 1.0 / self.z0 } else { 0.0 };
            }
        }
        Ok(StepKernel {
            kind: KernelKind::Bdf,
            parameter: a0,
            weights,
            inverse_starts,
            inverse_columns,
            inverse_values,
            conductance,
            dynamic_response,
        })
    }

    fn dc_weights(&self) -> Vec<f64> {
        let mut weights = vec![0.0; self.state_width];
        for mode in &self.modes {
            let pole = mode.pole;
            let state = mode.state;
            if pole.im == 0.0 {
                weights[state] = -1.0 / pole.re;
                continue;
            }
            let denominator = pole.re * pole.re + pole.im * pole.im;
            weights[state] = -2.0 * pole.re / denominator;
            weights[state + 1] = -2.0 * pole.im / denominator;
        }
        weights
    }

    fn build_wave_matrix(&self, weights: &[f64]) -> Vec<f64> {
        let mut matrix = vec![0.0; self.nports * self.nports];
        for row in 0..self.nports {
            for column in 0..self.nports {
                let response = row * self.nports + column;
                let mut value = self.constant[response] + if row == column { 1.0 } else { 0.0 };
                for term in self.terms(response) {
                    let mode = self.modes[term.mode];
                    value += term.residue.re * weights[mode.state];
                    if mode.pole.im != 0.0 {
                        value += term.residue.im * weights[mode.state + 1];
                    }
                }
                matrix[response] = value;
            }
        }
        matrix
    }

    fn fill_history(&self, values: &[f64], history: &mut [f64]) {
        debug_assert_eq!(values.len(), self.state_width);
        debug_assert_eq!(history.len(), self.nports);
        if let Some(coefficients) = &self.dense_history_coefficients {
            let coefficients =
                MatRef::from_row_major_slice(coefficients, self.nports, values.len());
            let values = MatRef::from_column_major_slice(values, values.len(), 1);
            let history = MatMut::from_column_major_slice_mut(history, self.nports, 1);
            matmul(history, Accum::Replace, coefficients, values, 1.0, Par::Seq);
            return;
        }
        history.fill(0.0);
        for (output, value) in history.iter_mut().enumerate() {
            for input in 0..self.nports {
                let response = output * self.nports + input;
                for term in self.terms(response) {
                    let mode = self.modes[term.mode];
                    *value += term.residue.re * values[mode.state];
                    if mode.pole.im != 0.0 {
                        *value += term.residue.im * values[mode.state + 1];
                    }
                }
            }
        }
    }

    fn fill_dynamic_output_voltage(&self, values: &[f64], output: &mut [f64]) {
        self.fill_history(values, output);
        let scale = self.z0.sqrt();
        for value in output {
            *value *= scale;
        }
    }
}

fn linear_frequency_bracket(frequencies_hz: &[f64], frequency_hz: f64) -> (usize, usize, f64) {
    debug_assert!(frequencies_hz.len() >= 2);
    let upper = frequencies_hz.partition_point(|frequency| *frequency < frequency_hz);
    let (left, right) = if upper == 0 {
        (0, 1)
    } else if upper == frequencies_hz.len() {
        (frequencies_hz.len() - 2, frequencies_hz.len() - 1)
    } else {
        (upper - 1, upper)
    };
    let fraction =
        (frequency_hz - frequencies_hz[left]) / (frequencies_hz[right] - frequencies_hz[left]);
    (left, right, fraction)
}

#[cfg(test)]
mod tests {
    use super::linear_frequency_bracket;

    #[test]
    fn linear_frequency_bracket_extrapolates_below_and_above_touchstone_range() {
        let frequencies = [1.0, 10.0, 100.0];
        assert_eq!(linear_frequency_bracket(&frequencies, 0.1), (0, 1, -0.1));
        assert_eq!(
            linear_frequency_bracket(&frequencies, 1_000.0),
            (1, 2, 11.0)
        );
    }
}

fn touchstone_fit_pole_count(samples: usize) -> usize {
    // Keep the initial state-space bounded for large N-port transient decks.
    // A later auto-order pass can raise this after fit-quality gates exist.
    samples.saturating_sub(1).clamp(1, 24)
}

fn real_fit_value(value: c64, label: &str) -> Result<f64> {
    if !value.re.is_finite() || !value.im.is_finite() {
        return Err(Error::Parse(format!(
            "native rational fit produced non-finite {label}"
        )));
    }
    if value.im.abs() > 1e-7 * (1.0 + value.re.abs()) {
        return Err(Error::Parse(format!(
            "native rational fit produced non-real {label}; cannot build a real transient model"
        )));
    }
    Ok(value.re)
}

fn pole_pair_matches(left: c64, right: c64) -> bool {
    let scale = left.norm().max(right.norm()).max(1.0);
    (left.re - right.re).abs() <= 1e-7 * scale && (left.im + right.im).abs() <= 1e-7 * scale
}

fn scattering_to_admittance(scattering: &[c64], nports: usize, z0: f64) -> Result<Vec<c64>> {
    let mut identity_plus_scattering = scattering.to_vec();
    for index in 0..nports {
        identity_plus_scattering[index * nports + index] += c64::new(1.0, 0.0);
    }
    let inverse = invert_complex(&identity_plus_scattering, nports)?;
    let mut admittance = vec![c64::new(0.0, 0.0); inverse.len()];
    for row in 0..nports {
        for column in 0..nports {
            let index = row * nports + column;
            admittance[index] = 2.0 * inverse[index] / z0
                - if row == column {
                    c64::new(1.0 / z0, 0.0)
                } else {
                    c64::new(0.0, 0.0)
                };
        }
    }
    Ok(admittance)
}

#[derive(Debug, Clone)]
pub struct RfmState {
    values: Vec<f64>,
    previous_values: Vec<f64>,
    older_values: Vec<f64>,
    incident: Vec<f64>,
    x_base: Vec<f64>,
    history: Vec<f64>,
    offset: Vec<f64>,
    dynamic_output: Vec<f64>,
    previous_dynamic_output: Vec<f64>,
    older_dynamic_output: Vec<f64>,
    dynamic_output_derivative: Vec<f64>,
    normalized_port_voltages: Vec<f64>,
    derivative_formula: Option<DerivativeFormula>,
    kernel: Option<Arc<StepKernel>>,
}

impl RfmState {
    pub fn conductance(&self) -> &[f64] {
        &self
            .kernel
            .as_ref()
            .expect("RFM companion was prepared")
            .conductance
    }

    pub fn offset(&self) -> &[f64] {
        &self.offset
    }
}

#[allow(clippy::too_many_arguments)]
fn charge_truncation_ratio(
    q0: f64,
    q1: f64,
    q2: f64,
    q3: f64,
    derivative0: f64,
    derivative1: f64,
    h0: f64,
    h1: f64,
    h2: f64,
    order: usize,
    second_order_factor: f64,
    derivative_absolute_tolerance: f64,
    relative_tolerance: f64,
    state_absolute_tolerance: f64,
    truncation_tolerance: f64,
) -> f64 {
    let derivative_tolerance = derivative_absolute_tolerance
        + relative_tolerance * derivative0.abs().max(derivative1.abs());
    let scaled_state_tolerance =
        relative_tolerance * q0.abs().max(q1.abs()).max(state_absolute_tolerance) / h0;
    let tolerance = derivative_tolerance.max(scaled_state_tolerance);
    let scaled_error = if order == 1 {
        let difference0 = (q0 - q1) / h0;
        let difference1 = (q1 - q2) / h1;
        0.5 * ((difference0 - difference1) / (h0 + h1)).abs() * h0
    } else {
        let difference0 = (q0 - q1) / h0;
        let difference1 = (q1 - q2) / h1;
        let difference2 = (q2 - q3) / h2;
        let second0 = (difference0 - difference1) / (h0 + h1);
        let second1 = (difference1 - difference2) / (h1 + h2);
        second_order_factor * ((second0 - second1) / (h0 + h1 + h2)).abs() * h0 * h0
    };
    let ratio = scaled_error / (truncation_tolerance * tolerance);
    if ratio.is_finite() {
        ratio
    } else {
        f64::INFINITY
    }
}

fn compress_real_rows(values: &[f64], size: usize) -> (Vec<usize>, Vec<usize>, Vec<f64>) {
    let mut starts = Vec::with_capacity(size + 1);
    let mut columns = Vec::new();
    let mut nonzero_values = Vec::new();
    for row in 0..size {
        starts.push(columns.len());
        for column in 0..size {
            let value = values[row * size + column];
            if value != 0.0 {
                columns.push(column);
                nonzero_values.push(value);
            }
        }
    }
    starts.push(columns.len());
    (starts, columns, nonzero_values)
}

fn invert_real(values: &[f64], size: usize) -> Result<Vec<f64>> {
    let complex: Vec<c64> = values.iter().map(|value| c64::new(*value, 0.0)).collect();
    invert_complex(&complex, size)?
        .into_iter()
        .map(|value| {
            if value.im.abs() > 1e-12 * (1.0 + value.re.abs()) {
                Err(Error::InvalidDeck(
                    "RFM real companion inverse became complex".into(),
                ))
            } else {
                Ok(value.re)
            }
        })
        .collect()
}

fn invert_complex(values: &[c64], size: usize) -> Result<Vec<c64>> {
    let matrix = Mat::from_fn(size, size, |row, column| values[row * size + column]);
    let inverse = matrix.partial_piv_lu().inverse();
    let mut values = Vec::with_capacity(size * size);
    for row in 0..size {
        for column in 0..size {
            values.push(inverse[(row, column)]);
        }
    }
    if values
        .iter()
        .any(|value| !value.re.is_finite() || !value.im.is_finite())
    {
        return Err(Error::InvalidDeck(
            "RFM wave matrix is singular or non-finite".into(),
        ));
    }
    Ok(values)
}

fn expect<'a>(
    lines: &'a [SourceLine],
    cursor: &mut usize,
    path: &Path,
    expected: &str,
    count: usize,
) -> Result<&'a SourceLine> {
    let line = lines.get(*cursor).ok_or_else(|| {
        Error::Parse(format!(
            "{}: expected {expected}, reached end of file",
            path.display()
        ))
    })?;
    *cursor += 1;
    let values = tokens(line);
    if values.len() != count || !values[0].eq_ignore_ascii_case(expected) {
        return Err(line_error(
            path,
            line,
            &format!("expected '{expected}' with {} value(s)", count - 1),
        ));
    }
    Ok(line)
}

fn keyword(line: &SourceLine, expected: &str) -> bool {
    tokens(line)
        .first()
        .is_some_and(|value| value.eq_ignore_ascii_case(expected))
}

fn tokens(line: &SourceLine) -> Vec<&str> {
    line.text.split_whitespace().collect()
}

fn integer(token: &str, path: &Path, line: &SourceLine, label: &str) -> Result<i32> {
    token
        .parse()
        .map_err(|_| line_error(path, line, &format!("invalid {label} '{token}'")))
}

fn number(token: &str, path: &Path, line: &SourceLine, label: &str) -> Result<f64> {
    let normalized = token.replace(['D', 'd'], "E");
    let value = normalized
        .parse::<f64>()
        .map_err(|_| line_error(path, line, &format!("invalid {label} '{token}'")))?;
    if !value.is_finite() {
        return Err(line_error(
            path,
            line,
            &format!("invalid {label} '{token}'"),
        ));
    }
    Ok(value)
}

fn line_error(path: &Path, line: &SourceLine, message: &str) -> Error {
    Error::Parse(format!("{}:{}: {message}", path.display(), line.number))
}
