//! Typed IBIS [Series Pin Mapping] Model Selector threshold table binding core (P4A-03ba).
//!
//! Lifts and validates IBIS [Series Pin Mapping] Model Selector threshold table binding records
//! (pin_first, pin_second, model_selector_name, threshold parameters) into typed clean-room structures.
//! Fail-closed: empty pin or selector names, non-ASCII characters, identical pin pairs,
//! non-finite values, or negative R/C/L threshold parameters are strictly rejected.

use sipi_types::FiniteF64;

/// Scope policy for the typed series pin table selector thresholds core.
pub const SERIES_PIN_TABLE_SELECTOR_THRESHOLDS_POLICY_V1: &str =
    "sipi.p4a-03ba.series-pin-table-selector-thresholds-v1.typed-selector-thresholds";

/// Fail-closed errors during series pin table selector thresholds lifting.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum SeriesPinTableSelectorThresholdsErrorV1 {
    EmptyPinName,
    EmptySelectorName,
    NonAsciiName,
    InvalidName,
    IdenticalPins,
    NonFiniteValue,
    NegativeThresholdParameter,
}

/// A typed IBIS [Series Pin Mapping] Model Selector threshold table record.
#[derive(Clone, Debug, PartialEq)]
pub struct TypedSeriesPinSelectorThresholdRecordV1 {
    pin_first: String,
    pin_second: String,
    model_selector_name: String,
    vthreshold_v: Option<FiniteF64>,
    rseries_ohm: Option<FiniteF64>,
    cseries_farad: Option<FiniteF64>,
    lseries_henry: Option<FiniteF64>,
}

impl TypedSeriesPinSelectorThresholdRecordV1 {
    pub fn try_new(
        pin_first: impl Into<String>,
        pin_second: impl Into<String>,
        model_selector_name: impl Into<String>,
        vthreshold_v: Option<f64>,
        rseries_ohm: Option<f64>,
        cseries_farad: Option<f64>,
        lseries_henry: Option<f64>,
    ) -> Result<Self, SeriesPinTableSelectorThresholdsErrorV1> {
        let pf = pin_first.into().trim().to_string();
        let ps = pin_second.into().trim().to_string();
        let ms = model_selector_name.into().trim().to_string();

        if pf.is_empty() || ps.is_empty() {
            return Err(SeriesPinTableSelectorThresholdsErrorV1::EmptyPinName);
        }
        if ms.is_empty() {
            return Err(SeriesPinTableSelectorThresholdsErrorV1::EmptySelectorName);
        }
        if !pf.is_ascii() || !ps.is_ascii() || !ms.is_ascii() {
            return Err(SeriesPinTableSelectorThresholdsErrorV1::NonAsciiName);
        }
        if !pf.chars().all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-' || c == '.')
            || !ps.chars().all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-' || c == '.')
            || !ms.chars().all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-' || c == '.')
        {
            return Err(SeriesPinTableSelectorThresholdsErrorV1::InvalidName);
        }
        if pf == ps {
            return Err(SeriesPinTableSelectorThresholdsErrorV1::IdenticalPins);
        }

        let validate_non_negative = |val: Option<f64>, kind: &'static str| -> Result<Option<FiniteF64>, SeriesPinTableSelectorThresholdsErrorV1> {
            match val {
                None => Ok(None),
                Some(v) => {
                    if !v.is_finite() {
                        return Err(SeriesPinTableSelectorThresholdsErrorV1::NonFiniteValue);
                    }
                    if v < 0.0 {
                        return Err(SeriesPinTableSelectorThresholdsErrorV1::NegativeThresholdParameter);
                    }
                    let finite = FiniteF64::try_new(v, kind)
                        .map_err(|_| SeriesPinTableSelectorThresholdsErrorV1::NonFiniteValue)?;
                    Ok(Some(finite))
                }
            }
        };

