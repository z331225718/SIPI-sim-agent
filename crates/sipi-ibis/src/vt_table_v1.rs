//! Typed V-T (voltage-versus-time) table semantics with an explicit
//! interpolation/extrapolation policy.
//!
//! Product-owned core for the P4A-04 required I-V/V-T/ramp/package surface.
//! This slice covers ONLY the V-T table: strictly time-ascending finite
//! knots, linear interpolation within the table domain, and explicit
//! out-of-domain rejection (no extrapolation). It does not decode IBIS text,
//! does not evaluate electrical circuits, and does not accept or imply any
//! profile; ramp/package semantics stay out of this slice.

use sipi_types::{Seconds, Volts};

/// One finite (time, voltage) knot of a V-T table. Units: seconds and volts.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct VtKnotV1 {
    time_s: Seconds,
    voltage_v: Volts,
}

impl VtKnotV1 {
    pub const fn new(time_s: Seconds, voltage_v: Volts) -> Self {
        Self { time_s, voltage_v }
    }

    pub const fn time_s(self) -> Seconds {
        self.time_s
    }

    pub const fn voltage_v(self) -> Volts {
        self.voltage_v
    }
}

/// One bounded, strictly time-ordered piecewise-linear V-T table with at
/// least two knots. Interpolation requires an ordered pair, so single-knot
/// tables are rejected.
#[derive(Clone, Debug, PartialEq)]
pub struct VtTableV1 {
    knots: Vec<VtKnotV1>,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum VtTableErrorV1 {
    TooFewKnots,
    TimeNotStrictlyIncreasing,
}

impl VtTableV1 {
    pub fn try_new(knots: Vec<VtKnotV1>) -> Result<Self, VtTableErrorV1> {
        if knots.len() < 2 {
            return Err(VtTableErrorV1::TooFewKnots);
        }
        for pair in knots.windows(2) {
            if pair[0].time_s().get() >= pair[1].time_s().get() {
                return Err(VtTableErrorV1::TimeNotStrictlyIncreasing);
            }
        }
        Ok(Self { knots })
    }

    pub fn knots(&self) -> &[VtKnotV1] {
        &self.knots
    }

    /// Closed time domain [first, last] of the table, in seconds.
    pub fn time_domain(&self) -> (f64, f64) {
        (
            self.knots[0].time_s().get(),
            self.knots[self.knots.len() - 1].time_s().get(),
        )
    }
}

/// Explicit evaluation policy of this slice. Linear interpolation within the
/// table domain; any requested time outside the closed domain is rejected.
/// No extrapolation is ever performed.
pub const VT_EVALUATION_POLICY_V1: &str =
    "sipi.p4a-04f.vt-table-v1.linear-within-domain.reject-out-of-domain";

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum VtEvaluationErrorV1 {
    OutOfDomain,
    NonFiniteEvaluation,
}

/// Evaluate the piecewise-linear V-T table at one finite time (seconds),
/// returning the interpolated voltage in volts.
pub fn evaluate_vt_v1(table: &VtTableV1, time_s: Seconds) -> Result<Volts, VtEvaluationErrorV1> {
    let requested = time_s.get();
    let first = table.knots[0].time_s().get();
    let last = table.knots[table.knots.len() - 1].time_s().get();
    if requested < first || requested > last {
        return Err(VtEvaluationErrorV1::OutOfDomain);
    }
    for pair in table.knots.windows(2) {
        let lower = pair[0];
        let upper = pair[1];
        if requested == lower.time_s().get() {
            return Ok(lower.voltage_v());
        }
        if requested <= upper.time_s().get() {
            let distance = upper.time_s().get() - lower.time_s().get();
            let ratio = (requested - lower.time_s().get()) / distance;
            let value = lower.voltage_v().get()
                + ratio * (upper.voltage_v().get() - lower.voltage_v().get());
            return Volts::try_new(value).map_err(|_| VtEvaluationErrorV1::NonFiniteEvaluation);
        }
    }
    Ok(table.knots[table.knots.len() - 1].voltage_v())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn seconds(value: f64) -> Seconds {
        Seconds::try_new(value).expect("finite seconds")
    }

    fn volts(value: f64) -> Volts {
        Volts::try_new(value).expect("finite volts")
    }

    fn table() -> VtTableV1 {
        VtTableV1::try_new(vec![
            VtKnotV1::new(seconds(0.0), volts(0.0)),
            VtKnotV1::new(seconds(1.0), volts(1.0)),
            VtKnotV1::new(seconds(2.0), volts(0.0)),
        ])
        .expect("valid table")
    }

    #[test]
    fn interpolates_linear_midpoint() {
        let value = evaluate_vt_v1(&table(), seconds(0.5)).expect("in domain");
        assert_eq!(value.get(), 0.5);
    }

    #[test]
    fn interpolates_second_segment() {
        let value = evaluate_vt_v1(&table(), seconds(1.5)).expect("in domain");
        assert_eq!(value.get(), 0.5);
    }

    #[test]
    fn hits_endpoint_exactly() {
        let value = evaluate_vt_v1(&table(), seconds(1.0)).expect("in domain");
        assert_eq!(value.get(), 1.0);
        let first = evaluate_vt_v1(&table(), seconds(0.0)).expect("in domain");
        assert_eq!(first.get(), 0.0);
    }

    #[test]
    fn rejects_out_of_domain() {
        assert_eq!(
            evaluate_vt_v1(&table(), seconds(-0.001)),
            Err(VtEvaluationErrorV1::OutOfDomain)
        );
        assert_eq!(
            evaluate_vt_v1(&table(), seconds(2.001)),
            Err(VtEvaluationErrorV1::OutOfDomain)
        );
    }

    #[test]
    fn rejects_single_knot_table() {
        assert_eq!(
            VtTableV1::try_new(vec![VtKnotV1::new(seconds(0.0), volts(1.0))]),
            Err(VtTableErrorV1::TooFewKnots)
        );
    }

    #[test]
    fn rejects_duplicate_time() {
        assert_eq!(
            VtTableV1::try_new(vec![
                VtKnotV1::new(seconds(1.0), volts(0.0)),
                VtKnotV1::new(seconds(1.0), volts(1.0)),
            ]),
            Err(VtTableErrorV1::TimeNotStrictlyIncreasing)
        );
    }

    #[test]
    fn rejects_descending_time() {
        assert_eq!(
            VtTableV1::try_new(vec![
                VtKnotV1::new(seconds(2.0), volts(0.0)),
                VtKnotV1::new(seconds(1.0), volts(1.0)),
            ]),
            Err(VtTableErrorV1::TimeNotStrictlyIncreasing)
        );
    }

    #[test]
    fn domain_is_closed_first_last() {
        assert_eq!(table().time_domain(), (0.0, 2.0));
    }

    #[test]
    fn policy_string_is_fixed() {
        assert_eq!(
            VT_EVALUATION_POLICY_V1,
            "sipi.p4a-04f.vt-table-v1.linear-within-domain.reject-out-of-domain"
        );
    }
}
