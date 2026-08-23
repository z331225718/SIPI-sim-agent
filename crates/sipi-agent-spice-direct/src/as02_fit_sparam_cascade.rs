//! AS-02 bounded direct port for `fit-sparam-cascade`.
//!
//! This module keeps the upstream reachable control flow visible: strict
//! version-1 manifest admission, ordered two-port fits, common frequency
//! intersection, ABCD cascade, singular-value passivity check, and bounded
//! Hamiltonian-band passivity optimization.  The pinned CLI admits only two-port `.s2p` blocks; that
//! upstream admission boundary is preserved rather than inventing n-port
//! cascade semantics here.

use std::collections::HashMap;
use std::fmt::{Display, Formatter};
use std::fs;
use std::path::{Path, PathBuf};

use faer::{Mat, linalg::solvers::DenseSolveCore};
use num_complex::Complex64 as Complex;
use serde_json::{Value, json};

use crate::as06_run_rfm::{RfmModel, write_cadence_rfm, write_cadence_rfm_wrapper};
use crate::fit_sparam::{
    FitSparamOptions, PassivityPolicy, PriorityBand, RationalFitModel, TouchstoneNetwork,
    fit_sparam, read_touchstone, renormalize_network, write_fitted_touchstone,
};

pub const UPSTREAM_COMMIT: &str = "2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5";
pub const UPSTREAM_TREE: &str = "b6bde97128030d6cea0d68b2f0a35d807be8c402";
pub const WORKFLOW_ID: &str = "AS-02";
pub const WORKFLOW_NAME: &str = "fit-sparam-cascade";
const MAX_BLOCKS: usize = 32;
const MAX_SAMPLES: usize = 4096;
const MAX_ARTIFACT_BYTES: usize = 8 * 1024 * 1024;

#[derive(Clone, Debug, PartialEq)]
pub struct CascadeBlockSpec {
    pub name: String,
    pub touchstone: PathBuf,
    pub rms_target: f64,
    pub max_order: usize,
    pub gate_full_band_rms: bool,
}

#[derive(Clone, Debug, PartialEq)]
pub struct FitSparamCascadeOptions {
    pub output_root: PathBuf,
    pub report: Option<PathBuf>,
    pub rms_target: Option<f64>,
    pub max_order: usize,
    pub min_order: usize,
    pub max_order_step: usize,
    pub passivity_epsilon: f64,
    pub cascade_passivity_epsilon: f64,
    pub cascade_rms_target: Option<f64>,
    pub cascade_samples: usize,
    pub reference_impedance: f64,
    pub adjustment_iterations: usize,
    pub minimum_scale: f64,
    pub priority_bands: Vec<PriorityBand>,
    pub outside_band_weight: f64,
    pub gate_full_band_rms: bool,
    pub priority_band_fit_only: bool,
    pub cascade_refit_max_iterations: usize,
}

