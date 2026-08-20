//! AMI parameter list Jaccard index core (P4B-02b154).
//!
//! Computes the Jaccard index of two validated List-typed
//! `AmiParameterValueV1` values under the P4B-02b1 list rule
//! (`(item, item, ...)`, items trimmed, non-empty):
//! `list_jaccard_index_v1` returns the ratio of the sizes of the distinct
//! intersection and distinct union of the two values' trimmed items (raw byte
//! equality, per the P4B-02b0 raw-byte binding), as an f64 in \[0, 1\]: 0 for
//! disjoint values, 1 for values with the same distinct set. This is the
//! set-similarity companion of 02b148 intersection and of 02b150 union.
//!
//! Fail-closed: either value not declared List yields `NotAList`; either
//! token not matching the List shape yields `MalformedList` (unreachable for
//! values built via `AmiParameterValueV1::try_new`, kept defensive instead
//! of panicking).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: set-based Jaccard similarity.
pub const PARAMETER_LIST_JACCARD_INDEX_POLICY_V1: &str =
    "sipi.p4b-02b154.parameter-list-jaccard-index-v1.jaccard-index";

/// Fail-closed error while computing the Jaccard index of two list values.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListJaccardIndexErrorV1 {
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

/// Return the Jaccard index of two List-typed validated values' distinct
/// trimmed item sets (intersection size / union size as f64 in [0, 1]).
pub fn list_jaccard_index_v1(
    left: &AmiParameterValueV1,
    right: &AmiParameterValueV1,
) -> Result<f64, ParameterListJaccardIndexErrorV1> {
    if left.parameter_type() != AmiParameterTypeV1::List
        || right.parameter_type() != AmiParameterTypeV1::List
    {
        return Err(ParameterListJaccardIndexErrorV1::NotAList);
    }
    let left_items =
        list_items(left.value_token()).ok_or(ParameterListJaccardIndexErrorV1::MalformedList)?;
    let right_items =
        list_items(right.value_token()).ok_or(ParameterListJaccardIndexErrorV1::MalformedList)?;
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
    let union = distinct_left.len() + distinct_right.len() - intersection;
    Ok(intersection as f64 / union as f64)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    #[test]
    fn identical_distinct_sets_index_one() {
        let a = value("left", "List", "(a, b)");
        let b = value("right", "List", "(b, a)");
        assert_eq!(list_jaccard_index_v1(&a, &b), Ok(1.0));
    }

    #[test]
    fn disjoint_index_zero() {
        let a = value("left", "List", "(a, b)");
        let b = value("right", "List", "(x, y)");
        assert_eq!(list_jaccard_index_v1(&a, &b), Ok(0.0));
    }

    #[test]
    fn partial_overlap() {
        let a = value("left", "List", "(a, b, c)");
        let b = value("right", "List", "(b, c, d)");
        let index = list_jaccard_index_v1(&a, &b).expect("valid");
        assert!((index - 2.0 / 4.0).abs() < 1e-12);
    }

    #[test]
    fn duplicates_do_not_change_index() {
        let a = value("left", "List", "(a, a, b)");
        let b = value("right", "List", "(a, b, b)");
        assert_eq!(list_jaccard_index_v1(&a, &b), Ok(1.0));
    }

    #[test]
    fn left_non_list_fails_closed() {
        let a = value("gain", "Float", "0.5");
        let b = value("right", "List", "(a)");
        assert_eq!(
            list_jaccard_index_v1(&a, &b),
            Err(ParameterListJaccardIndexErrorV1::NotAList)
        );
    }

    #[test]
    fn spacing_is_canonicalized() {
        let a = value("left", "List", "( a , b , c )");
        let b = value("right", "List", "(b, c, d)");
        let index = list_jaccard_index_v1(&a, &b).expect("valid");
        assert!((index - 0.5).abs() < 1e-12);
    }
}
