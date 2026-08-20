# P4B-02b159 Parameter List Longest Common Subsequence Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b159 (deterministic LCS items on AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_longest_common_subsequence_v1.rs` in `sipi-ami-text`:
`list_longest_common_subsequence_v1` computes one deterministic (left-biased) longest common
subsequence of two validated List-typed `AmiParameterValueV1` values under the P4B-02b1 list
rule (`(item, item, ...)`, items trimmed, non-empty): returns the canonical list token of the
LCS of the two values' trimmed item sequences (raw byte equality, per the P4B-02b0 raw-byte
binding), order-preserving, not necessarily contiguous. Tie-breaking is deterministic: the
match is taken when items are equal, otherwise the reconstruction prefers skipping the left
item on a length tie, so product and independent reference agree item-for-item. An empty LCS
yields the structural empty token `()` (token-layer total function, mirroring 02b100). This
is the items companion of 02b142 LCS length (the returned item count equals the 02b142
length). Fail-closed: either value not declared List yields `NotAList`; either token not
matching the List shape yields `MalformedList` (unreachable for values built via
`AmiParameterValueV1::try_new`, kept defensive instead of panicking). An independent Python
reference replicates the LCS rule over 4 test cases.

## Result

- 6 Rust unit tests green (deterministic LCS, subsequence, identical values, disjoint empty
  token, left-biased tie-break, non-list).
- Cross-check: 4 test cases (partial overlap, subsequence, left-biased tie, non-list)
  driven through product runner `p4b_02b159_parameter_list_longest_common_subsequence_runner`;
  independent Python reference matches 100% on canonical tokens and error keys; 4/4
  product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b159_parameter_list_longest_common_subsequence.py` + 6 tests;
  crosscheck evidence
  `docs/baselines/p4b-02b159-parameter-list-longest-common-subsequence-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b159-parameter-list-longest-common-subsequence-stage.v1.yaml`; source map
  `p4b-02b159-mit-source-map.v1.yaml`.
- PLAN **P4B-02b159**; ledger note/gate P4B-02; coverage gates 328 -> 329.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Computes one deterministic LCS on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
