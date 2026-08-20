# P4B-02b47 AMI Parameter Profile Diff Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b47 (regression diff of assembled parameter profiles)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_profile_diff_v1.rs` in `sipi-ami-text`: `diff_parameter_profiles_v1`
compares two assembled parameter maps (leaf name -> `AmiParameterValueV1`, e.g. produced by
P4B-02b44) by name: matched counts names present in both with identical values (full
`AmiParameterValueV1` equality, so a type or value-token change counts as changed); added lists
names only in the new map; removed lists names only in the old map; changed carries
`ParameterValueChangeV1` records (name + old + new values), all sorted by name. The diff is total
and result-based: empty maps are valid inputs and an empty diff is a valid result. An independent
Python reference replicates the by-name comparison over 4 test cases.

## Result

- 6 Rust unit tests green (identical profiles; added and removed; value change; type change;
  empty against full; mixed diff with all categories).
- Cross-check: 4 test cases (identical, added and removed, value change, empty a) driven through
  product runner `p4b_02b47_parameter_profile_diff_runner`; independent Python reference matches
  100% on valid flags, matched counts, added/removed lists, and change records; 4/4 product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b47_parameter_profile_diff.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b47-parameter-profile-diff-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b47-parameter-profile-diff-stage.v1.yaml`; source map
  `p4b-02b47-mit-source-map.v1.yaml`.
- PLAN **P4B-02b47**; ledger note/gate P4B-02; coverage gates 213 -> 214.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Diff is by parameter name; same-name entries in one map are impossible by construction.
- No release certification, no acceptance evidence.
