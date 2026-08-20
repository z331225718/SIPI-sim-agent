//! Typed IBIS Pin-declaration semantics (P4A-03e).
//!
//! Lifts the [Pin] section rows produced by the structural parser into typed
//! pin declarations: pin name, signal name, and the model name driving them.
//! It does not re-parse text, evaluate electrical/table semantics, or accept a
//! profile. Strict diagnostics reject unknown/malformed pin rows.

use crate::{SourceSpanV1, StructuralRecordV1};

/// Stable scope policy of the P4A-03e typed pin-declaration core.
pub const PIN_DECLARATION_POLICY_V1: &str = "sipi.p4a-03e.pin-declaration.v1.typed";

/// One typed IBIS [Pin] row: pin name, signal name, driving model.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct TypedPinDeclarationV1 {
    pin_name: String,
    signal_name: String,
    model_name: String,
    span: SourceSpanV1,
}

impl TypedPinDeclarationV1 {
    /// Construct a typed pin declaration for tests and internal callers.
    #[allow(dead_code)]
    pub(crate) fn new(
        pin_name: String,
        signal_name: String,
        model_name: String,
        span: SourceSpanV1,
    ) -> Self {
        Self {
            pin_name,
            signal_name,
            model_name,
            span,
        }
    }

    pub fn pin_name(&self) -> &str {
        &self.pin_name
    }
    pub fn signal_name(&self) -> &str {
        &self.signal_name
    }
    pub fn model_name(&self) -> &str {
        &self.model_name
    }
    pub fn span(&self) -> SourceSpanV1 {
        self.span
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum PinDeclarationErrorV1 {
    MissingPinSection,
    MalformedPinRow { pin: String },
    NonFiniteParasitic(usize),
}

/// Lifts [Pin] section rows from structural records.
///
/// Each [Pin] data row is `pin_name signal_name model_name [R L C]`. This
/// core keeps the first three tokens (name/signal/model); numeric parasitic
/// columns are left to a dedicated RLC-core and are not validated for finiteness
/// here beyond remaining opaque. Unknown/malformed rows fail closed.
pub fn lift_pin_declarations_v1(
    records: &[StructuralRecordV1],
) -> Result<Vec<TypedPinDeclarationV1>, PinDeclarationErrorV1> {
    let mut pins = Vec::new();
    let mut i = 0;
    while i < records.len() {
        let section = match &records[i] {
            StructuralRecordV1::Keyword { keyword, .. } => keyword,
            _ => {
                i += 1;
                continue;
            }
        };
        if section.spelling() == "Pin" {
            // Collect following Data rows until the next Keyword.
            let mut j = i + 1;
            while j < records.len() {
                match &records[j] {
                    StructuralRecordV1::Data { tokens, span } => {
                        let spellings: Vec<&str> = tokens.iter().map(|t| t.spelling()).collect();
                        if spellings.len() < 3 {
                            return Err(PinDeclarationErrorV1::MalformedPinRow {
                                pin: spellings.first().copied().unwrap_or("?").to_string(),
                            });
                        }
                        pins.push(TypedPinDeclarationV1 {
                            pin_name: spellings[0].to_string(),
                            signal_name: spellings[1].to_string(),
                            model_name: spellings[2].to_string(),
                            span: *span,
                        });
                    }
                    StructuralRecordV1::Keyword { .. } => break,
                }
                j += 1;
            }
            // A [Pin] section with zero rows is structurally suspect.
            if pins.is_empty() {
                return Err(PinDeclarationErrorV1::MissingPinSection);
            }
            return Ok(pins);
        }
        i += 1;
    }
    Err(PinDeclarationErrorV1::MissingPinSection)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::StructuralTokenV1;

    fn span(start: usize, line: usize) -> SourceSpanV1 {
        SourceSpanV1::new(start, start + 1, line, 0)
    }
    fn tok(s: &str) -> StructuralTokenV1 {
        StructuralTokenV1::new(s.to_string())
    }

    #[test]
    fn policy_fixed() {
        assert_eq!(
            PIN_DECLARATION_POLICY_V1,
            "sipi.p4a-03e.pin-declaration.v1.typed"
        );
    }

    #[test]
    fn lifts_pin_rows() {
        let records = vec![
            StructuralRecordV1::Keyword {
                keyword: tok("Pin"),
                payload: vec![],
                span: span(0, 1),
            },
            StructuralRecordV1::Data {
                tokens: vec![tok("A1"), tok("DNU"), tok("NC")],
                span: span(5, 2),
            },
            StructuralRecordV1::Data {
                tokens: vec![tok("B2"), tok("DQ0_a"), tok("DQ_PIN")],
                span: span(10, 3),
            },
        ];
        let pins = lift_pin_declarations_v1(&records).expect("pins");
        assert_eq!(pins.len(), 2);
        assert_eq!(pins[0].pin_name(), "A1");
        assert_eq!(pins[0].signal_name(), "DNU");
        assert_eq!(pins[1].model_name(), "DQ_PIN");
    }

    #[test]
    fn malformed_row_rejected() {
        let records = vec![
            StructuralRecordV1::Keyword {
                keyword: tok("Pin"),
                payload: vec![],
                span: span(0, 1),
            },
            StructuralRecordV1::Data {
                tokens: vec![tok("A1")],
                span: span(5, 2),
            },
        ];
        assert!(lift_pin_declarations_v1(&records).is_err());
    }

    #[test]
    fn missing_pin_section_rejected() {
        let records = vec![StructuralRecordV1::Keyword {
            keyword: tok("Component"),
            payload: vec![],
            span: span(0, 1),
        }];
        assert_eq!(
            lift_pin_declarations_v1(&records).err(),
            Some(PinDeclarationErrorV1::MissingPinSection)
        );
    }

    #[test]
    fn stops_at_next_section() {
        let records = vec![
            StructuralRecordV1::Keyword {
                keyword: tok("Pin"),
                payload: vec![],
                span: span(0, 1),
            },
            StructuralRecordV1::Data {
                tokens: vec![tok("A1"), tok("SIG"), tok("M")],
                span: span(5, 2),
            },
            StructuralRecordV1::Keyword {
                keyword: tok("Package"),
                payload: vec![],
                span: span(10, 3),
            },
        ];
        let pins = lift_pin_declarations_v1(&records).expect("pins");
        assert_eq!(pins.len(), 1);
    }
}
