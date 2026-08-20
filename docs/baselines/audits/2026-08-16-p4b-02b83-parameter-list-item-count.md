# P4B-02b83 Parameter List Item Count Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b83 (standalone list item counting on validated AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_item_count_v1.rs` in `sipi-ami-text`:
`count_parameter_list_items_v1` counts the items of a validated List-typed `AmiParameterValueV1`
under the P4B-02b1 list rule (`(item, item, ...)`, items trimmed, non-empty): returns the number
of items. This is the standalone value-level primitive for list sizes, distinct from 02b37 tree
leaf decoding (which needs a tree and a type map) and from 02b75 canonical spelling (which rewrites
spellings). Fail-closed: a value whose declared type is not List yields `NotAList`; a token that
does not match the List shape yields `MalformedList` (unreachable for values built via
`AmiParameterValueV1::try_new`, kept defensive instead of panicking). An independent Python
reference replicates the counting rule over 4 test cases.

## Result

- 6 Rust unit tests green (counts list items, single item, spacing ignored, non-list fail-closed,
  raw string items, count matches typed equivalence length).
- Cross-check: 4 test cases (three item list, single item, spacing variants, non-list) driven
  through product runner `p4b_02b83_parameter_list_item_count_runner`; independent Python
  reference matches 100% on counts and error keys; 4/4 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b83_parameter_list_item_count.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b83-parameter-list-item-count-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b83-parameter-list-item-count-stage.v1.yaml`; source map
  `p4b-02b83-mit-source-map.v1.yaml`.
- PLAN **P4B-02b83**; ledger note/gate P4B-02; coverage gates 252 -> 253.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Counts list items on validated values only; non-List values fail closed.
- No release certification, no acceptance evidence.
