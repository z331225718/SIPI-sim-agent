#![forbid(unsafe_code)]

//! A bounded, product-owned one-node RC/PULSE transient primitive.
//!
//! This crate accepts no netlist text and implements no generic circuit model.
//! The only topology is an ideal PULSE source, one series resistor, and one
//! capacitor to an explicit reference. The existing fixed profile is a wrapper
//! around this sole numerical core.

use std::{error::Error, fmt, num::NonZeroUsize};

use sipi_runtime::RunContext;
use sipi_types::{Axis, FiniteF64, Ohms, Seconds, TypeError, Volts, Waveform};

mod parsed_rc_measurement_v1;

pub use parsed_rc_measurement_v1::{
    EXACT_RC_MEASUREMENT_DECK_POLICY_V1, ExactRcMeasurementDeckErrorV1,
    ExactRcMeasurementDeckLimitsV1, ExactRcMeasurementDeckV1, ExactRcMeasurementResultV1,
    ExactRcMeasurementRunV1, parse_and_simulate_exact_rc_measurement_deck_v1,
    parse_exact_rc_measurement_deck_v1, simulate_exact_rc_measurement_deck_v1,
};

/// Identity of the externally compared fixed RC/PULSE profile.
pub const RC_PULSE_PROFILE_ID: &str = "tran-rc-pulse-v1";

const OUTPUT_TIMES_S: [f64; 4] = [0.0, 1.0e-6, 2.0e-6, 3.0e-6];
const RESISTANCE_OHM: f64 = 1.0e3;
const CAPACITANCE_F: f64 = 1.0e-6;
const PULSE_LOW_V: f64 = 0.0;
const PULSE_HIGH_V: f64 = 1.0;
const PULSE_DELAY_S: f64 = 1.0e-6;
const PULSE_RISE_S: f64 = 1.0e-9;
const PULSE_FALL_S: f64 = 1.0e-9;
const PULSE_WIDTH_S: f64 = 1.0e-5;
const PULSE_PERIOD_S: f64 = 2.0e-5;

/// Explicit ideal PULSE parameters for the one-node RC topology.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct IdealPulseV1 {
    low: Volts,
    high: Volts,
    delay: Seconds,
    rise: Seconds,
    fall: Seconds,
    width: Seconds,
    period: Seconds,
}

impl IdealPulseV1 {
    /// Creates a continuous periodic PULSE source with no implicit defaults.
    pub fn try_new(
        low: Volts,
        high: Volts,
        delay: Seconds,
        rise: Seconds,
        fall: Seconds,
        width: Seconds,
        period: Seconds,
    ) -> Result<Self, TranError> {
        if delay.get() < 0.0 {
            return Err(TranError::InvalidPulseDelay);
        }
        if rise.get() <= 0.0 || fall.get() <= 0.0 || period.get() <= 0.0 {
            return Err(TranError::InvalidPulseDuration);
        }
        if width.get() < 0.0 {
            return Err(TranError::InvalidPulseWidth);
        }

        let corner_end = delay.get() + rise.get() + width.get() + fall.get();
        if !corner_end.is_finite() {
            return Err(TranError::NonFiniteComputation);
        }
        if corner_end > period.get() {
            return Err(TranError::InvalidPulseCornerOrder);
        }

        Ok(Self {
            low,
            high,
            delay,
            rise,
            fall,
            width,
            period,
        })
    }

    pub const fn low(&self) -> Volts {
        self.low
    }

    pub const fn high(&self) -> Volts {
        self.high
    }

    pub const fn delay(&self) -> Seconds {
        self.delay
    }

    pub const fn rise(&self) -> Seconds {
        self.rise
    }

    pub const fn fall(&self) -> Seconds {
        self.fall
    }

    pub const fn width(&self) -> Seconds {
        self.width
    }

    pub const fn period(&self) -> Seconds {
        self.period
    }

    fn voltage_at(self, time_s: f64) -> f64 {
        let phase = time_s.rem_euclid(self.period.get());
        let rise_end = self.delay.get() + self.rise.get();
        let high_end = rise_end + self.width.get();
        let fall_end = high_end + self.fall.get();
        if phase < self.delay.get() {
            self.low.get()
        } else if phase < rise_end {
            self.low.get()
                + (self.high.get() - self.low.get()) * (phase - self.delay.get()) / self.rise.get()
        } else if phase < high_end {
            self.high.get()
        } else if phase < fall_end {
            self.high.get()
                - (self.high.get() - self.low.get()) * (phase - high_end) / self.fall.get()
        } else {
            self.low.get()
        }
    }

    fn corner_offsets(self) -> [f64; 4] {
        [
            self.delay.get(),
            self.delay.get() + self.rise.get(),
            self.delay.get() + self.rise.get() + self.width.get(),
            self.delay.get() + self.rise.get() + self.width.get() + self.fall.get(),
        ]
    }
}

/// Typed request for one source, one resistor, and one capacitor to reference.
///
/// The explicit output axis starts at zero and is also part of the deterministic
/// backward-Euler breakpoint set. It is not a resampling request.
#[derive(Clone, Debug, PartialEq)]
pub struct OneNodeRcPulseRequestV1 {
    output_axis: Axis<Seconds>,
    resistance: Ohms,
    capacitance_farads: FiniteF64,
    initial_output: Volts,
    pulse: IdealPulseV1,
}

