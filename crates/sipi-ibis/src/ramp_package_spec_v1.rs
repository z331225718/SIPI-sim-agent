//! Typed Ramp and Package declaration cores with explicit product-owned
//! validation rules.
//!
//! P4A-04g: [Ramp] (dV/dt_r, dV/dt_f, R_load) and [Package] (R_pin, L_pin,
//! C_pin) sections are represented as finite, strictly positive typed
//! declarations. This slice performs declaration validation ONLY: it does
//! not construct waveforms, build initial-slope models, solve terminal
//! networks, decode IBIS text, or accept any profile.

use sipi_types::{Farads, Henries, Ohms, VoltsPerSecond};

/// Typed [Ramp] declaration: rising/falling slope magnitudes (V/s) and the
/// reference load (ohms). All three fields are finite and strictly positive.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct RampSpecV1 {
    d_v_dt_r: VoltsPerSecond,
    d_v_dt_f: VoltsPerSecond,
    r_load: Ohms,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum RampSpecErrorV1 {
    NonPositiveSlopeRise,
    NonPositiveSlopeFall,
    NonPositiveLoad,
}

impl RampSpecV1 {
    pub fn try_new(
        d_v_dt_r: VoltsPerSecond,
        d_v_dt_f: VoltsPerSecond,
        r_load: Ohms,
    ) -> Result<Self, RampSpecErrorV1> {
        if d_v_dt_r.get() <= 0.0 {
            return Err(RampSpecErrorV1::NonPositiveSlopeRise);
        }
        if d_v_dt_f.get() <= 0.0 {
            return Err(RampSpecErrorV1::NonPositiveSlopeFall);
        }
        if r_load.get() <= 0.0 {
            return Err(RampSpecErrorV1::NonPositiveLoad);
        }
        Ok(Self { d_v_dt_r, d_v_dt_f, r_load })
    }

    pub const fn d_v_dt_r(self) -> VoltsPerSecond {
        self.d_v_dt_r
    }

    pub const fn d_v_dt_f(self) -> VoltsPerSecond {
        self.d_v_dt_f
    }

    pub const fn r_load(self) -> Ohms {
        self.r_load
    }
}

/// Typed [Package] declaration: pin resistance (ohms), inductance (henries),
/// and capacitance (farads). All three fields are finite and strictly
/// positive.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct PackageSpecV1 {
    r_pin: Ohms,
    l_pin: Henries,
    c_pin: Farads,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum PackageSpecErrorV1 {
    NonPositiveResistance,
    NonPositiveInductance,
    NonPositiveCapacitance,
}

impl PackageSpecV1 {
    pub fn try_new(
        r_pin: Ohms,
        l_pin: Henries,
        c_pin: Farads,
    ) -> Result<Self, PackageSpecErrorV1> {
        if r_pin.get() <= 0.0 {
            return Err(PackageSpecErrorV1::NonPositiveResistance);
        }
        if l_pin.get() <= 0.0 {
            return Err(PackageSpecErrorV1::NonPositiveInductance);
        }
        if c_pin.get() <= 0.0 {
            return Err(PackageSpecErrorV1::NonPositiveCapacitance);
        }
        Ok(Self { r_pin, l_pin, c_pin })
    }

    pub const fn r_pin(self) -> Ohms {
        self.r_pin
    }

    pub const fn l_pin(self) -> Henries {
        self.l_pin
    }

    pub const fn c_pin(self) -> Farads {
        self.c_pin
    }
}

/// Explicit scope policy of this slice: declaration validation only. No
/// waveform construction, no initial-slope model, no network solve, no
/// decoder, no profile acceptance.
pub const RAMP_PACKAGE_SCOPE_POLICY_V1: &str =
    "sipi.p4a-04g.ramp-package-spec-v1.declaration-only";

#[cfg(test)]
mod tests {
    use super::*;

    fn vps(value: f64) -> VoltsPerSecond {
        VoltsPerSecond::try_new(value).expect("finite slope")
    }

    fn ohms(value: f64) -> Ohms {
        Ohms::try_new(value).expect("finite ohms")
    }

    fn henries(value: f64) -> Henries {
        Henries::try_new(value).expect("finite henries")
    }

    fn farads(value: f64) -> Farads {
        Farads::try_new(value).expect("finite farads")
    }

    #[test]
    fn ramp_accepts_positive_declaration() {
        let spec = RampSpecV1::try_new(vps(1.0e9), vps(2.0e9), ohms(50.0)).expect("valid ramp");
        assert_eq!(spec.d_v_dt_r().get(), 1.0e9);
        assert_eq!(spec.d_v_dt_f().get(), 2.0e9);
        assert_eq!(spec.r_load().get(), 50.0);
    }

    #[test]
    fn ramp_rejects_zero_or_negative_fields() {
        assert_eq!(
            RampSpecV1::try_new(vps(0.0), vps(1.0e9), ohms(50.0)),
            Err(RampSpecErrorV1::NonPositiveSlopeRise)
        );
        assert_eq!(
            RampSpecV1::try_new(vps(-1.0e9), vps(1.0e9), ohms(50.0)),
            Err(RampSpecErrorV1::NonPositiveSlopeRise)
        );
        assert_eq!(
            RampSpecV1::try_new(vps(1.0e9), vps(0.0), ohms(50.0)),
            Err(RampSpecErrorV1::NonPositiveSlopeFall)
        );
        assert_eq!(
            RampSpecV1::try_new(vps(1.0e9), vps(1.0e9), ohms(0.0)),
            Err(RampSpecErrorV1::NonPositiveLoad)
        );
    }

    #[test]
    fn package_accepts_positive_declaration() {
        let spec = PackageSpecV1::try_new(ohms(1.0), henries(1.0e-9), farads(1.0e-12)).expect("valid package");
        assert_eq!(spec.r_pin().get(), 1.0);
        assert_eq!(spec.l_pin().get(), 1.0e-9);
        assert_eq!(spec.c_pin().get(), 1.0e-12);
    }

    #[test]
    fn package_rejects_zero_or_negative_fields() {
        assert_eq!(
            PackageSpecV1::try_new(ohms(0.0), henries(1.0e-9), farads(1.0e-12)),
            Err(PackageSpecErrorV1::NonPositiveResistance)
        );
        assert_eq!(
            PackageSpecV1::try_new(ohms(1.0), henries(-1.0e-9), farads(1.0e-12)),
            Err(PackageSpecErrorV1::NonPositiveInductance)
        );
        assert_eq!(
            PackageSpecV1::try_new(ohms(1.0), henries(1.0e-9), farads(0.0)),
            Err(PackageSpecErrorV1::NonPositiveCapacitance)
        );
    }

    #[test]
    fn scope_policy_string_is_fixed() {
        assert_eq!(
            RAMP_PACKAGE_SCOPE_POLICY_V1,
            "sipi.p4a-04g.ramp-package-spec-v1.declaration-only"
        );
    }
}
