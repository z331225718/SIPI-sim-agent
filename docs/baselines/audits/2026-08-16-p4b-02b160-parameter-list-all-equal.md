# P4B-02b160 Parameter List All-Equal Check Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b160 (value-level all-equal check on AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_all_equal_v1.rs` in `sipi-ami-text`:
`parameter_list_all_equal_v1` checks whether all trimmed items of a validated List-typed
`AmiParameterValueV1` value are mutually equal under the P4B-02b1 list rule
(`(item, item, ...)`, items trimmed, non-empty): returns whether every pair of trimmed items
is equal by raw byte equality (per the P4B-02b0 raw-byte binding); a single-item list is
trivially all-equal. This is the value-level companion of 02b134 equal-adjacent-count (all
adjacent pairs equal if and only if all items equal) and of 02b136 unique-item-count (unique
count 1 if and only if all equal). Fail-closed: the value not declared List yields
`NotAList`; the token not matching the List shape yields `MalformedList` (unreachable for
values built via `AmiParameterValueV1::try_new`, kept defensive instead of panicking). An
independent Python reference replicates the all-equal rule over 4 test cases.

## Result

- 6 Rust unit tests green (repeated items, mixed items, single item, spacing canonicalized,
  non-list, raw byte equality).
- Cross-check: 4 test cases (repeated items, mixed items, single item, non-list) driven
  through product runner `p4b_02b160_parameter_list_all_equal_runner`; independent Python
  reference matches 100% on booleans and error keys; 4/4 product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b160_parameter_list_all_equal.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b160-parameter-list-all-equal-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b160-parameter-list-all-equal-stage.v1.yaml`; source map
  `p4b-02b160-mit-source-map.v1.yaml`.
- PLAN **P4B-02b160**; ledger note/gate P4B-02; coverage gates 329 -> 330.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Checks all-equal on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
