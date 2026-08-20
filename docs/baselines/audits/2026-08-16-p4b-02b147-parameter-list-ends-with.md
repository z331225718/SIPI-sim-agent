# P4B-02b147 Parameter List Ends-With Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b147 (list-value suffix relation on validated AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_ends_with_v1.rs` in `sipi-ami-text`:
`list_ends_with_v1` checks whether the trimmed items of a validated List-typed
`AmiParameterValueV1` value end with the trimmed items of another validated List-typed value
under the P4B-02b1 list rule (`(item, item, ...)`, items trimmed, non-empty): returns whether
the suffix value's trimmed items equal the final items of the value element-wise (raw byte
equality, per the P4B-02b0 raw-byte binding). A suffix longer than the value is never a suffix.
This is the boolean companion of 02b131 longest-common-suffix (whose length equals the suffix
length exactly when the suffix holds) and the end-aligned mirror of 02b146 starts-with.
Fail-closed: either value not declared List yields `NotAList`; either token not matching the
List shape yields `MalformedList` (unreachable for values built via
`AmiParameterValueV1::try_new`, kept defensive instead of panicking). An independent Python
reference replicates the suffix rule over 4 test cases.

## Result

- 6 Rust unit tests green (suffix holds, full value, mismatched suffix, longer suffix,
  non-list, spacing canonicalized).
- Cross-check: 4 test cases (suffix holds, full suffix, longer suffix, non-list) driven through
  product runner `p4b_02b147_parameter_list_ends_with_runner`; independent Python reference
  matches 100% on booleans and error keys; 4/4 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b147_parameter_list_ends_with.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b147-parameter-list-ends-with-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b147-parameter-list-ends-with-stage.v1.yaml`; source map
  `p4b-02b147-mit-source-map.v1.yaml`.
- PLAN **P4B-02b147**; ledger note/gate P4B-02; coverage gates 316 -> 317.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Checks suffix relations on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
