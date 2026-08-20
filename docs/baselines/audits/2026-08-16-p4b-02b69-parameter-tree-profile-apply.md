# P4B-02b69 Parameter Tree Profile Apply Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b69 (assembled profile application onto an AMI parameter tree)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_tree_profile_apply_v1.rs` in `sipi-ami-text`: `apply_parameter_profile_to_tree_v1`
applies an assembled parameter profile (leaf name -> `AmiParameterValueV1`, e.g. produced by
P4B-02b44) onto an `AmiParameterTreeV1` (P4B-02b7): every leaf addressed by a profile name gets its
value tokens replaced by the profile value token. Profile values are already validated, so no
re-validation or type map is needed — this is the final consumption composition (assemble -> apply).
Fail-closed: an empty profile (`EmptyProfile`), a profile name with no leaf (`MissingLeaf`), and a
profile name matching leaves at multiple depths (`AmbiguousName`) are strictly rejected. An
independent Python reference replicates the tokenize/build/apply pipeline over 4 test cases.

## Result

- 5 Rust unit tests green (applies profile values; unlisted leaves unchanged; missing leaf;
  ambiguous name; empty profile).
- Cross-check: 4 test cases (apply single, apply multi, missing leaf, empty profile) driven through
  product runner `p4b_02b69_parameter_tree_profile_apply_runner`; independent Python reference
  matches 100% on valid flags, applied counts, resulting tree structures, and error contexts;
  4/4 product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b69_parameter_tree_profile_apply.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b69-parameter-tree-profile-apply-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b69-parameter-tree-profile-apply-stage.v1.yaml`; source map
  `p4b-02b69-mit-source-map.v1.yaml`.
- PLAN **P4B-02b69**; ledger note/gate P4B-02; coverage gates 238 -> 239.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Applies validated profile values only; no re-validation.
- No release certification, no acceptance evidence.
