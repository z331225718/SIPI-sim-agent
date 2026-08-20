//! Typed IBIS [Series Pin Mapping] group switch threshold table binding core (P4A-03bc).
//!
//! Lifts and validates IBIS [Series Pin Mapping] group switch threshold table binding records
//! (group_name, on_group_name, off_group_name, threshold parameters) into typed clean-room structures.
//! Fail-closed: empty group names, non-ASCII characters, identical ON/OFF state groups,
//! non-finite values, or negative R/C/L threshold parameters are strictly rejected.

use sipi_types::FiniteF64;

fn validate_non_negative_threshold(
    val: Option<f64>,
    kind: &'static str,
) -> Result<Option<FiniteF64>, SeriesPinTableGroupSwitchThresholdsErrorV1> {
    match val {
        None => Ok(None),
        Some(v) if !v.is_finite() => {
            Err(SeriesPinTableGroupSwitchThresholdsErrorV1::NonFiniteValue)
        }
        Some(v) if v < 0.0 => {
            Err(SeriesPinTableGroupSwitchThresholdsErrorV1::NegativeThresholdParameter)
        }
        Some(v) => FiniteF64::try_new(v, kind)
            .map(Some)
            .map_err(|_| SeriesPinTableGroupSwitchThresholdsErrorV1::NonFiniteValue),
    }
}

/// Scope policy for the typed series pin table group switch thresholds core.
pub const SERIES_PIN_TABLE_GROUP_SWITCH_THRESHOLDS_POLICY_V1: &str =
    "sipi.p4a-03bc.series-pin-table-group-switch-thresholds-v1.typed-group-switch-thresholds";

/// Fail-closed errors during series pin table group switch thresholds lifting.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum SeriesPinTableGroupSwitchThresholdsErrorV1 {
    EmptyGroupName,
    EmptyStateGroupName,
    NonAsciiName,
    InvalidName,
    IdenticalStateGroups,
    NonFiniteValue,
    NegativeThresholdParameter,
}

/// A typed IBIS [Series Pin Mapping] group switch threshold table record.
#[derive(Clone, Debug, PartialEq)]
pub struct TypedSeriesPinGroupSwitchThresholdRecordV1 {
    group_name: String,
    on_group_name: String,
    off_group_name: String,
    vthreshold_v: Option<FiniteF64>,
    rseries_ohm: Option<FiniteF64>,
    cseries_farad: Option<FiniteF64>,
    lseries_henry: Option<FiniteF64>,
}

impl TypedSeriesPinGroupSwitchThresholdRecordV1 {
    pub fn try_new(
        group_name: impl Into<String>,
        on_group_name: impl Into<String>,
        off_group_name: impl Into<String>,
        vthreshold_v: Option<f64>,
        rseries_ohm: Option<f64>,
        cseries_farad: Option<f64>,
        lseries_henry: Option<f64>,
    ) -> Result<Self, SeriesPinTableGroupSwitchThresholdsErrorV1> {
        let gn = group_name.into().trim().to_string();
        let on_g = on_group_name.into().trim().to_string();
        let off_g = off_group_name.into().trim().to_string();

        if gn.is_empty() {
            return Err(SeriesPinTableGroupSwitchThresholdsErrorV1::EmptyGroupName);
        }
        if on_g.is_empty() || off_g.is_empty() {
            return Err(SeriesPinTableGroupSwitchThresholdsErrorV1::EmptyStateGroupName);
        }
        if !gn.is_ascii() || !on_g.is_ascii() || !off_g.is_ascii() {
            return Err(SeriesPinTableGroupSwitchThresholdsErrorV1::NonAsciiName);
        }
        if !gn
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-' || c == '.')
            || !on_g
                .chars()
                .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-' || c == '.')
            || !off_g
                .chars()
                .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-' || c == '.')
        {
            return Err(SeriesPinTableGroupSwitchThresholdsErrorV1::InvalidName);
        }
        if on_g == off_g {
            return Err(SeriesPinTableGroupSwitchThresholdsErrorV1::IdenticalStateGroups);
        }

        let validate_finite =
            |val: Option<f64>,
             kind: &'static str|
             -> Result<Option<FiniteF64>, SeriesPinTableGroupSwitchThresholdsErrorV1> {
                match val {
                    None => Ok(None),
                    Some(v) => {
                        if !v.is_finite() {
                            return Err(SeriesPinTableGroupSwitchThresholdsErrorV1::NonFiniteValue);
                        }
                        let finite = FiniteF64::try_new(v, kind).map_err(|_| {
                            SeriesPinTableGroupSwitchThresholdsErrorV1::NonFiniteValue
                        })?;
                        Ok(Some(finite))
                    }
                }
            };

        let vthreshold_v = validate_finite(vthreshold_v, "vthreshold_v")?;
        let rseries_ohm = validate_non_negative_threshold(rseries_ohm, "rseries_ohm")?;
        let cseries_farad = validate_non_negative_threshold(cseries_farad, "cseries_farad")?;
        let lseries_henry = validate_non_negative_threshold(lseries_henry, "lseries_henry")?;

        Ok(Self {
            group_name: gn,
            on_group_name: on_g,
            off_group_name: off_g,
            vthreshold_v,
            rseries_ohm,
            cseries_farad,
            lseries_henry,
        })
    }

