# P4B-02b172 Parameter List Adjacent Change Count Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b172 (value-level adjacent change count on AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_adjacent_change_count_v1.rs` in `sipi-ami-text`:
`parameter_list_adjacent_change_count_v1` returns the number of adjacent item pairs with
unequal trimmed items of a validated List-typed `AmiParameterValueV1` value under the
P4B-02b1 list rule (`(item, item, ...)`, items trimmed, non-empty), counting adjacent pairs
`(i, i + 1)` whose items differ by raw byte equality (per the P4B-02b0 raw-byte binding). The
count is 0 for an all-equal list and `len - 1` for an all-distinct list. This is the change
companion of 02b168 run count (changes = runs - 1) and of 02b134 equal-adjacent-count
(changes + equals = len - 1). Fail-closed: the value not declared List yields `NotAList`;
the token not matching the List shape yields `MalformedList` (unreachable for values built
via `AmiParameterValueV1::try_new`, kept defensive instead of panicking). An independent
Python reference replicates the rule over 4 test cases.

## Result

- 6 Rust unit tests green (counts changes, all equal zero, all distinct len-1, single item
  zero, spacing canonicalized, non-list).
- Cross-check: 4 test cases (counts changes, all equal, all distinct, non-list) driven
  through product runner `p4b_02b172_parameter_list_adjacent_change_count_runner`;
  independent Python reference matches 100% on counts and error keys; 4/4 product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b172_parameter_list_adjacent_change_count.py` + 6 tests; crosscheck
  evidence `docs/baselines/p4b-02b172-parameter-list-adjacent-change-count-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b172-parameter-list-adjacent-change-count-stage.v1.yaml`; source map
  `p4b-02b172-mit-source-map.v1.yaml`.
- PLAN **P4B-02b172**; ledger note/gate P4B-02; coverage gates 341 -> 342.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Computes adjacent change count on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
