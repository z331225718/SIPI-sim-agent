//! AMI parameter list Tversky index core (P4B-02b158).
//!
//! Computes the Tversky index of two validated List-typed
//! `AmiParameterValueV1` values under the P4B-02b1 list rule
//! (`(item, item, ...)`, items trimmed, non-empty):
//! `list_tversky_index_v1` returns `|A & B| / (|A & B| + alpha * |A \ B| +
//! beta * |B \ A|)` over the distinct trimmed item sets of the two values
//! (raw byte equality, per the P4B-02b0 raw-byte binding), as an f64 in
//! \[0, 1\]. With alpha = beta = 1 it reduces to the 02b154 Jaccard index;
//! alpha = beta = 1/2 gives the 02b155 Dice index; alpha = beta = 0 gives 1.
//! This is the parameterized companion of 02b154 Jaccard, 02b155 Dice, and
//! 02b156 overlap coefficient.
//!
//! Fail-closed: either value not declared List yields `NotAList`; either
//! token not matching the List shape yields `MalformedList` (unreachable for
//! values built via `AmiParameterValueV1::try_new`, kept defensive instead
//! of panicking); a negative alpha or beta yields `InvalidParameters`.

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: parameterized set-based similarity.
pub const PARAMETER_LIST_TVERSKY_INDEX_POLICY_V1: &str =
    "sipi.p4b-02b158.parameter-list-tversky-index-v1.tversky-index";

/// Fail-closed error while computing the Tversky index of two list values.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListTverskyIndexErrorV1 {
    /// A value's declared type is not List.
    NotAList,
    /// A token does not match the List shape (defensive; unreachable for
    /// values built via `AmiParameterValueV1::try_new`).
    MalformedList,
    /// A parameter (alpha or beta) is negative.
    InvalidParameters,
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

/// Return the Tversky index of two List-typed validated values' distinct
/// trimmed item sets with parameters alpha and beta (both non-negative).
pub fn list_tversky_index_v1(
    left: &AmiParameterValueV1,
    right: &AmiParameterValueV1,
    alpha: f64,
    beta: f64,
) -> Result<f64, ParameterListTverskyIndexErrorV1> {
    if alpha < 0.0 || beta < 0.0 {
        return Err(ParameterListTverskyIndexErrorV1::InvalidParameters);
    }
    if left.parameter_type() != AmiParameterTypeV1::List
        || right.parameter_type() != AmiParameterTypeV1::List
    {
        return Err(ParameterListTverskyIndexErrorV1::NotAList);
    }
    let left_items =
        list_items(left.value_token()).ok_or(ParameterListTverskyIndexErrorV1::MalformedList)?;
    let right_items =
        list_items(right.value_token()).ok_or(ParameterListTverskyIndexErrorV1::MalformedList)?;
    let mut distinct_left: Vec<String> = Vec::new();
    for item in &left_items {
        if !distinct_left.contains(item) {
            distinct_left.push(item.clone());
        }
    }
    let mut distinct_right: Vec<String> = Vec::new();
    for item in &right_items {
        if !distinct_right.contains(item) {
            distinct_right.push(item.clone());
        }
    }
    let intersection = distinct_left
        .iter()
        .filter(|item| distinct_right.contains(item))
        .count();
    let left_only = distinct_left.len() - intersection;
    let right_only = distinct_right.len() - intersection;
    let numerator = intersection as f64;
    let denominator = numerator + alpha * left_only as f64 + beta * right_only as f64;
    Ok(numerator / denominator)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    #[test]
    fn jaccard_parameters_match_jaccard() {
        let a = value("left", "List", "(a, b, c)");
        let b = value("right", "List", "(b, c, d)");
        let index = list_tversky_index_v1(&a, &b, 1.0, 1.0).expect("valid");
        assert!((index - 2.0 / 4.0).abs() < 1e-12);
    }

    #[test]
    fn dice_parameters_match_dice() {
        let a = value("left", "List", "(a, b, c)");
        let b = value("right", "List", "(b, c, d)");
        let index = list_tversky_index_v1(&a, &b, 0.5, 0.5).expect("valid");
        assert!((index - 4.0 / 6.0).abs() < 1e-12);
    }

    #[test]
    fn zero_parameters_give_one() {
        let a = value("left", "List", "(a, b)");
        let b = value("right", "List", "(a, c)");
        assert_eq!(list_tversky_index_v1(&a, &b, 0.0, 0.0), Ok(1.0));
    }

    #[test]
    fn asymmetric_parameters() {
        let a = value("left", "List", "(a, b, c)");
        let b = value("right", "List", "(b, c, d)");
        let index = list_tversky_index_v1(&a, &b, 2.0, 0.5).expect("valid");
        let expected = 2.0 / (2.0 + 2.0 * 1.0 + 0.5 * 1.0);
        assert!((index - expected).abs() < 1e-12);
    }

    #[test]
    fn negative_parameter_fails_closed() {
        let a = value("left", "List", "(a)");
        let b = value("right", "List", "(a)");
        assert_eq!(
            list_tversky_index_v1(&a, &b, -0.1, 1.0),
            Err(ParameterListTverskyIndexErrorV1::InvalidParameters)
        );
    }

    #[test]
    fn left_non_list_fails_closed() {
        let a = value("gain", "Float", "0.5");
        let b = value("right", "List", "(a)");
        assert_eq!(
            list_tversky_index_v1(&a, &b, 1.0, 1.0),
            Err(ParameterListTverskyIndexErrorV1::NotAList)
        );
    }
}
