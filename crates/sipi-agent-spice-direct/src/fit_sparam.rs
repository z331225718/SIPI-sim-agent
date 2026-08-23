//! AS-01 direct-port of the pinned Agent-Spice `fit-sparam` workflow.
//!
//! This lane ports the bounded native numerical route rather than wrapping
//! the existing product kernel: Touchstone 1.x input, Native Vector Fitting
//! pole relocation with residue refits, bounded order search, sampled
//! passivity observation, fitted Touchstone, and diagnostic JSON/log output.
//! Unimplemented SPICE/RFM/HTML publication is rejected rather than faked;
//! AS-05 owns its explicit n-port S-preflight enforcement wrapper.

use std::fmt::{Display, Formatter};
use std::fs::{self, File};
use std::io::Read;
use std::path::{Component, Path, PathBuf};

use faer::{Mat, linalg::solvers::SolveLstsq};
use num_complex::Complex64 as Complex;
use serde_json::{Value, json};
use sipi_channel::{
    MatchedTwoPortSpectrumV1, SampledDiagnosticStatusV1, TwoPortS, analyze_matched_two_port_v1,
};
use sipi_types::{Complex64 as SipiComplex64, Hertz, Ohms};

pub const UPSTREAM_COMMIT: &str = "2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5";
pub const UPSTREAM_TREE: &str = "b6bde97128030d6cea0d68b2f0a35d807be8c402";
pub const WORKFLOW_ID: &str = "AS-01";
pub const WORKFLOW_NAME: &str = "fit-sparam";
pub const MAX_TOUCHSTONE_BYTES: usize = 16 * 1024 * 1024;
pub const MAX_TOUCHSTONE_LINE_BYTES: usize = 64 * 1024;
pub const MAX_TOUCHSTONE_SAMPLES: usize = 8_192;
pub const MAX_PRIORITY_BANDS: usize = 16;
pub const MAX_FIT_ORDER: usize = 100;
pub const MAX_ORDER_STEP: usize = 100;
pub const MAX_REAL_MATRIX_ROWS: usize = MAX_TOUCHSTONE_SAMPLES * 2;
pub const MAX_REAL_MATRIX_COLUMNS: usize = (MAX_FIT_ORDER + 2) * 2;
pub const MAX_REAL_MATRIX_CELLS: usize = 2_000_000;
pub const MAX_ARTIFACT_BYTES: usize = 4 * 1024 * 1024;
pub const MAX_ARTIFACT_PATH_BYTES: usize = 4_096;

/// The three public passivity policies accepted by the pinned CLI.
#[derive(Clone, Copy, Debug, Default, Eq, PartialEq)]
pub enum PassivityPolicy {
    Off,
    #[default]
    Check,
    Enforce,
}

impl PassivityPolicy {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Off => "off",
            Self::Check => "check",
            Self::Enforce => "enforce",
        }
    }

    pub fn parse(value: &str) -> Result<Self, FitSparamError> {
        match value {
            "off" => Ok(Self::Off),
            "check" => Ok(Self::Check),
            "enforce" => Ok(Self::Enforce),
            other => Err(FitSparamError::UnsupportedPassivity(other.to_owned())),
        }
    }
}

impl Display for PassivityPolicy {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(self.as_str())
    }
}

/// One priority-band entry.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct PriorityBand {
    pub f_min_hz: f64,
    pub f_max_hz: f64,
    pub rms_target: f64,
    pub weight: f64,
}

impl PriorityBand {
    pub fn new(
        f_min_hz: f64,
        f_max_hz: f64,
        rms_target: f64,
        weight: f64,
    ) -> Result<Self, FitSparamError> {
        if ![f_min_hz, f_max_hz, rms_target, weight]
            .into_iter()
            .all(f64::is_finite)
        {
            return Err(FitSparamError::NonFinitePriorityBand);
        }
        if f_min_hz < 0.0 || f_min_hz >= f_max_hz {
            return Err(FitSparamError::InvalidPriorityBandRange);
        }
        if rms_target <= 0.0 {
            return Err(FitSparamError::InvalidPriorityBandTarget);
        }
        if weight <= 0.0 {
            return Err(FitSparamError::InvalidPriorityBandWeight);
        }
        Ok(Self {
            f_min_hz,
            f_max_hz,
            rms_target,
            weight,
        })
    }
}

/// Compatibility flags hidden by the pinned parser but reachable from legacy
/// invocations. They are retained to preserve conflict detection.
#[derive(Clone, Copy, Debug, Default, Eq, PartialEq)]
pub struct LegacyPassivityFlags {
    pub enforce: bool,
    pub check: bool,
    pub skip_check: bool,
    pub skip_enforce: bool,
}

impl LegacyPassivityFlags {
    pub const fn any(self) -> bool {
        self.enforce || self.check || self.skip_check || self.skip_enforce
    }
}

/// The public quality profile choices in the pinned parser.
#[derive(Clone, Copy, Debug, Default, Eq, PartialEq)]
pub enum QualityProfile {
    #[default]
    Explore,
    Signoff,
}

impl QualityProfile {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Explore => "explore",
            Self::Signoff => "signoff",
        }
    }
}

/// Request options with the pinned public defaults. Advanced hidden Native
/// tuning flags remain an explicit evidence gap in this first slice.
#[derive(Clone, Debug, PartialEq)]
pub struct FitSparamOptions {
    pub output: Option<PathBuf>,
    pub report: Option<PathBuf>,
    pub html_report: Option<PathBuf>,
    pub fitted_touchstone: Option<PathBuf>,
    pub rfm: Option<PathBuf>,
    pub rfm_wrapper: Option<PathBuf>,
    pub report_top_rms: i64,
    pub log: Option<PathBuf>,
    pub rms_target: Option<f64>,
    pub priority_bands: Vec<PriorityBand>,
    pub outside_band_weight: f64,
    pub passivity: Option<PassivityPolicy>,
    pub legacy_passivity: LegacyPassivityFlags,
    pub max_order: Option<usize>,
    pub min_order: usize,
    pub max_order_step: usize,
    pub n_poles_real: usize,
    pub n_poles_cmplx: usize,
    pub fit_constant: bool,
    pub fit_proportional: bool,
    pub enforce_dc: bool,
    pub quality_profile: QualityProfile,
    pub fail_on_quality: bool,
    pub allow_quality_warnings: bool,
    pub subckt_name: String,
    pub tuning_profile: Option<PathBuf>,
    pub pole_spacing: String,
    pub fit_iterations: usize,
    pub high_frequency_complex_pairs: usize,
    pub high_frequency_pair_damping: f64,
    pub high_frequency_pair_start_fraction: f64,
    pub passivity_max_iterations: usize,
    pub passivity_samples: usize,
    pub passivity_active_variables: usize,
    /// Optional delivery reference.  When set, the input S matrix is
    /// renormalized before fitting, matching the upstream cascade path.
    pub reference_impedance: Option<f64>,
}

impl Default for FitSparamOptions {
    fn default() -> Self {
        Self {
            output: None,
            report: None,
            html_report: None,
            fitted_touchstone: None,
            rfm: None,
            rfm_wrapper: None,
            report_top_rms: 5,
            log: None,
            rms_target: None,
            priority_bands: Vec::new(),
            outside_band_weight: 0.1,
            passivity: None,
            legacy_passivity: LegacyPassivityFlags::default(),
            max_order: None,
            min_order: 1,
            max_order_step: 8,
            n_poles_real: 4,
            n_poles_cmplx: 18,
            fit_constant: true,
            fit_proportional: false,
            enforce_dc: true,
            quality_profile: QualityProfile::Explore,
            fail_on_quality: false,
            allow_quality_warnings: false,
            subckt_name: "s_equivalent".to_owned(),
            tuning_profile: None,
            pole_spacing: "log".to_owned(),
            fit_iterations: 14,
            high_frequency_complex_pairs: 2,
            high_frequency_pair_damping: 0.03,
            high_frequency_pair_start_fraction: 0.68,
            passivity_max_iterations: 3,
            passivity_samples: 8,
            passivity_active_variables: 3072,
            reference_impedance: None,
        }
    }
}

/// The exact output names derived by the pinned CLI before any fit starts.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct FitSparamArtifacts {
    pub output: PathBuf,
    pub report: PathBuf,
    pub html_report: PathBuf,
    pub fitted_touchstone: PathBuf,
    pub rfm: PathBuf,
    pub rfm_wrapper: PathBuf,
    pub log: PathBuf,
}

/// Artifacts the bounded Rust route actually publishes.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct FitSparamPublishedArtifacts {
    pub report: PathBuf,
    pub fitted_touchstone: PathBuf,
    pub log: PathBuf,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum TargetBranch {
    FullBand,
    PriorityBandOnly,
    PriorityBandAndFullBand,
}

impl TargetBranch {
    pub const fn full_band_is_blocking(self) -> bool {
        !matches!(self, Self::PriorityBandOnly)
    }
}

/// Which native Rust fit route is selected by the plan.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum KernelStatus {
    NativeVectorFitting,
}

/// A validated, side-effect-free candidate plan. It deliberately stops at
/// the pre-fit boundary: no input file is opened and no artifact is written.
#[derive(Clone, Debug, PartialEq)]
pub struct FitSparamPlan {
    pub touchstone: PathBuf,
    pub artifacts: FitSparamArtifacts,
    pub passivity: PassivityPolicy,
    pub target_branch: TargetBranch,
    pub rms_target: f64,
    pub max_order: usize,
    pub min_order: usize,
    pub max_order_step: usize,
    pub kernel_status: KernelStatus,
}

/// A parsed Touchstone 1.x S-parameter network.
///
/// Samples use row-major matrix ordering internally (`S11, S12, S21, S22` for
/// a two-port).  Touchstone 1.x stores the same matrix in column-major token
/// order, so the parser and writer are the explicit conversion boundary.
#[derive(Clone, Debug, PartialEq)]
pub struct TouchstoneNetwork {
    frequencies_hz: Vec<f64>,
    samples: Vec<Vec<Complex>>,
    ports: usize,
    reference_impedance: f64,
}

impl TouchstoneNetwork {
    pub(crate) fn from_samples(
        frequencies_hz: Vec<f64>,
        samples: Vec<Vec<Complex>>,
        ports: usize,
        reference_impedance: f64,
    ) -> Result<Self, FitSparamError> {
        if frequencies_hz.len() < 2 || frequencies_hz.len() != samples.len() {
            return Err(FitSparamError::TouchstoneFormat(
                "synthetic network requires at least two aligned samples".to_owned(),
            ));
        }
        if ports == 0 || samples.iter().any(|row| row.len() != ports * ports) {
            return Err(FitSparamError::TouchstoneFormat(
                "synthetic network response dimensions are invalid".to_owned(),
            ));
        }
        if !reference_impedance.is_finite() || reference_impedance <= 0.0 {
            return Err(FitSparamError::TouchstoneFormat(
                "synthetic network reference impedance must be finite and positive".to_owned(),
            ));
        }
        if frequencies_hz
            .iter()
            .any(|value| !value.is_finite() || *value < 0.0)
            || frequencies_hz.windows(2).any(|pair| pair[1] < pair[0])
            || samples
                .iter()
                .flatten()
                .any(|value| !finite_complex(*value))
        {
            return Err(FitSparamError::TouchstoneFormat(
                "synthetic network contains invalid samples".to_owned(),
            ));
        }
        Ok(Self {
            frequencies_hz,
            samples,
            ports,
            reference_impedance,
        })
    }

    pub fn ports(&self) -> usize {
        self.ports
    }

    pub fn sample_count(&self) -> usize {
        self.frequencies_hz.len()
    }

    pub fn frequencies_hz(&self) -> &[f64] {
        &self.frequencies_hz
    }

    pub fn samples(&self) -> &[Vec<Complex>] {
        &self.samples
    }

    pub fn reference_impedance(&self) -> f64 {
        self.reference_impedance
    }

    pub(crate) fn response_count(&self) -> usize {
        self.ports * self.ports
    }
}

/// The rational model returned after native pole relocation and residue fit.
#[derive(Clone, Debug, PartialEq)]
pub struct RationalFitModel {
    pub poles: Vec<Complex>,
    pub residues: Vec<Vec<Complex>>,
    pub constant: Vec<Complex>,
    pub proportional: Vec<Complex>,
    pub ports: usize,
    pub frequency_scale_hz: f64,
}

