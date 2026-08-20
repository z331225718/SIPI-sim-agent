//! Typed IBIS [Diff Pin] declaration core (P4A-03j).
//!
//! Lifts and validates IBIS [Diff Pin] declarations (non-inverting pin,
//! inverting pin, vdiff, tdelay) into typed, clean-room structures.
//! Fail-closed: empty pin names, non-ASCII characters, identical pin pairs,
//! or negative/non-finite threshold/delay values are strictly rejected.

use sipi_types::FiniteF64;

/// Scope policy for the typed differential pin declaration core.
pub const DIFF_PIN_DECLARATION_POLICY_V1: &str =
    "sipi.p4a-03j.diff-pin-declaration-v1.typed-diff-pin";

/// Fail-closed errors during differential pin declaration lifting.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum DiffPinDeclarationErrorV1 {
    EmptyPinName,
    NonAsciiPinName,
    IdenticalPins,
    NonFiniteValue,
    NegativeThreshold,
}

/// A typed IBIS [Diff Pin] declaration.
#[derive(Clone, Debug, PartialEq)]
pub struct TypedDiffPinDeclarationV1 {
    pin_non_inv: String,
    pin_inv: String,
    vdiff_v: Option<FiniteF64>,
    tdelay_s: Option<FiniteF64>,
}

impl TypedDiffPinDeclarationV1 {
    pub fn try_new(
        pin_non_inv: impl Into<String>,
        pin_inv: impl Into<String>,
        vdiff_v: Option<f64>,
        tdelay_s: Option<f64>,
    ) -> Result<Self, DiffPinDeclarationErrorV1> {
        let p1 = pin_non_inv.into().trim().to_string();
        let p2 = pin_inv.into().trim().to_string();

        if p1.is_empty() || p2.is_empty() {
            return Err(DiffPinDeclarationErrorV1::EmptyPinName);
        }
        if !p1.is_ascii() || !p2.is_ascii() {
            return Err(DiffPinDeclarationErrorV1::NonAsciiPinName);
        }
        if p1 == p2 {
            return Err(DiffPinDeclarationErrorV1::IdenticalPins);
        }

        let validate_val = |val: Option<f64>,
                            kind: &'static str|
         -> Result<Option<FiniteF64>, DiffPinDeclarationErrorV1> {
            match val {
                None => Ok(None),
                Some(v) => {
                    if !v.is_finite() {
                        return Err(DiffPinDeclarationErrorV1::NonFiniteValue);
                    }
                    if v < 0.0 {
                        return Err(DiffPinDeclarationErrorV1::NegativeThreshold);
                    }
                    let finite = FiniteF64::try_new(v, kind)
                        .map_err(|_| DiffPinDeclarationErrorV1::NonFiniteValue)?;
                    Ok(Some(finite))
                }
            }
        };

        let vdiff_v = validate_val(vdiff_v, "vdiff_v")?;
        let tdelay_s = validate_val(tdelay_s, "tdelay_s")?;

        Ok(Self {
            pin_non_inv: p1,
            pin_inv: p2,
            vdiff_v,
            tdelay_s,
        })
    }

    pub fn pin_non_inv(&self) -> &str {
        &self.pin_non_inv
    }

    pub fn pin_inv(&self) -> &str {
        &self.pin_inv
    }

    pub fn vdiff_v(&self) -> Option<FiniteF64> {
        self.vdiff_v
    }

    pub fn tdelay_s(&self) -> Option<FiniteF64> {
        self.tdelay_s
    }
}

/// Lift one differential pin declaration from raw parameters.
pub fn lift_diff_pin_declaration_v1(
    pin_non_inv: &str,
    pin_inv: &str,
    vdiff_v: Option<f64>,
    tdelay_s: Option<f64>,
) -> Result<TypedDiffPinDeclarationV1, DiffPinDeclarationErrorV1> {
    TypedDiffPinDeclarationV1::try_new(pin_non_inv, pin_inv, vdiff_v, tdelay_s)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn policy_fixed() {
        assert_eq!(
            DIFF_PIN_DECLARATION_POLICY_V1,
            "sipi.p4a-03j.diff-pin-declaration-v1.typed-diff-pin"
        );
    }

    #[test]
    fn valid_full_diff_pin() {
        let diff =
            lift_diff_pin_declaration_v1("DP1", "DN1", Some(0.1), Some(1e-10)).expect("lift");
        assert_eq!(diff.pin_non_inv(), "DP1");
        assert_eq!(diff.pin_inv(), "DN1");
        assert_eq!(diff.vdiff_v().unwrap().get(), 0.1);
        assert_eq!(diff.tdelay_s().unwrap().get(), 1e-10);
    }

    #[test]
    fn valid_minimal_diff_pin() {
        let diff = lift_diff_pin_declaration_v1("P1", "P2", None, None).expect("lift");
        assert_eq!(diff.pin_non_inv(), "P1");
        assert_eq!(diff.pin_inv(), "P2");
        assert_eq!(diff.vdiff_v(), None);
        assert_eq!(diff.tdelay_s(), None);
    }

    #[test]
    fn rejects_empty_pin_name() {
        assert_eq!(
            lift_diff_pin_declaration_v1("", "DN1", Some(0.1), None),
            Err(DiffPinDeclarationErrorV1::EmptyPinName)
        );
    }

    #[test]
    fn rejects_identical_pins() {
        assert_eq!(
            lift_diff_pin_declaration_v1("DP1", "DP1", Some(0.1), None),
            Err(DiffPinDeclarationErrorV1::IdenticalPins)
        );
    }

    #[test]
    fn rejects_negative_or_non_finite_values() {
        assert_eq!(
            lift_diff_pin_declaration_v1("DP1", "DN1", Some(-0.1), None),
            Err(DiffPinDeclarationErrorV1::NegativeThreshold)
        );
        assert_eq!(
            lift_diff_pin_declaration_v1("DP1", "DN1", Some(f64::NAN), None),
            Err(DiffPinDeclarationErrorV1::NonFiniteValue)
        );
    }
}
