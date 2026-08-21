//! Explicit in-memory RX CTLE -> RX FFE semantics.
//!
//! This module is intentionally not a wire or profile admission surface. A
//! caller must provide every stage control, including transfer representation,
//! grid, normalization, cursor convention, units, sign, sampling domain, and
//! initial state. The existing bounded full-linear convolution remains the
//! only numerical kernel.

use std::{error::Error, fmt, num::NonZeroUsize};

use sipi_types::{Axis, AxisView, FiniteF64, NonZeroStep, Seconds, TypeError, Waveform};

use crate::{
    ConvolutionLimitsV1, ExplicitCausalFirV1, LinkError, RxNamedFirErrorV1, RxNamedFirPlanV1,
    RxNamedFirStageV1, apply_rx_named_fir_prerequisite_v1,
};

/// Stable identity for the explicit, caller-supplied RX stage semantics.
pub const RX_CTLE_FFE_EXPLICIT_SEMANTICS_POLICY_V1: &str =
    "sipi.p3b-02.rx-ctle-ffe-explicit-semantics-v1";

/// Origin of a CTLE impulse grid.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum CtleGridOriginV1 {
    /// Sample zero is the input waveform's sample-zero origin.
    InputSampleZero,
}

/// Explicit CTLE impulse grid metadata.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct CtleGridV1 {
    sample_interval: Seconds,
    sample_count: NonZeroUsize,
    origin: CtleGridOriginV1,
}

impl CtleGridV1 {
    /// Constructs a finite, positive, non-empty uniform grid.
    pub fn try_new(
        sample_interval: Seconds,
        sample_count: usize,
        origin: CtleGridOriginV1,
    ) -> Result<Self, RxCtleFfeErrorV1> {
        if sample_interval.get() <= 0.0 {
            return Err(RxCtleFfeErrorV1::InvalidGridInterval);
        }
        Ok(Self {
            sample_interval,
            sample_count: NonZeroUsize::new(sample_count)
                .ok_or(RxCtleFfeErrorV1::EmptyCtleImpulse)?,
            origin,
        })
    }

    pub fn sample_interval(self) -> Seconds {
        self.sample_interval
    }

    pub fn sample_count(self) -> NonZeroUsize {
        self.sample_count
    }

    pub fn origin(self) -> CtleGridOriginV1 {
        self.origin
    }
}

/// Caller-selected normalization reference for a CTLE impulse.
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum CtleNormalizationV1 {
    /// Use the supplied impulse samples without scaling.
    None,
    /// Scale the sum of the supplied impulse to the explicit target.
    UnitSum { target: FiniteF64 },
    /// Scale the largest absolute impulse sample to the explicit target.
    PeakAbs { target: FiniteF64 },
}

/// Explicit CTLE initial-state policy.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum CtleStateV1 {
    /// The input begins with zero prehistory; no state is inferred.
    ZeroInitial,
}

/// A caller-supplied causal time-domain CTLE transfer.
#[derive(Clone, Debug, PartialEq)]
pub struct CtleTransferV1 {
    impulse: Vec<FiniteF64>,
    grid: CtleGridV1,
    normalization: CtleNormalizationV1,
    state: CtleStateV1,
}

impl CtleTransferV1 {
    /// Constructs an explicit impulse transfer and all of its semantics.
    pub fn try_new(
        impulse: Vec<FiniteF64>,
        grid: CtleGridV1,
        normalization: CtleNormalizationV1,
        state: CtleStateV1,
    ) -> Result<Self, RxCtleFfeErrorV1> {
        if impulse.is_empty() {
            return Err(RxCtleFfeErrorV1::EmptyCtleImpulse);
        }
        if impulse.len() != grid.sample_count().get() {
            return Err(RxCtleFfeErrorV1::CtleGridLengthMismatch);
        }
        Ok(Self {
            impulse,
            grid,
            normalization,
            state,
        })
    }

    pub fn impulse(&self) -> &[FiniteF64] {
        &self.impulse
    }

    pub fn grid(&self) -> CtleGridV1 {
        self.grid
    }

    pub fn normalization(&self) -> CtleNormalizationV1 {
        self.normalization
    }

