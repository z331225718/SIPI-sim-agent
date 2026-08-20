# P4B-02b90 Parameter Profile Typed Subset Check Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b90 (typed subset check of assembled parameter profiles)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_profile_typed_subset_v1.rs` in `sipi-ami-text`:
`check_parameter_profile_typed_subset_v1` checks whether one assembled parameter profile
(`BTreeMap<String, AmiParameterValueV1>`, e.g. produced by 02b44 assembly) is a typed subset of
another under `parameter_values_equivalent_v1` (02b70): reports whether every entry of the subset
profile is present in the superset profile under the same name with a typed-equivalent value
(spelling-insensitive, `0.5` vs `0.50`). This is the subset-direction companion of 02b71 exact
profile equivalence and of 02b79 typed diff: compatibility of a profile against a superset.
Fail-closed: names present in the subset but missing in the superset are reported sorted as
`missing`; shared names with typed-inequivalent values are reported sorted as `mismatched` (name
+ typed reason); `is_subset()` is true exactly when both lists are empty; the check is total (no
error path) and deterministic. An independent Python reference replicates the subset rule over 4
test cases.

## Result

- 6 Rust unit tests green (true subset, spelling variants, missing name, mismatched value, empty
  subset, cross-type mismatch).
- Cross-check: 4 test cases (subset ok, spelling variants, missing name, mismatched value) driven
  through product runner `p4b_02b90_parameter_profile_typed_subset_runner`; independent Python
  reference matches 100% on is_subset flags, sorted missing lists, and mismatched name/reason
  entries; 4/4 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b90_parameter_profile_typed_subset.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b90-parameter-profile-typed-subset-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b90-parameter-profile-typed-subset-stage.v1.yaml`; source map
  `p4b-02b90-mit-source-map.v1.yaml`.
- PLAN **P4B-02b90**; ledger note/gate P4B-02; coverage gates 259 -> 260.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Checks typed subset on validated profiles only; superset may carry extra names.
- No release certification, no acceptance evidence.
