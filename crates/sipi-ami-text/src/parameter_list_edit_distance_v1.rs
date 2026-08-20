//! AMI parameter list edit distance core (P4B-02b143).
//!
//! Computes the Levenshtein edit distance of two validated List-typed
//! `AmiParameterValueV1` values under the P4B-02b1 list rule
//! (`(item, item, ...)`, items trimmed, non-empty):
//! `list_edit_distance_v1` returns the minimum number of single-item insert,
//! delete, or substitute operations needed to transform one trimmed item
//! sequence into the other (unit costs; equality by raw byte equality, per
//! the P4B-02b0 raw-byte binding). The edit distance equals
//! `max(n, m) - lcs_length` when one sequence is a subsequence of the other
//! and otherwise is at least that bound. This is the distance companion of
//! 02b142 LCS length.
//!
//! Fail-closed: either value not declared List yields `NotAList`; either
//! token not matching the List shape yields `MalformedList` (unreachable for
//! values built via `AmiParameterValueV1::try_new`, kept defensive instead
//! of panicking).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: list value edit distance.
pub const PARAMETER_LIST_EDIT_DISTANCE_POLICY_V1: &str =
    "sipi.p4b-02b143.parameter-list-edit-distance-v1.edit-distance";

/// Fail-closed error while computing the edit distance of two list values.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListEditDistanceErrorV1 {
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

/// Return the Levenshtein edit distance between the trimmed items of two
/// List-typed validated values (unit insert/delete/substitute costs).
pub fn list_edit_distance_v1(
    left: &AmiParameterValueV1,
    right: &AmiParameterValueV1,
) -> Result<usize, ParameterListEditDistanceErrorV1> {
    if left.parameter_type() != AmiParameterTypeV1::List
        || right.parameter_type() != AmiParameterTypeV1::List
    {
        return Err(ParameterListEditDistanceErrorV1::NotAList);
    }
    let left_items = list_items(left.value_token())
        .ok_or(ParameterListEditDistanceErrorV1::MalformedList)?;
    let right_items = list_items(right.value_token())
        .ok_or(ParameterListEditDistanceErrorV1::MalformedList)?;
    let n = left_items.len();
    let m = right_items.len();
    let mut previous: Vec<usize> = (0..=m).collect();
    let mut current = vec![0usize; m + 1];
    for i in 1..=n {
        current[0] = i;
        for j in 1..=m {
            let substitute = previous[j - 1] + usize::from(left_items[i - 1] != right_items[j - 1]);
            current[j] = (previous[j] + 1).min(current[j - 1] + 1).min(substitute);
        }
        std::mem::swap(&mut previous, &mut current);
    }
    Ok(previous[m])
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    #[test]
    fn computes_edit_distance() {
        let a = value("left", "List", "(a, b, c)");
        let b = value("right", "List", "(a, x, c)");
        assert_eq!(list_edit_distance_v1(&a, &b), Ok(1));
    }

    #[test]
    fn identical_values_zero() {
        let a = value("left", "List", "(a, b, c)");
        let b = value("right", "List", "(a, b, c)");
        assert_eq!(list_edit_distance_v1(&a, &b), Ok(0));
    }

    #[test]
    fn disjoint_values_max_length() {
        let a = value("left", "List", "(a, b)");
        let b = value("right", "List", "(x, y, z)");
        assert_eq!(list_edit_distance_v1(&a, &b), Ok(3));
    }

    #[test]
    fn insert_and_delete_ops() {
        let a = value("left", "List", "(a, b)");
        let b = value("right", "List", "(x, a, b, y)");
        assert_eq!(list_edit_distance_v1(&a, &b), Ok(2));
    }

    #[test]
    fn left_non_list_fails_closed() {
        let a = value("gain", "Float", "0.5");
        let b = value("right", "List", "(a)");
        assert_eq!(
            list_edit_distance_v1(&a, &b),
            Err(ParameterListEditDistanceErrorV1::NotAList)
        );
    }

    #[test]
    fn spacing_is_canonicalized() {
        let a = value("left", "List", "( a , b , c )");
        let b = value("right", "List", "(a, x, c)");
        assert_eq!(list_edit_distance_v1(&a, &b), Ok(1));
    }
}