/// Explicit caller-owned piecewise-linear voltage source.
///
/// The source is defined only on its finite knot axis. It does not hold its
/// first or last value beyond that axis, and it has no periodic behavior.
#[derive(Clone, Debug, PartialEq)]
pub struct PiecewiseLinearVoltageV1 {
    knot_axis: Axis<Seconds>,
    knot_values: Vec<Volts>,
}

impl PiecewiseLinearVoltageV1 {
    pub fn try_new(knot_times: Vec<Seconds>, knot_values: Vec<Volts>) -> Result<Self, TranError> {
        if knot_times.len() != knot_values.len() {
            return Err(TranError::PwlKnotValueCountMismatch);
        }
        if knot_times.len() < 2 {
            return Err(TranError::PwlKnotAxisTooShort);
        }
        validate_pwl_knot_times(&knot_times)?;
        Ok(Self {
            knot_axis: Axis::explicit(knot_times)?,
            knot_values,
        })
    }

    pub fn knot_axis(&self) -> &Axis<Seconds> {
        &self.knot_axis
    }

    pub fn knot_values(&self) -> &[Volts] {
        &self.knot_values
    }

    fn voltage_at(&self, time_s: f64) -> Result<f64, TranError> {
        let times = explicit_axis_values(&self.knot_axis)?;
        if time_s < times[0] || time_s > *times.last().expect("validated PWL knot axis") {
            return Err(TranError::PwlOutsideCoverage);
        }
        match times.binary_search_by(|value| value.total_cmp(&time_s)) {
            Ok(index) => Ok(self.knot_values[index].get()),
            Err(upper) if upper > 0 && upper < times.len() => {
                let lower = upper - 1;
                let fraction = (time_s - times[lower]) / (times[upper] - times[lower]);
                let value = self.knot_values[lower].get()
                    + fraction * (self.knot_values[upper].get() - self.knot_values[lower].get());
                if value.is_finite() {
                    Ok(value)
                } else {
                    Err(TranError::NonFiniteComputation)
                }
            }
            _ => Err(TranError::PwlOutsideCoverage),
        }
    }
}

/// Typed request for a one-node RC topology with an explicit PWL voltage source.
///
/// This is deliberately a fixed topology, not netlist text or a generic
/// transient-circuit request. PWL knots and output samples begin at zero; the
/// final PWL knot must exactly own the last requested output instant.
#[derive(Clone, Debug, PartialEq)]
pub struct OneNodeRcPwlRequestV1 {
    output_axis: Axis<Seconds>,
    resistance: Ohms,
    capacitance_farads: FiniteF64,
    initial_output: Volts,
    source: PiecewiseLinearVoltageV1,
}

impl OneNodeRcPwlRequestV1 {
    pub fn try_new(
        output_times: Vec<Seconds>,
        resistance: Ohms,
        capacitance_farads: FiniteF64,
        initial_output: Volts,
        source: PiecewiseLinearVoltageV1,
    ) -> Result<Self, TranError> {
        validate_output_times(&output_times)?;
        if resistance.get() <= 0.0 {
            return Err(TranError::InvalidResistance);
        }
        if capacitance_farads.get() <= 0.0 {
            return Err(TranError::InvalidCapacitance);
        }
        let source_times = explicit_axis_values(source.knot_axis())?;
        if source_times[0] != 0.0
            || *source_times.last().expect("validated PWL knot axis")
                != output_times.last().expect("validated output axis").get()
        {
            return Err(TranError::PwlCoverageMismatch);
        }
        Ok(Self {
            output_axis: Axis::explicit(output_times)?,
            resistance,
            capacitance_farads,
            initial_output,
            source,
        })
    }

    pub fn output_axis(&self) -> &Axis<Seconds> {
        &self.output_axis
    }

    pub const fn resistance(&self) -> Ohms {
        self.resistance
    }

    pub const fn capacitance_farads(&self) -> FiniteF64 {
        self.capacitance_farads
    }

    pub const fn initial_output(&self) -> Volts {
        self.initial_output
    }

    pub fn source(&self) -> &PiecewiseLinearVoltageV1 {
        &self.source
    }
}

impl OneNodeRcPulseRequestV1 {
    pub fn try_new(
        output_times: Vec<Seconds>,
        resistance: Ohms,
        capacitance_farads: FiniteF64,
        initial_output: Volts,
        pulse: IdealPulseV1,
    ) -> Result<Self, TranError> {
        validate_output_times(&output_times)?;
        if resistance.get() <= 0.0 {
            return Err(TranError::InvalidResistance);
        }
        if capacitance_farads.get() <= 0.0 {
            return Err(TranError::InvalidCapacitance);
        }
        Ok(Self {
            output_axis: Axis::explicit(output_times)?,
            resistance,
            capacitance_farads,
            initial_output,
            pulse,
        })
    }

    pub fn output_axis(&self) -> &Axis<Seconds> {
        &self.output_axis
    }

    pub const fn resistance(&self) -> Ohms {
        self.resistance
    }

    pub const fn capacitance_farads(&self) -> FiniteF64 {
        self.capacitance_farads
    }

    pub const fn initial_output(&self) -> Volts {
        self.initial_output
    }

