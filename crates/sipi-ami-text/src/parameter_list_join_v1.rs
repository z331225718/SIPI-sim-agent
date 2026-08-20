//! AMI parameter list value join core (P4B-02b106).
//!
//! Joins two validated List-typed `AmiParameterValueV1` values under the
//! P4B-02b1 list rule (`(item, item, ...)`, items trimmed, non-empty):
//! `join_parameter_list_values_v1` returns the canonical list token whose
//! items are the left value's trimmed items followed by the right value's
//! trimmed items (duplicates preserved; re-joined with `", "`). This is the
//! concatenation companion of the list-edit family (02b84 access, 02b98 dedup,
//! 02b99 replace, 02b100 remove, 02b101 append, 02b102 insert, 02b103 swap,
//! 02b104 reverse, 02b105 sort).
//!
//! Fail-closed: either value not declared List yields `NotAList`; either
//! token not matching the List shape yields `MalformedList` (unreachable for
//! values built via `AmiParameterValueV1::try_new`, kept defensive instead of
//! panicking).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: list value join on values.
pub const PARAMETER_LIST_JOIN_POLICY_V1: &str =
    "sipi.p4b-02b106.parameter-list-join-v1.list-value-join";

/// Fail-closed error while joining two list values.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListJoinErrorV1 {
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

/// Join the trimmed items of two List-typed validated values.
pub fn join_parameter_list_values_v1(
    left: &AmiParameterValueV1,
    right: &AmiParameterValueV1,
) -> Result<String, ParameterListJoinErrorV1> {
    if left.parameter_type() != AmiParameterTypeV1::List
        || right.parameter_type() != AmiParameterTypeV1::List
    {
        return Err(ParameterListJoinErrorV1::NotAList);
    }
    let left_items =
        list_items(left.value_token()).ok_or(ParameterListJoinErrorV1::MalformedList)?;
    let right_items =
        list_items(right.value_token()).ok_or(ParameterListJoinErrorV1::MalformedList)?;
    let mut items = left_items;
    items.extend(right_items);
    Ok(format!("({})", items.join(", ")))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    #[test]
    fn joins_two_lists() {
        let a = value("left", "List", "(a, b)");
        let b = value("right", "List", "(c, d)");
        assert_eq!(
            join_parameter_list_values_v1(&a, &b),
            Ok("(a, b, c, d)".to_string())
        );
    }

    #[test]
    fn joins_single_items() {
        let a = value("left", "List", "(a)");
        let b = value("right", "List", "(b)");
        assert_eq!(
            join_parameter_list_values_v1(&a, &b),
            Ok("(a, b)".to_string())
        );
    }

    #[test]
    fn left_non_list_fails_closed() {
        let a = value("gain", "Float", "0.5");
        let b = value("right", "List", "(c)");
        assert_eq!(
            join_parameter_list_values_v1(&a, &b),
            Err(ParameterListJoinErrorV1::NotAList)
        );
    }

    #[test]
    fn right_non_list_fails_closed() {
        let a = value("left", "List", "(a)");
        let b = value("gain", "Float", "0.5");
        assert_eq!(
            join_parameter_list_values_v1(&a, &b),
            Err(ParameterListJoinErrorV1::NotAList)
        );
    }

    #[test]
    fn spacing_is_canonicalized() {
        let a = value("left", "List", "( a , b )");
        let b = value("right", "List", "(c)");
        assert_eq!(
            join_parameter_list_values_v1(&a, &b),
            Ok("(a, b, c)".to_string())
        );
    }

    #[test]
    fn join_preserves_duplicates() {
        let a = value("left", "List", "(a, b)");
        let b = value("right", "List", "(b, c)");
        assert_eq!(
            join_parameter_list_values_v1(&a, &b),
            Ok("(a, b, b, c)".to_string())
        );
    }
}
