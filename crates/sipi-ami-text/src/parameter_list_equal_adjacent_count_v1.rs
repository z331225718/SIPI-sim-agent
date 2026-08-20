//! AMI parameter list equal-adjacent count core (P4B-02b134).
//!
//! Counts the equal adjacent pairs of the trimmed items of a validated
//! List-typed `AmiParameterValueV1` under the P4B-02b1 list rule
//! (`(item, item, ...)`, items trimmed, non-empty):
//! `parameter_list_equal_adjacent_count_v1` returns the number of adjacent
//! index pairs `(i, i + 1)` whose items are equal (raw byte equality, per
//! the P4B-02b0 raw-byte binding). The number of 02b119 runs equals
//! `item_count - equal_adjacent_count`; a list with no equal adjacent pairs
//! has item_count runs. This is the adjacency companion of 02b119 run-length
//! encoding and of 02b108 occurrence counting.
//!
//! Fail-closed: a non-List value yields `NotAList`; a token that does not
//! match the List shape yields `MalformedList` (unreachable for values built
//! via `AmiParameterValueV1::try_new`, kept defensive instead of panicking).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: equal adjacent pair counting.
pub const PARAMETER_LIST_EQUAL_ADJACENT_COUNT_POLICY_V1: &str =
    "sipi.p4b-02b134.parameter-list-equal-adjacent-count-v1.equal-adjacent-pairs";

/// Fail-closed error while counting equal adjacent pairs of one list value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListEqualAdjacentCountErrorV1 {
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

/// Count the adjacent index pairs (i, i + 1) whose trimmed items are equal.
pub fn parameter_list_equal_adjacent_count_v1(
    value: &AmiParameterValueV1,
) -> Result<usize, ParameterListEqualAdjacentCountErrorV1> {
    if value.parameter_type() != AmiParameterTypeV1::List {
        return Err(ParameterListEqualAdjacentCountErrorV1::NotAList);
    }
    let items = list_items(value.value_token())
        .ok_or(ParameterListEqualAdjacentCountErrorV1::MalformedList)?;
    Ok(items
        .windows(2)
        .filter(|pair| pair[0] == pair[1])
        .count())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    #[test]
    fn counts_equal_adjacent_pairs() {
        let v = value("channels", "List", "(a, a, b, c, c, c)");
        assert_eq!(parameter_list_equal_adjacent_count_v1(&v), Ok(3));
    }

    #[test]
    fn all_distinct_has_zero() {
        let v = value("channels", "List", "(a, b, c)");
        assert_eq!(parameter_list_equal_adjacent_count_v1(&v), Ok(0));
    }

    #[test]
    fn all_equal_has_count_minus_one() {
        let v = value("channels", "List", "(x, x, x, x)");
        assert_eq!(parameter_list_equal_adjacent_count_v1(&v), Ok(3));
    }

    #[test]
    fn single_item_has_zero() {
        let v = value("channels", "List", "(x)");
        assert_eq!(parameter_list_equal_adjacent_count_v1(&v), Ok(0));
    }

    #[test]
    fn non_list_fails_closed() {
        let float = value("gain", "Float", "0.5");
        assert_eq!(
            parameter_list_equal_adjacent_count_v1(&float),
            Err(ParameterListEqualAdjacentCountErrorV1::NotAList)
        );
    }

    #[test]
    fn spacing_is_canonicalized() {
        let v = value("channels", "List", "( a , a , b )");
        assert_eq!(parameter_list_equal_adjacent_count_v1(&v), Ok(1));
    }
}
