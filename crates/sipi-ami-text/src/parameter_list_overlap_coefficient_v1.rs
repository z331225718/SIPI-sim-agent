//! AMI parameter list overlap coefficient core (P4B-02b156).
//!
//! Computes the overlap coefficient of two validated List-typed
//! `AmiParameterValueV1` values under the P4B-02b1 list rule
//! (`(item, item, ...)`, items trimmed, non-empty):
//! `list_overlap_coefficient_v1` returns `distinct_intersection_size /
//! min(size_a, size_b)` over the distinct trimmed item sets of the two values
//! (raw byte equality, per the P4B-02b0 raw-byte binding), as an f64 in
//! \[0, 1\]: 0 for disjoint values, 1 when one distinct set is a subset of
//! the other. This is the set-similarity companion of 02b154 Jaccard index
//! and of 02b155 Dice index.
//!
//! Fail-closed: either value not declared List yields `NotAList`; either
//! token not matching the List shape yields `MalformedList` (unreachable for
//! values built via `AmiParameterValueV1::try_new`, kept defensive instead
//! of panicking).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: set-based overlap coefficient.
pub const PARAMETER_LIST_OVERLAP_COEFFICIENT_POLICY_V1: &str =
    "sipi.p4b-02b156.parameter-list-overlap-coefficient-v1.overlap-coefficient";

/// Fail-closed error while computing the overlap coefficient of two lists.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListOverlapCoefficientErrorV1 {
    /// A value's declared type is not List.
    NotAList,
    /// A token does not match the List shape (defensive; unreachable for
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

/// Return the overlap coefficient of two List-typed validated values'
/// distinct trimmed item sets (intersection / min(size_a, size_b) as f64).
pub fn list_overlap_coefficient_v1(
    left: &AmiParameterValueV1,
    right: &AmiParameterValueV1,
) -> Result<f64, ParameterListOverlapCoefficientErrorV1> {
    if left.parameter_type() != AmiParameterTypeV1::List
        || right.parameter_type() != AmiParameterTypeV1::List
    {
        return Err(ParameterListOverlapCoefficientErrorV1::NotAList);
    }
    let left_items = list_items(left.value_token())
        .ok_or(ParameterListOverlapCoefficientErrorV1::MalformedList)?;
    let right_items = list_items(right.value_token())
        .ok_or(ParameterListOverlapCoefficientErrorV1::MalformedList)?;
    let mut distinct_left: Vec<String> = Vec::new();
    for item in &left_items {
        if !distinct_left.contains(item) {
            distinct_left.push(item.clone());
        }
    }
    let mut distinct_right: Vec<String> = Vec::new();
    for item in &right_items {
        if !distinct_right.contains(item) {
            distinct_right.push(item.clone());
        }
    }
    let intersection = distinct_left
        .iter()
        .filter(|item| distinct_right.contains(item))
        .count();
    let denominator = distinct_left.len().min(distinct_right.len());
    Ok(intersection as f64 / denominator as f64)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    #[test]
    fn subset_reaches_one() {
        let a = value("left", "List", "(a, b, c)");
        let b = value("right", "List", "(a, b)");
        assert_eq!(list_overlap_coefficient_v1(&a, &b), Ok(1.0));
    }

    #[test]
    fn disjoint_index_zero() {
        let a = value("left", "List", "(a, b)");
        let b = value("right", "List", "(x, y)");
        assert_eq!(list_overlap_coefficient_v1(&a, &b), Ok(0.0));
    }

    #[test]
    fn partial_overlap() {
        let a = value("left", "List", "(a, b, c)");
        let b = value("right", "List", "(b, c, d)");
        let index = list_overlap_coefficient_v1(&a, &b).expect("valid");
        assert!((index - 2.0 / 3.0).abs() < 1e-12);
    }

    #[test]
    fn duplicates_do_not_change_index() {
        let a = value("left", "List", "(a, a, b)");
        let b = value("right", "List", "(a, b, b)");
        assert_eq!(list_overlap_coefficient_v1(&a, &b), Ok(1.0));
    }

    #[test]
    fn left_non_list_fails_closed() {
        let a = value("gain", "Float", "0.5");
        let b = value("right", "List", "(a)");
        assert_eq!(
            list_overlap_coefficient_v1(&a, &b),
            Err(ParameterListOverlapCoefficientErrorV1::NotAList)
        );
    }

    #[test]
    fn spacing_is_canonicalized() {
        let a = value("left", "List", "( a , b , c )");
        let b = value("right", "List", "(b, c, d)");
        let index = list_overlap_coefficient_v1(&a, &b).expect("valid");
        assert!((index - 2.0 / 3.0).abs() < 1e-12);
    }
}
