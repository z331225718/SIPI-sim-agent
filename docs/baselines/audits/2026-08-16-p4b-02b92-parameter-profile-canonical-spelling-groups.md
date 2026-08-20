# P4B-02b92 Parameter Profile Canonical Spelling Groups Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b92 (canonical spelling groups of assembled parameter profiles)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_profile_canonical_spelling_groups_v1.rs` in `sipi-ami-text`:
`group_parameter_profile_names_by_canonical_spelling_v1` groups the names of an assembled
parameter profile (`BTreeMap<String, AmiParameterValueV1>`, e.g. produced by 02b44 assembly) by
the canonical spelling of their values (`canonicalize_parameter_value_spelling_v1`, 02b75): names
whose values normalize to the same canonical spelling form one group (e.g. Integer `007` and
`7`, List `(a,b,c)` and `(a, b, c)`). Float and String values stay raw, so only
spelling-normalizable types can group. This finds semantically redundant entries within a profile
and is the grouping companion of 02b80 value lookup (query direction) and of 02b54 tree duplicate
consistency (tree level). Fail-closed: the grouping is total (no error path); groups come back in
deterministic sorted (spelling) order and each group's names in sorted order; `covered_names()`
sums the group name counts. An independent Python reference replicates the grouping over 4 test
cases.

## Result

- 6 Rust unit tests green (integer grouping, list spacing grouping, float separated, singleton
  count, empty profile, mixed types).
- Cross-check: 4 test cases (integer grouping, float separate, list grouping, empty profile) driven
  through product runner `p4b_02b92_parameter_profile_canonical_spelling_groups_runner`;
  independent Python reference matches 100% on counts and group lists; 4/4 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b92_parameter_profile_canonical_spelling_groups.py` + 6 tests; crosscheck
  evidence `docs/baselines/p4b-02b92-parameter-profile-canonical-spelling-groups-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b92-parameter-profile-canonical-spelling-groups-stage.v1.yaml`; source map
  `p4b-02b92-mit-source-map.v1.yaml`.
- PLAN **P4B-02b92**; ledger note/gate P4B-02; coverage gates 261 -> 262.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Groups validated profiles by canonical spelling only; Float/String stay raw.
- No release certification, no acceptance evidence.
