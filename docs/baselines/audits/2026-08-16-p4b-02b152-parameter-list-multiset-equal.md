# P4B-02b152 Parameter List Multiset Equality Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b152 (multiset equality on validated AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_multiset_equal_v1.rs` in `sipi-ami-text`:
`list_multiset_equal_v1` checks whether two validated List-typed `AmiParameterValueV1`
values are equal as multisets under the P4B-02b1 list rule (`(item, item, ...)`, items trimmed,
non-empty): returns whether every trimmed item of one value occurs the same number of times in
the other (raw byte equality, per the P4B-02b0 raw-byte binding; order-insensitive, counts
equal). This is the multiset companion of 02b121 frequency mapping (two lists are
multiset-equal exactly when their frequency maps coincide) and of 02b150 union (a list is
multiset-equal to the union of itself and a sub-multiset). Fail-closed: either value not
declared List yields `NotAList`; either token not matching the List shape yields
`MalformedList` (unreachable for values built via `AmiParameterValueV1::try_new`, kept
defensive instead of panicking). An independent Python reference replicates the multiset rule
over 4 test cases.

## Result

- 6 Rust unit tests green (order-insensitive equal, counts must match, different items,
  different lengths, non-list, spacing canonicalized).
- Cross-check: 4 test cases (order-insensitive, counts mismatch, different lengths, non-list)
  driven through product runner `p4b_02b152_parameter_list_multiset_equal_runner`; independent
  Python reference matches 100% on booleans and error keys; 4/4 product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b152_parameter_list_multiset_equal.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b152-parameter-list-multiset-equal-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b152-parameter-list-multiset-equal-stage.v1.yaml`; source map
  `p4b-02b152-mit-source-map.v1.yaml`.
- PLAN **P4B-02b152**; ledger note/gate P4B-02; coverage gates 321 -> 322.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Checks multiset equality on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
