//! AMI parameter profile canonical deserialization core (P4B-02b82).
//!
//! Parses the canonical compact JSON produced by
//! `serialize_parameter_profile_v1` (02b81) back into an assembled parameter
//! profile (`BTreeMap<String, AmiParameterValueV1>`): each object key is a
//! parameter name whose value must be an object carrying a `type` and a
//! `value` string; every entry is rebuilt through `AmiParameterValueV1::try_new`
//! (02b1). Together with 02b81 this gives a deterministic profile round trip
//! (serialize -> deserialize -> identical profile). This is the profile-level
//! companion of 02b19 tree serde (which handles trees, not profiles).
//!
//! Fail-closed: invalid JSON, a non-object root, a non-object entry, a missing
//! `type`/`value` field, an unknown type token, or a value that violates the
//! 02b1 rules are all strictly rejected with distinct error variants; the
//! resulting map is deterministic (BTreeMap order).

use std::collections::BTreeMap;

use serde_json::Value;

use crate::{AmiParameterValueErrorV1, AmiParameterValueV1};

/// Explicit scope policy of this slice: canonical profile JSON parsing.
pub const PARAMETER_PROFILE_DESERIALIZATION_POLICY_V1: &str =
    "sipi.p4b-02b82.parameter-profile-deserialization-v1.canonical-profile-json-parse";

/// Fail-closed error while deserializing a profile from canonical JSON.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterProfileDeserializationErrorV1 {
    /// The input is not valid JSON.
    InvalidJson(String),
    /// The top-level JSON value is not an object.
    NotAnObject,
    /// A profile entry is not a JSON object.
    EntryNotObject(String),
    /// An entry has no string `type` field.
    MissingType(String),
    /// An entry has no string `value` field.
    MissingValue(String),
    /// The entry violates the P4B-02b1 value rules.
    InvalidValue {
        name: String,
        error: AmiParameterValueErrorV1,
    },
}

/// Outcome of a fully successful profile deserialization.
#[derive(Clone, Debug, PartialEq)]
pub struct ParameterProfileDeserializationV1 {
    profile: BTreeMap<String, AmiParameterValueV1>,
}

impl ParameterProfileDeserializationV1 {
    /// The deserialized profile.
    pub fn profile(&self) -> &BTreeMap<String, AmiParameterValueV1> {
        &self.profile
    }

    /// Number of deserialized entries.
    pub fn entry_count(&self) -> usize {
        self.profile.len()
    }
}

