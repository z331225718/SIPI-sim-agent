//! AMI parameter list longest common suffix core (P4B-02b131).
//!
//! Computes the longest common suffix of two validated List-typed
//! `AmiParameterValueV1` values under the P4B-02b1 list rule
//! (`(item, item, ...)`, items trimmed, non-empty):
//! `list_longest_common_suffix_v1` returns the canonical list token of the
//! longest trailing run of trimmed items equal element-wise between the two
//! values, read from their ends toward their starts (raw byte equality, per
//! the P4B-02b0 raw-byte binding). An empty common suffix yields the
//! structurally empty token `()` (not a valid 02b1 List value; the operation
//! is total on the token level and does not re-validate, mirroring 02b100
//! sole-item removal). This is the end-aligned mirror of 02b130
//! longest-common-prefix and the list-value companion of 02b67 tree-path
//! prefix relations.
//!
//! Fail-closed: either value not declared List yields `NotAList`; either
//! token not matching the List shape yields `MalformedList` (unreachable for
//! values built via `AmiParameterValueV1::try_new`, kept defensive instead
//! of panicking).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: list value common suffix.
pub const PARAMETER_LIST_LONGEST_COMMON_SUFFIX_POLICY_V1: &str =
    "sipi.p4b-02b131.parameter-list-longest-common-suffix-v1.common-suffix";

/// Fail-closed error while computing the common suffix of two list values.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListLongestCommonSuffixErrorV1 {
    /// A value's declared type is not List.
    NotAList,
    /// A token does not match the List shape (defensive; unreachable for
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

/// Return the canonical token of the longest common suffix of two List-typed
/// validated values (element-wise byte equality, end-aligned).
pub fn list_longest_common_suffix_v1(
    left: &AmiParameterValueV1,
    right: &AmiParameterValueV1,
) -> Result<String, ParameterListLongestCommonSuffixErrorV1> {
    if left.parameter_type() != AmiParameterTypeV1::List
        || right.parameter_type() != AmiParameterTypeV1::List
    {
        return Err(ParameterListLongestCommonSuffixErrorV1::NotAList);
    }
    let left_items = list_items(left.value_token())
        .ok_or(ParameterListLongestCommonSuffixErrorV1::MalformedList)?;
    let right_items = list_items(right.value_token())
        .ok_or(ParameterListLongestCommonSuffixErrorV1::MalformedList)?;
    let mut suffix: Vec<String> = Vec::new();
    for (l, r) in left_items.iter().rev().zip(right_items.iter().rev()) {
        if l == r {
            suffix.push(l.clone());
        } else {
            break;
        }
    }
    suffix.reverse();
    Ok(format!("({})", suffix.join(", ")))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    #[test]
    fn common_suffix() {
        let a = value("left", "List", "(a, b, c, d)");
        let b = value("right", "List", "(x, c, d)");
        assert_eq!(
            list_longest_common_suffix_v1(&a, &b),
            Ok("(c, d)".to_string())
        );
    }

    #[test]
    fn one_is_suffix_of_other() {
        let a = value("left", "List", "(x, b, c)");
        let b = value("right", "List", "(b, c)");
        assert_eq!(
            list_longest_common_suffix_v1(&a, &b),
            Ok("(b, c)".to_string())
        );
    }

    #[test]
    fn empty_suffix_yields_empty_token() {
        let a = value("left", "List", "(a, b)");
        let b = value("right", "List", "(b, a)");
        assert_eq!(
            list_longest_common_suffix_v1(&a, &b),
            Ok("()".to_string())
        );
    }

    #[test]
    fn equal_values_are_their_own_suffix() {
        let a = value("left", "List", "(a, b, c)");
        let b = value("right", "List", "(a, b, c)");
        assert_eq!(
            list_longest_common_suffix_v1(&a, &b),
            Ok("(a, b, c)".to_string())
        );
    }

    #[test]
    fn right_non_list_fails_closed() {
        let a = value("left", "List", "(a)");
        let b = value("gain", "Float", "0.5");
        assert_eq!(
            list_longest_common_suffix_v1(&a, &b),
            Err(ParameterListLongestCommonSuffixErrorV1::NotAList)
        );
    }

    #[test]
    fn spacing_is_canonicalized() {
        let a = value("left", "List", "( a , b , c )");
        let b = value("right", "List", "(x, b, c)");
        assert_eq!(
            list_longest_common_suffix_v1(&a, &b),
            Ok("(b, c)".to_string())
        );
    }
}
