use std::collections::{BTreeSet, HashMap};
use std::path::PathBuf;

use faer::c64;

use crate::error::{Error, Result};
use crate::rfm::RfmModel;

#[derive(Clone)]
pub struct RcBranch {
    pub positive: String,
    pub negative: String,
    pub value: f64,
    pub is_capacitor: bool,
}

/// A two-terminal linear RC CPM.  It deliberately supports only passive R/C
/// elements; nonlinear/current-source parts of a CPM belong in the waveform,
/// not its small-signal load.
#[derive(Clone)]
pub struct RcShunt {
    pub port: usize,
    pub positive_terminal: String,
    pub negative_terminal: String,
    pub branches: Vec<RcBranch>,
    pub source: PathBuf,
}

impl RcShunt {
    pub fn parse(port: usize, source: PathBuf) -> Result<Self> {
        let text = std::fs::read_to_string(&source)?;
        let mut records = Vec::<String>::new();
        for raw in text.lines() {
            let line = raw.split(';').next().unwrap_or("").trim();
            if line.is_empty() || line.starts_with('*') {
                continue;
            }
            if let Some(continuation) = line.strip_prefix('+') {
                let previous = records.last_mut().ok_or_else(|| {
                    Error::Parse(format!("{}: orphan SPICE continuation", source.display()))
                })?;
                previous.push(' ');
                previous.push_str(continuation.trim());
            } else {
                records.push(line.to_string());
            }
        }
        let subckts = records
            .iter()
            .filter(|line| line.to_ascii_lowercase().starts_with(".subckt"))
            .collect::<Vec<_>>();
        if subckts.len() != 1 {
            return Err(Error::Parse(format!(
                "{}: RC load must contain exactly one .SUBCKT (use a small wrapper deck for vendor includes)",
                source.display()
            )));
        }
        let subckt = subckts[0];
        let terminals = subckt.split_whitespace().collect::<Vec<_>>();
        if terminals.len() < 4 {
            return Err(Error::Parse(format!(
                "{}: RC load .SUBCKT needs two terminals",
                source.display()
            )));
        }
        let positive_terminal = terminals[2].to_string();
        let negative_terminal = terminals[3].to_string();
        let mut branches = Vec::new();
        for line in records {
            if line.starts_with('.') {
                continue;
            }
            let fields = line.split_whitespace().collect::<Vec<_>>();
            if fields.len() < 4 {
                return Err(Error::Parse(format!(
                    "{}: malformed RC load element '{line}'",
                    source.display()
                )));
            }
            let first = fields[0]
                .as_bytes()
                .first()
                .copied()
                .unwrap_or_default()
                .to_ascii_lowercase();
            let is_capacitor = match first {
                b'r' => false,
                b'c' => true,
                _ => {
                    return Err(Error::Parse(format!(
                        "{}: RC load supports only R/C elements, found '{line}'",
                        source.display()
                    )));
                }
            };
            let value = spice_number(fields[3]).ok_or_else(|| {
                Error::Parse(format!(
                    "{}: invalid RC load value '{}'",
                    source.display(),
                    fields[3]
                ))
            })?;
            if !value.is_finite() || value <= 0.0 {
                return Err(Error::Parse(format!(
                    "{}: RC load value must be positive",
                    source.display()
                )));
            }
            branches.push(RcBranch {
                positive: fields[1].to_string(),
                negative: fields[2].to_string(),
                value,
                is_capacitor,
            });
        }
        if branches.is_empty() {
            return Err(Error::Parse(format!(
                "{}: RC load contains no R/C elements",
                source.display()
            )));
        }
        Ok(Self {
            port,
            positive_terminal,
            negative_terminal,
            branches,
            source,
        })
    }

    pub fn admittance(&self, s: c64) -> Result<c64> {
        let mut names = BTreeSet::new();
        for branch in &self.branches {
            if branch.positive != self.negative_terminal {
                names.insert(branch.positive.clone());
            }
            if branch.negative != self.negative_terminal {
                names.insert(branch.negative.clone());
            }
        }
        let mut nodes = vec![self.positive_terminal.clone()];
        nodes.extend(
            names
                .into_iter()
                .filter(|node| node != &self.positive_terminal),
        );
        let indices = nodes
            .iter()
            .enumerate()
            .map(|(index, node)| (node.as_str(), index))
            .collect::<HashMap<_, _>>();
        let positive = *indices
            .get(self.positive_terminal.as_str())
            .ok_or_else(|| {
                Error::Parse(format!(
                    "{}: positive terminal is disconnected",
                    self.source.display()
                ))
            })?;
        if positive != 0 {
            return Err(Error::Parse(format!(
                "{}: RC load terminal ordering failed",
                self.source.display()
            )));
        }
        let size = nodes.len();
        let mut matrix = vec![c64::new(0.0, 0.0); size * size];
        for branch in &self.branches {
            let admittance = if branch.is_capacitor {
                s * branch.value
            } else {
                c64::new(1.0 / branch.value, 0.0)
            };
            let positive = indices.get(branch.positive.as_str()).copied();
            let negative = indices.get(branch.negative.as_str()).copied();
            if let Some(index) = positive {
                matrix[index * size + index] += admittance;
            }
            if let Some(index) = negative {
                matrix[index * size + index] += admittance;
            }
            if let (Some(row), Some(column)) = (positive, negative) {
                matrix[row * size + column] -= admittance;
                matrix[column * size + row] -= admittance;
            }
        }
        if size == 1 {
            return Ok(matrix[0]);
        }
        let internal_size = size - 1;
        let mut internal = Vec::with_capacity(internal_size * internal_size);
        for row in 0..internal_size {
            for column in 0..internal_size {
                internal.push(matrix[(row + 1) * size + column + 1]);
            }
        }
        let inverse = crate::rfm::invert_complex(&internal, internal_size)?;
        let mut correction = c64::new(0.0, 0.0);
        for left in 0..internal_size {
            for right in 0..internal_size {
                correction += matrix[left + 1]
                    * inverse[left * internal_size + right]
                    * matrix[(right + 1) * size];
            }
        }
        Ok(matrix[0] - correction)
    }
}

