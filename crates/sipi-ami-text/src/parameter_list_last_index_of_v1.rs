//! AMI parameter list item last-index-of core (P4B-02b111).
//!
//! Locates the last position of a query item in a validated List-typed
//! `AmiParameterValueV1` under the P4B-02b1 list rule (`(item, item, ...)`,
//! items trimmed, non-empty): `last_index_of_parameter_list_item_v1` returns
//! the 0-based index of the last trimmed item that equals the query item
//! exactly (raw byte equality, per the P4B-02b0 raw-byte binding; the query
//! itself is not trimmed). This is the reverse-position companion of 02b110
//! first-position lookup and of 02b108 occurrence counting.
//!
//! Fail-closed: a non-List value yields `NotAList`; a token that does not
//! match the List shape yields `MalformedList` (unreachable for values built
//! via `AmiParameterValueV1::try_new`, kept defensive instead of panicking);
//! an absent item yields `ItemNotFound` (never conflated with the valid
//! index 0).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: last-position list item lookup.
pub const PARAMETER_LIST_LAST_INDEX_OF_POLICY_V1: &str =
    "sipi.p4b-02b111.parameter-list-last-index-of-v1.last-position-lookup";

/// Fail-closed error while locating a list item in a parameter value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListLastIndexOfErrorV1 {
    /// The value's declared type is not List.
    NotAList,
    /// The token does not match the List shape (defensive; unreachable for
    /// values built via `AmiParameterValueV1::try_new`).
    MalformedList,
    /// The query item is not present among the trimmed items.
    ItemNotFound,
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

/// Return the last index whose trimmed item equals the raw query item.
pub fn last_index_of_parameter_list_item_v1(
    value: &AmiParameterValueV1,
    item: &str,
) -> Result<usize, ParameterListLastIndexOfErrorV1> {
    if value.parameter_type() != AmiParameterTypeV1::List {
        return Err(ParameterListLastIndexOfErrorV1::NotAList);
    }
    let items = list_items(value.value_token())
        .ok_or(ParameterListLastIndexOfErrorV1::MalformedList)?;
    items
        .iter()
        .rposition(|candidate| candidate.as_str() == item)
        .ok_or(ParameterListLastIndexOfErrorV1::ItemNotFound)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    #[test]
    fn finds_last_occurrence() {
        let v = value("channels", "List", "(a, b, a, c)");
        assert_eq!(last_index_of_parameter_list_item_v1(&v, "a"), Ok(2));
        assert_eq!(last_index_of_parameter_list_item_v1(&v, "b"), Ok(1));
    }

    #[test]
    fn single_occurrence_is_first_and_last() {
        let v = value("channels", "List", "(a, b, c)");
        assert_eq!(last_index_of_parameter_list_item_v1(&v, "c"), Ok(2));
        assert_eq!(last_index_of_parameter_list_item_v1(&v, "a"), Ok(0));
    }

    #[test]
    fn absent_item_fails_closed() {
        let v = value("channels", "List", "(a, b)");
        assert_eq!(
            last_index_of_parameter_list_item_v1(&v, "z"),
            Err(ParameterListLastIndexOfErrorV1::ItemNotFound)
        );
    }

    #[test]
    fn query_is_raw_but_items_are_trimmed() {
        let v = value("channels", "List", "( a , b )");
        assert_eq!(last_index_of_parameter_list_item_v1(&v, "b"), Ok(1));
        assert_eq!(
            last_index_of_parameter_list_item_v1(&v, " b "),
            Err(ParameterListLastIndexOfErrorV1::ItemNotFound)
        );
    }

    #[test]
    fn non_list_fails_closed() {
        let float = value("gain", "Float", "0.5");
        assert_eq!(
            last_index_of_parameter_list_item_v1(&float, "0.5"),
            Err(ParameterListLastIndexOfErrorV1::NotAList)
        );
    }

    #[test]
    fn last_index_of_matches_occurrence_count_tail() {
        let v = value("channels", "List", "(x, y, x, z, x)");
        assert_eq!(last_index_of_parameter_list_item_v1(&v, "x"), Ok(4));
    }
}
