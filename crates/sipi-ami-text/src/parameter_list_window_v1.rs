//! AMI parameter list sliding windows core (P4B-02b118).
//!
//! Enumerates the sliding windows of the trimmed items of a validated
//! List-typed `AmiParameterValueV1` under the P4B-02b1 list rule
//! (`(item, item, ...)`, items trimmed, non-empty):
//! `window_parameter_list_v1` returns the canonical list tokens of every
//! consecutive run of exactly `window_size` trimmed items, in order, each
//! re-joined with `", "` (windows slide by one item; when the list has fewer
//! items than `window_size`, no window exists and the result is empty). This
//! is the overlapping companion of 02b116 fixed-size chunking and 02b109
//! slice.
//!
//! Fail-closed: a non-List value yields `NotAList`; a token that does not
//! match the List shape yields `MalformedList` (unreachable for values built
//! via `AmiParameterValueV1::try_new`, kept defensive instead of panicking);
//! a zero window size yields `InvalidWindowSize` (no valid window exists).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: sliding window enumeration.
pub const PARAMETER_LIST_WINDOW_POLICY_V1: &str =
    "sipi.p4b-02b118.parameter-list-window-v1.sliding-windows";

/// Fail-closed error while windowing one list value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListWindowErrorV1 {
    /// The value's declared type is not List.
    NotAList,
    /// The token does not match the List shape (defensive; unreachable for
    /// values built via `AmiParameterValueV1::try_new`).
    MalformedList,
    /// The requested window size is zero.
    InvalidWindowSize,
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

/// Enumerate the sliding windows of exactly `window_size` items of a List
/// value, in order.
pub fn window_parameter_list_v1(
    value: &AmiParameterValueV1,
    window_size: usize,
) -> Result<Vec<String>, ParameterListWindowErrorV1> {
    if value.parameter_type() != AmiParameterTypeV1::List {
        return Err(ParameterListWindowErrorV1::NotAList);
    }
    if window_size == 0 {
        return Err(ParameterListWindowErrorV1::InvalidWindowSize);
    }
    let items = list_items(value.value_token()).ok_or(ParameterListWindowErrorV1::MalformedList)?;
    Ok(items
        .windows(window_size)
        .map(|window| format!("({})", window.join(", ")))
        .collect())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    #[test]
    fn windows_of_three() {
        let v = value("channels", "List", "(a, b, c, d)");
        assert_eq!(
            window_parameter_list_v1(&v, 3),
            Ok(vec!["(a, b, c)".to_string(), "(b, c, d)".to_string()])
        );
    }

    #[test]
    fn single_window() {
        let v = value("channels", "List", "(a, b, c)");
        assert_eq!(
            window_parameter_list_v1(&v, 3),
            Ok(vec!["(a, b, c)".to_string()])
        );
    }

    #[test]
    fn window_larger_than_list_is_empty() {
        let v = value("channels", "List", "(a, b)");
        assert_eq!(window_parameter_list_v1(&v, 5), Ok(vec![]));
    }

    #[test]
    fn zero_window_size_fails_closed() {
        let v = value("channels", "List", "(a, b)");
        assert_eq!(
            window_parameter_list_v1(&v, 0),
            Err(ParameterListWindowErrorV1::InvalidWindowSize)
        );
    }

    #[test]
    fn non_list_fails_closed() {
        let float = value("gain", "Float", "0.5");
        assert_eq!(
            window_parameter_list_v1(&float, 2),
            Err(ParameterListWindowErrorV1::NotAList)
        );
    }

    #[test]
    fn spacing_is_canonicalized() {
        let v = value("channels", "List", "( a , b , c , d )");
        assert_eq!(
            window_parameter_list_v1(&v, 2),
            Ok(vec![
                "(a, b)".to_string(),
                "(b, c)".to_string(),
                "(c, d)".to_string()
            ])
        );
    }
}
