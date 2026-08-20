//! AMI parameter list item removal core (P4B-02b100).
//!
//! Removes one item of a validated List-typed `AmiParameterValueV1` under
//! the P4B-02b1 list rule (`(item, item, ...)`, items trimmed, non-empty):
//! `remove_parameter_list_item_v1` returns the canonical list token whose
//! item at the 0-based index is removed (remaining items re-joined with
//! `", "`). This is the delete companion of 02b99 replace, 02b84 access, and
//! 02b98 dedup in the list-edit family.
//!
//! Fail-closed: a non-List value yields `NotAList`; a token that does not
//! match the List shape yields `MalformedList` (unreachable for values built
//! via `AmiParameterValueV1::try_new`, kept defensive instead of panicking);
//! an index at or beyond the item count yields `IndexOutOfRange` carrying both
//! the requested index and the actual item count. Removing the sole item
//! yields the structurally empty token `()` (not a valid 02b1 List value; the
//! operation is total on the token level and does not re-validate).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: indexed list item removal.
pub const PARAMETER_LIST_REMOVE_POLICY_V1: &str =
    "sipi.p4b-02b100.parameter-list-remove-v1.list-item-removal";

/// Fail-closed error while removing one list item of a parameter value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListRemoveErrorV1 {
    /// The value's declared type is not List.
    NotAList,
    /// The token does not match the List shape (defensive; unreachable for
    /// values built via `AmiParameterValueV1::try_new`).
    MalformedList,
    /// The requested index is at or beyond the item count.
    IndexOutOfRange { index: usize, item_count: usize },
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

/// Remove the trimmed item at `index` of a List-typed validated value.
pub fn remove_parameter_list_item_v1(
    value: &AmiParameterValueV1,
    index: usize,
) -> Result<String, ParameterListRemoveErrorV1> {
    if value.parameter_type() != AmiParameterTypeV1::List {
        return Err(ParameterListRemoveErrorV1::NotAList);
    }
    let mut items = list_items(value.value_token())
        .ok_or(ParameterListRemoveErrorV1::MalformedList)?;
    if index >= items.len() {
        return Err(ParameterListRemoveErrorV1::IndexOutOfRange {
            index,
            item_count: items.len(),
        });
    }
    items.remove(index);
    Ok(format!("({})", items.join(", ")))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    #[test]
    fn removes_item_at_index() {
        let v = value("channels", "List", "(a, b, c)");
        assert_eq!(
            remove_parameter_list_item_v1(&v, 1),
            Ok("(a, c)".to_string())
        );
    }

    #[test]
    fn removes_first_and_last() {
        let v = value("channels", "List", "(a, b, c)");
        assert_eq!(
            remove_parameter_list_item_v1(&v, 0),
            Ok("(b, c)".to_string())
        );
        assert_eq!(
            remove_parameter_list_item_v1(&v, 2),
            Ok("(a, b)".to_string())
        );
    }

    #[test]
    fn out_of_range_fails_closed() {
        let v = value("channels", "List", "(a, b)");
        assert_eq!(
            remove_parameter_list_item_v1(&v, 2),
            Err(ParameterListRemoveErrorV1::IndexOutOfRange {
                index: 2,
                item_count: 2,
            })
        );
    }

    #[test]
    fn non_list_fails_closed() {
        let float = value("gain", "Float", "0.5");
        assert_eq!(
            remove_parameter_list_item_v1(&float, 0),
            Err(ParameterListRemoveErrorV1::NotAList)
        );
    }

    #[test]
    fn sole_item_removal_yields_empty_token() {
        let v = value("channels", "List", "(x)");
        assert_eq!(remove_parameter_list_item_v1(&v, 0), Ok("()".to_string()));
    }

    #[test]
    fn spacing_is_canonicalized() {
        let v = value("channels", "List", "( a , b , c )");
        assert_eq!(
            remove_parameter_list_item_v1(&v, 0),
            Ok("(b, c)".to_string())
        );
    }
}
