//! AMI parameter list intersection core (P4B-02b148).
//!
//! Computes the value intersection of two validated List-typed
//! `AmiParameterValueV1` values under the P4B-02b1 list rule
//! (`(item, item, ...)`, items trimmed, non-empty):
//! `list_intersection_v1` returns the canonical list token whose items are
//! the trimmed items of the left value that equal some trimmed item of the
//! right value (raw byte equality, per the P4B-02b0 raw-byte binding), in
//! left order with duplicates preserved. This is the set-wise companion of
//! 02b140 multi-remove-all and of 02b113 single-query keep-only (the
//! intersection equals keeping only the right value's items).
//!
//! Fail-closed: either value not declared List yields `NotAList`; either
//! token not matching the List shape yields `MalformedList` (unreachable for
//! values built via `AmiParameterValueV1::try_new`, kept defensive instead
//! of panicking). An empty intersection yields the structurally empty token
//! `()` (not a valid 02b1 List value; the operation is total on the token
//! level and does not re-validate, mirroring 02b100 sole-item removal).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: list value intersection.
pub const PARAMETER_LIST_INTERSECTION_POLICY_V1: &str =
    "sipi.p4b-02b148.parameter-list-intersection-v1.value-intersection";

/// Fail-closed error while computing the intersection of two list values.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListIntersectionErrorV1 {
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

/// Return the canonical token of the left value's trimmed items that equal
/// some right value's trimmed item, in left order with duplicates preserved.
pub fn list_intersection_v1(
    left: &AmiParameterValueV1,
    right: &AmiParameterValueV1,
) -> Result<String, ParameterListIntersectionErrorV1> {
    if left.parameter_type() != AmiParameterTypeV1::List
        || right.parameter_type() != AmiParameterTypeV1::List
    {
        return Err(ParameterListIntersectionErrorV1::NotAList);
    }
    let left_items = list_items(left.value_token())
        .ok_or(ParameterListIntersectionErrorV1::MalformedList)?;
    let right_items = list_items(right.value_token())
        .ok_or(ParameterListIntersectionErrorV1::MalformedList)?;
    let kept: Vec<String> = left_items
        .into_iter()
        .filter(|candidate| right_items.contains(candidate))
        .collect();
    Ok(format!("({})", kept.join(", ")))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    #[test]
    fn intersection_in_left_order() {
        let a = value("left", "List", "(a, b, a, c)");
        let b = value("right", "List", "(b, c, d)");
        assert_eq!(
            list_intersection_v1(&a, &b),
            Ok("(b, c)".to_string())
        );
    }

    #[test]
    fn duplicates_preserved() {
        let a = value("left", "List", "(a, a, b)");
        let b = value("right", "List", "(a)");
        assert_eq!(
            list_intersection_v1(&a, &b),
            Ok("(a, a)".to_string())
        );
    }

    #[test]
    fn disjoint_intersection_empty() {
        let a = value("left", "List", "(a, b)");
        let b = value("right", "List", "(x, y)");
        assert_eq!(list_intersection_v1(&a, &b), Ok("()".to_string()));
    }

    #[test]
    fn equal_values_full_intersection() {
        let a = value("left", "List", "(a, b)");
        let b = value("right", "List", "(a, b)");
        assert_eq!(
            list_intersection_v1(&a, &b),
            Ok("(a, b)".to_string())
        );
    }

    #[test]
    fn left_non_list_fails_closed() {
        let a = value("gain", "Float", "0.5");
        let b = value("right", "List", "(a)");
        assert_eq!(
            list_intersection_v1(&a, &b),
            Err(ParameterListIntersectionErrorV1::NotAList)
        );
    }

    #[test]
    fn spacing_is_canonicalized() {
        let a = value("left", "List", "( a , b , c )");
        let b = value("right", "List", "(b, c)");
        assert_eq!(
            list_intersection_v1(&a, &b),
            Ok("(b, c)".to_string())
        );
    }
}
