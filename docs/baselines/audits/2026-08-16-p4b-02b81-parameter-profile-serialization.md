# P4B-02b81 Parameter Profile Canonical Serialization Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b81 (canonical compact JSON serialization of assembled parameter profiles)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_profile_serialization_v1.rs` in `sipi-ami-text`:
`serialize_parameter_profile_v1` serializes an assembled parameter profile (`BTreeMap<String,
AmiParameterValueV1>`, e.g. produced by 02b44 assembly) to a deterministic compact JSON object:
`{"name":{"type":"Float","value":"0.5"},...}` with names in sorted (BTreeMap) order. This is the
profile-level companion of 02b19 tree serde (which serializes trees, not profiles): a stable
textual form for hashing, caching, and cross-tool exchange. Values are raw token strings, so there
is no float formatting hazard. Fail-closed: serialization is total (no error path); the emitted
key order is deterministic (sorted names); the JSON escapes exactly per RFC 8259 (quotes and
backslashes in raw value tokens are escaped). An independent Python reference serializes the same
profile with sorted keys and compact separators over 4 test cases.

## Result

- 6 Rust unit tests green (simple profile, sorted names, mixed types, empty profile,
  deterministic across input orders, round-trip parse).
- Cross-check: 4 test cases (simple profile, sorted order, mixed types, empty profile) driven
  through product runner `p4b_02b81_parameter_profile_serialization_runner`; independent Python
  reference matches 100% on the exact serialized strings; 4/4 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b81_parameter_profile_serialization.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b81-parameter-profile-serialization-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b81-parameter-profile-serialization-stage.v1.yaml`; source map
  `p4b-02b81-mit-source-map.v1.yaml`.
- PLAN **P4B-02b81**; ledger note/gate P4B-02; coverage gates 250 -> 251.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Serializes validated typed profiles only; canonical compact JSON with sorted names.
- No release certification, no acceptance evidence.
