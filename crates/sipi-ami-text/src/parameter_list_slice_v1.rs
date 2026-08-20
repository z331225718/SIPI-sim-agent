//! AMI parameter list range slice core (P4B-02b109).
//!
//! Slices a validated List-typed `AmiParameterValueV1` under the P4B-02b1
//! list rule (`(item, item, ...)`, items trimmed, non-empty):
//! `slice_parameter_list_items_v1` returns the canonical list token whose
//! items are the trimmed items at half-open indices `[start, end)` (0-based,
//! end exclusive, re-joined with `", "`). This is the range companion of the
//! list-edit family (02b84 access, 02b100 remove, 02b102 insert, 02b103 swap,
//! 02b104 reverse, 02b105 sort, 02b106 join).
//!
//! Fail-closed: a non-List value yields `NotAList`; a token that does not
//! match the List shape yields `MalformedList` (unreachable for values built
//! via `AmiParameterValueV1::try_new`, kept defensive instead of panicking);
//! a bound violating `start <= end <= item_count` yields
//! `IndexOutOfRange` carrying the offending bound and the actual item count.
//! An empty range (`start == end`) yields the structurally empty token `()`
//! (not a valid 02b1 List value; the operation is total on the token level
//! and does not re-validate, mirroring 02b100 sole-item removal).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: half-open list range slicing.
pub const PARAMETER_LIST_SLICE_POLICY_V1: &str =
    "sipi.p4b-02b109.parameter-list-slice-v1.range-slice";

/// Fail-closed error while slicing one list value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListSliceErrorV1 {
    /// The value's declared type is not List.
    NotAList,
    /// The token does not match the List shape (defensive; unreachable for
    /// values built via `AmiParameterValueV1::try_new`).
    MalformedList,
    /// A bound violates `start <= end <= item_count`; carries the offending
    /// bound and the actual item count.
    IndexOutOfRange { index: usize, item_count: usize },
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

/// Slice the trimmed items at `[start, end)` of a List-typed validated value.
pub fn slice_parameter_list_items_v1(
    value: &AmiParameterValueV1,
    start: usize,
    end: usize,
) -> Result<String, ParameterListSliceErrorV1> {
    if value.parameter_type() != AmiParameterTypeV1::List {
        return Err(ParameterListSliceErrorV1::NotAList);
    }
    let items = list_items(value.value_token())
        .ok_or(ParameterListSliceErrorV1::MalformedList)?;
    let item_count = items.len();
    if start > end {
        return Err(ParameterListSliceErrorV1::IndexOutOfRange {
            index: start,
            item_count,
        });
    }
    if end > item_count {
        return Err(ParameterListSliceErrorV1::IndexOutOfRange {
            index: end,
            item_count,
        });
    }
    Ok(format!("({})", items[start..end].join(", ")))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    #[test]
    fn slices_middle_range() {
        let v = value("channels", "List", "(a, b, c, d)");
        assert_eq!(
            slice_parameter_list_items_v1(&v, 1, 3),
            Ok("(b, c)".to_string())
        );
    }

    #[test]
    fn slices_full_range() {
        let v = value("channels", "List", "(a, b, c)");
        assert_eq!(
            slice_parameter_list_items_v1(&v, 0, 3),
            Ok("(a, b, c)".to_string())
        );
    }

    #[test]
    fn empty_range_yields_empty_token() {
        let v = value("channels", "List", "(a, b, c)");
        assert_eq!(
            slice_parameter_list_items_v1(&v, 2, 2),
            Ok("()".to_string())
        );
    }

    #[test]
    fn out_of_range_fails_closed() {
        let v = value("channels", "List", "(a, b)");
        assert_eq!(
            slice_parameter_list_items_v1(&v, 1, 3),
            Err(ParameterListSliceErrorV1::IndexOutOfRange {
                index: 3,
                item_count: 2,
            })
        );
        assert_eq!(
            slice_parameter_list_items_v1(&v, 2, 1),
            Err(ParameterListSliceErrorV1::IndexOutOfRange {
                index: 2,
                item_count: 2,
            })
        );
    }

    #[test]
    fn non_list_fails_closed() {
        let float = value("gain", "Float", "0.5");
        assert_eq!(
            slice_parameter_list_items_v1(&float, 0, 1),
            Err(ParameterListSliceErrorV1::NotAList)
        );
    }

    #[test]
    fn spacing_is_canonicalized() {
        let v = value("channels", "List", "( a , b , c )");
        assert_eq!(
            slice_parameter_list_items_v1(&v, 1, 3),
            Ok("(b, c)".to_string())
        );
    }
}
