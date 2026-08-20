# P4B-02b132 Parameter List Interleave Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b132 (position-wise interleave on validated AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_interleave_v1.rs` in `sipi-ami-text`:
`interleave_parameter_list_values_v1` interleaves the trimmed items of two validated
List-typed `AmiParameterValueV1` values under the P4B-02b1 list rule (`(item, item, ...)`,
items trimmed, non-empty): returns the canonical list token whose items alternate position-wise
between the two values (left item at position i, then right item at position i, for i = 0, 1,
...); once the shorter value is exhausted, the longer value's remaining items are appended in
order (zip-with-padding semantics). This is the position-wise companion of 02b106 join (which
concatenates) and of 02b103 swap. Fail-closed: either value not declared List yields
`NotAList`; either token not matching the List shape yields `MalformedList` (unreachable for
values built via `AmiParameterValueV1::try_new`, kept defensive instead of panicking). An
independent Python reference replicates the interleave rule over 4 test cases.

## Result

- 6 Rust unit tests green (equal lengths, left longer, right longer, single items, non-list,
  spacing canonicalized).
- Cross-check: 4 test cases (equal lengths, left longer, right longer, non-list) driven through
  product runner `p4b_02b132_parameter_list_interleave_runner`; independent Python reference
  matches 100% on tokens and error keys; 4/4 product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b132_parameter_list_interleave.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b132-parameter-list-interleave-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b132-parameter-list-interleave-stage.v1.yaml`; source map
  `p4b-02b132-mit-source-map.v1.yaml`.
- PLAN **P4B-02b132**; ledger note/gate P4B-02; coverage gates 301 -> 302.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Interleaves list tokens on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
