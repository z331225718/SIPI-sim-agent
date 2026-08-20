//! Typed IBIS [Receiver Thresholds] complete block required keywords core (P4A-03ah).
//!
//! Lifts and validates IBIS [Receiver Thresholds] complete block required sub-keyword entries
//! (receiver thresholds vs optional sensitivity thresholds) into typed clean-room structures.
//! Fail-closed: invalid receiver thresholds or missing required fields are strictly rejected.

use crate::receiver_thresholds_v1::TypedReceiverThresholdsV1;
use sipi_types::FiniteF64;

/// Scope policy for the typed receiver thresholds keywords core.
pub const RECEIVER_THRESHOLDS_KEYWORDS_POLICY_V1: &str =
    "sipi.p4a-03ah.receiver-thresholds-keywords-v1.typed-receiver-keywords";

/// Fail-closed errors during receiver thresholds keywords validation.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ReceiverThresholdsKeywordsErrorV1 {
    MissingReceiverThresholds,
    NonFiniteValue,
    NegativeSensitivity,
}

/// A composite typed IBIS [Receiver Thresholds] complete block entry.
#[derive(Clone, Debug, PartialEq)]
pub struct TypedReceiverThresholdsBlockV1 {
    thresholds: TypedReceiverThresholdsV1,
    vsensitivity_v: Option<FiniteF64>,
}

impl TypedReceiverThresholdsBlockV1 {
    pub fn try_new(
        thresholds: TypedReceiverThresholdsV1,
        vsensitivity_v: Option<f64>,
    ) -> Result<Self, ReceiverThresholdsKeywordsErrorV1> {
        let vsensitivity_v = match vsensitivity_v {
            None => None,
            Some(v) => {
                if !v.is_finite() {
                    return Err(ReceiverThresholdsKeywordsErrorV1::NonFiniteValue);
                }
                if v < 0.0 {
                    return Err(ReceiverThresholdsKeywordsErrorV1::NegativeSensitivity);
                }
                let finite = FiniteF64::try_new(v, "vsensitivity_v")
                    .map_err(|_| ReceiverThresholdsKeywordsErrorV1::NonFiniteValue)?;
                Some(finite)
            }
        };

        Ok(Self {
            thresholds,
            vsensitivity_v,
        })
    }

    pub fn thresholds(&self) -> &TypedReceiverThresholdsV1 {
        &self.thresholds
    }

    pub fn vsensitivity_v(&self) -> Option<FiniteF64> {
        self.vsensitivity_v
    }
}

/// Lift one complete receiver thresholds block entry.
pub fn lift_receiver_thresholds_block_v1(
    thresholds: TypedReceiverThresholdsV1,
    vsensitivity_v: Option<f64>,
) -> Result<TypedReceiverThresholdsBlockV1, ReceiverThresholdsKeywordsErrorV1> {
    TypedReceiverThresholdsBlockV1::try_new(thresholds, vsensitivity_v)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::receiver_thresholds_v1::lift_receiver_thresholds_v1;

    #[test]
    fn policy_fixed() {
        assert_eq!(
            RECEIVER_THRESHOLDS_KEYWORDS_POLICY_V1,
            "sipi.p4a-03ah.receiver-thresholds-keywords-v1.typed-receiver-keywords"
        );
    }

    #[test]
    fn valid_receiver_thresholds_block() {
        let rx = lift_receiver_thresholds_v1(Some(0.8), Some(1.2), Some(0.15), None, None).unwrap();
        let block = lift_receiver_thresholds_block_v1(rx, Some(0.05)).expect("lift");

        assert_eq!(block.thresholds().vcross_low_v().unwrap().get(), 0.8);
        assert_eq!(block.vsensitivity_v().unwrap().get(), 0.05);
    }

    #[test]
    fn rejects_negative_sensitivity() {
        let rx = lift_receiver_thresholds_v1(Some(0.8), Some(1.2), None, None, None).unwrap();
        assert_eq!(
            lift_receiver_thresholds_block_v1(rx, Some(-0.05)),
            Err(ReceiverThresholdsKeywordsErrorV1::NegativeSensitivity)
        );
    }
}
