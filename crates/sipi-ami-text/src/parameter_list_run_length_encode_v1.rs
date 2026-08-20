//! AMI parameter list run-length encoding core (P4B-02b119).
//!
//! Run-length encodes the trimmed items of a validated List-typed
//! `AmiParameterValueV1` under the P4B-02b1 list rule (`(item, item, ...)`,
//! items trimmed, non-empty): `run_length_encode_parameter_list_v1` returns
//! the list of `(item, run_length)` pairs of the consecutive equal trimmed
//! items, in order (raw byte equality, per the P4B-02b0 raw-byte binding).
//! The sum of all run lengths equals the item count; the number of pairs
//! equals the number of runs. This is the compression companion of 02b98
//! dedup (which removes duplicate runs) and of 02b107 distinct counting.
//!
//! Fail-closed: a non-List value yields `NotAList`; a token that does not
//! match the List shape yields `MalformedList` (unreachable for values built
//! via `AmiParameterValueV1::try_new`, kept defensive instead of panicking).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: consecutive-run compression.
pub const PARAMETER_LIST_RUN_LENGTH_ENCODE_POLICY_V1: &str =
    "sipi.p4b-02b119.parameter-list-run-length-encode-v1.consecutive-runs";

/// Fail-closed error while run-length encoding one list value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListRunLengthEncodeErrorV1 {
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

/// Run-length encode the trimmed items of a List value into (item, length)
/// pairs of consecutive equal items, in order.
pub fn run_length_encode_parameter_list_v1(
    value: &AmiParameterValueV1,
) -> Result<Vec<(String, usize)>, ParameterListRunLengthEncodeErrorV1> {
    if value.parameter_type() != AmiParameterTypeV1::List {
        return Err(ParameterListRunLengthEncodeErrorV1::NotAList);
    }
    let items = list_items(value.value_token())
        .ok_or(ParameterListRunLengthEncodeErrorV1::MalformedList)?;
    let mut runs: Vec<(String, usize)> = Vec::new();
    for item in items {
        match runs.last_mut() {
            Some((last, length)) if *last == item => *length += 1,
            _ => runs.push((item, 1)),
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
    fn encodes_consecutive_runs() {
        let v = value("channels", "List", "(a, a, b, c, c, c)");
        assert_eq!(
            run_length_encode_parameter_list_v1(&v),
            Ok(vec![
                ("a".to_string(), 2),
                ("b".to_string(), 1),
                ("c".to_string(), 3),
            ])
        );
    }

    #[test]
    fn all_distinct_items_are_singleton_runs() {
        let v = value("channels", "List", "(a, b, c)");
        assert_eq!(
            run_length_encode_parameter_list_v1(&v),
            Ok(vec![
                ("a".to_string(), 1),
                ("b".to_string(), 1),
                ("c".to_string(), 1),
            ])
        );
    }

    #[test]
    fn non_adjacent_duplicates_are_separate_runs() {
        let v = value("channels", "List", "(a, b, a)");
        assert_eq!(
            run_length_encode_parameter_list_v1(&v),
            Ok(vec![
                ("a".to_string(), 1),
                ("b".to_string(), 1),
                ("a".to_string(), 1),
            ])
        );
    }

    #[test]
    fn single_item_is_one_run() {
        let v = value("channels", "List", "(x)");
        assert_eq!(
            run_length_encode_parameter_list_v1(&v),
            Ok(vec![("x".to_string(), 1)])
        );
    }

    #[test]
    fn non_list_fails_closed() {
        let float = value("gain", "Float", "0.5");
        assert_eq!(
            run_length_encode_parameter_list_v1(&float),
            Err(ParameterListRunLengthEncodeErrorV1::NotAList)
        );
    }

    #[test]
    fn spacing_is_canonicalized() {
        let v = value("channels", "List", "( a , a , b )");
        assert_eq!(
            run_length_encode_parameter_list_v1(&v),
            Ok(vec![
                ("a".to_string(), 2),
                ("b".to_string(), 1),
            ])
        );
    }
}
