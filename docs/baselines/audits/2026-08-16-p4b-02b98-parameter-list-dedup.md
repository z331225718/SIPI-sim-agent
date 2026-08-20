# P4B-02b98 Parameter List Item Deduplication Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b98 (list item deduplication on validated AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_dedup_v1.rs` in `sipi-ami-text`:
`deduplicate_parameter_list_items_v1` removes duplicate items from a validated List-typed
`AmiParameterValueV1` under the P4B-02b1 list rule (`(item, item, ...)`, items trimmed,
non-empty): returns the canonical list token whose items are trimmed, compared by raw byte
equality, and re-joined with `", "`, keeping the first occurrence of each distinct item. This is
the list-normalization companion of 02b83 item counting, 02b84 item access, and 02b85 membership.
Fail-closed: a non-List value yields `NotAList`; a token that does not match the List shape yields
`MalformedList` (unreachable for values built via `AmiParameterValueV1::try_new`, kept defensive
instead of panicking). An independent Python reference replicates the dedup rule over 4 test cases.

## Result

- 6 Rust unit tests green (duplicates removed keeping first, no duplicates unchanged, items
  trimmed before compare, non-list, single item, all duplicates collapse).
- Cross-check: 4 test cases (with dups, no dups, spacing dups, non-list) driven through product
  runner `p4b_02b98_parameter_list_dedup_runner`; independent Python reference matches 100% on
  deduped tokens and error keys; 4/4 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b98_parameter_list_dedup.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b98-parameter-list-dedup-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b98-parameter-list-dedup-stage.v1.yaml`; source map
  `p4b-02b98-mit-source-map.v1.yaml`.
- PLAN **P4B-02b98**; ledger note/gate P4B-02; coverage gates 267 -> 268.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Deduplicates list items on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
