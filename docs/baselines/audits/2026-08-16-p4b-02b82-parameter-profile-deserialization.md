# P4B-02b82 Parameter Profile Canonical Deserialization Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b82 (canonical profile JSON parsing back into assembled parameter profiles)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_profile_deserialization_v1.rs` in `sipi-ami-text`:
`deserialize_parameter_profile_v1` parses the canonical compact JSON produced by
`serialize_parameter_profile_v1` (02b81) back into an assembled parameter profile
(`BTreeMap<String, AmiParameterValueV1>`): each object key is a parameter name whose value must be
an object carrying a `type` and a `value` string; every entry is rebuilt through
`AmiParameterValueV1::try_new` (02b1). Together with 02b81 this gives a deterministic profile
round trip (serialize -> deserialize -> identical profile). Profile-level companion of 02b19 tree
serde (trees, not profiles). Fail-closed: invalid JSON, a non-object root, a non-object entry, a
missing `type`/`value` field, an unknown type token, or a value that violates the 02b1 rules are
all strictly rejected with distinct error variants; the resulting map is deterministic (BTreeMap
order). An independent Python reference replicates the parsing and validation over 4 test cases.

## Result

- 6 Rust unit tests green (valid profile, serialize/deserialize round trip, invalid JSON,
  non-object root, missing fields, invalid value).
- Cross-check: 4 test cases (valid profile, invalid JSON, missing value, unknown type) driven
  through product runner `p4b_02b82_parameter_profile_deserialization_runner`; independent Python
  reference matches 100% on valid flags, profile maps, and error/name keys; 4/4 product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b82_parameter_profile_deserialization.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b82-parameter-profile-deserialization-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b82-parameter-profile-deserialization-stage.v1.yaml`; source map
  `p4b-02b82-mit-source-map.v1.yaml`.
- PLAN **P4B-02b82**; ledger note/gate P4B-02; coverage gates 251 -> 252.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Parses canonical 02b81 profile JSON only; all malformed inputs fail closed with distinct errors.
- No release certification, no acceptance evidence.
