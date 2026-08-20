//! AMI parameter list head/tail core (P4B-02b117).
//!
//! Reads the first (head) and last (tail) trimmed items of a validated
//! List-typed `AmiParameterValueV1` under the P4B-02b1 list rule
//! (`(item, item, ...)`, items trimmed, non-empty):
//! `parameter_list_head_tail_v1` returns `(head, tail)` where head is the
//! item at index 0 and tail is the item at index item_count - 1. For a
//! single-item list head and tail coincide. This is the edge-access
//! companion of 02b84 item access and of 02b110/02b111 index lookups.
//!
//! Fail-closed: a non-List value yields `NotAList`; a token that does not
//! match the List shape yields `MalformedList` (unreachable for values built
//! via `AmiParameterValueV1::try_new`, kept defensive instead of panicking;
//! covers the structurally empty token, whose head/tail are undefined).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: list edge (head/tail) access.
pub const PARAMETER_LIST_HEAD_TAIL_POLICY_V1: &str =
    "sipi.p4b-02b117.parameter-list-head-tail-v1.edge-access";

/// Fail-closed error while reading the head/tail of a parameter value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListHeadTailErrorV1 {
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

/// Return the first (head) and last (tail) trimmed items of a List value.
pub fn parameter_list_head_tail_v1(
    value: &AmiParameterValueV1,
) -> Result<(String, String), ParameterListHeadTailErrorV1> {
    if value.parameter_type() != AmiParameterTypeV1::List {
        return Err(ParameterListHeadTailErrorV1::NotAList);
    }
    let items = list_items(value.value_token())
        .ok_or(ParameterListHeadTailErrorV1::MalformedList)?;
    let head = items.first().expect("non-empty by 02b1 rule").clone();
    let tail = items.last().expect("non-empty by 02b1 rule").clone();
    Ok((head, tail))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    #[test]
    fn head_and_tail() {
        let v = value("channels", "List", "(a, b, c)");
        assert_eq!(
            parameter_list_head_tail_v1(&v),
            Ok(("a".to_string(), "c".to_string()))
        );
    }

    #[test]
    fn two_items() {
        let v = value("channels", "List", "(a, b)");
        assert_eq!(
            parameter_list_head_tail_v1(&v),
            Ok(("a".to_string(), "b".to_string()))
        );
    }

    #[test]
    fn single_item_head_tail_coincide() {
        let v = value("channels", "List", "(x)");
        assert_eq!(
            parameter_list_head_tail_v1(&v),
            Ok(("x".to_string(), "x".to_string()))
        );
    }

    #[test]
    fn spacing_is_canonicalized() {
        let v = value("channels", "List", "( a , b )");
        assert_eq!(
            parameter_list_head_tail_v1(&v),
            Ok(("a".to_string(), "b".to_string()))
        );
    }

    #[test]
    fn non_list_fails_closed() {
        let float = value("gain", "Float", "0.5");
        assert_eq!(
            parameter_list_head_tail_v1(&float),
            Err(ParameterListHeadTailErrorV1::NotAList)
        );
    }

    #[test]
    fn head_matches_first_occurrence_and_tail_last() {
        let v = value("channels", "List", "(a, b, a, c)");
        assert_eq!(
            parameter_list_head_tail_v1(&v),
            Ok(("a".to_string(), "c".to_string()))
        );
    }
}
