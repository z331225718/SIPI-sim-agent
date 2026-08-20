//! AMI parameter list palindrome check core (P4B-02b126).
//!
//! Checks whether the trimmed items of a validated List-typed
//! `AmiParameterValueV1` under the P4B-02b1 list rule (`(item, item, ...)`,
//! items trimmed, non-empty) read the same forward and backward:
//! `parameter_list_is_palindrome_v1` returns whether the sequence of trimmed
//! items equals its own reverse (raw byte equality, per the P4B-02b0
//! raw-byte binding); a single-item list is trivially a palindrome. This is
//! the symmetry companion of 02b104 reverse (a list is a palindrome exactly
//! when reversing it reproduces the same token).
//!
//! Fail-closed: a non-List value yields `NotAList`; a token that does not
//! match the List shape yields `MalformedList` (unreachable for values built
//! via `AmiParameterValueV1::try_new`, kept defensive instead of panicking).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: list palindrome check.
pub const PARAMETER_LIST_IS_PALINDROME_POLICY_V1: &str =
    "sipi.p4b-02b126.parameter-list-is-palindrome-v1.palindrome-check";

/// Fail-closed error while checking the palindromicity of one list value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListIsPalindromeErrorV1 {
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

/// Check whether the trimmed items of a List value equal their own reverse.
pub fn parameter_list_is_palindrome_v1(
    value: &AmiParameterValueV1,
) -> Result<bool, ParameterListIsPalindromeErrorV1> {
    if value.parameter_type() != AmiParameterTypeV1::List {
        return Err(ParameterListIsPalindromeErrorV1::NotAList);
    }
    let items = list_items(value.value_token())
        .ok_or(ParameterListIsPalindromeErrorV1::MalformedList)?;
    let reversed: Vec<String> = items.iter().rev().cloned().collect();
    Ok(items == reversed)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    #[test]
    fn palindrome_is_true() {
        let v = value("channels", "List", "(a, b, a)");
        assert_eq!(parameter_list_is_palindrome_v1(&v), Ok(true));
    }

    #[test]
    fn non_palindrome_is_false() {
        let v = value("channels", "List", "(a, b, c)");
        assert_eq!(parameter_list_is_palindrome_v1(&v), Ok(false));
    }

    #[test]
    fn even_length_palindrome_is_true() {
        let v = value("channels", "List", "(a, b, b, a)");
        assert_eq!(parameter_list_is_palindrome_v1(&v), Ok(true));
    }

    #[test]
    fn single_item_is_trivially_palindrome() {
        let v = value("channels", "List", "(x)");
        assert_eq!(parameter_list_is_palindrome_v1(&v), Ok(true));
    }

    #[test]
    fn non_list_fails_closed() {
        let float = value("gain", "Float", "0.5");
        assert_eq!(
            parameter_list_is_palindrome_v1(&float),
            Err(ParameterListIsPalindromeErrorV1::NotAList)
        );
    }

    #[test]
    fn spacing_is_canonicalized() {
        let v = value("channels", "List", "( a , b , a )");
        assert_eq!(parameter_list_is_palindrome_v1(&v), Ok(true));
    }
}
