//! AMI parameter list mode frequency core (P4B-02b179).
//!
//! Returns the mode frequency of a validated List-typed `AmiParameterValueV1`
//! value under the P4B-02b1 list rule (`(item, item, ...)`, items trimmed,
//! non-empty): `parameter_list_mode_frequency_v1` returns the maximum
//! occurrence count over the distinct trimmed items (raw byte equality, per
//! the P4B-02b0 raw-byte binding). The list is non-empty by rule so the mode
//! frequency is at least 1; an all-distinct list has mode frequency 1. This
//! is the count companion of 02b165 mode items (the modes are exactly the
//! items at mode frequency) and of 02b121 frequency (the mode frequency is
//! the maximum entry count).
//!
//! Fail-closed: the value not declared List yields `NotAList`; the token not
//! matching the List shape yields `MalformedList` (unreachable for values
//! built via `AmiParameterValueV1::try_new`, kept defensive instead of
//! panicking).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: list value mode frequency.
pub const PARAMETER_LIST_MODE_FREQUENCY_POLICY_V1: &str =
    "sipi.p4b-02b179.parameter-list-mode-frequency-v1.mode-frequency";

/// Fail-closed error while computing the mode frequency of a list value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListModeFrequencyErrorV1 {
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

/// Return the maximum occurrence count over the distinct trimmed items of a
/// List-typed value (raw byte equality); at least 1 by the non-empty rule.
pub fn parameter_list_mode_frequency_v1(
    value: &AmiParameterValueV1,
) -> Result<usize, ParameterListModeFrequencyErrorV1> {
    if value.parameter_type() != AmiParameterTypeV1::List {
        return Err(ParameterListModeFrequencyErrorV1::NotAList);
    }
    let items =
        list_items(value.value_token()).ok_or(ParameterListModeFrequencyErrorV1::MalformedList)?;
    let mut counts: Vec<(String, usize)> = Vec::new();
    for item in &items {
        match counts.iter_mut().find(|(existing, _)| existing == item) {
            Some((_, count)) => *count += 1,
            None => counts.push((item.clone(), 1)),
        }
    }
    let max_count = counts.iter().map(|(_, count)| *count).max().unwrap_or(1);
    Ok(max_count)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    #[test]
    fn returns_mode_frequency() {
        let v = value("param", "List", "(b, a, b, c, b)");
        assert_eq!(parameter_list_mode_frequency_v1(&v), Ok(3));
    }

    #[test]
    fn all_distinct_mode_frequency_one() {
        let v = value("param", "List", "(c, a, b)");
        assert_eq!(parameter_list_mode_frequency_v1(&v), Ok(1));
    }

    #[test]
    fn all_equal_mode_frequency_len() {
        let v = value("param", "List", "(a, a, a)");
        assert_eq!(parameter_list_mode_frequency_v1(&v), Ok(3));
    }

    #[test]
    fn single_item_mode_frequency_one() {
        let v = value("param", "List", "(x)");
        assert_eq!(parameter_list_mode_frequency_v1(&v), Ok(1));
    }

    #[test]
    fn spacing_is_canonicalized() {
        let v = value("param", "List", "( b , a , b )");
        assert_eq!(parameter_list_mode_frequency_v1(&v), Ok(2));
    }

    #[test]
    fn non_list_fails_closed() {
        let v = value("gain", "Float", "0.5");
        assert_eq!(
            parameter_list_mode_frequency_v1(&v),
            Err(ParameterListModeFrequencyErrorV1::NotAList)
        );
    }
}