    pub const fn pulse(&self) -> IdealPulseV1 {
        self.pulse
    }
}

/// Explicit bounds for a one-node RC/PULSE evaluation.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct OneNodeRcPulseLimitsV1 {
    max_output_samples: NonZeroUsize,
    max_integration_breakpoints: NonZeroUsize,
}

/// Explicit bounds for a one-node RC/PWL evaluation.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct OneNodeRcPwlLimitsV1 {
    max_output_samples: NonZeroUsize,
    max_integration_breakpoints: NonZeroUsize,
}

impl OneNodeRcPwlLimitsV1 {
    pub const fn new(
        max_output_samples: NonZeroUsize,
        max_integration_breakpoints: NonZeroUsize,
    ) -> Self {
        Self {
            max_output_samples,
            max_integration_breakpoints,
        }
    }
}

impl OneNodeRcPulseLimitsV1 {
    pub const fn new(
        max_output_samples: NonZeroUsize,
        max_integration_breakpoints: NonZeroUsize,
    ) -> Self {
        Self {
            max_output_samples,
            max_integration_breakpoints,
        }
    }
}

/// A typed request for the sole externally compared v1 RC/PULSE profile.
///
/// Its fields are private so callers cannot silently expand the fixed profile's
/// device, sampling, or initial-condition semantics.
#[derive(Clone, Copy, Debug, Default, Eq, PartialEq)]
pub struct RcPulseTransientV1 {
    private: (),
}

impl RcPulseTransientV1 {
    /// Creates the exact RC/PULSE request defined by `tran-rc-pulse-v1`.
    pub const fn fixed_profile() -> Self {
        Self { private: () }
    }

    pub const fn profile_id(&self) -> &'static str {
        RC_PULSE_PROFILE_ID
    }
}

/// Product-owned result for a one-node RC/PULSE transient request.
#[derive(Clone, Debug, PartialEq)]
pub struct RcPulseTransientResultV1 {
    time_axis: Axis<Seconds>,
    voltage_in: Waveform,
    voltage_out: Waveform,
}

impl RcPulseTransientResultV1 {
    pub fn time_axis(&self) -> &Axis<Seconds> {
        &self.time_axis
    }

    pub fn voltage_in(&self) -> &Waveform {
        &self.voltage_in
    }

    pub fn voltage_out(&self) -> &Waveform {
        &self.voltage_out
    }
}

/// Fail-closed errors for the bounded one-node solver.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum TranError {
    Invariant(TypeError),
    Runtime(sipi_runtime::RuntimeFailure),
    InvalidOutputAxisStart,
    NonIncreasingOutputAxis,
    InvalidResistance,
    InvalidCapacitance,
    InvalidPulseDelay,
    InvalidPulseDuration,
    InvalidPulseWidth,
    InvalidPulseCornerOrder,
    PwlKnotValueCountMismatch,
    PwlKnotAxisTooShort,
    InvalidPwlKnotAxisStart,
    NonIncreasingPwlKnotAxis,
    PwlCoverageMismatch,
    PwlOutsideCoverage,
    OutputLimitExceeded,
    BreakpointLimitExceeded,
    BreakpointCountOverflow,
    NonFiniteComputation,
}

impl fmt::Display for TranError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Invariant(error) => error.fmt(formatter),
            Self::Runtime(error) => write!(formatter, "runtime failure: {}", error.code()),
            Self::InvalidOutputAxisStart => write!(formatter, "output axis must start at zero"),
            Self::NonIncreasingOutputAxis => {
                write!(formatter, "output axis must strictly increase")
            }
            Self::InvalidResistance => write!(formatter, "resistance must be positive"),
            Self::InvalidCapacitance => write!(formatter, "capacitance must be positive"),
            Self::InvalidPulseDelay => write!(formatter, "pulse delay must be non-negative"),
            Self::InvalidPulseDuration => {
                write!(formatter, "pulse rise, fall, and period must be positive")
            }
            Self::InvalidPulseWidth => write!(formatter, "pulse width must be non-negative"),
            Self::InvalidPulseCornerOrder => {
                write!(formatter, "pulse corners must fit within one period")
            }
            Self::PwlKnotValueCountMismatch => {
                write!(
                    formatter,
                    "PWL knot times and values must have equal length"
                )
            }
            Self::PwlKnotAxisTooShort => {
                write!(formatter, "PWL source requires at least two knots")
            }
            Self::InvalidPwlKnotAxisStart => write!(formatter, "PWL knot axis must start at zero"),
            Self::NonIncreasingPwlKnotAxis => {
                write!(formatter, "PWL knot axis must strictly increase")
            }
            Self::PwlCoverageMismatch => {
                write!(formatter, "PWL source must end at the final output time")
            }
            Self::PwlOutsideCoverage => {
                write!(formatter, "PWL evaluation is outside source coverage")
            }
            Self::OutputLimitExceeded => write!(formatter, "output sample limit exceeded"),
            Self::BreakpointLimitExceeded => {
                write!(formatter, "integration breakpoint limit exceeded")
            }
            Self::BreakpointCountOverflow => {
                write!(formatter, "integration breakpoint count overflow")
            }
            Self::NonFiniteComputation => write!(formatter, "transient computation is non-finite"),
        }
    }
}

