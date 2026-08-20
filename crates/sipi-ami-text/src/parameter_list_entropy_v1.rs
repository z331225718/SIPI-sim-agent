//! AMI parameter list Shannon entropy core (P4B-02b176).
//!
//! Returns the Shannon entropy in bits of the frequency distribution of the
//! trimmed items of a validated List-typed `AmiParameterValueV1` value under
//! the P4B-02b1 list rule (`(item, item, ...)`, items trimmed, non-empty):
//! `parameter_list_entropy_v1` computes `-sum(p_i * log2(p_i))` over the
//! distinct trimmed items with empirical probabilities `p_i = count_i / len`
//! (raw byte equality, per the P4B-02b0 raw-byte binding), returned as f64 in
//! \[0, log2(len)\] (0 for an all-equal list, log2(len) for an all-distinct
//! list). This is the information-theoretic companion of 02b121 frequency and
//! of 02b165 mode items (a single-mode distribution has entropy 0).
//!
//! Fail-closed: the value not declared List yields `NotAList`; the token not
//! matching the List shape yields `MalformedList` (unreachable for values
//! built via `AmiParameterValueV1::try_new`, kept defensive instead of
//! panicking).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: list value Shannon entropy.
pub const PARAMETER_LIST_ENTROPY_POLICY_V1: &str =
    "sipi.p4b-02b176.parameter-list-entropy-v1.entropy";

/// Fail-closed error while computing the entropy of a list value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListEntropyErrorV1 {
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

/// Return the Shannon entropy in bits of the trimmed-item frequency
/// distribution of a List-typed value (raw byte equality), as f64 in
/// \[0, log2(len)\].
pub fn parameter_list_entropy_v1(
    value: &AmiParameterValueV1,
) -> Result<f64, ParameterListEntropyErrorV1> {
    if value.parameter_type() != AmiParameterTypeV1::List {
        return Err(ParameterListEntropyErrorV1::NotAList);
    }
    let items = list_items(value.value_token())
        .ok_or(ParameterListEntropyErrorV1::MalformedList)?;
    let item_count = items.len() as f64;
    let mut counts: Vec<(String, usize)> = Vec::new();
    for item in &items {
        match counts.iter_mut().find(|(existing, _)| existing == item) {
            Some((_, count)) => *count += 1,
            None => counts.push((item.clone(), 1)),
        }
    }
    let entropy = counts.iter().fold(0.0f64, |acc, (_, count)| {
        let p = *count as f64 / item_count;
        acc - p * p.log2()
    });
    Ok(entropy)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    #[test]
    fn all_equal_entropy_zero() {
        let v = value("param", "List", "(a, a, a)");
        let entropy = parameter_list_entropy_v1(&v).expect("valid");
        assert!((entropy - 0.0).abs() < 1e-12);
    }

    #[test]
    fn all_distinct_entropy_log_len() {
        let v = value("param", "List", "(c, a, b)");
        let entropy = parameter_list_entropy_v1(&v).expect("valid");
        assert!((entropy - 3.0f64.log2()).abs() < 1e-12);
    }

    #[test]
    fn two_item_balanced_entropy_one() {
        let v = value("param", "List", "(a, b)");
        let entropy = parameter_list_entropy_v1(&v).expect("valid");
        assert!((entropy - 1.0).abs() < 1e-12);
    }

    #[test]
    fn single_item_entropy_zero() {
        let v = value("param", "List", "(x)");
        let entropy = parameter_list_entropy_v1(&v).expect("valid");
        assert!((entropy - 0.0).abs() < 1e-12);
    }

    #[test]
    fn spacing_is_canonicalized() {
        let v = value("param", "List", "( a , b )");
        let entropy = parameter_list_entropy_v1(&v).expect("valid");
        assert!((entropy - 1.0).abs() < 1e-12);
    }

    #[test]
    fn non_list_fails_closed() {
        let v = value("gain", "Float", "0.5");
        assert_eq!(
            parameter_list_entropy_v1(&v),
            Err(ParameterListEntropyErrorV1::NotAList)
        );
    }
}
