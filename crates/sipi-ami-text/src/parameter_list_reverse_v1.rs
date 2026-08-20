//! AMI parameter list item reverse core (P4B-02b104).
//!
//! Reverses the item order of a validated List-typed `AmiParameterValueV1`
//! under the P4B-02b1 list rule (`(item, item, ...)`, items trimmed,
//! non-empty): `reverse_parameter_list_items_v1` returns the canonical list
//! token with the trimmed items in reverse order (re-joined with `", "`).
//! This is the order-transformation companion of the list-edit family
//! (02b84 access, 02b98 dedup, 02b99 replace, 02b100 remove, 02b101 append,
//! 02b102 insert, 02b103 swap).
//!
//! Fail-closed: a non-List value yields `NotAList`; a token that does not
//! match the List shape yields `MalformedList` (unreachable for values built
//! via `AmiParameterValueV1::try_new`, kept defensive instead of panicking).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: list item order reversal.
pub const PARAMETER_LIST_REVERSE_POLICY_V1: &str =
    "sipi.p4b-02b104.parameter-list-reverse-v1.list-item-reverse";

/// Fail-closed error while reversing a list value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListReverseErrorV1 {
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

/// Reverse the trimmed items of a List-typed validated value.
pub fn reverse_parameter_list_items_v1(
    value: &AmiParameterValueV1,
) -> Result<String, ParameterListReverseErrorV1> {
    if value.parameter_type() != AmiParameterTypeV1::List {
        return Err(ParameterListReverseErrorV1::NotAList);
    }
    let mut items =
        list_items(value.value_token()).ok_or(ParameterListReverseErrorV1::MalformedList)?;
    items.reverse();
    Ok(format!("({})", items.join(", ")))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    #[test]
    fn reverses_items() {
        let v = value("channels", "List", "(a, b, c)");
        assert_eq!(
            reverse_parameter_list_items_v1(&v),
            Ok("(c, b, a)".to_string())
        );
    }

    #[test]
    fn four_items_reverse() {
        let v = value("channels", "List", "(a, b, c, d)");
        assert_eq!(
            reverse_parameter_list_items_v1(&v),
            Ok("(d, c, b, a)".to_string())
        );
    }

    #[test]
    fn single_item_is_unchanged() {
        let v = value("channels", "List", "(x)");
        assert_eq!(reverse_parameter_list_items_v1(&v), Ok("(x)".to_string()));
    }

    #[test]
    fn two_items_swap() {
        let v = value("channels", "List", "(a, b)");
        assert_eq!(
            reverse_parameter_list_items_v1(&v),
            Ok("(b, a)".to_string())
        );
    }

    #[test]
    fn non_list_fails_closed() {
        let float = value("gain", "Float", "0.5");
        assert_eq!(
            reverse_parameter_list_items_v1(&float),
            Err(ParameterListReverseErrorV1::NotAList)
        );
    }

    #[test]
    fn spacing_is_canonicalized() {
        let v = value("channels", "List", "( a , b , c )");
        assert_eq!(
            reverse_parameter_list_items_v1(&v),
            Ok("(c, b, a)".to_string())
        );
    }
}
