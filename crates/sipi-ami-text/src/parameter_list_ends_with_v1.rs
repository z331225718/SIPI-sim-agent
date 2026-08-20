//! AMI parameter list ends-with check core (P4B-02b147).
//!
//! Checks whether the trimmed items of a validated List-typed
//! `AmiParameterValueV1` value end with the trimmed items of another
//! validated List-typed value under the P4B-02b1 list rule (`(item, item,
//! ...)`, items trimmed, non-empty): `list_ends_with_v1` returns whether
//! the suffix value's trimmed items equal the final items of the value
//! element-wise (raw byte equality, per the P4B-02b0 raw-byte binding). A
//! suffix longer than the value is never a suffix. This is the boolean
//! companion of 02b131 longest-common-suffix (whose length equals the suffix
//! length exactly when the suffix holds) and the end-aligned mirror of
//! 02b146 starts-with.
//!
//! Fail-closed: either value not declared List yields `NotAList`; either
//! token not matching the List shape yields `MalformedList` (unreachable for
//! values built via `AmiParameterValueV1::try_new`, kept defensive instead
//! of panicking).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: list value suffix relation.
pub const PARAMETER_LIST_ENDS_WITH_POLICY_V1: &str =
    "sipi.p4b-02b147.parameter-list-ends-with-v1.suffix-check";

/// Fail-closed error while checking the suffix relation of two list values.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListEndsWithErrorV1 {
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

/// Check whether the trimmed items of `value` end with the trimmed items of
/// `suffix` (element-wise byte equality).
pub fn list_ends_with_v1(
    value: &AmiParameterValueV1,
    suffix: &AmiParameterValueV1,
) -> Result<bool, ParameterListEndsWithErrorV1> {
    if value.parameter_type() != AmiParameterTypeV1::List
        || suffix.parameter_type() != AmiParameterTypeV1::List
    {
        return Err(ParameterListEndsWithErrorV1::NotAList);
    }
    let value_items = list_items(value.value_token())
        .ok_or(ParameterListEndsWithErrorV1::MalformedList)?;
    let suffix_items = list_items(suffix.value_token())
        .ok_or(ParameterListEndsWithErrorV1::MalformedList)?;
    if suffix_items.len() > value_items.len() {
        return Ok(false);
    }
    let offset = value_items.len() - suffix_items.len();
    Ok(value_items[offset..]
        .iter()
        .zip(suffix_items.iter())
        .all(|(candidate, query)| candidate == query))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    #[test]
    fn suffix_holds() {
        let v = value("channels", "List", "(a, b, c, d)");
        let s = value("suffix", "List", "(c, d)");
        assert_eq!(list_ends_with_v1(&v, &s), Ok(true));
    }

    #[test]
    fn full_value_is_its_own_suffix() {
        let v = value("channels", "List", "(a, b)");
        let s = value("suffix", "List", "(a, b)");
        assert_eq!(list_ends_with_v1(&v, &s), Ok(true));
    }

    #[test]
    fn mismatched_suffix_is_false() {
        let v = value("channels", "List", "(a, b, c)");
        let s = value("suffix", "List", "(x, c)");
        assert_eq!(list_ends_with_v1(&v, &s), Ok(false));
    }

    #[test]
    fn longer_suffix_is_false() {
        let v = value("channels", "List", "(a, b)");
        let s = value("suffix", "List", "(x, a, b)");
        assert_eq!(list_ends_with_v1(&v, &s), Ok(false));
    }

    #[test]
    fn suffix_non_list_fails_closed() {
        let v = value("channels", "List", "(a)");
        let s = value("gain", "Float", "0.5");
        assert_eq!(
            list_ends_with_v1(&v, &s),
            Err(ParameterListEndsWithErrorV1::NotAList)
        );
    }

    #[test]
    fn spacing_is_canonicalized() {
        let v = value("channels", "List", "( a , b , c )");
        let s = value("suffix", "List", "(b, c)");
        assert_eq!(list_ends_with_v1(&v, &s), Ok(true));
    }
}
