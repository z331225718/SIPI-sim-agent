//! AMI parameter list interleave core (P4B-02b132).
//!
//! Interleaves the trimmed items of two validated List-typed
//! `AmiParameterValueV1` values under the P4B-02b1 list rule
//! (`(item, item, ...)`, items trimmed, non-empty):
//! `interleave_parameter_list_values_v1` returns the canonical list token
//! whose items alternate position-wise between the two values (left item at
//! position i, then right item at position i, for i = 0, 1, ...); once the
//! shorter value is exhausted, the longer value's remaining items are
//! appended in order (zip-with-padding semantics). This is the position-wise
//! companion of 02b106 join (which concatenates) and of 02b103 swap.
//!
//! Fail-closed: either value not declared List yields `NotAList`; either
//! token not matching the List shape yields `MalformedList` (unreachable for
//! values built via `AmiParameterValueV1::try_new`, kept defensive instead
//! of panicking).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: position-wise list interleave.
pub const PARAMETER_LIST_INTERLEAVE_POLICY_V1: &str =
    "sipi.p4b-02b132.parameter-list-interleave-v1.position-wise-interleave";

/// Fail-closed error while interleaving two list values.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListInterleaveErrorV1 {
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

/// Interleave the trimmed items of two List-typed validated values
/// position-wise (zip-with-padding semantics).
pub fn interleave_parameter_list_values_v1(
    left: &AmiParameterValueV1,
    right: &AmiParameterValueV1,
) -> Result<String, ParameterListInterleaveErrorV1> {
    if left.parameter_type() != AmiParameterTypeV1::List
        || right.parameter_type() != AmiParameterTypeV1::List
    {
        return Err(ParameterListInterleaveErrorV1::NotAList);
    }
    let left_items = list_items(left.value_token())
        .ok_or(ParameterListInterleaveErrorV1::MalformedList)?;
    let right_items = list_items(right.value_token())
        .ok_or(ParameterListInterleaveErrorV1::MalformedList)?;
    let mut interleaved: Vec<String> = Vec::new();
    let shared = left_items.len().min(right_items.len());
    for index in 0..shared {
        interleaved.push(left_items[index].clone());
        interleaved.push(right_items[index].clone());
    }
    interleaved.extend(left_items[shared..].iter().cloned());
    interleaved.extend(right_items[shared..].iter().cloned());
    Ok(format!("({})", interleaved.join(", ")))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    #[test]
    fn interleaves_equal_lengths() {
        let a = value("left", "List", "(a, b)");
        let b = value("right", "List", "(x, y)");
        assert_eq!(
            interleave_parameter_list_values_v1(&a, &b),
            Ok("(a, x, b, y)".to_string())
        );
    }

    #[test]
    fn left_longer_appends_remainder() {
        let a = value("left", "List", "(a, b, c)");
        let b = value("right", "List", "(x)");
        assert_eq!(
            interleave_parameter_list_values_v1(&a, &b),
            Ok("(a, x, b, c)".to_string())
        );
    }

    #[test]
    fn right_longer_appends_remainder() {
        let a = value("left", "List", "(a)");
        let b = value("right", "List", "(x, y, z)");
        assert_eq!(
            interleave_parameter_list_values_v1(&a, &b),
            Ok("(a, x, y, z)".to_string())
        );
    }

    #[test]
    fn single_items_interleave() {
        let a = value("left", "List", "(a)");
        let b = value("right", "List", "(b)");
        assert_eq!(
            interleave_parameter_list_values_v1(&a, &b),
            Ok("(a, b)".to_string())
        );
    }

    #[test]
    fn left_non_list_fails_closed() {
        let a = value("gain", "Float", "0.5");
        let b = value("right", "List", "(x)");
        assert_eq!(
            interleave_parameter_list_values_v1(&a, &b),
            Err(ParameterListInterleaveErrorV1::NotAList)
        );
    }

    #[test]
    fn spacing_is_canonicalized() {
        let a = value("left", "List", "( a , b )");
        let b = value("right", "List", "( x , y )");
        assert_eq!(
            interleave_parameter_list_values_v1(&a, &b),
            Ok("(a, x, b, y)".to_string())
        );
    }
}