impl Error for TranError {}

impl From<TypeError> for TranError {
    fn from(value: TypeError) -> Self {
        Self::Invariant(value)
    }
}

impl From<sipi_runtime::RuntimeFailure> for TranError {
    fn from(value: sipi_runtime::RuntimeFailure) -> Self {
        Self::Runtime(value)
    }
}

/// Simulates a bounded one-node RC/PULSE request with f64 backward Euler.
pub fn simulate_one_node_rc_pulse(
    request: &OneNodeRcPulseRequestV1,
    limits: OneNodeRcPulseLimitsV1,
) -> Result<RcPulseTransientResultV1, TranError> {
    simulate_one_node_rc_pulse_checked(request, limits, || Ok(()))
}

/// Simulates a bounded one-node RC/PULSE request with cooperative checkpoints.
pub fn simulate_one_node_rc_pulse_with_context(
    request: &OneNodeRcPulseRequestV1,
    limits: OneNodeRcPulseLimitsV1,
    context: &RunContext,
) -> Result<RcPulseTransientResultV1, TranError> {
    simulate_one_node_rc_pulse_checked(request, limits, || context.checkpoint().map_err(Into::into))
}

/// Simulates a bounded one-node RC/PWL request with f64 backward Euler.
pub fn simulate_one_node_rc_pwl(
    request: &OneNodeRcPwlRequestV1,
    limits: OneNodeRcPwlLimitsV1,
) -> Result<RcPulseTransientResultV1, TranError> {
    simulate_one_node_rc_pwl_checked(request, limits, || Ok(()))
}

/// Simulates a bounded one-node RC/PWL request with cooperative checkpoints.
pub fn simulate_one_node_rc_pwl_with_context(
    request: &OneNodeRcPwlRequestV1,
    limits: OneNodeRcPwlLimitsV1,
    context: &RunContext,
) -> Result<RcPulseTransientResultV1, TranError> {
    simulate_one_node_rc_pwl_checked(request, limits, || context.checkpoint().map_err(Into::into))
}

/// Simulates the exact fixed v1 RC/PULSE profile through the sole numerical core.
pub fn simulate_rc_pulse(
    request: RcPulseTransientV1,
) -> Result<RcPulseTransientResultV1, TranError> {
    let _ = request;
    let request = fixed_profile_request()?;
    simulate_one_node_rc_pulse(&request, fixed_profile_limits())
}

/// Runs the fixed profile with cooperative checkpoints supplied by its caller.
pub fn simulate_rc_pulse_with_context(
    request: RcPulseTransientV1,
    context: &RunContext,
) -> Result<RcPulseTransientResultV1, TranError> {
    let _ = request;
    let request = fixed_profile_request()?;
    simulate_one_node_rc_pulse_with_context(&request, fixed_profile_limits(), context)
}

fn simulate_one_node_rc_pulse_checked(
    request: &OneNodeRcPulseRequestV1,
    limits: OneNodeRcPulseLimitsV1,
    mut checkpoint: impl FnMut() -> Result<(), TranError>,
) -> Result<RcPulseTransientResultV1, TranError> {
    checkpoint()?;
    let output_times = explicit_axis_values(request.output_axis())?;
    if output_times.len() > limits.max_output_samples.get() {
        return Err(TranError::OutputLimitExceeded);
    }
    let breakpoints = build_breakpoints(&output_times, request.pulse, limits, &mut checkpoint)?;
    checkpoint()?;

    let mut voltage_out = request.initial_output.get();
    let mut voltage_in_samples = Vec::with_capacity(output_times.len());
    let mut voltage_out_samples = Vec::with_capacity(output_times.len());
    let mut output_index = 0usize;
    let mut current_time = breakpoints[0];

    voltage_in_samples.push(volts(request.pulse.voltage_at(current_time))?);
    voltage_out_samples.push(volts(voltage_out)?);
    output_index += 1;

    for next_time in breakpoints.into_iter().skip(1) {
        checkpoint()?;
        voltage_out = backward_euler_step(
            voltage_out,
            request.pulse.voltage_at(next_time),
            next_time - current_time,
            request.resistance.get(),
            request.capacitance_farads.get(),
        )?;
        current_time = next_time;
        if output_index < output_times.len() && current_time == output_times[output_index] {
            voltage_in_samples.push(volts(request.pulse.voltage_at(current_time))?);
            voltage_out_samples.push(volts(voltage_out)?);
            output_index += 1;
        }
    }

    if output_index != output_times.len() {
        return Err(TranError::BreakpointCountOverflow);
    }
    let axis = request.output_axis.clone();
    let voltage_in = Waveform::try_new(axis.clone(), voltage_in_samples)?;
    checkpoint()?;
    let voltage_out = Waveform::try_new(axis.clone(), voltage_out_samples)?;
    Ok(RcPulseTransientResultV1 {
        time_axis: axis,
        voltage_in,
        voltage_out,
    })
}

