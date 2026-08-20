//! AMI parameter list item append core (P4B-02b101).
//!
//! Appends one item to a validated List-typed `AmiParameterValueV1` under
//! the P4B-02b1 list rule (`(item, item, ...)`, items trimmed, non-empty):
//! `append_parameter_list_item_v1` returns the canonical list token with the
//! trimmed new item appended (re-joined with `", "`). This completes the
//! list-edit family: 02b84 access (read), 02b98 dedup, 02b99 replace, 02b100
//! remove, and this append.
//!
//! Fail-closed: a non-List value yields `NotAList`; a token that does not
//! match the List shape yields `MalformedList` (unreachable for values built
//! via `AmiParameterValueV1::try_new`, kept defensive instead of panicking);
//! a new item that is empty after trimming yields `EmptyNewItem` (appending
//! it would produce a list violating the 02b1 non-empty item rule).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: list item append on a value.
pub const PARAMETER_LIST_APPEND_POLICY_V1: &str =
    "sipi.p4b-02b101.parameter-list-append-v1.list-item-append";

/// Fail-closed error while appending one list item to a parameter value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListAppendErrorV1 {
    /// The value's declared type is not List.
    NotAList,
    /// The token does not match the List shape (defensive; unreachable for
    /// values built via `AmiParameterValueV1::try_new`).
    MalformedList,
    /// The new item is empty after trimming (would violate 02b1).
    EmptyNewItem,
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

/// Append the trimmed new item to a List-typed validated value.
pub fn append_parameter_list_item_v1(
    value: &AmiParameterValueV1,
    new_item: &str,
) -> Result<String, ParameterListAppendErrorV1> {
    if value.parameter_type() != AmiParameterTypeV1::List {
        return Err(ParameterListAppendErrorV1::NotAList);
    }
    let mut items =
        list_items(value.value_token()).ok_or(ParameterListAppendErrorV1::MalformedList)?;
    let trimmed = new_item.trim();
    if trimmed.is_empty() {
        return Err(ParameterListAppendErrorV1::EmptyNewItem);
    }
    items.push(trimmed.to_string());
    Ok(format!("({})", items.join(", ")))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    #[test]
    fn appends_item() {
        let v = value("channels", "List", "(a, b)");
        assert_eq!(
            append_parameter_list_item_v1(&v, "c"),
            Ok("(a, b, c)".to_string())
        );
    }

    #[test]
    fn appends_to_single_item() {
        let v = value("channels", "List", "(a)");
        assert_eq!(
            append_parameter_list_item_v1(&v, "b"),
            Ok("(a, b)".to_string())
        );
    }

    #[test]
    fn new_item_is_trimmed() {
        let v = value("channels", "List", "(a)");
        assert_eq!(
            append_parameter_list_item_v1(&v, "  b  "),
            Ok("(a, b)".to_string())
        );
    }

    #[test]
    fn empty_new_item_fails_closed() {
        let v = value("channels", "List", "(a)");
        assert_eq!(
            append_parameter_list_item_v1(&v, "   "),
            Err(ParameterListAppendErrorV1::EmptyNewItem)
        );
    }

    #[test]
    fn non_list_fails_closed() {
        let float = value("gain", "Float", "0.5");
        assert_eq!(
            append_parameter_list_item_v1(&float, "x"),
            Err(ParameterListAppendErrorV1::NotAList)
        );
    }

    #[test]
    fn spacing_is_canonicalized() {
        let v = value("channels", "List", "( a , b )");
        assert_eq!(
            append_parameter_list_item_v1(&v, "c"),
            Ok("(a, b, c)".to_string())
        );
    }
}
