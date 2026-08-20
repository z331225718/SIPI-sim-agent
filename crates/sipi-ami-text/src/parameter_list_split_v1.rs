//! AMI parameter list split-at-index core (P4B-02b114).
//!
//! Splits a validated List-typed `AmiParameterValueV1` under the P4B-02b1
//! list rule (`(item, item, ...)`, items trimmed, non-empty) at a 0-based
//! index: `split_parameter_list_at_index_v1` returns the pair of canonical
//! list tokens whose items are the trimmed items before and at/after the
//! split point (`[0, index)` and `[index, item_count)`, each re-joined with
//! `", "`). This is the partition inverse of 02b106 join and the split
//! companion of 02b109 slice.
//!
//! Fail-closed: a non-List value yields `NotAList`; a token that does not
//! match the List shape yields `MalformedList` (unreachable for values built
//! via `AmiParameterValueV1::try_new`, kept defensive instead of panicking);
//! an index beyond the item count (`index > item_count`) yields
//! `IndexOutOfRange` carrying the requested index and the actual item count.
//! A split at 0 or at the item count yields the structurally empty token
//! `()` on the empty side (not a valid 02b1 List value; the operation is
//! total on the token level and does not re-validate, mirroring 02b100
//! sole-item removal).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: list split at a 0-based index.
pub const PARAMETER_LIST_SPLIT_POLICY_V1: &str =
    "sipi.p4b-02b114.parameter-list-split-v1.split-at-index";

/// Fail-closed error while splitting one list value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListSplitErrorV1 {
    /// The value's declared type is not List.
    NotAList,
    /// The token does not match the List shape (defensive; unreachable for
    /// values built via `AmiParameterValueV1::try_new`).
    MalformedList,
    /// The split index is beyond the item count; carries the requested index
    /// and the actual item count.
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

/// Split the trimmed items at `index` into two canonical list tokens.
pub fn split_parameter_list_at_index_v1(
    value: &AmiParameterValueV1,
    index: usize,
) -> Result<(String, String), ParameterListSplitErrorV1> {
    if value.parameter_type() != AmiParameterTypeV1::List {
        return Err(ParameterListSplitErrorV1::NotAList);
    }
    let items = list_items(value.value_token())
        .ok_or(ParameterListSplitErrorV1::MalformedList)?;
    let item_count = items.len();
    if index > item_count {
        return Err(ParameterListSplitErrorV1::IndexOutOfRange {
            index,
            item_count,
        });
    }
    let left = format!("({})", items[..index].join(", "));
    let right = format!("({})", items[index..].join(", "));
    Ok((left, right))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    #[test]
    fn splits_at_middle() {
        let v = value("channels", "List", "(a, b, c, d)");
        assert_eq!(
            split_parameter_list_at_index_v1(&v, 2),
            Ok(("(a, b)".to_string(), "(c, d)".to_string()))
        );
    }

    #[test]
    fn splits_at_zero() {
        let v = value("channels", "List", "(a, b)");
        assert_eq!(
            split_parameter_list_at_index_v1(&v, 0),
            Ok(("()".to_string(), "(a, b)".to_string()))
        );
    }

    #[test]
    fn splits_at_end() {
        let v = value("channels", "List", "(a, b)");
        assert_eq!(
            split_parameter_list_at_index_v1(&v, 2),
            Ok(("(a, b)".to_string(), "()".to_string()))
        );
    }

    #[test]
    fn out_of_range_fails_closed() {
        let v = value("channels", "List", "(a, b)");
        assert_eq!(
            split_parameter_list_at_index_v1(&v, 3),
            Err(ParameterListSplitErrorV1::IndexOutOfRange {
                index: 3,
                item_count: 2,
            })
        );
    }

    #[test]
    fn non_list_fails_closed() {
        let float = value("gain", "Float", "0.5");
        assert_eq!(
            split_parameter_list_at_index_v1(&float, 0),
            Err(ParameterListSplitErrorV1::NotAList)
        );
    }

    #[test]
    fn spacing_is_canonicalized() {
        let v = value("channels", "List", "( a , b , c )");
        assert_eq!(
            split_parameter_list_at_index_v1(&v, 1),
            Ok(("(a)".to_string(), "(b, c)".to_string()))
        );
    }
}
