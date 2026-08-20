# P4B-02b48 AMI Parameter Profile Merge Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b48 (conflict-free merge of assembled parameter profiles)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_profile_merge_v1.rs` in `sipi-ami-text`: `merge_parameter_profiles_v1`
merges two assembled parameter maps (leaf name -> `AmiParameterValueV1`, e.g. produced by
P4B-02b44) into one conflict-free map: names present in only one map are taken from it; names
present in both with identical values are taken once (counted as matched); names present in both
with different values (type or value token) fail closed with
`ConflictingValue { name, old_type, old_value, new_type, new_value }`. This is the combination
primitive for assembled profiles — e.g. a base profile plus an override map. An independent Python
reference replicates the by-name merge over 4 test cases.

## Result

- 6 Rust unit tests green (disjoint merge; identical overlap matched; value conflict; type
  conflict; empty a; mixed merge counts).
- Cross-check: 4 test cases (disjoint, overlap identical, value conflict, empty a) driven through
  product runner `p4b_02b48_parameter_profile_merge_runner`; independent Python reference matches
  100% on valid flags, matched counts, merged maps, and error contexts; 4/4 product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b48_parameter_profile_merge.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b48-parameter-profile-merge-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b48-parameter-profile-merge-stage.v1.yaml`; source map
  `p4b-02b48-mit-source-map.v1.yaml`.
- PLAN **P4B-02b48**; ledger note/gate P4B-02; coverage gates 214 -> 215.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Merge is by parameter name; same-name entries in one map are impossible by construction.
- No release certification, no acceptance evidence.
