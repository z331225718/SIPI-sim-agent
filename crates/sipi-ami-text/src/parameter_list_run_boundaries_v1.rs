//! AMI parameter list run boundaries core (P4B-02b183).
//!
//! Returns the boundary positions of every maximal run of equal adjacent
//! trimmed items of a validated List-typed `AmiParameterValueV1` value under
//! the P4B-02b1 list rule (`(item, item, ...)`, items trimmed, non-empty):
//! `parameter_list_run_boundaries_v1` returns the `(start_index, end_index)`
//! pairs of the runs in order, both indices 0-based and inclusive (raw byte
//! equality, per the P4B-02b0 raw-byte binding). The list is non-empty by
//! rule so at least one run exists (a single-item list yields one run with
//! the zero-extent pair `(0, 0)`); the number of returned pairs equals the
//! run count of 02b168 run-count, each pair spans the same consecutive-equal
//! decomposition as 02b119 run-length-encode, and the first run always
//! starts at 0 while the last run always ends at `item_count - 1`. This is
//! the boundary companion of 02b119 run-length-encode (which returns
//! `(item, run_length)`), of 02b171 longest-run-start-index (whose result is
//! the start index of the maximum-extent pair in this slice's output), and
//! of 02b168 run-count (the pair count).
//!
//! Fail-closed: the value not declared List yields `NotAList`; the token not
//! matching the List shape yields `MalformedList` (unreachable for values
//! built via `AmiParameterValueV1::try_new`, kept defensive instead of
//! panicking).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: maximal-run boundary positions.
pub const PARAMETER_LIST_RUN_BOUNDARIES_POLICY_V1: &str =
    "sipi.p4b-02b183.parameter-list-run-boundaries-v1.run-boundaries";

/// Fail-closed error while computing the run boundaries of a list value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListRunBoundariesErrorV1 {
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

/// Return the `(start_index, end_index)` boundary pairs (both 0-based and
/// inclusive) of every maximal run of equal adjacent trimmed items of a
/// List-typed value, in order (raw byte equality).
pub fn parameter_list_run_boundaries_v1(
    value: &AmiParameterValueV1,
) -> Result<Vec<(usize, usize)>, ParameterListRunBoundariesErrorV1> {
    if value.parameter_type() != AmiParameterTypeV1::List {
        return Err(ParameterListRunBoundariesErrorV1::NotAList);
    }
    let items =
        list_items(value.value_token()).ok_or(ParameterListRunBoundariesErrorV1::MalformedList)?;
    let mut boundaries: Vec<(usize, usize)> = Vec::new();
    let mut run_start = 0usize;
    for (index, item) in items.iter().enumerate().skip(1) {
        if item != &items[index - 1] {
            boundaries.push((run_start, index - 1));
            run_start = index;
        }
    }
    boundaries.push((run_start, items.len() - 1));
    Ok(boundaries)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    #[test]
    fn mixed_runs_boundaries() {
        let v = value("channels", "List", "(a, a, b, c, c, c, a)");
        assert_eq!(
            parameter_list_run_boundaries_v1(&v),
            Ok(vec![(0, 1), (2, 2), (3, 5), (6, 6)])
        );
    }

    #[test]
    fn all_equal_single_run() {
        let v = value("param", "List", "(x, x, x)");
        assert_eq!(parameter_list_run_boundaries_v1(&v), Ok(vec![(0, 2)]));
    }

    #[test]
    fn all_distinct_singleton_runs() {
        let v = value("param", "List", "(p, q, r)");
        assert_eq!(
            parameter_list_run_boundaries_v1(&v),
            Ok(vec![(0, 0), (1, 1), (2, 2)])
        );
    }

    #[test]
    fn single_item_zero_extent() {
        let v = value("param", "List", "(x)");
        assert_eq!(parameter_list_run_boundaries_v1(&v), Ok(vec![(0, 0)]));
    }

    #[test]
    fn spacing_is_canonicalized() {
        let v = value("param", "List", "( a , a , b )");
        assert_eq!(
            parameter_list_run_boundaries_v1(&v),
            Ok(vec![(0, 1), (2, 2)])
        );
    }

    #[test]
    fn non_list_fails_closed() {
        let v = value("gain", "Float", "0.5");
        assert_eq!(
            parameter_list_run_boundaries_v1(&v),
            Err(ParameterListRunBoundariesErrorV1::NotAList)
        );
    }
}