    pub fn state(&self) -> CtleStateV1 {
        self.state
    }
}

/// Explicit selection for the CTLE slot. There is deliberately no `Default`.
#[derive(Clone, Debug, PartialEq)]
pub enum RxCtleStageV1 {
    Bypass,
    Explicit(CtleTransferV1),
}

/// Order in which caller-supplied FFE taps are declared.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum FfeTapOrderV1 {
    /// Index zero is the earliest tap and indices increase in time.
    AscendingTime,
    /// Index zero is the latest tap and indices decrease in time.
    DescendingTime,
}

/// Convention for the explicit FFE cursor index.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum FfeCursorConventionV1 {
    /// The cursor index is metadata; the first chronological tap is t = 0.
    FirstTapAtInputOrigin,
    /// The cursor index is t = 0; precursor output is represented on a
    /// negative output axis rather than silently shifted or discarded.
    CursorAtInputOrigin,
}

/// Explicit units for FFE coefficients.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum FfeTapUnitsV1 {
    /// Dimensionless voltage ratio, applied directly to voltage samples.
    NormalizedVoltageRatio,
}

/// Explicit sign convention for FFE coefficients.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum FfeTapSignV1 {
    /// A coefficient is multiplied and added as supplied.
    Direct,
    /// A coefficient is negated before multiplication and addition.
    Negated,
}

/// Explicit FFE sampling domain.
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum FfeSamplingV1 {
    /// One coefficient per input sample.
    SampleSpaced { sample_interval: Seconds },
    /// One coefficient per UI, expanded with an explicit sample count.
    UiSpaced {
        ui: Seconds,
        samples_per_ui: NonZeroUsize,
    },
}

/// Explicit FFE initial-state policy.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum FfeStateV1 {
    /// The input begins with zero prehistory; no state is inferred.
    ZeroInitial,
}

/// A caller-supplied FFE and every convention needed to apply it.
#[derive(Clone, Debug, PartialEq)]
pub struct FfeProfileV1 {
    taps: Vec<FiniteF64>,
    order: FfeTapOrderV1,
    cursor_index: usize,
    cursor_convention: FfeCursorConventionV1,
    units: FfeTapUnitsV1,
    sign: FfeTapSignV1,
    sampling: FfeSamplingV1,
    state: FfeStateV1,
}

impl FfeProfileV1 {
    /// Constructs an explicit FFE. No tap count, cursor, unit, sign, or state
    /// is inferred by this constructor.
    #[allow(clippy::too_many_arguments)]
    pub fn try_new(
        taps: Vec<FiniteF64>,
        order: FfeTapOrderV1,
        cursor_index: usize,
        cursor_convention: FfeCursorConventionV1,
        units: FfeTapUnitsV1,
        sign: FfeTapSignV1,
        sampling: FfeSamplingV1,
        state: FfeStateV1,
    ) -> Result<Self, RxCtleFfeErrorV1> {
        if taps.is_empty() {
            return Err(RxCtleFfeErrorV1::EmptyFfeTaps);
        }
        if cursor_index >= taps.len() {
            return Err(RxCtleFfeErrorV1::CursorOutOfRange);
        }
        Ok(Self {
            taps,
            order,
            cursor_index,
            cursor_convention,
            units,
            sign,
            sampling,
            state,
        })
    }

    pub fn taps(&self) -> &[FiniteF64] {
        &self.taps
    }

    pub fn order(&self) -> FfeTapOrderV1 {
        self.order
    }

    pub fn cursor_index(&self) -> usize {
        self.cursor_index
    }

    pub fn cursor_convention(&self) -> FfeCursorConventionV1 {
        self.cursor_convention
    }

    pub fn units(&self) -> FfeTapUnitsV1 {
        self.units
    }

    pub fn sign(&self) -> FfeTapSignV1 {
        self.sign
    }

    pub fn sampling(&self) -> FfeSamplingV1 {
        self.sampling
    }

    pub fn state(&self) -> FfeStateV1 {
        self.state
    }
}

/// Explicit selection for the FFE slot. There is deliberately no `Default`.
#[derive(Clone, Debug, PartialEq)]
pub enum RxFfeStageV1 {
    Bypass,
    Explicit(FfeProfileV1),
}

