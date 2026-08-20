# P4B-02b113 Parameter List Keep-Only-By-Value Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b113 (value-based retain on validated AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_keep_only_v1.rs` in `sipi-ami-text`:
`keep_only_parameter_list_items_v1` keeps every occurrence of a query item in a validated
List-typed `AmiParameterValueV1` under the P4B-02b1 list rule (`(item, item, ...)`, items
trimmed, non-empty): returns the canonical list token whose items are the trimmed items that
equal the query item exactly (raw byte equality, per the P4B-02b0 raw-byte binding; the query
itself is not trimmed), re-joined with `", "`. This is the retain inverse of 02b112
remove-all-by-value and of 02b108 occurrence counting (the kept count equals the occurrence count
of the query). Fail-closed: a non-List value yields `NotAList`; a token that does not match the
List shape yields `MalformedList` (unreachable for values built via
`AmiParameterValueV1::try_new`, kept defensive instead of panicking). Keeping no items yields the
structurally empty token `()` (not a valid 02b1 List value; the operation is total on the token
level and does not re-validate, mirroring 02b100 sole-item removal). An independent Python
reference replicates the retain rule over 4 test cases.

## Result

- 6 Rust unit tests green (keeps only matching, no match, keeps all, raw query vs trimmed items,
  non-list, kept-count consistency with occurrence counting).
- Cross-check: 4 test cases (keeps only matching, no match, keeps all, non-list) driven through
  product runner `p4b_02b113_parameter_list_keep_only_runner`; independent Python reference
  matches 100% on tokens and error keys; 4/4 product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b113_parameter_list_keep_only.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b113-parameter-list-keep-only-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b113-parameter-list-keep-only-stage.v1.yaml`; source map
  `p4b-02b113-mit-source-map.v1.yaml`.
- PLAN **P4B-02b113**; ledger note/gate P4B-02; coverage gates 282 -> 283.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Retains list items on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
