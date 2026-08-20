//! AMI parameter profile canonical serialization core (P4B-02b81).
//!
//! Serializes an assembled parameter profile (`BTreeMap<String,
//! AmiParameterValueV1>`, e.g. produced by 02b44 assembly) to a deterministic
//! compact JSON object: `{"name":{"type":"Float","value":"0.5"},...}` with
//! names in sorted (BTreeMap) order. This is the profile-level companion of
//! 02b19 tree serde (which serializes trees, not profiles): a stable textual
//! form for hashing, caching, and cross-tool exchange. Values are raw token
//! strings, so there is no float formatting hazard.
//!
//! Fail-closed: serialization is total (no error path); the emitted key order
//! is deterministic (sorted names); the JSON escapes exactly per RFC 8259
//! (quotes and backslashes in raw value tokens are escaped).

use std::collections::BTreeMap;

use serde_json::{Map, Value};

use crate::AmiParameterValueV1;

/// Explicit scope policy of this slice: canonical profile JSON serialization.
pub const PARAMETER_PROFILE_SERIALIZATION_POLICY_V1: &str =
    "sipi.p4b-02b81.parameter-profile-serialization-v1.canonical-profile-json";

/// Serialize an assembled parameter profile to canonical compact JSON.
pub fn serialize_parameter_profile_v1(
    profile: &BTreeMap<String, AmiParameterValueV1>,
) -> String {
    let mut object = Map::new();
    for (name, parameter) in profile {
        let mut entry = Map::new();
        entry.insert(
            "type".to_string(),
            Value::String(parameter.parameter_type().token().to_string()),
        );
        entry.insert(
            "value".to_string(),
            Value::String(parameter.value_token().to_string()),
        );
        object.insert(name.clone(), Value::Object(entry));
    }
    serde_json::to_string(&Value::Object(object)).expect("profile json serialization")
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
    fn simple_profile_serializes() {
        let p = profile(&[("gain", "Float", "0.5")]);
        let json = serialize_parameter_profile_v1(&p);
        assert_eq!(json, r#"{"gain":{"type":"Float","value":"0.5"}}"#);
    }

    #[test]
    fn names_serialize_in_sorted_order() {
        let p = profile(&[
            ("zeta", "Float", "1.0"),
            ("alpha", "Integer", "7"),
        ]);
        let json = serialize_parameter_profile_v1(&p);
        assert_eq!(
            json,
            r#"{"alpha":{"type":"Integer","value":"7"},"zeta":{"type":"Float","value":"1.0"}}"#
        );
    }

    #[test]
    fn mixed_types_serialize() {
        let p = profile(&[
            ("on", "Boolean", "True"),
            ("mode", "String", "Linear"),
            ("channels", "List", "(a, b)"),
        ]);
        let json = serialize_parameter_profile_v1(&p);
        assert_eq!(
            json,
            r#"{"channels":{"type":"List","value":"(a, b)"},"mode":{"type":"String","value":"Linear"},"on":{"type":"Boolean","value":"True"}}"#
        );
    }

    #[test]
    fn empty_profile_serializes_empty_object() {
        let p = BTreeMap::new();
        assert_eq!(serialize_parameter_profile_v1(&p), "{}");
    }

    #[test]
    fn serialization_is_deterministic_across_input_orders() {
        let a = profile(&[("b", "Integer", "7"), ("a", "Float", "0.5")]);
        let b = profile(&[("a", "Float", "0.5"), ("b", "Integer", "7")]);
        assert_eq!(
            serialize_parameter_profile_v1(&a),
            serialize_parameter_profile_v1(&b)
        );
    }

    #[test]
    fn serialized_output_parses_back() {
        let p = profile(&[
            ("gain", "Float", "0.5"),
            ("mode", "String", "Linear"),
        ]);
        let json = serialize_parameter_profile_v1(&p);
        let parsed: Value = serde_json::from_str(&json).expect("parse back");
        assert_eq!(parsed["gain"]["type"], "Float");
        assert_eq!(parsed["gain"]["value"], "0.5");
        assert_eq!(parsed["mode"]["type"], "String");
        assert_eq!(parsed["mode"]["value"], "Linear");
    }
}
