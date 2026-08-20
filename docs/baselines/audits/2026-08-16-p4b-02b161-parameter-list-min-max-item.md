# P4B-02b161 Parameter List Min-Max Item Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b161 (value-level min-max item on AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_min_max_item_v1.rs` in `sipi-ami-text`:
`parameter_list_min_item_v1` and `parameter_list_max_item_v1` return the lexicographically
smallest and largest trimmed items of a validated List-typed `AmiParameterValueV1` value
under the P4B-02b1 list rule (`(item, item, ...)`, items trimmed, non-empty), ordered by raw
byte equality and byte lexicographic order (per the P4B-02b0 raw-byte binding; for valid
UTF-8 this order equals code-point order). The list is non-empty by rule, so both always
exist; a single-item list returns that item for both. This is the value-level companion of
02b124 is-sorted and 02b125 is-strictly-sorted (the first and last items of a sorted list are
its min and max). Fail-closed: the value not declared List yields `NotAList`; the token not
matching the List shape yields `MalformedList` (unreachable for values built via
`AmiParameterValueV1::try_new`, kept defensive instead of panicking). An independent Python
reference replicates the min-max rule over 4 test cases.

## Result

- 6 Rust unit tests green (distinct items, single item both, duplicates, raw byte order,
  spacing canonicalized, non-list).
- Cross-check: 4 test cases (distinct items, single item, duplicates, non-list) driven
  through product runner `p4b_02b161_parameter_list_min_max_item_runner`; independent
  Python reference matches 100% on min/max items and error keys; 4/4 product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b161_parameter_list_min_max_item.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b161-parameter-list-min-max-item-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b161-parameter-list-min-max-item-stage.v1.yaml`; source map
  `p4b-02b161-mit-source-map.v1.yaml`.
- PLAN **P4B-02b161**; ledger note/gate P4B-02; coverage gates 330 -> 331.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Computes min/max items on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