/// The caller-supplied RX chain, always evaluated CTLE then FFE.
#[derive(Clone, Debug, PartialEq)]
pub struct RxCtleFfeProfileV1 {
    ctle: RxCtleStageV1,
    ffe: RxFfeStageV1,
}

impl RxCtleFfeProfileV1 {
    pub const fn new(ctle: RxCtleStageV1, ffe: RxFfeStageV1) -> Self {
        Self { ctle, ffe }
    }

    pub const fn ctle(&self) -> &RxCtleStageV1 {
        &self.ctle
    }

    pub const fn ffe(&self) -> &RxFfeStageV1 {
        &self.ffe
    }
}

/// Results at the CTLE boundary and after the FFE boundary.
#[derive(Clone, Debug, PartialEq)]
pub struct RxCtleFfeResultV1 {
    ctle_output: Waveform,
    output: Waveform,
}

impl RxCtleFfeResultV1 {
    pub fn ctle_output(&self) -> &Waveform {
        &self.ctle_output
    }

    pub fn output(&self) -> &Waveform {
        &self.output
    }
}

/// Fail-closed errors for explicit RX CTLE -> RX FFE composition.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum RxCtleFfeErrorV1 {
    NonUniformInputAxis,
    NonZeroInputOrigin,
    InvalidGridInterval,
    EmptyCtleImpulse,
    CtleGridLengthMismatch,
    CtleGridIntervalMismatch,
    InvalidNormalizationReference,
    NormalizationOverflow,
    EmptyFfeTaps,
    CursorOutOfRange,
    InvalidUi,
    FfeSampleIntervalMismatch,
    FfeUiIntervalMismatch,
    ResourceCountOverflow,
    ResourceLimitExceeded,
    NamedFir(RxNamedFirErrorV1),
    Link(LinkError),
    Invariant(TypeError),
}

impl fmt::Display for RxCtleFfeErrorV1 {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::NonUniformInputAxis => {
                write!(formatter, "RX CTLE/FFE input axis must be uniform")
            }
            Self::NonZeroInputOrigin => write!(formatter, "RX CTLE/FFE input origin must be zero"),
            Self::InvalidGridInterval => write!(formatter, "CTLE grid interval must be positive"),
            Self::EmptyCtleImpulse => write!(formatter, "CTLE impulse must not be empty"),
            Self::CtleGridLengthMismatch => {
                write!(formatter, "CTLE impulse and grid lengths differ")
            }
            Self::CtleGridIntervalMismatch => {
                write!(formatter, "CTLE grid interval differs from input")
            }
            Self::InvalidNormalizationReference => {
                write!(formatter, "normalization reference is zero or unavailable")
            }
            Self::NormalizationOverflow => {
                write!(formatter, "CTLE normalization produced a non-finite value")
            }
            Self::EmptyFfeTaps => write!(formatter, "FFE taps must not be empty"),
            Self::CursorOutOfRange => write!(formatter, "FFE cursor index is outside the tap list"),
            Self::InvalidUi => write!(formatter, "FFE UI and samples-per-UI must be positive"),
            Self::FfeSampleIntervalMismatch => {
                write!(formatter, "sample-spaced FFE interval differs from input")
            }
            Self::FfeUiIntervalMismatch => {
                write!(formatter, "UI-spaced FFE interval differs from input")
            }
            Self::ResourceCountOverflow => write!(formatter, "RX CTLE/FFE resource count overflow"),
            Self::ResourceLimitExceeded => write!(formatter, "RX CTLE/FFE resource limit exceeded"),
            Self::NamedFir(error) => error.fmt(formatter),
            Self::Link(error) => error.fmt(formatter),
            Self::Invariant(error) => error.fmt(formatter),
        }
    }
}

impl Error for RxCtleFfeErrorV1 {}

impl From<RxNamedFirErrorV1> for RxCtleFfeErrorV1 {
    fn from(value: RxNamedFirErrorV1) -> Self {
        Self::NamedFir(value)
    }
}

impl From<LinkError> for RxCtleFfeErrorV1 {
    fn from(value: LinkError) -> Self {
        Self::Link(value)
    }
}

