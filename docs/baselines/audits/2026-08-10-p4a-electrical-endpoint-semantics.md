# P4A Electrical Endpoint Semantics Audit

## Scope

Independent Orca review of `93bf58b` (`P4A-01d`), which records the selected
per-leg electrical-load topology without adding a solver or runtime path.

## Result

Orca message `msg_c9482356ce63` reported **0 P1 / 0 P2**.

The review confirmed exact `P/N/REF` terminal roles; the 100 ohm `P-N`
resistor; separate 1 pF `P-REF` and `N-REF` capacitors; no implicit global
ground/node-zero mapping; and no substitution with a total differential
capacitance. Across-pair capacitance and single-ended channel grammar remain
planned, independent capabilities.

## Accepted Boundary

`P4A-01d` is accepted as a selected topology contract only. It remains
`selected_pending_reference_and_acceptance_policy`: `REF` must be bound to a
particular channel return/reference, and the stimulus, timebase/initial state,
observable/tolerance, and acceptance evidence must be frozen before a solver
or required profile may be introduced.

## Verification

- `tools/verify_p4a_electrical_endpoint_semantic_contract.py`
- `tools/test_verify_p4a_electrical_endpoint_semantic_contract.py` (3 tests)
- product-boundary, clean-room-register, release-license-preflight, and Rust
  candidate-source-map verifiers

All checks passed. No external asset, parser, termination solver, CLI route, or
IBIS/AMI composition was added.
