//! AMI parameter list longest common prefix core (P4B-02b130).
//!
//! Computes the longest common prefix of two validated List-typed
//! `AmiParameterValueV1` values under the P4B-02b1 list rule
//! (`(item, item, ...)`, items trimmed, non-empty):
//! `list_longest_common_prefix_v1` returns the canonical list token of the
//! longest initial run of trimmed items equal element-wise between the two
//! values (raw byte equality, per the P4B-02b0 raw-byte binding). An empty
//! common prefix yields the structurally empty token `()` (not a valid 02b1
//! List value; the operation is total on the token level and does not
//! re-validate, mirroring 02b100 sole-item removal). This is the list-value
//! companion of 02b67 tree-path longest-common-prefix and of 02b106 join.
//!
//! Fail-closed: either value not declared List yields `NotAList`; either
//! token not matching the List shape yields `MalformedList` (unreachable for
//! values built via `AmiParameterValueV1::try_new`, kept defensive instead
//! of panicking).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: list value common prefix.
pub const PARAMETER_LIST_LONGEST_COMMON_PREFIX_POLICY_V1: &str =
    "sipi.p4b-02b130.parameter-list-longest-common-prefix-v1.common-prefix";

/// Fail-closed error while computing the common prefix of two list values.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListLongestCommonPrefixErrorV1 {
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

/// Return the canonical token of the longest common prefix of two List-typed
/// validated values (element-wise byte equality).
pub fn list_longest_common_prefix_v1(
    left: &AmiParameterValueV1,
    right: &AmiParameterValueV1,
) -> Result<String, ParameterListLongestCommonPrefixErrorV1> {
    if left.parameter_type() != AmiParameterTypeV1::List
        || right.parameter_type() != AmiParameterTypeV1::List
    {
        return Err(ParameterListLongestCommonPrefixErrorV1::NotAList);
    }
    let left_items = list_items(left.value_token())
        .ok_or(ParameterListLongestCommonPrefixErrorV1::MalformedList)?;
    let right_items = list_items(right.value_token())
        .ok_or(ParameterListLongestCommonPrefixErrorV1::MalformedList)?;
    let mut prefix: Vec<String> = Vec::new();
    for (l, r) in left_items.iter().zip(right_items.iter()) {
        if l == r {
            prefix.push(l.clone());
        } else {
            break;
        }
    }
    Ok(format!("({})", prefix.join(", ")))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    #[test]
    fn common_prefix() {
        let a = value("left", "List", "(a, b, c, d)");
        let b = value("right", "List", "(a, b, x)");
        assert_eq!(
            list_longest_common_prefix_v1(&a, &b),
            Ok("(a, b)".to_string())
        );
    }

    #[test]
    fn one_is_prefix_of_other() {
        let a = value("left", "List", "(a, b)");
        let b = value("right", "List", "(a, b, c)");
        assert_eq!(
            list_longest_common_prefix_v1(&a, &b),
            Ok("(a, b)".to_string())
        );
    }

    #[test]
    fn empty_prefix_yields_empty_token() {
        let a = value("left", "List", "(a, b)");
        let b = value("right", "List", "(x, y)");
        assert_eq!(list_longest_common_prefix_v1(&a, &b), Ok("()".to_string()));
    }

    #[test]
    fn equal_values_are_their_own_prefix() {
        let a = value("left", "List", "(a, b, c)");
        let b = value("right", "List", "(a, b, c)");
        assert_eq!(
            list_longest_common_prefix_v1(&a, &b),
            Ok("(a, b, c)".to_string())
        );
    }

    #[test]
    fn left_non_list_fails_closed() {
        let a = value("gain", "Float", "0.5");
        let b = value("right", "List", "(a)");
        assert_eq!(
            list_longest_common_prefix_v1(&a, &b),
            Err(ParameterListLongestCommonPrefixErrorV1::NotAList)
        );
    }

    #[test]
    fn spacing_is_canonicalized() {
        let a = value("left", "List", "( a , b )");
        let b = value("right", "List", "(a, b, c)");
        assert_eq!(
            list_longest_common_prefix_v1(&a, &b),
            Ok("(a, b)".to_string())
        );
    }
}
