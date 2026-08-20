//! AMI parameter list min-max item core (P4B-02b161).
//!
//! Returns the lexicographically smallest and largest trimmed items of a
//! validated List-typed `AmiParameterValueV1` value under the P4B-02b1 list
//! rule (`(item, item, ...)`, items trimmed, non-empty):
//! `parameter_list_min_item_v1` and `parameter_list_max_item_v1` return the
//! minimum and maximum trimmed item respectively, ordered by raw byte
//! equality and byte lexicographic order (per the P4B-02b0 raw-byte
//! binding; for valid UTF-8 this order equals code-point order). The list is
//! non-empty by rule, so both always exist; a single-item list returns that
//! item for both. This is the value-level companion of 02b124 is-sorted and
//! 02b125 is-strictly-sorted (the first and last items of a sorted list are
//! its min and max).
//!
//! Fail-closed: the value not declared List yields `NotAList`; the token not
//! matching the List shape yields `MalformedList` (unreachable for values
//! built via `AmiParameterValueV1::try_new`, kept defensive instead of
//! panicking).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: list value min-max item.
pub const PARAMETER_LIST_MIN_MAX_ITEM_POLICY_V1: &str =
    "sipi.p4b-02b161.parameter-list-min-max-item-v1.min-max-item";

/// Fail-closed error while computing min/max of a list value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListMinMaxItemErrorV1 {
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

/// Return the lexicographically smallest trimmed item of a List-typed value
/// (byte order); the list is non-empty by rule so the minimum always exists.
pub fn parameter_list_min_item_v1(
    value: &AmiParameterValueV1,
) -> Result<String, ParameterListMinMaxItemErrorV1> {
    if value.parameter_type() != AmiParameterTypeV1::List {
        return Err(ParameterListMinMaxItemErrorV1::NotAList);
    }
    let items = list_items(value.value_token())
        .ok_or(ParameterListMinMaxItemErrorV1::MalformedList)?;
    let mut min_item = &items[0];
    for item in &items[1..] {
        if item < min_item {
            min_item = item;
        }
    }
    Ok(min_item.clone())
}

/// Return the lexicographically largest trimmed item of a List-typed value
/// (byte order); the list is non-empty by rule so the maximum always exists.
pub fn parameter_list_max_item_v1(
    value: &AmiParameterValueV1,
) -> Result<String, ParameterListMinMaxItemErrorV1> {
    if value.parameter_type() != AmiParameterTypeV1::List {
        return Err(ParameterListMinMaxItemErrorV1::NotAList);
    }
    let items = list_items(value.value_token())
        .ok_or(ParameterListMinMaxItemErrorV1::MalformedList)?;
    let mut max_item = &items[0];
    for item in &items[1..] {
        if item > max_item {
            max_item = item;
        }
    }
    Ok(max_item.clone())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    #[test]
    fn computes_min_and_max() {
        let v = value("param", "List", "(c, a, b)");
        assert_eq!(parameter_list_min_item_v1(&v), Ok("a".to_string()));
        assert_eq!(parameter_list_max_item_v1(&v), Ok("c".to_string()));
    }

    #[test]
    fn single_item_is_both_min_and_max() {
        let v = value("param", "List", "(x)");
        assert_eq!(parameter_list_min_item_v1(&v), Ok("x".to_string()));
        assert_eq!(parameter_list_max_item_v1(&v), Ok("x".to_string()));
    }

    #[test]
    fn duplicates_do_not_change_result() {
        let v = value("param", "List", "(b, b, a, a)");
        assert_eq!(parameter_list_min_item_v1(&v), Ok("a".to_string()));
        assert_eq!(parameter_list_max_item_v1(&v), Ok("b".to_string()));
    }

    #[test]
    fn byte_order_is_raw() {
        // Uppercase sorts before lowercase in byte order.
        let v = value("param", "List", "(b, A, a)");
        assert_eq!(parameter_list_min_item_v1(&v), Ok("A".to_string()));
        assert_eq!(parameter_list_max_item_v1(&v), Ok("b".to_string()));
    }

    #[test]
    fn spacing_is_canonicalized() {
        let v = value("param", "List", "( c , a , b )");
        assert_eq!(parameter_list_min_item_v1(&v), Ok("a".to_string()));
    }

    #[test]
    fn non_list_fails_closed() {
        let v = value("gain", "Float", "0.5");
        assert_eq!(
            parameter_list_min_item_v1(&v),
            Err(ParameterListMinMaxItemErrorV1::NotAList)
        );
    }
}
