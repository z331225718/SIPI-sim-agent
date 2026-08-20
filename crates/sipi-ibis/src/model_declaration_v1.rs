//! Typed IBIS Model-declaration semantics (P4A-03d).
//!
//! Lifts the structural [Model] blocks produced by the structural
//! parser (IbisDocumentV1) into typed model declarations: model name,
//! IBIS Model_type, and optional Voltage Range / Temperature Range.
//! It does not re-parse text, does not evaluate electrical / table
//! semantics, and does not accept or imply a profile. Strict
//! diagnostics reject unknown Model_type, duplicate or missing
//! declarations per the typed surface.

use crate::{SourceSpanV1, StructuralRecordV1};

/// One typed IBIS Model declaration lifted from structural records.
#[derive(Clone, Debug, PartialEq)]
pub struct TypedModelDeclarationV1 {
    model_name: String,
    model_type: ModelTypeV1,
    voltage_range_v: Option<f64>,
    temperature_range_c: Option<f64>,
    span: SourceSpanV1,
}

impl TypedModelDeclarationV1 {
    /// Construct a typed model declaration for tests and internal callers.
    #[allow(dead_code)]
    pub(crate) fn new(model_name: String, span: SourceSpanV1) -> Self {
        Self {
            model_name,
            model_type: crate::model_declaration_v1::ModelTypeV1::Other(String::new()),
            voltage_range_v: None,
            temperature_range_c: None,
            span,
        }
    }

    pub fn model_name(&self) -> &str {
        &self.model_name
    }

    pub fn model_type(&self) -> &ModelTypeV1 {
        &self.model_type
    }

    pub const fn voltage_range_v(&self) -> Option<f64> {
        self.voltage_range_v
    }

    pub const fn temperature_range_c(&self) -> Option<f64> {
        self.temperature_range_c
    }

    pub const fn span(&self) -> SourceSpanV1 {
        self.span
    }
}

/// IBIS Model_type (IBIS 5.0 spec section 4, bounded set).
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ModelTypeV1 {
    Input,
    Output,
    IO,
    ThreeState,
    OpenDrain,
    OpenSink,
    OpenSource,
    InputEcl,
    OutputEcl,
    IOEcl,
    Terminator,
    Series,
    SeriesSwitch,
    Other(String),
}

