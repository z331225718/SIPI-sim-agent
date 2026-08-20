# P4B-02b84 Parameter List Item Access Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b84 (indexed list item access on validated AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_item_access_v1.rs` in `sipi-ami-text`:
`get_parameter_list_item_v1` reads one item of a validated List-typed `AmiParameterValueV1`
under the P4B-02b1 list rule (`(item, item, ...)`, items trimmed, non-empty): returns the trimmed
item at a 0-based index. This is the indexed companion of 02b83 list item counting and the
standalone value-level primitive for list element access (02b37 delivers whole lists only inside
tree decoding). Fail-closed: a non-List value yields `NotAList`; a token that does not match the
List shape yields `MalformedList` (unreachable for values built via `AmiParameterValueV1::try_new`,
kept defensive instead of panicking); an index at or beyond the item count yields
`IndexOutOfRange` carrying both the requested index and the actual item count. An independent
Python reference replicates the item reading rule over 4 test cases.

## Result

- 6 Rust unit tests green (item at index, spacing trimmed, out-of-range with counts, non-list,
  first and last items, single item list).
- Cross-check: 4 test cases (middle item, spacing, out of range, non-list) driven through product
  runner `p4b_02b84_parameter_list_item_access_runner`; independent Python reference matches 100%
  on items and error keys with index/count; 4/4 product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b84_parameter_list_item_access.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b84-parameter-list-item-access-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b84-parameter-list-item-access-stage.v1.yaml`; source map
  `p4b-02b84-mit-source-map.v1.yaml`.
- PLAN **P4B-02b84**; ledger note/gate P4B-02; coverage gates 253 -> 254.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Reads list items on validated values only; non-List and out-of-range inputs fail closed.
- No release certification, no acceptance evidence.
