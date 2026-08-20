//! Typed IBIS [Series Pin Mapping] group threshold parameters record core (P4A-03at).
//!
//! Lifts and validates IBIS [Series Pin Mapping] group threshold parameters records
//! (group_name, threshold parameters) into typed clean-room structures.
//! Fail-closed: empty group names, non-ASCII characters, non-finite values,
//! or negative R/C/L threshold parameters are strictly rejected.

use sipi_types::FiniteF64;

/// Scope policy for the typed series pin thresholds group core.
pub const SERIES_PIN_TABLE_THRESHOLDS_GROUP_POLICY_V1: &str =
    "sipi.p4a-03at.series-pin-table-thresholds-group-v1.typed-group-thresholds";

/// Fail-closed errors during series pin thresholds group lifting.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum SeriesPinTableThresholdsGroupErrorV1 {
    EmptyGroupName,
    NonAsciiName,
    InvalidName,
    NonFiniteValue,
    NegativeThresholdParameter,
}

/// A typed IBIS [Series Pin Mapping] group threshold parameters record.
#[derive(Clone, Debug, PartialEq)]
pub struct TypedSeriesPinTableGroupThresholdsV1 {
    group_name: String,
    vthreshold_v: Option<FiniteF64>,
    rseries_ohm: Option<FiniteF64>,
    cseries_farad: Option<FiniteF64>,
    lseries_henry: Option<FiniteF64>,
}

impl TypedSeriesPinTableGroupThresholdsV1 {
    pub fn try_new(
        group_name: impl Into<String>,
        vthreshold_v: Option<f64>,
        rseries_ohm: Option<f64>,
        cseries_farad: Option<f64>,
        lseries_henry: Option<f64>,
    ) -> Result<Self, SeriesPinTableThresholdsGroupErrorV1> {
        let gn = group_name.into().trim().to_string();

        if gn.is_empty() {
            return Err(SeriesPinTableThresholdsGroupErrorV1::EmptyGroupName);
        }
        if !gn.is_ascii() {
            return Err(SeriesPinTableThresholdsGroupErrorV1::NonAsciiName);
        }
        if !gn.chars().all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-' || c == '.') {
            return Err(SeriesPinTableThresholdsGroupErrorV1::InvalidName);
        }

        let validate_non_negative = |val: Option<f64>, kind: &'static str| -> Result<Option<FiniteF64>, SeriesPinTableThresholdsGroupErrorV1> {
            match val {
                None => Ok(None),
                Some(v) => {
                    if !v.is_finite() {
                        return Err(SeriesPinTableThresholdsGroupErrorV1::NonFiniteValue);
                    }
                    if v < 0.0 {
                        return Err(SeriesPinTableThresholdsGroupErrorV1::NegativeThresholdParameter);
                    }
                    let finite = FiniteF64::try_new(v, kind)
                        .map_err(|_| SeriesPinTableThresholdsGroupErrorV1::NonFiniteValue)?;
                    Ok(Some(finite))
                }
            }
        };

        let validate_finite = |val: Option<f64>, kind: &'static str| -> Result<Option<FiniteF64>, SeriesPinTableThresholdsGroupErrorV1> {
            match val {
                None => Ok(None),
                Some(v) => {
                    if !v.is_finite() {
                        return Err(SeriesPinTableThresholdsGroupErrorV1::NonFiniteValue);
                    }
                    let finite = FiniteF64::try_new(v, kind)
                        .map_err(|_| SeriesPinTableThresholdsGroupErrorV1::NonFiniteValue)?;
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
            vthreshold_v,
            rseries_ohm,
            cseries_farad,
            lseries_henry,
        })
    }

    pub fn group_name(&self) -> &str {
        &self.group_name
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

/// Lift one series pin group threshold parameters record.
pub fn lift_series_pin_table_group_thresholds_v1(
    group_name: &str,
    vthreshold_v: Option<f64>,
    rseries_ohm: Option<f64>,
    cseries_farad: Option<f64>,
    lseries_henry: Option<f64>,
) -> Result<TypedSeriesPinTableGroupThresholdsV1, SeriesPinTableThresholdsGroupErrorV1> {
    TypedSeriesPinTableGroupThresholdsV1::try_new(
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
            SERIES_PIN_TABLE_THRESHOLDS_GROUP_POLICY_V1,
            "sipi.p4a-03at.series-pin-table-thresholds-group-v1.typed-group-thresholds"
        );
    }

    #[test]
    fn valid_full_group_thresholds_record() {
        let rec = lift_series_pin_table_group_thresholds_v1(
            "SERIES_GRP1",
            Some(1.2),
            Some(50.0),
            Some(1e-12),
            Some(5e-9),
        )
        .expect("lift");
        assert_eq!(rec.group_name(), "SERIES_GRP1");
        assert_eq!(rec.vthreshold_v().unwrap().get(), 1.2);
        assert_eq!(rec.rseries_ohm().unwrap().get(), 50.0);
    }

    #[test]
    fn valid_minimal_group_thresholds_record() {
        let rec = lift_series_pin_table_group_thresholds_v1(
            "SERIES_GRP1",
            None,
            None,
            None,
            None,
        )
        .expect("lift");
        assert_eq!(rec.group_name(), "SERIES_GRP1");
        assert_eq!(rec.vthreshold_v(), None);
    }

    #[test]
    fn rejects_empty_group_name() {
        assert_eq!(
            lift_series_pin_table_group_thresholds_v1("", None, None, None, None),
            Err(SeriesPinTableThresholdsGroupErrorV1::EmptyGroupName)
        );
    }

    #[test]
    fn rejects_negative_rseries() {
        assert_eq!(
            lift_series_pin_table_group_thresholds_v1("SERIES_GRP1", None, Some(-50.0), None, None),
            Err(SeriesPinTableThresholdsGroupErrorV1::NegativeThresholdParameter)
        );
    }
}
