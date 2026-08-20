//! AMI parameter list item insert core (P4B-02b102).
//!
//! Inserts one item into a validated List-typed `AmiParameterValueV1` under
//! the P4B-02b1 list rule (`(item, item, ...)`, items trimmed, non-empty):
//! `insert_parameter_list_item_v1` returns the canonical list token with the
//! trimmed new item inserted before the current item at the 0-based index
//! (index equal to the item count appends, mirroring 02b101). This extends the
//! list-edit family (02b84 access, 02b98 dedup, 02b99 replace, 02b100 remove,
//! 02b101 append) with positional insertion.
//!
//! Fail-closed: a non-List value yields `NotAList`; a token that does not
//! match the List shape yields `MalformedList` (unreachable for values built
//! via `AmiParameterValueV1::try_new`, kept defensive instead of panicking);
//! a new item that is empty after trimming yields `EmptyNewItem`; an index
//! beyond the item count yields `IndexOutOfRange` carrying both the requested
//! index and the actual item count.

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: positional list item insertion.
pub const PARAMETER_LIST_INSERT_POLICY_V1: &str =
    "sipi.p4b-02b102.parameter-list-insert-v1.list-item-insert";

/// Fail-closed error while inserting one list item into a parameter value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListInsertErrorV1 {
    /// The value's declared type is not List.
    NotAList,
    /// The token does not match the List shape (defensive; unreachable for
    /// values built via `AmiParameterValueV1::try_new`).
    MalformedList,
    /// The new item is empty after trimming (would violate 02b1).
    EmptyNewItem,
    /// The requested index is beyond the item count.
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

/// Insert the trimmed new item at `index` of a List-typed validated value.
pub fn insert_parameter_list_item_v1(
    value: &AmiParameterValueV1,
    index: usize,
    new_item: &str,
) -> Result<String, ParameterListInsertErrorV1> {
    if value.parameter_type() != AmiParameterTypeV1::List {
        return Err(ParameterListInsertErrorV1::NotAList);
    }
    let mut items = list_items(value.value_token())
        .ok_or(ParameterListInsertErrorV1::MalformedList)?;
    let trimmed = new_item.trim();
    if trimmed.is_empty() {
        return Err(ParameterListInsertErrorV1::EmptyNewItem);
    }
    if index > items.len() {
        return Err(ParameterListInsertErrorV1::IndexOutOfRange {
            index,
            item_count: items.len(),
        });
    }
    items.insert(index, trimmed.to_string());
    Ok(format!("({})", items.join(", ")))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    #[test]
    fn inserts_at_middle() {
        let v = value("channels", "List", "(a, b, c)");
        assert_eq!(
            insert_parameter_list_item_v1(&v, 1, "x"),
            Ok("(a, x, b, c)".to_string())
        );
    }

    #[test]
    fn inserts_at_start() {
        let v = value("channels", "List", "(a, b)");
        assert_eq!(
            insert_parameter_list_item_v1(&v, 0, "x"),
            Ok("(x, a, b)".to_string())
        );
    }

    #[test]
    fn inserts_at_end_equals_append() {
        let v = value("channels", "List", "(a, b)");
        assert_eq!(
            insert_parameter_list_item_v1(&v, 2, "c"),
            Ok("(a, b, c)".to_string())
        );
    }

    #[test]
    fn out_of_range_fails_closed() {
        let v = value("channels", "List", "(a, b)");
        assert_eq!(
            insert_parameter_list_item_v1(&v, 3, "x"),
            Err(ParameterListInsertErrorV1::IndexOutOfRange {
                index: 3,
                item_count: 2,
            })
        );
    }

    #[test]
    fn empty_new_item_fails_closed() {
        let v = value("channels", "List", "(a)");
        assert_eq!(
            insert_parameter_list_item_v1(&v, 0, "   "),
            Err(ParameterListInsertErrorV1::EmptyNewItem)
        );
    }

    #[test]
    fn non_list_fails_closed() {
        let float = value("gain", "Float", "0.5");
        assert_eq!(
            insert_parameter_list_item_v1(&float, 0, "x"),
            Err(ParameterListInsertErrorV1::NotAList)
        );
    }
}
