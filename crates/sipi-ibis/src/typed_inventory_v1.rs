//! Bounded typed IBIS inventory consumer (P4A-03).
//!
//! This module is the first product-owned consumer that wires the existing
//! structural parser, semantic envelope, typed model/pin/selector
//! declarations, and caller-owned pin-reference policy together.  It
//! deliberately stops at declaration/linkage facts: it does not select a
//! model branch or corner, and it does not infer supply, reference node,
//! electrical profile, transient method, or AMI runtime.

use std::{collections::BTreeSet, error::Error, fmt};

use crate::{
    IbisDiagnosticV1, IbisSemanticDiagnosticV1, ModelBranchV1, ModelDeclarationErrorV1,
    ModelSelectorDeclarationErrorV1, ParseLimitsV1, PinDeclarationErrorV1, StructuralRecordV1,
    TypedModelDeclarationV1, TypedModelSelectorDeclarationV1, TypedPinDeclarationV1,
    build_semantic_envelope_v1, hex_sha256, lift_model_declarations_v1,
    lift_model_selector_declaration_v1, lift_pin_declarations_v1, parse_structural_v1,
};

/// Stable scope policy for the integrated declaration/linkage consumer.
pub const IBIS_TYPED_INVENTORY_POLICY_V1: &str =
    "sipi.p4a-03.typed-inventory-consumer.v1.declaration-linkage-only";

/// Fail-closed error from one bounded typed inventory pass.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum IbisTypedInventoryErrorV1 {
    Structural(IbisDiagnosticV1),
    Semantic(IbisSemanticDiagnosticV1),
    Model(ModelDeclarationErrorV1),
    Pin(PinDeclarationErrorV1),
    Selector(ModelSelectorDeclarationErrorV1),
    MissingEnd,
    DuplicateEnd,
    InvalidEnd,
    TrailingRecordAfterEnd,
    SelectorMissingName,
    SelectorMissingBranches {
        selector: String,
    },
    SelectorBranchUnknown {
        selector: String,
        model: String,
    },
    UnresolvedPinReference {
        pin: String,
        reference: String,
    },
    EnvelopeModelCountMismatch {
        envelope_count: usize,
        typed_count: usize,
    },
    EnvelopeModelNameMismatch {
        index: usize,
        envelope_name: String,
        typed_name: String,
    },
}

impl fmt::Display for IbisTypedInventoryErrorV1 {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Structural(error) => error.fmt(formatter),
            Self::Semantic(error) => error.fmt(formatter),
            Self::Model(error) => write!(formatter, "IBIS typed model inventory: {error:?}"),
            Self::Pin(error) => write!(formatter, "IBIS typed pin inventory: {error:?}"),
            Self::Selector(error) => write!(formatter, "IBIS model selector: {error:?}"),
            Self::MissingEnd => write!(formatter, "IBIS document is missing its final [End]"),
            Self::DuplicateEnd => write!(formatter, "IBIS document contains more than one [End]"),
            Self::InvalidEnd => write!(formatter, "IBIS [End] must not have a payload"),
            Self::TrailingRecordAfterEnd => {
                write!(formatter, "IBIS document contains a record after [End]")
            }
            Self::SelectorMissingName => write!(formatter, "IBIS model selector name is missing"),
            Self::SelectorMissingBranches { selector } => {
                write!(formatter, "IBIS model selector has no branches: {selector}")
            }
            Self::SelectorBranchUnknown { selector, model } => write!(
                formatter,
                "IBIS model selector branch is not a declared model: selector={selector}, model={model}"
            ),
            Self::UnresolvedPinReference { pin, reference } => write!(
                formatter,
                "IBIS pin reference is neither a model, selector, nor caller marker: pin={pin}, reference={reference}"
            ),
            Self::EnvelopeModelCountMismatch {
                envelope_count,
                typed_count,
            } => write!(
                formatter,
                "IBIS model declaration count mismatch: envelope={envelope_count}, typed={typed_count}"
            ),
            Self::EnvelopeModelNameMismatch {
                index,
                envelope_name,
                typed_name,
            } => write!(
                formatter,
                "IBIS model declaration name mismatch at index {index}: envelope={envelope_name}, typed={typed_name}"
            ),
        }
    }
}

impl Error for IbisTypedInventoryErrorV1 {}

/// Product-owned result of one structural-to-typed declaration pass.
#[derive(Clone, Debug, PartialEq)]
pub struct IbisTypedInventoryReportV1 {
    input_byte_length: usize,
    input_sha256: String,
    declared_version: String,
    component_names: Vec<String>,
    models: Vec<TypedModelDeclarationV1>,
    selectors: Vec<TypedModelSelectorDeclarationV1>,
    pins: Vec<TypedPinDeclarationV1>,
    linkage: IbisPinReferenceLinkageV1,
}

