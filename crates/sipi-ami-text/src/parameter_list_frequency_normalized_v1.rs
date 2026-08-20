//! AMI parameter list normalized frequency core (P4B-02b181).
//!
//! Returns the normalized frequency (proportion) of every distinct trimmed
//! item of a validated List-typed `AmiParameterValueV1` value under the
//! P4B-02b1 list rule (`(item, item, ...)`, items trimmed, non-empty):
//! `parameter_list_frequency_normalized_v1` returns the `(item, count / total)`
//! pairs in first-occurrence order (raw byte equality, per the P4B-02b0
//! raw-byte binding, mirroring the 02b107 distinct-count and 02b121 frequency
//! first-occurrence semantics). Each proportion lies in (0, 1] and the sum of
//! all proportions equals 1.0. This is the proportion companion of 02b121
//! item frequencies (the normalized map divides each count by the list length)
//! and the per-item companion of 02b180 prevalence ratio (the maximum entry is
//! the prevalence ratio).
//!
//! Fail-closed: the value not declared List yields `NotAList`; the token not
//! matching the List shape yields `MalformedList` (unreachable for values
//! built via `AmiParameterValueV1::try_new`, kept defensive instead of
//! panicking).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: normalized per-item frequency map.
pub const PARAMETER_LIST_FREQUENCY_NORMALIZED_POLICY_V1: &str =
    "sipi.p4b-02b181.parameter-list-frequency-normalized-v1.item-frequency-normalized";

/// Fail-closed error while computing the normalized frequency map of a list value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListFrequencyNormalizedErrorV1 {
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

/// Return the (item, count / total) pairs of a List value's trimmed items in
/// first-occurrence order; each proportion lies in (0, 1] and the sum is 1.0.
pub fn parameter_list_frequency_normalized_v1(
    value: &AmiParameterValueV1,
) -> Result<Vec<(String, f64)>, ParameterListFrequencyNormalizedErrorV1> {
    if value.parameter_type() != AmiParameterTypeV1::List {
        return Err(ParameterListFrequencyNormalizedErrorV1::NotAList);
    }
    let items = list_items(value.value_token())
        .ok_or(ParameterListFrequencyNormalizedErrorV1::MalformedList)?;
    let total = items.len() as f64;
    let mut frequencies: Vec<(String, usize)> = Vec::new();
    for item in items {
        match frequencies.iter_mut().find(|(key, _)| *key == item) {
            Some((_, count)) => *count += 1,
            None => frequencies.push((item, 1)),
        }
    }
    Ok(frequencies
        .into_iter()
        .map(|(item, count)| (item, count as f64 / total))
        .collect())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    #[test]
    fn normalizes_every_item() {
        let v = value("channels", "List", "(a, b, a, c, a, b)");
        assert_eq!(
            parameter_list_frequency_normalized_v1(&v),
            Ok(vec![
                ("a".to_string(), 0.5),
                ("b".to_string(), 2.0 / 6.0),
                ("c".to_string(), 1.0 / 6.0),
            ])
        );
    }

    #[test]
    fn all_equal_proportions_one() {
        let v = value("param", "List", "(x, x, x)");
        assert_eq!(
            parameter_list_frequency_normalized_v1(&v),
            Ok(vec![("x".to_string(), 1.0)])
        );
    }

    #[test]
    fn all_distinct_proportions_reciprocal() {
        let v = value("param", "List", "(p, q, r)");
        assert_eq!(
            parameter_list_frequency_normalized_v1(&v),
            Ok(vec![
                ("p".to_string(), 1.0 / 3.0),
                ("q".to_string(), 1.0 / 3.0),
                ("r".to_string(), 1.0 / 3.0),
            ])
        );
    }

    #[test]
    fn single_item_proportion_one() {
        let v = value("param", "List", "(x)");
        assert_eq!(
            parameter_list_frequency_normalized_v1(&v),
            Ok(vec![("x".to_string(), 1.0)])
        );
    }

    #[test]
    fn spacing_is_canonicalized() {
        let v = value("param", "List", "( a , b , a )");
        assert_eq!(
            parameter_list_frequency_normalized_v1(&v),
            Ok(vec![
                ("a".to_string(), 2.0 / 3.0),
                ("b".to_string(), 1.0 / 3.0),
            ])
        );
    }

    #[test]
    fn non_list_fails_closed() {
        let v = value("gain", "Float", "0.5");
        assert_eq!(
            parameter_list_frequency_normalized_v1(&v),
            Err(ParameterListFrequencyNormalizedErrorV1::NotAList)
        );
    }
}
