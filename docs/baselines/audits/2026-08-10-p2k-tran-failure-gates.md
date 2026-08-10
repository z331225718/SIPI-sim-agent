# P2-07 TRAN Failure Gates

Commits `104b988`, `55c6edc`, and `d332178` close the applicable failure gates
for the sole `tran-rc-pulse-v1` product request.

- The solver observes its cooperative `RunContext` at entry, integration
  breakpoints, and result construction. A pre-cancelled context returns no
  result.
- The CLI reserves bounded request/output bytes before simulation. A low
  explicit accounting budget fails with exit code `5` before any success
  artifact can be published. This is an application-accounted-byte limit, not
  RSS/OOM or managed-process containment.
- A process-level second invocation sends the full request again to the same
  artifact root and id. It gets the stable failed JSON/NDJSON protocol and
  exit code `5`; the first success manifest, result, and provenance remain
  byte-identical.
- Unknown request fields are contract-rejected. Unsupported devices and
  nonconvergence are not applicable to this closed one-topology, linear,
  fixed-step profile and are not claimed as implemented gates.

Verification: `cargo fmt --all -- --check`, `cargo test --workspace --locked`
(48 tests), `cargo clippy --workspace --all-targets --locked -- -D warnings`,
and all four P0 verifiers passed.

OMP request `msg_56320cfff433`; conclusion `msg_ec2e9f130e83`: **0 P1 / 0 P2**.
The auditor also confirmed the scope does not include `uv.lock`.

## Non-Claims

This acceptance does not provide hard timeout or kill semantics, RSS/OOM
protection, nonlinear convergence handling, arbitrary-device support, generic
SPICE parsing, or cross-platform certification.
