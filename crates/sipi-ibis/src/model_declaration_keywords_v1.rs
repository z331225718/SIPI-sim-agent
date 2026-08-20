//! Typed IBIS [Model] required sub-keywords validation core (P4A-03ab).
//!
//! Lifts and validates IBIS [Model] required sub-keywords according to Model_type rules
//! (e.g. Input/Output/I_O requiring [Pullup], [Pulldown], [GND Clamp], [POWER Clamp]).
//! Fail-closed: missing required sub-keywords for the specified Model_type
//! are strictly rejected.

use crate::model_declaration_v1::ModelTypeV1;

/// Scope policy for the typed model declaration keywords core.
pub const MODEL_DECLARATION_KEYWORDS_POLICY_V1: &str =
    "sipi.p4a-03ab.model-keywords-v1.typed-model-keywords";

/// Fail-closed errors during model keyword validation.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ModelDeclarationKeywordsErrorV1 {
    MissingRequiredSubKeyword {
        model_type: String,
        missing_keyword: String,
    },
}

/// A summary of present sub-keywords inside an IBIS [Model] block.
#[derive(Clone, Debug, Default, Eq, PartialEq)]
pub struct ModelSubKeywordsV1 {
    pub has_pullup: bool,
    pub has_pulldown: bool,
    pub has_gnd_clamp: bool,
    pub has_power_clamp: bool,
}

/// Validate sub-keyword completeness for a given Model_type.
pub fn validate_model_keywords_v1(
    model_type: ModelTypeV1,
    sub_keywords: &ModelSubKeywordsV1,
) -> Result<(), ModelDeclarationKeywordsErrorV1> {
    let type_str = format!("{model_type:?}");

    match model_type {
        ModelTypeV1::Output | ModelTypeV1::IO | ModelTypeV1::ThreeState => {
            if !sub_keywords.has_pullup {
                return Err(ModelDeclarationKeywordsErrorV1::MissingRequiredSubKeyword {
                    model_type: type_str.to_string(),
                    missing_keyword: "[Pullup]".to_string(),
                });
            }
            if !sub_keywords.has_pulldown {
                return Err(ModelDeclarationKeywordsErrorV1::MissingRequiredSubKeyword {
                    model_type: type_str.to_string(),
                    missing_keyword: "[Pulldown]".to_string(),
                });
            }
        }
        ModelTypeV1::Input => {
            // Inputs require GND Clamp or POWER Clamp or Pullup/Pulldown in full spec,
            // for clean-room sub-keyword validation core, check GND Clamp
            if !sub_keywords.has_gnd_clamp && !sub_keywords.has_power_clamp && !sub_keywords.has_pullup && !sub_keywords.has_pulldown {
                return Err(ModelDeclarationKeywordsErrorV1::MissingRequiredSubKeyword {
                    model_type: type_str.to_string(),
                    missing_keyword: "[GND Clamp] or [POWER Clamp]".to_string(),
                });
            }
        }
        _ => {}
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn policy_fixed() {
        assert_eq!(
            MODEL_DECLARATION_KEYWORDS_POLICY_V1,
            "sipi.p4a-03ab.model-keywords-v1.typed-model-keywords"
        );
    }

    #[test]
    fn valid_output_model_keywords() {
        let kw = ModelSubKeywordsV1 {
            has_pullup: true,
            has_pulldown: true,
            has_gnd_clamp: true,
            has_power_clamp: true,
        };
        assert!(validate_model_keywords_v1(ModelTypeV1::Output, &kw).is_ok());
    }

    #[test]
    fn rejects_missing_pullup_for_output() {
        let kw = ModelSubKeywordsV1 {
            has_pullup: false,
            has_pulldown: true,
            has_gnd_clamp: false,
            has_power_clamp: false,
        };
        assert_eq!(
            validate_model_keywords_v1(ModelTypeV1::Output, &kw),
            Err(ModelDeclarationKeywordsErrorV1::MissingRequiredSubKeyword {
                model_type: "Output".to_string(),
                missing_keyword: "[Pullup]".to_string(),
            })
        );
    }

    #[test]
    fn rejects_missing_pulldown_for_output() {
        let kw = ModelSubKeywordsV1 {
            has_pullup: true,
            has_pulldown: false,
            has_gnd_clamp: false,
            has_power_clamp: false,
        };
        assert_eq!(
            validate_model_keywords_v1(ModelTypeV1::Output, &kw),
            Err(ModelDeclarationKeywordsErrorV1::MissingRequiredSubKeyword {
                model_type: "Output".to_string(),
                missing_keyword: "[Pulldown]".to_string(),
            })
        );
    }
}
