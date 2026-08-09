# P2-02b RC Pulse Acceptance Contract Audit

Date: 2026-08-10

## Slice

Commit `05583cb` records the user-selected required TRAN profile as the
external Git object `agent-spice@2cc92316:native/AgentSpice.Engine/fixtures/rc.cir`.
The contract binds canonical origin, commit, tree, blob, and content SHA-256.
It allows only `.tran` time-axis, `v(in)`, and `v(out)` observables; OP, AC,
other nodes, measurements, netlist compatibility, and engine routing are
explicitly out of scope.

The source deck remains `external_only`. No product parser, fixture copy,
engine fallback, numerical implementation, or comparison output is introduced.
The acceptance state is deliberately `blocked_missing_tolerance`: sampling
alignment, time and voltage tolerances, initial-condition policy, and oracle
environment remain owner inputs. `--require-ready` therefore rejects the
contract rather than emitting an acceptance conclusion.

## Verification

- The external Git-object verifier passed against the fixed source anchor.
- Its `--require-ready` lane rejected the pending contract as required.
- Focused fail-closed tests passed; the Python tool suite reports 116 passing
  tests.
- Product-boundary, clean-room-register, release-license-preflight,
  Rust-candidate-source-map, and existing candidate-profile verifiers remain
  valid and provisional.

## Independent Audit

OMP request `msg_eff1656c8a1a` reviewed the committed slice. Conclusion
`msg_27e38dbca571`: 0 P1 / 0 P2.

## Scope Limits

This freezes a required external profile identity and its missing-parameter
gate only. It does not approve a tolerance, execute an oracle, implement
TRAN, establish parity, accept a result, promote `sipi-circuit`, or grant
clean-room, release, redistribution, or platform-certification status.
