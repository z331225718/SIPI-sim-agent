//! AMI parameter list most-frequent item core (P4B-02b122).
//!
//! Finds the most frequent distinct trimmed item of a validated List-typed
//! `AmiParameterValueV1` under the P4B-02b1 list rule (`(item, item, ...)`,
//! items trimmed, non-empty): `most_frequent_parameter_list_item_v1` returns
//! the `(item, count)` pair whose item has the largest total occurrence count
//! (raw byte equality, per the P4B-02b0 raw-byte binding); ties are resolved
//! to the item that first occurs earliest in the list. This is the
//! frequency-max companion of 02b121 frequency mapping (whose entries it
//! maximizes) and of 02b107 distinct counting (every count is at least 1 and
//! at most the item count).
//!
//! Fail-closed: a non-List value yields `NotAList`; a token that does not
//! match the List shape yields `MalformedList` (unreachable for values built
//! via `AmiParameterValueV1::try_new`, kept defensive instead of panicking).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: most frequent item analysis.
pub const PARAMETER_LIST_MOST_FREQUENT_POLICY_V1: &str =
    "sipi.p4b-02b122.parameter-list-most-frequent-v1.most-frequent-item";

/// Fail-closed error while analyzing one list value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListMostFrequentErrorV1 {
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

/// Return the (item, count) of the most frequent distinct trimmed item; ties
/// resolve to the earliest first-occurrence item.
pub fn most_frequent_parameter_list_item_v1(
    value: &AmiParameterValueV1,
) -> Result<(String, usize), ParameterListMostFrequentErrorV1> {
    if value.parameter_type() != AmiParameterTypeV1::List {
        return Err(ParameterListMostFrequentErrorV1::NotAList);
    }
    let items =
        list_items(value.value_token()).ok_or(ParameterListMostFrequentErrorV1::MalformedList)?;
    let mut best: (String, usize) = (items[0].clone(), 0);
    for item in &items {
        let count = items.iter().filter(|candidate| *candidate == item).count();
        if count > best.1 {
            best = (item.clone(), count);
        }
    }
    Ok(best)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    #[test]
    fn finds_most_frequent() {
        let v = value("channels", "List", "(a, b, a, c, a, b)");
        assert_eq!(
            most_frequent_parameter_list_item_v1(&v),
            Ok(("a".to_string(), 3))
        );
    }

    #[test]
    fn tie_resolves_to_earliest_first_occurrence() {
        let v = value("channels", "List", "(b, a, b, a)");
        assert_eq!(
            most_frequent_parameter_list_item_v1(&v),
            Ok(("b".to_string(), 2))
        );
    }

    #[test]
    fn all_distinct_returns_first_item() {
        let v = value("channels", "List", "(a, b, c)");
        assert_eq!(
            most_frequent_parameter_list_item_v1(&v),
            Ok(("a".to_string(), 1))
        );
    }

    #[test]
    fn single_item_is_most_frequent() {
        let v = value("channels", "List", "(x)");
        assert_eq!(
            most_frequent_parameter_list_item_v1(&v),
            Ok(("x".to_string(), 1))
        );
    }

    #[test]
    fn non_list_fails_closed() {
        let float = value("gain", "Float", "0.5");
        assert_eq!(
            most_frequent_parameter_list_item_v1(&float),
            Err(ParameterListMostFrequentErrorV1::NotAList)
        );
    }

    #[test]
    fn spacing_is_canonicalized() {
        let v = value("channels", "List", "( a , b , a )");
        assert_eq!(
            most_frequent_parameter_list_item_v1(&v),
            Ok(("a".to_string(), 2))
        );
    }
}