impl From<TypeError> for RxCtleFfeErrorV1 {
    fn from(value: TypeError) -> Self {
        Self::Invariant(value)
    }
}

/// Applies the explicit CTLE slot followed by the explicit FFE slot.
///
/// The input must be a zero-origin uniform waveform. Every enabled stage is
/// converted to a causal FIR and delegated to the existing bounded full-linear
/// convolution. A cursor-at-origin FFE reports its precursor on a negative
/// output axis instead of silently shifting or truncating it.
pub fn apply_rx_ctle_ffe_v1(
    input: &Waveform,
    profile: &RxCtleFfeProfileV1,
    limits: ConvolutionLimitsV1,
) -> Result<RxCtleFfeResultV1, RxCtleFfeErrorV1> {
    let input_interval = input_interval(input)?;
    let named = materialize_named_profile(input.samples().len(), profile, input_interval, limits)?;
    let result = apply_rx_named_fir_prerequisite_v1(input, &named, limits)?;
    let output = match profile.ffe() {
        RxFfeStageV1::Explicit(ffe)
            if ffe.cursor_convention() == FfeCursorConventionV1::CursorAtInputOrigin =>
        {
            let chronological_cursor = chronological_cursor_sample_index(ffe)?;
            let offset = input_interval.get() * chronological_cursor as f64;
            let start = Seconds::try_new(-offset)?;
            rebase_waveform(result.output(), start)?
        }
        _ => result.output().clone(),
    };
    Ok(RxCtleFfeResultV1 {
        ctle_output: result.ctle_named_slot_output().clone(),
        output,
    })
}

fn input_interval(input: &Waveform) -> Result<Seconds, RxCtleFfeErrorV1> {
    match input.axis().view() {
        AxisView::Uniform { start, step, .. } => {
            if start.get() != 0.0 {
                return Err(RxCtleFfeErrorV1::NonZeroInputOrigin);
            }
            if step.get() <= 0.0 {
                return Err(RxCtleFfeErrorV1::InvalidGridInterval);
            }
            Ok(step)
        }
        AxisView::Explicit(_) => Err(RxCtleFfeErrorV1::NonUniformInputAxis),
    }
}

fn materialize_named_profile(
    input_len: usize,
    profile: &RxCtleFfeProfileV1,
    input_interval: Seconds,
    limits: ConvolutionLimitsV1,
) -> Result<RxNamedFirPlanV1, RxCtleFfeErrorV1> {
    let ctle = match profile.ctle() {
        RxCtleStageV1::Bypass => RxNamedFirStageV1::Bypass,
        RxCtleStageV1::Explicit(transfer) => {
            if transfer.grid().origin() != CtleGridOriginV1::InputSampleZero {
                return Err(RxCtleFfeErrorV1::NonZeroInputOrigin);
            }
            if transfer.grid().sample_interval() != input_interval {
                return Err(RxCtleFfeErrorV1::CtleGridIntervalMismatch);
            }
            if transfer.state() != CtleStateV1::ZeroInitial {
                return Err(RxCtleFfeErrorV1::InvalidNormalizationReference);
            }
            checked_stage_budget(input_len, transfer.impulse().len(), limits)?;
            RxNamedFirStageV1::ExplicitCausalFir(ExplicitCausalFirV1::try_new(
                normalized_ctle_impulse(transfer)?,
            )?)
        }
    };
    let ffe = match profile.ffe() {
        RxFfeStageV1::Bypass => RxNamedFirStageV1::Bypass,
        RxFfeStageV1::Explicit(ffe) => {
            if ffe.state() != FfeStateV1::ZeroInitial {
                return Err(RxCtleFfeErrorV1::InvalidNormalizationReference);
            }
            RxNamedFirStageV1::ExplicitCausalFir(ExplicitCausalFirV1::try_new(
                materialize_ffe_taps(
                    stage_output_len(input_len, &ctle, limits)?,
                    ffe,
                    input_interval,
                    limits,
                )?,
            )?)
        }
    };
    Ok(RxNamedFirPlanV1::new(ctle, ffe))
}

