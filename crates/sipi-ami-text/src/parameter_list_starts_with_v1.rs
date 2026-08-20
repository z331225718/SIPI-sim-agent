//! AMI parameter list starts-with check core (P4B-02b146).
//!
//! Checks whether the trimmed items of a validated List-typed
//! `AmiParameterValueV1` value begin with the trimmed items of another
//! validated List-typed value under the P4B-02b1 list rule (`(item, item,
//! ...)`, items trimmed, non-empty): `list_starts_with_v1` returns whether
//! the prefix value's trimmed items equal the first items of the value
//! element-wise (raw byte equality, per the P4B-02b0 raw-byte binding). A
//! prefix longer than the value is never a prefix. This is the boolean
//! companion of 02b130 longest-common-prefix (whose length equals the prefix
//! length exactly when the prefix holds).
//!
//! Fail-closed: either value not declared List yields `NotAList`; either
//! token not matching the List shape yields `MalformedList` (unreachable for
//! values built via `AmiParameterValueV1::try_new`, kept defensive instead
//! of panicking).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: list value prefix relation.
pub const PARAMETER_LIST_STARTS_WITH_POLICY_V1: &str =
    "sipi.p4b-02b146.parameter-list-starts-with-v1.prefix-check";

/// Fail-closed error while checking the prefix relation of two list values.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListStartsWithErrorV1 {
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

/// Check whether the trimmed items of `value` begin with the trimmed items
/// of `prefix` (element-wise byte equality).
pub fn list_starts_with_v1(
    value: &AmiParameterValueV1,
    prefix: &AmiParameterValueV1,
) -> Result<bool, ParameterListStartsWithErrorV1> {
    if value.parameter_type() != AmiParameterTypeV1::List
        || prefix.parameter_type() != AmiParameterTypeV1::List
    {
        return Err(ParameterListStartsWithErrorV1::NotAList);
    }
    let value_items =
        list_items(value.value_token()).ok_or(ParameterListStartsWithErrorV1::MalformedList)?;
    let prefix_items =
        list_items(prefix.value_token()).ok_or(ParameterListStartsWithErrorV1::MalformedList)?;
    if prefix_items.len() > value_items.len() {
        return Ok(false);
    }
    Ok(value_items
        .iter()
        .zip(prefix_items.iter())
        .all(|(candidate, query)| candidate == query))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    #[test]
    fn prefix_holds() {
        let v = value("channels", "List", "(a, b, c, d)");
        let p = value("prefix", "List", "(a, b)");
        assert_eq!(list_starts_with_v1(&v, &p), Ok(true));
    }

    #[test]
    fn full_value_is_its_own_prefix() {
        let v = value("channels", "List", "(a, b)");
        let p = value("prefix", "List", "(a, b)");
        assert_eq!(list_starts_with_v1(&v, &p), Ok(true));
    }

    #[test]
    fn mismatched_prefix_is_false() {
        let v = value("channels", "List", "(a, b, c)");
        let p = value("prefix", "List", "(a, x)");
        assert_eq!(list_starts_with_v1(&v, &p), Ok(false));
    }

    #[test]
    fn longer_prefix_is_false() {
        let v = value("channels", "List", "(a, b)");
        let p = value("prefix", "List", "(a, b, c)");
        assert_eq!(list_starts_with_v1(&v, &p), Ok(false));
    }

    #[test]
    fn prefix_non_list_fails_closed() {
        let v = value("channels", "List", "(a)");
        let p = value("gain", "Float", "0.5");
        assert_eq!(
            list_starts_with_v1(&v, &p),
            Err(ParameterListStartsWithErrorV1::NotAList)
        );
    }

    #[test]
    fn spacing_is_canonicalized() {
        let v = value("channels", "List", "( a , b , c )");
        let p = value("prefix", "List", "(a, b)");
        assert_eq!(list_starts_with_v1(&v, &p), Ok(true));
    }
}
