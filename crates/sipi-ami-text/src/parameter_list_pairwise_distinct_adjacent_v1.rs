//! AMI parameter list pairwise-distinct adjacent pairs core (P4B-02b184).
//!
//! Returns the adjacent pairs whose two items differ within a validated
//! List-typed `AmiParameterValueV1` value under the P4B-02b1 list rule
//! (`(item, item, ...)`, items trimmed, non-empty):
//! `parameter_list_pairwise_distinct_adjacent_v1` returns, for every adjacent
//! index `i` with `item[i] != item[i + 1]` (raw byte equality, per the
//! P4B-02b0 raw-byte binding), the pair `(item[i], item[i + 1])` in list
//! order, keeping duplicate pairs at distinct positions. The pair count
//! therefore equals the 02b172 adjacent-change count, and every returned
//! pair is a length-2 window of the 02b157 contains-sequence semantics. The
//! result is empty for a single-item list or an all-equal list (an empty
//! result is a legal value, mirroring the 02b40 empty-search result).
//!
//! Fail-closed: the value not declared List yields `NotAList`; the token not
//! matching the List shape yields `MalformedList` (unreachable for values
//! built via `AmiParameterValueV1::try_new`, kept defensive instead of
//! panicking).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: pairwise-distinct adjacent pairs.
pub const PARAMETER_LIST_PAIRWISE_DISTINCT_ADJACENT_POLICY_V1: &str =
    "sipi.p4b-02b184.parameter-list-pairwise-distinct-adjacent-v1.pairwise-distinct-adjacent";

/// Fail-closed error while computing the pairwise-distinct adjacent pairs of a list value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListPairwiseDistinctAdjacentErrorV1 {
    /// The value's declared type is not List.
    NotAList,
    /// The token does not match the List shape (defensive; unreachable for
    /// values built via `AmiParameterValueV1::try_new`).
    MalformedList,
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

/// Return the `(item[i], item[i + 1])` pairs for every adjacent index at
/// which the two trimmed items differ (raw byte equality), in list order,
/// keeping duplicates; the pair count equals the 02b172 adjacent-change
/// count.
pub fn parameter_list_pairwise_distinct_adjacent_v1(
    value: &AmiParameterValueV1,
) -> Result<Vec<(String, String)>, ParameterListPairwiseDistinctAdjacentErrorV1> {
    if value.parameter_type() != AmiParameterTypeV1::List {
        return Err(ParameterListPairwiseDistinctAdjacentErrorV1::NotAList);
    }
    let items = list_items(value.value_token())
        .ok_or(ParameterListPairwiseDistinctAdjacentErrorV1::MalformedList)?;
    let mut pairs: Vec<(String, String)> = Vec::new();
    for pair in items.windows(2) {
        if pair[0] != pair[1] {
            pairs.push((pair[0].clone(), pair[1].clone()));
        }
    }
    Ok(pairs)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    #[test]
    fn mixed_pairs_in_order_with_duplicates() {
        let v = value("channels", "List", "(a, b, b, c, a)");
        assert_eq!(
            parameter_list_pairwise_distinct_adjacent_v1(&v),
            Ok(vec![
                ("a".to_string(), "b".to_string()),
                ("b".to_string(), "c".to_string()),
                ("c".to_string(), "a".to_string()),
            ])
        );
    }

    #[test]
    fn duplicate_pair_kept_at_each_position() {
        let v = value("param", "List", "(a, b, a, b)");
        assert_eq!(
            parameter_list_pairwise_distinct_adjacent_v1(&v),
            Ok(vec![
                ("a".to_string(), "b".to_string()),
                ("b".to_string(), "a".to_string()),
                ("a".to_string(), "b".to_string()),
            ])
        );
    }

    #[test]
    fn all_distinct_emit_every_adjacent_pair() {
        let v = value("param", "List", "(p, q, r)");
        assert_eq!(
            parameter_list_pairwise_distinct_adjacent_v1(&v),
            Ok(vec![
                ("p".to_string(), "q".to_string()),
                ("q".to_string(), "r".to_string()),
            ])
        );
    }

    #[test]
    fn all_equal_single_pair_empty_result() {
        let v = value("param", "List", "(x, x, x)");
        assert_eq!(parameter_list_pairwise_distinct_adjacent_v1(&v), Ok(vec![]));
    }

    #[test]
    fn single_item_empty_result() {
        let v = value("param", "List", "(x)");
        assert_eq!(parameter_list_pairwise_distinct_adjacent_v1(&v), Ok(vec![]));
    }

    #[test]
    fn non_list_fails_closed() {
        let v = value("gain", "Float", "0.5");
        assert_eq!(
            parameter_list_pairwise_distinct_adjacent_v1(&v),
            Err(ParameterListPairwiseDistinctAdjacentErrorV1::NotAList)
        );
    }
}