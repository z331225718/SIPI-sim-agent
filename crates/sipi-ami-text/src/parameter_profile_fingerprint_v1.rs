//! AMI parameter profile canonical fingerprint core (P4B-02b96).
//!
//! Computes a deterministic 64-bit fingerprint of an assembled parameter
//! profile (`BTreeMap<String, AmiParameterValueV1>`, e.g. produced by 02b44
//! assembly): `hash_parameter_profile_v1` hashes the canonical compact JSON
//! produced by `serialize_parameter_profile_v1` (02b81, sorted names, raw
//! value tokens) with the FNV-1a 64-bit algorithm. This is a stable change
//! detection and caching key for profiles: identical canonical serializations
//! hash identically, any spelling/name/value change changes the hash, and the
//! algorithm is trivially reproducible in any language.
//!
//! Fail-closed: the hash is total (no error path); FNV-1a 64 uses wrapping
//! arithmetic with the standard offset basis (14695981039346656037) and prime
//! (1099511628211); the empty profile hashes the empty object `{}`.

use std::collections::BTreeMap;

use crate::{AmiParameterValueV1, serialize_parameter_profile_v1};

/// Explicit scope policy of this slice: FNV-1a 64 canonical profile fingerprint.
pub const PARAMETER_PROFILE_FINGERPRINT_POLICY_V1: &str =
    "sipi.p4b-02b96.parameter-profile-fingerprint-v1.fnv1a64-canonical-profile";

const FNV1A64_OFFSET_BASIS: u64 = 14695981039346656037;
const FNV1A64_PRIME: u64 = 1099511628211;

/// FNV-1a 64-bit hash of a byte slice.
fn fnv1a64(bytes: &[u8]) -> u64 {
    let mut hash = FNV1A64_OFFSET_BASIS;
    for byte in bytes {
        hash ^= u64::from(*byte);
        hash = hash.wrapping_mul(FNV1A64_PRIME);
    }
    hash
}

/// 64-bit fingerprint of a profile's canonical serialization.
pub fn hash_parameter_profile_v1(profile: &BTreeMap<String, AmiParameterValueV1>) -> u64 {
    let serialized = serialize_parameter_profile_v1(profile);
    fnv1a64(serialized.as_bytes())
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
    fn hash_is_deterministic() {
        let p = profile(&[("gain", "Float", "0.5"), ("steps", "Integer", "7")]);
        assert_eq!(hash_parameter_profile_v1(&p), hash_parameter_profile_v1(&p));
    }

    #[test]
    fn hash_changes_with_value() {
        let a = profile(&[("gain", "Float", "0.5")]);
        let b = profile(&[("gain", "Float", "0.5001")]);
        assert_ne!(hash_parameter_profile_v1(&a), hash_parameter_profile_v1(&b));
    }

    #[test]
    fn hash_changes_with_name() {
        let a = profile(&[("gain", "Float", "0.5")]);
        let b = profile(&[("gain2", "Float", "0.5")]);
        assert_ne!(hash_parameter_profile_v1(&a), hash_parameter_profile_v1(&b));
    }

    #[test]
    fn hash_is_order_independent() {
        let a = profile(&[("b", "Integer", "7"), ("a", "Float", "0.5")]);
        let b = profile(&[("a", "Float", "0.5"), ("b", "Integer", "7")]);
        assert_eq!(hash_parameter_profile_v1(&a), hash_parameter_profile_v1(&b));
    }

    #[test]
    fn empty_profile_hash_matches_empty_object() {
        let p = BTreeMap::new();
        assert_eq!(hash_parameter_profile_v1(&p), fnv1a64(b"{}"));
    }

    #[test]
    fn float_spelling_changes_hash() {
        let a = profile(&[("gain", "Float", "0.5")]);
        let b = profile(&[("gain", "Float", "0.50")]);
        assert_ne!(hash_parameter_profile_v1(&a), hash_parameter_profile_v1(&b));
    }
}
