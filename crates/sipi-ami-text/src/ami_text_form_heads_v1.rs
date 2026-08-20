//! AMI text document form heads counting core (P4B-02b61).
//!
//! Counts the head spellings of the top-level forms of a parsed
//! `AmiTextDocumentV1` AST: for each form, the first item's spelling (atom or
//! quoted token, raw spelling preserved) is its head; the result maps each
//! distinct head to its occurrence count. This complements the document
//! statistics (P4B-02b51) with the section-name landscape. Fail-closed: an
//! empty document and any form whose first item is not an atom or quoted token
//! (empty form, or a nested list head) are strictly rejected.

use std::collections::BTreeMap;

use crate::{AmiTextDocumentV1, AmiTextNodeV1};

/// Scope policy for the AMI text form heads counting core.
pub const AMI_TEXT_FORM_HEADS_POLICY_V1: &str = "sipi.p4b-02b61.ami-text-form-heads-v1.head-counts";

/// Fail-closed errors during form heads counting.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum AmiTextFormHeadsErrorV1 {
    /// The document carries no forms.
    EmptyDocument,
    /// A form's first item is not an atom or quoted token (empty form, or a
    /// nested list head), so no head spelling exists.
    InvalidFormHead,
}

/// Count the head spellings of every top-level form of `doc`.
///
/// Returns the head -> count map (byte-wise head order). Raw spellings are
/// preserved (quoted heads keep their quotes). Fails closed on an empty
/// document or a form without an atom/quoted head.
pub fn count_ami_text_form_heads_v1(
    doc: &AmiTextDocumentV1,
) -> Result<BTreeMap<String, usize>, AmiTextFormHeadsErrorV1> {
    let mut heads = BTreeMap::new();
    for form in doc.forms() {
        let first = form
            .items()
            .first()
            .ok_or(AmiTextFormHeadsErrorV1::InvalidFormHead)?;
        let head = match first {
            AmiTextNodeV1::Atom(token) | AmiTextNodeV1::Quoted(token) => {
                token.spelling().to_string()
            }
            AmiTextNodeV1::List(_) => {
                return Err(AmiTextFormHeadsErrorV1::InvalidFormHead);
            }
        };
        *heads.entry(head).or_insert(0) += 1;
    }
    if heads.is_empty() {
        return Err(AmiTextFormHeadsErrorV1::EmptyDocument);
    }
    Ok(heads)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::ParseLimitsV1;
    use crate::parse_ami_text_v1;

    fn limits() -> ParseLimitsV1 {
        ParseLimitsV1::try_new(8 * 1024 * 1024, 64, 4096, 4096).expect("limits")
    }

    #[test]
    fn counts_repeated_heads() {
        let doc = parse_ami_text_v1(b"(a 1) (b 2) (a 3)", limits()).expect("parsed");
        let heads = count_ami_text_form_heads_v1(&doc).expect("counted");
        assert_eq!(heads.get("a"), Some(&2));
        assert_eq!(heads.get("b"), Some(&1));
        assert_eq!(heads.len(), 2);
    }

    #[test]
    fn counts_single_form_head() {
        let doc = parse_ami_text_v1(b"(root (x 1))", limits()).expect("parsed");
        let heads = count_ami_text_form_heads_v1(&doc).expect("counted");
        assert_eq!(heads.get("root"), Some(&1));
    }

    #[test]
    fn empty_document_fails_closed() {
        let empty = AmiTextDocumentV1 { forms: Vec::new() };
        let error = count_ami_text_form_heads_v1(&empty).unwrap_err();
        assert_eq!(error, AmiTextFormHeadsErrorV1::EmptyDocument);
    }

    #[test]
    fn nested_list_head_fails_closed() {
        let doc = parse_ami_text_v1(b"((a) 1)", limits()).expect("parsed");
        let error = count_ami_text_form_heads_v1(&doc).unwrap_err();
        assert_eq!(error, AmiTextFormHeadsErrorV1::InvalidFormHead);
    }

    #[test]
    fn empty_form_fails_closed() {
        let doc = parse_ami_text_v1(b"()", limits()).expect("parsed");
        let error = count_ami_text_form_heads_v1(&doc).unwrap_err();
        assert_eq!(error, AmiTextFormHeadsErrorV1::InvalidFormHead);
    }
}
