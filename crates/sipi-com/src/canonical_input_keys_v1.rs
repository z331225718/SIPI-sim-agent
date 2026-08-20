//! Canonical normalized-input key signature core (P5-06d).
//!
//! Given the set of normalized COM input keys that are actually consumed from
//! the authorized config (the P5-06c ''in_config'' keys) as (key, canonical
//! value token) pairs, produce a deterministic sorted canonical signature:
//! the lexicographically sorted list of ''key=value'' lines. This is the
//! profile-agnostic compare-readiness preflight: a stable, order-free key set
//! that a later compare matrix can consume without depending on config file
//! ordering or the MATLAB oracle.
//!
//! Fail-closed rules: empty input, an empty key or value token, or a duplicate
//! key are hard errors. The canonical value token is whatever the caller
//! supplies (it is not re-formatted here; float formatting is the caller's
//! responsibility so that both the product and an independent reference agree
//! on the exact token). Sorting is byte-wise over the full ASCII ''key=value''
//! line, deterministic across Rust and Python.

/// Stable scope policy of the P5-06d canonical-input-key core.
pub const CANONICAL_INPUT_KEYS_POLICY_V1: &str =
    "sipi.p5-06d.canonical-input-keys.v1.sorted-signature";

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum CanonicalInputKeysErrorV1 {
    EmptyInput,
    EmptyKey,
    EmptyValue,
    DuplicateKey(String),
}

/// Produces the sorted canonical 'key=value' signature lines.
///
/// The input is a list of (key, canonical value token) pairs in any order;
/// the output is the lexicographically sorted list of 'key=value' lines. A
/// duplicate key, empty key, or empty value token fails closed.
pub fn canonical_input_keys_v1(
    entries: &[(String, String)],
) -> Result<Vec<String>, CanonicalInputKeysErrorV1> {
    if entries.is_empty() {
        return Err(CanonicalInputKeysErrorV1::EmptyInput);
    }
    let mut seen = std::collections::BTreeSet::new();
    let mut lines = Vec::with_capacity(entries.len());
    for (key, value) in entries {
        if key.is_empty() {
            return Err(CanonicalInputKeysErrorV1::EmptyKey);
        }
        if value.is_empty() {
            return Err(CanonicalInputKeysErrorV1::EmptyValue);
        }
        if !seen.insert(key.clone()) {
            return Err(CanonicalInputKeysErrorV1::DuplicateKey(key.clone()));
        }
        lines.push(format!("{key}={value}"));
    }
    lines.sort();
    Ok(lines)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn policy_fixed() {
        assert_eq!(
            CANONICAL_INPUT_KEYS_POLICY_V1,
            "sipi.p5-06d.canonical-input-keys.v1.sorted-signature"
        );
    }

    #[test]
    fn sorts_lexicographically_bytewise() {
        let entries = vec![
            ("zeta".to_string(), "1.0".to_string()),
            ("alpha".to_string(), "0.5".to_string()),
            ("beta_x".to_string(), "0".to_string()),
        ];
        let lines = canonical_input_keys_v1(&entries).expect("ok");
        assert_eq!(
            lines,
            vec!["alpha=0.5", "beta_x=0", "zeta=1.0"]
        );
    }

    #[test]
    fn digest_is_stable_over_sort() {
        let a = canonical_input_keys_v1(&[
            ("b".to_string(), "2".to_string()),
            ("a".to_string(), "1".to_string()),
        ])
        .expect("a");
        let b = canonical_input_keys_v1(&[
            ("a".to_string(), "1".to_string()),
            ("b".to_string(), "2".to_string()),
        ])
        .expect("b");
        assert_eq!(a, b);
    }

    #[test]
    fn rejects_empty_input() {
        assert_eq!(
            canonical_input_keys_v1(&[]).err(),
            Some(CanonicalInputKeysErrorV1::EmptyInput)
        );
    }

    #[test]
    fn rejects_empty_key_or_value() {
        assert_eq!(
            canonical_input_keys_v1(&[("".to_string(), "1".to_string())]).err(),
            Some(CanonicalInputKeysErrorV1::EmptyKey)
        );
        assert_eq!(
            canonical_input_keys_v1(&[("k".to_string(), "".to_string())]).err(),
            Some(CanonicalInputKeysErrorV1::EmptyValue)
        );
    }

    #[test]
    fn rejects_duplicate_key() {
        let entries = vec![
            ("k".to_string(), "1".to_string()),
            ("k".to_string(), "2".to_string()),
        ];
        assert_eq!(
            canonical_input_keys_v1(&entries).err(),
            Some(CanonicalInputKeysErrorV1::DuplicateKey("k".to_string()))
        );
    }
}
