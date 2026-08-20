//! AMI parameter list adjacent change count core (P4B-02b172).
//!
//! Returns the number of adjacent item pairs with unequal trimmed items of a
//! validated List-typed `AmiParameterValueV1` value under the P4B-02b1 list
//! rule (`(item, item, ...)`, items trimmed, non-empty):
//! `parameter_list_adjacent_change_count_v1` counts the adjacent pairs
//! `(i, i + 1)` whose items differ by raw byte equality (per the P4B-02b0
//! raw-byte binding). The count is 0 for an all-equal list and `len - 1` for
//! an all-distinct list. This is the change companion of 02b168 run count
//! (changes = runs - 1) and of 02b134 equal-adjacent-count (changes + equals
//! = len - 1).
//!
//! Fail-closed: the value not declared List yields `NotAList`; the token not
//! matching the List shape yields `MalformedList` (unreachable for values
//! built via `AmiParameterValueV1::try_new`, kept defensive instead of
//! panicking).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: list value adjacent change count.
pub const PARAMETER_LIST_ADJACENT_CHANGE_COUNT_POLICY_V1: &str =
    "sipi.p4b-02b172.parameter-list-adjacent-change-count-v1.adjacent-change-count";

/// Fail-closed error while computing the adjacent change count of a list value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListAdjacentChangeCountErrorV1 {
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

/// Return the number of adjacent item pairs with unequal trimmed items of a
/// List-typed value (raw byte equality).
pub fn parameter_list_adjacent_change_count_v1(
    value: &AmiParameterValueV1,
) -> Result<usize, ParameterListAdjacentChangeCountErrorV1> {
    if value.parameter_type() != AmiParameterTypeV1::List {
        return Err(ParameterListAdjacentChangeCountErrorV1::NotAList);
    }
    let items = list_items(value.value_token())
        .ok_or(ParameterListAdjacentChangeCountErrorV1::MalformedList)?;
    let changes = items
        .windows(2)
        .filter(|pair| pair[0] != pair[1])
        .count();
    Ok(changes)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    #[test]
    fn counts_changes() {
        let v = value("param", "List", "(a, a, b, b, c, a)");
        assert_eq!(parameter_list_adjacent_change_count_v1(&v), Ok(3));
    }

    #[test]
    fn all_equal_zero_changes() {
        let v = value("param", "List", "(a, a, a)");
        assert_eq!(parameter_list_adjacent_change_count_v1(&v), Ok(0));
    }

    #[test]
    fn all_distinct_len_minus_one() {
        let v = value("param", "List", "(c, a, b)");
        assert_eq!(parameter_list_adjacent_change_count_v1(&v), Ok(2));
    }

    #[test]
    fn single_item_zero_changes() {
        let v = value("param", "List", "(x)");
        assert_eq!(parameter_list_adjacent_change_count_v1(&v), Ok(0));
    }

    #[test]
    fn spacing_is_canonicalized() {
        let v = value("param", "List", "( a , a , b )");
        assert_eq!(parameter_list_adjacent_change_count_v1(&v), Ok(1));
    }

    #[test]
    fn non_list_fails_closed() {
        let v = value("gain", "Float", "0.5");
        assert_eq!(
            parameter_list_adjacent_change_count_v1(&v),
            Err(ParameterListAdjacentChangeCountErrorV1::NotAList)
        );
    }
}
