# P4B-02b112 Parameter List Remove-All-By-Value Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b112 (value-based bulk item removal on validated AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_remove_all_v1.rs` in `sipi-ami-text`:
`remove_all_parameter_list_items_v1` removes every occurrence of a query item from a validated
List-typed `AmiParameterValueV1` under the P4B-02b1 list rule (`(item, item, ...)`, items
trimmed, non-empty): returns the canonical list token whose items are the trimmed items that do
not equal the query item exactly (raw byte equality, per the P4B-02b0 raw-byte binding; the query
itself is not trimmed), re-joined with `", "`. This is the value-based bulk companion of 02b100
index-based removal and of 02b108 occurrence counting (the removed count equals the occurrence
count of the query). Fail-closed: a non-List value yields `NotAList`; a token that does not
match the List shape yields `MalformedList` (unreachable for values built via
`AmiParameterValueV1::try_new`, kept defensive instead of panicking). Removing all items yields
the structurally empty token `()` (not a valid 02b1 List value; the operation is total on the
token level and does not re-validate, mirroring 02b100 sole-item removal). An independent Python
reference replicates the removal rule over 4 test cases.

## Result

- 6 Rust unit tests green (removes all occurrences, no occurrence, all removed, raw query vs
  trimmed items, non-list, single-item removal).
- Cross-check: 4 test cases (removes all occurrences, no occurrence, all removed, non-list)
  driven through product runner `p4b_02b112_parameter_list_remove_all_runner`; independent
  Python reference matches 100% on tokens and error keys; 4/4 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b112_parameter_list_remove_all.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b112-parameter-list-remove-all-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b112-parameter-list-remove-all-stage.v1.yaml`; source map
  `p4b-02b112-mit-source-map.v1.yaml`.
- PLAN **P4B-02b112**; ledger note/gate P4B-02; coverage gates 281 -> 282.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Removes list items on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
