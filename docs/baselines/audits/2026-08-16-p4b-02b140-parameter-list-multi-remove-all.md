# P4B-02b140 Parameter List Multi-Value Remove-All Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b140 (batch removal by query set on validated AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_multi_remove_all_v1.rs` in `sipi-ami-text`:
`remove_all_parameter_list_items_multi_v1` removes every occurrence of every query item from a
validated List-typed `AmiParameterValueV1` under the P4B-02b1 list rule (`(item, item, ...)`,
items trimmed, non-empty): returns the canonical list token whose items are the trimmed items
that do not equal any query item exactly (raw byte equality, per the P4B-02b0 raw-byte binding;
query items are not trimmed), re-joined with `", "`. An empty query set removes nothing. This
is the batch companion of 02b112 single-query remove-all and of 02b99 indexed replace.
Fail-closed: a non-List value yields `NotAList`; a token that does not match the List shape
yields `MalformedList` (unreachable for values built via `AmiParameterValueV1::try_new`, kept
defensive instead of panicking). Removing all items yields the structurally empty token `()`
(not a valid 02b1 List value; the operation is total on the token level and does not
re-validate, mirroring 02b100 sole-item removal). An independent Python reference replicates the
removal rule over 4 test cases.

## Result

- 6 Rust unit tests green (removes query items, empty query set, all removed, no match,
  non-list, spacing canonicalized).
- Cross-check: 4 test cases (removes query items, empty query, all removed, non-list) driven
  through product runner `p4b_02b140_parameter_list_multi_remove_all_runner`; independent
  Python reference matches 100% on tokens and error keys; 4/4 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b140_parameter_list_multi_remove_all.py` + 6 tests; crosscheck
  evidence `docs/baselines/p4b-02b140-parameter-list-multi-remove-all-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b140-parameter-list-multi-remove-all-stage.v1.yaml`; source map
  `p4b-02b140-mit-source-map.v1.yaml`.
- PLAN **P4B-02b140**; ledger note/gate P4B-02; coverage gates 309 -> 310.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Removes list tokens on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
