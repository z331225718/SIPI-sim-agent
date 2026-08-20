# P4B-02b151 Parameter List Relative Complement Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b151 (relative complement on validated AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_relative_complement_v1.rs` in `sipi-ami-text`:
`list_relative_complement_v1` computes the relative complement (set difference) of two
validated List-typed `AmiParameterValueV1` values under the P4B-02b1 list rule
(`(item, item, ...)`, items trimmed, non-empty): returns the canonical list token whose items
are the trimmed items of the left value that equal no right value item (raw byte equality, per
the P4B-02b0 raw-byte binding; left order, duplicates preserved). This is the one-sided
companion of 02b149 symmetric difference and the difference side of the 02b150 union identity
(union = relative complement + intersection). Fail-closed: either value not declared List yields
`NotAList`; either token not matching the List shape yields `MalformedList` (unreachable for
values built via `AmiParameterValueV1::try_new`, kept defensive instead of panicking). An empty
relative complement yields the structurally empty token `()` (not a valid 02b1 List value; the
operation is total on the token level and does not re-validate, mirroring 02b100 sole-item
removal). An independent Python reference replicates the difference rule over 4 test cases.

## Result

- 6 Rust unit tests green (relative complement, duplicates preserved, equal values empty,
  disjoint full left, non-list, spacing canonicalized).
- Cross-check: 4 test cases (relative complement, duplicates, equal values, non-list) driven
  through product runner `p4b_02b151_parameter_list_relative_complement_runner`; independent
  Python reference matches 100% on tokens and error keys; 4/4 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b151_parameter_list_relative_complement.py` + 6 tests; crosscheck
  evidence `docs/baselines/p4b-02b151-parameter-list-relative-complement-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b151-parameter-list-relative-complement-stage.v1.yaml`; source map
  `p4b-02b151-mit-source-map.v1.yaml`.
- PLAN **P4B-02b151**; ledger note/gate P4B-02; coverage gates 320 -> 321.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Computes relative complements on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
