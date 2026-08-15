# P7 BCryptPrimitives/ProcessPrng Preflight

This audit records a read-only, external-only preflight for the static PE rejection diagnosed in P7-06d. It does not revise the layout allowlist or advance the P7 candidate chain.

The two independently materialized `b775dde` candidate executables were identical and each imported exactly one named symbol, `ProcessPrng`, from `bcryptprimitives.dll`, with no delay-import directory. The same-host System32-only `version --json` smoke succeeded against a valid Microsoft Windows-signed `bcryptprimitives.dll`.

The observation binds the official Microsoft ProcessPrng API requirements, the Rust Windows MSVC target requirements, and the API-set loader documentation. It records Rust standard-library linkage support only; it does not claim a product callsite provenance, cross-version/device loader closure, fresh-machine evidence, security review, or release readiness.

The authoritative preflight evidence is [p7-bcryptprimitives-processprng-preflight.v1.yaml](../p7-bcryptprimitives-processprng-preflight.v1.yaml). Any additive layout-policy revision requires a separate decision and fresh P7 chain replay.

## OMP Audit

The existing OMP reviewer terminal `term_fa7831f5-ec22-4b3d-8737-25a919226b8b` reviewed the staged P7-06e scope. Result: 0 High / 0 Critical / 0 Medium findings. The review confirmed the name-import, authority-boundary, toolchain-provenance, no-promotion, external-custody, and P0 inventory constraints.
