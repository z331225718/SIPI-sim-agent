# P5-02i Warning-Call Observation — Audit Record

- Date (UTC): 2026-08-16
- Scope: P5-02 sub-slice 02i (warning calls in the r4.80 source)
- Status: delivered and mechanically bound; product warning contract
  pending behavior profile

## Method

External-only scan of the authorized MATLAB r4.80 source for warning(
...), fprintf('<strong> Warning...'), and msgbox(...,'warning') call
sites; each recorded with line number, kind, and message text; hash-bound
to the registry.

## Result

- 25 warning-class call sites observed (e.g. MLSE truncation failure,
  anti-causal channel response, reference impedance renormalization,
  INC_PACKAGE=0 support limitation).
- Observation `docs/baselines/p5-r480-warning-observation.v1.yaml`.

## Scope discipline

The observation is the oracle basis for a future product warning
contract; it is not itself the contract, and trigger conditions are not
derived (non_claims).

## Binding

- Verifier `verify_p5_02i_warning_observation.py` + 5 tests;
- PLAN **P5-02i**; ledger note/gate; coverage gates 80 -> 81.
