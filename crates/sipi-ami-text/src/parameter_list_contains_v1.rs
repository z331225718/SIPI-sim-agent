//! AMI parameter list item membership core (P4B-02b85).
//!
//! Checks whether a validated List-typed `AmiParameterValueV1` contains a
//! query item under the P4B-02b1 list rule (`(item, item, ...)`, items
//! trimmed, non-empty): `parameter_list_contains_item_v1` returns whether any
//! trimmed item equals the query item exactly (raw byte equality, per the
//! P4B-02b0 raw-byte binding; the query itself is not trimmed). This is the
//! membership companion of 02b83 item counting and 02b84 item access.
//!
//! Fail-closed: a non-List value yields `NotAList`; a token that does not
//! match the List shape yields `MalformedList` (unreachable for values built
//! via `AmiParameterValueV1::try_new`, kept defensive instead of panicking).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: list item membership on a value.
pub const PARAMETER_LIST_CONTAINS_POLICY_V1: &str =
    "sipi.p4b-02b85.parameter-list-contains-v1.list-item-membership";

/// Fail-closed error while checking list membership of a parameter value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListContainsErrorV1 {
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

/// Check whether a List-typed validated value contains the query item.
pub fn parameter_list_contains_item_v1(
    value: &AmiParameterValueV1,
    item: &str,
) -> Result<bool, ParameterListContainsErrorV1> {
    if value.parameter_type() != AmiParameterTypeV1::List {
        return Err(ParameterListContainsErrorV1::NotAList);
    }
    let items = list_items(value.value_token())
        .ok_or(ParameterListContainsErrorV1::MalformedList)?;
    Ok(items.iter().any(|candidate| candidate == item))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    #[test]
    fn contains_exact_item() {
        let v = value("channels", "List", "(a, b, c)");
        assert_eq!(parameter_list_contains_item_v1(&v, "a"), Ok(true));
        assert_eq!(parameter_list_contains_item_v1(&v, "b"), Ok(true));
        assert_eq!(parameter_list_contains_item_v1(&v, "c"), Ok(true));
    }

    #[test]
    fn missing_item_is_false() {
        let v = value("channels", "List", "(a, b, c)");
        assert_eq!(parameter_list_contains_item_v1(&v, "z"), Ok(false));
        assert_eq!(parameter_list_contains_item_v1(&v, "A"), Ok(false));
    }

    #[test]
    fn items_are_trimmed_but_query_is_raw() {
        let v = value("channels", "List", "( a , b )");
        // The stored items are trimmed: "b" is present.
        assert_eq!(parameter_list_contains_item_v1(&v, "b"), Ok(true));
        // The query is not trimmed: " b " (with spaces) is not present.
        assert_eq!(parameter_list_contains_item_v1(&v, " b "), Ok(false));
    }

    #[test]
    fn non_list_fails_closed() {
        let float = value("gain", "Float", "0.5");
        assert_eq!(
            parameter_list_contains_item_v1(&float, "0.5"),
            Err(ParameterListContainsErrorV1::NotAList)
        );
    }

    #[test]
    fn single_item_list() {
        let v = value("channels", "List", "(x)");
        assert_eq!(parameter_list_contains_item_v1(&v, "x"), Ok(true));
        assert_eq!(parameter_list_contains_item_v1(&v, "y"), Ok(false));
    }

    #[test]
    fn membership_matches_typed_equivalence_items() {
        let a = value("channels", "List", "(a, b, c)");
        let b = value("channels", "List", "(a,b,c)");
        for item in ["a", "b", "c", "d"] {
            assert_eq!(
                parameter_list_contains_item_v1(&a, item),
                parameter_list_contains_item_v1(&b, item)
            );
        }
    }
}