impl IbisTypedInventoryReportV1 {
    pub const fn input_byte_length(&self) -> usize {
        self.input_byte_length
    }

    pub fn input_sha256(&self) -> &str {
        &self.input_sha256
    }

    pub fn declared_version(&self) -> &str {
        &self.declared_version
    }

    pub fn component_names(&self) -> &[String] {
        &self.component_names
    }

    pub fn models(&self) -> &[TypedModelDeclarationV1] {
        &self.models
    }

    pub fn selectors(&self) -> &[TypedModelSelectorDeclarationV1] {
        &self.selectors
    }

    pub fn pins(&self) -> &[TypedPinDeclarationV1] {
        &self.pins
    }

    pub const fn linkage(&self) -> &IbisPinReferenceLinkageV1 {
        &self.linkage
    }

    /// This route only reports syntax/declaration/linkage facts.
    pub const fn electrical_behavior_status(&self) -> &'static str {
        "not_evaluated"
    }

    /// No model, corner, reference node, or external profile is selected.
    pub const fn profile_selection_status(&self) -> &'static str {
        "not_selected"
    }
}

/// One bounded pass over caller-provided ASCII bytes.
pub struct IbisTypedInventoryServiceV1;

/// Successful classification of every pin's third column.
///
/// A selector reference is intentionally not resolved to one branch.  The
/// caller must make that later decision with a separate explicit profile.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct IbisPinReferenceLinkageV1 {
    direct_models: Vec<String>,
    selectors: Vec<String>,
    markers: Vec<String>,
}

impl IbisPinReferenceLinkageV1 {
    pub fn direct_models(&self) -> &[String] {
        &self.direct_models
    }

    pub fn selectors(&self) -> &[String] {
        &self.selectors
    }

    pub fn markers(&self) -> &[String] {
        &self.markers
    }

    pub const fn direct_model_count(&self) -> usize {
        self.direct_models.len()
    }

    pub const fn selector_count(&self) -> usize {
        self.selectors.len()
    }

    pub const fn marker_count(&self) -> usize {
        self.markers.len()
    }
}

impl IbisTypedInventoryServiceV1 {
    /// Parse, envelope, lift, and link declarations without reading a file.
    ///
    /// `allowed_markers` is intentionally caller-owned.  The service never
    /// invents a no-connect/power/ground marker set for an input asset.
    pub fn inspect(
        bytes: &[u8],
        limits: ParseLimitsV1,
        allowed_markers: &BTreeSet<String>,
    ) -> Result<IbisTypedInventoryReportV1, IbisTypedInventoryErrorV1> {
        let structural =
            parse_structural_v1(bytes, limits).map_err(IbisTypedInventoryErrorV1::Structural)?;
        require_final_end(structural.records())?;
        let envelope =
            build_semantic_envelope_v1(&structural).map_err(IbisTypedInventoryErrorV1::Semantic)?;
        let models = lift_model_declarations_v1(structural.records())
            .map_err(IbisTypedInventoryErrorV1::Model)?;
        if envelope.models().len() != models.len() {
            return Err(IbisTypedInventoryErrorV1::EnvelopeModelCountMismatch {
                envelope_count: envelope.models().len(),
                typed_count: models.len(),
            });
        }
        for (index, (envelope_model, typed_model)) in
            envelope.models().iter().zip(models.iter()).enumerate()
        {
            let envelope_name = envelope_model.name().spelling();
            let typed_name = typed_model.model_name();
            if envelope_name != typed_name {
                return Err(IbisTypedInventoryErrorV1::EnvelopeModelNameMismatch {
                    index,
                    envelope_name: envelope_name.to_owned(),
                    typed_name: typed_name.to_owned(),
                });
            }
        }
        let selectors = lift_model_selectors(structural.records(), &models)?;
        let pins = lift_pin_declarations_v1(structural.records())
            .map_err(IbisTypedInventoryErrorV1::Pin)?;
        let linkage = classify_pin_references(&pins, &models, &selectors, allowed_markers)?;

        Ok(IbisTypedInventoryReportV1 {
            input_byte_length: bytes.len(),
            input_sha256: hex_sha256(bytes),
            declared_version: envelope.version().spelling().to_owned(),
            component_names: envelope
                .components()
                .iter()
                .map(|component| component.name().spelling().to_owned())
                .collect(),
            models,
            selectors,
            pins,
            linkage,
        })
    }
}

