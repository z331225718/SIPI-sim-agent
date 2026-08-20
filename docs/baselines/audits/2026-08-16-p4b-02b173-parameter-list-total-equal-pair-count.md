# P4B-02b173 Parameter List Total Equal Pair Count Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b173 (value-level equal-pair count on AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_total_equal_pair_count_v1.rs` in `sipi-ami-text`:
`parameter_list_total_equal_pair_count_v1` returns the number of unordered position pairs
with equal trimmed items of a validated List-typed `AmiParameterValueV1` value under the
P4B-02b1 list rule (`(item, item, ...)`, items trimmed, non-empty): counts the pairs
`(i, j)` with `i < j` whose items are equal by raw byte equality (per the P4B-02b0 raw-byte
binding), which equals the sum over distinct items of `count * (count - 1) / 2`. An
all-distinct list yields 0. This is the position-pair companion of 02b135 distinct-pair-count
(pairs of distinct values) and of 02b134 equal-adjacent-count (adjacent equal pairs are a
subset of the equal pairs). Fail-closed: the value not declared List yields `NotAList`; the
token not matching the List shape yields `MalformedList` (unreachable for values built via
`AmiParameterValueV1::try_new`, kept defensive instead of panicking). An independent Python
reference replicates the rule over 4 test cases.

## Result

- 6 Rust unit tests green (mixed counts, all distinct zero, single repeated all pairs,
  single item zero, spacing canonicalized, non-list).
- Cross-check: 4 test cases (mixed counts, all distinct, single repeated, non-list) driven
  through product runner `p4b_02b173_parameter_list_total_equal_pair_count_runner`;
  independent Python reference matches 100% on counts and error keys; 4/4 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b173_parameter_list_total_equal_pair_count.py` + 6 tests; crosscheck
  evidence `docs/baselines/p4b-02b173-parameter-list-total-equal-pair-count-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b173-parameter-list-total-equal-pair-count-stage.v1.yaml`; source map
  `p4b-02b173-mit-source-map.v1.yaml`.
- PLAN **P4B-02b173**; ledger note/gate P4B-02; coverage gates 342 -> 343.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Computes total equal pair count on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
