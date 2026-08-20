# P4B-02b71 Parameter Profile Semantic Equivalence Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b71 (typed semantic equivalence of assembled parameter profile maps)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_profile_equivalence_v1.rs` in `sipi-ami-text`: `parameter_profiles_equivalent_v1`
compares two assembled parameter profiles (`BTreeMap<String, AmiParameterValueV1>`, e.g. produced by
02b44 assembly) by typed value semantics — the profile-map-level companion of 02b70 value
equivalence, sitting above 02b47 profile diff which reports added/removed/changed by raw tokens.
Every shared name must hold typed-equivalent values (02b70 rules: cross-type never equivalent,
Float/Integer on parsed finite values, Boolean exact True/False, String raw bytes, List trimmed item
sequences) and the name sets must match exactly. Fail-closed: names present in exactly one profile
are reported as left_only/right_only; any typed value mismatch is reported per name with its reason;
both-empty profiles are Equivalent; all lists come back in deterministic sorted order. An independent
Python reference replicates the typed comparison over 4 test cases.

## Result

- 6 Rust unit tests green (identical profiles, spelling variants, missing names both directions,
  typed value mismatch with reason, cross-type mismatch, empty profiles).
- Cross-check: 4 test cases (identical profiles, spelling variants, missing name, value mismatch)
  driven through product runner `p4b_02b71_parameter_profile_equivalence_runner`; independent Python
  reference matches 100% on equivalent flags, sorted left_only/right_only lists, and mismatch
  name/reason lists; 4/4 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b71_parameter_profile_equivalence.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b71-parameter-profile-equivalence-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b71-parameter-profile-equivalence-stage.v1.yaml`; source map
  `p4b-02b71-mit-source-map.v1.yaml`.
- PLAN **P4B-02b71**; ledger note/gate P4B-02; coverage gates 240 -> 241.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Compares validated typed profiles only; parameter names are identity at map keys, values compare
  by typed semantics (02b70), not raw token spelling.
- No release certification, no acceptance evidence.
