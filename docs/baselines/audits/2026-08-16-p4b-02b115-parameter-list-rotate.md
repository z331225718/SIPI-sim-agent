# P4B-02b115 Parameter List Rotate-Left Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b115 (cyclic left rotation on validated AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_rotate_v1.rs` in `sipi-ami-text`:
`rotate_parameter_list_left_v1` rotates the trimmed items of a validated List-typed
`AmiParameterValueV1` under the P4B-02b1 list rule (`(item, item, ...)`, items trimmed,
non-empty) left by a non-negative shift: returns the canonical list token whose items are the
trimmed items cyclically shifted left by `shift` positions (effective shift is
`shift % item_count`, so a full rotation reproduces the original token), re-joined with
`", "`. This is the cyclic-permutation companion of 02b104 reverse, 02b103 swap, and 02b105
sort. Fail-closed: a non-List value yields `NotAList`; a token that does not match the List
shape yields `MalformedList` (unreachable for values built via `AmiParameterValueV1::try_new`,
kept defensive instead of panicking). An independent Python reference replicates the rotation
rule over 4 test cases.

## Result

- 6 Rust unit tests green (rotate by one, rotate by two, full rotation identity, non-list,
  spacing canonicalized, single-item identity).
- Cross-check: 4 test cases (rotate by one, rotate by two, full rotation, non-list) driven
  through product runner `p4b_02b115_parameter_list_rotate_runner`; independent Python
  reference matches 100% on tokens and error keys; 4/4 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b115_parameter_list_rotate.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b115-parameter-list-rotate-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b115-parameter-list-rotate-stage.v1.yaml`; source map
  `p4b-02b115-mit-source-map.v1.yaml`.
- PLAN **P4B-02b115**; ledger note/gate P4B-02; coverage gates 284 -> 285.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Rotates list tokens on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
