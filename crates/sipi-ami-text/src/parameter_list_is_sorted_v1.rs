//! AMI parameter list sortedness check core (P4B-02b124).
//!
//! Checks whether the trimmed items of a validated List-typed
//! `AmiParameterValueV1` under the P4B-02b1 list rule (`(item, item, ...)`,
//! items trimmed, non-empty) are in sorted order:
//! `parameter_list_is_sorted_v1` returns whether every adjacent pair of
//! trimmed items is in non-decreasing byte order (`descending == false`) or
//! non-increasing byte order (`descending == true`); a single-item list is
//! trivially sorted in either direction. Byte order follows the P4B-02b0
//! raw-byte binding. This is the order-check companion of 02b105 sort.
//!
//! Fail-closed: a non-List value yields `NotAList`; a token that does not
//! match the List shape yields `MalformedList` (unreachable for values built
//! via `AmiParameterValueV1::try_new`, kept defensive instead of panicking).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: list sortedness check.
pub const PARAMETER_LIST_IS_SORTED_POLICY_V1: &str =
    "sipi.p4b-02b124.parameter-list-is-sorted-v1.sortedness-check";

/// Fail-closed error while checking the sortedness of one list value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListIsSortedErrorV1 {
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

/// Check whether the trimmed items of a List value are in non-decreasing
/// (`descending == false`) or non-increasing (`descending == true`) byte
/// order.
pub fn parameter_list_is_sorted_v1(
    value: &AmiParameterValueV1,
    descending: bool,
) -> Result<bool, ParameterListIsSortedErrorV1> {
    if value.parameter_type() != AmiParameterTypeV1::List {
        return Err(ParameterListIsSortedErrorV1::NotAList);
    }
    let items = list_items(value.value_token())
        .ok_or(ParameterListIsSortedErrorV1::MalformedList)?;
    for pair in items.windows(2) {
        let ordered = if descending {
            pair[0] >= pair[1]
        } else {
            pair[0] <= pair[1]
        };
        if !ordered {
            return Ok(false);
        }
    }
    Ok(true)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    #[test]
    fn ascending_order_is_sorted() {
        let v = value("channels", "List", "(a, b, c)");
        assert_eq!(parameter_list_is_sorted_v1(&v, false), Ok(true));
    }

    #[test]
    fn descending_order_is_sorted() {
        let v = value("channels", "List", "(c, b, a)");
        assert_eq!(parameter_list_is_sorted_v1(&v, true), Ok(true));
    }

    #[test]
    fn wrong_direction_is_not_sorted() {
        let v = value("channels", "List", "(a, c, b)");
        assert_eq!(parameter_list_is_sorted_v1(&v, false), Ok(false));
        assert_eq!(parameter_list_is_sorted_v1(&v, true), Ok(false));
    }

    #[test]
    fn equal_adjacent_items_are_sorted() {
        let v = value("channels", "List", "(a, a, b)");
        assert_eq!(parameter_list_is_sorted_v1(&v, false), Ok(true));
        let v = value("channels", "List", "(b, b, a)");
        assert_eq!(parameter_list_is_sorted_v1(&v, true), Ok(true));
    }

    #[test]
    fn non_list_fails_closed() {
        let float = value("gain", "Float", "0.5");
        assert_eq!(
            parameter_list_is_sorted_v1(&float, false),
            Err(ParameterListIsSortedErrorV1::NotAList)
        );
    }

    #[test]
    fn single_item_is_trivially_sorted() {
        let v = value("channels", "List", "(x)");
        assert_eq!(parameter_list_is_sorted_v1(&v, false), Ok(true));
        assert_eq!(parameter_list_is_sorted_v1(&v, true), Ok(true));
    }
}
