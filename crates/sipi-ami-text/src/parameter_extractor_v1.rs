//! AMI text document parameter extraction core (P4B-02b6).
//!
//! Scans a structural `AmiTextDocumentV1` AST for 3-item list forms
//! `(name, type_token, value_token)` and extracts them into typed
//! `AmiParameterValueV1` objects.
//! Fail-closed: empty documents, duplicate parameter names, or invalid
//! parameter value syntax are strictly rejected.

use std::collections::BTreeMap;

use crate::{
    AmiParameterValueErrorV1, AmiParameterValueV1, AmiTextDocumentV1, AmiTextListV1,
    AmiTextNodeV1,
};

/// Scope policy for the parameter extractor core.
pub const PARAMETER_EXTRACTOR_POLICY_V1: &str =
    "sipi.p4b-02b6.parameter-extractor-v1.ast-triples-to-values";

/// Fail-closed errors during AST parameter extraction.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterExtractorErrorV1 {
    EmptyDocument,
    DuplicateParameter(String),
    InvalidValue(AmiParameterValueErrorV1),
    NoValidParameters,
}

fn item_spelling(node: &AmiTextNodeV1) -> Option<&str> {
    match node {
        AmiTextNodeV1::Atom(token) | AmiTextNodeV1::Quoted(token) => Some(token.spelling()),
        AmiTextNodeV1::List(_) => None,
    }
}

fn scan_list(
    list: &AmiTextListV1,
    map: &mut BTreeMap<String, AmiParameterValueV1>,
) -> Result<(), ParameterExtractorErrorV1> {
    let items = list.items();
    if items.len() == 3 {
        if let (Some(name), Some(ty), Some(val)) = (
            item_spelling(&items[0]),
            item_spelling(&items[1]),
            item_spelling(&items[2]),
        ) {
            if matches!(ty, "Float" | "Integer" | "Boolean" | "String" | "List") {
                let param_val = AmiParameterValueV1::try_new(name, ty, val)
                    .map_err(ParameterExtractorErrorV1::InvalidValue)?;
                if map.insert(param_val.name().to_string(), param_val).is_some() {
                    return Err(ParameterExtractorErrorV1::DuplicateParameter(name.to_string()));
                }
                return Ok(());
            }
        }
    }
    for item in items {
        if let AmiTextNodeV1::List(sub_list) = item {
            scan_list(sub_list, map)?;
        }
    }
    Ok(())
}

/// Extract typed parameter values from an AST document.
pub fn extract_parameter_values_v1(
    document: &AmiTextDocumentV1,
) -> Result<BTreeMap<String, AmiParameterValueV1>, ParameterExtractorErrorV1> {
    if document.forms().is_empty() {
        return Err(ParameterExtractorErrorV1::EmptyDocument);
    }
    let mut map = BTreeMap::new();
    for form in document.forms() {
        scan_list(form, &mut map)?;
    }
    if map.is_empty() {
        return Err(ParameterExtractorErrorV1::NoValidParameters);
    }
    Ok(map)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{parse_ami_text_v1, ParseLimitsV1};

    fn limits() -> ParseLimitsV1 {
        ParseLimitsV1::try_new(1024, 16, 64, 128).unwrap()
    }

    #[test]
    fn policy_fixed() {
        assert_eq!(
            PARAMETER_EXTRACTOR_POLICY_V1,
            "sipi.p4b-02b6.parameter-extractor-v1.ast-triples-to-values"
        );
    }

    #[test]
    fn extracts_valid_parameter_triples() {
        let doc = parse_ami_text_v1(
            b"(root (swing Float 0.5) (tap Integer 2) (flag Boolean True))",
            limits(),
        )
        .expect("parse");
        let map = extract_parameter_values_v1(&doc).expect("extract");
        assert_eq!(map.len(), 3);
        assert_eq!(map.get("swing").unwrap().value_token(), "0.5");
        assert_eq!(map.get("tap").unwrap().value_token(), "2");
        assert_eq!(map.get("flag").unwrap().value_token(), "True");
    }

    #[test]
    fn rejects_empty_document() {
        let doc = AmiTextDocumentV1 { forms: Vec::new() };
        assert_eq!(
            extract_parameter_values_v1(&doc),
            Err(ParameterExtractorErrorV1::EmptyDocument)
        );
    }

    #[test]
    fn rejects_document_with_no_valid_parameter_triples() {
        let doc = parse_ami_text_v1(b"(root (sub a b c d))", limits()).expect("parse");
        assert_eq!(
            extract_parameter_values_v1(&doc),
            Err(ParameterExtractorErrorV1::NoValidParameters)
        );
    }

    #[test]
    fn rejects_duplicate_parameters() {
        let doc = parse_ami_text_v1(
            b"(root (swing Float 0.5) (swing Float 0.9))",
            limits(),
        )
        .expect("parse");
        assert_eq!(
            extract_parameter_values_v1(&doc),
            Err(ParameterExtractorErrorV1::DuplicateParameter(
                "swing".to_string()
            ))
        );
    }

    #[test]
    fn rejects_invalid_value_syntax() {
        let doc = parse_ami_text_v1(b"(root (swing Float invalid_float))", limits()).expect("parse");
        assert!(matches!(
            extract_parameter_values_v1(&doc),
            Err(ParameterExtractorErrorV1::InvalidValue(_))
        ));
    }
}
