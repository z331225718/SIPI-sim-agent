# P4B-02b76 Typed Parameter Profile Override Merge Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b76 (typed override merge of assembled parameter profiles)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_profile_override_merge_v1.rs` in `sipi-ami-text`:
`merge_parameter_profiles_with_override_v1` merges two assembled parameter profiles
(`BTreeMap<String, AmiParameterValueV1>`, e.g. produced by 02b44 assembly) with override semantics
under the typed value rules of `parameter_values_equivalent_v1` (02b70): shared names with
typed-equivalent values (`0.5` vs `0.50`) keep the base entry and count as matched;
typed-inequivalent shared names are overridden by the second profile and counted as overridden;
disjoint names carry over. This is the lenient companion of 02b74 strict typed merge (which fails
closed on conflict) and of 02b48 raw-token merge: the natural layering of an explicit override
profile over a defaults profile. Fail-closed by construction: the merge is total (no error path),
typed equivalence is computed by 02b70, and the resulting map is deterministic (BTreeMap order;
base entries kept for matched names). An independent Python reference replicates the typed override
merge over 4 test cases.

## Result

- 6 Rust unit tests green (disjoint merge, typed-equivalent keeps base, typed conflict overridden,
  cross-type conflict overridden, empty profiles, matched+overridden counts).
- Cross-check: 4 test cases (disjoint merge, spelling variants, override conflict, empty profiles)
  driven through product runner `p4b_02b76_parameter_profile_override_merge_runner`; independent
  Python reference matches 100% on matched/overridden counts and merged maps; 4/4 product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b76_parameter_profile_override_merge.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b76-parameter-profile-override-merge-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b76-parameter-profile-override-merge-stage.v1.yaml`; source map
  `p4b-02b76-mit-source-map.v1.yaml`.
- PLAN **P4B-02b76**; ledger note/gate P4B-02; coverage gates 245 -> 246.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Merges validated typed profiles only; total merge with override-on-conflict, no error path.
- No release certification, no acceptance evidence.
