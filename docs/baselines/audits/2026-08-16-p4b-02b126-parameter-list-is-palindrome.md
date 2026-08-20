# P4B-02b126 Parameter List Palindrome Check Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b126 (palindrome check on validated AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_is_palindrome_v1.rs` in `sipi-ami-text`:
`parameter_list_is_palindrome_v1` checks whether the trimmed items of a validated List-typed
`AmiParameterValueV1` under the P4B-02b1 list rule (`(item, item, ...)`, items trimmed,
non-empty) read the same forward and backward: returns whether the sequence of trimmed items
equals its own reverse (raw byte equality, per the P4B-02b0 raw-byte binding); a single-item list
is trivially a palindrome. This is the symmetry companion of 02b104 reverse (a list is a
palindrome exactly when reversing it reproduces the same token). Fail-closed: a non-List value
yields `NotAList`; a token that does not match the List shape yields `MalformedList`
(unreachable for values built via `AmiParameterValueV1::try_new`, kept defensive instead of
panicking). An independent Python reference replicates the symmetry rule over 4 test cases.

## Result

- 6 Rust unit tests green (palindrome, non-palindrome, even-length palindrome, single item,
  non-list, spacing canonicalized).
- Cross-check: 4 test cases (palindrome, non-palindrome, even-length palindrome, non-list)
  driven through product runner `p4b_02b126_parameter_list_is_palindrome_runner`; independent
  Python reference matches 100% on booleans and error keys; 4/4 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b126_parameter_list_is_palindrome.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b126-parameter-list-is-palindrome-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b126-parameter-list-is-palindrome-stage.v1.yaml`; source map
  `p4b-02b126-mit-source-map.v1.yaml`.
- PLAN **P4B-02b126**; ledger note/gate P4B-02; coverage gates 295 -> 296.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Checks list tokens on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