fn simulate_one_node_rc_pwl_checked(
    request: &OneNodeRcPwlRequestV1,
    limits: OneNodeRcPwlLimitsV1,
    mut checkpoint: impl FnMut() -> Result<(), TranError>,
) -> Result<RcPulseTransientResultV1, TranError> {
    checkpoint()?;
    let output_times = explicit_axis_values(request.output_axis())?;
    if output_times.len() > limits.max_output_samples.get() {
        return Err(TranError::OutputLimitExceeded);
    }
    let source_times = explicit_axis_values(request.source().knot_axis())?;
    let breakpoints = build_pwl_breakpoints(&output_times, &source_times, limits, &mut checkpoint)?;
    checkpoint()?;

    let mut voltage_out = request.initial_output().get();
    let mut voltage_in_samples = Vec::with_capacity(output_times.len());
    let mut voltage_out_samples = Vec::with_capacity(output_times.len());
    let mut output_index = 0usize;
    let mut current_time = breakpoints[0];

    voltage_in_samples.push(volts(request.source().voltage_at(current_time)?)?);
    voltage_out_samples.push(volts(voltage_out)?);
    output_index += 1;

    for next_time in breakpoints.into_iter().skip(1) {
        checkpoint()?;
        voltage_out = backward_euler_step(
            voltage_out,
            request.source().voltage_at(next_time)?,
            next_time - current_time,
            request.resistance().get(),
            request.capacitance_farads().get(),
        )?;
        current_time = next_time;
        if output_index < output_times.len() && current_time == output_times[output_index] {
            voltage_in_samples.push(volts(request.source().voltage_at(current_time)?)?);
            voltage_out_samples.push(volts(voltage_out)?);
            output_index += 1;
        }
    }

    if output_index != output_times.len() {
        return Err(TranError::BreakpointCountOverflow);
    }
    let axis = request.output_axis().clone();
    let voltage_in = Waveform::try_new(axis.clone(), voltage_in_samples)?;
    checkpoint()?;
    let voltage_out = Waveform::try_new(axis.clone(), voltage_out_samples)?;
    Ok(RcPulseTransientResultV1 {
        time_axis: axis,
        voltage_in,
        voltage_out,
    })
}

fn fixed_profile_request() -> Result<OneNodeRcPulseRequestV1, TranError> {
    let pulse = IdealPulseV1::try_new(
        volts(PULSE_LOW_V)?,
        volts(PULSE_HIGH_V)?,
        seconds(PULSE_DELAY_S)?,
        seconds(PULSE_RISE_S)?,
        seconds(PULSE_FALL_S)?,
        seconds(PULSE_WIDTH_S)?,
        seconds(PULSE_PERIOD_S)?,
    )?;
    OneNodeRcPulseRequestV1::try_new(
        OUTPUT_TIMES_S
            .into_iter()
            .map(seconds)
            .collect::<Result<Vec<_>, _>>()?,
        Ohms::try_new(RESISTANCE_OHM)?,
        FiniteF64::try_new(CAPACITANCE_F, "capacitance farads")?,
        volts(0.0)?,
        pulse,
    )
}

fn fixed_profile_limits() -> OneNodeRcPulseLimitsV1 {
    OneNodeRcPulseLimitsV1::new(
        NonZeroUsize::new(OUTPUT_TIMES_S.len()).expect("fixed output limit"),
        NonZeroUsize::new(5).expect("fixed breakpoint limit"),
    )
}

fn validate_output_times(times: &[Seconds]) -> Result<(), TranError> {
    let Some(first) = times.first() else {
        return Err(TypeError::Empty {
            kind: "output axis",
        }
        .into());
    };
    if first.get() != 0.0 {
        return Err(TranError::InvalidOutputAxisStart);
    }
    if times.windows(2).any(|pair| pair[0].get() >= pair[1].get()) {
        return Err(TranError::NonIncreasingOutputAxis);
    }
    Ok(())
}

fn validate_pwl_knot_times(times: &[Seconds]) -> Result<(), TranError> {
    let Some(first) = times.first() else {
        return Err(TranError::PwlKnotAxisTooShort);
    };
    if first.get() != 0.0 {
        return Err(TranError::InvalidPwlKnotAxisStart);
    }
    if times.windows(2).any(|pair| pair[0].get() >= pair[1].get()) {
        return Err(TranError::NonIncreasingPwlKnotAxis);
    }
    Ok(())
}

fn explicit_axis_values(axis: &Axis<Seconds>) -> Result<Vec<f64>, TranError> {
    let sipi_types::AxisView::Explicit(values) = axis.view() else {
        return Err(TranError::NonIncreasingOutputAxis);
    };
    Ok(values.iter().map(|value| value.get()).collect())
}

fn build_breakpoints(
    output_times: &[f64],
    pulse: IdealPulseV1,
    limits: OneNodeRcPulseLimitsV1,
    checkpoint: &mut impl FnMut() -> Result<(), TranError>,
) -> Result<Vec<f64>, TranError> {
    let last_time = *output_times.last().expect("validated non-empty axis");
    let mut values = output_times.to_vec();
    if values.len() > limits.max_integration_breakpoints.get() {
        return Err(TranError::BreakpointLimitExceeded);
    }
    let corners = pulse.corner_offsets();
    let mut cycle_start: f64 = 0.0;
    loop {
        checkpoint()?;
        for offset in corners {
            let corner = cycle_start + offset;
            if !corner.is_finite() {
                return Err(TranError::BreakpointCountOverflow);
            }
            if corner > 0.0 && corner <= last_time {
                match values.binary_search_by(|value| value.total_cmp(&corner)) {
                    Ok(_) => {}
                    Err(index) => {
                        values.insert(index, corner);
                        if values.len() > limits.max_integration_breakpoints.get() {
                            return Err(TranError::BreakpointLimitExceeded);
                        }
                    }
                }
            }
        }
        let next_cycle_start = cycle_start + pulse.period.get();
        if next_cycle_start > last_time {
            break;
        }
        if next_cycle_start <= cycle_start {
            return Err(TranError::BreakpointCountOverflow);
        }
        cycle_start = next_cycle_start;
    }
    Ok(values)
}