fn stage_output_len(
    input_len: usize,
    stage: &RxNamedFirStageV1,
    limits: ConvolutionLimitsV1,
) -> Result<usize, RxCtleFfeErrorV1> {
    match stage {
        RxNamedFirStageV1::Bypass => checked_bypass_output(input_len, limits),
        RxNamedFirStageV1::ExplicitCausalFir(fir) => {
            checked_stage_budget(input_len, fir.taps().len(), limits)
        }
    }
}

fn checked_bypass_output(
    input_len: usize,
    limits: ConvolutionLimitsV1,
) -> Result<usize, RxCtleFfeErrorV1> {
    if input_len > limits.max_output_samples().get() {
        return Err(RxCtleFfeErrorV1::ResourceLimitExceeded);
    }
    Ok(input_len)
}

fn checked_stage_budget(
    input_len: usize,
    kernel_len: usize,
    limits: ConvolutionLimitsV1,
) -> Result<usize, RxCtleFfeErrorV1> {
    let work = input_len
        .checked_mul(kernel_len)
        .ok_or(RxCtleFfeErrorV1::ResourceCountOverflow)?;
    let output_len = input_len
        .checked_add(kernel_len)
        .and_then(|value| value.checked_sub(1))
        .ok_or(RxCtleFfeErrorV1::ResourceCountOverflow)?;
    if output_len > limits.max_output_samples().get()
        || work > limits.max_multiply_accumulates().get()
    {
        return Err(RxCtleFfeErrorV1::ResourceLimitExceeded);
    }
    Ok(output_len)
}

fn normalized_ctle_impulse(transfer: &CtleTransferV1) -> Result<Vec<FiniteF64>, RxCtleFfeErrorV1> {
    let raw = transfer.impulse.iter().map(|value| value.get());
    let scale = match transfer.normalization() {
        CtleNormalizationV1::None => 1.0,
        CtleNormalizationV1::UnitSum { target } => {
            let sum: f64 = raw.clone().sum();
            if !sum.is_finite() || sum == 0.0 || target.get() == 0.0 {
                return Err(RxCtleFfeErrorV1::InvalidNormalizationReference);
            }
            target.get() / sum
        }
        CtleNormalizationV1::PeakAbs { target } => {
            let peak = raw.clone().map(f64::abs).fold(0.0, f64::max);
            if !peak.is_finite() || peak == 0.0 || target.get() <= 0.0 {
                return Err(RxCtleFfeErrorV1::InvalidNormalizationReference);
            }
            target.get() / peak
        }
    };
    if !scale.is_finite() {
        return Err(RxCtleFfeErrorV1::NormalizationOverflow);
    }
    transfer
        .impulse
        .iter()
        .map(|value| FiniteF64::try_new(value.get() * scale, "normalized CTLE impulse"))
        .collect::<Result<Vec<_>, _>>()
        .map_err(Into::into)
}

fn chronological_cursor_index(ffe: &FfeProfileV1) -> usize {
    match ffe.order() {
        FfeTapOrderV1::AscendingTime => ffe.cursor_index(),
        FfeTapOrderV1::DescendingTime => ffe.taps().len() - 1 - ffe.cursor_index(),
    }
}

fn chronological_cursor_sample_index(ffe: &FfeProfileV1) -> Result<usize, RxCtleFfeErrorV1> {
    let cursor = chronological_cursor_index(ffe);
    match ffe.sampling() {
        FfeSamplingV1::SampleSpaced { .. } => Ok(cursor),
        FfeSamplingV1::UiSpaced { samples_per_ui, .. } => cursor
            .checked_mul(samples_per_ui.get())
            .ok_or(RxCtleFfeErrorV1::ResourceCountOverflow),
    }
}

