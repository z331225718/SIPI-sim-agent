# P4B-02b127 Parameter List Sublist Containment Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b127 (contiguous sublist membership on validated AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_contains_sublist_v1.rs` in `sipi-ami-text`:
`parameter_list_contains_sublist_v1` checks whether a validated List-typed
`AmiParameterValueV1` under the P4B-02b1 list rule (`(item, item, ...)`, items trimmed,
non-empty) contains a query sublist as a contiguous subsequence: returns whether the trimmed
items have a window equal to the query items element-wise (raw byte equality, per the P4B-02b0
raw-byte binding; query items are not trimmed). An empty query sublist is vacuously contained.
This is the sequence companion of 02b85 single-item membership and of 02b118 window enumeration
(which enumerates the candidate windows). Fail-closed: a non-List value yields `NotAList`; a
token that does not match the List shape yields `MalformedList` (unreachable for values built
via `AmiParameterValueV1::try_new`, kept defensive instead of panicking). An independent Python
reference replicates the sequence rule over 4 test cases.

## Result

- 6 Rust unit tests green (contiguous sublist, missing sublist, full sublist, empty sublist,
  non-list, raw query vs trimmed items).
- Cross-check: 4 test cases (contains sublist, missing sublist, full sublist, non-list) driven
  through product runner `p4b_02b127_parameter_list_contains_sublist_runner`; independent
  Python reference matches 100% on booleans and error keys; 4/4 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b127_parameter_list_contains_sublist.py` + 6 tests; crosscheck
  evidence `docs/baselines/p4b-02b127-parameter-list-contains-sublist-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b127-parameter-list-contains-sublist-stage.v1.yaml`; source map
  `p4b-02b127-mit-source-map.v1.yaml`.
- PLAN **P4B-02b127**; ledger note/gate P4B-02; coverage gates 296 -> 297.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Checks list tokens on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
