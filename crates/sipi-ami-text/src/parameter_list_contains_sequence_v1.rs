//! AMI parameter list sequence containment core (P4B-02b157).
//!
//! Checks whether the trimmed items of a validated List-typed
//! `AmiParameterValueV1` query value appear as a contiguous subsequence
//! (window) of the trimmed items of another validated List-typed host value
//! under the P4B-02b1 list rule (`(item, item, ...)`, items trimmed,
//! non-empty): `list_contains_sequence_v1` returns whether the host has a
//! window equal to the query's trimmed items element-wise (raw byte
//! equality, per the P4B-02b0 raw-byte binding). A query longer than the host
//! is never contained. This is the value-level companion of 02b127
//! raw-query sublist containment (the host contains the query's token
//! sequence as a window).
//!
//! Fail-closed: either value not declared List yields `NotAList`; either
//! token not matching the List shape yields `MalformedList` (unreachable for
//! values built via `AmiParameterValueV1::try_new`, kept defensive instead
//! of panicking).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: value-level contiguous sequence check.
pub const PARAMETER_LIST_CONTAINS_SEQUENCE_POLICY_V1: &str =
    "sipi.p4b-02b157.parameter-list-contains-sequence-v1.sequence-containment";

/// Fail-closed error while checking sequence containment of two list values.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListContainsSequenceErrorV1 {
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

/// Check whether the host's trimmed items contain the query's trimmed items
/// as a contiguous window (element-wise byte equality).
pub fn list_contains_sequence_v1(
    host: &AmiParameterValueV1,
    query: &AmiParameterValueV1,
) -> Result<bool, ParameterListContainsSequenceErrorV1> {
    if host.parameter_type() != AmiParameterTypeV1::List
        || query.parameter_type() != AmiParameterTypeV1::List
    {
        return Err(ParameterListContainsSequenceErrorV1::NotAList);
    }
    let host_items = list_items(host.value_token())
        .ok_or(ParameterListContainsSequenceErrorV1::MalformedList)?;
    let query_items = list_items(query.value_token())
        .ok_or(ParameterListContainsSequenceErrorV1::MalformedList)?;
    if query_items.len() > host_items.len() {
        return Ok(false);
    }
    Ok(host_items
        .windows(query_items.len())
        .any(|window| window.iter().zip(query_items.iter()).all(|(h, q)| h == q)))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    #[test]
    fn contiguous_sequence_contained() {
        let host = value("host", "List", "(a, b, c, d)");
        let query = value("query", "List", "(b, c)");
        assert_eq!(list_contains_sequence_v1(&host, &query), Ok(true));
    }

    #[test]
    fn non_contiguous_is_false() {
        let host = value("host", "List", "(a, x, b, y, c)");
        let query = value("query", "List", "(a, b, c)");
        assert_eq!(list_contains_sequence_v1(&host, &query), Ok(false));
    }

    #[test]
    fn longer_query_is_false() {
        let host = value("host", "List", "(a, b)");
        let query = value("query", "List", "(a, b, c)");
        assert_eq!(list_contains_sequence_v1(&host, &query), Ok(false));
    }

    #[test]
    fn equal_values_contained() {
        let host = value("host", "List", "(a, b)");
        let query = value("query", "List", "(a, b)");
        assert_eq!(list_contains_sequence_v1(&host, &query), Ok(true));
    }

    #[test]
    fn query_non_list_fails_closed() {
        let host = value("host", "List", "(a)");
        let query = value("gain", "Float", "0.5");
        assert_eq!(
            list_contains_sequence_v1(&host, &query),
            Err(ParameterListContainsSequenceErrorV1::NotAList)
        );
    }

    #[test]
    fn spacing_is_canonicalized() {
        let host = value("host", "List", "( a , b , c )");
        let query = value("query", "List", "(b, c)");
        assert_eq!(list_contains_sequence_v1(&host, &query), Ok(true));
    }
}
