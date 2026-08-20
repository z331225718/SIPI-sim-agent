# P4B-02b142 Parameter List LCS Length Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b142 (list-value LCS length on validated AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_longest_common_subsequence_length_v1.rs` in `sipi-ami-text`:
`list_longest_common_subsequence_length_v1` computes the length of the longest common
subsequence (LCS) of two validated List-typed `AmiParameterValueV1` values under the P4B-02b1
list rule (`(item, item, ...)`, items trimmed, non-empty): returns the length of the longest
sequence of trimmed items that appears in both values in order (not necessarily contiguously),
element-wise by raw byte equality (per the P4B-02b0 raw-byte binding). The LCS length is at most
the smaller item count and equals the full smaller count when one value is a subsequence of the
other. This is the sequence companion of 02b130 longest-common-prefix and of 02b131
longest-common-suffix. Fail-closed: either value not declared List yields `NotAList`; either
token not matching the List shape yields `MalformedList` (unreachable for values built via
`AmiParameterValueV1::try_new`, kept defensive instead of panicking). An independent Python
reference replicates the LCS rule over 4 test cases.

## Result

- 6 Rust unit tests green (LCS length, one is subsequence of other, identical values, disjoint,
  non-list, spacing canonicalized).
- Cross-check: 4 test cases (LCS length, subsequence, disjoint, non-list) driven through product
  runner `p4b_02b142_parameter_list_longest_common_subsequence_length_runner`; independent
  Python reference matches 100% on lengths and error keys; 4/4 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b142_parameter_list_longest_common_subsequence_length.py` + 6 tests;
  crosscheck evidence
  `docs/baselines/p4b-02b142-parameter-list-longest-common-subsequence-length-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b142-parameter-list-longest-common-subsequence-length-stage.v1.yaml`; source
  map `p4b-02b142-mit-source-map.v1.yaml`.
- PLAN **P4B-02b142**; ledger note/gate P4B-02; coverage gates 311 -> 312.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Computes LCS lengths on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