impl Default for FitSparamCascadeOptions {
    fn default() -> Self {
        Self {
            output_root: PathBuf::from("runs-sparam-cascade"),
            report: None,
            rms_target: None,
            max_order: 100,
            min_order: 1,
            max_order_step: 8,
            passivity_epsilon: 1e-6,
            cascade_passivity_epsilon: 1e-8,
            cascade_rms_target: None,
            cascade_samples: 1001,
            reference_impedance: 50.0,
            adjustment_iterations: 12,
            minimum_scale: 0.8,
            priority_bands: Vec::new(),
            outside_band_weight: 0.1,
            gate_full_band_rms: true,
            priority_band_fit_only: false,
            cascade_refit_max_iterations: 8,
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct FitSparamCascadeRequest {
    pub manifest: PathBuf,
    pub options: FitSparamCascadeOptions,
}

impl FitSparamCascadeRequest {
    pub fn new(
        manifest: impl Into<PathBuf>,
        options: FitSparamCascadeOptions,
    ) -> Result<Self, CascadeError> {
        let manifest = manifest.into();
        validate_options(&manifest, &options)?;
        Ok(Self { manifest, options })
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum CascadeError {
    InvalidManifest(String),
    InvalidOption(String),
    Input(String),
    Numerical(String),
    Output(String),
}

impl Display for CascadeError {
    fn fmt(&self, f: &mut Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::InvalidManifest(value) => write!(f, "invalid cascade manifest: {value}"),
            Self::InvalidOption(value) => write!(f, "invalid cascade option: {value}"),
            Self::Input(value) => write!(f, "cascade input error: {value}"),
            Self::Numerical(value) => write!(f, "cascade numerical error: {value}"),
            Self::Output(value) => write!(f, "cascade output error: {value}"),
        }
    }
}

impl std::error::Error for CascadeError {}

#[derive(Clone, Debug, PartialEq)]
pub struct FitSparamCascadeResult {
    pub status: String,
    pub report: PathBuf,
    pub cascade_touchstone: Option<PathBuf>,
    pub cascade_order: Vec<String>,
    pub max_sigma: Option<f64>,
    pub cascade_rms_error: Option<f64>,
    pub selected_scales: Vec<f64>,
}

#[derive(Clone)]
struct BlockFit {
    spec: CascadeBlockSpec,
    network: TouchstoneNetwork,
    model: RationalFitModel,
    report: PathBuf,
    fitted_touchstone: PathBuf,
    log: PathBuf,
    rfm: PathBuf,
    rfm_wrapper: PathBuf,
    spice: PathBuf,
    html: PathBuf,
    passivity_adjustment: Value,
    pole_relocation_iterations: usize,
}

fn validate_options(
    manifest: &Path,
    options: &FitSparamCascadeOptions,
) -> Result<(), CascadeError> {
    if manifest.as_os_str().is_empty() {
        return Err(CascadeError::InvalidOption(
            "manifest path is empty".to_owned(),
        ));
    }
    if options.max_order == 0 || options.max_order > 100 {
        return Err(CascadeError::InvalidOption(
            "max_order must be in 1..=100".to_owned(),
        ));
    }
    if options.min_order == 0 || options.min_order > options.max_order {
        return Err(CascadeError::InvalidOption(
            "min_order must be between 1 and max_order".to_owned(),
        ));
    }
    if options.max_order_step == 0 || options.max_order_step > 100 {
        return Err(CascadeError::InvalidOption(
            "max_order_step must be bounded and positive".to_owned(),
        ));
    }
    if options.cascade_samples < 2 || options.cascade_samples > MAX_SAMPLES {
        return Err(CascadeError::InvalidOption(format!(
            "cascade_samples must be in 2..={MAX_SAMPLES}"
        )));
    }
    if options.adjustment_iterations == 0 || options.adjustment_iterations > 64 {
        return Err(CascadeError::InvalidOption(
            "adjustment_iterations must be in 1..=64".to_owned(),
        ));
    }
    if options.cascade_refit_max_iterations > 64 {
        return Err(CascadeError::InvalidOption(
            "cascade_refit_max_iterations must be <= 64".to_owned(),
        ));
    }
    if options.priority_band_fit_only && options.priority_bands.is_empty() {
        return Err(CascadeError::InvalidOption(
            "priority_band_fit_only requires at least one priority band".to_owned(),
        ));
    }
    if !options.gate_full_band_rms && !options.priority_band_fit_only {
        return Err(CascadeError::InvalidOption(
            "priority_band_fit_only must be enabled when full-band RMS is non-blocking".to_owned(),
        ));
    }
    if !options.reference_impedance.is_finite() || options.reference_impedance <= 0.0 {
        return Err(CascadeError::InvalidOption(
            "reference_impedance must be finite and positive".to_owned(),
        ));
    }
    if !options.minimum_scale.is_finite()
        || !(0.0..=1.0).contains(&options.minimum_scale)
        || options.minimum_scale == 0.0
    {
        return Err(CascadeError::InvalidOption(
            "minimum_scale must satisfy 0 < value <= 1".to_owned(),
        ));
    }
    if !options.passivity_epsilon.is_finite()
        || options.passivity_epsilon < 0.0
        || !options.cascade_passivity_epsilon.is_finite()
        || options.cascade_passivity_epsilon < 0.0
    {
        return Err(CascadeError::InvalidOption(
            "passivity epsilon values must be finite and non-negative".to_owned(),
        ));
    }
    if let Some(target) = options.rms_target.or(options.cascade_rms_target)
        && (!target.is_finite() || target <= 0.0)
    {
        return Err(CascadeError::InvalidOption(
            "RMS targets must be finite and positive".to_owned(),
        ));
    }
    Ok(())
}

fn manifest_specs(
    path: &Path,
    options: &FitSparamCascadeOptions,
) -> Result<(Vec<CascadeBlockSpec>, Vec<String>), CascadeError> {
    let text = fs::read_to_string(path).map_err(|error| CascadeError::Input(error.to_string()))?;
    if text.len() > MAX_ARTIFACT_BYTES {
        return Err(CascadeError::InvalidManifest(
            "manifest exceeds byte budget".to_owned(),
        ));
    }
    let value: Value = serde_json::from_str(&text)
        .map_err(|error| CascadeError::InvalidManifest(error.to_string()))?;
    let object = value
        .as_object()
        .ok_or_else(|| CascadeError::InvalidManifest("manifest must be an object".to_owned()))?;
    if object
        .keys()
        .any(|key| !matches!(key.as_str(), "version" | "blocks" | "cascade"))
    {
        return Err(CascadeError::InvalidManifest(
            "manifest contains unsupported keys".to_owned(),
        ));
    }
    if object.get("version").and_then(Value::as_u64) != Some(1) {
        return Err(CascadeError::InvalidManifest(
            "manifest version must be 1".to_owned(),
        ));
    }
    let blocks = object
        .get("blocks")
        .and_then(Value::as_array)
        .ok_or_else(|| CascadeError::InvalidManifest("blocks must be an array".to_owned()))?;
    let order = object
        .get("cascade")
        .and_then(Value::as_array)
        .ok_or_else(|| CascadeError::InvalidManifest("cascade must be an array".to_owned()))?;
    if blocks.len() < 2 || blocks.len() > MAX_BLOCKS || order.len() != blocks.len() {
        return Err(CascadeError::InvalidManifest(
            "cascade requires 2..=32 blocks and a matching order".to_owned(),
        ));
    }
    let base = path.parent().unwrap_or_else(|| Path::new("."));
    let mut specs = Vec::with_capacity(blocks.len());
    let mut names = Vec::new();
    for (index, entry) in blocks.iter().enumerate() {
        let item = entry.as_object().ok_or_else(|| {
            CascadeError::InvalidManifest(format!("block {index} must be an object"))
        })?;
        if item.keys().any(|key| {
            !matches!(
                key.as_str(),
                "name" | "touchstone" | "rms_target" | "max_order"
            )
        }) {
            return Err(CascadeError::InvalidManifest(format!(
                "block {index} contains unsupported keys"
            )));
        }
        let name = item.get("name").and_then(Value::as_str).ok_or_else(|| {
            CascadeError::InvalidManifest(format!("block {index} name is required"))
        })?;
        if name.is_empty()
            || !name.chars().next().is_some_and(|c| c.is_ascii_alphabetic())
            || !name
                .chars()
                .all(|c| c.is_ascii_alphanumeric() || ".-_".contains(c))
            || names.iter().any(|value| value == name)
        {
            return Err(CascadeError::InvalidManifest(format!(
                "block {index} name is invalid or duplicated"
            )));
        }
        let raw_path = item
            .get("touchstone")
            .and_then(Value::as_str)
            .ok_or_else(|| {
                CascadeError::InvalidManifest(format!("block {name} touchstone is required"))
            })?;
        let touchstone = base.join(raw_path);
        let touchstone_bytes = touchstone
            .metadata()
            .map(|metadata| metadata.len())
            .unwrap_or(0);
        if !touchstone.is_file()
            || touchstone_bytes > MAX_ARTIFACT_BYTES as u64
            || touchstone
                .extension()
                .and_then(|value| value.to_str())
                .is_none_or(|value| !value.eq_ignore_ascii_case("s2p"))
        {
            return Err(CascadeError::Input(format!(
                "block {name} requires an existing .s2p Touchstone"
            )));
        }
        let rms_target_explicit = item.contains_key("rms_target");
        let rms_target = item
            .get("rms_target")
            .and_then(Value::as_f64)
            .or(options.rms_target)
            .or_else(|| {
                options.priority_band_fit_only.then(|| {
                    options
                        .priority_bands
                        .iter()
                        .map(|band| band.rms_target)
                        .fold(f64::INFINITY, f64::min)
                })
            })
            .ok_or_else(|| {
                CascadeError::InvalidManifest(format!(
                    "block {name} requires rms_target unless the CLI default is supplied"
                ))
            })?;
        let max_order = match item.get("max_order").and_then(Value::as_u64) {
            Some(value) if value <= options.max_order as u64 => value as usize,
            Some(_) => {
                return Err(CascadeError::InvalidManifest(format!(
                    "block {name} max_order is outside bounds"
                )));
            }
            None => options.max_order,
        };
        if !rms_target.is_finite()
            || rms_target <= 0.0
            || max_order < options.min_order
            || max_order > options.max_order
        {
            return Err(CascadeError::InvalidManifest(format!(
                "block {name} target/order is outside bounds"
            )));
        }
        names.push(name.to_owned());
        specs.push(CascadeBlockSpec {
            name: name.to_owned(),
            touchstone,
            rms_target,
            max_order,
            gate_full_band_rms: options.gate_full_band_rms || rms_target_explicit,
        });
    }
    let cascade_order = order
        .iter()
        .map(|value| {
            value.as_str().map(str::to_owned).ok_or_else(|| {
                CascadeError::InvalidManifest("cascade names must be strings".to_owned())
            })
        })
        .collect::<Result<Vec<_>, _>>()?;
    let mut sorted = cascade_order.clone();
    sorted.sort();
    let mut expected = names.clone();
    expected.sort();
    if sorted != expected || cascade_order.windows(2).any(|pair| pair[0] == pair[1]) {
        return Err(CascadeError::InvalidManifest(
            "cascade must contain every block exactly once".to_owned(),
        ));
    }
    Ok((specs, cascade_order))
}

fn interpolate(network: &TouchstoneNetwork, frequency: f64) -> [Complex; 4] {
    let frequencies = network.frequencies_hz();
    let samples = network.samples();
    if frequency <= frequencies[0] {
        return [samples[0][0], samples[0][1], samples[0][2], samples[0][3]];
    }
    if frequency >= *frequencies.last().unwrap_or(&frequency) {
        let row = samples.last().expect("sample count is validated");
        return [row[0], row[1], row[2], row[3]];
    }
    let upper = frequencies.partition_point(|value| *value < frequency);
    let lower = upper.saturating_sub(1);
    let span = frequencies[upper] - frequencies[lower];
    let ratio = if span == 0.0 {
        0.0
    } else {
        (frequency - frequencies[lower]) / span
    };
    let a = &samples[lower];
    let b = &samples[upper];
    [0, 1, 2, 3].map(|index| a[index] + (b[index] - a[index]) * ratio)
}

fn to_abcd(s: [Complex; 4], z0: f64) -> Option<[Complex; 4]> {
    // Internal matrices are row-major: [S11, S12, S21, S22].
    let denominator = 2.0 * s[2];
    if denominator.norm() <= f64::EPSILON {
        return None;
    }
    Some([
        ((Complex::new(1.0, 0.0) + s[0]) * (Complex::new(1.0, 0.0) - s[3]) + s[1] * s[2])
            / denominator,
        z0 * ((Complex::new(1.0, 0.0) + s[0]) * (Complex::new(1.0, 0.0) + s[3]) - s[1] * s[2])
            / denominator,
        ((Complex::new(1.0, 0.0) - s[0]) * (Complex::new(1.0, 0.0) - s[3]) - s[1] * s[2])
            / (2.0 * z0 * s[2]),
        ((Complex::new(1.0, 0.0) - s[0]) * (Complex::new(1.0, 0.0) + s[3]) + s[1] * s[2])
            / denominator,
    ])
}

fn multiply_abcd(left: [Complex; 4], right: [Complex; 4]) -> [Complex; 4] {
    [
        left[0] * right[0] + left[1] * right[2],
        left[0] * right[1] + left[1] * right[3],
        left[2] * right[0] + left[3] * right[2],
        left[2] * right[1] + left[3] * right[3],
    ]
}

fn from_abcd(value: [Complex; 4], z0: f64) -> Option<[Complex; 4]> {
    let denominator = value[0] + value[1] / z0 + value[2] * z0 + value[3];
    if denominator.norm() <= f64::EPSILON {
        return None;
    }
    Some([
        (value[0] + value[1] / z0 - value[2] * z0 - value[3]) / denominator,
        Complex::new(2.0, 0.0) * (value[0] * value[3] - value[1] * value[2]) / denominator,
        Complex::new(2.0, 0.0) / denominator,
        (-value[0] + value[1] / z0 - value[2] * z0 + value[3]) / denominator,
    ])
}

fn max_sigma(value: [Complex; 4]) -> f64 {
    let h00 = value[0].norm_sqr() + value[2].norm_sqr();
    let h11 = value[1].norm_sqr() + value[3].norm_sqr();
    let h01 = value[0].conj() * value[1] + value[2].conj() * value[3];
    let eigen = 0.5 * (h00 + h11 + ((h00 - h11) * (h00 - h11) + 4.0 * h01.norm_sqr()).sqrt());
    eigen.sqrt()
}

fn cmat_mul(a: &[Complex], ar: usize, ac: usize, b: &[Complex], bc: usize) -> Vec<Complex> {
    (0..ar)
        .flat_map(|row| {
            (0..bc).map(move |column| {
                (0..ac)
                    .map(|inner| a[row * ac + inner] * b[inner * bc + column])
                    .sum()
            })
        })
        .collect()
}

fn cmat_transpose(value: &[Complex], rows: usize, columns: usize) -> Vec<Complex> {
    (0..columns)
        .flat_map(|column| (0..rows).map(move |row| value[row * columns + column]))
        .collect()
}

fn cmat_inverse(value: &[Complex], n: usize) -> Option<Vec<Complex>> {
    let matrix = Mat::from_fn(n, n, |row, column| value[row * n + column]);
    let inverse = matrix.partial_piv_lu().inverse();
    let mut output = Vec::with_capacity(n * n);
    for row in 0..n {
        for column in 0..n {
            output.push(inverse[(row, column)]);
        }
    }
    if output
        .iter()
        .any(|value| !value.re.is_finite() || !value.im.is_finite())
    {
        return None;
    }
    Some(output)
}

/// Locate the bounded Hamiltonian crossover frequencies used by the pinned
/// passivity checker.  The result is advisory for the Rust enforcement grid;
/// the final acceptance gate is still sampled and reports continuous parity
/// separately.  A singular realization is treated as "no crossover" rather
/// than becoming a fake pass.
fn hamiltonian_crossovers(model: &RationalFitModel, f_max: f64) -> Vec<f64> {
    if model.proportional.iter().any(|value| value.norm() > 1e-12)
        || model
            .constant
            .iter()
            .any(|value| !value.im.is_finite() || value.im.abs() > 1e-8 * value.re.abs().max(1.0))
    {
        return Vec::new();
    }
    let mut real_poles = Vec::<(usize, f64)>::new();
    let mut complex_pairs = Vec::<(usize, usize, f64, f64)>::new();
    let mut visited = vec![false; model.poles.len()];
    for index in 0..model.poles.len() {
        if visited[index] {
            continue;
        }
        let pole = model.poles[index];
        if pole.im.abs() <= 1e-12 {
            real_poles.push((index, pole.re * model.frequency_scale_hz));
            visited[index] = true;
            continue;
        }
        let Some(partner) = (index + 1..model.poles.len()).find(|candidate| {
            !visited[*candidate]
                && (model.poles[*candidate] - pole.conj()).norm() <= 1e-8 * pole.norm().max(1.0)
        }) else {
            return Vec::new();
        };
        let positive = if pole.im > 0.0 { index } else { partner };
        let negative = if pole.im > 0.0 { partner } else { index };
        let _ = negative;
        let positive_pole = model.poles[positive];
        complex_pairs.push((
            positive,
            if positive == index { partner } else { index },
            positive_pole.re * model.frequency_scale_hz,
            positive_pole.im * model.frequency_scale_hz,
        ));
        visited[index] = true;
        visited[partner] = true;
    }
    let states_per_port = real_poles.len() + complex_pairs.len() * 2;
    if states_per_port == 0 {
        return Vec::new();
    }
    let n = model.ports;
    let states = n * states_per_port;
    let mut a = vec![Complex::new(0.0, 0.0); states * states];
    let mut b = vec![Complex::new(0.0, 0.0); states * n];
    let mut c = vec![Complex::new(0.0, 0.0); n * states];
    let d = model
        .constant
        .iter()
        .map(|value| Complex::new(value.re, 0.0))
        .collect::<Vec<_>>();
    let physical_residue_scale = model.frequency_scale_hz;
    for input in 0..n {
        let mut state = input * states_per_port;
        for (pole_index, pole) in &real_poles {
            a[state * states + state] = Complex::new(*pole, 0.0);
            b[state * n + input] = Complex::new(1.0, 0.0);
            for output in 0..n {
                c[output * states + state] = Complex::new(
                    (model.residues[*pole_index][output * n + input] * physical_residue_scale).re,
                    0.0,
                );
            }
            state += 1;
        }
        for (positive_index, _negative_index, sigma, omega) in &complex_pairs {
            let first = state;
            let second = state + 1;
            a[first * states + first] = Complex::new(*sigma, 0.0);
            a[first * states + second] = Complex::new(*omega, 0.0);
            a[second * states + first] = Complex::new(-*omega, 0.0);
            a[second * states + second] = Complex::new(*sigma, 0.0);
            b[first * n + input] = Complex::new(2.0, 0.0);
            for output in 0..n {
                let residue =
                    model.residues[*positive_index][output * n + input] * physical_residue_scale;
                c[output * states + first] = Complex::new(residue.re, 0.0);
                c[output * states + second] = Complex::new(residue.im, 0.0);
            }
            state += 2;
        }
    }
    let identity = (0..n * n)
        .map(|index| {
            if index / n == index % n {
                Complex::new(1.0, 0.0)
            } else {
                Complex::new(0.0, 0.0)
            }
        })
        .collect::<Vec<_>>();
    let d_transpose = cmat_transpose(&d, n, n);
    let d_transpose_d = cmat_mul(&d_transpose, n, n, &d, n);
    let d_d_transpose = cmat_mul(&d, n, n, &d_transpose, n);
    let left = identity
        .iter()
        .zip(&d_transpose_d)
        .map(|(one, value)| *one - *value)
        .collect::<Vec<_>>();
    let right = identity
        .iter()
        .zip(&d_d_transpose)
        .map(|(one, value)| *one - *value)
        .collect::<Vec<_>>();
    let Some(inv_left) = cmat_inverse(&left, n) else {
        return Vec::new();
    };
    let Some(inv_right) = cmat_inverse(&right, n) else {
        return Vec::new();
    };
    let bt = cmat_transpose(&b, states, n);
    let ct = cmat_transpose(&c, n, states);
    let m11 = {
        let term = cmat_mul(
            &cmat_mul(
                &cmat_mul(&b, states, n, &inv_left, n),
                states,
                n,
                &d_transpose,
                n,
            ),
            states,
            n,
            &c,
            states,
        );
        a.iter().zip(term).map(|(x, y)| *x + y).collect::<Vec<_>>()
    };
    let m12 = cmat_mul(
        &cmat_mul(&b, states, n, &inv_left, n),
        states,
        n,
        &bt,
        states,
    );
    let m21 = cmat_mul(
        &cmat_mul(&ct, states, n, &inv_right, n),
        states,
        n,
        &c,
        states,
    )
    .into_iter()
    .map(|value| -value)
    .collect::<Vec<_>>();
    let m22 = {
        let left_term = cmat_mul(
            &cmat_mul(&ct, states, n, &d, n),
            states,
            n,
            &cmat_mul(&inv_left, n, n, &bt, states),
            states,
        );
        let transposed_a = cmat_transpose(&a, states, states);
        transposed_a
            .into_iter()
            .zip(left_term)
            .map(|(x, y)| -x - y)
            .collect::<Vec<_>>()
    };
    let mut hamiltonian = vec![Complex::new(0.0, 0.0); states * 2 * states * 2];
    for row in 0..states {
        for column in 0..states {
            hamiltonian[row * states * 2 + column] = m11[row * states + column];
            hamiltonian[row * states * 2 + states + column] = m12[row * states + column];
            hamiltonian[(states + row) * states * 2 + column] = m21[row * states + column];
            hamiltonian[(states + row) * states * 2 + states + column] = m22[row * states + column];
        }
    }
    let matrix = Mat::from_fn(states * 2, states * 2, |row, column| {
        hamiltonian[row * states * 2 + column]
    });
    let Ok(eigen) = matrix.eigen() else {
        return Vec::new();
    };
    let mut frequencies = eigen
        .S()
        .column_vector()
        .iter()
        .copied()
        .filter_map(|value| {
            if value.re.abs() < 1e-4 && value.im.abs() > 1e-3 {
                let frequency = value.im.abs() / (2.0 * std::f64::consts::PI);
                (frequency > 0.0 && frequency.is_finite() && frequency <= f_max)
                    .then_some(frequency)
            } else {
                None
            }
        })
        .collect::<Vec<_>>();
    frequencies.sort_by(f64::total_cmp);
    frequencies.dedup_by(|left, right| (*left - *right).abs() <= 1e-9 * left.abs().max(1.0));
    frequencies
}

fn write_text(path: &Path, text: &str) -> Result<(), CascadeError> {
    if text.len() > MAX_ARTIFACT_BYTES {
        return Err(CascadeError::Output(
            "artifact byte budget exceeded".to_owned(),
        ));
    }
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|error| CascadeError::Output(error.to_string()))?;
    }
    fs::write(path, text).map_err(|error| CascadeError::Output(error.to_string()))
}

fn write_touchstone(
    path: &Path,
    frequencies: &[f64],
    samples: &[[Complex; 4]],
    z0: f64,
) -> Result<(), CascadeError> {
    let mut text = format!("# Hz S RI R {z0:.17e}\n");
    for (frequency, row) in frequencies.iter().zip(samples) {
        text.push_str(&format!("{frequency:.17e}"));
        for column in 0..2 {
            for row_index in 0..2 {
                let value = row[row_index * 2 + column];
                text.push_str(&format!(" {:.17e} {:.17e}", value.re, value.im));
            }
        }
        text.push('\n');
    }
    write_text(path, &text)
}

fn band_frequencies(frequencies: &[f64], bands: &[PriorityBand]) -> Vec<f64> {
    let mut points = Vec::new();
    for band in bands {
        let low = frequencies
            .first()
            .copied()
            .unwrap_or(0.0)
            .max(band.f_min_hz);
        let high = frequencies
            .last()
            .copied()
            .unwrap_or(0.0)
            .min(band.f_max_hz);
        if low > high {
            continue;
        }
        for frequency in frequencies
            .iter()
            .copied()
            .filter(|value| *value >= low && *value <= high)
        {
            points.push(frequency);
        }
        points.push(low);
        points.push(high);
    }
    points.sort_by(f64::total_cmp);
    points.dedup_by(|a, b| *a == *b);
    points
}

fn priority_evaluation_frequencies(
    f_min: f64,
    f_max: f64,
    sample_count: usize,
    bands: &[PriorityBand],
) -> Vec<f64> {
    let per_band = (sample_count / bands.len().max(1)).max(2);
    let mut points = Vec::new();
    for band in bands {
        let low = f_min.max(band.f_min_hz);
        let high = f_max.min(band.f_max_hz);
        if low >= high {
            continue;
        }
        if low > 0.0 {
            for index in 0..per_band {
                let ratio = index as f64 / (per_band - 1) as f64;
                points.push(low * (high / low).powf(ratio));
            }
        } else {
            for index in 0..per_band {
                let ratio = index as f64 / (per_band - 1) as f64;
                points.push(low + (high - low) * ratio);
            }
        }
    }
    points.sort_by(f64::total_cmp);
    points.dedup_by(|left, right| {
        (*left - *right).abs() <= 1e-12 * left.abs().max(right.abs()).max(1.0)
    });
    points
}

fn gate_metrics(
    block: &BlockFit,
    bands: &[PriorityBand],
    gate_full_band: bool,
) -> (f64, Option<f64>, bool) {
    gate_metrics_scaled(block, bands, gate_full_band, 1.0)
}

fn scaled_model_error(block: &BlockFit, frequencies: &[f64], scale: f64) -> f64 {
    let mut sum = 0.0;
    let mut count = 0usize;
    for frequency in frequencies {
        let raw = interpolate(&block.network, *frequency);
        let mut fitted = block.model.evaluate(*frequency);
        for value in &mut fitted {
            *value *= scale;
        }
        for (left, right) in raw.iter().zip(fitted.iter().take(4)) {
            sum += (*left - *right).norm_sqr();
            count += 1;
        }
    }
    if count == 0 {
        f64::INFINITY
    } else {
        (sum / count as f64).sqrt()
    }
}

fn gate_metrics_scaled(
    block: &BlockFit,
    bands: &[PriorityBand],
    gate_full_band: bool,
    scale: f64,
) -> (f64, Option<f64>, bool) {
    let full = scaled_model_error(block, block.network.frequencies_hz(), scale);
    let mut priority = None;
    let mut priority_met = true;
    if !bands.is_empty() {
        let mut worst = 0.0_f64;
        for band in bands {
            let frequencies =
                band_frequencies(block.network.frequencies_hz(), std::slice::from_ref(band));
            if frequencies.is_empty() {
                priority_met = false;
                worst = f64::INFINITY;
                continue;
            }
            let error = scaled_model_error(block, &frequencies, scale);
            worst = worst.max(error);
            if !error.is_finite() || error > band.rms_target {
                priority_met = false;
            }
        }
        priority = Some(worst);
    }
    let full_target = block.spec.rms_target;
    let target_met = if gate_full_band {
        full <= full_target && (bands.is_empty() || priority_met)
    } else {
        !bands.is_empty() && priority_met
    };
    (full, priority, target_met)
}

fn priority_worst_ratio(block: &BlockFit, bands: &[PriorityBand], scale: f64) -> f64 {
    if bands.is_empty() {
        return 0.0;
    }
    bands
        .iter()
        .map(|band| {
            let frequencies =
                band_frequencies(block.network.frequencies_hz(), std::slice::from_ref(band));
            if frequencies.is_empty() {
                f64::INFINITY
            } else {
                scaled_model_error(block, &frequencies, scale) / band.rms_target
            }
        })
        .fold(0.0_f64, f64::max)
}

fn scaled_block_gate(
    block: &BlockFit,
    bands: &[PriorityBand],
    scale: f64,
) -> (f64, Option<f64>, bool) {
    gate_metrics_scaled(block, bands, block.spec.gate_full_band_rms, scale)
}

fn cascade_mean_rms(reference: &[[Complex; 4]], fitted: &[[Complex; 4]]) -> f64 {
    if reference.is_empty() || reference.len() != fitted.len() {
        return f64::INFINITY;
    }
    let sum = reference
        .iter()
        .zip(fitted)
        .flat_map(|(left, right)| left.iter().zip(right))
        .map(|(left, right)| (*left - *right).norm_sqr())
        .sum::<f64>();
    (sum / (reference.len() * 4) as f64).sqrt()
}

// The shared fitter intentionally permits complex coefficients.  AS-02 also
// publishes Cadence RFM, whose real response is represented by conjugate pole
// pairs, so canonicalize each block before gates, cascade evaluation, and
// artifact publication.  This keeps the published model real without silently
// omitting the negative-frequency partner.
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

fn model_max_sigma(model: &RationalFitModel, frequencies: &[f64]) -> f64 {
    frequencies
        .iter()
        .map(|frequency| {
            let values = model.evaluate(*frequency);
            max_sigma([values[0], values[1], values[2], values[3]])
        })
        .fold(0.0_f64, f64::max)
}

fn passivity_violation_bands(
    model: &RationalFitModel,
    frequencies: &[f64],
    target: f64,
) -> Vec<Value> {
    let mut bands = Vec::new();
    let mut start = None;
    let mut worst = target;
    for (index, frequency) in frequencies.iter().copied().enumerate() {
        let sigma = max_sigma({
            let values = model.evaluate(frequency);
            [values[0], values[1], values[2], values[3]]
        });
        if sigma > target {
            start.get_or_insert(frequency);
            worst = worst.max(sigma);
        }
        let closes = sigma <= target || index + 1 == frequencies.len();
        if closes && let Some(low) = start.take() {
            let high = if sigma > target {
                frequency
            } else {
                frequencies[index.saturating_sub(1)]
            };
            bands.push(json!({"f_min_hz": low, "f_max_hz": high, "max_sigma": worst}));
            worst = target;
        }
    }
    bands
}

fn adaptive_passivity_grid(
    model: &RationalFitModel,
    seed: &[f64],
    target: f64,
) -> (Vec<f64>, Vec<Value>) {
    let mut grid = seed.to_vec();
    grid.sort_by(f64::total_cmp);
    grid.dedup_by(|left, right| *left == *right);
    for _ in 0..5 {
        let mut additions = Vec::new();
        for pair in grid.windows(2) {
            let left = max_sigma({
                let values = model.evaluate(pair[0]);
                [values[0], values[1], values[2], values[3]]
            });
            let right = max_sigma({
                let values = model.evaluate(pair[1]);
                [values[0], values[1], values[2], values[3]]
            });
            if left > target || right > target {
                additions.push(if pair[0] > 0.0 && pair[1] > 0.0 {
                    (pair[0] * pair[1]).sqrt()
                } else {
                    0.5 * (pair[0] + pair[1])
                });
            }
        }
        if additions.is_empty() {
            break;
        }
        grid.extend(additions);
        grid.sort_by(f64::total_cmp);
        grid.dedup_by(|left, right| *left == *right);
        if grid.len() >= 4096 {
            grid.truncate(4096);
            break;
        }
    }
    let bands = passivity_violation_bands(model, &grid, target);
    (grid, bands)
}

/// Apply the pinned passivity branch with explicit Hamiltonian crossover
/// bands, adaptive violation samples, and bounded coordinate optimization of
/// constants, residues, and pole damping.  A global contraction is not used:
/// every accepted candidate identifies the parameter family changed and is
/// rechecked against the adaptive bands before publication.
fn enforce_sampled_passivity(
    model: &mut RationalFitModel,
    frequencies: &[f64],
    epsilon: f64,
) -> Result<Value, CascadeError> {
    if frequencies.is_empty() {
        return Err(CascadeError::Numerical(
            "passivity enforcement requires at least one frequency".to_owned(),
        ));
    }
    let f_max = frequencies.iter().copied().fold(0.0_f64, f64::max);
    let crossovers = hamiltonian_crossovers(model, f_max);
    let mut enforcement_grid = frequencies.to_vec();
    enforcement_grid.extend(crossovers.iter().copied());
    let (mut enforcement_grid, initial_bands) =
        adaptive_passivity_grid(model, &enforcement_grid, 1.0 + epsilon);
    let before = model_max_sigma(model, &enforcement_grid);
    if !before.is_finite() {
        return Err(CascadeError::Numerical(
            "passivity sample contains a non-finite singular value".to_owned(),
        ));
    }
    let target = 1.0 + epsilon;
    if before <= target {
        return Ok(json!({
            "policy": "enforce",
            "method": "hamiltonian_violation_band_coordinate_descent",
            "status": "already_passive_on_sample_grid",
            "sample_max_sigma_before": before,
            "sample_max_sigma_after": before,
            "adjustment": "none",
            "hamiltonian_crossovers_hz": crossovers,
            "violation_bands_hz": initial_bands,
        }));
    }
    let mut after = before;
    let mut optimization_iterations = 0usize;
    let mut accepted_updates = Vec::new();
    for _ in 0..12 {
        if after <= target {
            break;
        }
        let mut best_candidate: Option<(RationalFitModel, f64, String)> = None;
        let mut candidates = Vec::<(RationalFitModel, String)>::new();
        for factor in [0.99, 0.95, 0.90] {
            let mut candidate = model.clone();
            for value in &mut candidate.constant {
                *value *= factor;
            }
            candidates.push((candidate, format!("constant_scale:{factor:.3}")));
        }
        for pole_index in 0..model.poles.len() {
            let pole = model.poles[pole_index];
            for factor in [0.99, 0.95, 0.90] {
                let mut candidate = model.clone();
                for value in &mut candidate.residues[pole_index] {
                    *value *= factor;
                }
                if pole.im.abs() > 1e-12
                    && let Some(partner) = (0..candidate.poles.len()).find(|index| {
                        *index != pole_index
                            && (candidate.poles[*index] - pole.conj()).norm()
                                <= 1e-8 * pole.norm().max(1.0)
                    })
                {
                    for value in &mut candidate.residues[partner] {
                        *value *= factor;
                    }
                }
                candidates.push((
                    candidate,
                    format!("residue_scale:pole={pole_index}:{factor:.3}"),
                ));
            }
            for factor in [1.10, 1.35, 1.75] {
                let mut candidate = model.clone();
                candidate.poles[pole_index].re *= factor;
                if pole.im.abs() > 1e-12
                    && let Some(partner) = (0..candidate.poles.len()).find(|index| {
                        *index != pole_index
                            && (candidate.poles[*index] - pole.conj()).norm()
                                <= 1e-8 * pole.norm().max(1.0)
                    })
                {
                    candidate.poles[partner].re = candidate.poles[pole_index].re;
                }
                candidates.push((
                    candidate,
                    format!("pole_damping:pole={pole_index}:{factor:.2}"),
                ));
            }
        }
        for (candidate, update) in candidates {
            let score = model_max_sigma(&candidate, &enforcement_grid);
            if score.is_finite()
                && score + 1e-12
                    < best_candidate
                        .as_ref()
                        .map_or(after, |(_, value, _)| *value)
            {
                best_candidate = Some((candidate, score, update));
            }
        }
        let Some((candidate, score, update)) = best_candidate else {
            break;
        };
        *model = candidate;
        after = score;
        optimization_iterations += 1;
        accepted_updates.push(update);
        let (grid, _bands) = adaptive_passivity_grid(model, &enforcement_grid, target);
        enforcement_grid = grid;
    }
    let final_bands = passivity_violation_bands(model, &enforcement_grid, target);
    if !after.is_finite() || after > target + 1e-9 {
        return Err(CascadeError::Numerical(format!(
            "adaptive passivity optimization did not meet sigma target: before={before:.6e}, after={after:.6e}, target={target:.6e}, violation_bands={final_bands:?}"
        )));
    }
    Ok(json!({
        "policy": "enforce",
        "method": "hamiltonian_violation_band_coordinate_descent",
        "status": "optimized",
        "sample_max_sigma_before": before,
        "sample_max_sigma_after": after,
        "target_sigma": target,
        "frequency_samples": enforcement_grid.len(),
        "optimization_iterations": optimization_iterations,
        "accepted_updates": accepted_updates,
        "hamiltonian_crossovers_hz": crossovers,
        "initial_violation_bands_hz": initial_bands,
        "final_violation_bands_hz": final_bands,
        "continuous_hamiltonian_parity": "sampled_hamiltonian_crossovers_with_adaptive_bands",
    }))
}

fn model_to_rfm(model: &RationalFitModel, z0: f64) -> Result<RfmModel, CascadeError> {
    if model.proportional.iter().any(|value| value.norm() > 1e-12) {
        return Err(CascadeError::Numerical(
            "cascade RFM export rejects proportional coefficients".to_owned(),
        ));
    }
    if model
        .constant
        .iter()
        .any(|value| value.im.abs() > 1e-8 * value.re.abs().max(1.0))
    {
        return Err(CascadeError::Numerical(
            "cascade RFM export requires real constants".to_owned(),
        ));
    }
    let indices = model
        .poles
        .iter()
        .enumerate()
        .filter(|(_, pole)| pole.im >= 0.0)
        .collect::<Vec<_>>();
    // RationalFitModel evaluates with s/frequency_scale_hz.  RFM stores
    // physical rad/s, so both poles and residues must be de-normalized.
    let poles = indices
        .iter()
        .map(|(_, pole)| **pole * model.frequency_scale_hz)
        .collect::<Vec<_>>();
    let residues = (0..model.ports * model.ports)
        .map(|response| {
            indices
                .iter()
                .map(|(index, _)| model.residues[*index][response] * model.frequency_scale_hz)
                .collect::<Vec<_>>()
        })
        .collect::<Vec<_>>();
    Ok(RfmModel {
        version: 200600,
        nports: model.ports,
        matrix_type: "S".to_owned(),
        z0,
        poles,
        residues,
        constant: model.constant.clone(),
    })
}

fn write_block_artifacts(
    block: &BlockFit,
    output_root: &Path,
    z0: f64,
) -> Result<(), CascadeError> {
    // Passivity adjustment/refit mutates the selected model after the shared
    // fitter has written its initial artifacts.  Rewrite the delivery
    // Touchstone and the block report so every published artifact describes
    // the same post-adjustment model.
    write_fitted_touchstone(&block.fitted_touchstone, &block.network, &block.model)
        .map_err(|error| CascadeError::Output(error.to_string()))?;
    let rfm = model_to_rfm(&block.model, z0)?;
    write_cadence_rfm(&block.rfm, &rfm).map_err(|error| CascadeError::Output(error.to_string()))?;
    write_cadence_rfm_wrapper(
        &block.rfm_wrapper,
        &block.rfm,
        rfm.nports,
        Some(&format!("{}_rfm", block.spec.name)),
    )
    .map_err(|error| CascadeError::Output(error.to_string()))?;
    let relative = block
        .rfm
        .file_name()
        .and_then(|v| v.to_str())
        .unwrap_or("model.rfm");
    write_text(
        &block.spice,
        &format!(
            "* AS-02 dynamic S-equivalent for {}\n.include '{relative}'\n.include '{}'\n",
            block.spec.name,
            block
                .rfm_wrapper
                .file_name()
                .and_then(|v| v.to_str())
                .unwrap_or("rfm_wrapper.sp")
        ),
    )?;
    let payload = json!({"workflow": WORKFLOW_NAME, "block": block.spec.name, "ports": block.model.ports, "order": block.model.order(), "reference_impedance_ohm": z0, "pole_relocation_iterations": block.pole_relocation_iterations, "passivity": block.passivity_adjustment, "artifacts": {"spice": block.spice, "rfm": block.rfm, "rfm_wrapper": block.rfm_wrapper, "fitted_touchstone": block.fitted_touchstone}, "source": "native vector fitting with pole relocation and residue refit"});
    let report = serde_json::to_string_pretty(&payload)
        .map_err(|error| CascadeError::Output(error.to_string()))?
        + "\n";
    write_text(&block.report, &report)?;
    write_text(
        &block.log,
        &format!(
            "workflow={} block={} order={} pole_relocation_iterations={} passivity={}\n",
            WORKFLOW_NAME,
            block.spec.name,
            block.model.order(),
            block.pole_relocation_iterations,
            block.passivity_adjustment
        ),
    )?;
    write_text(
        &block.html,
        &format!(
            "<!doctype html><meta charset=\"utf-8\"><title>AS-02 {}</title><h1>{}</h1><pre>{}</pre>\n",
            block.spec.name,
            block.spec.name,
            html_escape(&serde_json::to_string_pretty(&payload).unwrap_or_default())
        ),
    )?;
    let _ = output_root;
    Ok(())
}

fn html_escape(value: &str) -> String {
    value
        .replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
}

fn evaluate_cascade(
    blocks: &[BlockFit],
    order: &[String],
    frequencies: &[f64],
    scales: &[f64],
    z0: f64,
) -> Result<(Vec<[Complex; 4]>, f64), CascadeError> {
    let mut output = Vec::with_capacity(frequencies.len());
    let mut total_sigma: f64 = 0.0;
    for frequency in frequencies {
        let mut combined = [
            Complex::new(1.0, 0.0),
            Complex::new(0.0, 0.0),
            Complex::new(0.0, 0.0),
            Complex::new(1.0, 0.0),
        ];
        for (position, name) in order.iter().enumerate() {
            let block = blocks
                .iter()
                .find(|candidate| candidate.spec.name == *name)
                .ok_or_else(|| {
                    CascadeError::Numerical("cascade order references missing block".to_owned())
                })?;
            let mut sample = block.model.evaluate(*frequency);
            let scale = scales.get(position).copied().unwrap_or(1.0);
            for value in &mut sample {
                *value *= scale;
            }
            let s = [sample[0], sample[1], sample[2], sample[3]];
            let abcd = to_abcd(s, z0).ok_or_else(|| {
                CascadeError::Numerical(format!(
                    "block '{}' has zero forward transmission at {frequency:.6e} Hz",
                    block.spec.name
                ))
            })?;
            combined = multiply_abcd(combined, abcd);
        }
        let s = from_abcd(combined, z0).ok_or_else(|| {
            CascadeError::Numerical("cascade ABCD conversion is singular".to_owned())
        })?;
        total_sigma = total_sigma.max(max_sigma(s));
        output.push(s);
    }
    Ok((output, total_sigma))
}

fn evaluate_hybrid_cascade(
    blocks: &[BlockFit],
    order: &[String],
    frequencies: &[f64],
    scales: &[f64],
    z0: f64,
    raw_block: Option<usize>,
) -> Result<Vec<[Complex; 4]>, CascadeError> {
    let mut output = Vec::with_capacity(frequencies.len());
    for frequency in frequencies {
        let mut combined = [
            Complex::new(1.0, 0.0),
            Complex::new(0.0, 0.0),
            Complex::new(0.0, 0.0),
            Complex::new(1.0, 0.0),
        ];
        for (position, name) in order.iter().enumerate() {
            let block_index = blocks
                .iter()
                .position(|candidate| candidate.spec.name == *name)
                .ok_or_else(|| {
                    CascadeError::Numerical("cascade order references missing block".to_owned())
                })?;
            let block = &blocks[block_index];
            let mut sample = if Some(block_index) == raw_block {
                interpolate(&block.network, *frequency).to_vec()
            } else {
                block.model.evaluate(*frequency)
            };
            let scale = scales.get(position).copied().unwrap_or(1.0);
            for value in &mut sample {
                *value *= scale;
            }
            let s = [sample[0], sample[1], sample[2], sample[3]];
            let abcd = to_abcd(s, z0).ok_or_else(|| {
                CascadeError::Numerical(format!(
                    "block '{}' has zero forward transmission at {frequency:.6e} Hz",
                    block.spec.name
                ))
            })?;
            combined = multiply_abcd(combined, abcd);
        }
        output.push(from_abcd(combined, z0).ok_or_else(|| {
            CascadeError::Numerical("cascade ABCD conversion is singular".to_owned())
        })?);
    }
    Ok(output)
}

fn raw_cascade(
    blocks: &[BlockFit],
    order: &[String],
    frequencies: &[f64],
    z0: f64,
) -> Result<Vec<[Complex; 4]>, CascadeError> {
    let mut output = Vec::with_capacity(frequencies.len());
    for frequency in frequencies {
        let mut combined = [
            Complex::new(1.0, 0.0),
            Complex::new(0.0, 0.0),
            Complex::new(0.0, 0.0),
            Complex::new(1.0, 0.0),
        ];
        for name in order {
            let block = blocks
                .iter()
                .find(|candidate| candidate.spec.name == *name)
                .ok_or_else(|| {
                    CascadeError::Numerical("cascade order references missing block".to_owned())
                })?;
            let abcd = to_abcd(interpolate(&block.network, *frequency), z0).ok_or_else(|| {
                CascadeError::Numerical("raw cascade has zero forward transmission".to_owned())
            })?;
            combined = multiply_abcd(combined, abcd);
        }
        output.push(from_abcd(combined, z0).ok_or_else(|| {
            CascadeError::Numerical("raw cascade conversion is singular".to_owned())
        })?);
    }
    Ok(output)
}

fn block_artifact_paths(block: &BlockFit) -> [&Path; 7] {
    [
        &block.spice,
        &block.report,
        &block.html,
        &block.log,
        &block.fitted_touchstone,
        &block.rfm,
        &block.rfm_wrapper,
    ]
}

fn copy_block_artifacts(block: &BlockFit, destination: &Path) -> Result<(), CascadeError> {
    fs::create_dir_all(destination).map_err(|error| CascadeError::Output(error.to_string()))?;
    for source in block_artifact_paths(block) {
        if source.is_file() {
            let file_name = source.file_name().ok_or_else(|| {
                CascadeError::Output("block artifact has no file name".to_owned())
            })?;
            fs::copy(source, destination.join(file_name))
                .map_err(|error| CascadeError::Output(error.to_string()))?;
        }
    }
    Ok(())
}

fn restore_block_artifacts(block: &BlockFit, backup: &Path) -> Result<(), CascadeError> {
    for destination in block_artifact_paths(block) {
        let Some(file_name) = destination.file_name() else {
            continue;
        };
        let source = backup.join(file_name);
        if source.is_file() {
            if let Some(parent) = destination.parent() {
                fs::create_dir_all(parent)
                    .map_err(|error| CascadeError::Output(error.to_string()))?;
            }
            fs::copy(source, destination)
                .map_err(|error| CascadeError::Output(error.to_string()))?;
        }
    }
    Ok(())
}

fn refit_block_candidate(
    block: &BlockFit,
    options: &FitSparamCascadeOptions,
    requested_min_order: usize,
) -> Result<Option<BlockFit>, CascadeError> {
    if requested_min_order > block.spec.max_order || requested_min_order <= block.model.order() {
        return Ok(None);
    }
    let fit_options = FitSparamOptions {
        report: Some(block.report.clone()),
        fitted_touchstone: Some(block.fitted_touchstone.clone()),
        log: Some(block.log.clone()),
        rms_target: block
            .spec
            .gate_full_band_rms
            .then_some(block.spec.rms_target),
        max_order: Some(block.spec.max_order),
        min_order: requested_min_order,
        max_order_step: options.max_order_step,
        passivity: Some(PassivityPolicy::Off),
        reference_impedance: Some(options.reference_impedance),
        priority_bands: options.priority_bands.clone(),
        outside_band_weight: options.outside_band_weight,
        ..FitSparamOptions::default()
    };
    let request = crate::fit_sparam::FitSparamRequest::new(&block.spec.touchstone, fit_options)
        .map_err(|e| CascadeError::Input(e.to_string()))?;
    let result = fit_sparam(&request).map_err(|e| {
        CascadeError::Numerical(format!("block '{}' refit failed: {e}", block.spec.name))
    })?;
    if result.selected_order <= block.model.order() {
        return Ok(None);
    }
    let mut candidate = block.clone();
    candidate.model = result.model;
    candidate.pole_relocation_iterations = result
        .trials
        .iter()
        .map(|trial| trial.pole_relocation_iterations)
        .max()
        .unwrap_or(0);
    enforce_real_rational_coefficients(&mut candidate.model);
    candidate.passivity_adjustment = enforce_sampled_passivity(
        &mut candidate.model,
        block.network.frequencies_hz(),
        options.passivity_epsilon,
    )?;
    write_block_artifacts(
        &candidate,
        options.output_root.as_path(),
        options.reference_impedance,
    )?;
    Ok(Some(candidate))
}

fn refit_cascade_to_rms_target(
    blocks: &mut [BlockFit],
    order: &[String],
    frequencies: &[f64],
    raw_cascade: &[[Complex; 4]],
    options: &FitSparamCascadeOptions,
) -> Result<Value, CascadeError> {
    let Some(target) = options.cascade_rms_target else {
        return Ok(json!({
            "enabled": false,
            "target": null,
            "max_iterations": options.cascade_refit_max_iterations,
            "initial_mean_rms_error": null,
            "final_mean_rms_error": null,
            "target_met": null,
            "stop_reason": "target_not_set",
            "iterations": [],
        }));
    };
    let identity = vec![1.0; order.len()];
    let (initial_fitted, _) = evaluate_cascade(
        blocks,
        order,
        frequencies,
        &identity,
        options.reference_impedance,
    )?;
    let initial_rms = cascade_mean_rms(raw_cascade, &initial_fitted);
    let mut current_rms = initial_rms;
    let mut next_min_orders = blocks
        .iter()
        .map(|block| {
            (
                block.spec.name.clone(),
                block.model.order().saturating_add(1),
            )
        })
        .collect::<HashMap<_, _>>();
    let mut iterations = Vec::new();
    let mut stop_reason = (current_rms <= target).then_some("initial_target_met");

    while current_rms > target && iterations.len() < options.cascade_refit_max_iterations {
        let mut contributions = Vec::new();
        for (index, block) in blocks.iter().enumerate() {
            let hybrid = evaluate_hybrid_cascade(
                blocks,
                order,
                frequencies,
                &identity,
                options.reference_impedance,
                Some(index),
            )?;
            let hybrid_rms = cascade_mean_rms(raw_cascade, &hybrid);
            let next_min_order = *next_min_orders
                .get(&block.spec.name)
                .unwrap_or(&block.spec.max_order.saturating_add(1));
            let block_error = scaled_model_error(block, frequencies, 1.0);
            contributions.push(json!({
                "block": block.spec.name,
                "block_index": index,
                "current_order": block.model.order(),
                "next_min_order": next_min_order,
                "max_order": block.spec.max_order,
                "eligible": next_min_order <= block.spec.max_order,
                "block_mean_rms_error": block_error,
                "hybrid_cascade_mean_rms_error": hybrid_rms,
                "estimated_cascade_rms_improvement": current_rms - hybrid_rms,
            }));
        }
        let mut candidates = contributions
            .iter()
            .enumerate()
            .filter(|(_, item)| item["eligible"].as_bool().unwrap_or(false))
            .collect::<Vec<_>>();
        candidates.sort_by(|(_, left), (_, right)| {
            let left_improvement = left["estimated_cascade_rms_improvement"]
                .as_f64()
                .unwrap_or(f64::NEG_INFINITY);
            let right_improvement = right["estimated_cascade_rms_improvement"]
                .as_f64()
                .unwrap_or(f64::NEG_INFINITY);
            right_improvement
                .total_cmp(&left_improvement)
                .then_with(|| {
                    right["block_mean_rms_error"]
                        .as_f64()
                        .unwrap_or(f64::NEG_INFINITY)
                        .total_cmp(
                            &left["block_mean_rms_error"]
                                .as_f64()
                                .unwrap_or(f64::NEG_INFINITY),
                        )
                })
                .then_with(|| {
                    left["block_index"]
                        .as_u64()
                        .unwrap_or(usize::MAX as u64)
                        .cmp(&right["block_index"].as_u64().unwrap_or(usize::MAX as u64))
                })
        });
        let Some((contribution_index, selected)) = candidates.first().copied() else {
            stop_reason = Some("no_refittable_blocks");
            break;
        };
        let block_index = selected["block_index"].as_u64().ok_or_else(|| {
            CascadeError::Numerical("refit contribution has no block index".to_owned())
        })? as usize;
        let block_name = blocks[block_index].spec.name.clone();
        let requested_min_order = selected["next_min_order"].as_u64().ok_or_else(|| {
            CascadeError::Numerical("refit contribution has no next order".to_owned())
        })? as usize;
        let before_rms = current_rms;
        let iteration_number = iterations.len() + 1;
        let history_dir = options
            .output_root
            .join("cascade_refit_history")
            .join(format!("iteration_{iteration_number:02}_{block_name}"));
        let previous_dir = history_dir.join("previous");
        let candidate_dir = history_dir.join("candidate");
        copy_block_artifacts(&blocks[block_index], &previous_dir)?;

        let candidate_result =
            refit_block_candidate(&blocks[block_index], options, requested_min_order);
        let (candidate, error) = match candidate_result {
            Ok(candidate) => (candidate, None),
            Err(error) => (None, Some(error.to_string())),
        };
        copy_block_artifacts(&blocks[block_index], &candidate_dir)?;
        let candidate_order = candidate.as_ref().map(|value| value.model.order());
        next_min_orders.insert(
            block_name.clone(),
            candidate_order.map_or_else(
                || blocks[block_index].spec.max_order.saturating_add(1),
                |value| value + 1,
            ),
        );

        let mut after_rms = None;
        let mut accepted = false;
        let mut candidate_gate_met = false;
        if let Some(candidate_block) = candidate {
            let (_, _, gate_met) =
                scaled_block_gate(&candidate_block, &options.priority_bands, 1.0);
            candidate_gate_met = gate_met;
            if gate_met {
                let mut candidate_blocks = blocks.to_vec();
                candidate_blocks[block_index] = candidate_block.clone();
                let (candidate_fitted, _) = evaluate_cascade(
                    &candidate_blocks,
                    order,
                    frequencies,
                    &identity,
                    options.reference_impedance,
                )?;
                let candidate_rms = cascade_mean_rms(raw_cascade, &candidate_fitted);
                after_rms = Some(candidate_rms);
                let tolerance = (current_rms.abs() * 1e-9).max(1e-15);
                accepted = candidate_rms.is_finite()
                    && (candidate_rms <= target || candidate_rms < current_rms - tolerance);
                if accepted {
                    blocks[block_index] = candidate_block;
                    current_rms = candidate_rms;
                }
            }
        }
        if !accepted {
            restore_block_artifacts(&blocks[block_index], &previous_dir)?;
        }
        let rejection_reason = if accepted {
            None
        } else if error.is_some() {
            Some("refit_failed")
        } else if !candidate_gate_met {
            Some("block_target_not_met")
        } else {
            Some("cascade_rms_not_improved")
        };
        iterations.push(json!({
            "iteration": iteration_number,
            "before_mean_rms_error": before_rms,
            "contributions": contributions,
            "selected_contribution_index": contribution_index,
            "selected_block": block_name,
            "requested_min_order": requested_min_order,
            "candidate_selected_order": candidate_order,
            "candidate_block_target_met": candidate_gate_met,
            "candidate_mean_rms_error": after_rms,
            "accepted_rms_improvement": after_rms.map(|value| before_rms - value),
            "accepted": accepted,
            "rejection_reason": rejection_reason,
            "restored_previous_artifacts": !accepted,
            "error": error,
            "history_path": history_dir,
        }));
    }
    if current_rms <= target {
        stop_reason = stop_reason.or(Some("target_met"));
    } else if stop_reason.is_none() {
        stop_reason = Some("max_iterations_reached");
    }
    Ok(json!({
        "enabled": true,
        "target": target,
        "max_iterations": options.cascade_refit_max_iterations,
        "initial_mean_rms_error": initial_rms,
        "final_mean_rms_error": current_rms,
        "target_met": current_rms <= target,
        "stop_reason": stop_reason.unwrap_or("max_iterations_reached"),
        "iterations": iterations,
    }))
}

fn cascade_adjustment(
    blocks: &[BlockFit],
    order: &[String],
    frequencies: &[f64],
    raw_cascade: &[[Complex; 4]],
    options: &FitSparamCascadeOptions,
) -> Result<(Option<Vec<f64>>, Vec<Value>), CascadeError> {
    let identity = vec![1.0; order.len()];
    let (_, baseline_sigma) = evaluate_cascade(
        blocks,
        order,
        frequencies,
        &identity,
        options.reference_impedance,
    )?;
    let baseline_ratios = order
        .iter()
        .map(|name| {
            blocks
                .iter()
                .find(|block| block.spec.name == *name)
                .map(|block| {
                    if block.spec.gate_full_band_rms {
                        scaled_model_error(block, block.network.frequencies_hz(), 1.0)
                            / block.spec.rms_target
                    } else {
                        priority_worst_ratio(block, &options.priority_bands, 1.0)
                    }
                })
                .unwrap_or(f64::INFINITY)
        })
        .collect::<Vec<_>>();
    if baseline_sigma <= 1.0 + options.cascade_passivity_epsilon {
        return Ok((Some(identity), Vec::new()));
    }
    let mut groups = (0..order.len())
        .map(|index| vec![index])
        .collect::<Vec<_>>();
    if order.len() > 1 {
        groups.push((0..order.len()).collect());
    }
    let mut diagnostics = Vec::new();
    let mut candidates = Vec::<(f64, f64, Vec<f64>)>::new();
    for group in groups {
        let mut previous_scale = 1.0;
        let mut passing_scale = None;
        let mut passing_ratio = f64::INFINITY;
        for step in 1..=options.adjustment_iterations {
            let scale = 1.0
                - (1.0 - options.minimum_scale) * step as f64
                    / options.adjustment_iterations as f64;
            let scales = (0..order.len())
                .map(|index| if group.contains(&index) { scale } else { 1.0 })
                .collect::<Vec<_>>();
            let (fitted, sigma) = evaluate_cascade(
                blocks,
                order,
                frequencies,
                &scales,
                options.reference_impedance,
            )?;
            let mut block_rms = Vec::new();
            let mut rms_ok = true;
            let mut ratio_sum = 0.0;
            for (position, name) in order.iter().enumerate() {
                let block = blocks
                    .iter()
                    .find(|candidate| candidate.spec.name == *name)
                    .ok_or_else(|| {
                        CascadeError::Numerical(
                            "cascade adjustment references missing block".to_owned(),
                        )
                    })?;
                let (full, priority, target_met) =
                    scaled_block_gate(block, &options.priority_bands, scales[position]);
                let ratio = if block.spec.gate_full_band_rms {
                    full / block.spec.rms_target
                } else {
                    priority_worst_ratio(block, &options.priority_bands, scales[position])
                };
                ratio_sum += (ratio - baseline_ratios[position]).max(0.0);
                rms_ok &= target_met;
                block_rms.push(json!({
                    "name": name,
                    "full_band_mean_rms_error": full,
                    "priority_band_mean_rms_error": priority,
                    "target_met": target_met,
                    "scale": scales[position],
                }));
            }
            let cascade_rms_error = cascade_mean_rms(raw_cascade, &fitted);
            let cascade_rms_ok = options
                .cascade_rms_target
                .is_none_or(|target| cascade_rms_error.is_finite() && cascade_rms_error <= target);
            let pass = sigma <= 1.0 + options.cascade_passivity_epsilon && rms_ok && cascade_rms_ok;
            diagnostics.push(json!({
                "blocks": group.iter().filter_map(|index| order.get(*index)).collect::<Vec<_>>(),
                "scale": scale,
                "cascade_max_sigma": sigma,
                "block_rms_gates": block_rms,
                "rms_ok": rms_ok,
                "cascade_mean_rms_error": cascade_rms_error,
                "cascade_rms_target": options.cascade_rms_target,
                "cascade_rms_target_met": options.cascade_rms_target.map(|target| cascade_rms_error.is_finite() && cascade_rms_error <= target),
                "pass": pass,
            }));
            if pass {
                passing_scale = Some(scale);
                passing_ratio = ratio_sum;
                break;
            }
            previous_scale = scale;
        }
        let Some(mut low) = passing_scale else {
            continue;
        };
        let mut high = previous_scale;
        if high < low {
            std::mem::swap(&mut high, &mut low);
        }
        for _ in 0..options.adjustment_iterations {
            let scale = (low + high) * 0.5;
            let scales = (0..order.len())
                .map(|index| if group.contains(&index) { scale } else { 1.0 })
                .collect::<Vec<_>>();
            let (fitted, sigma) = evaluate_cascade(
                blocks,
                order,
                frequencies,
                &scales,
                options.reference_impedance,
            )?;
            let block_ok = order.iter().enumerate().all(|(position, name)| {
                blocks
                    .iter()
                    .find(|block| block.spec.name == *name)
                    .is_some_and(|block| {
                        scaled_block_gate(block, &options.priority_bands, scales[position]).2
                    })
            });
            let cascade_rms_error = cascade_mean_rms(raw_cascade, &fitted);
            let pass = sigma <= 1.0 + options.cascade_passivity_epsilon
                && block_ok
                && options.cascade_rms_target.is_none_or(|target| {
                    cascade_rms_error.is_finite() && cascade_rms_error <= target
                });
            if pass {
                low = scale;
                passing_ratio = order
                    .iter()
                    .enumerate()
                    .map(|(position, name)| {
                        blocks
                            .iter()
                            .find(|block| block.spec.name == *name)
                            .map(|block| {
                                let (full, _priority, _) = scaled_block_gate(
                                    block,
                                    &options.priority_bands,
                                    scales[position],
                                );
                                let ratio = if block.spec.gate_full_band_rms {
                                    full / block.spec.rms_target
                                } else {
                                    priority_worst_ratio(
                                        block,
                                        &options.priority_bands,
                                        scales[position],
                                    )
                                };
                                (ratio - baseline_ratios[position]).max(0.0)
                            })
                            .unwrap_or(f64::INFINITY)
                    })
                    .sum();
            } else {
                high = scale;
            }
        }
        let scales = (0..order.len())
            .map(|index| if group.contains(&index) { low } else { 1.0 })
            .collect::<Vec<_>>();
        candidates.push((
            passing_ratio,
            scales.iter().map(|value| 1.0 - value).sum(),
            scales,
        ));
    }
    let selected = candidates.into_iter().min_by(|left, right| {
        left.0
            .total_cmp(&right.0)
            .then_with(|| left.1.total_cmp(&right.1))
    });
    Ok((selected.map(|(_, _, scales)| scales), diagnostics))
}

/// Run the portable AS-02 cascade fit and publication path.
pub fn fit_sparam_cascade(
    request: &FitSparamCascadeRequest,
) -> Result<FitSparamCascadeResult, CascadeError> {
    validate_options(&request.manifest, &request.options)?;
    let (specs, order) = manifest_specs(&request.manifest, &request.options)?;
    fs::create_dir_all(&request.options.output_root)
        .map_err(|error| CascadeError::Output(error.to_string()))?;
    let mut blocks = Vec::new();
    for spec in specs {
        let directory = request.options.output_root.join("blocks").join(&spec.name);
        let report = directory.join("fit_report.json");
        let fitted_touchstone = directory.join(format!("{}_fitted.s2p", spec.name));
        let log = directory.join("fit.log");
        let rfm = directory.join(format!("{}.rfm", spec.name));
        let rfm_wrapper = directory.join(format!("{}_rfm_wrapper.sp", spec.name));
        let spice = directory.join(format!("{}_s_equivalent.sp", spec.name));
        let html = directory.join("fit_report.html");
        let options = FitSparamOptions {
            report: Some(report.clone()),
            fitted_touchstone: Some(fitted_touchstone.clone()),
            log: Some(log.clone()),
            rms_target: spec.gate_full_band_rms.then_some(spec.rms_target),
            max_order: Some(spec.max_order),
            min_order: request.options.min_order,
            max_order_step: request.options.max_order_step,
            passivity: Some(PassivityPolicy::Off),
            reference_impedance: Some(request.options.reference_impedance),
            priority_bands: request.options.priority_bands.clone(),
            outside_band_weight: request.options.outside_band_weight,
            ..FitSparamOptions::default()
        };
        let result = fit_sparam(
            &crate::fit_sparam::FitSparamRequest::new(&spec.touchstone, options)
                .map_err(|error| CascadeError::Input(error.to_string()))?,
        )
        .map_err(|error| {
            CascadeError::Numerical(format!("block '{}' fit failed: {error}", spec.name))
        })?;
        let pole_relocation_iterations = result
            .trials
            .iter()
            .map(|trial| trial.pole_relocation_iterations)
            .max()
            .unwrap_or(0);
        let spec_name = spec.name.clone();
        let spec_path = spec.touchstone.clone();
        let spec_gate_full_band_rms = spec.gate_full_band_rms;
        let mut block = BlockFit {
            spec,
            network: {
                let source_network = read_touchstone(&spec_path)
                    .map_err(|error| CascadeError::Input(error.to_string()))?;
                renormalize_network(&source_network, request.options.reference_impedance)
                    .map_err(|error| CascadeError::Input(error.to_string()))?
            },
            model: result.model,
            report,
            fitted_touchstone,
            log,
            rfm,
            rfm_wrapper,
            spice,
            html,
            passivity_adjustment: json!({"policy":"enforce","status":"not_run"}),
            pole_relocation_iterations,
        };
        enforce_real_rational_coefficients(&mut block.model);
        block.passivity_adjustment = enforce_sampled_passivity(
            &mut block.model,
            block.network.frequencies_hz(),
            request.options.passivity_epsilon,
        )?;
        if !result.target_met && spec_gate_full_band_rms {
            let failed_report = request
                .options
                .report
                .clone()
                .unwrap_or_else(|| request.options.output_root.join("cascade_report.json"));
            let payload = json!({"schema": "sipi.agent-spice-as-02-fit-sparam-cascade-result.v1", "workflow": WORKFLOW_NAME, "status": "FAIL", "reason": "block_fit_target_not_met", "failed_block": spec_name, "upstream_commit": UPSTREAM_COMMIT, "upstream_tree": UPSTREAM_TREE});
            write_text(
                &failed_report,
                &(serde_json::to_string_pretty(&payload)
                    .unwrap_or_else(|_| "{\"status\":\"FAIL\"}".to_owned())
                    + "\n"),
            )?;
            return Ok(FitSparamCascadeResult {
                status: "FAIL".to_owned(),
                report: failed_report,
                cascade_touchstone: None,
                cascade_order: order,
                max_sigma: None,
                cascade_rms_error: None,
                selected_scales: Vec::new(),
            });
        }
        if !request.options.priority_bands.is_empty()
            && band_frequencies(
                block.network.frequencies_hz(),
                &request.options.priority_bands,
            )
            .is_empty()
        {
            return Err(CascadeError::Input(format!(
                "block '{}' has no samples in the requested priority bands",
                spec_name
            )));
        }
        let (_, _, gate_met) = gate_metrics(
            &block,
            &request.options.priority_bands,
            block.spec.gate_full_band_rms,
        );
        if !gate_met && block.spec.gate_full_band_rms {
            let failed_report = request
                .options
                .report
                .clone()
                .unwrap_or_else(|| request.options.output_root.join("cascade_report.json"));
            let payload = json!({"schema":"sipi.agent-spice-as-02-fit-sparam-cascade-result.v2","workflow":WORKFLOW_NAME,"status":"FAIL","reason":"block_gate_not_met","failed_block":block.spec.name,"gate_full_band_rms":request.options.gate_full_band_rms});
            write_text(
                &failed_report,
                &(serde_json::to_string_pretty(&payload)
                    .unwrap_or_else(|_| "{\"status\":\"FAIL\"}".to_owned())
                    + "\n"),
            )?;
            return Ok(FitSparamCascadeResult {
                status: "FAIL".to_owned(),
                report: failed_report,
                cascade_touchstone: None,
                cascade_order: order,
                max_sigma: None,
                cascade_rms_error: None,
                selected_scales: Vec::new(),
            });
        }
        write_block_artifacts(
            &block,
            &request.options.output_root,
            request.options.reference_impedance,
        )?;
        blocks.push(block);
    }
    let f_min = blocks
        .iter()
        .map(|block| {
            block
                .network
                .frequencies_hz()
                .first()
                .copied()
                .unwrap_or(0.0)
        })
        .fold(0.0, f64::max);
    let f_max = blocks
        .iter()
        .map(|block| {
            block
                .network
                .frequencies_hz()
                .last()
                .copied()
                .unwrap_or(0.0)
        })
        .fold(f64::INFINITY, f64::min);
    if f_min.partial_cmp(&f_max) != Some(std::cmp::Ordering::Less) {
        return Err(CascadeError::Input(
            "cascade blocks have no overlapping frequency range".to_owned(),
        ));
    }
    let full_frequencies = if f_min > 0.0 {
        (0..request.options.cascade_samples)
            .map(|index| {
                let ratio = index as f64 / (request.options.cascade_samples - 1) as f64;
                f_min * (f_max / f_min).powf(ratio)
            })
            .collect::<Vec<_>>()
    } else {
        (0..request.options.cascade_samples)
            .map(|index| {
                f_min
                    + (f_max - f_min) * index as f64 / (request.options.cascade_samples - 1) as f64
            })
            .collect::<Vec<_>>()
    };
    let priority_only = request.options.priority_band_fit_only
        && !request.options.priority_bands.is_empty()
        && blocks.iter().all(|block| !block.spec.gate_full_band_rms);
    let frequencies = if priority_only {
        priority_evaluation_frequencies(
            f_min,
            f_max,
            request.options.cascade_samples,
            &request.options.priority_bands,
        )
    } else {
        full_frequencies.clone()
    };
    if frequencies.len() < 2 {
        return Err(CascadeError::Input(
            "priority bands do not overlap the cascade frequency intersection".to_owned(),
        ));
    }
    let raw_cascade_samples = raw_cascade(
        &blocks,
        &order,
        &frequencies,
        request.options.reference_impedance,
    )?;
    let cascade_refit = refit_cascade_to_rms_target(
        &mut blocks,
        &order,
        &frequencies,
        &raw_cascade_samples,
        &request.options,
    )?;
    let (selected_scales, adjustment_trials) = cascade_adjustment(
        &blocks,
        &order,
        &frequencies,
        &raw_cascade_samples,
        &request.options,
    )?;
    let scales = selected_scales.clone().unwrap_or_default();
    let evaluation_scales = if scales.is_empty() {
        vec![1.0; order.len()]
    } else {
        scales.clone()
    };
    let (fitted, mut sigma) = evaluate_cascade(
        &blocks,
        &order,
        &frequencies,
        &evaluation_scales,
        request.options.reference_impedance,
    )?;
    if scales.is_empty() {
        sigma = f64::INFINITY;
    }
    let cascade_rms = cascade_mean_rms(&raw_cascade_samples, &fitted);
    let effective_scales = evaluation_scales;
    let full_band_postcheck = if priority_only {
        let full_raw = raw_cascade(
            &blocks,
            &order,
            &full_frequencies,
            request.options.reference_impedance,
        )?;
        let (full_fitted, full_sigma) = evaluate_cascade(
            &blocks,
            &order,
            &full_frequencies,
            &effective_scales,
            request.options.reference_impedance,
        )?;
        Some(json!({
            "blocking": false,
            "frequency_range_hz": [f_min, f_max],
            "frequency_points": full_frequencies.len(),
            "cascade_mean_rms_error": cascade_mean_rms(&full_raw, &full_fitted),
            "passivity": {"max_sigma": full_sigma, "target_met": full_sigma <= 1.0 + request.options.cascade_passivity_epsilon},
        }))
    } else {
        None
    };
    let cascade_target_met = request
        .options
        .cascade_rms_target
        .is_none_or(|target| cascade_rms <= target);
    let cascade_passivity_met = sigma <= 1.0 + request.options.cascade_passivity_epsilon;
    let mut blocking_reasons = Vec::new();
    if !cascade_passivity_met {
        blocking_reasons.push("cascade_passivity_target_not_met");
    }
    if request.options.cascade_rms_target.is_some() && !cascade_target_met {
        blocking_reasons.push("cascade_rms_target_not_met");
    }
    if selected_scales.is_none() {
        blocking_reasons.push("cascade_passivity_adjustment_failed_within_limits");
    }
    let status = if blocking_reasons.is_empty() {
        "PASS"
    } else {
        "FAIL"
    };
    let cascade_touchstone = request.options.output_root.join("cascade_fitted.s2p");
    write_touchstone(
        &cascade_touchstone,
        &frequencies,
        &fitted,
        request.options.reference_impedance,
    )?;
    let report = request
        .options
        .report
        .clone()
        .unwrap_or_else(|| request.options.output_root.join("cascade_report.json"));
    let accepted_refits_by_block = blocks
        .iter()
        .map(|block| {
            let count = cascade_refit["iterations"]
                .as_array()
                .map(|iterations| {
                    iterations
                        .iter()
                        .filter(|item| {
                            item["selected_block"].as_str() == Some(block.spec.name.as_str())
                                && item["accepted"].as_bool() == Some(true)
                        })
                        .count()
                })
                .unwrap_or(0);
            (block.spec.name.clone(), count)
        })
        .collect::<HashMap<_, _>>();
    let payload = json!({
        "schema": "sipi.agent-spice-as-02-fit-sparam-cascade-result.v2",
        "workflow": WORKFLOW_NAME,
        "upstream_commit": UPSTREAM_COMMIT,
        "upstream_tree": UPSTREAM_TREE,
        "status": status,
        "blocking_reasons": blocking_reasons.clone(),
        "reason": blocking_reasons.first().copied(),
        "cascade_order": order,
        "reference_impedance_ohm": request.options.reference_impedance,
        "frequency_range_hz": [f_min, f_max],
        "frequency_points": frequencies.len(),
        "cascade_mean_rms_error": cascade_rms,
        "cascade_rms_target": request.options.cascade_rms_target,
        "cascade_rms_target_blocking": request.options.cascade_rms_target.is_some(),
        "cascade_rms_target_met": request.options.cascade_rms_target.map(|_| cascade_target_met),
        "evaluation_scope": if priority_only { "priority_band_union_only_no_extrapolation" } else { "intersection_only_no_extrapolation" },
        "passivity_after_adjustment": {"max_sigma": sigma, "epsilon": request.options.cascade_passivity_epsilon, "target_met": cascade_passivity_met},
        "full_band_postcheck": full_band_postcheck,
        "selected_scales": scales,
        "adjustment_trials": adjustment_trials,
        "cascade_refit_max_iterations": request.options.cascade_refit_max_iterations,
        "cascade_refit": cascade_refit,
        "gate_full_band_rms": request.options.gate_full_band_rms,
        "priority_band_fit_only": request.options.priority_band_fit_only,
        "cascade_touchstone_path": cascade_touchstone,
        "blocks": blocks.iter().map(|block| {
            let position = order.iter().position(|name| name == &block.spec.name).unwrap_or(0);
            let scale = effective_scales.get(position).copied().unwrap_or(1.0);
            let (full,priority,gate)=gate_metrics_scaled(block,&request.options.priority_bands,block.spec.gate_full_band_rms,scale);
            json!({"name": block.spec.name, "touchstone_path": block.spec.touchstone, "rms_target": block.spec.rms_target, "selected_order": block.model.order(), "pole_relocation_iterations": block.pole_relocation_iterations, "cascade_refit_count": accepted_refits_by_block.get(&block.spec.name).copied().unwrap_or(0), "scale": scale, "report_path": block.report, "fitted_touchstone_path": block.fitted_touchstone, "log_path": block.log, "gate": {"full_band_rms":full,"priority_band_rms":priority,"full_band_blocking":block.spec.gate_full_band_rms,"target_met":gate}, "artifacts": {"spice_subcircuit": block.spice, "html_report": block.html, "rfm": block.rfm, "rfm_wrapper": block.rfm_wrapper}})
        }).collect::<Vec<_>>(),
        "portable_branches": ["native-vector-fitting-pole-relocation", "priority-band-evaluation", "full-band-or-priority-gate", "bounded-cascade-refit", "hamiltonian-violation-bands", "adaptive-passivity-samples", "constant-residue-pole-coordinate-optimization", "z0-renormalization", "physical-frequency-rfm-export", "row-major-touchstone-delivery", "sampled-passivity-enforcement", "SPICE/HTML/RFM/wrapper-artifacts"],
        "external_runtime_boundary": [],
    });
    write_text(
        &report,
        &(serde_json::to_string_pretty(&payload)
            .map_err(|error| CascadeError::Output(error.to_string()))?
            + "\n"),
    )?;
    Ok(FitSparamCascadeResult {
        status: status.to_owned(),
        report,
        cascade_touchstone: Some(cascade_touchstone),
        cascade_order: order,
        max_sigma: Some(sigma),
        cascade_rms_error: Some(cascade_rms),
        selected_scales: scales,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn abc_conversion_round_trips() {
        let sample = [
            Complex::new(0.1, 0.0),
            Complex::new(0.5, 0.0),
            Complex::new(0.5, 0.0),
            Complex::new(0.1, 0.0),
        ];
        let abcd = to_abcd(sample, 50.0).unwrap();
        let recovered = from_abcd(abcd, 50.0).unwrap();
        for (left, right) in sample.into_iter().zip(recovered) {
            assert!((left - right).norm() < 1e-12);
        }
    }

    #[test]
    fn malformed_manifest_is_rejected_before_output() {
        let root = std::env::temp_dir().join(format!("sipi-as02-{}", std::process::id()));
        let path = root.join("bad.json");
        fs::create_dir_all(&root).unwrap();
        fs::write(&path, "{\"version\":2}").unwrap();
        let result = FitSparamCascadeRequest::new(&path, FitSparamCascadeOptions::default())
            .and_then(|request| fit_sparam_cascade(&request));
        assert!(matches!(result, Err(CascadeError::InvalidManifest(_))));
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn priority_only_manifest_derives_block_target_from_priority_band() {
        let root = std::env::temp_dir().join(format!("sipi-as02-priority-{}", std::process::id()));
        fs::create_dir_all(&root).unwrap();
        let touchstone = root.join("line.s2p");
        fs::write(
            &touchstone,
            "# Hz S RI R 50\n1e6 0 0 0.8 0 0.8 0 0 0\n1e7 0 0 0.8 0 0.8 0 0 0\n",
        )
        .unwrap();
        let manifest = root.join("cascade.json");
        fs::write(
            &manifest,
            format!(
                "{{\"version\":1,\"blocks\":[{{\"name\":\"a\",\"touchstone\":\"{}\"}},{{\"name\":\"b\",\"touchstone\":\"{}\"}}],\"cascade\":[\"a\",\"b\"]}}",
                touchstone.file_name().unwrap().to_string_lossy(),
                touchstone.file_name().unwrap().to_string_lossy()
            ),
        )
        .unwrap();
        let options = FitSparamCascadeOptions {
            priority_band_fit_only: true,
            gate_full_band_rms: false,
            priority_bands: vec![PriorityBand::new(1e6, 1e7, 0.25, 1.0).unwrap()],
            ..FitSparamCascadeOptions::default()
        };
        let (specs, _) = manifest_specs(&manifest, &options).unwrap();
        assert!(
            specs
                .iter()
                .all(|spec| (spec.rms_target - 0.25).abs() < f64::EPSILON)
        );
        let explicit_manifest = root.join("cascade-explicit.json");
        fs::write(
            &explicit_manifest,
            format!(
                "{{\"version\":1,\"blocks\":[{{\"name\":\"a\",\"touchstone\":\"{}\",\"rms_target\":0.25}},{{\"name\":\"b\",\"touchstone\":\"{}\"}}],\"cascade\":[\"a\",\"b\"]}}",
                touchstone.file_name().unwrap().to_string_lossy(),
                touchstone.file_name().unwrap().to_string_lossy()
            ),
        )
        .unwrap();
        let (explicit_specs, _) = manifest_specs(&explicit_manifest, &options).unwrap();
        assert!(explicit_specs[0].gate_full_band_rms);
        assert!(!explicit_specs[1].gate_full_band_rms);
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn sampled_passivity_enforcement_contracts_an_active_two_port_model() {
        let mut model = RationalFitModel {
            poles: Vec::new(),
            residues: Vec::new(),
            constant: vec![
                Complex::new(2.0, 0.0),
                Complex::new(0.0, 0.0),
                Complex::new(0.0, 0.0),
                Complex::new(2.0, 0.0),
            ],
            proportional: vec![Complex::new(0.0, 0.0); 4],
            ports: 2,
            frequency_scale_hz: 1.0,
        };
        let report = enforce_sampled_passivity(&mut model, &[0.0, 1.0e9], 1.0e-9).unwrap();
        assert_eq!(report["status"], "optimized");
        let values = model.evaluate(1.0e9);
        assert!(max_sigma([values[0], values[1], values[2], values[3]]) <= 1.0 + 1.0e-8);
    }

    #[test]
    fn hamiltonian_crossover_probe_is_bounded_for_real_rational_model() {
        let model = RationalFitModel {
            poles: vec![Complex::new(-1.0, 0.0)],
            residues: vec![vec![Complex::new(0.25, 0.0); 4]],
            constant: vec![Complex::new(0.1, 0.0); 4],
            proportional: vec![Complex::new(0.0, 0.0); 4],
            ports: 2,
            frequency_scale_hz: 1.0e9,
        };
        let crossovers = hamiltonian_crossovers(&model, 1.0e12);
        assert!(crossovers.len() <= model.poles.len() * 2);
        assert!(crossovers.iter().all(|frequency| {
            frequency.is_finite() && *frequency > 0.0 && *frequency <= 1.0e12
        }));
    }

    #[test]
    fn rfm_export_de_normalizes_frequency_scale() {
        let model = RationalFitModel {
            poles: vec![Complex::new(-2.0, 0.0)],
            residues: vec![vec![Complex::new(3.0, 0.0); 4]],
            constant: vec![Complex::new(0.1, 0.0); 4],
            proportional: vec![Complex::new(0.0, 0.0); 4],
            ports: 2,
            frequency_scale_hz: 1.0e9,
        };
        let rfm = model_to_rfm(&model, 50.0).unwrap();
        assert_eq!(rfm.poles, vec![Complex::new(-2.0e9, 0.0)]);
        assert_eq!(rfm.residues[0], vec![Complex::new(3.0e9, 0.0)]);
        for frequency in [0.0, 1.0e6, 1.0e9] {
            assert!((model.evaluate(frequency)[0] - rfm.evaluate_s(frequency)[0]).norm() < 1e-12);
        }
    }

    #[test]
    fn priority_gate_checks_each_band_target_independently() {
        let network = TouchstoneNetwork::from_samples(
            vec![1.0, 2.0, 3.0, 4.0],
            vec![
                vec![Complex::new(0.005, 0.0); 4],
                vec![Complex::new(0.005, 0.0); 4],
                vec![Complex::new(0.15, 0.0); 4],
                vec![Complex::new(0.15, 0.0); 4],
            ],
            2,
            50.0,
        )
        .unwrap();
        let block = BlockFit {
            spec: CascadeBlockSpec {
                name: "multi-band".to_owned(),
                touchstone: PathBuf::from("multi-band.s2p"),
                rms_target: 1.0,
                max_order: 1,
                gate_full_band_rms: false,
            },
            network,
            model: RationalFitModel {
                poles: Vec::new(),
                residues: Vec::new(),
                constant: vec![Complex::new(0.0, 0.0); 4],
                proportional: vec![Complex::new(0.0, 0.0); 4],
                ports: 2,
                frequency_scale_hz: 1.0,
            },
            report: PathBuf::from("fit-report.json"),
            fitted_touchstone: PathBuf::from("fitted.s2p"),
            log: PathBuf::from("fit.log"),
            rfm: PathBuf::from("model.rfm"),
            rfm_wrapper: PathBuf::from("model_wrapper.sp"),
            spice: PathBuf::from("model.sp"),
            html: PathBuf::from("model.html"),
            passivity_adjustment: json!({}),
            pole_relocation_iterations: 0,
        };
        let bands = vec![
            PriorityBand::new(1.0, 2.0, 0.01, 1.0).unwrap(),
            PriorityBand::new(3.0, 4.0, 0.2, 1.0).unwrap(),
        ];
        let (full, priority, met) = gate_metrics_scaled(&block, &bands, false, 1.0);
        assert!((full - 0.106_124_926_5).abs() < 1e-8);
        assert_eq!(priority, Some(0.15));
        assert!(met);
        assert!((priority_worst_ratio(&block, &bands, 1.0) - 0.75).abs() < 1e-12);
    }
}
