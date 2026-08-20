# P2-02 Solver-Singleton Invariant Gate

P2-02 requires the accepted TRAN kernel to converge into the `sipi-tran`
library: the CLI and pipeline may only call the library API and must not
copy or re-implement the solver. The library convergence itself was
completed by P2-02c/d (sole one-node RC/PULSE core) and P2-02e/f (CLI
routes calling that core). This audit records the mechanical gate that
freezes the "no copied solver" invariant going forward.

## Delivered Gate

- `tools/verify_p2_02_solver_singleton.py` — verifier for schema
  `sipi.p2-02.solver-singleton.v1`. It fails closed if: any of the 9
  solver symbols (`simulate_rc_pulse`, `simulate_rc_pulse_with_context`,
  `simulate_one_node_rc_pulse`, `simulate_one_node_rc_pulse_with_context`,
  `simulate_one_node_rc_pulse_checked`, `simulate_one_node_rc_pwl`,
  `simulate_one_node_rc_pwl_with_context`, `simulate_one_node_rc_pwl_checked`,
  `backward_euler_step`) is defined anywhere other than
  `crates/sipi-tran/src/lib.rs`, or is defined more than once there; if
  any consumer crate (`sipi-cli`, `sipi-pipeline`) defines a solver
  symbol (copied solver); if any consumer reference to a solver symbol
  lacks an explicit `use sipi_tran::{...}` import in the same file; or
  if the comparator harness loses its `rc-pulse-harness` required-feature
  gate or its comparator-only role comment.
- `tools/test_verify_p2_02_solver_singleton.py` — 7 tests: live invariant,
  per-symbol single definition in the library, no consumer definitions,
  multi-line and single-line import detection, harness feature gate, and
  consumer-definition rejection.

## Verification

`python -B tools/verify_p2_02_solver_singleton.py` returned
`{"schema": "sipi.p2-02.solver-singleton.v1", "solver_symbols": 9, "valid": true}`.
`python -B -m unittest tools.test_verify_p2_02_solver_singleton` passed 7/7.
The current consumer surface was inspected: `sipi-cli` and `sipi-pipeline`
reference solver symbols only through `use sipi_tran::{...}` imports, and
`crates/sipi-tran/src/bin/sipi_tran_rc_pulse_harness.rs` is gated behind
`required-features = ["rc-pulse-harness"]`.

## Artifact Hashes (SHA-256)

- verifier: `A4B7708217F51ABA8FB46137DCE0808F312415E14ACA2B93E7B8382280C0D137`
- tests: `F21BE8DFBCCFCFA956F91FE51ACB81A8B089F8E70DAD85A4BEE2079C26258EDA`

## Scope and Non-Claims

- This gate records an engineering invariant only. It does not accept a
  TRAN profile, certify a solver, change numerical semantics, or replace
  the remaining P2-03/P2-04 semantic freezing tasks.
- The harness binary remains comparator-only and is not wired into the
  product CLI; this gate keeps it that way.
