//! AMI text document structure statistics core (P4B-02b51).
//!
//! Computes structural statistics over a parsed `AmiTextDocumentV1` AST: total
//! list count (top-level forms plus nested lists), atom count, quoted token
//! count, and maximum list nesting depth (a top-level form is depth 1).
//! Fail-closed: an empty document (no forms) is strictly rejected.

use crate::{AmiTextDocumentV1, AmiTextListV1, AmiTextNodeV1};

/// Scope policy for the AMI text document statistics core.
pub const AMI_TEXT_DOCUMENT_STATS_POLICY_V1: &str =
    "sipi.p4b-02b51.ami-text-document-stats-v1.ast-structure-stats";

/// Fail-closed errors during document statistics computation.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum AmiTextStatsErrorV1 {
    /// The document carries no forms.
    EmptyDocument,
}

/// Structural statistics of an AMI text document.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct AmiTextDocumentStatsV1 {
    list_count: usize,
    atom_count: usize,
    quoted_count: usize,
    max_depth: usize,
}

impl AmiTextDocumentStatsV1 {
    pub fn list_count(&self) -> usize {
        self.list_count
    }

    pub fn atom_count(&self) -> usize {
        self.atom_count
    }

    pub fn quoted_count(&self) -> usize {
        self.quoted_count
    }

    pub fn max_depth(&self) -> usize {
        self.max_depth
    }
}

fn walk_list(list: &AmiTextListV1, depth: usize, stats: &mut AmiTextDocumentStatsV1) {
    stats.list_count += 1;
    if depth > stats.max_depth {
        stats.max_depth = depth;
    }
    for item in list.items() {
        match item {
            AmiTextNodeV1::List(sub) => walk_list(sub, depth + 1, stats),
            AmiTextNodeV1::Atom(_) => stats.atom_count += 1,
            AmiTextNodeV1::Quoted(_) => stats.quoted_count += 1,
        }
    }
}

/// Compute structural statistics over `doc` (forms at depth 1).
///
/// Fails closed on a document with no forms.
pub fn compute_ami_text_document_stats_v1(
    doc: &AmiTextDocumentV1,
) -> Result<AmiTextDocumentStatsV1, AmiTextStatsErrorV1> {
    let mut stats = AmiTextDocumentStatsV1 {
        list_count: 0,
        atom_count: 0,
        quoted_count: 0,
        max_depth: 0,
    };
    for form in doc.forms() {
        walk_list(form, 1, &mut stats);
    }
    if stats.list_count == 0 {
        return Err(AmiTextStatsErrorV1::EmptyDocument);
    }
    Ok(stats)
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
    fn mixed_document_counts_all_categories() {
        let doc = parse_ami_text_v1(b"(a b (c \"d\" e))", limits()).expect("parsed");
        let stats = compute_ami_text_document_stats_v1(&doc).expect("stats");
        assert_eq!(stats.list_count(), 2);
        assert_eq!(stats.atom_count(), 4);
        assert_eq!(stats.quoted_count(), 1);
        assert_eq!(stats.max_depth(), 2);
    }

    #[test]
    fn multiple_forms_are_counted() {
        let doc = parse_ami_text_v1(b"(x 1) (y 2)", limits()).expect("parsed");
        let stats = compute_ami_text_document_stats_v1(&doc).expect("stats");
        assert_eq!(stats.list_count(), 2);
        assert_eq!(stats.atom_count(), 4);
        assert_eq!(stats.quoted_count(), 0);
        assert_eq!(stats.max_depth(), 1);
    }

    #[test]
    fn deep_nesting_reports_max_depth() {
        let doc = parse_ami_text_v1(b"(a (b (c (d 1))))", limits()).expect("parsed");
        let stats = compute_ami_text_document_stats_v1(&doc).expect("stats");
        assert_eq!(stats.list_count(), 4);
        assert_eq!(stats.max_depth(), 4);
        assert_eq!(stats.atom_count(), 5);
    }

    #[test]
    fn quoted_tokens_are_not_atoms() {
        let doc = parse_ami_text_v1(b"(a \"b\")", limits()).expect("parsed");
        let stats = compute_ami_text_document_stats_v1(&doc).expect("stats");
        assert_eq!(stats.atom_count(), 1);
        assert_eq!(stats.quoted_count(), 1);
    }

    #[test]
    fn empty_document_fails_closed() {
        // construct an empty document directly (crate-internal access)
        let empty = AmiTextDocumentV1 { forms: Vec::new() };
        let error = compute_ami_text_document_stats_v1(&empty).unwrap_err();
        assert_eq!(error, AmiTextStatsErrorV1::EmptyDocument);
    }
}
