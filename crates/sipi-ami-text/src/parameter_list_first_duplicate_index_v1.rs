//! AMI parameter list first-duplicate index core (P4B-02b138).
//!
//! Locates the first repeating position of the trimmed items of a validated
//! List-typed `AmiParameterValueV1` under the P4B-02b1 list rule
//! (`(item, item, ...)`, items trimmed, non-empty):
//! `parameter_list_first_duplicate_index_v1` returns the smallest 0-based
//! index whose trimmed item equals some earlier trimmed item (raw byte
//! equality, per the P4B-02b0 raw-byte binding). This is the repeat-position
//! companion of 02b110 index-of (first query match) and of 02b136
//! duplicate-item counting (the duplicate count is positive exactly when a
//! first duplicate index exists).
//!
//! Fail-closed: a non-List value yields `NotAList`; a token that does not
//! match the List shape yields `MalformedList` (unreachable for values built
//! via `AmiParameterValueV1::try_new`, kept defensive instead of panicking);
//! a list with no repeating item yields `NoDuplicate` (never conflated with
//! the valid index 0).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: first repeating position.
pub const PARAMETER_LIST_FIRST_DUPLICATE_INDEX_POLICY_V1: &str =
    "sipi.p4b-02b138.parameter-list-first-duplicate-index-v1.first-duplicate-position";

/// Fail-closed error while locating the first duplicate of one list value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListFirstDuplicateIndexErrorV1 {
    /// The value's declared type is not List.
    NotAList,
    /// The token does not match the List shape (defensive; unreachable for
    /// values built via `AmiParameterValueV1::try_new`).
    MalformedList,
    /// No trimmed item repeats an earlier one.
    NoDuplicate,
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

/// Return the smallest index whose trimmed item equals an earlier trimmed
/// item of the same List-typed validated value.
pub fn parameter_list_first_duplicate_index_v1(
    value: &AmiParameterValueV1,
) -> Result<usize, ParameterListFirstDuplicateIndexErrorV1> {
    if value.parameter_type() != AmiParameterTypeV1::List {
        return Err(ParameterListFirstDuplicateIndexErrorV1::NotAList);
    }
    let items = list_items(value.value_token())
        .ok_or(ParameterListFirstDuplicateIndexErrorV1::MalformedList)?;
    let mut seen: Vec<String> = Vec::new();
    for (index, item) in items.iter().enumerate() {
        if seen.contains(item) {
            return Ok(index);
        }
        seen.push(item.clone());
    }
    Err(ParameterListFirstDuplicateIndexErrorV1::NoDuplicate)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    #[test]
    fn finds_first_repeating_index() {
        let v = value("channels", "List", "(a, b, a, c)");
        assert_eq!(parameter_list_first_duplicate_index_v1(&v), Ok(2));
    }

    #[test]
    fn adjacent_repeat_is_found() {
        let v = value("channels", "List", "(a, b, b, c)");
        assert_eq!(parameter_list_first_duplicate_index_v1(&v), Ok(2));
    }

    #[test]
    fn all_distinct_fails_closed() {
        let v = value("channels", "List", "(a, b, c)");
        assert_eq!(
            parameter_list_first_duplicate_index_v1(&v),
            Err(ParameterListFirstDuplicateIndexErrorV1::NoDuplicate)
        );
    }

    #[test]
    fn single_item_has_no_duplicate() {
        let v = value("channels", "List", "(x)");
        assert_eq!(
            parameter_list_first_duplicate_index_v1(&v),
            Err(ParameterListFirstDuplicateIndexErrorV1::NoDuplicate)
        );
    }

    #[test]
    fn non_list_fails_closed() {
        let float = value("gain", "Float", "0.5");
        assert_eq!(
            parameter_list_first_duplicate_index_v1(&float),
            Err(ParameterListFirstDuplicateIndexErrorV1::NotAList)
        );
    }

    #[test]
    fn spacing_is_canonicalized() {
        let v = value("channels", "List", "( a , b , a )");
        assert_eq!(parameter_list_first_duplicate_index_v1(&v), Ok(2));
    }
}
