//! Typed IBIS [Model Selector] keyword completeness core (P4A-03ad).
//!
//! Lifts and validates IBIS [Model Selector] declarations
//! (selector_name, list of model option entries) into typed clean-room structures.
//! Fail-closed: empty selector names, non-ASCII characters, invalid name spellings,
//! or empty model option lists are strictly rejected.

use std::collections::BTreeSet;

/// Scope policy for the typed model selector keywords core.
pub const MODEL_SELECTOR_KEYWORDS_POLICY_V1: &str =
    "sipi.p4a-03ad.model-selector-keywords-v1.typed-selector-keywords";

/// Fail-closed errors during model selector keyword lifting.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ModelSelectorKeywordsErrorV1 {
    EmptySelectorName,
    NonAsciiName,
    InvalidName,
    EmptyModelOptions,
    DuplicateModelOption(String),
}

/// One model option entry inside a [Model Selector] block.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ModelOptionEntryV1 {
    model_name: String,
    description: Option<String>,
}

impl ModelOptionEntryV1 {
    pub fn try_new(
        model_name: impl Into<String>,
        description: Option<&str>,
    ) -> Result<Self, ModelSelectorKeywordsErrorV1> {
        let name = model_name.into();
        let trimmed = name.trim();
        if trimmed.is_empty() {
            return Err(ModelSelectorKeywordsErrorV1::EmptySelectorName);
        }
        if !trimmed.is_ascii() {
            return Err(ModelSelectorKeywordsErrorV1::NonAsciiName);
        }
        if !trimmed
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-' || c == '.')
        {
            return Err(ModelSelectorKeywordsErrorV1::InvalidName);
        }

        let desc = description.and_then(|d| {
            let t = d.trim().to_string();
            if t.is_empty() { None } else { Some(t) }
        });

        if let Some(ref d) = desc
            && !d.is_ascii()
        {
            return Err(ModelSelectorKeywordsErrorV1::NonAsciiName);
        }

        Ok(Self {
            model_name: trimmed.to_string(),
            description: desc,
        })
    }

    pub fn model_name(&self) -> &str {
        &self.model_name
    }

    pub fn description(&self) -> Option<&str> {
        self.description.as_deref()
    }
}

/// A typed IBIS [Model Selector] declaration.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct TypedModelSelectorKeywordsV1 {
    selector_name: String,
    model_options: Vec<ModelOptionEntryV1>,
}

impl TypedModelSelectorKeywordsV1 {
    pub fn try_new(
        selector_name: impl Into<String>,
        model_options: Vec<ModelOptionEntryV1>,
    ) -> Result<Self, ModelSelectorKeywordsErrorV1> {
        let name = selector_name.into();
        let trimmed = name.trim();
        if trimmed.is_empty() {
            return Err(ModelSelectorKeywordsErrorV1::EmptySelectorName);
        }
        if !trimmed.is_ascii() {
            return Err(ModelSelectorKeywordsErrorV1::NonAsciiName);
        }
        if !trimmed
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-' || c == '.')
        {
            return Err(ModelSelectorKeywordsErrorV1::InvalidName);
        }

        if model_options.is_empty() {
            return Err(ModelSelectorKeywordsErrorV1::EmptyModelOptions);
        }

        let mut seen = BTreeSet::new();
        for opt in &model_options {
            let mname = opt.model_name().to_string();
            if !seen.insert(mname.clone()) {
                return Err(ModelSelectorKeywordsErrorV1::DuplicateModelOption(mname));
            }
        }

        Ok(Self {
            selector_name: trimmed.to_string(),
            model_options,
        })
    }

    pub fn selector_name(&self) -> &str {
        &self.selector_name
    }

    pub fn model_options(&self) -> &[ModelOptionEntryV1] {
        &self.model_options
    }
}

/// Lift one model selector keywords declaration.
pub fn lift_model_selector_keywords_v1(
    selector_name: &str,
    model_options: Vec<ModelOptionEntryV1>,
) -> Result<TypedModelSelectorKeywordsV1, ModelSelectorKeywordsErrorV1> {
    TypedModelSelectorKeywordsV1::try_new(selector_name, model_options)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn policy_fixed() {
        assert_eq!(
            MODEL_SELECTOR_KEYWORDS_POLICY_V1,
            "sipi.p4a-03ad.model-selector-keywords-v1.typed-selector-keywords"
        );
    }

    #[test]
    fn valid_model_selector_declaration() {
        let opt1 = ModelOptionEntryV1::try_new("MODE_50OHM", Some("50 Ohm Driver")).unwrap();
        let opt2 = ModelOptionEntryV1::try_new("MODE_40OHM", Some("40 Ohm Driver")).unwrap();
        let sel = lift_model_selector_keywords_v1("SEL_DRV_IMP", vec![opt1, opt2]).expect("lift");
        assert_eq!(sel.selector_name(), "SEL_DRV_IMP");
        assert_eq!(sel.model_options().len(), 2);
    }

    #[test]
    fn rejects_empty_selector_name() {
        let opt1 = ModelOptionEntryV1::try_new("MODE_50OHM", None).unwrap();
        assert_eq!(
            lift_model_selector_keywords_v1("", vec![opt1]),
            Err(ModelSelectorKeywordsErrorV1::EmptySelectorName)
        );
    }

    #[test]
    fn rejects_empty_model_options() {
        assert_eq!(
            lift_model_selector_keywords_v1("SEL_1", vec![]),
            Err(ModelSelectorKeywordsErrorV1::EmptyModelOptions)
        );
    }

    #[test]
    fn rejects_duplicate_model_option() {
        let opt1 = ModelOptionEntryV1::try_new("MODE_50OHM", None).unwrap();
        let opt2 = ModelOptionEntryV1::try_new("MODE_50OHM", None).unwrap();
        assert_eq!(
            lift_model_selector_keywords_v1("SEL_1", vec![opt1, opt2]),
            Err(ModelSelectorKeywordsErrorV1::DuplicateModelOption(
                "MODE_50OHM".to_string()
            ))
        );
    }
}
