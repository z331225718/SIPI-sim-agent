# P4B-02b102 Parameter List Item Insert Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b102 (positional list item insertion on validated AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_insert_v1.rs` in `sipi-ami-text`:
`insert_parameter_list_item_v1` inserts one item into a validated List-typed `AmiParameterValueV1`
under the P4B-02b1 list rule (`(item, item, ...)`, items trimmed, non-empty): returns the canonical
list token with the trimmed new item inserted before the current item at the 0-based index (index
equal to the item count appends, mirroring 02b101). This extends the list-edit family (02b84
access, 02b98 dedup, 02b99 replace, 02b100 remove, 02b101 append) with positional insertion.
Fail-closed: a non-List value yields `NotAList`; a token that does not match the List shape yields
`MalformedList` (unreachable for values built via `AmiParameterValueV1::try_new`, kept defensive
instead of panicking); a new item that is empty after trimming yields `EmptyNewItem`; an index
beyond the item count yields `IndexOutOfRange` carrying both the requested index and the actual
item count. An independent Python reference replicates the insert rule over 4 test cases.

## Result

- 6 Rust unit tests green (insert at middle, insert at start, insert at end equals append,
  out of range, empty new item, non-list).
- Cross-check: 4 test cases (insert middle, insert start, out of range, empty new item) driven
  through product runner `p4b_02b102_parameter_list_insert_runner`; independent Python reference
  matches 100% on inserted tokens and error keys with index/count; 4/4 product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b102_parameter_list_insert.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b102-parameter-list-insert-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b102-parameter-list-insert-stage.v1.yaml`; source map
  `p4b-02b102-mit-source-map.v1.yaml`.
- PLAN **P4B-02b102**; ledger note/gate P4B-02; coverage gates 271 -> 272.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Inserts list items on validated values only; out-of-range, empty-new-item, non-List fail closed.
- No release certification, no acceptance evidence.