fn require_final_end(records: &[StructuralRecordV1]) -> Result<(), IbisTypedInventoryErrorV1> {
    let ends: Vec<(usize, bool)> = records
        .iter()
        .enumerate()
        .filter_map(|(index, record)| match record {
            StructuralRecordV1::Keyword {
                keyword, payload, ..
            } if keyword.spelling().eq_ignore_ascii_case("End") => {
                Some((index, payload.is_empty()))
            }
            _ => None,
        })
        .collect();
    let [(index, empty)] = ends.as_slice() else {
        return Err(if ends.is_empty() {
            IbisTypedInventoryErrorV1::MissingEnd
        } else {
            IbisTypedInventoryErrorV1::DuplicateEnd
        });
    };
    if !empty {
        return Err(IbisTypedInventoryErrorV1::InvalidEnd);
    }
    if *index + 1 != records.len() {
        return Err(IbisTypedInventoryErrorV1::TrailingRecordAfterEnd);
    }
    Ok(())
}

fn lift_model_selectors(
    records: &[StructuralRecordV1],
    models: &[TypedModelDeclarationV1],
) -> Result<Vec<TypedModelSelectorDeclarationV1>, IbisTypedInventoryErrorV1> {
    let model_names: BTreeSet<&str> = models.iter().map(|model| model.model_name()).collect();
    let mut selectors = Vec::new();
    let mut seen = BTreeSet::new();
    let mut index = 0;
    while index < records.len() {
        let StructuralRecordV1::Keyword {
            keyword, payload, ..
        } = &records[index]
        else {
            index += 1;
            continue;
        };
        if !keyword.spelling().eq_ignore_ascii_case("Model Selector") {
            index += 1;
            continue;
        }
        let Some(selector_name) = payload.first().map(|token| token.spelling().to_owned()) else {
            return Err(IbisTypedInventoryErrorV1::SelectorMissingName);
        };
        if payload.len() != 1 {
            return Err(IbisTypedInventoryErrorV1::SelectorMissingName);
        }
        if !seen.insert(selector_name.clone()) {
            return Err(IbisTypedInventoryErrorV1::Selector(
                ModelSelectorDeclarationErrorV1::InvalidName,
            ));
        }
        let mut branches = Vec::new();
        let mut next = index + 1;
        while next < records.len() {
            match &records[next] {
                StructuralRecordV1::Keyword { .. } => break,
                StructuralRecordV1::Data { tokens, .. } => {
                    let Some(model_name) = tokens.first().map(|token| token.spelling()) else {
                        return Err(IbisTypedInventoryErrorV1::SelectorMissingBranches {
                            selector: selector_name.clone(),
                        });
                    };
                    if !model_names.contains(model_name) {
                        return Err(IbisTypedInventoryErrorV1::SelectorBranchUnknown {
                            selector: selector_name.clone(),
                            model: model_name.to_owned(),
                        });
                    }
                    let description = (tokens.len() > 1).then(|| {
                        tokens
                            .iter()
                            .skip(1)
                            .map(|token| token.spelling())
                            .collect::<Vec<_>>()
                            .join(" ")
                    });
                    branches.push(ModelBranchV1::new(model_name, description));
                }
            }
            next += 1;
        }
        if branches.is_empty() {
            return Err(IbisTypedInventoryErrorV1::SelectorMissingBranches {
                selector: selector_name,
            });
        }
        selectors.push(
            lift_model_selector_declaration_v1(payload[0].spelling(), branches)
                .map_err(IbisTypedInventoryErrorV1::Selector)?,
        );
        index = next;
    }
    Ok(selectors)
}