fn build_pwl_breakpoints(
    output_times: &[f64],
    source_times: &[f64],
    limits: OneNodeRcPwlLimitsV1,
    checkpoint: &mut impl FnMut() -> Result<(), TranError>,
) -> Result<Vec<f64>, TranError> {
    let mut values = output_times.to_vec();
    if values.len() > limits.max_integration_breakpoints.get() {
        return Err(TranError::BreakpointLimitExceeded);
    }
    for time in source_times {
        checkpoint()?;
        match values.binary_search_by(|value| value.total_cmp(time)) {
            Ok(_) => {}
            Err(index) => {
                values.insert(index, *time);
                if values.len() > limits.max_integration_breakpoints.get() {
                    return Err(TranError::BreakpointLimitExceeded);
                }
            }
        }
    }
    Ok(values)
}

fn backward_euler_step(
    previous: f64,
    source_endpoint: f64,
    step_s: f64,
    resistance_ohm: f64,
    capacitance_f: f64,
) -> Result<f64, TranError> {
    let time_constant = resistance_ohm * capacitance_f;
    let next =
        (previous + (step_s / time_constant) * source_endpoint) / (1.0 + step_s / time_constant);
    if next.is_finite() {
        Ok(next)
    } else {
        Err(TranError::NonFiniteComputation)
    }
}

fn seconds(value: f64) -> Result<Seconds, TranError> {
    Seconds::try_new(value).map_err(Into::into)
}

fn volts(value: f64) -> Result<Volts, TranError> {
    Volts::try_new(value).map_err(Into::into)
}

#[cfg(test)]
mod tests {
    use super::*;
    use sipi_runtime::{CancelReason, RunId, RunPolicy, Runtime};
    use sipi_types::AxisView;

    fn pulse(
        low: f64,
        high: f64,
        delay: f64,
        rise: f64,
        fall: f64,
        width: f64,
        period: f64,
    ) -> IdealPulseV1 {
        IdealPulseV1::try_new(
            volts(low).unwrap(),
            volts(high).unwrap(),
            seconds(delay).unwrap(),
            seconds(rise).unwrap(),
            seconds(fall).unwrap(),
            seconds(width).unwrap(),
            seconds(period).unwrap(),
        )
        .unwrap()
    }

    fn request(times: &[f64], low: f64, high: f64, initial: f64) -> OneNodeRcPulseRequestV1 {
        OneNodeRcPulseRequestV1::try_new(
            times
                .iter()
                .copied()
                .map(seconds)
                .collect::<Result<Vec<_>, _>>()
                .unwrap(),
            Ohms::try_new(1_000.0).unwrap(),
            FiniteF64::try_new(1.0e-6, "capacitance farads").unwrap(),
            volts(initial).unwrap(),
            pulse(low, high, 1.0e-9, 1.0e-12, 1.0e-12, 1.0, 2.0),
        )
        .unwrap()
    }

    fn limits(outputs: usize, breakpoints: usize) -> OneNodeRcPulseLimitsV1 {
        OneNodeRcPulseLimitsV1::new(
            NonZeroUsize::new(outputs).unwrap(),
            NonZeroUsize::new(breakpoints).unwrap(),
        )
    }

    fn pwl_source(knots: &[(f64, f64)]) -> PiecewiseLinearVoltageV1 {
        PiecewiseLinearVoltageV1::try_new(
            knots
                .iter()
                .map(|(time, _)| seconds(*time))
                .collect::<Result<Vec<_>, _>>()
                .unwrap(),
            knots
                .iter()
                .map(|(_, voltage)| volts(*voltage))
                .collect::<Result<Vec<_>, _>>()
                .unwrap(),
        )
        .unwrap()
    }

    fn pwl_request(
        output_times: &[f64],
        source: PiecewiseLinearVoltageV1,
    ) -> OneNodeRcPwlRequestV1 {
        OneNodeRcPwlRequestV1::try_new(
            output_times
                .iter()
                .copied()
                .map(seconds)
                .collect::<Result<Vec<_>, _>>()
                .unwrap(),
            Ohms::try_new(1.0).unwrap(),
            FiniteF64::try_new(1.0, "capacitance farads").unwrap(),
            volts(0.0).unwrap(),
            source,
        )
        .unwrap()
    }

    fn pwl_limits(outputs: usize, breakpoints: usize) -> OneNodeRcPwlLimitsV1 {
        OneNodeRcPwlLimitsV1::new(
            NonZeroUsize::new(outputs).unwrap(),
            NonZeroUsize::new(breakpoints).unwrap(),
        )
    }

    fn output_values(result: &RcPulseTransientResultV1) -> Vec<f64> {
        result
            .voltage_out()
            .samples()
            .iter()
            .map(|value| value.get())
            .collect()
    }

