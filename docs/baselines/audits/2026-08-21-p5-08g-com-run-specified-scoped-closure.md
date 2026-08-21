# P5-08g specified COM artifact scoped closure

P5-08g records an additive child closure for the owner decision `D6=A`.
The live route is `com run-artifact`, not the historical `com run` route.
The route accepts a caller-owned explicit parameter partition, one sealed
`pulse.f64le` payload identified by artifact id and manifest SHA-256, and a
caller-owned output root/id. It publishes one immutable `result.json` with a
16 KiB limit after bounded local execution.

The closure is mechanical and local. The route reads at most 65537 bytes, then
performs a lexical preflight before serde deserialization: total encoded bytes,
JSON container count, per-container item count, nesting depth, and string bytes
are all bounded. The request contract then rejects unknown fields, values
outside the consumed set, provided/default overlap, duplicate unconsumed keys,
invalid identities, and non-finite parameter values. The execution source
calls `consume_exact_verified_v1` for the exact pulse file,
rechecks the sealed manifest and payload hash through the existing artifact
primitive, and uses `publish_new` for the result. The result projection is an
allowlisted metadata/scalar envelope: it contains no caller filesystem path,
raw pulse bytes, or waveform array.

The frozen threat model is the existing local artifact v1 model: no hostile
concurrent writer is assumed. This record therefore does not assert hostile
writer safety, external provenance, external ownership, signatures,
authoritative COM profile/oracle, acceptance, Agent-COM parity, IEEE
certification, or release evidence. P5-02 and P5-06 remain unchanged.

The exact specified/non-oracle route is scoped closed, but generalized P5-08
remains open. A child closure is required because the full item still needs
authoritative profile/oracle and acceptance evidence. The verifier binds the
live command descriptor, protocol catalog route, request schema source and
generated schema, execution/parameter/artifact sources, existing P5-08e/f
records, and the focused Rust test markers. Mutation tests fail closed on
scope promotion, threat-model expansion, budget/identity drift, source or
schema drift, and audit tampering.
