# P4B-02b157 Parameter List Sequence Containment Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b157 (value-level contiguous sequence containment on AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_contains_sequence_v1.rs` in `sipi-ami-text`:
`list_contains_sequence_v1` checks whether the trimmed items of a validated List-typed
`AmiParameterValueV1` query value appear as a contiguous subsequence (window) of the trimmed
items of another validated List-typed host value under the P4B-02b1 list rule
(`(item, item, ...)`, items trimmed, non-empty): returns whether the host has a window equal to
the query's trimmed items element-wise (raw byte equality, per the P4B-02b0 raw-byte binding). A
query longer than the host is never contained. This is the value-level companion of 02b127
raw-query sublist containment (the host contains the query's token sequence as a window).
Fail-closed: either value not declared List yields `NotAList`; either token not matching the
List shape yields `MalformedList` (unreachable for values built via
`AmiParameterValueV1::try_new`, kept defensive instead of panicking). An independent Python
reference replicates the sequence rule over 4 test cases.

## Result

- 6 Rust unit tests green (contiguous contained, non-contiguous false, longer query false,
  equal values, non-list, spacing canonicalized).
- Cross-check: 4 test cases (contiguous contained, non-contiguous, longer query, non-list)
  driven through product runner `p4b_02b157_parameter_list_contains_sequence_runner`;
  independent Python reference matches 100% on booleans and error keys; 4/4 product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b157_parameter_list_contains_sequence.py` + 6 tests; crosscheck
  evidence `docs/baselines/p4b-02b157-parameter-list-contains-sequence-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b157-parameter-list-contains-sequence-stage.v1.yaml`; source map
  `p4b-02b157-mit-source-map.v1.yaml`.
- PLAN **P4B-02b157**; ledger note/gate P4B-02; coverage gates 326 -> 327.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Checks sequence containment on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
