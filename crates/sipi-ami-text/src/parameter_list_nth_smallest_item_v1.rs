//! AMI parameter list nth-smallest item core (P4B-02b162).
//!
//! Returns the nth-smallest trimmed item of a validated List-typed
//! `AmiParameterValueV1` value under the P4B-02b1 list rule
//! (`(item, item, ...)`, items trimmed, non-empty):
//! `parameter_list_nth_smallest_item_v1` returns the item at zero-based rank
//! `nth` in the sorted order of the value's trimmed items (raw byte equality
//! and byte lexicographic order, per the P4B-02b0 raw-byte binding; for valid
//! UTF-8 this order equals code-point order), with duplicates counted as
//! separate positions. This is the order-statistic companion of 02b161
//! min-max item (rank 0 is the minimum, rank len-1 the maximum).
//!
//! Fail-closed: the value not declared List yields `NotAList`; the token not
//! matching the List shape yields `MalformedList` (unreachable for values
//! built via `AmiParameterValueV1::try_new`, kept defensive instead of
//! panicking); a rank beyond the item count yields `IndexOutOfRange` with the
//! requested index and item count (never confused with a legal rank 0).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: list value nth-smallest item.
pub const PARAMETER_LIST_NTH_SMALLEST_ITEM_POLICY_V1: &str =
    "sipi.p4b-02b162.parameter-list-nth-smallest-item-v1.nth-smallest-item";

/// Fail-closed error while computing the nth-smallest item of a list value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListNthSmallestItemErrorV1 {
    /// The value's declared type is not List.
    NotAList,
    /// The token does not match the List shape (defensive; unreachable for
    /// values built via `AmiParameterValueV1::try_new`).
    MalformedList,
    /// The requested rank is beyond the item count.
    IndexOutOfRange { index: usize, item_count: usize },
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

/// Return the item at zero-based rank `nth` in sorted order of the trimmed
/// items of a List-typed value (byte lexicographic order, duplicates counted
/// as separate positions).
pub fn parameter_list_nth_smallest_item_v1(
    value: &AmiParameterValueV1,
    nth: usize,
) -> Result<String, ParameterListNthSmallestItemErrorV1> {
    if value.parameter_type() != AmiParameterTypeV1::List {
        return Err(ParameterListNthSmallestItemErrorV1::NotAList);
    }
    let items = list_items(value.value_token())
        .ok_or(ParameterListNthSmallestItemErrorV1::MalformedList)?;
    let item_count = items.len();
    if nth >= item_count {
        return Err(ParameterListNthSmallestItemErrorV1::IndexOutOfRange {
            index: nth,
            item_count,
        });
    }
    let mut sorted = items.clone();
    sorted.sort();
    Ok(sorted[nth].clone())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    #[test]
    fn computes_nth_smallest() {
        let v = value("param", "List", "(c, a, b)");
        assert_eq!(parameter_list_nth_smallest_item_v1(&v, 0), Ok("a".to_string()));
        assert_eq!(parameter_list_nth_smallest_item_v1(&v, 1), Ok("b".to_string()));
        assert_eq!(parameter_list_nth_smallest_item_v1(&v, 2), Ok("c".to_string()));
    }

    #[test]
    fn duplicates_count_as_separate_positions() {
        let v = value("param", "List", "(b, a, b)");
        assert_eq!(parameter_list_nth_smallest_item_v1(&v, 0), Ok("a".to_string()));
        assert_eq!(parameter_list_nth_smallest_item_v1(&v, 1), Ok("b".to_string()));
        assert_eq!(parameter_list_nth_smallest_item_v1(&v, 2), Ok("b".to_string()));
    }

    #[test]
    fn single_item_only_rank_zero() {
        let v = value("param", "List", "(x)");
        assert_eq!(parameter_list_nth_smallest_item_v1(&v, 0), Ok("x".to_string()));
    }

    #[test]
    fn rank_out_of_range_fails_closed() {
        let v = value("param", "List", "(a, b)");
        assert_eq!(
            parameter_list_nth_smallest_item_v1(&v, 2),
            Err(ParameterListNthSmallestItemErrorV1::IndexOutOfRange {
                index: 2,
                item_count: 2,
            })
        );
    }

    #[test]
    fn spacing_is_canonicalized() {
        let v = value("param", "List", "( c , a , b )");
        assert_eq!(parameter_list_nth_smallest_item_v1(&v, 1), Ok("b".to_string()));
    }

    #[test]
    fn non_list_fails_closed() {
        let v = value("gain", "Float", "0.5");
        assert_eq!(
            parameter_list_nth_smallest_item_v1(&v, 0),
            Err(ParameterListNthSmallestItemErrorV1::NotAList)
        );
    }
}