impl RationalFitModel {
    pub fn order(&self) -> usize {
        self.poles.len()
    }

    pub fn evaluate(&self, frequency_hz: f64) -> Vec<Complex> {
        let normalized_frequency = frequency_hz / self.frequency_scale_hz;
        let s = Complex::new(0.0, 2.0 * std::f64::consts::PI * normalized_frequency);
        (0..self.response_count())
            .map(|response| {
                let pole_sum = self
                    .poles
                    .iter()
                    .enumerate()
                    .fold(Complex::new(0.0, 0.0), |sum, (pole, value)| {
                        sum + self.residues[pole][response] / (s - *value)
                    });
                self.constant[response] + self.proportional[response] * s + pole_sum
            })
            .collect()
    }

    pub fn evaluated_samples(&self, frequencies_hz: &[f64]) -> Vec<Vec<Complex>> {
        frequencies_hz
            .iter()
            .copied()
            .map(|frequency| self.evaluate(frequency))
            .collect()
    }

    fn response_count(&self) -> usize {
        self.ports * self.ports
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum PassivityObservation {
    NotRequested,
    SampledPass,
    SampledFail,
    Indeterminate,
}

#[derive(Clone, Debug, PartialEq)]
pub struct FitTrial {
    pub requested_order: usize,
    pub effective_order: usize,
    pub rms_error: f64,
    pub mean_rms_error: f64,
    pub priority_rms_error: Option<f64>,
    pub passivity: PassivityObservation,
    pub target_met: bool,
    pub pole_relocation_iterations: usize,
}

#[derive(Clone, Debug, PartialEq)]
pub struct FitSparamResult {
    pub target_met: bool,
    pub selected_order: usize,
    pub rms_error: f64,
    pub mean_rms_error: f64,
    pub passivity: PassivityObservation,
    pub artifacts: FitSparamPublishedArtifacts,
    pub trials: Vec<FitTrial>,
    pub model: RationalFitModel,
}

/// Typed request matching the upstream adapter's AS-01 request boundary.
#[derive(Clone, Debug, PartialEq)]
pub struct FitSparamRequest {
    pub touchstone: PathBuf,
    pub options: FitSparamOptions,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum FitSparamError {
    EmptyTouchstonePath,
    MissingRmsTarget,
    NonFiniteRmsTarget,
    InvalidRmsTarget,
    UnsupportedPassivity(String),
    ConflictingPassivityFlags,
    NonFinitePriorityBand,
    InvalidPriorityBandRange,
    InvalidPriorityBandTarget,
    InvalidPriorityBandWeight,
    InvalidOutsideBandWeight,
    InvalidOrder,
    InvalidOrderStep,
    InvalidReportTopRms,
    EmptySubcircuitName,
    WhitespaceInSubcircuitName,
    UnsupportedPoleSpacing(String),
    InvalidFitIterations,
    InvalidPassivityBudget,
    NonFiniteTuningValue,
    UnsupportedPortCount(usize),
    TouchstoneIo(String),
    TouchstoneFormat(String),
    FitNumericalFailure(String),
    OutputIo(String),
    PassivityEnforceNotImplemented,
    DuplicateOutputPath(String),
    UnsupportedExecutionOption(&'static str),
    BudgetExceeded {
        kind: &'static str,
        limit: usize,
        actual: usize,
    },
}

impl Display for FitSparamError {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::EmptyTouchstonePath => formatter.write_str("touchstone path must not be empty"),
            Self::MissingRmsTarget => {
                formatter.write_str("--rms-target is required without --priority-band")
            }
            Self::NonFiniteRmsTarget => formatter.write_str("rms target must be finite"),
            Self::InvalidRmsTarget => formatter.write_str("rms target must be > 0"),
            Self::UnsupportedPassivity(value) => {
                write!(formatter, "unsupported passivity policy '{value}'")
            }
            Self::ConflictingPassivityFlags => {
                formatter.write_str("--passivity cannot be combined with legacy passivity flags")
            }
            Self::NonFinitePriorityBand => {
                formatter.write_str("priority band values must be finite")
            }
            Self::InvalidPriorityBandRange => {
                formatter.write_str("priority band must satisfy 0 <= F_MIN < F_MAX")
            }
            Self::InvalidPriorityBandTarget => {
                formatter.write_str("priority band RMS target must be > 0")
            }
            Self::InvalidPriorityBandWeight => {
                formatter.write_str("priority band weight must be > 0")
            }
            Self::InvalidOutsideBandWeight => {
                formatter.write_str("outside-band weight must be finite and > 0")
            }
            Self::InvalidOrder => formatter.write_str("min/max order must be positive and ordered"),
            Self::InvalidOrderStep => formatter.write_str("max order step must be >= 1"),
            Self::InvalidReportTopRms => formatter.write_str("report-top-rms must be >= 0"),
            Self::EmptySubcircuitName => formatter.write_str("subcircuit name must not be empty"),
            Self::WhitespaceInSubcircuitName => {
                formatter.write_str("subcircuit name must be a SPICE token")
            }
            Self::UnsupportedPoleSpacing(value) => {
                write!(formatter, "unsupported pole spacing '{value}'")
            }
            Self::InvalidFitIterations => formatter.write_str("fit iterations must be >= 1"),
            Self::InvalidPassivityBudget => formatter.write_str("passivity budgets must be >= 1"),
            Self::NonFiniteTuningValue => formatter.write_str("tuning values must be finite"),
            Self::UnsupportedPortCount(value) => {
                write!(
                    formatter,
                    "AS-01 minimal Rust route supports only two ports, got {value}"
                )
            }
            Self::TouchstoneIo(value) => write!(formatter, "Touchstone I/O failed: {value}"),
            Self::TouchstoneFormat(value) => {
                write!(formatter, "Touchstone format is unsupported: {value}")
            }
            Self::FitNumericalFailure(value) => write!(formatter, "fit numerical failure: {value}"),
            Self::OutputIo(value) => write!(formatter, "artifact output failed: {value}"),
            Self::PassivityEnforceNotImplemented => formatter.write_str(
                "passivity enforcement remains outside the AS-01 minimal support matrix",
            ),
            Self::DuplicateOutputPath(value) => {
                write!(formatter, "output paths must be distinct: {value}")
            }
            Self::UnsupportedExecutionOption(option) => {
                write!(
                    formatter,
                    "{option} is not implemented by the bounded Rust fit route"
                )
            }
            Self::BudgetExceeded {
                kind,
                limit,
                actual,
            } => write!(
                formatter,
                "{kind} budget exceeded: limit={limit}, actual={actual}"
            ),
        }
    }
}

impl std::error::Error for FitSparamError {}

impl FitSparamRequest {
    pub fn new(
        touchstone: impl Into<PathBuf>,
        options: FitSparamOptions,
    ) -> Result<Self, FitSparamError> {
        let touchstone = touchstone.into();
        if touchstone.as_os_str().is_empty() {
            return Err(FitSparamError::EmptyTouchstonePath);
        }
        Ok(Self {
            touchstone,
            options,
        })
    }

    pub fn plan(&self) -> Result<FitSparamPlan, FitSparamError> {
        plan_fit_sparam(self.touchstone.clone(), self.options.clone())
    }
}

/// Resolve the pinned explicit/legacy passivity precedence without fitting.
pub fn resolve_passivity(
    explicit: Option<PassivityPolicy>,
    legacy: LegacyPassivityFlags,
) -> Result<PassivityPolicy, FitSparamError> {
    if explicit.is_some() && legacy.any() {
        return Err(FitSparamError::ConflictingPassivityFlags);
    }
    Ok(match explicit {
        Some(value) => value,
        None if legacy.enforce => PassivityPolicy::Enforce,
        None if legacy.skip_check => PassivityPolicy::Off,
        _ => PassivityPolicy::Check,
    })
}

fn validate_options(options: &FitSparamOptions) -> Result<(), FitSparamError> {
    if !options.outside_band_weight.is_finite() || options.outside_band_weight <= 0.0 {
        return Err(FitSparamError::InvalidOutsideBandWeight);
    }
    if options.report_top_rms < 0 {
        return Err(FitSparamError::InvalidReportTopRms);
    }
    if options.min_order == 0
        || options.max_order == Some(0)
        || options.max_order.is_some_and(|max| options.min_order > max)
    {
        return Err(FitSparamError::InvalidOrder);
    }
    let max_order = options.max_order.unwrap_or(MAX_FIT_ORDER);
    if max_order > MAX_FIT_ORDER {
        return Err(FitSparamError::BudgetExceeded {
            kind: "fit order",
            limit: MAX_FIT_ORDER,
            actual: max_order,
        });
    }
    if options.max_order_step == 0 {
        return Err(FitSparamError::InvalidOrderStep);
    }
    if options.max_order_step > MAX_ORDER_STEP {
        return Err(FitSparamError::BudgetExceeded {
            kind: "order step",
            limit: MAX_ORDER_STEP,
            actual: options.max_order_step,
        });
    }
    if options.priority_bands.len() > MAX_PRIORITY_BANDS {
        return Err(FitSparamError::BudgetExceeded {
            kind: "priority band count",
            limit: MAX_PRIORITY_BANDS,
            actual: options.priority_bands.len(),
        });
    }
    if options.subckt_name.is_empty() {
        return Err(FitSparamError::EmptySubcircuitName);
    }
    if options.subckt_name.chars().any(char::is_whitespace) {
        return Err(FitSparamError::WhitespaceInSubcircuitName);
    }
    if options.pole_spacing != "lin"
        && options.pole_spacing != "log"
        && options.pole_spacing != "resonance"
    {
        return Err(FitSparamError::UnsupportedPoleSpacing(
            options.pole_spacing.clone(),
        ));
    }
    if options.fit_iterations == 0 {
        return Err(FitSparamError::InvalidFitIterations);
    }
    if options.passivity_max_iterations == 0
        || options.passivity_samples == 0
        || options.passivity_active_variables == 0
    {
        return Err(FitSparamError::InvalidPassivityBudget);
    }
    if !options.high_frequency_pair_damping.is_finite()
        || !options.high_frequency_pair_start_fraction.is_finite()
    {
        return Err(FitSparamError::NonFiniteTuningValue);
    }
    for band in &options.priority_bands {
        PriorityBand::new(band.f_min_hz, band.f_max_hz, band.rms_target, band.weight)?;
    }
    Ok(())
}

fn validate_execution_options(options: &FitSparamOptions) -> Result<(), FitSparamError> {
    if options
        .reference_impedance
        .is_some_and(|value| !value.is_finite() || value <= 0.0)
    {
        return Err(FitSparamError::UnsupportedExecutionOption(
            "--reference-impedance",
        ));
    }
    if options.output.is_some() {
        return Err(FitSparamError::UnsupportedExecutionOption("--output"));
    }
    if options.html_report.is_some() {
        return Err(FitSparamError::UnsupportedExecutionOption("--html-report"));
    }
    if options.rfm.is_some() {
        return Err(FitSparamError::UnsupportedExecutionOption("--rfm"));
    }
    if options.rfm_wrapper.is_some() {
        return Err(FitSparamError::UnsupportedExecutionOption("--rfm-wrapper"));
    }
    if options.report_top_rms != 5 {
        return Err(FitSparamError::UnsupportedExecutionOption(
            "--report-top-rms",
        ));
    }
    if options.outside_band_weight.to_bits() != 0.1_f64.to_bits() {
        return Err(FitSparamError::UnsupportedExecutionOption(
            "--outside-band-weight",
        ));
    }
    if options.priority_bands.iter().any(|band| band.weight != 1.0) {
        return Err(FitSparamError::UnsupportedExecutionOption(
            "weighted --priority-band",
        ));
    }
    if options.quality_profile != QualityProfile::Explore {
        return Err(FitSparamError::UnsupportedExecutionOption(
            "--quality-profile",
        ));
    }
    if options.fail_on_quality {
        return Err(FitSparamError::UnsupportedExecutionOption(
            "--fail-on-quality",
        ));
    }
    if options.allow_quality_warnings {
        return Err(FitSparamError::UnsupportedExecutionOption(
            "--allow-quality-warnings",
        ));
    }
    if options.subckt_name != "s_equivalent" {
        return Err(FitSparamError::UnsupportedExecutionOption("--subckt-name"));
    }
    if options.tuning_profile.is_some() {
        return Err(FitSparamError::UnsupportedExecutionOption(
            "--tuning-profile",
        ));
    }
    if options.pole_spacing == "resonance" {
        return Err(FitSparamError::UnsupportedExecutionOption(
            "--pole-spacing resonance",
        ));
    }
    if options.fit_iterations != 14 {
        return Err(FitSparamError::UnsupportedExecutionOption(
            "--fit-iterations",
        ));
    }
    if options.high_frequency_complex_pairs != 2
        || options.high_frequency_pair_damping.to_bits() != 0.03_f64.to_bits()
        || options.high_frequency_pair_start_fraction.to_bits() != 0.68_f64.to_bits()
    {
        return Err(FitSparamError::UnsupportedExecutionOption("--hf-*"));
    }
    if options.passivity_max_iterations != 3
        || options.passivity_samples != 8
        || options.passivity_active_variables != 3072
    {
        return Err(FitSparamError::UnsupportedExecutionOption("--passivity-*"));
    }
    Ok(())
}

fn target_from_options(options: &FitSparamOptions) -> Result<(TargetBranch, f64), FitSparamError> {
    let target = match options.rms_target {
        Some(value) if !value.is_finite() => return Err(FitSparamError::NonFiniteRmsTarget),
        Some(value) if value <= 0.0 => return Err(FitSparamError::InvalidRmsTarget),
        Some(value) => value,
        None if options.priority_bands.is_empty() => return Err(FitSparamError::MissingRmsTarget),
        None => options
            .priority_bands
            .iter()
            .map(|band| band.rms_target)
            .fold(f64::INFINITY, f64::min),
    };
    let branch = match (
        options.priority_bands.is_empty(),
        options.rms_target.is_some(),
    ) {
        (true, true) => TargetBranch::FullBand,
        (false, false) => TargetBranch::PriorityBandOnly,
        (false, true) => TargetBranch::PriorityBandAndFullBand,
        (true, false) => unreachable!("missing target returned above"),
    };
    Ok((branch, target))
}

fn replace_suffix(path: PathBuf, suffix: Option<&str>) -> PathBuf {
    match suffix {
        Some(value) if !value.is_empty() => path.with_extension(value),
        _ => path,
    }
}

fn derive_artifacts(
    touchstone: &std::path::Path,
    options: &FitSparamOptions,
) -> FitSparamArtifacts {
    let output_was_defaulted = options.output.is_none();
    let output = options.output.clone().unwrap_or_else(|| {
        touchstone.with_file_name(format!(
            "{}_fitted.sp",
            touchstone
                .file_stem()
                .and_then(|stem| stem.to_str())
                .unwrap_or("input")
        ))
    });
    let output_stem = output
        .file_stem()
        .and_then(|stem| stem.to_str())
        .unwrap_or("model");
    let report = options.report.clone().unwrap_or_else(|| {
        if output_was_defaulted {
            output.with_file_name(format!("{output_stem}_report.json"))
        } else {
            output
                .parent()
                .unwrap_or_else(|| std::path::Path::new("."))
                .join("fit_report.json")
        }
    });
    let html_report = options.html_report.clone().unwrap_or_else(|| {
        if output_was_defaulted {
            output.with_file_name(format!("{output_stem}_report.html"))
        } else {
            output
                .parent()
                .unwrap_or_else(|| std::path::Path::new("."))
                .join("fit_report.html")
        }
    });
    let log = options.log.clone().unwrap_or_else(|| {
        report
            .parent()
            .unwrap_or_else(|| std::path::Path::new("."))
            .join(format!(
                "{}.log",
                touchstone
                    .file_stem()
                    .and_then(|stem| stem.to_str())
                    .unwrap_or("input")
            ))
    });
    let fitted_touchstone = options.fitted_touchstone.clone().unwrap_or_else(|| {
        replace_suffix(
            output.clone(),
            touchstone
                .extension()
                .and_then(|extension| extension.to_str()),
        )
    });
    let rfm = options
        .rfm
        .clone()
        .unwrap_or_else(|| output.with_extension("rfm"));
    let rfm_wrapper = options.rfm_wrapper.clone().unwrap_or_else(|| {
        let stem = rfm
            .file_stem()
            .and_then(|value| value.to_str())
            .unwrap_or("model");
        rfm.with_file_name(format!("{stem}_rfm_wrapper.sp"))
    });
    FitSparamArtifacts {
        output,
        report,
        html_report,
        fitted_touchstone,
        rfm,
        rfm_wrapper,
        log,
    }
}

/// Validate the upstream request boundary and derive its artifact names.
/// This is deliberately side-effect free and does not claim a fit result.
pub fn plan_fit_sparam(
    touchstone: impl Into<PathBuf>,
    options: FitSparamOptions,
) -> Result<FitSparamPlan, FitSparamError> {
    let touchstone = touchstone.into();
    if touchstone.as_os_str().is_empty() {
        return Err(FitSparamError::EmptyTouchstonePath);
    }
    validate_options(&options)?;
    let (target_branch, rms_target) = target_from_options(&options)?;
    Ok(FitSparamPlan {
        artifacts: derive_artifacts(&touchstone, &options),
        touchstone,
        passivity: resolve_passivity(options.passivity, options.legacy_passivity)?,
        target_branch,
        rms_target,
        max_order: options.max_order.unwrap_or(MAX_FIT_ORDER),
        min_order: options.min_order,
        max_order_step: options.max_order_step,
        kernel_status: KernelStatus::NativeVectorFitting,
    })
}

/// Read the pinned lightweight Touchstone 1.x syntax used by Agent-Spice.
///
/// The loader intentionally accepts only S-parameter files with an option
/// line and the classic RI/MA/DB pair formats. Touchstone 2.0 bracket
/// sections and mixed parameter blocks are rejected rather than guessed.
pub fn read_touchstone(
    path: impl AsRef<std::path::Path>,
) -> Result<TouchstoneNetwork, FitSparamError> {
    read_touchstone_with_port_policy(path, false)
}

/// AS-05's S-element preflight uses the same bounded parser for arbitrary
/// n-port files.  The public AS-01 reader retains its historical two-port
/// admission boundary for compatibility, while this crate-local route keeps
/// the actual S-domain fit available to n-port dispatch.
pub(crate) fn read_touchstone_multiport(
    path: impl AsRef<std::path::Path>,
) -> Result<TouchstoneNetwork, FitSparamError> {
    read_touchstone_with_port_policy(path, true)
}

fn read_touchstone_with_port_policy(
    path: impl AsRef<std::path::Path>,
    allow_multiport: bool,
) -> Result<TouchstoneNetwork, FitSparamError> {
    let path = path.as_ref();
    let ports = infer_touchstone_ports(path)?;
    if !allow_multiport && ports != 2 {
        return Err(FitSparamError::UnsupportedPortCount(ports));
    }
    let file = File::open(path).map_err(|error| FitSparamError::TouchstoneIo(error.to_string()))?;
    let mut bytes = Vec::new();
    file.take((MAX_TOUCHSTONE_BYTES + 1) as u64)
        .read_to_end(&mut bytes)
        .map_err(|error| FitSparamError::TouchstoneIo(error.to_string()))?;
    if bytes.len() > MAX_TOUCHSTONE_BYTES {
        return Err(FitSparamError::BudgetExceeded {
            kind: "Touchstone input bytes",
            limit: MAX_TOUCHSTONE_BYTES,
            actual: bytes.len(),
        });
    }
    if bytes.iter().any(|byte| !byte.is_ascii()) {
        return Err(FitSparamError::TouchstoneFormat(
            "input must be ASCII Touchstone 1.x text".to_owned(),
        ));
    }
    let text = std::str::from_utf8(&bytes)
        .map_err(|error| FitSparamError::TouchstoneFormat(error.to_string()))?;
    let expected = 1usize
        .checked_add(2usize.saturating_mul(ports.saturating_mul(ports)))
        .ok_or_else(|| FitSparamError::TouchstoneFormat("port count is too large".to_owned()))?;
    let mut unit_scale = None;
    let mut data_format = None;
    let mut reference_impedance = 50.0;
    let mut header_seen = false;
    let mut pending = Vec::new();
    let mut frequencies_hz = Vec::new();
    let mut samples = Vec::new();

    for raw_line in text.lines() {
        if raw_line.len() > MAX_TOUCHSTONE_LINE_BYTES {
            return Err(FitSparamError::BudgetExceeded {
                kind: "Touchstone line bytes",
                limit: MAX_TOUCHSTONE_LINE_BYTES,
                actual: raw_line.len(),
            });
        }
        let without_comment = raw_line.split_once('!').map_or(raw_line, |(line, _)| line);
        let line = without_comment.trim();
        if line.is_empty() {
            continue;
        }
        if line.starts_with('[') {
            return Err(FitSparamError::TouchstoneFormat(
                "Touchstone 2.0 bracket sections are unsupported".to_owned(),
            ));
        }
        if line.starts_with('#') {
            if header_seen {
                return Err(FitSparamError::TouchstoneFormat(
                    "multiple option lines are unsupported".to_owned(),
                ));
            }
            let tokens = line.split_whitespace().collect::<Vec<_>>();
            if tokens.len() < 4 || tokens[0] != "#" {
                return Err(FitSparamError::TouchstoneFormat(
                    "option line must contain unit, parameter, and format".to_owned(),
                ));
            }
            unit_scale = Some(match tokens[1].to_ascii_lowercase().as_str() {
                "hz" => 1.0,
                "khz" => 1.0e3,
                "mhz" => 1.0e6,
                "ghz" => 1.0e9,
                other => {
                    return Err(FitSparamError::TouchstoneFormat(format!(
                        "unsupported frequency unit '{other}'"
                    )));
                }
            });
            if !tokens[2].eq_ignore_ascii_case("s") {
                return Err(FitSparamError::TouchstoneFormat(
                    "only S-parameters are supported".to_owned(),
                ));
            }
            data_format = Some(match tokens[3].to_ascii_lowercase().as_str() {
                "ri" => TouchstoneDataFormat::Ri,
                "ma" => TouchstoneDataFormat::Ma,
                "db" => TouchstoneDataFormat::Db,
                other => {
                    return Err(FitSparamError::TouchstoneFormat(format!(
                        "unsupported data format '{other}'"
                    )));
                }
            });
            let mut index = 4;
            while index < tokens.len() {
                if tokens[index].eq_ignore_ascii_case("r") {
                    let value = tokens.get(index + 1).ok_or_else(|| {
                        FitSparamError::TouchstoneFormat("R requires an impedance".to_owned())
                    })?;
                    reference_impedance = value.parse::<f64>().map_err(|_| {
                        FitSparamError::TouchstoneFormat("R impedance is not numeric".to_owned())
                    })?;
                    index += 2;
                } else {
                    return Err(FitSparamError::TouchstoneFormat(format!(
                        "unexpected option token '{}'",
                        tokens[index]
                    )));
                }
            }
            header_seen = true;
            continue;
        }
        if !header_seen {
            return Err(FitSparamError::TouchstoneFormat(
                "option line must precede network data".to_owned(),
            ));
        }
        for token in line.split_whitespace() {
            let value = token.parse::<f64>().map_err(|_| {
                FitSparamError::TouchstoneFormat(format!("non-numeric data token '{token}'"))
            })?;
            if !value.is_finite() {
                return Err(FitSparamError::TouchstoneFormat(
                    "network data must be finite".to_owned(),
                ));
            }
            pending.push(value);
        }
        while pending.len() >= expected {
            let row = pending.drain(..expected).collect::<Vec<_>>();
            let scale = unit_scale.expect("header_seen fixes the option line");
            let frequency = row[0] * scale;
            if frequency < 0.0 || !frequency.is_finite() {
                return Err(FitSparamError::TouchstoneFormat(
                    "frequency must be finite and non-negative".to_owned(),
                ));
            }
            let format = data_format.expect("header_seen fixes the data format");
            let mut response = vec![Complex::new(0.0, 0.0); ports * ports];
            for (token_index, pair) in row[1..].chunks_exact(2).enumerate() {
                let value = match format {
                    TouchstoneDataFormat::Ri => Complex::new(pair[0], pair[1]),
                    TouchstoneDataFormat::Ma => {
                        let radians = pair[1].to_radians();
                        Complex::new(pair[0] * radians.cos(), pair[0] * radians.sin())
                    }
                    TouchstoneDataFormat::Db => {
                        let radians = pair[1].to_radians();
                        let magnitude = 10.0_f64.powf(pair[0] / 20.0);
                        Complex::new(magnitude * radians.cos(), magnitude * radians.sin())
                    }
                };
                // Touchstone emits columns first: token k is matrix
                // (row=k%N, column=k/N).  Keep the fitter's row-major view.
                let row_index = token_index % ports;
                let column_index = token_index / ports;
                response[row_index * ports + column_index] = value;
            }
            frequencies_hz.push(frequency);
            samples.push(response);
            if samples.len() > MAX_TOUCHSTONE_SAMPLES {
                return Err(FitSparamError::BudgetExceeded {
                    kind: "Touchstone sample count",
                    limit: MAX_TOUCHSTONE_SAMPLES,
                    actual: samples.len(),
                });
            }
        }
    }
    if !header_seen {
        return Err(FitSparamError::TouchstoneFormat(
            "missing Touchstone option line".to_owned(),
        ));
    }
    if !pending.is_empty() {
        return Err(FitSparamError::TouchstoneFormat(
            "incomplete Touchstone data row".to_owned(),
        ));
    }
    if samples.len() < 2 {
        return Err(FitSparamError::TouchstoneFormat(
            "at least two network samples are required".to_owned(),
        ));
    }
    if reference_impedance <= 0.0 || !reference_impedance.is_finite() {
        return Err(FitSparamError::TouchstoneFormat(
            "reference impedance must be finite and positive".to_owned(),
        ));
    }
    if frequencies_hz.windows(2).any(|pair| pair[1] < pair[0]) {
        return Err(FitSparamError::TouchstoneFormat(
            "frequency rows must be non-decreasing".to_owned(),
        ));
    }
    Ok(TouchstoneNetwork {
        frequencies_hz,
        samples,
        ports,
        reference_impedance,
    })
}

fn invert_complex_matrix(value: &[Complex], n: usize) -> Option<Vec<Complex>> {
    if n == 0 || value.len() != n * n {
        return None;
    }
    let mut augmented = vec![Complex::new(0.0, 0.0); n * 2 * n];
    for row in 0..n {
        for column in 0..n {
            augmented[row * 2 * n + column] = value[row * n + column];
            augmented[row * 2 * n + n + column] = if row == column {
                Complex::new(1.0, 0.0)
            } else {
                Complex::new(0.0, 0.0)
            };
        }
    }
    for column in 0..n {
        let pivot = (column..n).max_by(|left, right| {
            augmented[*left * 2 * n + column]
                .norm()
                .total_cmp(&augmented[*right * 2 * n + column].norm())
        })?;
        let pivot_value = augmented[pivot * 2 * n + column];
        if !pivot_value.re.is_finite()
            || !pivot_value.im.is_finite()
            || pivot_value.norm() <= f64::MIN_POSITIVE
        {
            return None;
        }
        if pivot != column {
            for index in 0..2 * n {
                augmented.swap(pivot * 2 * n + index, column * 2 * n + index);
            }
        }
        let pivot_value = augmented[column * 2 * n + column];
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
    let mut result = Vec::with_capacity(n * n);
    for row in 0..n {
        for column in 0..n {
            result.push(augmented[row * 2 * n + n + column]);
        }
    }
    Some(result)
}

/// Renormalize a row-major S matrix from the source scalar reference to the
/// requested scalar reference.  The upstream cascade explicitly performs
/// this before fitting and ABCD composition; rejecting a singular sample is
/// safer than silently publishing an unrenormalized cascade.
pub(crate) fn renormalize_network(
    network: &TouchstoneNetwork,
    target_impedance: f64,
) -> Result<TouchstoneNetwork, FitSparamError> {
    if !target_impedance.is_finite() || target_impedance <= 0.0 {
        return Err(FitSparamError::TouchstoneFormat(
            "target reference impedance must be finite and positive".to_owned(),
        ));
    }
    if (network.reference_impedance - target_impedance).abs() <= 1e-12 * target_impedance.max(1.0) {
        return Ok(network.clone());
    }
    let n = network.ports;
    let mut samples = Vec::with_capacity(network.samples.len());
    for sample in &network.samples {
        let identity = (0..n * n)
            .map(|index| {
                if index / n == index % n {
                    Complex::new(1.0, 0.0)
                } else {
                    Complex::new(0.0, 0.0)
                }
            })
            .collect::<Vec<_>>();
        let plus = identity
            .iter()
            .zip(sample)
            .map(|(one, value)| *one + *value)
            .collect::<Vec<_>>();
        let minus = identity
            .iter()
            .zip(sample)
            .map(|(one, value)| *one - *value)
            .collect::<Vec<_>>();
        let Some(minus_inverse) = invert_complex_matrix(&minus, n) else {
            return Err(FitSparamError::FitNumericalFailure(
                "S renormalization encountered singular I-S".to_owned(),
            ));
        };
        let mut z = Vec::with_capacity(n * n);
        for row in 0..n {
            for column in 0..n {
                z.push(
                    network.reference_impedance
                        * (0..n)
                            .map(|inner| plus[row * n + inner] * minus_inverse[inner * n + column])
                            .sum::<Complex>(),
                );
            }
        }
        let denominator = z
            .iter()
            .enumerate()
            .map(|(index, value)| {
                *value
                    + if index / n == index % n {
                        Complex::new(target_impedance, 0.0)
                    } else {
                        Complex::new(0.0, 0.0)
                    }
            })
            .collect::<Vec<_>>();
        let Some(denominator_inverse) = invert_complex_matrix(&denominator, n) else {
            return Err(FitSparamError::FitNumericalFailure(
                "S renormalization encountered singular Z+target*I".to_owned(),
            ));
        };
        let numerator = z
            .iter()
            .enumerate()
            .map(|(index, value)| {
                *value
                    - if index / n == index % n {
                        Complex::new(target_impedance, 0.0)
                    } else {
                        Complex::new(0.0, 0.0)
                    }
            })
            .collect::<Vec<_>>();
        let mut renormalized = Vec::with_capacity(n * n);
        for row in 0..n {
            for column in 0..n {
                renormalized.push(
                    (0..n)
                        .map(|inner| {
                            numerator[row * n + inner] * denominator_inverse[inner * n + column]
                        })
                        .sum::<Complex>(),
                );
            }
        }
        samples.push(renormalized);
    }
    TouchstoneNetwork::from_samples(
        network.frequencies_hz.clone(),
        samples,
        network.ports,
        target_impedance,
    )
}

#[derive(Clone, Copy)]
enum TouchstoneDataFormat {
    Ri,
    Ma,
    Db,
}

fn infer_touchstone_ports(path: &std::path::Path) -> Result<usize, FitSparamError> {
    let name = path
        .file_name()
        .and_then(|value| value.to_str())
        .ok_or_else(|| FitSparamError::TouchstoneFormat("input filename is not UTF-8".to_owned()))?
        .to_ascii_lowercase();
    let marker = name
        .rfind(".s")
        .ok_or_else(|| FitSparamError::TouchstoneFormat("filename must end in .sNp".to_owned()))?;
    let suffix = &name[marker + 2..];
    let digits = suffix
        .strip_suffix('p')
        .ok_or_else(|| FitSparamError::TouchstoneFormat("filename must end in .sNp".to_owned()))?;
    if digits.is_empty() || !digits.chars().all(|value| value.is_ascii_digit()) {
        return Err(FitSparamError::TouchstoneFormat(
            "filename must contain a numeric port count".to_owned(),
        ));
    }
    let ports = digits.parse::<usize>().map_err(|_| {
        FitSparamError::TouchstoneFormat("port count is outside the supported range".to_owned())
    })?;
    if ports == 0 {
        return Err(FitSparamError::TouchstoneFormat(
            "port count must be positive".to_owned(),
        ));
    }
    Ok(ports)
}

#[derive(Clone, Copy)]
pub(crate) enum BasisKind {
    RealPole(usize),
    ComplexReal(usize),
    ComplexImag(usize),
    Constant,
    Proportional,
}

fn network_frequency_scale(network: &TouchstoneNetwork) -> f64 {
    let scale = network.frequencies_hz.iter().sum::<f64>() / network.sample_count() as f64;
    if scale.is_finite() && scale > 0.0 {
        scale
    } else {
        1.0
    }
}

pub(crate) fn initial_poles(
    frequencies_hz: &[f64],
    real_count: usize,
    complex_pairs: usize,
    spacing: &str,
    frequency_scale_hz: f64,
) -> Result<(Vec<Complex>, Vec<BasisKind>), FitSparamError> {
    if frequencies_hz.len() < 2 {
        return Err(FitSparamError::FitNumericalFailure(
            "at least two samples are required to initialize poles".to_owned(),
        ));
    }
    let fmax = *frequencies_hz.last().unwrap_or(&0.0) / frequency_scale_hz;
    let mut fmin = frequencies_hz[0];
    if fmin == 0.0 {
        fmin = frequencies_hz[1] / 1000.0;
    }
    fmin /= frequency_scale_hz;
    if fmin <= 0.0 || fmax <= 0.0 || !fmin.is_finite() || !fmax.is_finite() {
        return Err(FitSparamError::FitNumericalFailure(
            "frequency range must contain positive finite values".to_owned(),
        ));
    }
    let total = real_count.saturating_add(complex_pairs);
    if total == 0 {
        return Err(FitSparamError::FitNumericalFailure(
            "order must contain at least one pole".to_owned(),
        ));
    }
    let frequencies = |count: usize| -> Vec<f64> {
        if count == 1 {
            return vec![fmax];
        }
        (0..count)
            .map(|index| {
                let ratio = index as f64 / (count - 1) as f64;
                match spacing {
                    "lin" => fmin + (fmax - fmin) * ratio,
                    _ => fmin * (fmax / fmin).powf(ratio),
                }
            })
            .collect()
    };
    let real_frequencies = frequencies(real_count);
    let complex_frequencies = frequencies(complex_pairs);
    let mut poles = Vec::with_capacity(real_count + complex_pairs * 2);
    let mut basis = Vec::with_capacity(real_count + complex_pairs * 2);
    for frequency in real_frequencies {
        let index = poles.len();
        poles.push(Complex::new(-2.0 * std::f64::consts::PI * frequency, 0.0));
        basis.push(BasisKind::RealPole(index));
    }
    for frequency in complex_frequencies {
        let omega = 2.0 * std::f64::consts::PI * frequency;
        let index = poles.len();
        let pole = Complex::new(-0.01 * omega, omega);
        poles.push(pole);
        poles.push(pole.conj());
        basis.push(BasisKind::ComplexReal(index));
        basis.push(BasisKind::ComplexImag(index));
    }
    Ok((poles, basis))
}

fn basis_value(kind: BasisKind, poles: &[Complex], s: Complex) -> Complex {
    match kind {
        BasisKind::RealPole(index) => Complex::new(1.0, 0.0) / (s - poles[index]),
        BasisKind::ComplexReal(index) => {
            Complex::new(1.0, 0.0) / (s - poles[index])
                + Complex::new(1.0, 0.0) / (s - poles[index + 1])
        }
        BasisKind::ComplexImag(index) => {
            let imaginary = Complex::new(0.0, 1.0);
            imaginary / (s - poles[index]) - imaginary / (s - poles[index + 1])
        }
        BasisKind::Constant => Complex::new(1.0, 0.0),
        BasisKind::Proportional => s,
    }
}

fn finite_complex(value: Complex) -> bool {
    value.re.is_finite() && value.im.is_finite()
}

pub(crate) fn fit_residues(
    network: &TouchstoneNetwork,
    poles: &[Complex],
    basis: &[BasisKind],
    options: &FitSparamOptions,
) -> Result<RationalFitModel, FitSparamError> {
    let frequency_scale_hz = network_frequency_scale(network);
    let dc_constrained = options.enforce_dc
        && options.fit_constant
        && network
            .frequencies_hz
            .first()
            .is_some_and(|value| *value == 0.0);
    let active = basis
        .iter()
        .enumerate()
        .filter(|(_, kind)| !(dc_constrained && matches!(kind, BasisKind::Constant)))
        .map(|(index, _)| index)
        .collect::<Vec<_>>();
    let rows = if dc_constrained {
        1..network.sample_count()
    } else {
        0..network.sample_count()
    };
    let sample_indices = rows.collect::<Vec<_>>();
    if active.is_empty() || sample_indices.is_empty() {
        return Err(FitSparamError::FitNumericalFailure(
            "the selected pole basis has no solvable rows".to_owned(),
        ));
    }
    let row_count = sample_indices
        .len()
        .checked_mul(2)
        .ok_or(FitSparamError::BudgetExceeded {
            kind: "least-squares rows",
            limit: MAX_TOUCHSTONE_SAMPLES * 2,
            actual: usize::MAX,
        })?;
    let column_count = active
        .len()
        .checked_mul(2)
        .ok_or(FitSparamError::BudgetExceeded {
            kind: "least-squares columns",
            limit: MAX_REAL_MATRIX_COLUMNS,
            actual: usize::MAX,
        })?;
    if row_count > MAX_REAL_MATRIX_ROWS {
        return Err(FitSparamError::BudgetExceeded {
            kind: "least-squares rows",
            limit: MAX_REAL_MATRIX_ROWS,
            actual: row_count,
        });
    }
    if column_count > MAX_REAL_MATRIX_COLUMNS {
        return Err(FitSparamError::BudgetExceeded {
            kind: "least-squares columns",
            limit: MAX_REAL_MATRIX_COLUMNS,
            actual: column_count,
        });
    }
    if column_count > row_count {
        return Err(FitSparamError::FitNumericalFailure(format!(
            "order basis has {column_count} real columns but only {row_count} real rows"
        )));
    }
    let matrix_cells =
        row_count
            .checked_mul(column_count)
            .ok_or(FitSparamError::BudgetExceeded {
                kind: "least-squares matrix cells",
                limit: MAX_REAL_MATRIX_CELLS,
                actual: usize::MAX,
            })?;
    if matrix_cells > MAX_REAL_MATRIX_CELLS {
        return Err(FitSparamError::BudgetExceeded {
            kind: "least-squares matrix cells",
            limit: MAX_REAL_MATRIX_CELLS,
            actual: matrix_cells,
        });
    }
    let response_count = network.response_count();
    let mut scales = Vec::with_capacity(active.len());
    for basis_index in &active {
        let norm = sample_indices
            .iter()
            .map(|sample| {
                basis_value(
                    basis[*basis_index],
                    poles,
                    Complex::new(
                        0.0,
                        2.0 * std::f64::consts::PI * network.frequencies_hz[*sample]
                            / frequency_scale_hz,
                    ),
                )
                .norm_sqr()
            })
            .sum::<f64>()
            .sqrt();
        if !norm.is_finite() || norm == 0.0 {
            return Err(FitSparamError::FitNumericalFailure(
                "a rational basis column has zero or non-finite norm".to_owned(),
            ));
        }
        scales.push(1.0 / norm);
    }
    let system = Mat::from_fn(row_count, column_count, |row, column| {
        let sample = sample_indices[row / 2];
        let value = basis_value(
            basis[active[column / 2]],
            poles,
            Complex::new(
                0.0,
                2.0 * std::f64::consts::PI * network.frequencies_hz[sample] / frequency_scale_hz,
            ),
        ) * scales[column / 2];
        if row % 2 == 0 {
            if column % 2 == 0 { value.re } else { -value.im }
        } else if column % 2 == 0 {
            value.im
        } else {
            value.re
        }
    });
    let response = Mat::from_fn(row_count, response_count, |row, column| {
        let value = network.samples[sample_indices[row / 2]][column];
        if row % 2 == 0 { value.re } else { value.im }
    });
    let solved = system.as_ref().col_piv_qr().solve_lstsq(response.as_ref());
    let mut coefficients = vec![vec![Complex::new(0.0, 0.0); response_count]; basis.len()];
    for (active_index, basis_index) in active.iter().enumerate() {
        for response_index in 0..response_count {
            let value = Complex::new(
                solved[(2 * active_index, response_index)] * scales[active_index],
                solved[(2 * active_index + 1, response_index)] * scales[active_index],
            );
            if !finite_complex(value) {
                return Err(FitSparamError::FitNumericalFailure(
                    "least-squares coefficients are non-finite".to_owned(),
                ));
            }
            coefficients[*basis_index][response_index] = value;
        }
    }
    let mut residues = vec![vec![Complex::new(0.0, 0.0); response_count]; poles.len()];
    let mut constant = vec![Complex::new(0.0, 0.0); response_count];
    let mut proportional = vec![Complex::new(0.0, 0.0); response_count];
    for (basis_index, kind) in basis.iter().enumerate() {
        match kind {
            BasisKind::RealPole(pole) => {
                residues[*pole] = coefficients[basis_index].clone();
            }
            BasisKind::ComplexReal(pole) => {
                let real = &coefficients[basis_index];
                let imag = &coefficients[basis_index + 1];
                for response_index in 0..response_count {
                    residues[*pole][response_index] =
                        real[response_index] + Complex::new(0.0, 1.0) * imag[response_index];
                    residues[*pole + 1][response_index] =
                        real[response_index] - Complex::new(0.0, 1.0) * imag[response_index];
                }
            }
            BasisKind::ComplexImag(_) => {}
            BasisKind::Constant => constant = coefficients[basis_index].clone(),
            BasisKind::Proportional => proportional = coefficients[basis_index].clone(),
        }
    }
    let mut model = RationalFitModel {
        poles: poles.to_vec(),
        residues,
        constant,
        proportional,
        ports: network.ports,
        frequency_scale_hz,
    };
    if dc_constrained {
        let dc_target = &network.samples[0];
        let without_constant = model.evaluate(0.0);
        for response_index in 0..response_count {
            model.constant[response_index] =
                dc_target[response_index] - without_constant[response_index];
        }
    }
    if model
        .constant
        .iter()
        .chain(model.proportional.iter())
        .chain(model.residues.iter().flatten())
        .any(|value| !finite_complex(*value))
    {
        return Err(FitSparamError::FitNumericalFailure(
            "fitted rational model is non-finite".to_owned(),
        ));
    }
    Ok(model)
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub(crate) struct NativeVectorFitDiagnostics {
    pub iterations: usize,
    pub initial_rms: f64,
    pub final_rms: f64,
}

fn relocation_peak(network: &TouchstoneNetwork, model: &RationalFitModel) -> Option<(f64, f64)> {
    network
        .frequencies_hz
        .iter()
        .enumerate()
        .map(|(index, frequency)| {
            let fitted = model.evaluate(*frequency);
            let error = network.samples[index]
                .iter()
                .zip(fitted)
                .map(|(left, right)| (*left - right).norm_sqr())
                .sum::<f64>()
                .sqrt();
            (*frequency, error)
        })
        .filter(|(_, error)| error.is_finite())
        .max_by(|left, right| left.1.total_cmp(&right.1))
}

fn pole_frequency_hz(pole: Complex, scale: f64) -> f64 {
    let normalized = pole.im.abs().max(pole.re.abs());
    normalized * scale / (2.0 * std::f64::consts::PI)
}

/// Run bounded native vector fitting: residue LS followed by deterministic
/// pole relocation/refit steps.  The relocation is accepted only when the
/// all-response RMS improves, so a difficult corpus remains fail-closed
/// instead of claiming that an unchanged fixed-pole solve is VF.
pub(crate) fn fit_native_vector_fitting(
    network: &TouchstoneNetwork,
    poles: &[Complex],
    basis: &[BasisKind],
    options: &FitSparamOptions,
    max_iterations: usize,
) -> Result<(RationalFitModel, NativeVectorFitDiagnostics), FitSparamError> {
    let indices = (0..network.sample_count()).collect::<Vec<_>>();
    let mut current = fit_residues(network, poles, basis, options)?;
    let mut current_rms = rms_error_for_indices(network, &current, &indices);
    let initial_rms = current_rms;
    let mut accepted = 0usize;
    for _ in 0..max_iterations.min(32) {
        let Some((peak_frequency, peak_error)) = relocation_peak(network, &current) else {
            break;
        };
        if peak_error <= f64::EPSILON || !peak_frequency.is_finite() {
            break;
        }
        let Some((representative, _)) = current
            .poles
            .iter()
            .enumerate()
            .filter(|(_, pole)| pole.im >= 0.0)
            .min_by(|(_, left), (_, right)| {
                (pole_frequency_hz(**left, current.frequency_scale_hz) - peak_frequency)
                    .abs()
                    .total_cmp(
                        &(pole_frequency_hz(**right, current.frequency_scale_hz) - peak_frequency)
                            .abs(),
                    )
            })
        else {
            break;
        };
        let mut candidate_poles = current.poles.clone();
        let normalized_frequency =
            (2.0 * std::f64::consts::PI * peak_frequency / current.frequency_scale_hz).max(1e-12);
        let pole = candidate_poles[representative];
        if pole.im.abs() <= 1e-12 {
            candidate_poles[representative] = Complex::new(-normalized_frequency, 0.0);
        } else {
            let damping = (0.01 * normalized_frequency).max(1e-8);
            candidate_poles[representative] = Complex::new(-damping, normalized_frequency);
            if let Some(partner) = (0..candidate_poles.len()).find(|index| {
                *index != representative
                    && (candidate_poles[*index] - pole.conj()).norm() <= 1e-8 * pole.norm().max(1.0)
            }) {
                candidate_poles[partner] = candidate_poles[representative].conj();
            }
        }
        let candidate = fit_residues(network, &candidate_poles, basis, options)?;
        let candidate_rms = rms_error_for_indices(network, &candidate, &indices);
        if candidate_rms.is_finite() && candidate_rms + 1e-14 < current_rms {
            current = candidate;
            current_rms = candidate_rms;
            accepted += 1;
        } else {
            break;
        }
    }
    Ok((
        current,
        NativeVectorFitDiagnostics {
            iterations: accepted,
            initial_rms,
            final_rms: current_rms,
        },
    ))
}

pub(crate) fn rms_error_for_indices(
    network: &TouchstoneNetwork,
    model: &RationalFitModel,
    indices: &[usize],
) -> f64 {
    if indices.is_empty() {
        return f64::INFINITY;
    }
    let fitted = model.evaluated_samples(
        &indices
            .iter()
            .map(|index| network.frequencies_hz[*index])
            .collect::<Vec<_>>(),
    );
    let mut total = 0.0;
    for response in 0..network.response_count() {
        let mean = indices
            .iter()
            .zip(fitted.iter())
            .map(|(index, row)| (network.samples[*index][response] - row[response]).norm_sqr())
            .sum::<f64>()
            / indices.len() as f64;
        total += mean;
    }
    total.sqrt()
}

pub(crate) fn mean_rms_error_for_indices(
    network: &TouchstoneNetwork,
    model: &RationalFitModel,
    indices: &[usize],
) -> f64 {
    let rms = rms_error_for_indices(network, model, indices);
    if rms.is_finite() {
        rms / network.ports as f64
    } else {
        rms
    }
}

fn priority_metrics(
    network: &TouchstoneNetwork,
    model: &RationalFitModel,
    bands: &[PriorityBand],
) -> (Option<f64>, bool) {
    if bands.is_empty() {
        return (None, true);
    }
    let mut maximum = 0.0_f64;
    let mut all_met = true;
    for band in bands {
        let indices = network
            .frequencies_hz
            .iter()
            .enumerate()
            .filter(|(_, frequency)| **frequency >= band.f_min_hz && **frequency <= band.f_max_hz)
            .map(|(index, _)| index)
            .collect::<Vec<_>>();
        let rms = mean_rms_error_for_indices(network, model, &indices);
        if !rms.is_finite() || rms > band.rms_target {
            all_met = false;
        }
        maximum = maximum.max(rms);
    }
    (Some(maximum), all_met)
}

fn observe_sampled_passivity(
    network: &TouchstoneNetwork,
    model: &RationalFitModel,
    policy: PassivityPolicy,
) -> Result<PassivityObservation, FitSparamError> {
    match policy {
        PassivityPolicy::Off => Ok(PassivityObservation::NotRequested),
        PassivityPolicy::Enforce => Err(FitSparamError::PassivityEnforceNotImplemented),
        PassivityPolicy::Check => {
            if network.ports != 2 {
                let samples = model.evaluated_samples(&network.frequencies_hz);
                for row in samples {
                    if row.len() != network.response_count() {
                        return Ok(PassivityObservation::Indeterminate);
                    }
                    let matrix = Mat::from_fn(network.ports, network.ports, |row_index, column| {
                        row[row_index * network.ports + column]
                    });
                    let singular = matrix.singular_values().map_err(|error| {
                        FitSparamError::FitNumericalFailure(format!(
                            "n-port passivity singular-value solve failed: {error:?}"
                        ))
                    })?;
                    let sigma = singular.first().copied().unwrap_or(f64::INFINITY);
                    if !sigma.is_finite() {
                        return Ok(PassivityObservation::Indeterminate);
                    }
                    if sigma > 1.0 + 1.0e-9 {
                        return Ok(PassivityObservation::SampledFail);
                    }
                }
                return Ok(PassivityObservation::SampledPass);
            }
            let samples = model
                .evaluated_samples(&network.frequencies_hz)
                .into_iter()
                .map(|row| {
                    let make = |value: Complex| {
                        SipiComplex64::try_new(value.re, value.im)
                            .map_err(|error| FitSparamError::FitNumericalFailure(error.to_string()))
                    };
                    Ok(TwoPortS {
                        s11: make(row[0])?,
                        s21: make(row[2])?,
                        s12: make(row[1])?,
                        s22: make(row[3])?,
                    })
                })
                .collect::<Result<Vec<_>, FitSparamError>>()?;
            let step = network
                .frequencies_hz
                .windows(2)
                .map(|pair| pair[1] - pair[0])
                .find(|value| *value > 0.0)
                .unwrap_or(1.0);
            let impedance = Ohms::try_new(network.reference_impedance)
                .map_err(|error| FitSparamError::FitNumericalFailure(error.to_string()))?;
            let frequency_step = Hertz::try_new(step)
                .map_err(|error| FitSparamError::FitNumericalFailure(error.to_string()))?;
            let input = MatchedTwoPortSpectrumV1::try_new(impedance, frequency_step, samples)
                .map_err(|error| FitSparamError::FitNumericalFailure(error.to_string()))?;
            let status = analyze_matched_two_port_v1(&input)
                .sampled_passivity()
                .status();
            Ok(match status {
                SampledDiagnosticStatusV1::PassesSampledBound => PassivityObservation::SampledPass,
                SampledDiagnosticStatusV1::ViolatesSampledBound => {
                    PassivityObservation::SampledFail
                }
                SampledDiagnosticStatusV1::Indeterminate => PassivityObservation::Indeterminate,
            })
        }
    }
}

#[allow(dead_code)] // Retained for the additive S-domain preflight API boundary.
fn sampled_s_sigma(model: &RationalFitModel, frequency_hz: f64) -> Result<f64, FitSparamError> {
    let values = model.evaluate(frequency_hz);
    if values.len() != model.response_count() {
        return Err(FitSparamError::FitNumericalFailure(
            "S passivity model response dimensions are invalid".to_owned(),
        ));
    }
    let matrix = Mat::from_fn(model.ports, model.ports, |row, column| {
        values[row * model.ports + column]
    });
    let singular = matrix.singular_values().map_err(|error| {
        FitSparamError::FitNumericalFailure(format!(
            "S passivity singular-value solve failed: {error:?}"
        ))
    })?;
    singular.first().copied().ok_or_else(|| {
        FitSparamError::FitNumericalFailure("S passivity singular-value result is empty".to_owned())
    })
}

#[allow(dead_code)] // Retained for the additive S-domain preflight API boundary.
fn sampled_s_violation_bands(
    model: &RationalFitModel,
    frequencies: &[f64],
    target: f64,
) -> Result<Vec<Value>, FitSparamError> {
    let mut bands = Vec::new();
    let mut start = None;
    let mut worst = target;
    for (index, frequency) in frequencies.iter().copied().enumerate() {
        let sigma = sampled_s_sigma(model, frequency)?;
        if sigma > target {
            start.get_or_insert(frequency);
            worst = worst.max(sigma);
        }
        if (sigma <= target || index + 1 == frequencies.len())
            && let Some(low) = start.take()
        {
            let high = if sigma > target {
                frequency
            } else {
                frequencies[index.saturating_sub(1)]
            };
            bands.push(json!({
                "f_min_hz": low,
                "f_max_hz": high,
                "max_sigma": worst,
            }));
            worst = target;
        }
    }
    Ok(bands)
}

#[allow(dead_code)] // Retained for the additive S-domain preflight API boundary.
fn adaptive_s_passivity_grid(
    model: &RationalFitModel,
    seed: &[f64],
    target: f64,
) -> Result<(Vec<f64>, Vec<Value>), FitSparamError> {
    let mut grid = seed.to_vec();
    grid.sort_by(f64::total_cmp);
    grid.dedup_by(|left, right| *left == *right);
    for _ in 0..5 {
        let mut additions = Vec::new();
        for pair in grid.windows(2) {
            let left = sampled_s_sigma(model, pair[0])?;
            let right = sampled_s_sigma(model, pair[1])?;
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
    let bands = sampled_s_violation_bands(model, &grid, target)?;
    Ok((grid, bands))
}

#[allow(dead_code)] // Retained for the additive S-domain preflight API boundary.
fn enforce_sampled_s_passivity(
    model: &mut RationalFitModel,
    frequencies: &[f64],
    epsilon: f64,
) -> Result<Value, FitSparamError> {
    if frequencies.is_empty() {
        return Err(FitSparamError::FitNumericalFailure(
            "S passivity enforcement requires at least one frequency".to_owned(),
        ));
    }
    let target = 1.0 + epsilon;
    let (mut grid, initial_bands) = adaptive_s_passivity_grid(model, frequencies, target)?;
    let before = grid
        .iter()
        .map(|frequency| sampled_s_sigma(model, *frequency))
        .collect::<Result<Vec<_>, _>>()?
        .into_iter()
        .fold(0.0_f64, f64::max);
    if !before.is_finite() {
        return Err(FitSparamError::FitNumericalFailure(
            "S passivity sample contains a non-finite singular value".to_owned(),
        ));
    }
    if before <= target {
        return Ok(json!({
            "policy": "enforce",
            "method": "sampled_violation_band_coordinate_descent",
            "status": "already_passive_on_sample_grid",
            "sample_max_sigma_before": before,
            "sample_max_sigma_after": before,
            "frequency_samples": grid.len(),
            "initial_violation_bands_hz": initial_bands,
            "final_violation_bands_hz": initial_bands,
        }));
    }
    let mut after = before;
    let mut accepted_updates = Vec::new();
    for _ in 0..12 {
        if after <= target {
            break;
        }
        let mut best: Option<(RationalFitModel, f64, String)> = None;
        let mut candidates = Vec::new();
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
            let score = grid
                .iter()
                .map(|frequency| sampled_s_sigma(&candidate, *frequency))
                .collect::<Result<Vec<_>, _>>()?
                .into_iter()
                .fold(0.0_f64, f64::max);
            if score.is_finite() && score + 1e-12 < best.as_ref().map_or(after, |entry| entry.1) {
                best = Some((candidate, score, update));
            }
        }
        let Some((candidate, score, update)) = best else {
            break;
        };
        *model = candidate;
        after = score;
        accepted_updates.push(update);
        let (next_grid, _) = adaptive_s_passivity_grid(model, &grid, target)?;
        grid = next_grid;
    }
    let final_bands = sampled_s_violation_bands(model, &grid, target)?;
    if after > target + 1e-9 || !after.is_finite() {
        return Err(FitSparamError::FitNumericalFailure(format!(
            "S passivity enforcement did not meet target: before={before:.6e}, after={after:.6e}, target={target:.6e}, violation_bands={final_bands:?}"
        )));
    }
    Ok(json!({
        "policy": "enforce",
        "method": "sampled_violation_band_coordinate_descent",
        "status": "optimized",
        "sample_max_sigma_before": before,
        "sample_max_sigma_after": after,
        "target_sigma": target,
        "frequency_samples": grid.len(),
        "accepted_updates": accepted_updates,
        "initial_violation_bands_hz": initial_bands,
        "final_violation_bands_hz": final_bands,
    }))
}

/// AS-05 uses the upstream `passivity=enforce` S-domain preflight.  AS-01's
/// public two-port API intentionally keeps enforcement unsupported, so this
/// crate-local n-port route fits first and then applies the bounded sampled
/// violation-band optimizer before publishing the preflight result.
#[allow(dead_code)] // Retained for the additive S-domain preflight API boundary.
pub(crate) fn fit_sparam_multiport_enforced(
    request: &FitSparamRequest,
) -> Result<FitSparamResult, FitSparamError> {
    let plan = request.plan()?;
    if plan.passivity != PassivityPolicy::Enforce {
        return fit_sparam_multiport(request);
    }
    let mut options = request.options.clone();
    options.passivity = Some(PassivityPolicy::Off);
    options.legacy_passivity = LegacyPassivityFlags::default();
    let fit_request = FitSparamRequest::new(request.touchstone.clone(), options)?;
    let mut result = fit_sparam_with_port_policy(&fit_request, true)?;
    let source_network = read_touchstone_multiport(&plan.touchstone)?;
    let network = request
        .options
        .reference_impedance
        .map_or(Ok(source_network.clone()), |target| {
            renormalize_network(&source_network, target)
        })?;
    let enforcement =
        enforce_sampled_s_passivity(&mut result.model, network.frequencies_hz(), 1.0e-9)?;
    let passivity = observe_sampled_passivity(&network, &result.model, PassivityPolicy::Check)?;
    let all_indices = (0..network.sample_count()).collect::<Vec<_>>();
    let rms_error = rms_error_for_indices(&network, &result.model, &all_indices);
    let mean_rms_error = mean_rms_error_for_indices(&network, &result.model, &all_indices);
    let (priority_rms_error, priority_met) =
        priority_metrics(&network, &result.model, &request.options.priority_bands);
    let mut gate_plan = plan.clone();
    gate_plan.passivity = PassivityPolicy::Check;
    let target_met = target_met(&gate_plan, mean_rms_error, priority_met, passivity);
    if let Some(trial) = result.trials.last_mut() {
        trial.rms_error = rms_error;
        trial.mean_rms_error = mean_rms_error;
        trial.priority_rms_error = priority_rms_error;
        trial.passivity = passivity;
        trial.target_met = target_met;
    }
    write_fit_artifacts(&FitArtifactContext {
        artifacts: &result.artifacts,
        network: &network,
        model: &result.model,
        trials: &result.trials,
        target_met,
        rms_error,
        mean_rms_error,
        passivity,
        passivity_enforcement: Some(&enforcement),
    })?;
    result.target_met = target_met;
    result.rms_error = rms_error;
    result.mean_rms_error = mean_rms_error;
    result.passivity = passivity;
    Ok(result)
}

fn target_met(
    plan: &FitSparamPlan,
    rms_error: f64,
    priority_met: bool,
    passivity: PassivityObservation,
) -> bool {
    let full_met = rms_error.is_finite() && rms_error <= plan.rms_target;
    let branch_met = match plan.target_branch {
        TargetBranch::FullBand => full_met,
        TargetBranch::PriorityBandOnly => priority_met,
        TargetBranch::PriorityBandAndFullBand => full_met && priority_met,
    };
    let passivity_met = match plan.passivity {
        PassivityPolicy::Off => true,
        PassivityPolicy::Check => passivity == PassivityObservation::SampledPass,
        PassivityPolicy::Enforce => false,
    };
    branch_met && passivity_met
}

fn next_search_order(
    current: usize,
    max_order: usize,
    max_order_step: usize,
    rms_error: f64,
    rms_target: f64,
    short_range: bool,
) -> usize {
    if current >= max_order {
        return current;
    }
    if short_range {
        return current.saturating_add(1).min(max_order);
    }
    let ratio = rms_error / rms_target;
    let step = if !ratio.is_finite() || ratio >= 100.0 {
        max_order_step
    } else if ratio >= 10.0 {
        max_order_step.min(4)
    } else if ratio >= 3.0 {
        max_order_step.min(3)
    } else {
        max_order_step.min(2)
    };
    current.saturating_add(step.max(1)).min(max_order)
}

fn order_pole_configuration(
    network: &TouchstoneNetwork,
    options: &FitSparamOptions,
    order: usize,
) -> Result<(Vec<Complex>, Vec<BasisKind>), FitSparamError> {
    let pair_count = options.n_poles_cmplx.min(order / 2);
    let real_count = order.saturating_sub(pair_count * 2);
    let (poles, mut basis) = initial_poles(
        &network.frequencies_hz,
        real_count.max(if pair_count == 0 { 1 } else { 0 }),
        pair_count,
        &options.pole_spacing,
        network_frequency_scale(network),
    )?;
    if options.fit_constant {
        basis.push(BasisKind::Constant);
    }
    if options.fit_proportional {
        basis.push(BasisKind::Proportional);
    }
    Ok((poles, basis))
}

fn published_artifacts(artifacts: &FitSparamArtifacts) -> FitSparamPublishedArtifacts {
    FitSparamPublishedArtifacts {
        report: artifacts.report.clone(),
        fitted_touchstone: artifacts.fitted_touchstone.clone(),
        log: artifacts.log.clone(),
    }
}

struct CheckedArtifactPath<'a> {
    label: &'static str,
    original: &'a Path,
    lexical: PathBuf,
    resolved: PathBuf,
    exists: bool,
}

fn normalize_absolute(path: &Path) -> Result<PathBuf, FitSparamError> {
    let absolute = std::path::absolute(path)
        .map_err(|error| FitSparamError::OutputIo(format!("path normalization failed: {error}")))?;
    let mut normalized = PathBuf::new();
    for component in absolute.components() {
        match component {
            Component::Prefix(prefix) => normalized.push(prefix.as_os_str()),
            Component::RootDir => normalized.push(component.as_os_str()),
            Component::CurDir => {}
            Component::ParentDir => {
                if !normalized.pop() {
                    return Err(FitSparamError::OutputIo(
                        "path normalization escaped the filesystem root".to_owned(),
                    ));
                }
            }
            Component::Normal(value) => normalized.push(value),
        }
    }
    Ok(normalized)
}

fn resolve_existing_ancestor(path: &Path) -> Result<(PathBuf, bool), FitSparamError> {
    let lexical = normalize_absolute(path)?;
    let mut cursor = lexical.as_path();
    let mut tail = Vec::new();
    loop {
        match fs::symlink_metadata(cursor) {
            Ok(_) => {
                let mut resolved = fs::canonicalize(cursor).map_err(|error| {
                    FitSparamError::OutputIo(format!(
                        "artifact path identity check failed for '{}': {error}",
                        path.display()
                    ))
                })?;
                for component in tail.iter().rev() {
                    resolved.push(component);
                }
                return Ok((normalize_absolute(&resolved)?, tail.is_empty()));
            }
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                let name = cursor.file_name().ok_or_else(|| {
                    FitSparamError::OutputIo(format!(
                        "artifact path has no existing ancestor: '{}'",
                        path.display()
                    ))
                })?;
                tail.push(name.to_os_string());
                cursor = cursor.parent().ok_or_else(|| {
                    FitSparamError::OutputIo(format!(
                        "artifact path has no parent: '{}'",
                        path.display()
                    ))
                })?;
            }
            Err(error) => {
                return Err(FitSparamError::OutputIo(format!(
                    "artifact path identity check failed for '{}': {error}",
                    path.display()
                )));
            }
        }
    }
}

fn identity_path_eq(left: &Path, right: &Path) -> bool {
    #[cfg(windows)]
    {
        left.as_os_str()
            .to_string_lossy()
            .eq_ignore_ascii_case(&right.as_os_str().to_string_lossy())
    }
    #[cfg(not(windows))]
    {
        left == right
    }
}

fn ensure_artifact_boundaries(
    input: &Path,
    artifacts: &FitSparamPublishedArtifacts,
) -> Result<(), FitSparamError> {
    let named_paths = [
        ("input", input),
        ("report", artifacts.report.as_path()),
        ("fitted_touchstone", artifacts.fitted_touchstone.as_path()),
        ("log", artifacts.log.as_path()),
    ];
    let mut checked = Vec::with_capacity(named_paths.len());
    for (label, path) in named_paths {
        let bytes = path.as_os_str().to_string_lossy().len();
        if bytes > MAX_ARTIFACT_PATH_BYTES {
            return Err(FitSparamError::BudgetExceeded {
                kind: "artifact path bytes",
                limit: MAX_ARTIFACT_PATH_BYTES,
                actual: bytes,
            });
        }
        let lexical = normalize_absolute(path)?;
        let (resolved, exists) = resolve_existing_ancestor(path)?;
        checked.push(CheckedArtifactPath {
            label,
            original: path,
            lexical,
            resolved,
            exists,
        });
    }
    for (index, left) in checked.iter().enumerate() {
        for right in checked.iter().skip(index + 1) {
            let same_identity = left.exists
                && right.exists
                && same_file::is_same_file(left.original, right.original).map_err(|error| {
                    FitSparamError::OutputIo(format!(
                        "artifact file identity check failed for '{}' and '{}': {error}",
                        left.original.display(),
                        right.original.display()
                    ))
                })?;
            if identity_path_eq(&left.lexical, &right.lexical)
                || identity_path_eq(&left.resolved, &right.resolved)
                || same_identity
            {
                return Err(FitSparamError::DuplicateOutputPath(format!(
                    "{} '{}' aliases {} '{}'",
                    left.label,
                    left.original.display(),
                    right.label,
                    right.original.display()
                )));
            }
        }
    }
    Ok(())
}

fn write_text(path: &std::path::Path, text: &str) -> Result<(), FitSparamError> {
    if text.len() > MAX_ARTIFACT_BYTES {
        return Err(FitSparamError::BudgetExceeded {
            kind: "artifact bytes",
            limit: MAX_ARTIFACT_BYTES,
            actual: text.len(),
        });
    }
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|error| FitSparamError::OutputIo(error.to_string()))?;
    }
    fs::write(path, text).map_err(|error| FitSparamError::OutputIo(error.to_string()))
}

/// Write fitted values as Touchstone 1.x column-major tokens.  The model is
/// row-major internally, so this explicit remap keeps S12/S21 from swapping
/// at the artifact boundary.
pub fn write_fitted_touchstone(
    path: impl AsRef<std::path::Path>,
    network: &TouchstoneNetwork,
    model: &RationalFitModel,
) -> Result<(), FitSparamError> {
    let path = path.as_ref();
    let values_per_sample = 1usize
        .checked_add(network.response_count().saturating_mul(2))
        .ok_or(FitSparamError::BudgetExceeded {
            kind: "fitted Touchstone values",
            limit: MAX_ARTIFACT_BYTES,
            actual: usize::MAX,
        })?;
    let estimated_bytes = network
        .sample_count()
        .checked_mul(values_per_sample)
        .and_then(|value| value.checked_mul(32))
        .ok_or(FitSparamError::BudgetExceeded {
            kind: "fitted Touchstone bytes",
            limit: MAX_ARTIFACT_BYTES,
            actual: usize::MAX,
        })?;
    if estimated_bytes > MAX_ARTIFACT_BYTES {
        return Err(FitSparamError::BudgetExceeded {
            kind: "fitted Touchstone bytes",
            limit: MAX_ARTIFACT_BYTES,
            actual: estimated_bytes,
        });
    }
    let mut output = format!("# Hz S RI R {}\n", network.reference_impedance);
    for (frequency, row) in network
        .frequencies_hz
        .iter()
        .zip(model.evaluated_samples(&network.frequencies_hz))
    {
        output.push_str(&format!("{frequency:.17e}"));
        for column in 0..network.ports {
            for row_index in 0..network.ports {
                let value = row[row_index * network.ports + column];
                output.push_str(&format!(" {:.17e} {:.17e}", value.re, value.im));
            }
        }
        output.push('\n');
    }
    write_text(path, &output)
}

fn passivity_name(value: PassivityObservation) -> &'static str {
    match value {
        PassivityObservation::NotRequested => "not_requested",
        PassivityObservation::SampledPass => "sampled_pass",
        PassivityObservation::SampledFail => "sampled_fail",
        PassivityObservation::Indeterminate => "indeterminate",
    }
}

