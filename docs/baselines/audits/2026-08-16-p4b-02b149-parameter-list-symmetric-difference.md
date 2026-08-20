# P4B-02b149 Parameter List Symmetric Difference Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b149 (symmetric difference on validated AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_symmetric_difference_v1.rs` in `sipi-ami-text`:
`list_symmetric_difference_v1` computes the symmetric difference of two validated List-typed
`AmiParameterValueV1` values under the P4B-02b1 list rule (`(item, item, ...)`, items trimmed,
non-empty): returns the canonical list token whose items are the trimmed items of the left value
that equal no right value item followed by the trimmed items of the right value that equal no
left value item (raw byte equality, per the P4B-02b0 raw-byte binding; each side in its own
order, duplicates preserved). This is the exclusive companion of 02b148 intersection (a list
equals the join of its intersection and symmetric difference with another list). Fail-closed:
either value not declared List yields `NotAList`; either token not matching the List shape
yields `MalformedList` (unreachable for values built via `AmiParameterValueV1::try_new`, kept
defensive instead of panicking). An empty symmetric difference yields the structurally empty
token `()` (not a valid 02b1 List value; the operation is total on the token level and does not
re-validate, mirroring 02b100 sole-item removal). An independent Python reference replicates the
exclusive rule over 4 test cases.

## Result

- 6 Rust unit tests green (symmetric difference, duplicates per side, equal values empty,
  disjoint full join, non-list, spacing canonicalized).
- Cross-check: 4 test cases (symmetric difference, duplicates, equal values, non-list) driven
  through product runner `p4b_02b149_parameter_list_symmetric_difference_runner`; independent
  Python reference matches 100% on tokens and error keys; 4/4 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b149_parameter_list_symmetric_difference.py` + 6 tests; crosscheck
  evidence `docs/baselines/p4b-02b149-parameter-list-symmetric-difference-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b149-parameter-list-symmetric-difference-stage.v1.yaml`; source map
  `p4b-02b149-mit-source-map.v1.yaml`.
- PLAN **P4B-02b149**; ledger note/gate P4B-02; coverage gates 318 -> 319.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Computes symmetric differences on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
