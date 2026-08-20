//! AMI parameter list item deduplication core (P4B-02b98).
//!
//! Removes duplicate items from a validated List-typed `AmiParameterValueV1`
//! under the P4B-02b1 list rule (`(item, item, ...)`, items trimmed,
//! non-empty): `deduplicate_parameter_list_items_v1` returns the canonical
//! list token whose items are trimmed, compared by raw byte equality, and
//! re-joined with `", "`, keeping the first occurrence of each distinct item.
//! This is the list-normalization companion of 02b83 item counting, 02b84 item
//! access, and 02b85 membership.
//!
//! Fail-closed: a non-List value yields `NotAList`; a token that does not
//! match the List shape yields `MalformedList` (unreachable for values built
//! via `AmiParameterValueV1::try_new`, kept defensive instead of panicking).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: list item deduplication on a value.
pub const PARAMETER_LIST_DEDUP_POLICY_V1: &str =
    "sipi.p4b-02b98.parameter-list-dedup-v1.list-item-deduplication";

/// Fail-closed error while deduplicating a list value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListDedupErrorV1 {
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

/// Return the canonical list token with duplicate items removed.
pub fn deduplicate_parameter_list_items_v1(
    value: &AmiParameterValueV1,
) -> Result<String, ParameterListDedupErrorV1> {
    if value.parameter_type() != AmiParameterTypeV1::List {
        return Err(ParameterListDedupErrorV1::NotAList);
    }
    let items = list_items(value.value_token()).ok_or(ParameterListDedupErrorV1::MalformedList)?;
    let mut seen: Vec<String> = Vec::new();
    for item in items {
        if !seen.contains(&item) {
            seen.push(item);
        }
    }
    Ok(format!("({})", seen.join(", ")))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    #[test]
    fn removes_duplicates_keeping_first() {
        let v = value("channels", "List", "(a, b, a, c, b)");
        assert_eq!(
            deduplicate_parameter_list_items_v1(&v),
            Ok("(a, b, c)".to_string())
        );
    }

    #[test]
    fn no_duplicates_are_unchanged() {
        let v = value("channels", "List", "(a, b, c)");
        assert_eq!(
            deduplicate_parameter_list_items_v1(&v),
            Ok("(a, b, c)".to_string())
        );
    }

    #[test]
    fn items_are_trimmed_before_compare() {
        let v = value("channels", "List", "( a , a , b )");
        assert_eq!(
            deduplicate_parameter_list_items_v1(&v),
            Ok("(a, b)".to_string())
        );
        let compact = value("channels", "List", "(a,a,b)");
        assert_eq!(
            deduplicate_parameter_list_items_v1(&compact),
            Ok("(a, b)".to_string())
        );
    }

    #[test]
    fn non_list_fails_closed() {
        let float = value("gain", "Float", "0.5");
        assert_eq!(
            deduplicate_parameter_list_items_v1(&float),
            Err(ParameterListDedupErrorV1::NotAList)
        );
    }

    #[test]
    fn single_item_list_is_unchanged() {
        let v = value("channels", "List", "(x)");
        assert_eq!(
            deduplicate_parameter_list_items_v1(&v),
            Ok("(x)".to_string())
        );
    }

    #[test]
    fn all_duplicates_collapse_to_one() {
        let v = value("channels", "List", "(x, x, x)");
        assert_eq!(
            deduplicate_parameter_list_items_v1(&v),
            Ok("(x)".to_string())
        );
    }
}
