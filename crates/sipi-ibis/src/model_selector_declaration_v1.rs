//! Typed IBIS [Model Selector] & [Series Pin Mapping] core (P4A-03i).
//!
//! Lifts and validates IBIS [Model Selector] branches and [Series Pin Mapping]
//! entries into typed, clean-room structures.
//! Fail-closed: empty names, non-ASCII characters, invalid name spellings,
//! empty branch lists, or identical series pin pairs are strictly rejected.

/// Scope policy for the typed model selector declaration core.
pub const MODEL_SELECTOR_DECLARATION_POLICY_V1: &str =
    "sipi.p4a-03i.model-selector-declaration-v1.typed-selector-series";

/// Fail-closed errors during model selector or series pin mapping lifting.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ModelSelectorDeclarationErrorV1 {
    EmptyName,
    NonAsciiName,
    InvalidName,
    EmptyBranches,
    IdenticalSeriesPins,
}

/// One model choice inside a [Model Selector] block.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ModelBranchV1 {
    model_name: String,
    description: Option<String>,
}

impl ModelBranchV1 {
    pub fn new(model_name: impl Into<String>, description: Option<impl Into<String>>) -> Self {
        Self {
            model_name: model_name.into().trim().to_string(),
            description: description
                .map(|d| d.into().trim().to_string())
                .filter(|d| !d.is_empty()),
        }
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
pub struct TypedModelSelectorDeclarationV1 {
    selector_name: String,
    branches: Vec<ModelBranchV1>,
}

impl TypedModelSelectorDeclarationV1 {
    pub fn try_new(
        selector_name: impl Into<String>,
        branches: Vec<ModelBranchV1>,
    ) -> Result<Self, ModelSelectorDeclarationErrorV1> {
        let name = selector_name.into();
        let trimmed = name.trim();
        if trimmed.is_empty() {
            return Err(ModelSelectorDeclarationErrorV1::EmptyName);
        }
        if !trimmed.is_ascii() {
            return Err(ModelSelectorDeclarationErrorV1::NonAsciiName);
        }
        if !trimmed
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-' || c == '.')
        {
            return Err(ModelSelectorDeclarationErrorV1::InvalidName);
        }
        if branches.is_empty() {
            return Err(ModelSelectorDeclarationErrorV1::EmptyBranches);
        }
        for b in &branches {
            if b.model_name().is_empty() {
                return Err(ModelSelectorDeclarationErrorV1::EmptyName);
            }
            if !b.model_name().is_ascii() {
                return Err(ModelSelectorDeclarationErrorV1::NonAsciiName);
            }
        }
        Ok(Self {
            selector_name: trimmed.to_string(),
            branches,
        })
    }

    pub fn selector_name(&self) -> &str {
        &self.selector_name
    }

    pub fn branches(&self) -> &[ModelBranchV1] {
        &self.branches
    }
}

/// A typed IBIS [Series Pin Mapping] entry.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct TypedSeriesPinMappingV1 {
    pin_first: String,
    pin_second: String,
    model_name: String,
}

impl TypedSeriesPinMappingV1 {
    pub fn try_new(
        pin_first: impl Into<String>,
        pin_second: impl Into<String>,
        model_name: impl Into<String>,
    ) -> Result<Self, ModelSelectorDeclarationErrorV1> {
        let pf = pin_first.into().trim().to_string();
        let ps = pin_second.into().trim().to_string();
        let mn = model_name.into().trim().to_string();

        if pf.is_empty() || ps.is_empty() || mn.is_empty() {
            return Err(ModelSelectorDeclarationErrorV1::EmptyName);
        }
        if !pf.is_ascii() || !ps.is_ascii() || !mn.is_ascii() {
            return Err(ModelSelectorDeclarationErrorV1::NonAsciiName);
        }
        if pf == ps {
            return Err(ModelSelectorDeclarationErrorV1::IdenticalSeriesPins);
        }
        Ok(Self {
            pin_first: pf,
            pin_second: ps,
            model_name: mn,
        })
    }

    pub fn pin_first(&self) -> &str {
        &self.pin_first
    }

    pub fn pin_second(&self) -> &str {
        &self.pin_second
    }

    pub fn model_name(&self) -> &str {
        &self.model_name
    }
}

/// Lift one model selector declaration.
pub fn lift_model_selector_declaration_v1(
    selector_name: &str,
    branches: Vec<ModelBranchV1>,
) -> Result<TypedModelSelectorDeclarationV1, ModelSelectorDeclarationErrorV1> {
    TypedModelSelectorDeclarationV1::try_new(selector_name, branches)
}

/// Lift one series pin mapping.
pub fn lift_series_pin_mapping_v1(
    pin_first: &str,
    pin_second: &str,
    model_name: &str,
) -> Result<TypedSeriesPinMappingV1, ModelSelectorDeclarationErrorV1> {
    TypedSeriesPinMappingV1::try_new(pin_first, pin_second, model_name)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn policy_fixed() {
        assert_eq!(
            MODEL_SELECTOR_DECLARATION_POLICY_V1,
            "sipi.p4a-03i.model-selector-declaration-v1.typed-selector-series"
        );
    }

    #[test]
    fn valid_model_selector() {
        let b1 = ModelBranchV1::new("MODE_FAST", Some("Fast corner model"));
        let b2 = ModelBranchV1::new("MODE_SLOW", Some("Slow corner model"));
        let sel = lift_model_selector_declaration_v1("SPEED_SEL", vec![b1, b2]).expect("lift");
        assert_eq!(sel.selector_name(), "SPEED_SEL");
        assert_eq!(sel.branches().len(), 2);
        assert_eq!(sel.branches()[0].model_name(), "MODE_FAST");
        assert_eq!(sel.branches()[0].description(), Some("Fast corner model"));
    }

    #[test]
    fn valid_series_pin_mapping() {
        let mapping = lift_series_pin_mapping_v1("A1", "A2", "R_SERIES_50").expect("lift");
        assert_eq!(mapping.pin_first(), "A1");
        assert_eq!(mapping.pin_second(), "A2");
        assert_eq!(mapping.model_name(), "R_SERIES_50");
    }

    #[test]
    fn rejects_empty_selector_name() {
        let b1: ModelBranchV1 = ModelBranchV1::new("MODE_FAST", None::<&str>);
        assert_eq!(
            lift_model_selector_declaration_v1("", vec![b1]),
            Err(ModelSelectorDeclarationErrorV1::EmptyName)
        );
    }

    #[test]
    fn rejects_empty_branches() {
        assert_eq!(
            lift_model_selector_declaration_v1("SEL", vec![]),
            Err(ModelSelectorDeclarationErrorV1::EmptyBranches)
        );
    }

    #[test]
    fn rejects_identical_series_pins() {
        assert_eq!(
            lift_series_pin_mapping_v1("A1", "A1", "R_SERIES"),
            Err(ModelSelectorDeclarationErrorV1::IdenticalSeriesPins)
        );
    }
}