    #[test]
    fn fixed_profile_keeps_its_harness_bits_through_the_shared_core() {
        let fixed = simulate_rc_pulse(RcPulseTransientV1::fixed_profile()).unwrap();
        let direct =
            simulate_one_node_rc_pulse(&fixed_profile_request().unwrap(), fixed_profile_limits())
                .unwrap();
        assert_eq!(fixed, direct);
        assert_eq!(
            output_values(&fixed)
                .iter()
                .map(|value| value.to_bits())
                .collect::<Vec<_>>(),
            vec![0, 0, 4_562_249_906_436_303_834, 4_566_751_202_524_209_188]
        );
        assert_eq!(
            fixed.time_axis().view(),
            AxisView::Explicit(&[
                Seconds::try_new(0.0).unwrap(),
                Seconds::try_new(1.0e-6).unwrap(),
                Seconds::try_new(2.0e-6).unwrap(),
                Seconds::try_new(3.0e-6).unwrap(),
            ])
        );
    }

    #[test]
    fn parameterized_request_uses_requested_axis_and_source_corners() {
        let request = request(&[0.0, 1.0e-6, 2.0e-6], 0.0, 1.0, 0.0);
        let result = simulate_one_node_rc_pulse(&request, limits(3, 8)).unwrap();
        assert_eq!(
            result
                .voltage_in()
                .samples()
                .iter()
                .map(|value| value.get())
                .collect::<Vec<_>>(),
            vec![0.0, 1.0, 1.0]
        );
        assert_eq!(result.voltage_out().samples().len(), 3);
        assert!(output_values(&result).iter().all(|value| value.is_finite()));
    }

    #[test]
    fn backward_euler_refines_toward_independent_constant_rc_closed_form() {
        let coarse = request(&[0.0, 1.0e-6], 0.0, 1.0, 0.0);
        let fine = request(&[0.0, 0.5e-6, 1.0e-6], 0.0, 1.0, 0.0);
        let coarse_value =
            output_values(&simulate_one_node_rc_pulse(&coarse, limits(2, 8)).unwrap())[1];
        let fine_value =
            output_values(&simulate_one_node_rc_pulse(&fine, limits(3, 8)).unwrap())[2];
        let exact = 1.0_f64 - (-1.0e-6_f64 / (1_000.0_f64 * 1.0e-6_f64)).exp();
        assert!(coarse_value <= fine_value && fine_value <= exact);
        assert!(exact - fine_value < exact - coarse_value);
    }

    #[test]
    fn response_is_linear_under_source_and_initial_offset_and_scale() {
        let baseline = request(&[0.0, 1.0e-6, 2.0e-6], 0.1, 0.9, 0.1);
        let shifted = request(&[0.0, 1.0e-6, 2.0e-6], 3.1, 3.9, 3.1);
        let scaled = request(&[0.0, 1.0e-6, 2.0e-6], 0.25, 2.25, 0.25);
        let baseline = output_values(&simulate_one_node_rc_pulse(&baseline, limits(3, 8)).unwrap());
        let shifted = output_values(&simulate_one_node_rc_pulse(&shifted, limits(3, 8)).unwrap());
        let scaled = output_values(&simulate_one_node_rc_pulse(&scaled, limits(3, 8)).unwrap());
        for ((base, shifted), scaled) in baseline.iter().zip(shifted).zip(scaled) {
            assert!((shifted - (base + 3.0)).abs() <= 1.0e-13);
            assert!((scaled - base * 2.5).abs() <= 1.0e-13);
        }
    }

    #[test]
    fn pwl_source_inserts_non_output_knot_before_backward_euler_step() {
        let request = pwl_request(
            &[0.0, 2.0],
            pwl_source(&[(0.0, 0.0), (1.0, 1.0), (2.0, 1.0)]),
        );
        let result = simulate_one_node_rc_pwl(&request, pwl_limits(2, 3)).unwrap();
        assert_eq!(
            result
                .voltage_in()
                .samples()
                .iter()
                .map(|value| value.get())
                .collect::<Vec<_>>(),
            vec![0.0, 1.0]
        );
        assert_eq!(
            output_values(&result)
                .iter()
                .map(|value| value.to_bits())
                .collect::<Vec<_>>(),
            vec![0, 4_604_930_618_986_332_160]
        );
    }

    #[test]
    fn pwl_interpolates_at_output_endpoints_and_is_deterministic() {
        let request = pwl_request(
            &[0.0, 0.5, 1.0],
            pwl_source(&[(0.0, 0.0), (0.75, 1.5), (1.0, 2.0)]),
        );
        let first = simulate_one_node_rc_pwl(&request, pwl_limits(3, 4)).unwrap();
        let second = simulate_one_node_rc_pwl(&request, pwl_limits(3, 4)).unwrap();
        assert_eq!(first, second);
        assert_eq!(
            first
                .voltage_in()
                .samples()
                .iter()
                .map(|value| value.get())
                .collect::<Vec<_>>(),
            vec![0.0, 1.0, 2.0]
        );
    }

