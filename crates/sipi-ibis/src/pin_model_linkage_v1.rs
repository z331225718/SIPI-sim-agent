//! Typed IBIS pin-to-model linkage resolution core (P4A-03f).
//!
//! Joins the typed pin declarations (P4A-03e) with the typed model
//! declarations (P4A-03d): every pin's driving model name must resolve to a
//! declared model name, or to an explicitly allowed no-model marker supplied
//! by the caller (e.g. "NC" for a no-connect pin in an IBIS file). Any pin
//! whose model name is neither a declared model nor an allowed marker is a
//! hard error: a pin that drives an undeclared model cannot be typed, and
//! silently guessing at a mapping would drift from the input it was handed.
//!
//! This core is deliberately profile-agnostic: it carries no reserved-name
//! catalog, does not select a profile, and does not evaluate electrical,
//! package, or table semantics. The allowed-marker set is caller-supplied;
//! the caller decides what markers are legitimate no-model spellings for
//! their profile.

use crate::model_declaration_v1::TypedModelDeclarationV1;
use crate::pin_declaration_v1::TypedPinDeclarationV1;

/// Stable scope policy of the P4A-03f pin-to-model linkage core.
pub const PIN_MODEL_LINKAGE_POLICY_V1: &str = "sipi.p4a-03f.pin-model-linkage.v1.typed";

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum PinModelLinkageErrorV1 {
    EmptyPins,
    EmptyModels,
    UnresolvedModel { pin: String, model: String },
}

/// The deterministic result of linking pins to declared models.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct PinModelLinkageV1 {
    resolved: Vec<String>,
    marker: Vec<String>,
    unresolved: Vec<(String, String)>,
}

impl PinModelLinkageV1 {
    pub fn resolved(&self) -> &[String] {
        &self.resolved
    }
    pub fn marker(&self) -> &[String] {
        &self.marker
    }
    pub fn unresolved(&self) -> &[(String, String)] {
        &self.unresolved
    }
    pub fn resolved_count(&self) -> usize {
        self.resolved.len()
    }
    pub fn marker_count(&self) -> usize {
        self.marker.len()
    }
    pub fn unresolved_count(&self) -> usize {
        self.unresolved.len()
    }
}