struct FitArtifactContext<'a> {
    artifacts: &'a FitSparamPublishedArtifacts,
    network: &'a TouchstoneNetwork,
    model: &'a RationalFitModel,
    trials: &'a [FitTrial],
    target_met: bool,
    rms_error: f64,
    mean_rms_error: f64,
    passivity: PassivityObservation,
    passivity_enforcement: Option<&'a Value>,
}

fn write_fit_artifacts(context: &FitArtifactContext<'_>) -> Result<(), FitSparamError> {
    let artifacts = context.artifacts;
    let network = context.network;
    let model = context.model;
    let trials = context.trials;
    let target_met = context.target_met;
    let rms_error = context.rms_error;
    let passivity = context.passivity;
    write_fitted_touchstone(&artifacts.fitted_touchstone, network, model)?;
    let trial_values = trials
        .iter()
        .map(|trial| {
            json!({
                "requested_order": trial.requested_order,
                "effective_order": trial.effective_order,
                "rms_error": trial.rms_error,
                "mean_rms_error": trial.mean_rms_error,
                "priority_rms_error": trial.priority_rms_error,
                "passivity": passivity_name(trial.passivity),
                "target_met": trial.target_met,
                "pole_relocation_iterations": trial.pole_relocation_iterations,
            })
        })
        .collect::<Vec<Value>>();
    let report = json!({
        "schema": "as-01-fit-sparam-result-v1",
        "workflow": WORKFLOW_NAME,
        "upstream_commit": UPSTREAM_COMMIT,
        "upstream_tree": UPSTREAM_TREE,
        "ports": network.ports,
        "sample_count": network.sample_count(),
        "reference_impedance_ohms": network.reference_impedance,
        "target_met": target_met,
        "selected_order": model.order(),
        "rms_error": rms_error,
        "mean_rms_error": context.mean_rms_error,
        "passivity": passivity_name(passivity),
        "passivity_enforcement": context.passivity_enforcement,
        "trials": trial_values,
        "artifacts": {
            "report": artifacts.report,
            "fitted_touchstone": artifacts.fitted_touchstone,
            "log": artifacts.log,
        },
        "unsupported_artifacts": ["spice_subcircuit", "html_report", "rfm", "rfm_wrapper"],
    });
    let report_text = serde_json::to_string_pretty(&report)
        .map_err(|error| FitSparamError::OutputIo(error.to_string()))?;
    write_text(&artifacts.report, &(report_text + "\n"))?;
    let log = trials
        .iter()
        .map(|trial| {
            format!(
                "order={} effective_order={} rms={:.17e} mean_rms={:.17e} passivity={} target_met={}\n",
                trial.requested_order,
                trial.effective_order,
                trial.rms_error,
                trial.mean_rms_error,
                passivity_name(trial.passivity),
                trial.target_met
            )
        })
        .collect::<String>();
    write_text(&artifacts.log, &log)
}

