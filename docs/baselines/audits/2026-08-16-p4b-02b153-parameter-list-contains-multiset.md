# P4B-02b153 Parameter List Multiset Containment Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b153 (multiset sub-multiset check on validated AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_contains_multiset_v1.rs` in `sipi-ami-text`:
`list_contains_multiset_v1` checks whether one validated List-typed `AmiParameterValueV1`
value contains another as a multiset sub-multiset under the P4B-02b1 list rule
(`(item, item, ...)`, items trimmed, non-empty): returns whether every trimmed item of the
query value occurs at least as many times in the host value (raw byte equality, per the P4B-02b0
raw-byte binding; order-insensitive). This is the multiset companion of 02b152 multiset equality
(mutual containment is equality) and of 02b140 multi-remove-all (the relative complement of the
query in the host is empty exactly when containment holds). Fail-closed: either value not
declared List yields `NotAList`; either token not matching the List shape yields
`MalformedList` (unreachable for values built via `AmiParameterValueV1::try_new`, kept
defensive instead of panicking). An independent Python reference replicates the containment rule
over 4 test cases.

## Result

- 6 Rust unit tests green (sub-multiset contained, count exceeded, missing item, equal values,
  non-list, spacing canonicalized).
- Cross-check: 4 test cases (sub-multiset, count exceeded, missing item, non-list) driven
  through product runner `p4b_02b153_parameter_list_contains_multiset_runner`; independent
  Python reference matches 100% on booleans and error keys; 4/4 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b153_parameter_list_contains_multiset.py` + 6 tests; crosscheck
  evidence `docs/baselines/p4b-02b153-parameter-list-contains-multiset-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b153-parameter-list-contains-multiset-stage.v1.yaml`; source map
  `p4b-02b153-mit-source-map.v1.yaml`.
- PLAN **P4B-02b153**; ledger note/gate P4B-02; coverage gates 322 -> 323.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Checks multiset containment on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
