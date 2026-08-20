//! AMI parameter list last-sublist index core (P4B-02b129).
//!
//! Locates the last start index of a query sublist in the trimmed items of a
//! validated List-typed `AmiParameterValueV1` under the P4B-02b1 list rule
//! (`(item, item, ...)`, items trimmed, non-empty):
//! `last_sublist_index_parameter_list_v1` returns the 0-based start index of
//! the latest window equal to the query items element-wise (raw byte
//! equality, per the P4B-02b0 raw-byte binding; query items are not trimmed).
//! An empty query sublist is vacuously contained at index 0. This is the
//! reverse-position companion of 02b128 first-sublist lookup and of 02b111
//! single-item last-index-of.
//!
//! Fail-closed: a non-List value yields `NotAList`; a token that does not
//! match the List shape yields `MalformedList` (unreachable for values built
//! via `AmiParameterValueV1::try_new`, kept defensive instead of panicking);
//! an absent sublist yields `SublistNotFound` (never conflated with the
//! valid index 0).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: last-position sublist lookup.
pub const PARAMETER_LIST_LAST_SUBLIST_INDEX_POLICY_V1: &str =
    "sipi.p4b-02b129.parameter-list-last-sublist-index-v1.last-sublist-position";

/// Fail-closed error while locating a sublist in a parameter value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListLastSublistIndexErrorV1 {
    /// The value's declared type is not List.
    NotAList,
    /// The token does not match the List shape (defensive; unreachable for
    /// values built via `AmiParameterValueV1::try_new`).
    MalformedList,
    /// The query sublist is not present as a contiguous subsequence.
    SublistNotFound,
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

/// Return the last start index of the query sublist in the trimmed items of a
/// List-typed validated value (contiguous, element-wise byte equality).
pub fn last_sublist_index_parameter_list_v1(
    value: &AmiParameterValueV1,
    sublist: &[&str],
) -> Result<usize, ParameterListLastSublistIndexErrorV1> {
    if value.parameter_type() != AmiParameterTypeV1::List {
        return Err(ParameterListLastSublistIndexErrorV1::NotAList);
    }
    let items = list_items(value.value_token())
        .ok_or(ParameterListLastSublistIndexErrorV1::MalformedList)?;
    if sublist.is_empty() {
        return Ok(0);
    }
    if sublist.len() > items.len() {
        return Err(ParameterListLastSublistIndexErrorV1::SublistNotFound);
    }
    let mut last: Option<usize> = None;
    for (index, window) in items.windows(sublist.len()).enumerate() {
        if window
            .iter()
            .zip(sublist.iter())
            .all(|(candidate, query)| candidate.as_str() == *query)
        {
            last = Some(index);
        }
    }
    last.ok_or(ParameterListLastSublistIndexErrorV1::SublistNotFound)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    #[test]
    fn finds_last_sublist_start_index() {
        let v = value("channels", "List", "(x, b, c, b, c)");
        let sublist = ["b", "c"];
        assert_eq!(last_sublist_index_parameter_list_v1(&v, &sublist), Ok(3));
    }

    #[test]
    fn single_match_is_first_and_last() {
        let v = value("channels", "List", "(a, b, c, d)");
        let sublist = ["c", "d"];
        assert_eq!(last_sublist_index_parameter_list_v1(&v, &sublist), Ok(2));
    }

    #[test]
    fn absent_sublist_fails_closed() {
        let v = value("channels", "List", "(a, b, c)");
        let sublist = ["b", "d"];
        assert_eq!(
            last_sublist_index_parameter_list_v1(&v, &sublist),
            Err(ParameterListLastSublistIndexErrorV1::SublistNotFound)
        );
    }

    #[test]
    fn empty_sublist_is_at_zero() {
        let v = value("channels", "List", "(a, b)");
        let sublist: [&str; 0] = [];
        assert_eq!(last_sublist_index_parameter_list_v1(&v, &sublist), Ok(0));
    }

    #[test]
    fn non_list_fails_closed() {
        let float = value("gain", "Float", "0.5");
        let sublist = ["0.5"];
        assert_eq!(
            last_sublist_index_parameter_list_v1(&float, &sublist),
            Err(ParameterListLastSublistIndexErrorV1::NotAList)
        );
    }

    #[test]
    fn items_are_trimmed_but_query_is_raw() {
        let v = value("channels", "List", "( a , b , c , b , c )");
        let sublist = ["b", "c"];
        assert_eq!(last_sublist_index_parameter_list_v1(&v, &sublist), Ok(3));
        let spaced = [" b ", "c"];
        assert_eq!(
            last_sublist_index_parameter_list_v1(&v, &spaced),
            Err(ParameterListLastSublistIndexErrorV1::SublistNotFound)
        );
    }
}
