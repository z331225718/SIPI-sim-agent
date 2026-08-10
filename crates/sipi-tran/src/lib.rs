#![forbid(unsafe_code)]

//! A narrowly scoped RC/PULSE transient implementation.
//!
//! This crate accepts no netlist text and implements no generic circuit model.
//! It only evaluates the independently specified first RC/PULSE profile.

use std::{error::Error, fmt};

use sipi_runtime::RunContext;
use sipi_types::{Axis, Seconds, TypeError, Volts, Waveform};

/// Identity of the only implemented TRAN profile.
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

/// A typed request for the sole v1 RC/PULSE transient profile.
///
/// Its fields are private so callers cannot silently expand the first profile's
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

/// Product-owned result for the fixed RC/PULSE transient request.
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

/// Fail-closed errors for the fixed-profile solver.
#[derive(Debug)]
pub enum TranError {
    Invariant(TypeError),
    Runtime(sipi_runtime::RuntimeFailure),
    NonFiniteComputation,
}

impl fmt::Display for TranError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Invariant(error) => error.fmt(formatter),
            Self::Runtime(error) => write!(formatter, "runtime failure: {}", error.code()),
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

/// Simulates the exact v1 RC/PULSE profile with f64 backward Euler.
///
/// Requested output times and pulse corners partition the integration path;
/// no interpolation or resampling is applied to the returned waveforms.
pub fn simulate_rc_pulse(
    request: RcPulseTransientV1,
) -> Result<RcPulseTransientResultV1, TranError> {
    simulate_rc_pulse_checked(request, || Ok(()))
}

/// Runs the fixed profile with cooperative checkpoints supplied by its caller.
pub fn simulate_rc_pulse_with_context(
    request: RcPulseTransientV1,
    context: &RunContext,
) -> Result<RcPulseTransientResultV1, TranError> {
    simulate_rc_pulse_checked(request, || context.checkpoint().map_err(Into::into))
}

fn simulate_rc_pulse_checked(
    request: RcPulseTransientV1,
    mut checkpoint: impl FnMut() -> Result<(), TranError>,
) -> Result<RcPulseTransientResultV1, TranError> {
    let _ = request;
    checkpoint()?;
    let axis = explicit_time_axis()?;
    let mut voltage_out = 0.0;
    let mut voltage_in_samples = Vec::with_capacity(OUTPUT_TIMES_S.len());
    let mut voltage_out_samples = Vec::with_capacity(OUTPUT_TIMES_S.len());
    let mut current_time = OUTPUT_TIMES_S[0];

    voltage_in_samples.push(volts(pulse_voltage(current_time))?);
    voltage_out_samples.push(volts(voltage_out)?);
    for next_time in integration_breakpoints().into_iter().skip(1) {
        checkpoint()?;
        voltage_out = backward_euler_step(
            voltage_out,
            pulse_voltage(next_time),
            next_time - current_time,
            RESISTANCE_OHM,
            CAPACITANCE_F,
        )?;
        current_time = next_time;
        if OUTPUT_TIMES_S.contains(&current_time) {
            voltage_in_samples.push(volts(pulse_voltage(current_time))?);
            voltage_out_samples.push(volts(voltage_out)?);
        }
    }

    let voltage_in = Waveform::try_new(axis.clone(), voltage_in_samples)?;
    checkpoint()?;
    let voltage_out = Waveform::try_new(axis.clone(), voltage_out_samples)?;
    Ok(RcPulseTransientResultV1 {
        time_axis: axis,
        voltage_in,
        voltage_out,
    })
}

fn explicit_time_axis() -> Result<Axis<Seconds>, TranError> {
    OUTPUT_TIMES_S
        .into_iter()
        .map(Seconds::try_new)
        .collect::<Result<Vec<_>, _>>()
        .and_then(Axis::explicit)
        .map_err(Into::into)
}

