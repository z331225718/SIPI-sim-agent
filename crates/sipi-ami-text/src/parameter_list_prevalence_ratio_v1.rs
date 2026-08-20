//! AMI parameter list prevalence ratio core (P4B-02b180).
//!
//! Returns the prevalence ratio of the most prevalent item of a validated
//! List-typed `AmiParameterValueV1` value under the P4B-02b1 list rule
//! (`(item, item, ...)`, items trimmed, non-empty): `parameter_list_prevalence_ratio_v1`
//! returns `max_count / item_count` over the distinct trimmed items (raw byte
//! equality, per the P4B-02b0 raw-byte binding), as f64 in (0, 1]. An
//! all-equal list yields 1.0; an all-distinct list yields `1/n`. This is the
//! ratio companion of 02b179 mode frequency (the prevalence ratio is the mode
//! frequency divided by the list length) and of 02b121 frequency.
//!
//! Fail-closed: the value not declared List yields `NotAList`; the token not
//! matching the List shape yields `MalformedList` (unreachable for values
//! built via `AmiParameterValueV1::try_new`, kept defensive instead of
//! panicking).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: list value prevalence ratio.
pub const PARAMETER_LIST_PREVALENCE_RATIO_POLICY_V1: &str =
    "sipi.p4b-02b180.parameter-list-prevalence-ratio-v1.prevalence-ratio";

/// Fail-closed error while computing the prevalence ratio of a list value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListPrevalenceRatioErrorV1 {
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

/// Return the prevalence ratio (max count / total) over the distinct trimmed
/// items of a List-typed value (raw byte equality); in (0, 1] by the
/// non-empty rule.
pub fn parameter_list_prevalence_ratio_v1(
    value: &AmiParameterValueV1,
) -> Result<f64, ParameterListPrevalenceRatioErrorV1> {
    if value.parameter_type() != AmiParameterTypeV1::List {
        return Err(ParameterListPrevalenceRatioErrorV1::NotAList);
    }
    let items = list_items(value.value_token())
        .ok_or(ParameterListPrevalenceRatioErrorV1::MalformedList)?;
    let item_count = items.len();
    let mut counts: Vec<(String, usize)> = Vec::new();
    for item in &items {
        match counts.iter_mut().find(|(existing, _)| existing == item) {
            Some((_, count)) => *count += 1,
            None => counts.push((item.clone(), 1)),
        }
    }
    let max_count = counts.iter().map(|(_, count)| *count).max().unwrap_or(1);
    Ok(max_count as f64 / item_count as f64)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    #[test]
    fn all_equal_ratio_one() {
        let v = value("param", "List", "(a, a, a)");
        assert_eq!(parameter_list_prevalence_ratio_v1(&v), Ok(1.0));
    }

    #[test]
    fn all_distinct_ratio_reciprocal() {
        let v = value("param", "List", "(c, a, b)");
        assert_eq!(parameter_list_prevalence_ratio_v1(&v), Ok(1.0 / 3.0));
    }

    #[test]
    fn unbalanced_ratio_three_fifths() {
        let v = value("param", "List", "(a, a, a, b, c)");
        assert_eq!(parameter_list_prevalence_ratio_v1(&v), Ok(3.0 / 5.0));
    }

    #[test]
    fn single_item_ratio_one() {
        let v = value("param", "List", "(x)");
        assert_eq!(parameter_list_prevalence_ratio_v1(&v), Ok(1.0));
    }

    #[test]
    fn spacing_is_canonicalized() {
        let v = value("param", "List", "( b , b , a )");
        assert_eq!(parameter_list_prevalence_ratio_v1(&v), Ok(2.0 / 3.0));
    }

    #[test]
    fn non_list_fails_closed() {
        let v = value("gain", "Float", "0.5");
        assert_eq!(
            parameter_list_prevalence_ratio_v1(&v),
            Err(ParameterListPrevalenceRatioErrorV1::NotAList)
        );
    }
}
