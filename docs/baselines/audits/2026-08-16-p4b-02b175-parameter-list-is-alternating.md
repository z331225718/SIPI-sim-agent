# P4B-02b175 Parameter List Is-Alternating Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b175 (value-level alternating check on AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_is_alternating_v1.rs` in `sipi-ami-text`:
`parameter_list_is_alternating_v1` returns whether no two adjacent trimmed items of a
validated List-typed `AmiParameterValueV1` value are equal under the P4B-02b1 list rule
(`(item, item, ...)`, items trimmed, non-empty): every adjacent pair `(i, i + 1)` differs
by raw byte equality (per the P4B-02b0 raw-byte binding); equivalently the 02b172 adjacent
change count equals `len - 1` and every run has length 1. A single-item list is trivially
alternating. This is the alternating companion of 02b160 all-equal (the negation direction:
an all-equal list of length >= 2 is never alternating) and of 02b168 run count (alternating
if and only if runs == len). Fail-closed: the value not declared List yields `NotAList`; the
token not matching the List shape yields `MalformedList` (unreachable for values built via
`AmiParameterValueV1::try_new`, kept defensive instead of panicking). An independent Python
reference replicates the rule over 4 test cases.

## Result

- 6 Rust unit tests green (alternating true, repeated adjacent false, single item trivial,
  all equal long false, spacing canonicalized, non-list).
- Cross-check: 4 test cases (alternating, repeated adjacent, single item, non-list) driven
  through product runner `p4b_02b175_parameter_list_is_alternating_runner`; independent
  Python reference matches 100% on booleans and error keys; 4/4 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b175_parameter_list_is_alternating.py` + 6 tests; crosscheck
  evidence `docs/baselines/p4b-02b175-parameter-list-is-alternating-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b175-parameter-list-is-alternating-stage.v1.yaml`; source map
  `p4b-02b175-mit-source-map.v1.yaml`.
- PLAN **P4B-02b175**; ledger note/gate P4B-02; coverage gates 344 -> 345.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Checks is-alternating on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
