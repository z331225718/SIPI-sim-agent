//! AMI parameter list dedup keep-last core (P4B-02b167).
//!
//! Returns the canonical list token of a validated List-typed
//! `AmiParameterValueV1` value under the P4B-02b1 list rule
//! (`(item, item, ...)`, items trimmed, non-empty) keeping only the last
//! occurrence of each distinct trimmed item (raw byte equality, per the
//! P4B-02b0 raw-byte binding), ordered by last occurrence in the value's
//! trimmed item sequence. Every item appears exactly once in the result; the
//! result order is the last-occurrence order (distinct from the 02b98
//! first-occurrence order in general). This is the keep-last companion of
//! 02b98 parameter-list-dedup and of 02b107 distinct-count (the result item
//! count equals the distinct count).
//!
//! Fail-closed: the value not declared List yields `NotAList`; the token not
//! matching the List shape yields `MalformedList` (unreachable for values
//! built via `AmiParameterValueV1::try_new`, kept defensive instead of
//! panicking).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: list value dedup keep-last.
pub const PARAMETER_LIST_DEDUP_KEEP_LAST_POLICY_V1: &str =
    "sipi.p4b-02b167.parameter-list-dedup-keep-last-v1.dedup-keep-last";

/// Fail-closed error while computing dedup keep-last of a list value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListDedupKeepLastErrorV1 {
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

/// Return the canonical token of a List-typed value keeping only the last
/// occurrence of each distinct trimmed item (raw byte equality), ordered by
/// last occurrence.
pub fn parameter_list_dedup_keep_last_v1(
    value: &AmiParameterValueV1,
) -> Result<String, ParameterListDedupKeepLastErrorV1> {
    if value.parameter_type() != AmiParameterTypeV1::List {
        return Err(ParameterListDedupKeepLastErrorV1::NotAList);
    }
    let items =
        list_items(value.value_token()).ok_or(ParameterListDedupKeepLastErrorV1::MalformedList)?;
    let mut last_order: Vec<String> = Vec::new();
    for item in items.iter().rev() {
        if !last_order.contains(item) {
            last_order.push(item.clone());
        }
    }
    last_order.reverse();
    Ok(format!("({})", last_order.join(", ")))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    #[test]
    fn keeps_last_occurrence_in_last_occurrence_order() {
        let v = value("param", "List", "(a, b, a, c, b)");
        assert_eq!(
            parameter_list_dedup_keep_last_v1(&v),
            Ok("(a, c, b)".to_string())
        );
    }

    #[test]
    fn all_distinct_unchanged() {
        let v = value("param", "List", "(c, a, b)");
        assert_eq!(
            parameter_list_dedup_keep_last_v1(&v),
            Ok("(c, a, b)".to_string())
        );
    }

    #[test]
    fn single_item_unchanged() {
        let v = value("param", "List", "(x)");
        assert_eq!(parameter_list_dedup_keep_last_v1(&v), Ok("(x)".to_string()));
    }

    #[test]
    fn adjacent_duplicates_keep_last() {
        let v = value("param", "List", "(a, a, b, b, b)");
        assert_eq!(
            parameter_list_dedup_keep_last_v1(&v),
            Ok("(a, b)".to_string())
        );
    }

    #[test]
    fn spacing_is_canonicalized() {
        let v = value("param", "List", "( a , b , a )");
        assert_eq!(
            parameter_list_dedup_keep_last_v1(&v),
            Ok("(b, a)".to_string())
        );
    }

    #[test]
    fn non_list_fails_closed() {
        let v = value("gain", "Float", "0.5");
        assert_eq!(
            parameter_list_dedup_keep_last_v1(&v),
            Err(ParameterListDedupKeepLastErrorV1::NotAList)
        );
    }
}
