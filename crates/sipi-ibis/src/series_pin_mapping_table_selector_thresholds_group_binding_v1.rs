//! Typed IBIS [Series Pin Mapping] Model Selector group threshold table binding core (P4A-03ay).
//!
//! Lifts and validates IBIS [Series Pin Mapping] Model Selector group threshold table binding records
//! (pin_first, pin_second, model_selector_name, group_name, threshold parameters) into typed clean-room structures.
//! Fail-closed: empty pin, selector or group names, non-ASCII characters, identical pin pairs,
//! non-finite values, or negative R/C/L threshold parameters are strictly rejected.

use sipi_types::FiniteF64;

/// Scope policy for the typed series pin table selector thresholds group core.
pub const SERIES_PIN_TABLE_SELECTOR_THRESHOLDS_GROUP_POLICY_V1: &str =
    "sipi.p4a-03ay.series-pin-table-selector-thresholds-group-v1.typed-selector-thresholds-group";

/// Fail-closed errors during series pin table selector thresholds group lifting.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum SeriesPinTableSelectorThresholdsGroupErrorV1 {
    EmptyPinName,
    EmptySelectorName,
    EmptyGroupName,
    NonAsciiName,
    InvalidName,
    IdenticalPins,
    NonFiniteValue,
    NegativeThresholdParameter,
}

/// A typed IBIS [Series Pin Mapping] Model Selector group threshold table record.
#[derive(Clone, Debug, PartialEq)]
pub struct TypedSeriesPinSelectorGroupThresholdRecordV1 {
    pin_first: String,
    pin_second: String,
    model_selector_name: String,
    group_name: Option<String>,
    vthreshold_v: Option<FiniteF64>,
    rseries_ohm: Option<FiniteF64>,
    cseries_farad: Option<FiniteF64>,
    lseries_henry: Option<FiniteF64>,
}

