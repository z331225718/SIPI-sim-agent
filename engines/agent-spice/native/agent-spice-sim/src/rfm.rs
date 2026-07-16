use std::collections::HashMap;
use std::fs;
use std::path::Path;
use std::sync::Arc;

use faer::linalg::solvers::DenseSolveCore;
use faer::{Mat, c64};

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
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum KernelKind {
    Trapezoidal,
    Bdf,
}

#[derive(Debug)]
pub struct RfmModel {
    pub nports: usize,
    pub z0: f64,
    poles: Vec<c64>,
    residues: Vec<c64>,
    constant: Vec<f64>,
    state_offsets: Vec<usize>,
    state_width: usize,
    history_starts: Vec<usize>,
    history_state_indices: Vec<usize>,
    history_residue_real: Vec<f64>,
    history_residue_imaginary: Vec<f64>,
    history_has_imaginary_state: Vec<bool>,
}

impl RfmModel {
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
        let mut poles = Vec::new();
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
            for (pole, _) in &terms {
                if !poles.contains(pole) {
                    poles.push(*pole);
                }
            }
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
        let mut residues = vec![c64::new(0.0, 0.0); response_count * poles.len()];
        for (response, terms) in response_terms.into_iter().enumerate() {
            for (pole, residue) in terms.expect("all RFM responses were checked") {
                let pole_index = poles
                    .iter()
                    .position(|candidate| *candidate == pole)
                    .expect("RFM pole was collected");
                residues[response * poles.len() + pole_index] += residue;
            }
        }

