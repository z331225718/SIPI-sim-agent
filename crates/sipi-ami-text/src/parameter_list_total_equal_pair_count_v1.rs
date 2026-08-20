//! AMI parameter list total equal pair count core (P4B-02b173).
//!
//! Returns the number of unordered position pairs with equal trimmed items
//! of a validated List-typed `AmiParameterValueV1` value under the P4B-02b1
//! list rule (`(item, item, ...)`, items trimmed, non-empty):
//! `parameter_list_total_equal_pair_count_v1` counts the pairs
//! `(i, j)` with `i < j` whose items are equal by raw byte equality (per the
//! P4B-02b0 raw-byte binding), which equals the sum over distinct items of
//! `count * (count - 1) / 2`. An all-distinct list yields 0. This is the
//! position-pair companion of 02b135 distinct-pair-count (pairs of distinct
//! values) and of 02b134 equal-adjacent-count (adjacent equal pairs are a
//! subset of the equal pairs).
//!
//! Fail-closed: the value not declared List yields `NotAList`; the token not
//! matching the List shape yields `MalformedList` (unreachable for values
//! built via `AmiParameterValueV1::try_new`, kept defensive instead of
//! panicking).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: list value total equal pair count.
pub const PARAMETER_LIST_TOTAL_EQUAL_PAIR_COUNT_POLICY_V1: &str =
    "sipi.p4b-02b173.parameter-list-total-equal-pair-count-v1.total-equal-pair-count";

/// Fail-closed error while computing the total equal pair count of a list value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListTotalEqualPairCountErrorV1 {
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

/// Return the number of unordered position pairs (i < j) with equal trimmed
/// items of a List-typed value (raw byte equality), i.e. the sum over distinct
/// items of count * (count - 1) / 2.
pub fn parameter_list_total_equal_pair_count_v1(
    value: &AmiParameterValueV1,
) -> Result<usize, ParameterListTotalEqualPairCountErrorV1> {
    if value.parameter_type() != AmiParameterTypeV1::List {
        return Err(ParameterListTotalEqualPairCountErrorV1::NotAList);
    }
    let items = list_items(value.value_token())
        .ok_or(ParameterListTotalEqualPairCountErrorV1::MalformedList)?;
    let mut counts: Vec<(String, usize)> = Vec::new();
    for item in &items {
        match counts.iter_mut().find(|(existing, _)| existing == item) {
            Some((_, count)) => *count += 1,
            None => counts.push((item.clone(), 1)),
        }
    }
    let pairs = counts
        .iter()
        .map(|(_, count)| count * (count - 1) / 2)
        .sum();
    Ok(pairs)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    #[test]
    fn computes_equal_pair_count() {
        // (a, a, b, b, a): a count 3 -> 3 pairs, b count 2 -> 1 pair, total 4.
        let v = value("param", "List", "(a, a, b, b, a)");
        assert_eq!(parameter_list_total_equal_pair_count_v1(&v), Ok(4));
    }

    #[test]
    fn all_distinct_zero_pairs() {
        let v = value("param", "List", "(c, a, b)");
        assert_eq!(parameter_list_total_equal_pair_count_v1(&v), Ok(0));
    }

    #[test]
    fn single_repeated_item_all_pairs() {
        let v = value("param", "List", "(a, a, a, a)");
        assert_eq!(parameter_list_total_equal_pair_count_v1(&v), Ok(6));
    }

    #[test]
    fn single_item_zero_pairs() {
        let v = value("param", "List", "(x)");
        assert_eq!(parameter_list_total_equal_pair_count_v1(&v), Ok(0));
    }

    #[test]
    fn spacing_is_canonicalized() {
        let v = value("param", "List", "( a , a , b )");
        assert_eq!(parameter_list_total_equal_pair_count_v1(&v), Ok(1));
    }

    #[test]
    fn non_list_fails_closed() {
        let v = value("gain", "Float", "0.5");
        assert_eq!(
            parameter_list_total_equal_pair_count_v1(&v),
            Err(ParameterListTotalEqualPairCountErrorV1::NotAList)
        );
    }
}
