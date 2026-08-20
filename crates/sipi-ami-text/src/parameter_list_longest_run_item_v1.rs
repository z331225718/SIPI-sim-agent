//! AMI parameter list longest run item core (P4B-02b170).
//!
//! Returns the trimmed item of the earliest maximal run achieving the
//! longest length within a validated List-typed `AmiParameterValueV1` value
//! under the P4B-02b1 list rule (`(item, item, ...)`, items trimmed,
//! non-empty): `parameter_list_longest_run_item_v1` scans the maximal runs
//! of equal adjacent trimmed items (raw byte equality, per the P4B-02b0
//! raw-byte binding) left to right and returns the item of the first run
//! whose length equals the maximum run length. The list is non-empty by rule
//! so at least one run exists. This is the item companion of 02b120
//! longest-run (which returns the length) and of 02b119 run-length-encode
//! (the longest run entry's item).
//!
//! Fail-closed: the value not declared List yields `NotAList`; the token not
//! matching the List shape yields `MalformedList` (unreachable for values
//! built via `AmiParameterValueV1::try_new`, kept defensive instead of
//! panicking).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: list value longest run item.
pub const PARAMETER_LIST_LONGEST_RUN_ITEM_POLICY_V1: &str =
    "sipi.p4b-02b170.parameter-list-longest-run-item-v1.longest-run-item";

/// Fail-closed error while computing the longest run item of a list value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListLongestRunItemErrorV1 {
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

/// Return the trimmed item of the earliest maximal run achieving the longest
/// length within a List-typed value (raw byte equality, left-to-right scan).
pub fn parameter_list_longest_run_item_v1(
    value: &AmiParameterValueV1,
) -> Result<String, ParameterListLongestRunItemErrorV1> {
    if value.parameter_type() != AmiParameterTypeV1::List {
        return Err(ParameterListLongestRunItemErrorV1::NotAList);
    }
    let items =
        list_items(value.value_token()).ok_or(ParameterListLongestRunItemErrorV1::MalformedList)?;
    let mut best_item = &items[0];
    let mut best_len = 1usize;
    let mut current_item = &items[0];
    let mut current_len = 1usize;
    for item in &items[1..] {
        if item == current_item {
            current_len += 1;
        } else {
            if current_len > best_len {
                best_len = current_len;
                best_item = current_item;
            }
            current_item = item;
            current_len = 1;
        }
    }
    if current_len > best_len {
        best_item = current_item;
    }
    Ok(best_item.clone())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    #[test]
    fn returns_longest_run_item() {
        let v = value("param", "List", "(a, b, b, b, c)");
        assert_eq!(parameter_list_longest_run_item_v1(&v), Ok("b".to_string()));
    }

    #[test]
    fn tie_prefers_earliest_run() {
        let v = value("param", "List", "(a, a, b, b, c)");
        assert_eq!(parameter_list_longest_run_item_v1(&v), Ok("a".to_string()));
    }

    #[test]
    fn all_distinct_first_item_wins_tie() {
        let v = value("param", "List", "(c, a, b)");
        assert_eq!(parameter_list_longest_run_item_v1(&v), Ok("c".to_string()));
    }

    #[test]
    fn single_item_is_its_own_longest_run() {
        let v = value("param", "List", "(x)");
        assert_eq!(parameter_list_longest_run_item_v1(&v), Ok("x".to_string()));
    }

    #[test]
    fn spacing_is_canonicalized() {
        let v = value("param", "List", "( a , b , b )");
        assert_eq!(parameter_list_longest_run_item_v1(&v), Ok("b".to_string()));
    }

    #[test]
    fn non_list_fails_closed() {
        let v = value("gain", "Float", "0.5");
        assert_eq!(
            parameter_list_longest_run_item_v1(&v),
            Err(ParameterListLongestRunItemErrorV1::NotAList)
        );
    }
}
