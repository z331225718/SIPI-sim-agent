//! Typed AMI parameter value semantic equivalence core (P4B-02b70).
//!
//! Compares two validated `AmiParameterValueV1` values by their declared type
//! and parsed typed value, not by raw token spelling: numeric spellings that
//! parse to the same value (`0.5` vs `0.50`, `007` vs `7`, `1e0` vs `1.0`)
//! are Equivalent, list spellings are compared by trimmed item sequences
//! (`(a, b, c)` vs `(a,b,c)`), and String values keep raw byte equality (no
//! normalization, per the P4B-02b0 raw-byte binding). This is the typed value
//! equality layer beneath profile diff/merge (02b47/02b48) and duplicate
//! consistency (02b54), which currently compare raw tokens.
//!
//! Fail-closed: a declared type mismatch is never equivalent; Float and
//! Integer compare on parsed finite values (IEEE equality, so `0.0` and
//! `-0.0` are equivalent); Boolean compares the exact `True`/`False` token;
//! List compares trimmed item sequences item-by-item with index reporting;
//! any token that cannot be parsed per its declared type yields
//! `MalformedValue` (unreachable for values built via `AmiParameterValueV1::try_new`,
//! kept fail-closed instead of panicking).

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: typed-value semantic equivalence only.
pub const PARAMETER_VALUE_EQUIVALENCE_POLICY_V1: &str =
    "sipi.p4b-02b70.parameter-value-equivalence-v1.typed-value-semantics";

/// Outcome of comparing two validated parameter values by typed semantics.
#[derive(Clone, Debug, PartialEq)]
pub enum ParameterValueEquivalenceV1 {
    Equivalent,
    NotEquivalent(ParameterValueInequivalenceReasonV1),
}

/// Why two parameter values are not equivalent under typed semantics.
#[derive(Clone, Debug, PartialEq)]
pub enum ParameterValueInequivalenceReasonV1 {
    /// Declared type tokens differ; cross-type values are never equivalent.
    TypeMismatch {
        left: AmiParameterTypeV1,
        right: AmiParameterTypeV1,
    },
    /// Parsed Float values differ (IEEE equality).
    FloatMismatch { left: f64, right: f64 },
    /// Parsed Integer values differ.
    IntegerMismatch { left: i64, right: i64 },
    /// Boolean tokens differ (`True` vs `False`).
    BooleanMismatch { left: bool, right: bool },
    /// Raw String spellings differ (byte equality, no normalization).
    StringMismatch { left: String, right: String },
    /// List item counts differ.
    ListLengthMismatch { left: usize, right: usize },
    /// The item at `index` (0-based, after trimming) differs.
    ListItemMismatch {
        index: usize,
        left: String,
        right: String,
    },
    /// A value token violates its declared type rule; unreachable for values
    /// constructed via `AmiParameterValueV1::try_new`, kept fail-closed.
    MalformedValue { left: String, right: String },
}

impl ParameterValueInequivalenceReasonV1 {
    /// Stable short key for cross-check reporting and diagnostics.
    pub fn key(&self) -> &'static str {
        match self {
            Self::TypeMismatch { .. } => "TypeMismatch",
            Self::FloatMismatch { .. } => "FloatMismatch",
            Self::IntegerMismatch { .. } => "IntegerMismatch",
            Self::BooleanMismatch { .. } => "BooleanMismatch",
            Self::StringMismatch { .. } => "StringMismatch",
            Self::ListLengthMismatch { .. } => "ListLengthMismatch",
            Self::ListItemMismatch { .. } => "ListItemMismatch",
            Self::MalformedValue { .. } => "MalformedValue",
        }
    }
}

/// Split a validated List value token into trimmed item spellings, mirroring
/// the P4B-02b1 List rule (`(item, item, ...)`, items trimmed, non-empty).
fn list_items(value_token: &str) -> Option<Vec<String>> {
    if !value_token.starts_with('(') || !value_token.ends_with(')') || value_token.len() < 2 {
        return None;
    }
    let inner = &value_token[1..value_token.len() - 1];
    if inner.is_empty() {
        return None;
    }
    let items: Vec<String> = inner
        .split(',')
        .map(|item| item.trim().to_string())
        .collect();
    if items.iter().any(|item| item.is_empty()) {
        return None;
    }
    Some(items)
}

