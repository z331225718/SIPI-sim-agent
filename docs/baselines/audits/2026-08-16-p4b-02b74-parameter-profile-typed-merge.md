# P4B-02b74 Typed Parameter Profile Merge Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b74 (typed-value merge of assembled parameter profiles)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_profile_typed_merge_v1.rs` in `sipi-ami-text`:
`merge_parameter_profiles_typed_v1` merges two assembled parameter profiles (`BTreeMap<String,
AmiParameterValueV1>`, e.g. produced by 02b44 assembly) using the typed value semantics of
`parameter_values_equivalent_v1` (02b70) instead of raw token equality: shared names with
typed-equivalent values (`0.5` vs `0.50`, `007` vs `7`) merge as matched, typed-inequivalent shared
names are a conflict, disjoint names carry over. This sits beside 02b48 profile merge (raw `Eq` on
tokens, so `0.5` vs `0.50` would conflict) as the spelling-insensitive composition layer.
Fail-closed: any typed-inequivalent shared name yields `ConflictingValue` with the declared types
and raw value tokens of both sides; the merged map keeps the left profile's entry for matched names
and is deterministic (BTreeMap order). An independent Python reference replicates the typed merge
over 4 test cases.

## Result

- 6 Rust unit tests green (disjoint merge, typed-equivalent spelling merge, integer spelling
  variants, typed conflict report, cross-type conflict report, empty profiles).
- Cross-check: 4 test cases (disjoint merge, spelling variants, typed conflict, empty profiles)
  driven through product runner `p4b_02b74_parameter_profile_typed_merge_runner`; independent
  Python reference matches 100% on valid flags, matched counts, merged maps, and conflict details;
  4/4 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b74_parameter_profile_typed_merge.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b74-parameter-profile-typed-merge-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b74-parameter-profile-typed-merge-stage.v1.yaml`; source map
  `p4b-02b74-mit-source-map.v1.yaml`.
- PLAN **P4B-02b74**; ledger note/gate P4B-02; coverage gates 243 -> 244.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Merges validated typed profiles only; spelling-insensitive matching via 02b70, conflicts fail
  closed with both sides' types and raw tokens.
- No release certification, no acceptance evidence.
