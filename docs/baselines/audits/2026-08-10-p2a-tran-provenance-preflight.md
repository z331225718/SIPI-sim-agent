# P2-01 TRAN Provenance Preflight Audit

Date: 2026-08-10

## Slice

Commit `e7fbfd4` adds a Git-object-only provenance, Cargo dependency, and
NOTICE preflight for the current `native/crates/sipi-circuit` candidate. It
anchors the target snapshot at `c323425d70f62dec5c532d3fd83e3f547e5623d9`
and the external observer source at
`agent-spice@2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5`.

The named source anchor has no `native/crates/sipi-circuit` tree. Therefore
the generated inventory classifies all 29 target paths as
`quarantine/unknown` with `source_path_absent_at_anchor`; it creates no
direct-source or clean-room promotion. The preflight records the source
LICENSE Git object and scoped NOTICE absence, plus exact Cargo.toml/Cargo.lock
object metadata and pending release-input/NOTICE actions for observed direct
dependencies.

## Verification

- The preflight verifier completed against the fixed source Git objects with
  `status=preflight_passed`, `direct=0`, `unknown=29`, and
  `source_native_tree_status=absent_at_commit`.
- The Python tool suite reports 113 passing tests.
- Rust workspace fmt, tests, and clippy with warnings denied passed.
- Product-boundary, clean-room-register, release-license-preflight, and
  Rust-candidate-source-map verifiers remain valid and provisional.

## Independent Audit

OMP request `msg_84b48daacb55` reviewed the committed slice. Conclusion
`msg_be9b696d8678`: 0 P1 / 0 P2.

## Scope Limits

This is an observer-side metadata preflight only. It neither copies external
source nor decides licensing, proves clean-room status, promotes a candidate,
implements a TRAN solver, runs a TRAN example, establishes numerical parity,
or grants release readiness. P2-02 and later require a user-confirmed TRAN
profile and separate clean-room/source acceptance evidence.
