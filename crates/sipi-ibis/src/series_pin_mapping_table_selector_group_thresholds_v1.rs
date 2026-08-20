//! Typed IBIS [Series Pin Mapping] Model Selector group threshold table binding core (P4A-03bd).
//!
//! Lifts and validates IBIS [Series Pin Mapping] Model Selector group threshold table binding records
//! (group_name, model_selector_name, threshold parameters) into typed clean-room structures.
//! Fail-closed: empty group or selector names, non-ASCII characters, non-finite values,
//! or negative R/C/L threshold parameters are strictly rejected.

use sipi_types::FiniteF64;

/// Scope policy for the typed series pin table selector group thresholds core.
pub const SERIES_PIN_TABLE_SELECTOR_GROUP_THRESHOLDS_POLICY_V1: &str =
    "sipi.p4a-03bd.series-pin-table-selector-group-thresholds-v1.typed-selector-group-thresholds";

/// Fail-closed errors during series pin table selector group thresholds lifting.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum SeriesPinTableSelectorGroupThresholdsErrorV1 {
    EmptyGroupName,
    EmptySelectorName,
    NonAsciiName,
    InvalidName,
    NonFiniteValue,
    NegativeThresholdParameter,
}

/// A typed IBIS [Series Pin Mapping] group Model Selector threshold table record.
#[derive(Clone, Debug, PartialEq)]
pub struct TypedSeriesPinGroupSelectorThresholdRecordV1 {
    group_name: String,
    model_selector_name: String,
    vthreshold_v: Option<FiniteF64>,
    rseries_ohm: Option<FiniteF64>,
    cseries_farad: Option<FiniteF64>,
    lseries_henry: Option<FiniteF64>,
}

impl TypedSeriesPinGroupSelectorThresholdRecordV1 {
    pub fn try_new(
        group_name: impl Into<String>,
        model_selector_name: impl Into<String>,
        vthreshold_v: Option<f64>,
        rseries_ohm: Option<f64>,
        cseries_farad: Option<f64>,
        lseries_henry: Option<f64>,
    ) -> Result<Self, SeriesPinTableSelectorGroupThresholdsErrorV1> {
        let gn = group_name.into().trim().to_string();
        let ms = model_selector_name.into().trim().to_string();

        if gn.is_empty() {
            return Err(SeriesPinTableSelectorGroupThresholdsErrorV1::EmptyGroupName);
        }
        if ms.is_empty() {
            return Err(SeriesPinTableSelectorGroupThresholdsErrorV1::EmptySelectorName);
        }
        if !gn.is_ascii() || !ms.is_ascii() {
            return Err(SeriesPinTableSelectorGroupThresholdsErrorV1::NonAsciiName);
        }
        if !gn.chars().all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-' || c == '.')
            || !ms.chars().all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-' || c == '.')
        {
            return Err(SeriesPinTableSelectorGroupThresholdsErrorV1::InvalidName);
        }

        let validate_non_negative = |val: Option<f64>, kind: &'static str| -> Result<Option<FiniteF64>, SeriesPinTableSelectorGroupThresholdsErrorV1> {
            match val {
                None => Ok(None),
                Some(v) => {
                    if !v.is_finite() {
                        return Err(SeriesPinTableSelectorGroupThresholdsErrorV1::NonFiniteValue);
                    }
                    if v < 0.0 {
                        return Err(SeriesPinTableSelectorGroupThresholdsErrorV1::NegativeThresholdParameter);
                    }
                    let finite = FiniteF64::try_new(v, kind)
                        .map_err(|_| SeriesPinTableSelectorGroupThresholdsErrorV1::NonFiniteValue)?;
                    Ok(Some(finite))
                }
            }
        };

        let validate_finite = |val: Option<f64>, kind: &'static str| -> Result<Option<FiniteF64>, SeriesPinTableSelectorGroupThresholdsErrorV1> {
            match val {
                None => Ok(None),
                Some(v) => {
                    if !v.is_finite() {
                        return Err(SeriesPinTableSelectorGroupThresholdsErrorV1::NonFiniteValue);
                    }
                    let finite = FiniteF64::try_new(v, kind)
                        .map_err(|_| SeriesPinTableSelectorGroupThresholdsErrorV1::NonFiniteValue)?;
                    Ok(Some(finite))
                }
            }
        };

        let vthreshold_v = validate_finite(vthreshold_v, "vthreshold_v")?;
        let rseries_ohm = validate_non_negative(rseries_ohm, "rseries_ohm")?;
        let cseries_farad = validate_non_negative(cseries_farad, "cseries_farad")?;
        let lseries_henry = validate_non_negative(lseries_henry, "lseries_henry")?;

        Ok(Self {
            group_name: gn,
            model_selector_name: ms,
            vthreshold_v,
            rseries_ohm,
            cseries_farad,
            lseries_henry,
        })
    }

    pub fn group_name(&self) -> &str {
        &self.group_name
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

/// Lift one series pin group selector threshold table record.
pub fn lift_series_pin_group_selector_threshold_record_v1(
    group_name: &str,
    model_selector_name: &str,
    vthreshold_v: Option<f64>,
    rseries_ohm: Option<f64>,
    cseries_farad: Option<f64>,
    lseries_henry: Option<f64>,
) -> Result<TypedSeriesPinGroupSelectorThresholdRecordV1, SeriesPinTableSelectorGroupThresholdsErrorV1> {
    TypedSeriesPinGroupSelectorThresholdRecordV1::try_new(
        group_name,
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
            SERIES_PIN_TABLE_SELECTOR_GROUP_THRESHOLDS_POLICY_V1,
            "sipi.p4a-03bd.series-pin-table-selector-group-thresholds-v1.typed-selector-group-thresholds"
        );
    }

    #[test]
    fn valid_full_group_selector_threshold_record() {
        let rec = lift_series_pin_group_selector_threshold_record_v1(
            "SERIES_GRP1",
            "SEL_SERIES_RES",
            Some(1.2),
            Some(50.0),
            Some(1e-12),
            Some(5e-9),
        )
        .expect("lift");
        assert_eq!(rec.group_name(), "SERIES_GRP1");
        assert_eq!(rec.model_selector_name(), "SEL_SERIES_RES");
        assert_eq!(rec.vthreshold_v().unwrap().get(), 1.2);
        assert_eq!(rec.rseries_ohm().unwrap().get(), 50.0);
    }

    #[test]
    fn valid_minimal_group_selector_threshold_record() {
        let rec = lift_series_pin_group_selector_threshold_record_v1(
            "SERIES_GRP1",
            "SEL_SERIES_RES",
            None,
            None,
            None,
            None,
        )
        .expect("lift");
        assert_eq!(rec.group_name(), "SERIES_GRP1");
        assert_eq!(rec.model_selector_name(), "SEL_SERIES_RES");
        assert_eq!(rec.vthreshold_v(), None);
    }

    #[test]
    fn rejects_empty_group_name() {
        assert_eq!(
            lift_series_pin_group_selector_threshold_record_v1("", "SEL1", None, None, None, None),
            Err(SeriesPinTableSelectorGroupThresholdsErrorV1::EmptyGroupName)
        );
    }

    #[test]
    fn rejects_negative_rseries() {
        assert_eq!(
            lift_series_pin_group_selector_threshold_record_v1("SERIES_GRP1", "SEL1", None, Some(-50.0), None, None),
            Err(SeriesPinTableSelectorGroupThresholdsErrorV1::NegativeThresholdParameter)
        );
    }
}
