//! AMI parameter list multiset containment core (P4B-02b153).
//!
//! Checks whether one validated List-typed `AmiParameterValueV1` value
//! contains another as a multiset sub-multiset under the P4B-02b1 list rule
//! (`(item, item, ...)`, items trimmed, non-empty):
//! `list_contains_multiset_v1` returns whether every trimmed item of the
//! query value occurs at least as many times in the host value (raw byte
//! equality, per the P4B-02b0 raw-byte binding; order-insensitive). This is
//! the multiset companion of 02b152 multiset equality (mutual containment is
//! equality) and of 02b140 multi-remove-all (the relative complement of the
//! query in the host is empty exactly when containment holds).
//!
//! Fail-closed: either value not declared List yields `NotAList`; either
//! token not matching the List shape yields `MalformedList` (unreachable for
//! values built via `AmiParameterValueV1::try_new`, kept defensive instead
//! of panicking).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: multiset sub-multiset check.
pub const PARAMETER_LIST_CONTAINS_MULTISET_POLICY_V1: &str =
    "sipi.p4b-02b153.parameter-list-contains-multiset-v1.multiset-containment";

/// Fail-closed error while checking multiset containment of two list values.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListContainsMultisetErrorV1 {
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

/// Check whether the query value is a multiset sub-multiset of the host value
/// (every query item count is at most the host count, byte equality).
pub fn list_contains_multiset_v1(
    host: &AmiParameterValueV1,
    query: &AmiParameterValueV1,
) -> Result<bool, ParameterListContainsMultisetErrorV1> {
    if host.parameter_type() != AmiParameterTypeV1::List
        || query.parameter_type() != AmiParameterTypeV1::List
    {
        return Err(ParameterListContainsMultisetErrorV1::NotAList);
    }
    let host_items = list_items(host.value_token())
        .ok_or(ParameterListContainsMultisetErrorV1::MalformedList)?;
    let query_items = list_items(query.value_token())
        .ok_or(ParameterListContainsMultisetErrorV1::MalformedList)?;
    if query_items.len() > host_items.len() {
        return Ok(false);
    }
    for item in &query_items {
        let query_count = query_items
            .iter()
            .filter(|candidate| *candidate == item)
            .count();
        let host_count = host_items
            .iter()
            .filter(|candidate| *candidate == item)
            .count();
        if query_count > host_count {
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
    fn sub_multiset_contained() {
        let host = value("host", "List", "(a, b, a, c)");
        let query = value("query", "List", "(a, a, c)");
        assert_eq!(list_contains_multiset_v1(&host, &query), Ok(true));
    }

    #[test]
    fn count_exceeded_is_false() {
        let host = value("host", "List", "(a, b, a)");
        let query = value("query", "List", "(a, a, a)");
        assert_eq!(list_contains_multiset_v1(&host, &query), Ok(false));
    }

    #[test]
    fn missing_item_is_false() {
        let host = value("host", "List", "(a, b)");
        let query = value("query", "List", "(a, c)");
        assert_eq!(list_contains_multiset_v1(&host, &query), Ok(false));
    }

    #[test]
    fn equal_values_contained() {
        let host = value("host", "List", "(a, b)");
        let query = value("query", "List", "(b, a)");
        assert_eq!(list_contains_multiset_v1(&host, &query), Ok(true));
    }

    #[test]
    fn query_non_list_fails_closed() {
        let host = value("host", "List", "(a)");
        let query = value("gain", "Float", "0.5");
        assert_eq!(
            list_contains_multiset_v1(&host, &query),
            Err(ParameterListContainsMultisetErrorV1::NotAList)
        );
    }

    #[test]
    fn spacing_is_canonicalized() {
        let host = value("host", "List", "( a , b , a )");
        let query = value("query", "List", "(a, a)");
        assert_eq!(list_contains_multiset_v1(&host, &query), Ok(true));
    }
}