/// Execute the minimal, numerically real AS-01 route.
pub fn fit_sparam(request: &FitSparamRequest) -> Result<FitSparamResult, FitSparamError> {
    fit_sparam_with_port_policy(request, false)
}

/// Execute the same S-domain vector fit without AS-01's public two-port
/// admission restriction.  AS-05 uses this for n-port S-element preflight;
/// all order, passivity, artifact, and budget gates remain shared.
#[allow(dead_code)] // Retained for the additive S-domain preflight API boundary.
pub(crate) fn fit_sparam_multiport(
    request: &FitSparamRequest,
) -> Result<FitSparamResult, FitSparamError> {
    fit_sparam_with_port_policy(request, true)
}

fn fit_sparam_with_port_policy(
    request: &FitSparamRequest,
    allow_multiport: bool,
) -> Result<FitSparamResult, FitSparamError> {
    let plan = request.plan()?;
    validate_execution_options(&request.options)?;
    if plan.passivity == PassivityPolicy::Enforce {
        return Err(FitSparamError::PassivityEnforceNotImplemented);
    }
    let source_network = if allow_multiport {
        read_touchstone_multiport(&plan.touchstone)?
    } else {
        read_touchstone(&plan.touchstone)?
    };
    let network = request
        .options
        .reference_impedance
        .map_or(Ok(source_network.clone()), |target| {
            renormalize_network(&source_network, target)
        })?;
    let artifacts = published_artifacts(&plan.artifacts);
    ensure_artifact_boundaries(&plan.touchstone, &artifacts)?;
    let max_order = plan.max_order;
    let mut trials = Vec::new();
    let mut best: Option<(RationalFitModel, FitTrial)> = None;
    let short_range = plan.min_order == 1 && max_order < 4;
    let mut requested_order = if short_range {
        1
    } else if plan.min_order == 1 {
        4.min(max_order)
    } else {
        plan.min_order
    };
    loop {
        // A failed order is not recoverable by retrying the same immutable
        // request. Propagate it rather than spinning forever.
        let (poles, basis) = order_pole_configuration(&network, &request.options, requested_order)?;
        let (model, relocation) = fit_native_vector_fitting(
            &network,
            &poles,
            &basis,
            &request.options,
            request.options.fit_iterations,
        )?;
        let all_indices = (0..network.sample_count()).collect::<Vec<_>>();
        let rms_error = rms_error_for_indices(&network, &model, &all_indices);
        let mean_rms_error = mean_rms_error_for_indices(&network, &model, &all_indices);
        let (priority_rms_error, priority_met) =
            priority_metrics(&network, &model, &request.options.priority_bands);
        let passivity = observe_sampled_passivity(&network, &model, plan.passivity)?;
        let trial_target_met = target_met(&plan, mean_rms_error, priority_met, passivity);
        let trial = FitTrial {
            requested_order,
            effective_order: model.order(),
            rms_error,
            mean_rms_error,
            priority_rms_error,
            passivity,
            target_met: trial_target_met,
            pole_relocation_iterations: relocation.iterations,
        };
        let is_better = best
            .as_ref()
            .is_none_or(|(_, current)| trial.rms_error < current.rms_error);
        if is_better {
            best = Some((model.clone(), trial.clone()));
        }
        trials.push(trial.clone());
        if trial_target_met {
            best = Some((model, trial));
            break;
        }
        let next_order = next_search_order(
            requested_order,
            max_order,
            plan.max_order_step,
            trial.mean_rms_error,
            plan.rms_target,
            short_range,
        );
        if next_order == requested_order {
            break;
        }
        requested_order = next_order;
    }
    let (model, selected) = best.ok_or_else(|| {
        FitSparamError::FitNumericalFailure("no requested order produced a finite model".to_owned())
    })?;
    let target_met = selected.target_met;
    write_fit_artifacts(&FitArtifactContext {
        artifacts: &artifacts,
        network: &network,
        model: &model,
        trials: &trials,
        target_met,
        rms_error: selected.rms_error,
        mean_rms_error: selected.mean_rms_error,
        passivity: selected.passivity,
        passivity_enforcement: None,
    })?;
    Ok(FitSparamResult {
        target_met,
        selected_order: selected.effective_order,
        rms_error: selected.rms_error,
        mean_rms_error: selected.mean_rms_error,
        passivity: selected.passivity,
        artifacts,
        trials,
        model,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pinned_defaults_derive_default_artifact_family() {
        let plan = plan_fit_sparam(
            "fixtures/line.s2p",
            FitSparamOptions {
                rms_target: Some(0.001),
                ..FitSparamOptions::default()
            },
        )
        .unwrap();
        assert_eq!(plan.target_branch, TargetBranch::FullBand);
        assert_eq!(plan.passivity, PassivityPolicy::Check);
        assert_eq!(plan.max_order, 100);
        assert_eq!(
            plan.artifacts.output,
            PathBuf::from("fixtures/line_fitted.sp")
        );
        assert_eq!(
            plan.artifacts.report,
            PathBuf::from("fixtures/line_fitted_report.json")
        );
        assert_eq!(
            plan.artifacts.html_report,
            PathBuf::from("fixtures/line_fitted_report.html")
        );
        assert_eq!(
            plan.artifacts.fitted_touchstone,
            PathBuf::from("fixtures/line_fitted.s2p")
        );
        assert_eq!(
            plan.artifacts.rfm,
            PathBuf::from("fixtures/line_fitted.rfm")
        );
        assert_eq!(
            plan.artifacts.rfm_wrapper,
            PathBuf::from("fixtures/line_fitted_rfm_wrapper.sp")
        );
        assert_eq!(plan.artifacts.log, PathBuf::from("fixtures/line.log"));
    }

    #[test]
    fn explicit_output_uses_shared_report_names_and_priority_target() {
        let options = FitSparamOptions {
            output: Some(PathBuf::from("out/model.sp")),
            priority_bands: vec![PriorityBand::new(0.0, 1.0e9, 0.01, 2.0).unwrap()],
            passivity: Some(PassivityPolicy::Enforce),
            ..FitSparamOptions::default()
        };
        let plan = plan_fit_sparam("input.s4p", options).unwrap();
        assert_eq!(plan.target_branch, TargetBranch::PriorityBandOnly);
        assert_eq!(plan.rms_target, 0.01);
        assert_eq!(plan.artifacts.report, PathBuf::from("out/fit_report.json"));
        assert_eq!(
            plan.artifacts.html_report,
            PathBuf::from("out/fit_report.html")
        );
        assert_eq!(
            plan.artifacts.fitted_touchstone,
            PathBuf::from("out/model.s4p")
        );
        assert_eq!(plan.passivity, PassivityPolicy::Enforce);
    }

    #[test]
    fn full_band_target_with_priority_bands_is_explicitly_blocking() {
        let plan = plan_fit_sparam(
            "line.s2p",
            FitSparamOptions {
                rms_target: Some(0.02),
                priority_bands: vec![PriorityBand::new(1.0, 2.0, 0.01, 1.0).unwrap()],
                ..FitSparamOptions::default()
            },
        )
        .unwrap();
        assert_eq!(plan.target_branch, TargetBranch::PriorityBandAndFullBand);
        assert!(plan.target_branch.full_band_is_blocking());
    }

    #[test]
    fn legacy_passivity_precedence_matches_pinned_cli() {
        assert_eq!(
            resolve_passivity(
                None,
                LegacyPassivityFlags {
                    enforce: true,
                    skip_check: true,
                    ..LegacyPassivityFlags::default()
                }
            )
            .unwrap(),
            PassivityPolicy::Enforce
        );
        assert_eq!(
            resolve_passivity(
                None,
                LegacyPassivityFlags {
                    skip_check: true,
                    ..LegacyPassivityFlags::default()
                }
            )
            .unwrap(),
            PassivityPolicy::Off
        );
        assert_eq!(
            resolve_passivity(
                Some(PassivityPolicy::Off),
                LegacyPassivityFlags {
                    check: true,
                    ..LegacyPassivityFlags::default()
                }
            )
            .unwrap_err(),
            FitSparamError::ConflictingPassivityFlags
        );
    }

    #[test]
    fn target_and_option_errors_fail_closed() {
        assert_eq!(
            plan_fit_sparam("line.s2p", FitSparamOptions::default()).unwrap_err(),
            FitSparamError::MissingRmsTarget
        );
        assert_eq!(
            plan_fit_sparam(
                "line.s2p",
                FitSparamOptions {
                    rms_target: Some(f64::NAN),
                    ..FitSparamOptions::default()
                }
            )
            .unwrap_err(),
            FitSparamError::NonFiniteRmsTarget
        );
        assert_eq!(
            plan_fit_sparam(
                "line.s2p",
                FitSparamOptions {
                    rms_target: Some(0.1),
                    max_order: Some(2),
                    min_order: 3,
                    ..FitSparamOptions::default()
                }
            )
            .unwrap_err(),
            FitSparamError::InvalidOrder
        );
        assert_eq!(
            plan_fit_sparam(
                "line.s2p",
                FitSparamOptions {
                    rms_target: Some(0.1),
                    report_top_rms: -1,
                    ..FitSparamOptions::default()
                }
            )
            .unwrap_err(),
            FitSparamError::InvalidReportTopRms
        );
    }

    #[test]
    fn candidate_declares_kernel_not_bound_to_generic_sparam() {
        let request = FitSparamRequest::new(
            "line.s2p",
            FitSparamOptions {
                rms_target: Some(0.1),
                ..FitSparamOptions::default()
            },
        )
        .unwrap();
        let plan = request.plan().unwrap();
        assert_eq!(plan.kernel_status, KernelStatus::NativeVectorFitting);
    }

    #[test]
    fn touchstone_delivery_preserves_column_major_s12_s21_order() {
        let root = std::env::temp_dir().join(format!("sipi-as01-order-{}", std::process::id()));
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(&root).unwrap();
        let input = root.join("asym.s2p");
        fs::write(
            &input,
            "# Hz S RI R 50\n1 0.1 0 0.2 0 0.3 0 0.4 0\n2 0.1 0 0.2 0 0.3 0 0.4 0\n",
        )
        .unwrap();
        let network = read_touchstone(&input).unwrap();
        assert_eq!(
            network.samples()[0],
            [
                Complex::new(0.1, 0.0),
                Complex::new(0.3, 0.0),
                Complex::new(0.2, 0.0),
                Complex::new(0.4, 0.0),
            ]
        );
        let model = RationalFitModel {
            poles: Vec::new(),
            residues: Vec::new(),
            constant: network.samples()[0].clone(),
            proportional: vec![Complex::new(0.0, 0.0); 4],
            ports: 2,
            frequency_scale_hz: 1.0,
        };
        let output = root.join("roundtrip.s2p");
        write_fitted_touchstone(&output, &network, &model).unwrap();
        assert_eq!(
            read_touchstone(&output).unwrap().samples()[0],
            network.samples()[0]
        );
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn z0_renormalization_round_trips_without_swapping_ports() {
        let network = TouchstoneNetwork::from_samples(
            vec![1.0, 2.0],
            vec![
                vec![
                    Complex::new(0.1, 0.02),
                    Complex::new(0.3, -0.01),
                    Complex::new(0.2, 0.04),
                    Complex::new(0.4, 0.01),
                ];
                2
            ],
            2,
            50.0,
        )
        .unwrap();
        let shifted = renormalize_network(&network, 75.0).unwrap();
        let restored = renormalize_network(&shifted, 50.0).unwrap();
        for (left, right) in network.samples().iter().zip(restored.samples()) {
            assert!(
                left.iter()
                    .zip(right)
                    .all(|(a, b)| (*a - *b).norm() < 1.0e-9)
            );
        }
    }

    #[test]
    fn native_vector_fit_reports_bounded_pole_relocation_attempts() {
        let scale = 1.0e8;
        let true_model = RationalFitModel {
            poles: vec![Complex::new(
                -2.0 * std::f64::consts::PI * 8.0e6 / scale,
                0.0,
            )],
            residues: vec![vec![Complex::new(0.2, 0.0); 4]],
            constant: vec![Complex::new(0.05, 0.0); 4],
            proportional: vec![Complex::new(0.0, 0.0); 4],
            ports: 2,
            frequency_scale_hz: scale,
        };
        let frequencies = (1..=24)
            .map(|index| index as f64 * 4.0e6)
            .collect::<Vec<_>>();
        let samples = true_model.evaluated_samples(&frequencies);
        let network = TouchstoneNetwork::from_samples(frequencies, samples, 2, 50.0).unwrap();
        let options = FitSparamOptions {
            fit_iterations: 4,
            enforce_dc: false,
            ..FitSparamOptions::default()
        };
        let poles = vec![Complex::new(
            -2.0 * std::f64::consts::PI * 1.0e6 / scale,
            0.0,
        )];
        let basis = vec![BasisKind::RealPole(0), BasisKind::Constant];
        let (_model, diagnostics) =
            fit_native_vector_fitting(&network, &poles, &basis, &options, options.fit_iterations)
                .unwrap();
        assert!(diagnostics.initial_rms.is_finite());
        assert!(diagnostics.final_rms.is_finite());
        assert!(diagnostics.final_rms <= diagnostics.initial_rms + 1.0e-12);
        assert!(diagnostics.iterations <= options.fit_iterations);
    }
}
