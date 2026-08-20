//! AMI parameter list distinct-pair count core (P4B-02b135).
//!
//! Counts the distinct unordered pairs of the trimmed items of a validated
//! List-typed `AmiParameterValueV1` under the P4B-02b1 list rule
//! (`(item, item, ...)`, items trimmed, non-empty):
//! `parameter_list_distinct_pair_count_v1` returns the number of index pairs
//! `(i, j)` with `i < j` whose items are unequal (raw byte equality and
//! inequality, per the P4B-02b0 raw-byte binding). The total number of
//! unordered pairs is `n*(n-1)/2`; the equal unordered pair count is that
//! total minus the distinct pair count. This is the pair-level companion of
//! 02b133 inversion counting (same iteration domain) and of 02b107 distinct
//! counting.
//!
//! Fail-closed: a non-List value yields `NotAList`; a token that does not
//! match the List shape yields `MalformedList` (unreachable for values built
//! via `AmiParameterValueV1::try_new`, kept defensive instead of panicking).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: distinct unordered pair counting.
pub const PARAMETER_LIST_DISTINCT_PAIR_COUNT_POLICY_V1: &str =
    "sipi.p4b-02b135.parameter-list-distinct-pair-count-v1.distinct-pairs";

/// Fail-closed error while counting distinct pairs of one list value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterListDistinctPairCountErrorV1 {
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

/// Count the index pairs (i, j) with i < j whose trimmed items are unequal.
pub fn parameter_list_distinct_pair_count_v1(
    value: &AmiParameterValueV1,
) -> Result<usize, ParameterListDistinctPairCountErrorV1> {
    if value.parameter_type() != AmiParameterTypeV1::List {
        return Err(ParameterListDistinctPairCountErrorV1::NotAList);
    }
    let items = list_items(value.value_token())
        .ok_or(ParameterListDistinctPairCountErrorV1::MalformedList)?;
    let mut count = 0usize;
    for i in 0..items.len() {
        for j in (i + 1)..items.len() {
            if items[i] != items[j] {
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
    fn all_distinct_has_max_pairs() {
        let v = value("channels", "List", "(a, b, c)");
        assert_eq!(parameter_list_distinct_pair_count_v1(&v), Ok(3));
    }

    #[test]
    fn all_equal_has_zero_pairs() {
        let v = value("channels", "List", "(x, x, x)");
        assert_eq!(parameter_list_distinct_pair_count_v1(&v), Ok(0));
    }

    #[test]
    fn counts_partial_distinct_pairs() {
        let v = value("channels", "List", "(a, a, b)");
        assert_eq!(parameter_list_distinct_pair_count_v1(&v), Ok(2));
    }

    #[test]
    fn four_items_total_six_pairs() {
        let v = value("channels", "List", "(a, b, c, d)");
        assert_eq!(parameter_list_distinct_pair_count_v1(&v), Ok(6));
    }

    #[test]
    fn non_list_fails_closed() {
        let float = value("gain", "Float", "0.5");
        assert_eq!(
            parameter_list_distinct_pair_count_v1(&float),
            Err(ParameterListDistinctPairCountErrorV1::NotAList)
        );
    }

    #[test]
    fn single_item_has_zero_pairs() {
        let v = value("channels", "List", "(x)");
        assert_eq!(parameter_list_distinct_pair_count_v1(&v), Ok(0));
    }
}
