//! AMI parameter list run count core (P4B-02b168).
//!
//! Returns the number of maximal runs of equal adjacent trimmed items of a
//! validated List-typed `AmiParameterValueV1` value under the P4B-02b1 list
//! rule (`(item, item, ...)`, items trimmed, non-empty):
//! `parameter_list_run_count_v1` counts the maximal runs (raw byte equality,
//! per the P4B-02b0 raw-byte binding); the list is non-empty by rule so the
//! run count is at least 1. This is the run-count companion of 02b119
//! run-length-encode (the run count equals the number of RLE entries) and of
//! 02b120 longest-run (the longest run length is at most the run count in the
//! all-distinct case, exactly 1).
//!
//! Fail-closed: the value not declared List yields `NotAList`; the token not
//! matching the List shape yields `MalformedList` (unreachable for values
//! built via `AmiParameterValueV1::try_new`, kept defensive instead of
//! panicking).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: list value run count.
pub const PARAMETER_LIST_RUN_COUNT_POLICY_V1: &str =
    "sipi.p4b-02b168.parameter-list-run-count-v1.run-count";

/// Fail-closed error while computing the run count of a list value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListRunCountErrorV1 {
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

/// Return the number of maximal runs of equal adjacent trimmed items of a
/// List-typed value (raw byte equality); the list is non-empty by rule so
/// the run count is at least 1.
pub fn parameter_list_run_count_v1(
    value: &AmiParameterValueV1,
) -> Result<usize, ParameterListRunCountErrorV1> {
    if value.parameter_type() != AmiParameterTypeV1::List {
        return Err(ParameterListRunCountErrorV1::NotAList);
    }
    let items = list_items(value.value_token())
        .ok_or(ParameterListRunCountErrorV1::MalformedList)?;
    let mut runs = 1usize;
    for pair in items.windows(2) {
        if pair[0] != pair[1] {
            runs += 1;
        }
    }
    Ok(runs)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    #[test]
    fn single_run() {
        let v = value("param", "List", "(a, a, a)");
        assert_eq!(parameter_list_run_count_v1(&v), Ok(1));
    }

    #[test]
    fn multiple_runs() {
        let v = value("param", "List", "(a, a, b, b, c, a)");
        assert_eq!(parameter_list_run_count_v1(&v), Ok(4));
    }

    #[test]
    fn all_distinct_each_item_own_run() {
        let v = value("param", "List", "(c, a, b)");
        assert_eq!(parameter_list_run_count_v1(&v), Ok(3));
    }

    #[test]
    fn single_item_one_run() {
        let v = value("param", "List", "(x)");
        assert_eq!(parameter_list_run_count_v1(&v), Ok(1));
    }

    #[test]
    fn spacing_is_canonicalized() {
        let v = value("param", "List", "( a , a , b )");
        assert_eq!(parameter_list_run_count_v1(&v), Ok(2));
    }

    #[test]
    fn non_list_fails_closed() {
        let v = value("gain", "Float", "0.5");
        assert_eq!(
            parameter_list_run_count_v1(&v),
            Err(ParameterListRunCountErrorV1::NotAList)
        );
    }
}
