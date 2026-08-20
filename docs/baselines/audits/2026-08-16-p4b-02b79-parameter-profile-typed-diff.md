# P4B-02b79 Typed Parameter Profile Diff Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b79 (typed semantic diff of assembled parameter profiles)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_profile_typed_diff_v1.rs` in `sipi-ami-text`:
`diff_parameter_profiles_typed_v1` diffs two assembled parameter profiles (`BTreeMap<String,
AmiParameterValueV1>`, e.g. produced by 02b44 assembly) under the typed value semantics of
`parameter_values_equivalent_v1` (02b70): shared names with typed-equivalent values (`0.5` vs
`0.50`) count as matched, shared names with typed-inequivalent values are reported as changed
(with both sides' declared types and raw value tokens plus the typed reason), left-only names are
removed and right-only names are added. This is the typed companion of 02b47 profile diff (raw
token equality) and the report-level view over the boolean 02b71 profile equivalence.
Fail-closed: the diff is total (no error path), all lists come back in deterministic sorted order,
and every changed entry carries its typed reason via `ParameterValueInequivalenceReasonV1`. An
independent Python reference replicates the typed diff over 4 test cases.

## Result

- 6 Rust unit tests green (identical profiles, spelling variants matched, added/removed, typed
  change with reason, cross-type change, empty profiles).
- Cross-check: 4 test cases (identical, spelling variants, added/removed, typed changed) driven
  through product runner `p4b_02b79_parameter_profile_typed_diff_runner`; independent Python
  reference matches 100% on matched/added/removed lists and changed entries with reasons;
  4/4 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b79_parameter_profile_typed_diff.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b79-parameter-profile-typed-diff-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b79-parameter-profile-typed-diff-stage.v1.yaml`; source map
  `p4b-02b79-mit-source-map.v1.yaml`.
- PLAN **P4B-02b79**; ledger note/gate P4B-02; coverage gates 248 -> 249.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Diffs validated typed profiles only; spelling-insensitive matching via 02b70, changed entries
  carry typed reasons.
- No release certification, no acceptance evidence.
