//! AS-03 direct port of the reachable `fit-yparam` path.
//!
//! This module keeps the portable multi-port branches from the pinned Python
//! implementation: bounded Touchstone-1.x parsing, strict `(I-S)(I+S)^-1/Z0`
//! conversion, sampled positive-real checks, native vector fitting, common-ground
//! Y delivery, HTML diagnostics, and the exact proper-rational Y-to-S LFT.
//! Commercial simulator execution remains an explicit AS-05/AS-06 concern.

use std::fmt::{Display, Formatter};
use std::fs;
use std::path::{Path, PathBuf};

use faer::{Mat, Side, linalg::solvers::DenseSolveCore, prelude::Solve};
use num_complex::Complex64 as Complex;
use serde_json::{Value, json};

use crate::as06_run_rfm::{RfmModel, write_cadence_rfm, write_cadence_rfm_wrapper};
use crate::fit_sparam::{
    BasisKind, FitSparamOptions, PassivityPolicy, RationalFitModel, TouchstoneNetwork,
    fit_native_vector_fitting, initial_poles,
};

pub const UPSTREAM_COMMIT: &str = "2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5";
pub const UPSTREAM_TREE: &str = "b6bde97128030d6cea0d68b2f0a35d807be8c402";
pub const WORKFLOW_ID: &str = "AS-03";
pub const WORKFLOW_NAME: &str = "fit-yparam";
const MAX_ORDER: usize = 40;
const MAX_EVALUATIONS: usize = 64;
const MAX_PORTS: usize = 32;
const MAX_SAMPLES: usize = 8_192;
const MAX_ARTIFACT_BYTES: usize = 4 * 1024 * 1024;
// Keep the dense local KYP-LMI route within the pinned CLI's default state
// budget. Larger exact deliveries fail closed before allocating a quadratic
// Riccati pencil instead of turning n-port input into an unbounded workload.
const MAX_KYP_STATES: usize = 128;

#[derive(Clone, Debug, PartialEq)]
pub struct FitYparamOptions {
    pub output: Option<PathBuf>,
    pub derived_s_touchstone: Option<PathBuf>,
    pub html_report: Option<PathBuf>,
    pub report: Option<PathBuf>,
    pub log: Option<PathBuf>,
    pub subckt_name: String,
    pub n_poles_real: usize,
    pub n_poles_cmplx: usize,
    pub max_order: usize,
    pub order_step: usize,
    pub pole_spacing: String,
    pub fit_iterations: usize,
    pub fit_proportional: bool,
    pub max_y_rms_siemens: Option<f64>,
    pub passivity: PassivityPolicy,
    pub passivity_epsilon: f64,
    pub conversion_condition_limit: f64,
    pub exact_s_rfm: Option<PathBuf>,
    pub exact_s_touchstone: Option<PathBuf>,
    pub exact_s_rfm_wrapper: Option<PathBuf>,
}

