# P2 RC Pulse Acceptance Contract Specification v1

## Scope

This specification defines a governance record for the user-selected external
RC pulse TRAN profile. It fixes the external Git-object identity and the
limited intended observables: the `.tran` time axis, `v(in)`, and `v(out)`.
It does not define an input syntax, circuit representation, solver, numerical
method, tolerance, or product API.

## Boundary

The selected deck is an external-only oracle asset. It may be materialized only
by an observer or comparator in a worktree-external verification lane. It must
not be copied into this repository, product tests, product schemas, or the
implementer material set. A product implementation must use separately
authored request data and may never fall back to the external engine or deck.

## Required Decision State

Until the owner fixes sampling alignment, time tolerance, voltage tolerances,
initial-condition policy, and the oracle environment, the contract is
`blocked_missing_tolerance` and `acceptance_ready: false`. A verifier must
reject an accepted or passed conclusion while in this state.

## Non-Claims

This contract does not certify TRAN support, same-configuration numerical
parity, netlist compatibility, clean-room completion, redistribution rights,
or release readiness.
