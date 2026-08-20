//! AMI parameter list item remove-all-by-value core (P4B-02b112).
//!
//! Removes every occurrence of a query item from a validated List-typed
//! `AmiParameterValueV1` under the P4B-02b1 list rule (`(item, item, ...)`,
//! items trimmed, non-empty): `remove_all_parameter_list_items_v1` returns
//! the canonical list token whose items are the trimmed items that do not
//! equal the query item exactly (raw byte equality, per the P4B-02b0
//! raw-byte binding; the query itself is not trimmed), re-joined with
//! `", "`. This is the value-based bulk companion of 02b100 index-based
//! removal and of 02b108 occurrence counting (the removed count equals the
//! occurrence count of the query).
//!
//! Fail-closed: a non-List value yields `NotAList`; a token that does not
//! match the List shape yields `MalformedList` (unreachable for values built
//! via `AmiParameterValueV1::try_new`, kept defensive instead of panicking).
//! Removing all items yields the structurally empty token `()` (not a valid
//! 02b1 List value; the operation is total on the token level and does not
//! re-validate, mirroring 02b100 sole-item removal).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: value-based bulk list item removal.
pub const PARAMETER_LIST_REMOVE_ALL_POLICY_V1: &str =
    "sipi.p4b-02b112.parameter-list-remove-all-v1.bulk-removal-by-value";

/// Fail-closed error while removing list items of a parameter value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListRemoveAllErrorV1 {
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

/// Remove every trimmed item equal to the raw query item of a List value.
pub fn remove_all_parameter_list_items_v1(
    value: &AmiParameterValueV1,
    item: &str,
) -> Result<String, ParameterListRemoveAllErrorV1> {
    if value.parameter_type() != AmiParameterTypeV1::List {
        return Err(ParameterListRemoveAllErrorV1::NotAList);
    }
    let items =
        list_items(value.value_token()).ok_or(ParameterListRemoveAllErrorV1::MalformedList)?;
    let kept: Vec<String> = items
        .into_iter()
        .filter(|candidate| candidate.as_str() != item)
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
    fn removes_all_occurrences() {
        let v = value("channels", "List", "(a, b, a, c, a)");
        assert_eq!(
            remove_all_parameter_list_items_v1(&v, "a"),
            Ok("(b, c)".to_string())
        );
    }

    #[test]
    fn no_occurrence_returns_original_items() {
        let v = value("channels", "List", "(a, b)");
        assert_eq!(
            remove_all_parameter_list_items_v1(&v, "z"),
            Ok("(a, b)".to_string())
        );
    }

    #[test]
    fn removing_all_yields_empty_token() {
        let v = value("channels", "List", "(x, x)");
        assert_eq!(
            remove_all_parameter_list_items_v1(&v, "x"),
            Ok("()".to_string())
        );
    }

    #[test]
    fn query_is_raw_but_items_are_trimmed() {
        let v = value("channels", "List", "( a , b )");
        assert_eq!(
            remove_all_parameter_list_items_v1(&v, "a"),
            Ok("(b)".to_string())
        );
        assert_eq!(
            remove_all_parameter_list_items_v1(&v, " a "),
            Ok("(a, b)".to_string())
        );
    }

    #[test]
    fn non_list_fails_closed() {
        let float = value("gain", "Float", "0.5");
        assert_eq!(
            remove_all_parameter_list_items_v1(&float, "0.5"),
            Err(ParameterListRemoveAllErrorV1::NotAList)
        );
    }

    #[test]
    fn single_item_removal_yields_empty_token() {
        let v = value("channels", "List", "(x)");
        assert_eq!(
            remove_all_parameter_list_items_v1(&v, "x"),
            Ok("()".to_string())
        );
    }
}