    #[test]
    fn pwl_axis_coverage_and_breakpoint_limits_fail_closed() {
        assert_eq!(
            PiecewiseLinearVoltageV1::try_new(
                vec![seconds(0.0).unwrap()],
                vec![volts(0.0).unwrap()]
            ),
            Err(TranError::PwlKnotAxisTooShort)
        );
        assert_eq!(
            PiecewiseLinearVoltageV1::try_new(
                vec![seconds(0.1).unwrap(), seconds(1.0).unwrap()],
                vec![volts(0.0).unwrap(), volts(1.0).unwrap()],
            ),
            Err(TranError::InvalidPwlKnotAxisStart)
        );
        assert_eq!(
            PiecewiseLinearVoltageV1::try_new(
                vec![seconds(0.0).unwrap(), seconds(0.0).unwrap()],
                vec![volts(0.0).unwrap(), volts(1.0).unwrap()],
            ),
            Err(TranError::NonIncreasingPwlKnotAxis)
        );
        let source = pwl_source(&[(0.0, 0.0), (1.0, 1.0)]);
        assert_eq!(
            OneNodeRcPwlRequestV1::try_new(
                vec![seconds(0.0).unwrap(), seconds(2.0).unwrap()],
                Ohms::try_new(1.0).unwrap(),
                FiniteF64::try_new(1.0, "capacitance farads").unwrap(),
                volts(0.0).unwrap(),
                source,
            ),
            Err(TranError::PwlCoverageMismatch)
        );
        let request = pwl_request(
            &[0.0, 2.0],
            pwl_source(&[(0.0, 0.0), (1.0, 1.0), (2.0, 1.0)]),
        );
        assert_eq!(
            simulate_one_node_rc_pwl(&request, pwl_limits(2, 2)),
            Err(TranError::BreakpointLimitExceeded)
        );
    }

    #[test]
    fn invalid_parameters_axes_and_limits_fail_closed() {
        assert_eq!(
            OneNodeRcPulseRequestV1::try_new(
                vec![seconds(1.0).unwrap()],
                Ohms::try_new(1.0).unwrap(),
                FiniteF64::try_new(1.0, "capacitance farads").unwrap(),
                volts(0.0).unwrap(),
                pulse(0.0, 1.0, 0.0, 1.0, 1.0, 0.0, 3.0),
            ),
            Err(TranError::InvalidOutputAxisStart)
        );
        assert_eq!(
            OneNodeRcPulseRequestV1::try_new(
                vec![seconds(0.0).unwrap(), seconds(0.0).unwrap()],
                Ohms::try_new(1.0).unwrap(),
                FiniteF64::try_new(1.0, "capacitance farads").unwrap(),
                volts(0.0).unwrap(),
                pulse(0.0, 1.0, 0.0, 1.0, 1.0, 0.0, 3.0),
            ),
            Err(TranError::NonIncreasingOutputAxis)
        );
        assert!(matches!(
            IdealPulseV1::try_new(
                volts(0.0).unwrap(),
                volts(1.0).unwrap(),
                seconds(0.0).unwrap(),
                seconds(0.0).unwrap(),
                seconds(1.0).unwrap(),
                seconds(0.0).unwrap(),
                seconds(2.0).unwrap()
            ),
            Err(TranError::InvalidPulseDuration)
        ));
        assert!(matches!(
            IdealPulseV1::try_new(
                volts(0.0).unwrap(),
                volts(1.0).unwrap(),
                seconds(2.0).unwrap(),
                seconds(1.0).unwrap(),
                seconds(1.0).unwrap(),
                seconds(0.0).unwrap(),
                seconds(3.0).unwrap()
            ),
            Err(TranError::InvalidPulseCornerOrder)
        ));
        let request = request(&[0.0, 1.0e-6], 0.0, 1.0, 0.0);
        assert_eq!(
            simulate_one_node_rc_pulse(&request, limits(1, 8)),
            Err(TranError::OutputLimitExceeded)
        );
        assert_eq!(
            simulate_one_node_rc_pulse(&request, limits(2, 1)),
            Err(TranError::BreakpointLimitExceeded)
        );
        let no_corner_in_range = OneNodeRcPulseRequestV1::try_new(
            vec![seconds(0.0).unwrap(), seconds(1.0).unwrap()],
            Ohms::try_new(1.0).unwrap(),
            FiniteF64::try_new(1.0, "capacitance farads").unwrap(),
            volts(0.0).unwrap(),
            pulse(0.0, 1.0, 2.0, 1.0, 1.0, 0.0, 5.0),
        )
        .unwrap();
        assert_eq!(
            simulate_one_node_rc_pulse(&no_corner_in_range, limits(2, 1)),
            Err(TranError::BreakpointLimitExceeded)
        );
    }

    #[test]
    fn cooperative_context_cancels_before_any_success_result() {
        let (controller, context) = Runtime::start(
            RunId::try_new("cancelled-rc").unwrap(),
            RunPolicy::try_new(std::time::Duration::from_secs(1), 8, 1024).unwrap(),
        )
        .unwrap();
        controller.cancel(CancelReason::Requested);
        let request = request(&[0.0, 1.0e-6], 0.0, 1.0, 0.0);
        assert_eq!(
            simulate_one_node_rc_pulse_with_context(&request, limits(2, 8), &context),
            Err(TranError::Runtime(sipi_runtime::RuntimeFailure::Cancelled))
        );
    }
}