impl ModelTypeV1 {
    fn parse(spelling: &str) -> Option<Self> {
        let lower = spelling.to_ascii_lowercase().replace('_', "-");
        match lower.as_str() {
            "input" => Some(Self::Input),
            "output" => Some(Self::Output),
            "i/o" | "io" => Some(Self::IO),
            "3-state" | "3state" => Some(Self::ThreeState),
            "open-drain" | "opendrain" => Some(Self::OpenDrain),
            "open-sink" | "opensink" => Some(Self::OpenSink),
            "open-source" | "opensource" => Some(Self::OpenSource),
            "input-ecl" | "inputecl" => Some(Self::InputEcl),
            "output-ecl" | "outputecl" => Some(Self::OutputEcl),
            "i/o-ecl" | "ioecl" => Some(Self::IOEcl),
            "terminator" => Some(Self::Terminator),
            "series" => Some(Self::Series),
            "series-switch" | "seriesswitch" => Some(Self::SeriesSwitch),
            _ => None,
        }
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ModelDeclarationErrorV1 {
    UnexpectedRecordShape,
    MissingModelType,
    UnknownModelType(String),
    DuplicateModel(String),
    MissingModelName,
    NonFiniteRange,
}

impl std::fmt::Display for ModelDeclarationErrorV1 {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{self:?}")
    }
}

/// Try to read a leading finite number from a keyword payload; returns
/// None for non-parsable payloads (range/unit-aware semantics deferred to the
/// P4A-04 layer, so this slice does not reject on them).
fn leading_finite(payload: &[crate::StructuralTokenV1]) -> Option<f64> {
    let first = payload.first()?;
    let spelling = first.spelling();
    // Tolerate a trailing unit suffix like "V" on the leading token of a range.
    let numeric = spelling
        .strip_suffix('V')
        .or_else(|| spelling.strip_suffix('v'))
        .unwrap_or(spelling);
    let value: f64 = numeric.trim().parse().ok()?;
    if value.is_finite() {
        Some(value)
    } else {
        None
    }
}

/// Lift [Model] declaration blocks out of structural records.
///
/// Iterates the top-level records; a [Model] keyword starts a block,
/// and the following Model_type / Voltage Range / Temperature Range
/// keyword records (until the next top-level keyword) fill it. Unknown
/// keywords inside the block are ignored (left structural).
pub fn lift_model_declarations_v1(
    records: &[StructuralRecordV1],
) -> Result<Vec<TypedModelDeclarationV1>, ModelDeclarationErrorV1> {
    let mut declarations: Vec<TypedModelDeclarationV1> = Vec::new();
    let mut i = 0;
    let mut seen = std::collections::HashMap::new();
    while i < records.len() {
        if let StructuralRecordV1::Keyword { keyword, payload: _payload, span } = &records[i] {
            if keyword.spelling() == "Model" {
                // Model name is the first payload token.
                let name = match _payload.first() {
                    Some(tok) => tok.spelling().to_string(),
                    None => return Err(ModelDeclarationErrorV1::MissingModelName),
                };
                if seen.contains_key(&name) {
                    return Err(ModelDeclarationErrorV1::DuplicateModel(name));
                }
                seen.insert(name.clone(), ());

                // Collect typed fields until the next top-level [Keyword].
                let mut model_type = None;
                let mut voltage_range_v = None;
                let mut temperature_range_c = None;
                let mut j = i + 1;
                while j < records.len() {
                    match &records[j] {
                        StructuralRecordV1::Keyword { keyword: k, payload: p, .. } => {
                            let spelling = k.spelling();
                            if spelling == "Model" {
                                break; // next model block
                            }
                            match spelling {
                                "Model_type" | "Model Type" => {
                                    let value = p.first().map(|t| t.spelling().to_string())
                                        .ok_or(ModelDeclarationErrorV1::MissingModelType)?;
                                    let mt = ModelTypeV1::parse(&value)
                                        .ok_or_else(|| ModelDeclarationErrorV1::UnknownModelType(value.clone()))?;
                                    model_type = Some(mt);
                                }
                                "Voltage Range" => {
                                    voltage_range_v = leading_finite(p);
                                }
                                "Temperature Range" => {
                                    temperature_range_c = leading_finite(p);
                                }
                                _ => {} // other keyword: left structural
                            }
                        }
                        StructuralRecordV1::Data { tokens, .. } => {
                            // In IBIS files Model_type is a bare keyword-value
                            // line (e.g. "Model_type  Input"), which the
                            // structural parser emits as a Data record.
                            if let Some(first) = tokens.first() {
                                if first.spelling() == "Model_type"
                                    || first.spelling() == "Model Type"
                                {
                                    let typ = tokens
                                        .get(1)
                                        .map(|t| t.spelling().to_string())
                                        .ok_or(ModelDeclarationErrorV1::MissingModelType)?;
                                    let mt = ModelTypeV1::parse(&typ)
                                        .ok_or_else(|| ModelDeclarationErrorV1::UnknownModelType(typ.clone()))?;
                                    model_type = Some(mt);
                                }
                            }
                        }
                    }
                    j += 1;
                }

                let mt = model_type.ok_or(ModelDeclarationErrorV1::MissingModelType)?;
                declarations.push(TypedModelDeclarationV1 {
                    model_name: name,
                    model_type: mt,
                    voltage_range_v,
                    temperature_range_c,
                    span: *span,
                });
                i = j;
                continue;
            }
        }
        i += 1;
    }
    Ok(declarations)
}

/// Stable scope policy of the P4A-03d typed model-declaration core.
pub const MODEL_DECLARATION_POLICY_V1: &str =
    "sipi.p4a-03d.model-declaration.v1.typed-declaration-only";

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{SourceSpanV1, StructuralTokenV1, StructuralRecordV1};

    fn span(start: usize, line: usize) -> SourceSpanV1 {
        SourceSpanV1::new(start, start + 1, line, 0)
    }

    fn tok(spelling: &str) -> StructuralTokenV1 {
        StructuralTokenV1::new(spelling.to_string())
    }

    #[test]
    fn policy_fixed() {
        assert_eq!(MODEL_DECLARATION_POLICY_V1, "sipi.p4a-03d.model-declaration.v1.typed-declaration-only");
    }

