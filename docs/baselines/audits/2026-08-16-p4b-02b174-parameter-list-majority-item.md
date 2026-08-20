# P4B-02b174 Parameter List Majority Item Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b174 (value-level strict majority on AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_majority_item_v1.rs` in `sipi-ami-text`:
`parameter_list_majority_item_v1` returns the distinct trimmed item whose occurrence count
is strictly greater than half the item count (raw byte equality, per the P4B-02b0 raw-byte
binding) of a validated List-typed `AmiParameterValueV1` value under the P4B-02b1 list rule
(`(item, item, ...)`, items trimmed, non-empty). At most one such item can exist; a
single-item list trivially has its item as the majority. This is the strict-majority
companion of 02b165 mode items (the mode is the majority when it exceeds half the count) and
of 02b121 frequency. Fail-closed: the value not declared List yields `NotAList`; the token
not matching the List shape yields `MalformedList` (unreachable for values built via
`AmiParameterValueV1::try_new`, kept defensive instead of panicking); no item exceeding half
the count yields `NoMajority`. An independent Python reference replicates the rule over 4
test cases.

## Result

- 6 Rust unit tests green (majority, single item, tie no majority, all distinct no majority,
  spacing canonicalized, non-list).
- Cross-check: 4 test cases (has majority, tie no majority, all distinct, non-list) driven
  through product runner `p4b_02b174_parameter_list_majority_item_runner`; independent
  Python reference matches 100% on items and error keys; 4/4 product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b174_parameter_list_majority_item.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b174-parameter-list-majority-item-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b174-parameter-list-majority-item-stage.v1.yaml`; source map
  `p4b-02b174-mit-source-map.v1.yaml`.
- PLAN **P4B-02b174**; ledger note/gate P4B-02; coverage gates 343 -> 344.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Computes majority item on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
