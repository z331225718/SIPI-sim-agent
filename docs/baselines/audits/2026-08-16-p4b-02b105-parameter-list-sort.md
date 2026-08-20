# P4B-02b105 Parameter List Item Sort Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b105 (list item byte-order sort on validated AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_sort_v1.rs` in `sipi-ami-text`:
`sort_parameter_list_items_v1` sorts the items of a validated List-typed `AmiParameterValueV1`
under the P4B-02b1 list rule (`(item, item, ...)`, items trimmed, non-empty): returns the canonical
list token with the trimmed items sorted in byte (lexicographic) order, duplicates preserved
(re-joined with `", "`). This is the order-transform companion of 02b104 reverse in the list-edit
family. Note: items are sorted by raw byte order, so numeric spellings sort lexicographically
(`10` before `2`). Fail-closed: a non-List value yields `NotAList`; a token that does not match
the List shape yields `MalformedList` (unreachable for values built via
`AmiParameterValueV1::try_new`, kept defensive instead of panicking). An independent Python
reference replicates the sort rule over 4 test cases.

## Result

- 6 Rust unit tests green (sort items, numeric lexicographic, duplicates preserved, non-list,
  single unchanged, spacing canonicalized).
- Cross-check: 4 test cases (sort multi, numeric lex, duplicates, non-list) driven through product
  runner `p4b_02b105_parameter_list_sort_runner`; independent Python reference matches 100% on
  sorted tokens and error keys; 4/4 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b105_parameter_list_sort.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b105-parameter-list-sort-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b105-parameter-list-sort-stage.v1.yaml`; source map
  `p4b-02b105-mit-source-map.v1.yaml`.
- PLAN **P4B-02b105**; ledger note/gate P4B-02; coverage gates 274 -> 275.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Sorts list items on validated values only; non-List inputs fail closed; byte-order sort only.
- No release certification, no acceptance evidence.
