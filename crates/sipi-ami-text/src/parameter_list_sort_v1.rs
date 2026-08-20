//! AMI parameter list item sort core (P4B-02b105).
//!
//! Sorts the items of a validated List-typed `AmiParameterValueV1` under the
//! P4B-02b1 list rule (`(item, item, ...)`, items trimmed, non-empty):
//! `sort_parameter_list_items_v1` returns the canonical list token with the
//! trimmed items sorted in byte (lexicographic) order, duplicates preserved
//! (re-joined with `", "`). This is the order-transform companion of 02b104
//! reverse in the list-edit family. Note: items are sorted by raw byte order,
//! so numeric spellings sort lexicographically (`10` before `2`).
//!
//! Fail-closed: a non-List value yields `NotAList`; a token that does not
//! match the List shape yields `MalformedList` (unreachable for values built
//! via `AmiParameterValueV1::try_new`, kept defensive instead of panicking).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: list item sort on a value.
pub const PARAMETER_LIST_SORT_POLICY_V1: &str =
    "sipi.p4b-02b105.parameter-list-sort-v1.list-item-sort";

/// Fail-closed error while sorting a list value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListSortErrorV1 {
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

/// Sort the trimmed items of a List-typed validated value (byte order).
pub fn sort_parameter_list_items_v1(
    value: &AmiParameterValueV1,
) -> Result<String, ParameterListSortErrorV1> {
    if value.parameter_type() != AmiParameterTypeV1::List {
        return Err(ParameterListSortErrorV1::NotAList);
    }
    let mut items = list_items(value.value_token())
        .ok_or(ParameterListSortErrorV1::MalformedList)?;
    items.sort();
    Ok(format!("({})", items.join(", ")))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    #[test]
    fn sorts_items() {
        let v = value("channels", "List", "(c, a, b)");
        assert_eq!(
            sort_parameter_list_items_v1(&v),
            Ok("(a, b, c)".to_string())
        );
    }

    #[test]
    fn numeric_spellings_sort_lexicographically() {
        let v = value("taps", "List", "(2, 10, 1)");
        assert_eq!(
            sort_parameter_list_items_v1(&v),
            Ok("(1, 10, 2)".to_string())
        );
    }

    #[test]
    fn duplicate_items_are_preserved() {
        let v = value("channels", "List", "(b, a, b, c)");
        assert_eq!(
            sort_parameter_list_items_v1(&v),
            Ok("(a, b, b, c)".to_string())
        );
    }

    #[test]
    fn non_list_fails_closed() {
        let float = value("gain", "Float", "0.5");
        assert_eq!(
            sort_parameter_list_items_v1(&float),
            Err(ParameterListSortErrorV1::NotAList)
        );
    }

    #[test]
    fn single_item_is_unchanged() {
        let v = value("channels", "List", "(x)");
        assert_eq!(
            sort_parameter_list_items_v1(&v),
            Ok("(x)".to_string())
        );
    }

    #[test]
    fn spacing_is_canonicalized() {
        let v = value("channels", "List", "( c , a , b )");
        assert_eq!(
            sort_parameter_list_items_v1(&v),
            Ok("(a, b, c)".to_string())
        );
    }
}
