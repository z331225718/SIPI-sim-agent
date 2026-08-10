#![forbid(unsafe_code)]

//! Product-owned continuous constitutive relation for one selected RX load.
//!
//! This crate has no sampled-time integrator, channel resolver, file I/O,
//! CLI, IBIS, AMI, or external-oracle dependency.

use std::{error::Error, fmt};

use sipi_types::{Amps, FiniteF64, TypeError, Volts};

/// The fixed selected differential resistor, connected from P to N.
pub const DIFFERENTIAL_RESISTANCE_OHMS: f64 = 100.0;

/// The fixed capacitor on each leg, connected from P/N to REF.
pub const LEG_CAPACITANCE_FARADS: f64 = 1.0e-12;

/// Continuous voltage and voltage-derivative observations relative to REF.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct DifferentialRcLoadProbeV1 {
    p_to_ref: Volts,
    n_to_ref: Volts,
    p_to_ref_slope_v_per_s: FiniteF64,
    n_to_ref_slope_v_per_s: FiniteF64,
}

impl DifferentialRcLoadProbeV1 {
    /// Constructs an explicit continuous-time probe; no derivative is inferred.
    pub fn try_new(
        p_to_ref_v: f64,
        n_to_ref_v: f64,
        p_to_ref_slope_v_per_s: f64,
        n_to_ref_slope_v_per_s: f64,
    ) -> Result<Self, DifferentialRcLoadError> {
        Ok(Self {
            p_to_ref: Volts::try_new(p_to_ref_v)?,
            n_to_ref: Volts::try_new(n_to_ref_v)?,
            p_to_ref_slope_v_per_s: FiniteF64::try_new(
                p_to_ref_slope_v_per_s,
                "P-to-REF voltage slope in volts per second",
            )?,
            n_to_ref_slope_v_per_s: FiniteF64::try_new(
                n_to_ref_slope_v_per_s,
                "N-to-REF voltage slope in volts per second",
            )?,
        })
    }

    pub fn p_to_ref(self) -> Volts {
        self.p_to_ref
    }

    pub fn n_to_ref(self) -> Volts {
        self.n_to_ref
    }

    pub fn p_to_ref_slope_v_per_s(self) -> f64 {
        self.p_to_ref_slope_v_per_s.get()
    }

    pub fn n_to_ref_slope_v_per_s(self) -> f64 {
        self.n_to_ref_slope_v_per_s.get()
    }
}

/// Branch and terminal currents for the selected P/N/REF electrical load.
///
/// Every terminal current is positive when flowing into that load terminal.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct DifferentialRcLoadCurrentsV1 {
    resistor_p_to_n: Amps,
    p_capacitor_to_ref: Amps,
    n_capacitor_to_ref: Amps,
    p_terminal: Amps,
    n_terminal: Amps,
    ref_terminal: Amps,
}

impl DifferentialRcLoadCurrentsV1 {
    pub fn resistor_p_to_n(self) -> Amps {
        self.resistor_p_to_n
    }

    pub fn p_capacitor_to_ref(self) -> Amps {
        self.p_capacitor_to_ref
    }

    pub fn n_capacitor_to_ref(self) -> Amps {
        self.n_capacitor_to_ref
    }

    pub fn p_terminal(self) -> Amps {
        self.p_terminal
    }

    pub fn n_terminal(self) -> Amps {
        self.n_terminal
    }

    pub fn ref_terminal(self) -> Amps {
        self.ref_terminal
    }
}

/// Errors from evaluating the selected continuous constitutive relation.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum DifferentialRcLoadError {
    Invariant(TypeError),
    NumericOverflow { quantity: &'static str },
}

impl fmt::Display for DifferentialRcLoadError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Invariant(error) => error.fmt(formatter),
            Self::NumericOverflow { quantity } => {
                write!(
                    formatter,
                    "selected differential R-C load overflowed at {quantity}"
                )
            }
        }
    }
}

impl Error for DifferentialRcLoadError {}

impl From<TypeError> for DifferentialRcLoadError {
    fn from(value: TypeError) -> Self {
        Self::Invariant(value)
    }
}

