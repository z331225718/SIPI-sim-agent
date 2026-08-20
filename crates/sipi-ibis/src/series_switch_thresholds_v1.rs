//! Typed IBIS [Series Switch Groups] threshold parameters core (P4A-03aa).
//!
//! Lifts and validates IBIS [Series Switch Groups] threshold parameter declarations
//! (Vthreshold, Rseries, Cseries, Lseries) associated with standalone series switch groups into typed clean-room structures.
//! Fail-closed: non-finite values or negative R/C/L threshold parameters are strictly rejected.

use sipi_types::FiniteF64;

/// Scope policy for the typed series switch thresholds core.
pub const SERIES_SWITCH_THRESHOLDS_POLICY_V1: &str =
    "sipi.p4a-03aa.series-switch-thresholds-v1.typed-switch-thresholds";

/// Fail-closed errors during series switch thresholds declaration lifting.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum SeriesSwitchThresholdsErrorV1 {
    NonFiniteValue,
    NegativeThresholdParameter,
}

/// A typed IBIS [Series Switch Groups] threshold parameter declaration.
#[derive(Clone, Debug, PartialEq)]
pub struct TypedSeriesSwitchThresholdsV1 {
    vthreshold_v: Option<FiniteF64>,
    rseries_ohm: Option<FiniteF64>,
    cseries_farad: Option<FiniteF64>,
    lseries_henry: Option<FiniteF64>,
}

impl TypedSeriesSwitchThresholdsV1 {
    pub fn try_new(
        vthreshold_v: Option<f64>,
        rseries_ohm: Option<f64>,
        cseries_farad: Option<f64>,
        lseries_henry: Option<f64>,
    ) -> Result<Self, SeriesSwitchThresholdsErrorV1> {
        let validate_non_negative =
            |val: Option<f64>,
             kind: &'static str|
             -> Result<Option<FiniteF64>, SeriesSwitchThresholdsErrorV1> {
                match val {
                    None => Ok(None),
                    Some(v) => {
                        if !v.is_finite() {
                            return Err(SeriesSwitchThresholdsErrorV1::NonFiniteValue);
                        }
                        if v < 0.0 {
                            return Err(SeriesSwitchThresholdsErrorV1::NegativeThresholdParameter);
                        }
                        let finite = FiniteF64::try_new(v, kind)
                            .map_err(|_| SeriesSwitchThresholdsErrorV1::NonFiniteValue)?;
                        Ok(Some(finite))
                    }
                }
            };

        let validate_finite = |val: Option<f64>,
                               kind: &'static str|
         -> Result<Option<FiniteF64>, SeriesSwitchThresholdsErrorV1> {
            match val {
                None => Ok(None),
                Some(v) => {
                    if !v.is_finite() {
                        return Err(SeriesSwitchThresholdsErrorV1::NonFiniteValue);
                    }
                    let finite = FiniteF64::try_new(v, kind)
                        .map_err(|_| SeriesSwitchThresholdsErrorV1::NonFiniteValue)?;
                    Ok(Some(finite))
                }
            }
        };

        let vthreshold_v = validate_finite(vthreshold_v, "vthreshold_v")?;
        let rseries_ohm = validate_non_negative(rseries_ohm, "rseries_ohm")?;
        let cseries_farad = validate_non_negative(cseries_farad, "cseries_farad")?;
        let lseries_henry = validate_non_negative(lseries_henry, "lseries_henry")?;

        Ok(Self {
            vthreshold_v,
            rseries_ohm,
            cseries_farad,
            lseries_henry,
        })
    }

    pub fn vthreshold_v(&self) -> Option<FiniteF64> {
        self.vthreshold_v
    }

    pub fn rseries_ohm(&self) -> Option<FiniteF64> {
        self.rseries_ohm
    }

    pub fn cseries_farad(&self) -> Option<FiniteF64> {
        self.cseries_farad
    }

    pub fn lseries_henry(&self) -> Option<FiniteF64> {
        self.lseries_henry
    }
}

/// Lift one series switch threshold parameters declaration.
pub fn lift_series_switch_thresholds_v1(
    vthreshold_v: Option<f64>,
    rseries_ohm: Option<f64>,
    cseries_farad: Option<f64>,
    lseries_henry: Option<f64>,
) -> Result<TypedSeriesSwitchThresholdsV1, SeriesSwitchThresholdsErrorV1> {
    TypedSeriesSwitchThresholdsV1::try_new(vthreshold_v, rseries_ohm, cseries_farad, lseries_henry)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn policy_fixed() {
        assert_eq!(
            SERIES_SWITCH_THRESHOLDS_POLICY_V1,
            "sipi.p4a-03aa.series-switch-thresholds-v1.typed-switch-thresholds"
        );
    }

    #[test]
    fn valid_full_switch_thresholds() {
        let thresh =
            lift_series_switch_thresholds_v1(Some(1.8), Some(10.0), Some(0.5e-12), Some(2e-9))
                .expect("lift");
        assert_eq!(thresh.vthreshold_v().unwrap().get(), 1.8);
        assert_eq!(thresh.rseries_ohm().unwrap().get(), 10.0);
        assert_eq!(thresh.cseries_farad().unwrap().get(), 0.5e-12);
        assert_eq!(thresh.lseries_henry().unwrap().get(), 2e-9);
    }

    #[test]
    fn valid_minimal_switch_thresholds() {
        let thresh = lift_series_switch_thresholds_v1(None, None, None, None).expect("lift");
        assert_eq!(thresh.vthreshold_v(), None);
        assert_eq!(thresh.rseries_ohm(), None);
        assert_eq!(thresh.cseries_farad(), None);
        assert_eq!(thresh.lseries_henry(), None);
    }

    #[test]
    fn rejects_negative_rseries() {
        assert_eq!(
            lift_series_switch_thresholds_v1(None, Some(-10.0), None, None),
            Err(SeriesSwitchThresholdsErrorV1::NegativeThresholdParameter)
        );
    }

    #[test]
    fn rejects_non_finite_values() {
        assert_eq!(
            lift_series_switch_thresholds_v1(Some(f64::NAN), None, None, None),
            Err(SeriesSwitchThresholdsErrorV1::NonFiniteValue)
        );
    }
}
