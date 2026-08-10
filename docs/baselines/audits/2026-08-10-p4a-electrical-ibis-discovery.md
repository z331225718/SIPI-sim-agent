# P4A Electrical and IBIS Discovery Audit

## Scope

Independent Orca review of `a2057d5` (`P4A-01c`), covering the differential
electrical-load candidate and bounded local/public IBIS discovery record.

## Result

Orca message `msg_c1077af5a204` reported **0 P1 / 0 P2**.

The reviewer verified that the 100 ohm resistor is limited to the `P`-to-`N`
connection; the 1 pF Cload has no selected placement, reference net, solver,
CLI, or acceptance claim; `example_rx` stays oracle-only with its declared
Windows x64 DLL-name blocker; `minimal.ibs` remains synthetic-test-only; and
the public IBIS entry is only an unfetched, unlicensed discovery lead.

## Accepted Boundary

`P4A-01c` is accepted as a discovery/ambiguity preflight. It does not complete
an electrical-load profile. The next required owner decision is the explicit
1 pF placement: `across_pair`, `each_leg_to_reference` with a named reference,
or `total_differential_equivalent`. A stimulus, observable, and comparison
contract remain required after that decision.

## Verification

- `tools/verify_p4a_electrical_ibis_discovery.py`
- `tools/test_verify_p4a_electrical_ibis_discovery.py` (3 tests)
- product-boundary, clean-room-register, release-license-preflight, and Rust
  candidate-source-map verifiers

All listed checks passed before review. No external assets were copied, and no
runtime or parser capability was added.
