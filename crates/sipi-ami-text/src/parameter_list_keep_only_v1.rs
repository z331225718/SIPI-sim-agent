//! AMI parameter list item keep-only-by-value core (P4B-02b113).
//!
//! Keeps every occurrence of a query item in a validated List-typed
//! `AmiParameterValueV1` under the P4B-02b1 list rule (`(item, item, ...)`,
//! items trimmed, non-empty): `keep_only_parameter_list_items_v1` returns
//! the canonical list token whose items are the trimmed items that equal the
//! query item exactly (raw byte equality, per the P4B-02b0 raw-byte binding;
//! the query itself is not trimmed), re-joined with `", "`. This is the
//! retain inverse of 02b112 remove-all-by-value and of 02b108 occurrence
//! counting (the kept count equals the occurrence count of the query).
//!
//! Fail-closed: a non-List value yields `NotAList`; a token that does not
//! match the List shape yields `MalformedList` (unreachable for values built
//! via `AmiParameterValueV1::try_new`, kept defensive instead of panicking).
//! Keeping no items yields the structurally empty token `()` (not a valid
//! 02b1 List value; the operation is total on the token level and does not
//! re-validate, mirroring 02b100 sole-item removal).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: value-based retain of list items.
pub const PARAMETER_LIST_KEEP_ONLY_POLICY_V1: &str =
    "sipi.p4b-02b113.parameter-list-keep-only-v1.retain-by-value";

/// Fail-closed error while retaining list items of a parameter value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListKeepOnlyErrorV1 {
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

/// Keep every trimmed item equal to the raw query item of a List value.
pub fn keep_only_parameter_list_items_v1(
    value: &AmiParameterValueV1,
    item: &str,
) -> Result<String, ParameterListKeepOnlyErrorV1> {
    if value.parameter_type() != AmiParameterTypeV1::List {
        return Err(ParameterListKeepOnlyErrorV1::NotAList);
    }
    let items = list_items(value.value_token())
        .ok_or(ParameterListKeepOnlyErrorV1::MalformedList)?;
    let kept: Vec<String> = items
        .into_iter()
        .filter(|candidate| candidate.as_str() == item)
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
    fn keeps_only_matching() {
        let v = value("channels", "List", "(a, b, a, c, a)");
        assert_eq!(
            keep_only_parameter_list_items_v1(&v, "a"),
            Ok("(a, a, a)".to_string())
        );
    }

    #[test]
    fn no_match_yields_empty_token() {
        let v = value("channels", "List", "(a, b)");
        assert_eq!(
            keep_only_parameter_list_items_v1(&v, "z"),
            Ok("()".to_string())
        );
    }

    #[test]
    fn keeps_all_when_all_match() {
        let v = value("channels", "List", "(x, x)");
        assert_eq!(
            keep_only_parameter_list_items_v1(&v, "x"),
            Ok("(x, x)".to_string())
        );
    }

    #[test]
    fn query_is_raw_but_items_are_trimmed() {
        let v = value("channels", "List", "( a , b )");
        assert_eq!(
            keep_only_parameter_list_items_v1(&v, "a"),
            Ok("(a)".to_string())
        );
        assert_eq!(
            keep_only_parameter_list_items_v1(&v, " a "),
            Ok("()".to_string())
        );
    }

    #[test]
    fn non_list_fails_closed() {
        let float = value("gain", "Float", "0.5");
        assert_eq!(
            keep_only_parameter_list_items_v1(&float, "0.5"),
            Err(ParameterListKeepOnlyErrorV1::NotAList)
        );
    }

    #[test]
    fn kept_count_matches_occurrence_count() {
        let v = value("channels", "List", "(x, y, x)");
        assert_eq!(
            keep_only_parameter_list_items_v1(&v, "x"),
            Ok("(x, x)".to_string())
        );
    }
}