/// Compare two validated parameter values by declared type and parsed typed
/// value. Parameter names are identity, not value: values with the same type
/// and semantic value compare Equivalent even under different names (callers
/// compare names at the profile-map level, as in 02b47).
pub fn parameter_values_equivalent_v1(
    left: &AmiParameterValueV1,
    right: &AmiParameterValueV1,
) -> ParameterValueEquivalenceV1 {
    let left_type = left.parameter_type();
    let right_type = right.parameter_type();
    if left_type != right_type {
        return ParameterValueEquivalenceV1::NotEquivalent(
            ParameterValueInequivalenceReasonV1::TypeMismatch {
                left: left_type,
                right: right_type,
            },
        );
    }
    match left_type {
        AmiParameterTypeV1::Float => match (
            left.value_token().parse::<f64>(),
            right.value_token().parse::<f64>(),
        ) {
            (Ok(left_value), Ok(right_value)) => {
                if left_value == right_value {
                    ParameterValueEquivalenceV1::Equivalent
                } else {
                    ParameterValueEquivalenceV1::NotEquivalent(
                        ParameterValueInequivalenceReasonV1::FloatMismatch {
                            left: left_value,
                            right: right_value,
                        },
                    )
                }
            }
            _ => ParameterValueEquivalenceV1::NotEquivalent(
                ParameterValueInequivalenceReasonV1::MalformedValue {
                    left: left.value_token().to_string(),
                    right: right.value_token().to_string(),
                },
            ),
        },
        AmiParameterTypeV1::Integer => match (
            left.value_token().parse::<i64>(),
            right.value_token().parse::<i64>(),
        ) {
            (Ok(left_value), Ok(right_value)) => {
                if left_value == right_value {
                    ParameterValueEquivalenceV1::Equivalent
                } else {
                    ParameterValueEquivalenceV1::NotEquivalent(
                        ParameterValueInequivalenceReasonV1::IntegerMismatch {
                            left: left_value,
                            right: right_value,
                        },
                    )
                }
            }
            _ => ParameterValueEquivalenceV1::NotEquivalent(
                ParameterValueInequivalenceReasonV1::MalformedValue {
                    left: left.value_token().to_string(),
                    right: right.value_token().to_string(),
                },
            ),
        },
        AmiParameterTypeV1::Boolean => {
            let left_value = left.value_token() == "True";
            let right_value = right.value_token() == "True";
            if left_value == right_value {
                ParameterValueEquivalenceV1::Equivalent
            } else {
                ParameterValueEquivalenceV1::NotEquivalent(
                    ParameterValueInequivalenceReasonV1::BooleanMismatch {
                        left: left_value,
                        right: right_value,
                    },
                )
            }
        }
        AmiParameterTypeV1::String_ => {
            if left.value_token() == right.value_token() {
                ParameterValueEquivalenceV1::Equivalent
            } else {
                ParameterValueEquivalenceV1::NotEquivalent(
                    ParameterValueInequivalenceReasonV1::StringMismatch {
                        left: left.value_token().to_string(),
                        right: right.value_token().to_string(),
                    },
                )
            }
        }
        AmiParameterTypeV1::List => match (
            list_items(left.value_token()),
            list_items(right.value_token()),
        ) {
            (Some(left_items), Some(right_items)) => {
                if left_items.len() != right_items.len() {
                    return ParameterValueEquivalenceV1::NotEquivalent(
                        ParameterValueInequivalenceReasonV1::ListLengthMismatch {
                            left: left_items.len(),
                            right: right_items.len(),
                        },
                    );
                }
                for (index, (left_item, right_item)) in
                    left_items.iter().zip(right_items.iter()).enumerate()
                {
                    if left_item != right_item {
                        return ParameterValueEquivalenceV1::NotEquivalent(
                            ParameterValueInequivalenceReasonV1::ListItemMismatch {
                                index,
                                left: left_item.clone(),
                                right: right_item.clone(),
                            },
                        );
                    }
                }
                ParameterValueEquivalenceV1::Equivalent
            }
            _ => ParameterValueEquivalenceV1::NotEquivalent(
                ParameterValueInequivalenceReasonV1::MalformedValue {
                    left: left.value_token().to_string(),
                    right: right.value_token().to_string(),
                },
            ),
        },
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    #[test]
    fn float_spelling_equivalence() {
        let a = value("gain", "Float", "0.5");
        let b = value("gain", "Float", "0.50");
        assert_eq!(
            parameter_values_equivalent_v1(&a, &b),
            ParameterValueEquivalenceV1::Equivalent
        );
        let c = value("gain", "Float", "1e0");
        let d = value("gain", "Float", "1.0");
        assert_eq!(
            parameter_values_equivalent_v1(&c, &d),
            ParameterValueEquivalenceV1::Equivalent
        );
    }

    #[test]
    fn integer_spelling_equivalence() {
        let a = value("steps", "Integer", "007");
        let b = value("steps", "Integer", "7");
        assert_eq!(
            parameter_values_equivalent_v1(&a, &b),
            ParameterValueEquivalenceV1::Equivalent
        );
        let c = value("steps", "Integer", "-0");
        let d = value("steps", "Integer", "0");
        assert_eq!(
            parameter_values_equivalent_v1(&c, &d),
            ParameterValueEquivalenceV1::Equivalent
        );
    }

    #[test]
    fn string_values_keep_raw_spelling() {
        let a = value("mode", "String", "Linear");
        let b = value("mode", "String", "Linear");
        assert_eq!(
            parameter_values_equivalent_v1(&a, &b),
            ParameterValueEquivalenceV1::Equivalent
        );
        let c = value("mode", "String", "Linear ");
        assert_eq!(
            parameter_values_equivalent_v1(&a, &c),
            ParameterValueEquivalenceV1::NotEquivalent(
                ParameterValueInequivalenceReasonV1::StringMismatch {
                    left: "Linear".to_string(),
                    right: "Linear ".to_string(),
                }
            )
        );
    }

    #[test]
    fn list_spacing_equivalence() {
        let a = value("channels", "List", "(a, b, c)");
        let b = value("channels", "List", "(a,b,c)");
        assert_eq!(
            parameter_values_equivalent_v1(&a, &b),
            ParameterValueEquivalenceV1::Equivalent
        );
        let c = value("channels", "List", "(a, b)");
        assert_eq!(
            parameter_values_equivalent_v1(&a, &c),
            ParameterValueEquivalenceV1::NotEquivalent(
                ParameterValueInequivalenceReasonV1::ListLengthMismatch { left: 3, right: 2 }
            )
        );
    }

    #[test]
    fn typed_value_mismatches_report_reasons() {
        let a = value("gain", "Float", "0.5");
        let b = value("gain", "Float", "0.5001");
        assert_eq!(
            parameter_values_equivalent_v1(&a, &b),
            ParameterValueEquivalenceV1::NotEquivalent(
                ParameterValueInequivalenceReasonV1::FloatMismatch {
                    left: 0.5,
                    right: 0.5001,
                }
            )
        );
        let c = value("steps", "Integer", "7");
        let d = value("steps", "Integer", "8");
        assert_eq!(
            parameter_values_equivalent_v1(&c, &d),
            ParameterValueEquivalenceV1::NotEquivalent(
                ParameterValueInequivalenceReasonV1::IntegerMismatch { left: 7, right: 8 }
            )
        );
        let e = value("on", "Boolean", "True");
        let f = value("on", "Boolean", "False");
        assert_eq!(
            parameter_values_equivalent_v1(&e, &f),
            ParameterValueEquivalenceV1::NotEquivalent(
                ParameterValueInequivalenceReasonV1::BooleanMismatch {
                    left: true,
                    right: false,
                }
            )
        );
        let g = value("taps", "List", "(1, 2)");
        let h = value("taps", "List", "(1, 3)");
        assert_eq!(
            parameter_values_equivalent_v1(&g, &h),
            ParameterValueEquivalenceV1::NotEquivalent(
                ParameterValueInequivalenceReasonV1::ListItemMismatch {
                    index: 1,
                    left: "2".to_string(),
                    right: "3".to_string(),
                }
            )
        );
    }

    #[test]
    fn cross_type_values_never_equivalent() {
        let a = value("x", "Float", "1.0");
        let b = value("x", "Integer", "1");
        assert_eq!(
            parameter_values_equivalent_v1(&a, &b),
            ParameterValueEquivalenceV1::NotEquivalent(
                ParameterValueInequivalenceReasonV1::TypeMismatch {
                    left: AmiParameterTypeV1::Float,
                    right: AmiParameterTypeV1::Integer,
                }
            )
        );
    }
}
