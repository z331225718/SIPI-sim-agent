//! AMI parameter list last-occurrence indices core (P4B-02b189).
//!
//! Returns the last-occurrence index of every distinct trimmed item of a
//! validated List-typed `AmiParameterValueV1` value under the P4B-02b1 list
//! rule (`(item, item, ...)`, items trimmed, non-empty):
//! `parameter_list_last_occurrence_indices_v1` returns the `(item, index)`
//! pairs in first-occurrence order (raw byte equality, per the P4B-02b0
//! raw-byte binding, mirroring the 02b182 first-occurrence-indices ordering),
//! where `index` is the 0-based position of the item's last appearance. This
//! is the last-occurrence mirror companion of 02b182 first-occurrence-indices
//! (same key set and same first-occurrence ordering, value = last index
//! instead of first) and the positional companion of 02b187 last-occurrence
//! map (which carries the same data as a BTreeMap keyed by item).
//!
//! Fail-closed: the value not declared List yields `NotAList`; the token not
//! matching the List shape yields `MalformedList` (unreachable for values
//! built via `AmiParameterValueV1::try_new`, kept defensive instead of
//! panicking).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: last-occurrence index list.
pub const PARAMETER_LIST_LAST_OCCURRENCE_INDICES_POLICY_V1: &str =
    "sipi.p4b-02b189.parameter-list-last-occurrence-indices-v1.last-occurrence-index";

/// Fail-closed error while computing the last-occurrence index list of a list value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListLastOccurrenceIndicesErrorV1 {
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

/// Return the `(item, last_occurrence_index)` pairs of a List value's trimmed
/// items in first-occurrence order; each index is the 0-based position of the
/// item's last appearance.
pub fn parameter_list_last_occurrence_indices_v1(
    value: &AmiParameterValueV1,
) -> Result<Vec<(String, usize)>, ParameterListLastOccurrenceIndicesErrorV1> {
    if value.parameter_type() != AmiParameterTypeV1::List {
        return Err(ParameterListLastOccurrenceIndicesErrorV1::NotAList);
    }
    let items = list_items(value.value_token())
        .ok_or(ParameterListLastOccurrenceIndicesErrorV1::MalformedList)?;
    let mut indices: Vec<(String, usize)> = Vec::new();
    for (position, item) in items.iter().enumerate() {
        match indices.iter_mut().find(|(key, _)| key == item) {
            Some(entry) => entry.1 = position,
            None => indices.push((item.clone(), position)),
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
    fn last_occurrence_indices_mixed() {
        let v = value("channels", "List", "(a, b, a, c, a, b)");
        assert_eq!(
            parameter_list_last_occurrence_indices_v1(&v),
            Ok(vec![
                ("a".to_string(), 4),
                ("b".to_string(), 5),
                ("c".to_string(), 3),
            ])
        );
    }

    #[test]
    fn all_equal_single_entry() {
        let v = value("param", "List", "(x, x, x)");
        assert_eq!(
            parameter_list_last_occurrence_indices_v1(&v),
            Ok(vec![("x".to_string(), 2)])
        );
    }

    #[test]
    fn all_distinct_contiguous_indices() {
        let v = value("param", "List", "(p, q, r)");
        assert_eq!(
            parameter_list_last_occurrence_indices_v1(&v),
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
            parameter_list_last_occurrence_indices_v1(&v),
            Ok(vec![("x".to_string(), 0)])
        );
    }

    #[test]
    fn spacing_is_canonicalized() {
        let v = value("param", "List", "( a , b , a )");
        assert_eq!(
            parameter_list_last_occurrence_indices_v1(&v),
            Ok(vec![("a".to_string(), 2), ("b".to_string(), 1)])
        );
    }

    #[test]
    fn non_list_fails_closed() {
        let v = value("gain", "Float", "0.5");
        assert_eq!(
            parameter_list_last_occurrence_indices_v1(&v),
            Err(ParameterListLastOccurrenceIndicesErrorV1::NotAList)
        );
    }
}
