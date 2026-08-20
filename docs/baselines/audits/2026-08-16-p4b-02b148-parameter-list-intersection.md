# P4B-02b148 Parameter List Intersection Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b148 (value intersection on validated AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_intersection_v1.rs` in `sipi-ami-text`:
`list_intersection_v1` computes the value intersection of two validated List-typed
`AmiParameterValueV1` values under the P4B-02b1 list rule (`(item, item, ...)`, items trimmed,
non-empty): returns the canonical list token whose items are the trimmed items of the left value
that equal some trimmed item of the right value (raw byte equality, per the P4B-02b0 raw-byte
binding), in left order with duplicates preserved. This is the set-wise companion of 02b140
multi-remove-all and of 02b113 single-query keep-only (the intersection equals keeping only the
right value's items). Fail-closed: either value not declared List yields `NotAList`; either
token not matching the List shape yields `MalformedList` (unreachable for values built via
`AmiParameterValueV1::try_new`, kept defensive instead of panicking). An empty intersection
yields the structurally empty token `()` (not a valid 02b1 List value; the operation is total
on the token level and does not re-validate, mirroring 02b100 sole-item removal). An independent
Python reference replicates the intersection rule over 4 test cases.

## Result

- 6 Rust unit tests green (left order, duplicates preserved, disjoint empty, equal values,
  non-list, spacing canonicalized).
- Cross-check: 4 test cases (intersection, duplicates, disjoint, non-list) driven through
  product runner `p4b_02b148_parameter_list_intersection_runner`; independent Python reference
  matches 100% on tokens and error keys; 4/4 product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b148_parameter_list_intersection.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b148-parameter-list-intersection-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b148-parameter-list-intersection-stage.v1.yaml`; source map
  `p4b-02b148-mit-source-map.v1.yaml`.
- PLAN **P4B-02b148**; ledger note/gate P4B-02; coverage gates 317 -> 318.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Computes intersections on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
