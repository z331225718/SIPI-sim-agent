//! AMI parameter list mode items core (P4B-02b165).
//!
//! Returns all mode trimmed items of a validated List-typed
//! `AmiParameterValueV1` value under the P4B-02b1 list rule
//! (`(item, item, ...)`, items trimmed, non-empty):
//! `parameter_list_mode_items_v1` returns the canonical list token of the
//! distinct trimmed items whose occurrence count equals the maximum count
//! (raw byte equality, per the P4B-02b0 raw-byte binding), ordered by first
//! occurrence in the value's trimmed item sequence. The list is non-empty by
//! rule so at least one mode always exists; a list where every item is
//! distinct has all items as modes. This is the multi-mode companion of
//! 02b122 most-frequent (a single arbitrary tie-winner) and of 02b121
//! frequency (the modes are the items at maximum count).
//!
//! Fail-closed: the value not declared List yields `NotAList`; the token not
//! matching the List shape yields `MalformedList` (unreachable for values
//! built via `AmiParameterValueV1::try_new`, kept defensive instead of
//! panicking).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: list value mode items.
pub const PARAMETER_LIST_MODE_ITEMS_POLICY_V1: &str =
    "sipi.p4b-02b165.parameter-list-mode-items-v1.mode-items";

/// Fail-closed error while computing the mode items of a list value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListModeItemsErrorV1 {
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

/// Return the canonical token of the mode trimmed items of a List-typed value:
/// distinct items at maximum occurrence count (raw byte equality), ordered by
/// first occurrence.
pub fn parameter_list_mode_items_v1(
    value: &AmiParameterValueV1,
) -> Result<String, ParameterListModeItemsErrorV1> {
    if value.parameter_type() != AmiParameterTypeV1::List {
        return Err(ParameterListModeItemsErrorV1::NotAList);
    }
    let items = list_items(value.value_token())
        .ok_or(ParameterListModeItemsErrorV1::MalformedList)?;
    let mut order: Vec<String> = Vec::new();
    let mut counts: Vec<(String, usize)> = Vec::new();
    for item in &items {
        match counts.iter_mut().find(|(existing, _)| existing == item) {
            Some((_, count)) => *count += 1,
            None => {
                counts.push((item.clone(), 1));
                order.push(item.clone());
            }
        }
    }
    let max_count = counts.iter().map(|(_, count)| *count).max().unwrap_or(0);
    let modes: Vec<String> = order
        .iter()
        .filter(|item| {
            counts
                .iter()
                .find(|(existing, _)| existing == *item)
                .map(|(_, count)| *count == max_count)
                .unwrap_or(false)
        })
        .cloned()
        .collect();
    Ok(format!("({})", modes.join(", ")))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    #[test]
    fn single_mode_in_first_occurrence_order() {
        let v = value("param", "List", "(b, a, b, c, b)");
        assert_eq!(parameter_list_mode_items_v1(&v), Ok("(b)".to_string()));
    }

    #[test]
    fn multiple_modes_all_reported() {
        let v = value("param", "List", "(b, a, b, a, c)");
        assert_eq!(parameter_list_mode_items_v1(&v), Ok("(b, a)".to_string()));
    }

    #[test]
    fn all_distinct_items_are_modes() {
        let v = value("param", "List", "(c, a, b)");
        assert_eq!(parameter_list_mode_items_v1(&v), Ok("(c, a, b)".to_string()));
    }

    #[test]
    fn single_item_is_its_own_mode() {
        let v = value("param", "List", "(x)");
        assert_eq!(parameter_list_mode_items_v1(&v), Ok("(x)".to_string()));
    }

    #[test]
    fn spacing_is_canonicalized() {
        let v = value("param", "List", "( b , a , b )");
        assert_eq!(parameter_list_mode_items_v1(&v), Ok("(b)".to_string()));
    }

    #[test]
    fn non_list_fails_closed() {
        let v = value("gain", "Float", "0.5");
        assert_eq!(
            parameter_list_mode_items_v1(&v),
            Err(ParameterListModeItemsErrorV1::NotAList)
        );
    }
}
