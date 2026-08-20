//! AMI parameter list occurrence-indices map core (P4B-02b188).
//!
//! Returns a mapping from every distinct trimmed item to its full occurrence
//! index list in a validated List-typed `AmiParameterValueV1` value under the
//! P4B-02b1 list rule (`(item, item, ...)`, items trimmed, non-empty):
//! `parameter_list_occurrence_indices_map_v1` returns a `BTreeMap` keyed by
//! trimmed item string whose values are the 0-based indices of every
//! occurrence, in ascending position order (raw byte equality, per the
//! P4B-02b0 raw-byte binding). This is the full-list enrichment of the
//! 02b186 first-occurrence-map and 02b187 last-occurrence-map companions:
//! per item, `indices[0]` equals the 02b186 first index, `indices[last]`
//! equals the 02b187 last index, and `indices.len()` equals the 02b121
//! per-item count.
//!
//! Fail-closed: the value not declared List yields `NotAList`; the token not
//! matching the List shape yields `MalformedList` (unreachable for values
//! built via `AmiParameterValueV1::try_new`, kept defensive instead of
//! panicking).

use std::collections::BTreeMap;

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: occurrence-indices map.
pub const PARAMETER_LIST_OCCURRENCE_INDICES_MAP_POLICY_V1: &str =
    "sipi.p4b-02b188.parameter-list-occurrence-indices-map-v1.occurrence-indices-map";

/// Fail-closed error while computing the occurrence-indices map of a list value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListOccurrenceIndicesMapErrorV1 {
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

/// Return a `BTreeMap` mapping each distinct trimmed item to the list of
/// 0-based indices of every occurrence, in ascending position order.
pub fn parameter_list_occurrence_indices_map_v1(
    value: &AmiParameterValueV1,
) -> Result<BTreeMap<String, Vec<usize>>, ParameterListOccurrenceIndicesMapErrorV1> {
    if value.parameter_type() != AmiParameterTypeV1::List {
        return Err(ParameterListOccurrenceIndicesMapErrorV1::NotAList);
    }
    let items = list_items(value.value_token())
        .ok_or(ParameterListOccurrenceIndicesMapErrorV1::MalformedList)?;

    let mut map: BTreeMap<String, Vec<usize>> = BTreeMap::new();
    for (position, item) in items.iter().enumerate() {
        map.entry(item.clone()).or_default().push(position);
    }
    Ok(map)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    #[test]
    fn mixed_items_occurrence_indices() {
        let v = value("channels", "List", "(b, a, b, c, a)");
        let map = parameter_list_occurrence_indices_map_v1(&v).unwrap();
        assert_eq!(map.get("a"), Some(&vec![1, 4]));
        assert_eq!(map.get("b"), Some(&vec![0, 2]));
        assert_eq!(map.get("c"), Some(&vec![3]));
        assert_eq!(map.len(), 3);
    }

    #[test]
    fn all_equal_single_entry() {
        let v = value("param", "List", "(x, x, x)");
        let map = parameter_list_occurrence_indices_map_v1(&v).unwrap();
        assert_eq!(map.len(), 1);
        assert_eq!(map.get("x"), Some(&vec![0, 1, 2]));
    }

    #[test]
    fn all_distinct_sequential() {
        let v = value("param", "List", "(p, q, r)");
        let map = parameter_list_occurrence_indices_map_v1(&v).unwrap();
        assert_eq!(map.get("p"), Some(&vec![0]));
        assert_eq!(map.get("q"), Some(&vec![1]));
        assert_eq!(map.get("r"), Some(&vec![2]));
        assert_eq!(map.len(), 3);
    }

    #[test]
    fn single_item() {
        let v = value("param", "List", "(x)");
        let map = parameter_list_occurrence_indices_map_v1(&v).unwrap();
        assert_eq!(map, BTreeMap::from([("x".to_string(), vec![0])]));
    }

    #[test]
    fn spacing_is_canonicalized() {
        let v = value("param", "List", "( a , b , a )");
        let map = parameter_list_occurrence_indices_map_v1(&v).unwrap();
        assert_eq!(map.get("a"), Some(&vec![0, 2]));
        assert_eq!(map.get("b"), Some(&vec![1]));
    }

    #[test]
    fn non_list_fails_closed() {
        let v = value("gain", "Float", "0.5");
        assert_eq!(
            parameter_list_occurrence_indices_map_v1(&v),
            Err(ParameterListOccurrenceIndicesMapErrorV1::NotAList)
        );
    }
}