fn materialize_ffe_taps(
    input_len: usize,
    ffe: &FfeProfileV1,
    input_interval: Seconds,
    limits: ConvolutionLimitsV1,
) -> Result<Vec<FiniteF64>, RxCtleFfeErrorV1> {
    let expanded_len = match ffe.sampling() {
        FfeSamplingV1::SampleSpaced { .. } => ffe.taps().len(),
        FfeSamplingV1::UiSpaced { samples_per_ui, .. } => ffe
            .taps()
            .len()
            .checked_sub(1)
            .and_then(|intervals| intervals.checked_mul(samples_per_ui.get()))
            .and_then(|last_index| last_index.checked_add(1))
            .ok_or(RxCtleFfeErrorV1::ResourceCountOverflow)?,
    };
    let _ = checked_stage_budget(input_len, expanded_len, limits)?;
    let mut chronological = ffe.taps().to_vec();
    if ffe.order() == FfeTapOrderV1::DescendingTime {
        chronological.reverse();
    }
    if ffe.sign() == FfeTapSignV1::Negated {
        chronological = chronological
            .into_iter()
            .map(|tap| FiniteF64::try_new(-tap.get(), "negated FFE tap"))
            .collect::<Result<Vec<_>, _>>()?;
    }
    match ffe.units() {
        FfeTapUnitsV1::NormalizedVoltageRatio => {}
    }
    match ffe.sampling() {
        FfeSamplingV1::SampleSpaced { sample_interval } => {
            if sample_interval.get() <= 0.0 {
                return Err(RxCtleFfeErrorV1::InvalidGridInterval);
            }
            if sample_interval != input_interval {
                return Err(RxCtleFfeErrorV1::FfeSampleIntervalMismatch);
            }
            Ok(chronological)
        }
        FfeSamplingV1::UiSpaced { ui, samples_per_ui } => {
            if ui.get() <= 0.0 {
                return Err(RxCtleFfeErrorV1::InvalidUi);
            }
            let interval = ui.get() / samples_per_ui.get() as f64;
            if !interval.is_finite() {
                return Err(RxCtleFfeErrorV1::InvalidUi);
            }
            if Seconds::try_new(interval)? != input_interval {
                return Err(RxCtleFfeErrorV1::FfeUiIntervalMismatch);
            }
            let length = expanded_len;
            let mut expanded = vec![FiniteF64::try_new(0.0, "FFE zero tap")?; length];
            for (index, tap) in chronological.into_iter().enumerate() {
                expanded[index * samples_per_ui.get()] = tap;
            }
            Ok(expanded)
        }
    }
}

fn rebase_waveform(waveform: &Waveform, start: Seconds) -> Result<Waveform, RxCtleFfeErrorV1> {
    let AxisView::Uniform { step, count, .. } = waveform.axis().view() else {
        return Err(RxCtleFfeErrorV1::NonUniformInputAxis);
    };
    let axis = Axis::uniform(start, NonZeroStep::try_new(step)?, count);
    Ok(Waveform::try_new(axis, waveform.samples().to_vec())?)
}

#[cfg(test)]
mod tests {
    use super::*;
    use sipi_types::{Axis, Volts};
    use std::num::NonZeroUsize;

    fn waveform(values: &[f64]) -> Waveform {
        let axis = Axis::uniform(
            Seconds::try_new(0.0).unwrap(),
            NonZeroStep::try_new(Seconds::try_new(1.0).unwrap()).unwrap(),
            NonZeroUsize::new(values.len()).unwrap(),
        );
        Waveform::try_new(
            axis,
            values
                .iter()
                .copied()
                .map(Volts::try_new)
                .collect::<Result<Vec<_>, _>>()
                .unwrap(),
        )
        .unwrap()
    }

    fn finite(values: &[f64]) -> Vec<FiniteF64> {
        values
            .iter()
            .copied()
            .map(|value| FiniteF64::try_new(value, "test value"))
            .collect::<Result<Vec<_>, _>>()
            .unwrap()
    }

    fn limits() -> ConvolutionLimitsV1 {
        ConvolutionLimitsV1::try_new(64, 512).unwrap()
    }

