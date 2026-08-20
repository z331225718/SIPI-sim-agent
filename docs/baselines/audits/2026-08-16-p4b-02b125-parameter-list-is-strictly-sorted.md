# P4B-02b125 Parameter List Strict Sortedness Check Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b125 (strict sortedness check on validated AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_is_strictly_sorted_v1.rs` in `sipi-ami-text`:
`parameter_list_is_strictly_sorted_v1` checks whether the trimmed items of a validated
List-typed `AmiParameterValueV1` under the P4B-02b1 list rule (`(item, item, ...)`, items
trimmed, non-empty) are in strictly sorted order: returns whether every adjacent pair of trimmed
items is in strictly increasing byte order (`descending == false`) or strictly decreasing byte
order (`descending == true`); a single-item list is trivially strictly sorted in either
direction. Byte order follows the P4B-02b0 raw-byte binding. This is the strict-order companion
of 02b124 sortedness check and of 02b105 sort. Fail-closed: a non-List value yields `NotAList`;
a token that does not match the List shape yields `MalformedList` (unreachable for values built
via `AmiParameterValueV1::try_new`, kept defensive instead of panicking). An independent Python
reference replicates the order rule over 4 test cases.

## Result

- 6 Rust unit tests green (strictly ascending, strictly descending, equal breaks strict,
  wrong direction, non-list, single item).
- Cross-check: 4 test cases (strictly ascending, strictly descending, equal breaks strict,
  non-list) driven through product runner `p4b_02b125_parameter_list_is_strictly_sorted_runner`;
  independent Python reference matches 100% on booleans and error keys; 4/4 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b125_parameter_list_is_strictly_sorted.py` + 6 tests; crosscheck
  evidence `docs/baselines/p4b-02b125-parameter-list-is-strictly-sorted-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b125-parameter-list-is-strictly-sorted-stage.v1.yaml`; source map
  `p4b-02b125-mit-source-map.v1.yaml`.
- PLAN **P4B-02b125**; ledger note/gate P4B-02; coverage gates 294 -> 295.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Checks list tokens on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