impl TypedSeriesPinSelectorGroupThresholdRecordV1 {
    pub fn try_new(
        pin_first: impl Into<String>,
        pin_second: impl Into<String>,
        model_selector_name: impl Into<String>,
        group_name: Option<impl Into<String>>,
        vthreshold_v: Option<f64>,
        rseries_ohm: Option<f64>,
        cseries_farad: Option<f64>,
        lseries_henry: Option<f64>,
    ) -> Result<Self, SeriesPinTableSelectorThresholdsGroupErrorV1> {
        let pf = pin_first.into().trim().to_string();
        let ps = pin_second.into().trim().to_string();
        let ms = model_selector_name.into().trim().to_string();

        if pf.is_empty() || ps.is_empty() {
            return Err(SeriesPinTableSelectorThresholdsGroupErrorV1::EmptyPinName);
        }
        if ms.is_empty() {
            return Err(SeriesPinTableSelectorThresholdsGroupErrorV1::EmptySelectorName);
        }
        if !pf.is_ascii() || !ps.is_ascii() || !ms.is_ascii() {
            return Err(SeriesPinTableSelectorThresholdsGroupErrorV1::NonAsciiName);
        }
        if !pf
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-' || c == '.')
            || !ps
                .chars()
                .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-' || c == '.')
            || !ms
                .chars()
                .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-' || c == '.')
        {
            return Err(SeriesPinTableSelectorThresholdsGroupErrorV1::InvalidName);
        }
        if pf == ps {
            return Err(SeriesPinTableSelectorThresholdsGroupErrorV1::IdenticalPins);
        }

        let gn = group_name.and_then(|g| {
            let t = g.into().trim().to_string();
            if t.is_empty() { None } else { Some(t) }
        });

        if let Some(ref g) = gn {
            if !g.is_ascii() {
                return Err(SeriesPinTableSelectorThresholdsGroupErrorV1::NonAsciiName);
            }
            if !g
                .chars()
                .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-' || c == '.')
            {
                return Err(SeriesPinTableSelectorThresholdsGroupErrorV1::InvalidName);
            }
        }

        let validate_non_negative = |val: Option<f64>,
                                     kind: &'static str|
         -> Result<
            Option<FiniteF64>,
            SeriesPinTableSelectorThresholdsGroupErrorV1,
        > {
            match val {
                None => Ok(None),
                Some(v) => {
                    if !v.is_finite() {
                        return Err(SeriesPinTableSelectorThresholdsGroupErrorV1::NonFiniteValue);
                    }
                    if v < 0.0 {
                        return Err(SeriesPinTableSelectorThresholdsGroupErrorV1::NegativeThresholdParameter);
                    }
                    let finite = FiniteF64::try_new(v, kind).map_err(|_| {
                        SeriesPinTableSelectorThresholdsGroupErrorV1::NonFiniteValue
                    })?;
                    Ok(Some(finite))
                }
            }
        };

        let validate_finite = |val: Option<f64>,
                               kind: &'static str|
         -> Result<
            Option<FiniteF64>,
            SeriesPinTableSelectorThresholdsGroupErrorV1,
        > {
            match val {
                None => Ok(None),
                Some(v) => {
                    if !v.is_finite() {
                        return Err(SeriesPinTableSelectorThresholdsGroupErrorV1::NonFiniteValue);
                    }
                    let finite = FiniteF64::try_new(v, kind).map_err(|_| {
                        SeriesPinTableSelectorThresholdsGroupErrorV1::NonFiniteValue
                    })?;
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
            group_name: gn,
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

    pub fn group_name(&self) -> Option<&str> {
        self.group_name.as_deref()
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

/// Lift one series pin selector group threshold table record.
pub fn lift_series_pin_selector_group_threshold_record_v1(
    pin_first: &str,
    pin_second: &str,
    model_selector_name: &str,
    group_name: Option<&str>,
    vthreshold_v: Option<f64>,
    rseries_ohm: Option<f64>,
    cseries_farad: Option<f64>,
    lseries_henry: Option<f64>,
) -> Result<
    TypedSeriesPinSelectorGroupThresholdRecordV1,
    SeriesPinTableSelectorThresholdsGroupErrorV1,
> {
    TypedSeriesPinSelectorGroupThresholdRecordV1::try_new(
        pin_first,
        pin_second,
        model_selector_name,
        group_name,
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
            SERIES_PIN_TABLE_SELECTOR_THRESHOLDS_GROUP_POLICY_V1,
            "sipi.p4a-03ay.series-pin-table-selector-thresholds-group-v1.typed-selector-thresholds-group"
        );
    }

    #[test]
    fn valid_full_selector_group_threshold_record() {
        let rec = lift_series_pin_selector_group_threshold_record_v1(
            "P1",
            "P2",
            "SEL_SERIES_RES",
            Some("GRP1"),
            Some(1.2),
            Some(50.0),
            Some(1e-12),
            Some(5e-9),
        )
        .expect("lift");
        assert_eq!(rec.pin_first(), "P1");
        assert_eq!(rec.pin_second(), "P2");
        assert_eq!(rec.model_selector_name(), "SEL_SERIES_RES");
        assert_eq!(rec.group_name(), Some("GRP1"));
        assert_eq!(rec.vthreshold_v().unwrap().get(), 1.2);
        assert_eq!(rec.rseries_ohm().unwrap().get(), 50.0);
    }

    #[test]
    fn valid_minimal_selector_group_threshold_record() {
        let rec = lift_series_pin_selector_group_threshold_record_v1(
            "P1",
            "P2",
            "SEL_SERIES_RES",
            None,
            None,
            None,
            None,
            None,
        )
        .expect("lift");
        assert_eq!(rec.pin_first(), "P1");
        assert_eq!(rec.pin_second(), "P2");
        assert_eq!(rec.model_selector_name(), "SEL_SERIES_RES");
        assert_eq!(rec.group_name(), None);
        assert_eq!(rec.vthreshold_v(), None);
    }

    #[test]
    fn rejects_empty_pin_name() {
        assert_eq!(
            lift_series_pin_selector_group_threshold_record_v1(
                "", "P2", "SEL1", None, None, None, None, None
            ),
            Err(SeriesPinTableSelectorThresholdsGroupErrorV1::EmptyPinName)
        );
    }

    #[test]
    fn rejects_negative_rseries() {
        assert_eq!(
            lift_series_pin_selector_group_threshold_record_v1(
                "P1",
                "P2",
                "SEL1",
                None,
                None,
                Some(-50.0),
                None,
                None
            ),
            Err(SeriesPinTableSelectorThresholdsGroupErrorV1::NegativeThresholdParameter)
        );
    }
}
