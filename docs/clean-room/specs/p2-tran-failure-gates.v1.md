# P2 TRAN Failure Gates Specification v1

## Scope

This specification defines fail-closed behavior for the implemented
`tran-rc-pulse-v1` product request only. It does not introduce netlist text,
device dispatch, nonlinear solving, or an additional numerical resolver.

## Cooperative Execution

The RC/PULSE library must use the caller-provided `RunContext` at entry, each
integration breakpoint, and before it constructs its final result. A cancelled
or expired context must return a runtime failure and must not yield a result.
This is cooperative cancellation and deadline observation only; it is not
process preemption or a hard wall-clock guarantee.

Before simulation, the CLI must account its bounded request and prospective
output bytes against the explicit run policy. Exceeding that limit must return
an operational failure before a success artifact can be published. The limit
is an application-accounted-byte budget, not RSS, allocator, or OOM isolation.

## Artifact Publication

The CLI publishes only through the product artifact primitive. Reusing an
existing artifact identifier at the same root must fail with exit code `5`, a
single failed response envelope, and an `operational_failure` diagnostic. The
previous success manifest and payloads must remain byte-identical; no new
success artifact may be published.

## Applicability Matrix

| Case | v1 state | Reason |
| --- | --- | --- |
| cancellation | applicable | The fixed solver has cooperative checkpoints. |
| deadline observation | applicable | `RunContext` checks its explicit deadline at checkpoints. |
| accounted output budget | applicable | The CLI reserves bounded request/output bytes before work. |
| artifact publication failure | applicable | The immutable artifact primitive rejects an existing destination. |
| unsupported device | not applicable | The request has no device-dispatch or topology-union surface; unknown fields are contract-rejected. |
| nonconvergence | not applicable | The fixed linear backward-Euler RC profile has no iterative solver or convergence state. |
| hard RSS/OOM or kill | not applicable | This in-process cooperative runtime has no managed process isolation. |

## Non-Claims

These gates do not claim nonlinearity handling, arbitrary-device rejection,
general SPICE/netlist support, hard resource containment, cross-platform
certification, or accuracy beyond the separately scoped RC/PULSE acceptance
profile.