/// Deserialize a canonical profile JSON document into a parameter profile.
pub fn deserialize_parameter_profile_v1(
    json_text: &str,
) -> Result<ParameterProfileDeserializationV1, ParameterProfileDeserializationErrorV1> {
    let value: Value = serde_json::from_str(json_text)
        .map_err(|error| ParameterProfileDeserializationErrorV1::InvalidJson(error.to_string()))?;
    let object = match value {
        Value::Object(object) => object,
        _ => return Err(ParameterProfileDeserializationErrorV1::NotAnObject),
    };
    let mut profile = BTreeMap::new();
    for (name, entry) in object {
        let entry_object = match entry {
            Value::Object(entry_object) => entry_object,
            _ => return Err(ParameterProfileDeserializationErrorV1::EntryNotObject(name)),
        };
        let type_token = match entry_object.get("type") {
            Some(Value::String(type_token)) => type_token.clone(),
            _ => return Err(ParameterProfileDeserializationErrorV1::MissingType(name)),
        };
        let value_token = match entry_object.get("value") {
            Some(Value::String(value_token)) => value_token.clone(),
            _ => return Err(ParameterProfileDeserializationErrorV1::MissingValue(name)),
        };
        let parameter = AmiParameterValueV1::try_new(&name, &type_token, &value_token)
            .map_err(|error| ParameterProfileDeserializationErrorV1::InvalidValue {
                name: name.clone(),
                error,
            })?;
        profile.insert(name, parameter);
    }
    Ok(ParameterProfileDeserializationV1 { profile })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(name: &str, type_token: &str, value_token: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value_token).expect("valid value")
    }

    fn profile(pairs: &[(&str, &str, &str)]) -> BTreeMap<String, AmiParameterValueV1> {
        pairs
            .iter()
            .map(|(name, type_token, value_token)| {
                ((*name).to_string(), value(name, type_token, value_token))
            })
            .collect()
    }

    #[test]
    fn deserializes_valid_profile() {
        let json = r#"{"gain":{"type":"Float","value":"0.5"},"steps":{"type":"Integer","value":"7"}}"#;
        let result = deserialize_parameter_profile_v1(json).expect("deserialize");
        assert_eq!(result.entry_count(), 2);
        assert_eq!(result.profile()["gain"].value_token(), "0.5");
        assert_eq!(result.profile()["steps"].value_token(), "7");
    }

    #[test]
    fn round_trip_serialize_deserialize() {
        let p = profile(&[
            ("gain", "Float", "0.5"),
            ("mode", "String", "Linear"),
        ]);
        let json = crate::serialize_parameter_profile_v1(&p);
        let back = deserialize_parameter_profile_v1(&json).expect("round trip");
        assert_eq!(back.profile(), &p);
    }

    #[test]
    fn invalid_json_fails_closed() {
        match deserialize_parameter_profile_v1("not json") {
            Ok(_) => panic!("expected InvalidJson"),
            Err(ParameterProfileDeserializationErrorV1::InvalidJson(_)) => {}
            Err(other) => panic!("unexpected error: {other:?}"),
        }
    }

    #[test]
    fn non_object_root_fails_closed() {
        match deserialize_parameter_profile_v1("[1, 2]") {
            Ok(_) => panic!("expected NotAnObject"),
            Err(ParameterProfileDeserializationErrorV1::NotAnObject) => {}
            Err(other) => panic!("unexpected error: {other:?}"),
        }
    }

    #[test]
    fn missing_fields_fail_closed() {
        match deserialize_parameter_profile_v1(r#"{"gain":{"type":"Float"}}"#) {
            Ok(_) => panic!("expected MissingValue"),
            Err(ParameterProfileDeserializationErrorV1::MissingValue(name)) => {
                assert_eq!(name, "gain");
            }
            Err(other) => panic!("unexpected error: {other:?}"),
        }
        match deserialize_parameter_profile_v1(r#"{"gain":{"value":"0.5"}}"#) {
            Ok(_) => panic!("expected MissingType"),
            Err(ParameterProfileDeserializationErrorV1::MissingType(name)) => {
                assert_eq!(name, "gain");
            }
            Err(other) => panic!("unexpected error: {other:?}"),
        }
        match deserialize_parameter_profile_v1(r#"{"gain":42}"#) {
            Ok(_) => panic!("expected EntryNotObject"),
            Err(ParameterProfileDeserializationErrorV1::EntryNotObject(name)) => {
                assert_eq!(name, "gain");
            }
            Err(other) => panic!("unexpected error: {other:?}"),
        }
    }

    #[test]
    fn invalid_value_fails_closed() {
        match deserialize_parameter_profile_v1(r#"{"gain":{"type":"Float","value":"abc"}}"#) {
            Ok(_) => panic!("expected InvalidValue"),
            Err(ParameterProfileDeserializationErrorV1::InvalidValue { name, error }) => {
                assert_eq!(name, "gain");
                assert_eq!(error, AmiParameterValueErrorV1::InvalidFloat);
            }
            Err(other) => panic!("unexpected error: {other:?}"),
        }
        match deserialize_parameter_profile_v1(r#"{"gain":{"type":"Nope","value":"0.5"}}"#) {
            Ok(_) => panic!("expected InvalidValue"),
            Err(ParameterProfileDeserializationErrorV1::InvalidValue { error, .. }) => {
                assert_eq!(error, AmiParameterValueErrorV1::UnknownTypeToken);
            }
            Err(other) => panic!("unexpected error: {other:?}"),
        }
    }
}