    pub fn group_name(&self) -> &str {
        &self.group_name
    }

    pub fn on_group_name(&self) -> &str {
        &self.on_group_name
    }

    pub fn off_group_name(&self) -> &str {
        &self.off_group_name
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

/// Lift one series pin group switch threshold table record.
pub fn lift_series_pin_group_switch_threshold_record_v1(
    group_name: &str,
    on_group_name: &str,
    off_group_name: &str,
    vthreshold_v: Option<f64>,
    rseries_ohm: Option<f64>,
    cseries_farad: Option<f64>,
    lseries_henry: Option<f64>,
) -> Result<TypedSeriesPinGroupSwitchThresholdRecordV1, SeriesPinTableGroupSwitchThresholdsErrorV1>
{
    TypedSeriesPinGroupSwitchThresholdRecordV1::try_new(
        group_name,
        on_group_name,
        off_group_name,
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
            SERIES_PIN_TABLE_GROUP_SWITCH_THRESHOLDS_POLICY_V1,
            "sipi.p4a-03bc.series-pin-table-group-switch-thresholds-v1.typed-group-switch-thresholds"
        );
    }

    #[test]
    fn valid_full_group_switch_threshold_record() {
        let rec = lift_series_pin_group_switch_threshold_record_v1(
            "SERIES_GRP1",
            "GROUP_ON_1",
            "GROUP_OFF_1",
            Some(1.8),
            Some(10.0),
            Some(0.5e-12),
            Some(2e-9),
        )
        .expect("lift");
        assert_eq!(rec.group_name(), "SERIES_GRP1");
        assert_eq!(rec.on_group_name(), "GROUP_ON_1");
        assert_eq!(rec.off_group_name(), "GROUP_OFF_1");
        assert_eq!(rec.vthreshold_v().unwrap().get(), 1.8);
        assert_eq!(rec.rseries_ohm().unwrap().get(), 10.0);
    }

    #[test]
    fn valid_minimal_group_switch_threshold_record() {
        let rec = lift_series_pin_group_switch_threshold_record_v1(
            "SERIES_GRP1",
            "GROUP_ON_1",
            "GROUP_OFF_1",
            None,
            None,
            None,
            None,
        )
        .expect("lift");
        assert_eq!(rec.group_name(), "SERIES_GRP1");
        assert_eq!(rec.on_group_name(), "GROUP_ON_1");
        assert_eq!(rec.off_group_name(), "GROUP_OFF_1");
        assert_eq!(rec.vthreshold_v(), None);
    }

    #[test]
    fn rejects_empty_group_name() {
        assert_eq!(
            lift_series_pin_group_switch_threshold_record_v1(
                "",
                "GROUP_ON_1",
                "GROUP_OFF_1",
                None,
                None,
                None,
                None
            ),
            Err(SeriesPinTableGroupSwitchThresholdsErrorV1::EmptyGroupName)
        );
    }

    #[test]
    fn rejects_identical_state_groups() {
        assert_eq!(
            lift_series_pin_group_switch_threshold_record_v1(
                "SERIES_GRP1",
                "GROUP_1",
                "GROUP_1",
                None,
                None,
                None,
                None
            ),
            Err(SeriesPinTableGroupSwitchThresholdsErrorV1::IdenticalStateGroups)
        );
    }

    #[test]
    fn rejects_negative_rseries() {
        assert_eq!(
            lift_series_pin_group_switch_threshold_record_v1(
                "SERIES_GRP1",
                "GROUP_ON_1",
                "GROUP_OFF_1",
                None,
                Some(-10.0),
                None,
                None
            ),
            Err(SeriesPinTableGroupSwitchThresholdsErrorV1::NegativeThresholdParameter)
        );
    }
}
