//! Typed IBIS [Series Pin Mapping] required sub-keywords completeness core (P4A-03af).
//!
//! Lifts and validates IBIS [Series Pin Mapping] required sub-keyword entries
//! (pin pair record vs group record vs threshold parameters) into typed clean-room structures.
//! Fail-closed: invalid series pin records or missing required fields are strictly rejected.

use crate::series_pin_mapping_v1::TypedSeriesPinRecordV1;
use crate::series_pin_thresholds_v1::TypedSeriesPinThresholdsV1;

/// Scope policy for the typed series pin mapping keywords core.
pub const SERIES_PIN_MAPPING_KEYWORDS_POLICY_V1: &str =
    "sipi.p4a-03af.series-pin-mapping-keywords-v1.typed-series-keywords";

/// Fail-closed errors during series pin mapping keywords validation.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum SeriesPinMappingKeywordsErrorV1 {
    MissingSeriesPinPair,
}

/// A composite typed IBIS [Series Pin Mapping] complete block entry.
#[derive(Clone, Debug, PartialEq)]
pub struct TypedSeriesPinMappingBlockV1 {
    pin_record: TypedSeriesPinRecordV1,
    thresholds: Option<TypedSeriesPinThresholdsV1>,
}

impl TypedSeriesPinMappingBlockV1 {
    pub fn try_new(
        pin_record: TypedSeriesPinRecordV1,
        thresholds: Option<TypedSeriesPinThresholdsV1>,
    ) -> Result<Self, SeriesPinMappingKeywordsErrorV1> {
        Ok(Self {
            pin_record,
            thresholds,
        })
    }

    pub fn pin_record(&self) -> &TypedSeriesPinRecordV1 {
        &self.pin_record
    }

    pub fn thresholds(&self) -> Option<&TypedSeriesPinThresholdsV1> {
        self.thresholds.as_ref()
    }
}

/// Lift one complete series pin mapping block entry.
pub fn lift_series_pin_mapping_block_v1(
    pin_record: TypedSeriesPinRecordV1,
    thresholds: Option<TypedSeriesPinThresholdsV1>,
) -> Result<TypedSeriesPinMappingBlockV1, SeriesPinMappingKeywordsErrorV1> {
    TypedSeriesPinMappingBlockV1::try_new(pin_record, thresholds)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::series_pin_mapping_v1::lift_series_pin_record_v1;
    use crate::series_pin_thresholds_v1::lift_series_pin_thresholds_v1;

    #[test]
    fn policy_fixed() {
        assert_eq!(
            SERIES_PIN_MAPPING_KEYWORDS_POLICY_V1,
            "sipi.p4a-03af.series-pin-mapping-keywords-v1.typed-series-keywords"
        );
    }

    #[test]
    fn valid_series_pin_mapping_block() {
        let rec = lift_series_pin_record_v1("P1", "P2", "R_SERIES_50", Some("GRP1")).unwrap();
        let thresh = lift_series_pin_thresholds_v1(Some(1.2), Some(50.0), None, None).unwrap();
        let block = lift_series_pin_mapping_block_v1(rec, Some(thresh)).expect("lift");

        assert_eq!(block.pin_record().pin_first(), "P1");
        assert_eq!(block.pin_record().pin_second(), "P2");
        assert_eq!(block.thresholds().unwrap().vthreshold_v().unwrap().get(), 1.2);
    }
}