/// Resolves every pin's driving model against the declared model names and
/// the caller-supplied set of allowed no-model markers.
///
/// The resolution order is deterministic: pins are processed in the order
/// they were supplied and the result lists preserve that order. A pin's model
/// name is resolved as a declared model if it exactly matches a declared
/// model name; otherwise it is a marker if it is in the allowed marker set;
/// otherwise the whole call fails closed with the first unresolved pair in
/// pin order.
pub fn resolve_pin_model_linkage_v1(
    pins: &[TypedPinDeclarationV1],
    models: &[TypedModelDeclarationV1],
    allowed_markers: &std::collections::BTreeSet<String>,
) -> Result<PinModelLinkageV1, PinModelLinkageErrorV1> {
    if pins.is_empty() {
        return Err(PinModelLinkageErrorV1::EmptyPins);
    }
    if models.is_empty() {
        return Err(PinModelLinkageErrorV1::EmptyModels);
    }
    let model_names: std::collections::BTreeSet<String> =
        models.iter().map(|m| m.model_name().to_string()).collect();
    let mut resolved = Vec::new();
    let mut marker = Vec::new();
    let mut unresolved = Vec::new();
    for pin in pins {
        let model_name = pin.model_name();
        if model_names.contains(model_name) {
            resolved.push(model_name.to_string());
        } else if allowed_markers.contains(model_name) {
            marker.push(model_name.to_string());
        } else {
            unresolved.push((pin.pin_name().to_string(), model_name.to_string()));
            return Err(PinModelLinkageErrorV1::UnresolvedModel {
                pin: pin.pin_name().to_string(),
                model: model_name.to_string(),
            });
        }
    }
    Ok(PinModelLinkageV1 {
        resolved,
        marker,
        unresolved,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::SourceSpanV1;

    fn span(start: usize, line: usize) -> SourceSpanV1 {
        SourceSpanV1::new(start, start + 1, line, 0)
    }

    fn pin(pin_name: &str, signal: &str, model: &str) -> TypedPinDeclarationV1 {
        TypedPinDeclarationV1::new(
            pin_name.to_string(),
            signal.to_string(),
            model.to_string(),
            span(0, 1),
        )
    }

    fn model(name: &str) -> TypedModelDeclarationV1 {
        TypedModelDeclarationV1::new(name.to_string(), span(0, 1))
    }

    fn markers(items: &[&str]) -> std::collections::BTreeSet<String> {
        items.iter().map(|s| s.to_string()).collect()
    }

    #[test]
    fn policy_fixed() {
        assert_eq!(
            PIN_MODEL_LINKAGE_POLICY_V1,
            "sipi.p4a-03f.pin-model-linkage.v1.typed"
        );
    }

    #[test]
    fn resolves_all_pins_to_declared_models() {
        let pins = vec![
            pin("A1", "DQ0", "DQ_PIN"),
            pin("B2", "DQ1", "DQ_PIN"),
            pin("C3", "CK", "CK_PIN"),
        ];
        let models = vec![model("DQ_PIN"), model("CK_PIN")];
        let result = resolve_pin_model_linkage_v1(&pins, &models, &markers(&[])).expect("ok");
        assert_eq!(result.resolved_count(), 3);
        assert_eq!(result.marker_count(), 0);
        assert_eq!(result.unresolved_count(), 0);
        assert_eq!(result.resolved(), &["DQ_PIN", "DQ_PIN", "CK_PIN"]);
    }

    #[test]
    fn nc_marker_allowed_when_supplied() {
        let pins = vec![pin("A1", "NC", "NC"), pin("B2", "DQ0", "DQ_PIN")];
        let models = vec![model("DQ_PIN")];
        let result = resolve_pin_model_linkage_v1(&pins, &models, &markers(&["NC"])).expect("ok");
        assert_eq!(result.resolved_count(), 1);
        assert_eq!(result.marker_count(), 1);
        assert_eq!(result.marker(), &["NC"]);
    }

    #[test]
    fn nc_is_unresolved_without_allowance() {
        let pins = vec![pin("A1", "NC", "NC"), pin("B2", "DQ0", "DQ_PIN")];
        let models = vec![model("DQ_PIN")];
        let err = resolve_pin_model_linkage_v1(&pins, &models, &markers(&[])).expect_err("err");
        assert!(
            matches!(err, PinModelLinkageErrorV1::UnresolvedModel { pin, model } if pin == "A1" && model == "NC")
        );
    }

    #[test]
    fn unknown_model_rejected_in_pin_order() {
        let pins = vec![
            pin("A1", "DQ0", "DQ_PIN"),
            pin("B2", "DQ1", "MISSING"),
            pin("C3", "DQ2", "DQ_PIN"),
        ];
        let models = vec![model("DQ_PIN")];
        let err = resolve_pin_model_linkage_v1(&pins, &models, &markers(&[])).expect_err("err");
        assert_eq!(
            err,
            PinModelLinkageErrorV1::UnresolvedModel {
                pin: "B2".to_string(),
                model: "MISSING".to_string()
            }
        );
    }

    #[test]
    fn empty_pins_rejected() {
        let models = vec![model("DQ_PIN")];
        assert_eq!(
            resolve_pin_model_linkage_v1(&[], &models, &markers(&[])).err(),
            Some(PinModelLinkageErrorV1::EmptyPins)
        );
    }

    #[test]
    fn empty_models_rejected() {
        let pins = vec![pin("A1", "DQ0", "DQ_PIN")];
        assert_eq!(
            resolve_pin_model_linkage_v1(&pins, &[], &markers(&[])).err(),
            Some(PinModelLinkageErrorV1::EmptyModels)
        );
    }

    #[test]
    fn marker_and_resolved_order_is_deterministic() {
        let pins = vec![
            pin("A1", "NC", "NC"),
            pin("B2", "DQ0", "DQ_PIN"),
            pin("C3", "NC2", "NC"),
        ];
        let models = vec![model("DQ_PIN"), model("OTHER")];
        let result = resolve_pin_model_linkage_v1(&pins, &models, &markers(&["NC"])).expect("ok");
        assert_eq!(result.resolved(), &["DQ_PIN"]);
        assert_eq!(result.marker(), &["NC", "NC"]);
    }
}
