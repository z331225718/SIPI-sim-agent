//! AMI parameter list majority item core (P4B-02b174).
//!
//! Returns the majority trimmed item of a validated List-typed
//! `AmiParameterValueV1` value under the P4B-02b1 list rule
//! (`(item, item, ...)`, items trimmed, non-empty):
//! `parameter_list_majority_item_v1` returns the distinct trimmed item whose
//! occurrence count is strictly greater than half the item count (raw byte
//! equality, per the P4B-02b0 raw-byte binding). At most one such item can
//! exist; a single-item list trivially has its item as the majority. This is
//! the strict-majority companion of 02b165 mode items (the mode is the
//! majority when it exceeds half the count) and of 02b121 frequency.
//!
//! Fail-closed: the value not declared List yields `NotAList`; the token not
//! matching the List shape yields `MalformedList` (unreachable for values
//! built via `AmiParameterValueV1::try_new`, kept defensive instead of
//! panicking); no item exceeding half the count yields `NoMajority`.

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: list value majority item.
pub const PARAMETER_LIST_MAJORITY_ITEM_POLICY_V1: &str =
    "sipi.p4b-02b174.parameter-list-majority-item-v1.majority-item";

/// Fail-closed error while computing the majority item of a list value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListMajorityItemErrorV1 {
    /// The value's declared type is not List.
    NotAList,
    /// The token does not match the List shape (defensive; unreachable for
    /// values built via `AmiParameterValueV1::try_new`).
    MalformedList,
    /// No item occurs strictly more than half the item count.
    NoMajority,
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

/// Return the majority trimmed item of a List-typed value: the distinct item
/// whose occurrence count is strictly greater than half the item count (raw
/// byte equality); a single-item list is trivially its own majority.
pub fn parameter_list_majority_item_v1(
    value: &AmiParameterValueV1,
) -> Result<String, ParameterListMajorityItemErrorV1> {
    if value.parameter_type() != AmiParameterTypeV1::List {
        return Err(ParameterListMajorityItemErrorV1::NotAList);
    }
    let items =
        list_items(value.value_token()).ok_or(ParameterListMajorityItemErrorV1::MalformedList)?;
    let item_count = items.len();
    let mut counts: Vec<(String, usize)> = Vec::new();
    for item in &items {
        match counts.iter_mut().find(|(existing, _)| existing == item) {
            Some((_, count)) => *count += 1,
            None => counts.push((item.clone(), 1)),
        }
    }
    for (item, count) in &counts {
        if *count * 2 > item_count {
            return Ok(item.clone());
        }
    }
    Err(ParameterListMajorityItemErrorV1::NoMajority)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    #[test]
    fn returns_majority_item() {
        let v = value("param", "List", "(b, a, b, b, c)");
        assert_eq!(parameter_list_majority_item_v1(&v), Ok("b".to_string()));
    }

    #[test]
    fn single_item_is_its_own_majority() {
        let v = value("param", "List", "(x)");
        assert_eq!(parameter_list_majority_item_v1(&v), Ok("x".to_string()));
    }

    #[test]
    fn tie_is_not_majority() {
        let v = value("param", "List", "(a, a, b, b)");
        assert_eq!(
            parameter_list_majority_item_v1(&v),
            Err(ParameterListMajorityItemErrorV1::NoMajority)
        );
    }

    #[test]
    fn all_distinct_no_majority() {
        let v = value("param", "List", "(c, a, b)");
        assert_eq!(
            parameter_list_majority_item_v1(&v),
            Err(ParameterListMajorityItemErrorV1::NoMajority)
        );
    }

    #[test]
    fn spacing_is_canonicalized() {
        let v = value("param", "List", "( b , a , b , b )");
        assert_eq!(parameter_list_majority_item_v1(&v), Ok("b".to_string()));
    }

    #[test]
    fn non_list_fails_closed() {
        let v = value("gain", "Float", "0.5");
        assert_eq!(
            parameter_list_majority_item_v1(&v),
            Err(ParameterListMajorityItemErrorV1::NotAList)
        );
    }
}
