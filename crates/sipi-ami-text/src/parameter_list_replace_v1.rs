//! AMI parameter list item replace core (P4B-02b99).
//!
//! Replaces one item of a validated List-typed `AmiParameterValueV1` under
//! the P4B-02b1 list rule (`(item, item, ...)`, items trimmed, non-empty):
//! `replace_parameter_list_item_v1` returns the canonical list token whose
//! item at the 0-based index is replaced by the trimmed new item (re-joined
//! with `", "`). This is the write companion of 02b84 item access (read) and
//! the list-edit primitive complementing 02b98 dedup.
//!
//! Fail-closed: a non-List value yields `NotAList`; a token that does not
//! match the List shape yields `MalformedList` (unreachable for values built
//! via `AmiParameterValueV1::try_new`, kept defensive instead of panicking);
//! an index at or beyond the item count yields `IndexOutOfRange` carrying both
//! the requested index and the actual item count.

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: indexed list item replacement.
pub const PARAMETER_LIST_REPLACE_POLICY_V1: &str =
    "sipi.p4b-02b99.parameter-list-replace-v1.list-item-replacement";

/// Fail-closed error while replacing one list item of a parameter value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListReplaceErrorV1 {
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

/// Replace the trimmed item at `index` of a List-typed validated value.
pub fn replace_parameter_list_item_v1(
    value: &AmiParameterValueV1,
    index: usize,
    new_item: &str,
) -> Result<String, ParameterListReplaceErrorV1> {
    if value.parameter_type() != AmiParameterTypeV1::List {
        return Err(ParameterListReplaceErrorV1::NotAList);
    }
    let mut items = list_items(value.value_token())
        .ok_or(ParameterListReplaceErrorV1::MalformedList)?;
    if index >= items.len() {
        return Err(ParameterListReplaceErrorV1::IndexOutOfRange {
            index,
            item_count: items.len(),
        });
    }
    items[index] = new_item.trim().to_string();
    Ok(format!("({})", items.join(", ")))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    #[test]
    fn replaces_item_at_index() {
        let v = value("channels", "List", "(a, b, c)");
        assert_eq!(
            replace_parameter_list_item_v1(&v, 1, "x"),
            Ok("(a, x, c)".to_string())
        );
    }

    #[test]
    fn replaces_first_and_last() {
        let v = value("channels", "List", "(a, b, c)");
        assert_eq!(
            replace_parameter_list_item_v1(&v, 0, "x"),
            Ok("(x, b, c)".to_string())
        );
        assert_eq!(
            replace_parameter_list_item_v1(&v, 2, "x"),
            Ok("(a, b, x)".to_string())
        );
    }

    #[test]
    fn new_item_is_trimmed() {
        let v = value("channels", "List", "(a, b)");
        assert_eq!(
            replace_parameter_list_item_v1(&v, 0, "  x  "),
            Ok("(x, b)".to_string())
        );
    }

    #[test]
    fn out_of_range_fails_closed() {
        let v = value("channels", "List", "(a, b)");
        assert_eq!(
            replace_parameter_list_item_v1(&v, 2, "x"),
            Err(ParameterListReplaceErrorV1::IndexOutOfRange {
                index: 2,
                item_count: 2,
            })
        );
    }

    #[test]
    fn non_list_fails_closed() {
        let float = value("gain", "Float", "0.5");
        assert_eq!(
            replace_parameter_list_item_v1(&float, 0, "x"),
            Err(ParameterListReplaceErrorV1::NotAList)
        );
    }

    #[test]
    fn single_item_replace() {
        let v = value("channels", "List", "(x)");
        assert_eq!(
            replace_parameter_list_item_v1(&v, 0, "y"),
            Ok("(y)".to_string())
        );
        assert_eq!(
            replace_parameter_list_item_v1(&v, 1, "y"),
            Err(ParameterListReplaceErrorV1::IndexOutOfRange {
                index: 1,
                item_count: 1,
            })
        );
    }
}
