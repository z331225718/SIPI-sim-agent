//! AMI parameter list item count core (P4B-02b83).
//!
//! Counts the items of a validated List-typed `AmiParameterValueV1` under the
//! P4B-02b1 list rule (`(item, item, ...)`, items trimmed, non-empty):
//! `count_parameter_list_items_v1` returns the number of items. This is the
//! standalone value-level primitive for list sizes, distinct from 02b37 tree
//! leaf decoding (which needs a tree and a type map) and from 02b75 canonical
//! spelling (which rewrites spellings).
//!
//! Fail-closed: a value whose declared type is not List yields `NotAList`; a
//! token that does not match the List shape yields `MalformedList` (unreachable
//! for values built via `AmiParameterValueV1::try_new`, kept defensive instead
//! of panicking).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: list item counting on a value.
pub const PARAMETER_LIST_ITEM_COUNT_POLICY_V1: &str =
    "sipi.p4b-02b83.parameter-list-item-count-v1.list-item-count";

/// Fail-closed error while counting the items of a parameter value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListItemCountErrorV1 {
    /// The value's declared type is not List.
    NotAList,
    /// The token does not match the List shape (defensive; unreachable for
    /// values built via `AmiParameterValueV1::try_new`).
    MalformedList,
}

/// Count the items of a List-typed validated parameter value.
pub fn count_parameter_list_items_v1(
    value: &AmiParameterValueV1,
) -> Result<usize, ParameterListItemCountErrorV1> {
    if value.parameter_type() != AmiParameterTypeV1::List {
        return Err(ParameterListItemCountErrorV1::NotAList);
    }
    let token = value.value_token();
    if !token.starts_with('(') || !token.ends_with(')') || token.len() < 2 {
        return Err(ParameterListItemCountErrorV1::MalformedList);
    }
    let inner = &token[1..token.len() - 1];
    if inner.is_empty() {
        return Err(ParameterListItemCountErrorV1::MalformedList);
    }
    let items: Vec<&str> = inner
        .split(',')
        .map(|item| item.trim())
        .filter(|item| !item.is_empty())
        .collect();
    // Mirror 02b1: every item must be non-empty after trimming; if any is
    // empty the shape is malformed (defensive for validated inputs).
    let all_non_empty = inner
        .split(',')
        .all(|item| !item.trim().is_empty());
    if !all_non_empty {
        return Err(ParameterListItemCountErrorV1::MalformedList);
    }
    Ok(items.len())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    #[test]
    fn counts_list_items() {
        let v = value("channels", "List", "(a, b, c)");
        assert_eq!(count_parameter_list_items_v1(&v), Ok(3));
    }

    #[test]
    fn single_item_list() {
        let v = value("channels", "List", "(x)");
        assert_eq!(count_parameter_list_items_v1(&v), Ok(1));
    }

    #[test]
    fn item_spacing_is_ignored() {
        let v = value("channels", "List", "( a , b , c , d )");
        assert_eq!(count_parameter_list_items_v1(&v), Ok(4));
        let compact = value("channels", "List", "(a,b,c)");
        assert_eq!(count_parameter_list_items_v1(&compact), Ok(3));
    }

    #[test]
    fn non_list_fails_closed() {
        let float = value("gain", "Float", "0.5");
        assert_eq!(
            count_parameter_list_items_v1(&float),
            Err(ParameterListItemCountErrorV1::NotAList)
        );
        let integer = value("steps", "Integer", "7");
        assert_eq!(
            count_parameter_list_items_v1(&integer),
            Err(ParameterListItemCountErrorV1::NotAList)
        );
    }

    #[test]
    fn string_items_are_counted_as_raw() {
        let v = value("taps", "List", "(1, tap2, tap3)");
        assert_eq!(count_parameter_list_items_v1(&v), Ok(3));
    }

    #[test]
    fn count_matches_typed_equivalence_length() {
        let a = value("channels", "List", "(a, b, c)");
        let b = value("channels", "List", "(a,b,c)");
        assert_eq!(
            count_parameter_list_items_v1(&a),
            count_parameter_list_items_v1(&b)
        );
    }
}
