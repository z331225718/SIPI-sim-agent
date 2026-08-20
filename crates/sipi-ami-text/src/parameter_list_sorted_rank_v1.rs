//! AMI parameter list sorted rank core (P4B-02b169).
//!
//! Returns the zero-based rank of a raw query item within a validated
//! List-typed `AmiParameterValueV1` value under the P4B-02b1 list rule
//! (`(item, item, ...)`, items trimmed, non-empty):
//! `parameter_list_sorted_rank_v1` returns the first position of an item
//! equal to the query in ascending sorted order of the value's trimmed items
//! (raw byte equality and byte lexicographic order, per the P4B-02b0 raw-byte
//! binding; for valid UTF-8 this order equals code-point order), with
//! duplicates counted as separate positions; the query item is compared
//! without trimming (raw query semantics, mirroring 02b110 index-of). This
//! bridges 02b110 index-of (position in the original sequence) and the
//! order statistics 02b162 nth-smallest / 02b163 nth-largest (rank maps to
//! the nth-smallest item).
//!
//! Fail-closed: the value not declared List yields `NotAList`; the token not
//! matching the List shape yields `MalformedList` (unreachable for values
//! built via `AmiParameterValueV1::try_new`, kept defensive instead of
//! panicking); no item equal to the query yields `ItemNotFound` (never
//! confused with a legal rank 0).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: list value sorted rank.
pub const PARAMETER_LIST_SORTED_RANK_POLICY_V1: &str =
    "sipi.p4b-02b169.parameter-list-sorted-rank-v1.sorted-rank";

/// Fail-closed error while computing the sorted rank in a list value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListSortedRankErrorV1 {
    /// The value's declared type is not List.
    NotAList,
    /// The token does not match the List shape (defensive; unreachable for
    /// values built via `AmiParameterValueV1::try_new`).
    MalformedList,
    /// No item equal to the raw query (compared without trimming).
    ItemNotFound,
}

/// Split a validated List token into trimmed non-empty items (02b1 rule).
fn list_items(value_token: &str) -> Option<Vec<String>> {
    if !value_token.starts_with('(') || !value_token.ends_with(')') || value_token.len() < 2 {
        return None;
    }
    let inner = &value_token[1..value_token.len() - 1];
    if inner.is_empty() {
        return None;
    }
    let raw: Vec<&str> = inner.split(',').collect();
    if raw.iter().any(|item| item.trim().is_empty()) {
        return None;
    }
    Some(raw.iter().map(|item| item.trim().to_string()).collect())
}

/// Return the zero-based rank (first position in ascending sorted order) of
/// the raw query item within the trimmed items of a List-typed value (byte
/// lexicographic order, duplicates counted as separate positions).
pub fn parameter_list_sorted_rank_v1(
    value: &AmiParameterValueV1,
    query: &str,
) -> Result<usize, ParameterListSortedRankErrorV1> {
    if value.parameter_type() != AmiParameterTypeV1::List {
        return Err(ParameterListSortedRankErrorV1::NotAList);
    }
    let items = list_items(value.value_token())
        .ok_or(ParameterListSortedRankErrorV1::MalformedList)?;
    let mut sorted = items.clone();
    sorted.sort();
    match sorted.iter().position(|item| item == query) {
        Some(rank) => Ok(rank),
        None => Err(ParameterListSortedRankErrorV1::ItemNotFound),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    #[test]
    fn computes_sorted_rank() {
        let v = value("param", "List", "(c, a, b)");
        assert_eq!(parameter_list_sorted_rank_v1(&v, "b"), Ok(1));
        assert_eq!(parameter_list_sorted_rank_v1(&v, "a"), Ok(0));
        assert_eq!(parameter_list_sorted_rank_v1(&v, "c"), Ok(2));
    }

    #[test]
    fn duplicates_first_rank() {
        let v = value("param", "List", "(b, a, b, a)");
        assert_eq!(parameter_list_sorted_rank_v1(&v, "a"), Ok(0));
        assert_eq!(parameter_list_sorted_rank_v1(&v, "b"), Ok(2));
    }

    #[test]
    fn query_not_found_fails_closed() {
        let v = value("param", "List", "(a, b)");
        assert_eq!(
            parameter_list_sorted_rank_v1(&v, "x"),
            Err(ParameterListSortedRankErrorV1::ItemNotFound)
        );
    }

    #[test]
    fn spacing_is_canonicalized() {
        let v = value("param", "List", "( c , a , b )");
        assert_eq!(parameter_list_sorted_rank_v1(&v, "b"), Ok(1));
    }

    #[test]
    fn non_list_fails_closed() {
        let v = value("gain", "Float", "0.5");
        assert_eq!(
            parameter_list_sorted_rank_v1(&v, "a"),
            Err(ParameterListSortedRankErrorV1::NotAList)
        );
    }

    #[test]
    fn raw_query_byte_equality() {
        // Sorted order is byte lexicographic: "A" before "a"; both queries
        // are compared without trimming and both items are present.
        let v = value("param", "List", "(A, a)");
        assert_eq!(parameter_list_sorted_rank_v1(&v, "A"), Ok(0));
        assert_eq!(parameter_list_sorted_rank_v1(&v, "a"), Ok(1));
        assert_eq!(
            parameter_list_sorted_rank_v1(&v, " A "),
            Err(ParameterListSortedRankErrorV1::ItemNotFound)
        );
    }
}
