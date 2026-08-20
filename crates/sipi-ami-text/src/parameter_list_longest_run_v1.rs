//! AMI parameter list longest-run core (P4B-02b120).
//!
//! Finds the longest run of consecutive equal trimmed items in a validated
//! List-typed `AmiParameterValueV1` under the P4B-02b1 list rule
//! (`(item, item, ...)`, items trimmed, non-empty):
//! `longest_run_parameter_list_v1` returns the `(item, run_length)` pair of
//! the longest consecutive equal trimmed items (raw byte equality, per the
//! P4B-02b0 raw-byte binding); ties are resolved to the earliest run. This is
//! the run-max companion of 02b119 run-length encoding (whose run list it
//! maximizes) and of 02b108 occurrence counting (a run never exceeds the
//! total occurrence count of its item).
//!
//! Fail-closed: a non-List value yields `NotAList`; a token that does not
//! match the List shape yields `MalformedList` (unreachable for values built
//! via `AmiParameterValueV1::try_new`, kept defensive instead of panicking).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: longest consecutive run analysis.
pub const PARAMETER_LIST_LONGEST_RUN_POLICY_V1: &str =
    "sipi.p4b-02b120.parameter-list-longest-run-v1.longest-consecutive-run";

/// Fail-closed error while analyzing one list value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListLongestRunErrorV1 {
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

/// Return the (item, length) of the longest consecutive equal trimmed items;
/// ties resolve to the earliest run.
pub fn longest_run_parameter_list_v1(
    value: &AmiParameterValueV1,
) -> Result<(String, usize), ParameterListLongestRunErrorV1> {
    if value.parameter_type() != AmiParameterTypeV1::List {
        return Err(ParameterListLongestRunErrorV1::NotAList);
    }
    let items = list_items(value.value_token())
        .ok_or(ParameterListLongestRunErrorV1::MalformedList)?;
    let mut best: (String, usize) = (items[0].clone(), 1);
    let mut current: (String, usize) = (items[0].clone(), 1);
    for item in &items[1..] {
        if *item == current.0 {
            current.1 += 1;
        } else {
            current = (item.clone(), 1);
        }
        if current.1 > best.1 {
            best = current.clone();
        }
    }
    Ok(best)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    #[test]
    fn finds_longest_run() {
        let v = value("channels", "List", "(a, a, b, c, c, c)");
        assert_eq!(
            longest_run_parameter_list_v1(&v),
            Ok(("c".to_string(), 3))
        );
    }

    #[test]
    fn tie_resolves_to_earliest_run() {
        let v = value("channels", "List", "(a, a, b, b)");
        assert_eq!(
            longest_run_parameter_list_v1(&v),
            Ok(("a".to_string(), 2))
        );
    }

    #[test]
    fn all_distinct_has_unit_runs() {
        let v = value("channels", "List", "(a, b, c)");
        assert_eq!(
            longest_run_parameter_list_v1(&v),
            Ok(("a".to_string(), 1))
        );
    }

    #[test]
    fn single_item_is_its_own_longest_run() {
        let v = value("channels", "List", "(x)");
        assert_eq!(
            longest_run_parameter_list_v1(&v),
            Ok(("x".to_string(), 1))
        );
    }

    #[test]
    fn non_list_fails_closed() {
        let float = value("gain", "Float", "0.5");
        assert_eq!(
            longest_run_parameter_list_v1(&float),
            Err(ParameterListLongestRunErrorV1::NotAList)
        );
    }

    #[test]
    fn spacing_is_canonicalized() {
        let v = value("channels", "List", "( a , a , b )");
        assert_eq!(
            longest_run_parameter_list_v1(&v),
            Ok(("a".to_string(), 2))
        );
    }
}
