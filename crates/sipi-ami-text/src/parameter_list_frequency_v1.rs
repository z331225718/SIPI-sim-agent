//! AMI parameter list frequency map core (P4B-02b121).
//!
//! Counts the total occurrences of every distinct trimmed item of a validated
//! List-typed `AmiParameterValueV1` under the P4B-02b1 list rule
//! (`(item, item, ...)`, items trimmed, non-empty):
//! `parameter_list_item_frequencies_v1` returns the `(item, count)` pairs
//! in first-occurrence order (raw byte equality, per the P4B-02b0 raw-byte
//! binding, mirroring the 02b107 distinct-count first-occurrence semantics).
//! The sum of all counts equals the item count; the number of pairs equals
//! the 02b107 distinct count. This is the total-count companion of 02b108
//! occurrence counting (per single query) and of 02b119 run-length encoding
//! (whose run lengths sum to these counts per item).
//!
//! Fail-closed: a non-List value yields `NotAList`; a token that does not
//! match the List shape yields `MalformedList` (unreachable for values built
//! via `AmiParameterValueV1::try_new`, kept defensive instead of panicking).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: per-item frequency map.
pub const PARAMETER_LIST_FREQUENCY_POLICY_V1: &str =
    "sipi.p4b-02b121.parameter-list-frequency-v1.item-frequency-map";

/// Fail-closed error while computing the frequency map of one list value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListFrequencyErrorV1 {
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

/// Return the (item, total count) pairs of a List value's trimmed items in
/// first-occurrence order.
pub fn parameter_list_item_frequencies_v1(
    value: &AmiParameterValueV1,
) -> Result<Vec<(String, usize)>, ParameterListFrequencyErrorV1> {
    if value.parameter_type() != AmiParameterTypeV1::List {
        return Err(ParameterListFrequencyErrorV1::NotAList);
    }
    let items =
        list_items(value.value_token()).ok_or(ParameterListFrequencyErrorV1::MalformedList)?;
    let mut frequencies: Vec<(String, usize)> = Vec::new();
    for item in items {
        match frequencies.iter_mut().find(|(key, _)| *key == item) {
            Some((_, count)) => *count += 1,
            None => frequencies.push((item, 1)),
        }
    }
    Ok(frequencies)
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
        assert_eq!(
            parameter_list_item_frequencies_v1(&v),
            Ok(vec![
                ("a".to_string(), 3),
                ("b".to_string(), 2),
                ("c".to_string(), 1),
            ])
        );
    }

    #[test]
    fn first_occurrence_order() {
        let v = value("channels", "List", "(b, a, b)");
        assert_eq!(
            parameter_list_item_frequencies_v1(&v),
            Ok(vec![("b".to_string(), 2), ("a".to_string(), 1),])
        );
    }

    #[test]
    fn all_distinct_items_have_unit_counts() {
        let v = value("channels", "List", "(a, b, c)");
        assert_eq!(
            parameter_list_item_frequencies_v1(&v),
            Ok(vec![
                ("a".to_string(), 1),
                ("b".to_string(), 1),
                ("c".to_string(), 1),
            ])
        );
    }

    #[test]
    fn single_item_has_unit_count() {
        let v = value("channels", "List", "(x)");
        assert_eq!(
            parameter_list_item_frequencies_v1(&v),
            Ok(vec![("x".to_string(), 1)])
        );
    }

    #[test]
    fn non_list_fails_closed() {
        let float = value("gain", "Float", "0.5");
        assert_eq!(
            parameter_list_item_frequencies_v1(&float),
            Err(ParameterListFrequencyErrorV1::NotAList)
        );
    }

    #[test]
    fn spacing_is_canonicalized() {
        let v = value("channels", "List", "( a , b , a )");
        assert_eq!(
            parameter_list_item_frequencies_v1(&v),
            Ok(vec![("a".to_string(), 2), ("b".to_string(), 1),])
        );
    }
}
