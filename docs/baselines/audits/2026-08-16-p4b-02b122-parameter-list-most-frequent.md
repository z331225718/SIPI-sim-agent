# P4B-02b122 Parameter List Most-Frequent Item Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b122 (most frequent item analysis on validated AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_most_frequent_v1.rs` in `sipi-ami-text`:
`most_frequent_parameter_list_item_v1` finds the most frequent distinct trimmed item of a
validated List-typed `AmiParameterValueV1` under the P4B-02b1 list rule (`(item, item, ...)`,
items trimmed, non-empty): returns the `(item, count)` pair whose item has the largest total
occurrence count (raw byte equality, per the P4B-02b0 raw-byte binding); ties are resolved to the
item that first occurs earliest in the list. This is the frequency-max companion of 02b121
frequency mapping (whose entries it maximizes) and of 02b107 distinct counting (every count is at
least 1 and at most the item count). Fail-closed: a non-List value yields `NotAList`; a token
that does not match the List shape yields `MalformedList` (unreachable for values built via
`AmiParameterValueV1::try_new`, kept defensive instead of panicking). An independent Python
reference replicates the frequency rule over 4 test cases.

## Result

- 6 Rust unit tests green (most frequent, earliest tie, all distinct, single item, non-list,
  spacing canonicalized).
- Cross-check: 4 test cases (most frequent, earliest tie, all distinct, non-list) driven through
  product runner `p4b_02b122_parameter_list_most_frequent_runner`; independent Python
  reference matches 100% on item/count pairs and error keys; 4/4 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b122_parameter_list_most_frequent.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b122-parameter-list-most-frequent-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b122-parameter-list-most-frequent-stage.v1.yaml`; source map
  `p4b-02b122-mit-source-map.v1.yaml`.
- PLAN **P4B-02b122**; ledger note/gate P4B-02; coverage gates 291 -> 292.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Analyzes list tokens on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
