//! AMI parameter list prevalence map core (P4B-02b193).
//!
//! Returns the mode-subset prevalence map of a validated List-typed
//! `AmiParameterValueV1` value under the P4B-02b1 list rule
//! (`(item, item, ...)`, items trimmed, non-empty):
//! `parameter_list_prevalence_map_v1` returns a `BTreeMap` keyed by every
//! trimmed item whose occurrence count equals the maximum count over all
//! distinct items, with the shared proportion `max_count / item_count` as
//! value (raw byte equality, per the P4B-02b0 raw-byte binding). Every value
//! is therefore identical and equals the 02b180 prevalence ratio; the key set
//! is the 02b165 mode-item set. An all-equal list yields a single entry with
//! 1.0; an all-distinct list yields n entries each with `1/n`. This is the
//! map形态 companion of 02b180 prevalence-ratio (single f64) — the ratio
//! together with the mode items that attain it — distinct from 02b192
//! relative-frequency-map (which covers every distinct item).
//!
//! Fail-closed: the value not declared List yields `NotAList`; the token not
//! matching the List shape yields `MalformedList` (unreachable for values
//! built via `AmiParameterValueV1::try_new`, kept defensive instead of
//! panicking).

use std::collections::BTreeMap;

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: mode-subset prevalence map.
pub const PARAMETER_LIST_PREVALENCE_MAP_POLICY_V1: &str =
    "sipi.p4b-02b193.parameter-list-prevalence-map-v1.prevalence-map";

/// Fail-closed error while computing the prevalence map of a list value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListPrevalenceMapErrorV1 {
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

/// Return a `BTreeMap` mapping every mode item (occurrence count equal to the
/// maximum over distinct items) to the shared prevalence proportion
/// `max_count / item_count`; every value equals the 02b180 prevalence ratio.
pub fn parameter_list_prevalence_map_v1(
    value: &AmiParameterValueV1,
) -> Result<BTreeMap<String, f64>, ParameterListPrevalenceMapErrorV1> {
    if value.parameter_type() != AmiParameterTypeV1::List {
        return Err(ParameterListPrevalenceMapErrorV1::NotAList);
    }
    let items =
        list_items(value.value_token()).ok_or(ParameterListPrevalenceMapErrorV1::MalformedList)?;
    let item_count = items.len();

    let mut counts: BTreeMap<String, usize> = BTreeMap::new();
    for item in &items {
        *counts.entry(item.clone()).or_insert(0) += 1;
    }
    let max_count = counts.values().copied().max().unwrap_or(1);
    let ratio = max_count as f64 / item_count as f64;
    Ok(counts
        .into_iter()
        .filter(|(_, count)| *count == max_count)
        .map(|(item, _)| (item, ratio))
        .collect())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    #[test]
    fn all_equal_single_entry_ratio_one() {
        let v = value("param", "List", "(a, a, a)");
        let map = parameter_list_prevalence_map_v1(&v).unwrap();
        assert_eq!(map, BTreeMap::from([("a".to_string(), 1.0)]));
    }

    #[test]
    fn all_distinct_every_item_reciprocal() {
        let v = value("param", "List", "(c, a, b)");
        let map = parameter_list_prevalence_map_v1(&v).unwrap();
        assert_eq!(map.len(), 3);
        assert_eq!(map.get("a"), Some(&(1.0 / 3.0)));
        assert_eq!(map.get("b"), Some(&(1.0 / 3.0)));
        assert_eq!(map.get("c"), Some(&(1.0 / 3.0)));
    }

    #[test]
    fn unbalanced_only_mode_item() {
        let v = value("param", "List", "(a, a, a, b, c)");
        let map = parameter_list_prevalence_map_v1(&v).unwrap();
        assert_eq!(map.len(), 1);
        assert_eq!(map.get("a"), Some(&(3.0 / 5.0)));
    }

    #[test]
    fn tied_mode_both_items() {
        let v = value("param", "List", "(x, x, y, y, z)");
        let map = parameter_list_prevalence_map_v1(&v).unwrap();
        assert_eq!(map.len(), 2);
        assert_eq!(map.get("x"), Some(&(2.0 / 5.0)));
        assert_eq!(map.get("y"), Some(&(2.0 / 5.0)));
    }

    #[test]
    fn single_item_ratio_one() {
        let v = value("param", "List", "(x)");
        let map = parameter_list_prevalence_map_v1(&v).unwrap();
        assert_eq!(map, BTreeMap::from([("x".to_string(), 1.0)]));
    }

    #[test]
    fn non_list_fails_closed() {
        let v = value("gain", "Float", "0.5");
        assert_eq!(
            parameter_list_prevalence_map_v1(&v),
            Err(ParameterListPrevalenceMapErrorV1::NotAList)
        );
    }
}