fn integration_breakpoints() -> [f64; 5] {
    [
        0.0,
        PULSE_DELAY_S,
        PULSE_DELAY_S + PULSE_RISE_S,
        2.0e-6,
        3.0e-6,
    ]
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

fn pulse_voltage(time_s: f64) -> f64 {
    let phase = time_s.rem_euclid(PULSE_PERIOD_S);
    if phase < PULSE_DELAY_S {
        PULSE_LOW_V
    } else if phase < PULSE_DELAY_S + PULSE_RISE_S {
        PULSE_LOW_V + (PULSE_HIGH_V - PULSE_LOW_V) * (phase - PULSE_DELAY_S) / PULSE_RISE_S
    } else if phase < PULSE_DELAY_S + PULSE_RISE_S + PULSE_WIDTH_S {
        PULSE_HIGH_V
    } else if phase < PULSE_DELAY_S + PULSE_RISE_S + PULSE_WIDTH_S + PULSE_FALL_S {
        PULSE_HIGH_V
            - (PULSE_HIGH_V - PULSE_LOW_V) * (phase - PULSE_DELAY_S - PULSE_RISE_S - PULSE_WIDTH_S)
                / PULSE_FALL_S
    } else {
        PULSE_LOW_V
    }
}

fn volts(value: f64) -> Result<Volts, TranError> {
    Volts::try_new(value).map_err(Into::into)
}

#[cfg(test)]
mod tests {
    use super::*;
    use sipi_types::AxisView;

    fn test_only_pwl_rc(
        initial: f64,
        source: &[f64],
        step: f64,
        resistance: f64,
        capacitance: f64,
    ) -> Vec<f64> {
        let mut output = vec![initial];
        for value in source.iter().copied().skip(1) {
            let next = backward_euler_step(
                *output.last().expect("initial"),
                value,
                step,
                resistance,
                capacitance,
            )
            .expect("finite owned RC test");
            output.push(next);
        }
        output
    }

    fn exact_linear_segment(previous: f64, left: f64, right: f64, duration: f64, tau: f64) -> f64 {
        let slope = (right - left) / duration;
        right - slope * tau + (previous - left + slope * tau) * (-duration / tau).exp()
    }

    #[test]
    fn fixed_profile_has_the_specified_index_aligned_waveforms() {
        let result = simulate_rc_pulse(RcPulseTransientV1::fixed_profile()).expect("fixed profile");
        assert_eq!(
            RcPulseTransientV1::fixed_profile().profile_id(),
            RC_PULSE_PROFILE_ID
        );
        assert_eq!(
            result.time_axis().view(),
            AxisView::Explicit(&[
                Seconds::try_new(0.0).expect("finite"),
                Seconds::try_new(1.0e-6).expect("finite"),
                Seconds::try_new(2.0e-6).expect("finite"),
                Seconds::try_new(3.0e-6).expect("finite"),
            ])
        );
        assert_eq!(
            result
                .voltage_in()
                .samples()
                .iter()
                .map(|value| value.get())
                .collect::<Vec<_>>(),
            vec![0.0, 0.0, 1.0, 1.0]
        );
        assert_eq!(result.voltage_out().samples().len(), OUTPUT_TIMES_S.len());
        assert!(
            result
                .voltage_out()
                .samples()
                .iter()
                .all(|value| value.get().is_finite())
        );
        let first = 1.0e-9 / (RESISTANCE_OHM * CAPACITANCE_F + 1.0e-9);
        let second_step = 0.999e-6;
        let second = (first + second_step / (RESISTANCE_OHM * CAPACITANCE_F))
            / (1.0 + second_step / (RESISTANCE_OHM * CAPACITANCE_F));
        let third = (second + 1.0e-6 / (RESISTANCE_OHM * CAPACITANCE_F))
            / (1.0 + 1.0e-6 / (RESISTANCE_OHM * CAPACITANCE_F));
        let actual = result
            .voltage_out()
            .samples()
            .iter()
            .map(|value| value.get())
            .collect::<Vec<_>>();
        assert_eq!(&actual[..2], &[0.0, 0.0]);
        assert!((actual[2] - second).abs() <= 1.0e-18);
        assert!((actual[3] - third).abs() <= 1.0e-18);
    }

    #[test]
    fn backward_euler_tracks_the_independent_constant_rc_closed_form() {
        let step_s = 1.0e-6;
        let time_constant = RESISTANCE_OHM * CAPACITANCE_F;
        let backward_euler = backward_euler_step(0.0, 1.0, step_s, RESISTANCE_OHM, CAPACITANCE_F)
            .expect("finite step");
        let closed_form = 1.0 - (-step_s / time_constant).exp();
        assert!(backward_euler <= closed_form);
        assert!(closed_form - backward_euler <= 1.0e-6 / time_constant);
    }

    #[test]
    fn pulse_corners_are_explicit_breakpoints() {
        assert_eq!(
            integration_breakpoints(),
            [0.0, 1.0e-6, 1.001e-6, 2.0e-6, 3.0e-6]
        );
        assert_eq!(pulse_voltage(1.0e-6), 0.0);
        assert_eq!(pulse_voltage(1.001e-6), 1.0);
    }

    #[test]
    fn product_owned_pwl_rc_case_tracks_closed_form_without_external_fixture() {
        // This test-only PWL case is intentionally unrelated to rc.cir. The
        // closed form is an analytical oracle, not another circuit resolver.
        let source = [0.2, 0.8, 1.4, 0.6, 0.2];
        let step = 0.01;
        let resistance = 20.0;
        let capacitance = 0.01;
        let tau = resistance * capacitance;
        let numerical = test_only_pwl_rc(0.2, &source, step, resistance, capacitance);
        let mut analytical = vec![0.2];
        for pair in source.windows(2) {
            analytical.push(exact_linear_segment(
                *analytical.last().expect("initial"),
                pair[0],
                pair[1],
                step,
                tau,
            ));
        }
        assert_eq!(numerical.len(), analytical.len());
        for (actual, expected) in numerical.iter().zip(analytical) {
            // The fixed 10 ms backward-Euler step is at most 0.05 tau;
            // this 40 mV bound is a stated discretization budget, not a
            // copied waveform tolerance.
            assert!((actual - expected).abs() <= 0.04, "{actual} vs {expected}");
            assert!(actual.is_finite() && (0.2..=1.4).contains(actual));
        }
    }

    #[test]
    fn owned_rc_response_is_linear_under_offset_and_scale() {
        let source = [0.1, 0.9, 0.4, 0.1];
        let baseline = test_only_pwl_rc(0.1, &source, 0.02, 50.0, 0.01);
        let offset_source = source.map(|value| value + 3.0);
        let offset = test_only_pwl_rc(3.1, &offset_source, 0.02, 50.0, 0.01);
        let scale_source = source.map(|value| value * 2.5);
        let scaled = test_only_pwl_rc(0.25, &scale_source, 0.02, 50.0, 0.01);
        for ((base, shifted), multiplied) in baseline.iter().zip(offset).zip(scaled) {
            assert!((shifted - (base + 3.0)).abs() <= 1.0e-14);
            assert!((multiplied - base * 2.5).abs() <= 1.0e-14);
        }
    }
}
