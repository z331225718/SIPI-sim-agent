//! AMI parameter list longest common subsequence core (P4B-02b159).
//!
//! Computes one deterministic longest common subsequence (LCS) of two
//! validated List-typed `AmiParameterValueV1` values under the P4B-02b1 list
//! rule (`(item, item, ...)`, items trimmed, non-empty):
//! `list_longest_common_subsequence_v1` returns the canonical list token of
//! the lexicographically left-biased LCS of the two values' trimmed item
//! sequences, element-wise by raw byte equality (per the P4B-02b0 raw-byte
//! binding), order-preserving, not necessarily contiguous. Tie-breaking is
//! deterministic: when items are equal the match is taken; otherwise the
//! reconstruction prefers skipping the left item on a length tie, so both
//! product and independent reference produce the same items. An empty LCS
//! yields the structural empty token `()` (token-layer total function, no
//! re-validation, mirroring 02b100). This is the items companion of 02b142
//! LCS length (the returned item count equals the 02b142 length).
//!
//! Fail-closed: either value not declared List yields `NotAList`; either
//! token not matching the List shape yields `MalformedList` (unreachable for
//! values built via `AmiParameterValueV1::try_new`, kept defensive instead
//! of panicking).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: list value LCS items.
pub const PARAMETER_LIST_LONGEST_COMMON_SUBSEQUENCE_POLICY_V1: &str =
    "sipi.p4b-02b159.parameter-list-longest-common-subsequence-v1.lcs";

/// Fail-closed error while computing the LCS of two list values.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListLongestCommonSubsequenceErrorV1 {
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

/// Return the canonical token of one deterministic LCS of the trimmed items
/// of two List-typed values (byte equality, order-preserving, left-biased
/// tie-breaking).
pub fn list_longest_common_subsequence_v1(
    left: &AmiParameterValueV1,
    right: &AmiParameterValueV1,
) -> Result<String, ParameterListLongestCommonSubsequenceErrorV1> {
    if left.parameter_type() != AmiParameterTypeV1::List
        || right.parameter_type() != AmiParameterTypeV1::List
    {
        return Err(ParameterListLongestCommonSubsequenceErrorV1::NotAList);
    }
    let left_items = list_items(left.value_token())
        .ok_or(ParameterListLongestCommonSubsequenceErrorV1::MalformedList)?;
    let right_items = list_items(right.value_token())
        .ok_or(ParameterListLongestCommonSubsequenceErrorV1::MalformedList)?;
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
    let mut picked: Vec<String> = Vec::new();
    let (mut i, mut j) = (0usize, 0usize);
    while i < n && j < m {
        if left_items[i] == right_items[j] {
            picked.push(left_items[i].clone());
            i += 1;
            j += 1;
        } else if table[i + 1][j] >= table[i][j + 1] {
            i += 1;
        } else {
            j += 1;
        }
    }
    Ok(if picked.is_empty() {
        "()".to_string()
    } else {
        format!("({})", picked.join(", "))
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    #[test]
    fn computes_deterministic_lcs() {
        let a = value("left", "List", "(a, b, c, d)");
        let b = value("right", "List", "(b, d, e)");
        assert_eq!(
            list_longest_common_subsequence_v1(&a, &b),
            Ok("(b, d)".to_string())
        );
    }

    #[test]
    fn one_is_subsequence_of_other() {
        let a = value("left", "List", "(a, b, c)");
        let b = value("right", "List", "(x, a, y, b, c)");
        assert_eq!(
            list_longest_common_subsequence_v1(&a, &b),
            Ok("(a, b, c)".to_string())
        );
    }

    #[test]
    fn identical_values_full_length() {
        let a = value("left", "List", "(a, b, c)");
        let b = value("right", "List", "(a, b, c)");
        assert_eq!(
            list_longest_common_subsequence_v1(&a, &b),
            Ok("(a, b, c)".to_string())
        );
    }

    #[test]
    fn disjoint_values_empty_token() {
        let a = value("left", "List", "(a, b)");
        let b = value("right", "List", "(x, y)");
        assert_eq!(
            list_longest_common_subsequence_v1(&a, &b),
            Ok("()".to_string())
        );
    }

    #[test]
    fn tie_breaks_left_biased() {
        // left=(a, b), right=(b, a): both (a) and (b) are LCS of length 1;
        // left-biased tie-breaking must pick (b) because at (0,0) the items
        // differ and table[1][0] == table[0][1], so the left item is skipped.
        let a = value("left", "List", "(a, b)");
        let b = value("right", "List", "(b, a)");
        assert_eq!(
            list_longest_common_subsequence_v1(&a, &b),
            Ok("(b)".to_string())
        );
    }

    #[test]
    fn left_non_list_fails_closed() {
        let a = value("gain", "Float", "0.5");
        let b = value("right", "List", "(a)");
        assert_eq!(
            list_longest_common_subsequence_v1(&a, &b),
            Err(ParameterListLongestCommonSubsequenceErrorV1::NotAList)
        );
    }
}
