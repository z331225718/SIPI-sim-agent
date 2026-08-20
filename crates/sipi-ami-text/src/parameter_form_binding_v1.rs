//! Identity binding between one caller-declared typed parameter triple and
//! one caller-selected structural form of a bound document.
//!
//! P4B-02b2: `bind_parameter_value_v1` verifies, byte-exactly, that the
//! spelling of a caller-selected form's three items equals the caller's
//! declared (name, type token, value token) triple. The API never
//! interprets a form as a parameter: it only proves identity. Two-item
//! forms, nested lists, mismatched spellings, and out-of-range indexes all
//! fail closed. No catalog, no reserved names, no defaults, no document
//! decoding.

use crate::{AmiParameterValueV1, AmiTextBindingV1, AmiTextNodeV1};

/// One verified identity binding: a caller-selected form index and the
/// validated triple whose spellings match that form byte-exactly.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ParameterFormBindingV1 {
    form_index: usize,
    value: AmiParameterValueV1,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ParameterFormBindingErrorV1 {
    FormIndexOutOfRange,
    FormNotThreeItems,
    FormItemIsNestedList,
    NameSpellingMismatch,
    TypeTokenSpellingMismatch,
    ValueTokenSpellingMismatch,
}

impl ParameterFormBindingV1 {
    pub const fn form_index(&self) -> usize {
        self.form_index
    }

    pub const fn value(&self) -> &AmiParameterValueV1 {
        &self.value
    }
}

fn item_spelling(node: &AmiTextNodeV1) -> Option<&str> {
    match node {
        AmiTextNodeV1::Atom(token) | AmiTextNodeV1::Quoted(token) => Some(token.spelling()),
        AmiTextNodeV1::List(_) => None,
    }
}

/// Verify that a caller-selected form of a bound document matches a
/// caller-declared typed parameter triple byte-exactly.
///
/// Product-owned identity rules, documented in the P4B-02b2 charter:
/// - the form index must be in range;
/// - the form must have exactly three items (name, type token, value token);
/// - every item must be an atom or quoted token, not a nested list;
/// - item spellings must equal the triple's name, type token, and value
///   token respectively, byte-exactly.
pub fn bind_parameter_value_v1(
    binding: &AmiTextBindingV1,
    form_index: usize,
    value: &AmiParameterValueV1,
) -> Result<ParameterFormBindingV1, ParameterFormBindingErrorV1> {
    let forms = binding.document().forms();
    let form = forms
        .get(form_index)
        .ok_or(ParameterFormBindingErrorV1::FormIndexOutOfRange)?;
    let items = form.items();
    if items.len() != 3 {
        return Err(ParameterFormBindingErrorV1::FormNotThreeItems);
    }
    let name_spelling = item_spelling(&items[0])
        .ok_or(ParameterFormBindingErrorV1::FormItemIsNestedList)?;
    let type_spelling = item_spelling(&items[1])
        .ok_or(ParameterFormBindingErrorV1::FormItemIsNestedList)?;
    let value_spelling = item_spelling(&items[2])
        .ok_or(ParameterFormBindingErrorV1::FormItemIsNestedList)?;
    if name_spelling != value.name() {
        return Err(ParameterFormBindingErrorV1::NameSpellingMismatch);
    }
    if type_spelling != value.parameter_type().token() {
        return Err(ParameterFormBindingErrorV1::TypeTokenSpellingMismatch);
    }
    if value_spelling != value.value_token() {
        return Err(ParameterFormBindingErrorV1::ValueTokenSpellingMismatch);
    }
    Ok(ParameterFormBindingV1 {
        form_index,
        value: value.clone(),
    })
}

/// Explicit scope policy of this slice: identity-only binding of one
/// caller-declared triple to one caller-selected form.
pub const PARAMETER_FORM_BINDING_POLICY_V1: &str =
    "sipi.p4b-02b2.parameter-form-binding-v1.identity-only";

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{parse_and_bind_v1, AmiParameterValueErrorV1, ParseLimitsV1};

    fn limits() -> ParseLimitsV1 {
        ParseLimitsV1::try_new(2048, 8, 64, 256).expect("limits")
    }

    fn triple(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid triple")
    }

    #[test]
    fn binds_exact_matching_form() {
        let binding = parse_and_bind_v1(b"(Resistance Float 50.0)", limits()).expect("bind");
        let value = triple("Resistance", "Float", "50.0");
        let bound = bind_parameter_value_v1(&binding, 0, &value).expect("identity");
        assert_eq!(bound.form_index(), 0);
        assert_eq!(bound.value(), &value);
    }

    #[test]
    fn rejects_out_of_range_form_index() {
        let binding = parse_and_bind_v1(b"(Resistance Float 50.0)", limits()).expect("bind");
        assert_eq!(
            bind_parameter_value_v1(&binding, 1, &triple("Resistance", "Float", "50.0")),
            Err(ParameterFormBindingErrorV1::FormIndexOutOfRange)
        );
    }

    #[test]
    fn rejects_two_item_forms() {
        let binding = parse_and_bind_v1(b"(SinkTime 100)", limits()).expect("bind");
        assert_eq!(
            bind_parameter_value_v1(&binding, 0, &triple("SinkTime", "Integer", "100")),
            Err(ParameterFormBindingErrorV1::FormNotThreeItems)
        );
    }

    #[test]
    fn rejects_nested_list_item() {
        let binding = parse_and_bind_v1(b"(Taps List (1 2))", limits()).expect("bind");
        assert_eq!(
            bind_parameter_value_v1(&binding, 0, &triple("Taps", "List", "(1 2)")),
            Err(ParameterFormBindingErrorV1::FormItemIsNestedList)
        );
    }

    #[test]
    fn rejects_spelling_mismatches() {
        let binding = parse_and_bind_v1(b"(Resistance Float 50.0)", limits()).expect("bind");
        assert_eq!(
            bind_parameter_value_v1(&binding, 0, &triple("resistance", "Float", "50.0")),
            Err(ParameterFormBindingErrorV1::NameSpellingMismatch)
        );
        assert_eq!(
            bind_parameter_value_v1(&binding, 0, &triple("Resistance", "Integer", "100")),
            Err(ParameterFormBindingErrorV1::TypeTokenSpellingMismatch)
        );
        assert_eq!(
            bind_parameter_value_v1(&binding, 0, &triple("Resistance", "Float", "50")),
            Err(ParameterFormBindingErrorV1::ValueTokenSpellingMismatch)
        );
    }

    #[test]
    fn rejects_invalid_triple_before_binding() {
        assert_eq!(
            AmiParameterValueV1::try_new("Resistance", "Float", "NaN"),
            Err(AmiParameterValueErrorV1::InvalidFloat)
        );
    }

    #[test]
    fn policy_string_is_fixed() {
        assert_eq!(
            PARAMETER_FORM_BINDING_POLICY_V1,
            "sipi.p4b-02b2.parameter-form-binding-v1.identity-only"
        );
    }
}
