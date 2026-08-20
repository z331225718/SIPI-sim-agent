//! AMI parameter list normalized entropy core (P4B-02b178).
//!
//! Returns the normalized Shannon entropy (evenness) of the frequency
//! distribution of the trimmed items of a validated List-typed
//! `AmiParameterValueV1` value under the P4B-02b1 list rule
//! (`(item, item, ...)`, items trimmed, non-empty):
//! `parameter_list_normalized_entropy_v1` computes the 02b176 Shannon
//! entropy in bits divided by `log2(len)` (raw byte equality, per the
//! P4B-02b0 raw-byte binding), returned as f64 in \[0, 1\] (0 for an
//! all-equal list, 1 for an all-distinct list; a single-item list yields 0,
//! the limit of H / log2(len) as the distribution concentrates). This is the
//! evenness (Pielou J') companion of 02b176 Shannon entropy and of 02b177
//! Gini impurity.
//!
//! Fail-closed: the value not declared List yields `NotAList`; the token not
//! matching the List shape yields `MalformedList` (unreachable for values
//! built via `AmiParameterValueV1::try_new`, kept defensive instead of
//! panicking).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: list value normalized entropy.
pub const PARAMETER_LIST_NORMALIZED_ENTROPY_POLICY_V1: &str =
    "sipi.p4b-02b178.parameter-list-normalized-entropy-v1.normalized-entropy";

/// Fail-closed error while computing the normalized entropy of a list value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListNormalizedEntropyErrorV1 {
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

/// Return the normalized Shannon entropy (evenness) of the trimmed-item
/// frequency distribution of a List-typed value (raw byte equality), as f64
/// in \[0, 1\].
pub fn parameter_list_normalized_entropy_v1(
    value: &AmiParameterValueV1,
) -> Result<f64, ParameterListNormalizedEntropyErrorV1> {
    if value.parameter_type() != AmiParameterTypeV1::List {
        return Err(ParameterListNormalizedEntropyErrorV1::NotAList);
    }
    let items = list_items(value.value_token())
        .ok_or(ParameterListNormalizedEntropyErrorV1::MalformedList)?;
    let item_count = items.len() as f64;
    let mut counts: Vec<(String, usize)> = Vec::new();
    for item in &items {
        match counts.iter_mut().find(|(existing, _)| existing == item) {
            Some((_, count)) => *count += 1,
            None => counts.push((item.clone(), 1)),
        }
    }
    if item_count <= 1.0 {
        // A single-item list has entropy 0 and log2(len) = 0; the quotient
        // 0/0 is resolved to 0, the limit of H / log2(len) as the
        // distribution concentrates on one item.
        return Ok(0.0);
    }
    let entropy = counts.iter().fold(0.0f64, |acc, (_, count)| {
        let p = *count as f64 / item_count;
        acc - p * p.log2()
    });
    Ok(entropy / item_count.log2())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    #[test]
    fn all_equal_evenness_zero() {
        let v = value("param", "List", "(a, a, a)");
        let e = parameter_list_normalized_entropy_v1(&v).expect("valid");
        assert!((e - 0.0).abs() < 1e-12);
    }

    #[test]
    fn all_distinct_evenness_one() {
        let v = value("param", "List", "(c, a, b)");
        let e = parameter_list_normalized_entropy_v1(&v).expect("valid");
        assert!((e - 1.0).abs() < 1e-12);
    }

    #[test]
    fn two_item_balanced_evenness_one() {
        let v = value("param", "List", "(a, b)");
        let e = parameter_list_normalized_entropy_v1(&v).expect("valid");
        assert!((e - 1.0).abs() < 1e-12);
    }

    #[test]
    fn single_item_evenness_zero() {
        // 0/0 resolved to 0 (the limit of H / log2(len) as the distribution
        // concentrates on one item).
        let v = value("param", "List", "(x)");
        let e = parameter_list_normalized_entropy_v1(&v).expect("valid");
        assert!((e - 0.0).abs() < 1e-12);
    }

    #[test]
    fn unbalanced_below_one() {
        // (a, a, a, b, c): entropy = 3/5*log2(5/3) + 2/5*log2(5/2) < log2(5).
        let v = value("param", "List", "(a, a, a, b, c)");
        let e = parameter_list_normalized_entropy_v1(&v).expect("valid");
        assert!(e > 0.0 && e < 1.0);
    }

    #[test]
    fn non_list_fails_closed() {
        let v = value("gain", "Float", "0.5");
        assert_eq!(
            parameter_list_normalized_entropy_v1(&v),
            Err(ParameterListNormalizedEntropyErrorV1::NotAList)
        );
    }
}
