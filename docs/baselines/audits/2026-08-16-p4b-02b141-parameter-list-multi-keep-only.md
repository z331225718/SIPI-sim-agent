# P4B-02b141 Parameter List Multi-Value Keep-Only Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b141 (batch retain by query set on validated AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_multi_keep_only_v1.rs` in `sipi-ami-text`:
`keep_only_parameter_list_items_multi_v1` keeps every occurrence of every query item in a
validated List-typed `AmiParameterValueV1` under the P4B-02b1 list rule (`(item, item, ...)`,
items trimmed, non-empty): returns the canonical list token whose items are the trimmed items
that equal some query item exactly (raw byte equality, per the P4B-02b0 raw-byte binding; query
items are not trimmed), re-joined with `", "`. An empty query set keeps nothing. This is the
batch retain companion of 02b113 single-query keep-only and the inverse of 02b140
multi-remove-all. Fail-closed: a non-List value yields `NotAList`; a token that does not match
the List shape yields `MalformedList` (unreachable for values built via
`AmiParameterValueV1::try_new`, kept defensive instead of panicking). Keeping no items yields
the structurally empty token `()` (not a valid 02b1 List value; the operation is total on the
token level and does not re-validate, mirroring 02b100 sole-item removal). An independent Python
reference replicates the retain rule over 4 test cases.

## Result

- 6 Rust unit tests green (keeps query items, empty query set, keeps all, no match, non-list,
  spacing canonicalized).
- Cross-check: 4 test cases (keeps query items, empty query, keeps all, non-list) driven through
  product runner `p4b_02b141_parameter_list_multi_keep_only_runner`; independent Python
  reference matches 100% on tokens and error keys; 4/4 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b141_parameter_list_multi_keep_only.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b141-parameter-list-multi-keep-only-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b141-parameter-list-multi-keep-only-stage.v1.yaml`; source map
  `p4b-02b141-mit-source-map.v1.yaml`.
- PLAN **P4B-02b141**; ledger note/gate P4B-02; coverage gates 310 -> 311.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Retains list tokens on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