impl Default for FitYparamOptions {
    fn default() -> Self {
        Self {
            output: None,
            derived_s_touchstone: None,
            html_report: None,
            report: None,
            log: None,
            subckt_name: "y_equivalent".to_owned(),
            n_poles_real: 1,
            n_poles_cmplx: 3,
            max_order: MAX_ORDER,
            order_step: 2,
            pole_spacing: "log".to_owned(),
            fit_iterations: 20,
            fit_proportional: true,
            max_y_rms_siemens: None,
            passivity: PassivityPolicy::Check,
            passivity_epsilon: 1e-9,
            conversion_condition_limit: 1e12,
            exact_s_rfm: None,
            exact_s_touchstone: None,
            exact_s_rfm_wrapper: None,
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct FitYparamRequest {
    pub touchstone: PathBuf,
    pub options: FitYparamOptions,
}

impl FitYparamRequest {
    pub fn new(
        touchstone: impl Into<PathBuf>,
        options: FitYparamOptions,
    ) -> Result<Self, FitYparamError> {
        let touchstone = touchstone.into();
        validate_options(&touchstone, &options)?;
        Ok(Self {
            touchstone,
            options,
        })
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct FitYparamResult {
    pub target_met: bool,
    pub selected_order: usize,
    pub y_rms_siemens: f64,
    pub y_mean_rms_siemens: f64,
    pub conversion_condition_max: f64,
    pub passivity_min_eigenvalue: Option<f64>,
    pub passivity_violation_count: Option<usize>,
    pub model: RationalFitModel,
    pub report: PathBuf,
    pub output: PathBuf,
    pub derived_s_touchstone: Option<PathBuf>,
    pub html_report: Option<PathBuf>,
    pub exact_s_rfm: Option<PathBuf>,
    pub exact_s_touchstone: Option<PathBuf>,
    pub exact_s_rfm_wrapper: Option<PathBuf>,
    pub log: PathBuf,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum FitYparamError {
    InvalidOption(String),
    Unsupported(String),
    Input(String),
    Numerical(String),
    Output(String),
}

impl Display for FitYparamError {
    fn fmt(&self, f: &mut Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::InvalidOption(value) => write!(f, "invalid fit-yparam option: {value}"),
            Self::Unsupported(value) => write!(f, "unsupported fit-yparam path: {value}"),
            Self::Input(value) => write!(f, "fit-yparam input error: {value}"),
            Self::Numerical(value) => write!(f, "fit-yparam numerical error: {value}"),
            Self::Output(value) => write!(f, "fit-yparam output error: {value}"),
        }
    }
}

impl std::error::Error for FitYparamError {}

fn validate_options(path: &Path, options: &FitYparamOptions) -> Result<(), FitYparamError> {
    if path.as_os_str().is_empty() {
        return Err(FitYparamError::InvalidOption(
            "touchstone path is empty".to_owned(),
        ));
    }
    if options.max_order == 0 || options.max_order > MAX_ORDER {
        return Err(FitYparamError::InvalidOption(format!(
            "max_order must be in 1..={MAX_ORDER}"
        )));
    }
    if options.order_step == 0 || options.order_step > MAX_ORDER {
        return Err(FitYparamError::InvalidOption(
            "order_step must be positive and bounded".to_owned(),
        ));
    }
    if options.fit_iterations == 0 || options.fit_iterations > MAX_EVALUATIONS {
        return Err(FitYparamError::InvalidOption(
            "fit_iterations exceeds the bounded budget".to_owned(),
        ));
    }
    if options
        .n_poles_real
        .saturating_add(options.n_poles_cmplx.saturating_mul(2))
        == 0
    {
        return Err(FitYparamError::InvalidOption(
            "at least one fitting pole is required".to_owned(),
        ));
    }
    if options.n_poles_real > MAX_ORDER || options.n_poles_cmplx > MAX_ORDER / 2 {
        return Err(FitYparamError::InvalidOption(
            "initial pole counts exceed the bounded order".to_owned(),
        ));
    }
    if !options.passivity_epsilon.is_finite() || options.passivity_epsilon < 0.0 {
        return Err(FitYparamError::InvalidOption(
            "passivity_epsilon must be finite and non-negative".to_owned(),
        ));
    }
    if options.passivity == PassivityPolicy::Enforce {
        return Err(FitYparamError::Unsupported(
            "Y positive-real enforcement requires the exact KYP delivery path; use --passivity check or off".to_owned(),
        ));
    }
    if !options.conversion_condition_limit.is_finite() || options.conversion_condition_limit <= 1.0
    {
        return Err(FitYparamError::InvalidOption(
            "conversion_condition_limit must be finite and > 1".to_owned(),
        ));
    }
    if let Some(target) = options.max_y_rms_siemens
        && (!target.is_finite() || target <= 0.0)
    {
        return Err(FitYparamError::InvalidOption(
            "max_y_rms_siemens must be finite and > 0".to_owned(),
        ));
    }
    if options.subckt_name.is_empty() || options.subckt_name.chars().any(char::is_whitespace) {
        return Err(FitYparamError::InvalidOption(
            "subckt_name must be non-empty and whitespace-free".to_owned(),
        ));
    }
    if options.pole_spacing != "lin" && options.pole_spacing != "log" {
        return Err(FitYparamError::InvalidOption(
            "pole_spacing must be lin or log".to_owned(),
        ));
    }
    if options.exact_s_rfm_wrapper.is_some() && options.exact_s_rfm.is_none() {
        return Err(FitYparamError::InvalidOption(
            "exact_s_rfm_wrapper requires exact_s_rfm".to_owned(),
        ));
    }
    if (options.exact_s_rfm.is_some()
        || options.exact_s_touchstone.is_some()
        || options.exact_s_rfm_wrapper.is_some())
        && options.fit_proportional
    {
        return Err(FitYparamError::Unsupported("exact Y-to-S RFM delivery requires --no-fit-proportional (descriptor delivery is not enabled)".to_owned()));
    }
    Ok(())
}

#[derive(Clone, Copy)]
enum DataFormat {
    Ri,
    Ma,
    Db,
}

fn infer_ports(path: &Path) -> Result<usize, FitYparamError> {
    let name = path
        .file_name()
        .and_then(|v| v.to_str())
        .ok_or_else(|| FitYparamError::Input("Touchstone filename is not UTF-8".to_owned()))?
        .to_ascii_lowercase();
    let marker = name
        .rfind(".s")
        .ok_or_else(|| FitYparamError::Input("filename must end in .sNp".to_owned()))?;
    let digits = name[marker + 2..]
        .strip_suffix('p')
        .ok_or_else(|| FitYparamError::Input("filename must end in .sNp".to_owned()))?;
    let ports = digits
        .parse::<usize>()
        .map_err(|_| FitYparamError::Input("Touchstone port count is invalid".to_owned()))?;
    if ports == 0 || ports > MAX_PORTS {
        return Err(FitYparamError::Unsupported(format!(
            "n-port input is outside 1..={MAX_PORTS}"
        )));
    }
    Ok(ports)
}

/// Bounded Touchstone-1.x loader that intentionally does not inherit AS-01's
/// two-port admission gate.  The file is column-major, while the returned
/// network is row-major so every matrix operation and delivery path uses the
/// same S12/S21 convention.
pub(crate) fn read_multiport_touchstone(path: &Path) -> Result<TouchstoneNetwork, FitYparamError> {
    let ports = infer_ports(path);
    let ports = ports?;
    let bytes = fs::read(path).map_err(|e| FitYparamError::Input(e.to_string()))?;
    if bytes.len() > 16 * 1024 * 1024 {
        return Err(FitYparamError::Input(
            "Touchstone exceeds byte budget".to_owned(),
        ));
    }
    if !bytes.is_ascii() {
        return Err(FitYparamError::Input("Touchstone must be ASCII".to_owned()));
    }
    let text = std::str::from_utf8(&bytes).map_err(|e| FitYparamError::Input(e.to_string()))?;
    let expected = 1 + 2 * ports * ports;
    let mut scale = None;
    let mut format = None;
    let mut z0: f64 = 50.0;
    let mut header = false;
    let mut pending = Vec::<f64>::new();
    let mut frequencies = Vec::new();
    let mut samples = Vec::new();
    for raw in text.lines() {
        let line = raw.split_once('!').map_or(raw, |(a, _)| a).trim();
        if line.is_empty() {
            continue;
        }
        if line.starts_with('[') {
            return Err(FitYparamError::Unsupported(
                "Touchstone 2.0 bracket sections".to_owned(),
            ));
        }
        if line.starts_with('#') {
            if header {
                return Err(FitYparamError::Input(
                    "multiple Touchstone option lines".to_owned(),
                ));
            }
            let t = line.split_whitespace().collect::<Vec<_>>();
            if t.len() < 4 || t[0] != "#" {
                return Err(FitYparamError::Input(
                    "invalid Touchstone option line".to_owned(),
                ));
            }
            scale = Some(match t[1].to_ascii_lowercase().as_str() {
                "hz" => 1.0,
                "khz" => 1e3,
                "mhz" => 1e6,
                "ghz" => 1e9,
                other => {
                    return Err(FitYparamError::Input(format!(
                        "unsupported frequency unit {other}"
                    )));
                }
            });
            format = Some(match t[3].to_ascii_lowercase().as_str() {
                "ri" => DataFormat::Ri,
                "ma" => DataFormat::Ma,
                "db" => DataFormat::Db,
                other => {
                    return Err(FitYparamError::Input(format!(
                        "unsupported Touchstone format {other}"
                    )));
                }
            });
            if !t[2].eq_ignore_ascii_case("s") {
                return Err(FitYparamError::Input(
                    "only S parameters are accepted".to_owned(),
                ));
            }
            let mut i = 4;
            while i < t.len() {
                if !t[i].eq_ignore_ascii_case("r") {
                    return Err(FitYparamError::Input(format!("unexpected option {}", t[i])));
                }
                z0 = t
                    .get(i + 1)
                    .ok_or_else(|| FitYparamError::Input("R requires a value".to_owned()))?
                    .parse()
                    .map_err(|_| FitYparamError::Input("R is not numeric".to_owned()))?;
                i += 2;
            }
            header = true;
            continue;
        }
        if !header {
            return Err(FitYparamError::Input(
                "Touchstone option line is required".to_owned(),
            ));
        }
        for token in line.split_whitespace() {
            pending.push(token.parse().map_err(|_| {
                FitYparamError::Input(format!("non-numeric Touchstone token {token}"))
            })?);
        }
        while pending.len() >= expected {
            let row = pending.drain(..expected).collect::<Vec<_>>();
            let f = row[0] * scale.expect("header sets scale");
            if !f.is_finite() || f < 0.0 {
                return Err(FitYparamError::Input("frequency is invalid".to_owned()));
            }
            let mut response = vec![Complex::new(0.0, 0.0); ports * ports];
            for (token_index, pair) in row[1..].chunks_exact(2).enumerate() {
                let value = match format.expect("header sets format") {
                    DataFormat::Ri => Complex::new(pair[0], pair[1]),
                    DataFormat::Ma => {
                        let a = pair[1].to_radians();
                        Complex::from_polar(pair[0], a)
                    }
                    DataFormat::Db => {
                        let a = pair[1].to_radians();
                        Complex::from_polar(10.0_f64.powf(pair[0] / 20.0), a)
                    }
                };
                let row_index = token_index % ports;
                let column_index = token_index / ports;
                response[row_index * ports + column_index] = value;
            }
            if response
                .iter()
                .any(|v| !v.re.is_finite() || !v.im.is_finite())
            {
                return Err(FitYparamError::Input(
                    "network sample is non-finite".to_owned(),
                ));
            }
            frequencies.push(f);
            samples.push(response);
            if samples.len() > MAX_SAMPLES {
                return Err(FitYparamError::Input(
                    "Touchstone sample budget exceeded".to_owned(),
                ));
            }
        }
    }
    if !header || !pending.is_empty() || samples.len() < 2 {
        return Err(FitYparamError::Input(
            "incomplete Touchstone data".to_owned(),
        ));
    }
    if !z0.is_finite() || z0 <= 0.0 || frequencies.windows(2).any(|w| w[1] < w[0]) {
        return Err(FitYparamError::Input(
            "Touchstone reference/frequency ordering is invalid".to_owned(),
        ));
    }
    TouchstoneNetwork::from_samples(frequencies, samples, ports, z0)
        .map_err(|e| FitYparamError::Input(e.to_string()))
}

fn mat_add_identity(a: &[Complex], n: usize, sign: f64) -> Vec<Complex> {
    a.iter()
        .enumerate()
        .map(|(i, v)| {
            *v + if i / n == i % n {
                Complex::new(sign, 0.0)
            } else {
                Complex::new(0.0, 0.0)
            }
        })
        .collect()
}
fn mat_mul(a: &[Complex], b: &[Complex], n: usize) -> Vec<Complex> {
    (0..n)
        .flat_map(|i| (0..n).map(move |j| (0..n).map(|k| a[i * n + k] * b[k * n + j]).sum()))
        .collect()
}
fn mat_sub(a: &[Complex], b: &[Complex]) -> Vec<Complex> {
    a.iter().zip(b).map(|(x, y)| *x - *y).collect()
}
fn mat_scale(a: &[Complex], scale: Complex) -> Vec<Complex> {
    a.iter().map(|x| *x * scale).collect()
}
fn mat_mul_rect(a: &[Complex], ar: usize, ac: usize, b: &[Complex], bc: usize) -> Vec<Complex> {
    (0..ar)
        .flat_map(|i| (0..bc).map(move |j| (0..ac).map(|k| a[i * ac + k] * b[k * bc + j]).sum()))
        .collect()
}

fn mat_inverse(a: &[Complex], n: usize) -> Option<Vec<Complex>> {
    if a.len() != n * n {
        return None;
    }
    let mut aug = vec![Complex::new(0.0, 0.0); n * 2 * n];
    for i in 0..n {
        for j in 0..n {
            aug[i * 2 * n + j] = a[i * n + j];
            aug[i * 2 * n + n + j] = if i == j {
                Complex::new(1.0, 0.0)
            } else {
                Complex::new(0.0, 0.0)
            };
        }
    }
    for column in 0..n {
        let pivot = (column..n).max_by(|&i, &j| {
            aug[i * 2 * n + column]
                .norm()
                .total_cmp(&aug[j * 2 * n + column].norm())
        })?;
        if aug[pivot * 2 * n + column].norm() <= f64::MIN_POSITIVE {
            return None;
        }
        if pivot != column {
            for j in 0..2 * n {
                aug.swap(pivot * 2 * n + j, column * 2 * n + j);
            }
        }
        let value = aug[column * 2 * n + column];
        for j in 0..2 * n {
            aug[column * 2 * n + j] /= value;
        }
        let pivot_row = aug[column * 2 * n..(column + 1) * 2 * n].to_vec();
        for row in 0..n {
            if row != column {
                let factor = aug[row * 2 * n + column];
                for j in 0..2 * n {
                    aug[row * 2 * n + j] -= factor * pivot_row[j];
                }
            }
        }
    }
    let mut result = Vec::with_capacity(n * n);
    for i in 0..n {
        for j in 0..n {
            result.push(aug[i * 2 * n + n + j]);
        }
    }
    Some(result)
}

fn condition_number(a: &[Complex], n: usize) -> Result<f64, FitYparamError> {
    let matrix = Mat::from_fn(n, n, |i, j| a[i * n + j]);
    let singular = matrix
        .singular_values()
        .map_err(|e| FitYparamError::Numerical(format!("singular-value solve failed: {e:?}")))?;
    let max = singular.first().copied().unwrap_or(0.0);
    let min = singular.last().copied().unwrap_or(0.0);
    Ok(if min.is_finite() && min > f64::MIN_POSITIVE {
        max / min
    } else {
        f64::INFINITY
    })
}

fn convert_s_to_y(
    sample: &[Complex],
    n: usize,
    z0: f64,
    limit: f64,
) -> Result<(Vec<Complex>, f64), FitYparamError> {
    let plus = mat_add_identity(sample, n, 1.0);
    let condition = condition_number(&plus, n)?;
    if !condition.is_finite() || condition > limit {
        return Err(FitYparamError::Numerical(format!(
            "S-to-Y conversion condition estimate {condition:.12e} exceeds {limit:.12e}"
        )));
    }
    // Keep the pinned scikit-rf power-wave sequence: build A=(S@G+conj(G))@F,
    // B=(I-S)@F, then solve A X=B instead of materializing an inverse. The
    // caller-configured condition gate above remains fail-closed; nudge_eig is
    // not ported, so equivalence is limited to verified well-conditioned cases.
    let g = (0..n * n)
        .map(|index| {
            if index / n == index % n {
                Complex::new(z0, 0.0)
            } else {
                Complex::new(0.0, 0.0)
            }
        })
        .collect::<Vec<_>>();
    let f_value = 1.0 / (2.0 * z0.sqrt());
    let f = (0..n * n)
        .map(|index| {
            if index / n == index % n {
                Complex::new(f_value, 0.0)
            } else {
                Complex::new(0.0, 0.0)
            }
        })
        .collect::<Vec<_>>();
    let a = mat_mul(
        &mat_mul(sample, &g, n)
            .iter()
            .zip(g.iter())
            .map(|(left, right)| *left + right.conj())
            .collect::<Vec<_>>(),
        &f,
        n,
    );
    let identity = (0..n * n)
        .map(|index| {
            if index / n == index % n {
                Complex::new(1.0, 0.0)
            } else {
                Complex::new(0.0, 0.0)
            }
        })
        .collect::<Vec<_>>();
    let b = mat_mul(
        &identity
            .iter()
            .zip(sample.iter())
            .map(|(left, right)| *left - *right)
            .collect::<Vec<_>>(),
        &f,
        n,
    );
    let lhs = Mat::from_fn(n, n, |row, column| a[row * n + column]);
    let rhs = Mat::from_fn(n, n, |row, column| b[row * n + column]);
    let solved = lhs.partial_piv_lu().solve(rhs.as_ref());
    let result = (0..n * n)
        .map(|index| solved[(index / n, index % n)])
        .collect::<Vec<_>>();
    if result
        .iter()
        .any(|value| !value.re.is_finite() || !value.im.is_finite())
    {
        return Err(FitYparamError::Numerical(
            "power-wave S-to-Y solve produced non-finite values".to_owned(),
        ));
    }
    Ok((result, condition))
}

fn y_to_s(y: &[Complex], n: usize, z0: f64) -> Option<Vec<Complex>> {
    let z = mat_scale(y, Complex::new(z0, 0.0));
    let numerator = mat_add_identity(&z, n, -1.0)
        .into_iter()
        .map(|v| -v)
        .collect::<Vec<_>>();
    let denominator = mat_add_identity(&z, n, 1.0);
    let inverse = mat_inverse(&denominator, n)?;
    Some(mat_mul(&numerator, &inverse, n))
}

fn min_hermitian_eigenvalue(value: &[Complex], n: usize) -> Result<f64, FitYparamError> {
    let hermitian = Mat::from_fn(n, n, |i, j| {
        (value[i * n + j] + value[j * n + i].conj()) * Complex::new(0.5, 0.0)
    });
    let values = hermitian
        .self_adjoint_eigenvalues(Side::Lower)
        .map_err(|e| {
            FitYparamError::Numerical(format!("Hermitian eigenvalue solve failed: {e:?}"))
        })?;
    values
        .into_iter()
        .reduce(f64::min)
        .ok_or_else(|| FitYparamError::Numerical("empty Hermitian matrix".to_owned()))
}

fn pole_counts_for_order(real_count: usize, requested_order: usize) -> (usize, usize) {
    let mut real = real_count.min(requested_order);
    if !(requested_order - real).is_multiple_of(2) {
        if real < requested_order {
            real += 1;
        } else {
            real = real.saturating_sub(1);
        }
    }
    (real, (requested_order - real) / 2)
}

// The upstream fitter solves an unconstrained complex least-squares system.
// Y-SPICE and Cadence RFM are real-coefficient delivery formats, so canonicalize
// each candidate to its real rational representation before measuring or writing
// artifacts.  For a conjugate pole pair, averaging with the conjugate partner
// preserves the closest real model instead of silently dropping an imaginary
// coefficient.
fn enforce_real_rational_coefficients(model: &mut RationalFitModel) {
    for value in &mut model.constant {
        value.im = 0.0;
    }
    for value in &mut model.proportional {
        value.im = 0.0;
    }
    for index in 0..model.poles.len() {
        if model.poles[index].im.abs() <= 1e-12 {
            model.poles[index].im = 0.0;
            for value in &mut model.residues[index] {
                value.im = 0.0;
            }
            continue;
        }
        if model.poles[index].im < 0.0 {
            continue;
        }
        let Some(partner) = (index + 1..model.poles.len()).find(|candidate| {
            (model.poles[*candidate] - model.poles[index].conj()).norm()
                <= 1e-10 * model.poles[index].norm().max(1.0)
        }) else {
            continue;
        };
        for response in 0..model.residues[index].len() {
            let positive = model.residues[index][response];
            let negative = model.residues[partner][response].conj();
            let averaged = (positive + negative) * Complex::new(0.5, 0.0);
            model.residues[index][response] = averaged;
            model.residues[partner][response] = averaged.conj();
        }
    }
}

fn rms_metrics(
    original: &TouchstoneNetwork,
    fitted: &RationalFitModel,
    y_samples: &[Vec<Complex>],
) -> (f64, f64) {
    let per_response = (0..original.response_count())
        .map(|response| {
            let sum = original
                .frequencies_hz()
                .iter()
                .enumerate()
                .map(|(i, f)| {
                    fitted
                        .evaluate(*f)
                        .get(response)
                        .zip(y_samples[i].get(response))
                        .map_or(0.0, |(a, b)| (*a - *b).norm_sqr())
                })
                .sum::<f64>();
            (sum / y_samples.len() as f64).sqrt()
        })
        .collect::<Vec<_>>();
    let rms = per_response
        .iter()
        .map(|value| value * value)
        .sum::<f64>()
        .sqrt();
    let mean_rms = rms / original.ports() as f64;
    (rms, mean_rms)
}

fn passivity_metrics(
    model: &RationalFitModel,
    frequencies: &[f64],
    policy: PassivityPolicy,
    epsilon: f64,
) -> Result<(f64, usize), FitYparamError> {
    if policy == PassivityPolicy::Off {
        return Ok((f64::NAN, 0));
    }
    let mut points = frequencies.to_vec();
    points.extend(
        frequencies
            .windows(2)
            .filter(|w| w[0] > 0.0 && w[1] > 0.0)
            .map(|w| (w[0] * w[1]).sqrt()),
    );
    for pole in &model.poles {
        points.push(pole.im.abs() * model.frequency_scale_hz / (2.0 * std::f64::consts::PI));
        points.push(pole.re.abs() * model.frequency_scale_hz / (2.0 * std::f64::consts::PI));
    }
    points.retain(|x| x.is_finite() && *x >= 0.0);
    points.sort_by(f64::total_cmp);
    points.dedup_by(|a, b| *a == *b);
    let mut minimum = f64::INFINITY;
    let mut violations = 0;
    for f in points {
        let eigen = min_hermitian_eigenvalue(&model.evaluate(f), model.ports)?;
        minimum = minimum.min(eigen);
        if eigen < -epsilon {
            violations += 1;
        }
    }
    Ok((minimum, violations))
}

fn output_paths(
    input: &Path,
    options: &FitYparamOptions,
) -> (PathBuf, PathBuf, PathBuf, Option<PathBuf>, Option<PathBuf>) {
    let stem = input
        .file_stem()
        .and_then(|v| v.to_str())
        .unwrap_or("input");
    let parent = input.parent().unwrap_or_else(|| Path::new("."));
    let base = parent.join(format!("{stem}_fitted.y.sp"));
    (
        options.output.clone().unwrap_or(base.clone()),
        options
            .report
            .clone()
            .unwrap_or_else(|| base.with_extension("json")),
        options
            .log
            .clone()
            .unwrap_or_else(|| base.with_extension("log")),
        options.derived_s_touchstone.clone(),
        options.html_report.clone(),
    )
}
fn write_text(path: &Path, text: &str) -> Result<(), FitYparamError> {
    if text.len() > MAX_ARTIFACT_BYTES {
        return Err(FitYparamError::Output(
            "artifact byte budget exceeded".to_owned(),
        ));
    }
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|e| FitYparamError::Output(e.to_string()))?;
    }
    fs::write(path, text).map_err(|e| FitYparamError::Output(e.to_string()))
}
fn real_coeff(value: Complex, label: &str) -> Result<f64, FitYparamError> {
    if !value.re.is_finite()
        || !value.im.is_finite()
        || value.im.abs() > 1e-8 * value.re.abs().max(1.0)
    {
        return Err(FitYparamError::Unsupported(format!(
            "Y SPICE export requires real {label}"
        )));
    }
    Ok(value.re)
}

fn write_y_subcircuit(
    path: &Path,
    model: &RationalFitModel,
    name: &str,
) -> Result<(), FitYparamError> {
    if model.poles.iter().any(|p| p.re >= 0.0) {
        return Err(FitYparamError::Unsupported(
            "Y SPICE export requires stable poles".to_owned(),
        ));
    }
    let n = model.ports;
    let mut lines = vec![
        "* Y-PARAMETER NORTON/MNA EQUIVALENT".to_owned(),
        "* I=Y(s)V; current is positive into each port; global ground references".to_owned(),
        format!(
            ".subckt {name} {}",
            (1..=n)
                .map(|i| format!("p{i}"))
                .collect::<Vec<_>>()
                .join(" ")
        ),
    ];
    for row in 0..n {
        for column in 0..n {
            let r = row * n + column;
            let d = real_coeff(model.constant[r], "constant coefficient")?;
            let e = real_coeff(model.proportional[r], "proportional coefficient")?;
            if d != 0.0 {
                lines.push(format!(
                    "Gd{row}_{column} p{} 0 p{} 0 {d:.16e}",
                    row + 1,
                    column + 1
                ));
            }
            if e != 0.0 {
                lines.push(format!(
                    "Fy{row}_{column} p{} 0 Vdy{} {e:.16e}",
                    row + 1,
                    column + 1
                ));
            }
            for (k, pole) in model.poles.iter().enumerate() {
                let residue = model.residues[k][r];
                let physical_residue = residue * model.frequency_scale_hz;
                if pole.im == 0.0 {
                    let v = real_coeff(physical_residue, "real-pole residue")?;
                    if v != 0.0 {
                        lines.push(format!(
                            "Gr{k}_{row}_{column} p{} 0 x{k}_a{} 0 {v:.16e}",
                            row + 1,
                            column + 1
                        ));
                    }
                } else if pole.im > 0.0 {
                    // SPICE receives separate real/imaginary residue paths;
                    // do not reject the imaginary coefficient as if it were
                    // a real-pole scalar.
                    let v = physical_residue.re;
                    let vi = if physical_residue.im.is_finite() {
                        physical_residue.im
                    } else {
                        return Err(FitYparamError::Numerical(
                            "complex residue is non-finite".to_owned(),
                        ));
                    };
                    if v != 0.0 {
                        lines.push(format!(
                            "Gr{k}r_{row}_{column} p{} 0 x{k}r_a{} 0 {v:.16e}",
                            row + 1,
                            column + 1
                        ));
                    }
                    if vi != 0.0 {
                        lines.push(format!(
                            "Gr{k}i_{row}_{column} p{} 0 x{k}i_a{} 0 {vi:.16e}",
                            row + 1,
                            column + 1
                        ));
                    }
                }
            }
        }
    }
    for column in 0..n {
        for (k, pole) in model.poles.iter().enumerate() {
            let physical_pole = *pole * model.frequency_scale_hz;
            if pole.im == 0.0 {
                lines.extend([
                    format!("Cx{k}_a{} x{k}_a{} 0 1", column + 1, column + 1),
                    format!(
                        "Gx{k}_a{} 0 x{k}_a{} p{} 0 1",
                        column + 1,
                        column + 1,
                        column + 1
                    ),
                    format!(
                        "Rp{k}_a{} x{k}_a{} 0 {:.16e}",
                        column + 1,
                        column + 1,
                        -1.0 / physical_pole.re
                    ),
                ]);
            } else if pole.im > 0.0 {
                lines.extend([
                    format!("Cx{k}r_a{} x{k}r_a{} 0 1", column + 1, column + 1),
                    format!(
                        "Gx{k}r_a{} 0 x{k}r_a{} p{} 0 2",
                        column + 1,
                        column + 1,
                        column + 1
                    ),
                    format!(
                        "Rp{k}r_a{} x{k}r_a{} 0 {:.16e}",
                        column + 1,
                        column + 1,
                        -1.0 / physical_pole.re
                    ),
                    format!(
                        "Gp{k}ri_a{} 0 x{k}r_a{} x{k}i_a{} 0 {:.16e}",
                        column + 1,
                        column + 1,
                        column + 1,
                        physical_pole.im
                    ),
                    format!("Cx{k}i_a{} x{k}i_a{} 0 1", column + 1, column + 1),
                    format!(
                        "Gp{k}ir_a{} 0 x{k}i_a{} x{k}r_a{} 0 {:.16e}",
                        column + 1,
                        column + 1,
                        column + 1,
                        -physical_pole.im
                    ),
                    format!(
                        "Rp{k}i_a{} x{k}i_a{} 0 {:.16e}",
                        column + 1,
                        column + 1,
                        -1.0 / physical_pole.re
                    ),
                ]);
            }
        }
    }
    lines.push(format!(".ends {name}"));
    write_text(path, &(lines.join("\n") + "\n"))
}

fn write_s_touchstone(
    path: &Path,
    frequencies: &[f64],
    model: &RationalFitModel,
    z0: f64,
) -> Result<(), FitYparamError> {
    let mut out = format!("# Hz S RI R {z0:.17e}\n");
    for f in frequencies {
        let s = y_to_s(&model.evaluate(*f), model.ports, z0).ok_or_else(|| {
            FitYparamError::Numerical("fitted Y-to-S conversion is singular".to_owned())
        })?;
        out.push_str(&format!("{f:.17e}"));
        for column in 0..model.ports {
            for row in 0..model.ports {
                let v = s[row * model.ports + column];
                out.push_str(&format!(" {:.17e} {:.17e}", v.re, v.im));
            }
        }
        out.push('\n');
    }
    write_text(path, &out)
}
fn html_escape(value: &str) -> String {
    value
        .replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
}
fn html_report(path: &Path, payload: &serde_json::Value) -> Result<(), FitYparamError> {
    let body =
        serde_json::to_string_pretty(payload).map_err(|e| FitYparamError::Output(e.to_string()))?;
    write_text(
        path,
        &format!(
            "<!doctype html><meta charset=\"utf-8\"><title>fit-yparam report</title><h1>fit-yparam</h1><p>Portable multi-port Y fit diagnostics.</p><pre>{}</pre>\n",
            html_escape(&body)
        ),
    )
}

/// Convert the native vector-fit model to the exact proper-rational LFT used
/// by upstream `exact_y_to_s_rational`; this is a state-space transform, not a
/// sampled S refit.
fn fit_to_rfm(model: &RationalFitModel, z0: f64) -> Result<RfmModel, FitYparamError> {
    if model.proportional.iter().any(|x| x.norm() > 1e-12) {
        return Err(FitYparamError::Unsupported(
            "exact RFM delivery requires a proper Y model".to_owned(),
        ));
    }
    let n = model.ports;
    let count = n * n;
    let state = model.poles.len() * n;
    let dim = state;
    let mut a = vec![Complex::new(0.0, 0.0); dim * dim];
    let mut b = vec![Complex::new(0.0, 0.0); state * n];
    let mut c = vec![Complex::new(0.0, 0.0); n * state];
    for (pole_index, pole) in model.poles.iter().enumerate() {
        for input in 0..n {
            let si = pole_index * n + input;
            a[si * dim + si] = *pole * model.frequency_scale_hz;
            b[si * n + input] = Complex::new(1.0, 0.0);
            for output in 0..n {
                c[output * state + si] =
                    model.residues[pole_index][output * n + input] * model.frequency_scale_hz;
            }
        }
    }
    let d = model.constant.clone();
    let f = mat_inverse(
        &mat_add_identity(&mat_scale(&d, Complex::new(z0, 0.0)), n, 1.0),
        n,
    )
    .ok_or_else(|| FitYparamError::Numerical("exact Y-to-S LFT has singular I+z0D".to_owned()))?;
    let zc = mat_scale(&c, Complex::new(z0, 0.0));
    let bf = mat_mul_rect(&b, state, n, &f, n);
    let b_f_zc = mat_mul_rect(&bf, state, n, &zc, state);
    let asys = mat_sub(&a, &b_f_zc);
    let i_minus = mat_add_identity(&mat_scale(&d, Complex::new(z0, 0.0)), n, -1.0);
    let fc = mat_mul_rect(&f, n, n, &zc, state);
    let cs = mat_sub(
        &mat_scale(&zc, Complex::new(-1.0, 0.0)),
        &mat_mul_rect(&i_minus, n, n, &fc, state),
    );
    let ds = mat_mul(&i_minus, &f, n);
    let am = Mat::from_fn(dim, dim, |r, col| asys[r * dim + col]);
    let eigen = am
        .eigen()
        .map_err(|e| FitYparamError::Numerical(format!("exact Y-to-S eigensolve failed: {e:?}")))?;
    let u = eigen.U();
    let inverse = u.to_owned().partial_piv_lu().inverse();
    let eigenvalues = eigen
        .S()
        .column_vector()
        .iter()
        .copied()
        .collect::<Vec<_>>();
    let mut modes = Vec::<(Complex, Vec<Complex>)>::new();
    let bs = bf;
    for (k, pole) in eigenvalues.into_iter().enumerate() {
        let tol = 1e-8 * pole.norm().max(1.0);
        if pole.re >= -tol {
            return Err(FitYparamError::Numerical(
                "exact Y-to-S LFT produced an unstable pole".to_owned(),
            ));
        }
        let mut row = vec![Complex::new(0.0, 0.0); count];
        for output in 0..n {
            for input in 0..n {
                let left = (0..dim)
                    .map(|q| cs[output * dim + q] * u[(q, k)])
                    .sum::<Complex>();
                let right = (0..dim)
                    .map(|q| inverse[(k, q)] * bs[q * n + input])
                    .sum::<Complex>();
                row[output * n + input] = left * right;
            }
        }
        modes.push((
            Complex::new(pole.re, if pole.im.abs() <= tol { 0.0 } else { pole.im }),
            row,
        ));
    }
    let mut poles = Vec::new();
    let mut residues = Vec::new();
    let mut used = vec![false; modes.len()];
    for index in 0..modes.len() {
        if used[index] || modes[index].0.im < 0.0 {
            continue;
        }
        used[index] = true;
        let (pole, mut row) = modes[index].clone();
        if pole.im == 0.0 {
            for value in &mut row {
                value.im = 0.0;
            }
        } else {
            let partner = (0..modes.len()).find(|candidate| {
                !used[*candidate]
                    && (modes[*candidate].0 - pole.conj()).norm() <= 1e-7 * pole.norm().max(1.0)
            });
            let Some(partner) = partner else {
                return Err(FitYparamError::Numerical(
                    "exact Y-to-S LFT produced an unpaired complex pole".to_owned(),
                ));
            };
            used[partner] = true;
            for (response, value) in row.iter_mut().enumerate() {
                *value = (*value + modes[partner].1[response].conj()) * Complex::new(0.5, 0.0);
            }
        }
        poles.push(pole);
        residues.push(row);
    }
    if ds.iter().any(|x| x.im.abs() > 1e-7 * x.re.abs().max(1.0)) {
        return Err(FitYparamError::Unsupported(
            "exact Y-to-S feedthrough is not real-RFM compatible".to_owned(),
        ));
    }
    let residue_matrix = (0..count)
        .map(|response| residues.iter().map(|row| row[response]).collect::<Vec<_>>())
        .collect::<Vec<_>>();
    Ok(RfmModel {
        version: 200600,
        nports: n,
        matrix_type: "S".to_owned(),
        z0,
        poles,
        residues: residue_matrix,
        constant: ds,
    })
}

const KYP_MARGIN: f64 = 1.0e-8;
const KYP_MAX_RELATIVE_CORRECTION: f64 = 0.05;
const KYP_TOLERANCE: f64 = 1.0e-8;

#[derive(Clone, Copy)]
enum KypPoleBlock {
    Real { pole: usize, offset: usize },
    Complex { pole: usize, offset: usize },
}

#[derive(Clone)]
struct KypRealStateSpace {
    a: Vec<f64>,
    b: Vec<f64>,
    c: Vec<f64>,
    d: Vec<f64>,
    states: usize,
    ports: usize,
    frequency_scale_hz: f64,
    blocks: Vec<KypPoleBlock>,
}

fn real_matrix_inverse(value: &[f64], n: usize) -> Option<Vec<f64>> {
    if value.len() != n * n {
        return None;
    }
    let mut augmented = vec![0.0; n * 2 * n];
    for row in 0..n {
        for column in 0..n {
            augmented[row * 2 * n + column] = value[row * n + column];
            augmented[row * 2 * n + n + column] = (row == column) as u8 as f64;
        }
    }
    for column in 0..n {
        let pivot = (column..n).max_by(|left, right| {
            augmented[left * 2 * n + column]
                .abs()
                .total_cmp(&augmented[right * 2 * n + column].abs())
        })?;
        let pivot_value = augmented[pivot * 2 * n + column];
        if !pivot_value.is_finite() || pivot_value.abs() <= f64::MIN_POSITIVE {
            return None;
        }
        if pivot != column {
            for index in 0..2 * n {
                augmented.swap(pivot * 2 * n + index, column * 2 * n + index);
            }
        }
        for index in 0..2 * n {
            augmented[column * 2 * n + index] /= pivot_value;
        }
        let pivot_row = augmented[column * 2 * n..(column + 1) * 2 * n].to_vec();
        for row in 0..n {
            if row == column {
                continue;
            }
            let factor = augmented[row * 2 * n + column];
            for index in 0..2 * n {
                augmented[row * 2 * n + index] -= factor * pivot_row[index];
            }
        }
    }
    let mut inverse = vec![0.0; n * n];
    for row in 0..n {
        for column in 0..n {
            inverse[row * n + column] = augmented[row * 2 * n + n + column];
        }
    }
    Some(inverse)
}

fn real_min_eigenvalue(value: &[f64], n: usize) -> Result<f64, FitYparamError> {
    let matrix = Mat::from_fn(n, n, |row, column| {
        0.5 * (value[row * n + column] + value[column * n + row])
    });
    matrix
        .self_adjoint_eigenvalues(Side::Lower)
        .map_err(|error| {
            FitYparamError::Numerical(format!("real KYP eigensolve failed: {error:?}"))
        })?
        .into_iter()
        .reduce(f64::min)
        .ok_or_else(|| FitYparamError::Numerical("empty KYP matrix".to_owned()))
}

fn real_max_eigenvalue(value: &[f64], n: usize) -> Result<f64, FitYparamError> {
    let matrix = Mat::from_fn(n, n, |row, column| {
        0.5 * (value[row * n + column] + value[column * n + row])
    });
    matrix
        .self_adjoint_eigenvalues(Side::Lower)
        .map_err(|error| {
            FitYparamError::Numerical(format!("real KYP eigensolve failed: {error:?}"))
        })?
        .into_iter()
        .reduce(f64::max)
        .ok_or_else(|| FitYparamError::Numerical("empty KYP matrix".to_owned()))
}

fn real_matrix_transpose(value: &[f64], rows: usize, columns: usize) -> Vec<f64> {
    (0..columns)
        .flat_map(|column| (0..rows).map(move |row| value[row * columns + column]))
        .collect()
}

fn real_matrix_mul(
    left: &[f64],
    left_rows: usize,
    left_columns: usize,
    right: &[f64],
    right_columns: usize,
) -> Vec<f64> {
    (0..left_rows)
        .flat_map(|row| {
            (0..right_columns).map(move |column| {
                (0..left_columns)
                    .map(|inner| {
                        left[row * left_columns + inner] * right[inner * right_columns + column]
                    })
                    .sum()
            })
        })
        .collect()
}

fn kyp_real_state_space(model: &RationalFitModel) -> Result<KypRealStateSpace, FitYparamError> {
    if model
        .proportional
        .iter()
        .any(|value| value.norm() > 1.0e-12)
    {
        return Err(FitYparamError::Unsupported(
            "KYP exact delivery requires a proper Y model".to_owned(),
        ));
    }
    if model.ports == 0 || model.constant.len() != model.ports * model.ports {
        return Err(FitYparamError::Numerical(
            "KYP model dimensions are invalid".to_owned(),
        ));
    }
    if !model.frequency_scale_hz.is_finite() || model.frequency_scale_hz <= 0.0 {
        return Err(FitYparamError::Numerical(
            "KYP model frequency scale is invalid".to_owned(),
        ));
    }
    let n = model.ports;
    let mut states = 0usize;
    let mut blocks = Vec::new();
    for (pole_index, pole) in model.poles.iter().copied().enumerate() {
        if !pole.re.is_finite() || pole.re >= 0.0 {
            return Err(FitYparamError::Unsupported(
                "KYP exact delivery requires stable poles".to_owned(),
            ));
        }
        if pole.im.abs() <= 1.0e-12 {
            blocks.push(KypPoleBlock::Real {
                pole: pole_index,
                offset: states,
            });
            states = states.saturating_add(n);
        } else if pole.im > 0.0 {
            let partner = (pole_index + 1..model.poles.len()).find(|candidate| {
                (model.poles[*candidate] - pole.conj()).norm() <= 1.0e-9 * pole.norm().max(1.0)
            });
            if partner.is_none() {
                return Err(FitYparamError::Unsupported(
                    "KYP exact delivery requires conjugate pole pairs".to_owned(),
                ));
            }
            blocks.push(KypPoleBlock::Complex {
                pole: pole_index,
                offset: states,
            });
            states = states.saturating_add(2 * n);
        }
    }
    if states > MAX_KYP_STATES {
        return Err(FitYparamError::Unsupported(format!(
            "KYP state budget exceeded: {states} > {MAX_KYP_STATES}"
        )));
    }
    let mut a = vec![0.0; states * states];
    let mut b = vec![0.0; states * n];
    let mut c = vec![0.0; n * states];
    let scale = model.frequency_scale_hz;
    for block in &blocks {
        match *block {
            KypPoleBlock::Real { pole, offset } => {
                let value = model.poles[pole];
                for input in 0..n {
                    a[(offset + input) * states + offset + input] = value.re * scale;
                    b[(offset + input) * n + input] = 1.0;
                    for output in 0..n {
                        let residue = model.residues[pole][output * n + input];
                        if residue.im.abs() > KYP_TOLERANCE * residue.re.abs().max(1.0) {
                            return Err(FitYparamError::Unsupported(
                                "KYP exact delivery requires real residues at real poles"
                                    .to_owned(),
                            ));
                        }
                        c[output * states + offset + input] = residue.re * scale;
                    }
                }
            }
            KypPoleBlock::Complex { pole, offset } => {
                let value = model.poles[pole];
                for input in 0..n {
                    let top = offset + input;
                    let bottom = offset + n + input;
                    a[top * states + top] = value.re * scale;
                    a[top * states + bottom] = value.im * scale;
                    a[bottom * states + top] = -value.im * scale;
                    a[bottom * states + bottom] = value.re * scale;
                    b[top * n + input] = 2.0;
                    for output in 0..n {
                        let residue = model.residues[pole][output * n + input];
                        c[output * states + top] = residue.re * scale;
                        c[output * states + bottom] = residue.im * scale;
                    }
                }
            }
        }
    }
    let d = model
        .constant
        .iter()
        .map(|value| value.re)
        .collect::<Vec<_>>();
    Ok(KypRealStateSpace {
        a,
        b,
        c,
        d,
        states,
        ports: n,
        frequency_scale_hz: scale,
        blocks,
    })
}

fn kyp_lmi_matrix(space: &KypRealStateSpace, p: &[f64]) -> Vec<f64> {
    let n = space.states;
    let m = space.ports;
    let a_t = real_matrix_transpose(&space.a, n, n);
    let p_a = real_matrix_mul(p, n, n, &space.a, n);
    let a_t_p = real_matrix_mul(&a_t, n, n, p, n);
    let p_b = real_matrix_mul(p, n, n, &space.b, m);
    let c_t = real_matrix_transpose(&space.c, m, n);
    let b_t_p = real_matrix_mul(&real_matrix_transpose(&space.b, n, m), m, n, p, n);
    let mut result = vec![0.0; (n + m) * (n + m)];
    for row in 0..n {
        for column in 0..n {
            result[row * (n + m) + column] = a_t_p[row * n + column] + p_a[row * n + column];
        }
        for column in 0..m {
            result[row * (n + m) + n + column] = p_b[row * m + column] - c_t[row * m + column];
            result[(n + column) * (n + m) + row] =
                b_t_p[column * n + row] - space.c[column * n + row];
        }
    }
    for row in 0..m {
        for column in 0..m {
            result[(n + row) * (n + m) + n + column] =
                -(space.d[row * m + column] + space.d[column * m + row]);
        }
    }
    result
}

/// Solve the continuous-time KYP feasibility problem through the equivalent
/// Riccati invariant subspace, then audit the original LMI directly. The
/// Hamiltonian is only an algebraic P solver; it is never used as a sampled
/// or feedthrough-only proxy for the certificate.
fn kyp_lmi_feasible_p(
    space: &KypRealStateSpace,
    margin: f64,
) -> Result<(Vec<f64>, f64, f64), FitYparamError> {
    let n = space.states;
    let m = space.ports;
    let d_t = real_matrix_transpose(&space.d, m, m);
    let r = space
        .d
        .iter()
        .zip(&d_t)
        .map(|(left, right)| left + right)
        .collect::<Vec<_>>();
    let r_min = real_min_eigenvalue(&r, m)?;
    if !r_min.is_finite() || r_min <= margin {
        return Err(FitYparamError::Unsupported(format!(
            "KYP feedthrough is not strictly positive: {r_min:.6e}"
        )));
    }
    if n == 0 {
        let kyp_max = real_max_eigenvalue(&r.iter().map(|value| -value).collect::<Vec<_>>(), m)?;
        if kyp_max > -margin {
            return Err(FitYparamError::Unsupported(
                "KYP feedthrough margin is not met".to_owned(),
            ));
        }
        return Ok((Vec::new(), kyp_max, f64::INFINITY));
    }
    let r_inverse = real_matrix_inverse(&r, m).ok_or_else(|| {
        FitYparamError::Unsupported("KYP feedthrough inverse is singular".to_owned())
    })?;
    let b_r = real_matrix_mul(&space.b, n, m, &r_inverse, m);
    let b_r_c = real_matrix_mul(&b_r, n, m, &space.c, n);
    let a_hat = space
        .a
        .iter()
        .zip(b_r_c)
        .map(|(left, right)| left - right)
        .collect::<Vec<_>>();
    let g = real_matrix_mul(&b_r, n, m, &real_matrix_transpose(&space.b, n, m), n);
    let c_t = real_matrix_transpose(&space.c, m, n);
    let c_t_r = real_matrix_mul(&c_t, n, m, &r_inverse, m);
    let q = real_matrix_mul(&c_t_r, n, m, &space.c, n);
    let mut hamiltonian = vec![Complex::new(0.0, 0.0); 2 * n * 2 * n];
    for row in 0..n {
        for column in 0..n {
            hamiltonian[row * 2 * n + column] = Complex::new(a_hat[row * n + column], 0.0);
            hamiltonian[row * 2 * n + n + column] = Complex::new(g[row * n + column], 0.0);
            hamiltonian[(n + row) * 2 * n + column] = Complex::new(-q[row * n + column], 0.0);
            hamiltonian[(n + row) * 2 * n + n + column] =
                Complex::new(-a_hat[column * n + row], 0.0);
        }
    }
    let matrix = Mat::from_fn(2 * n, 2 * n, |row, column| {
        hamiltonian[row * 2 * n + column]
    });
    let eigen = matrix.eigen().map_err(|error| {
        FitYparamError::Numerical(format!("KYP LMI P eigensolve failed: {error:?}"))
    })?;
    let values = eigen
        .S()
        .column_vector()
        .iter()
        .copied()
        .collect::<Vec<_>>();
    let stable = values
        .iter()
        .enumerate()
        .filter(|(_, value)| value.re < -KYP_TOLERANCE * value.norm().max(1.0))
        .map(|(index, _)| index)
        .collect::<Vec<_>>();
    if stable.len() != n {
        return Err(FitYparamError::Unsupported(format!(
            "KYP Riccati pencil has {} stable modes; expected {n}",
            stable.len()
        )));
    }
    let u = eigen.U();
    let v1 = stable
        .iter()
        .flat_map(|column| (0..n).map(move |row| u[(row, *column)]))
        .collect::<Vec<_>>();
    let v2 = stable
        .iter()
        .flat_map(|column| (n..2 * n).map(move |row| u[(row, *column)]))
        .collect::<Vec<_>>();
    let v1_inverse = mat_inverse(&v1, n).ok_or_else(|| {
        FitYparamError::Unsupported("KYP stable invariant subspace is singular".to_owned())
    })?;
    let mut p_complex = vec![Complex::new(0.0, 0.0); n * n];
    for row in 0..n {
        for column in 0..n {
            p_complex[row * n + column] = (0..n)
                .map(|inner| v2[row * n + inner] * v1_inverse[inner * n + column])
                .sum();
        }
    }
    let p_scale = p_complex
        .iter()
        .map(|value| value.norm())
        .fold(1.0, f64::max);
    if p_complex
        .iter()
        .any(|value| !value.re.is_finite() || value.im.abs() > 1.0e-5 * p_scale)
    {
        return Err(FitYparamError::Unsupported(
            "KYP invariant-subspace P is not real".to_owned(),
        ));
    }
    let mut base = p_complex.iter().map(|value| value.re).collect::<Vec<_>>();
    for row in 0..n {
        for column in 0..n {
            base[row * n + column] = 0.5 * (base[row * n + column] + base[column * n + row]);
        }
    }
    let mut candidates = Vec::new();
    for factor in [0.05, 0.1, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 4.0, 8.0] {
        let mut candidate = base.iter().map(|value| value * factor).collect::<Vec<_>>();
        for index in 0..n {
            candidate[index * n + index] += margin * factor;
        }
        candidates.push(candidate);
    }
    candidates.push(
        (0..n * n)
            .map(|index| (index / n == index % n) as u8 as f64)
            .collect(),
    );
    let mut best = None;
    for candidate in candidates {
        let p_min = real_min_eigenvalue(&candidate, n)?;
        let kyp = kyp_lmi_matrix(space, &candidate);
        let kyp_max = real_max_eigenvalue(&kyp, n + m)?;
        if p_min >= margin * 0.5 && kyp_max <= -margin * 0.5 {
            best = Some((candidate, kyp_max, p_min));
            break;
        }
    }
    best.ok_or_else(|| {
        FitYparamError::Unsupported(
            "KYP invariant-subspace P did not satisfy the strict LMI".to_owned(),
        )
    })
}

fn kyp_correction_norm(space: &KypRealStateSpace, baseline: &KypRealStateSpace) -> f64 {
    let c_delta = space
        .c
        .iter()
        .zip(&baseline.c)
        .map(|(left, right)| (left - right).powi(2))
        .sum::<f64>();
    let d_delta = space
        .d
        .iter()
        .zip(&baseline.d)
        .map(|(left, right)| (left - right).powi(2))
        .sum::<f64>();
    (c_delta + d_delta).sqrt()
}

fn apply_kyp_realization(model: &mut RationalFitModel, space: &KypRealStateSpace) {
    let scale = space.frequency_scale_hz;
    for (row, value) in model.constant.iter_mut().enumerate() {
        value.re = space.d[row];
        value.im = 0.0;
    }
    for block in &space.blocks {
        match *block {
            KypPoleBlock::Real { pole, offset } => {
                for output in 0..space.ports {
                    for input in 0..space.ports {
                        model.residues[pole][output * space.ports + input] = Complex::new(
                            space.c[output * space.states + offset + input] / scale,
                            0.0,
                        );
                    }
                }
            }
            KypPoleBlock::Complex { pole, offset } => {
                for output in 0..space.ports {
                    for input in 0..space.ports {
                        let real = space.c[output * space.states + offset + input] / scale;
                        let imag =
                            space.c[output * space.states + offset + space.ports + input] / scale;
                        model.residues[pole][output * space.ports + input] =
                            Complex::new(real, imag);
                        if let Some(partner) = (0..model.poles.len()).find(|candidate| {
                            *candidate != pole
                                && (model.poles[*candidate] - model.poles[pole].conj()).norm()
                                    <= 1.0e-9 * model.poles[pole].norm().max(1.0)
                        }) {
                            model.residues[partner][output * space.ports + input] =
                                Complex::new(real, -imag);
                        }
                    }
                }
            }
        }
    }
}

fn enforce_y_positive_real_kyp(
    model: &mut RationalFitModel,
    z0: f64,
    frequencies: &[f64],
) -> Result<Value, FitYparamError> {
    let baseline = kyp_real_state_space(model)?;
    let baseline_norm = (baseline
        .c
        .iter()
        .chain(&baseline.d)
        .map(|value| value * value)
        .sum::<f64>())
    .sqrt()
    .max(1.0);
    let source = baseline.clone();
    let try_candidate = |space: &KypRealStateSpace| -> Option<(f64, f64)> {
        kyp_lmi_feasible_p(space, KYP_MARGIN)
            .ok()
            .map(|(_, kyp_max, p_min)| (kyp_max, p_min))
    };
    if let Some((kyp_max, p_min)) = try_candidate(&source) {
        return Ok(json!({
            "solver": "native-kyp-lmi",
            "status": "feasible",
            "p_solver": "continuous_time_riccati_invariant_subspace",
            "certificate_scope": "full_continuous_frequency_kyp_lmi",
            "state_count": source.states,
            "kyp_max_eigenvalue": kyp_max,
            "p_min_eigenvalue": p_min,
            "correction_frobenius_norm": 0.0,
            "correction_relative": 0.0,
            "lmi": "[A^T P+PA, PB-C^T; B^T P-C, -(D+D^T)] << -margin I; P >> margin I",
            "margin": KYP_MARGIN,
            "frequency_samples": frequencies.len(),
            "z0_ohms": z0,
        }));
    }
    let d_norm = source.d.iter().map(|value| value.abs()).fold(1.0, f64::max);
    let c_norm = source.c.iter().map(|value| value.abs()).fold(1.0, f64::max);
    let mut safe_alpha = (d_norm + c_norm * c_norm + 1.0).max(1.0);
    let safe = loop {
        let mut candidate = source.clone();
        for row in 0..candidate.ports {
            candidate.d[row * candidate.ports + row] += safe_alpha;
        }
        candidate.c.fill(0.0);
        if try_candidate(&candidate).is_some() {
            break candidate;
        }
        safe_alpha *= 10.0;
        if !safe_alpha.is_finite() || safe_alpha > 1.0e12 {
            return Err(FitYparamError::Unsupported(
                "KYP LMI could not construct a strict feasible starting point".to_owned(),
            ));
        }
    };
    let mut best = safe.clone();
    let mut best_t = 0.0;
    for step in 1..=64 {
        let t = step as f64 / 64.0;
        let mut candidate = safe.clone();
        for (index, value) in candidate.c.iter_mut().enumerate() {
            *value = safe.c[index] * (1.0 - t) + source.c[index] * t;
        }
        for (index, value) in candidate.d.iter_mut().enumerate() {
            *value = safe.d[index] * (1.0 - t) + source.d[index] * t;
        }
        if try_candidate(&candidate).is_some() {
            best = candidate;
            best_t = t;
        }
    }
    let correction = kyp_correction_norm(&best, &source);
    if correction > KYP_MAX_RELATIVE_CORRECTION * baseline_norm {
        return Err(FitYparamError::Unsupported(format!(
            "KYP LMI requires excessive C/D correction ({:.6e} relative; limit {:.6e})",
            correction / baseline_norm,
            KYP_MAX_RELATIVE_CORRECTION
        )));
    }
    let (kyp_max, p_min) = try_candidate(&best).ok_or_else(|| {
        FitYparamError::Unsupported("KYP corrected model failed strict LMI audit".to_owned())
    })?;
    apply_kyp_realization(model, &best);
    Ok(json!({
        "solver": "native-kyp-lmi",
        "status": "feasible_after_bounded_cd_correction",
        "p_solver": "continuous_time_riccati_invariant_subspace",
        "certificate_scope": "full_continuous_frequency_kyp_lmi",
        "state_count": best.states,
        "kyp_max_eigenvalue": kyp_max,
        "p_min_eigenvalue": p_min,
        "correction_frobenius_norm": correction,
        "correction_relative": correction / baseline_norm,
        "correction_path_fraction": best_t,
        "lmi": "[A^T P+PA, PB-C^T; B^T P-C, -(D+D^T)] << -margin I; P >> margin I",
        "margin": KYP_MARGIN,
        "frequency_samples": frequencies.len(),
        "z0_ohms": z0,
    }))
}

pub fn fit_yparam(request: &FitYparamRequest) -> Result<FitYparamResult, FitYparamError> {
    validate_options(&request.touchstone, &request.options)?;
    let network = read_multiport_touchstone(&request.touchstone)?;
    let n = network.ports();
    let mut y_samples = Vec::with_capacity(network.sample_count());
    let mut condition_max: f64 = 0.0;
    for sample in network.samples() {
        let (y, condition) = convert_s_to_y(
            sample,
            n,
            network.reference_impedance(),
            request.options.conversion_condition_limit,
        )?;
        condition_max = condition_max.max(condition);
        y_samples.push(y);
    }
    let y_network = TouchstoneNetwork::from_samples(
        network.frequencies_hz().to_vec(),
        y_samples.clone(),
        n,
        network.reference_impedance(),
    )
    .map_err(|e| FitYparamError::Input(e.to_string()))?;
    let initial_order = request.options.n_poles_real + request.options.n_poles_cmplx * 2;
    if initial_order == 0 || request.options.max_order < initial_order {
        return Err(FitYparamError::InvalidOption(format!(
            "max_order must be at least initial order {initial_order}"
        )));
    }
    let fit_options = FitSparamOptions {
        rms_target: Some(request.options.max_y_rms_siemens.unwrap_or(f64::MAX)),
        passivity: Some(PassivityPolicy::Off),
        fit_proportional: request.options.fit_proportional,
        fit_iterations: request.options.fit_iterations,
        enforce_dc: true,
        ..FitSparamOptions::default()
    };
    let wants_exact = request.options.exact_s_rfm.is_some()
        || request.options.exact_s_touchstone.is_some()
        || request.options.exact_s_rfm_wrapper.is_some();
    let mut best: Option<(RationalFitModel, f64, usize, bool, f64)> = None;
    let mut trials = Vec::new();
    let mut orders = (initial_order..=request.options.max_order)
        .step_by(request.options.order_step)
        .collect::<Vec<_>>();
    if orders.last() != Some(&request.options.max_order) {
        orders.push(request.options.max_order);
    }
    for order in orders {
        let (real, complex_pairs) = pole_counts_for_order(request.options.n_poles_real, order);
        let (poles, mut basis) = initial_poles(
            y_network.frequencies_hz(),
            real,
            complex_pairs,
            &request.options.pole_spacing,
            y_network.frequencies_hz().iter().sum::<f64>() / y_network.sample_count() as f64,
        )
        .map_err(|e| FitYparamError::Numerical(e.to_string()))?;
        basis.push(BasisKind::Constant);
        if request.options.fit_proportional {
            basis.push(BasisKind::Proportional);
        }
        let (mut model, relocation) = fit_native_vector_fitting(
            &y_network,
            &poles,
            &basis,
            &fit_options,
            request.options.fit_iterations,
        )
        .map_err(|e| FitYparamError::Numerical(e.to_string()))?;
        enforce_real_rational_coefficients(&mut model);
        let exact_kyp = if wants_exact {
            enforce_y_positive_real_kyp(
                &mut model,
                network.reference_impedance(),
                network.frequencies_hz(),
            )
        } else {
            Ok(json!(null))
        };
        let exact_delivery_gate = if wants_exact {
            exact_kyp.is_ok() && fit_to_rfm(&model, network.reference_impedance()).is_ok()
        } else {
            true
        };
        let (rms, mean_rms) = rms_metrics(&network, &model, &y_samples);
        let (min, violations) = passivity_metrics(
            &model,
            network.frequencies_hz(),
            request.options.passivity,
            request.options.passivity_epsilon,
        )?;
        let target = request
            .options
            .max_y_rms_siemens
            .is_none_or(|t| mean_rms <= t)
            && (request.options.passivity == PassivityPolicy::Off || violations == 0)
            && exact_delivery_gate;
        trials.push(json!({"requested_order":order,"effective_order":model.order(),"y_rms_siemens":rms,"y_mean_rms_siemens":mean_rms,"pole_relocation_iterations":relocation.iterations,"passivity_min_eigenvalue":min,"passivity_violation_count":violations,"exact_delivery_gate":exact_delivery_gate,"kyp_certificate":exact_kyp.as_ref().ok(),"target_met":target,"rejection_reason":if !exact_delivery_gate { Some("exact_y_to_s_kyp_gate_failed") } else if request.options.passivity != PassivityPolicy::Off && violations != 0 { Some("y_not_positive_real") } else if request.options.max_y_rms_siemens.is_some_and(|t| mean_rms > t) { Some("y_rms_target_not_met") } else { None }}));
        let replace = best
            .as_ref()
            .is_none_or(|(_, old, old_v, old_exact, old_mean)| {
                (!exact_delivery_gate, violations, mean_rms, rms)
                    < (!*old_exact, *old_v, *old_mean, *old)
            });
        if replace {
            best = Some((model, rms, violations, exact_delivery_gate, mean_rms));
        }
        if target {
            break;
        }
    }
    let (mut model, rms, violations, exact_delivery_gate, mean_rms) =
        best.ok_or_else(|| FitYparamError::Numerical("no finite Y model was produced".to_owned()))?;
    let target_met = request
        .options
        .max_y_rms_siemens
        .is_none_or(|t| mean_rms <= t)
        && (request.options.passivity == PassivityPolicy::Off || violations == 0)
        && exact_delivery_gate;
    let selected_kyp = if wants_exact {
        Some(enforce_y_positive_real_kyp(
            &mut model,
            network.reference_impedance(),
            network.frequencies_hz(),
        )?)
    } else {
        None
    };
    let (output, report, log, derived, html) = output_paths(&request.touchstone, &request.options);
    write_y_subcircuit(&output, &model, &request.options.subckt_name)?;
    if let Some(path) = derived.as_deref() {
        write_s_touchstone(
            path,
            network.frequencies_hz(),
            &model,
            network.reference_impedance(),
        )?;
    }
    let exact = if wants_exact {
        Some(fit_to_rfm(&model, network.reference_impedance())?)
    } else {
        None
    };
    let exact_touchstone = request.options.exact_s_touchstone.clone().or_else(|| {
        request
            .options
            .exact_s_rfm
            .as_ref()
            .map(|p| p.with_extension(format!("s{n}p")))
    });
    if let Some(exact) = exact.as_ref() {
        if let Some(path) = request.options.exact_s_rfm.as_deref() {
            write_cadence_rfm(path, exact).map_err(|e| FitYparamError::Output(e.to_string()))?;
        }
        if let Some(path) = exact_touchstone.as_deref() {
            let mut out = format!("# Hz S RI R {:.17e}\n", network.reference_impedance());
            for f in network.frequencies_hz() {
                out.push_str(&format!("{f:.17e}"));
                let values = exact.evaluate_s(*f);
                for column in 0..n {
                    for row in 0..n {
                        let v = values[row * n + column];
                        out.push_str(&format!(" {:.17e} {:.17e}", v.re, v.im));
                    }
                }
                out.push('\n');
            }
            write_text(path, &out)?;
        }
        if let Some(path) = request.options.exact_s_rfm_wrapper.as_deref() {
            let rfm = request
                .options
                .exact_s_rfm
                .as_ref()
                .expect("validated exact wrapper dependency");
            write_cadence_rfm_wrapper(
                path,
                rfm,
                exact.nports,
                Some(&format!("{}_exact_s", request.options.subckt_name)),
            )
            .map_err(|e| FitYparamError::Output(e.to_string()))?;
        }
    }
    let passivity_min = (request.options.passivity != PassivityPolicy::Off).then_some(
        passivity_metrics(
            &model,
            network.frequencies_hz(),
            request.options.passivity,
            request.options.passivity_epsilon,
        )?
        .0,
    );
    let exact_y_to_s = wants_exact.then(|| {
        json!({
            "method": "state-space rational LFT; no sampled S refit",
            "delivery_gate": "proper_rational_real_stable_model",
            "positive_real_certificate": "native_kyp_lmi",
            "continuous_kyp_certificate": selected_kyp,
            "external_boundary": null,
            "rfm_path": request.options.exact_s_rfm,
            "touchstone_path": exact_touchstone,
            "wrapper_path": request.options.exact_s_rfm_wrapper,
        })
    });
    let payload = json!({"schema":"sipi.agent-spice-as-03-fit-yparam-result.v2","workflow":WORKFLOW_NAME,"upstream_commit":UPSTREAM_COMMIT,"upstream_tree":UPSTREAM_TREE,"ports":n,"frequency_points":network.sample_count(),"reference_impedance_ohms":network.reference_impedance(),"selected_order":model.order(),"y_rms_siemens":rms,"y_mean_rms_siemens":mean_rms,"target_metric":"mean_rms = sqrt(sum(element_rms^2)) / nports","target_met":target_met,"conversion_condition_max":condition_max,"passivity":{"policy":request.options.passivity.as_str(),"min_eigenvalue":passivity_min,"violation_count":(request.options.passivity!=PassivityPolicy::Off).then_some(violations),"criterion":"lambda_min((Y+Y^H)/2) >= -epsilon","enforcement":"sampled_check"},"trials":trials,"exact_y_to_s":exact_y_to_s,"artifacts":{"output":output,"report":report,"derived_s_touchstone":derived,"html_report":html,"exact_s_rfm":request.options.exact_s_rfm,"exact_s_touchstone":exact_touchstone,"exact_s_rfm_wrapper":request.options.exact_s_rfm_wrapper,"log":log},"portable_branches":["nport","auto-order","sampled-positive-real","proper-rational-y-to-s-lft","html-report","native-kyp-positive-real-lmi-gate"],"external_runtime_boundary":Vec::<&str>::new()});
    write_text(
        &report,
        &(serde_json::to_string_pretty(&payload)
            .map_err(|e| FitYparamError::Output(e.to_string()))?
            + "\n"),
    )?;
    if let Some(path) = html.as_deref() {
        html_report(path, &payload)?;
    }
    write_text(
        &log,
        &trials.iter().map(|v| format!("{v}\n")).collect::<String>(),
    )?;
    Ok(FitYparamResult {
        target_met,
        selected_order: model.order(),
        y_rms_siemens: rms,
        y_mean_rms_siemens: mean_rms,
        conversion_condition_max: condition_max,
        passivity_min_eigenvalue: passivity_min,
        passivity_violation_count: (request.options.passivity != PassivityPolicy::Off)
            .then_some(violations),
        model,
        report,
        output,
        derived_s_touchstone: derived,
        html_report: html,
        exact_s_rfm: request.options.exact_s_rfm.clone(),
        exact_s_touchstone: exact_touchstone,
        exact_s_rfm_wrapper: request.options.exact_s_rfm_wrapper.clone(),
        log,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn matrix_round_trip_is_multiport() {
        let s = vec![
            Complex::new(0.1, 0.),
            Complex::new(0.02, 0.),
            Complex::new(0.03, 0.),
            Complex::new(0.2, 0.),
        ];
        let (y, _) = convert_s_to_y(&s, 2, 50., 1e12).unwrap();
        let recovered = y_to_s(&y, 2, 50.).unwrap();
        assert!(
            s.iter()
                .zip(recovered)
                .all(|(a, b)| (*a - b).norm() < 1e-12)
        );
    }

    #[test]
    fn fixed_line_fixture_s_to_y_regression_checkpoint() {
        let s = vec![
            Complex::new(0.01, 0.0),
            Complex::new(0.8, 0.0),
            Complex::new(0.8, 0.0),
            Complex::new(0.01, 0.0),
        ];
        let (y, condition) = convert_s_to_y(&s, 2, 50.0, 1.0e12).unwrap();
        assert!(condition.is_finite());
        assert!((y[0].re - 0.0862878189950013).abs() < 1.0e-14);
        assert!((y[1].re + 0.0841883714811892).abs() < 1.0e-14);
        assert!((y[2].re + 0.0841883714811892).abs() < 1.0e-14);
        assert!((y[3].re - 0.0862878189950013).abs() < 1.0e-14);
    }

    #[test]
    fn power_wave_solve_has_stable_fixed_line_checkpoint() {
        let s = vec![
            Complex::new(0.01, 0.0),
            Complex::new(0.8, 0.0),
            Complex::new(0.8, 0.0),
            Complex::new(0.01, 0.0),
        ];
        let (y, condition) = convert_s_to_y(&s, 2, 50.0, 1.0e12).unwrap();
        assert!(condition.is_finite());
        assert_eq!(y[0].re.to_bits(), 0x3fb6_16f5_60a0_6f4a);
        assert_eq!(y[1].re.to_bits(), 0xbfb5_8d5e_7e37_17c4);
        assert_eq!(y[2].re.to_bits(), 0xbfb5_8d5e_7e37_17c4);
        assert_eq!(y[3].re.to_bits(), 0x3fb6_16f5_60a0_6f49);
    }

    #[test]
    fn power_wave_solve_preserves_complex_two_port_direction() {
        let s = vec![
            Complex::new(0.1, 0.02),
            Complex::new(0.03, -0.04),
            Complex::new(0.07, 0.05),
            Complex::new(-0.08, 0.01),
        ];
        // scikit-rf v2.0.1 s2y(..., s_def="power") checkpoint.
        let expected = [
            Complex::new(0.016497023844251828, -0.000_714_953_490_144_419_1),
            Complex::new(-0.0011413990243110358, 0.0016225473355625177),
            Complex::new(-0.0028364373781399723, -0.0018983044283924807),
            Complex::new(0.023647463899561454, -0.000_535_851_088_336_346_8),
        ];
        let (actual, condition) = convert_s_to_y(&s, 2, 50.0, 1.0e12).unwrap();
        assert!(condition < 2.0);
        assert!(
            actual
                .iter()
                .zip(expected)
                .all(|(left, right)| (*left - right).norm() < 1.0e-17)
        );
    }

    #[test]
    fn power_wave_solve_preserves_nport_row_column_direction() {
        let s = vec![
            Complex::new(0.05, 0.01),
            Complex::new(0.02, -0.03),
            Complex::new(-0.01, 0.04),
            Complex::new(0.07, 0.02),
            Complex::new(-0.04, 0.01),
            Complex::new(0.03, -0.02),
            Complex::new(-0.02, 0.01),
            Complex::new(0.06, 0.05),
            Complex::new(0.08, -0.03),
        ];
        // scikit-rf v2.0.1 s2y(..., s_def="power") checkpoint.
        let expected = [
            Complex::new(0.018166332032645744, -0.00046389054974381384),
            Complex::new(-0.0008668313453335766, 0.001282945590378771),
            Complex::new(0.000_377_061_201_475_975_9, -0.0014590790234972437),
            Complex::new(-0.0028224709621312376, -0.000_709_314_748_825_646),
            Complex::new(0.021863720420335974, -0.0004987635301543018),
            Complex::new(-0.0012297418170710939, 0.000_852_917_361_848_341_2),
            Complex::new(0.000_831_143_353_744_531_1, -0.00016881888673416406),
            Complex::new(-0.002_299_067_993_686_986, -0.0019425046516270731),
            Complex::new(0.017_110_263_411_363_31, 0.0010098775546285635),
        ];
        let (actual, condition) = convert_s_to_y(&s, 3, 50.0, 1.0e12).unwrap();
        assert!(condition < 2.0);
        assert!(
            actual
                .iter()
                .zip(expected)
                .all(|(left, right)| (*left - right).norm() < 1.0e-17)
        );
    }

    #[test]
    fn power_wave_solve_rejects_singular_and_over_limit_inputs() {
        let singular = vec![
            Complex::new(-1.0, 0.0),
            Complex::new(0.0, 0.0),
            Complex::new(0.0, 0.0),
            Complex::new(-1.0, 0.0),
        ];
        assert!(matches!(
            convert_s_to_y(&singular, 2, 50.0, 1.0e12),
            Err(FitYparamError::Numerical(message)) if message.contains("condition estimate")
        ));

        let conditioned = vec![
            Complex::new(0.1, 0.02),
            Complex::new(0.03, -0.04),
            Complex::new(0.07, 0.05),
            Complex::new(-0.08, 0.01),
        ];
        assert!(matches!(
            convert_s_to_y(&conditioned, 2, 50.0, 1.1),
            Err(FitYparamError::Numerical(message)) if message.contains("exceeds")
        ));
    }

    #[test]
    fn exact_rfm_requires_no_proportional() {
        let o = FitYparamOptions {
            exact_s_rfm: Some(PathBuf::from("x.rfm")),
            ..FitYparamOptions::default()
        };
        assert!(matches!(
            FitYparamRequest::new("x.s2p", o),
            Err(FitYparamError::Unsupported(_))
        ));
    }

    #[test]
    fn exact_lft_matches_bilinear_one_port_response() {
        let model = RationalFitModel {
            poles: vec![Complex::new(-2.0, 0.0)],
            residues: vec![vec![Complex::new(3.0, 0.0)]],
            constant: vec![Complex::new(0.02, 0.0)],
            proportional: vec![Complex::new(0.0, 0.0)],
            ports: 1,
            frequency_scale_hz: 1.0e8,
        };
        let transformed = fit_to_rfm(&model, 50.0).unwrap();
        for frequency in [0.0, 1.0e6, 50.0e6, 500.0e6] {
            let y = model.evaluate(frequency)[0];
            let expected =
                (Complex::new(1.0, 0.0) - 50.0 * y) / (Complex::new(1.0, 0.0) + 50.0 * y);
            let actual = transformed.evaluate_s(frequency)[0];
            assert!(
                (actual - expected).norm() < 1.0e-8,
                "{frequency}: {actual:?} != {expected:?}"
            );
        }
    }
    #[test]
    fn html_escape_is_bounded() {
        assert_eq!(html_escape("<&>"), "&lt;&amp;&gt;");
    }

    #[test]
    fn bounded_loader_accepts_three_port_touchstone() {
        let root = std::env::temp_dir().join(format!("sipi-as03-nport-{}", std::process::id()));
        fs::create_dir_all(&root).unwrap();
        let path = root.join("network.s3p");
        let row = std::iter::repeat_n("0", 18).collect::<Vec<_>>().join(" ");
        fs::write(&path, format!("# GHz S RI R 50\n0.1 {row}\n1.0 {row}\n")).unwrap();
        let network = read_multiport_touchstone(&path).unwrap();
        assert_eq!(network.ports(), 3);
        assert_eq!(network.sample_count(), 2);
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn nport_fit_can_publish_html_and_exact_rfm() {
        let root = std::env::temp_dir().join(format!("sipi-as03-fit-{}", std::process::id()));
        fs::create_dir_all(&root).unwrap();
        let input = root.join("network.s3p");
        let row_low = [
            0.1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.1,
            0.0,
        ]
        .iter()
        .map(ToString::to_string)
        .collect::<Vec<_>>()
        .join(" ");
        let row_high = row_low.replacen("0.1", "0.12", 3);
        fs::write(
            &input,
            format!("# GHz S RI R 50\n0.1 {row_low}\n1.0 {row_high}\n"),
        )
        .unwrap();
        let options = FitYparamOptions {
            n_poles_real: 1,
            n_poles_cmplx: 0,
            max_order: 1,
            order_step: 1,
            fit_proportional: false,
            passivity: PassivityPolicy::Off,
            max_y_rms_siemens: Some(1.0),
            html_report: Some(root.join("fit.html")),
            exact_s_rfm: Some(root.join("exact.rfm")),
            ..FitYparamOptions::default()
        };
        let result = fit_yparam(&FitYparamRequest::new(&input, options).unwrap());
        assert!(result.is_ok(), "{result:?}");
        let result = result.unwrap();
        assert_eq!(result.model.ports, 3);
        assert!(result.html_report.unwrap().is_file());
        assert!(result.exact_s_rfm.unwrap().is_file());
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn complex_pole_residues_emit_separate_real_and_imaginary_paths() {
        let root = std::env::temp_dir().join(format!("sipi-as03-complex-{}", std::process::id()));
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(&root).unwrap();
        let model = RationalFitModel {
            poles: vec![Complex::new(-0.1, 1.0), Complex::new(-0.1, -1.0)],
            residues: vec![vec![Complex::new(2.0, 0.5)], vec![Complex::new(2.0, -0.5)]],
            constant: vec![Complex::new(0.0, 0.0)],
            proportional: vec![Complex::new(0.0, 0.0)],
            ports: 1,
            frequency_scale_hz: 1.0e6,
        };
        let path = root.join("model.sp");
        write_y_subcircuit(&path, &model, "y_model").unwrap();
        let text = fs::read_to_string(path).unwrap();
        assert!(text.contains("Gr0r_0_0"));
        assert!(text.contains("Gr0i_0_0"));
        assert!(text.contains("2.0000000000000000e6"));
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn exact_kyp_gate_rejects_non_positive_real_feedthrough() {
        let model = RationalFitModel {
            poles: Vec::new(),
            residues: Vec::new(),
            constant: vec![Complex::new(-1.0, 0.0)],
            proportional: vec![Complex::new(0.0, 0.0)],
            ports: 1,
            frequency_scale_hz: 1.0,
        };
        let mut model = model;
        assert!(enforce_y_positive_real_kyp(&mut model, 50.0, &[1.0, 2.0]).is_err());
    }

    #[test]
    fn exact_kyp_certificate_contains_audited_p_and_lmi_eigenvalues() {
        let mut model = RationalFitModel {
            poles: vec![Complex::new(-1.0, 0.0)],
            residues: vec![vec![Complex::new(1.0, 0.0)]],
            constant: vec![Complex::new(1.0, 0.0)],
            proportional: vec![Complex::new(0.0, 0.0)],
            ports: 1,
            frequency_scale_hz: 1.0,
        };
        let certificate = enforce_y_positive_real_kyp(&mut model, 50.0, &[1.0, 2.0]).unwrap();
        assert_eq!(certificate["solver"], "native-kyp-lmi");
        assert!(certificate["kyp_max_eigenvalue"].as_f64().unwrap() < -KYP_MARGIN * 0.5);
        assert!(certificate["p_min_eigenvalue"].as_f64().unwrap() >= KYP_MARGIN * 0.5);
        assert_eq!(certificate["correction_frobenius_norm"], 0.0);
    }

    #[test]
    fn exact_kyp_repairs_a_small_cd_violation_before_delivery() {
        let mut model = RationalFitModel {
            poles: vec![Complex::new(-1.0, 0.0)],
            residues: vec![vec![Complex::new(-1.01, 0.0)]],
            constant: vec![Complex::new(1.0, 0.0)],
            proportional: vec![Complex::new(0.0, 0.0)],
            ports: 1,
            frequency_scale_hz: 1.0,
        };
        let certificate = enforce_y_positive_real_kyp(&mut model, 50.0, &[1.0, 2.0]).unwrap();
        assert_eq!(
            certificate["status"],
            "feasible_after_bounded_cd_correction"
        );
        assert!(certificate["correction_relative"].as_f64().unwrap() <= 0.05);
        assert!(model.evaluate(0.0)[0].re >= -1.0e-8);
    }

    #[test]
    fn exact_kyp_gate_rejects_dense_state_budget_before_allocation() {
        let mut model = RationalFitModel {
            poles: (0..MAX_KYP_STATES + 1)
                .map(|index| Complex::new(-1.0 - index as f64, 0.0))
                .collect(),
            residues: (0..MAX_KYP_STATES + 1)
                .map(|_| vec![Complex::new(0.0, 0.0)])
                .collect(),
            constant: vec![Complex::new(0.01, 0.0)],
            proportional: vec![Complex::new(0.0, 0.0)],
            ports: 1,
            frequency_scale_hz: 1.0,
        };
        let error = enforce_y_positive_real_kyp(&mut model, 50.0, &[1.0, 2.0])
            .expect_err("dense exact KYP must fail closed");
        assert!(error.to_string().contains("KYP state budget exceeded"));
    }

    #[test]
    fn passivity_enforce_is_explicitly_rejected_for_y_fit() {
        let options = FitYparamOptions {
            passivity: PassivityPolicy::Enforce,
            ..FitYparamOptions::default()
        };
        assert!(matches!(
            FitYparamRequest::new("input.s2p", options),
            Err(FitYparamError::Unsupported(_))
        ));
    }
}
