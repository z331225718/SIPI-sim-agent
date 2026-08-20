//! AMI parameter list item swap core (P4B-02b103).
//!
//! Swaps two items of a validated List-typed `AmiParameterValueV1` under the
//! P4B-02b1 list rule (`(item, item, ...)`, items trimmed, non-empty):
//! `swap_parameter_list_items_v1` returns the canonical list token whose
//! items at the two 0-based indices are exchanged (equal indices leave the
//! token unchanged; items re-joined with `", "`). This extends the list-edit
//! family (02b84 access, 02b98 dedup, 02b99 replace, 02b100 remove, 02b101
//! append, 02b102 insert) with positional exchange.
//!
//! Fail-closed: a non-List value yields `NotAList`; a token that does not
//! match the List shape yields `MalformedList` (unreachable for values built
//! via `AmiParameterValueV1::try_new`, kept defensive instead of panicking);
//! either index at or beyond the item count yields `IndexOutOfRange` carrying
//! the offending index and the actual item count.

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: positional list item swap.
pub const PARAMETER_LIST_SWAP_POLICY_V1: &str =
    "sipi.p4b-02b103.parameter-list-swap-v1.list-item-swap";

/// Fail-closed error while swapping two list items of a parameter value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListSwapErrorV1 {
    /// The value's declared type is not List.
    NotAList,
    /// The token does not match the List shape (defensive; unreachable for
    /// values built via `AmiParameterValueV1::try_new`).
    MalformedList,
    /// An index is at or beyond the item count.
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

/// Swap the trimmed items at `index_a` and `index_b` of a List value.
pub fn swap_parameter_list_items_v1(
    value: &AmiParameterValueV1,
    index_a: usize,
    index_b: usize,
) -> Result<String, ParameterListSwapErrorV1> {
    if value.parameter_type() != AmiParameterTypeV1::List {
        return Err(ParameterListSwapErrorV1::NotAList);
    }
    let mut items =
        list_items(value.value_token()).ok_or(ParameterListSwapErrorV1::MalformedList)?;
    for index in [index_a, index_b] {
        if index >= items.len() {
            return Err(ParameterListSwapErrorV1::IndexOutOfRange {
                index,
                item_count: items.len(),
            });
        }
    }
    items.swap(index_a, index_b);
    Ok(format!("({})", items.join(", ")))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    #[test]
    fn swaps_two_indices() {
        let v = value("channels", "List", "(a, b, c)");
        assert_eq!(
            swap_parameter_list_items_v1(&v, 0, 2),
            Ok("(c, b, a)".to_string())
        );
    }

    #[test]
    fn swaps_middle_pair() {
        let v = value("channels", "List", "(a, b, c, d)");
        assert_eq!(
            swap_parameter_list_items_v1(&v, 1, 2),
            Ok("(a, c, b, d)".to_string())
        );
    }

    #[test]
    fn equal_indices_leave_unchanged() {
        let v = value("channels", "List", "(a, b, c)");
        assert_eq!(
            swap_parameter_list_items_v1(&v, 1, 1),
            Ok("(a, b, c)".to_string())
        );
    }

    #[test]
    fn out_of_range_fails_closed() {
        let v = value("channels", "List", "(a, b)");
        assert_eq!(
            swap_parameter_list_items_v1(&v, 0, 2),
            Err(ParameterListSwapErrorV1::IndexOutOfRange {
                index: 2,
                item_count: 2,
            })
        );
        assert_eq!(
            swap_parameter_list_items_v1(&v, 2, 0),
            Err(ParameterListSwapErrorV1::IndexOutOfRange {
                index: 2,
                item_count: 2,
            })
        );
    }

    #[test]
    fn non_list_fails_closed() {
        let float = value("gain", "Float", "0.5");
        assert_eq!(
            swap_parameter_list_items_v1(&float, 0, 1),
            Err(ParameterListSwapErrorV1::NotAList)
        );
    }

    #[test]
    fn spacing_is_canonicalized() {
        let v = value("channels", "List", "( a , b , c )");
        assert_eq!(
            swap_parameter_list_items_v1(&v, 0, 1),
            Ok("(b, a, c)".to_string())
        );
    }
}
