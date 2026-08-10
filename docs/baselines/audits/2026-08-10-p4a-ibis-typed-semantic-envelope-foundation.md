# P4A IBIS Typed Semantic Envelope Foundation Audit

## Scope

Commit `456c117` adds a product-owned typed semantic envelope above the
existing bounded structural parser. It operates only on an already parsed
document and introduces no file, external asset, profile, electrical, or AMI
runtime path.

## Independent Audit

Orca reviewer message `msg_d3f625cfc344` concludes **0 P1 / 0 P2**.

The reviewer confirmed that the envelope recognizes only lexical document
versions, component and model declarations, a `Model_type` section role,
unknown `Other` sections, and explicit section-block ownership. It has no
IBIS revision allowlist or selected external selector. Required-keyword profile
rules explicitly remain unavailable.

## Evidence

- `crates/sipi-ibis/src/lib.rs` (8 unit tests)
- `docs/clean-room/specs/p4a-ibis-typed-semantic-envelope-foundation.v1.md`
- `cargo fmt --manifest-path crates/sipi-ibis/Cargo.toml -- --check`
- `cargo test -p sipi-ibis`
- `cargo clippy -p sipi-ibis --all-targets -- -D warnings`
- P0 product-boundary, clean-room-register, release-license-preflight, and
  Rust candidate-source-map verifiers

## Accepted Boundary

This is a typed semantic-envelope and diagnostic foundation only. It does not
provide IBIS electrical behavior, parser compatibility, a selected pure-IBIS
profile, required-keyword rules, PVT/package/table semantics, AMI composition,
or a runtime/CLI capability. The external asset remains external-only and
requires an owner-selected semantic and acceptance charter before comparison.