    #[test]
    fn explicit_ctle_then_ui_ffe_is_full_linear_and_metadata_bound() {
        let grid = CtleGridV1::try_new(
            Seconds::try_new(1.0).unwrap(),
            2,
            CtleGridOriginV1::InputSampleZero,
        )
        .unwrap();
        let ctle = CtleTransferV1::try_new(
            finite(&[1.0, 1.0]),
            grid,
            CtleNormalizationV1::None,
            CtleStateV1::ZeroInitial,
        )
        .unwrap();
        let ffe = FfeProfileV1::try_new(
            finite(&[1.0, -1.0]),
            FfeTapOrderV1::AscendingTime,
            0,
            FfeCursorConventionV1::FirstTapAtInputOrigin,
            FfeTapUnitsV1::NormalizedVoltageRatio,
            FfeTapSignV1::Direct,
            FfeSamplingV1::UiSpaced {
                ui: Seconds::try_new(2.0).unwrap(),
                samples_per_ui: NonZeroUsize::new(2).unwrap(),
            },
            FfeStateV1::ZeroInitial,
        )
        .unwrap();
        let profile =
            RxCtleFfeProfileV1::new(RxCtleStageV1::Explicit(ctle), RxFfeStageV1::Explicit(ffe));
        let result = apply_rx_ctle_ffe_v1(&waveform(&[1.0, 2.0]), &profile, limits()).unwrap();
        assert_eq!(
            result
                .ctle_output()
                .samples()
                .iter()
                .map(|sample| sample.get())
                .collect::<Vec<_>>(),
            [1.0, 3.0, 2.0]
        );
        assert_eq!(
            result.output().axis().view(),
            AxisView::Uniform {
                start: Seconds::try_new(0.0).unwrap(),
                step: Seconds::try_new(1.0).unwrap(),
                count: NonZeroUsize::new(5).unwrap(),
            }
        );
        assert_eq!(
            result
                .output()
                .samples()
                .iter()
                .map(|sample| sample.get())
                .collect::<Vec<_>>(),
            [1.0, 3.0, 1.0, -3.0, -2.0]
        );
    }

    #[test]
    fn ui_cursor_axis_uses_expanded_sample_index() {
        let ffe = FfeProfileV1::try_new(
            finite(&[2.0, 1.0, 3.0]),
            FfeTapOrderV1::AscendingTime,
            1,
            FfeCursorConventionV1::CursorAtInputOrigin,
            FfeTapUnitsV1::NormalizedVoltageRatio,
            FfeTapSignV1::Direct,
            FfeSamplingV1::UiSpaced {
                ui: Seconds::try_new(2.0).unwrap(),
                samples_per_ui: NonZeroUsize::new(2).unwrap(),
            },
            FfeStateV1::ZeroInitial,
        )
        .unwrap();
        let profile = RxCtleFfeProfileV1::new(RxCtleStageV1::Bypass, RxFfeStageV1::Explicit(ffe));
        let result = apply_rx_ctle_ffe_v1(&waveform(&[1.0]), &profile, limits()).unwrap();
        assert_eq!(
            result.output().axis().view(),
            AxisView::Uniform {
                start: Seconds::try_new(-2.0).unwrap(),
                step: Seconds::try_new(1.0).unwrap(),
                count: NonZeroUsize::new(5).unwrap(),
            }
        );
    }

    #[test]
    fn bypass_checks_output_limit_without_consuming_mac_budget() {
        let profile = RxCtleFfeProfileV1::new(RxCtleStageV1::Bypass, RxFfeStageV1::Bypass);
        let input = waveform(&[1.0, 2.0]);
        let result = apply_rx_ctle_ffe_v1(
            &input,
            &profile,
            ConvolutionLimitsV1::try_new(2, 1).unwrap(),
        )
        .unwrap();
        assert_eq!(result.ctle_output(), &input);
        assert_eq!(result.output(), &input);
        assert_eq!(
            apply_rx_ctle_ffe_v1(
                &input,
                &profile,
                ConvolutionLimitsV1::try_new(1, 1).unwrap(),
            ),
            Err(RxCtleFfeErrorV1::NamedFir(
                RxNamedFirErrorV1::ResourceLimitExceeded,
            ))
        );
    }

