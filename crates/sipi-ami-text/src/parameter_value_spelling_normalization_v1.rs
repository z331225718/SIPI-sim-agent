//! AMI parameter value spelling normalization core (P4B-02b75).
//!
//! Produces the deterministic canonical spelling of a validated
//! `AmiParameterValueV1`'s value token for the types where a canonical form is
//! well-defined without float formatting hazards:
//! - Integer: parsed i64 rendered in decimal (`007` -> `7`, `-0` -> `0`).
//! - List: items trimmed and joined with `", "` inside the parens
//!   (`(a,b,c)` -> `(a, b, c)`), mirroring the P4B-02b1 list item rule.
//! - Boolean: already canonical (`True`/`False`), returned unchanged.
//! - Float and String: returned raw (no normalization, per the P4B-02b0
//!   raw-byte binding; float formatting is explicitly out of scope).
//!
//! This is the canonical-string companion of 02b70 typed equivalence (a
//! boolean predicate) and sits below any caller that needs a stable spelling
//! key for non-float values. Fail-closed: inputs are validated values built
//! via `AmiParameterValueV1::try_new`, so Integer/List parses cannot fail; a
//! defensive fallback returns the raw token rather than panicking.

use crate::{AmiParameterTypeV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: canonical spelling of non-float values.
pub const PARAMETER_VALUE_SPELLING_NORMALIZATION_POLICY_V1: &str =
    "sipi.p4b-02b75.parameter-value-spelling-normalization-v1.canonical-non-float-spelling";

/// Canonical spelling of a validated value token by declared type.
pub fn canonicalize_parameter_value_spelling_v1(value: &AmiParameterValueV1) -> String {
    let token = value.value_token();
    match value.parameter_type() {
        AmiParameterTypeV1::Integer => match token.parse::<i64>() {
            Ok(integer) => integer.to_string(),
            Err(_) => token.to_string(),
        },
        AmiParameterTypeV1::List => {
            if token.starts_with('(') && token.ends_with(')') && token.len() >= 2 {
                let inner = &token[1..token.len() - 1];
                let items: Vec<&str> = inner
                    .split(',')
                    .map(|item| item.trim())
                    .filter(|item| !item.is_empty())
                    .collect();
                format!("({})", items.join(", "))
            } else {
                token.to_string()
            }
        }
        AmiParameterTypeV1::Boolean | AmiParameterTypeV1::Float | AmiParameterTypeV1::String_ => {
            token.to_string()
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    #[test]
    fn integer_spellings_normalize_to_decimal() {
        assert_eq!(
            canonicalize_parameter_value_spelling_v1(&value("steps", "Integer", "007")),
            "7"
        );
        assert_eq!(
            canonicalize_parameter_value_spelling_v1(&value("steps", "Integer", "-0")),
            "0"
        );
        assert_eq!(
            canonicalize_parameter_value_spelling_v1(&value("steps", "Integer", "42")),
            "42"
        );
    }

    #[test]
    fn list_spellings_normalize_item_spacing() {
        assert_eq!(
            canonicalize_parameter_value_spelling_v1(&value("channels", "List", "(a,b,c)")),
            "(a, b, c)"
        );
        assert_eq!(
            canonicalize_parameter_value_spelling_v1(&value("channels", "List", "( a , b )")),
            "(a, b)"
        );
        assert_eq!(
            canonicalize_parameter_value_spelling_v1(&value("channels", "List", "(x)")),
            "(x)"
        );
    }

    #[test]
    fn boolean_spellings_are_canonical() {
        assert_eq!(
            canonicalize_parameter_value_spelling_v1(&value("on", "Boolean", "True")),
            "True"
        );
        assert_eq!(
            canonicalize_parameter_value_spelling_v1(&value("on", "Boolean", "False")),
            "False"
        );
    }

    #[test]
    fn float_spellings_stay_raw() {
        assert_eq!(
            canonicalize_parameter_value_spelling_v1(&value("gain", "Float", "0.50")),
            "0.50"
        );
        assert_eq!(
            canonicalize_parameter_value_spelling_v1(&value("gain", "Float", "1e0")),
            "1e0"
        );
    }

    #[test]
    fn string_spellings_stay_raw() {
        assert_eq!(
            canonicalize_parameter_value_spelling_v1(&value("mode", "String", "Linear ")),
            "Linear "
        );
    }

    #[test]
    fn normalization_is_idempotent_for_non_float_types() {
        let cases = [
            ("steps", "Integer", "007"),
            ("channels", "List", "( a , b , c )"),
            ("on", "Boolean", "True"),
        ];
        for (name, type_token, value_token) in cases {
            let first =
                canonicalize_parameter_value_spelling_v1(&value(name, type_token, value_token));
            let second = canonicalize_parameter_value_spelling_v1(&value(name, type_token, &first));
            assert_eq!(first, second);
        }
    }
}
