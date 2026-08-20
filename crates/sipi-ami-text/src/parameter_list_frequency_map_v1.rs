//! AMI parameter list frequency map core (P4B-02b190).
//!
//! Counts the total occurrences of every distinct trimmed item of a validated
//! List-typed `AmiParameterValueV1` under the P4B-02b1 list rule
//! (`(item, item, ...)`, items trimmed, non-empty):
//! `parameter_list_frequency_map_v1` returns a `BTreeMap` keyed by trimmed
//! item string with the total occurrence count as value (raw byte equality,
//! per the P4B-02b0 raw-byte binding). This is the map形态 companion of
//! 02b121 frequency (which returns the same data as an ordered
//! `Vec<(String, usize)>` in first-occurrence order): the two slices carry
//! identical information but differ in access structure — O(log n) lookup by item
//! key (this slice) vs positional iteration (02b121). Per item the count
//! equals `indices.len()` of the 02b188 occurrence-indices map, and the sum
//! of all counts equals the 02b083 item count.
//!
//! Fail-closed: the value not declared List yields `NotAList`; the token not
//! matching the List shape yields `MalformedList` (unreachable for values
//! built via `AmiParameterValueV1::try_new`, kept defensive instead of
//! panicking).

use std::collections::BTreeMap;

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: frequency map.
pub const PARAMETER_LIST_FREQUENCY_MAP_POLICY_V1: &str =
    "sipi.p4b-02b190.parameter-list-frequency-map-v1.frequency-map";

/// Fail-closed error while computing the frequency map of a list value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListFrequencyMapErrorV1 {
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

/// Return a `BTreeMap` mapping each distinct trimmed item to its total
/// occurrence count.
pub fn parameter_list_frequency_map_v1(
    value: &AmiParameterValueV1,
) -> Result<BTreeMap<String, usize>, ParameterListFrequencyMapErrorV1> {
    if value.parameter_type() != AmiParameterTypeV1::List {
        return Err(ParameterListFrequencyMapErrorV1::NotAList);
    }
    let items =
        list_items(value.value_token()).ok_or(ParameterListFrequencyMapErrorV1::MalformedList)?;

    let mut map: BTreeMap<String, usize> = BTreeMap::new();
    for item in items {
        *map.entry(item).or_insert(0) += 1;
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
    fn counts_every_item() {
        let v = value("channels", "List", "(a, b, a, c, a, b)");
        let map = parameter_list_frequency_map_v1(&v).unwrap();
        assert_eq!(map.get("a"), Some(&3));
        assert_eq!(map.get("b"), Some(&2));
        assert_eq!(map.get("c"), Some(&1));
        assert_eq!(map.len(), 3);
    }

    #[test]
    fn all_equal_single_entry() {
        let v = value("param", "List", "(x, x, x)");
        let map = parameter_list_frequency_map_v1(&v).unwrap();
        assert_eq!(map.len(), 1);
        assert_eq!(map.get("x"), Some(&3));
    }

    #[test]
    fn all_distinct_unit_counts() {
        let v = value("param", "List", "(a, b, c)");
        let map = parameter_list_frequency_map_v1(&v).unwrap();
        assert_eq!(map.get("a"), Some(&1));
        assert_eq!(map.get("b"), Some(&1));
        assert_eq!(map.get("c"), Some(&1));
        assert_eq!(map.len(), 3);
    }

    #[test]
    fn single_item() {
        let v = value("param", "List", "(x)");
        let map = parameter_list_frequency_map_v1(&v).unwrap();
        assert_eq!(map, BTreeMap::from([("x".to_string(), 1)]));
    }

    #[test]
    fn spacing_is_canonicalized() {
        let v = value("param", "List", "( a , b , a )");
        let map = parameter_list_frequency_map_v1(&v).unwrap();
        assert_eq!(map.get("a"), Some(&2));
        assert_eq!(map.get("b"), Some(&1));
    }

    #[test]
    fn non_list_fails_closed() {
        let v = value("gain", "Float", "0.5");
        assert_eq!(
            parameter_list_frequency_map_v1(&v),
            Err(ParameterListFrequencyMapErrorV1::NotAList)
        );
    }
}
