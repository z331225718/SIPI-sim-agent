# P4B-02b150 Parameter List Union Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b150 (multiset union on validated AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_union_v1.rs` in `sipi-ami-text`:
`list_union_v1` computes the multiset union of two validated List-typed `AmiParameterValueV1`
values under the P4B-02b1 list rule (`(item, item, ...)`, items trimmed, non-empty): returns
the canonical list token whose items are the trimmed items of the left value followed by the
trimmed items of the right value that equal no left value item (raw byte equality, per the
P4B-02b0 raw-byte binding; left duplicates preserved, right-only items appended). This is the
set-wise companion of 02b106 join (which appends all right items) and the complement of 02b149
symmetric difference (a list equals the join of its intersection and symmetric difference with
another list). Fail-closed: either value not declared List yields `NotAList`; either token not
matching the List shape yields `MalformedList` (unreachable for values built via
`AmiParameterValueV1::try_new`, kept defensive instead of panicking). An independent Python
reference replicates the union rule over 4 test cases.

## Result

- 6 Rust unit tests green (union appends right-only items, left duplicates preserved, equal
  values, disjoint full join, non-list, spacing canonicalized).
- Cross-check: 4 test cases (union, left duplicates, equal values, non-list) driven through
  product runner `p4b_02b150_parameter_list_union_runner`; independent Python reference
  matches 100% on tokens and error keys; 4/4 product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b150_parameter_list_union.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b150-parameter-list-union-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b150-parameter-list-union-stage.v1.yaml`; source map
  `p4b-02b150-mit-source-map.v1.yaml`.
- PLAN **P4B-02b150**; ledger note/gate P4B-02; coverage gates 319 -> 320.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Computes unions on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
