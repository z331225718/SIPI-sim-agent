//! AMI parameter list distinct item count core (P4B-02b107).
//!
//! Counts the distinct items of a validated List-typed `AmiParameterValueV1`
//! under the P4B-02b1 list rule (`(item, item, ...)`, items trimmed,
//! non-empty): `count_distinct_parameter_list_items_v1` returns the number of
//! distinct trimmed items (raw byte equality, first-occurrence semantics for
//! membership). This is the distinct-count companion of 02b83 total item
//! counting and of 02b98 dedup (which rewrites the token).
//!
//! Fail-closed: a non-List value yields `NotAList`; a token that does not
//! match the List shape yields `MalformedList` (unreachable for values built
//! via `AmiParameterValueV1::try_new`, kept defensive instead of panicking).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: distinct list item counting.
pub const PARAMETER_LIST_DISTINCT_COUNT_POLICY_V1: &str =
    "sipi.p4b-02b107.parameter-list-distinct-count-v1.distinct-item-count";

/// Fail-closed error while counting distinct items of a list value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListDistinctCountErrorV1 {
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

/// Count the distinct trimmed items of a List-typed validated value.
pub fn count_distinct_parameter_list_items_v1(
    value: &AmiParameterValueV1,
) -> Result<usize, ParameterListDistinctCountErrorV1> {
    if value.parameter_type() != AmiParameterTypeV1::List {
        return Err(ParameterListDistinctCountErrorV1::NotAList);
    }
    let items = list_items(value.value_token())
        .ok_or(ParameterListDistinctCountErrorV1::MalformedList)?;
    let mut distinct: Vec<String> = Vec::new();
    for item in items {
        if !distinct.contains(&item) {
            distinct.push(item);
        }
    }
    Ok(distinct.len())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    #[test]
    fn counts_distinct_items() {
        let v = value("channels", "List", "(a, b, a, c, b)");
        assert_eq!(count_distinct_parameter_list_items_v1(&v), Ok(3));
    }

    #[test]
    fn all_distinct() {
        let v = value("channels", "List", "(a, b, c)");
        assert_eq!(count_distinct_parameter_list_items_v1(&v), Ok(3));
    }

    #[test]
    fn all_same() {
        let v = value("channels", "List", "(x, x, x)");
        assert_eq!(count_distinct_parameter_list_items_v1(&v), Ok(1));
    }

    #[test]
    fn non_list_fails_closed() {
        let float = value("gain", "Float", "0.5");
        assert_eq!(
            count_distinct_parameter_list_items_v1(&float),
            Err(ParameterListDistinctCountErrorV1::NotAList)
        );
    }

    #[test]
    fn spacing_is_trimmed() {
        let v = value("channels", "List", "( a , a , b )");
        assert_eq!(count_distinct_parameter_list_items_v1(&v), Ok(2));
    }

    #[test]
    fn single_item() {
        let v = value("channels", "List", "(x)");
        assert_eq!(count_distinct_parameter_list_items_v1(&v), Ok(1));
    }
}
