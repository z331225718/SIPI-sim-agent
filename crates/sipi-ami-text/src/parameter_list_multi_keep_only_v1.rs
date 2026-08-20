//! AMI parameter list multi-value keep-only core (P4B-02b141).
//!
//! Keeps every occurrence of every query item in a validated List-typed
//! `AmiParameterValueV1` under the P4B-02b1 list rule (`(item, item, ...)`,
//! items trimmed, non-empty): `keep_only_parameter_list_items_multi_v1`
//! returns the canonical list token whose items are the trimmed items that
//! equal some query item exactly (raw byte equality, per the P4B-02b0
//! raw-byte binding; query items are not trimmed), re-joined with `", "`. An
//! empty query set keeps nothing. This is the batch retain companion of
//! 02b113 single-query keep-only and the inverse of 02b140 multi-remove-all.
//!
//! Fail-closed: a non-List value yields `NotAList`; a token that does not
//! match the List shape yields `MalformedList` (unreachable for values built
//! via `AmiParameterValueV1::try_new`, kept defensive instead of panicking).
//! Keeping no items yields the structurally empty token `()` (not a valid
//! 02b1 List value; the operation is total on the token level and does not
//! re-validate, mirroring 02b100 sole-item removal).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: batch retain by query set.
pub const PARAMETER_LIST_MULTI_KEEP_ONLY_POLICY_V1: &str =
    "sipi.p4b-02b141.parameter-list-multi-keep-only-v1.batch-retain";

/// Fail-closed error while retaining list items of a parameter value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListMultiKeepOnlyErrorV1 {
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

/// Keep every trimmed item equal to any query item of a List-typed value.
pub fn keep_only_parameter_list_items_multi_v1(
    value: &AmiParameterValueV1,
    items: &[&str],
) -> Result<String, ParameterListMultiKeepOnlyErrorV1> {
    if value.parameter_type() != AmiParameterTypeV1::List {
        return Err(ParameterListMultiKeepOnlyErrorV1::NotAList);
    }
    let list = list_items(value.value_token())
        .ok_or(ParameterListMultiKeepOnlyErrorV1::MalformedList)?;
    let kept: Vec<String> = list
        .into_iter()
        .filter(|candidate| items.contains(&candidate.as_str()))
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
    fn keeps_only_query_items() {
        let v = value("channels", "List", "(a, b, a, c, b)");
        let query = ["a", "b"];
        assert_eq!(
            keep_only_parameter_list_items_multi_v1(&v, &query),
            Ok("(a, b, a, b)".to_string())
        );
    }

    #[test]
    fn empty_query_set_keeps_nothing() {
        let v = value("channels", "List", "(a, b)");
        let query: [&str; 0] = [];
        assert_eq!(
            keep_only_parameter_list_items_multi_v1(&v, &query),
            Ok("()".to_string())
        );
    }

    #[test]
    fn keeping_all_preserves_order() {
        let v = value("channels", "List", "(x, y, x)");
        let query = ["x", "y"];
        assert_eq!(
            keep_only_parameter_list_items_multi_v1(&v, &query),
            Ok("(x, y, x)".to_string())
        );
    }

    #[test]
    fn no_match_yields_empty_token() {
        let v = value("channels", "List", "(a, b)");
        let query = ["z"];
        assert_eq!(
            keep_only_parameter_list_items_multi_v1(&v, &query),
            Ok("()".to_string())
        );
    }

    #[test]
    fn non_list_fails_closed() {
        let float = value("gain", "Float", "0.5");
        let query = ["0.5"];
        assert_eq!(
            keep_only_parameter_list_items_multi_v1(&float, &query),
            Err(ParameterListMultiKeepOnlyErrorV1::NotAList)
        );
    }

    #[test]
    fn spacing_is_canonicalized() {
        let v = value("channels", "List", "( a , a , b )");
        let query = ["a"];
        assert_eq!(
            keep_only_parameter_list_items_multi_v1(&v, &query),
            Ok("(a, a)".to_string())
        );
    }
}