    #[test]
    fn cursor_origin_is_explicit_and_preserves_precursor_axis() {
        let ffe = FfeProfileV1::try_new(
            finite(&[2.0, 1.0, 3.0]),
            FfeTapOrderV1::AscendingTime,
            1,
            FfeCursorConventionV1::CursorAtInputOrigin,
            FfeTapUnitsV1::NormalizedVoltageRatio,
            FfeTapSignV1::Direct,
            FfeSamplingV1::SampleSpaced {
                sample_interval: Seconds::try_new(1.0).unwrap(),
            },
            FfeStateV1::ZeroInitial,
        )
        .unwrap();
        let profile = RxCtleFfeProfileV1::new(RxCtleStageV1::Bypass, RxFfeStageV1::Explicit(ffe));
        let result = apply_rx_ctle_ffe_v1(&waveform(&[1.0]), &profile, limits()).unwrap();
        assert_eq!(
            result.output().axis().view(),
            AxisView::Uniform {
                start: Seconds::try_new(-1.0).unwrap(),
                step: Seconds::try_new(1.0).unwrap(),
                count: NonZeroUsize::new(3).unwrap(),
            }
        );
    }

    #[test]
    fn invalid_explicit_metadata_fails_closed_without_profile_fallback() {
        let grid = CtleGridV1::try_new(
            Seconds::try_new(1.0).unwrap(),
            1,
            CtleGridOriginV1::InputSampleZero,
        )
        .unwrap();
        let ctle = CtleTransferV1::try_new(
            finite(&[1.0]),
            grid,
            CtleNormalizationV1::UnitSum {
                target: FiniteF64::try_new(0.0, "test target").unwrap(),
            },
            CtleStateV1::ZeroInitial,
        )
        .unwrap();
        let invalid_normalization =
            RxCtleFfeProfileV1::new(RxCtleStageV1::Explicit(ctle), RxFfeStageV1::Bypass);
        assert_eq!(
            apply_rx_ctle_ffe_v1(&waveform(&[1.0]), &invalid_normalization, limits()),
            Err(RxCtleFfeErrorV1::InvalidNormalizationReference)
        );
        let negative_peak = CtleTransferV1::try_new(
            finite(&[1.0]),
            CtleGridV1::try_new(
                Seconds::try_new(1.0).unwrap(),
                1,
                CtleGridOriginV1::InputSampleZero,
            )
            .unwrap(),
            CtleNormalizationV1::PeakAbs {
                target: FiniteF64::try_new(-1.0, "test target").unwrap(),
            },
            CtleStateV1::ZeroInitial,
        )
        .unwrap();
        let negative_peak_profile =
            RxCtleFfeProfileV1::new(RxCtleStageV1::Explicit(negative_peak), RxFfeStageV1::Bypass);
        assert_eq!(
            apply_rx_ctle_ffe_v1(&waveform(&[1.0]), &negative_peak_profile, limits()),
            Err(RxCtleFfeErrorV1::InvalidNormalizationReference)
        );
        let ffe = FfeProfileV1::try_new(
            finite(&[1.0]),
            FfeTapOrderV1::AscendingTime,
            2,
            FfeCursorConventionV1::FirstTapAtInputOrigin,
            FfeTapUnitsV1::NormalizedVoltageRatio,
            FfeTapSignV1::Direct,
            FfeSamplingV1::SampleSpaced {
                sample_interval: Seconds::try_new(1.0).unwrap(),
            },
            FfeStateV1::ZeroInitial,
        );
        assert_eq!(ffe, Err(RxCtleFfeErrorV1::CursorOutOfRange));

        let bounded_ffe = FfeProfileV1::try_new(
            finite(&[1.0, 1.0]),
            FfeTapOrderV1::AscendingTime,
            0,
            FfeCursorConventionV1::FirstTapAtInputOrigin,
            FfeTapUnitsV1::NormalizedVoltageRatio,
            FfeTapSignV1::Direct,
            FfeSamplingV1::UiSpaced {
                ui: Seconds::try_new(100.0).unwrap(),
                samples_per_ui: NonZeroUsize::new(100).unwrap(),
            },
            FfeStateV1::ZeroInitial,
        )
        .unwrap();
        let bounded_profile =
            RxCtleFfeProfileV1::new(RxCtleStageV1::Bypass, RxFfeStageV1::Explicit(bounded_ffe));
        assert_eq!(
            apply_rx_ctle_ffe_v1(
                &waveform(&[1.0]),
                &bounded_profile,
                ConvolutionLimitsV1::try_new(8, 8).unwrap(),
            ),
            Err(RxCtleFfeErrorV1::ResourceLimitExceeded)
        );
    }
}
