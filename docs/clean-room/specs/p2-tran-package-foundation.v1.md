# P2 TRAN Package Foundation Specification v1

## Scope

This specification establishes the project-owned Rust package boundary
`crates/sipi-tran`. It does not specify a circuit representation, netlist
syntax, device model, solver, initial condition, time integration, sampling,
measurement, unit convention, or error taxonomy.

## Allowed Materials

The implementation may use only this independently authored specification and
project-authored Rust workspace metadata. It must not consume legacy circuit
source, external engines, model files, fixtures, oracle outputs, or a legacy
profile as implementation input.

## Observable Behavior

The crate is a `publish = false`, std-only workspace member. Its only public
observable declaration is an explicit `"unsupported"` foundation status. The
CLI remains the existing unsupported capability surface and does not route to
this crate.

## Non-Claims

This package boundary does not implement or select a TRAN API, parser, solver,
algorithm, numerical result, legacy-example comparison, default route, or
platform certification. It does not promote any `sipi-circuit` source file or
establish clean-room completion, release eligibility, or MIT/legal approval.
