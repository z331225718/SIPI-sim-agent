//! AMI parameter list all-equal check core (P4B-02b160).
//!
//! Checks whether all trimmed items of a validated List-typed
//! `AmiParameterValueV1` value are mutually equal under the P4B-02b1 list
//! rule (`(item, item, ...)`, items trimmed, non-empty):
//! `parameter_list_all_equal_v1` returns whether every pair of trimmed items
//! is equal by raw byte equality (per the P4B-02b0 raw-byte binding). A
//! single-item list is trivially all-equal. This is the value-level companion
//! of 02b134 equal-adjacent-count (all adjacent pairs equal if and only if
//! all items equal) and of 02b136 unique-item-count (unique count 1 if and
//! only if all equal).
//!
//! Fail-closed: the value not declared List yields `NotAList`; the token not
//! matching the List shape yields `MalformedList` (unreachable for values
//! built via `AmiParameterValueV1::try_new`, kept defensive instead of
//! panicking).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: list value all-equal check.
pub const PARAMETER_LIST_ALL_EQUAL_POLICY_V1: &str =
    "sipi.p4b-02b160.parameter-list-all-equal-v1.all-equal";

/// Fail-closed error while checking all-equal of a list value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListAllEqualErrorV1 {
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

/// Return whether all trimmed items of a List-typed value are mutually equal
/// (raw byte equality); a single-item list is trivially all-equal.
pub fn parameter_list_all_equal_v1(
    value: &AmiParameterValueV1,
) -> Result<bool, ParameterListAllEqualErrorV1> {
    if value.parameter_type() != AmiParameterTypeV1::List {
        return Err(ParameterListAllEqualErrorV1::NotAList);
    }
    let items = list_items(value.value_token())
        .ok_or(ParameterListAllEqualErrorV1::MalformedList)?;
    let first = &items[0];
    Ok(items.iter().all(|item| item == first))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    #[test]
    fn repeated_items_are_all_equal() {
        let v = value("param", "List", "(a, a, a)");
        assert_eq!(parameter_list_all_equal_v1(&v), Ok(true));
    }

    #[test]
    fn mixed_items_are_not_all_equal() {
        let v = value("param", "List", "(a, b, a)");
        assert_eq!(parameter_list_all_equal_v1(&v), Ok(false));
    }

    #[test]
    fn single_item_is_trivially_all_equal() {
        let v = value("param", "List", "(a)");
        assert_eq!(parameter_list_all_equal_v1(&v), Ok(true));
    }

    #[test]
    fn spacing_is_canonicalized() {
        let v = value("param", "List", "( a , a , a )");
        assert_eq!(parameter_list_all_equal_v1(&v), Ok(true));
    }

    #[test]
    fn non_list_fails_closed() {
        let v = value("gain", "Float", "0.5");
        assert_eq!(
            parameter_list_all_equal_v1(&v),
            Err(ParameterListAllEqualErrorV1::NotAList)
        );
    }

    #[test]
    fn byte_equality_is_raw() {
        // Trimmed items compare by raw bytes; "A" and "a" differ.
        let v = value("param", "List", "(A, a)");
        assert_eq!(parameter_list_all_equal_v1(&v), Ok(false));
    }
}