/// Evaluates the selected three-terminal R-C load at one continuous instant.
///
/// The relation is `i_r=(V(P)-V(N))/100`, `i_cp=1pF*dV(P)/dt`, and
/// `i_cn=1pF*dV(N)/dt`. It deliberately does not choose a time integration
/// scheme or derive a slope from samples.
pub fn evaluate_selected_differential_rc_load_v1(
    probe: DifferentialRcLoadProbeV1,
) -> Result<DifferentialRcLoadCurrentsV1, DifferentialRcLoadError> {
    let resistor = finite_current(
        (probe.p_to_ref().get() - probe.n_to_ref().get()) / DIFFERENTIAL_RESISTANCE_OHMS,
        "resistor branch",
    )?;
    let p_capacitor = finite_current(
        LEG_CAPACITANCE_FARADS * probe.p_to_ref_slope_v_per_s(),
        "P capacitor branch",
    )?;
    let n_capacitor = finite_current(
        LEG_CAPACITANCE_FARADS * probe.n_to_ref_slope_v_per_s(),
        "N capacitor branch",
    )?;
    let p_terminal = finite_current(resistor.get() + p_capacitor.get(), "P terminal")?;
    let n_terminal = finite_current(-resistor.get() + n_capacitor.get(), "N terminal")?;
    let ref_terminal = finite_current(-(p_capacitor.get() + n_capacitor.get()), "REF terminal")?;

    Ok(DifferentialRcLoadCurrentsV1 {
        resistor_p_to_n: resistor,
        p_capacitor_to_ref: p_capacitor,
        n_capacitor_to_ref: n_capacitor,
        p_terminal,
        n_terminal,
        ref_terminal,
    })
}

fn finite_current(value: f64, quantity: &'static str) -> Result<Amps, DifferentialRcLoadError> {
    if !value.is_finite() {
        return Err(DifferentialRcLoadError::NumericOverflow { quantity });
    }
    Ok(Amps::try_new(value)?)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn probe(p: f64, n: f64, dp: f64, dn: f64) -> DifferentialRcLoadProbeV1 {
        DifferentialRcLoadProbeV1::try_new(p, n, dp, dn).unwrap()
    }

    fn close(left: f64, right: f64) {
        assert!((left - right).abs() <= 1.0e-15, "{left} != {right}");
    }

    #[test]
    fn pure_differential_dc_is_resistive_and_kcl_balanced() {
        let result = evaluate_selected_differential_rc_load_v1(probe(0.5, -0.5, 0.0, 0.0)).unwrap();
        close(result.resistor_p_to_n().get(), 0.01);
        close(result.p_terminal().get(), 0.01);
        close(result.n_terminal().get(), -0.01);
        close(result.ref_terminal().get(), 0.0);
        assert!((1.0 * result.resistor_p_to_n().get()) >= 0.0);
        close(
            result.p_terminal().get() + result.n_terminal().get() + result.ref_terminal().get(),
            0.0,
        );
    }

    #[test]
    fn common_mode_ramp_preserves_each_leg_capacitor_and_ref_current() {
        let result =
            evaluate_selected_differential_rc_load_v1(probe(1.0, 1.0, 1.0e9, 1.0e9)).unwrap();
        close(result.resistor_p_to_n().get(), 0.0);
        close(result.p_capacitor_to_ref().get(), 0.001);
        close(result.n_capacitor_to_ref().get(), 0.001);
        close(result.p_terminal().get(), 0.001);
        close(result.n_terminal().get(), 0.001);
        close(result.ref_terminal().get(), -0.002);
    }

    #[test]
    fn differential_ramp_keeps_ref_branch_balanced() {
        let result =
            evaluate_selected_differential_rc_load_v1(probe(0.0, 0.0, 1.0e9, -1.0e9)).unwrap();
        close(result.p_terminal().get(), 0.001);
        close(result.n_terminal().get(), -0.001);
        close(result.ref_terminal().get(), 0.0);
    }

    #[test]
    fn relation_is_linear_and_deterministic() {
        let left =
            evaluate_selected_differential_rc_load_v1(probe(0.2, -0.1, 2.0e8, -3.0e8)).unwrap();
        let doubled =
            evaluate_selected_differential_rc_load_v1(probe(0.4, -0.2, 4.0e8, -6.0e8)).unwrap();
        close(doubled.p_terminal().get(), 2.0 * left.p_terminal().get());
        close(doubled.n_terminal().get(), 2.0 * left.n_terminal().get());
        close(
            doubled.ref_terminal().get(),
            2.0 * left.ref_terminal().get(),
        );
        assert_eq!(
            left,
            evaluate_selected_differential_rc_load_v1(probe(0.2, -0.1, 2.0e8, -3.0e8)).unwrap()
        );
    }

    #[test]
    fn non_finite_inputs_and_derived_overflow_fail_closed() {
        assert_eq!(
            DifferentialRcLoadProbeV1::try_new(f64::NAN, 0.0, 0.0, 0.0),
            Err(DifferentialRcLoadError::Invariant(TypeError::NonFinite {
                kind: "volts"
            }))
        );
        assert_eq!(
            evaluate_selected_differential_rc_load_v1(probe(f64::MAX, -f64::MAX, 0.0, 0.0)),
            Err(DifferentialRcLoadError::NumericOverflow {
                quantity: "resistor branch"
            })
        );
    }
}