fn classify_pin_references(
    pins: &[TypedPinDeclarationV1],
    models: &[TypedModelDeclarationV1],
    selectors: &[TypedModelSelectorDeclarationV1],
    allowed_markers: &BTreeSet<String>,
) -> Result<IbisPinReferenceLinkageV1, IbisTypedInventoryErrorV1> {
    if pins.is_empty() {
        return Err(IbisTypedInventoryErrorV1::Pin(
            PinDeclarationErrorV1::MissingPinSection,
        ));
    }
    let model_names: BTreeSet<&str> = models.iter().map(|model| model.model_name()).collect();
    let selector_names: BTreeSet<&str> = selectors
        .iter()
        .map(|selector| selector.selector_name())
        .collect();
    let mut direct_models = Vec::new();
    let mut selector_refs = Vec::new();
    let mut markers = Vec::new();
    for pin in pins {
        let reference = pin.model_name();
        if model_names.contains(reference) {
            direct_models.push(reference.to_owned());
        } else if selector_names.contains(reference) {
            selector_refs.push(reference.to_owned());
        } else if allowed_markers.contains(reference) {
            markers.push(reference.to_owned());
        } else {
            return Err(IbisTypedInventoryErrorV1::UnresolvedPinReference {
                pin: pin.pin_name().to_owned(),
                reference: reference.to_owned(),
            });
        }
    }
    Ok(IbisPinReferenceLinkageV1 {
        direct_models,
        selectors: selector_refs,
        markers,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn limits() -> ParseLimitsV1 {
        ParseLimitsV1::try_new(16 * 1024, 1024, 256, 512).expect("limits")
    }

    fn markers(values: &[&str]) -> BTreeSet<String> {
        values.iter().map(|value| (*value).to_owned()).collect()
    }

    fn source() -> &'static [u8] {
        br#"[IBIS Ver] 5.0
[Component] board
[Pin] signal_name model_name R_pin L_pin C_pin
A1 SIG M_INPUT
A2 NC NC
[Model] M_INPUT
Model_type Input
[GND Clamp]
0V 0A
[Model] M_OUTPUT
Model_type Output
[Pullup]
0V 0A
[Pulldown]
0V 0A
[End]
"#
    }

    #[test]
    fn integrates_structural_envelope_typed_declarations_and_explicit_marker_policy() {
        let report = IbisTypedInventoryServiceV1::inspect(source(), limits(), &markers(&["NC"]))
            .expect("typed inventory");

        assert_eq!(report.declared_version(), "5.0");
        assert_eq!(report.component_names(), &["board".to_owned()]);
        assert_eq!(report.models().len(), 2);
        assert_eq!(report.models()[0].model_name(), "M_INPUT");
        assert_eq!(report.pins().len(), 2);
        assert_eq!(report.linkage().direct_model_count(), 1);
        assert_eq!(report.linkage().markers(), &["NC"]);
        assert_eq!(report.electrical_behavior_status(), "not_evaluated");
        assert_eq!(report.profile_selection_status(), "not_selected");
    }

    #[test]
    fn never_invents_marker_policy_for_unresolved_pin_models() {
        let error = IbisTypedInventoryServiceV1::inspect(source(), limits(), &BTreeSet::new())
            .expect_err("missing marker must reject");
        assert!(matches!(
            error,
            IbisTypedInventoryErrorV1::UnresolvedPinReference { pin, reference }
                if pin == "A2" && reference == "NC"
        ));
    }

    #[test]
    fn rejects_missing_typed_model_type_before_linkage() {
        let source = b"[IBIS Ver] 5.0\n[Component] board\n[Pin]\nA1 SIG M\n[Model] M\n[End]\n";
        let error = IbisTypedInventoryServiceV1::inspect(source, limits(), &BTreeSet::new())
            .expect_err("missing model type must reject");
        assert!(matches!(
            error,
            IbisTypedInventoryErrorV1::Model(ModelDeclarationErrorV1::MissingModelType)
        ));
    }

    #[test]
    fn rejects_non_structural_input_before_allocating_typed_result() {
        let error =
            IbisTypedInventoryServiceV1::inspect(b"[IBIS Ver] 5.0\n\0", limits(), &BTreeSet::new())
                .expect_err("NUL must reject");
        assert!(matches!(
            error,
            IbisTypedInventoryErrorV1::Structural(IbisDiagnosticV1 { .. })
        ));
    }

    #[test]
    fn selected_asset_rejects_at_complete_document_boundary() {
        let bytes = include_bytes!("../../../fixtures/ibis/as4c512m16md4v-053bin.ibs");
        let limits =
            ParseLimitsV1::try_new(8 * 1024 * 1024, 4 * 1024 * 1024, 128 * 1024, 256 * 1024)
                .expect("limits");
        let error =
            IbisTypedInventoryServiceV1::inspect(bytes, limits, &markers(&["GND", "NC", "POWER"]))
                .expect_err("the selected asset is a truncated document prefix");
        assert_eq!(error, IbisTypedInventoryErrorV1::MissingEnd);
    }

    #[test]
    fn rejects_duplicate_end_markers() {
        let mut bytes = source().to_vec();
        bytes.extend_from_slice(b"[End]\n");
        assert_eq!(
            IbisTypedInventoryServiceV1::inspect(&bytes, limits(), &markers(&["NC"]))
                .expect_err("duplicate End must reject"),
            IbisTypedInventoryErrorV1::DuplicateEnd
        );
    }

    #[test]
    fn rejects_end_payload() {
        let mut bytes = source()[..source().len() - b"[End]\n".len()].to_vec();
        bytes.extend_from_slice(b"[End] payload\n");
        assert_eq!(
            IbisTypedInventoryServiceV1::inspect(&bytes, limits(), &markers(&["NC"]))
                .expect_err("End payload must reject"),
            IbisTypedInventoryErrorV1::InvalidEnd
        );
    }

    #[test]
    fn rejects_record_after_end() {
        let mut bytes = source().to_vec();
        bytes.extend_from_slice(b"trailing\n");
        assert_eq!(
            IbisTypedInventoryServiceV1::inspect(&bytes, limits(), &markers(&["NC"]))
                .expect_err("record after End must reject"),
            IbisTypedInventoryErrorV1::TrailingRecordAfterEnd
        );
    }
}
