//! AMI parameter list pairwise-equal adjacent pairs core (P4B-02b191).
//!
//! Returns the adjacent pairs whose two items are equal within a validated
//! List-typed `AmiParameterValueV1` value under the P4B-02b1 list rule
//! (`(item, item, ...)`, items trimmed, non-empty):
//! `parameter_list_pairwise_equal_adjacent_v1` returns, for every adjacent
//! index `i` with `item[i] == item[i + 1]` (raw byte equality, per the
//! P4B-02b0 raw-byte binding), the pair `(item[i], item[i + 1])` in list
//! order, keeping duplicate pairs at distinct positions. The pair count
//! therefore equals the 02b134 equal-adjacent count, and every returned
//! pair is a length-2 window of the 02b157 contains-sequence semantics. The
//! result is empty for a single-item list or an all-distinct list (an empty
//! result is a legal value, mirroring the 02b40 empty-search result). This is
//! the equal mirror companion of 02b184 pairwise-distinct-adjacent (same
//! windowing, complementary predicate).
//!
//! Fail-closed: the value not declared List yields `NotAList`; the token not
//! matching the List shape yields `MalformedList` (unreachable for values
//! built via `AmiParameterValueV1::try_new`, kept defensive instead of
//! panicking).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: pairwise-equal adjacent pairs.
pub const PARAMETER_LIST_PAIRWISE_EQUAL_ADJACENT_POLICY_V1: &str =
    "sipi.p4b-02b191.parameter-list-pairwise-equal-adjacent-v1.pairwise-equal-adjacent";

/// Fail-closed error while computing the pairwise-equal adjacent pairs of a list value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListPairwiseEqualAdjacentErrorV1 {
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
/// which the two trimmed items are equal (raw byte equality), in list order,
/// keeping duplicates; the pair count equals the 02b134 equal-adjacent
/// count.
pub fn parameter_list_pairwise_equal_adjacent_v1(
    value: &AmiParameterValueV1,
) -> Result<Vec<(String, String)>, ParameterListPairwiseEqualAdjacentErrorV1> {
    if value.parameter_type() != AmiParameterTypeV1::List {
        return Err(ParameterListPairwiseEqualAdjacentErrorV1::NotAList);
    }
    let items = list_items(value.value_token())
        .ok_or(ParameterListPairwiseEqualAdjacentErrorV1::MalformedList)?;
    let mut pairs: Vec<(String, String)> = Vec::new();
    for pair in items.windows(2) {
        if pair[0] == pair[1] {
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
            parameter_list_pairwise_equal_adjacent_v1(&v),
            Ok(vec![("b".to_string(), "b".to_string())])
        );
    }

    #[test]
    fn duplicate_pair_kept_at_each_position() {
        let v = value("param", "List", "(a, a, b, b, b)");
        assert_eq!(
            parameter_list_pairwise_equal_adjacent_v1(&v),
            Ok(vec![
                ("a".to_string(), "a".to_string()),
                ("b".to_string(), "b".to_string()),
                ("b".to_string(), "b".to_string()),
            ])
        );
    }

    #[test]
    fn all_equal_emit_every_adjacent_pair() {
        let v = value("param", "List", "(x, x, x)");
        assert_eq!(
            parameter_list_pairwise_equal_adjacent_v1(&v),
            Ok(vec![
                ("x".to_string(), "x".to_string()),
                ("x".to_string(), "x".to_string()),
            ])
        );
    }

    #[test]
    fn all_distinct_empty_result() {
        let v = value("param", "List", "(p, q, r)");
        assert_eq!(parameter_list_pairwise_equal_adjacent_v1(&v), Ok(vec![]));
    }

    #[test]
    fn single_item_empty_result() {
        let v = value("param", "List", "(x)");
        assert_eq!(parameter_list_pairwise_equal_adjacent_v1(&v), Ok(vec![]));
    }

    #[test]
    fn non_list_fails_closed() {
        let v = value("gain", "Float", "0.5");
        assert_eq!(
            parameter_list_pairwise_equal_adjacent_v1(&v),
            Err(ParameterListPairwiseEqualAdjacentErrorV1::NotAList)
        );
    }
}
