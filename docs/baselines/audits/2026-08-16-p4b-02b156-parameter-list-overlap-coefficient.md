# P4B-02b156 Parameter List Overlap Coefficient Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b156 (set-based overlap coefficient on validated AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_overlap_coefficient_v1.rs` in `sipi-ami-text`:
`list_overlap_coefficient_v1` computes the overlap coefficient of two validated List-typed
`AmiParameterValueV1` values under the P4B-02b1 list rule (`(item, item, ...)`, items trimmed,
non-empty): returns `distinct_intersection_size / min(size_a, size_b)` over the distinct
trimmed item sets of the two values (raw byte equality, per the P4B-02b0 raw-byte binding), as
an f64 in [0, 1]: 0 for disjoint values, 1 when one distinct set is a subset of the other. This
is the set-similarity companion of 02b154 Jaccard index and of 02b155 Dice index. Fail-closed:
either value not declared List yields `NotAList`; either token not matching the List shape
yields `MalformedList` (unreachable for values built via `AmiParameterValueV1::try_new`, kept
defensive instead of panicking). An independent Python reference replicates the similarity rule
over 4 test cases.

## Result

- 6 Rust unit tests green (subset reaches one, disjoint zero, partial overlap, duplicates
  ignored, non-list, spacing canonicalized).
- Cross-check: 4 test cases (subset, disjoint, partial overlap, non-list) driven through product
  runner `p4b_02b156_parameter_list_overlap_coefficient_runner`; independent Python reference
  matches 100% on formatted indices and error keys; 4/4 product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b156_parameter_list_overlap_coefficient.py` + 6 tests; crosscheck
  evidence `docs/baselines/p4b-02b156-parameter-list-overlap-coefficient-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b156-parameter-list-overlap-coefficient-stage.v1.yaml`; source map
  `p4b-02b156-mit-source-map.v1.yaml`.
- PLAN **P4B-02b156**; ledger note/gate P4B-02; coverage gates 325 -> 326.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Computes overlap coefficients on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
