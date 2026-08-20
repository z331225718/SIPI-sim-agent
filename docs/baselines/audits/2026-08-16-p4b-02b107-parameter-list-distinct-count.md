# P4B-02b107 Parameter List Distinct Item Count Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b107 (distinct list item counting on validated AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_distinct_count_v1.rs` in `sipi-ami-text`:
`count_distinct_parameter_list_items_v1` counts the distinct items of a validated List-typed
`AmiParameterValueV1` under the P4B-02b1 list rule (`(item, item, ...)`, items trimmed,
non-empty): returns the number of distinct trimmed items (raw byte equality, first-occurrence
semantics for membership). This is the distinct-count companion of 02b83 total item counting and of
02b98 dedup (which rewrites the token). Fail-closed: a non-List value yields `NotAList`; a token
that does not match the List shape yields `MalformedList` (unreachable for values built via
`AmiParameterValueV1::try_new`, kept defensive instead of panicking). An independent Python
reference replicates the distinct count rule over 4 test cases.

## Result

- 6 Rust unit tests green (counts distinct, all distinct, all same, non-list, spacing trimmed,
  single item).
- Cross-check: 4 test cases (with dups, all distinct, all same, non-list) driven through product
  runner `p4b_02b107_parameter_list_distinct_count_runner`; independent Python reference matches
  100% on distinct counts and error keys; 4/4 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b107_parameter_list_distinct_count.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b107-parameter-list-distinct-count-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b107-parameter-list-distinct-count-stage.v1.yaml`; source map
  `p4b-02b107-mit-source-map.v1.yaml`.
- PLAN **P4B-02b107**; ledger note/gate P4B-02; coverage gates 276 -> 277.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Counts distinct list items on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