        let mut state_offsets = Vec::with_capacity(poles.len());
        let mut state_width = 0usize;
        for pole in &poles {
            state_offsets.push(state_width);
            state_width += if pole.im == 0.0 { 1 } else { 2 };
        }
        let mut history_starts = Vec::with_capacity(nports + 1);
        let mut history_state_indices = Vec::new();
        let mut history_residue_real = Vec::new();
        let mut history_residue_imaginary = Vec::new();
        let mut history_has_imaginary_state = Vec::new();
        for output in 0..nports {
            history_starts.push(history_state_indices.len());
            for input in 0..nports {
                let response = output * nports + input;
                for pole_index in 0..poles.len() {
                    let residue = residues[response * poles.len() + pole_index];
                    if residue == c64::new(0.0, 0.0) {
                        continue;
                    }
                    history_state_indices.push(input * state_width + state_offsets[pole_index]);
                    history_residue_real.push(residue.re);
                    history_residue_imaginary.push(residue.im);
                    history_has_imaginary_state.push(poles[pole_index].im != 0.0);
                }
            }
        }
        history_starts.push(history_state_indices.len());
        Ok(Self {
            nports,
            z0,
            poles,
            residues,
            constant: constants,
            state_offsets,
            state_width,
            history_starts,
            history_state_indices,
            history_residue_real,
            history_residue_imaginary,
            history_has_imaginary_state,
        })
    }

    pub fn admittance(&self, s: c64) -> Result<Vec<c64>> {
        let mut identity_plus_scattering = vec![c64::new(0.0, 0.0); self.nports * self.nports];
        for row in 0..self.nports {
            for column in 0..self.nports {
                let response = row * self.nports + column;
                let mut value = c64::new(self.constant[response], 0.0);
                for pole_index in 0..self.poles.len() {
                    let pole = self.poles[pole_index];
                    let residue = self.residues[response * self.poles.len() + pole_index];
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
        let value_count = self.nports * self.state_width;
        RfmState {
            values: vec![0.0; value_count],
            previous_values: vec![0.0; value_count],
            older_values: vec![0.0; value_count],
            incident: vec![0.0; self.nports],
            x_base: vec![0.0; value_count],
            history: vec![0.0; self.nports],
            offset: vec![0.0; self.nports],
            truncation_scratch: vec![0.0; 6 * self.nports + value_count],
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
            for (state_index, weight) in weights.iter().enumerate() {
                state.values[input * self.state_width + state_index] = weight * incident;
            }
        }
        state.previous_values.copy_from_slice(&state.values);
        state.older_values.copy_from_slice(&state.values);
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

        let half = 0.5 * step;
        for input in 0..self.nports {
            let old_incident = state.incident[input];
            for pole_index in 0..self.poles.len() {
                let pole = self.poles[pole_index];
                let base = input * self.state_width + self.state_offsets[pole_index];
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
        for input in 0..self.nports {
            for pole_index in 0..self.poles.len() {
                let pole = self.poles[pole_index];
                let base = input * self.state_width + self.state_offsets[pole_index];
                let q_real = -a1 * state.values[base] - a2 * state.previous_values[base];
                if pole.im == 0.0 {
                    state.x_base[base] = q_real / (a0 - pole.re);
                    continue;
                }
                let q_imaginary =
                    -a1 * state.values[base + 1] - a2 * state.previous_values[base + 1];
                let d = a0 - pole.re;
                let e = pole.im;
                let denominator = d * d + e * e;
                state.x_base[base] = (d * q_real + e * q_imaginary) / denominator;
                state.x_base[base + 1] = (-e * q_real + d * q_imaginary) / denominator;
            }
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

    pub fn commit(&self, state: &mut RfmState, port_voltages: &[f64]) {
        state.older_values.copy_from_slice(&state.previous_values);
        state.previous_values.copy_from_slice(&state.values);
        let kernel = state.kernel.as_ref().expect("RFM companion was prepared");
        for input in 0..self.nports {
            let incident: f64 = (kernel.inverse_starts[input]..kernel.inverse_starts[input + 1])
                .map(|term| {
                    let output = kernel.inverse_columns[term];
                    kernel.inverse_values[term]
                        * (port_voltages[output] / self.z0.sqrt() - state.history[output])
                })
                .sum();
            state.incident[input] = incident;
            for state_index in 0..self.state_width {
                let index = input * self.state_width + state_index;
                state.values[index] = state.x_base[index] + kernel.weights[state_index] * incident;
            }
        }
    }

    #[allow(clippy::too_many_arguments)]
    pub fn truncation_error_ratio(
        &self,
        current: &mut RfmState,
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
        let mut scratch = std::mem::take(&mut current.truncation_scratch);
        scratch.resize(6 * self.nports + current.values.len(), 0.0);
        let (q0, rest) = scratch.split_at_mut(self.nports);
        let (q1, rest) = rest.split_at_mut(self.nports);
        let (q2, rest) = rest.split_at_mut(self.nports);
        let (q3, rest) = rest.split_at_mut(self.nports);
        let (derivative0, rest) = rest.split_at_mut(self.nports);
        let (derivative1, derivative_state) = rest.split_at_mut(self.nports);
        self.fill_dynamic_output_voltage(&current.values, q0);
        self.fill_dynamic_output_voltage(&previous.values, q1);
        self.fill_dynamic_output_voltage(&previous.previous_values, q2);
        self.fill_dynamic_output_voltage(&previous.older_values, q3);
        self.fill_dynamic_output_voltage_derivative(
            &current.values,
            &current.incident,
            derivative0,
            derivative_state,
        );
        self.fill_dynamic_output_voltage_derivative(
            &previous.values,
            &previous.incident,
            derivative1,
            derivative_state,
        );
        let mut maximum: f64 = 0.0;
        for port in 0..self.nports {
            maximum = maximum.max(charge_truncation_ratio(
                q0[port],
                q1[port],
                q2[port],
                q3[port],
                derivative0[port],
                derivative1[port],
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
        current.truncation_scratch = scratch;
        maximum
    }

    fn build_trapezoidal_kernel(&self, step: f64) -> Result<StepKernel> {
        let half = 0.5 * step;
        let mut weights = vec![0.0; self.state_width];
        for pole_index in 0..self.poles.len() {
            let pole = self.poles[pole_index];
            let state = self.state_offsets[pole_index];
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
        let inverse = invert_real(&self.build_wave_matrix(&weights), self.nports)?;
        let (inverse_starts, inverse_columns, inverse_values) =
            compress_real_rows(&inverse, self.nports);
        let mut conductance = vec![0.0; self.nports * self.nports];
        for row in 0..self.nports {
            for column in 0..self.nports {
                let index = row * self.nports + column;
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
        })
    }

    fn build_bdf_kernel(&self, a0: f64) -> Result<StepKernel> {
        let mut weights = vec![0.0; self.state_width];
        for pole_index in 0..self.poles.len() {
            let pole = self.poles[pole_index];
            let state = self.state_offsets[pole_index];
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
        let inverse = invert_real(&self.build_wave_matrix(&weights), self.nports)?;
        let (inverse_starts, inverse_columns, inverse_values) =
            compress_real_rows(&inverse, self.nports);
        let mut conductance = vec![0.0; self.nports * self.nports];
        for row in 0..self.nports {
            for column in 0..self.nports {
                let index = row * self.nports + column;
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
        })
    }

    fn dc_weights(&self) -> Vec<f64> {
        let mut weights = vec![0.0; self.state_width];
        for pole_index in 0..self.poles.len() {
            let pole = self.poles[pole_index];
            let state = self.state_offsets[pole_index];
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
                for pole_index in 0..self.poles.len() {
                    let residue = self.residues[response * self.poles.len() + pole_index];
                    let state = self.state_offsets[pole_index];
                    value += residue.re * weights[state];
                    if self.poles[pole_index].im != 0.0 {
                        value += residue.im * weights[state + 1];
                    }
                }
                matrix[response] = value;
            }
        }
        matrix
    }

    fn fill_history(&self, values: &[f64], history: &mut [f64]) {
        for (output, history_value) in history.iter_mut().enumerate() {
            let mut value = 0.0;
            for term in self.history_starts[output]..self.history_starts[output + 1] {
                let state = self.history_state_indices[term];
                value += self.history_residue_real[term] * values[state];
                if self.history_has_imaginary_state[term] {
                    value += self.history_residue_imaginary[term] * values[state + 1];
                }
            }
            *history_value = value;
        }
    }

    fn fill_dynamic_output_voltage(&self, values: &[f64], output: &mut [f64]) {
        self.fill_history(values, output);
        let scale = self.z0.sqrt();
        for value in output {
            *value *= scale;
        }
    }

    fn fill_dynamic_output_voltage_derivative(
        &self,
        values: &[f64],
        incident: &[f64],
        output: &mut [f64],
        derivative_state: &mut [f64],
    ) {
        for (input, incident_value) in incident.iter().copied().enumerate().take(self.nports) {
            let input_offset = input * self.state_width;
            for pole_index in 0..self.poles.len() {
                let pole = self.poles[pole_index];
                let state = input_offset + self.state_offsets[pole_index];
                if pole.im == 0.0 {
                    derivative_state[state] = pole.re * values[state] + incident_value;
                    continue;
                }
                let real = values[state];
                let imaginary = values[state + 1];
                derivative_state[state] =
                    pole.re * real + pole.im * imaginary + 2.0 * incident_value;
                derivative_state[state + 1] = -pole.im * real + pole.re * imaginary;
            }
        }
        self.fill_dynamic_output_voltage(derivative_state, output);
    }
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
    truncation_scratch: Vec<f64>,
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
