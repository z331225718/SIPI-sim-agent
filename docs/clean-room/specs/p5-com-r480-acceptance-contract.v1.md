# P5 COM R480 Acceptance Contract v1

## Scope

This project-owned record freezes `com-r480-envelope-v1` as a user-selected
external-oracle comparison profile. It defines only the product-facing
evidence families that a later clean-room Rust implementation must emit:
normalized input identity, channel-role selection evidence, equalizer-selection
evidence, PDF axes/density, and scalar COM, ERL, and TDILN metrics in dB.

## Clean-Room Boundary

The historical R480 envelope, MATLAB source, workbooks, and fixture data are
external quarantine. They may be materialized only by an observer or
comparator in a worktree-external, controlled environment. They are prohibited
as product source, product input, product test fixture, release asset, runtime
dependency, or fallback. The Rust implementation must receive a separately
authored product contract and must not duplicate a legacy wire API merely to
make comparison easier.

## Reference Gate

The authoritative reference is deliberately `missing`. Exact normalized input,
oracle runtime identity, a reference metric-bundle hash, and tolerance/alignment
policy must all be present under external custody before any comparison can
start. The comparison gate is fail-closed while any item is absent; neither a
new golden nor a product self-comparison may substitute for it.

## Non-Claims

This contract does not implement COM, freeze MATLAB behavior, grant any asset
redistribution right, establish numerical parity, or enable a CLI/default
route. It records a required comparison obligation and its current evidence
gap only.
