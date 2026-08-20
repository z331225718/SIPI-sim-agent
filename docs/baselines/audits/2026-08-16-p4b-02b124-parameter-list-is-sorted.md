# P4B-02b124 Parameter List Sortedness Check Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b124 (sortedness check on validated AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_is_sorted_v1.rs` in `sipi-ami-text`:
`parameter_list_is_sorted_v1` checks whether the trimmed items of a validated List-typed
`AmiParameterValueV1` under the P4B-02b1 list rule (`(item, item, ...)`, items trimmed,
non-empty) are in sorted order: returns whether every adjacent pair of trimmed items is in
non-decreasing byte order (`descending == false`) or non-increasing byte order (`descending ==
true`); a single-item list is trivially sorted in either direction. Byte order follows the
P4B-02b0 raw-byte binding. This is the order-check companion of 02b105 sort. Fail-closed: a
non-List value yields `NotAList`; a token that does not match the List shape yields
`MalformedList` (unreachable for values built via `AmiParameterValueV1::try_new`, kept
defensive instead of panicking). An independent Python reference replicates the order rule over
4 test cases.

## Result

- 6 Rust unit tests green (ascending, descending, wrong direction, equal adjacent items,
  non-list, single item).
- Cross-check: 4 test cases (ascending, descending, not sorted, non-list) driven through product
  runner `p4b_02b124_parameter_list_is_sorted_runner`; independent Python reference matches
  100% on booleans and error keys; 4/4 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b124_parameter_list_is_sorted.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b124-parameter-list-is-sorted-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b124-parameter-list-is-sorted-stage.v1.yaml`; source map
  `p4b-02b124-mit-source-map.v1.yaml`.
- PLAN **P4B-02b124**; ledger note/gate P4B-02; coverage gates 293 -> 294.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Checks list tokens on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
