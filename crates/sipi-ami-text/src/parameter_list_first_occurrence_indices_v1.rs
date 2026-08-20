//! AMI parameter list first-occurrence indices core (P4B-02b182).
//!
//! Returns the first-occurrence index of every distinct trimmed item of a
//! validated List-typed `AmiParameterValueV1` value under the P4B-02b1 list
//! rule (`(item, item, ...)`, items trimmed, non-empty):
//! `parameter_list_first_occurrence_indices_v1` returns the `(item, index)`
//! pairs in first-occurrence order (raw byte equality, per the P4B-02b0
//! raw-byte binding, mirroring the 02b107 distinct-count and 02b121 frequency
//! first-occurrence semantics), where `index` is the 0-based position of the
//! item's first appearance (consistent with the 0-based convention of 02b110
//! item index-of). This is the positional companion of 02b181 normalized
//! frequency (which returns `(item, count / total)`): the two slices share the
//! same first-occurrence ordering, differing only in the paired value.
//!
//! Fail-closed: the value not declared List yields `NotAList`; the token not
//! matching the List shape yields `MalformedList` (unreachable for values
//! built via `AmiParameterValueV1::try_new`, kept defensive instead of
//! panicking).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: first-occurrence index map.
pub const PARAMETER_LIST_FIRST_OCCURRENCE_INDICES_POLICY_V1: &str =
    "sipi.p4b-02b182.parameter-list-first-occurrence-indices-v1.first-occurrence-index";

/// Fail-closed error while computing the first-occurrence index map of a list value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListFirstOccurrenceIndicesErrorV1 {
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

/// Return the `(item, first_occurrence_index)` pairs of a List value's trimmed
/// items in first-occurrence order; each index is the 0-based position of the
/// item's first appearance.
pub fn parameter_list_first_occurrence_indices_v1(
    value: &AmiParameterValueV1,
) -> Result<Vec<(String, usize)>, ParameterListFirstOccurrenceIndicesErrorV1> {
    if value.parameter_type() != AmiParameterTypeV1::List {
        return Err(ParameterListFirstOccurrenceIndicesErrorV1::NotAList);
    }
    let items = list_items(value.value_token())
        .ok_or(ParameterListFirstOccurrenceIndicesErrorV1::MalformedList)?;
    let mut indices: Vec<(String, usize)> = Vec::new();
    for (position, item) in items.iter().enumerate() {
        if !indices.iter().any(|(key, _)| key == item) {
            indices.push((item.clone(), position));
        }
    }
    Ok(indices)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    #[test]
    fn first_occurrence_indices_mixed() {
        let v = value("channels", "List", "(a, b, a, c, a, b)");
        assert_eq!(
            parameter_list_first_occurrence_indices_v1(&v),
            Ok(vec![
                ("a".to_string(), 0),
                ("b".to_string(), 1),
                ("c".to_string(), 3),
            ])
        );
    }

    #[test]
    fn all_equal_single_entry() {
        let v = value("param", "List", "(x, x, x)");
        assert_eq!(
            parameter_list_first_occurrence_indices_v1(&v),
            Ok(vec![("x".to_string(), 0)])
        );
    }

    #[test]
    fn all_distinct_contiguous_indices() {
        let v = value("param", "List", "(p, q, r)");
        assert_eq!(
            parameter_list_first_occurrence_indices_v1(&v),
            Ok(vec![
                ("p".to_string(), 0),
                ("q".to_string(), 1),
                ("r".to_string(), 2),
            ])
        );
    }

    #[test]
    fn single_item_index_zero() {
        let v = value("param", "List", "(x)");
        assert_eq!(
            parameter_list_first_occurrence_indices_v1(&v),
            Ok(vec![("x".to_string(), 0)])
        );
    }

    #[test]
    fn spacing_is_canonicalized() {
        let v = value("param", "List", "( a , b , a )");
        assert_eq!(
            parameter_list_first_occurrence_indices_v1(&v),
            Ok(vec![("a".to_string(), 0), ("b".to_string(), 1)])
        );
    }

    #[test]
    fn non_list_fails_closed() {
        let v = value("gain", "Float", "0.5");
        assert_eq!(
            parameter_list_first_occurrence_indices_v1(&v),
            Err(ParameterListFirstOccurrenceIndicesErrorV1::NotAList)
        );
    }
}
