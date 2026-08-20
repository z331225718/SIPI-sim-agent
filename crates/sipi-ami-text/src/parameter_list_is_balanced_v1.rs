//! AMI parameter list is-balanced core (P4B-02b185).
//!
//! Returns whether every maximal run of equal adjacent trimmed items of a
//! validated List-typed `AmiParameterValueV1` value under the P4B-02b1 list
//! rule (`(item, item, ...)`, items trimmed, non-empty) has the same length:
//! `parameter_list_is_balanced_v1` returns `true` when all run lengths are
//! equal, `false` otherwise (raw byte equality, per the P4B-02b0 raw-byte
//! binding). A single run is always balanced (trivially true); a fully-distinct
//! list of length > 1 is unbalanced (each run has length 1 but there are
//! multiple runs — still balanced because all lengths are 1). This is the
//! boolean companion of 02b168 run-count (all runs equal ⟺ the list of run
//! lengths from 02b119 run-length-encode has all identical values) and of
//! 02b183 run-boundaries (all boundary extents equal ⟺ is-balanced).
//!
//! Fail-closed: the value not declared List yields `NotAList`; the token not
//! matching the List shape yields `MalformedList` (unreachable for values
//! built via `AmiParameterValueV1::try_new`, kept defensive instead of
//! panicking).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: list value is-balanced flag.
pub const PARAMETER_LIST_IS_BALANCED_POLICY_V1: &str =
    "sipi.p4b-02b185.parameter-list-is-balanced-v1.is-balanced";

/// Fail-closed error while computing the is-balanced flag of a list value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListIsBalancedErrorV1 {
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

/// Return whether every maximal run of equal adjacent trimmed items has the
/// same length (`true`) or not (`false`).
pub fn parameter_list_is_balanced_v1(
    value: &AmiParameterValueV1,
) -> Result<bool, ParameterListIsBalancedErrorV1> {
    if value.parameter_type() != AmiParameterTypeV1::List {
        return Err(ParameterListIsBalancedErrorV1::NotAList);
    }
    let items =
        list_items(value.value_token()).ok_or(ParameterListIsBalancedErrorV1::MalformedList)?;

    let mut run_lengths: Vec<usize> = Vec::new();
    let mut current_len = 1usize;
    for (index, item) in items.iter().enumerate().skip(1) {
        if item == &items[index - 1] {
            current_len += 1;
        } else {
            run_lengths.push(current_len);
            current_len = 1;
        }
    }
    run_lengths.push(current_len);

    // A single run is always balanced; multiple runs are balanced iff all
    // lengths are equal.
    Ok(run_lengths.windows(2).all(|w| w[0] == w[1]))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    #[test]
    fn single_run_all_equal() {
        let v = value("param", "List", "(x, x, x)");
        assert_eq!(parameter_list_is_balanced_v1(&v), Ok(true));
    }

    #[test]
    fn two_runs_equal_length() {
        let v = value("param", "List", "(a, a, b, b)");
        assert_eq!(parameter_list_is_balanced_v1(&v), Ok(true));
    }

    #[test]
    fn two_runs_unequal_length() {
        let v = value("param", "List", "(a, a, b)");
        assert_eq!(parameter_list_is_balanced_v1(&v), Ok(false));
    }

    #[test]
    fn all_distinct_length_1_each() {
        let v = value("param", "List", "(p, q, r)");
        assert_eq!(parameter_list_is_balanced_v1(&v), Ok(true));
    }

    #[test]
    fn single_item_trivially_balanced() {
        let v = value("param", "List", "(x)");
        assert_eq!(parameter_list_is_balanced_v1(&v), Ok(true));
    }

    #[test]
    fn non_list_fails_closed() {
        let v = value("gain", "Float", "0.5");
        assert_eq!(
            parameter_list_is_balanced_v1(&v),
            Err(ParameterListIsBalancedErrorV1::NotAList)
        );
    }
}
