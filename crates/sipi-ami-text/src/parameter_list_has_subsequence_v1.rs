//! AMI parameter list subsequence check core (P4B-02b144).
//!
//! Checks whether a query sequence of raw items appears as a subsequence of
//! the trimmed items of a validated List-typed `AmiParameterValueV1` under
//! the P4B-02b1 list rule (`(item, item, ...)`, items trimmed, non-empty):
//! `parameter_list_has_subsequence_v1` returns whether every query item can
//! be matched in order (not necessarily contiguously) by raw byte equality
//! (per the P4B-02b0 raw-byte binding; query items are not trimmed). An empty
//! query sequence is vacuously a subsequence. This is the order-preserving
//! companion of 02b127 contiguous sublist containment and of 02b142 LCS
//! length (the LCS length equals the query length exactly when the query is a
//! subsequence).
//!
//! Fail-closed: a non-List value yields `NotAList`; a token that does not
//! match the List shape yields `MalformedList` (unreachable for values built
//! via `AmiParameterValueV1::try_new`, kept defensive instead of panicking).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: order-preserving subsequence check.
pub const PARAMETER_LIST_HAS_SUBSEQUENCE_POLICY_V1: &str =
    "sipi.p4b-02b144.parameter-list-has-subsequence-v1.subsequence-check";

/// Fail-closed error while checking subsequence membership of a list value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListHasSubsequenceErrorV1 {
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

/// Check whether the query sequence appears as a subsequence of the trimmed
/// items of a List-typed validated value (order-preserving, element-wise byte
/// equality, not necessarily contiguous).
pub fn parameter_list_has_subsequence_v1(
    value: &AmiParameterValueV1,
    query: &[&str],
) -> Result<bool, ParameterListHasSubsequenceErrorV1> {
    if value.parameter_type() != AmiParameterTypeV1::List {
        return Err(ParameterListHasSubsequenceErrorV1::NotAList);
    }
    let items = list_items(value.value_token())
        .ok_or(ParameterListHasSubsequenceErrorV1::MalformedList)?;
    let mut cursor = 0usize;
    for item in &items {
        if cursor < query.len() && item.as_str() == query[cursor] {
            cursor += 1;
        }
    }
    Ok(cursor == query.len())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    #[test]
    fn non_contiguous_subsequence_is_found() {
        let v = value("channels", "List", "(a, x, b, y, c)");
        let query = ["a", "b", "c"];
        assert_eq!(
            parameter_list_has_subsequence_v1(&v, &query),
            Ok(true)
        );
    }

    #[test]
    fn out_of_order_query_is_false() {
        let v = value("channels", "List", "(a, b, c)");
        let query = ["c", "a"];
        assert_eq!(
            parameter_list_has_subsequence_v1(&v, &query),
            Ok(false)
        );
    }

    #[test]
    fn missing_item_is_false() {
        let v = value("channels", "List", "(a, b)");
        let query = ["a", "z"];
        assert_eq!(
            parameter_list_has_subsequence_v1(&v, &query),
            Ok(false)
        );
    }

    #[test]
    fn empty_query_is_vacuous() {
        let v = value("channels", "List", "(a, b)");
        let query: [&str; 0] = [];
        assert_eq!(
            parameter_list_has_subsequence_v1(&v, &query),
            Ok(true)
        );
    }

    #[test]
    fn non_list_fails_closed() {
        let float = value("gain", "Float", "0.5");
        let query = ["0.5"];
        assert_eq!(
            parameter_list_has_subsequence_v1(&float, &query),
            Err(ParameterListHasSubsequenceErrorV1::NotAList)
        );
    }

    #[test]
    fn items_are_trimmed_but_query_is_raw() {
        let v = value("channels", "List", "( a , b , c )");
        let query = ["a", "c"];
        assert_eq!(
            parameter_list_has_subsequence_v1(&v, &query),
            Ok(true)
        );
        let spaced = [" a ", "c"];
        assert_eq!(
            parameter_list_has_subsequence_v1(&v, &spaced),
            Ok(false)
        );
    }
}
