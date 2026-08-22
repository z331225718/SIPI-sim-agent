# Upstream CLI Integration Audit

Date: 2026-08-22

The unified `sipi` CLI now exposes the fifteen pinned workflows from
Agent-Spice, PyBERT, and Agent-COM through exact `upstream <repository>
<workflow> --stdin` routes. Requests use the versioned
`sipi.upstream-migration-request.v1` discriminator and each route is listed
individually in the command manifest and protocol catalog.

This is an integration boundary, not a Rust numerical replacement. The
adapter crates remain the owners of process supervision, upstream argument
construction, bounded output and artifact custody. The CLI emits only the
pinned contract source, an explicit `runtime_identity.attestation =
not_performed`, exit, backend-selection, and artifact metadata. The
caller-supplied launcher is not asserted to contain the pinned Git bytes.
Child stdout/stderr and artifact payloads are deliberately omitted.

The route set is frozen to the six Agent-Spice, five PyBERT, and four
Agent-COM workflows recorded in the active upstream inventory. Unknown
workflow names fail closed. `sim-auto` reports the selection recorded by its
upstream artifact; the CLI does not choose or silently fall back to a backend.
The request schema and protocol catalog use repository-specific discriminated
bindings: Agent-Spice requires an interpreter and argument vector, PyBERT
requires an executable and typed input, and Agent-COM requires both executable
and interpreter plus typed input.

Focused coverage verifies the fifteen manifest rows, one callable route for
each source repository, visible `sim-auto` selection, unknown-route rejection,
and machine-only non-zero/timeout diagnostics. The CLI rejects unknown
top-level or route-inapplicable fields, keeps caller limits at adapter hard
defaults, rejects cancellation markers on routes that cannot consume them,
and admits only canonical existing roots plus future output directories inside
the declared artifact root.

The test-only upstream fake is isolated by an empty Cargo feature,
`test-support = []`. Both the `sipi-upstream-fake` binary and the
`upstream_migration` integration test declare the exact fixture gate
`required-features = ["test-support"]`. A normal product build therefore does
not compile or publish the fake launcher, while the focused integration test
must opt in explicitly.

An Agent-COM comparison mismatch is a typed comparison result, not a transport
failure: the product command succeeds in carrying the response, while its JSON
body records `comparison.matched = false` and upstream `exit.code = 3` with
`exit.success = false`. Malformed or missing comparison reports are protocol
failures and other non-zero upstream exits remain transport failures. No product
capability, numerical acceptance, release readiness, or Rust parity claim is made.

The evidence gate binds this audit and the exact CLI source files by SHA-256.
That binding is intentionally separate from the upstream source identities:
the upstream repositories remain pinned to their migration inventory, while
the local CLI route implementation is verified against the checked-in files.
