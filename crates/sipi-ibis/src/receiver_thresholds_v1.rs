//! Typed IBIS [Receiver Thresholds] declaration core (P4A-03q).
//!
//! Lifts and validates IBIS [Receiver Thresholds] declarations
//! (Vcross_low, Vcross_high, Vdiff_ac, Vdiff_dc, Tskew) into typed clean-room structures.
//! Fail-closed: non-finite voltage or time values, or negative AC/DC differential thresholds
//! are strictly rejected.

use sipi_types::FiniteF64;

/// Scope policy for the typed receiver thresholds declaration core.
pub const RECEIVER_THRESHOLDS_POLICY_V1: &str =
    "sipi.p4a-03q.receiver-thresholds-v1.typed-thresholds";

/// Fail-closed errors during receiver thresholds declaration lifting.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ReceiverThresholdsErrorV1 {
    NonFiniteValue,
    NegativeThreshold,
}

/// A typed IBIS [Receiver Thresholds] declaration.
#[derive(Clone, Debug, PartialEq)]
pub struct TypedReceiverThresholdsV1 {
    vcross_low_v: Option<FiniteF64>,
    vcross_high_v: Option<FiniteF64>,
    vdiff_ac_v: Option<FiniteF64>,
    vdiff_dc_v: Option<FiniteF64>,
    tskew_s: Option<FiniteF64>,
}

impl TypedReceiverThresholdsV1 {
    pub fn try_new(
        vcross_low_v: Option<f64>,
        vcross_high_v: Option<f64>,
        vdiff_ac_v: Option<f64>,
        vdiff_dc_v: Option<f64>,
        tskew_s: Option<f64>,
    ) -> Result<Self, ReceiverThresholdsErrorV1> {
        let validate_finite = |val: Option<f64>, kind: &'static str| -> Result<Option<FiniteF64>, ReceiverThresholdsErrorV1> {
            match val {
                None => Ok(None),
                Some(v) => {
                    if !v.is_finite() {
                        return Err(ReceiverThresholdsErrorV1::NonFiniteValue);
                    }
                    let finite = FiniteF64::try_new(v, kind)
                        .map_err(|_| ReceiverThresholdsErrorV1::NonFiniteValue)?;
                    Ok(Some(finite))
                }
            }
        };

        let validate_non_negative = |val: Option<f64>, kind: &'static str| -> Result<Option<FiniteF64>, ReceiverThresholdsErrorV1> {
            match val {
                None => Ok(None),
                Some(v) => {
                    if !v.is_finite() {
                        return Err(ReceiverThresholdsErrorV1::NonFiniteValue);
                    }
                    if v < 0.0 {
                        return Err(ReceiverThresholdsErrorV1::NegativeThreshold);
                    }
                    let finite = FiniteF64::try_new(v, kind)
                        .map_err(|_| ReceiverThresholdsErrorV1::NonFiniteValue)?;
                    Ok(Some(finite))
                }
            }
        };

        let vcross_low_v = validate_finite(vcross_low_v, "vcross_low_v")?;
        let vcross_high_v = validate_finite(vcross_high_v, "vcross_high_v")?;
        let vdiff_ac_v = validate_non_negative(vdiff_ac_v, "vdiff_ac_v")?;
        let vdiff_dc_v = validate_non_negative(vdiff_dc_v, "vdiff_dc_v")?;
        let tskew_s = validate_non_negative(tskew_s, "tskew_s")?;

        Ok(Self {
            vcross_low_v,
            vcross_high_v,
            vdiff_ac_v,
            vdiff_dc_v,
            tskew_s,
        })
    }

    pub fn vcross_low_v(&self) -> Option<FiniteF64> {
        self.vcross_low_v
    }

    pub fn vcross_high_v(&self) -> Option<FiniteF64> {
        self.vcross_high_v
    }

    pub fn vdiff_ac_v(&self) -> Option<FiniteF64> {
        self.vdiff_ac_v
    }

    pub fn vdiff_dc_v(&self) -> Option<FiniteF64> {
        self.vdiff_dc_v
    }

    pub fn tskew_s(&self) -> Option<FiniteF64> {
        self.tskew_s
    }
}

/// Lift one receiver thresholds declaration.
pub fn lift_receiver_thresholds_v1(
    vcross_low_v: Option<f64>,
    vcross_high_v: Option<f64>,
    vdiff_ac_v: Option<f64>,
    vdiff_dc_v: Option<f64>,
    tskew_s: Option<f64>,
) -> Result<TypedReceiverThresholdsV1, ReceiverThresholdsErrorV1> {
    TypedReceiverThresholdsV1::try_new(vcross_low_v, vcross_high_v, vdiff_ac_v, vdiff_dc_v, tskew_s)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn policy_fixed() {
        assert_eq!(
            RECEIVER_THRESHOLDS_POLICY_V1,
            "sipi.p4a-03q.receiver-thresholds-v1.typed-thresholds"
        );
    }

    #[test]
    fn valid_full_thresholds() {
        let rx = lift_receiver_thresholds_v1(
            Some(0.8),
            Some(1.2),
            Some(0.15),
            Some(0.10),
            Some(20e-12),
        )
        .expect("lift");
        assert_eq!(rx.vcross_low_v().unwrap().get(), 0.8);
        assert_eq!(rx.vcross_high_v().unwrap().get(), 1.2);
        assert_eq!(rx.vdiff_ac_v().unwrap().get(), 0.15);
        assert_eq!(rx.vdiff_dc_v().unwrap().get(), 0.10);
        assert_eq!(rx.tskew_s().unwrap().get(), 20e-12);
    }

    #[test]
    fn valid_minimal_thresholds() {
        let rx = lift_receiver_thresholds_v1(None, None, None, None, None).expect("lift");
        assert_eq!(rx.vcross_low_v(), None);
        assert_eq!(rx.vcross_high_v(), None);
        assert_eq!(rx.vdiff_ac_v(), None);
        assert_eq!(rx.vdiff_dc_v(), None);
        assert_eq!(rx.tskew_s(), None);
    }

    #[test]
    fn rejects_negative_vdiff_ac() {
        assert_eq!(
            lift_receiver_thresholds_v1(None, None, Some(-0.05), None, None),
            Err(ReceiverThresholdsErrorV1::NegativeThreshold)
        );
    }

    #[test]
    fn rejects_non_finite_values() {
        assert_eq!(
            lift_receiver_thresholds_v1(Some(f64::NAN), None, None, None, None),
            Err(ReceiverThresholdsErrorV1::NonFiniteValue)
        );
    }
}
