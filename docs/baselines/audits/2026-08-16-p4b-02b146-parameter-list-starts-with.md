# P4B-02b146 Parameter List Starts-With Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b146 (list-value prefix relation on validated AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_starts_with_v1.rs` in `sipi-ami-text`:
`list_starts_with_v1` checks whether the trimmed items of a validated List-typed
`AmiParameterValueV1` value begin with the trimmed items of another validated List-typed value
under the P4B-02b1 list rule (`(item, item, ...)`, items trimmed, non-empty): returns whether
the prefix value's trimmed items equal the first items of the value element-wise (raw byte
equality, per the P4B-02b0 raw-byte binding). A prefix longer than the value is never a prefix.
This is the boolean companion of 02b130 longest-common-prefix (whose length equals the prefix
length exactly when the prefix holds). Fail-closed: either value not declared List yields
`NotAList`; either token not matching the List shape yields `MalformedList` (unreachable for
values built via `AmiParameterValueV1::try_new`, kept defensive instead of panicking). An
independent Python reference replicates the prefix rule over 4 test cases.

## Result

- 6 Rust unit tests green (prefix holds, full value, mismatched prefix, longer prefix,
  non-list, spacing canonicalized).
- Cross-check: 4 test cases (prefix holds, full prefix, longer prefix, non-list) driven through
  product runner `p4b_02b146_parameter_list_starts_with_runner`; independent Python reference
  matches 100% on booleans and error keys; 4/4 product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b146_parameter_list_starts_with.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b146-parameter-list-starts-with-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b146-parameter-list-starts-with-stage.v1.yaml`; source map
  `p4b-02b146-mit-source-map.v1.yaml`.
- PLAN **P4B-02b146**; ledger note/gate P4B-02; coverage gates 315 -> 316.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Checks prefix relations on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
