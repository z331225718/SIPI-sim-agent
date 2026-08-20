//! AMI parameter list left rotation core (P4B-02b115).
//!
//! Rotates the trimmed items of a validated List-typed `AmiParameterValueV1`
//! under the P4B-02b1 list rule (`(item, item, ...)`, items trimmed,
//! non-empty) left by a non-negative shift:
//! `rotate_parameter_list_left_v1` returns the canonical list token whose
//! items are the trimmed items cyclically shifted left by `shift` positions
//! (effective shift is `shift % item_count`, so a full rotation reproduces
//! the original token), re-joined with `", "`. This is the cyclic-permutation
//! companion of 02b104 reverse, 02b103 swap, and 02b105 sort.
//!
//! Fail-closed: a non-List value yields `NotAList`; a token that does not
//! match the List shape yields `MalformedList` (unreachable for values built
//! via `AmiParameterValueV1::try_new`, kept defensive instead of panicking).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: cyclic left rotation of list items.
pub const PARAMETER_LIST_ROTATE_POLICY_V1: &str =
    "sipi.p4b-02b115.parameter-list-rotate-v1.left-rotation";

/// Fail-closed error while rotating one list value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListRotateErrorV1 {
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

/// Rotate the trimmed items left by `shift` positions of a List value.
pub fn rotate_parameter_list_left_v1(
    value: &AmiParameterValueV1,
    shift: usize,
) -> Result<String, ParameterListRotateErrorV1> {
    if value.parameter_type() != AmiParameterTypeV1::List {
        return Err(ParameterListRotateErrorV1::NotAList);
    }
    let items = list_items(value.value_token()).ok_or(ParameterListRotateErrorV1::MalformedList)?;
    let item_count = items.len();
    let effective = shift % item_count;
    let mut rotated = items;
    rotated.rotate_left(effective);
    Ok(format!("({})", rotated.join(", ")))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    #[test]
    fn rotates_left_by_one() {
        let v = value("channels", "List", "(a, b, c)");
        assert_eq!(
            rotate_parameter_list_left_v1(&v, 1),
            Ok("(b, c, a)".to_string())
        );
    }

    #[test]
    fn rotates_left_by_two() {
        let v = value("channels", "List", "(a, b, c, d)");
        assert_eq!(
            rotate_parameter_list_left_v1(&v, 2),
            Ok("(c, d, a, b)".to_string())
        );
    }

    #[test]
    fn full_rotation_returns_original() {
        let v = value("channels", "List", "(a, b, c)");
        assert_eq!(
            rotate_parameter_list_left_v1(&v, 3),
            Ok("(a, b, c)".to_string())
        );
        assert_eq!(
            rotate_parameter_list_left_v1(&v, 6),
            Ok("(a, b, c)".to_string())
        );
    }

    #[test]
    fn non_list_fails_closed() {
        let float = value("gain", "Float", "0.5");
        assert_eq!(
            rotate_parameter_list_left_v1(&float, 1),
            Err(ParameterListRotateErrorV1::NotAList)
        );
    }

    #[test]
    fn spacing_is_canonicalized() {
        let v = value("channels", "List", "( a , b , c )");
        assert_eq!(
            rotate_parameter_list_left_v1(&v, 1),
            Ok("(b, c, a)".to_string())
        );
    }

    #[test]
    fn single_item_rotation_is_identity() {
        let v = value("channels", "List", "(x)");
        assert_eq!(rotate_parameter_list_left_v1(&v, 5), Ok("(x)".to_string()));
    }
}
