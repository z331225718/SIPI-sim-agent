//! AMI parameter list multi-value removal core (P4B-02b140).
//!
//! Removes every occurrence of every query item from a validated List-typed
//! `AmiParameterValueV1` under the P4B-02b1 list rule (`(item, item, ...)`,
//! items trimmed, non-empty): `remove_all_parameter_list_items_multi_v1`
//! returns the canonical list token whose items are the trimmed items that do
//! not equal any query item exactly (raw byte equality, per the P4B-02b0
//! raw-byte binding; query items are not trimmed), re-joined with `", "`.
//! An empty query set removes nothing. This is the batch companion of 02b112
//! single-query remove-all and of 02b99 indexed replace.
//!
//! Fail-closed: a non-List value yields `NotAList`; a token that does not
//! match the List shape yields `MalformedList` (unreachable for values built
//! via `AmiParameterValueV1::try_new`, kept defensive instead of panicking).
//! Removing all items yields the structurally empty token `()` (not a valid
//! 02b1 List value; the operation is total on the token level and does not
//! re-validate, mirroring 02b100 sole-item removal).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: batch removal by query set.
pub const PARAMETER_LIST_MULTI_REMOVE_ALL_POLICY_V1: &str =
    "sipi.p4b-02b140.parameter-list-multi-remove-all-v1.batch-removal";

/// Fail-closed error while removing list items of a parameter value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListMultiRemoveAllErrorV1 {
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

/// Remove every trimmed item equal to any query item of a List-typed value.
pub fn remove_all_parameter_list_items_multi_v1(
    value: &AmiParameterValueV1,
    items: &[&str],
) -> Result<String, ParameterListMultiRemoveAllErrorV1> {
    if value.parameter_type() != AmiParameterTypeV1::List {
        return Err(ParameterListMultiRemoveAllErrorV1::NotAList);
    }
    let list =
        list_items(value.value_token()).ok_or(ParameterListMultiRemoveAllErrorV1::MalformedList)?;
    let kept: Vec<String> = list
        .into_iter()
        .filter(|candidate| !items.contains(&candidate.as_str()))
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
    fn removes_all_query_items() {
        let v = value("channels", "List", "(a, b, a, c, b)");
        let query = ["a", "b"];
        assert_eq!(
            remove_all_parameter_list_items_multi_v1(&v, &query),
            Ok("(c)".to_string())
        );
    }

    #[test]
    fn empty_query_set_removes_nothing() {
        let v = value("channels", "List", "(a, b)");
        let query: [&str; 0] = [];
        assert_eq!(
            remove_all_parameter_list_items_multi_v1(&v, &query),
            Ok("(a, b)".to_string())
        );
    }

    #[test]
    fn removing_all_yields_empty_token() {
        let v = value("channels", "List", "(x, y)");
        let query = ["x", "y"];
        assert_eq!(
            remove_all_parameter_list_items_multi_v1(&v, &query),
            Ok("()".to_string())
        );
    }

    #[test]
    fn no_match_returns_original_items() {
        let v = value("channels", "List", "(a, b)");
        let query = ["z"];
        assert_eq!(
            remove_all_parameter_list_items_multi_v1(&v, &query),
            Ok("(a, b)".to_string())
        );
    }

    #[test]
    fn non_list_fails_closed() {
        let float = value("gain", "Float", "0.5");
        let query = ["0.5"];
        assert_eq!(
            remove_all_parameter_list_items_multi_v1(&float, &query),
            Err(ParameterListMultiRemoveAllErrorV1::NotAList)
        );
    }

    #[test]
    fn spacing_is_canonicalized() {
        let v = value("channels", "List", "( a , a , b )");
        let query = ["a"];
        assert_eq!(
            remove_all_parameter_list_items_multi_v1(&v, &query),
            Ok("(b)".to_string())
        );
    }
}
