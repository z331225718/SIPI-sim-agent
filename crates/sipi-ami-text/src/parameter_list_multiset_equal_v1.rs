//! AMI parameter list multiset equality core (P4B-02b152).
//!
//! Checks whether two validated List-typed `AmiParameterValueV1` values are
//! equal as multisets under the P4B-02b1 list rule (`(item, item, ...)`,
//! items trimmed, non-empty): `list_multiset_equal_v1` returns whether every
//! trimmed item of one value occurs the same number of times in the other
//! (raw byte equality, per the P4B-02b0 raw-byte binding; order-insensitive,
//! counts equal). This is the multiset companion of 02b121 frequency mapping
//! (two lists are multiset-equal exactly when their frequency maps coincide)
//! and of 02b150 union (a list is multiset-equal to the union of itself and a
//! sub-multiset).
//!
//! Fail-closed: either value not declared List yields `NotAList`; either
//! token not matching the List shape yields `MalformedList` (unreachable for
//! values built via `AmiParameterValueV1::try_new`, kept defensive instead
//! of panicking).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: multiset equality of list values.
pub const PARAMETER_LIST_MULTISET_EQUAL_POLICY_V1: &str =
    "sipi.p4b-02b152.parameter-list-multiset-equal-v1.multiset-equality";

/// Fail-closed error while checking multiset equality of two list values.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListMultisetEqualErrorV1 {
    /// A value's declared type is not List.
    NotAList,
    /// A token does not match the List shape (defensive; unreachable for
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

/// Check whether two List-typed validated values are equal as multisets
/// (order-insensitive; every item count matches by byte equality).
pub fn list_multiset_equal_v1(
    left: &AmiParameterValueV1,
    right: &AmiParameterValueV1,
) -> Result<bool, ParameterListMultisetEqualErrorV1> {
    if left.parameter_type() != AmiParameterTypeV1::List
        || right.parameter_type() != AmiParameterTypeV1::List
    {
        return Err(ParameterListMultisetEqualErrorV1::NotAList);
    }
    let left_items =
        list_items(left.value_token()).ok_or(ParameterListMultisetEqualErrorV1::MalformedList)?;
    let right_items =
        list_items(right.value_token()).ok_or(ParameterListMultisetEqualErrorV1::MalformedList)?;
    if left_items.len() != right_items.len() {
        return Ok(false);
    }
    for item in &left_items {
        let left_count = left_items
            .iter()
            .filter(|candidate| *candidate == item)
            .count();
        let right_count = right_items
            .iter()
            .filter(|candidate| *candidate == item)
            .count();
        if left_count != right_count {
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
    fn order_insensitive_equal() {
        let a = value("left", "List", "(a, b, c)");
        let b = value("right", "List", "(c, a, b)");
        assert_eq!(list_multiset_equal_v1(&a, &b), Ok(true));
    }

    #[test]
    fn counts_must_match() {
        let a = value("left", "List", "(a, a, b)");
        let b = value("right", "List", "(a, b, b)");
        assert_eq!(list_multiset_equal_v1(&a, &b), Ok(false));
    }

    #[test]
    fn different_items_false() {
        let a = value("left", "List", "(a, b)");
        let b = value("right", "List", "(a, c)");
        assert_eq!(list_multiset_equal_v1(&a, &b), Ok(false));
    }

    #[test]
    fn different_lengths_false() {
        let a = value("left", "List", "(a, b)");
        let b = value("right", "List", "(a, b, c)");
        assert_eq!(list_multiset_equal_v1(&a, &b), Ok(false));
    }

    #[test]
    fn right_non_list_fails_closed() {
        let a = value("left", "List", "(a)");
        let b = value("gain", "Float", "0.5");
        assert_eq!(
            list_multiset_equal_v1(&a, &b),
            Err(ParameterListMultisetEqualErrorV1::NotAList)
        );
    }

    #[test]
    fn spacing_is_canonicalized() {
        let a = value("left", "List", "( a , b , c )");
        let b = value("right", "List", "(c, b, a)");
        assert_eq!(list_multiset_equal_v1(&a, &b), Ok(true));
    }
}
