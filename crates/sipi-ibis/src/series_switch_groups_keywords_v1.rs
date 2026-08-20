//! Typed IBIS [Series Switch Groups] complete block required keywords core (P4A-03ag).
//!
//! Lifts and validates IBIS [Series Switch Groups] complete block required sub-keyword entries
//! (switch group record vs switch threshold parameters) into typed clean-room structures.
//! Fail-closed: invalid series switch records or missing required fields are strictly rejected.

use crate::series_switch_mapping_v1::TypedSeriesSwitchRecordV1;
use crate::series_switch_thresholds_v1::TypedSeriesSwitchThresholdsV1;

/// Scope policy for the typed series switch keywords core.
pub const SERIES_SWITCH_KEYWORDS_POLICY_V1: &str =
    "sipi.p4a-03ag.series-switch-keywords-v1.typed-switch-keywords";

/// Fail-closed errors during series switch keywords validation.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum SeriesSwitchKeywordsErrorV1 {
    MissingSeriesSwitchRecord,
}

/// A composite typed IBIS [Series Switch Groups] complete block entry.
#[derive(Clone, Debug, PartialEq)]
pub struct TypedSeriesSwitchBlockV1 {
    switch_record: TypedSeriesSwitchRecordV1,
    thresholds: Option<TypedSeriesSwitchThresholdsV1>,
}

impl TypedSeriesSwitchBlockV1 {
    pub fn try_new(
        switch_record: TypedSeriesSwitchRecordV1,
        thresholds: Option<TypedSeriesSwitchThresholdsV1>,
    ) -> Result<Self, SeriesSwitchKeywordsErrorV1> {
        Ok(Self {
            switch_record,
            thresholds,
        })
    }

    pub fn switch_record(&self) -> &TypedSeriesSwitchRecordV1 {
        &self.switch_record
    }

    pub fn thresholds(&self) -> Option<&TypedSeriesSwitchThresholdsV1> {
        self.thresholds.as_ref()
    }
}

/// Lift one complete series switch block entry.
pub fn lift_series_switch_block_v1(
    switch_record: TypedSeriesSwitchRecordV1,
    thresholds: Option<TypedSeriesSwitchThresholdsV1>,
) -> Result<TypedSeriesSwitchBlockV1, SeriesSwitchKeywordsErrorV1> {
    TypedSeriesSwitchBlockV1::try_new(switch_record, thresholds)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::series_switch_mapping_v1::lift_series_switch_record_v1;
    use crate::series_switch_thresholds_v1::lift_series_switch_thresholds_v1;

    #[test]
    fn policy_fixed() {
        assert_eq!(
            SERIES_SWITCH_KEYWORDS_POLICY_V1,
            "sipi.p4a-03ag.series-switch-keywords-v1.typed-switch-keywords"
        );
    }

    #[test]
    fn valid_series_switch_block() {
        let rec = lift_series_switch_record_v1("GROUP_ON_1", "GROUP_OFF_1").unwrap();
        let thresh = lift_series_switch_thresholds_v1(Some(1.8), Some(10.0), None, None).unwrap();
        let block = lift_series_switch_block_v1(rec, Some(thresh)).expect("lift");

        assert_eq!(block.switch_record().on_group_name(), "GROUP_ON_1");
        assert_eq!(block.switch_record().off_group_name(), "GROUP_OFF_1");
        assert_eq!(
            block.thresholds().unwrap().vthreshold_v().unwrap().get(),
            1.8
        );
    }
}