        let validate_finite = |val: Option<f64>, kind: &'static str| -> Result<Option<FiniteF64>, SeriesPinTableSelectorThresholdsErrorV1> {
            match val {
                None => Ok(None),
                Some(v) => {
                    if !v.is_finite() {
                        return Err(SeriesPinTableSelectorThresholdsErrorV1::NonFiniteValue);
                    }
                    let finite = FiniteF64::try_new(v, kind)
                        .map_err(|_| SeriesPinTableSelectorThresholdsErrorV1::NonFiniteValue)?;
                    Ok(Some(finite))
                }
            }
        };

        let vthreshold_v = validate_finite(vthreshold_v, "vthreshold_v")?;
        let rseries_ohm = validate_non_negative(rseries_ohm, "rseries_ohm")?;
        let cseries_farad = validate_non_negative(cseries_farad, "cseries_farad")?;
        let lseries_henry = validate_non_negative(lseries_henry, "lseries_henry")?;

        Ok(Self {
            pin_first: pf,
            pin_second: ps,
            model_selector_name: ms,
            vthreshold_v,
            rseries_ohm,
            cseries_farad,
            lseries_henry,
        })
    }

    pub fn pin_first(&self) -> &str {
        &self.pin_first
    }

    pub fn pin_second(&self) -> &str {
        &self.pin_second
    }

    pub fn model_selector_name(&self) -> &str {
        &self.model_selector_name
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

/// Lift one series pin selector threshold table record.
pub fn lift_series_pin_selector_threshold_record_v1(
    pin_first: &str,
    pin_second: &str,
    model_selector_name: &str,
    vthreshold_v: Option<f64>,
    rseries_ohm: Option<f64>,
    cseries_farad: Option<f64>,
    lseries_henry: Option<f64>,
) -> Result<TypedSeriesPinSelectorThresholdRecordV1, SeriesPinTableSelectorThresholdsErrorV1> {
    TypedSeriesPinSelectorThresholdRecordV1::try_new(
        pin_first,
        pin_second,
        model_selector_name,
        vthreshold_v,
        rseries_ohm,
        cseries_farad,
        lseries_henry,
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn policy_fixed() {
        assert_eq!(
            SERIES_PIN_TABLE_SELECTOR_THRESHOLDS_POLICY_V1,
            "sipi.p4a-03ba.series-pin-table-selector-thresholds-v1.typed-selector-thresholds"
        );
    }

    #[test]
    fn valid_full_selector_threshold_record() {
        let rec = lift_series_pin_selector_threshold_record_v1(
            "P1",
            "P2",
            "SEL_SERIES_RES",
            Some(1.2),
            Some(50.0),
            Some(1e-12),
            Some(5e-9),
        )
        .expect("lift");
        assert_eq!(rec.pin_first(), "P1");
        assert_eq!(rec.pin_second(), "P2");
        assert_eq!(rec.model_selector_name(), "SEL_SERIES_RES");
        assert_eq!(rec.vthreshold_v().unwrap().get(), 1.2);
        assert_eq!(rec.rseries_ohm().unwrap().get(), 50.0);
    }

    #[test]
    fn valid_minimal_selector_threshold_record() {
        let rec = lift_series_pin_selector_threshold_record_v1(
            "P1",
            "P2",
            "SEL_SERIES_RES",
            None,
            None,
            None,
            None,
        )
        .expect("lift");
        assert_eq!(rec.pin_first(), "P1");
        assert_eq!(rec.pin_second(), "P2");
        assert_eq!(rec.model_selector_name(), "SEL_SERIES_RES");
        assert_eq!(rec.vthreshold_v(), None);
    }

    #[test]
    fn rejects_empty_pin_name() {
        assert_eq!(
            lift_series_pin_selector_threshold_record_v1("", "P2", "SEL1", None, None, None, None),
            Err(SeriesPinTableSelectorThresholdsErrorV1::EmptyPinName)
        );
    }

    #[test]
    fn rejects_negative_rseries() {
        assert_eq!(
            lift_series_pin_selector_threshold_record_v1("P1", "P2", "SEL1", None, Some(-50.0), None, None),
            Err(SeriesPinTableSelectorThresholdsErrorV1::NegativeThresholdParameter)
        );
    }
}