    #[test]
    fn lifts_output_model_typed() {
        let records = vec![
            StructuralRecordV1::Keyword { keyword: tok("Model"), payload: vec![tok("pcie_tx")], span: span(0, 1) },
            StructuralRecordV1::Keyword { keyword: tok("Model_type"), payload: vec![tok("Output")], span: span(5, 2) },
        ];
        let decls = lift_model_declarations_v1(&records).expect("lift");
        assert_eq!(decls.len(), 1);
        assert_eq!(decls[0].model_name(), "pcie_tx");
        assert_eq!(decls[0].model_type(), &ModelTypeV1::Output);
    }

    #[test]
    fn parses_io_and_ecl_types() {
        assert_eq!(ModelTypeV1::parse("I/O"), Some(ModelTypeV1::IO));
        assert_eq!(ModelTypeV1::parse("3-state"), Some(ModelTypeV1::ThreeState));
        assert_eq!(ModelTypeV1::parse("Input_ECL"), Some(ModelTypeV1::InputEcl));
    }

    #[test]
    fn captures_voltage_temperature_ranges() {
        let records = vec![
            StructuralRecordV1::Keyword { keyword: tok("Model"), payload: vec![tok("m1")], span: span(0, 1) },
            StructuralRecordV1::Keyword { keyword: tok("Model_type"), payload: vec![tok("Input")], span: span(5, 2) },
            StructuralRecordV1::Keyword { keyword: tok("Voltage Range"), payload: vec![tok("1.1")], span: span(10, 3) },
            StructuralRecordV1::Keyword { keyword: tok("Temperature Range"), payload: vec![tok("85")], span: span(16, 4) },
        ];
        let decls = lift_model_declarations_v1(&records).expect("lift");
        assert_eq!(decls[0].voltage_range_v(), Some(1.1));
        assert_eq!(decls[0].temperature_range_c(), Some(85.0));
    }

    #[test]
    fn rejects_unknown_model_type() {
        let records = vec![
            StructuralRecordV1::Keyword { keyword: tok("Model"), payload: vec![tok("m1")], span: span(0, 1) },
            StructuralRecordV1::Keyword { keyword: tok("Model_type"), payload: vec![tok("Bogus")], span: span(5, 2) },
        ];
        let err = lift_model_declarations_v1(&records).err().expect("err");
        assert!(matches!(err, ModelDeclarationErrorV1::UnknownModelType(_)));
    }

    #[test]
    fn rejects_duplicate_model_name() {
        let records = vec![
            StructuralRecordV1::Keyword { keyword: tok("Model"), payload: vec![tok("m1")], span: span(0, 1) },
            StructuralRecordV1::Keyword { keyword: tok("Model_type"), payload: vec![tok("Output")], span: span(5, 2) },
            StructuralRecordV1::Keyword { keyword: tok("Model"), payload: vec![tok("m1")], span: span(10, 3) },
            StructuralRecordV1::Keyword { keyword: tok("Model_type"), payload: vec![tok("Input")], span: span(15, 4) },
        ];
        let err = lift_model_declarations_v1(&records).err().expect("err");
        assert!(matches!(err, ModelDeclarationErrorV1::DuplicateModel(_)));
    }

    #[test]
    fn rejects_missing_model_type() {
        let records = vec![
            StructuralRecordV1::Keyword { keyword: tok("Model"), payload: vec![tok("m1")], span: span(0, 1) },
        ];
        let err = lift_model_declarations_v1(&records).err().expect("err");
        assert!(matches!(err, ModelDeclarationErrorV1::MissingModelType));
    }

    #[test]
    fn skips_opaque_data_within_block() {
        let records = vec![
            StructuralRecordV1::Keyword { keyword: tok("Model"), payload: vec![tok("m1")], span: span(0, 1) },
            StructuralRecordV1::Data { tokens: vec![tok("0.0"), tok("0.0")], span: span(5, 2) },
            StructuralRecordV1::Keyword { keyword: tok("Model_type"), payload: vec![tok("Output")], span: span(10, 3) },
        ];
        let decls = lift_model_declarations_v1(&records).expect("lift");
        assert_eq!(decls.len(), 1);
        assert_eq!(decls[0].model_type(), &ModelTypeV1::Output);
    }
}