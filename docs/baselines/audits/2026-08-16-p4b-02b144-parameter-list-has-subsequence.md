# P4B-02b144 Parameter List Subsequence Check Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b144 (order-preserving subsequence check on validated AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_has_subsequence_v1.rs` in `sipi-ami-text`:
`parameter_list_has_subsequence_v1` checks whether a query sequence of raw items appears as a
subsequence of the trimmed items of a validated List-typed `AmiParameterValueV1` under the
P4B-02b1 list rule (`(item, item, ...)`, items trimmed, non-empty): returns whether every query
item can be matched in order (not necessarily contiguously) by raw byte equality (per the
P4B-02b0 raw-byte binding; query items are not trimmed). An empty query sequence is vacuously a
subsequence. This is the order-preserving companion of 02b127 contiguous sublist containment and
of 02b142 LCS length (the LCS length equals the query length exactly when the query is a
subsequence). Fail-closed: a non-List value yields `NotAList`; a token that does not match the
List shape yields `MalformedList` (unreachable for values built via
`AmiParameterValueV1::try_new`, kept defensive instead of panicking). An independent Python
reference replicates the subsequence rule over 4 test cases.

## Result

- 6 Rust unit tests green (non-contiguous found, out of order, missing item, empty query,
  non-list, raw query vs trimmed items).
- Cross-check: 4 test cases (non-contiguous, out of order, missing item, non-list) driven
  through product runner `p4b_02b144_parameter_list_has_subsequence_runner`; independent
  Python reference matches 100% on booleans and error keys; 4/4 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b144_parameter_list_has_subsequence.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b144-parameter-list-has-subsequence-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b144-parameter-list-has-subsequence-stage.v1.yaml`; source map
  `p4b-02b144-mit-source-map.v1.yaml`.
- PLAN **P4B-02b144**; ledger note/gate P4B-02; coverage gates 313 -> 314.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Checks subsequences on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