#[derive(Clone)]
pub struct ResponseLoads {
    pub shorted_ports: Vec<usize>,
    pub conductance: Vec<f64>,
    pub rc_shunts: Vec<RcShunt>,
}

impl ResponseLoads {
    pub fn empty(nports: usize) -> Self {
        Self {
            shorted_ports: Vec::new(),
            conductance: vec![0.0; nports],
            rc_shunts: Vec::new(),
        }
    }

    pub fn admittances(&self, s: c64) -> Result<Vec<c64>> {
        let mut result = self
            .conductance
            .iter()
            .map(|value| c64::new(*value, 0.0))
            .collect::<Vec<_>>();
        for shunt in &self.rc_shunts {
            result[shunt.port] += shunt.admittance(s)?;
        }
        Ok(result)
    }
}

pub fn evaluate_response_grid(
    model: &RfmModel,
    fft_size: usize,
    dt: f64,
    inputs: &[usize],
    outputs: &[usize],
    loads: &ResponseLoads,
    threads: usize,
) -> Result<Vec<c64>> {
    let bins = fft_size / 2 + 1;
    let values_per_bin = inputs.len() * outputs.len();
    let workers = threads.min(bins).max(1);
    if workers == 1 {
        let mut values = Vec::with_capacity(bins * values_per_bin);
        for bin in 0..bins {
            let frequency = bin as f64 / (fft_size as f64 * dt);
            let s = c64::new(0.0, 2.0 * std::f64::consts::PI * frequency);
            values.extend(model.loaded_impedance_response(
                s,
                outputs,
                inputs,
                &loads.shorted_ports,
                &loads.admittances(s)?,
            )?);
        }
        return Ok(values);
    }
    let chunk = bins.div_ceil(workers);
    let mut pieces = Vec::new();
    std::thread::scope(|scope| -> Result<()> {
        let mut handles = Vec::new();
        for start in (0..bins).step_by(chunk) {
            let stop = (start + chunk).min(bins);
            handles.push(scope.spawn(move || -> Result<(usize, Vec<c64>)> {
                let mut values = Vec::with_capacity((stop - start) * values_per_bin);
                for bin in start..stop {
                    let frequency = bin as f64 / (fft_size as f64 * dt);
                    let s = c64::new(0.0, 2.0 * std::f64::consts::PI * frequency);
                    values.extend(model.loaded_impedance_response(
                        s,
                        outputs,
                        inputs,
                        &loads.shorted_ports,
                        &loads.admittances(s)?,
                    )?);
                }
                Ok((start, values))
            }));
        }
        for handle in handles {
            pieces.push(
                handle
                    .join()
                    .map_err(|_| Error::Sparse("RFM response worker panicked".into()))??,
            );
        }
        Ok(())
    })?;
    pieces.sort_by_key(|(start, _)| *start);
    Ok(pieces.into_iter().flat_map(|(_, values)| values).collect())
}

pub fn spice_number(token: &str) -> Option<f64> {
    let token = token.trim().replace(['D', 'd'], "E");
    if let Ok(value) = token.parse::<f64>() {
        return Some(value);
    }
    let numeric_end = token
        .char_indices()
        .take_while(|(_, character)| {
            character.is_ascii_digit() || matches!(character, '.' | '+' | '-' | 'E' | 'e')
        })
        .map(|(index, character)| index + character.len_utf8())
        .last()?;
    let number = token[..numeric_end].parse::<f64>().ok()?;
    let suffix = token[numeric_end..].to_ascii_lowercase();
    let multiplier = if suffix.starts_with("meg") {
        1e6
    } else if suffix.starts_with('t') {
        1e12
    } else if suffix.starts_with('g') {
        1e9
    } else if suffix.starts_with('k') {
        1e3
    } else if suffix.starts_with('m') {
        1e-3
    } else if suffix.starts_with('u') {
        1e-6
    } else if suffix.starts_with('n') {
        1e-9
    } else if suffix.starts_with('p') {
        1e-12
    } else if suffix.starts_with('f') {
        1e-15
    } else {
        return None;
    };
    Some(number * multiplier)
}
