//! AMI parameter list item access core (P4B-02b84).
//!
//! Reads one item of a validated List-typed `AmiParameterValueV1` under the
//! P4B-02b1 list rule (`(item, item, ...)`, items trimmed, non-empty):
//! `get_parameter_list_item_v1` returns the trimmed item at a 0-based index.
//! This is the indexed companion of 02b83 list item counting and the
//! standalone value-level primitive for list element access (02b37 delivers
//! whole lists only inside tree decoding).
//!
//! Fail-closed: a non-List value yields `NotAList`; a token that does not
//! match the List shape yields `MalformedList` (unreachable for values built
//! via `AmiParameterValueV1::try_new`, kept defensive instead of panicking);
//! an index at or beyond the item count yields `IndexOutOfRange` carrying both
//! the requested index and the actual item count.

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: indexed list item access on a value.
pub const PARAMETER_LIST_ITEM_ACCESS_POLICY_V1: &str =
    "sipi.p4b-02b84.parameter-list-item-access-v1.list-item-access";

/// Fail-closed error while reading one list item of a parameter value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListItemAccessErrorV1 {
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

/// Read the trimmed item at `index` of a List-typed validated value.
pub fn get_parameter_list_item_v1(
    value: &AmiParameterValueV1,
    index: usize,
) -> Result<String, ParameterListItemAccessErrorV1> {
    if value.parameter_type() != AmiParameterTypeV1::List {
        return Err(ParameterListItemAccessErrorV1::NotAList);
    }
    let items =
        list_items(value.value_token()).ok_or(ParameterListItemAccessErrorV1::MalformedList)?;
    items
        .get(index)
        .cloned()
        .ok_or(ParameterListItemAccessErrorV1::IndexOutOfRange {
            index,
            item_count: items.len(),
        })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    #[test]
    fn gets_item_at_index() {
        let v = value("channels", "List", "(a, b, c)");
        assert_eq!(get_parameter_list_item_v1(&v, 0), Ok("a".to_string()));
        assert_eq!(get_parameter_list_item_v1(&v, 1), Ok("b".to_string()));
        assert_eq!(get_parameter_list_item_v1(&v, 2), Ok("c".to_string()));
    }

    #[test]
    fn item_spacing_is_trimmed() {
        let v = value("channels", "List", "( a , b )");
        assert_eq!(get_parameter_list_item_v1(&v, 0), Ok("a".to_string()));
        assert_eq!(get_parameter_list_item_v1(&v, 1), Ok("b".to_string()));
        let compact = value("channels", "List", "(a,b)");
        assert_eq!(get_parameter_list_item_v1(&compact, 1), Ok("b".to_string()));
    }

    #[test]
    fn out_of_range_fails_closed() {
        let v = value("channels", "List", "(a, b)");
        assert_eq!(
            get_parameter_list_item_v1(&v, 2),
            Err(ParameterListItemAccessErrorV1::IndexOutOfRange {
                index: 2,
                item_count: 2,
            })
        );
        assert_eq!(
            get_parameter_list_item_v1(&v, 10),
            Err(ParameterListItemAccessErrorV1::IndexOutOfRange {
                index: 10,
                item_count: 2,
            })
        );
    }

    #[test]
    fn non_list_fails_closed() {
        let float = value("gain", "Float", "0.5");
        assert_eq!(
            get_parameter_list_item_v1(&float, 0),
            Err(ParameterListItemAccessErrorV1::NotAList)
        );
    }

    #[test]
    fn first_and_last_items() {
        let v = value("taps", "List", "(tap0, tap1, tap2, tap3)");
        assert_eq!(get_parameter_list_item_v1(&v, 0), Ok("tap0".to_string()));
        assert_eq!(get_parameter_list_item_v1(&v, 3), Ok("tap3".to_string()));
    }

    #[test]
    fn single_item_list() {
        let v = value("channels", "List", "(x)");
        assert_eq!(get_parameter_list_item_v1(&v, 0), Ok("x".to_string()));
        assert_eq!(
            get_parameter_list_item_v1(&v, 1),
            Err(ParameterListItemAccessErrorV1::IndexOutOfRange {
                index: 1,
                item_count: 1,
            })
        );
    }
}
