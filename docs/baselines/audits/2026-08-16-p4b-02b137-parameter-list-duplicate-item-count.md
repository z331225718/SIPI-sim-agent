# P4B-02b137 Parameter List Duplicate-Item Count Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b137 (multi-occurrence item counting on validated AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_duplicate_item_count_v1.rs` in `sipi-ami-text`:
`parameter_list_duplicate_item_count_v1` counts the duplicate distinct trimmed items of a
validated List-typed `AmiParameterValueV1` under the P4B-02b1 list rule (`(item, item, ...)`,
items trimmed, non-empty): returns the number of distinct trimmed items that occur more than
once (raw byte equality, per the P4B-02b0 raw-byte binding). The 02b107 distinct count equals
the 02b136 unique count plus the duplicate-item count. This is the multi-occurrence companion of
02b136 unique-item counting and of 02b121 frequency mapping (whose entries with count > 1 it
counts). Fail-closed: a non-List value yields `NotAList`; a token that does not match the List
shape yields `MalformedList` (unreachable for values built via `AmiParameterValueV1::try_new`,
kept defensive instead of panicking). An independent Python reference replicates the duplicate
rule over 4 test cases.

## Result

- 6 Rust unit tests green (duplicate distinct items, all distinct, single repeated, single item,
  non-list, spacing canonicalized).
- Cross-check: 4 test cases (duplicate items, all distinct, single repeated, non-list) driven
  through product runner `p4b_02b137_parameter_list_duplicate_item_count_runner`; independent
  Python reference matches 100% on counts and error keys; 4/4 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b137_parameter_list_duplicate_item_count.py` + 6 tests; crosscheck
  evidence `docs/baselines/p4b-02b137-parameter-list-duplicate-item-count-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b137-parameter-list-duplicate-item-count-stage.v1.yaml`; source map
  `p4b-02b137-mit-source-map.v1.yaml`.
- PLAN **P4B-02b137**; ledger note/gate P4B-02; coverage gates 306 -> 307.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Counts duplicate items on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
