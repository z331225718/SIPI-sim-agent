//! AMI parameter list inversion count core (P4B-02b133).
//!
//! Counts the inversions of the trimmed items of a validated List-typed
//! `AmiParameterValueV1` under the P4B-02b1 list rule (`(item, item, ...)`,
//! items trimmed, non-empty): `parameter_list_inversion_count_v1` returns
//! the number of index pairs `(i, j)` with `i < j` whose items are in
//! strictly decreasing byte order (raw byte equality and byte comparison, per
//! the P4B-02b0 raw-byte binding). A sorted list has zero inversions; a
//! reversed list of length n has n*(n-1)/2 inversions. This is the
//! disorder companion of 02b105 sort and of 02b124 sortedness check.
//!
//! Fail-closed: a non-List value yields `NotAList`; a token that does not
//! match the List shape yields `MalformedList` (unreachable for values built
//! via `AmiParameterValueV1::try_new`, kept defensive instead of panicking).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: pairwise inversion counting.
pub const PARAMETER_LIST_INVERSION_COUNT_POLICY_V1: &str =
    "sipi.p4b-02b133.parameter-list-inversion-count-v1.inversion-count";

/// Fail-closed error while counting inversions of one list value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListInversionCountErrorV1 {
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

/// Count the index pairs (i, j) with i < j whose trimmed items are in
/// strictly decreasing byte order.
pub fn parameter_list_inversion_count_v1(
    value: &AmiParameterValueV1,
) -> Result<usize, ParameterListInversionCountErrorV1> {
    if value.parameter_type() != AmiParameterTypeV1::List {
        return Err(ParameterListInversionCountErrorV1::NotAList);
    }
    let items =
        list_items(value.value_token()).ok_or(ParameterListInversionCountErrorV1::MalformedList)?;
    let mut count = 0usize;
    for i in 0..items.len() {
        for j in (i + 1)..items.len() {
            if items[i] > items[j] {
                count += 1;
            }
        }
    }
    Ok(count)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    #[test]
    fn sorted_list_has_zero_inversions() {
        let v = value("channels", "List", "(a, b, c)");
        assert_eq!(parameter_list_inversion_count_v1(&v), Ok(0));
    }

    #[test]
    fn reversed_list_has_max_inversions() {
        let v = value("channels", "List", "(c, b, a)");
        assert_eq!(parameter_list_inversion_count_v1(&v), Ok(3));
    }

    #[test]
    fn counts_partial_inversions() {
        let v = value("channels", "List", "(a, c, b, d)");
        assert_eq!(parameter_list_inversion_count_v1(&v), Ok(1));
    }

    #[test]
    fn equal_items_are_not_inversions() {
        let v = value("channels", "List", "(b, a, a)");
        assert_eq!(parameter_list_inversion_count_v1(&v), Ok(2));
    }

    #[test]
    fn non_list_fails_closed() {
        let float = value("gain", "Float", "0.5");
        assert_eq!(
            parameter_list_inversion_count_v1(&float),
            Err(ParameterListInversionCountErrorV1::NotAList)
        );
    }

    #[test]
    fn single_item_has_zero_inversions() {
        let v = value("channels", "List", "(x)");
        assert_eq!(parameter_list_inversion_count_v1(&v), Ok(0));
    }
}
