# P4B-02b104 Parameter List Item Reverse Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b104 (list item order reversal on validated AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_reverse_v1.rs` in `sipi-ami-text`:
`reverse_parameter_list_items_v1` reverses the item order of a validated List-typed
`AmiParameterValueV1` under the P4B-02b1 list rule (`(item, item, ...)`, items trimmed,
non-empty): returns the canonical list token with the trimmed items in reverse order (re-joined
with `", "`). This is the order-transformation companion of the list-edit family (02b84 access,
02b98 dedup, 02b99 replace, 02b100 remove, 02b101 append, 02b102 insert, 02b103 swap).
Fail-closed: a non-List value yields `NotAList`; a token that does not match the List shape yields
`MalformedList` (unreachable for values built via `AmiParameterValueV1::try_new`, kept defensive
instead of panicking). An independent Python reference replicates the reverse rule over 4 test
cases.

## Result

- 6 Rust unit tests green (reverse items, four items, single unchanged, two swap, non-list,
  spacing canonicalized).
- Cross-check: 4 test cases (reverse multi, single, two items, non-list) driven through product
  runner `p4b_02b104_parameter_list_reverse_runner`; independent Python reference matches 100% on
  reversed tokens and error keys; 4/4 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b104_parameter_list_reverse.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b104-parameter-list-reverse-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b104-parameter-list-reverse-stage.v1.yaml`; source map
  `p4b-02b104-mit-source-map.v1.yaml`.
- PLAN **P4B-02b104**; ledger note/gate P4B-02; coverage gates 273 -> 274.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Reverses list items on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
