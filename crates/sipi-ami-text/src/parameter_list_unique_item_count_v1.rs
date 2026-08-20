//! AMI parameter list unique-item count core (P4B-02b136).
//!
//! Counts the unique trimmed items of a validated List-typed
//! `AmiParameterValueV1` under the P4B-02b1 list rule (`(item, item, ...)`,
//! items trimmed, non-empty): `parameter_list_unique_item_count_v1` returns
//! the number of distinct trimmed items that occur exactly once (raw byte
//! equality, per the P4B-02b0 raw-byte binding). This is the
//! exactly-once companion of 02b121 frequency mapping (whose entries with
//! count 1 it sums) and of 02b107 distinct counting (the unique count never
//! exceeds the distinct count).
//!
//! Fail-closed: a non-List value yields `NotAList`; a token that does not
//! match the List shape yields `MalformedList` (unreachable for values built
//! via `AmiParameterValueV1::try_new`, kept defensive instead of panicking).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: exactly-once item counting.
pub const PARAMETER_LIST_UNIQUE_ITEM_COUNT_POLICY_V1: &str =
    "sipi.p4b-02b136.parameter-list-unique-item-count-v1.unique-items";

/// Fail-closed error while counting unique items of one list value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListUniqueItemCountErrorV1 {
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

/// Count the distinct trimmed items that occur exactly once in a List value.
pub fn parameter_list_unique_item_count_v1(
    value: &AmiParameterValueV1,
) -> Result<usize, ParameterListUniqueItemCountErrorV1> {
    if value.parameter_type() != AmiParameterTypeV1::List {
        return Err(ParameterListUniqueItemCountErrorV1::NotAList);
    }
    let items = list_items(value.value_token())
        .ok_or(ParameterListUniqueItemCountErrorV1::MalformedList)?;
    let mut unique = 0usize;
    for item in &items {
        if items.iter().filter(|candidate| *candidate == item).count() == 1 {
            unique += 1;
        }
    }
    Ok(unique)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    #[test]
    fn all_distinct_are_unique() {
        let v = value("channels", "List", "(a, b, c)");
        assert_eq!(parameter_list_unique_item_count_v1(&v), Ok(3));
    }

    #[test]
    fn repeated_items_are_not_unique() {
        let v = value("channels", "List", "(a, a, b, c, c)");
        assert_eq!(parameter_list_unique_item_count_v1(&v), Ok(1));
    }

    #[test]
    fn all_equal_has_no_unique() {
        let v = value("channels", "List", "(x, x, x)");
        assert_eq!(parameter_list_unique_item_count_v1(&v), Ok(0));
    }

    #[test]
    fn single_item_is_unique() {
        let v = value("channels", "List", "(x)");
        assert_eq!(parameter_list_unique_item_count_v1(&v), Ok(1));
    }

    #[test]
    fn non_list_fails_closed() {
        let float = value("gain", "Float", "0.5");
        assert_eq!(
            parameter_list_unique_item_count_v1(&float),
            Err(ParameterListUniqueItemCountErrorV1::NotAList)
        );
    }

    #[test]
    fn spacing_is_canonicalized() {
        let v = value("channels", "List", "( a , a , b )");
        assert_eq!(parameter_list_unique_item_count_v1(&v), Ok(1));
    }
}
