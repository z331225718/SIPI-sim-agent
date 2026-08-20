# P4B-02b100 Parameter List Item Remove Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b100 (indexed list item removal on validated AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_remove_v1.rs` in `sipi-ami-text`:
`remove_parameter_list_item_v1` removes one item of a validated List-typed `AmiParameterValueV1`
under the P4B-02b1 list rule (`(item, item, ...)`, items trimmed, non-empty): returns the canonical
list token whose item at the 0-based index is removed (remaining items re-joined with `", "`).
This is the delete companion of 02b99 replace, 02b84 access, and 02b98 dedup in the list-edit
family. Fail-closed: a non-List value yields `NotAList`; a token that does not match the List
shape yields `MalformedList` (unreachable for values built via `AmiParameterValueV1::try_new`,
kept defensive instead of panicking); an index at or beyond the item count yields
`IndexOutOfRange` carrying both the requested index and the actual item count. Removing the sole
item yields the structurally empty token `()` (not a valid 02b1 List value; the operation is total
on the token level and does not re-validate). An independent Python reference replicates the remove
rule over 4 test cases.

## Result

- 6 Rust unit tests green (remove at index, first and last, out of range with counts, non-list,
  sole item yields empty token, spacing canonicalized).
- Cross-check: 4 test cases (remove middle, remove last, out of range, non-list) driven through
  product runner `p4b_02b100_parameter_list_remove_runner`; independent Python reference matches
  100% on removed tokens and error keys with index/count; 4/4 product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b100_parameter_list_remove.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b100-parameter-list-remove-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b100-parameter-list-remove-stage.v1.yaml`; source map
  `p4b-02b100-mit-source-map.v1.yaml`.
- PLAN **P4B-02b100**; ledger note/gate P4B-02; coverage gates 269 -> 270.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Removes list items on validated values only; non-List and out-of-range inputs fail closed.
- No release certification, no acceptance evidence.
