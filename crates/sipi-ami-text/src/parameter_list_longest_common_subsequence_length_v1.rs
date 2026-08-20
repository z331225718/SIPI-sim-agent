//! AMI parameter list longest common subsequence length core (P4B-02b142).
//!
//! Computes the length of the longest common subsequence (LCS) of two
//! validated List-typed `AmiParameterValueV1` values under the P4B-02b1 list
//! rule (`(item, item, ...)`, items trimmed, non-empty):
//! `list_longest_common_subsequence_length_v1` returns the length of the
//! longest sequence of trimmed items that appears in both values in order
//! (not necessarily contiguously), element-wise by raw byte equality (per the
//! P4B-02b0 raw-byte binding). The LCS length is at most the smaller item
//! count and equals the full smaller count when one value is a subsequence of
//! the other. This is the sequence companion of 02b130 longest-common-prefix
//! and of 02b131 longest-common-suffix.
//!
//! Fail-closed: either value not declared List yields `NotAList`; either
//! token not matching the List shape yields `MalformedList` (unreachable for
//! values built via `AmiParameterValueV1::try_new`, kept defensive instead
//! of panicking).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: list value LCS length.
pub const PARAMETER_LIST_LONGEST_COMMON_SUBSEQUENCE_LENGTH_POLICY_V1: &str =
    "sipi.p4b-02b142.parameter-list-longest-common-subsequence-length-v1.lcs-length";

/// Fail-closed error while computing the LCS length of two list values.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListLongestCommonSubsequenceLengthErrorV1 {
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

/// Return the LCS length of the trimmed items of two List-typed values
/// (element-wise byte equality, order-preserving, not necessarily contiguous).
pub fn list_longest_common_subsequence_length_v1(
    left: &AmiParameterValueV1,
    right: &AmiParameterValueV1,
) -> Result<usize, ParameterListLongestCommonSubsequenceLengthErrorV1> {
    if left.parameter_type() != AmiParameterTypeV1::List
        || right.parameter_type() != AmiParameterTypeV1::List
    {
        return Err(ParameterListLongestCommonSubsequenceLengthErrorV1::NotAList);
    }
    let left_items = list_items(left.value_token())
        .ok_or(ParameterListLongestCommonSubsequenceLengthErrorV1::MalformedList)?;
    let right_items = list_items(right.value_token())
        .ok_or(ParameterListLongestCommonSubsequenceLengthErrorV1::MalformedList)?;
    let n = left_items.len();
    let m = right_items.len();
    let mut table = vec![vec![0usize; m + 1]; n + 1];
    for i in (0..n).rev() {
        for j in (0..m).rev() {
            table[i][j] = if left_items[i] == right_items[j] {
                table[i + 1][j + 1] + 1
            } else {
                table[i + 1][j].max(table[i][j + 1])
            };
        }
    }
    Ok(table[0][0])
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    #[test]
    fn computes_lcs_length() {
        let a = value("left", "List", "(a, b, c, d)");
        let b = value("right", "List", "(b, d, e)");
        assert_eq!(
            list_longest_common_subsequence_length_v1(&a, &b),
            Ok(2)
        );
    }

    #[test]
    fn one_is_subsequence_of_other() {
        let a = value("left", "List", "(a, b, c)");
        let b = value("right", "List", "(x, a, y, b, c)");
        assert_eq!(
            list_longest_common_subsequence_length_v1(&a, &b),
            Ok(3)
        );
    }

    #[test]
    fn identical_values_full_length() {
        let a = value("left", "List", "(a, b, c)");
        let b = value("right", "List", "(a, b, c)");
        assert_eq!(
            list_longest_common_subsequence_length_v1(&a, &b),
            Ok(3)
        );
    }

    #[test]
    fn disjoint_values_zero() {
        let a = value("left", "List", "(a, b)");
        let b = value("right", "List", "(x, y)");
        assert_eq!(
            list_longest_common_subsequence_length_v1(&a, &b),
            Ok(0)
        );
    }

    #[test]
    fn left_non_list_fails_closed() {
        let a = value("gain", "Float", "0.5");
        let b = value("right", "List", "(a)");
        assert_eq!(
            list_longest_common_subsequence_length_v1(&a, &b),
            Err(ParameterListLongestCommonSubsequenceLengthErrorV1::NotAList)
        );
    }

    #[test]
    fn spacing_is_canonicalized() {
        let a = value("left", "List", "( a , b , c )");
        let b = value("right", "List", "(x, b, c)");
        assert_eq!(
            list_longest_common_subsequence_length_v1(&a, &b),
            Ok(2)
        );
    }
}
